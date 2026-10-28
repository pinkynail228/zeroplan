"""M1 (0.6.3 V2): the chat's messages have no author line. One invariant test per size (80x24 and 140x40) through the
real shell covers C1-C5; the pure rules (time lines, L-2 before Markdown, draft lines) are checked without an app.

Interpretations (the task leaves these open; the worker's summary never reaches the reviewers):
- The previous entry of a time line is the previous entry that carries a stored time; the owner's optimistic line has
  none yet, so it gets no time line until the turn stamps it from the store row (`chat._stamp_owner_line`).
- A `ts` the zone rule cannot read (`chat.moment` is None) names no time: its entry gets no time line.
- "Reset and event entries unchanged (V3)": they keep their plain text, with no gutter, no bar and no author line (C1
  holds for every entry); only the owner, the architect and the error entries are restyled.
- The architect's gutter is part of the entry's body (a 2-cell column of a rich table beside the Markdown), so it
  stays beside the text however it wraps; the owner's bar is the body's CSS `border-left: outer ansi_yellow`.
- A draft line is dim text outside the Markdown, so model text can never style it; a draft already in the reply stays
  collapsed at its block (the narrative around it is rendered as Markdown on either side).
- The shell reads each entry's rows off the widget (`render_lines`), because at 80x24 the pane holds only a few
  rows and the entries are checked whole, not as the scroll happens to show them.
"""

import contextlib
from datetime import date, datetime, timedelta, timezone
import os
import time
import unittest

from terminal_planner.tui import chat as chat_module
from tui_support import HAVE_TEXTUAL
from test_tui_chat import ChatShell, TEXTUAL_REASON

if HAVE_TEXTUAL:
    from rich.console import Console
    from textual.geometry import Region

    from terminal_planner.tui import app as app_module

TODAY = datetime.now(timezone.utc).date()
REPLY = ("## План\n- M1\n\n```python\nx = 1\n```\n[bold]x[/] \x1b[31my\n\n```zplan-goal\nСделать X\n```\nконец")
DRAFTS = [{"kind": "goal", "text": "Сделать X", "milestone": None, "identity": "no plan"}]


def stamp(day, clock):
    return "%sT%s:00Z" % (day.isoformat(), clock)


@contextlib.contextmanager
def utc():
    """The process zone pinned to UTC, so a `Z` stamp reads the same on every machine."""
    before = os.environ.get("TZ")
    os.environ["TZ"] = "UTC"
    time.tzset()
    try:
        yield
    finally:
        if before is None:
            del os.environ["TZ"]
        else:
            os.environ["TZ"] = before
        time.tzset()


class TimeLineTests(unittest.TestCase):
    """C1: the time line of each entry, from the stored `ts` alone."""

    def test_c1_a_time_line_stands_before_the_first_entry_and_after_ten_minutes(self):
        with utc():
            rows = [{"role": "owner", "text": "а", "ts": stamp(TODAY, "10:00")},
                    {"role": "architect", "text": "б", "ts": stamp(TODAY, "10:01")},
                    {"role": "owner", "text": "в", "ts": stamp(TODAY, "10:30")},
                    {"role": "architect", "text": "г", "ts": stamp(TODAY, "10:39")},
                    {"role": "owner", "text": "д", "ts": stamp(TODAY - timedelta(days=1), "10:49")}]
            found = chat_module.entries_of(rows)
            self.assertEqual(chat_module.time_labels(found[:3], today=TODAY), ["10:00", "", "10:30"])
            self.assertEqual(chat_module.time_labels(found[2:4], today=TODAY), ["10:30", ""])   # 9 minutes: none
            self.assertEqual(chat_module.time_labels(found[:1], today=TODAY + timedelta(days=1)),
                             [TODAY.strftime("%d.%m") + " 10:00"])                              # not today: the date
            # an entry with no stored time (the optimistic owner line) has none and moves no gap
            plain = chat_module.entries_of([rows[0], {"role": "owner", "text": "ещё"}, rows[2]])
            self.assertEqual(chat_module.time_labels(plain, today=TODAY), ["10:00", "", "10:30"])


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class TextRulesTests(unittest.TestCase):
    """C3/C4 without an app: L-2 runs on the raw text before Markdown, and a draft line is its own dim line."""

    def plain(self, renderable, width=60):
        console = Console(width=width, no_color=True, force_terminal=False)
        with console.capture() as capture:
            console.print(renderable)
        return [line.rstrip() for line in capture.get().split("\n") if line.strip()]

    def test_c3_model_markup_is_text_and_a_terminal_sequence_is_gone(self):
        entry = chat_module.entries_of([{"role": "architect", "text": "[bold]x[/] \x1b[31my\n**жирный**"}])[0]
        _entry, role, shown = app_module.entry_rows([entry])[0]
        self.assertEqual(shown.blocks, (("text", "[bold]x[/] y\n**жирный**"),))
        self.assertEqual(self.plain(app_module.message_body(role, shown.blocks)), ["● [bold]x[/] y жирный"])

    def test_m2_text_that_looks_like_html_shows_literally(self):
        """M2 C1-C4 at 80 columns, through L-2 (`entry_rows`) and `message_body`: rich drops markdown-it's HTML tokens,
        so `Vec<String>` and `<!-- hi -->` used to vanish.

        Interpretation: an HTML block shows as typed, line for line, with no Markdown styling inside it; inline
        HTML is plain text inside the surrounding Markdown; nothing is rendered as HTML."""
        def shown(text):
            entry = chat_module.entries_of([{"role": "architect", "text": text}])[0]
            _entry, role, body = app_module.entry_rows([entry])[0]
            return self.plain(app_module.message_body(role, body.blocks), width=80)

        # C1: inline tags, comments, a generic type: character for character; other styling still applies
        self.assertEqual(shown("use Vec<String> here"), ["● use Vec<String> here"])
        self.assertEqual(shown("<!-- hi --> z"), ["● <!-- hi --> z"])
        self.assertEqual(shown("**a** <b>y</b> `c`"), ["● a <b>y</b> c"])
        # C2: block HTML keeps its lines, in order
        self.assertEqual(shown("x\n\n<div>\nblock\n</div>\n\ny"), ["● x", "  <div>", "  block", "  </div>", "  y"])
        # C3: code spans, comparisons, headings and lists as before
        self.assertEqual(shown("`Vec<T>` ok"), ["● Vec<T> ok"])
        self.assertEqual(shown("1 < 2 and 3 > 2"), ["● 1 < 2 and 3 > 2"])
        self.assertEqual(shown("## План\n- M1"), ["● План", "   • M1"])
        # C4: L-2 first (the escape sequence is gone), model markup is text next to literal tags
        self.assertEqual(shown("[bold]x[/] <b>y</b> \x1b[31mz"), ["● [bold]x[/] <b>y</b> z"])

    def test_c4_draft_lines_have_no_reply_name_or_author(self):
        goal = chat_module.entries_of([{"role": "architect", "text": "Вот.", "status": "completed",
                                        "drafts": [{"kind": "goal", "text": "Сделать X", "identity": "no plan"}]}])[0]
        answer = chat_module.entries_of([{"role": "architect", "text": "", "status": "completed",
                                          "drafts": [{"kind": "answer", "text": "Да", "milestone": "M1",
                                                      "identity": {"milestone": "M1", "attempt": 1}}]}])[0]
        self.assertEqual(chat_module.entry_blocks(goal), [("text", "Вот."), ("draft", "↳ goal draft: Сделать X")])
        self.assertEqual(chat_module.entry_blocks(answer), [("draft", "↳ answer draft M1: Да")])
        self.assertFalse(hasattr(chat_module, "reply_names"))


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class MessagesShellTests(ChatShell):
    """C1-C5 through the real shell: the entries are read off their own widgets, whatever the scroll shows."""

    def seeded(self):
        store = self.fixture.store()
        store.append("owner", text="привет", ts=stamp(TODAY, "10:00"))
        store.append("architect", text=REPLY, status="completed", drafts=DRAFTS, ts=stamp(TODAY, "10:01"))
        store.append("error", text="сбой сети", ts=stamp(TODAY, "10:02"))
        store.append("owner", text="ещё", ts=stamp(TODAY, "10:30"))
        return store

    def rows(self, widget):
        """The drawn rows of one widget, whole (borders and padding included), and the styles of its segments."""
        lines = widget.render_lines(Region(0, 0, widget.outer_size.width, widget.outer_size.height))
        return [line.text.rstrip() for line in lines], lines

    async def drive(self, size):
        self.enterContext(utc())
        async with self.shell(size=size, store=self.seeded()) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            await self.until(pilot, lambda: len(list(self.app.query("#chat .msg"))) == 4, 10.0)
            await pilot.pause()
            await pilot.pause()
            messages = list(self.app.query("#chat .msg"))
            owner1, architect, error, owner2 = messages
            every = [self.rows(message)[0] for message in messages]
            # C1: no author line anywhere; the time lines are dim, centred, and stand where the rule puts them
            flat = [row for rows in every for row in rows]
            for word in ("ты ·", "архитектор ·", "сбой ·", "· 10:"):
                self.assertFalse([row for row in flat if word in row], word)
            for message, label in zip(messages, ("10:00", "", "", "10:30")):
                time_line = message.query_one(".time")
                self.assertEqual(time_line.display, bool(label), label)
                if label:
                    row = self.rows(time_line)[0][0]
                    self.assertEqual(row.strip(), label)
                    self.assertGreater(len(row) - len(row.lstrip()), 2)        # centred, not left
                    self.assertEqual(time_line.styles.text_align, "center")
                    self.assertEqual(time_line.styles.color.ansi, 8)            # ansi_bright_black: dim
            # C2, owner: bright text behind a yellow left bar, a blank row above
            for message in (owner1, owner2):
                body = message.query_one(".body")
                self.assertEqual(body.styles.border_left[0], "outer")
                self.assertEqual(body.styles.border_left[1].ansi, 3)            # ansi_yellow
                self.assertEqual(body.styles.color.ansi, 15)                    # ansi_bright_white
                self.assertEqual(body.styles.margin.top, 1)
            self.assertEqual(self.rows(owner1.query_one(".body"))[0][-1].strip("▌▎▏▊ "), "привет")
            # C2, architect: a bold magenta ● in a 2-cell gutter, Markdown beside it, no left bar
            body = architect.query_one(".body")
            self.assertEqual(body.styles.border_left[0], "")
            rows, lines = self.rows(body)
            self.assertTrue(rows[0].startswith("● План"), rows)
            self.assertNotIn("##", "\n".join(rows))
            self.assertIn("   • M1", rows)                                      # a list row, bullet and all, beside the gutter
            self.assertIn("    x = 1", rows)                                    # fenced code, no ``` and indented
            self.assertNotIn("```", "\n".join(rows))
            gutter = [segment for segment in lines[0] if segment.text.startswith("●")][0]
            self.assertTrue(gutter.style.bold)
            self.assertEqual(gutter.style.color.number, 5)                      # magenta
            heading = [segment for segment in lines[0] if "План" in segment.text][0]
            self.assertTrue(heading.style.bold)
            code = [segment for segment in lines[rows.index("    x = 1")] if "x" in segment.text][0]
            self.assertTrue(code.style.bgcolor is None or code.style.bgcolor.is_default)  # code: no background
            # C3: L-2 first, Markdown after; the model's markup shows as typed
            self.assertIn("  [bold]x[/] y", rows)
            # C4: the draft already in the text stays collapsed at its block, as one dim line
            draft = [row for row in rows if "draft" in row]
            self.assertEqual(draft, ["  ↳ goal draft: Сделать X"])
            self.assertEqual(rows.index(draft[0]), rows.index("  [bold]x[/] y") + 1)
            self.assertEqual(rows[-1], "  конец")
            # C5: an error entry is a red ! gutter and its text
            rows, lines = self.rows(error.query_one(".body"))
            self.assertEqual(rows, ["! сбой сети"])
            self.assertEqual([segment for segment in lines[0] if segment.text.startswith("!")][0].style.color.number, 1)                  # red
            self.assertEqual(error.query_one(".body").styles.border_left[0], "")

    async def test_c1_c5_at_80x24(self):
        await self.drive((80, 24))

    async def test_c1_c5_at_140x40(self):
        await self.drive((140, 40))


if __name__ == "__main__":
    unittest.main()
