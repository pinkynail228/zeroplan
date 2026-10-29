"""D6: the goal draft tab closes once its plan exists.

D1: a draft card sent with `/plan` becomes its receipt and keeps its «Goal draft» tab only until the snapshot names
the plan built from it; then the tab closes and the pane shows the tab it showed before the draft (here the plan
tab). D3: a sent draft whose plan is not in the snapshot yet keeps its tab (unit level, stand-in screen).
(D2, a merged line in the history, was taken out by the orchestrator: it cost an architect turn per merge.)

Interpretations:
- «its plan revision exists» is the snapshot naming a plan (`snapshot.version`) whose identity the draft is stale
  against, the same test `retire_stale_draft_cards` applies to an open card.
"""

import unittest
from types import SimpleNamespace

import tui_support  # noqa: F401
import test_tui_draft_card as card_tests

from terminal_planner.tui import chat as chat_module

HAVE, MISSING_REASON = card_tests.HAVE, card_tests.MISSING_REASON

if HAVE:
    from terminal_planner.tui import app as ui
    from terminal_planner.tui.card_host import CardHost


@unittest.skipUnless(HAVE, MISSING_REASON)
class DraftTabEndsTests(card_tests.DraftCardShell):
    async def test_d1_a_sent_drafts_tab_closes_once_its_plan_exists(self):
        async with self.shell(size=(120, 40), store=self.seed_goal_draft()) as pilot:
            await self.settled(pilot)
            await self.card_shown(pilot)
            main = self.main()
            self.assertEqual(len(main.view_tabs), 1)
            await self.choose(pilot, "/plan")
            await self.until(pilot, lambda: self.app.snapshot.version is not None and not main.view_tabs)
            self.assertEqual(main.sent_drafts, {})
            self.assertEqual(main.query_one("#right").active, ui.TAB_PLAN)


@unittest.skipUnless(HAVE, MISSING_REASON)
class SentDraftUnitTests(unittest.TestCase):
    def test_d3_a_sent_draft_keeps_its_tab_until_the_snapshot_names_a_plan(self):
        closed = []
        draft = SimpleNamespace(identity=chat_module.NO_PLAN)
        screen = SimpleNamespace(app=SimpleNamespace(snapshot=SimpleNamespace(version=None, plan_state=None)),
                                 draft_cards={}, sent_drafts={"draft:1": draft}, view_paths={"tab-view-1": "draft:1"},
                                 view_tabs=["tab-view-1"], close_view_tab=closed.append,
                                 plan_identity_now=lambda: chat_module.NO_PLAN)
        screen.close_draft_tab = lambda key: CardHost.close_draft_tab(screen, key)
        CardHost.retire_stale_draft_cards(screen)
        self.assertEqual((closed, list(screen.sent_drafts)), ([], ["draft:1"]))
        screen.app.snapshot = SimpleNamespace(version=1, plan_state="unsent")
        screen.plan_identity_now = lambda: [1, "unsent"]
        CardHost.retire_stale_draft_cards(screen)
        self.assertEqual((closed, screen.sent_drafts), (["tab-view-1"], {}))

if __name__ == "__main__":
    unittest.main()
