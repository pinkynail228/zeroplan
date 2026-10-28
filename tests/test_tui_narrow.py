"""I7 (0.5.2): below 100 columns the main screen shows one pane at a time — «Conversation» first, the canvas tabs
beside it.

Two whole-app tests (A1+A2 in the first, A3 in the second), each a fresh shell through `tests/tui_support.py`; the
layout at 120x40 and its resize behaviour are the other runs' business (`tests/test_tui.py` LayoutTests).

Interpretations recorded here (both reviewers inspect this docstring):

- «Conversation» is not a `TabPane` (the chat pane is outside `#right`), so its state lives in one attribute
  (`MainScreen.chat_shown`) and the strip carries a label for it: the simpler of the two options the brief names —
  a plain, disabled `Tab` (`TAB_CHAT`) prepended to the built-in strip — is used, labelled with the existing
  `strings.text("pane.chat")` («Conversation»). The one-row strip of the lab is *not* redrawn; the built-in strip is
  reused with one extra label in front. The label is only mounted in narrow mode and is never selectable (disabled
  and without a pane), so clicking it cannot switch anything; the arrows are the cycle.
- The chat pane's border title in narrow mode is `strings.text("chat.title_narrow")` in every state (it replaces
  the planner/run title the wide pane shows), because the narrow title carries the «←→ tabs» hint the hidden
  canvas strip would otherwise give.
- Opening or re-activating a file/diff canvas tab (`add_view_tab`/`activate_view_tab`) brings the canvas into view
  in narrow mode; `show_chat()` brings the chat back. `show_chat()`/`show_canvas()` are no-ops in wide mode (both
  panes already show).
- Not addressed (spec gaps left for the orchestrator): the app's own status line (`status_note`'s `chat_note`) and
  the chat's operation refusals live above the chat, so while narrow mode shows the canvas they are off screen; the
  brief's non-goals and criteria do not name this case, so nothing is changed for it here.
"""

import unittest

from terminal_planner.tui import strings
from test_tui import ShellTest
from tui_support import HAVE_TEXTUAL, screen_text


@unittest.skipUnless(HAVE_TEXTUAL, "Textual недоступен: нужен ZPLAN_TEST_WHEELHOUSE с wheels textual 8.2.8")
class NarrowShellTests(ShellTest):
    def main(self):
        return next(s for s in self.app.screen_stack if type(s).__name__ == "MainScreen")

    def tab(self):
        return self.main().query_one("#right").active

    async def test_a1_a2_narrow_shows_one_pane_and_resizing_keeps_the_canvas_tab(self):
        """A1: at 80x24 the first frame shows the chat at full width and no canvas; `→`, `→` show «Scheme» then
        «Plan» at full width; `←`, `←` return to «Conversation». At 120x40 both panes show, as today. A2: resizing
        120x40 -> 80x24 -> 120x40 switches modes and keeps the canvas tab that was active (entering narrow shows
        the chat, leaving it restores the canvas the `#right` tab holds)."""
        from terminal_planner.tui import app as ui
        self.approve(running=True)  # a running attempt: «Scheme» is the start tab, so a resize has one to keep
        async with self.shell(size=(80, 24)) as pilot:
            await self.loaded(pilot)
            chat = self.app.query_one("#chat-pane")
            canvas = self.app.query_one("#right-column")
            panes = self.app.query_one("#panes")
            # A1: the first frame is the chat alone, full width; the canvas is hidden
            self.assertTrue(self.app.screen.narrow)
            self.assertTrue(chat.display)
            self.assertFalse(canvas.display)
            self.assertEqual(chat.region.width, panes.region.width)
            self.assertEqual(chat.border_title, strings.text("chat.title_narrow"))
            self.assertNotIn("Plan r1", screen_text(self.app))
            # A1: `→` shows «Scheme», `→` again «Plan», each full width
            await pilot.press("right")
            await pilot.pause()
            self.assertFalse(chat.display)
            self.assertTrue(canvas.display)
            self.assertEqual(self.tab(), ui.TAB_LIVE)
            self.assertEqual(canvas.region.width, panes.region.width)
            await pilot.press("right")
            await pilot.pause()
            self.assertEqual(self.tab(), ui.TAB_PLAN)
            self.assertIn("Plan r1", screen_text(self.app))
            # A1: `←`, `←` return to «Conversation» (Plan -> Scheme -> Conversation)
            await pilot.press("left", "left")
            await pilot.pause()
            self.assertTrue(chat.display)
            self.assertFalse(canvas.display)
            # A2: 120x40 shows both panes, as today
            await pilot.resize_terminal(120, 40)
            await pilot.pause(0.2)
            self.assertFalse(self.app.screen.narrow)
            self.assertTrue(chat.display)
            self.assertTrue(canvas.display)
            # A2: 120x40 -> 80x24 -> 120x40 switches modes and keeps the canvas tab that was active
            await pilot.press("right")  # wide: «Scheme» -> «Plan»
            await pilot.pause()
            self.assertEqual(self.tab(), ui.TAB_PLAN)
            await pilot.resize_terminal(80, 24)
            await pilot.pause(0.2)
            self.assertTrue(self.app.screen.narrow)
            self.assertTrue(chat.display)
            self.assertFalse(canvas.display)  # entering narrow shows the chat
            await pilot.resize_terminal(120, 40)
            await pilot.pause(0.2)
            self.assertFalse(self.app.screen.narrow)
            self.assertEqual(self.tab(), ui.TAB_PLAN)  # the canvas tab that was active is kept

    async def test_a3_show_chat_and_opening_a_file_switch_the_narrow_pane(self):
        """A3: `show_chat()` from the canvas at 80x24 shows the chat; `open_file_tab("README.md")` from the chat at
        80x24 shows the file tab (the canvas appears with the file's first lines).

        Regression (I7 repair, code review P2): an explicit switch to a canvas tab must reveal it in narrow mode
        before it takes the focus. `show_tab` used to set `#right.active` without showing the canvas, so `Tab` into
        the plan pane focused the invisible pane and `/status` switched to a hidden «Scheme». Interpretation: the
        one caller that must not reveal the canvas is `choose_tab`'s start choice (`reveal=False`) so A1's first
        frame stays the chat alone; every other caller reveals its destination.

        Regression (I7 repair, code review P2, focus): hiding the canvas under the focus must hand the focus to the
        chat input and remember that «Plan» owned it, so the pane's keys keep working across the switch. `show_chat`
        used to set `chat_shown` and hide the canvas without the hand-off `show_tab` makes when it leaves «Plan», so
        the focused plan pane blurred to `None` and the input stayed empty. Interpretation: the hand-off lives in
        `apply_narrow`, the one place that hides the canvas, so the arrows (`action_view`), `show_chat()` and a
        resize into narrow all get it; a modal on top owns the focus and is left alone."""
        from terminal_planner.tui import app as ui
        self.approve(running=False)
        (self.project / "README.md").write_text("# Title\nfirst line\nsecond line\n")
        async with self.shell(size=(80, 24)) as pilot:
            await self.loaded(pilot)
            chat = self.app.query_one("#chat-pane")
            canvas = self.app.query_one("#right-column")
            await pilot.press("right")  # leave «Conversation» for the canvas («Scheme»)
            await pilot.pause()
            self.assertFalse(chat.display)
            self.assertTrue(canvas.display)
            main = self.main()
            main.show_chat()  # A3: from the canvas, show_chat returns to «Conversation»
            await pilot.pause()
            self.assertTrue(chat.display)
            self.assertFalse(canvas.display)
            main.open_file_tab("README.md")  # A3: from the chat, a file tab shows the canvas
            await self.until(pilot, lambda: "1 # Title" in screen_text(self.app))
            self.assertFalse(chat.display)
            self.assertTrue(canvas.display)
            self.assertIn("README.md", screen_text(self.app))
            main.show_chat()  # back to «Conversation» for the two explicit canvas switches below
            await pilot.pause()
            self.assertTrue(chat.display)
            # Regression: `Tab` into the plan pane reveals the canvas it targets (C0c2/A3, docs/USER_FLOW.md)
            await pilot.press("tab")
            await pilot.pause()
            self.assertTrue(canvas.display)
            self.assertFalse(chat.display)
            self.assertEqual(getattr(self.app.focused, "id", None), "plan-pane")
            self.assertEqual(self.tab(), ui.TAB_PLAN)
            # Regression: `/status` from the chat input reveals the canvas it switches to («Scheme»)
            main.show_chat()
            await pilot.pause()
            self.app.query_one("#input").focus()
            await pilot.press("/", "s", "t", "a", "t", "u", "s")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            self.assertTrue(canvas.display)
            self.assertFalse(chat.display)
            self.assertEqual(self.tab(), ui.TAB_LIVE)
            # Regression: a canvas hidden under the focus (the narrow branch of `action_view`, C0c2/A3's «same
            # action_view» rule) hands the focus to the chat input; `a` then reaches the input instead of dying.
            main.show_chat()
            await pilot.pause()
            self.app.query_one("#input").focus()
            await pilot.press("tab")  # into the plan pane: reveals the canvas and shows «Plan»
            await pilot.pause()
            self.assertEqual(getattr(self.app.focused, "id", None), "plan-pane")
            self.assertTrue(canvas.display)
            await pilot.press("left", "left")  # «Plan» -> «Scheme» -> «Conversation»: hidden under the focus
            await pilot.pause()
            self.assertTrue(chat.display)
            self.assertFalse(canvas.display)
            self.assertEqual(getattr(self.app.focused, "id", None), "input")
            await pilot.press("a")
            await pilot.pause()
            self.assertEqual(self.app.query_one("#input").value, "a")
            await pilot.press("backspace")
            await pilot.pause()
            await pilot.press("right", "right")  # «Conversation» -> «Scheme» -> «Plan»: the remembered pane returns
            await pilot.pause()
            self.assertEqual(self.tab(), ui.TAB_PLAN)
            self.assertEqual(getattr(self.app.focused, "id", None), "plan-pane")
            # Regression (i9 repair, code review): the input now lives *inside* the chat pane, so leaving «Conversation»
            # for the canvas blurs it (Textual drops the focus of a widget whose ancestor stops displaying) — and
            # returning to «Conversation» must put the focus back where the reader types, so the next keystroke lands in
            # the input instead of dying on nothing.
            main.show_chat()
            await pilot.pause()
            self.assertTrue(chat.display)
            self.app.query_one("#input").focus()
            await pilot.press("right")  # «Conversation» -> «Scheme»: the chat pane, and the focused input in it, go away
            await pilot.pause()
            self.assertFalse(chat.display)
            self.assertIsNone(self.app.focused)
            await pilot.press("left")  # «Scheme» -> «Conversation»: the chat comes back, and the focus with it
            await pilot.pause()
            self.assertTrue(chat.display)
            self.assertEqual(getattr(self.app.focused, "id", None), "input")
            await pilot.press("a")
            await pilot.pause()
            self.assertEqual(self.app.query_one("#input").value, "a")
