"""R-A: high defects of the 0.5.2 bug hunt — a stale draft card after a restart and the focus after Esc. One
regression test per criterion; each fails on the unfixed code. (C3, the dirty-tree line, went with the refusal itself:
D4a, tests/test_dirty_head.py.)

Interpretations (the worker's summary never reaches the reviewers):

- C1: «never opens on mount or refresh» is checked where the decision is made, `MainScreen.refresh_draft_card` (the
  real method on the card contract's stand-in screen). The draft is compared with the plan identity the screen's own
  snapshot names (`chat.stale_reason`); until the first snapshot arrives the screen cannot tell, so it opens nothing
  and the key stays unseen for the next refresh. A card already open when the plan moves on stays open (its `/plan`
  is refused as stale, test_tui_draft_card A3).
- C2: the goal form's retained text as a draft state went with the form (K1b); its test is removed.
- C4 -> C1 (attempt 3): the focus goes back to the widget that had it when the plan screen (opened by the owner
  from the main screen, `PlanScreen.from_main`) or Settings opened — `ZplanApp.leave_to_input` hands the main
  screen's own `focused` to `on_screen_resume`. The pane case (Tab, `p`, Esc, `i`) is test_tui_milestones a3 and
  test_tui_chat c7, unchanged.
"""

import unittest
from types import SimpleNamespace

import tui_support  # noqa: F401  (the offline wheelhouse joins `sys.path` before the guarded imports)
from tui_support import HAVE_TEXTUAL, screen_lines

from test_tui_draft_card import GOAL_DRAFT, NO_PLAN, _DraftScreen, draft_chat
from test_tui_milestones import MilestoneShell

try:
    from terminal_planner.tui import app as ui
except ImportError:  # pragma: no cover - the bare import scan of tests.test_toolchain covers this path
    ui = None

PROPOSED = {"status": "proposed", "override": None}


def snapshot(version, status=None):
    return SimpleNamespace(rows=(), plan=None, version=version, status=status,
                           plan_state=PROPOSED if version is not None else None)


def goal_reply(identity):
    return [{"role": "owner", "text": "вопрос"},
            {"role": "architect", "status": "completed", "text": "Вот черновик.",
             "drafts": [{"kind": "goal", "text": GOAL_DRAFT, "milestone": None, "identity": identity}]}]


@unittest.skipUnless(ui is not None, "Rich and Textual are unavailable")
class StaleDraftCardTests(unittest.TestCase):
    def test_c1_a_draft_the_plan_moved_past_opens_no_card(self):
        """Draft d1 (made with no plan), plan r1 exists, restart: no card request, so no draft card and no tab."""
        screen = _DraftScreen(draft_chat(goal_reply(NO_PLAN)))
        screen.app.snapshot = snapshot(1, "proposed")
        screen.refresh_draft_card()
        screen.refresh_draft_card()
        self.assertEqual(screen.posted, [])
        self.assertEqual(screen.draft_cards, {})
        # the draft made against that very plan is current: its card opens
        current = _DraftScreen(draft_chat(goal_reply([1, PROPOSED])))
        current.app.snapshot = snapshot(1, "proposed")
        current.refresh_draft_card()
        self.assertEqual(len(current.posted), 1)


@unittest.skipUnless(HAVE_TEXTUAL, "Textual unavailable: ZPLAN_TEST_WHEELHOUSE with the textual 8.2.8 wheels is needed")
class FocusAfterEscTests(MilestoneShell):
    async def test_c1_esc_from_settings_returns_the_focus_to_the_input_it_was_opened_from(self):
        """C1 (replaces R-A C4): the focus goes back to the widget that had it when the screen opened. The
        pane case (Tab, `p`, Esc, `i`) is test_tui_milestones a3, unchanged. The input case: the pane owned the
        focus once (`tab_owner == "pane"`, left by a switch to the Flow tab that moved the focus to the input),
        the owner opens Settings from the input, and a switch to the Plan tab happens under it (it only defers
        the focus move). On Esc main hands the focus to the pane although the input held it, and the typed `/run`
        fires pane letter keys; with C1 the input keeps it. Interpretation: the switch under Settings is made by
        calling `show_tab` (what an arriving state change does); the plan screen goes through the same code path
        (`ZplanApp.leave_to_input`), so one screen is driven here."""
        self.approve(running=False)
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            main = self.app.screen
            await self.until(pilot, lambda: getattr(self.app.focused, "id", None) == "input")
            await pilot.press("tab")
            await self.until(pilot, lambda: getattr(self.app.focused, "id", None) == "plan-pane")
            main.show_tab(ui.TAB_LIVE)  # the pane held the focus: it moves to the input, the pane stays the owner
            await self.until(pilot, lambda: getattr(self.app.focused, "id", None) == "input")
            await self.command(pilot, "/setup")
            await self.until(pilot, lambda: type(self.app.screen).__name__ == "SettingsScreen")
            main.show_tab(ui.TAB_PLAN)  # under Settings: the focus move is only deferred
            await pilot.press("escape")
            await self.until(pilot, lambda: type(self.app.screen).__name__ == "MainScreen")
            await pilot.pause(0.2)
            self.assertEqual(getattr(self.app.focused, "id", None), "input")
            await self.type(pilot, "/run")
            await pilot.pause(0.2)
            self.assertEqual(main.query_one("#input").value, "/run")  # no pane action fired
            self.assertEqual(type(self.app.screen).__name__, "MainScreen")
            self.assertNotIn("Start M1", "\n".join(screen_lines(self.app)))


if __name__ == "__main__":
    unittest.main()
