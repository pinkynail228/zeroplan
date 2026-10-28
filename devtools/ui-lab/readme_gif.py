"""README GIF frames: the real zplan shell, from the start screen with the mascot to a running milestone whose right
pane switches between the plan and the worker's scheme, then the merge card.

Run from the repo root like readme_shots.py (same environment):
  env -u XDG_DATA_HOME TMPDIR=$(mktemp -d /tmp/zs.XXXX) ZPLAN_TEST_WHEELHOUSE=~/.cache/zplan-wheelhouse \
    PYTHONPATH=.:tests:devtools/ui-lab ZPLAN_GIF=build/readme-gif python3.13 devtools/ui-lab/readme_gif.py
then `devtools/ui-lab/readme_gif.sh build/readme-gif docs/img/demo.gif` turns the frames into the GIF.
Every frame is the shipped app on the readme_shots fixtures: no model, no network, no Zeroshot. Lab tooling, not a test.
"""
import json
import os
import re
import pathlib
import sys
import unittest

OUT = pathlib.Path(os.environ.get("ZPLAN_GIF", "build/readme-gif")).resolve()
os.environ["ZPLAN_SHOTS"] = str(OUT)  # readme_shots reads it at import; its SIZE and fixtures are reused as they are

import readme_shots as shots  # noqa: E402
from readme_shots import GOAL, NO_PLAN, SIZE, Notes, ui, chat_module  # noqa: E402
from test_tui_canvas_files import CanvasShell  # noqa: E402
from test_tui_chat import ChatShell  # noqa: E402
from test_tui_live import LiveShell  # noqa: E402
from terminal_planner.tui.start import StartApp  # noqa: E402

TIMELINE = OUT / "timeline.json"
TEMP = re.compile(r"(/private)?/tmp/[^\s<\"'&]*?/notes")
shots.OWNER = "Add CSV export and search. Where do we start?"  # fits the chat input while it is typed


def home(match):
    """The harness's temp folder reads as a real one; padded to the same length, since Rich fixes each span's width."""
    return "~/code/notes".ljust(len(match.group(0))).replace(" ", "&#160;")


def frame(app, name, seconds):
    """Save one SVG frame and append it, with how long it stays on screen, to the timeline."""
    app.save_screenshot(name + ".svg", str(OUT))
    svg = OUT / (name + ".svg")
    svg.write_text(TEMP.sub(home, svg.read_text()))
    rows = json.loads(TIMELINE.read_text()) if TIMELINE.exists() else []
    rows.append([name + ".svg", seconds])
    TIMELINE.write_text(json.dumps(rows))


class A_Start(Notes, CanvasShell, ChatShell):
    async def test_start(self):
        app = StartApp(self.project)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause(0.5)
            frame(app, "a-start", 2.5)


class B_Chat(Notes, CanvasShell, ChatShell):
    async def test_1_type(self):
        async with self.shell(size=SIZE, store=self.fixture.store()) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            field = self.query("#input")
            field.focus()
            step = 6
            for end in range(step, len(shots.OWNER) + step, step):
                field.value = shots.OWNER[:end]
                field.cursor_position = len(field.value)
                await pilot.pause(0.05)
                frame(self.app, "b-type-%03d" % end, 0.08)
            frame(self.app, "b-type-end", 0.6)

    async def test_2_reply(self):
        store = self.talk([{"kind": "goal", "text": GOAL, "milestone": None, "identity": NO_PLAN}])
        async with self.shell(size=SIZE, store=store) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            await self.until(pilot, lambda: chat_module.newest_goal_draft(self.app.chat.state.entries) is not None)
            await self.until(pilot, lambda: self.main().draft_card_open())
            await pilot.pause(0.5)
            frame(self.app, "c-reply", 3.0)


class C_Plan(Notes, CanvasShell, ChatShell):
    async def test_plan(self):
        with shots.tp.Authority(self.state, self.project) as a:
            self.begin(a)
            self.propose(a)
        async with self.shell(size=SIZE, store=self.talk()) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            await self.until(pilot, lambda: self.main().card_widgets)
            await pilot.pause(0.5)
            frame(self.app, "d-plan", 2.5)


class D_Run(Notes, LiveShell, ChatShell):
    async def test_run(self):
        self.approve(running=False)
        self.driver.modes = [("advance", 40)] * 12
        async with self.shell(size=SIZE, follow=True, store=self.talk()) as pilot:
            await self.start_held(pilot)
            await self.step(pilot)
            frame(self.app, "e1-plan", 1.6)
            self.main().show_tab(ui.TAB_LIVE)
            await pilot.pause(0.4)
            frame(self.app, "e2-scheme", 1.2)
            for index in range(3):
                await self.step(pilot)
                frame(self.app, "e3-scheme-%d" % index, 1.0)
            self.main().show_tab(ui.TAB_PLAN)
            await pilot.pause(0.4)
            frame(self.app, "e4-plan", 1.6)
            await self.step(pilot)
            self.main().show_tab(ui.TAB_LIVE)
            await pilot.pause(0.4)
            frame(self.app, "e5-scheme", 1.6)


class E_Merge(Notes, CanvasShell, ChatShell):
    async def test_merge(self):
        self.approve(running=False)
        self.plain("g\ny\nl\nq\n")  # M1 done and waiting for its merge, made by the line UI
        async with self.shell(size=SIZE, store=self.talk()) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            await self.until(pilot, lambda: any(k.startswith("merge:") for k in self.main().card_widgets))
            await pilot.pause(0.5)
            frame(self.app, "f-merge", 3.5)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    TIMELINE.unlink(missing_ok=True)
    loader = unittest.TestLoader()
    loader.sortTestMethodsUsing = None  # source order inside a class
    suite = unittest.TestSuite(loader.loadTestsFromTestCase(case) for case in (A_Start, B_Chat, C_Plan, D_Run, E_Merge))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    print(OUT)
    sys.exit(0 if result.wasSuccessful() else 1)
