"""D4a: uncommitted changes never block, and every zplan reader sees HEAD.

Real temporary Git repositories, the fixture engine and the scripted native CLI of `test_terminal_planner`; no
provider, no network. Each test fails on the code before D4a.

Interpretations (the task leaves them open):
- «a stored 0.7.0 revision» is a record whose baseline carries no `v2:` prefix: it is checked with the old formula
  (HEAD, branch and the working-tree state), so on a clean tree it is current and on an edited tree it is stale.
- «write_set ∩ uncommitted paths» treats a write_set entry as a file, a directory or a glob; the warning names the
  entry and the uncommitted paths it covers (`write_set src/a.py, a.py modified` is read as src/a.py modified).
- A symlink is not a regular file of the HEAD tree, so `project_read` neither lists nor reads it.
- The merge paths are covered by tests/test_merge_dirty.py."""

import hashlib
from pathlib import Path
import re
from types import SimpleNamespace
import unittest

from terminal_planner import architect, foreman, merge_critic, project_read, setup
from terminal_planner.authority import Authority as RealAuthority, BASELINE_PREFIX, Blocked, baseline, digest
from terminal_planner.runs import FixtureDriver, MilestoneRuns
import test_foreman
import test_plan_stop
import test_runs
import test_task_gate_record as gates
import test_terminal_planner as tp
from test_terminal_planner import ROLES
from tui_support import HAVE_TEXTUAL

ROOT = Path(__file__).resolve().parents[1]


def make_dirty(project):
    """A modified tracked file and an untracked one: the tree holds what the last commit does not."""
    (project / "source.txt").write_text("edited, not committed\n")
    (project / "new.txt").write_text("untracked\n")


class PlanTests(test_plan_stop.PlanStopTest):
    def test_k1_the_planner_checkout_is_made_from_head_of_a_dirty_project(self):
        make_dirty(self.project)
        engine, calls = self.engine([])
        with self.authority() as authority:
            self.begin(authority, "native")
            directory, workspace = engine.prepare(authority)
        self.assertEqual(calls, [])
        self.assertEqual((workspace / "source.txt").read_text(), "baseline\n")
        self.assertFalse((workspace / "new.txt").exists())


class TaskGateTests(gates.NativeGateBase):
    def test_k1_the_task_check_checkout_is_made_from_head_of_a_dirty_project(self):
        self.approved_native_plan()
        make_dirty(self.project)
        with self.bound() as authority:
            engine, _ = self.dispatching([])
            service = self.delivery(authority, engine)
            status, plan = service.task_gate_admission("M1")
            record, documents = service.task_gate_new("M1", None, plan, status, engine)
            directory, workspace = engine.gate_prepare(authority, record, documents)
        self.assertEqual((workspace / "source.txt").read_text(), "baseline\n")
        self.assertFalse((workspace / "new.txt").exists())


class MergeCriticTests(tp.ProjectTest):
    native = tp.NativeTests.native
    engine = tp.NativeTests.engine

    def test_k1_the_merge_critic_checkout_is_made_from_a_dirty_project(self):
        engine, _ = self.engine([])
        head = self.git("rev-parse", "HEAD").decode().strip()
        tree = self.git("rev-parse", "HEAD^{tree}").decode().strip()
        documents = {name: {"name": name} for name in merge_critic.DOCUMENTS}
        record = {"id": "critic-1", "run_id": None, "identity": {"candidate": head, "tree": tree},
                  "documents": {name: digest(value) for name, value in documents.items()}}
        make_dirty(self.project)
        with RealAuthority(None, self.project) as authority:
            directory, workspace = engine.critic_prepare(authority, record, documents)
        self.assertEqual((workspace / "source.txt").read_text(), "baseline\n")
        self.assertFalse((workspace / "new.txt").exists())


class StartTests(test_runs.RunsTest):
    def test_k1_a_milestone_starts_from_head_of_a_dirty_project(self):
        self.approve_fixture()
        make_dirty(self.project)
        with self.fixture_authority() as a:
            record = self.fixture_runs(a).start("M1", 1, ROLES)
        worktree = Path(record["worktree"])
        self.assertEqual((worktree / "source.txt").read_text(), "baseline\n")
        self.assertFalse((worktree / "new.txt").exists())
        self.assertEqual((self.project / "new.txt").read_text(), "untracked\n")  # the user's tree is untouched


class ReadinessTests(tp.ProjectTest):
    def clean_item(self):
        return next(i for i in setup.check_target(self.project) if i["id"] == "clean")

    def test_k1_the_clean_item_is_information_and_names_an_uncommitted_profile(self):
        self.assertEqual(self.clean_item()["line"], "Working tree clean")
        make_dirty(self.project)
        item = self.clean_item()
        self.assertTrue(item["ok"])
        self.assertEqual(item["severity"], "ok")
        self.assertEqual(item["line"], "Not committed: 2 files — the plan sees the last commit")
        (self.project / "zplan.process.json").write_text("{}\n")
        item = self.clean_item()
        self.assertTrue(item["ok"])
        self.assertIn("3 files", item["line"])
        self.assertIn("zplan.process.json", item["line"])


class BaselineTests(tp.ProjectTest):
    def test_k2_the_baseline_is_v2_of_head_and_branch_and_ignores_the_tree(self):
        before = baseline(self.project)
        self.assertTrue(before.startswith(BASELINE_PREFIX))
        make_dirty(self.project)
        self.git("update-index", "--assume-unchanged", "source.txt")  # a hidden edit is no longer an error
        self.assertEqual(baseline(self.project), before)
        self.git("add", "new.txt")
        self.git("commit", "-qm", "new")
        self.assertNotEqual(baseline(self.project), before)
        after = baseline(self.project)
        self.git("switch", "-q", "-c", "other")
        self.assertNotEqual(baseline(self.project), after)

    def test_k2_a_plan_stays_approvable_after_an_unrelated_edit_and_goes_stale_on_a_commit(self):
        with tp.Authority(self.state, self.project) as authority:
            self.begin(authority)
            self.propose(authority)
            make_dirty(self.project)
            self.assertTrue(authority.fresh())
            self.git("add", "new.txt")
            self.git("commit", "-qm", "new")
            self.assertFalse(authority.fresh())
            with self.assertRaises(Blocked) as raised:
                authority.approve(1)
            self.assertEqual(raised.exception.family, "plan.stale")

    def test_k2_a_record_without_the_prefix_is_checked_with_the_old_formula(self):
        def old_formula():
            digest_ = hashlib.sha256()
            digest_.update(self.git("rev-parse", "HEAD"))
            digest_.update(self.git("symbolic-ref", "--quiet", "--short", "HEAD"))
            digest_.update(self.git("status", "--porcelain=v1", "-z", "--untracked-files=all"))
            digest_.update(self.git("diff", "--no-ext-diff", "--no-textconv", "--binary", "HEAD"))
            return digest_.hexdigest()

        with tp.Authority(self.state, self.project) as authority:
            self.begin(authority)
            self.propose(authority)
            authority.current["baseline"] = baseline(self.project)  # a new record: the tree is not part of it
            (self.project / "source.txt").write_text("edited\n")
            self.assertTrue(authority.fresh())
            self.git("checkout", "--", "source.txt")
            authority.current["baseline"] = old_formula()  # a 0.7.0 revision, stored on a clean tree
            self.assertTrue(authority.fresh())
            (self.project / "source.txt").write_text("edited\n")
            self.assertFalse(authority.fresh())  # the old formula saw the tree
            self.git("checkout", "--", "source.txt")
            self.assertTrue(authority.fresh())


class ReadTests(tp.ProjectTest):
    def test_k3_project_read_sees_head_not_the_disk(self):
        self.project.joinpath("kept.txt").write_text("only in head\n")
        (self.project / "link").symlink_to("source.txt")
        self.git("add", "kept.txt", "link")
        self.git("commit", "-qm", "kept")
        (self.project / "source.txt").write_text("baseline\nuncommitted needle\n")
        (self.project / "kept.txt").unlink()
        (self.project / "new.txt").write_text("needle in an untracked file\n")
        root = self.project
        self.assertEqual(project_read.list_files(root, root)["paths"], ["kept.txt", "source.txt"])
        self.assertEqual(project_read.read_file(root, root, "kept.txt")["lines"], ["only in head"])
        self.assertEqual(project_read.read_file(root, root, "source.txt")["lines"], ["baseline"])
        self.assertEqual(project_read.search(root, root, "needle")["hits"], [])
        self.assertEqual(project_read.search(root, root, "only in")["hits"],
                         [{"path": "kept.txt", "line": 1, "text": "only in head"}])
        for path in ("new.txt", "link"):
            with self.assertRaises(Blocked) as raised:
                project_read.read_file(root, root, path)
            self.assertEqual(raised.exception.family, "read.outside_project")

    def test_k4_uncommitted_paths_follow_status_including_renames(self):
        self.git("mv", "source.txt", "moved.txt")
        (self.project / "new.txt").write_text("x\n")
        self.assertEqual(sorted(project_read.uncommitted_paths(self.project)), ["moved.txt", "new.txt"])
        self.assertEqual(project_read.shown_paths(["a", "b", "c", "d", "e", "f", "g"]), "a, b, c, d, e and 2 more")


class ForemanTests(unittest.TestCase):
    setUp = test_foreman.ForemanTest.setUp  # the fixture only: its own tests are not run again
    write = test_foreman.ForemanTest.write
    commit = test_foreman.ForemanTest.commit

    def test_k3_a_citation_that_exists_only_in_an_uncommitted_edit_is_missing(self):
        self.write("src/a.py", "one\n")
        self.commit()
        self.write("src/a.py", "one\ntwo\n")
        brief = test_foreman.make_brief(write_set=["src/other.py"], reuse="see `src/a.py:2`")
        self.assertEqual([(f["check"], f["blocking"]) for f in foreman.inspect(self.p, brief)], [("F1", True)])

    def test_k4_the_write_set_warns_about_uncommitted_paths(self):
        self.write("src/a.py", "one\n")
        self.write("src/b.py", "one\n")
        self.commit()
        brief = test_foreman.make_brief(write_set=["src/a.py", "src/b.py", "src/new.py"])
        self.assertEqual(foreman.inspect(self.p, brief), [])
        self.write("src/a.py", "edited\n")
        found = foreman.inspect(self.p, brief)
        self.assertEqual([(f["check"], f["blocking"]) for f in found], [("F6", False)])
        self.assertIn("src/a.py", found[0]["text"])
        self.assertNotIn("src/b.py", found[0]["text"])
        for entry in ("src", "src/*.py"):  # a directory and a glob cover the uncommitted file too
            found = foreman.inspect(self.p, test_foreman.make_brief(write_set=[entry]))
            self.assertEqual([f["check"] for f in found], ["F6"], entry)
            self.assertIn("src/a.py", found[0]["text"])


class ArchitectTests(tp.ProjectTest):
    def test_k4_the_state_section_lists_the_first_five_uncommitted_paths(self):
        names = ["f%d.txt" % number for number in range(1, 8)]
        section = architect._state_section({"project": "p", "branch": "main", "uncommitted": names})
        self.assertIn("f1.txt, f2.txt, f3.txt, f4.txt, f5.txt and 2 more", section)
        self.assertNotIn("f6.txt", section)
        self.assertNotIn("Uncommitted", architect._state_section({"project": "p", "branch": "main"}))

    def test_k4_the_controller_reports_the_uncommitted_paths(self):
        make_dirty(self.project)
        with tp.Authority(self.state, self.project) as authority:
            runs = MilestoneRuns(authority, FixtureDriver(self.root / "fixture-runs", "done"), worktrees=self.root / "w")
            self.assertEqual(sorted(runs.uncommitted()), ["new.txt", "source.txt"])

    @unittest.skipUnless(HAVE_TEXTUAL, "Textual is unavailable")
    def test_k4_the_chat_snapshot_carries_the_uncommitted_paths(self):
        from terminal_planner.tui.app import ZplanApp
        from terminal_planner.tui.controller import Snapshot
        snapshot = Snapshot(project="p", branch="main", clean=False, version=None, status=None, lines=(), roles=(),
                            uncommitted=("a.txt", "b.txt"))
        app = SimpleNamespace(snapshot=snapshot, controller=SimpleNamespace(name="p"))
        self.assertEqual(ZplanApp.chat_snapshot(app)["uncommitted"], ["a.txt", "b.txt"])


class TextTests(unittest.TestCase):
    def test_k5_no_text_tells_to_commit_before_planning(self):
        phrase = re.compile("clean working tree|clean tree", re.IGNORECASE)
        found = {}
        for path in [*(ROOT / "terminal_planner").rglob("*.py"), ROOT / "README.md", ROOT / "docs" / "REFERENCE.md",
                     ROOT / "docs" / "USER_FLOW.md"]:
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if phrase.search(line):
                    found.setdefault(path.name, []).append(number)
        self.assertEqual(found, {}, found)


if __name__ == "__main__":
    unittest.main()
