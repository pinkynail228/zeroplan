"""Required checks run on the base before a start (docs/PRODUCT_CONTRACT.md section 2, Delegation; roadmap D1).

A check that fails or cannot run on the project's HEAD refuses the start before anything is created, so a milestone
never stops at its final check for a reason its base already had."""
import sys
import unittest

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


if __name__ == "__main__":
    unittest.main()
