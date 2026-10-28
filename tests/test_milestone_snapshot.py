"""A5e: an unchanged milestone keeps its done attempt across a plan revision.

One smoke test per criterion (C1 selection, C2 actions, C3 amendment, C4 label) plus the invariant the change can
break (data loss: the carried attempt's exported result, its worktree and its result commit stay reachable and
merge under the new revision). Everything runs the real fixture project, the fixture driver and the delivery
service both UIs build.

Interpretations (the reviewers never see the worker's summary; none of them waives a stated requirement):
- The brief's C1/C3 examples need M1 and M2 to be independent: the fixture plan's own M2 depends on M1, so beside
  M1's unmerged attempt M2 would read `ждёт M1` instead of `ready` and could not start fresh. `proposal()` clears
  that dependency (two independent milestones still validate) and adds M3 depending on M1, the dependent of C2's
  example that stops waiting once M1 is integrated; `change="M2"` edits M2's brief for revision 2.
- "Its last current-revision attempt (today)" and "the last older-revision record in store order" are the append
  order of `authority.state["runs"]`; the selection is `MilestoneRuns.current_record`.
- C2's "reachable from its row" is read as the brief states it: `Delivery.row` gives the carried attempt its token
  and `Delivery.resolve` accepts that token's older revision, so the merge/finish modal works; a carried row
  without a token (an integrated result) keeps today's plain-UI refusal.
"""

import unittest
from pathlib import Path
from unittest.mock import patch

from terminal_planner import live, milestone, planning, runs
from terminal_planner.authority import Blocked, decode
from terminal_planner.delivery import Delivery, Token
from terminal_planner.engine import FixtureEngine, fixture_proposal
from test_runs import ROLES, RunsTest


def proposal(change=None):
    """M1, M2 independent and M3 (depending on M1); `change` edits one milestone's brief for the next revision."""
    plan = fixture_proposal()
    plan["milestones"][1]["depends_on"] = []
    plan["requirements"].append({"id": "R3", "text": "Polish the result."})
    plan["milestones"].append({"id": "M3", "title": "Polish", "depends_on": ["M1"], "slices": [
        {"id": "S3", "title": "Polish", "requirements": ["R3"], "tasks": [
            {"id": "T3", "title": "Polish the result", "checks": ["Polish check"]}]}]})
    if change:
        found = next(m for m in plan["milestones"] if m["id"] == change)
        found["slices"][0]["tasks"][0]["title"] += " (changed)"
    return plan


class MilestoneSnapshotTests(RunsTest):
    def approve(self, authority, plan):
        with patch("terminal_planner.engine.fixture_proposal", return_value=plan):
            authority.begin("Next goal", ROLES, "fixture")
            self.propose(authority)
            authority.approve(authority.current["version"])

    def armed(self, authority):
        """The fixture controller and the delivery service over the same store, as both UIs build them."""
        controller = self.fixture_runs(authority)
        service = Delivery(authority, controller, planning.Planning(authority, controller, lambda *_: FixtureEngine()))
        return controller, service

    def exported(self, controller, milestone_id, revision=1):
        """One done attempt of `milestone_id`, exported: its result waits for the owner's merge."""
        r = controller.observe(controller.start(milestone_id, revision, ROLES))
        self.assertEqual(r["outcome"], "done")
        controller.finish(r)
        self.assertEqual((r["delivery"], runs.run_state(r)), ("awaiting_merge", "awaiting_merge"))
        return r

    def two_attempts_then_revised_m2(self, authority):
        """The brief's example state: M1 and M2 have an exported r1 attempt; r2 changes only M2's brief."""
        self.begin(authority)
        with patch("terminal_planner.engine.fixture_proposal", return_value=proposal()):
            self.propose(authority)
        authority.approve(1)
        controller, service = self.armed(authority)
        first, second = self.exported(controller, "M1"), self.exported(controller, "M2")
        self.approve(authority, proposal("M2"))
        return controller, service, first, second

    # C1 ---------------------------------------------------------------------------------------------------------

    def test_c1_the_selection_keeps_a_carried_awaiting_merge_attempt_under_the_new_revision(self):
        with self.fixture_authority() as authority:
            controller, service, first, second = self.two_attempts_then_revised_m2(authority)
            items = {item["id"]: item for item in controller.overview()}
            self.assertIs(items["M1"]["record"], first)
            self.assertTrue(items["M1"]["carried"])
            self.assertEqual(items["M1"]["state"], "awaiting_merge")
            self.assertEqual(Delivery.state_text(items["M1"]), "waiting for merge (r1)")
            # M2's brief changed: its older record is never its row's record (C3), so the row is ready.
            self.assertIsNone(items["M2"]["record"])
            self.assertEqual(items["M2"]["state"], "ready")
            self.assertEqual(items["M3"]["state"], "waiting")
            self.assertEqual(items["M3"]["waiting"], ["M1"])
            # One selection: Delivery.latest and what reads it (resolve, latest_only, journal_sections).
            self.assertIs(service.latest("M1"), first)
            self.assertIs(service.latest("M2"), None)
            self.assertIs(service.latest_only(first), first)
            self.assertIs(service.resolve(Token.of(first)), first)
            self.assertIn("Journal M1 (attempt 1):", service.journal_sections(authority.current))
            # plan_section shows the carried attempt: it no longer claims nothing was implemented.
            section = service.plan_section(authority.current)
            self.assertNotIn("Nothing has been implemented; this is only a plan.", section)
            self.assertTrue(section[0].startswith("Plan r2"))

    # C2 ---------------------------------------------------------------------------------------------------------

    def test_c2_the_carried_attempt_carries_todays_actions_and_other_old_records_stay_refused(self):
        with self.fixture_authority() as authority:
            controller, service, first, second = self.two_attempts_then_revised_m2(authority)
            # check_current passes for the carried attempt: finish/export and merge are reachable from its row.
            self.assertEqual(controller.check_current(first), authority.current)
            items = {item["id"]: item for item in controller.overview()}
            row = service.row(items["M1"])
            self.assertTrue(row.carried)
            self.assertEqual(row.token, Token.of(first))
            self.assertIs(service.resolve(row.token), first)
            # Data loss: the carried attempt's worktree, result commit and result branch are all still there.
            self.assertTrue(Path(first["worktree"]).is_dir())
            self.assertEqual(self.git("rev-parse", "refs/heads/" + first["result"]["branch"]).decode().strip(),
                             first["result"]["commit"])
            merged = service.merge(first)
            self.assertEqual(merged.kind, "integrated")
            items = {item["id"]: item for item in controller.overview()}
            self.assertEqual(items["M1"]["state"], "integrated")
            self.assertEqual(Delivery.state_text(items["M1"]), "merged %s (r1)" % self.head()[:7])
            self.assertEqual(items["M3"]["state"], "ready")  # the dependent stops waiting
            # Every other older record keeps today's refusal, text and family.
            self.assertEqual(service.merge(second).kind, "refused")  # the UI verdict, not an exception
            for call in (lambda: controller.check_current(second), lambda: controller.merge(second),
                         lambda: controller.check_followup(second)):
                with self.assertRaises(Blocked) as raised:
                    call()
                self.assertIn("Revision 1 is stale", str(raised.exception))
                self.assertEqual(raised.exception.family, "store.invalid")
            # check_current also passes the carried attempt, so check_followup needs its own guard (C2).
            with self.assertRaises(Blocked) as raised:
                controller.check_followup(first)
            self.assertIn("Revision 1 is stale", str(raised.exception))
            self.assertEqual(raised.exception.family, "store.invalid")

    def test_c2_a_carried_attempt_that_is_only_done_exports_under_the_new_revision(self):
        with self.fixture_authority() as authority:
            self.begin(authority)
            with patch("terminal_planner.engine.fixture_proposal", return_value=proposal()):
                self.propose(authority)
            authority.approve(1)
            controller, service = self.armed(authority)
            done = controller.observe(controller.start("M1", 1, ROLES))
            self.assertEqual((done["delivery"], runs.owner_actions(done)), ("none", ("finish",)))
            self.approve(authority, proposal("M2"))
            self.assertIs(controller.current_record("M1"), done)  # a done attempt is an awaiting_merge state
            self.assertEqual(runs.run_state(done), "awaiting_merge")
            exported = controller.finish(done)
            self.assertEqual((exported["delivery"], runs.run_state(exported)), ("awaiting_merge", "awaiting_merge"))
            self.assertIs(service.latest("M1"), done)
            self.assertEqual({item["id"]: item["state"] for item in controller.overview()}["M1"], "awaiting_merge")

    def test_c2_refresh_reconciles_a_carried_attempt_merged_by_hand_and_a_branch_reset(self):
        with self.fixture_authority() as authority:
            controller, service, first, second = self.two_attempts_then_revised_m2(authority)
            base = self.head()
            self.git("merge", "--no-ff", "--no-edit", "-m", "merged by hand", first["result"]["commit"])
            controller.refresh()
            self.assertEqual((first["delivery"], runs.run_state(first)), ("integrated", "integrated"))
            items = {item["id"]: item for item in controller.overview()}
            self.assertEqual(items["M1"]["state"], "integrated")
            self.assertEqual(items["M3"]["state"], "ready")
            # A branch reset takes the confirmation away again, exactly as for a current-revision result.
            self.git("reset", "--hard", base)
            controller.refresh()
            self.assertEqual(runs.run_state(first), "awaiting_merge")
            self.assertEqual(controller.waiting("M3"), ["M1"])

    # C3 ---------------------------------------------------------------------------------------------------------

    def test_c3_a_changed_milestone_starts_fresh_with_its_new_brief(self):
        with self.fixture_authority() as authority:
            controller, service, first, second = self.two_attempts_then_revised_m2(authority)
            # Its older attempts never show in its row (the older record is not the selection).
            self.assertIsNone({item["id"]: item for item in controller.overview()}["M2"]["record"])
            fresh = controller.observe(controller.start("M2", 2, ROLES))
            self.assertEqual((fresh["plan_revision"], fresh["attempt"]), (2, 1))
            baseline = decode((Path(fresh["worktree"]) / milestone.BASELINE).read_text())
            self.assertEqual(baseline, milestone.build_baseline(proposal("M2"), "M2", 2))
            self.assertEqual([task["title"] for task in baseline["tasks"]], ["Acceptance and code review (changed)"])

    # C4 ---------------------------------------------------------------------------------------------------------

    def test_c4_node_label_names_the_preflight_node(self):
        self.assertEqual(runs.node_label("preflight", "T1"), "pre-check")
        self.assertEqual(runs.node_label("empty_preflight", "T1"), live.ROLES["preflight"])
        manifest = {"tasks": [{"id": "T1", "status": "open"}], "progress": [], "amendments": []}
        statuses = [{"phase": "running", "activeExecutions": [{"node": "preflight", "execution": "e1"}]}]
        lines, _ = runs.activity(manifest, statuses)
        self.assertEqual(lines, ["pre-check"])


if __name__ == "__main__":
    unittest.main()
