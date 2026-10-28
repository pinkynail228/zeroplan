"""D4c: the confirmed «commit» action for the owner's own files (`terminal_planner/user_commit.py`, the
architect's `zplan_propose_commit`, the controller's `commit_files`, the commit card).

One test per criterion U1-U5 plus the invariants the action can break (the owner's files, secrets, the index). Fixture
repositories live in a scratch directory under an isolated HOME with no global Git config; hooks are real scripts.

Interpretations (the reviewers never see the worker's summary):

- "The project lock used by merge": merges run as Controller jobs inside the session that holds the Authority's
  project flock for its whole life; what a commit must not overlap is a landing merge. `Controller._project_op` is
  held by both merge paths (the owner's and the architect's), and `commit_files` takes it without waiting: a merge
  being landed refuses the commit with a line, a commit never queues behind it on the UI thread.
- «yes» runs on the UI thread under `App.suspend()` exactly like the login, so `commit_files` takes `terminal=True`
  there (git inherits the terminal); the tests pass `terminal=False` to capture the output.
- The stat of an untracked file is a «new file» line (a diff against HEAD has none); the architect's diff of it is
  `git diff --no-index` against /dev/null. Both are scrubbed and capped; LFS and binary handling are git's own
  («Binary files differ»), no extra marking.
- A staged rename is detected from `status --renames`; an unstaged `mv` is a deletion plus a new file, which git
  itself does not pair, so both are separate paths there.
- The architect is told the answer through `zplan_status` (`commit`), not by holding the tool call open.
"""

import os
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import tui_support  # noqa: F401  (the offline wheelhouse joins sys.path before the guarded imports)
from tui_support import HAVE_TEXTUAL

from terminal_planner import architect_tools, process, user_commit
from terminal_planner.authority import Blocked

try:
    from terminal_planner.tui import card_host, card_kinds, strings
    from terminal_planner.tui.controller import Controller
except ImportError:  # pragma: no cover - the bare import scan covers this path
    card_host = card_kinds = strings = Controller = None

HAVE = HAVE_TEXTUAL and card_kinds is not None


class RepoTest(unittest.TestCase):
    identity = True

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        home = self.root / "home"
        home.mkdir()
        patcher = patch.dict(os.environ, {"HOME": str(home), "XDG_CONFIG_HOME": str(home / "xdg"),
                                          "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.project = self.root / "proj"
        self.project.mkdir()
        self.git("init", "-q", "-b", "main")
        self.write("a.py", "one\n")
        self.write("b.py", "two\n")
        self.write("other.txt", "x\n")
        self.git("add", "-A")
        self.git("-c", "user.name=Init", "-c", "user.email=init@example.com", "commit", "-q", "-m", "init")
        if self.identity:
            self.git("config", "user.name", "Owner Name")
            self.git("config", "user.email", "owner@example.com")
        self.marker = self.root / "hook-ran"

    def git(self, *args):
        result = subprocess.run(["git", "-C", str(self.project), *args], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def write(self, name, text):
        path = self.project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def hook(self, name, body):
        path = self.project / ".git" / "hooks" / name
        path.parent.mkdir(exist_ok=True)
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(0o755)

    def head(self):
        return self.git("rev-parse", "HEAD").strip()

    def index(self):
        return (self.project / ".git" / "index").read_bytes()

    def state(self):
        """Everything a refused or declined action must leave alone."""
        return (self.head(), self.index(), self.git("--no-optional-locks", "status", "--porcelain", "-z"))

    def dirty(self):
        self.write("a.py", "one\nchanged\n")
        self.write("new.py", "fresh\n")


class SelectionTests(RepoTest):
    def test_u2_the_paths_are_the_proposal_met_with_the_live_status(self):
        """proposal [".env", "a.py", ...] -> .env refused and named, a.py selected; unchanged, ignored, directory
        and outside paths are refused with their reason; nothing is ever added by force."""
        self.write(".gitignore", "*.log\n")
        self.git("add", ".gitignore")
        self.git("commit", "-q", "-m", "ignore")
        self.dirty()
        self.write(".env", "TOKEN=abc\n")
        self.write("x.log", "ignored\n")
        self.write("sub/inner.py", "inner\n")
        proposal = [".env", "a.py", "new.py", "x.log", "b.py", "sub", "../out", "missing.py"]
        selection = user_commit.select(self.project, proposal)
        self.assertEqual(selection.paths, ("a.py", "new.py"))
        self.assertEqual(selection.untracked, ("new.py",))
        self.assertEqual({path for path, _ in selection.refused},
                         {".env", "x.log", "b.py", "sub", "../out", "missing.py"})
        user_commit.commit(self.project, proposal, "msg")
        self.assertEqual(self.git("ls-files").split(), [".gitignore", "a.py", "b.py", "new.py", "other.txt"])
        self.assertIn("?? .env", self.git("status", "--porcelain"))

    def test_u2_a_rename_needs_both_sides(self):
        self.git("mv", "a.py", "c.py")
        alone = user_commit.select(self.project, ["c.py"])
        self.assertEqual(alone.paths, ())
        self.assertIn("rename", alone.refused[0][1])
        self.assertEqual(user_commit.select(self.project, ["c.py", "a.py"]).paths, ("a.py", "c.py"))
        user_commit.commit(self.project, ["c.py", "a.py"], "rename")
        self.assertEqual(self.git("ls-files").split(), ["b.py", "c.py", "other.txt"])

    def test_u2_every_path_is_literal(self):
        """A file named `*.py` is that file only; a glob never reaches the modified a.py."""
        self.write("a.py", "one\nchanged\n")
        self.write("*.py", "star\n")
        result = user_commit.commit(self.project, ["*.py"], "star")
        self.assertEqual(result.paths, ("*.py",))
        self.assertEqual(self.git("show", "--name-only", "--format=", "HEAD").split(), ["*.py"])
        self.assertIn(" M a.py", self.git("status", "--porcelain"))


class CommitTests(RepoTest):
    def test_u3_u5_only_the_selection_lands_with_the_owners_identity_and_other_staged_stays(self):
        self.dirty()
        self.write(".env", "TOKEN=abc\n")
        self.write("other.txt", "staged\n")
        self.git("add", "other.txt")
        self.write("b.py", "two\nunstaged\n")
        self.hook("pre-commit", 'echo ran >> "%s"' % self.marker)
        before = self.head()
        result = user_commit.commit(self.project, ["a.py", "new.py", ".env"], "Change a, add new")
        self.assertEqual(self.git("show", "--name-only", "--format=", "HEAD").split(), ["a.py", "new.py"])
        self.assertEqual(self.git("log", "-1", "--format=%an <%ae>|%s").strip(),
                         "Owner Name <owner@example.com>|Change a, add new")
        self.assertEqual(self.git("rev-parse", "HEAD~1").strip(), before)
        self.assertEqual(self.git("status", "--porcelain").splitlines(), [" M b.py", "M  other.txt", "?? .env"])
        self.assertTrue(self.marker.exists(), "the hooks run")
        self.assertEqual((result.extra, result.parent_moved, [p for p, _ in result.refused]), ((), False, [".env"]))

    def test_u3_a_refusing_hook_leaves_head_and_index_byte_identical(self):
        self.dirty()
        self.write("other.txt", "staged\n")
        self.git("add", "other.txt")
        self.hook("pre-commit", 'echo ran >> "%s"\nexit 1' % self.marker)
        before = self.state()
        with self.assertRaises(Blocked) as raised:
            user_commit.commit(self.project, ["a.py", "new.py"], "msg")
        self.assertEqual(raised.exception.family, "commit.failed")
        self.assertEqual(self.state(), before)
        self.assertTrue(self.marker.exists())
        self.assertIn("?? new.py", self.git("status", "--porcelain"))

    def test_u3_the_index_is_byte_identical_right_after_a_commit_too(self):
        """A fresh index holds git's cache-tree; `add -N` drops it and `rm --cached` alone would not bring it back."""
        self.write("new.py", "fresh\n")
        self.hook("pre-commit", "exit 1")
        before = self.state()
        with self.assertRaises(Blocked):
            user_commit.commit(self.project, ["new.py"], "msg")
        self.assertEqual(self.state(), before)

    def test_u3_the_profile_commit_takes_the_same_undo(self):
        """`process.Profile._commit_file` on a refusing hook: the new file is no longer staged."""
        self.write(process.PROFILE_FILE, "{}\n")
        self.hook("pre-commit", "exit 1")
        before = self.state()
        notice = process.Profile._commit_file(SimpleNamespace(project=self.project))
        self.assertIn(process.PROFILE_FILE, notice)
        self.assertEqual(self.state(), before)

    def test_u5_what_the_hooks_changed_is_reported(self):
        self.dirty()
        self.hook("pre-commit", 'echo formatted >> b.py\ngit add b.py')
        result = user_commit.commit(self.project, ["a.py"], "msg")
        self.assertEqual(result.extra, ("b.py",))
        self.assertIn("b.py", "\n".join(result.lines()))

    def test_u5_a_moved_parent_is_reported(self):
        self.dirty()
        mark = self.root / "again"
        self.hook("post-commit", '[ -e "%s" ] || { : > "%s"; git commit -q --allow-empty -m hook; }' % (mark, mark))
        result = user_commit.commit(self.project, ["a.py"], "msg")
        self.assertTrue(result.parent_moved)


class RefusalTests(RepoTest):
    def test_u4_each_state_is_refused_with_its_fix_and_nothing_runs(self):
        self.dirty()
        self.hook("pre-commit", 'echo ran >> "%s"' % self.marker)
        git_dir = self.project / ".git"
        head = self.head()
        cases = {
            "detached": (lambda: self.git("checkout", "-q", "--detach"), "is detached", "commit.refused"),
            "merge": (lambda: (git_dir / "MERGE_HEAD").write_text(head + "\n"), "merge is in progress", "commit.refused"),
            "rebase": (lambda: (git_dir / "rebase-merge").mkdir(), "rebase is in progress", "commit.refused"),
            "lock": (lambda: (git_dir / "index.lock").write_text(""), "index.lock", "commit.refused"),
            "identity": (lambda: self.git("config", "--unset", "user.name"), "user.name", "readiness.identity"),
        }
        for name, (arrange, words, family) in cases.items():
            with self.subTest(name):
                arrange()
                before = (self.head(), self.index())
                with self.assertRaises(Blocked) as raised:
                    user_commit.commit(self.project, ["a.py", "new.py"], "msg")
                self.assertIn(words, str(raised.exception))
                self.assertEqual(raised.exception.family, family)
                self.assertEqual((self.head(), self.index()), before)
                self.assertFalse(self.marker.exists())
                for leftover in ("MERGE_HEAD", "index.lock"):
                    (git_dir / leftover).unlink(missing_ok=True)
                if name == "rebase":
                    (git_dir / "rebase-merge").rmdir()
                if name == "detached":
                    self.git("checkout", "-q", "main")
                if name == "identity":
                    self.git("config", "user.name", "Owner Name")


@unittest.skipUnless(HAVE, "Textual is not installed")
class ProposalTests(RepoTest):
    """U1: the architect proposes, the owner decides; only «yes» commits."""

    def setUp(self):
        super().setUp()
        self.controller = Controller(lambda stack: None, "t", project=self.project)
        self.app = SimpleNamespace(authority=SimpleNamespace(project=self.project))

    def propose(self, paths=("a.py", "new.py", ".env"), message="Change a, add new"):
        return self.controller._run_tool(self.app, "zplan_propose_commit", {"paths": list(paths), "message": message})

    def test_u1_a_proposal_shows_stat_and_a_scrubbed_diff_and_commits_nothing(self):
        self.dirty()
        self.write("a.py", "one\npassword=hunter2\n")
        self.write(".env", "TOKEN=abc\n")
        before = self.state()
        reply = self.propose()
        self.assertEqual(self.state(), before)
        self.assertEqual(reply["status"], "awaiting_owner")
        self.assertEqual(reply["paths"], ["a.py", "new.py"])
        self.assertEqual([item["path"] for item in reply["refused"]], [".env"])
        self.assertIn("a.py", reply["stat"])
        self.assertIn("new.py", reply["stat"])
        self.assertIn("+fresh", reply["diff"])
        self.assertNotIn("hunter2", reply["diff"])  # scrubbed
        self.assertNotIn("TOKEN=abc", str(reply))
        self.assertEqual(self.controller.commit_proposal.state, "awaiting")

    def test_u1_declining_runs_nothing_and_the_proposal_cannot_be_confirmed_afterwards(self):
        self.dirty()
        self.propose()
        proposal = self.controller.commit_proposal
        before = self.state()
        self.controller.decline_commit(proposal.id)
        self.assertEqual(self.controller.commit_proposal.state, "declined")
        with self.assertRaises(Blocked):
            self.controller.commit_files(proposal.id, terminal=False)
        self.assertEqual(self.state(), before)

    def test_u1_only_the_owners_yes_commits_and_the_architect_status_shows_it(self):
        self.dirty()
        self.propose()
        proposal = self.controller.commit_proposal
        self.write("a.py", "one\nchanged again after the proposal\n")  # the live status decides at «yes»
        result = self.controller.commit_files(proposal.id, terminal=False)
        self.assertEqual(result.paths, ("a.py", "new.py"))
        self.assertEqual(self.git("show", "HEAD:a.py"), "one\nchanged again after the proposal\n")
        self.assertEqual(self.controller.commit_proposal.state, "committed")
        with self.assertRaises(Blocked):  # a second «yes» commits nothing more
            self.controller.commit_files(proposal.id, terminal=False)

    def test_u4_a_landing_merge_holds_the_lock_the_commit_needs(self):
        self.dirty()
        self.propose()
        before = self.state()
        with self.controller._project_op:
            with self.assertRaises(Blocked) as raised:
                self.controller.commit_files(self.controller.commit_proposal.id, terminal=False)
        self.assertIn("merge", str(raised.exception))
        self.assertEqual(self.state(), before)
        self.controller.commit_files(self.controller.commit_proposal.id, terminal=False)  # the lock is free again

    def test_u2_a_proposal_of_credentials_only_is_refused_and_bad_arguments_are_invalid(self):
        self.write(".env", "TOKEN=abc\n")
        with self.assertRaises(Blocked) as raised:
            self.propose(paths=[".env"])
        self.assertEqual(raised.exception.family, "commit.refused")
        self.assertIsNone(self.controller.commit_proposal)
        for args in ({"paths": "a.py", "message": "m"}, {"paths": [], "message": "m"}, {"paths": ["a.py"], "message": " "},
                     {"paths": ["a.py"], "message": "m", "force": True}):
            with self.subTest(args):
                with self.assertRaises(Blocked) as raised:
                    self.controller._run_tool(self.app, "zplan_propose_commit", args)
                self.assertEqual(raised.exception.family, "architect.request_invalid")

    def test_the_tool_is_an_action_tool_with_a_strict_schema(self):
        tool = next(t for t in architect_tools.TOOLS if t["name"] == "zplan_propose_commit")
        self.assertIn("zplan_propose_commit", architect_tools.ACTION_TOOLS)
        self.assertFalse(tool["inputSchema"]["additionalProperties"])
        self.assertEqual(tool["inputSchema"]["required"], ["paths", "message"])


@unittest.skipUnless(HAVE, "Textual is not installed")
class CardTests(RepoTest):
    """U1 at the card: what the owner reads, and what «yes» and «no» do on the real card methods."""

    def setUp(self):
        super().setUp()
        self.controller = Controller(lambda stack: None, "t", project=self.project)
        self.app = SimpleNamespace(authority=SimpleNamespace(project=self.project))
        self.dirty()
        self.write(".env", "TOKEN=abc\n")
        self.controller._run_tool(self.app, "zplan_propose_commit",
                                  {"paths": ["a.py", "new.py", ".env"], "message": "Change a, add new"})
        self.closed = []
        suspended = []

        @contextmanager
        def suspend():
            suspended.append(True)
            yield

        self.suspended = suspended
        self.screen = SimpleNamespace(
            app=SimpleNamespace(controller=self.controller, suspend=suspend, request_refresh=lambda: None,
                                changed=lambda: None),
            merge_card_at=lambda key: "12:00", status_note=lambda text: self.closed.append(("note", text)),
            close_card=lambda key, text: self.closed.append((key, text)))

    def test_u1_the_card_shows_message_stat_warning_and_two_buttons(self):
        (spec,) = card_kinds.commit_card_source(self.screen)
        for needle in ("Change a, add new", "a.py", "new.py", user_commit.STAMP, ".env"):
            self.assertIn(needle, spec.text)
        self.assertEqual([(label, command) for label, command in spec.buttons],
                         [(strings.text("card.commit_yes"), "/approve"), (strings.text("card.commit_no"), "/decline")])
        self.assertEqual(card_kinds.CARD_ROUTES[("/approve", "commit")].__name__, "<lambda>")

    def test_u1_no_card_once_the_proposal_is_decided(self):
        proposal = self.controller.commit_proposal
        self.controller.decline_commit(proposal.id)
        self.assertEqual(tuple(card_kinds.commit_card_source(self.screen)), ())

    def test_u1_no_runs_nothing_and_yes_commits_under_the_terminal_suspend(self):
        key = card_kinds.commit_key(self.controller.commit_proposal)
        before = self.state()
        card_host.CardHost.decline_commit(self.screen, key)
        self.assertEqual(self.state(), before)
        self.assertEqual(self.suspended, [])
        self.assertEqual(self.closed[-1][0], key)
        # a new proposal, then «yes»; terminal=True hands the real terminal to git, so the fixture captures it
        self.controller._run_tool(self.app, "zplan_propose_commit", {"paths": ["a.py"], "message": "Only a"})
        key = card_kinds.commit_key(self.controller.commit_proposal)
        real = self.controller.commit_files
        with patch.object(self.controller, "commit_files", lambda pid: real(pid, terminal=False)):
            card_host.CardHost.confirm_commit(self.screen, key)
        self.assertEqual(self.suspended, [True])
        self.assertEqual(self.git("show", "--name-only", "--format=", "HEAD").split(), ["a.py"])
        self.assertIn(self.head()[:12], self.closed[-1][1])


if __name__ == "__main__":
    unittest.main()
