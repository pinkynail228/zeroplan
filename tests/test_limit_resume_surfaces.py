# tests/test_limit_resume_surfaces.py
"""The surfaces of the provider limit pause: the open app's tick calls `Controller.resume_due`, `paused` has its words,
tone and reference row, and the architect's rules say what to do about a pause and a second limit.

The tick walks need Textual and skip without it; the module itself imports without it (tests.test_toolchain)."""
import contextlib
import io
from pathlib import Path
import unittest
from unittest.mock import patch

# imported first for its side effect: the offline wheelhouse joins `sys.path`, and the language is pinned.
import tui_support  # noqa: F401
from tui_support import HAVE_TEXTUAL

from terminal_planner import architect, catalog
from terminal_planner.runs import MilestoneRuns
from terminal_planner.tui import chat as chat_module
from terminal_planner.tui import strings

import test_bridge as tb
import test_terminal_planner as tp
from test_terminal_planner import ROLES
from test_tui_draft_card import MISSING_REASON
from test_tui_milestones import MilestoneShell

try:
    from terminal_planner.tui import app as ui
    from terminal_planner.tui.controller import Controller
except ImportError:  # pragma: no cover - the bare import scan of tests.test_toolchain covers this path
    ui = Controller = None

HAVE = HAVE_TEXTUAL and ui is not None
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "REFERENCE.md"
NOON = "2026-11-04T12:00:00Z"
RESET = "3:10pm (UTC)"
MOMENT = "2026-11-04T15:12:00Z"  # the reset plus the 120-second margin


class VocabularyTests(unittest.TestCase):
    def test_paused_has_a_word_in_every_language_and_an_idle_tone(self):
        words = strings.CATALOG["step.run.paused"]
        self.assertEqual(set(words), {"en", "ru", "zh"})
        self.assertTrue(all(words.values()))
        tone, text, _ = chat_module.step_of("M1 attempt 1: running -> paused")
        self.assertEqual(tone, "idle")
        self.assertIn(strings.text("step.run.paused"), text)

    def test_the_generated_reference_documents_paused(self):
        self.assertIn("paused", catalog.MILESTONE_STATE)
        self.assertIn("`paused`", catalog.generated("milestone_state"))
        self.assertIn("`paused`", REFERENCE.read_text(encoding="utf-8"))
        with contextlib.redirect_stdout(io.StringIO()):
            status = catalog.main(["--check", str(REFERENCE)])
        self.assertEqual(status, 0)

    @unittest.skipUnless(HAVE, MISSING_REASON)
    def test_the_tick_runs_every_thirty_seconds(self):
        self.assertEqual(ui.RESUME_SECONDS, 30.0)


class ArchitectRuleTests(unittest.TestCase):
    def test_the_rules_leave_a_paused_milestone_alone_and_report_a_second_limit(self):
        rules = " ".join(" ".join(architect.TOOL_RULES).split())
        self.assertIn("A paused milestone: do nothing", rules)
        self.assertIn("do not resume it now; report the reset", rules)
        self.assertEqual(sum("zplan_resume" in line for line in architect.TOOL_RULES), 1)

    def test_the_method_carries_the_limit_rule_within_its_size(self):
        method = architect.method()
        self.assertIn("A provider limit pauses a run", method)
        self.assertLessEqual(len(method.encode("utf-8")), 4600)


@unittest.skipUnless(HAVE, MISSING_REASON)
class PausedTickTests(MilestoneShell):
    """The whole app over a real store and the gated fixture driver, with a fast tick and the clock in hand."""

    write_auto_profile = tb.BridgeCase.write_auto_profile
    finish = staticmethod(tb.BridgeCase.finish)

    def setUp(self):
        super().setUp()
        self.now = NOON
        for patcher in (patch("terminal_planner.runs.now", lambda: self.now),
                        patch.object(ui, "RESUME_SECONDS", 0.05)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def paused(self):
        """M1 paused on a provider limit under an accepted auto profile; returns the paused record."""
        self.write_auto_profile()
        self.driver.outcomes = ("failed_limit",)
        self.driver.reset = RESET
        self.approve(running=False)
        with tp.Authority(self.state, self.project) as authority:
            runs = MilestoneRuns(authority, self.driver, worktrees=authority.directory / "worktrees")
            return self.finish(runs, runs.start("M1", 1, ROLES))

    def m1(self):
        return next(row for row in self.app.rows() if row.id == "M1")

    def main(self):
        return next(screen for screen in self.app.screen_stack if type(screen).__name__ == "MainScreen")

    def counted(self, calls):
        """A spy on the controller's method that still runs it."""
        real = Controller.resume_due

        def spy(controller, *args, **kwargs):
            calls.append(controller)
            return real(controller, *args, **kwargs)
        return patch.object(Controller, "resume_due", spy)

    async def test_the_tick_resumes_a_due_attempt_and_the_app_follows_it(self):
        self.paused()
        self.now = MOMENT
        async with self.shell(self.controller(profile=True), follow=True) as pilot:
            await self.loaded(pilot)
            await self.until(pilot, lambda: self.m1().token.run_id.endswith("-r"))
            await self.until(pilot, lambda: self.m1().state == "awaiting_merge")

    async def test_the_tick_leaves_an_attempt_paused_before_its_moment(self):
        record = self.paused()
        self.assertEqual(record["resume_at"], MOMENT)
        calls = []
        with self.counted(calls):
            async with self.shell(self.controller(profile=True), follow=True) as pilot:
                await self.loaded(pilot)
                await self.until(pilot, lambda: self.m1().state == "paused", 5.0)
                await self.until(pilot, lambda: len(calls) >= 2, 5.0)
                await pilot.pause(0.2)
                self.assertEqual((self.m1().state, self.m1().token.run_id), ("paused", record["run_id"]))

    async def test_the_tick_posts_no_job_while_nothing_is_paused(self):
        self.approve(running=False)
        calls = []
        with self.counted(calls):
            async with self.shell(self.controller()) as pilot:
                await self.loaded(pilot)
                await pilot.pause(0.4)
                self.assertEqual(calls, [])

    async def test_a_paused_row_shows_no_failed_card_and_no_error_state(self):
        self.paused()
        async with self.shell(self.controller(profile=True)) as pilot:
            await self.loaded(pilot)
            await self.until(pilot, lambda: self.m1().state == "paused", 5.0)
            await pilot.pause(0.2)
            self.assertEqual([key for key in self.main().card_specs if key.startswith("failed:")], [])
            self.assertNotEqual(ui.screen_slash_state(self.app), "error")


if __name__ == "__main__":
    unittest.main()
