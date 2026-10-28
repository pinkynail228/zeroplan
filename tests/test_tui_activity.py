"""W3 — `terminal_planner/tui/activity.py` (release 0.5.2, run w3): A1-A6.

The widgets run in a minimal test App that holds nothing but them — no project, no controller, no network (A6) —
and every test uses an isolated `XDG_CONFIG_HOME` with a pinned language, so the frozen string catalog is
deterministic and the runner's own UI settings are never read. A1 and A2 read the pane's own content and border
(what `show` put there), A3 the rows of the real screen (the ellipsis is added while drawing).

Worker interpretations (both reviewers inspect this docstring):

- A1's "4-row pane" is a pane whose *content* box is four rows: the widget is six rows tall, because the round
  border of `DEFAULT_CSS` (the lab's `#log-pane`) costs two. Textual's `size` is the content box, and it is the
  number that decides how many lines fit: a `Static` draws its text top-aligned, so counting the border rows in
  would push the newest lines out of the pane instead of showing them. The test asserts `pane.size.height == 4`, so
  the criterion is checked at the size it names.
- `silence` counts as measured only when it is an `int` (A2's 187): any other value — None, a float, a string —
  leaves the subtitle empty, so a run without a measured silence never shows an invented `0:00`. `flow.silence` is
  seconds between two stored clocks, i.e. an int, when it exists at all.
- `bar_text`'s `branch` is `Snapshot.branch`, which is optional: a false branch is dropped together with its `" · "`
  separator, so the bar never prints a literal "None". The separator before the job phrase, before each key pair
  and before `bar.continue` is the one `" · "` (i9/A1, three cells); `tests/test_tui_look.py` pins the bar's whole
  idle text.
- An unknown `job` value (outside the seven the task lists) falls back to `bar.idle`, exactly as the lab's
  `{...}.get(state)` did; the test does not name one, so this is only a guard, not checked behaviour.
- U1 (the architect's turn on the bar), interpretations: the turn's clock is `m:ss` (the task's «0:03», «4:10»), the
  job's own clock keeps its `h:mm:ss`; "the owner's running turn" is the chat's mode `owner` (read as `chat._mode`,
  `tui/chat.py` stays untouched — no public accessor names it), so an event turn or the `/new` warm-up cancelled by
  Esc shows no cancel line; "until the next send" is the next *accepted* send (a refused one keeps the line); the
  tail ` · the architect is replying` is dropped when the bar with it would not fit the width, before `bar.continue` is
  considered. The screen tests call `MainScreen` / `ZplanApp` methods on a stand-in `self`, no app is driven.
- 0.5.2 keeps the journal lines plain and the pane's text is the app's own lines, wedged in unchanged: no role
  colours, no alarm rows, no spinner (the task's non-goals).
- The border title and subtitle carry data (the catalog's caption, the clipped journal line), so both are assigned
  as a literal `rich.text.Text`: a bracket in either is drawn as typed, never read as console markup. The subtitle
  of an unmeasured silence stays the empty string `""`, as A2 states.
"""

import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from terminal_planner.tui import strings
from tui_support import HAVE_TEXTUAL, screen_lines, screen_text

# The reason the other TUI modules give: without Textual the classes below are still declared (unittest discovery
# must see them) and skipped, never hidden.
TEXTUAL_REASON = "Textual недоступен: нужен ZPLAN_TEST_WHEELHOUSE с wheels textual 8.2.8"

PROJECT = "zeroshot-planning-kit"
BRANCH = "main"
KEYS = [("←→", "bar.key_tabs"), ("/", "bar.key_commands"), ("ctrl+q", "bar.key_quit")]

if HAVE_TEXTUAL:
    from rich.cells import cell_len
    from textual.app import App, ComposeResult

    from terminal_planner.tui.activity import Activity, Bar, bar_text

    class ActivityApp(App):
        """The minimal test App of A6: the journal pane and the bar, nothing else (no project, no controller, no
        toolchain, no file system and no network beyond what composing and running these two widgets touches)."""

        CSS = """
        Activity { height: 6; width: 40; }
        Bar { width: 100%; }
        """

        def compose(self) -> ComposeResult:
            yield Activity()
            yield Bar()


def pane_content(app, widget):
    """The pane's content rows as the terminal shows them: the round border and `padding: 0 1` cut away."""
    region = widget.region
    inner = region.x + 2
    rows = screen_lines(app)[region.y + 1: region.y + region.height - 1]
    return [row[inner: inner + widget.size.width] for row in rows]


def row_segments(app, row):
    """The drawn segments of screen `row`: the styles each cell really carries (borders included)."""
    return app.screen._compositor.render_strips()[row]._segments


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class ActivityTests(unittest.IsolatedAsyncioTestCase):
    """A1-A6 of the run; `ActivityApp` above is the whole screen they run in (A6)."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        self.environment = patch.dict(os.environ, {"XDG_CONFIG_HOME": str(root / "config")})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        strings.set_language("ru")  # the runner's own choice is never read (the file lives in the scratch root)

    # A1 --------------------------------------------------------------------------------------------------
    async def test_a1_the_newest_lines_that_fit_show_oldest_first_or_the_empty_text(self):
        app = ActivityApp()
        async with app.run_test(size=(60, 12)) as pilot:
            pane = app.query_one(Activity)
            self.assertEqual(pane.size.height, 4)  # the four-row content box A1 names
            pane.show(["line %d" % number for number in range(1, 11)], 5)
            await pilot.pause()
            self.assertEqual(pane.render().plain, "line 7\nline 8\nline 9\nline 10")  # newest four, oldest first
            pane.show([], None)
            await pilot.pause()
            self.assertEqual(pane.render().plain, strings.text("canvas.log_empty"))
            self.assertEqual([bool(getattr(span.style, "dim", False))
                              for span in pane.render().spans], [True])

    # A2 --------------------------------------------------------------------------------------------------
    async def test_a2_the_subtitle_names_the_last_line_and_the_measured_silence(self):
        app = ActivityApp()
        async with app.run_test(size=(60, 12)) as pilot:
            pane = app.query_one(Activity)
            pane.show(["first line nobody names", "я" * 60], 187)
            await pilot.pause()
            clipped = "я" * 39 + "…"  # the last line clipped to 40 cells
            self.assertEqual(pane.border_subtitle, strings.text("live.last_event", what=clipped, m="3:07"))
            self.assertIn("3:07", pane.border_subtitle)
            self.assertEqual(cell_len(clipped), 40)
            pane.show(["first line nobody names"], None)
            await pilot.pause()
            self.assertEqual(pane.border_subtitle, "")  # no measured silence: no invented 0:00
            pane.show([], 187)
            await pilot.pause()
            self.assertEqual(pane.border_subtitle, "")  # no lines: nothing to name

    # A3 --------------------------------------------------------------------------------------------------
    async def test_a3_a_line_wider_than_the_pane_is_cut_with_an_ellipsis_and_does_not_wrap(self):
        app = ActivityApp()
        async with app.run_test(size=(60, 12)) as pilot:
            pane = app.query_one(Activity)
            pane.show(["x" * 200], None)
            await pilot.pause()
            rows = [row.rstrip() for row in pane_content(app, pane)]
            self.assertEqual(rows[0], "x" * (pane.size.width - 1) + "…")
            self.assertEqual(rows, [rows[0], "", "", ""])  # the tail is cut, never carried to a second row

    async def test_a2_a_bracketed_journal_line_stays_literal_in_the_subtitle(self):
        """A2, regression: the subtitle shows the clipped last line literally — never console markup.

        A journal line is a formatted string the app already holds (`Snapshot.journal`), so it may carry `[`; both
        border texts are therefore assigned as a literal `rich.text.Text` (the title too — the catalog is data as
        well). Interpretations: an absent subtitle is the empty string the A2 test above names, never `None`, and
        the tag is checked on its own border row, the row the user reads.
        """
        app = ActivityApp()
        async with app.run_test(size=(80, 12)) as pilot:
            pane = app.query_one(Activity)
            pane.styles.width = 60  # room for the whole subtitle: a parsed-away tag cannot hide behind the clip
            await pilot.pause()
            pane.show(["07:12 [red] проверка"], 187)
            await pilot.pause()
            row = pane.region.y + pane.region.height - 1  # the pane's bottom border, where the subtitle is drawn
            subtitle = screen_lines(app)[row]
            self.assertIn(strings.text("live.last_event", what="07:12 [red] проверка", m="3:07"), subtitle)
            colors = {str(segment.style.color) for segment in row_segments(app, row)}
            self.assertNotIn("red", colors)  # the line is drawn as typed, not restyled from its own brackets
            pane.show(["07:12 worker: unmatched [/bold]"], 187)
            await pilot.pause()
            self.assertIn("[/bold]", screen_lines(app)[row])  # an unmatched tag is data: no MarkupError

    # A4 --------------------------------------------------------------------------------------------------
    def test_a4_every_job_shows_its_catalog_text_and_the_clock(self):
        for job, job_id in ((None, "bar.idle"), ("planning", "bar.job_planning"),
                            ("approve", "bar.waiting_approve"), ("merge", "bar.waiting_merge"),
                            ("question", "bar.waiting_question"), ("error", "bar.stopped_error")):
            with self.subTest(job=job):
                plain = bar_text(PROJECT, BRANCH, job, "M2", 3725, KEYS, 200).plain
                self.assertIn(strings.text(job_id, stage="M2", clock="1:02:05"), plain)
        running = bar_text(PROJECT, BRANCH, "running", "M2", 3725, KEYS, 200).plain
        self.assertIn(strings.text("live.job_timer", stage="M2", h="1:02:05"), running)
        self.assertIn("1:02:05", running)
        unknown = bar_text(PROJECT, BRANCH, "running", "M2", None, KEYS, 200).plain
        self.assertIn(strings.text("live.job_timer", stage="M2", h="—"), unknown)
        self.assertIn("—", unknown)

    def test_p2a_an_unknown_planning_time_shows_no_clock_and_no_dash(self):
        """P2a/C2: `_job_text("planning", "", None)` is the phrase alone; a known time keeps its clock."""
        from terminal_planner.tui.activity import _job_text
        self.assertEqual(_job_text("planning", "", None), strings.text("bar.job_planning", clock="").strip())
        self.assertNotIn("—", _job_text("planning", "", None))
        self.assertEqual(_job_text("planning", "", None), _job_text("planning", "", None).strip())
        self.assertEqual(_job_text("planning", "", 65), strings.text("bar.job_planning", clock="0:01:05"))
        self.assertTrue(_job_text("planning", "", 65).endswith("0:01:05"))

    # A5 --------------------------------------------------------------------------------------------------
    def test_a5_the_bar_fits_every_width_and_keeps_continue_only_with_room(self):
        for width in (40, 80, 120):
            with self.subTest(width=width):
                self.assertLessEqual(bar_text(PROJECT, BRANCH, "planning", "M2", 65, KEYS, width).cell_len, width)
        wide = bar_text(PROJECT, BRANCH, "planning", "M2", 65, KEYS, 120).plain
        narrow = bar_text(PROJECT, BRANCH, "planning", "M2", 65, KEYS, 40).plain
        self.assertIn(strings.text("bar.continue"), wide)  # 120 leaves at least 24 cells
        self.assertNotIn(strings.text("bar.continue"), narrow)
        self.assertTrue(narrow.endswith("…"))  # a bar longer than 40 cells is cut with an ellipsis, never wrapped

    # U1 --------------------------------------------------------------------------------------------------
    def test_u1_c1_c3_an_architect_turn_alone_is_the_job_phrase_with_its_clock(self):
        turn = bar_text(PROJECT, BRANCH, None, "", None, KEYS, 120, turn=3).plain
        self.assertIn("%s 0:03" % strings.text("bar.architect"), turn)
        self.assertNotIn(strings.text("bar.idle"), turn)
        self.assertIn(strings.text("bar.idle"), bar_text(PROJECT, BRANCH, None, "", None, KEYS, 120).plain)  # C3

    def test_u1_c2_beside_a_job_the_phrase_is_a_tail_and_a_narrow_bar_drops_it_first(self):
        job = strings.text("live.job_timer", stage="M1", h="0:04:10")
        wide = bar_text(PROJECT, BRANCH, "running", "M1", 250, KEYS, 160, turn=7).plain
        self.assertIn("%s · %s" % (job, strings.text("bar.architect")), wide)
        narrow = bar_text(PROJECT, BRANCH, "running", "M1", 250, KEYS, 80, turn=7).plain
        self.assertIn(job, narrow)
        self.assertNotIn(strings.text("bar.architect"), narrow)
        self.assertEqual(narrow, bar_text(PROJECT, BRANCH, "running", "M1", 250, KEYS, 80).plain)

    def test_u1_screen_clock_counts_from_the_turns_own_start_and_ends_with_the_turn(self):
        """U1b C1: the clock reads the chat's `turn_started`, so a turn that follows another with no look between
        (a queued owner message behind an event turn) starts at 0:00; a busy bare check is no turn."""
        from terminal_planner.tui.app import MainScreen

        chat = SimpleNamespace(busy=True, turn_running=False, turn_started=0.0)  # a bare check: busy, not a turn
        screen = SimpleNamespace(app=SimpleNamespace(chat=chat))
        self.assertIsNone(MainScreen.turn_clock(screen))
        chat.turn_running, chat.turn_started = True, 100.0
        with patch("terminal_planner.tui.app.time.monotonic", side_effect=[100.0, 103.0, 150.0]):
            self.assertEqual(MainScreen.turn_clock(screen), 0.0)  # the turn's own start, not a first look
            self.assertEqual(MainScreen.turn_clock(screen), 3.0)
            chat.turn_started = 149.0  # the next turn began without a look that saw `turn_running` False
            self.assertEqual(MainScreen.turn_clock(screen), 1.0)
        chat.turn_running = False
        self.assertIsNone(MainScreen.turn_clock(screen))  # C3: the next refresh returns to the job's own phrase

    def test_u1_c4_esc_on_the_owner_turn_leaves_a_line_the_next_send_clears(self):
        from terminal_planner.tui.app import MainScreen, ZplanApp

        for mode, shown in (("owner", True), ("check", False)):
            with self.subTest(mode=mode):
                notes = []
                box = SimpleNamespace(display=False)
                chat = SimpleNamespace(_mode=mode, cancel=lambda: True,
                                       send=lambda value, snapshot=None: (True, ""))
                app = SimpleNamespace(chat=chat, chat_note="", chat_snapshot=lambda: None)
                screen = SimpleNamespace(app=app, query_one=lambda *_: box, close_active_view_tab=lambda: False,
                                         status_note=lambda line: setattr(app, "chat_note", line),
                                         render_state=lambda: notes.append("render"))
                MainScreen.action_cancel_turn(screen)
                line = strings.text("note.turn_cancelled")
                self.assertEqual(app.chat_note, line if shown else "")
                ZplanApp.send_chat(app, "ещё")
                self.assertEqual(app.chat_note, "")
        self.assertEqual(strings.CATALOG["note.turn_cancelled"]["en"], "The architect's reply was cancelled.")

    # A6 --------------------------------------------------------------------------------------------------
    async def test_a6_the_widgets_run_in_a_minimal_app_without_a_project_or_controller(self):
        app = ActivityApp()
        async with app.run_test(size=(60, 12)) as pilot:
            self.assertFalse(hasattr(app, "controller"))  # the fixture App carries no project or controller
            pane, bar = app.query_one(Activity), app.query_one(Bar)
            pane.show(["07:12:00  исполнитель  начал"], 12)
            bar.update_bar(PROJECT, BRANCH, "running", "M2", 5, KEYS)
            await pilot.pause()
            shown = screen_text(app)
            self.assertIn("07:12:00  исполнитель  начал", shown)
            self.assertIn(strings.text("live.job_timer", stage="M2", h="0:00:05"), shown)  # the bar's own width
            await pilot.resize_terminal(30, 12)  # the widgets redraw for their new size, no `show`/`update_bar`
            await pilot.pause()
            self.assertLessEqual(cell_len(bar.render().plain), bar.size.width)
            self.assertEqual(bar.render().plain,
                             bar_text(PROJECT, BRANCH, "running", "M2", 5, KEYS, bar.size.width).plain)


if __name__ == "__main__":
    unittest.main()
