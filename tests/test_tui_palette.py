"""W2 A1-A6: the `/` command palette (`terminal_planner.tui.palette`) — the rows a typed command lists and the
decision over the line the owner submitted.

One test per acceptance criterion: A1-A5 drive a minimal `App` that holds nothing but the widget (no project, no
controller, no engine, no socket — A6), A6 also scans the module's imports for anything outside drawing and
deciding. Every test runs with an isolated `XDG_CONFIG_HOME` and pinned locale variables, so the catalog texts the
rows show come from the test's own environment, never from the runner's preferences.

Interpretations recorded here (the worker's session summary never reaches the reviewers):

- The two result values are spelled after the task's own wording: `Submitted(command_name, argument)` and
  `Refused(note)`; `note` holds the finished text (the catalog's `strings.text` of the `slash.problem` id), because
  A4 speaks of "Refused with the `note.not_now` text", not of an id.
- The `{name}` the note ids ask for is `Parsed.name` — the command word as typed, cyrillic look-alikes and case
  included — because `slash`'s docstring says the note "can name what the user wrote"; passing the canonical name
  would rename the user's input.
- The name column and the padding are the lab's (`f"{cmd:<11}"`, `devtools/ui-lab/work.py`), so the descriptions
  start in one column; the name is bold and the description dim, as the task says (the lab's yellow is the lab's
  own ANSI theme and is not repeated in the widget's `DEFAULT_CSS`).
- `DEFAULT_CSS` carries the lab's `#palette` block (`height: auto`, a rounded yellow border, `padding: 0 1`, nowrap +
  ellipsis), with one deliberate change: `max-height: 9` instead of the lab's `8`. `max-height` counts the two border
  rows, so the lab's eight showed only six of A1's seven rows in a 100x30 Pilot; nine leaves room for all seven rows
  plus the border. "Docked above the input" is left to the integration run i2, which composes the widget as the
  prompt box's sibling (the lab's own order); the widget carries no `dock` rule of its own.
- The empty-list row is dim like a description; `note.palette_empty` carries no format values.
- The command rows are read off the widget's own content (`Static.content`, the Rich `Text` `show_for` set) for the
  text and styles, and off `render_line` for the rows the box actually draws: A1's "lists" is the observable list,
  so a row the box clips fails even though the content holds it.
- `show_for` requires a mounted widget, as every `Static.update` with a Rich renderable does in Textual 8.2.8
  (`visualize` asks the widget's app for its console); the task states no unmounted use, and the screen calls it
  from the input's change event, which fires only on a mounted screen. The tests here mount a bare `App` for it.
"""

import ast
import contextlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

# `tui_support` is imported first on purpose, for its side effect: importing it puts the offline wheelhouse
# (ZPLAN_TEST_WHEELHOUSE) on `sys.path` before the guarded imports below, so this module — the first one the task's
# DoD command loads — sees Textual and Rich there instead of skipping on a host that installs neither.
import tui_support  # noqa: F401
from tui_support import screen_lines

from terminal_planner.tui import slash, strings
from test_tui_live import LiveShell

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "terminal_planner" / "tui" / "palette.py"
MISSING_REASON = "Rich и Textual недоступны: нужен ZPLAN_TEST_WHEELHOUSE с wheels rich и textual"

try:
    from rich.cells import cell_len
    from rich.console import Console
    from textual.app import App, ComposeResult
    from terminal_planner.tui import app as ui
    from terminal_planner.tui import chat as chat_module, palette
except ImportError:  # pragma: no cover - the bare import scan of tests.test_toolchain covers this path
    palette = ui = None

HAVE_WIDGET = palette is not None

if HAVE_WIDGET:

    class PaletteApp(App):
        """The minimal test app of A5: one palette, no project, no controller, no other widget."""

        def compose(self) -> ComposeResult:
            yield palette.Palette(id="commands")


# A1's list spelled out, so the check does not just read `slash` back: the first seven commands a bare `/` lists in
# `idle`, in `slash.matches` order (`/help` is the eighth, cut by the seven-row cap; K1b: `/plan` acts in idle and leads).
IDLE_ROWS = ["/plan", "/run", "/diff", "/open", "/status", "/language", "/setup"]
BY_NAME = {command.name: command for command in slash.COMMANDS}


def listed(value, state):
    """The command names the palette must list for `value` in `state`: `slash`'s order, the acting ones only, at
    most seven — written here from the task, not read from `palette`."""
    return [command.name for command in slash.matches(value, state) if slash.available(command, state)][:7]


def row_names(rows):
    """The command word each row starts with (the descriptions are the rest of the row)."""
    return [row.split()[0] for row in rows]


class PaletteSourceTests(unittest.TestCase):
    """A6: the module draws and decides only — no project, no controller, no engine, no network."""

    def imported(self, path):
        """Every module name `path` imports: absolute dotted names, or the relative form (".", ".strings", ...)."""
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                found.add("." * node.level + (node.module or ""))
        return found

    def test_a6_the_module_and_these_tests_need_no_project_controller_or_network(self):
        """A6: `palette.py` imports only the frozen registry, the catalog, Rich's `Text` and Textual's `Static`;
        it opens nothing, spawns nothing and reaches no socket; and these tests import no project-, controller-,
        engine- or network-bearing module either."""
        self.assertEqual(self.imported(SOURCE), {"dataclasses", "rich.text", "textual.widgets", "."})

        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        calls = {node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                 for node in ast.walk(tree) if isinstance(node, ast.Call)}
        self.assertEqual(calls & {"open", "read_text", "read_bytes", "write_text", "write_bytes", "unlink", "mkdir",
                                  "system", "popen", "run", "check_output", "urlopen", "socket", "connect",
                                  "Popen", "call"}, set())
        self.assertEqual(calls & {"matches", "available", "parse", "problem", "text", "append", "update"},
                         {"matches", "available", "parse", "problem", "text", "append", "update"})

        mine = self.imported(Path(__file__).resolve())
        self.assertEqual(mine & {"terminal_planner.controller", "terminal_planner.runs", "terminal_planner.engine",
                                 "terminal_planner.cli", "subprocess", "socket", "urllib", "terminal_planner.setup"},
                         set())
        # these tests reach the module under test, the frozen registry, the catalog and the wheelhouse helper
        self.assertEqual(mine & {"terminal_planner.tui", "tui_support"}, {"terminal_planner.tui", "tui_support"})


@unittest.skipUnless(HAVE_WIDGET, MISSING_REASON)
class PaletteTests(unittest.IsolatedAsyncioTestCase):
    """A1-A5 of `terminal_planner.tui.palette`: the rows of `show_for` and the values of `submit`."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        environment = patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.root / "config"),
                                              "LC_ALL": "", "LC_MESSAGES": "", "LANG": ""})
        environment.start()
        self.addCleanup(environment.stop)
        offered = patch.object(strings, "OFFERED", strings.LANGUAGES)  # L1: these tests pin all three languages
        offered.start()
        self.addCleanup(offered.stop)

    @contextlib.asynccontextmanager
    async def shown(self, value, state, size=(100, 30)):
        """The widget of a bare app after `show_for(value, state)` and one pause."""
        app = PaletteApp()
        async with app.run_test(size=size) as pilot:
            widget = app.query_one(palette.Palette)
            widget.show_for(value, state)
            await pilot.pause()
            yield widget

    async def rows(self, value, state, size=(100, 30)):
        """What the palette lists for `value` in `state`, row by row."""
        async with self.shown(value, state, size) as widget:
            self.assertTrue(widget.display, "the palette hid itself for %r" % (value,))
            return widget.content.plain.splitlines()

    async def test_l1_slash_language_is_not_listed_while_one_language_is_offered(self):
        """L1/C3: with `OFFERED` back at `("ru",)` (the setUp patch is undone) a bare `/` in `idle` lists the
        first seven of the other commands, and `/lang` finds no row at all."""
        with patch.object(strings, "OFFERED", ("ru",)):
            rows = await self.rows("/", "idle")
            self.assertNotIn("/language", row_names(rows))
            every = [c.name for c in slash.matches("/", "idle") if slash.available(c, "idle")]
            self.assertEqual(row_names(rows), [name for name in every if name != "/language"][:7])
            async with self.shown("/lang", "idle") as widget:
                self.assertFalse(widget.found)
        async with self.shown("/lang", "idle") as widget:
            self.assertEqual([command.name for command in widget.found], ["/language"])

    async def test_a1_a_bare_slash_lists_the_first_seven_commands_idle_allows(self):
        """A1: `/` in `idle` lists exactly the first seven commands available there, in `slash.matches` order, each
        with the name in bold and its catalog description dimmed; no unavailable command appears."""
        async with self.shown("/", "idle") as widget:
            content, rows = widget.content, widget.content.plain.splitlines()
            visible = [widget.render_line(y).text for y in range(widget.size.height)]

        self.assertEqual(row_names(rows), IDLE_ROWS)
        self.assertEqual(IDLE_ROWS, listed("/", "idle"))
        self.assertEqual(len(rows), 7)
        for row, name in zip(rows, IDLE_ROWS):
            with self.subTest(row):
                self.assertTrue(row.startswith(name), row)
                self.assertIn(strings.text(BY_NAME[name].description_id), row)
        # no command that does not act in idle is listed, also not by a shared prefix
        for absent in ("/approve", "/decline", "/merge", "/stop"):
            self.assertNotIn(absent, row_names(rows))
        # the two styles: the name bold, the description dim, one pair per row; the highlighted first row (O3) is
        # drawn reversed, the second row is the plain pair
        styles = [str(span.style) for span in content.spans]
        self.assertEqual(styles[:4], ["bold reverse", "reverse", "bold", "dim"])
        self.assertEqual(len(content.spans), 2 * 7)
        # and the box really shows all seven rows: the border must not clip the last one (A1's observable list)
        self.assertEqual(row_names([line.rstrip() for line in visible]), IDLE_ROWS)

    async def test_a2_a_prefix_lists_only_what_acts_and_an_empty_list_shows_the_note_row(self):
        """A2: `/ap` in `plan_ready` lists /approve alone; the same prefix in `idle` (where /approve does not act)
        shows the one dim `note.palette_empty` row."""
        rows = await self.rows("/ap", "plan_ready")
        self.assertEqual(row_names(rows), ["/approve"])
        self.assertIn(strings.text("cmd.approve"), rows[0])

        async with self.shown("/ap", "idle") as widget:
            self.assertEqual(widget.content.plain.splitlines(), [strings.text("note.palette_empty")])
            self.assertEqual([str(span.style) for span in widget.content.spans], ["dim"])
        self.assertEqual(listed("/ap", "idle"), [])

    async def test_a3_a_line_that_is_not_a_command_hides_the_palette(self):
        """A3: `show_for` hides the palette for a message ("hello") and for an empty input, in any state, and shows
        it again for a command."""
        async with self.shown("/", "idle") as widget:
            self.assertTrue(widget.display)
            for value, state in (("hello", "idle"), ("", "planning")):
                with self.subTest("%r in %s" % (value, state)):
                    widget.show_for(value, state)
                    self.assertFalse(widget.display)
            widget.show_for("/", "merge")
            self.assertTrue(widget.display)
            self.assertEqual(row_names(widget.content.plain.splitlines()), listed("/", "merge")[:7])

    async def test_a4_submit_returns_the_command_the_refusal_text_or_none(self):
        """A4: `submit` -> `Submitted(name, argument)` when `slash.problem` is None, `Refused` with the catalog text
        of the problem id otherwise, and None for a line that is not a command; a pure function, no widget."""
        self.assertEqual(palette.submit("/open README.md", "idle"), palette.Submitted("/open", "README.md"))
        self.assertEqual(palette.submit("/plan ", "draft"), palette.Submitted("/plan", ""))
        self.assertEqual(palette.submit("/Plan", "draft"), palette.Submitted("/plan", ""))     # as `parse` reads it
        self.assertEqual(palette.submit("/merge", "idle"),
                         palette.Refused(strings.text("note.not_now", name="/merge")))
        self.assertEqual(palette.submit("/nope", "idle"),
                         palette.Refused(strings.text("note.unknown_command", name="/nope")))
        self.assertIsNone(palette.submit("hi", "idle"))
        self.assertIsNone(palette.submit("", "idle"))
        self.assertIsNone(palette.submit("   ", "idle"))
        # the other two reasons the catalog can give, and the word as typed in the note
        self.assertEqual(palette.submit("/open", "idle"),
                         palette.Refused(strings.text("note.needs_arg", name="/open")))
        self.assertEqual(palette.submit("/language xx", "idle"),
                         palette.Refused(strings.text("note.bad_language", name="/language")))
        self.assertEqual(palette.submit("/Nope", "idle"),
                         palette.Refused(strings.text("note.unknown_command", name="/Nope")))

    async def test_regression_the_box_shows_all_seven_rows_not_six(self):
        """Regression (A1): the accepted lab CSS `max-height: 8` counts the two border rows, so in a 100x30 Pilot the
        box drew only six of the seven rows and `/help` was absent from `render_line`. A1's "lists ... the first 7"
        is the observable list, so the box must render every row; the fix leaves room for `MAX_ROWS` rows plus the
        border, and this check reads the rows the box actually draws, not the stored content."""
        async with self.shown("/", "idle") as widget:
            visible = [widget.render_line(y).text for y in range(widget.size.height)]
        names = row_names([line.rstrip() for line in visible])
        self.assertEqual(names, IDLE_ROWS)
        self.assertIn("/setup", names)  # the last of the seven rows

    def test_regression_a_line_not_starting_with_slash_is_not_a_submission(self):
        """Regression (A4; task: "a line not starting with '/' -> None"): `slash.parse` strips leading whitespace, so
        delegating to it made `submit(" /open README.md", "idle")` return `Submitted(...)` (and `"\\t/status"` submit
        too) while `show_for` correctly hid the palette for the same raw input. The fix guards the raw prefix before
        parsing. Interpretation: the guard is the same raw `startswith("/")` `show_for` uses, so hiding and refusing
        agree — a command begins at the first character, and a whitespace-prefixed line is the owner's chat."""
        self.assertIsNone(palette.submit(" /open README.md", "idle"))
        self.assertIsNone(palette.submit("\t/status", "idle"))
        self.assertEqual(palette.submit("/open README.md", "idle"), palette.Submitted("/open", "README.md"))

    async def test_a5_at_40_columns_no_row_is_wider_than_the_widget(self):
        """A5: in a 40-column screen the palette stays inside it and every row it lists is drawn inside the widget,
        one row per command (a row never wraps)."""
        async with self.shown("/", "idle", (40, 20)) as widget:
            self.assertLessEqual(widget.region.right, 40)
            width = widget.size.width
            # how the widget itself wraps its rows at its own width (`Text.wrap` honours the text's `no_wrap`),
            # and the rows the widget actually draws
            lines = [str(line) for line in widget.content.wrap(Console(width=width, no_color=True), width)]
            drawn = [widget.render_line(y).text for y in range(widget.size.height)]
        self.assertEqual(len(lines), 7, "a row wrapped instead of being cut")
        for line in lines + drawn:
            self.assertLessEqual(cell_len(line), width, line)
        self.assertEqual(row_names([line.rstrip() for line in lines]), IDLE_ROWS)


    async def test_o3_the_highlight_starts_on_the_first_row_moves_and_wraps(self):
        """O3/C1 at the widget: the first row is highlighted by default (and is `picked()`); `move` walks down and
        wraps past the last row, walks up and wraps past the first, and a new value starts over on the first row. An
        empty list has nothing to pick."""
        async with self.shown("/", "idle") as widget:
            self.assertEqual(widget.picked().name, IDLE_ROWS[0])
            widget.move(1, "/", "idle")
            widget.move(1, "/", "idle")
            self.assertEqual(widget.picked().name, IDLE_ROWS[2])
            self.assertEqual(widget.content.spans[2 * 2].style, "bold reverse")  # the third row is the drawn one
            widget.move(-3, "/", "idle")
            self.assertEqual(widget.picked().name, IDLE_ROWS[-1])  # up from the first wraps to the last
            widget.move(1, "/", "idle")
            self.assertEqual(widget.picked().name, IDLE_ROWS[0])
            widget.move(1, "/", "idle")
            widget.show_for("/s", "idle")
            self.assertEqual(widget.picked().name, listed("/s", "idle")[0])
            widget.show_for("/zzz", "idle")
            self.assertIsNone(widget.picked())

    async def test_regression_o3_a_palette_opened_again_starts_on_the_first_row(self):
        """Regression (O3 review, C1): the highlight moved on a bare `/` came back when the palette was hidden (Esc,
        Backspace, Enter on the bare `/` all clear the input) and the same `/` was typed again; a hidden palette
        forgets it, so the reopened one starts on the first row."""
        async with self.shown("/", "idle") as widget:
            widget.move(1, "/", "idle")
            widget.move(1, "/", "idle")
            self.assertEqual(widget.picked().name, IDLE_ROWS[2])
            widget.show_for("", "idle")
            self.assertFalse(widget.display)
            widget.show_for("/", "idle")
            self.assertEqual(widget.picked().name, IDLE_ROWS[0])
            self.assertEqual(widget.content.spans[0].style, "bold reverse")

    async def test_regression_o3_hidden_commands_leave_the_palette_seven_rows(self):
        """Regression (O3 review): `RunAwarePalette` drops the commands the app would refuse (`/run`) and the palette
        still lists `MAX_ROWS` rows — the cut comes after that filter, so a bare `/` in idle keeps `/help`."""
        class HidingApp(App):
            def palette_hidden(self):
                return ("/run",)

            def compose(self):
                yield ui.RunAwarePalette(id="commands")

        app = HidingApp()
        async with app.run_test(size=(100, 30)) as pilot:
            widget = app.query_one(ui.RunAwarePalette)
            widget.show_for("/", "idle")
            await pilot.pause()
            names = row_names(widget.content.plain.splitlines())
        expected = [command.name for command in slash.matches("/", "idle") if slash.available(command, "idle")
                    and command.name != "/run"][:7]
        self.assertEqual(names, expected)
        self.assertEqual(len(names), 7)
        self.assertIn("/help", names)


@unittest.skipUnless(HAVE_WIDGET, MISSING_REASON)
class PaletteKeysTests(LiveShell):
    """O3 through the real shell: the keys that work the palette and the keys that must stay as they were. At most
    two whole-app tests.

    Interpretations: Tab completes only while the chat input has the focus and holds a command name or a prefix of one (no argument) — with
    an argument typed (`/open README.md`) completing would replace the owner's text, so Tab keeps its focus switch;
    Enter picks the highlighted row only for such a bare prefix (a full command name, with or without an argument,
    keeps today's path); the history keeps the lines the owner sent or ran (a refused line is not kept) and a recalled
    line is walked with Up/Down until the input is edited (a recalled command line is then not a palette pick)."""

    def box(self):
        return self.app.query_one("#palette", palette.Palette)

    def field(self):
        return self.app.query_one("#input")

    async def test_o3_c1_c2_c3_c5_arrows_pick_tab_completes_and_enter_runs_the_pick(self):
        """C1: `/` then Down twice highlights the third row, Up from the first wraps to the last. C2: `/op` + Tab
        fills `/open ` and the palette re-filters to it; Tab on a line with an argument keeps it and switches the
        focus. C3: `/hel` + Enter runs `/help` (the help opens); a full name with an argument keeps its path
        (`/open` with no file still says it needs one). C5: the bar names Tab and the arrows while the palette is shown
        and not when it is hidden."""
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            await pilot.press("/")
            await pilot.pause()
            names = row_names(self.box().content.plain.splitlines())
            self.assertGreaterEqual(len(names), 4)
            self.assertEqual(self.box().picked().name, names[0])
            await pilot.press("down", "down")
            self.assertEqual(self.box().picked().name, names[2])
            await pilot.press("up", "up", "up")
            self.assertEqual(self.box().picked().name, names[-1])
            bar = screen_lines(self.app)[-1]
            for key_id in ("bar.key_complete", "bar.key_pick"):
                self.assertIn(strings.text(key_id), bar)
            await self.type(pilot, "op")
            await pilot.press("tab")
            await pilot.pause()
            self.assertEqual(self.field().value, "/open ")
            self.assertEqual(row_names(self.box().content.plain.splitlines()), ["/open"])
            await self.type(pilot, "README.md")
            await pilot.press("tab")
            await pilot.pause()
            self.assertEqual(self.field().value, "/open README.md")  # nothing the owner typed is replaced
            self.assertIs(self.app.focused, self.app.query_one("#plan-pane"))
            await pilot.press("tab")
            self.field().value = ""
            await pilot.pause()
            self.assertFalse(self.box().display)
            self.assertNotIn(strings.text("bar.key_complete"), screen_lines(self.app)[-1])
            await self.type(pilot, "/hel")
            await pilot.press("enter")
            await self.until(pilot, lambda: type(self.app.screen).__name__ == "HelpScreen")
            await pilot.press("escape")
            await self.until(pilot, lambda: type(self.app.screen).__name__ == "MainScreen")
            await self.type(pilot, "/open")
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(self.field().value, "/open")  # the refusal of today's path: it needs a file
            await pilot.press("tab")  # a full name completes too (it only gains the space); the focus stays
            await pilot.pause()
            self.assertEqual(self.field().value, "/open ")
            self.assertIs(self.app.focused, self.field())

    async def test_o3_c4_without_the_palette_tab_switches_the_pane_and_up_down_recall_the_lines(self):
        """C4: with the palette hidden Tab moves the focus to the plan pane and back; after a message is sent and a
        command is run, Up in the empty input recalls them newest first, Down walks back and ends on empty. E1: the
        recall is the arrows' job once the chat has an entry (an empty chat's arrows pick the intro's examples), so
        the chat is given one first."""
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            self.app.chat = Mock(busy=False, turn_running=False, state=chat_module.ChatState(
                phase="ready", entries=(chat_module.owner_entry("раньше"),)))
            self.app.screen.render_chat()
            await pilot.pause()
            self.assertFalse(self.box().display)
            await pilot.press("tab")
            self.assertIs(self.app.focused, self.app.query_one("#plan-pane"))
            await pilot.press("tab")
            self.assertIs(self.app.focused, self.field())
            with patch.object(self.app, "send_chat", return_value=(True, "")):
                await self.type(pilot, "привет")
                await pilot.press("enter")
                await pilot.pause()
            self.assertEqual(self.field().value, "")
            await self.type(pilot, "/help")
            await pilot.press("enter")
            await self.until(pilot, lambda: type(self.app.screen).__name__ == "HelpScreen")
            await pilot.press("escape")
            await self.until(pilot, lambda: type(self.app.screen).__name__ == "MainScreen")
            await pilot.press("up")
            self.assertEqual(self.field().value, "/help")
            await pilot.press("up")
            self.assertEqual(self.field().value, "привет")
            await pilot.press("up")
            self.assertEqual(self.field().value, "привет")  # the oldest stays
            await pilot.press("down", "down")
            self.assertEqual(self.field().value, "")
            await pilot.press("down")
            self.assertEqual(self.field().value, "")


if __name__ == "__main__":
    unittest.main()
