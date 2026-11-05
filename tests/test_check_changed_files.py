# tests/test_check_changed_files.py
"""A check that changes tracked files says which ones: its evidence carries a bounded, scrubbed list of the paths, and
the refusal of a start and of a merge name them. Real git in temporary repositories, as in tests/test_checks.py."""
import sys
import unittest

from terminal_planner import checks, delivery, live, runs
from terminal_planner.authority import Blocked

import test_base_checks as tbc
import test_checks as tc
import test_merge_gate as tmg
import test_process as tpr


class ChangedFilesEvidence(tc.Fixture):
    def tracked(self, *names):
        """Commit `names` to the project; the candidate identity follows the new commit."""
        for name in names:
            (self.project / name).write_text("one\n")
        tc.git(self.project, "add", "-A")
        tc.git(self.project, "commit", "-qm", "more files")
        self.commit = tc.git(self.project, "rev-parse", "HEAD")
        self.tree = tc.git(self.project, "rev-parse", "HEAD^{tree}")

    def rewrites(self, *names):
        """A check that exits 0 after writing `names` in its checkout."""
        code = "from pathlib import Path\nfor name in %s:\n    Path(name).write_text('fixed\\n')\n" % ascii(list(names))
        return self.check("unit", code)

    def qualified(self, *listed):
        return checks.qualify(self.project, self.commit, self.tree, list(listed), self.work)["checks"]

    def test_a_changed_candidate_names_its_tracked_files_and_not_its_untracked_output(self):
        self.tracked("other.txt")
        entry = self.qualified(self.rewrites("file.txt", "report.txt"))[0]
        self.assertEqual(entry["status"], "candidate_changed")
        self.assertEqual(entry["changed_files"], ["file.txt"])

    def test_a_candidate_changed_before_the_check_names_its_files_too(self):
        (self.project / "file.txt").write_text("edited\n")
        found = checks.run_checks([self.check("unit", "pass")], str(self.project), candidate=(self.commit, self.tree))
        entry = found["checks"][0]
        self.assertEqual(entry["status"], "candidate_changed")
        self.assertEqual(entry["changed_files"], ["file.txt"])

    def test_a_long_change_keeps_the_first_twenty_paths(self):
        names = ["f%02d.txt" % number for number in range(25)]
        self.tracked(*names)
        entry = self.qualified(self.rewrites(*names))[0]
        self.assertEqual(entry["changed_files"], names[:20])

    def test_a_secret_in_a_file_name_is_scrubbed(self):
        secret = "sk-abcdefghijklmnop"
        name = "api_key=%s.txt" % secret
        self.tracked(name)
        shown = self.qualified(self.rewrites(name))[0]["changed_files"]
        self.assertEqual(len(shown), 1)
        self.assertNotIn(secret, shown[0])
        self.assertIn(live.HIDDEN, shown[0])

    def test_spaces_and_non_ascii_file_names_stay_readable(self):
        names = ["a b.txt", "план.txt"]
        self.tracked(*names)
        entry = self.qualified(self.rewrites(*names))[0]
        self.assertEqual(entry["changed_files"], names)

    def test_a_moved_head_with_a_clean_tree_names_nothing_and_is_still_valid(self):
        tc.git(self.project, "commit", "--allow-empty", "-qm", "second")
        self.commit = tc.git(self.project, "rev-parse", "HEAD")
        check = self.check("unit", "import subprocess; subprocess.run(['git', 'checkout', '--detach', 'HEAD^'], check=True)")
        entry = self.qualified(check)[0]
        self.assertEqual(entry["status"], "candidate_changed")
        self.assertEqual(entry["changed_files"], [])
        self.assertTrue(runs.valid_check_evidence(entry, check))

    def test_the_store_accepts_only_a_bounded_list_on_a_changed_check(self):
        check = self.rewrites("file.txt")
        entry = self.qualified(check)[0]
        self.assertEqual(entry["changed_files"], ["file.txt"])
        self.assertTrue(runs.valid_check_evidence(entry, check))
        for wrong in ("file.txt", [""], [1], ["x"] * 21):
            with self.subTest(wrong=wrong):
                self.assertFalse(runs.valid_check_evidence(dict(entry, changed_files=wrong), check))
        red = self.check("red", "raise SystemExit(3)")
        plain = self.qualified(red)[0]
        self.assertFalse(runs.valid_check_evidence(dict(plain, changed_files=[]), red))

    def test_every_other_status_keeps_its_evidence_keys(self):
        failed = self.qualified(self.check("red", "raise SystemExit(3)"), self.check("later", "pass"))
        passed = self.qualified(self.check("green", "pass"))
        self.assertEqual([entry["status"] for entry in failed + passed], [3, "not_run", 0])
        for entry in failed + passed:
            self.assertNotIn("changed_files", entry)


class ChangedFilesInRefusals(tpr.ProfileTest):
    """The merge and start helpers of the merge gate and base check tests, borrowed without their own tests."""
    gated = tmg.MergeGateTests.gated
    merge = tmg.MergeGateTests.merge
    start = tbc.BaseChecks.start

    def test_a_refused_merge_names_the_files_and_its_gate_stays_readable(self):
        self.gated(argv=(sys.executable, "-c", "from pathlib import Path; Path('ZPLAN_FIXTURE.md').write_text('fixed')"))
        result = self.merge()
        self.assertEqual((result.kind, result.family), ("refused", "merge.checks_failed"))
        self.assertIn("ZPLAN_FIXTURE.md", result.line)
        stored = self.stored()["runs"][0]  # opening the store validates what the gate saved
        self.assertEqual(stored["gate"]["evidence"]["checks"][0]["changed_files"], ["ZPLAN_FIXTURE.md"])
        runs.validate_gate(stored)

    def test_a_refused_start_names_the_files_even_when_the_check_printed_a_lot(self):
        noisy = ("from pathlib import Path\nfor _ in range(40):\n    print('noise ' * 20)\n"
                 "Path('source.txt').write_text('fixed')\n")
        self.accept_file(tbc.profile(sys.executable, "-c", noisy))
        self.approved_plan()
        with self.assertRaises(Blocked) as refused:
            self.start()
        self.assertEqual(refused.exception.family, "milestone.preflight")
        self.assertIn("source.txt", delivery.refusal(refused.exception))  # the bounded line a screen shows
        self.assertEqual(self.stored()["runs"], [])


if __name__ == "__main__":
    unittest.main()
