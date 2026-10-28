"""A6b2b: the architect chat's feed port over the Controller worker, its bootstrap and the observation wake-up.

One smoke test per criterion on a real `Controller` over the fixture session (a scripted codex stands behind the
chat, as in `test_tui_chat`; no Textual, no provider, no network):

- C1 port: `pending()`/`handle(seq)` run one job each on the worker thread (never the caller's), in seq order, and
  a timeout, a closing controller and the worker's own thread are `Blocked`; `snapshot()` is the app's snapshot.
- C2 bootstrap: the worker creates the feed once after the session opens, seeded with every run's last state.
- C3 wiring and wake-up: a run moving to awaiting_merge makes the chat run one event turn; a further notify with
  nothing pending starts no turn.
- C4 no regression without an architect: no port is requested, so the worker never bootstraps (no save).

Interpretations (the reviewers never see the worker's summary):
- The port's snapshot comes from `Controller.snapshot_source`, which the app sets to `chat_snapshot` (the same way it
  sets `on_plan_submission`), so `controller.feed_port()` takes no argument.
- "After each completed OBSERVATIONS job" is read as after each such job that was not skipped, whatever its outcome:
  a failed slice may still have saved a state, and the chat's check is a cheap read.
- "Once on the worker after the session opens, before the first observation job" is read literally: lazily, before the
  first OBSERVATIONS job (a watch slice); a port requested after the session opened bootstraps as a job of its own.
  Every other job (a refresh, a draft, a mutating job, the feed's own `pending`/`handle`) leaves the store
  byte-identical: `test_tui_chat` pins that an opened draft, a refused answer and a probe job write nothing, which an
  eager save at open or before every non-cuttable job breaks. `feed.pending` reads an absent feed as empty and the
  ack on an absent feed is handled by feed.py. Consequence: right after open, before any observation, `state["feed"]`
  is not there yet.
- A bootstrap the store refuses leaves the feed absent (`feed.pending` then reads as an empty queue) and the session
  usable; it is not a session error.
"""

import copy
import json
import threading
import time
import unittest
from unittest.mock import patch

from terminal_planner import bridge, feed
from terminal_planner.authority import Authority, Blocked
from terminal_planner.engine import FixtureEngine
from terminal_planner.runs import FixtureDriver, MilestoneRuns
from terminal_planner.tui import chat as chat_module
from terminal_planner.tui.controller import OBSERVE, Controller
import test_terminal_planner as tp
from test_feed import state_event
from test_terminal_planner import ROLES
from test_tui_chat import Fixture
from tui_support import HAVE_TEXTUAL


class FeedWiringCase(tp.ProjectTest):
    def setUp(self):
        super().setUp()
        self.driver = FixtureDriver(self.root / "fixture-runs")

    def attempts(self, count):
        """The approved fixture plan with `count` M1 attempts; every one but the last is stopped."""
        with tp.Authority(self.state, self.project) as authority:
            self.begin(authority)
            self.propose(authority)
            authority.approve(1)
            runs = MilestoneRuns(authority, self.driver, worktrees=authority.directory / "worktrees")
            for index in range(count):
                record = runs.start("M1", 1, ROLES)
                if index < count - 1:
                    runs.stop(record)
                    mark = None
                    for _ in range(200):
                        if record["status"] not in ("submitted", "running", "stopping"):
                            break
                        _, mark = runs.poll(record, mark)
                    else:
                        self.fail("the fixture run did not stop")

    def controller(self, port=True, **kw):
        kw.setdefault("driver_factory", lambda _: self.driver)
        kw.setdefault("engine_factory", lambda *_: FixtureEngine())
        controller = Controller.for_project(self.project, self.state, fixture_id="test", **kw)
        result = controller.feed_port() if port else None
        controller.start()
        self.addCleanup(controller.stop)
        return controller, result

    @staticmethod
    def on_worker(controller, work, timeout=10):
        """`work(app)` run on the worker, its result returned (a job error fails the test)."""
        return FeedWiringCase.on_worker_as(controller, OBSERVE, work, timeout)

    @staticmethod
    def on_worker_as(controller, label, work, timeout=10):
        """The same under a job label (a cuttable non-observation label is a read-only screen job; the default
        `on_worker` is an observation, which bootstraps the feed first)."""
        event, box = threading.Event(), {}

        def done(result, error):
            box["result"], box["error"] = result, error
            event.set()

        controller.post(label, work, done)
        assert event.wait(timeout), "the probe job never ran"
        if box["error"] is not None:
            raise AssertionError(box["error"])
        return box["result"]

    @staticmethod
    def wait(condition, timeout=10.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if condition():
                return True
            time.sleep(0.01)
        return False


class PortTests(FeedWiringCase):
    def test_c2_bootstrap_creates_the_feed_once_with_every_runs_last_state(self):
        """C2: a store with two runs and no feed -> after open the worker has created `state["feed"]` (both runs'
        last states, nothing pending)."""
        self.attempts(2)
        controller, _ = self.controller()
        queue = self.on_worker(controller, lambda app: copy.deepcopy(app.authority.state.get("feed")))
        self.assertEqual(sorted(queue["last"].values()), ["running", "stopped"])
        self.assertEqual((queue["events"], queue["seq"], queue["handled"]), ([], 0, 0))

    def test_c2_a_read_only_screen_job_leaves_the_store_bytes_alone(self):
        """C2 regression: before the first observation job the store is untouched (no feed yet, also after a
        non-cuttable job); the first observation bootstraps first."""
        self.attempts(2)
        path = Authority(self.state, self.project, fixture_id="test").path
        before = path.read_bytes()
        controller, _ = self.controller()
        self.assertIsNone(self.on_worker_as(controller, "open_answer_draft", lambda app: app.authority.state.get("feed")))
        self.assertIsNone(self.on_worker_as(controller, "probe", lambda app: app.authority.state.get("feed")))
        self.assertEqual(path.read_bytes(), before)
        self.assertIsNotNone(self.on_worker(controller, lambda app: app.authority.state.get("feed")))

    def test_c1_pending_and_handle_run_on_the_worker_and_are_bounded(self):
        """C1: two stored wake events -> `pending()` returns both in seq order from a thread that is not the worker;
        `handle` acks through the worker; a timeout, the worker's own thread and a closing controller are Blocked."""
        self.attempts(1)
        controller, port = self.controller()

        def store(app):
            queue = app.authority.state["feed"]
            for _ in (1, 2):
                feed._append(queue, state_event(0, state="awaiting_merge", previous="running"))
            app.authority.save()
        self.on_worker(controller, store)

        threads, real = [], feed.pending

        def spy(authority, limit=50):
            threads.append((threading.current_thread(), limit))
            return real(authority, limit=limit)
        with patch.object(feed, "pending", spy):
            events = port.pending()
        self.assertEqual([event["seq"] for event in events], [1, 2])
        self.assertEqual(threads, [(controller._thread, None)])

        port.handle(2)
        self.assertEqual(port.pending(), [])
        self.assertEqual(self.on_worker(controller, lambda app: app.authority.state["feed"]["handled"]), 2)

        release = threading.Event()
        controller.post("hold", lambda app: release.wait(10))
        with patch.object(bridge, "TIMEOUT", 0.3):
            with self.assertRaises(Blocked):
                port.pending()
        release.set()

        with self.assertRaises(Blocked):  # no snapshot source is wired yet
            port.snapshot()
        controller.snapshot_source = lambda: {"project": "p"}
        self.assertEqual(port.snapshot(), {"project": "p"})

        # the worker never waits on the chat: asked from its own thread the port refuses instead of deadlocking
        with self.assertRaises(AssertionError) as caught:
            self.on_worker(controller, lambda app: port.pending())
        self.assertIn("worker thread", str(caught.exception))
        controller.stop()
        for call in (port.pending, lambda: port.handle(3)):
            with self.assertRaises(Blocked):
                call()

    def test_c4_a_session_without_a_port_never_bootstraps(self):
        """C4: no port requested -> the worker never calls bootstrap and the store gets no feed."""
        self.attempts(1)
        with patch.object(feed, "bootstrap") as bootstrap:
            controller, _ = self.controller(port=False)
            self.assertNotIn("feed", self.on_worker(controller, lambda app: app.authority.state))
        bootstrap.assert_not_called()


class WakeTests(FeedWiringCase):
    def test_c3_an_observed_run_that_finished_wakes_the_chat_for_one_event_turn(self):
        """C3: the chat built on the controller's port and woken by `on_observed`; the run moves running ->
        awaiting_merge under the controller's observation jobs -> one event turn whose message holds the
        awaiting_merge line; a second notify with nothing pending starts no turn."""
        self.attempts(1)
        fixture = Fixture(self.root, self.project)
        controller, port = self.controller()
        controller.snapshot_source = lambda: {"project": "p", "branch": None, "milestones": []}
        chat = chat_module.ArchitectChat(self.project, fixture.prepare(), binding=fixture.binding(),
                                         feed=port, hand_over=lambda call: call())
        self.addCleanup(chat.close)
        controller.on_observed = chat.notify
        chat.start()
        self.assertTrue(self.wait(lambda: chat.state.phase == "ready" and not chat.busy))
        self.assertEqual(fixture.calls(), [])  # the running attempt is no wake event

        for _ in range(100):
            ended = threading.Event()
            controller.observe_run("M1", lambda line: None, lambda result, error: ended.set())
            self.assertTrue(ended.wait(20))
            if self.wait(lambda: fixture.calls(), 0.5):
                break
        self.assertTrue(self.wait(lambda: len(fixture.calls()) == 1 and not chat.busy), fixture.calls())
        stdin = fixture.calls()[0]["stdin"]
        self.assertRegex(stdin, r"M1 attempt 1: \S+ -> awaiting_merge")
        # C1a C1: the turn carries the status `zplan_status` answers (the controller's own payload, real rows)
        status = json.loads(stdin.split("Status: ", 1)[1].split("\n", 1)[0])
        row = next(row for row in status["rows"] if row["id"] == "M1")
        self.assertEqual(row["state"], "awaiting_merge")
        self.assertIn("token", row)
        self.assertIn("merge", row)
        self.assertNotIn("proposal", status["plan"])
        self.assertNotIn("stale", status)
        self.assertTrue(self.wait(lambda: self.on_worker(
            controller, lambda app: app.authority.state["feed"]["handled"]) >= 1))

        chat.notify()
        time.sleep(0.5)
        self.assertEqual(len(fixture.calls()), 1)

    def test_rs5_c3_an_owner_approval_wakes_the_chat_for_one_event_turn(self):
        """RS5 C3: a proposed plan, the chat on the controller's port; the owner's approval on a supervised session's
        worker (the same `Authority.save` every approval path ends in) -> one event turn naming
        «plan r1: proposed -> approved».

        The wake is the controller's own: `on_observed` is `chat.notify` and the mutating job (the approval) calls it
        when it ends, with no manual notify; the architect's `zplan_approve_plan` and the CLI call the same
        `Authority.approve`. Interpretation: the level is patched at `autonomy.level` (the fixture controller is
        unprofiled, which reads as manual: no wake)."""
        with tp.Authority(self.state, self.project) as authority:
            self.begin(authority)
            self.propose(authority)
        fixture = Fixture(self.root, self.project)
        controller, port = self.controller()
        controller.snapshot_source = lambda: {"project": "p", "branch": None, "milestones": []}
        self.on_worker(controller, lambda app: None)  # the first observation job bootstraps the feed
        chat = chat_module.ArchitectChat(self.project, fixture.prepare(), binding=fixture.binding(),
                                         feed=port, hand_over=lambda call: call())
        self.addCleanup(chat.close)
        chat.start()
        self.assertTrue(self.wait(lambda: chat.state.phase == "ready" and not chat.busy))
        self.assertEqual(fixture.calls(), [])  # the proposed plan seeded at bootstrap is no event
        controller.on_observed = chat.notify  # what the app wires

        with patch("terminal_planner.autonomy.level", return_value="supervised"):
            done = threading.Event()
            self.assertTrue(controller.post("approve", lambda app: app.authority.approve(1),
                                            lambda result, error: done.set()))
            self.assertTrue(done.wait(10))
        self.assertTrue(self.wait(lambda: len(fixture.calls()) == 1 and not chat.busy), fixture.calls())
        self.assertIn("plan r1: proposed -> approved", fixture.calls()[0]["stdin"])

    def approval_event(self, acting):
        """The «proposed -> approved» plan event of a proposed plan approved in `auto`, by the architect's action
        (`_bridge_action`, the real `_run_tool` stood in by the `Authority.approve` the approve tool ends in) or by
        an ordinary job (the owner's); with the flag as the worker leaves it."""
        with tp.Authority(self.state, self.project) as authority:
            self.begin(authority)
            self.propose(authority)
        controller, port = self.controller()
        self.on_worker(controller, lambda app: None)  # bootstrap
        with patch("terminal_planner.autonomy.level", return_value="auto"):
            if acting:
                with patch.object(controller, "_run_tool",
                                  lambda app, tool, args, planning=None: app.authority.approve(1)):
                    ok, error = controller._bridge_action("c1b-approve", "zplan_approve_plan", {})
                self.assertIsNone(error, error)
            else:
                done = threading.Event()
                self.assertTrue(controller.post("approve", lambda app: app.authority.approve(1),
                                                lambda result, error: done.set()))
                self.assertTrue(done.wait(10))
        events, flag = self.on_worker(controller, lambda app: (
            [e for e in feed.pending(app.authority)[0] if e["kind"] == "plan" and e["status"] == "approved"],
            getattr(app.authority, "architect_acting", False)))
        self.assertEqual(len(events), 1)  # the event pends either way: it rides along with the next wake batch
        self.assertFalse(flag)  # the flag is down again once the action's job returned
        return events[0]

    def test_c1b_c1_the_architects_own_action_captures_a_quiet_plan_event(self):
        """C1b C1: in `auto` the plan event «proposed -> approved» captured while the architect's action runs has
        wake false (the architect learns it from the tool's answer)."""
        self.assertIs(self.approval_event(True)["wake"], False)

    def test_c1b_c1_the_owners_approval_of_the_same_plan_still_wakes(self):
        """C1b C4: the owner's approval of the same plan in `auto` wakes (RS5)."""
        self.assertIs(self.approval_event(False)["wake"], True)

    def test_rs5_c3_only_a_mutating_job_notifies_not_a_read_or_the_ack(self):
        """RS5 C3: `on_observed` is called after a job outside CUTTABLE (a mutation) and after an observation, never
        after a read-only job (refresh, the feed read) or the feed ack."""
        controller, port = self.controller()
        calls = []
        controller.on_observed = lambda: calls.append(1)
        self.on_worker_as(controller, "refresh", lambda app: None)
        self.on_worker_as(controller, "feed_pending", lambda app: None)
        self.on_worker_as(controller, "feed_handle", lambda app: None)
        self.assertTrue(self.wait(lambda: self.on_worker_as(controller, "refresh", lambda app: None) is None))
        self.assertEqual(calls, [])
        self.on_worker_as(controller, "approve", lambda app: None)
        self.assertTrue(self.wait(lambda: calls == [1]))


@unittest.skipUnless(HAVE_TEXTUAL, "Textual недоступен: нужен ZPLAN_TEST_WHEELHOUSE с wheels textual 8.2.8")
class AppWiringTests(FeedWiringCase):
    def test_c3_c4_the_app_wires_the_port_and_the_hooks_only_for_an_architect_session(self):
        """C3: an architect session's chat holds the controller's port and the controller calls `chat.notify` after
        an observation and `chat_snapshot` for the port's snapshot; C4: `architect=False` (a `--fixture ID` demo)
        builds no chat, no port and no hook, and the worker never bootstraps (the app is built, not run)."""
        from terminal_planner.tui.app import ZplanApp
        controller = Controller.for_project(self.project, self.state, fixture_id="test")
        app = ZplanApp(controller)
        self.assertIs(app.chat.feed, controller._feed)
        self.assertEqual(controller.on_observed, app.chat.notify)
        self.assertEqual(controller.snapshot_source, app.chat_snapshot)
        self.assertEqual(app.chat.feed.snapshot(), app.chat_snapshot())

        plain = Controller.for_project(self.project, self.state, fixture_id="test")
        demo = ZplanApp(plain, architect=False)
        self.assertIsNone(demo.chat)
        self.assertIsNone(plain._feed)
        self.assertIsNone(plain.on_observed)
        self.assertIsNone(plain.snapshot_source)


if __name__ == "__main__":
    unittest.main()
