"""F9: after an approval or a start the canvas shows the work once, unless the owner chose a tab since.

Textual Pilot over a real temporary Git repository and the fixture store, as `test_tui_milestones`. No provider, no
network. They need Textual and skip without it."""

import unittest

from terminal_planner.authority import Authority
from test_tui_milestones import MilestoneShell
from tui_support import HAVE_TEXTUAL

STARTED = "M1 started · plan r1 · attempt 1"


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is unavailable: ZPLAN_TEST_WHEELHOUSE with textual 8.2.8 wheels is needed")
class CanvasFollowTests(MilestoneShell):
    def setUp(self):
        super().setUp()
        from terminal_planner.tui import app as ui
        self.ui = ui

    def tab(self):
        return self.app.query_one("#right", self.ui.TabbedContent).active

    def put(self, tab):
        """Show `tab` the way the app's start choice does: not an owner choice (`owner_tab` stays as it was)."""
        self.app.query_one("#right", self.ui.TabbedContent).active = tab

    async def architect_start(self, pilot):
        """M1 started through the controller alone, as the architect's tool does: the screen's own start path
        (`begin_run`) is not involved, so only the snapshot poll can tell the app."""
        box = []
        self.app.controller.preview_start("M1", lambda outcome, error: box.append((outcome, error)))
        await self.until(pilot, lambda: box)
        self.assertEqual(box[0][0].kind, "preview", box)
        self.app.controller.start_run(box[0][0].data, lambda outcome, error: box.append((outcome, error)))
        await self.until(pilot, lambda: len(box) == 2)
        self.assertEqual(box[1][0].kind, "started", box)

    async def poll(self, pilot):
        """One snapshot the UI applied, then a settled render."""
        before = self.app.snapshot
        self.app.request_refresh()
        await self.until(pilot, lambda: self.app.snapshot is not before)
        await pilot.pause(0.3)

    async def test_f1_f4_an_approval_and_a_start_show_their_tab_once_by_any_path(self):
        """F1 + F4: the owner's `decide` approves r1 -> Plan once, and the poll that reports r1 approved moves
        nothing; a run the architect starts (a second writer on the store, as `zplan_start` is) -> the poll shows the
        Scheme tab and `M1 started · plan r1 · attempt 1` once on the run lines, and the next poll moves and adds
        nothing. The tab is put back with `put`, which is no owner choice.

        Interpretation: «shows once» is per revision and per run id, not per poll; the start line is the owner's own
        wording, written by `follow_runs` for a run `begin_run` did not start."""
        with Authority(self.state, self.project, fixture_id="test") as a:
            self.begin(a)
            self.propose(a)  # r1 proposed, not approved
        self.driver.gate.clear()
        async with self.shell(self.controller(), follow=True) as pilot:
            await self.loaded(pilot)
            self.put(self.ui.TAB_LIVE)
            self.app.decide("approve", 1)
            await self.until(pilot, lambda: self.tab() == self.ui.TAB_PLAN)
            self.put(self.ui.TAB_LIVE)
            await self.poll(pilot)
            self.assertEqual(self.app.snapshot.status, "approved")
            self.assertEqual(self.tab(), self.ui.TAB_LIVE)  # keyed by the revision: the poll does not move it again
            self.put(self.ui.TAB_PLAN)
            await self.architect_start(pilot)
            await self.poll(pilot)
            self.assertEqual(self.tab(), self.ui.TAB_LIVE)
            self.put(self.ui.TAB_PLAN)
            await self.poll(pilot)
            self.assertEqual(self.tab(), self.ui.TAB_PLAN)
            self.assertEqual(list(self.app.run_lines).count(STARTED), 1, list(self.app.run_lines))

    async def test_f2_f3_the_snapshot_at_start_is_a_baseline_and_the_owner_choice_wins_until_the_next_send(self):
        """F3: a store that holds an approved r1 and a running M1 at the first snapshot moves nothing and writes no
        started line. F2: after `→` the owner's tab stays when a run starts, after `←` when a revision is approved;
        a command (`/theme`) ends that choice, and the next approval moves the tab again; a click on a label is a choice.
        The app's own events are driven through `run_started` / `plan_approved`, the methods the poll and the
        owner's start call.

        Interpretation: a chat send ends the owner's choice the same way a command does; the chat of this fixture
        is not ready, so the reset is read through the command."""
        self.approve(running=True)
        self.driver.gate.clear()
        async with self.shell(self.controller(), follow=True) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            self.assertEqual(self.tab(), self.ui.TAB_LIVE)
            self.put(self.ui.TAB_PLAN)
            await self.poll(pilot)
            self.assertEqual(self.tab(), self.ui.TAB_PLAN)
            self.assertFalse([line for line in self.app.run_lines if "started" in line], list(self.app.run_lines))
            await pilot.press("left")  # the owner's own choice: Scheme -> Plan -> Scheme
            await pilot.press("right")
            self.assertEqual(self.tab(), self.ui.TAB_PLAN)
            self.app.run_started("run-new")
            self.assertEqual(self.tab(), self.ui.TAB_PLAN)
            await pilot.press("left")
            self.assertEqual(self.tab(), self.ui.TAB_LIVE)
            self.app.plan_approved(2)
            self.assertEqual(self.tab(), self.ui.TAB_LIVE)
            await self.command(pilot, "/theme")
            self.app.plan_approved(3)
            await self.until(pilot, lambda: self.tab() == self.ui.TAB_PLAN)
            await pilot.click("#--content-tab-%s" % self.ui.TAB_LIVE)  # a click on a label is the owner's choice too
            await self.until(pilot, lambda: self.tab() == self.ui.TAB_LIVE)
            self.app.plan_approved(4)
            self.assertEqual(self.tab(), self.ui.TAB_LIVE)
