"""v3d: the Drafts tab is a permanent canvas tab, not a per-draft view tab (v3e: and a saved draft leaves one line in
the chat instead of a card).

A1: two goal-draft replies -> one Drafts tab holding both, the newer first, and no «Goal draft» tab (the strip is
Scheme, Plan, Drafts; `view_tabs` stays empty). A2: esc on the Drafts tab and sending the newest draft with `/plan`
(then the snapshot naming the plan built from it) leave the tab and both drafts where they are (the plan then comes forward by its own rule). A3: a new draft
brings Drafts forward through `ZplanApp.move_tab` once (its owner-choice rule is `move_tab`'s, unchanged); the unit
test pins that the handler of the saved draft asks for it, opens no view tab and mounts one line, no card.

Interpretations:
- «the goal drafts of the retained chat history» is every `goal` draft of the retained entries, actionable or not;
  its time is the reply's stored `ts` as `HH:MM`.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import tui_support  # noqa: F401
import test_tui_draft_card as card_tests

HAVE, MISSING_REASON = card_tests.HAVE, card_tests.MISSING_REASON

if HAVE:  # Textual and Rich only: this module must import without them (tests.test_toolchain)
    from terminal_planner.tui import app as ui, card_kinds
    from terminal_planner.tui.card_host import CardHost
    from textual.widgets import TabPane

OLDER, NEWER = "первый черновик цели", "второй черновик цели"


@unittest.skipUnless(HAVE, MISSING_REASON)
class DraftsTabTests(card_tests.DraftShell):
    async def test_a1_a2_one_drafts_tab_holds_both_drafts_and_stays(self):
        self.seed_goal_draft(OLDER)
        store = self.seed_goal_draft(NEWER)
        calls = []
        async with self.shell(size=(120, 40), store=store) as pilot:
            await self.settled(pilot)
            await self.note_shown(pilot)
            main = self.main()
            right = main.query_one("#right")
            self.assertEqual([pane.id for pane in right.query(TabPane)], [ui.TAB_LIVE, ui.TAB_PLAN, ui.TAB_DRAFTS])
            self.assertEqual(main.view_tabs, [])                      # A1: no per-draft view tab
            self.assertEqual(right.active, ui.TAB_DRAFTS)             # A3: no owner choice, Drafts came forward
            body = self.draft_tab()[1]
            self.assertEqual((body.count(OLDER), body.count(NEWER)), (1, 1))
            self.assertLess(body.index(NEWER), body.index(OLDER))    # the newer first
            await pilot.press("escape")                               # A2: esc closes no fixed tab
            self.assertEqual(right.active, ui.TAB_DRAFTS)
            with patch.object(card_tests.Controller, "start_planning", self.counting_start(calls)):
                await self.send(pilot, "/plan")                       # a bare /plan sends the newer draft...
                await self.until(pilot, lambda: self.app.snapshot.version is not None)
            self.assertEqual(calls, [(NEWER, card_tests.NO_PLAN)])    # ...with its own identity
            await pilot.pause(0.3)
            self.assertEqual([pane.id for pane in right.query(TabPane)], [ui.TAB_LIVE, ui.TAB_PLAN, ui.TAB_DRAFTS])
            self.assertEqual(main.view_tabs, [])
            self.assertTrue(self.draft_tab()[1].endswith(body))       # both drafts remain after the plan exists...
            self.assertIn("Plan r1 · proposed", self.draft_tab()[1])  # ...below the unapproved revision (v3i)


@unittest.skipUnless(HAVE, MISSING_REASON)
class DraftsTabUnitTests(unittest.TestCase):
    def test_a3_a_new_draft_asks_the_app_to_bring_drafts_forward_and_opens_no_view_tab(self):
        moved, mounted = [], []
        chat = SimpleNamespace(mount=lambda widget, **kw: mounted.append(widget), children=[])
        screen = SimpleNamespace(app=SimpleNamespace(move_tab=moved.append), sendable_drafts={"draft:1": object()},
                                 view_tabs=[], draft_reply_widget=lambda draft: None, plan_possible=lambda: True,
                                 query_one=lambda selector, *kind: chat,
                                 scroll_chat_end=lambda: None, call_after_refresh=lambda *a: None,
                                 render_chat=lambda: None)
        CardHost.on_draft_saved(screen, card_kinds.DraftSaved("draft:1", object()))
        self.assertEqual((moved, len(mounted), screen.view_tabs), ([ui.TAB_DRAFTS], 1, []))
        self.assertEqual(mounted[0].content.plain, card_tests.strings.text("chat.draft_saved") + " "
                         + card_tests.strings.text("chat.draft_send"))        # one line; a card would carry buttons
        screen.plan_possible = lambda: False  # `/plan` cannot send now (a stage runs): the first sentence alone
        CardHost.on_draft_saved(screen, card_kinds.DraftSaved("draft:1", object()))
        self.assertEqual(mounted[1].content.plain, card_tests.strings.text("chat.draft_saved"))
        CardHost.on_draft_saved(screen, card_kinds.DraftSaved("draft:2", object()))
        self.assertEqual((moved, len(mounted)), ([ui.TAB_DRAFTS] * 2, 2))     # sent or retired before: nothing

    def test_the_tab_text_lists_goal_drafts_newest_first_and_says_so_when_empty(self):
        self.assertEqual(card_kinds.draft_tab_text(()).plain, card_tests.strings.text("canvas.drafts_empty"))


if __name__ == "__main__":
    unittest.main()
