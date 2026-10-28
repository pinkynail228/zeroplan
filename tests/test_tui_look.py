"""i9-look: the main screen takes the approved lab look (`devtools/ui-lab/work.py` + `work.tcss`).

The logo and the header are gone, the panes begin at row 0, the input is the lab's `#prompt-box` at the bottom of
the chat pane (the `/` palette opens straight above it, inside the same pane), the canvas tabs read «Scheme»/
«Plan», the chat entries stand behind a time line (0.6.3 V2: no author line) and the whole screen paints with the
terminal's own ANSI palette (`ansi_color=True`, theme `ansi-dark`).

One smoke check per acceptance criterion A1..A5, at most two of them through the whole app: A1/A2 (the frame and
the input) and A3/A4/A5 (the colours, the titles and the time lines) each read the running screen once, and the
stylesheet and card rules (A3) and the stored-time rule (A5) are also checked without an app, from the source and the
pure chat module the screen is built from.

Interpretations (recorded here because the worker's summary never reaches the reviewers):

* The lab's fixture project name `notes` is an example, not a constant: the bar and the canvas frame take the
  *selected* project's own name and branch, so A1/A4 read `<project> · <branch> · nothing runs · ←→ tabs ·
  / commands · ctrl+q quit` and `<project> · nothing runs`. The bar's groups are separated by the ` · ` the
  criterion spells (`activity.GAP`), `bar.continue` included; `LabBarTests` asserts the exact idle string.
* A1 `Row 0 is the top border of the panes`: both boxes start at row 0 — the chat pane's own and the canvas frame
  (`#right`, the `TabbedContent` whose border wraps the tab strip, the lab's `#flow-pane` around its `Tabs`), whose
  first content row is the strip (`Scheme  Plan`). Nothing (no logo, no header) sits above them.
* A3: the cards' colours (`ansi_magenta`; `ansi_red` on alarm; a done card is a borderless row since 0.6.3 S1) live in `cards.py`'s
  `DEFAULT_CSS`, which this task leaves untouched, so they are checked at that source; the panes', the prompt
  box's and the architect message's rules are read from `zplan.tcss` and, for the chat pane, the canvas frame and
  the prompt, as the renderer resolves them (`widget.styles.border`, its `Color.ansi` slot).
* A5 `from the transcript ts`: a stored row's time stands in a time line above the first entry and after a gap
  (0.6.3 V2). The optimistic owner line the pane posts before the store row exists (`chat.owner_entry`) has no stored
  `ts` yet and no time line, and while the turn runs the line is stamped from the row the turn wrote
  (`chat._stamp_owner_line`): the check here sends a message through a gated turn and reads the new `HH:MM` time
  line off the running screen, with the clock the store's own row carries.
* `README.md`'s own description of the shell used to open with «a logo, the header `project · branch ·
  readiness`»; the same paragraph is updated with this change (no logo, no header row, the input inside the chat
  pane), because it is a live document and would otherwise describe a screen the app no longer draws.
"""

import ast
import contextlib
import os
import re
import time
import unittest
from datetime import date
from pathlib import Path

import tui_support  # noqa: F401  (pins the UI language to ru before the app is imported, like the other shells)
from terminal_planner import catalog
from terminal_planner.tui import chat as chat_module
from terminal_planner.tui import strings
from tui_support import HAVE_TEXTUAL, screen_lines, screen_text
from test_tui_chat import OPENING, ChatShell

TEXTUAL_REASON = "Textual is unavailable: ZPLAN_TEST_WHEELHOUSE with textual 8.2.8 wheels is needed"

ROOT = Path(__file__).resolve().parents[1]
TUI = ROOT / "terminal_planner" / "tui"


def ansi(edge):
    """The ANSI slot of one resolved border edge (`styles.border.top`): 3 yellow, 8 bright black, 5 magenta, …."""
    return edge[1].ansi


class LabStyleTests(unittest.TestCase):
    """A1/A3 from the source the screen is built from: the logo/header rules are gone and the ANSI rules the look
    is made of are the lab's. No Textual, no app — the stylesheet and the widgets' own `DEFAULT_CSS`."""

    def source(self, name):
        return (TUI / name).read_text(encoding="utf-8")

    def test_a1_the_logo_and_the_header_are_gone(self):
        css = self.source("zplan.tcss")
        self.assertNotIn("#logo", css)
        self.assertNotIn("#header", css)
        app_source = self.source("app.py")
        self.assertNotIn('id="logo"', app_source)
        self.assertNotIn('id="header"', app_source)
        self.assertNotIn("LOGO", app_source)  # the logo sizing helpers went with the logo

    def test_a3_the_pane_prompt_registry_and_message_rules_are_the_labs_ansi_ones(self):
        css = self.source("zplan.tcss")
        for rule in ("#chat-pane {\n    width: 1fr;\n    border: round ansi_bright_black;",
                     "#chat-pane:focus-within {\n    border: round ansi_yellow;",
                     "#right {\n    width: 1fr;\n    height: 1fr;\n    border: round ansi_bright_black;",
                     "#right:focus-within {\n    border: round ansi_yellow;",
                     "#prompt-box {\n    height: 3;\n    border: round ansi_bright_black;",
                     "#prompt-box:focus-within {\n    border: round ansi_yellow;",
                     "#chevron {\n    width: 3;\n    padding-left: 1;\n    color: ansi_yellow;",
                     "#input {\n    border: none;",
                     "#chat .msg.owner > .body {\n    border-left: outer ansi_yellow;"):
            self.assertIn(rule, css)
        # the canvas frame is the one box around the tab panes: the panes inside carry no border of their own
        self.assertNotIn("#live-pane {\n    border:", css)
        self.assertNotIn("#plan-pane {\n    height: 1fr;\n    border:", css)
        cards = self.source("cards.py")
        self.assertIn("border: round ansi_magenta;", cards)                 # a decision card
        self.assertIn("Card.alarm { border: round ansi_red; }", cards)      # red on an alarm


class LabTitlesTests(unittest.TestCase):
    """A4 without an app: the catalog words the pane titles and the tab labels are drawn from are the lab's."""

    def test_a4_the_titles_and_the_tab_labels_are_the_labs(self):
        self.assertEqual(strings.CATALOG["chat.title"]["en"], "Conversation with the architect")
        self.assertEqual(strings.CATALOG["pane.flow"]["en"], "Scheme")
        self.assertEqual(strings.CATALOG["pane.plan"]["en"], "Plan")
        self.assertEqual(strings.CATALOG["pane.activity"]["en"], "What's happening")
        self.assertEqual(strings.CATALOG["canvas.scheme_running"]["en"], "{stage} · running")
        self.assertEqual(strings.CATALOG["bar.idle"]["en"], "nothing runs")


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class LabBarTests(unittest.TestCase):
    """A1 without a screen: the whole idle bottom bar reads exactly as the criterion spells it (F1)."""

    def test_a1_the_idle_bar_is_the_labs_exact_text(self):
        from terminal_planner.tui.activity import bar_text
        from terminal_planner.tui.app import BAR_KEYS_IDLE
        self.assertEqual(bar_text("notes", "main", None, "", None, BAR_KEYS_IDLE, 118).plain,
                         "notes · main · nothing runs · ←→ tabs · / commands · ctrl+q quit")
        running = bar_text("notes", "main", "planning", "M2", 65, BAR_KEYS_IDLE, 200).plain
        self.assertTrue(running.endswith(" · " + strings.text("bar.continue")), running)  # the same separator


@contextlib.contextmanager
def zone(name):
    """The process time zone set to `name` (`TZ` + `time.tzset()`) and restored on exit."""
    before = os.environ.get("TZ")
    os.environ["TZ"] = name
    time.tzset()
    try:
        yield
    finally:
        if before is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = before
        time.tzset()


class LabStampTests(unittest.TestCase):
    """A5 without an app: the stored `ts` is read in the local zone (P2a) by the time lines and the card footers."""

    def test_p2a_a_utc_stamp_is_shown_in_the_local_zone_and_a_zoneless_one_as_stored(self):
        """P2a/C1 smoke: the chat's time line and the card footer's (`stamp_hm`) read the same local clock; a `ts`
        without `Z` keeps the stored text. Interpretation: a `Z` stamp that is not a full ISO time keeps its stored
        HH:MM (card footers) and names no time to a time line."""
        from terminal_planner.tui import card_kinds
        with zone("Europe/Moscow"):
            self.assertEqual(chat_module.stamp_at("2026-10-26T16:20:05Z"), "19:20")
            self.assertEqual(card_kinds.stamp_hm("2026-10-26T16:20:05Z"), "19:20")
            entry = chat_module.entries_of([{"role": "owner", "text": "вопрос", "ts": "2026-10-26T16:20:05Z"}])[0]
            self.assertEqual(chat_module.time_labels([entry], today=date(2026, 10, 26)), ["19:20"])
            self.assertEqual(chat_module.stamp_at("2026-10-26T16:20:05+05:00"), "16:20")
            self.assertEqual(chat_module.stamp_at("2026-10-26 16:20:05"), "16:20")
            self.assertEqual(chat_module.stamp_at("xx16:20Z"), "")
            self.assertIsNone(chat_module.moment("xx16:20Z"))
        with zone("UTC"):
            self.assertEqual(chat_module.stamp_at("2026-10-24T21:01:00Z"), "21:01")
        self.assertEqual(chat_module.stamp_at("no time here"), "")


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class LabFrameTests(ChatShell):
    """A1/A2 through the real shell at 120x40: the frame and the input live where the lab puts them."""

    async def test_a1_a2_the_frame_and_the_input_are_the_labs(self):
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            app = self.app
            # A1: no logo, no header; both panes' frames begin at row 0, the canvas tabs riding the canvas frame's
            # first content row (the frame's border wraps the strip, the lab's `#flow-pane` around its `Tabs`)
            self.assertEqual(len(app.query("#logo")), 0)
            self.assertEqual(len(app.query("#header")), 0)
            rows = screen_lines(app)
            self.assertTrue(rows[0].startswith("╭"), rows[0])  # row 0 is a pane's top border, nothing above it
            canvas_frame = app.query_one("#right")
            chat_frame = app.query_one("#chat-pane")
            self.assertEqual((chat_frame.region.y, canvas_frame.region.y), (0, 0))  # both borders on row 0
            self.assertEqual(canvas_frame.region.right, app.size.width)  # the canvas frame closes the row
            self.assertNotIn(strings.text("pane.flow"), rows[0])  # the tabs ride inside the frame, not on row 0
            self.assertIn(strings.text("pane.flow"), rows[1])
            self.assertIn(strings.text("pane.plan"), rows[1])
            # A1: the bottom bar carries the project · branch · job · keys, and nothing else does
            project, branch = app.snapshot.project, app.snapshot.branch
            bar = app.query_one("#keys").render().plain
            # the project, the branch, the idle job and the three idle key hints, the ` · ` separator A1 spells
            # between every group (the `Bar`'s own spelling of `bar.key_*`)
            expected = "%s · %s · %s · ←→ tabs · / commands · ctrl+q quit" % (
                project, branch, strings.text("bar.idle"))
            self.assertTrue(bar.startswith(expected), bar)  # ... then the dim `model/effort` tail (C2)
            # A4 (idle half): the canvas frame names the idle project, the chat keeps the lab's one title
            self.assertEqual(canvas_frame.border_title, "%s · %s" % (project, strings.text("bar.idle")))
            self.assertEqual(app.query_one("#chat-pane").border_title, strings.text("chat.title"))
            # A2: the input is inside the chat pane (the wide column, V6), at its bottom, as the lab's prompt box
            pane = app.query_one("#chat-pane")
            self.assertAlmostEqual(pane.region.width, app.size.width - app.size.width * 0.40, delta=1)
            prompt = app.query_one("#prompt-box")
            field = app.query_one("#input")
            self.assertIn("chat-pane", [getattr(node, "id", None) for node in field.ancestors])
            self.assertGreater(field.region.y, app.query_one("#chat").region.y)  # below the conversation
            self.assertLessEqual(prompt.region.bottom, pane.region.bottom)       # hanging at the pane's bottom
            self.assertEqual(field.placeholder, strings.text("chat.placeholder"))
            self.assertIn("›", screen_text(app))                                 # the lab's chevron is drawn
            # A2: `/` opens the palette straight above the input, inside the same pane
            await pilot.press("/")
            await pilot.pause()
            palette = app.query_one("#palette")
            self.assertTrue(palette.display)
            self.assertIn("chat-pane", [getattr(node, "id", None) for node in palette.ancestors])
            self.assertEqual(palette.region.bottom, prompt.region.y)  # its last row is the prompt box's first


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class LabLookTests(ChatShell):
    """A3/A4/A5 through the real shell at 120x40: the ANSI colours, the titles and the time lines on a running
    stage, over a transcript read back from the store, and the clock the running turn's own line takes from the row
    that turn writes.

    A3/A4 interpretation: the canvas frame — the box the state title and the border ride — is the `#right`
    `TabbedContent` around the tab strip (the lab's `#flow-pane` around its `Tabs`), so the focusable canvas panes
    (`#live-pane`, `#plan-pane`) carry no border of their own and the frame takes the yellow of the focused box
    (`#right:focus-within`), while the unfocused frame stays the idle bright black."""

    async def test_a3_a4_a5_the_colours_the_titles_and_the_time_lines(self):
        self.enterContext(zone("UTC"))  # the rows' `Z` stamps are shown in the local zone: pinned to read 21:01
        self.approve(running=True)  # M1 running: the canvas frame title names it
        store = self.fixture.store()
        store.append("architect", text="Ответ", ts="2026-10-24T21:01:00Z")
        store.append("owner", text="вопрос", ts="2026-10-24T21:02:00Z")
        # A gated reply: the turn persists its owner row and then waits, so the running screen is what the A5 check
        # reads (the fixture releases the process once the assertions are made).
        release = self.root / "release"
        self.fixture.script([{"lines": OPENING, "release": str(release), "release_timeout": 30}])
        async with self.shell(size=(120, 40), store=store) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            app = self.app
            # A3: the screen paints with the terminal's palette; the borders resolve to the lab's ANSI names
            self.assertTrue(app.ansi_color)
            self.assertEqual(app.theme, "ansi-dark")
            self.assertEqual(ansi(app.query_one("#chat-pane").styles.border.top), 3)   # focused chat pane: yellow
            self.assertEqual(ansi(app.query_one("#prompt-box").styles.border.top), 3)  # focused input box: yellow
            self.assertFalse(app.query_one("#input").styles.border)  # the input itself carries no border
            canvas = app.query_one("#right")
            self.assertEqual(ansi(canvas.styles.border.top), 8)  # the canvas frame, no focus in it: bright black
            self.assertEqual(ansi(canvas.styles.border.right), 8)
            architect = [message for message in app.query(".msg") if message.role == "architect"]
            owner = [message for message in app.query(".msg") if message.role == "owner"]
            self.assertTrue(architect and owner)
            self.assertEqual(ansi(owner[0].query_one(".body").styles.border_left), 3)   # the owner's yellow bar
            self.assertEqual(architect[0].query_one(".body").styles.border_left[0], "")      # the architect has none
            # A3: a focused canvas pane — the Scheme one, focused the way the arrows and the mouse reach it — turns
            # the frame it lives in yellow (the lab's focused box), and leaving it for the input turns it back.
            app.query_one("#live-pane").focus()
            await pilot.pause()
            self.assertEqual(app.focused.id, "live-pane")
            self.assertEqual(ansi(canvas.styles.border.top), 3)
            app.query_one("#plan-pane").focus()
            await pilot.pause()
            self.assertEqual(app.focused.id, "plan-pane")
            self.assertEqual(ansi(canvas.styles.border.top), 3)  # the Plan pane's focus colours the frame too
            app.query_one("#input").focus()
            await pilot.pause()
            self.assertEqual(ansi(canvas.styles.border.top), 8)
            # A4: the titles and the tab labels
            self.assertEqual(app.query_one("#chat-pane").border_title, strings.text("chat.title"))
            running = [row for row in app.rows() if row.state == "running"]
            self.assertTrue(running)
            self.assertEqual(canvas.border_title,
                             strings.text("canvas.scheme_running", stage="%s %s" % (running[0].id, running[0].title)))
            self.assertEqual([tab.label_text for tab in app.query("Tab")],
                             [strings.text("pane.flow"), strings.text("pane.plan")])
            self.assertEqual(app.query_one("#activity").border_title, strings.text("pane.activity"))
            # A5: the first entry stands behind a time line taken from the stored row's ts, the next (a minute later)
            # does not
            shown = screen_text(app)
            self.assertIn("24.10 21:01", shown)
            self.assertNotIn("21:02", shown)
            # A5 while a turn runs: the line the send posts is stamped from the row the turn writes, so its time
            # line (a day later than the rows above) appears before the reply arrives.
            field = app.query_one("#input")
            field.value = "живой вопрос"
            await pilot.press("enter")
            await self.until(pilot, lambda: app.chat.busy)
            await self.until(pilot, lambda: any(row["role"] == "owner" and row.get("text") == "живой вопрос"
                                                for row in store.transcript()))
            stamp = chat_module.stamp_at([row for row in store.transcript()
                                          if row.get("text") == "живой вопрос"][-1]["ts"])
            self.assertTrue(stamp)
            await self.until(pilot, lambda: stamp in screen_text(app))
            self.assertTrue(app.chat.busy)  # the reply still waits: the stamp appeared during the turn
            release.write_text("go")
            await self.chat_done(pilot)


class PolishLineTests(unittest.TestCase):
    """i10/P3 without an app: the Plan tab names the `/` command in place of the line UI's letter key."""

    def test_p3_the_plan_tab_names_commands_not_letter_keys(self):
        from terminal_planner.tui.app import plan_tab_line
        self.assertEqual(plan_tab_line("Next: [p] plan — describe the goal"), "Next: write the goal to the architect in the chat")
        self.assertEqual(plan_tab_line("Next: [p] plan — approve or revise"),
                         "Next: /approve — approve, or tell the architect what to revise")
        self.assertEqual(plan_tab_line("No plan."), "No plan.")
        self.assertEqual(plan_tab_line("Next: [g] start M1"), "Next: /run — start M1")
        self.assertEqual(plan_tab_line("Next: [g] new attempt M1 — from the current HEAD"),
                         "Next: /run — new attempt M1 — from the current HEAD")
        # K1a: the other removed pane keys a line names become their commands (the lines are the line UI's)
        self.assertEqual(plan_tab_line("Next: [w] watch M1"), "Next: /attempt watch M1")
        self.assertEqual(plan_tab_line("Next: [g] continue M1 — the same attempt; [o] open — a new attempt"),
                         "Next: /run — continue M1 — the same attempt; /attempt open — a new attempt")
        self.assertEqual(plan_tab_line("All 2 slots are busy (M1, M2): they wait. [w] watch, [g] check."),
                         "All 2 slots are busy (M1, M2): they wait. /attempt watch, /run check.")
        # K1d: every letter of the line UI has its step (`[l]`, `[r]` included); only a letter outside the table is dropped
        self.assertEqual(plan_tab_line("Next: all stages are merged; [r] revise — a new goal"),
                         "Next: all stages are merged; /view → revise — a new goal")
        self.assertEqual(plan_tab_line("Next: [l] refresh login, then [g] check readiness."),
                         "Next: /setup → log in, then /run — check readiness.")
        self.assertIsNone(plan_tab_line("Next: [k] something"))


SERVICE_FILES = ("planning.py", "delivery.py", "setup.py", "runs.py", "authority.py", "engine.py", "live.py")
LETTER_KEY = re.compile(r"\[[a-z]\]")


def letter_texts(path):
    """The string literals of one service file that name a letter key (`[g]`, `[l]`, …), docstrings aside: the texts
    the line UI prints and the TUI receives."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {id(node.body[0].value) for node in ast.walk(tree)
                  if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                  and node.body and isinstance(node.body[0], ast.Expr)}
    return [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in docstrings and LETTER_KEY.search(node.value)]


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class LetterKeyTests(unittest.TestCase):
    """K1d: no TUI text names a letter key. The TUI has no letter keys, but the services write `[g]`, `[l]`, `[r]` …
    for the line UI; the TUI rewrites them at its display boundary with one table (`KEY_COMMANDS`) and Settings
    names its two buttons instead.

    Interpretations (the worker's summary never reaches the reviewers):

    * The inputs of the task are found, not copied: every non-docstring string literal of the service files that
      names a letter key goes through each surface's function (`plan_tab_line` for the plan screen and tab,
      `command_hints` for notes, the run screen and the chat, `button_hints` for Settings, `ready_text` and
      `failed_card_text` for the cards). A new `[k]` hint in a service therefore fails here, as the task asks.
    * A label the service repeats after `[l]`, `[u]` or `[r]` (`[l] refresh login`, `[r] revise`) is the step's
      own label and is not said twice: «/setup → log in», not «/setup → log in refresh login».
    * `[l]`/`[u]` at the head of a Settings sentence read «Button «…»»; a Settings line that ends in `— [l] log in (…)`
      ends in «— button «log in»».
    * The login-failed line of the app says «log in again: [l].» so that both of its
      forms, «…again: /setup → log in.» and «…again: button «log in».», read as a sentence.
    * The plain CLI is untouched (C3): the service texts keep their letters, which the scan below asserts and
      `tests/test_ux.py` pins on the line UI's failed-plan screen.
    """

    def inputs(self):
        root = Path(__file__).resolve().parents[1] / "terminal_planner"
        texts = [text for name in SERVICE_FILES for text in letter_texts(root / name)]
        self.assertGreater(len(texts), 20)  # the scan found the service hints
        own = letter_texts(root / "tui" / "app.py")  # the app's own notes (block_lines, the login-failed line)
        self.assertTrue(any("[g]" in text for text in own))
        return texts + own

    def test_c1_one_table_maps_every_letter_to_its_step(self):
        from terminal_planner.tui.app import command_hints
        steps = {"g": "/run", "o": "/attempt", "w": "/attempt", "n": "/attempt", "p": "/view", "e": "/log",
                 "i": "/details", "d": "/diff", "t": "/answer", "u": "/setup → install", "l": "/setup → log in",
                 "r": "/view → revise"}
        for letter, step in steps.items():
            with self.subTest(letter):
                self.assertEqual(command_hints("before [%s] after" % letter), "before %s after" % step)
        self.assertEqual(command_hints("Next: [l] refresh login, then"), "Next: /setup → log in, then")
        self.assertEqual(command_hints("[r] revise rebuilds the plan"), "/view → revise rebuilds the plan")
        self.assertEqual(command_hints("[q] back"), "[q] back")  # a letter outside the table stays

    def test_c2_settings_names_the_buttons(self):
        from terminal_planner.tui.app import button_hints
        self.assertEqual(button_hints("Codex: not logged in at ~ — [l] log in (zplan's own login, not ~/.codex)"),
                         "Codex: not logged in at ~ — button «%s»" % catalog.label("tui_settings.login"))
        self.assertEqual(button_hints("Install: [u] or zplan setup."),
                         "Install: button «%s» or zplan setup." % catalog.label("tui_settings.setup"))
        self.assertEqual(button_hints("[l] starts the Codex login"),
                         "Button «%s» starts the Codex login" % catalog.label("tui_settings.login"))
        self.assertEqual(button_hints("There are changes — [d] view"), "There are changes — /diff view")

    def test_c3_c4_no_service_text_shows_a_letter_key_on_a_tui_surface(self):
        from terminal_planner.tui.app import button_hints, command_hints, plan_tab_line
        from terminal_planner.tui.card_kinds import failed_card_text, note_text, ready_text
        check = type("Check", (), {"ok": False, "line": ""})()
        texts = self.inputs()
        self.assertTrue(any("[l] refresh login" in text for text in texts))  # C3: the service text keeps its letters
        for text in texts:
            check.line = text
            shown = {"plan screen": plan_tab_line(text), "notes": command_hints(text), "note": note_text(text),
                     "settings": button_hints(text), "failed card": failed_card_text([text]),
                     "ready card": ready_text([check])}
            for surface, rendered in shown.items():
                with self.subTest(surface=surface, text=text):
                    self.assertIsNotNone(rendered)
                    self.assertNotRegex(rendered, LETTER_KEY)

    def test_c4_the_plan_screen_block_lines_show_no_letter_key(self):
        """`block_lines` (both branches) reaches the PlanScreen body through `plan_tab_line`; the app's own literals
        are also scanned in `inputs`, so a new `[k]` there fails too."""
        from terminal_planner.tui.app import ZplanApp, plan_tab_line
        ok, bad = (type("Check", (), {"ok": ok, "line": "Codex: not logged in"})() for ok in (True, False))
        for checks in ([ok], [bad], [ok, bad]):
            stub = type("Stub", (), {"plan_block": checks, "checks": None})()
            lines = ZplanApp.block_lines(stub)
            self.assertTrue(lines)
            for line in lines:
                with self.subTest(line=line):
                    self.assertNotRegex(plan_tab_line(line), LETTER_KEY)


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class LabPolishTests(ChatShell):
    """i10 P1/P2/P3 through the real shell (two app tests).

    Interpretations: P1 «the prompt box spans the chat pane's content width» is the box region equal to the pane's
    `content_region` in x and width (the entries sit in the same region); the box loses its side padding and the
    chevron keeps one column of its own so the 36-column placeholder fits the 41-column pane of 120x40. P2: the
    full refusal stays in the `#status` area (wrapped, with its remedy and code) and the chat head's elided
    repeat of it is gone, so the text is counted once in the whole chat pane. P3: a «Next:» line that names a
    letter key with no `/` command, and the line UI's footer, are not shown on the tab."""

    async def test_p1_p2_the_hint_fits_and_the_refusal_shows_once(self):
        hint = strings.text("chat.placeholder")
        for size in ((120, 40), (80, 24)):
            async with self.shell(size=size, chat_prepare=False) as pilot:  # False: the production prepare, blocked
                await self.loaded(pilot)
                await self.chat_ready(pilot)
                await pilot.pause(0.3)
                app = self.app
                rows = screen_lines(app)
                box, content = app.query_one("#prompt-box"), app.query_one("#chat-pane").content_region
                self.assertEqual((box.region.x, box.region.width), (content.x, content.width), size)
                self.assertIn(hint, rows[box.region.y + 1], size)
                pane = "\n".join(row[:app.query_one("#chat-pane").region.right] for row in rows)
                self.assertEqual(pane.count("setup.tools_invalid"), 1, size)  # the refusal (T1's text) shows once, by its code
                self.assertIn("setup.tools_invalid", pane)

    async def test_p3_the_plan_tab_reads_the_command(self):
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            lines = list(self.app.screen.plan_lines)
            self.assertIn("No plan.", lines)
            self.assertIn("Next: write the goal to the architect in the chat", lines)
            self.assertNotIn("[p]", "\n".join(lines))


if __name__ == "__main__":
    unittest.main()
