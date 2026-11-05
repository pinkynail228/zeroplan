"""Required checks run on the base before a start (docs/PRODUCT_CONTRACT.md section 2, Delegation; roadmap D1).

A check that fails or cannot run on the project's HEAD refuses the start before anything is created, so a milestone
never stops at its final check for a reason its base already had."""
import sys
import unittest
import unittest.mock

from terminal_planner.authority import Blocked

import test_process as tpr


def profile(*argv):
    return {"gates": {"merge": "required"}, "checks": [{"name": "unit", "argv": list(argv), "timeout_s": 60}]}


class BaseChecks(tpr.ProfileTest):
    def start(self):
        with self.app() as app:
            return app.delivery.start(app.delivery.preview("M1", app.roles), app.roles)

    def base_checks(self):
        with self.app() as app:
            return app.delivery.base_checks()

    def test_a_check_that_fails_on_the_base_refuses_the_start_and_creates_nothing(self):
        self.accept_file(profile(sys.executable, "-c", "import sys; print('base is red'); sys.exit(3)"))
        self.approved_plan()
        with self.assertRaises(Blocked) as refused:
            self.start()
        self.assertEqual(refused.exception.family, "milestone.preflight")
        self.assertIn("unit", str(refused.exception))
        self.assertIn("base is red", str(refused.exception))
        self.assertEqual(self.stored()["runs"], [])

    def test_a_check_that_cannot_run_refuses_the_start(self):
        self.accept_file(profile(str(self.root / "missing" / "python3"), "-m", "pytest"))
        self.approved_plan()
        with self.assertRaises(Blocked) as refused:
            self.start()
        self.assertEqual(refused.exception.family, "milestone.preflight")
        self.assertEqual(self.stored()["runs"], [])

    def test_a_passing_base_starts_and_is_checked_once_until_the_base_moves(self):
        marker = self.root / "ran.txt"
        self.accept_file(profile(sys.executable, "-c", "open(%r, 'a').write('x')" % str(marker)))
        self.approved_plan()
        self.assertEqual(self.base_checks()["outcome"], "passed")
        self.assertEqual(self.base_checks()["outcome"], "passed")
        self.assertEqual(marker.read_text(), "x")
        run = self.start()
        self.assertIsNotNone(run["run_id"])
        self.assertEqual(marker.read_text(), "x")
        (self.project / "more.txt").write_text("next\n")
        self.git("add", "more.txt")
        self.git("commit", "-qm", "the base moves")
        self.assertEqual(self.base_checks()["outcome"], "passed")
        self.assertEqual(marker.read_text(), "xx")

    def test_a_failure_is_not_remembered(self):
        flag = self.root / "ready.flag"
        self.accept_file(profile(sys.executable, "-c", "import os, sys; sys.exit(0 if os.path.exists(%r) else 1)" % str(flag)))
        self.approved_plan()
        self.assertEqual(self.base_checks()["outcome"], "failed")
        flag.write_text("fixed outside the tree\n")
        self.assertEqual(self.base_checks()["outcome"], "passed")

    def test_no_required_merge_gate_or_no_checks_runs_nothing(self):
        self.accept_file({"gates": {"merge": "off"}, "checks": [{"name": "unit", "argv": ["false"], "timeout_s": 60}]})
        self.approved_plan()
        self.assertIsNone(self.base_checks())
        self.assertIsNotNone(self.start()["run_id"])


def flagged(*checks):
    """A profile whose checks fail while their flag file is absent: [(name, flag path), ...]."""
    return {"gates": {"merge": "required"},
            "checks": [{"name": name, "argv": [sys.executable, "-c", "import os, sys; sys.exit(0 if os.path.exists(%r) else 1)" % str(flag)],
                        "timeout_s": 60} for name, flag in checks]}


class RedBaseSettledWhilePlanning(tpr.ProfileTest):
    """R2a (docs/designs/2026-11-05-r2-base-checks.md): the base checks run before the plan card shows; the owner's yes
    on a card that showed a red base lets the plan start on exactly that base, and its merges wait for him."""

    def proposed_and_settled(self, approve=True):
        with self.app() as app:
            self.begin(app.authority)
            self.propose(app.authority)
            app.planning.settle_base()
            card = app.planning.proposal(app.authority.current).lines
            if approve:
                app.planning.approve(1)
            return dict(app.authority.current), card

    def start(self):
        with self.app() as app:
            return app.delivery.start(app.delivery.preview("M1", app.roles), app.roles)

    def test_the_card_shows_the_red_base_and_the_revision_keeps_what_it_showed(self):
        self.accept_file(flagged(("unit", self.root / "unit.flag")))
        revision, card = self.proposed_and_settled()
        self.assertEqual(revision["base_checks"]["outcome"], "failed")
        self.assertEqual(revision["base_checks"]["failed"], ["unit"])
        self.assertEqual(revision["base_checks"]["commit"], self.head())
        self.assertTrue(any("unit fails on" in line and "first milestone must fix" in line for line in card), card)

    def test_a_passing_base_says_so(self):
        self.accept_file(profile(sys.executable, "-c", "pass"))
        revision, card = self.proposed_and_settled(approve=False)
        self.assertEqual(revision["base_checks"]["outcome"], "passed")
        self.assertIn("Checks on the base: all passed (unit).", card)

    def test_the_approved_red_base_starts_and_its_merge_waits_for_the_owner(self):
        self.accept_file(flagged(("unit", self.root / "unit.flag")))
        self.proposed_and_settled()
        run = self.start()
        self.assertIsNotNone(run["run_id"])
        with self.app() as app:
            r = app.delivery.latest("M1")
            self.assertTrue(app.delivery.base_red(r))
            merged = app.delivery.merge(r)
        self.assertEqual((merged.kind, merged.family), ("refused", "merge.base_red"))

    def test_a_moved_base_or_a_different_failure_refuses_the_start(self):
        self.accept_file(flagged(("a", self.root / "a.flag"), ("b", self.root / "b.flag")))
        (self.root / "a.flag").write_text("a passes while planning, b fails\n")
        self.proposed_and_settled()
        (self.root / "a.flag").unlink()  # now a fails: not the failure the owner accepted
        with self.assertRaises(Blocked) as refused:
            self.start()
        self.assertEqual(refused.exception.family, "milestone.preflight")
        (self.root / "a.flag").write_text("a passes again\n")
        (self.project / "more.txt").write_text("the base moves\n")
        self.git("add", "more.txt")
        self.git("commit", "-qm", "the base moves")
        with self.assertRaises(Blocked) as moved:
            self.start()
        self.assertEqual(moved.exception.family, "milestone.preflight")
        self.assertEqual(self.stored()["runs"], [])

    def test_the_plan_job_settles_the_base_before_the_card_and_an_unsettled_approval_settles_first(self):
        self.accept_file(flagged(("unit", self.root / "unit.flag")))
        with self.app() as app:
            self.begin(app.authority)
            self.assertEqual(app.planning.watch(lambda line: None).step(), "done")
            self.assertEqual(app.authority.current["base_checks"]["failed"], ["unit"])
            plan = __import__("terminal_planner.tui.controller", fromlist=["plan_fields"]).plan_fields(app.authority.current)
            self.assertEqual(plan["base_checks"]["failed"], ["unit"])
            self.assertEqual(set(plan["base_checks"]), {"outcome", "failed", "commit", "refused"})
        self.git("commit", "-q", "--allow-empty", "-m", "a reopen with an unsettled revision")
        with self.app() as app:  # a revision that never got its base result (an interrupted slice)
            self.begin(app.authority)
            self.propose(app.authority)
            with self.assertRaises(Blocked):
                app.planning.approve(2)  # the red base is settled now and shown, not approved unseen
            self.assertEqual(app.authority.current["base_checks"]["failed"], ["unit"])
            app.planning.approve(2)
            self.assertEqual(app.authority.current["status"], "approved")

    def test_checks_that_cannot_run_are_not_a_red_base_a_milestone_can_fix(self):
        self.accept_file(profile(str(self.root / "missing" / "python3"), "-m", "pytest"))
        revision, card = self.proposed_and_settled()
        self.assertEqual((revision["base_checks"]["outcome"], revision["base_checks"]["failed"]), ("failed", []))
        self.assertTrue(any("could not run" in line and "no milestone can start" in line for line in card), card)
        with self.assertRaises(Blocked) as refused:
            self.start()
        self.assertEqual(refused.exception.family, "milestone.preflight")

    def test_the_architect_never_approves_a_red_base_revision_alone(self):
        from terminal_planner.tui.controller import architect_may_approve
        owner = {"version": 1, "approval": "x", "frozen": {"review": "goldfish"}, "by": "owner"}
        later = {"version": 2, "approval": None, "frozen": {"review": "goldfish"}, "by": "architect"}
        red = dict(later, base_checks={"outcome": "failed"})
        with unittest.mock.patch("terminal_planner.tui.controller.chain_approved", return_value=True):
            self.assertTrue(architect_may_approve([owner, later]))
            self.assertFalse(architect_may_approve([owner, red]))


if __name__ == "__main__":
    unittest.main()
