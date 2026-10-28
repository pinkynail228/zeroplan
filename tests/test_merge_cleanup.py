"""Cleanup after an integrated merge (A7c): the attempt's worktree and branches go, nothing else moves.

Every test runs a real fixture project through `Delivery.merge` (the production path of `[m]` and of the TUI's
merge): one smoke test per criterion (C1 cleanup, C2 best effort, C3 the non-integrated merges clean nothing) plus
the invariants the cleanup can break (data loss: the merge and the result commits stay reachable; secrets: a
leftover the disposable caches do not cover keeps the worktree and its branch; a worktree whose product tree
differs or cannot be read is kept).

Interpretations (none of them waives a stated requirement):
- "An ignored or untracked path left" (orchestrator amendment 2026-10-25, critic a7c-merge): the fixture leaves its
  product untracked in the worktree, as export does (it commits through a scratch index), and such an attempt is
  cleaned. Untracked files are listed without ignore rules; each must be under `.zplan/` or a disposable cache or be
  carried byte-identical by the result. Every staged entry must equal the result's, and HEAD and every deleted
  branch must be ancestors of the integration commit: a commit of the attempt (a resume checkpoint) keeps the
  worktree and its branch, named in the leftovers.
- "The items left by name" are reported per the state after the cleanup ran: the attempt's worktree path while it
  still exists, then its working branch and its result branch while they still exist; an item removed now or absent
  before is not reported, so the line stays today's `Merged: M → B.` when everything is gone.
- `.zplan/` at the worktree root or a `__pycache__`/`node_modules`/`.pytest_cache`/`.mypy_cache`/`.ruff_cache`
  path segment at any depth is a disposable leftover; any other ignored or untracked path keeps the worktree (and,
  with it, the working branch), while the result branch still goes.
- An inspection that fails -- an unreadable worktree parent, a Git refusal answering `show-ref`/`branch` -- is
  uncertainty, not absence: the worktree and the branch are treated as still there, kept, and named in the leftovers.
- Cleanup runs only from `Delivery.merge`, on the owner's own merge press: a record already integrated in the
  store is refused up front by `MilestoneRuns.merge`, while a manual merge the press is the first to see is
  detected by the `refresh` inside it and then cleaned like any other integrated attempt -- cleanup of a merge done
  by hand outside zplan is a non-goal, not a refusal."""

import errno
import subprocess
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from terminal_planner import delivery, runs
from terminal_planner.authority import Blocked
import test_process as tpr

CHECKS = [{"name": "unit", "argv": ["true"], "timeout_s": 60}]


class MergeCleanupTests(tpr.ProfileTest):
    def merge(self):
        with self.app() as app:
            return app.delivery.merge(app.delivery.latest("M1"))

    def gated(self):
        """An accepted profile that requires the merge gate, written after the attempt awaits the merge."""
        self.awaiting_merge()
        self.write({"gates": {"merge": "required"}, "checks": CHECKS})

    def ignores(self, *rules):
        """A committed `.gitignore` the base, the attempt worktree and the result all share."""
        (self.project / ".gitignore").write_text("".join(rule + "\n" for rule in rules), encoding="utf-8")
        self.git("add", ".gitignore")
        self.git("commit", "-qm", "ignore")

    def branch(self, name):
        """The commit refs/heads/<name> points at, or None when the branch does not exist."""
        done = subprocess.run(["git", "-C", str(self.project), "rev-parse", "--verify", "--quiet", "refs/heads/" + name],
                              capture_output=True)
        return done.stdout.decode().strip() if done.returncode == 0 else None

    def record(self):
        return self.stored()["runs"][0]

    def merged(self):
        """The one merge of this test: its verdict, with the integrated kind asserted."""
        result = self.merge()
        self.assertEqual(result.kind, "integrated")
        return result

    # C1: cleanup --------------------------------------------------------------------------------------------------

    def test_c1_an_integrated_merge_removes_worktree_and_both_branches(self):
        self.awaiting_merge()
        r = self.record()
        worktree, result = Path(r["worktree"]), r["result"]
        self.assertTrue(worktree.is_dir())
        self.assertIsNotNone(self.branch(r["branch"]))
        self.assertIsNotNone(self.branch(result["branch"]))
        self.assertEqual(self.merged().line, "Merged: M1 → main.")
        self.assertFalse(worktree.exists())
        self.assertIsNone(self.branch(r["branch"]))
        self.assertIsNone(self.branch(result["branch"]))
        # The merge and the result commits stay reachable from the destination.
        self.assertEqual(self.git("rev-parse", "main").decode().strip(), self.record()["integration"]["commit"])
        self.assertEqual(self.git("merge-base", "--is-ancestor", result["commit"], "main").decode(), "")

    def test_c1_an_untracked_product_the_result_carries_is_cleaned(self):
        self.awaiting_merge()
        r = self.record()
        worktree = Path(r["worktree"])
        status = subprocess.check_output(["git", "-C", str(worktree), "status", "--porcelain=v1",
                                          "--ignored", "--untracked-files=all"], text=True)
        # The fixture leaves its product untracked in the worktree (as export does); the result commit carries it.
        self.assertIn("?? ZPLAN_FIXTURE.md", status)
        with self.app() as app:
            self.assertEqual(app.delivery.runs.product_tree(app.delivery.latest("M1")), r["result"]["tree"])
        self.assertEqual(self.merged().line, "Merged: M1 → main.")
        self.assertFalse(worktree.exists())
        self.assertIsNone(self.branch(r["branch"]))
        self.assertIsNone(self.branch(r["result"]["branch"]))
        self.assertEqual((self.project / "ZPLAN_FIXTURE.md").is_file(), True)

    def test_c1_only_the_control_dir_and_disposable_caches_may_be_left(self):
        self.ignores("__pycache__/")
        self.awaiting_merge()
        r = self.record()
        worktree = Path(r["worktree"])
        (worktree / "__pycache__" / "deep").mkdir(parents=True)
        (worktree / "__pycache__" / "deep" / "m.pyc").write_bytes(b"cache")
        self.assertTrue((worktree / ".zplan").is_dir())
        self.assertEqual(self.merged().line, "Merged: M1 → main.")
        self.assertFalse(worktree.exists())
        self.assertIsNone(self.branch(r["branch"]))
        self.assertIsNone(self.branch(r["result"]["branch"]))

    def test_c1_a_missing_worktree_is_pruned_and_its_branch_deleted(self):
        self.awaiting_merge()
        r = self.record()
        shutil.rmtree(r["worktree"])
        self.assertEqual(self.merged().line, "Merged: M1 → main.")
        self.assertIsNone(self.branch(r["branch"]))
        self.assertIsNone(self.branch(r["result"]["branch"]))
        # The stale administration entry of the gone worktree is pruned, not merely abandoned.
        self.assertNotIn(r["worktree"], self.git("worktree", "list", "--porcelain").decode())

    def test_c1_a_gated_integrated_merge_cleans_up(self):
        self.gated()
        r = self.record()
        worktree = Path(r["worktree"])
        self.assertEqual(self.merged().line, "Merged: M1 → main.")
        self.assertFalse(worktree.exists())
        self.assertIsNone(self.branch(r["branch"]))
        self.assertIsNone(self.branch(r["result"]["branch"]))

    # C2: best effort ----------------------------------------------------------------------------------------------

    def test_c2_a_leftover_outside_the_caches_keeps_the_worktree_and_branch(self):
        self.ignores(".env.local")
        self.awaiting_merge()
        r = self.record()
        worktree = Path(r["worktree"])
        (worktree / ".env.local").write_text("secret\n", encoding="utf-8")
        self.assertEqual(self.merged().line, "Merged: M1 → main; left in place: %s, %s." % (worktree, r["branch"]))
        self.assertTrue(worktree.is_dir())
        self.assertIsNotNone(self.branch(r["branch"]))
        self.assertIsNone(self.branch(r["result"]["branch"]))

    def wt(self, worktree, *args):
        subprocess.check_call(["git", "-C", str(worktree), *args], stdout=subprocess.DEVNULL)

    def kept(self, worktree, r):
        self.assertEqual(self.merged().line, "Merged: M1 → main; left in place: %s, %s." % (worktree, r["branch"]))
        self.assertTrue(worktree.is_dir())
        self.assertIsNotNone(self.branch(r["branch"]))

    def test_c2_an_untracked_file_only_the_project_config_ignores_keeps_the_worktree(self):
        # critic a7c-merge P1: product_tree reads the project's ignore configuration, the worktree has its own.
        self.awaiting_merge()
        r = self.record()
        worktree = Path(r["worktree"])
        excludes = self.project.parent / "excludes"
        excludes.write_text("notes.txt\n", encoding="utf-8")
        self.git("config", "extensions.worktreeConfig", "true")
        self.git("config", "--worktree", "core.excludesFile", str(excludes))
        (worktree / "notes.txt").write_text("work after the export\n", encoding="utf-8")
        with self.app() as app:  # the file is hidden from the product tree, so its identity still matches
            self.assertEqual(app.delivery.runs.product_tree(app.delivery.latest("M1")), r["result"]["tree"])
        self.kept(worktree, r)
        self.assertTrue((worktree / "notes.txt").is_file())

    def test_c2_a_staged_file_the_result_lacks_keeps_the_worktree(self):
        # critic a7c-merge P1: `git add -f` of an ignored file is neither untracked nor in the product tree.
        self.ignores(".env.local")
        self.awaiting_merge()
        r = self.record()
        worktree = Path(r["worktree"])
        (worktree / ".env.local").write_text("secret\n", encoding="utf-8")
        self.wt(worktree, "add", "-f", ".env.local")
        self.kept(worktree, r)
        self.assertTrue((worktree / ".env.local").is_file())

    def test_c2_a_commit_beyond_the_result_keeps_the_worktree_and_branch(self):
        # critic a7c-merge P1: equal files do not prove the working branch's commits are merged.
        self.awaiting_merge()
        r = self.record()
        worktree = Path(r["worktree"])
        (worktree / "extra.txt").write_text("more work\n", encoding="utf-8")
        self.wt(worktree, "add", "-A", "--", ":!.zplan")
        self.wt(worktree, "commit", "-qm", "extra")
        tip = self.branch(r["branch"])
        (worktree / "extra.txt").unlink()
        self.wt(worktree, "read-tree", self.record()["result"]["commit"])  # index = the result, files = the result
        self.kept(worktree, r)
        self.assertEqual(self.branch(r["branch"]), tip)

    def test_c2_history_the_destination_lacks_keeps_the_worktree_even_with_equal_files(self):
        # critic a7c-merge2 P1: add then remove a file in two commits -- the tree is the result's, the history is not.
        self.awaiting_merge()
        r = self.record()
        worktree = Path(r["worktree"])
        self.wt(worktree, "add", "-A", "--", ":!.zplan")
        self.wt(worktree, "commit", "-qm", "product")
        (worktree / "extra.txt").write_text("more work\n", encoding="utf-8")
        self.wt(worktree, "add", "extra.txt")
        self.wt(worktree, "commit", "-qm", "extra")
        self.wt(worktree, "rm", "-q", "extra.txt")
        self.wt(worktree, "commit", "-qm", "drop extra")
        tip = self.branch(r["branch"])
        self.kept(worktree, r)
        self.assertEqual(self.branch(r["branch"]), tip)

    def test_c1_a_partly_staged_product_is_cleaned(self):
        # critic a7c-merge2 P2: a staged entry the result holds as staged is merged work, not a reason to keep.
        self.awaiting_merge()
        r = self.record()
        worktree = Path(r["worktree"])
        self.wt(worktree, "add", "ZPLAN_FIXTURE.md")
        self.assertEqual(self.merged().line, "Merged: M1 → main.")
        self.assertFalse(worktree.exists())
        self.assertIsNone(self.branch(r["branch"]))

    def test_c2_a_differing_product_tree_keeps_the_worktree_and_branch(self):
        self.awaiting_merge()
        r = self.record()
        worktree = Path(r["worktree"])
        (worktree / "leftover.txt").write_text("unmerged work\n", encoding="utf-8")
        self.assertEqual(self.merged().line, "Merged: M1 → main; left in place: %s, %s." % (worktree, r["branch"]))
        self.assertTrue(worktree.is_dir())
        self.assertEqual((worktree / "leftover.txt").read_text(), "unmerged work\n")

    def test_c2_an_unreadable_product_tree_keeps_the_worktree_and_branch(self):
        self.awaiting_merge()
        r = self.record()
        worktree = Path(r["worktree"])
        with patch.object(runs.MilestoneRuns, "product_tree", side_effect=Blocked("not read", family="project.unreadable")):
            result = self.merge()
        self.assertEqual(result.kind, "integrated")
        self.assertEqual(result.line, "Merged: M1 → main; left in place: %s, %s." % (worktree, r["branch"]))
        self.assertTrue(worktree.is_dir())
        self.assertIsNotNone(self.branch(r["branch"]))

    def test_c2_a_filesystem_failure_reading_the_tree_still_cleans_the_result_branch(self):
        self.awaiting_merge()
        r = self.record()
        worktree = Path(r["worktree"])
        # An out-of-space failure while the product tree is read (e.g. its scratch directory cannot be made) is
        # not a Git refusal: the merge still stands and only its cleanup falls back for this one step.
        with patch.object(runs.MilestoneRuns, "product_tree", side_effect=OSError(errno.ENOSPC, "No space left on device")):
            result = self.merge()
        self.assertEqual(result.kind, "integrated")
        self.assertEqual(result.line, "Merged: M1 → main; left in place: %s, %s." % (worktree, r["branch"]))
        self.assertTrue(worktree.is_dir())
        self.assertIsNotNone(self.branch(r["branch"]))
        self.assertIsNone(self.branch(r["result"]["branch"]))

    def test_c2_an_uninspectable_worktree_is_kept_and_the_result_branch_still_cleaned(self):
        self.awaiting_merge()
        r = self.record()
        worktree = Path(r["worktree"])
        # An unreadable parent makes even `is_dir` fail; the inspection is uncertain, so the worktree must not be
        # removed and the merge must still return integrated after the independent result-branch cleanup.
        parent = worktree.parent
        parent.chmod(0)
        try:
            result = self.merge()
        finally:
            parent.chmod(0o755)
        self.assertEqual(result.kind, "integrated")
        self.assertEqual(result.line, "Merged: M1 → main; left in place: %s, %s." % (worktree, r["branch"]))
        self.assertTrue(worktree.is_dir())
        self.assertIsNotNone(self.branch(r["branch"]))
        self.assertIsNone(self.branch(r["result"]["branch"]))

    def test_c2_an_unreadable_branch_check_keeps_the_branches_in_the_leftovers(self):
        self.awaiting_merge()
        r = self.record()
        worktree = Path(r["worktree"])
        real = runs.git_call

        def blocked(project, *args, **kwargs):
            if args and args[0] in {"branch", "show-ref"}:
                raise Blocked("Git did not answer; the operation was aborted.", family="git.failed")
            return real(project, *args, **kwargs)

        # A refused `branch`/`show-ref` is uncertainty, not absence: the branches remain and must be named.
        with patch.object(delivery, "git_call", side_effect=blocked):
            result = self.merge()
        self.assertEqual(result.kind, "integrated")
        self.assertEqual(result.line, "Merged: M1 → main; left in place: %s, %s."
                         % (r["branch"], r["result"]["branch"]))
        self.assertFalse(worktree.exists())
        self.assertIsNotNone(self.branch(r["branch"]))
        self.assertIsNotNone(self.branch(r["result"]["branch"]))

    # C3: scope ----------------------------------------------------------------------------------------------------

    def test_c3_a_refused_merge_cleans_nothing(self):
        self.awaiting_merge()
        r = self.record()
        worktree = Path(r["worktree"])
        (self.project / ".git" / "MERGE_HEAD").write_text(self.head() + "\n")  # an unfinished merge refuses
        self.assertEqual(self.merge().kind, "refused")
        self.assertTrue(worktree.is_dir())
        self.assertIsNotNone(self.branch(r["branch"]))
        self.assertIsNotNone(self.branch(r["result"]["branch"]))

    def test_c3_a_conflict_cleans_nothing(self):
        self.awaiting_merge()
        r = self.record()
        worktree = Path(r["worktree"])
        (self.project / "ZPLAN_FIXTURE.md").write_text("owner version\n", encoding="utf-8")
        self.git("add", "ZPLAN_FIXTURE.md")
        self.git("commit", "-qm", "owner")
        self.assertNotEqual(self.merge().kind, "integrated")
        self.assertTrue(worktree.is_dir())
        self.assertIsNotNone(self.branch(r["branch"]))
        self.assertIsNotNone(self.branch(r["result"]["branch"]))

    def test_c3_a_gated_conflict_is_open_and_cleans_nothing(self):
        self.gated()
        r = self.record()
        worktree = Path(r["worktree"])
        (self.project / "ZPLAN_FIXTURE.md").write_text("owner version\n", encoding="utf-8")
        self.git("add", "ZPLAN_FIXTURE.md")
        self.git("commit", "-qm", "owner")
        self.assertEqual(self.merge().kind, "open")
        self.assertTrue(worktree.is_dir())
        self.assertIsNotNone(self.branch(r["branch"]))
        self.assertIsNotNone(self.branch(r["result"]["branch"]))


if __name__ == "__main__":
    unittest.main()
