# tests/test_demo_architect.py
"""In `zplan --fixture ID` the full-screen chat has a scripted architect. An owner goal reaches `zplan_plan` over the
real bridge, the plan card shows the fresh reader's paraphrase and asks the owner, and approve and run lead to the merge
card. The script never approves, starts or merges, and a fixture session still reaches no provider or tool probe.

The journey enters at `cli.main`, so the wiring under test is the product's own. Real Git, stores, Controller, bridge
socket, fixture engine and fixture driver; no provider, no network."""
import contextlib
from dataclasses import replace
import json
from pathlib import Path
import time
import unittest
from unittest.mock import patch

import tui_support  # noqa: F401  (imported first: the wheelhouse and the pinned UI language)
from tui_support import screen_text

from terminal_planner import architect as adapter, autonomy, cli, engine, process, setup
from terminal_planner.authority import Authority, Blocked
from terminal_planner.engine import FIXTURE_PARAPHRASE
from terminal_planner.planning import PlanView
from terminal_planner.process import Profile
from terminal_planner.tui import chat as chat_module
from terminal_planner.tui import controller as controller_module
from test_fixture_scope import accept_fixture_profile, capture_tui, fixture_argv
from test_terminal_planner import ProjectTest
from test_tui_approve_card import HAVE, MISSING_REASON, Button
from test_tui_auto_plan_card import card_of, snapshot_at

GOAL = "Add a changelog to the project"
LATER = "thanks"
READER = 'How a fresh reader understood it: "%s"'


def flat(text):
    """Card text with its wrap breaks taken out."""
    return " ".join(text.split())


class ScriptedArchitectTests(ProjectTest):
    """The script behind the chat's interface, with the bridge replaced by scripted replies."""

    def setUp(self):
        super().setUp()
        self.requests = []
        self.replies = {}

        def call(path, request, timeout=None):
            self.requests.append(request)
            return dict(self.replies[request["tool"]], id=request["id"])

        patcher = patch.object(adapter.bridge, "call", call)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.store = adapter.fixture_store(self.project, self.state, "demo")
        self.architect = adapter.FixtureArchitect(self.store)

    def owner_turn(self, text=GOAL):
        self.architect.begin()
        try:
            return self.architect.run(text, role="owner", turn="token", recorded=True, turn_id="turn-1")
        finally:
            self.architect.finish()

    def tools(self):
        return [request["tool"] for request in self.requests]

    def test_the_first_owner_message_writes_the_plan_for_that_goal(self):
        self.replies = {"zplan_status": {"ok": {"plan": None}},
                        "zplan_plan": {"ok": {"revision": 1, "status": "ready"}}}
        result = self.owner_turn()
        self.assertEqual(result.status, "completed")
        self.assertEqual(self.tools(), ["zplan_status", "zplan_plan"])
        self.assertEqual(self.requests[1]["args"], {"goal": GOAL, "plan": engine.fixture_draft()})
        self.assertEqual({request["turn"] for request in self.requests}, {"token"})
        self.assertEqual(len({request["id"] for request in self.requests}), 2)
        row = self.store.transcript()[-1]
        self.assertEqual((row["role"], row["turn_id"]), ("architect", "turn-1"))

    def test_a_later_owner_message_keeps_the_plan_it_has(self):
        self.replies = {"zplan_status": {"ok": {"plan": {"version": 1, "status": "proposed"}}}}
        self.assertEqual(self.owner_turn(LATER).status, "completed")
        self.assertEqual(self.tools(), ["zplan_status"])
        self.assertEqual(self.store.transcript()[-1]["role"], "architect")

    def test_a_status_it_cannot_read_writes_no_plan(self):
        self.replies = {"zplan_status": {"ok": {"plan": "plan unavailable"}}}
        self.assertEqual(self.owner_turn().status, "completed")
        self.assertEqual(self.tools(), ["zplan_status"])

    def test_a_refused_plan_is_reported_and_not_claimed(self):
        self.replies = {"zplan_status": {"ok": {"plan": None}},
                        "zplan_plan": {"error": "action.refused", "message": "refusal-from-the-tool"}}
        self.assertEqual(self.owner_turn().status, "completed")
        self.assertIn("refusal-from-the-tool", self.store.transcript()[-1]["text"])

    def test_a_cancel_before_the_call_stops_the_turn(self):
        self.assertFalse(self.architect.cancel())
        self.architect.begin()
        self.assertTrue(self.architect.cancel())
        result = self.architect.run(GOAL, role="owner", turn="token", recorded=True, turn_id="turn-1")
        self.architect.finish()
        self.assertEqual((result.status, result.cause), ("cancelled", adapter.CAUSE_CANCELLED))
        self.assertEqual(self.requests, [])
        row = self.store.transcript()[-1]
        self.assertEqual((row["role"], row["status"], row["turn_id"]), ("error", "cancelled", "turn-1"))
        self.assertFalse(self.architect.cancel())

    def test_only_one_turn_is_reserved_at_a_time(self):
        self.architect.begin()
        with self.assertRaises(Blocked) as caught:
            self.architect.begin()
        self.assertEqual(caught.exception.family, "architect.busy")
        self.architect.finish()
        self.architect.begin()
        self.architect.finish()

    def test_a_turn_the_owner_did_not_start_writes_its_row_and_calls_no_tool(self):
        for role in ("events", chat_module.PROMPT_ROLE):
            self.architect.begin()
            result = self.architect.run("a wake", role=role)
            self.architect.finish()
            self.assertEqual(result.status, "completed")
        self.assertEqual(self.requests, [])
        self.assertEqual([row["role"] for row in self.store.transcript()], ["events", chat_module.PROMPT_ROLE])

    def test_a_new_conversation_adds_one_reset_row_and_calls_no_tool(self):
        chat = chat_module.ArchitectChat(self.project, lambda: (self.architect, chat_module.ChatHeader()),
                                         binding=lambda: ("", ""), store=self.store)
        chat.start()
        end = time.monotonic() + 10
        while not chat.ready:
            self.assertLess(time.monotonic(), end)
            time.sleep(0.01)
        accepted, line = chat.new_session()
        self.assertTrue(accepted, line)
        self.assertTrue(chat.wait(10))
        self.assertEqual([row["role"] for row in self.store.transcript()].count("reset"), 1)
        self.assertEqual(self.requests, [])
        self.assertEqual(chat.state.header, "")

    def test_the_transcript_lives_under_the_state_directory(self):
        self.assertEqual(self.store.directory,
                         self.state / "architect" / "demo" / adapter.project_key(self.project))

    def test_without_a_state_directory_the_transcript_sits_beside_the_fixture_state(self):
        with Authority(None, self.project, fixture_id="demo") as authority:
            base = authority.directory.parents[3]
        store = adapter.fixture_store(self.project, None, "demo")
        self.assertEqual(store.directory, base / "architect" / "demo" / adapter.project_key(self.project))
        self.assertFalse((Path(setup.data_root()) / "architect").exists())


@unittest.skipUnless(HAVE, MISSING_REASON)
class PlanCardScopeTests(unittest.TestCase):
    """`scripted` decides who approves; the card shows the reader in every session."""

    def read_snapshot(self, paraphrase=FIXTURE_PARAPHRASE):
        base = snapshot_at("auto")
        view = PlanView("proposal", 1, "proposed", base.plan.lines + (READER % paraphrase,), ("approve",))
        return replace(base, plan=view)

    def test_a_session_without_the_script_shows_the_reader_and_keeps_its_buttons(self):
        spec = card_of(self.read_snapshot())
        self.assertIn(FIXTURE_PARAPHRASE, flat(spec.text))
        self.assertEqual([command for _, command in spec.buttons], ["/approve", "/decline"])

    def test_a_scripted_session_shows_the_reader_and_asks_the_owner(self):
        for narrow in (False, True):
            with self.subTest(narrow=narrow):
                spec = card_of(replace(self.read_snapshot(), scripted=True), narrow)
                self.assertIn(FIXTURE_PARAPHRASE, flat(spec.text))
                self.assertIn("/approve", [command for _, command in spec.buttons])

    def test_a_long_reader_line_takes_at_most_three_rows_of_the_card(self):
        bare = card_of(replace(snapshot_at("auto"), scripted=True), width=40).text.split("\n")
        rows = card_of(replace(self.read_snapshot("word " * 80), scripted=True), width=40).text.split("\n")
        added = rows[len(bare):]
        self.assertGreater(len(added), 0)
        self.assertLessEqual(len(added), 3)
        self.assertTrue(all(len(row) <= 40 for row in added), added)
        self.assertTrue(added[-1].endswith("…"), added)


class DemoShell(ProjectTest, unittest.IsolatedAsyncioTestCase):
    """The app `cli.main` builds for `--fixture demo`, driven through the chat input. The project has no origin, as a
    demo project may not, and the accepted profile is at `auto`."""

    def demo_app(self):
        self.git("remote", "remove", "origin")
        accept_fixture_profile(self.project, self.state, "demo")
        status = Profile.peek(self.project, root=self.state, fixture_id="demo").status(write=False)
        self.assertEqual(autonomy.level_of(status), "auto")
        self.sinks = []
        self.readiness_calls = []
        sinks, calls = self.sinks, self.readiness_calls
        real_readiness, real_store = cli.readiness, adapter.ArchitectStore

        def readiness(project, state, tools=True):
            calls.append(tools)
            return real_readiness(project, state, tools=tools)

        def sink(name):
            def reached(*args, **kwargs):
                sinks.append(name)
                raise Blocked("fixture: no %s" % name, family="action.refused")
            return reached

        class Store(real_store):  # a real store; one without an explicit root is the production one
            def __init__(self, project, root=None, **kwargs):
                if root is None:
                    sinks.append("production store")
                super().__init__(project, root=root, **kwargs)

        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        for target, name, value in ((cli, "readiness", readiness),
                                    (cli, "FIXTURE_DELAY", 0.01),
                                    (cli, "check_installation", sink("cli.check_installation")),
                                    (setup, "check_installation", sink("setup.check_installation")),
                                    (adapter, "verify_cli", sink("verify_cli")),
                                    (adapter, "prepare", sink("prepare")),
                                    (adapter, "architect_binding", sink("architect_binding")),
                                    (adapter, "ArchitectStore", Store),
                                    (chat_module, "ArchitectStore", Store),
                                    (controller_module, "ArchitectStore", Store),
                                    (chat_module, "Architect", sink("Architect")),
                                    (chat_module, "default_prepare", sink("default_prepare")),
                                    (chat_module, "architect_binding", sink("chat architect_binding"))):
            stack.enter_context(patch.object(target, name, value))
        code, app = capture_tui(fixture_argv(self.project, self.state, "demo"))
        self.assertEqual(code, 0)
        self.app = app
        self.addCleanup(app.controller.stop)
        self.assertIsNotNone(app.chat)
        return app

    async def until(self, pilot, condition, timeout=30.0):
        end = time.monotonic() + timeout
        while not condition():
            self.assertLess(time.monotonic(), end, "did not reach the state:\n" + screen_text(self.app))
            await pilot.pause(0.05)

    async def enter(self, pilot, line):
        field = self.app.main_screen().query_one("#input")
        field.focus()
        field.value = line
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

    async def say(self, pilot, line):
        await self.until(pilot, lambda: not self.app.chat.busy)
        await self.enter(pilot, line)

    def open_card(self, prefix):
        main = self.app.main_screen()
        if main is None:
            return None
        return next((card for key, card in main.card_widgets.items()
                     if key.startswith(prefix) and card.spec.done is None), None)

    def commands(self, card):
        return {button.command for button in card.query(Button)} if card is not None else set()

    def rows(self, name):
        """One JSONL file of the demo's architect directory, read as raw JSON; a line being written is skipped."""
        path = self.state / "architect" / "demo" / adapter.project_key(self.project) / name
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        found = []
        for line in text.splitlines():
            try:
                found.append(json.loads(line))
            except ValueError:
                pass
        return found

    def spoken(self, role):
        return [row for row in self.rows("transcript.jsonl") if row["role"] == role]



@unittest.skipUnless(HAVE, MISSING_REASON)
class DemoJourneyTests(DemoShell):
    async def test_an_owner_goal_reaches_the_merge_card_through_one_owner_approval(self):
        app = self.demo_app()
        self.assertFalse((Path(setup.data_root()) / "architect").exists())
        async with app.run_test(size=(120, 40)) as pilot:
            self.assertIsNone(app.controller.install)
            self.assertIsNone(app.controller.login)
            await self.until(pilot, lambda: app.chat.ready)
            await self.say(pilot, GOAL)

            await self.until(pilot, lambda: self.commands(self.open_card("plan:")))
            card = self.open_card("plan:")
            self.assertIn(FIXTURE_PARAPHRASE, flat(card.spec.text))
            self.assertIn("/approve", self.commands(card))
            self.assertEqual(app.origin_note, "")
            self.assertEqual(app.chat.state.header, "")

            # the first revision waits for the owner at every level: no events turn follows the proposed plan
            await self.until(pilot, lambda: not app.chat.busy)
            self.assertEqual(self.spoken("events"), [])
            self.assertEqual(app.snapshot.status, "proposed")

            await self.say(pilot, LATER)
            await self.until(pilot, lambda: len(self.spoken("architect")) == 2)
            await self.until(pilot, lambda: not app.chat.busy)
            self.assertEqual((app.snapshot.version, app.snapshot.status), (1, "proposed"))

            await self.enter(pilot, "/approve")
            await self.until(pilot, lambda: any(row.startable for row in app.rows()))
            await self.enter(pilot, "/run")
            await self.until(pilot, lambda: self.commands(self.open_card("merge:")), 60.0)
            self.assertIn("/merge", self.commands(self.open_card("merge:")))
            self.assertEqual(next(row for row in app.rows() if row.id == "M1").state, "awaiting_merge")

        owners = self.spoken("owner")
        self.assertEqual([row["text"] for row in owners], [GOAL, LATER])
        self.assertEqual([row["turn_id"] for row in self.spoken("architect")], [row["turn_id"] for row in owners])
        plans = [row for row in self.rows("operations.jsonl")
                 if row.get("tool") == "zplan_plan" and row.get("state") == "terminal"]
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["binding"], "owner")
        self.assertIsNotNone(plans[0]["parent_operation_id"])
        self.assertEqual(plans[0]["turn_id"], owners[0]["turn_id"])
        with Authority(self.state, self.project, fixture_id="demo") as authority:
            revisions = authority.state["revisions"]
            current = authority.current
            runs = authority.state["runs"]
            self.assertEqual(len(revisions), 1)
            self.assertEqual((current["frozen"]["review"], current["origin"], current["by"], current["status"]),
                             ("goldfish", "plan", "owner", "approved"))
            self.assertEqual(current["goal"], GOAL)
            self.assertEqual(current["draft"], engine.fixture_draft())
            self.assertEqual([run["milestone"] for run in runs], ["M1"])
        self.assertEqual(self.sinks, [])
        self.assertFalse((Path(setup.data_root()) / "architect").exists())
        self.assertFalse((self.project / process.PROFILE_FILE).exists())
        self.assertTrue(self.readiness_calls and all(tools is False for tools in self.readiness_calls))

    async def test_at_80x24_the_plan_card_keeps_its_buttons_in_view_with_the_reader(self):
        app = self.demo_app()
        async with app.run_test(size=(80, 24)) as pilot:
            await self.until(pilot, lambda: app.chat.ready)
            await self.say(pilot, GOAL)
            await self.until(pilot, lambda: self.commands(self.open_card("plan:")))
            await pilot.pause(0.3)
            card = self.open_card("plan:")
            self.assertIn(FIXTURE_PARAPHRASE, flat(card.spec.text))
            pane = app.main_screen().query_one("#chat-pane")
            for button in card.query(Button):
                self.assertGreater(button.region.height, 0)
                self.assertGreaterEqual(button.region.y, pane.region.y)
                self.assertLessEqual(button.region.bottom, pane.region.bottom)
                self.assertIn(button.label.plain, screen_text(app))


if __name__ == "__main__":
    unittest.main()
