"""S2a/S2b: the chat input is a `ChatInput(TextArea)` that behaves as the `Input` it replaced and takes several lines.

C1/C2 and M1/M3/M4 drive a bare `App` that holds nothing but the widget; C2 (the screen's up/down), C3 and C4, and
M2/M3/M4 on the screen, drive the real shell, two whole-app tests. Every test runs on the fixture shell's isolated
home. The byte filter for `ESC CR` (M1) is in tests/test_tui_theme.py.

Interpretations: `value =` with the text it already holds posts no `Changed` (as `Input.value` did), and the screen's
`close_scheme_cmd` relies on that; the up/down rule is "first or last visual row" (every key press while the text is
one row); "the value starts with `/`" is read on the text the paste would leave, so a paste of `/a\nb` into an empty
input keeps `/a`; a paste's `\r\n` and `\r` are new lines; an Enter on only spaces and new lines answers the card
and empties the input; the sends of the shell test are a stand-in `send_chat` that records the text (the chat's own
path is not under test).
"""
import unittest

import tui_support  # noqa: F401  (puts the offline wheelhouse on sys.path before the guarded imports)
from tui_support import screen_lines

from test_tui_live import LiveShell

try:
    import textual  # noqa: F401
except ImportError:  # pragma: no cover - tests.test_toolchain covers the bare import
    HAVE_WIDGET = False
else:
    HAVE_WIDGET = True
    from textual import events
    from textual.app import App
    from textual.binding import Binding
    from textual.widgets import Input, TextArea
    from unittest.mock import MagicMock, patch
    # Not guarded: only a missing Textual skips, a missing or broken `chat_input` module errors the tests.
    from terminal_planner.tui.chat_input import ChatInput

if HAVE_WIDGET:

    class InputApp(App):
        """The widget alone, with the screen's `up` key standing in for `pick` and every message recorded."""

        BINDINGS = [Binding("up", "pick(-1)"), Binding("down", "pick(1)")]

        def __init__(self):
            super().__init__()
            self.seen, self.picked = [], []

        def compose(self):
            yield ChatInput(placeholder="say", id="input")

        def action_pick(self, delta):
            self.picked.append(delta)

        def on_input_changed(self, event):
            self.seen.append(("changed", event.input.id, event.value))

        def on_input_submitted(self, event):
            self.seen.append(("submitted", event.input.id, event.value))
            event.input.value = ""


@unittest.skipUnless(HAVE_WIDGET, "Textual is unavailable: ZPLAN_TEST_WHEELHOUSE")
class ChatInputTests(unittest.IsolatedAsyncioTestCase):
    async def test_c1_c2_the_input_api_and_the_one_line_keys(self):
        """C1: typing posts `Changed` with `.input` and `.value`; Enter posts `Submitted` and never adds a newline;
        `value =` puts the cursor at the end, `insert_text_at_cursor` and `cursor_position` work. C2: up and down on
        a one-row text are not consumed, so the screen's `pick` gets them."""
        app = InputApp()
        async with app.run_test() as pilot:
            field = app.query_one("#input", ChatInput)
            self.assertIsInstance(field, TextArea)
            self.assertNotIsInstance(field, Input)
            await pilot.press("a", "b")
            self.assertEqual(app.seen[-1], ("changed", "input", "ab"))
            await pilot.press("enter")
            self.assertEqual(app.seen[-2:], [("submitted", "input", "ab"), ("changed", "input", "")])
            field.value = "xyz"
            self.assertEqual(field.cursor_position, 3)
            field.cursor_position = 1
            field.insert_text_at_cursor("-")
            self.assertEqual((field.value, field.cursor_position), ("x-yz", 2))
            field.value = ""
            await pilot.press("up", "down")
            self.assertEqual(app.picked, [-1, 1])
            await pilot.press("a")
            await pilot.press("up", "down")
            self.assertEqual(app.picked, [-1, 1, -1, 1])
            await pilot.press("enter")
            self.assertEqual(app.seen[-2:], [("submitted", "input", "a"), ("changed", "input", "")])

    async def test_m1_m3_m4_new_lines_arrows_pastes_and_commands(self):
        """M1: ctrl+j, alt+enter and shift+enter add a line, Enter sends the whole text. M3: up and down move the cursor
        inside the text (also between the wrapped rows of one line) and are the screen's `pick` on the first and last
        row. M4: a paste keeps its lines and sends nothing, a `/` text stays one line, `cursor_position` is the offset
        in the whole text."""
        app = InputApp()
        async with app.run_test(size=(40, 12)) as pilot:
            field = app.query_one("#input", ChatInput)
            await pilot.press("a", "ctrl+j", "b")
            self.assertEqual((field.value, field.cursor_position), ("a\nb", 3))
            await pilot.press("up")
            self.assertEqual((field.cursor_position, app.picked), (1, []))
            await pilot.press("up", "down", "down")
            self.assertEqual((field.cursor_position, app.picked), (3, [-1, 1]))
            await pilot.press("alt+enter", "shift+enter", "c", "enter")
            self.assertEqual(app.seen[-2:], [("submitted", "input", "a\nb\n\nc"), ("changed", "input", "")])
            field.value = "x" * 100
            await pilot.press("up")
            self.assertEqual(app.picked, [-1, 1])
            self.assertLess(field.cursor_position, 100)
            field.value = ""
            field.post_message(events.Paste("x\r\ny"))
            await pilot.pause()
            self.assertEqual((field.value, field.cursor_position, [seen for seen in app.seen if seen[0] == "submitted"][-1]),
                             ("x\ny", 3, ("submitted", "input", "a\nb\n\nc")))
            field.value = "/he"
            await pilot.press("ctrl+j", "alt+enter")
            field.post_message(events.Paste("l\np"))
            await pilot.pause()
            self.assertEqual(field.value, "/hel")
            field.value = ""
            field.post_message(events.Paste("/a\nb"))
            await pilot.pause()
            self.assertEqual(field.value, "/a")


@unittest.skipUnless(HAVE_WIDGET, "Textual is unavailable: ZPLAN_TEST_WHEELHOUSE")
class ChatInputShellTests(LiveShell):
    async def test_c2_c3_c4_the_screen_keys_the_look_and_the_forwarded_typing(self):
        """C2: the intro's examples are picked; with a history, up recalls the newest line and down walks back to empty; with `/` typed, down moves
        the palette row. C3: one row, no border, no line numbers, the placeholder shown. C4: a key typed on another
        screen is appended at the end of the text."""
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            screen = self.app.screen
            field = screen.query_one("#input", ChatInput)
            self.assertEqual((field.size.height, field.styles.border.top[0], field.show_line_numbers), (1, "", False))
            self.assertIn(field.placeholder, "\n".join(screen_lines(self.app)))
            await pilot.press("down")  # the intro of an empty chat is shown: the arrows pick its examples
            example = field.value
            self.assertTrue(example)
            await pilot.press("up", "up")
            self.assertNotEqual(field.value, example)
            field.value = ""
            screen.intro = None  # a chat with an entry shows no intro: the arrows recall the history
            screen.history = ("a", "b")
            await pilot.press("up")
            self.assertEqual(field.value, "b")
            await pilot.press("down")
            self.assertEqual(field.value, "")
            await self.type(pilot, "/")
            before = screen.query_one("#palette").picked().name
            await pilot.press("down")
            self.assertNotEqual(screen.query_one("#palette").picked().name, before)
            self.assertEqual(field.value, "/")
            field.value = "ab"
            self.app.type_in_chat(field, "x")
            await pilot.pause()
            self.assertEqual(field.value, "abx")


    async def test_m2_m3_m4_the_box_grows_to_eight_rows_and_the_screen_takes_the_ends(self):
        """M2: 1 row, then one per line up to 8, then the text scrolls with the cursor in view; the box stays at the
        pane's bottom; a send makes it one row; a resize rewraps; at 80x24 the bar still shows. M3: up on the first
        row of a recalled two-line entry moves the cursor, then recalls the entry before it. M4: Enter on spaces and
        new lines answers the open card and empties the input; a refused send keeps the text."""
        sent = []

        def send(value):
            sent.append(value)
            return not value.startswith("no"), ""
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            screen = self.app.screen
            screen.intro = None
            field, prompt, pane = (screen.query_one(name) for name in ("#input", "#prompt-box", "#chat-pane"))
            with patch.object(self.app, "send_chat", send):
                self.assertEqual(field.size.height, 1)
                heights = []
                for line in range(12):
                    await pilot.press("x", *(["ctrl+j"] if line < 11 else []))
                    heights.append(field.size.height)
                self.assertEqual(heights, [2, 3, 4, 5, 6, 7, 8, 8, 8, 8, 8, 8])  # a line and its new line
                row = field.wrapped_document.location_to_offset(field.cursor_location).y
                self.assertTrue(field.scroll_y <= row < field.scroll_y + 8 and field.scroll_y > 0)
                self.assertEqual(prompt.region.bottom, pane.region.bottom - 1)
                await pilot.press("enter")
                self.assertEqual((sent, field.size.height), (["\n".join("x" * 12)], 1))
                field.value = "word " * 60
                await pilot.pause()
                wide = field.size.height
                await pilot.resize_terminal(80, 24)
                await pilot.pause()
                self.assertEqual(self.app.query_one("#keys").region.bottom, self.app.size.height)
                await pilot.resize_terminal(50, 24)
                await pilot.pause()
                self.assertGreater(field.size.height, wide)
                field.value = ""
                screen.intro = None
                screen.history = ("a", "x\ny")
                await pilot.press("up")
                self.assertEqual((field.value, field.cursor_position), ("x\ny", 3))
                await pilot.press("up")
                self.assertEqual((field.value, field.cursor_position), ("x\ny", 1))
                await pilot.press("up")
                self.assertEqual(field.value, "a")
                pressed = []
                screen.keyed_card = lambda: MagicMock(press_choice=lambda: pressed.append(1))
                del sent[:]
                field.value = " "
                await pilot.press("ctrl+j", "enter")
                self.assertEqual((pressed, sent, field.value), ([1], [], ""))
                del screen.keyed_card
                field.value = "no"
                await pilot.press("ctrl+j", "x", "enter")
                self.assertEqual((sent, field.value), (["no\nx"], "no\nx"))
