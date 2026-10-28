"""D6b: the first-run fixes from the newcomer test (R6). One smoke test per criterion G1-G5, fixtures only.

A fake `codex` (a shell script that logs its argv and the colour variables it got) stands in for the pinned Codex;
repositories, HOME and XDG are scratch paths, never the runner's. Each test fails on the code before D6b.

Interpretations (the reviewers never see the worker's summary):
- G1 "Ctrl-C during `zplan login`": a SIGINT reaching Python (the fake child signals its parent) and the Codex child
  leaving with 130 on its own both end as “Login interrupted” and exit 130. A login in a home that is not zplan's runs no
  Codex (D6a) and gets no “Login not finished” either; a login that fails with another code keeps that hint.
- G1 "the commit card is caught like login's": `user_commit.commit` turns the interrupt into a `Blocked` (family
  `commit.failed`, “Commit interrupted”), which the card already shows as a receipt; `CardHost.confirm_commit` also
  catches an interrupt that arrives outside the commit.
- G2 "one hint line": the editor's own copy of its key bar is gone; the modal's key bar at the bottom of the screen
  (`Modal.key_bar`) is the one line. The picked button of a group is the one labelled «● »; focus keeps its own look.
- G3 the bootstrap card gets a “Autonomy” line (the owner's word for the level, and max_runs); the
  `zplan profile` line keeps the level as stored, without “(for later stages)”.
- G4 `profile init` that fails to commit keeps the notice that names the command (the file is not committed then).
- G5 "read-only": `cli.ReadOnlyAuthority` takes no lock (`Authority` is outside the write-set) and writes nothing.
  The overview's integration check (a run merged by hand, or a reset) updates the records in memory only: `save` is
  a no-op there, so `status` shows the merge and the store's bytes stay as they were.
"""

import contextlib
import io
import os
from pathlib import Path
import signal
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import tui_support  # noqa: F401  (the offline wheelhouse joins sys.path before the guarded imports)
from tui_support import HAVE_TEXTUAL

from terminal_planner import cli, process, setup, user_commit
from terminal_planner.authority import Authority, Blocked, production_root
from terminal_planner.cli import Terminal
from test_runs import ROLES, RunsTest
from test_terminal_planner import ProjectTest

if HAVE_TEXTUAL:
    from textual.app import App
    from textual.widgets import Button, Input
    from terminal_planner.tui import card_host
    from terminal_planner.tui.modals import ProfileScreen

FAKE = """#!/bin/sh
echo "$@" >> "$FAKE_CODEX_LOG"
case "$*" in
  *"login status"*) exit 1 ;;
  *device-auth*)
    echo "env NO_COLOR=${NO_COLOR-unset} TERM=${TERM-unset}" >> "$FAKE_CODEX_LOG"
    case "$FAKE_CODEX_MODE" in
      sigint) kill -INT "$PPID"; sleep 5 ;;
      child130) exit 130 ;;
      fail) exit 7 ;;
    esac ;;
esac
exit 0
"""


class LoginInterruptTests(unittest.TestCase):
    """G1, the login."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        (self.root / "home").mkdir()
        self.log = self.root / "codex.log"
        environment = patch.dict(os.environ, {"HOME": str(self.root / "home"), "XDG_DATA_HOME": str(self.root / "data"),
                                              "XDG_CONFIG_HOME": str(self.root / "config"), "TERM": "xterm",
                                              "FAKE_CODEX_LOG": str(self.log), "FAKE_CODEX_MODE": ""})
        environment.start()
        self.addCleanup(environment.stop)
        for name in ("CODEX_HOME", "CODEX_API_KEY", "OPENAI_API_KEY", "NO_COLOR"):
            os.environ.pop(name, None)
        for patcher in (patch.object(setup, "platform_key", return_value=("Darwin", "arm64")),
                        patch.object(setup, "check_installation", return_value=setup.tools_root())):
            patcher.start()
            self.addCleanup(patcher.stop)
        codex = setup.tool_paths()[1]
        codex.parent.mkdir(parents=True)
        codex.write_text(FAKE)
        codex.chmod(0o755)
        before = signal.signal(signal.SIGINT, signal.default_int_handler)  # a runner may have left SIGINT ignored
        self.addCleanup(signal.signal, signal.SIGINT, before)

    def run_login(self, mode="", tty=False):
        os.environ["FAKE_CODEX_MODE"] = mode
        out = io.StringIO()
        stdout = SimpleNamespace(isatty=lambda: tty)
        with patch.object(cli, "Terminal", lambda: Terminal(io.StringIO(), out)), \
                patch.object(setup, "sys", SimpleNamespace(stdout=stdout)):
            code = cli.main(["login"])
        return code, out.getvalue()

    def test_g1_ctrl_c_during_login_says_so_and_exits_130(self):
        for mode in ("sigint", "child130"):  # SIGINT reaches zplan / only the Codex child leaves with 130
            with self.subTest(mode=mode):
                code, shown = self.run_login(mode)
                self.assertEqual(code, 130)
                self.assertIn("Login interrupted", shown)
                for absent in ("Login not finished", "Session closed", "setup.login_failed"):
                    self.assertNotIn(absent, shown)

    def test_g1_another_failure_keeps_its_hint_and_a_foreign_home_gets_none(self):
        code, shown = self.run_login("fail")
        self.assertEqual(code, 7)
        self.assertIn("Login not finished; retry zplan login.", shown)
        mine = self.root / "mine"
        mine.mkdir()
        with patch.dict(os.environ, {"CODEX_HOME": str(mine)}):  # not zplan's home: D6a says whose Codex it is
            code, shown = self.run_login("fail")
        self.assertEqual(code, 1)
        self.assertIn("This is your Codex (%s)" % mine, shown)
        self.assertNotIn("Login not finished", shown)

    def test_g1_a_codex_child_off_a_terminal_gets_no_colour(self):
        for tty, expected in ((False, "env NO_COLOR=1 TERM=dumb"), (True, "env NO_COLOR=unset TERM=xterm")):
            with self.subTest(tty=tty):
                self.log.unlink(missing_ok=True)
                self.assertEqual(self.run_login(tty=tty)[0], 0)
                self.assertIn(expected, self.log.read_text().splitlines())


class CommitInterruptTests(ProjectTest):
    """G1, the commit card: a Ctrl-C in a hook is “Commit interrupted” and the index is as it was."""

    def test_g1_ctrl_c_in_a_commit_hook_leaves_head_and_index_alone(self):
        (self.project / "new.txt").write_text("new\n")
        hook = self.project / ".git" / "hooks" / "pre-commit"
        hook.write_text('#!/bin/sh\nkill -INT "$ZP_TEST_PID"\nsleep 5\n')
        hook.chmod(0o755)
        index = self.project / ".git" / "index"
        head, saved = self.git("rev-parse", "HEAD"), index.read_bytes()
        before = signal.signal(signal.SIGINT, signal.default_int_handler)
        self.addCleanup(signal.signal, signal.SIGINT, before)
        with patch.dict(os.environ, {"ZP_TEST_PID": str(os.getpid())}), self.assertRaises(Blocked) as raised:
            user_commit.commit(self.project, ["new.txt"], "add new", terminal=True)
        self.assertIn("Commit interrupted", str(raised.exception))
        self.assertEqual(raised.exception.family, "commit.failed")
        self.assertEqual((self.git("rev-parse", "HEAD"), index.read_bytes()), (head, saved))
        self.assertEqual(self.git("status", "--porcelain").decode().strip(), "?? new.txt")

    @unittest.skipUnless(HAVE_TEXTUAL, "Textual (or ZPLAN_TEST_WHEELHOUSE) is required")
    def test_g1_the_card_closes_as_a_receipt_when_the_interrupt_arrives_outside_the_commit(self):
        closed = []

        def interrupted(proposal_id):
            raise KeyboardInterrupt

        app = SimpleNamespace(suspend=contextlib.nullcontext, controller=SimpleNamespace(commit_files=interrupted),
                              request_refresh=lambda: None, changed=lambda: None)
        host = SimpleNamespace(app=app, close_card=lambda key, text: closed.append((key, text)))
        card_host.CardHost.confirm_commit(host, "commit:abc")
        self.assertEqual(len(closed), 1)
        self.assertIn("Commit interrupted.", closed[0][1])


class ProfileTextTests(ProjectTest):
    """G3 and G4 over a real repository in production mode (the file is written and committed)."""

    def setUp(self):
        super().setUp()
        environment = patch.dict(os.environ, {"XDG_DATA_HOME": str(self.root / "data"),
                                              "XDG_CONFIG_HOME": str(self.root / "config")})
        environment.start()
        self.addCleanup(environment.stop)

    def main(self, *argv):
        out = io.StringIO()
        with patch.object(cli, "Terminal", lambda: Terminal(io.StringIO(), out)):
            code = cli.main([*argv, "--project", str(self.project)])
        return code, out.getvalue()

    def test_g3_the_card_and_the_profile_show_the_level_and_max_runs_as_they_are(self):
        status = process.Profile.peek(self.project, root=self.state, fixture_id="t").status()
        autonomy = status.resolved.config["autonomy"]
        self.assertEqual((autonomy["level"], autonomy["max_runs"]), ("auto", 3))
        card = [line for line in process.bootstrap_lines(status) if "Autonomy" in line]
        self.assertEqual(len(card), 1)
        self.assertIn("auto", card[0])
        self.assertIn("3", card[0])
        line = next(line for line in process.describe(status) if line.startswith("  autonomy: "))
        self.assertIn("auto", line)
        self.assertNotIn("for later stages", line)

    def test_g4_profile_init_says_it_committed_and_never_asks_for_a_commit(self):
        code, shown = self.main("profile", "init")
        self.assertEqual(code, 0, shown)
        self.assertIn("committed: zplan profile", shown)
        for absent in ("git commit", "Commit ", "not committed"):
            self.assertNotIn(absent, shown)
        self.assertEqual(self.git("log", "-1", "--format=%s").decode().strip(), "zplan profile")

    def test_g4_a_refused_commit_is_not_called_committed(self):
        hook = self.project / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        code, shown = self.main("profile", "init")
        self.assertEqual(code, 0, shown)
        self.assertNotIn("committed: zplan profile", shown)
        self.assertIn("but not committed", shown)  # the notice names the command to run by hand


class StatusBesideTheShellTests(ProjectTest):
    """G5: `zplan status` answers while another session holds the project."""

    def setUp(self):
        super().setUp()
        environment = patch.dict(os.environ, {"XDG_DATA_HOME": str(self.root / "data"),
                                              "XDG_CONFIG_HOME": str(self.root / "config")})
        environment.start()
        self.addCleanup(environment.stop)

    def status(self, *extra):
        out = io.StringIO()
        with patch.object(cli, "Terminal", lambda: Terminal(io.StringIO(), out)):
            code = cli.main(["status", "--project", str(self.project), *extra])
        return code, out.getvalue()

    def test_g5_status_works_while_the_shell_holds_the_lock_and_changes_nothing(self):
        with Authority(None, self.project):
            with self.assertRaises(Blocked) as raised:  # the shell really holds it: a second session is refused
                with Authority(None, self.project):
                    pass
            self.assertEqual(raised.exception.family, "store.locked")
            code, shown = self.status()
        self.assertEqual(code, 0, shown)
        self.assertIn(self.project.name, shown)

    def test_g5_status_is_read_only(self):
        with Authority(None, self.project) as shell:
            project_id = shell.project_id
        store = production_root() / project_id
        before = sorted(str(p) for p in production_root().parent.rglob("*"))
        code, _ = self.status()
        self.assertEqual(code, 0)
        self.assertEqual(sorted(str(p) for p in production_root().parent.rglob("*")), before)
        self.assertFalse((store / "planning.json").exists())


class StatusAfterAManualMergeTests(RunsTest):
    """G5 with an approved plan: a run merged by hand since the last save makes the overview re-check integration,
    which used to save into the store and so needs the lock `status` does not take."""

    def test_g5_status_shows_a_hand_merged_run_without_writing_the_store(self):
        self.approve_fixture()
        with self.fixture_authority() as a:
            controller, r = self.done_run(a)
            controller.finish(r)
            sha = r["result"]["commit"]
            path = a.path
        self.git("merge", "--no-ff", "-q", "-m", "owner merge", sha)
        saved = path.read_bytes()
        out = io.StringIO()
        with self.fixture_authority():  # the shell holds the project
            cli.status(Terminal(io.StringIO(), out), self.project, self.state, fixture_id="test", worktrees=self.worktrees)
        self.assertIn("1/2 stages merged", out.getvalue())
        self.assertEqual(path.read_bytes(), saved)

    def done_run(self, a):
        controller = self.fixture_runs(a)
        return controller, controller.observe(controller.start("M1", 1, ROLES))


@unittest.skipUnless(HAVE_TEXTUAL, "Textual (or ZPLAN_TEST_WHEELHOUSE) is required for Pilot tests")
class ProfileEditorTests(unittest.IsolatedAsyncioTestCase):
    """G2 in a bare host app (no engine, no store)."""

    ROLES = tuple((name, "model-" + name, "high") for name in process.ROLES)

    def editor(self):
        sent = []
        form = process.Form("auto", 1, "off", False, self.ROLES)

        class Host(App):
            def changed(self):
                pass

            def deliver(self, handler):
                return handler

            def on_mount(self):
                self.push_screen(ProfileScreen(form, lambda changes, done: sent.append(changes)))
        return Host(), sent

    async def test_g2_the_picked_button_is_marked_apart_from_focus_and_the_keys_are_one_line(self):
        host, sent = self.editor()
        async with host.run_test(size=(100, 60)) as pilot:
            await pilot.pause(0.1)
            screen = host.screen
            label = lambda ident: screen.query_one("#" + ident, Button).label.plain
            self.assertEqual((label("profile-max_runs-1"), label("profile-max_runs-2")), ("● 1", "2"))
            screen.query_one("#profile-max_runs-2", Button).focus()  # focus on «2» while «1» is picked
            await pilot.pause(0.1)
            self.assertEqual((label("profile-max_runs-1"), label("profile-max_runs-2")), ("● 1", "2"))
            await pilot.press("enter")  # pick the focused one: the mark moves, the other group is untouched
            await pilot.pause(0.1)
            self.assertEqual((label("profile-max_runs-1"), label("profile-max_runs-2")), ("1", "● 2"))
            screen.query_one("#profile-max_runs-3", Button).focus()
            await pilot.press("space")  # Space picks as Enter does, and types a space in the model field
            await pilot.pause(0.1)
            self.assertEqual((label("profile-max_runs-2"), label("profile-max_runs-3")), ("2", "● 3"))
            field = screen.query_one("#profile-model-planner", Input)
            field.focus()
            field.value = ""
            await pilot.press("a", "space", "b")
            await pilot.pause(0.1)
            self.assertEqual(field.value, "a b")
            screen.query_one("#profile-max_runs-2", Button).focus()
            await pilot.press("enter")
            await pilot.pause(0.1)
            self.assertEqual(label("profile-level-auto"), "● auto")
            hint = screen.key_bar(100)
            for key in ("←→/tab", "enter/space", "ctrl+s", "esc"):
                self.assertIn(key, hint)
            self.assertIn("<svg", host.export_screenshot())  # the editor's look
            await pilot.press("ctrl+s")
            await pilot.pause(0.1)
            self.assertEqual(sent, [{"max_runs": 2, "roles": {"planner": {"model": "a b", "effort": "high"}}}])
