"""P1b: `/stop` stops a running planner from the TUI (0.6.0, run p1b), one smoke test per criterion.

Pilot tests over the fixture store and a planner double (`test_tui_planning.Planner`) that keeps the revision's
run "running" across watch slices; its `force_stop` counts the calls and ends the run as a force-stopped failure,
which `Authority.commit_terminal` concludes as `stopped` because the request was saved first. No provider, no
network. The milestone stop is p1b's S4 and keeps its own tests (`test_tui`, `test_tui_live`).

Interpretations (the worker's summary never reaches a reviewer):

* "the chat shows the stopped-plan card" is read as the existing failure card of `card_kinds.failed_card_source`
  (red card, restart button «new attempt»), which now also names an owner-stopped revision: `"stopped"` joined
  `FAILED_PLAN_STATUS` (card_kinds.py:687, one constant outside the task's write-set but the only place the card is
  decided: on the base `failed_plan_view` does not match a `stopped` view, so the orchestrator must either widen
  the write-set by this line or name another reuse path; reverting it fails test_s2), so the card shows the view's own cause line «Plan rN stopped by you at HH:MM.» (the stop time is the
  stored UTC stamp, so the test matches the line up to the clock; the line is the services' text, so the test
  anchors on the revision and the clock, not on the words).
* "the bar no longer reads planning" is read through the slash state (`screen_slash_state`): it is anything but `planning`
  (the fixture double's watch raises Blocked, so the bar shows the progress error; otherwise it would be idle).
* "a refusal ... a second `/stop` asks again" is read as: the confirmation opens again and, answered «yes», calls
  `Planning.stop()` a second time (each refused call is counted by the double).
"""

import re
import unittest

from terminal_planner.authority import Blocked
from test_tui_planning import Planner, PlanningShell
from tui_support import HAVE_TEXTUAL, screen_text


def screen_slash_state(app):
    """The app's slash state; imported on use so the module imports without Textual or Rich (test_toolchain)."""
    from terminal_planner.tui.app import screen_slash_state as state
    return state(app)


class StoppablePlanner(Planner):
    """The planner double with a native-like `force_stop`: counts its calls, can refuse, and ends the run."""

    def __init__(self):
        super().__init__()
        self.force_stops = 0
        self.refuse = None
        self.stopped = False

    def force_stop(self, binding, run_id, cwd):
        self.force_stops += 1
        if self.refuse:
            raise Blocked(self.refuse, family="plan.stop_unconfirmed")
        self.stopped = True

    def proposal(self, authority, progress, slice=None):
        if self.stopped:
            self.fail(authority, "force_stopped")  # commit_terminal: a saved stop request makes this `stopped`
            raise Blocked("run_failed: force_stopped", family="plan.failed")
        return super().proposal(authority, progress, slice)


@unittest.skipUnless(HAVE_TEXTUAL, "Textual unavailable: ZPLAN_TEST_WHEELHOUSE with the textual 8.2.8 wheels is needed")
class StopPlanningTests(PlanningShell):
    def setUp(self):
        super().setUp()
        self.planner = StoppablePlanner()
        self.planner.running = True
        self.plan(receipt=True)

    async def planning(self, pilot):
        await self.loaded(pilot)
        await self.until(pilot, lambda: screen_slash_state(self.app) == "planning")

    async def confirm_open(self, pilot):
        await pilot.press("slash", *"stop", "enter")
        await self.until(pilot, lambda: type(self.app.screen).__name__ == "ConfirmScreen")

    async def test_s1_stop_is_offered_while_the_planner_runs_and_no_leaves_it_running(self):
        async with self.shell(size=(120, 40)) as pilot:
            await self.planning(pilot)
            await self.confirm_open(pilot)
            self.assertIn("Stop planning of plan r1?", screen_text(self.app))
            await self.press_button(pilot, "no")
            await self.until(pilot, lambda: type(self.app.screen).__name__ != "ConfirmScreen")
            self.assertEqual(self.planner.force_stops, 0)
            self.assertEqual(screen_slash_state(self.app), "planning")

    async def test_s2_yes_stops_once_off_the_ui_thread_and_the_chat_shows_the_stopped_card(self):
        async with self.shell(size=(120, 40)) as pilot:
            await self.planning(pilot)
            await self.confirm_open(pilot)
            await self.press_button(pilot, "yes")
            # the view's cause line, "Plan r1 stopped by you at HH:MM."
            await self.until(pilot, lambda: re.search(r"r1 .*\d\d:\d\d\.", self.flat()))
            self.assertIn("try again", self.flat())  # the card's restart button
            self.assertEqual(self.planner.force_stops, 1)
            self.assertNotEqual(screen_slash_state(self.app), "planning")
        self.assertEqual(self.stored()["revisions"][0]["status"], "stopped")

    async def test_s3_a_refused_stop_shows_one_line_keeps_planning_and_asks_again(self):
        self.planner.refuse = "Zeroshot отклонил остановку"
        async with self.shell(size=(120, 40)) as pilot:
            await self.planning(pilot)
            for expected in (1, 2):
                await self.confirm_open(pilot)
                await self.press_button(pilot, "yes")
                await self.until(pilot, lambda: self.planner.force_stops == expected)
                await self.until(pilot, lambda: "Not done: " in self.flat())
                await self.until(pilot, lambda: type(self.app.screen).__name__ != "ConfirmScreen")
                self.assertEqual(self.status_text().count("Not done: "), 1)
                self.assertIn("Zeroshot отклонил остановку", self.flat())
                self.assertEqual(screen_slash_state(self.app), "planning")


if __name__ == "__main__":
    unittest.main()
