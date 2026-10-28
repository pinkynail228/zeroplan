"""I11 (release 0.5.2 D1/D4): `/run` starts the next milestone from the chat, with the plan pane's [g] behind it.

R3 (the Plan tab names `/run`) is pure and pinned in tests/test_tui_look.py. Here:

- R1 + R4 (the one whole-app walk): a proposed fixture plan, the chat input focused all the way, no Tab and no
  letter key (the start confirmation is answered with Enter). The keys `/`, esc, ←/→ and enter work; `/approve` + Enter approves r1; `/run` + Enter opens the start
  confirmation [g] opens ("Start M1"); Enter answers «yes» (`EnterConfirmScreen`: Enter and the Russian-layout `y`) and gives the driver exactly one submission, for M1; ctrl+q ends the app.
- R2: `ZplanApp.action_run_next` on a stand-in app (no Textual widget runs): no row to start gives the one line
  «Not done: no stage is ready to start.» and no start branch; a busy slot hands the held-back ready row to
  `action_run_milestone`, whose own busy branch writes the existing busy note.

Regression (review): while a stage runs the screen is in the `running` state, so `/run` acts there too (slash.py):
the walk types `/run` after the start and gets the «Not done» line (no ready row is held back by the busy
slot in the fixture) instead of the «nothing now» refusal; the held-back-row busy note is the stand-in case above.

P1a C2 also covers a screen opened from a decision card's button: Esc returns the focus to that button, and a `/` that
reaches the main screen from any widget but the chat input moves to the input (`MainScreen.on_key`).
P1a (palette and input): the palette lists `/run` only when `ZplanApp.run_target` finds a row (the rule `/run` itself
acts on); a typed `/run` still reaches the refusal. A printable key on the run end screen is typed into the chat input
(`forward_to_chat`); a `/` left from the plan screen is covered in test_tui_planning.
Interpretations (P1a): «go to the chat input» keeps the run screen open with its button focus (tests/test_tui_polish.py
pins that no letter acts or closes it, and is outside this task's write-set), so the text waits in the input under the
modal; space stays the focused button's, so only non-space characters are forwarded. `/run` is hidden in every state
when no row has a [g] action, busy-slot rule included (`run_target`).

Interpretations: «the first row whose g_action is not None» is searched only when the selected row (the owner's
pick, else the service's focus) has no [g] action; a selected row with a [g] action wins, like on the pane. With a
busy slot every ready/failed/stopped row has no [g] action, so the busy note comes from the held-back row (the
selected one when it is such a row, else the first); the owner's selection is restored after the call. `/run` is
registered in `COMMAND_ACTIONS` from app.py because card_kinds.py is outside the write-set. The R4 ctrl+q is
pressed at the end of the walk, after the start."""

import unittest
from types import SimpleNamespace

from test_tui_milestones import MilestoneShell
from tui_support import HAVE_TEXTUAL, screen_text


def stand_in(rows, busy=None, selected=None):
    """The part of `ZplanApp` that `/run` touches, with the real selection and [g] decision and a recorder in place
    of the start branches."""
    from terminal_planner.tui.app import ZplanApp
    app = SimpleNamespace(snapshot=SimpleNamespace(rows=tuple(rows), busy=busy, focus=None), selected=selected,
                          chat_note="", started=[], changed=lambda: None)
    app.rows = lambda: app.snapshot.rows
    app.selection = lambda: ZplanApp.selection(app)
    app.g_action = lambda row: ZplanApp.g_action(app, row)
    app.run_target = lambda: ZplanApp.run_target(app)
    app.action_run_milestone = lambda: app.started.append(app.selected)
    return app


def row(id, state, startable=False):
    return SimpleNamespace(id=id, state=state, startable=startable)


@unittest.skipUnless(HAVE_TEXTUAL, "Textual unavailable: ZPLAN_TEST_WHEELHOUSE with the textual 8.2.8 wheels is needed")
class RunCommandTests(unittest.TestCase):
    def test_r2_nothing_to_start_is_one_line_and_a_busy_slot_keeps_the_busy_branch(self):
        from terminal_planner.tui.app import ZplanApp
        done = stand_in([row("M1", "merged"), row("M2", "waiting")], selected="M2")
        ZplanApp.action_run_next(done)
        self.assertEqual((done.chat_note, done.started), ("Not done: no stage is ready to start.", []))
        busy = stand_in([row("M1", "running"), row("M2", "ready", startable=True)], busy="M1", selected="M1")
        ZplanApp.action_run_next(busy)
        self.assertEqual((busy.started, busy.selected, busy.chat_note), (["M2"], "M1", ""))
        pick = stand_in([row("M1", "merged"), row("M2", "ready", startable=True), row("M3", "ready", startable=True)],
                        selected="M1")
        ZplanApp.action_run_next(pick)  # the selected row has no [g] action: the first one with it
        self.assertEqual((pick.started, pick.selected), (["M2"], "M1"))


@unittest.skipUnless(HAVE_TEXTUAL, "Textual unavailable: ZPLAN_TEST_WHEELHOUSE with the textual 8.2.8 wheels is needed")
class RunScreenKeyTests(unittest.TestCase):
    def test_p1a_c2_a_printable_key_on_the_run_screen_goes_to_the_chat_and_space_stays_the_buttons(self):
        """P1a C2: the end screen forwards a typed character (also a Cyrillic one) to the chat input instead of
        dropping it, staying open; space and non-printable keys are left to the focused button and the bindings."""
        from terminal_planner.tui.modals import RunScreen
        forwarded, stopped = [], []

        def key(character, printable=True):
            return SimpleNamespace(character=character, is_printable=printable, stop=lambda: stopped.append(character),
                                   prevent_default=lambda: None)
        screen = SimpleNamespace(app=SimpleNamespace(forward_to_chat=forwarded.append))
        for event in (key("a"), key("/"), key("ы"), key(" "), key(None, printable=False)):
            RunScreen.on_key(screen, event)
        self.assertEqual((forwarded, stopped), (["a", "/", "ы"], ["a", "/", "ы"]))


@unittest.skipUnless(HAVE_TEXTUAL, "Textual unavailable: ZPLAN_TEST_WHEELHOUSE with the textual 8.2.8 wheels is needed")
class ConfirmKeyLineTests(unittest.TestCase):
    def test_rs2_the_run_confirm_names_what_enter_does_and_the_others_keep_no(self):
        """RS2 C5: the `/run` confirmation (focus on «yes») has a key line that says Enter starts; the other
        confirmations (focus on «no») keep the neutral «press» line, and neither names the other's Enter."""
        from terminal_planner import catalog
        from terminal_planner.tui.app import EnterConfirmScreen, keys_bar
        from terminal_planner.tui.modals import ConfirmScreen
        starts = EnterConfirmScreen("Start M1?").key_bar(120)
        plain = keys_bar(ConfirmScreen.bar, 120)
        self.assertIn("[enter] " + catalog.label("tui_confirm_run.start"), starts)
        self.assertNotIn(catalog.label("tui_confirm.press"), starts)
        self.assertIn("[enter] " + catalog.label("tui_confirm.press"), plain)
        self.assertNotIn(catalog.label("tui_confirm_run.start"), plain)
        self.assertTrue(EnterConfirmScreen.default_yes and not ConfirmScreen.default_yes)


@unittest.skipUnless(HAVE_TEXTUAL, "Textual unavailable: ZPLAN_TEST_WHEELHOUSE with the textual 8.2.8 wheels is needed")
class RunCommandWhileRunning(unittest.TestCase):
    def test_regression_a_typed_run_while_a_stage_runs_reaches_the_busy_branch(self):
        """Review repair (R2): M1 running puts the screen in `running`; `/run` typed there is dispatched, not refused
        with «сейчас нечего», so the busy note of `action_run_milestone` stays reachable. The real `on_input_submitted`
        and the real `COMMAND_ACTIONS['/run']` run on the stand-ins of test_tui_commands."""
        from test_tui_commands import _FakeApp, _FakeInput, _FakePalette, _FakeScreen
        from terminal_planner.tui import app as ui
        snapshot = SimpleNamespace(rows=(row("M1", "running"), row("M2", "ready", startable=True)), busy="M1",
                                   plan=None, status="approved", version=1, focus=None)
        app = _FakeApp(snapshot)
        app.run_next = []
        app.action_run_next = lambda: app.run_next.append(True)
        field = _FakeInput("/run")
        screen = _FakeScreen(app, field, _FakePalette())
        self.assertEqual(ui.screen_slash_state(app), "running")
        ui.MainScreen.on_input_submitted(screen, type("Ev", (), {"value": "/run"})())
        self.assertEqual((app.run_next, field.value, app.chat_note), ([True], "", ""))


class RunCommandShell(MilestoneShell):
    async def test_p1a_c1_c2_the_palette_lists_run_only_when_it_acts_and_a_slash_after_esc_opens_it(self):
        """P1a C1 + C2 (the whole-app walk): a proposed, unapproved plan has no row to start, so `/` lists no `/run`
        and a typed `/run` still answers with the refusal; once approved `/run` is listed. After the details screen
        is closed with Esc the next `/st` opens the palette on `/status`."""
        from terminal_planner.authority import Authority
        with Authority(self.state, self.project, fixture_id="test") as authority:
            self.begin(authority)
            self.propose(authority)

        def listed():
            return self.app.screen.query_one("#palette").content.plain
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            # A screen opened from a card button hands the focus back to that button on Esc: the next `/` still opens
            # the palette (the key moves to the chat input), it is not dropped.
            main = self.app.screen
            await self.until(pilot, lambda: bool(main.card_widgets))
            await pilot.pause(0.3)
            from textual.widgets import Button
            decline = next(b for card in main.card_widgets.values() for b in card.query(Button) if b.command == "/decline")
            await pilot.click(decline)
            await self.until(pilot, lambda: type(self.app.screen).__name__ == "NoteScreen")
            await pilot.press("escape")
            await self.until(pilot, lambda: self.app.screen is main)
            self.assertIs(self.app.focused, decline)
            await pilot.press("/", "s", "t")
            await pilot.pause(0.3)
            self.assertEqual((main.query_one("#input").value, main.query_one("#palette").display), ("/st", True))
            self.assertIn("/status", listed())
            await pilot.press("escape")
            self.assertEqual(main.query_one("#input").value, "")
            await pilot.press("/")
            self.assertIn("/approve", listed())
            self.assertNotIn("/run", listed())
            await pilot.press("escape")
            await self.type(pilot, "/run\n")
            await self.shows(pilot, "no stage is ready to start")
            await self.type(pilot, "/approve\n")
            await self.until(pilot, lambda: any(r.startable for r in self.app.rows()))
            await pilot.press("/")
            self.assertIn("/run", listed())
            await pilot.press("escape")
            await self.command(pilot, "/details")
            await self.until(pilot, lambda: type(self.app.screen).__name__ == "TextScreen")
            await pilot.press("escape")
            await pilot.press("/", "s", "t")
            await self.until(pilot, lambda: type(self.app.screen).__name__ == "MainScreen")
            self.assertTrue(self.app.screen.query_one("#palette").display)
            self.assertIn("/status", listed())
            self.assertEqual(self.app.screen.query_one("#input").value, "/st")

    async def test_r1_r4_approve_then_run_from_the_chat_input_without_a_letter_key(self):
        from terminal_planner.authority import Authority
        with Authority(self.state, self.project, fixture_id="test") as authority:
            self.begin(authority)
            self.propose(authority)
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            self.assertEqual(self.app.focused.id, "input")
            await pilot.press("/")
            self.assertTrue(self.app.screen.query_one("#palette").display)
            await pilot.press("escape")
            self.assertFalse(self.app.screen.query_one("#palette").display)
            right = self.app.screen.query_one("#right")
            first = right.active
            await pilot.press("left")
            self.assertNotEqual(right.active, first)
            await pilot.press("right")
            self.assertEqual((right.active, self.app.focused.id), (first, "input"))
            await self.type(pilot, "/approve\n")
            await self.until(pilot, lambda: any(r.startable for r in self.app.rows()))
            await self.type(pilot, "/run\n")
            await self.shows(pilot, "Start M1")
            self.assertEqual(self.driver.sent, [])
            await pilot.press("enter")  # «yes» without a letter key (a Russian layout has no Latin `y`)
            await self.until(pilot, lambda: len(self.driver.sent) == 1)
            self.assertEqual(self.app.focused.id, "input", screen_text(self.app))
            self.assertEqual(len(self.driver.sent), 1)
            await self.until(pilot, lambda: self.app.run_last == "M1")
            await pilot.press("ctrl+q")
            await self.until(pilot, lambda: self.app._exit)


if __name__ == "__main__":
    unittest.main()
