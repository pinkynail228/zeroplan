# tests/test_late_results.py
"""A merge, start or re-brief the architect asked for that ends after its bridge wait wakes the architect once, with
the job's result. A job that ends inside its wait adds no wake, nothing wakes at manual, and the owner's own merge is
unchanged. Real Git, stores, the live Controller and bridge socket, the fixture driver; the slow job is a held
`Delivery.merge` or a busy worker under a patched `bridge.TIMEOUT`, never a real wait."""
import contextlib
import threading
import time
import unittest
from unittest.mock import patch

from terminal_planner import bridge, delivery, feed
from terminal_planner.runs import FixtureDriver
from terminal_planner.tui import chat as chat_module
from terminal_planner.tui.controller import token_identity

import test_bridge as tb
import test_feed_wiring as fw
import test_terminal_planner as tp
from test_tui_chat import Fixture

NO_WAKE = "the late job wrote no wake event"


class LateBase(tp.ProjectTest):
    """The live-controller helpers of test_bridge.BridgeCase, borrowed without its own tests."""
    def setUp(self):
        super().setUp()
        self.driver = FixtureDriver(self.root / "fixture-runs")

    plan = tb.BridgeCase.plan
    attempt = tb.BridgeCase.attempt
    finish = staticmethod(tb.BridgeCase.finish)
    write_auto_profile = tb.BridgeCase.write_auto_profile
    write_profile = tb.BridgeCase.write_profile
    awaiting_merge = tb.BridgeCase.awaiting_merge
    controller = tb.BridgeCase.controller
    controller_stop = tb.BridgeCase.controller_stop
    _controllers = tb.BridgeCase._controllers
    call = tb.BridgeCase.call
    entry = tb.BridgeCase.entry
    rows = tb.BridgeCase.rows

    def session(self):
        """The live controller with the chat's feed port; the first observation job bootstraps the feed."""
        controller = self.controller(profile=True)
        port = controller.feed_port()
        fw.FeedWiringCase.on_worker(controller, lambda app: None)
        return controller, port

    def m1(self):
        return next(item for item in self.rows()["rows"] if item["id"] == "M1")

    def finished(self, rid):
        """The job's registry entry is done, so its callback is on the worker: the next feed job runs after it."""
        self.assertTrue(fw.FeedWiringCase.wait(lambda: self.entry(rid)["state"] == "done"), rid)

    @contextlib.contextmanager
    def slow_merge(self):
        """`Delivery.merge` held inside the job until released, as a merge's project checks hold it."""
        entered, release = threading.Event(), threading.Event()
        real = delivery.Delivery.merge

        def held(service, *args, **kwargs):
            entered.set()
            release.wait(10)
            return real(service, *args, **kwargs)

        with patch.object(delivery.Delivery, "merge", held):
            try:
                yield entered, release
            finally:
                release.set()

    def merge_outlives_the_wait(self, row):
        with self.slow_merge() as (entered, release):
            with patch.object(bridge, "TIMEOUT", 0.2):
                reply = self.call("zplan_merge", {"milestone": "M1", "token": row["token"]}, rid="late")
            self.assertEqual(reply.get("error"), bridge.TIMEOUT_FAMILY, reply)
            self.assertTrue(entered.wait(5))
            release.set()
            self.finished("late")

    def queued_past_the_wait(self, controller, tool, args):
        """The worker is busy, so the job only runs after its wait expired."""
        release = threading.Event()
        self.addCleanup(release.set)
        controller.post("hold", lambda app: release.wait(10))
        with patch.object(bridge, "TIMEOUT", 0.2):
            reply = self.call(tool, args, rid="late")
        self.assertEqual(reply.get("error"), bridge.TIMEOUT_FAMILY, reply)
        release.set()
        self.finished("late")

    @staticmethod
    def wakes(port):
        return [event for event in port.pending() if event["wake"]]

    @staticmethod
    def result_of(controller, rid):
        return next(result for result in controller.results() if result.get("request") == rid)


class LateResults(LateBase):
    def assert_one_merge_wake(self, controller, port):
        wakes = self.wakes(port)
        self.assertEqual(len(wakes), 1, NO_WAKE)
        result = self.result_of(controller, "late")
        self.assertEqual((wakes[0]["kind"], wakes[0]["operation"], wakes[0]["outcome"]), ("result", "merge", "done"))
        self.assertEqual(wakes[0]["lines"], result["lines"])
        self.assertIn(result["lines"][0], feed.summary(wakes, 0))
        return wakes[0]

    def test_a_merge_that_outlives_its_wait_wakes_the_architect_once_with_its_result(self):
        self.awaiting_merge()
        controller, port = self.session()
        self.merge_outlives_the_wait(self.m1())
        event = self.assert_one_merge_wake(controller, port)
        self.controller_stop()
        with tp.Authority(self.state, self.project) as authority:  # the store with the event loads again
            kept = [item["seq"] for item in feed.pending(authority, limit=None)[0] if item["wake"]]
        self.assertEqual(kept, [event["seq"]])

    def test_a_merge_that_outlives_its_wait_wakes_the_architect_at_supervised(self):
        self.awaiting_merge(level="supervised", tier="low")
        controller, port = self.session()
        self.merge_outlives_the_wait(self.m1())
        self.assert_one_merge_wake(controller, port)

    def test_a_start_refused_after_its_wait_wakes_the_architect_with_the_refusal(self):
        self.write_auto_profile()
        self.plan(0, profile=True)
        controller, port = self.session()
        self.queued_past_the_wait(controller, "zplan_start", {"milestone": "M1", "revision": 99})
        wakes = self.wakes(port)
        self.assertEqual(len(wakes), 1, NO_WAKE)
        self.assertEqual((wakes[0]["operation"], wakes[0]["outcome"]), ("start", "refused"))
        self.assertEqual(wakes[0]["family"], self.entry("late")["error"]["family"])
        self.assertEqual(wakes[0]["lines"], self.result_of(controller, "late")["lines"])

    def test_a_rebrief_that_ends_after_its_wait_wakes_the_architect(self):
        self.write_auto_profile()
        self.attempt("failed")
        controller, port = self.session()
        self.queued_past_the_wait(controller, "zplan_rebrief",
                                  {"milestone": "M1", "token": self.m1()["token"], "note": "another way"})
        wakes = self.wakes(port)
        self.assertEqual(len(wakes), 1, NO_WAKE)
        self.assertEqual((wakes[0]["operation"], wakes[0]["outcome"]), ("rebrief", "done"))

    def test_a_request_refused_before_its_tool_ran_still_carries_the_refusal(self):
        self.write_auto_profile()
        self.plan(0, profile=True)
        controller, port = self.session()
        self.queued_past_the_wait(controller, "zplan_merge", {"milestone": "M1", "token": {}})
        wakes = self.wakes(port)
        self.assertEqual(len(wakes), 1, NO_WAKE)
        self.assertEqual((wakes[0]["operation"], wakes[0]["outcome"], wakes[0]["family"]),
                         ("merge", "failed", "architect.request_invalid"))
        self.assertEqual(wakes[0]["lines"], [self.entry("late")["error"]["message"]])

    def test_nothing_wakes_the_architect_at_manual(self):
        self.awaiting_merge(level="manual", tier="low")
        controller, port = self.session()
        self.queued_past_the_wait(controller, "zplan_merge", {"milestone": "M1", "token": self.m1()["token"]})
        self.assertEqual(self.wakes(port), [])

    def test_a_merge_inside_its_wait_writes_no_wake(self):
        self.awaiting_merge()
        _, port = self.session()
        row = self.m1()
        reply = self.call("zplan_merge", {"milestone": "M1", "token": row["token"]}, rid="quick")
        self.assertEqual(reply["ok"]["kind"], "integrated", reply)
        events = port.pending()
        self.assertEqual([event for event in events if event["wake"]], [])
        self.assertEqual([event for event in events if event["kind"] == "result"], [])

    def test_the_owners_own_merge_writes_no_result_event(self):
        self.awaiting_merge()
        controller, port = self.session()
        token = token_identity(self.m1()["token"])
        ended = threading.Event()
        with self.slow_merge() as (entered, release), patch.object(bridge, "TIMEOUT", 0.01):
            self.assertTrue(controller.merge(token, lambda outcome, error: ended.set()))
            self.assertTrue(entered.wait(5))
            time.sleep(0.05)
            release.set()
            self.assertTrue(ended.wait(10))
        events = port.pending()
        self.assertEqual([event for event in events if event["kind"] == "result"], [])
        self.assertEqual([event.get("state") for event in events if event["wake"]], ["integrated"])

    def test_a_late_merge_runs_one_event_turn_carrying_its_result(self):
        self.awaiting_merge()
        fixture = Fixture(self.root, self.project)
        controller, port = self.session()
        row = self.m1()
        controller.snapshot_source = lambda: {"project": "p", "branch": None, "milestones": []}
        chat = chat_module.ArchitectChat(self.project, fixture.prepare(), binding=fixture.binding(),
                                         feed=port, hand_over=lambda call: call())
        self.addCleanup(chat.close)
        controller.on_observed = chat.notify  # what the app wires
        chat.start()
        wait = fw.FeedWiringCase.wait
        self.assertTrue(wait(lambda: chat.state.phase == "ready" and not chat.busy))
        self.assertEqual(fixture.calls(), [])

        self.merge_outlives_the_wait(row)
        self.assertTrue(wait(lambda: len(fixture.calls()) == 1 and not chat.busy, 5.0), NO_WAKE)
        events_text = fixture.calls()[0]["stdin"].split(feed.STATUS_PREFIX, 1)[0]  # the status also lists results
        self.assertIn(self.result_of(controller, "late")["lines"][0], events_text)

        chat.notify()
        time.sleep(0.5)
        self.assertEqual(len(fixture.calls()), 1)


if __name__ == "__main__":
    unittest.main()
