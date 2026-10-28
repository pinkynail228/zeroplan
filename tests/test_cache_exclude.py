"""K1: a tool cache never enters a milestone commit, one smoke test per criterion (C1-C4).

Interpretations (the task leaves them open):
- The five lines are written in sorted order after the existing ones, as `<name>/` (no leading `/`).
- A tracked file under a cache name (`node_modules/x`) stays in the attempt's tree: info/exclude never untracks.
- C3 lives in tests/test_export.py (`test_untracked_cache_dropped_by_target_exclude_is_left_out`)."""

from pathlib import Path
import subprocess
import unittest

from test_runs import RunsTest, ROLES
from terminal_planner import project_state
from terminal_planner.delivery import CLEANUP_CACHES

LINES = [name + "/" for name in sorted(CLEANUP_CACHES)]


class CacheExcludeTest(RunsTest):
    def exclude(self):
        return self.project / ".git" / "info" / "exclude"

    def start(self):
        self.approve_fixture()
        with self.fixture_authority() as a:
            return self.fixture_runs(a).start("M1", 1, ROLES)

    # C1
    def test_start_writes_each_cache_line_once_and_keeps_existing_lines(self):
        self.exclude().write_text("/.zplan/\nmine")  # no final newline
        self.start()
        self.assertEqual(self.exclude().read_text().splitlines(), ["/.zplan/", "mine"] + LINES)
        self.assertEqual(len(LINES), 5)
        self.assertTrue(all(not line.startswith("/") for line in LINES))
        before = self.exclude().read_bytes()
        project_state.exclude_caches(self.project)  # a later start repeats exactly this call
        self.assertEqual(self.exclude().read_bytes(), before)

    def test_missing_exclude_file_is_created(self):
        self.exclude().unlink(missing_ok=True)
        self.start()
        self.assertEqual(self.exclude().read_text().splitlines(), LINES)

    # C2
    def test_untracked_cache_does_not_block_start_and_worker_cache_is_not_staged(self):
        (self.project / "__pycache__").mkdir()
        (self.project / "__pycache__" / "x.pyc").write_bytes(b"\0")
        r = self.start()  # a dirty tree would raise Blocked
        worktree = Path(r["worktree"])
        (worktree / "pkg" / "__pycache__").mkdir(parents=True)
        (worktree / "pkg" / "__pycache__" / "a.pyc").write_bytes(b"\0")
        (worktree / "pkg" / "real.py").write_text("x = 1\n")
        subprocess.run(["git", "-C", str(worktree), "add", "--all"], check=True)
        staged = subprocess.run(["git", "-C", str(worktree), "diff", "--cached", "--name-only"], check=True,
                                capture_output=True, text=True).stdout.split()
        self.assertEqual([p for p in staged if not p.startswith(".zplan/")], ["pkg/real.py"])  # control files: CONTROL

    # C4
    def test_tracked_file_under_a_cache_name_stays_tracked(self):
        (self.project / "node_modules").mkdir()
        (self.project / "node_modules" / "x").write_text("tracked\n")
        self.git("add", "-f", "node_modules/x")
        self.git("commit", "-qm", "track node_modules")
        r = self.start()
        listed = subprocess.run(["git", "-C", str(self.project), "ls-tree", "-r", "--name-only", r["destination"]["base"]],
                                check=True, capture_output=True, text=True).stdout.split()
        self.assertIn("node_modules/x", listed)
        worktree = Path(r["worktree"])
        (worktree / "node_modules" / "x").write_text("changed\n")
        status = subprocess.run(["git", "-C", str(worktree), "status", "--porcelain"], check=True,
                                capture_output=True, text=True).stdout
        self.assertEqual([l for l in status.splitlines() if ".zplan" not in l], [" M node_modules/x"])


if __name__ == "__main__":
    unittest.main()
