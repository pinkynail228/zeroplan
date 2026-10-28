"""README screenshots: the real zplan full-screen shell in five moments of one session, as SVG.

Run from the repo root (same environment as devtools/fasttest.py; XDG_DATA_HOME unset so nothing reaches your data):
  env -u XDG_DATA_HOME TMPDIR=$(mktemp -d /tmp/zs.XXXX) ZPLAN_TEST_WHEELHOUSE=~/.cache/zplan-wheelhouse \
    PYTHONPATH=.:tests ZPLAN_SHOTS=docs/img python3.13 devtools/ui-lab/readme_shots.py
Every screen is the shipped app on the test harness's fixture stores and scripted Codex: no model, no network, no
Zeroshot. The conversation and the plan are written into the stores; the run is the fixture driver stepped by hand.
Lab tooling, not a test.
"""
import os
import pathlib
import sys
import unittest
from unittest.mock import patch

OUT = pathlib.Path(os.environ.get("ZPLAN_SHOTS", "build/readme-shots")).resolve()
SIZE = (120, 40)

import tui_support  # noqa: E402,F401  (wheelhouse on sys.path first)
import test_terminal_planner as tp  # noqa: E402
from test_tui_canvas_files import CanvasShell  # noqa: E402
from test_tui_chat import ChatShell, Fixture  # noqa: E402
from test_tui_live import LiveShell  # noqa: E402
from terminal_planner.architect import NO_PLAN  # noqa: E402
from terminal_planner.tui import app as ui, chat as chat_module  # noqa: E402

GOAL = ("Add CSV export and full-text search to the notes CLI: `notes export --csv FILE` writes every note "
        "(title, tags, created) and `notes search QUERY` lists matches, title hits first.")
OWNER = "I want to export my notes to CSV and search them. Where do we start?"
REPLY = ("Two independent pieces, then a release:\n\n"
         "1. **CSV export**: `notes export --csv FILE`, one row per note; `notes.py` already loads them all.\n"
         "2. **Search**: `notes search QUERY`, a plain scan is enough for a few thousand notes.\n"
         "3. **Release 1.1**: version, changelog.\n\n"
         "Here is the goal as I would plan it; approve it below or tell me what to change.")
PLAN = {
    "requirements": [
        {"id": "R1", "text": "`notes export --csv FILE` writes every note with title, tags and creation date."},
        {"id": "R2", "text": "`notes search QUERY` lists matching notes, title matches first."},
        {"id": "R3", "text": "Version 1.1 ships with a changelog entry."}],
    "milestones": [
        {"id": "M1", "title": "CSV export", "depends_on": [], "slices": [
            {"id": "S1", "title": "Export command", "requirements": ["R1"], "tasks": [
                {"id": "T1", "title": "Add the export subcommand", "checks": ["CSV round-trip test"]},
                {"id": "T2", "title": "Quote commas and newlines", "checks": ["A note with a comma survives"]}]}]},
        {"id": "M2", "title": "Full-text search", "depends_on": [], "slices": [
            {"id": "S2", "title": "Search command", "requirements": ["R2"], "tasks": [
                {"id": "T3", "title": "Add the search subcommand", "checks": ["Matches are listed"]},
                {"id": "T4", "title": "Rank title matches first", "checks": ["Ranking test"]}]}]},
        {"id": "M3", "title": "Release 1.1", "depends_on": ["M1", "M2"], "slices": [
            {"id": "S3", "title": "Release", "requirements": ["R3"], "tasks": [
                {"id": "T5", "title": "Bump the version and the changelog", "checks": ["Version test"]}]}]}],
}


class Notes:
    """A project folder named `notes` with a small README, and the plan above in place of the fixture plan."""

    def setUp(self):
        super().setUp()
        new = self.root / "notes"
        self.project.rename(new)
        self.project = new
        (self.project / "notes.py").write_text("print('notes')\n")
        self.git("add", "notes.py")
        self.git("commit", "-qm", "notes CLI")
        self.fixture = Fixture(self.root, self.project)
        proposal = patch("terminal_planner.engine.fixture_proposal", return_value=PLAN)
        proposal.start()
        self.addCleanup(proposal.stop)

    def begin(self, authority, engine="fixture"):
        authority.begin(GOAL, tp.ROLES, engine)

    def main(self):
        return next(s for s in self.app.screen_stack if type(s).__name__ == "MainScreen")

    def talk(self, drafts=()):
        store = self.fixture.store()
        store.append("owner", text=OWNER)
        store.append("architect", text=REPLY, status="completed", drafts=list(drafts))
        return store

    async def save(self, pilot, name):
        await pilot.pause(0.5)
        self.app.save_screenshot(name + ".svg", str(OUT))


class ChatShots(Notes, CanvasShell, ChatShell):
    async def test_1_chat(self):
        store = self.talk([{"kind": "goal", "text": GOAL, "milestone": None, "identity": NO_PLAN}])
        async with self.shell(size=SIZE, store=store) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            await self.until(pilot, lambda: chat_module.newest_goal_draft(self.app.chat.state.entries) is not None)
            await self.until(pilot, lambda: self.main().draft_card_open())
            await self.save(pilot, "1-chat")

    async def test_2_plan(self):
        with tp.Authority(self.state, self.project) as a:
            self.begin(a)
            self.propose(a)
        async with self.shell(size=SIZE, store=self.talk()) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            await self.until(pilot, lambda: self.main().card_widgets)
            await self.save(pilot, "2-plan")
            await self.command(pilot, "/view")
            await self.until(pilot, lambda: type(self.app.screen).__name__ == "PlanScreen")
            await self.save(pilot, "2b-plan-screen")

    async def test_4_merge(self):
        self.approve(running=False)
        self.plain("g\ny\nl\nq\n")  # M1 done and waiting for its merge, made by the line UI
        async with self.shell(size=SIZE, store=self.talk()) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            await self.until(pilot, lambda: any(k.startswith("merge:") for k in self.main().card_widgets))
            await self.save(pilot, "4-merge")


class RunShots(Notes, LiveShell, ChatShell):
    async def test_3_running(self):
        self.approve(running=False)
        self.driver.modes = [("advance", 40)] * 6
        async with self.shell(size=SIZE, follow=True, store=self.talk()) as pilot:
            await self.start_held(pilot)
            for _ in range(4):
                await self.step(pilot)
            await self.save(pilot, "3-running")
            self.main().show_tab(ui.TAB_LIVE)
            await self.save(pilot, "3b-scheme")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    result = unittest.main(argv=[sys.argv[0], "ChatShots", "RunShots"], exit=False).result
    print(OUT)
    sys.exit(0 if result.wasSuccessful() else 1)
