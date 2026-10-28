"""D4b: the merge lands beside uncommitted changes and never writes a conflict into the owner's tree.

One smoke test per criterion (M1-M5) on a real fixture project, plus the invariants the change can break: the owner's
files (bytes and `git status`) after every refusal, a conflict and a landing, and no `merge --abort`, `reset` or
`checkout` of the owner's tree.

Interpretations (none of them waives a stated requirement):
- "dirty set identical before/after" (M3, M4) is the set of `git status` entries read right before and right after
  the `merge --ff-only`; an unrelated change the owner made earlier does not block, a change that appears during the
  landing is recorded in `integration["landing"]` and the merge stays landed.
- The conflict record keeps `aborted: True` (the gate path's existing value): nothing was written, so the tree is as
  clean as it was.
- "merge later" is `/merge later`; the overlap card is the merge card turned red (`card_kinds.merge_spec`)."""

import os
import stat
import subprocess
from pathlib import Path
import unittest
from unittest.mock import patch

from terminal_planner import delivery, runs, setup
from terminal_planner.authority import Blocked
import test_merge_gate as gate
import test_process as tpr
from test_runs import ROLES, RunsTest
from tui_support import HAVE_TEXTUAL


class MergeBesideDirtTests(RunsTest):
    def done(self, a):
        controller = self.fixture_runs(a)
        r = controller.observe(controller.start("M1", 1, ROLES))
        self.assertEqual(r["outcome"], "done")
        controller.finish(r)
        return controller, r

    def owner_commit(self, name, text):
        (self.project / name).write_text(text)
        self.git("add", name)
        self.git("commit", "-qm", "owner " + name)

    def tree_state(self, *names):
        return (self.git("status", "--porcelain", "--ignored"), [(self.project / n).read_bytes() for n in names])

    def calls(self):
        """Every Git invocation of the merge, recorded while it still runs."""
        seen, real = [], runs.git_call

        def record(project, *args, **kwargs):
            seen.append(args)
            return real(project, *args, **kwargs)
        return seen, patch.object(runs, "git_call", record)

    def test_m1_a_conflict_is_recorded_from_merge_tree_and_the_dirty_tree_is_never_touched(self):
        """M1 (example): conflicting candidate + dirty unrelated file -> conflict, status and bytes identical."""
        self.approve_fixture()
        with self.fixture_authority() as a:
            controller, r = self.done(a)
            self.owner_commit("ZPLAN_FIXTURE.md", "owner version\n")
            self.owner_commit("other.txt", "tracked\n")
            (self.project / "other.txt").write_text("edited, not committed\n")
            (self.project / "notes.md").write_text("draft\n")
            head, before = self.head(), self.tree_state("other.txt", "notes.md")
            seen, patched = self.calls()
            with patched:
                self.assertIs(controller.merge(r), r)
            self.assertEqual((r["delivery"], r["integration"]["conflicts"], r["integration"]["aborted"]),
                             ("conflict", ["ZPLAN_FIXTURE.md"], True))
            self.assertEqual((self.head(), self.tree_state("other.txt", "notes.md")), (head, before))
            self.assertFalse((self.project / ".git" / "MERGE_HEAD").exists())
            self.assertIn("merge-tree", [c[0] for c in seen])
            self.assertEqual([c for c in seen if c[0] in {"merge", "reset", "checkout"}], [])

    def test_m1_m3_unrelated_changes_never_block_and_the_merge_is_off_tree_then_fast_forwarded(self):
        """M1 + M3 (example): dirty notes.md and a modified tracked file, candidate touches elsewhere -> merged with the
        owner's identity, both still dirty, and only `merge --ff-only` touched the tree."""
        self.approve_fixture()
        with self.fixture_authority() as a:
            controller, r = self.done(a)
            self.owner_commit("other.txt", "tracked\n")
            (self.project / "other.txt").write_text("edited, not committed\n")
            (self.project / "notes.md").write_text("draft\n")
            self.git("add", "other.txt")  # staged: the index differs from HEAD too
            head, before = self.head(), self.tree_state("other.txt", "notes.md")
            seen, patched = self.calls()
            with patched:
                controller.merge(r)
            merge = self.head()
            self.assertEqual((r["delivery"], r["integration"]["commit"]), ("integrated", merge))
            self.assertEqual(self.git("rev-list", "--parents", "-n", "1", merge).decode().split()[1:],
                             [head, r["result"]["commit"]])
            self.assertEqual(self.git("log", "-1", "--format=%an <%ae>", merge).decode().strip(),
                             "Fixture <fixture@example.invalid>")
            self.assertEqual(self.tree_state("other.txt", "notes.md"), before)
            self.assertEqual([c[:2] for c in seen if c[0] in {"merge", "reset", "checkout"}], [("merge", "--ff-only")])
            self.assertIn("commit-tree", [c[0] for c in seen])
            self.assertIn("merge-tree", [c[0] for c in seen])
            self.assertNotIn("--no-ff", [x for c in seen for x in c])
            self.assertIsNone(r["integration"].get("landing"))

    def test_m2_an_ignored_local_file_the_candidate_adds_is_never_overwritten(self):
        """M2 (example): the candidate adds a path, a local ignored file of that name exists -> one refusal naming it,
        the file byte-identical, the branch and the record untouched."""
        self.approve_fixture()
        with self.fixture_authority() as a:
            controller, r = self.done(a)
            self.owner_commit(".gitignore", "ZPLAN_FIXTURE.md\n")
            (self.project / "ZPLAN_FIXTURE.md").write_text("my local settings\n")
            head, before = self.head(), self.tree_state("ZPLAN_FIXTURE.md")
            with self.assertRaises(runs.Overlap) as raised:
                controller.merge(r)
            self.assertEqual(raised.exception.paths, ("ZPLAN_FIXTURE.md",))
            self.assertEqual(raised.exception.family, "milestone.merge_overlap")
            self.assertIn(r["result"]["branch"], str(raised.exception))
            self.assertEqual((self.head(), self.tree_state("ZPLAN_FIXTURE.md")), (head, before))
            self.assertEqual((r["delivery"], r["integration"]), ("awaiting_merge", None))
            self.git("rev-parse", "--verify", "refs/heads/" + r["result"]["branch"])
            # Moving the file away lets the same merge land.
            (self.project / "ZPLAN_FIXTURE.md").rename(self.project / "mine.txt")
            controller.merge(r)
            self.assertEqual(r["delivery"], "integrated")
            self.assertEqual((self.project / "mine.txt").read_text(), "my local settings\n")

    def test_m2_untracked_modified_and_parent_files_in_the_way_are_found_and_clean_ones_are_not(self):
        """M2: a changed path, or a parent of one, that is untracked, ignored or modified; a clean tracked file the
        candidate changes is no overlap; an untracked directory holding unrelated files is (the commit would write into it)."""
        git = lambda *a: subprocess.run(["git", "-C", str(self.project), *a], capture_output=True, check=True).stdout
        git("checkout", "-q", "-b", "cand")
        (self.project / "sub").mkdir()
        (self.project / "sub" / "new.txt").write_text("n\n")
        (self.project / "dir").mkdir()
        (self.project / "dir" / "one.txt").write_text("1\n")
        (self.project / "source.txt").write_text("changed\n")
        git("add", "-A")
        git("commit", "-qm", "candidate")
        candidate = git("rev-parse", "HEAD").decode().strip()
        git("checkout", "-q", "main")
        overlap = lambda: runs.overlapping_paths(self.project, candidate, runs.dirty_entries(self.project))
        self.assertEqual(overlap(), [])  # source.txt is clean: the candidate may change it
        (self.project / "sub").write_text("a file where the candidate needs a directory\n")
        self.assertEqual(overlap(), ["sub"])
        (self.project / "sub").unlink()
        (self.project / "dir").mkdir()
        (self.project / "dir" / "unrelated.txt").write_text("u\n")
        self.assertEqual(overlap(), ["dir"])  # an untracked directory the commit would write into
        (self.project / "dir" / "one.txt").write_text("mine\n")
        self.assertEqual(overlap(), ["dir/one.txt"])
        (self.project / "dir" / "one.txt").unlink()
        (self.project / "dir" / "unrelated.txt").unlink()
        (self.project / "dir").rmdir()
        (self.project / "source.txt").write_text("edited by the owner\n")
        self.assertEqual(overlap(), ["source.txt"])
        git("checkout", "--", "source.txt")
        (self.project / "outside").symlink_to(self.project / "dir")  # a symlink is never written through
        self.assertEqual(overlap(), [])

    def test_m2_untracked_and_ignored_parent_directories_are_in_the_way(self):
        """M2 regression: the commit adds drafts/x.md and (force-added) secrets/template.txt; the owner has untracked
        drafts/mine.md and ignored secrets/mine.txt -> both parent directories are reported (git shows `?? drafts/`,
        `!! secrets/`); a tracked directory with an unrelated local edit (src/) is not."""
        git = lambda *a: subprocess.run(["git", "-C", str(self.project), *a], capture_output=True, check=True).stdout
        (self.project / ".gitignore").write_text("secrets/\n")
        (self.project / "src").mkdir()
        (self.project / "src" / "a.txt").write_text("a\n")
        (self.project / "src" / "b.txt").write_text("b\n")
        git("add", "-A")
        git("commit", "-qm", "ignore secrets, add src")
        git("checkout", "-q", "-b", "cand")
        for name in ("drafts/x.md", "secrets/template.txt", "src/a.txt"):
            (self.project / name).parent.mkdir(exist_ok=True)
            (self.project / name).write_text("candidate\n")
        git("add", "-f", "-A")
        git("commit", "-qm", "candidate")
        candidate = git("rev-parse", "HEAD").decode().strip()
        git("checkout", "-q", "main")
        overlap = lambda: runs.overlapping_paths(self.project, candidate, runs.dirty_entries(self.project))
        (self.project / "src" / "b.txt").write_text("edited\n")
        self.assertEqual(overlap(), [])
        for name in ("drafts/mine.md", "secrets/mine.txt"):
            (self.project / name).parent.mkdir(exist_ok=True)
            (self.project / name).write_text("mine\n")
        self.assertEqual(overlap(), ["drafts", "secrets"])

    def test_m2_an_ignored_directory_where_the_candidate_adds_a_file_is_in_the_way(self):
        """M2 regression: the commit adds a file `cfg`, a local ignored directory `cfg/` holds the owner's file -> the
        directory is reported (the fast-forward would delete it); a directory of tracked files the commit replaces
        is no overlap."""
        git = lambda *a: subprocess.run(["git", "-C", str(self.project), *a], capture_output=True, check=True).stdout
        (self.project / ".gitignore").write_text("cfg/\n")
        git("add", ".gitignore")
        git("commit", "-qm", "ignore cfg")
        git("checkout", "-q", "-b", "cand")
        (self.project / "cfg").write_text("tracked file\n")
        git("add", "-f", "cfg")
        git("commit", "-qm", "candidate adds a file cfg")
        candidate = git("rev-parse", "HEAD").decode().strip()
        git("checkout", "-q", "main")
        (self.project / "cfg").mkdir()
        (self.project / "cfg" / "local.json").write_text("secret\n")
        self.assertEqual(runs.dirty_entries(self.project), set())
        self.assertEqual(runs.overlapping_paths(self.project, candidate, set()), ["cfg"])
        self.assertEqual((self.project / "cfg" / "local.json").read_text(), "secret\n")
        (self.project / "cfg" / "local.json").unlink()
        self.assertEqual(runs.overlapping_paths(self.project, candidate, set()), [])  # an empty directory goes cleanly

    def test_m4_a_dirty_set_that_changes_during_landing_is_recorded_and_nothing_is_reset(self):
        """M4 (example): the dirty set differs right after the landing -> the record says so, HEAD stays at the merge
        commit, the new file stays."""
        self.approve_fixture()
        with self.fixture_authority() as a:
            controller, r = self.done(a)
            real, count = runs.dirty_entries, []

            def racing(project):
                count.append(1)
                if len(count) == 2:  # right after the landing
                    (self.project / "late.txt").write_text("appeared meanwhile\n")
                return real(project)
            seen, patched = self.calls()
            with patched, patch.object(runs, "dirty_entries", racing):
                controller.merge(r)
            self.assertEqual((r["delivery"], r["integration"]["commit"]), ("integrated", self.head()))
            self.assertIn("late.txt", r["integration"]["landing"])
            self.assertEqual((self.project / "late.txt").read_text(), "appeared meanwhile\n")
            self.assertEqual([c for c in seen if c[0] in {"reset", "checkout"}], [])
            self.assertIn("late.txt", self.stored(a)[0]["integration"]["landing"])  # saved and valid in the store

    def test_m3_a_change_that_overlaps_after_the_candidate_was_built_is_refused_at_landing(self):
        """M3: the overlap is recomputed right before landing, not read once at the start."""
        self.approve_fixture()
        with self.fixture_authority() as a:
            controller, r = self.done(a)
            real = runs.commit_candidate

            def late(*args, **kwargs):
                made = real(*args, **kwargs)
                (self.project / "ZPLAN_FIXTURE.md").write_text("typed while merging\n")
                return made
            with patch.object(runs, "commit_candidate", late), self.assertRaises(runs.Overlap):
                controller.merge(r)
            self.assertEqual((self.project / "ZPLAN_FIXTURE.md").read_text(), "typed while merging\n")
            self.assertEqual(r["delivery"], "awaiting_merge")


class GatedMergeBesideDirtTests(tpr.ProfileTest):
    gated = gate.MergeGateTests.gated
    merge = gate.MergeGateTests.merge
    owner_commit = gate.MergeGateTests.owner_commit

    def test_m1_m3_the_gated_merge_lands_beside_dirty_files(self):
        self.gated()
        head = self.owner_commit()
        (self.project / "notes.md").write_text("draft\n")
        (self.project / "other.txt").write_text("edited\n")
        before = self.git("status", "--porcelain")
        self.assertEqual(self.merge().kind, "integrated")
        self.assertNotEqual(self.head(), head)
        self.assertEqual(self.git("status", "--porcelain"), before)

    @unittest.skipUnless(HAVE_TEXTUAL, "Textual is unavailable")
    def test_m2_the_gated_overlap_is_one_refusal_naming_the_files_and_the_card_offers_later_and_the_diff(self):
        self.gated()
        self.owner_commit(".gitignore", "ZPLAN_FIXTURE.md\n")
        (self.project / "ZPLAN_FIXTURE.md").write_text("mine\n")
        head = self.head()
        result = self.merge()
        self.assertEqual((result.kind, result.paths, result.stay), ("overlap", ("ZPLAN_FIXTURE.md",), True))
        self.assertIn("milestone.merge_overlap", result.line)
        self.assertEqual((self.head(), (self.project / "ZPLAN_FIXTURE.md").read_text()), (head, "mine\n"))
        self.assertEqual(self.stored()["runs"][0]["delivery"], "awaiting_merge")
        from terminal_planner.tui import card_kinds  # the card module imports Rich at load
        spec = card_kinds.merge_spec("merge:r1:M1", "12:00", "M1", None, result.paths)
        self.assertTrue(spec.alarm)
        self.assertIn("ZPLAN_FIXTURE.md", spec.text)
        self.assertEqual([command for _, command in spec.buttons], ["/merge later", "/diff"])

    def test_m1_a_gated_conflict_beside_a_dirty_file_is_recorded_and_the_tree_is_untouched(self):
        self.gated()
        self.owner_commit("ZPLAN_FIXTURE.md", "owner version\n")
        (self.project / "notes.md").write_text("draft\n")
        before = self.git("status", "--porcelain")
        self.merge()
        self.assertEqual(self.git("status", "--porcelain"), before)
        self.assertFalse((self.project / ".git" / "MERGE_HEAD").exists())
        run = self.stored()["runs"][0]
        self.assertEqual((run["delivery"], run["integration"]["conflicts"]), ("conflict", ["ZPLAN_FIXTURE.md"]))


class OldGitTests(unittest.TestCase):
    def test_m5_doctor_refuses_git_older_than_2_38_with_the_readiness_git_family(self):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            fake = Path(root) / "git"
            fake.write_text("#!/bin/sh\necho 'git version 2.37.1'\n")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            with patch.object(setup.shutil, "which", return_value=str(fake)):
                item = next(i for i in setup.readiness(None, tools=False) if i["id"] == "git")
            self.assertFalse(item["ok"])
            self.assertEqual(setup.severity(item), "block")
            self.assertIn("2.38", item["doctor"])
            self.assertIn("2.37", item["doctor"])
            self.assertIn("readiness.git", "readiness." + item["id"])
            fake.write_text("#!/bin/sh\necho 'git version 2.38.0'\n")
            with patch.object(setup.shutil, "which", return_value=str(fake)):
                self.assertTrue(next(i for i in setup.readiness(None, tools=False) if i["id"] == "git")["ok"])


if __name__ == "__main__":
    unittest.main()
