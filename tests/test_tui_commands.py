"""I2: the `/` commands in the chat input and the new bottom `Bar` on the main screen (release 0.5.2).

Four checks, each mapped to one acceptance criterion:

* A1+A2 (one whole-app test, `CommandPaletteTests.test_a1_a2_...`): typing `/` in the chat input shows the palette
  straight above it, with only the commands the current state allows, at 120x40 and 80x24; `/st` narrows it and
  deleting the `/` hides it; a plain line still goes to the chat (the chat tests keep that path green). Then the
  wired commands act: `/help` opens the help, `/stop` while a stage runs reaches the existing stop confirmation,
  `/stop` while idle and the out-of-state `/plan` show the not-now note and change nothing else, and Esc with the
  palette open only hides it.
* A3 (one whole-app test, `CommandPaletteTests.test_a3_...`): the bottom row of the main screen is the `Bar` —
  project, branch, the running stage's clock for the fixture flow (`elapsed` 187 -> `0:03:07`), `—` when the clock
  is unknown, and all four key hints at 120 columns (the Bar's own clipping is allowed at 80); a modal's bar is
  unchanged, and it survives a resize (the HelpScreen leg resizes to 80x24 and re-reads the last row).
* A4 (unit level, `SlashStateTests`): `slash_state` maps the three fixture situations to idle, plan_ready and
  running (a running stage beats an unrelated error line); `/stop` targets the running row while another row is
  selected.

The whole-app tests run through `tui_support`/Textual Pilot; the unit tests need neither a project nor an engine.

Interpretations recorded here (the worker's summary never reaches the reviewers):

* A4 builds `Snapshot`/`Row` values directly instead of opening the shell: `slash_state` is pure and reads only the
  facts the screen already holds (rows, the plan revision and status, the draft), so the three situations mirror
  the fixtures (no plan -> idle; a proposed revision -> plan_ready; one running row -> running) without a store.
* `/stop` targeting is unit-tested through the real `MainScreen.stop_running_row` with a stand-in screen/app that
  exposes only what the method touches (`rows()`, `selected`, `action_stop_milestone`) — the whole-app walk is
  avoided as the criterion asks, and the method's own contract (pick the running row, restore the owner's
  selection) is what the assertion pins.
* A3's `—` case: the fixture flow always carries a known `elapsed`, so the snapshot's flow is replaced with one
  whose `elapsed` is None (the unknown-clock case `activity` draws `—` for); the bar is still fed through the real
  `MainScreen.show_keys`, no widget is stubbed.
* The bar's expectations are read from `strings.text`, not from a pinned language, so the test holds whatever
  locale/`ui.json` the runner would otherwise use (this module never writes a language file).

* Regressions for the findings of this run history (all unit level, no extra whole-app test): an
  unwired-but-allowed command keeps the typed text (`test_regression_an_unwired_command_keeps_the_input`); a failed
  planning run maps to `error` while a running stage still wins (`test_a4_a_failed_planning_run_is_error`); an open
  palette is re-listed against the *current* state when the lifecycle changes
  (`test_regression_an_open_palette_follows_the_state`); and a displayed run-pane operation error or blocked note
  maps to `error`, not only the plan-open error (`test_regression_a_displayed_run_error_maps_to_error` — the
  code-review finding, whose fix the bar's job mapping inherits through `screen_slash_state`); and a planner
  observation failure shown in the planner pane maps to `error`, not a phantom `planning`
  (`test_regression_a_displayed_planner_error_maps_to_error`, driven through the real `ZplanApp.watched` callback).
  The first asserts
  `MainScreen.on_input_submitted`'s own branch with a stand-in screen/app/input, so the ordering fix (dispatch
  availability checked before the input is cleared) is pinned without a third pilot walk; the third pins
  `MainScreen.refresh_palette` feeding `show_for` the current `screen_slash_state` — the palette widget's own
  filtering is what A1 covers. The acceptance finding that a modal's key bar must survive a resize is covered
  inside the A3 whole-app test, keeping the two-whole-app budget.
"""

import unittest
from unittest import mock
from dataclasses import replace

# imported first for its side effect: the offline wheelhouse (ZPLAN_TEST_WHEELHOUSE) joins `sys.path` before the
# guarded imports below, so this module sees Textual and Rich there on a host that installs neither.
import tui_support  # noqa: F401
from tui_support import HAVE_TEXTUAL, screen_lines, screen_text

from terminal_planner.tui import slash, strings
from test_tui_live import LiveShell

MISSING_REASON = "Rich и Textual недоступны: нужен ZPLAN_TEST_WHEELHOUSE с wheels rich и textual 8.2.8"
# The app, the palette, `Row` and `Snapshot` all need Rich (through Textual), so they are imported under the same
# guard the other TUI modules use: the module still loads (with both classes declared and skipped) where neither is
# importable, which `tests.test_toolchain` scans for (A-2 of that module).
try:
    from rich.cells import cell_len  # noqa: F401
    from terminal_planner.delivery import Row
    from terminal_planner.tui import app as ui
    from terminal_planner.tui import palette
    from terminal_planner.tui.activity import bar_text
    from terminal_planner.tui.controller import Snapshot
except ImportError:  # pragma: no cover - the bare import scan of tests.test_toolchain covers this path
    Row = ui = palette = Snapshot = bar_text = None

HAVE = HAVE_TEXTUAL and ui is not None and palette is not None and Row is not None


@unittest.skipUnless(HAVE, MISSING_REASON)
class CommandPaletteTests(LiveShell):
    """A1+A2 and A3 through the real shell; at most two whole-app tests, one per group."""

    def setUp(self):
        super().setUp()
        offered = mock.patch.object(strings, "OFFERED", strings.LANGUAGES)  # L1: this test pins `/language`
        offered.start()
        self.addCleanup(offered.stop)

    def palette(self):
        return self.app.query_one("#palette", palette.Palette)

    def field(self):
        return self.app.query_one("#input")

    def flat(self):
        """The `#status` area's own text with its line wrapping collapsed (i9: the chat pane is 38% wide, so a note
        the area shows wraps inside it — and `screen_text` interleaves the right pane's cells on the same rows — so
        the note is read from the widget the app put it in, not the whole screen)."""
        raw = self.app.query_one("#status").render()
        return " ".join(getattr(raw, "plain", str(raw)).split())

    async def type_slash(self, pilot, word=""):
        """Type `/` then `word` in the chat input, letting the change events land."""
        await pilot.press("/")
        await pilot.pause()
        if word:
            await self.type(pilot, word)
            await pilot.pause()

    async def test_a1_a2_the_palette_lists_the_allowed_commands_and_the_wired_ones_act(self):
        """A1 at 120x40 and 80x24: `/` shows the palette above the input with only the commands idle allows, `st`
        narrows it, deleting the `/` hides it. A2: `/help` opens the help screen, `/stop` while a stage runs
        reaches its stop confirmation, `/stop` while idle only shows the not-now note, a bare `/plan` with no card and
        no unsent revision says `note.plan_needs_goal` (K1b), and Esc with the palette open hides it and leaves the
        screen as it was."""
        idle_names = ("/plan", "/diff", "/open", "/status", "/language", "/setup")  # P1a: no plan, so no row for `/run`
        for size in ((120, 40), (80, 24)):
            with self.subTest(size=size):
                async with self.shell(size=size) as pilot:
                    await self.loaded(pilot)
                    box, field = self.palette(), self.field()
                    self.assertFalse(box.display)  # hidden until a "/"
                    self.assertEqual(field.value, "")
                    await self.type_slash(pilot)
                    # A1: the palette shows, straight above the prompt box
                    self.assertTrue(box.display)
                    self.assertGreaterEqual(box.region.height, 3)  # a border and at least a row
                    self.assertLessEqual(box.region.bottom, field.region.y)
                    shown = screen_text(self.app)
                    for name in idle_names:
                        self.assertIn(name, shown, size)
                    self.assertNotIn("/stop", shown, size)  # /stop acts only while a stage runs
                    self.assertNotIn("/run", shown, size)  # P1a: no stage to start, so `/run` is not offered
                    # A1: a prefix narrows the list; deleting the "/" hides it
                    await self.type(pilot, "st")
                    await pilot.pause()
                    self.assertTrue(box.display)
                    narrowed = screen_text(self.app)
                    self.assertIn("/status", narrowed)
                    self.assertNotIn("/help", narrowed)
                    await pilot.press("backspace", "backspace", "backspace")
                    await pilot.pause()
                    self.assertFalse(box.display)
                    self.assertEqual(field.value, "")
                    # A2: Esc with the palette open hides it and leaves the screen as it was
                    await self.type_slash(pilot)
                    self.assertTrue(box.display)
                    await pilot.press("escape")
                    await pilot.pause()
                    self.assertFalse(box.display)
                    self.assertEqual(field.value, "")
                    self.assertEqual(type(self.app.screen).__name__, "MainScreen")
        # A2: the refusals and the help, once, at 120x40 (the panel's own words are read in full here)
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            await self.type_slash(pilot, "plan")  # K1b: acts in idle; nothing to send -> the note, input cleared
            await pilot.press("enter")
            await pilot.pause()
            self.assertIn(strings.text("note.plan_needs_goal"), self.flat())
            self.assertEqual(self.field().value, "")
            for name in ("/stop",):  # refused while idle (no running stage)
                await self.type_slash(pilot, name[1:])
                await pilot.press("enter")
                await pilot.pause()
                note = strings.text("note.not_now", name=name)
                self.assertIn(" ".join(note.split()), self.flat(), name)
                self.assertEqual(type(self.app.screen).__name__, "MainScreen", name)  # nothing else happened
                self.assertEqual(self.field().value, name, name)  # a refusal keeps the text (see the docstring)
                for _ in range(len(name)):  # the input kept the text; clear it for the next check
                    await pilot.press("backspace")
                await pilot.pause()
                self.assertFalse(self.palette().display)  # the "/" is gone, so the palette hides
            # /language is wired since the i6 + i3a merge: a bare /language opens the chooser (the unwired branch
            # is test_regression_an_unwired_command_keeps_the_input).
            await self.type_slash(pilot, "language")
            await pilot.press("enter")
            await self.until(pilot, lambda: type(self.app.screen).__name__ == "LanguageScreen")
            await pilot.press("escape")
            await self.until(pilot, lambda: type(self.app.screen).__name__ == "MainScreen")
            await self.type_slash(pilot, "help")
            await pilot.press("enter")
            await self.until(pilot, lambda: type(self.app.screen).__name__ == "HelpScreen")
            self.assertEqual(self.palette().display, False)
            await pilot.press("escape")
            await self.until(pilot, lambda: type(self.app.screen).__name__ == "MainScreen")
        # A2: /stop reaches the running stage's own stop confirmation (a running fixture row, nothing to follow)
        self.approve(running=True)
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            self.assertEqual(ui.screen_slash_state(self.app), "running")
            await self.type_slash(pilot, "stop")
            self.assertIn("/stop", screen_text(self.app))  # allowed while a stage runs
            await pilot.press("enter")
            # the confirm text is runs.py's (T1's): wait for the modal itself, not for its wording
            await self.until(pilot, lambda: type(self.app.screen).__name__ == "ConfirmScreen")
            await pilot.press("escape")
            await self.until(pilot, lambda: type(self.app.screen).__name__ == "MainScreen")

    async def test_a3_the_bottom_row_is_the_bar_with_the_project_branch_clock_and_keys(self):
        """A3: the main screen's bottom row is the `Bar` — project and branch (the fields the old `#header` also
        carried), the running stage's job phrase with its clock (`elapsed` 187 -> `0:03:07`), `—` when the clock is
        unknown, and the four key hints at 120 columns; the same row is clipped at 80, and a modal's bar is
        unchanged."""
        self.approve()  # M1 running from START
        self.clock.advance(187)  # the active attempt's own clock: 0:03:07
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            bar = screen_lines(self.app)[-1]
            self.assertIn("project with spaces", bar)  # the project shows
            self.assertIn("main", bar)  # and the branch
            self.assertEqual(self.main().bar_job()[2], 187)  # the fixture flow's own elapsed
            self.assertIn(strings.text("live.job_timer", stage="M1", h="0:03:07"), bar)
            for key_id in ("bar.key_tabs", "bar.key_commands", "bar.key_close", "bar.key_quit"):
                self.assertIn(strings.text(key_id), bar)
            # A3: an unknown clock draws — (the fixture flow's elapsed replaced with None), still through the real
            # Bar: `show_keys` feeds it and the widget's own render is read, so a background repaint cannot race it
            snap = self.app.snapshot
            self.app.snapshot = replace(snap, flow={**snap.flow, "elapsed": None})
            self.main().show_keys()
            self.assertIn("—", self.app.query_one("#keys", ui.Bar).render().plain)
            # A3: a modal's own bar is untouched (the help's [esc] закрыть, the catalog bar as before)
            await self.command(pilot, "/help")
            await self.until(pilot, lambda: type(self.app.screen).__name__ == "HelpScreen")
            await pilot.pause()
            self.assertIn("[esc]", screen_lines(self.app)[-1])  # the label is the catalog's (T1)
            # Regression (acceptance finding 1): the modal's own bar must survive a resize. The `Bar` repaints its
            # cached main fields on its *own* resize, and that repaint lands after `MainScreen.on_resize` fed the
            # modal's keys — so the main project/status/key bar used to replace «[esc] закрыть». `on_resize` now
            # re-feeds the row once the layout has settled (see `docs/USER_FLOW.md` / the fix in `app.py`).
            await pilot.resize_terminal(80, 24)
            await pilot.pause(0.3)
            self.assertIn("[esc]", screen_lines(self.app)[-1])  # the modal key bar, not the main one
            await pilot.press("escape")
            await self.until(pilot, lambda: type(self.app.screen).__name__ == "MainScreen")
        # A3: at 80 columns the Bar's own clipping is allowed — the row is still the Bar (it starts with the project)
        async with self.shell(size=(80, 24)) as pilot:
            await self.loaded(pilot)
            self.assertIn("project with spaces", screen_lines(self.app)[-1])


@unittest.skipUnless(HAVE, MISSING_REASON)
class SlashStateTests(unittest.TestCase):
    """A4 at unit level: `slash_state`'s mapping and `/stop`'s target, with no whole-app walk."""

    def snapshot(self, **kw):
        facts = dict(project="Project", branch="main", clean=True, version=None, status=None, lines=(), roles=())
        facts.update(kw)
        return Snapshot(**facts)

    def test_a4_slash_state_maps_the_three_fixture_situations(self):
        """A4: no plan is idle, a proposed revision is plan_ready, one running row is running; a running stage
        beats an unrelated error line. Interpretation: `slash_state` is pure (the screen's own facts), so the three
        situations are their `Snapshot` values, not a shell walk."""
        self.assertEqual(ui.slash_state(self.snapshot()), "idle")
        self.assertEqual(ui.slash_state(self.snapshot(version=1, status="proposed")), "plan_ready")
        running = self.snapshot(rows=(Row(id="M1", title="M1", state="running", text="идёт"),))
        self.assertEqual(ui.slash_state(running), "running")
        self.assertEqual(ui.slash_state(running, blocked="план не открылся"), "running")  # running beats an error

    def test_a4_a_failed_planning_run_is_error(self):
        """Regression (acceptance finding 2): the plan screen's own failure facts — its `kind == "failed"` view,
        whose body is the «планирование остановилось» line, and the `run_failed`/`proposal_invalid` status behind it
        — map to `error`, so the bar reports the failure and the palette stops offering idle commands. A running
        stage keeps precedence over the same failure (the task's «a running stage takes precedence»). Interpretation:
        the error is derived from the facts the screen already holds (the loaded `PlanView` and `snapshot.status`),
        with no controller or engine call."""
        from terminal_planner.planning import PlanView

        failed = self.snapshot(
            version=1, status="run_failed",
            plan=PlanView("failed", 1, "run_failed",
                          ("", "План r1 · планирование остановилось"), ("retry", "revise")))
        self.assertEqual(ui.slash_state(failed), "error")
        # the status alone (no view) is the same failure fact
        self.assertEqual(ui.slash_state(self.snapshot(version=1, status="proposal_invalid")), "error")
        # running-stage precedence is preserved
        live = replace(failed, rows=(Row(id="M1", title="M1", state="running", text="идёт"),))
        self.assertEqual(ui.slash_state(live), "running")

    def test_a4_stop_targets_the_running_row_while_another_row_is_selected(self):
        """A4: `/stop` (through `running_row` and `MainScreen.stop_running_row`) targets the one running row, not
        the owner's own selection, and puts the selection back. Interpretation: the method is exercised with a
        stand-in screen/app exposing only what it touches, per the criterion's "unit-level tests, not a whole-app
        walk"."""
        rows = (Row(id="M1", title="M1", state="running", text="идёт"),
                Row(id="M2", title="M2", state="waiting", text="ждёт"))
        self.assertEqual(ui.running_row(rows).id, "M1")
        self.assertIsNone(ui.running_row((rows[1],)))

        class FakeApp:
            def __init__(self, rows):
                self._rows, self.selected, self.stopped = rows, "M2", []

            def rows(self):
                return self._rows

            def action_stop_milestone(self):
                self.stopped.append(self.selected)

        class FakeScreen:
            def __init__(self, app):
                self.app = app

        app = FakeApp(rows)
        ui.MainScreen.stop_running_row(FakeScreen(app))
        self.assertEqual(app.stopped, ["M1"])  # the running row, not the selected M2
        self.assertEqual(app.selected, "M2")  # the owner's own selection is untouched

    def test_a4_stop_targets_the_selected_row_when_it_is_running_too(self):
        """K1a regression: `x` stopped the selected row; with parallel slots `/stop` follows the selection among the
        running rows and falls back to the first running row only when the selection is not running."""
        rows = (Row(id="M1", title="M1", state="running", text="идёт"),
                Row(id="M2", title="M2", state="running", text="идёт"))

        class FakeApp:
            def __init__(self, selected):
                self.selected, self.stopped = selected, []

            def rows(self):
                return rows

            def action_stop_milestone(self):
                self.stopped.append(self.selected)

        class FakeScreen:
            def __init__(self, app):
                self.app = app

        for selected, stopped in (("M2", "M2"), ("M1", "M1"), ("M3", "M1")):
            app = FakeApp(selected)
            ui.MainScreen.stop_running_row(FakeScreen(app))
            self.assertEqual(app.stopped, [stopped], selected)
            self.assertEqual(app.selected, selected)


class _Recorder:
    """Answers any attribute with a recorder and records any call: only an entry's convention is checked with it."""

    def __getattr__(self, name):
        return _Recorder()

    def __call__(self, *args, **kwargs):
        return None


class _FakeInput:
    def __init__(self, value=""):
        self.value = value


class _FakePalette:
    def __init__(self, display=True):
        self.display, self.calls = display, []

    def show_for(self, value, state):
        self.calls.append((value, state))
        self.display = True


class _FakeApp:
    def __init__(self, snapshot=None):
        self.snapshot, self.plan_error, self.watching, self.goal_draft = snapshot, "", False, ""
        self.run_note = ""
        # i3a: `screen_slash_state` also reads the main screen's open goal-draft card from the stack; this stand-in
        # has no screen, so the fact is simply absent (no card, the `goal_draft` text alone decides `draft`).
        self.screen_stack = ()
        self.chat_note, self.changes = "", 0
        self.progress = []  # the planner pane's own lines (`screen_slash_state` reads its newest one)
        self.run_watch, self.finish_note, self.refreshes = None, "", 0

    def changed(self):
        self.changes += 1

    def note(self, line):
        self.progress.append(line)
        self.changed()

    def request_refresh(self):
        self.refreshes += 1


def _main_method(name):
    """The real `MainScreen` method `name`, copied onto the stand-in class so the method under test runs on it.
    Without the app module (Textual/Rich missing) a stub stands in its place: the class, and with it every declared
    test, still exists (the declared test count a `tests.test_toolchain` scan reads must not depend on the
    dependencies), and the skipped test never reaches the stub."""
    def missing(self, *args, **kwargs):  # pragma: no cover - reached only where the tests skip anyway
        raise AssertionError(MISSING_REASON)
    return missing if ui is None else getattr(ui.MainScreen, name)


class _BarScreen:
    """The `MainScreen` methods `/status` and the bar read, on the fake app: the real `status_summary`,
    `show_status`, `bar_job` and `status_note` run; the tab switch is recorded."""

    status_summary = _main_method("status_summary")
    show_status = _main_method("show_status")
    bar_job = _main_method("bar_job")
    status_note = _main_method("status_note")

    def __init__(self, app):
        self.app, self.tabs = app, []

    def show_tab(self, tab, reveal=True):
        self.tabs.append(tab)


class _FakeScreen:
    """Only the widgets `MainScreen.on_input_submitted`/`refresh_palette` touch, so their own contract is what
    the assertions read — no whole-app walk. i3a: the dispatcher (`run_command`) and the note it shows are the real
    `MainScreen` methods, bound here; the entries they call are read from the production `COMMAND_ACTIONS`."""

    run_command = _main_method("run_command")
    status_note = _main_method("status_note")

    card_specs = {}  # `submit_verdict` asks whether a merge card is open

    def __init__(self, app, field, box):
        self.app, self._field, self._box = app, field, box

    def palette_pick(self, line, complete=False):
        return None  # O3: no highlighted row, so the typed line keeps its own path

    def remember(self, line):
        pass  # O3: the history of accepted lines is not what these stand-ins read

    def query_one(self, selector, *args):
        if selector == "#input":
            return self._field
        if selector == "#palette":
            return self._box
        raise AssertionError(selector)


@unittest.skipUnless(HAVE, MISSING_REASON)
class CommandWiringTests(unittest.TestCase):
    """Regressions for the acceptance findings 1 and 3, at unit level (no pilot): the input/dispatch branch and
    the open palette following the lifecycle."""

    def test_regression_an_unwired_command_keeps_the_input(self):
        """Acceptance finding 1 (docs/USER_FLOW.md «a refused or unwired command ... keeps the text»): an
        unwired-but-allowed command is a `Submitted`, so `on_input_submitted` must read the dispatcher's own
        not-run report *before* clearing the input — the not-now note shows and the typed text stays. i3a moved the
        availability check into the one dispatcher (`run_command`) and wired `/open`, so the stand-in walks
        `/language` — allowed in every state and still unwired (run i6 wires it). Interpretation: the branch is
        driven with a stand-in screen/app/input rather than another pilot walk, per the A5 limit of two whole-app
        tests; a wired command still clears its input."""
        app = _FakeApp()  # no snapshot -> idle, where /language is allowed
        field = _FakeInput("/language")
        box = _FakePalette()
        screen = _FakeScreen(app, field, box)
        # `/language` exists only while several languages are offered (T2), so the test offers all three
        with mock.patch.object(strings, "OFFERED", strings.LANGUAGES), mock.patch.dict(ui.COMMAND_ACTIONS):
            del ui.COMMAND_ACTIONS["/language"]
            ui.MainScreen.on_input_submitted(screen, type("Ev", (), {"value": "/language"})())
            expected = strings.text("note.not_now", name="/language")  # the stored language `ru` is offered here
        self.assertEqual(app.chat_note, expected)
        self.assertEqual(app.changes, 1)
        self.assertEqual(field.value, "/language")  # the unwired note kept the text
        self.assertTrue(box.display)  # and the palette was left alone

    def test_p2a_a_refusal_above_the_chat_clears_on_an_accepted_command_or_an_owner_turn(self):
        """C4: `chat_note` clears on the owner's next accepted command or accepted turn, whatever set it (a refused
        command, a renewal's outcome, a cancel note). Interpretation: "a command is accepted" is `run_command`
        finding an action for it; a refused send keeps the line."""
        ran = []
        with mock.patch.object(strings, "OFFERED", strings.LANGUAGES), \
                mock.patch.dict(ui.COMMAND_ACTIONS, {"/language": lambda screen, argument, key: ran.append(argument)}):
            app = _FakeApp()  # no snapshot -> idle: /merge is refused, /language is allowed
            screen = _FakeScreen(app, _FakeInput("/merge"), _FakePalette())
            ui.MainScreen.on_input_submitted(screen, type("Ev", (), {"value": "/merge"})())
            refusal = app.chat_note
            self.assertTrue(refusal)
            screen._field = _FakeInput("/language en")
            ui.MainScreen.on_input_submitted(screen, type("Ev", (), {"value": "/language en"})())
            self.assertEqual(ran, ["en"])
            self.assertEqual(app.chat_note, "")  # the accepted command ended the refusal
            app.chat_note = "Подготовлен новый план"  # a note the refusal did not set goes the same way
            ui.MainScreen.on_input_submitted(screen, type("Ev", (), {"value": "/language en"})())
            self.assertEqual(app.chat_note, "")

        for accepted, left in ((True, ""), (False, "Подготовлен новый план")):
            turn = type("Turn", (), {"chat_note": "Подготовлен новый план",
                                     "chat_snapshot": lambda self: None,
                                     "chat": type("Chat", (), {"send": lambda self, value, snapshot=None:
                                                               (accepted, "")})()})()
            ui.ZplanApp.send_chat(turn, "привет")
            self.assertEqual(turn.chat_note, left)

    def test_the_entries_share_one_convention_and_name_registered_commands(self):
        """i3a's entry convention: every `COMMAND_ACTIONS` entry is `callable(screen, argument, key)` and its name is
        a command `slash` registers — the typed line and a card button both come through `MainScreen.run_command`,
        which is the only caller. The probe answers any attribute a recorder, so only the convention is checked (the
        actions themselves have their own tests)."""
        probe = _Recorder()
        names = {command.name for command in slash.COMMANDS}
        for name in ("/help", "/quit", "/stop", "/setup", "/status", "/approve", "/merge", "/plan", "/decline",
                     "/open", "/diff"):
            with self.subTest(name):
                self.assertIn(name, ui.COMMAND_ACTIONS)
                self.assertIn(name, names)
        for name, action in ui.COMMAND_ACTIONS.items():
            with self.subTest(name):
                action(probe, "", None)  # every entry takes the parsed argument and the card key

    def test_regression_an_open_palette_follows_the_state(self):
        """Acceptance finding 3 (A1: «only the commands allowed ... in the current state»): `refresh_palette`
        re-lists an open palette against the *current* `screen_slash_state`, so a lifecycle change (a stage starts or
        finishes) shows the new commands without the owner retyping — the previous code refreshed only on
        `Input.Changed`. A hidden palette is left hidden."""
        running = Snapshot(project="P", branch="main", clean=True, version=1, status="proposed",
                           lines=(), roles=(),
                           rows=(Row(id="M1", title="M1", state="running", text="идёт"),))
        app = _FakeApp(running)
        field = _FakeInput("/")
        box = _FakePalette()
        screen = _FakeScreen(app, field, box)
        ui.MainScreen.refresh_palette(screen)
        self.assertEqual(box.calls, [("/", "running")])
        # the same open palette re-lists after the stage finishes into merge, with no input change
        app.snapshot = replace(running, rows=(Row(id="M1", title="M1", state="awaiting_merge", text="ждёт слияния"),))
        ui.MainScreen.refresh_palette(screen)
        self.assertEqual(box.calls[-1], ("/", "merge"))
        # a hidden palette stays hidden (no needless redraw)
        box.display = False
        ui.MainScreen.refresh_palette(screen)
        self.assertEqual(len(box.calls), 2)

    def test_regression_a_displayed_run_error_maps_to_error(self):
        """Code-review finding: A3's «an error/blocked line shown -> error» must cover the run pane's own displayed
        operation error or blocked note (`app.run_note`), not only the plan-open error — the bar's job mapping reads
        the same `screen_slash_state`, so it inherits the fix. Reproduction: approve the fixture plan without
        starting, configure readiness with a failing check, focus the pane and press g; the pane shows
        `Не запущено: сначала исправьте отмеченное ниже.` while every row is still ready/waiting — `screen_slash_state`
        used to stay `idle`, so the palette offered idle commands and the bar reported no work. Interpretation: the
        note text is the only fact the screen holds for these verdicts (no separate status flag), so
        `blocked_note` recognises them by the prefix each of those paths writes and leaves ordinary informational
        notes (a pending stop, a watch summary, «… выполняется») out of the error state."""
        ready = Row(id="M1", title="M1", state="ready", text="готова")
        waiting = Row(id="M2", title="M2", state="waiting", text="ждёт")
        app = _FakeApp(Snapshot(project="P", branch="main", clean=True, version=1, status="proposed",
                                lines=(), roles=(), rows=(ready, waiting)))
        # a blocked start (readiness not clean) shows the not-started line while the rows are still ready/waiting
        app.run_note = "Not started: fix the items marked below first.\n! git"
        self.assertEqual(ui.screen_slash_state(app), "error")
        # a failed or unstopped operation and a lost observation are the same kind of shown error
        app.run_note = "Not done: unavailable"
        self.assertEqual(ui.screen_slash_state(app), "error")
        app.run_note = "Watch interrupted: connection lost [o] — continue."
        self.assertEqual(ui.screen_slash_state(app), "error")
        # a running stage keeps precedence over the shown error
        app.snapshot = replace(app.snapshot, rows=(Row(id="M1", title="M1", state="running", text="идёт"), waiting))
        self.assertEqual(ui.screen_slash_state(app), "running")
        # an ordinary informational note is not an error: the screen stays in its normal state
        app.snapshot = replace(app.snapshot, rows=(ready, waiting))
        app.run_note = "Stop of M1 requested; waiting for Zeroshot to confirm."
        self.assertEqual(ui.screen_slash_state(app), "plan_ready")

    def test_rs2_an_error_no_row_owns_never_shows_an_empty_stage(self):
        """RS2 C4: the slash state is `error` from a shown blocked-start note while every row is ready — no row is
        the error's stage, so the canvas title and the bar's job phrase must not start with a blank name
        (« · остановлен: ошибка»); with a failed row they still name it."""
        app = _FakeApp(Snapshot(project="P", branch="main", clean=True, version=1, status="approved", lines=(),
                                roles=(), rows=(Row(id="M1", title="Экспорт", state="ready", text="готов"),)))
        app.rows = lambda: app.snapshot.rows
        app.run_note = "Not started: fix the items marked below first."
        screen = _BarScreen(app)
        title = ui.canvas_title(app)
        self.assertEqual(ui.screen_slash_state(app), "error")
        self.assertEqual(title, strings.text("canvas.scheme_error_plain"))
        self.assertEqual(title, title.strip(" ·"))
        job, stage, elapsed = screen.bar_job()
        plain = bar_text("P", "main", job, stage, elapsed, (), 120).plain
        self.assertIn(strings.text("bar.error_plain"), plain)
        self.assertNotIn("·  ·", plain)
        self.assertFalse(plain.startswith("P · main ·  "))  # no blank name before the phrase
        app.snapshot = replace(app.snapshot, rows=(Row(id="M1", title="Экспорт", state="failed", text="сбой"),))
        self.assertEqual(ui.canvas_title(app), strings.text("canvas.scheme_error", stage="M1 Экспорт"))
        self.assertIn(strings.text("bar.stopped_error", stage="M1"),
                      bar_text("P", "main", *screen.bar_job(), (), 120).plain)

    def test_rs2_status_writes_one_chat_note_with_the_plan_the_stages_and_the_running_job(self):
        """RS2 C3: `/status` shows the «Сейчас» tab and writes the one-line summary on the chat's status line:
        «План r1 · утверждён · M1 влит» when idle after a merge, every milestone with its state word, and the
        running job's clock; without a plan the `note.no_plan` line."""
        rows = (Row(id="M1", title="a", state="integrated", text="влит"), Row(id="M2", title="b", state="ready", text="г"))
        app = _FakeApp(Snapshot(project="P", branch="main", clean=True, version=1, status="approved", lines=(),
                                roles=(), rows=rows[:1]))
        app.rows = lambda: app.snapshot.rows
        screen = _BarScreen(app)
        ui.COMMAND_ACTIONS["/status"](screen, "", None)
        self.assertEqual(app.chat_note, "Plan r1 · approved · M1 merged")
        self.assertEqual(screen.tabs, [ui.TAB_LIVE])
        app.snapshot = replace(app.snapshot, rows=(rows[0], Row(id="M2", title="b", state="running", text="идёт")),
                               flow={"elapsed": 65})
        ui.COMMAND_ACTIONS["/status"](screen, "", None)
        self.assertEqual(app.chat_note, "Plan r1 · approved · M1 merged · M2 running · "
                         + strings.text("live.job_timer", stage="M2", h="0:01:05"))
        app.snapshot = replace(app.snapshot, version=None, status=None, rows=())
        ui.COMMAND_ACTIONS["/status"](screen, "", None)
        self.assertEqual(app.chat_note, strings.text("note.no_plan"))

    def test_regression_a_displayed_planner_error_maps_to_error(self):
        """Acceptance finding 1 (A3: «an error/blocked line shown -> error»): a planner observation failure the
        pane displays must map to `error`, not `planning`. Reproduction on the prepared checkout: a detached/blocked
        snapshot (`status="observation_blocked"`) with `PlanView.kind == "observing"` and watching on, then the real
        `ZplanApp.watched` callback with an error — the pane then shows «Не выполнено: …» and stops watching, but
        `screen_slash_state` used to return `planning` (the observing plan view), so the bar reported planning and
        the palette used planning availability. The fix derives the displayed planner failure from `app.progress`.
        Interpretation: only the pane's newest line counts (a later successful re-observation appends its own
        phases over the failure, so a stale failure never pins the state), and only while not watching — an active
        observation stays «the planner running -> planning». A running stage keeps precedence, as before."""
        from terminal_planner.planning import PlanView
        observing = Snapshot(project="P", branch="main", clean=True, version=1, status="observation_blocked",
                             lines=(), roles=(),
                             plan=PlanView("observing", 1, "observation_blocked", (), ()))
        app = _FakeApp(observing)
        app.watching = True
        ui.ZplanApp.watched(app, None, "Zeroshot unavailable")  # the real observation-error callback
        self.assertIn("Not done: Zeroshot unavailable", list(app.progress))
        self.assertFalse(app.watching)
        self.assertEqual(ui.screen_slash_state(app), "error")
        # a running stage keeps precedence over the displayed planner failure
        app.snapshot = replace(app.snapshot, rows=(Row(id="M1", title="M1", state="running", text="идёт"),))
        self.assertEqual(ui.screen_slash_state(app), "running")
        # with no such line the normal observing revision is still `planning`
        app.snapshot = replace(app.snapshot, rows=())
        app.progress.clear()
        self.assertEqual(ui.screen_slash_state(app), "planning")
