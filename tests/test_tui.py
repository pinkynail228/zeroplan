"""Full-screen shell: plain fallback, layout and resize, plan panel, Settings, serialized controller worker, keys and
a real PTY smoke. Textual Pilot with real temporary Git repositories and the fixture store; no provider, no network.

Pilot tests need Textual (the interpreter's own, or the wheels of ZPLAN_TEST_WHEELHOUSE) and skip without it."""

import contextlib
import fcntl
import io
import os
from pathlib import Path
import pty
import select
import struct
import subprocess
import sys
import termios
import threading
import time
import types
import unittest
from unittest.mock import patch

from terminal_planner import catalog, cli
from terminal_planner.cli import Terminal
from terminal_planner.runs import FixtureDriver, MilestoneRuns
import test_terminal_planner as tp
from test_terminal_planner import ProjectTest, ROLES
from tui_support import HAVE_TEXTUAL, screen_lines, screen_text

ROOT = Path(__file__).resolve().parents[1]
ESC = b"\x1b"
CTRL_Q = b"\x11"


def check(name, ok=True, line="", detail="", key=None, doctor=None):
    return {"id": name, "ok": ok, "doctor": doctor or ("%s ok" % name), "line": line or name, "detail": detail, "key": key}


class Readiness:
    """setup.readiness() stand-in: a mutable list of items and a call counter."""

    def __init__(self, *items):
        self.items, self.calls = list(items), 0

    def __call__(self):
        self.calls += 1
        return [dict(i) for i in self.items]

    def fix(self, name):
        self.items = [dict(i, ok=True) if i["id"] == name else i for i in self.items]


def plain_env(**extra):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ["HOME"], "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHONUTF8": "1", "LANG": "C.UTF-8", "TERM": "xterm-256color", "PYTHONPATH": ROOT_PATH()}
    env.update(extra)
    return env


def ROOT_PATH():
    """The checkout plus, when Textual came from extracted wheels, the directory it lives in."""
    paths = [str(ROOT)]
    if HAVE_TEXTUAL:
        import textual
        site = str(Path(textual.__file__).resolve().parents[1])
        if site not in sys.path[:1] + [p for p in sys.path if p.endswith("site-packages")]:
            paths.append(site)
        else:
            paths.append(site)
    return os.pathsep.join(dict.fromkeys(paths))


class PtyTest(ProjectTest):
    """Runs the real entry point under a pseudo-terminal."""

    def pty(self, argv, steps=(), rows=24, cols=80, timeout=30, cwd=None, **env):
        """Returns (output bytes, wait status). `steps` is a list of (bytes to wait for, bytes to type); the child
        starts in `cwd` (default: the project)."""
        # i6: the full-screen shell's own texts now follow the stored UI language, which lives at
        # `$XDG_CONFIG_HOME/planning-kit/ui.json`. The in-process pin `tests/tui_support.py` sets cannot reach a
        # child process, so store `ru` here: these tests assert the Russian shell (and a stored language keeps the
        # first-run chooser from covering it). The plain fallback ignores the file.
        ui = self.root / "config" / "planning-kit" / "ui.json"
        ui.parent.mkdir(parents=True, exist_ok=True)
        ui.write_text('{"language": "ru"}\n', encoding="utf-8")
        environment = plain_env(XDG_DATA_HOME=str(self.root / "data"), XDG_CONFIG_HOME=str(self.root / "config"), **env)
        pid, fd = pty.fork()
        if pid == 0:
            try:
                fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
                os.chdir(cwd or self.project)
                os.execvpe(argv[0], argv, environment)
            finally:
                os._exit(127)
        output, pending, deadline = b"", list(steps), time.monotonic() + timeout
        try:
            while time.monotonic() < deadline:
                ready, _, _ = select.select([fd], [], [], 0.1)
                if ready:
                    try:
                        chunk = os.read(fd, 65536)
                    except OSError:
                        break
                    if not chunk:
                        break
                    output += chunk
                if pending and pending[0][0] in output:
                    os.write(fd, pending.pop(0)[1])
            else:
                os.kill(pid, 9)
                self.fail("PTY: no exit within %s s; output:\n%s" % (timeout, output[-2000:].decode(errors="replace")))
        finally:
            _, status = os.waitpid(pid, 0)
            os.close(fd)
        self.assertEqual(pending, [], "PTY: did not wait for %r; output:\n%s" % (pending[:1], output[-2000:].decode(errors="replace")))
        return output, status

    def cli(self, *args):
        return [sys.executable, "-m", "terminal_planner.cli", "--project", str(self.project), "--state-dir",
                str(self.state), "--fixture", "pty", *args]


class PlainFallbackTests(PtyTest):
    """A1: no escape bytes unless the full-screen UI is both wanted and possible."""

    def test_piped_stdin_stays_plain(self):
        result = subprocess.run(self.cli(), input=b"q\n", capture_output=True, env=plain_env(), cwd=self.project, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(ESC, result.stdout)
        self.assertIn("zplan · project with spaces".encode(), result.stdout)

    def test_plain_flag_on_a_terminal_stays_plain(self):
        output, status = self.pty(self.cli("--plain"), [(b"[l] ", b"l\n"), (b"[p] ", b"q\n")])
        self.assertEqual(os.waitstatus_to_exitcode(status), 0)
        self.assertNotIn(ESC, output)
        self.assertIn("zplan · project with spaces".encode(), output)

    def test_plain_session_says_the_chat_is_tui_only(self):
        """The line UI of the installed zplan does not offer the architect chat: its home line says where it is."""
        result = subprocess.run(self.cli(), input=b"q\n", capture_output=True, env=plain_env(), cwd=self.project, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(cli.PLAIN_CHAT, result.stdout.decode())

    def test_term_dumb_on_a_terminal_stays_plain(self):
        output, status = self.pty(self.cli(), [(b"[l] ", b"l\n"), (b"[p] ", b"q\n")], TERM="dumb")
        self.assertEqual(os.waitstatus_to_exitcode(status), 0)
        self.assertNotIn(ESC, output)

    def test_status_and_doctor_on_a_terminal_have_no_escape_codes(self):
        output, status = self.pty(self.cli("status"))
        self.assertEqual(os.waitstatus_to_exitcode(status), 0)
        self.assertNotIn(ESC, output)
        self.assertIn("No plan.".encode(), output)
        output, _ = self.pty([sys.executable, "-m", "terminal_planner.cli", "doctor", "--project", str(self.project)])
        self.assertNotIn(ESC, output)
        self.assertIn(b"Planning Kit", output)

    def test_missing_textual_falls_back_to_the_plain_flow(self):
        class Tty(io.StringIO):
            def isatty(self):
                return True
        out, stdin = Tty(), Tty("q\n")
        with patch.dict(sys.modules, {"terminal_planner.tui.app": None}), patch.object(sys, "stdin", stdin), \
                patch.object(sys, "stdout", out), patch.object(cli, "Terminal", lambda: Terminal(stdin, out)), \
                patch.dict(os.environ, {"TERM": "xterm"}):
            code = cli.main(["--project", str(self.project), "--state-dir", str(self.state), "--fixture", "pty"])
        self.assertEqual(code, 0)
        self.assertIn("zplan --plain", out.getvalue())
        self.assertNotIn("\x1b", out.getvalue())

    def test_tui_wanted_needs_a_terminal_on_both_ends_and_no_override(self):
        class Stream:
            def __init__(self, tty):
                self.tty = tty

            def isatty(self):
                return self.tty

        def args(**kw):
            return type("Args", (), dict({"plain": False, "command": None}, **kw))

        term = {"TERM": "xterm-256color"}
        yes = Stream(True)
        self.assertTrue(cli.tui_wanted(args(), term, yes, yes))
        self.assertFalse(cli.tui_wanted(args(plain=True), term, yes, yes))
        self.assertFalse(cli.tui_wanted(args(command="status"), term, yes, yes))
        self.assertFalse(cli.tui_wanted(args(), {"TERM": "dumb"}, yes, yes))
        self.assertFalse(cli.tui_wanted(args(), {}, yes, yes))
        self.assertFalse(cli.tui_wanted(args(), term, Stream(False), yes))
        self.assertFalse(cli.tui_wanted(args(), term, yes, Stream(False)))


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is unavailable: ZPLAN_TEST_WHEELHOUSE with textual 8.2.8 wheels is needed")
class PtySmokeTests(PtyTest):
    """A7: the real process on a real terminal."""

    OPEN_THIS = ("Open this project".encode(), b"\r")  # the start screen, answered first: Enter on the highlighted row

    PROBE = ("import termios;f=termios.tcgetattr(0)[3];"
             "print('LFLAG', bool(f & termios.ICANON), bool(f & termios.ECHO))")

    def wrapped(self, *args):
        """Entry point, then the exit status and the terminal's line discipline, all on the same terminal."""
        script = '"$0" "$@"; echo "EXIT=$?"; "$0" -c "%s"' % self.PROBE
        return ["/bin/sh", "-c", script, sys.executable, "-m", "terminal_planner.cli", "--project", str(self.project),
                "--state-dir", str(self.state), "--fixture", "pty", *args]

    def assertRestored(self, output, code="EXIT=0"):
        text = output.decode(errors="replace")
        self.assertIn(code, text)
        self.assertIn("LFLAG True True", text)  # cooked mode with echo again
        opened, closed = output.rfind(b"\x1b[?1049h"), output.rfind(b"\x1b[?1049l")
        self.assertGreaterEqual(opened, 0)
        self.assertGreater(closed, opened)  # the alternate screen was closed after it was opened
        self.assertLess(closed, output.find(code.encode()))

    def test_screen_shows_the_panes_and_ctrl_q_exits_cleanly(self):
        """i9: the full-screen shell shows the approved lab look — row 0 is the panes' top border and the chat pane
        reads «Conversation with the architect», no logo (`███████╗`) above it — and ctrl+q restores the terminal."""
        output, status = self.pty(self.wrapped(), [self.OPEN_THIS, ("Conversation with the architect".encode(), CTRL_Q)], rows=40, cols=120)
        self.assertEqual(os.waitstatus_to_exitcode(status), 0)
        text = output.decode(errors="replace")
        self.assertNotIn("███████╗██████╗", text)
        self.assertIn("project with spaces", text)
        self.assertIn("Conversation with the architect", text)
        self.assertRestored(output)

    def test_an_exception_still_restores_the_terminal(self):
        script = ('import sys; sys.argv=["zplan"]; import terminal_planner.cli as c; '
                  'from terminal_planner.tui import app; '
                  'app.MainScreen.render_state = lambda self: (_ for _ in ()).throw(RuntimeError("boom")); '
                  'raise SystemExit(c.main(sys.argv[1:] + %r))' % (["--project", str(self.project), "--state-dir",
                                                                     str(self.state), "--fixture", "pty"],))
        argv = ["/bin/sh", "-c", '"$0" -c "$1"; echo "EXIT=$?"; "$0" -c "%s"' % self.PROBE, sys.executable, script]
        output, _ = self.pty(argv, [self.OPEN_THIS])
        self.assertIn(b"boom", output)
        self.assertRestored(output, "EXIT=1")

    def test_an_empty_folder_stops_at_the_start_screen_and_esc_leaves_it_untouched(self):
        """O2a-mini: a folder without Git is offered on the start screen; Esc leaves with 0 and writes nothing."""
        empty = self.root / "empty folder"
        empty.mkdir()
        argv = [sys.executable, "-m", "terminal_planner.cli", "--state-dir", str(self.state), "--fixture", "pty"]
        output, status = self.pty(argv, [("There is no Git project here".encode(), ESC)], rows=40, cols=120, cwd=empty)
        self.assertEqual(os.waitstatus_to_exitcode(status), 0)
        self.assertFalse((empty / ".git").exists())


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is unavailable: ZPLAN_TEST_WHEELHOUSE with textual 8.2.8 wheels is needed")
class ShellTest(ProjectTest, unittest.IsolatedAsyncioTestCase):
    def controller(self, readiness=None, **kw):
        from terminal_planner.tui.controller import Controller
        kw.setdefault("driver_factory", lambda _: FixtureDriver(self.root / "fixture-runs"))
        controller = Controller.for_project(self.project, self.state, fixture_id="test",
                                            readiness=readiness if readiness is not None else Readiness(check("git")), **kw)
        self.addCleanup(controller.stop)
        return controller

    def approve(self, running=True):
        """An approved fixture plan (M1, M2 after M1); M1 submitted and running when asked."""
        with tp.Authority(self.state, self.project) as a:
            self.begin(a)
            self.propose(a)
            a.approve(1)
            if running:
                MilestoneRuns(a, FixtureDriver(self.root / "fixture-runs"), worktrees=a.directory / "worktrees") \
                    .start("M1", 1, ROLES)

    def plain_body(self):
        """The plain `status` screen of the same store, as the line UI prints it."""
        out = io.StringIO()
        cli.status(Terminal(io.StringIO(), out), self.project, self.state, "test",
                   lambda a: FixtureDriver(self.root / "fixture-runs"))
        return out.getvalue().splitlines()

    def shell(self, controller=None, size=(120, 40), follow=False, chat_prepare=None, chat_binding=None):
        """`follow` is off unless asked: a running attempt is then observed only by an explicit [o], so tests of
        what the screens show do not move the fixture run underneath them. `chat_prepare(project)` builds the
        ready architect; the default is production (an uninstalled toolchain: the chat shows its refusal).
        `chat_binding(project)` is the role the chat re-reads before every turn; also production by default."""
        from terminal_planner.tui.app import ZplanApp
        self.app = ZplanApp(controller or self.controller(), follow=follow, chat_prepare=chat_prepare,
                            chat_binding=chat_binding)
        return self.app.run_test(size=size)

    async def chat_ready(self, pilot, timeout=20.0):
        """Wait until the chat left "preparing the chat…" (its preparation runs off the event loop). K1d: 20 s, not 5 — a
        load flake (3 on 2026-10-25) waited 5 s beside a run; a passing test is not slower."""
        await self.until(pilot, lambda: self.app.chat is not None and self.app.chat.state.phase != "preparing",
                         timeout)

    async def until(self, pilot, condition, timeout=20.0):
        end = time.monotonic() + timeout
        while not condition():
            self.assertLess(time.monotonic(), end, "did not reach the state:\n" + screen_text(self.app))
            await pilot.pause(0.05)

    async def run_button(self, pilot, name):
        """K1c3: wait for the run end screen to show the button `name` (the row is built after the first paint)."""
        await self.until(pilot, lambda: type(self.app.screen).__name__ == "RunScreen"
                         and self.app.screen.query("#run-buttons-%s" % name))

    async def press_button(self, pilot, name):
        """K1c1/K1c2/K1c3: a modal, the plan screen, Settings and the run end screen answer with buttons, not letters — put the focus on the
        button (`yes`, `no`, `accept`, `later`, `send`; on the plan screen and Settings the action name: `approve`,
        `recheck`; on the run end screen the action name too: `merge`, `diff`, `tail`, `details`; what Tab and the
        arrows do) and press Enter, the way the owner answers."""
        modal = self.app.screen
        prefix = {"ConfirmScreen": "confirm", "EnterConfirmScreen": "confirm", "BootstrapScreen": "bootstrap",
                  "NoteScreen": "note", "QuestionNoteScreen": "note", "PlanScreen": "plan-buttons",
                  "SettingsScreen": "settings-buttons", "RunScreen": "run-buttons"}[type(modal).__name__]
        await self.until(pilot, lambda: modal.query("#%s-%s" % (prefix, name)))  # K1c2: the row is rebuilt after a repaint
        button = modal.query_one("#%s-%s" % (prefix, name))
        await self.until(pilot, lambda: not button.has_class("-active"))  # a press within 0.2 s of the last is dropped
        button.focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

    async def loaded(self, pilot):
        await self.until(pilot, lambda: self.app.snapshot is not None and self.app.checks is not None)
        await pilot.pause()

    async def command(self, pilot, line):
        """K1a: the main screen has no letter keys — an action is a `/` command typed in the chat input. Types `line`
        and presses Enter the way the owner does; a plan pane that had the focus gets it back, so a test goes on
        with the pane's arrows."""
        on_pane = getattr(self.app.focused, "id", None) == "plan-pane"
        if on_pane:
            await pilot.press("tab")
            await self.until(pilot, lambda: getattr(self.app.focused, "id", None) == "input")
        field = self.app.screen.query_one("#input")
        field.value = line
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        if on_pane and type(self.app.screen).__name__ == "MainScreen":
            await pilot.press("tab")
            await self.until(pilot, lambda: getattr(self.app.focused, "id", None) == "plan-pane")

    async def panel(self, pilot):
        """D4: the main screen starts with the chat input focused, so a test that wants a plan-pane key asks for
        the pane here — one Tab when the pane does not have the focus yet (the pane's keys then work at once)."""
        if getattr(self.app.focused, "id", None) != "plan-pane":
            await pilot.press("tab")
        await self.until(pilot, lambda: getattr(self.app.focused, "id", None) == "plan-pane")


class LayoutTests(ShellTest):
    async def test_a2_layout_at_80x24_and_120x40_and_resize(self):
        """i9/A1/A2/A4 through the real shell: at 80x24 the screen is narrow — the chat alone, full width, row 0 its
        own top border (`Conversation · ←→ tabs`) and the bottom `Bar` carrying the project; the arrows reach the
        canvas. At 120x40 both panes show, row 0 is their top borders (no logo, no header), the chat pane reads
        «Conversation with the architect», the canvas tabs «Scheme  Plan», and the input lives inside the chat pane at its
        bottom. The `Bar` is kept across every resize.

        (The old header row this test also read — `project with spaces · main · ✓ ready` at lines[1]/lines[6] — is
        gone with the header itself; i9 keeps the project, branch and job state only in the `Bar`.)"""
        self.approve()
        async with self.shell(size=(80, 24)) as pilot:
            await self.loaded(pilot)
            lines = screen_lines(self.app)
            self.assertEqual(len(lines), 24)
            self.assertNotIn("ZPLAN", "\n".join(lines))  # no logo, block or compact
            # I7: below 100 columns the screen is narrow — the chat alone, full width, the canvas hidden.
            self.assertTrue(self.app.screen.narrow)
            self.assertTrue(self.app.query_one("#chat-pane").display)
            self.assertFalse(self.app.query_one("#right-column").display)
            self.assertIn("Conversation", lines[0])  # row 0 is the chat pane's own top border
            self.assertNotIn("Plan r1", "\n".join(lines))  # the canvas is not shown
            await self.chat_ready(pilot)
            self.assertIn("zplan setup", "\n".join(screen_lines(self.app)))  # no install: the catalog refusal
            self.assertIn("project with spaces", lines[-1])  # i2: the bottom row is the Bar
            # I7/A1: the arrows reach the canvas; C0c2 opens it on «Scheme» (a running attempt), so one [→] shows
            # the scheme and a second shows the «Plan» tab, each full width.
            await pilot.press("right", "right")
            await pilot.pause()
            self.assertFalse(self.app.query_one("#chat-pane").display)
            self.assertTrue(self.app.query_one("#right-column").display)
            self.assertIn("Plan r1", "\n".join(screen_lines(self.app)))
            await pilot.resize_terminal(120, 40)
            await pilot.pause(0.2)
            lines = screen_lines(self.app)
            self.assertEqual(len(lines), 40)
            self.assertNotIn("██████", "\n".join(lines))  # no logo
            self.assertIn("Conversation with the architect", lines[0])  # row 0 is the panes' top borders
            self.assertIn("running", lines[0])  # the canvas frame's own state title rides that border (M1 running)
            self.assertIn("Scheme", lines[1])  # the tabs ride inside the canvas frame, on its first content row
            self.assertIn("Plan", lines[1])
            self.assertIn("ctrl+q", lines[-1])  # the Bar names the exit key at the wider size
            # I7: wide again — both panes show, the chat keeps its place next to the plan.
            self.assertFalse(self.app.screen.narrow)
            self.assertTrue(self.app.query_one("#chat-pane").display)
            self.assertTrue(self.app.query_one("#right-column").display)
            # A2: the input lives inside the chat pane, at its bottom.
            pane = self.app.query_one("#chat-pane")
            field = self.app.query_one("#input")
            self.assertIn(pane, field.ancestors)
            self.assertLessEqual(field.region.bottom, pane.region.bottom)
            self.assertIn("Plan r1", "\n".join(lines))
            await pilot.resize_terminal(80, 24)  # resize re-flows: narrow again, key bar kept
            await pilot.pause(0.2)
            lines = screen_lines(self.app)
            self.assertEqual(len(lines), 24)
            self.assertNotIn("ZPLAN", "\n".join(lines))
            self.assertIn("project with spaces", lines[-1])  # the Bar is kept across the resize

    async def test_header_shortens_the_project_name_not_the_readiness(self):
        from terminal_planner.tui.app import header_text
        line = header_text("a-very-long-project-name-that-will-not-fit", "main", (), 40)
        self.assertLessEqual(len(line), 38)
        self.assertTrue(line.endswith(" · main · ✓ ready"), line)
        self.assertIn("…", line)

    async def test_input_focus_and_tab_toggle(self):
        """D4: the main screen starts with the chat input focused and Tab toggles the focus to the plan pane and
        back. (i2 moved the bottom row to the shared `Bar`, so the old main-bar text this test also pinned — the
        panel's `[s] settings` — is gone; the focus behaviour alone is what is left to check here.)"""
        async with self.shell() as pilot:
            await self.loaded(pilot)
            self.assertEqual(self.app.focused.id, "input")  # D4: the chat input is where the main screen starts
            await pilot.press("tab")
            self.assertEqual(self.app.focused.id, "plan-pane")
            await pilot.press("tab")
            self.assertEqual(self.app.focused.id, "input")

    async def test_a1_start_focus_is_the_chat_input_and_typed_keys_are_text(self):
        """A1/D4: the main screen starts with `#input` focused, so the first keystroke is the owner's text: a
        letter, `?` (which the panel would turn into help) and each of the panel keys land in the input unchanged
        and start no action.

        Interpretations this change had to make (the worker's summary never reaches the reviewers, so they are
        recorded here):

        - `docs/USER_FLOW.md` had no sentence that said where the focus starts (its `main | Tab` row documented
          the toggle alone), so the write-set's doc change — allowed only for such a sentence — is not made:
          the doc is left as it was. A test that wants a pane key reaches the pane first through the shared
          `ShellTest.panel` helper, which encodes exactly the Tab that row already documents.
        - The start key bar becomes the input bar with the input focus. At 80x24 that bar is wider than the panel
          bar, so `[ctrl+q]` is shown unlabelled there (`[ctrl+q] quit` at 120x40): forced by the focus change,
          and allowed by the catalog's bar contract, whose `reserve`/exit-hint rule belongs to the panel bar (the
          input bar keeps its primary actions labelled only while it can afford them)."""
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            self.assertEqual(self.app.focused.id, "input")
            await pilot.press("question_mark", *"pnctgxoiwe")
            self.assertEqual(self.app.query_one("#input").value, "?pnctgxoiwe")
            self.assertEqual(self.app.screen.__class__.__name__, "MainScreen")  # no panel action fired

    async def test_a2_tab_reaches_the_plan_pane_and_no_letter_acts_there(self):
        """A2 + K1a: Tab still cycles input -> plan pane -> input; in the pane no letter, `?`, F1, Ctrl+S or
        Ctrl+R does anything (the actions are `/` commands), so the main screen stays as it was."""
        self.approve(running=False)
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            self.assertEqual(self.app.focused.id, "input")
            await pilot.press("tab")
            self.assertEqual(self.app.focused.id, "plan-pane")
            await pilot.press(*"pgxoiwets", "question_mark", "f1", "ctrl+s", "ctrl+r")
            await pilot.pause(0.3)
            self.assertEqual(self.app.screen.__class__.__name__, "MainScreen")
            self.assertEqual(self.app.focused.id, "plan-pane")
            self.assertIsNone(self.app.pending)  # `g` started nothing
            await pilot.press("tab")
            self.assertEqual(self.app.focused.id, "input")

    async def test_help_command_lists_keys_and_escape_closes(self):
        async with self.shell() as pilot:
            await self.loaded(pilot)
            await self.command(pilot, "/help")
            self.assertIn("Keys", screen_text(self.app))
            self.assertIn("ctrl+q", screen_text(self.app))
            await pilot.press("escape")
            self.assertEqual(self.app.screen.__class__.__name__, "MainScreen")
            await pilot.press("?")  # in the input line it is text
            self.assertEqual(self.app.query_one("#input").value, "?")
            await pilot.press("f1")  # K1a: the main screen binds no F1
            self.assertEqual(self.app.screen.__class__.__name__, "MainScreen")


class PanelTests(ShellTest):
    async def test_a3_panel_matches_the_plain_overview_of_the_same_store(self):
        self.approve()
        expected = [l for l in self.plain_body()[2:] if l.strip() and not l.startswith("Next:")]
        self.assertTrue(any("task 1/1" in l for l in expected), expected)
        self.assertEqual(sum(l.startswith("  ") for l in expected), 2)  # M1 running, M2 waiting
        async with self.shell(size=(200, 45)) as pilot:  # V6: the plan column is 40% wide; 200 keeps its rows whole
            await self.loaded(pilot)
            await pilot.press("right")  # C0c2: a running attempt opens the pane on «Now»; [→] shows «Plan»
            await pilot.pause()
            shown = [l for l in self.app.screen.plan_lines]
            self.assertEqual(shown[:len(expected)], expected)
            self.assertEqual(self.app.snapshot.version, 1)
            self.assertEqual(self.app.snapshot.status, "approved")
            text = screen_text(self.app)
            self.assertIn("Plan r1 · approved · 0/2 stages merged", text)
            self.assertIn("task 1/1 (T1)", text)
            self.assertIn("M2 Independent verification", text)

    async def test_a1_the_chat_pane_is_the_wide_column_and_the_canvas_takes_40_percent(self):
        """V6/C1: the chat pane is `1fr` and the canvas column `40%`, so at 160x45, 120x40 and 100x30 the chat's
        region is the rest after the column's 40% (each +-1) — read from the regions the app reports, not from a
        constant. Before V6 the chat was 38% and the right column the rest."""
        for size in ((160, 45), (120, 40), (100, 30)):
            async with self.shell(size=size) as pilot:
                await self.loaded(pilot)
                screen = self.app.size.width
                chat = self.app.query_one("#chat-pane").region.width
                right = self.app.query_one("#right-column").region.width
                self.assertAlmostEqual(right, 0.40 * screen, delta=1, msg=(size, right, screen))
                self.assertAlmostEqual(chat, screen - 0.40 * screen, delta=1, msg=(size, chat, screen))
                self.assertEqual(chat + right, screen, (size, chat, right))

    async def test_no_plan_shows_the_plain_empty_state(self):
        async with self.shell() as pilot:
            await self.loaded(pilot)
            self.assertIn("No plan.", self.app.screen.plan_lines)
            self.assertIn("Next: write the goal to the architect in the chat", self.app.screen.plan_lines)  # i10/P3: the command, not the key

    async def test_markup_and_control_bytes_in_titles_are_shown_literally(self):
        from terminal_planner import engine

        original = engine.fixture_proposal

        def hostile():
            proposal = original()
            proposal["milestones"][0]["title"] = "[bold red]Hack[/] \x1b[31mred"
            return proposal
        with patch.object(engine, "fixture_proposal", hostile), tp.Authority(self.state, self.project) as a:
            self.begin(a)
            self.propose(a)
            a.approve(1)
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            text = "\n".join(self.app.screen.plan_lines)
            self.assertIn("[bold red]Hack[/]", text)
            self.assertNotIn("\x1b", text)

    async def test_a_blocked_chat_refuses_the_message_and_keeps_the_text(self):
        """Without an install under the temporary HOME the chat shows its catalog refusal; the text is not lost."""
        async with self.shell() as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            await pilot.press(*"hello", "enter")  # the input has the start focus (D4): no Tab needed
            self.assertIn("zplan setup", screen_text(self.app))
            self.assertIn("setup.tools_invalid", screen_text(self.app))  # the narrow pane wraps the line
            self.assertEqual(self.app.query_one("#input").value, "hello")  # text kept, nothing lost


class ResponsivenessTests(ShellTest):
    async def test_a4_a_slow_readiness_check_never_blocks_the_keys(self):
        release = threading.Event()
        self.addCleanup(release.set)

        def slow():
            release.wait(3)
            return [check("git")]
        async with self.shell(self.controller(slow), size=(80, 24)) as pilot:
            await pilot.pause(0.2)  # the worker is inside the 3 s check
            self.assertEqual(self.app.controller.running, "check")
            started = time.monotonic()
            self.assertEqual(self.app.focused.id, "input")
            await self.command(pilot, "/setup")  # `/setup` still opens Settings during the slow check
            self.assertEqual(self.app.screen.__class__.__name__, "SettingsScreen")
            await pilot.press("escape")
            # The bound only has to catch the UI blocking on the setup's 3 s `release.wait(3)`; two pilot presses
            # take 0.2-0.7 s on a loaded full-suite run.
            self.assertLess(time.monotonic() - started, 2.0)
            self.assertEqual(self.app.screen.__class__.__name__, "MainScreen")
            # i9: the header that used to say «checking…» is gone; the main screen is painted while the slow check
            # runs — narrow at 80x24 with the canvas revealed (the [tab] above), so the frame carries its state
            # title on row 0 and the strip inside it names «Conversation» among its labels.
            self.assertIn("Conversation", screen_text(self.app))

    async def test_a4_a_slow_setup_keeps_settings_responsive(self):
        release = threading.Event()
        self.addCleanup(release.set)

        def install(show):
            show("step 1")
            release.wait(3)
            show("step 2")
        async with self.shell(self.controller(install=install)) as pilot:
            await self.loaded(pilot)
            await self.command(pilot, "/setup")
            await self.press_button(pilot, "setup")
            await self.until(pilot, lambda: "step 1" in self.app.log_lines)
            started = time.monotonic()
            await self.press_button(pilot, "roles")  # roles view toggles while the setup sleeps
            self.assertTrue(self.app.screen.query_one("#roles").display)
            await pilot.press("escape")
            # The bound only has to catch the UI blocking on the setup's 3 s `release.wait(3)`; two pilot presses
            # take 0.2-0.7 s on a loaded full-suite run.
            self.assertLess(time.monotonic() - started, 2.0)
            self.assertTrue(self.app.setting_up)
            release.set()
            await self.until(pilot, lambda: not self.app.setting_up)
            self.assertIn("step 2", self.app.log_lines)

    async def test_a4_refresh_never_polls_or_submits(self):
        self.approve()
        calls = []
        driver = FixtureDriver(self.root / "fixture-runs")
        originals = {}
        for owner, names in ((MilestoneRuns, ("poll", "start", "dispatch", "observe", "stop", "resume", "merge", "finish",
                                              "reconcile", "retry", "answer")),
                             (FixtureDriver, ("submit", "begin", "advance", "force_stop", "resume"))):
            for name in names:
                originals[(owner, name)] = getattr(owner, name)

                def spy(*args, _name=name, _owner=owner, **kw):
                    calls.append(_name)
                    return originals[(_owner, _name)](*args, **kw)
                patch.object(owner, name, spy).start()
        self.addCleanup(patch.stopall)
        overviews = []
        real = MilestoneRuns.overview

        def counting(self_):
            overviews.append(1)
            return real(self_)
        patch.object(MilestoneRuns, "overview", counting).start()
        from terminal_planner.tui import app as module
        with patch.object(module, "REFRESH_SECONDS", 0.1):
            async with self.shell(self.controller(driver_factory=lambda _: driver)) as pilot:
                await self.loaded(pilot)
                await self.until(pilot, lambda: len(overviews) >= 4)
                self.app.request_refresh()  # [r] refresh: still only the read-only slices
                self.app.request_check()
                await pilot.pause(0.3)
        self.assertGreaterEqual(len(overviews), 4)
        self.assertEqual(calls, [])

    async def test_worker_runs_actions_one_at_a_time_in_order(self):
        order = []
        gate = threading.Event()
        self.addCleanup(gate.set)
        controller = self.controller()
        controller.start()
        done = threading.Event()
        controller.post("a", lambda app: (order.append("a-start"), gate.wait(2), order.append("a-end")))
        controller.post("b", lambda app: order.append("b"), lambda *_: done.set())
        time.sleep(0.2)
        self.assertEqual(order, ["a-start"])  # b waits behind a
        gate.set()
        self.assertTrue(done.wait(3))
        self.assertEqual(order, ["a-start", "a-end", "b"])
        # a coalesced slice is queued once while one is waiting
        gate.clear()
        controller.post("c", lambda app: gate.wait(2))
        time.sleep(0.1)
        self.assertTrue(controller.post("d", lambda app: None, coalesce=True))
        self.assertFalse(controller.post("d", lambda app: None, coalesce=True))
        gate.set()


class SlowWaitTests(unittest.IsolatedAsyncioTestCase):
    """K1d C5: a wait beside a run on a loaded machine lasts 20 s, not 5 (3 load flakes on 2026-10-25). The clock is
    fake: the condition turns true at 6 fake seconds, so `until` and `chat_ready` must pass there and give up only
    after 20."""

    class Waits:
        """The two waits of `ShellTest` on their own: they read only `assertLess`, `until` and the app's chat."""
        until, chat_ready = ShellTest.until, ShellTest.chat_ready

        def __init__(self, test):
            self.assertLess = test.assertLess
            self.app = types.SimpleNamespace(chat=types.SimpleNamespace(state=types.SimpleNamespace(phase="preparing")))

    async def test_c5_until_and_chat_ready_wait_20_seconds_by_default(self):
        clock = [0.0]

        class Pilot:
            async def pause(self, delay):
                clock[0] += delay

        waits = self.Waits(self)
        with patch.object(sys.modules[__name__], "time", types.SimpleNamespace(monotonic=lambda: clock[0])), \
                patch.object(sys.modules[__name__], "screen_text", lambda app: ""):
            await waits.until(Pilot(), lambda: clock[0] >= 6.0)  # true at 6 s: a 5 s wait would have failed
            clock[0] = 0.0
            with self.assertRaises(AssertionError):
                await waits.chat_ready(Pilot())  # never ready: gives up, but only after 20 s
            self.assertGreaterEqual(clock[0], 20.0)
            clock[0] = 0.0
            waits.app.chat.state.phase = "ready"
            await waits.chat_ready(Pilot())
            self.assertEqual(clock[0], 0.0)  # a passing wait is not slower


class SettingsTests(ShellTest):
    def three_problems(self):
        # The shell runs a fixture session, which needs no tools or login (readiness per action): the ids are
        # items a fixture still checks, the texts are the screen's.
        return Readiness(check("git"),
                         check("identity", False, "The zplan tools are not installed — [i] details", "Install: [u] or zplan setup.", "u"),
                         check("branch", False, "Codex: not logged in at ~/.codex — [l] log in", "[l] starts the Codex login.", "l"),
                         check("repo", False, "There are uncommitted changes — [d] view", "Commit or remove them yourself.", "d"))

    async def test_a5_lists_items_and_g_rechecks_after_a_fix(self):
        readiness = self.three_problems()
        async with self.shell(self.controller(readiness), size=(120, 40)) as pilot:
            await self.loaded(pilot)
            await self.command(pilot, "/setup")
            await pilot.pause(0.2)
            text = screen_text(self.app)
            self.assertIn("✓ git ok", text)
            for line in ("! The zplan tools are not installed", "! Codex: not logged in at ~/.codex — button «%s»" % catalog.label("tui_settings.login"),
                         "! There are uncommitted changes"):
                self.assertIn(line, text)
            self.assertIn("Install: button «%s» or zplan setup." % catalog.label("tui_settings.setup"), text)  # K1d: the detail names the button
            self.assertNotRegex(text, r"\[[a-z]\]")  # K1d: no letter key on Settings
            self.assertIn("Commit or remove them yourself.", text)
            self.assertNotIn("[i] details", text)  # plain-screen keys are not offered here
            self.assertNotIn("[d] view", text)
            readiness.fix("identity")
            readiness.fix("branch")
            readiness.fix("repo")
            before = readiness.calls
            await self.press_button(pilot, "recheck")
            await self.until(pilot, lambda: readiness.calls > before and not self.app.checking)
            await pilot.pause(0.1)
            text = screen_text(self.app)
            self.assertNotIn("!", "\n".join(l for l in text.splitlines() if l.startswith("│ ")))
            self.assertEqual(text.count("✓"), 4)
            await pilot.press("escape")
            self.assertEqual(self.app.screen.__class__.__name__, "MainScreen")
            # i9: the readiness line the old `#header` showed is gone with the header; the Settings pane above is
            # what reports the readiness now.
            self.assertIn("Conversation with the architect", screen_lines(self.app)[0])

    async def test_k1c2_settings_answers_with_buttons_not_letters(self):
        """K1c2 C3/C4: Settings has a button for each action it offers (setup, login, recheck, roles — setup and
        login only when the session has them), labelled by its `tui_settings.*` entry; no letter or `?` does
        anything; Tab / Left / Right move, Enter on «recheck» rechecks, Esc goes back; the key line names Tab,
        Enter and Esc, no letter.

        Interpretation: the checks pane and the log are not focusable (Tab visits the buttons only); Up/Down/
        PgUp/PgDn scroll the checks pane."""
        readiness = self.three_problems()
        async with self.shell(self.controller(readiness, install=lambda show: show("x"), login=lambda: 0),
                              size=(120, 40)) as pilot:
            await self.loaded(pilot)
            await self.command(pilot, "/setup")
            screen = self.app.screen
            names = lambda: [button.name for button in screen.query("#settings-buttons Button")]
            await self.until(pilot, lambda: names() == ["setup", "login", "recheck", "roles"])
            self.assertEqual([button.label.plain for button in screen.query("#settings-buttons Button")],
                             [catalog.label("tui_settings." + name) for name in names()])
            bar = screen_lines(self.app)[-1]
            self.assertTrue(all("[%s]" % key in bar for key in ("tab", "enter", "esc")), bar)
            self.assertNotRegex(bar, r"\[[a-z?]\]")
            await self.until(pilot, lambda: not self.app.checking)
            before = readiness.calls
            await pilot.press(*"ugrlq?", "question_mark")  # no letter and no `?` is an action
            await pilot.pause(0.3)
            self.assertIs(self.app.screen, screen)
            self.assertEqual((readiness.calls, list(self.app.log_lines), screen.query_one("#roles").display),
                             (before, [], False))
            await pilot.press("tab", "tab")
            self.assertEqual(self.app.focused.name, "recheck")
            await pilot.press("right", "left", "left")
            self.assertEqual(self.app.focused.name, "login")
            await pilot.press("right", "enter")
            await self.until(pilot, lambda: readiness.calls > before)
            await pilot.press("escape")
            self.assertEqual(self.app.screen.__class__.__name__, "MainScreen")

    async def test_a5_u_streams_setup_output_into_the_log(self):
        readiness = self.three_problems()
        seen = []

        def install(show):
            seen.append(1)
            show("Downloading Zeroshot 10.11.0")
            show("double\nwrap")
            readiness.fix("identity")
            show("Tools installed")
        async with self.shell(self.controller(readiness, install=install), size=(120, 40)) as pilot:
            await self.loaded(pilot)
            await self.command(pilot, "/setup")
            await self.press_button(pilot, "setup")
            await self.until(pilot, lambda: not self.app.setting_up and seen)
            await pilot.pause(0.1)
            text = screen_text(self.app)
            for line in ("Downloading Zeroshot 10.11.0", "double", "wrap", "Tools installed"):
                self.assertIn(line, text)
            self.assertNotIn("! The zplan tools are not installed", text)  # re-checked after the setup
            await pilot.press("escape")
            await self.command(pilot, "/setup")  # the log survives leaving Settings
            await pilot.pause(0.1)
            self.assertIn("Tools installed", screen_text(self.app))

    async def test_a5_l_runs_the_login_under_suspend_and_rechecks(self):
        readiness = self.three_problems()
        events = []

        @contextlib.contextmanager
        def suspend():
            events.append("suspended")
            yield
            events.append("resumed")

        def login():
            events.append("login")
            readiness.fix("branch")
            return 0
        async with self.shell(self.controller(readiness, login=login), size=(120, 40)) as pilot:
            await self.loaded(pilot)
            before = readiness.calls
            with patch.object(self.app, "suspend", suspend):
                await self.command(pilot, "/setup")
                await self.press_button(pilot, "login")
                await self.until(pilot, lambda: "Login finished." in self.app.log_lines)
            self.assertEqual(events, ["suspended", "login", "resumed"])
            await self.until(pilot, lambda: readiness.calls > before and not self.app.checking)
            await pilot.pause(0.1)
            self.assertNotIn("! Codex: not logged in", screen_text(self.app))
            self.assertEqual(self.app.screen.__class__.__name__, "SettingsScreen")
            await pilot.press("escape")
            self.assertEqual(self.app.screen.__class__.__name__, "MainScreen")

    async def test_a5_failed_login_is_reported_not_raised(self):
        def login():
            raise OSError("codex is missing")

        @contextlib.contextmanager
        def suspend():
            yield
        async with self.shell(self.controller(login=login)) as pilot:
            await self.loaded(pilot)
            with patch.object(self.app, "suspend", suspend):
                await self.command(pilot, "/setup")
                await self.press_button(pilot, "login")
                await self.until(pilot, lambda: any("Login failed" in l for l in self.app.log_lines))
            self.assertIn("codex is missing", "\n".join(self.app.log_lines))

    async def test_a1_a_failed_login_names_the_device_code_guidance_before_the_retry(self):
        """A1/A2 (D5 repair 1): the TUI line for a login that returns a nonzero code (the `[l]` action, its login
        callable standing in for `setup.login`) carries the one Russian device-code guidance constant before the
        `[l]` retry hint and the tag, which keep their own wording. Interpretation: the guidance is a standalone
        sentence appended after the existing retry line. K1d: that line says «log in again: [l].» (the service text keeps
        its letter; Settings shows it as the button «log in»)."""
        @contextlib.contextmanager
        def suspend():
            yield
        async with self.shell(self.controller(login=lambda: 9), size=(120, 40)) as pilot:
            await self.loaded(pilot)
            with patch.object(self.app, "suspend", suspend):
                await self.command(pilot, "/setup")
                await self.press_button(pilot, "login")
                await self.until(pilot, lambda: any("code 9" in line for line in self.app.log_lines))
            journal = "\n".join(self.app.log_lines)
            self.assertIn(catalog.LOGIN_DEVICE_CODE_OFF, journal)  # the one constant holds the guidance
            self.assertIn("Login not completed (code 9); log in again: [l].", journal)  # the retry hint stays as it was
            self.assertIn(catalog.tag("setup.login_failed"), journal)  # and so does the tag
            self.assertIn("code 9", screen_text(self.app))  # the failed login is on screen, not only in the journal
            self.assertIn("log in again: button «%s»." % catalog.label("tui_settings.login"), screen_text(self.app))  # K1d: Settings names the button

    async def test_roles_view_lists_every_role(self):
        self.approve()
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            await self.command(pilot, "/setup")
            await self.press_button(pilot, "roles")
            await pilot.pause(0.1)
            text = screen_text(self.app)
            self.assertIn("Roles (model / effort)", text)
            from terminal_planner.setup import ROLE_DEFAULTS
            for role in ROLE_DEFAULTS:
                self.assertIn(role, text)

    async def test_settings_fit_80x24_with_the_key_row_visible(self):
        async with self.shell(self.controller(self.three_problems()), size=(80, 24)) as pilot:
            await self.loaded(pilot)
            await self.command(pilot, "/setup")
            await pilot.pause(0.2)
            lines = screen_lines(self.app)
            self.assertEqual(len(lines), 24)
            self.assertIn("Settings", lines[0])
            self.assertIn(catalog.label("tui_settings.recheck"), lines[-2])  # the button row sits above the key line
            self.assertIn("[enter] " + catalog.label("tui_settings.press"), lines[-1])
            self.assertIn("[esc] " + catalog.label("tui_settings.back"), lines[-1])


class KeyTests(ShellTest):
    async def test_a6_letters_typed_into_the_input_are_text(self):
        readiness = Readiness(check("git"))
        async with self.shell(self.controller(readiness)) as pilot:
            await self.loaded(pilot)
            before = readiness.calls
            await pilot.press(*"qgsmr?u")  # the input is the start focus (D4): letters are text at once
            self.assertEqual(self.app.query_one("#input").value, "qgsmr?u")
            self.assertEqual(self.app.screen.__class__.__name__, "MainScreen")
            self.assertEqual(list(self.app.log_lines), [])
            await pilot.pause(0.2)
            self.assertEqual(readiness.calls, before)  # no [r] refresh either
            await pilot.press("ctrl+q")
            await pilot.pause(0.1)
            self.assertTrue(self.app._exit)
            self.assertEqual(self.app.return_code, 0)

    async def test_ctrl_q_quits_from_settings_and_help(self):
        async with self.shell() as pilot:
            await self.loaded(pilot)
            await self.command(pilot, "/setup")
            await pilot.press("ctrl+q")
            await pilot.pause(0.1)
            self.assertTrue(self.app._exit)

    async def test_setup_opens_settings_only_from_the_main_screen(self):
        """K1a: Ctrl+S is gone; `/setup` opens Settings from the main screen, and the key does nothing over it."""
        async with self.shell() as pilot:
            await self.loaded(pilot)
            await self.command(pilot, "/setup")
            await pilot.press("ctrl+s")
            self.assertEqual(len([s for s in self.app.screen_stack if s.__class__.__name__ == "SettingsScreen"]), 1)

    async def test_a_session_that_cannot_open_is_reported_in_the_panel(self):
        from terminal_planner.authority import Authority
        with Authority(self.state, self.project, fixture_id="test"):  # another zplan holds the project lock
            async with self.shell() as pilot:
                await self.until(pilot, lambda: self.app.plan_error)
                self.assertIn("Not opened:", screen_text(self.app))
                await self.command(pilot, "/setup")  # Settings still works
                self.assertEqual(self.app.screen.__class__.__name__, "SettingsScreen")


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is unavailable: ZPLAN_TEST_WHEELHOUSE with textual 8.2.8 wheels is needed")
class ModalButtonTests(ShellTest):
    """K1c1: the modals answer with buttons, not letters. One smoke test per criterion, plus the invariant that no
    modal binds a letter and each modal's buttons are its catalog entries.

    Interpretations: the send button of a note form is shown on every `NoteScreen`, an `enter=True` card note
    included (its Enter-sends behaviour is unchanged, the button is one more way); the catalog's `tui_confirm` and
    `tui_bootstrap` entries `yes` / `no` / `accept` / `later` are the buttons' own labels, the other entries
    (`press`, `button`, `send`, `back`) name the keys."""

    async def push(self, pilot, modal):
        """Push `modal`, wait for it to be on top, return the list its answer lands in."""
        answers = []
        self.app.push_screen(modal, answers.append)
        await self.until(pilot, lambda: self.app.screen is modal and modal.query("Button, TextArea, VerticalScroll"))
        await pilot.pause()
        return answers

    def focused_id(self):
        return getattr(self.app.focused, "id", None)

    async def test_c1_confirm_answers_with_buttons_and_esc_is_no(self):
        from terminal_planner.tui.modals import ConfirmScreen
        async with self.shell() as pilot:
            await self.loaded(pilot)
            answers = await self.push(pilot, ConfirmScreen("Merge?"))
            self.assertEqual(self.focused_id(), "confirm-no")
            await pilot.press("y", "n", "q", "a")  # no letter answers
            await pilot.pause(0.1)
            self.assertEqual(answers, [])
            await pilot.press("right")
            self.assertEqual(self.focused_id(), "confirm-yes")
            await pilot.press("left")
            self.assertEqual(self.focused_id(), "confirm-no")
            await pilot.press("tab")
            self.assertEqual(self.focused_id(), "confirm-yes")
            await pilot.press("enter")
            await self.until(pilot, lambda: answers)
            self.assertEqual(answers, [True])
            answers = await self.push(pilot, ConfirmScreen("Merge?"))
            await pilot.press("enter")  # the focus starts on «no»
            await self.until(pilot, lambda: answers)
            self.assertEqual(answers, [False])
            answers = await self.push(pilot, ConfirmScreen("Merge?"))
            await pilot.press("escape")
            await self.until(pilot, lambda: answers)
            self.assertEqual(answers, [False])

    async def test_c2_run_start_confirm_starts_on_yes(self):
        from terminal_planner.tui.app import EnterConfirmScreen
        async with self.shell() as pilot:
            await self.loaded(pilot)
            answers = await self.push(pilot, EnterConfirmScreen("Start M1?"))
            self.assertEqual(self.focused_id(), "confirm-yes")
            await pilot.press("н", "y")  # the old Russian-layout key answers nothing
            await pilot.pause(0.1)
            self.assertEqual(answers, [])
            await pilot.press("enter")
            await self.until(pilot, lambda: answers)
            self.assertEqual(answers, [True])

    async def test_c4_note_form_sends_with_its_button_not_ctrl_g(self):
        from terminal_planner.tui.card_kinds import QuestionNoteScreen
        from terminal_planner.tui.modals import NoteScreen
        async with self.shell() as pilot:
            await self.loaded(pilot)
            answers = await self.push(pilot, NoteScreen(answer=True))
            await pilot.press("o", "k", "ctrl+g")
            await pilot.pause(0.1)
            self.assertEqual(answers, [])
            await pilot.press("tab")
            self.assertEqual(self.focused_id(), "note-send")
            await pilot.press("enter")
            await self.until(pilot, lambda: answers)
            self.assertEqual(answers, ["ok"])
            answers = await self.push(pilot, QuestionNoteScreen("Answer", answer=True, enter=True))
            await pilot.press("o", "k", "enter")  # a card note: Enter in the field still sends
            await self.until(pilot, lambda: answers)
            self.assertEqual(answers, ["ok"])
            answers = await self.push(pilot, NoteScreen(answer=True))
            await pilot.press("o", "escape")
            await self.until(pilot, lambda: answers)
            self.assertEqual(answers, [None])

    async def test_k1d_a_refused_answer_form_note_names_steps_not_letter_keys(self):
        """K1d C1/C4: the note a blocked answer send puts above the reopened form (the failing readiness lines, built
        as `send_answer_draft` builds it) shows each letter key of a service line as its TUI step."""
        from terminal_planner.cli import summary
        from terminal_planner.tui.card_kinds import FIX_KEY, NOT_STARTED_BELOW
        from terminal_planner.tui.modals import NoteScreen
        lines = ["There are uncommitted changes — [d] view",
                 "Codex: not logged in at ~/x — [l] log in (zplan's own login, not ~/.codex)"]
        note = "\n".join([NOT_STARTED_BELOW] + ["! " + FIX_KEY.sub("", summary(line)) for line in lines])
        async with self.shell() as pilot:
            await self.loaded(pilot)
            await self.push(pilot, NoteScreen("Answer to the question of M1", answer=True, text="x", note=note))
            shown = str(self.app.screen.query_one("#note-note").render())
            self.assertIn("! There are uncommitted changes — /diff view", shown)
            self.assertIn("! Codex: not logged in at ~/x — /setup → log in (zplan's own login", shown)
            self.assertNotRegex(shown, r"\[[a-z]\]")

    async def test_k1d_a_lost_planner_watch_names_a_step_not_a_letter_key(self):
        """K1d C1/C4: a watch that ends without a result (`ObservationDetached`, engine.py) lands in the planner
        progress lines with its `[w]` hint; the status area above the chat and the «Now» tab show the step."""
        from terminal_planner.engine import ObservationDetached
        from terminal_planner.tui.app import ZplanApp
        from terminal_planner.tui.controller import refusal
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            self.app.watching = True
            ZplanApp.watched(self.app, None, refusal(ObservationDetached()))
            await pilot.pause(0.3)
            shown = screen_text(self.app)
            self.assertIn("/attempt", shown)  # wrapped in the status box, so the rest of the line is not compared
            self.assertNotRegex(shown, r"\[[a-z]\]")
            self.assertIn("/attempt", " ".join(self.app.screen.live_view()))  # the rest of the line is T1's engine text

    async def test_c5_help_and_text_close_with_esc_only(self):
        from terminal_planner.tui.modals import HelpScreen, TextScreen
        async with self.shell() as pilot:
            await self.loaded(pilot)
            for modal in (HelpScreen("tui_input"), TextScreen("Changes", ["line"], diff=True)):
                await self.push(pilot, modal)
                await pilot.press("q", "question_mark", "f1")
                await pilot.pause(0.1)
                self.assertIs(self.app.screen, modal)
                await pilot.press("escape")
                await self.until(pilot, lambda: self.app.screen is not modal)

    async def test_no_modal_binds_a_letter_and_its_buttons_are_its_catalog_entries(self):
        """The invariant: no modal of `modals.py` (nor `EnterConfirmScreen`) binds a single-letter key, and the
        labels of each modal's buttons are exactly its catalog entries named by `BUTTONS`."""
        from textual.widgets import Button
        from terminal_planner.tui import modals
        from terminal_planner.tui.app import EnterConfirmScreen
        from terminal_planner.tui.card_kinds import QuestionNoteScreen
        for cls in (modals.HelpScreen, modals.ConfirmScreen, EnterConfirmScreen, modals.BootstrapScreen,
                    modals.NoteScreen, QuestionNoteScreen, modals.TextScreen):
            keys = {key for klass in cls.__mro__ for binding in vars(klass).get("BINDINGS", ())
                    for key in binding.key.split(",")}
            self.assertEqual({key for key in keys if len(key) == 1 and key.isalpha()}, set(), cls.__name__)
        from terminal_planner.tui.screens import PlanScreen, SettingsScreen
        for cls in (PlanScreen, SettingsScreen, modals.RunScreen):  # K1c2/K1c3: the same for the plan screen,
            # Settings and the run end screen (whose buttons are `tui_run` entries), `?` included
            keys = {key for klass in cls.__mro__ for binding in vars(klass).get("BINDINGS", ())
                    for key in binding.key.split(",")}
            self.assertEqual({key for key in keys if len(key) == 1 or key == "question_mark"}, set(), cls.__name__)
        # K1c3: the run end screen's buttons are its `tui_run` entries, keyed Tab, Enter or Esc, never a letter
        self.assertEqual({a.key for a in catalog.ACTIONS.values() if a.screen == "tui_run"} - {"tab", "enter", "esc"},
                         set())
        self.assertTrue(set(modals.RunScreen.IDS.values()) <= set(catalog.ACTIONS))
        profile = type("View", (), {"bootstrap": ("profile",), "present": False})
        modals_and_entries = (
            (modals.ConfirmScreen("?"), {"tui_confirm.yes", "tui_confirm.no"}),
            (EnterConfirmScreen("?"), {"tui_confirm.yes", "tui_confirm.no"}),
            (modals.BootstrapScreen(profile), {"tui_bootstrap.accept", "tui_bootstrap.later"}),
            (modals.NoteScreen(), {"tui_note.send"}),
            (modals.NoteScreen(answer=True), {"tui_answer.send"}),
            (modals.NoteScreen(answer=True, bar="tui_attempt"), {"tui_attempt.send"}),
        )
        async with self.shell() as pilot:
            await self.loaded(pilot)
            for modal, entries in modals_and_entries:
                await self.push(pilot, modal)
                self.assertEqual({button.label.plain for button in modal.query(Button)},
                                 {catalog.label(entry) for entry in entries}, type(modal).__name__)
                self.assertTrue(entries <= {a.id for a in catalog.ACTIONS.values() if a.screen == modal.bar})
                bar = modal.key_bar(120)
                self.assertTrue(all("[%s]" % key in bar for key in ("enter", "esc")) or isinstance(
                    modal, modals.BootstrapScreen), bar)
                self.assertNotIn("ctrl+g", bar)
                modal.dismiss(None)
                await self.until(pilot, lambda: self.app.screen is not modal)
            # K1c2: each button of Settings is an entry of its bar, and the bar names no letter
            await self.command(pilot, "/setup")
            settings = self.app.screen
            await self.until(pilot, lambda: settings.query("#settings-buttons Button"))
            self.assertEqual({button.name for button in settings.query("#settings-buttons Button")},
                             {"recheck", "roles"})
            self.assertTrue({"tui_settings." + button.name for button in settings.query("#settings-buttons Button")}
                            <= {a.id for a in catalog.ACTIONS.values() if a.screen == settings.bar})
            self.assertNotRegex(screen_lines(self.app)[-1], r"\[[a-z?]\]")


if __name__ == "__main__":
    unittest.main()
