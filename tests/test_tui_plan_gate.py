"""G1b: the argued plan gate in the full-screen UI. Same texts as the line UI; no approval without the critic's
acceptance; a stale gate is refused on the action. Pilot tests over the fixture store (they need Textual)."""

import unittest

from terminal_planner.authority import Authority, Blocked
from terminal_planner.engine import FixtureEngine
from terminal_planner.planning import Planning, one_line
from test_tui_planning import GOAL, PlanningShell
import test_process as tpr
from test_terminal_planner import ROLES
from tui_support import HAVE_TEXTUAL, screen_text


@unittest.skipUnless(HAVE_TEXTUAL, "Textual unavailable: ZPLAN_TEST_WHEELHOUSE with the textual 8.2.8 wheels is needed")
class PlanGateShell(tpr.ProfileTest, PlanningShell):
    def argued(self, scenario):
        with Authority(self.state, self.project, fixture_id="test") as authority:
            authority.begin(GOAL, ROLES, "fixture")
            try:
                FixtureEngine(scenario).proposal(authority, lambda _: None)
            except Blocked:
                pass
            return list(Planning.gate_lines(authority.current["evidence"]))

    async def open_plan(self, pilot):
        await self.loaded(pilot)
        await self.panel(pilot)  # D4: the input has the start focus; [p] is a pane key
        await self.command(pilot, "/view")
        await self.until(pilot, lambda: type(self.app.screen).__name__ == "PlanScreen")

    async def test_an_exhausted_plan_shows_its_rounds_and_cannot_be_approved(self):
        from terminal_planner.tui.app import plan_tab_line
        lines = self.argued("exhausted")
        self.assertTrue(lines)  # the exhausted rounds, in the services' words (not pinned here)
        async with self.shell(size=(140, 50)) as pilot:
            await self.open_plan(pilot)
            await self.press_button(pilot, "info")
            await pilot.pause(0.3)
            flat = self.flat()
            for line in lines:  # the very text of the line UI, its letter keys as the TUI steps (K1d)
                self.assertIn(" ".join(plan_tab_line(line).split()), flat)
            await pilot.press("escape")
            await pilot.pause(0.2)
            self.assertFalse(self.app.screen.query("#plan-buttons-approve"))  # not offered: no button to press
            self.assertNotIn("Approve plan r1?", screen_text(self.app))
        self.assertEqual(self.stored()["revisions"][0]["status"], "review_exhausted")

    async def test_an_accepted_plan_after_a_dispute_is_approved(self):
        lines = self.argued("dispute")
        self.assertTrue(lines)  # the planner's dispute response is among the services' lines (their words are not pinned)
        async with self.shell(size=(140, 50)) as pilot:
            await self.open_plan(pilot)
            await self.press_button(pilot, "approve")  # p4a: the button is the consent, no second question
            await self.until(pilot, lambda: self.app.snapshot.status == "approved")
            await pilot.pause(0.5)
        self.assertEqual(self.stored()["revisions"][0]["status"], "approved")

    async def test_a_stale_gate_is_refused_on_the_action_and_writes_nothing(self):
        self.rules("AGENTS.md", "one\n")
        self.accept_file()
        with self.app() as app:
            app.planning.begin("Goal", app.roles)
            FixtureEngine().proposal(app.authority, lambda _: None)
        (self.project / "AGENTS.md").write_text("two\n")
        before = self.sidecar().parent.joinpath("planning.json").read_bytes()
        async with self.shell(self.controller(profile=True), size=(140, 50)) as pilot:
            await self.open_plan(pilot)
            await self.press_button(pilot, "approve")
            await self.shows(pilot, "/view → revise")  # the refusal's `[r]` hint as the TUI step (K1d glossary)
        self.assertEqual(self.sidecar().parent.joinpath("planning.json").read_bytes(), before)
        self.assertEqual(self.stored()["revisions"][0]["status"], "proposed")

    # G1b-override: the owner approves a rejected gate with a reason ---------------------------------------------

    def planning_json(self):
        return self.sidecar().parent / "planning.json"

    async def test_o4_the_override_form_cancels_refuses_a_too_long_reason_and_approves_with_a_valid_one(self):
        self.argued("exhausted")
        path = self.planning_json()
        before = path.read_bytes()
        verdict_text = one_line(self.stored()["revisions"][0]["evidence"]["findings"], 300)[:40]
        async with self.shell(size=(140, 50)) as pilot:
            await self.open_plan(pilot)
            self.assertTrue(self.app.screen.query("#plan-buttons-override"))  # offered next to revise/restart
            self.assertFalse(self.app.screen.query("#plan-buttons-approve"))  # the ordinary approval is not offered
            await self.press_button(pilot, "override")
            await self.shows(pilot, "Approve plan r1 despite the check?")
            await pilot.press("escape")
            await pilot.pause(0.3)
            self.assertNotIn("Approve plan r1 despite the check?", screen_text(self.app))
            self.assertEqual(path.read_bytes(), before)
            await self.press_button(pilot, "override")
            await self.shows(pilot, "Approve plan r1 despite the check?")
            await self.type(pilot, "x" * 501)
            await self.press_button(pilot, "send")
            await self.shows(pilot, "at most 500")  # the refusal names the reason length limit
            self.assertEqual(path.read_bytes(), before)
            await self.press_button(pilot, "override")
            await self.shows(pilot, "Approve plan r1 despite the check?")
            await self.type(pilot, "the owner accepts the broad scope")
            await self.press_button(pilot, "send")
            await self.until(pilot, lambda: type(self.app.screen).__name__ == "PlanScreen")  # the form closed
            await self.shows(pilot, "the owner accepts the broad scope")
            flat = self.flat()
            self.assertIn(verdict_text, flat)  # the verdict is never hidden
            await self.press_button(pilot, "info")
            await pilot.pause(0.3)
            self.assertGreaterEqual(self.flat().count("the owner accepts the broad scope"), 2)
            await pilot.press("escape", "escape")
            await self.until(pilot, lambda: type(self.app.screen).__name__ == "MainScreen")
        stored = self.stored()["revisions"][0]
        self.assertEqual((stored["status"], stored["override"]["reason"], stored["override"]["verdict"]),
                         ("approved", "the owner accepts the broad scope", "rejected"))
        self.assertEqual(stored["evidence"]["critic_verdict"], "rejected")
        async with self.shell(size=(140, 50)) as pilot:  # reopened: still shown, nothing offered to override
            await self.open_plan(pilot)
            flat = self.flat()
            self.assertIn(verdict_text, flat)
            self.assertIn("the owner accepts the broad scope", flat)
            self.assertFalse(self.app.screen.query("#plan-buttons-override"))

    async def test_o4_a_version_one_exhausted_plan_has_no_override_action(self):
        from test_plan_override import V1Rejecting
        with Authority(self.state, self.project, fixture_id="test") as authority:
            authority.begin(GOAL, ROLES, "fixture", execution=1)
            V1Rejecting().proposal(authority, lambda _: None)
            self.assertEqual(authority.current["status"], "review_exhausted")
        path = self.planning_json()
        before = path.read_bytes()
        async with self.shell(size=(140, 50)) as pilot:
            await self.open_plan(pilot)
            self.assertFalse(self.app.screen.query("#plan-buttons-override"))
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.stored()["revisions"][0]["status"], "review_exhausted")

    async def test_o4_an_accepted_plan_offers_no_override(self):
        self.argued("accept")
        async with self.shell(size=(140, 50)) as pilot:
            await self.open_plan(pilot)
            self.assertFalse(self.app.screen.query("#plan-buttons-override"))

    async def test_o4_a_stale_gate_refuses_the_override_and_writes_nothing(self):
        self.rules("AGENTS.md", "one\n")
        self.accept_file()
        with self.app() as app:
            app.planning.begin("Goal", app.roles)
            FixtureEngine("exhausted").proposal(app.authority, lambda _: None)
        (self.project / "AGENTS.md").write_text("two\n")
        path = self.planning_json()
        before = path.read_bytes()
        async with self.shell(self.controller(profile=True), size=(140, 50)) as pilot:
            await self.open_plan(pilot)
            await self.press_button(pilot, "override")
            await self.shows(pilot, "Approve plan r1 despite the check?")
            await self.type(pilot, "the owner accepts the broad scope")
            await self.press_button(pilot, "send")
            await self.shows(pilot, "/view → revise")  # the refusal's `[r]` hint as the TUI step (K1d glossary)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.stored()["revisions"][0]["status"], "review_exhausted")


if __name__ == "__main__":
    unittest.main()
