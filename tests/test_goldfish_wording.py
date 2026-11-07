# tests/test_goldfish_wording.py
"""Owner-facing texts of a Goldfish revision say "plan check", because no planner runs; an older planner revision keeps
its wording (design docs/designs/2026-11-03-egm-planning.md 4.7). Plain views, the real app over the fixture store and
a planner double that stays busy across watch slices; no provider."""
import tui_support  # noqa: F401  bootstraps the offline wheelhouse before Rich

import unittest

from terminal_planner import engine
from terminal_planner.authority import Authority
from terminal_planner.engine import FixtureEngine, NativeEngine
from terminal_planner.planning import Planning

import test_process as tpr
from test_goldfish_planning import briefed
from test_goldfish_tools import goldfish
from test_tui_approve_card import HAVE, MISSING_REASON, ApproveCardShell


class ViewWording(tpr.ProfileTest):
    def session(self):
        self.write({})
        self.accept_file()
        manager = self.app()
        app = manager.__enter__()
        self.addCleanup(manager.__exit__, None, None, None)
        return app

    def goldfish_session(self):
        """A session holding one reviewed goldfish revision: the app and the revision."""
        app = self.session()
        app.planning.plan_draft("Goal", briefed())
        FixtureEngine().proposal(app.authority, lambda _: None)
        return app, app.authority.current

    def test_a_goldfish_revision_says_plan_check_in_every_status(self):
        app, current = self.goldfish_session()
        for status in ("submission_unknown", "observing", "proposal_invalid"):
            current.update(status=status, diagnostic="bad")
            for lines in (app.planning.view().lines, app.delivery.home().lines, app.delivery.details()):
                self.assertNotIn("planner", "\n".join(lines).lower(), status)
        current.update(status="observing")
        self.assertIn("plan check", "\n".join(app.planning.view().lines).lower())

    def test_the_journal_and_the_diagnostics_of_a_goldfish_revision_name_no_planner(self):
        app, current = self.goldfish_session()
        journal = dict(current, live={"journal": [{"at": "2026-11-04T10:00:00Z", "text": "read"}]})
        commands = Planning.planner_commands({"engine": "native", "run_id": "r1", "frozen": {"review": "goldfish"},
                                              "native_binding": {"state_root": "/s", "executable": "/z"}})
        self.assertTrue(commands)
        for lines in (app.delivery.journal_sections(journal), app.delivery.activity()[:1], commands):
            self.assertNotIn("planner", "\n".join(lines).lower())

    def test_an_older_planner_revision_keeps_its_words(self):
        app = self.session()
        self.begin_old_planner(app.authority)
        self.propose(app.authority)
        self.assertIn("planner", "\n".join(app.delivery.details()).lower())
        self.assertIn("planner", app.delivery.activity()[0].lower())
        app.authority.current.update(status="observing")
        self.assertIn("planner", "\n".join(app.planning.view().lines).lower())
        self.assertIn("planner", "\n".join(app.delivery.home().lines).lower())


class AdmittedPhaseWording(unittest.TestCase):
    def test_a_goldfish_run_starts_without_the_planner_and_an_older_one_with_it(self):
        admitted = {"phase": "admitted"}
        phase = engine.PHASES.get("admitted_goldfish", engine.PHASES["admitted"])
        self.assertNotIn("planner", phase.lower())
        self.assertEqual(NativeEngine.phase(None, admitted, "r1", goldfish=True), phase)
        self.assertIn("planner", NativeEngine.phase(None, admitted, "r1").lower())


@unittest.skipUnless(HAVE, MISSING_REASON)
class ScreenWording(ApproveCardShell):
    async def test_a_running_goldfish_review_and_its_finish_name_the_plan_check(self):
        self.planner.running = True
        with Authority(self.state, self.project, fixture_id="test") as authority:
            goldfish(authority, "plan", "owner", reject=False)
            self.planner.receipt(authority)
        async with self.shell(self.controller(), size=(120, 40)) as pilot:
            await self.loaded(pilot)
            await self.until(pilot, lambda: self.app.watching)
            await self.until(pilot, lambda: self.app.snapshot.status in ("observing", "detached"))
            self.assertNotIn("planner", " ".join(self.app.snapshot.plan.lines).lower())
            self.assertNotIn("planner", " ".join(self.app.snapshot.lines).lower())
            self.assertNotIn("planner", self.main().status_summary().lower())

            self.app.progress.clear()  # no await until the read: the watch cannot add a phase line in between
            working = " ".join(self.main().live_status(False)).lower()
            self.assertIn("working", working)
            self.assertNotIn("planner", working)

            block, checks = self.app.plan_block, self.app.checks
            self.app.plan_block, self.app.checks = (object(),), ()
            passed = "\n".join(self.app.block_lines())
            self.app.plan_block, self.app.checks = block, checks
            self.assertNotIn("planner", passed.lower())

            await self.command(pilot, "/view")
            await self.until(pilot, lambda: type(self.app.screen).__name__ == "PlanScreen")
            title = str(self.app.screen.query_one("#plan-progress").border_title)
            self.assertNotIn("planner", title.lower())
            await pilot.press("escape")

            self.planner.running = False
            await self.until(pilot, lambda: self.app.finish_note)
            self.assertIn("plan check", self.app.finish_note.lower())
            self.assertNotIn("planner", self.app.finish_note.lower())


if __name__ == "__main__":
    unittest.main()
