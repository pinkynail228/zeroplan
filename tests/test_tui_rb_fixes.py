"""R-B: medium defects from the 0.5.2 bug hunt (2026-10-24) — status after reopen, user stop, raw commands, 80x24 chat.

One test per criterion (C1-C4), each failing on 48360c8. C1-C3 read the pure functions (`slash_state`, the catalog
and the display helpers); only C4 drives the whole app, at 80x24.

Interpretations (the worker's summary never reaches the reviewers, so they are recorded here):

- C1: "draft wins only when nothing else is active" is read as: running, error, question, merge and planning
  rank ahead of `draft`; `plan_ready` and the plan screen's own failed planning run (`run_failed`, the card's
  `/plan` retry — pinned by test_tui_draft_card) stay behind it (the i3a rule is kept for those two).
- C2: "the slash state stays error" — the milestone row state `stopped` is still an `error` row for `slash_state`;
  the bar job is `stopped` (`bar.stopped_owner`, «M1 stopped by you» — without the `/status` hint the error text
  carries), the canvas title and the card title read as a stop too. The card reason comes from `Delivery.reason`,
  which names a `stopped` attempt «stopped by you» (the plan-stop wording, `PLAN_STATUS["stopped"]`) whatever
  the engine's diagnostic says; neutral style is the card spec's `alarm=False`.
- C3: the program name of a shell wrapper is the first program of the command it runs, after `NAME=value` words
  and `env`; a text cut off inside a quote shows the wrapper's own name. The activity subtitle's last journal line
  has its first absolute local path (two or more parts) replaced by the program name of the rest of the line.
- C4: "opens at its newest message" is read as the `#chat` scroll standing at `max_scroll_y`, with `max_scroll_y`
  above zero (a pane that has nothing to scroll proves nothing), once the layout has settled. The harness lays the
  chat out before the jump, so the pre-layout case is built by hand: the narrow layout hides the chat, a jump made
  meanwhile must survive until the chat is shown again.
"""

import unittest
from types import SimpleNamespace

import tui_support  # noqa: F401  (its import joins the offline wheelhouse to sys.path before the guarded imports)
from tui_support import HAVE_TEXTUAL

from test_tui_chat import chat_band
from test_tui_chat_scroll import ChatScroll, TEXTUAL_REASON

if HAVE_TEXTUAL:
    from terminal_planner import live
    from terminal_planner.delivery import Delivery
    from terminal_planner.tui import app as app_module, strings
    from terminal_planner.tui.activity import Activity, bar_text
    from terminal_planner.tui.scheme import observation_from_flow


def snapshot_of(*states):
    rows = tuple(SimpleNamespace(id="M%d" % (index + 1), state=state) for index, state in enumerate(states))
    return SimpleNamespace(rows=rows, plan=None, status="approved", version=1)


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class StatusAfterReopenTests(unittest.TestCase):
    def test_c1_every_active_fact_outranks_the_draft(self):
        for state, wanted in (("running", "running"), ("needs_owner", "question"), ("awaiting_merge", "merge"),
                              ("failed", "error")):
            with self.subTest(state):
                self.assertEqual(app_module.slash_state(snapshot_of(state), draft=True), wanted)
        self.assertEqual(app_module.slash_state(snapshot_of("ready"), blocked="failure", draft=True), "error")
        self.assertEqual(app_module.slash_state(snapshot_of("ready"), watching=True, draft=True), "planning")
        self.assertEqual(app_module.slash_state(snapshot_of("ready"), draft=True), "draft")  # nothing else active
        self.assertEqual(app_module.slash_state(None, draft=True), "draft")


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class OwnerStopTests(unittest.TestCase):
    def test_c2_a_stop_by_the_owner_reads_as_a_stop_and_stays_an_error_state(self):
        snapshot = snapshot_of("stopped")
        self.assertEqual(app_module.slash_state(snapshot), "error")  # `/run` still offers a new attempt
        row = snapshot.rows[0]
        self.assertTrue(app_module.owner_stopped(row))
        bar = bar_text("notes", "main", "stopped", row.id, None, (), 120).plain
        self.assertIn("M1 stopped by you", bar)
        self.assertNotIn("error", bar)
        record = {"status": "stopped", "diagnostic": "force_stopped"}
        reason = Delivery.reason(SimpleNamespace(), record)
        self.assertIn("stopped by you", reason)
        self.assertNotIn("force_stopped", reason)
        self.assertNotIn("Error", strings.text("card.stopped_title", task="M1"))


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class RawCommandTests(unittest.TestCase):
    COMMAND = "/bin/zsh -lc 'PATH=\"/Users/user/bin:$PATH\" pytest -q'"

    def test_c3_the_tui_shows_a_command_by_its_program_name(self):
        flow = {"worker": {"state": "running"}, "command": self.COMMAND}
        self.assertEqual(observation_from_flow(flow)["worker"]["detail"], "pytest")
        pane = Activity()
        pane._lines, pane._silence = ("  12:00:01  " + self.COMMAND,), 5
        subtitle = pane._subtitle().plain
        self.assertIn("pytest", subtitle)
        self.assertNotIn("/Users", subtitle)
        self.assertNotIn("/bin", subtitle)
        stored = live.new()
        stored["command"] = {"at": "2026-10-24T12:00:00Z", "text": self.COMMAND}
        self.assertEqual(live.flow(stored, "2026-10-24T12:00:00Z", "2026-10-24T12:00:05Z")["command"], self.COMMAND)  # the store is untouched


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class ChatAt80x24Tests(ChatScroll):
    async def test_c4_the_chat_opens_at_its_newest_message_and_paging_works_from_the_input(self):
        self.seed_history(40)
        async with self.shell(size=(80, 24)) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            await self.until(pilot, lambda: len(self.main().chat_entry_widgets) >= 40, 10.0)
            for _ in range(5):
                await pilot.pause()
            scroll = self.scroll()
            self.assertGreater(scroll.max_scroll_y, 0)
            self.assertEqual(scroll.scroll_offset.y, scroll.max_scroll_y)
            self.assertIn("строка 39", chat_band(self.app))
            self.assertEqual(self.app.focused.id, "input")
            await pilot.press("pageup")
            await pilot.pause()
            self.assertLess(self.offset(), scroll.max_scroll_y)
            await pilot.press("pagedown")
            await pilot.pause()
            self.assertTrue(self.at_bottom())
            # The jump that finds no layout (the narrow layout hides the chat while the canvas shows) is not spent:
            # it is made when the chat is shown again.
            screen = self.main()
            scroll.scroll_home(animate=False)
            screen.show_canvas()
            await pilot.pause()
            screen.chat_go_end = True
            screen.scroll_chat_end()
            screen.show_chat()
            for _ in range(5):
                await pilot.pause()
            self.assertTrue(scroll.max_scroll_y > 0 and self.at_bottom())


if __name__ == "__main__":
    unittest.main()
