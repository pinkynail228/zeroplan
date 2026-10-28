"""G1b-override: the owner approves a plan whose gate ended rejected, with a typed reason.

Real temporary Git repositories and the deterministic fixture engine; no provider, no network. The rule lives in
Authority, which reads the live configuration digest from its session-bound profile; the line UI only asks for the
reason."""

import copy
import inspect
import io
import json
import shutil
import unittest

from terminal_planner import authority as auth, cli
from terminal_planner.authority import Authority as RealAuthority, Blocked, canonical, digest
from terminal_planner.engine import FixtureEngine
from terminal_planner.runs import FixtureDriver
import test_process as tpr
import test_terminal_planner as tp
from test_terminal_planner import ROLES, ScriptedTerminal
from test_tui_planning import Planner

REASON = "The scope is intentional; the owner accepts the risk."


class V1Rejecting(FixtureEngine):
    """A version 1 review that ended rejected (the fixture never produces one by itself)."""

    def output(self, authority):
        output = super().output(authority)
        if output["schemaVersion"] == "1":
            output.update(planVerdict="rejected", planFindings="Fixture v1 rejection.")
        return output


class InvalidProposal(FixtureEngine):
    def output(self, authority):
        return dict(super().output(authority), proposal=canonical({"not": "a plan"}))


class OverrideCase(tpr.ProfileTest):
    def reset(self):
        shutil.rmtree(self.state, ignore_errors=True)
        self.state.mkdir(parents=True)

    def make(self, scenario="exhausted", engine=None, execution=2, approve=False):
        """A stored revision after one fixture review (the project's profile accepted first)."""
        self.accept_file()
        with self.app() as app:
            app.authority.begin("Goal", app.roles, "fixture", execution=execution)
            (engine or FixtureEngine(scenario)).proposal(app.authority, lambda _: None)
            if approve:
                app.planning.approve(app.authority.current["version"])

    def exhausted(self):
        self.reset()
        self.make()

    def raw(self):
        with self.app() as app:
            return app.authority.path.read_bytes()

    def refused(self, family, call=None, version=1):
        """`call(app)` (default: override with a valid reason) is refused with `family` and writes nothing."""
        with self.app() as app:
            before = app.authority.path.read_bytes()
            with self.assertRaises(Blocked) as raised:
                (call or (lambda a: a.planning.override(version, REASON)))(app)
            self.assertEqual(raised.exception.family, family, str(raised.exception))
            self.assertEqual(app.authority.path.read_bytes(), before)
            return str(raised.exception)

    def tamper(self, mutate):
        """Rewrite the stored current revision as the owner's file; returns the bytes written."""
        with self.app() as app:
            path = app.authority.path
        state = json.loads(path.read_text())
        mutate(state["revisions"][-1])
        path.write_bytes((canonical(state) + "\n").encode())

    def assert_invalid(self):
        with self.assertRaises(Blocked) as raised:
            with RealAuthority(self.state, self.project, fixture_id="test"):
                pass
        self.assertEqual(raised.exception.family, "store.invalid")


# O-1 -----------------------------------------------------------------------------------------------------------

class OverrideTests(OverrideCase):
    def test_o1_a_rejected_gate_is_approved_with_a_reason_and_the_evidence_stays(self):
        self.exhausted()
        with self.app() as app:
            before = copy.deepcopy(app.authority.current)
            self.assertEqual(before["status"], "review_exhausted")
            app.planning.override(1, "  " + REASON + "  ")
            current = app.authority.current
            self.assertEqual(current["status"], "approved")
            self.assertEqual(canonical(current["evidence"]), canonical(before["evidence"]))
            self.assertEqual(current["evidence"]["critic_verdict"], "rejected")
            self.assertEqual(current["proposal"], before["proposal"])
            self.assertEqual(current["override"], {"reason": REASON, "verdict": "rejected",
                                                   "evidence_digest": digest(before["evidence"])})
            self.assertEqual(current["approval"], auth.Authority.approval_identity(current))
            self.assertEqual(app.authority.state["revisions"][-1]["override"]["reason"], REASON)
        with self.app() as app:  # reloads and validates
            self.assertEqual(app.authority.current["status"], "approved")
            self.assertIn("approved despite the check", app.delivery.home().lines[1])

    def test_o1_milestone_start_works_for_an_overridden_plan(self):
        self.exhausted()
        with self.app() as app:
            app.planning.override(1, REASON)
        with self.app() as app:
            run = app.delivery.start(app.delivery.preview("M1", app.roles), app.roles)
            self.assertIsNotNone(run)
        runs = self.stored()["runs"]
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["milestone"] if "milestone" in runs[0] else "M1", "M1")

    def test_o1_the_digest_comes_from_the_bound_provider_not_the_caller(self):
        """R-2: the service passes no digest and no caller can supply one; Authority reads the session-bound
        profile itself, and the ordinary service path therefore still clears the gate digest."""
        self.exhausted()
        with self.app() as app:
            self.assertIs(app.authority.profile, app.planning.profile)
            # the public API carries no digest parameter a caller could use to disable or replace the provider
            self.assertEqual(list(inspect.signature(app.authority.approve).parameters), ["version"])
            self.assertEqual(list(inspect.signature(app.authority.override).parameters), ["version", "reason"])
            app.planning.override(1, REASON)
            self.assertEqual(app.authority.current["status"], "approved")


# O-2 -----------------------------------------------------------------------------------------------------------

class RefusalTests(OverrideCase):
    def test_o2_a_bad_reason_is_refused_and_writes_nothing(self):
        self.exhausted()
        for label, reason in (("empty", ""), ("blank", "   \t "), ("multiline", "first line\nsecond line"),
                              ("carriage", "first line\rsecond line"), ("9", "x" * 9), ("501", "y" * 501),
                              ("padded 9", "  " + "z" * 9 + "  "), ("control", "text with \x07 bell chars")):
            with self.subTest(label):
                self.refused("action.refused", lambda a, r=reason: a.planning.override(1, r))
        with self.app() as app:
            self.assertEqual(app.authority.current["status"], "review_exhausted")
            self.assertNotIn("override", app.authority.current)

    def test_o2_the_length_boundaries_are_ten_and_five_hundred_characters(self):
        for reason in ("x" * 10, "y" * 500, "  " + "z" * 10 + "\n"):
            with self.subTest(length=len(reason.strip())):
                self.exhausted()
                with self.app() as app:
                    app.planning.override(1, reason)
                    self.assertEqual(app.authority.current["override"]["reason"], reason.strip())
                    self.assertEqual(app.authority.current["status"], "approved")

    def test_o2_only_a_rejected_gate_of_the_current_revision_is_overridden(self):
        cases = {"proposed": lambda: self.make("accept"),
                 "approved": lambda: self.make("accept", approve=True),
                 "run_failed": self.failed, "proposal_invalid": lambda: self.make(engine=InvalidProposal())}
        for status, build in cases.items():
            with self.subTest(status):
                self.reset()
                build()
                with self.app() as app:
                    self.assertEqual(app.authority.current["status"], status)
                self.refused("action.refused")

    def failed(self):
        self.accept_file()
        with self.app() as app:
            planner = Planner()
            app.authority.begin("Goal", app.roles, "fixture")
            planner.receipt(app.authority)
            planner.fail(app.authority)

    def test_o2_a_wrong_version_is_refused(self):
        self.exhausted()
        self.refused("action.refused", version=2)

    def test_o2_a_version_one_revision_has_no_gate_to_override(self):
        self.reset()
        self.make(engine=V1Rejecting(), execution=1)
        with self.app() as app:
            current = app.authority.current
            self.assertEqual((current["status"], "execution" in current), ("review_exhausted", False))
            self.assertNotIn("override", app.planning.proposal(current).actions)
        self.refused("action.refused")

    def test_o2_a_moved_project_is_stale(self):
        self.exhausted()
        (self.project / "later.txt").write_text("later\n")
        self.git("add", "later.txt")
        self.git("commit", "-qm", "owner commit")
        self.refused("plan.stale")

    def test_rs2_a_stale_proposal_offers_no_approve_and_its_refusal_names_the_next_step(self):
        """RS2 C1 (regression): the project moved after planning, so the proposal's view offers no approve (revise
        is the way on) and a typed approve or override is refused with a «Next:» step, writing nothing."""
        self.reset()
        self.make("accept")
        with self.app() as app:
            self.assertIn("approve", app.planning.proposal(app.authority.current).actions)  # fresh: approve is offered
        (self.project / "later.txt").write_text("later\n")
        self.git("add", "later.txt")
        self.git("commit", "-qm", "owner commit")
        with self.app() as app:
            view = app.planning.proposal(app.authority.current)
            self.assertEqual(view.family, "plan.stale")
            self.assertNotIn("approve", view.actions)
            self.assertIn("revise", view.actions)
        text = self.refused("plan.stale", lambda a: a.planning.approve(1))
        self.assertIn("The project changed after planning", text)
        self.assertIn("Next: [r] revise", text)

    def test_o2_a_changed_live_configuration_is_gate_stale(self):
        self.rules("AGENTS.md", "one\n")
        self.exhausted()
        (self.project / "AGENTS.md").write_text("two\n")
        self.refused("plan.gate_stale")
        with self.app() as app:  # the owner's way on: revise, argue again
            self.assertEqual(app.authority.current["status"], "review_exhausted")

    def test_o2_a_changed_roles_file_is_gate_stale(self):
        self.save_roles({"planner": {"model": "other-model", "effort": "high"}})
        self.write({"limits": {"plan_rounds": 3}})
        self.exhausted()
        self.save_roles({"planner": {"model": "changed-model", "effort": "high"}})
        self.refused("plan.gate_stale")

    def test_o2_authority_itself_refuses_a_rejected_gate_with_a_changed_digest(self):
        """R-2: no caller argument is involved; the bound provider reports the drift and Authority refuses."""
        self.exhausted()
        with self.app() as app:
            before = app.authority.path.read_bytes()
            app.profile.live_digest = lambda: "0" * 64  # the session-bound provider itself reports a changed live config
            with self.assertRaises(Blocked) as raised:
                app.authority.override(1, REASON)
            self.assertEqual(raised.exception.family, "plan.gate_stale")
            self.assertEqual(app.authority.path.read_bytes(), before)
            with self.assertRaises(Blocked):  # the ordinary approval of the same revision is still refused
                app.planning.approve(1)


# R-2 (rel04-lifecycle-guard) -------------------------------------------------------------------------------------

class DigestProviderTests(OverrideCase):
    """R-2: approve/override read the live configuration digest from the session-bound profile, not from the caller.

    With no caller digest the base skipped the comparison entirely (`None` disables it); every refusal below
    therefore fails on the base at its own named assertion. `absence of zplan.process.json` is not an unprofiled
    session: a postponed profile is bound and its snapshot answers, so it can be refused like any other provider."""

    def proposed(self, scenario="accept"):
        self.reset()
        self.make(scenario)

    def test_r2_approve_refuses_a_drifted_configuration_with_no_caller_digest(self):
        self.rules("AGENTS.md", "one\n")
        self.proposed()
        (self.project / "AGENTS.md").write_text("two\n")
        with self.app() as app:
            version = app.authority.current["version"]
            before = app.authority.path.read_bytes()
            with self.assertRaises(Blocked) as raised:
                app.authority.approve(version)          # no caller digest at all (the base's default None disabled it)
            self.assertEqual(raised.exception.family, "plan.gate_stale")
            self.assertEqual(app.authority.current["status"], "proposed")   # in-memory state unchanged
            self.assertEqual(app.authority.path.read_bytes(), before)       # persisted bytes unchanged

    def test_r2_override_refuses_a_drifted_configuration_with_no_caller_digest(self):
        self.rules("AGENTS.md", "one\n")
        self.exhausted()
        (self.project / "AGENTS.md").write_text("two\n")
        with self.app() as app:
            before = app.authority.path.read_bytes()
            with self.assertRaises(Blocked) as raised:
                app.authority.override(1, REASON)
            self.assertEqual(raised.exception.family, "plan.gate_stale")
            self.assertEqual(app.authority.current["status"], "review_exhausted")
            self.assertEqual(app.authority.path.read_bytes(), before)

    def test_r2_an_unusable_profile_is_refused_with_no_caller_digest(self):
        self.proposed()
        self.write("{ not json")                        # the bound profile becomes unusable (malformed)
        with self.app() as app:
            version = app.authority.current["version"]
            before = app.authority.path.read_bytes()
            with self.assertRaises(Blocked) as raised:
                app.authority.approve(version)
            self.assertEqual(raised.exception.family, "plan.gate_stale")
            self.assertEqual(app.authority.current["status"], "proposed")
            self.assertEqual(app.authority.path.read_bytes(), before)

    def test_r2_a_postponed_profile_is_a_bound_provider(self):
        """A postponed profile (no zplan.process.json) is bound: its snapshot is the live digest, so it refuses an
        approval argued under another configuration. The revision was frozen with no profile at all, so the
        postponed snapshot is the only digest that can answer — and it must not read as "unprofiled"/None."""
        self.rules("AGENTS.md", "one\n")
        self.defer()
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            authority.begin("Goal", ROLES, "fixture")        # no profile bound: the default configuration
            FixtureEngine().proposal(authority, lambda _: None)
        with self.app() as app:
            self.assertFalse(app.profile.file.exists())
            before = app.authority.path.read_bytes()
            with self.assertRaises(Blocked) as raised:
                app.authority.approve(app.authority.current["version"])
            self.assertEqual(raised.exception.family, "plan.gate_stale")
            self.assertEqual(app.authority.path.read_bytes(), before)

    def test_r2_execution_one_needs_no_digest(self):
        """A version 1 revision has no gate to compare against: a drifted bound profile does not refuse it."""
        self.reset()
        self.accept_file()
        with self.app() as app:
            app.authority.begin("Goal", app.roles, "fixture", execution=1)
            FixtureEngine().proposal(app.authority, lambda _: None)
            app.profile.live_digest = lambda: "0" * 64
            app.authority.approve(app.authority.current["version"])
            self.assertEqual(app.authority.current["status"], "approved")


# O-3 -----------------------------------------------------------------------------------------------------------

class ValidationTests(OverrideCase):
    def overridden(self):
        self.exhausted()
        with self.app() as app:
            app.planning.override(1, REASON)

    def test_o3_a_valid_override_loads(self):
        self.overridden()
        with self.app() as app:
            self.assertEqual(app.authority.current["override"]["reason"], REASON)

    def test_o3_replacing_the_reason_after_approval_invalidates_the_store(self):
        self.overridden()
        self.tamper(lambda r: r["override"].update(reason="Another perfectly valid reason."))
        self.assert_invalid()

    def test_o3_a_changed_verdict_or_evidence_digest_invalidates_the_store(self):
        for key, value in (("verdict", "accepted"), ("evidence_digest", "0" * 64)):
            with self.subTest(key):
                self.reset()
                self.overridden()
                self.tamper(lambda r: r["override"].update({key: value}))
                self.assert_invalid()

    def test_o3_an_override_even_with_a_matching_approval_needs_matching_evidence_digest(self):
        self.overridden()

        def retarget(r):
            r["override"]["evidence_digest"] = "1" * 64
            r["approval"] = auth.Authority.approval_identity(r)
        self.tamper(retarget)
        self.assert_invalid()

    def test_o3_an_override_cannot_be_added_to_an_accepted_revision(self):
        for approved in (False, True):
            with self.subTest(approved=approved):
                self.reset()
                self.make("accept", approve=approved)

                def add(r):
                    r["override"] = {"reason": REASON, "verdict": "accepted", "evidence_digest": digest(r["evidence"])}
                    if approved:  # a consistent approval: only the rule itself may refuse
                        r["approval"] = auth.Authority.approval_identity(r)
                self.tamper(add)
                self.assert_invalid()

    def test_o3_an_override_cannot_be_added_to_a_rejected_unapproved_revision(self):
        self.exhausted()
        self.tamper(lambda r: r.update(override={"reason": REASON, "verdict": "rejected",
                                                 "evidence_digest": digest(r["evidence"])}))
        self.assert_invalid()

    def test_o3_an_approved_rejected_verdict_needs_its_override(self):
        self.overridden()

        def drop(r):
            del r["override"]
            r["approval"] = auth.Authority.approval_identity(r)
        self.tamper(drop)
        self.assert_invalid()

    def test_o3_an_override_on_a_version_one_revision_is_invalid(self):
        self.reset()
        self.make("accept", execution=1, approve=True)
        self.tamper(lambda r: r.update(override={"reason": REASON, "verdict": "rejected", "evidence_digest": "0" * 64}))
        self.assert_invalid()

    def test_o3_a_malformed_reason_or_extra_field_is_invalid(self):
        for label, mutate in (("short", lambda o: o.update(reason="too short")),
                              ("multiline", lambda o: o.update(reason="two\nlines of reason")),
                              ("padded", lambda o: o.update(reason=" " + REASON)),
                              ("extra", lambda o: o.update(extra="x")),
                              ("missing", lambda o: o.pop("verdict"))):
            with self.subTest(label):
                self.reset()
                self.overridden()

                def change(r):
                    mutate(r["override"])
                    r["approval"] = auth.Authority.approval_identity(r)
                self.tamper(change)
                self.assert_invalid()

    def test_o3_records_without_an_override_keep_their_approval_digest_and_bytes(self):
        self.accept_file()
        with self.app() as app:
            a = app.authority
            a.begin("Goal one", app.roles, "fixture", execution=1)
            FixtureEngine().proposal(a, lambda _: None)
            a.approve(1)
            a.begin("Goal two", app.roles, "fixture")
            FixtureEngine().proposal(a, lambda _: None)
            app.planning.approve(2)
        raw = self.raw()
        with self.app() as app:
            for revision in app.authority.state["revisions"]:
                self.assertNotIn("override", revision)
                self.assertEqual(revision["approval"], digest(
                    {"intent": revision["intent"], "evidence": revision["evidence"], "proposal": revision["proposal"]}))
        self.assertEqual(self.raw(), raw)  # nothing is rewritten on read


# O-4 (plain mode) ----------------------------------------------------------------------------------------------

class PlainTests(OverrideCase):
    def session(self, text, engine=None):
        output = io.StringIO()
        terminal = ScriptedTerminal(text, output)
        driver = FixtureDriver(self.root / "fixture-runs", "done")
        cli.session(terminal, self.project, self.state, lambda *_: engine or FixtureEngine(), fixture_id="test",
                    driver_factory=lambda _: driver, worktrees=self.root / "worktrees", profile=True)
        return output.getvalue()

    def test_o4_the_line_ui_offers_the_action_asks_for_the_reason_and_shows_the_override(self):
        self.exhausted()
        text = self.session("p\no\n" + REASON + "\n\np\ni\n\nq\nq\n")
        self.assertIn("[o] approve despite the check", text)
        self.assertIn("Plan r1 approved despite the check.", text)
        self.assertIn("The plan check did not accept it:", text)
        self.assertIn('Approved despite the check: "%s"' % REASON, text)
        self.assertIn('  Approved despite the check: "%s"' % REASON, text)  # the [i] gate lines
        self.assertNotIn("this plan cannot be approved", text.split("Plan r1 approved despite the check.", 1)[1])
        stored = self.stored()["revisions"][-1]
        self.assertEqual((stored["status"], stored["override"]["reason"]), ("approved", REASON))

    def test_o4_an_empty_reason_cancels_and_a_short_one_is_refused(self):
        self.exhausted()
        before = self.raw()
        text = self.session("p\no\n\nq\nq\n")
        self.assertIn("Empty text: the plan is unchanged.", text)
        self.assertEqual(self.raw(), before)
        text = self.session("p\no\nshort\n\nq\nq\n")
        self.assertIn("A reason is required: one line, 10 to 500 characters.", text)
        self.assertIn("[code: action.refused]", text)
        self.assertEqual(self.raw(), before)
        text = self.session("p\no\nfirst line of text\nsecond line of text\n\nq\nq\n")
        self.assertIn("A reason is required", text)
        self.assertEqual(self.raw(), before)

    def test_o4_a_version_one_review_exhausted_plan_offers_no_override(self):
        self.reset()
        self.make(engine=V1Rejecting(), execution=1)
        before = self.raw()
        text = self.session("p\no\n" + REASON + "\n\nq\nq\n", engine=V1Rejecting())
        self.assertNotIn("approve despite the check", text)
        self.assertEqual(self.raw(), before)

    def test_o4_an_accepted_plan_offers_approve_only(self):
        self.reset()
        self.make("accept")
        text = self.session("p\nq\nq\n")
        self.assertIn("[a] approve", text)
        self.assertNotIn("despite the check", text)


if __name__ == "__main__":
    unittest.main()
