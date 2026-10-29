"""S3a: zplan learns whether the terminal is light and sets the theme (terminal_planner/tui/theme.py).
S3b (L1-L3, last three tests): the light rules, the code theme, and `/theme`.

One smoke test per criterion: R1 the choice and the mount of both apps, R2 the OSC 11 filter, the query and the
answer's switch, R3 the read loop over a fake source and clock. R4 (`set_theme` keeps the language) is in
tests/test_tui_strings.py. Nothing here touches the runner's terminal: no driver starts, the source is a script.

Worker interpretations (the reviewers never see the worker's summary):

- `ZPLAN_THEME` set to an unknown value reads as auto (it does not fall through to `ui.json`); an empty one is unset.
- Luminance is 0.2126 R + 0.7152 G + 0.0722 B of the reply's channels, each scaled by its digit count (`ff` = `ffff`).
- A hold that ran out tells the parser its ESCAPE_DELAY has been waited (a lone Escape takes one delay, not two).
- A reply whose colour cannot be read is removed all the same and changes nothing.
- S3b L3: `/theme CODE` sets `process.chosen`, which beats `ZPLAN_THEME` for the rest of the run (the variable wins at
  start only); the sixth test runs the real command route on a stand-in screen, the status note is `note.theme`.
- S3b L1: "a darker ANSI colour" is `ansi_black` for titles and `ansi_yellow` for the wordmark; the field background
  is `ansi_white` under light (dark text on it). L2: open file/diff tabs keep the code theme they were drawn with.
"""

import asyncio
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import tui_support  # noqa: F401  (pins the UI language and the theme env before the app is imported)
from tui_support import HAVE_TEXTUAL

if HAVE_TEXTUAL:
    from textual import constants
    from terminal_planner import setup
    from terminal_planner.tui import strings, theme
    from terminal_planner.tui.start import StartApp

DELAY = constants.ESCAPE_DELAY if HAVE_TEXTUAL else 0.1
FF = "\x1b]11;rgb:ffff/ffff/ffff\x07"


class Source:
    """A scripted input: `(seconds passed, bytes or None)` per wait; the script's end stops the loop."""

    def __init__(self, script, stopped):
        self.script, self.stopped, self.now, self.data = list(script), stopped, 0.0, None

    def ready(self, timeout):
        if not self.script:
            self.stopped.set()
            return False
        seconds, self.data = self.script.pop(0)
        self.now += seconds
        return self.data is not None

    def read(self):
        return self.data.encode()

    def close(self):
        pass


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is unavailable: ZPLAN_TEST_WHEELHOUSE needs the textual 8.2.8 wheels")
class ThemeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        environ = patch.dict(os.environ, {"XDG_CONFIG_HOME": temp.name})
        environ.start()
        self.addCleanup(environ.stop)
        process = patch.object(theme, "process", theme.Process())
        process.start()
        self.addCleanup(process.stop)

    def env(self, **values):
        for name in ("ZPLAN_THEME", "COLORFGBG", "SSH_CONNECTION"):
            os.environ.pop(name, None)
        os.environ.update(values)

    def read(self, script):
        """The keys and the answers the read loop gives for `script`, on a fake clock."""
        import threading
        stopped, keys, found = threading.Event(), [], []
        source = Source(script, stopped)
        with patch("textual._parser.get_time", lambda: source.now):
            theme.read_input(source, stopped, lambda event: keys.append(event.key), found.append, clock=lambda: source.now)
        return keys, found

    def test_r1_the_choice_and_both_apps_mount_with_it(self):
        """R1: ZPLAN_THEME beats ui.json beats auto; other values are auto; `ZPLAN_THEME=light` with a dark `ui.json`
        mounts both apps `ansi-light` (the main app's `on_mount` runs on a stand-in self)."""
        from terminal_planner.tui.app import ZplanApp
        self.env()
        self.assertEqual(theme.theme_name(), "ansi-dark")
        self.env(COLORFGBG="0;15")
        self.assertEqual(theme.theme_name(), "ansi-light")
        self.env(COLORFGBG="15;0")
        self.assertEqual(theme.theme_name(), "ansi-dark")
        self.env(COLORFGBG="0;7")
        self.assertEqual(theme.theme_name(), "ansi-light")
        strings.set_theme("dark")
        self.assertEqual(theme.theme_name(), "ansi-dark")
        self.env(ZPLAN_THEME="bogus", COLORFGBG="0;15")
        self.assertEqual(theme.choice(), "auto")
        strings.set_theme("dark")
        self.env(ZPLAN_THEME="light")
        self.assertEqual(theme.choice(), "light")
        stand_in = MagicMock()
        with patch("terminal_planner.tui.app.asyncio.get_running_loop"):
            ZplanApp.on_mount(stand_in)
        self.assertEqual(stand_in.theme, "ansi-light")
        app = StartApp(tempfile.gettempdir())

        async def mount():
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                return app.theme
        self.assertEqual(asyncio.run(mount()), "ansi-light")

    def test_r2_the_reply_is_cut_out_and_read_and_asked_once(self):
        """R2: the reply leaves the input at any split (BEL or ST), light when luminance > 0.5; the query goes out
        once per process and not over SSH; the answer switches the theme only under auto."""
        state = theme.IDLE
        light = []
        for chunk in ("a", "\x1b]11;rgb:ffff/", "ffff/ffff\x07b"):
            state, output, answer = theme.remove_reply(state, chunk, 0.0)
            light.append((output, answer))
        self.assertEqual(light, [("a", None), ("", None), ("b", True)])
        self.assertEqual(theme.remove_reply(theme.IDLE, "\x1b]11;rgb:00/00/00\x1b\\\x1b]", 0.0)[1:], ("", False))
        self.assertEqual(theme.remove_reply(theme.IDLE, "\x1b]11;rgb:80/80/80\x07", 0.0)[1:], ("", True))
        self.assertEqual(theme.remove_reply(theme.IDLE, "\x1b]11;nonsense\x07z", 0.0)[1:], ("z", None))
        driver = object.__new__(theme.Driver)
        driver._key_thread, driver.input_tty, driver.write, driver.flush = object(), True, MagicMock(), MagicMock()
        self.env()
        with patch.object(theme.LinuxDriver, "start_application_mode"):
            driver.start_application_mode()
            driver.start_application_mode()
            driver.write.assert_called_once_with("\x1b]11;?\x1b\\")
            theme.process.asked = False
            self.env(SSH_CONNECTION="1 2 3 4")
            driver.start_application_mode()
            driver.write.assert_called_once()
        driver._app, driver._loop = MagicMock(), MagicMock(call_soon_threadsafe=lambda call, *args: call(*args))
        for chosen, expected in (("auto", "ansi-light"), ("dark", "ansi-dark")):
            driver._app.theme = "ansi-dark"
            self.env(ZPLAN_THEME=chosen)
            driver.found(True)
            self.assertEqual(driver._app.theme, expected)

    def test_r3_the_read_loop_holds_only_what_may_be_a_reply(self):
        """R3: plain input passes in order; a lone ESC is Escape after one ESCAPE_DELAY, `ESC [ A` is up; a reply
        split across reads is cut out; a reply that stalls is dropped and never eats the key after it; `ESC CR` is
        alt+enter (S2b), also when the two come in separate reads."""
        self.assertEqual(self.read([(0, "x")]), (["x"], []))
        self.assertEqual(self.read([(0, "\x1b"), (DELAY, None)])[0], ["escape"])
        self.assertEqual(self.read([(0, "\x1b[A")])[0], ["up"])
        self.assertEqual(self.read([(0, "ab\x1b\rcd\r")])[0], ["a", "b", "alt+enter", "c", "d", "enter"])
        self.assertEqual(self.read([(0, "a\x1b"), (0.01, "\rb")])[0], ["a", "alt+enter", "b"])
        self.assertEqual(self.read([(0, "a"), (0, FF[:8]), (0.01, FF[8:] + "b")]), (["a", "b"], [True]))
        theme.process.state = theme.IDLE
        self.assertEqual(self.read([(0, "\x1b]11;rgb:ff"), (DELAY, "q")])[0], ["q"])
        self.assertEqual(theme.process.state, theme.IDLE)

    def test_l1_the_light_rules_change_what_assumed_a_dark_terminal(self):
        """L1: under `ansi-light` the owner body is the default foreground and the pane/card titles are black, the
        start wordmark and field are darker; under `ansi-dark` every value is what it was."""
        from textual.app import App
        from textual.color import Color
        from textual.containers import Vertical
        from textual.widgets import Static
        from terminal_planner.tui import activity, cards

        class Lab(App):
            CSS_PATH = str(Path(cards.__file__).with_name("zplan.tcss"))

            def compose(self):
                with Vertical(id="chat"):
                    with Vertical(classes="msg owner"):
                        yield Static("x", classes="body")
                yield Vertical(id="chat-pane")
                yield activity.Activity(id="activity")

        async def colours(app, name):
            async with app.run_test(size=(80, 24)) as pilot:
                app.theme = name
                await pilot.pause()
                return (app.query_one(".body").styles.color, app.query_one("#chat-pane").styles.border_title_color,
                        app.query_one("#activity").styles.border_title_color)
        parse = Color.parse
        self.assertEqual(asyncio.run(colours(Lab(), "ansi-dark")),
                         (parse("ansi_bright_white"), parse("ansi_white"), parse("ansi_white")))
        self.assertEqual(asyncio.run(colours(Lab(), "ansi-light")),
                         (parse("ansi_default"), parse("ansi_black"), parse("ansi_black")))
        self.assertIn("#wordmark:light", StartApp.CSS)
        self.assertIn("Card:light", cards.Card.DEFAULT_CSS)

    def test_l2_code_follows_the_apps_theme_and_chat_bodies_redraw(self):
        """L2: an architect reply's code theme is `ansi_light` under `ansi-light`, else `ansi_dark`; a mounted entry
        redraws when the theme changes; the viewer takes the same name."""
        from rich.text import Text
        from textual.app import App
        from terminal_planner.tui import app as app_module, viewer
        blocks = (("text", "```py\nx = 1\n```"),)
        reply = lambda code: app_module.message_body("architect", blocks, code).columns[1]._cells[0].renderables[0]
        self.assertEqual((reply("ansi_light").code_theme, reply("ansi_dark").code_theme), ("ansi_light", "ansi_dark"))
        self.assertEqual(theme.code_theme("ansi-light"), "ansi_light")
        self.assertEqual(theme.code_theme("ansi-dark"), "ansi_dark")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "a.py")
            path.write_text("x = 1\n")
            styles = lambda view: view._theme.style_map
            self.assertEqual(styles(viewer.file_view(path)), styles(viewer.file_view(path, code="ansi_dark")))
            self.assertNotEqual(styles(viewer.file_view(path, code="ansi_light")), styles(viewer.file_view(path)))

        class Lab(App):
            def compose(self):
                yield app_module.ChatMessage(app_module.Shown("", blocks), "architect")

        async def draw():
            app, seen = Lab(), []
            with patch.object(app_module, "message_body", lambda role, blocks, code="ansi_dark": seen.append(code) or Text("x")):
                async with app.run_test() as pilot:
                    app.theme = "ansi-dark"
                    await pilot.pause()
                    app.theme = "ansi-light"
                    await pilot.pause()
            return seen
        seen = asyncio.run(draw())
        self.assertEqual((seen[0], seen[-1]), ("ansi_dark", "ansi_light"))

    def test_l3_theme_command_stores_and_applies_the_choice(self):
        """L3: `/theme` is the last command, takes auto|dark|light, stores the choice (language kept) and applies it
        now; bare it names the choice; another value is a note and stores nothing; the choice beats `ZPLAN_THEME` and
        a late terminal answer after `dark` or `light`."""
        from terminal_planner.tui import card_kinds, slash
        from terminal_planner.tui.app import MainScreen
        self.assertEqual(slash.COMMANDS[-1].name, "/theme")
        self.assertIsNone(slash.problem(slash.parse("/theme light"), "idle"))
        self.assertEqual(slash.problem(slash.parse("/theme blue"), "idle"), "note.bad_theme")
        strings.set_language("en")
        self.env(ZPLAN_THEME="dark")
        screen = MagicMock()
        screen.app.theme = "ansi-dark"
        screen.choose_theme = lambda code: MainScreen.choose_theme(screen, code)
        run = card_kinds.COMMAND_ACTIONS["/theme"]
        run(screen, "light", None)
        self.assertEqual((screen.app.theme, strings.stored_theme(), strings.language()), ("ansi-light", "light", "en"))
        theme.process.light = False  # a late terminal answer
        theme.apply(screen.app)
        self.assertEqual(screen.app.theme, "ansi-light")
        run(screen, "", None)
        screen.status_note.assert_called_with(strings.text("note.theme", name="light"))
        run(screen, "auto", None)
        theme.process.light = True
        run(screen, "", None)  # T2: auto names the theme in effect
        screen.status_note.assert_called_with(strings.text("note.theme", name="auto (light)"))
        self.assertEqual((screen.app.theme, strings.stored_theme()), ("ansi-dark", "auto"))
        theme.process.light = True
        theme.apply(screen.app)
        self.assertEqual(screen.app.theme, "ansi-light")


if __name__ == "__main__":
    unittest.main()
