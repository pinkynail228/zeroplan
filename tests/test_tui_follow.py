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
        Plan tab and `M1 started · plan r1 · attempt 1` once on the run lines, and the next poll moves and adds
        nothing. The tab is put back with `put`, which is no owner choice.

        v3h: a start shows the Plan tab (not Scheme), once per run.

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
            self.put(self.ui.TAB_LIVE)
            await self.architect_start(pilot)
            await self.poll(pilot)
            self.assertEqual(self.tab(), self.ui.TAB_PLAN)  # v3h A1: the start brings Plan forward, not Scheme
            self.put(self.ui.TAB_LIVE)
            await self.poll(pilot)
            self.assertEqual(self.tab(), self.ui.TAB_LIVE)  # once per run: the next poll moves nothing
            self.assertEqual(list(self.app.run_lines).count(STARTED), 1, list(self.app.run_lines))

    async def test_v3i_the_plan_tab_shows_the_approved_plan_and_drafts_the_unapproved_revision(self):
        """v3i A2 + A3 + A1: with only r1 proposed Plan says there is no approved plan and Drafts holds r1's plan
        text; approving r1 puts it on Plan (which comes forward) and takes it off Drafts; a later proposed r2 leaves
        Plan on r1 and shows r2 in Drafts, above the goal drafts' place.

        Interpretation: the store refuses a new revision while a stage runs, so «r1 approved» here has no stage
        running, and r2 is written between two sessions (the app holds the project lock); r1's progress line is the one the approved view carries (`Delivery.approved`)."""
        with Authority(self.state, self.project, fixture_id="test") as a:
            self.begin(a)
            self.propose(a)
        self.driver.gate.clear()
        async with self.shell(self.controller(), follow=True) as pilot:
            await self.loaded(pilot)
            drafts = lambda: self.app.main_screen().query_one("#drafts").content.plain
            await self.plan_shows(pilot, "No approved plan yet: the proposal is in Drafts.")
            self.assertNotIn("Plan r1", self.pane_flat())
            self.assertIn("Plan r1 · proposed", drafts())
            self.put(self.ui.TAB_LIVE)
            self.app.decide("approve", 1)  # A3: the action acts on the current revision as before
            await self.until(pilot, lambda: self.tab() == self.ui.TAB_PLAN)
            await self.plan_shows(pilot, "Plan r1 · approved")
            self.assertNotIn("No approved plan yet", self.pane_flat())
            self.assertNotIn("Plan r1", drafts())
        with Authority(self.state, self.project, fixture_id="test") as a:  # A1: a newer revision, proposed
            self.begin(a)
            self.propose(a)
        async with self.shell(self.controller(), follow=True) as pilot:
            await self.loaded(pilot)
            drafts = lambda: self.app.main_screen().query_one("#drafts").content.plain
            await self.plan_shows(pilot, "Plan r1 · approved")
            self.assertEqual((self.app.snapshot.version, self.app.snapshot.status), (2, "proposed"))
            self.assertIn("Plan r1 · approved", self.pane_flat())
            self.assertNotIn("Plan r2", self.pane_flat())
            self.assertIn("Plan r2 · proposed", drafts())
            self.assertNotIn("Plan r1", drafts())

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
            self.app.run_started("run-newer")  # v3h A2: the owner moved to Scheme, so a start leaves it
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

    async def test_u5a_the_planners_end_brings_the_plan_tab_forward_unless_the_owner_chose_a_tab(self):
        """u5a A1 + A2 (v3i: Drafts): the planner's «done» and «failed» ends move to the Drafts tab through `move_tab` and
        say where the plan is (not `/view`); with the owner's tab chosen since their last command the tab stays and the note still
        shows; «stale» keeps its note and moves nothing. The ends are driven through `watched`, the method the
        planner's observation calls.

        Interpretation: «a goal sent, no tab chosen since» is the state after a command (`/theme`), which resets
        `owner_tab` the way a chat send does; the chat of this fixture is not ready."""
        from types import SimpleNamespace
        end = lambda kind: self.app.watched(SimpleNamespace(kind=kind), None)
        self.approve(running=True)
        self.driver.gate.clear()
        async with self.shell(self.controller(), follow=True) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            await self.command(pilot, "/theme")  # a command: no tab chosen since
            for kind, note in (("done", "The planner finished; the plan is in Drafts."),
                               ("failed", "Planning stopped; Drafts shows why.")):
                self.put(self.ui.TAB_LIVE)
                end(kind)
                self.assertEqual((self.tab(), self.app.finish_note), (self.ui.TAB_DRAFTS, note), kind)
            self.put(self.ui.TAB_LIVE)
            end("stale")
            self.assertEqual((self.tab(), self.app.finish_note), (self.ui.TAB_LIVE, self.ui.PLAN_OUTDATED))
            await pilot.press("left")  # the owner's own choice: the app moves nothing after it
            self.put(self.ui.TAB_LIVE)
            self.assertTrue(self.app.main_screen().owner_tab)
            end("done")
            self.assertEqual((self.tab(), self.app.finish_note),
                             (self.ui.TAB_LIVE, "The planner finished; the plan is in Drafts."))
