# tests/test_event_turn_retry.py
"""A failed architect event turn runs again before the chat holds (docs/PRODUCT_CONTRACT.md section 2, Delegation).

A scripted codex stands behind the chat. The test thread is the UI thread: `tc.Deferred` parks the hand-overs and the
test drains them, and `Clock` stands in for `chat.call_later`, so no backoff is ever waited for."""
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from terminal_planner import architect as adapter
from terminal_planner import process
from terminal_planner.authority import Authority
from terminal_planner.tui import chat as chat_module

import test_terminal_planner as tp
import test_tui_chat as tc

FAIL = {"lines": tc.OPENING, "exit": 2}
REPLY = {"lines": tc.REPLY}


class Clock:
    """Keeps each delay and its callback until the test fires it."""

    def __init__(self):
        self.delays = []
        self.due = []

    def later(self, delay, call):
        self.delays.append(delay)
        self.due.append(call)

    def fire(self):
        self.due.pop(0)()


class RetryCase(tp.ProjectTest):
    """The chat helpers of test_tui_chat, borrowed without its own tests."""
    drain_until = tc.ChatUnitTests.drain_until

    def setUp(self):
        super().setUp()
        self.fixture = tc.Fixture(self.root, self.project)
        self.gate = tc.Deferred()
        self.clock = Clock()
        later = patch.object(chat_module, "call_later", self.clock.later, create=True)
        later.start()
        self.addCleanup(later.stop)

    def allow_retries(self, count):
        """An accepted profile with this `architect_retries`, in the production state under the test's HOME."""
        (self.project / process.PROFILE_FILE).write_text(json.dumps(
            {"preset": process.PRESET_V2, "autonomy": {"architect_retries": count}}))
        with Authority(None, self.project) as authority:
            process.Profile.of(authority).accept()

    def chat(self, port, *steps):
        self.fixture.script(list(steps))
        chat = chat_module.ArchitectChat(self.project, self.fixture.prepare(), binding=self.fixture.binding(),
                                         feed=port, hand_over=self.gate.hand_over)
        self.addCleanup(chat.close)
        chat.start()
        return chat

    def settle(self, chat):
        """Run the parked UI callbacks until the chat is ready and idle with nothing left parked."""
        self.assertTrue(self.drain_until(self.gate, lambda: chat.state.phase == "ready" and not chat.busy
                                         and not self.gate.pending), chat.state)

    def fire(self, chat):
        self.clock.fire()
        self.settle(chat)

    def notified(self, chat):
        chat.notify()
        self.settle(chat)

    def scheduled(self, *delays):
        self.assertEqual(self.clock.delays, list(delays), "no retry was scheduled")

    def turns(self):
        return len(self.fixture.calls())

    def last_error(self):
        return self.fixture.store().transcript()[-1]["text"]

    def assert_held_on(self, chat, cause):
        self.assertEqual(chat.state.note, chat_module.HELD % cause)

    def assert_held(self, chat):
        self.assertTrue(chat.state.note.startswith(chat_module.HELD % ""), chat.state.note)

    def remove_login(self):
        (Path(self.fixture.env["CODEX_HOME"]) / "auth.json").unlink()


class EventTurnRetries(RetryCase):
    def test_a_failed_turn_runs_again_after_the_backoff_and_a_completed_turn_restarts_the_count(self):
        self.allow_retries(2)
        port = tc.Port([tc.event(1)], {})
        chat = self.chat(port, FAIL, REPLY, FAIL)
        self.settle(chat)
        self.scheduled(5.0)
        self.assertEqual((self.turns(), port.handled), (1, []))
        self.fire(chat)
        self.assertEqual((self.turns(), port.handled), (2, [1]))
        self.scheduled(5.0)
        port.events = [tc.event(2)]
        self.notified(chat)
        self.scheduled(5.0, 5.0)

    def test_the_backoff_doubles_to_its_cap_and_then_the_chat_holds_on_the_cause(self):
        self.allow_retries(5)
        port = tc.Port([tc.event(1)], {})
        chat = self.chat(port, FAIL)
        self.settle(chat)
        self.scheduled(5.0)
        for _ in range(5):
            self.fire(chat)
        self.scheduled(5.0, 10.0, 20.0, 40.0, 60.0)
        self.assertEqual((self.turns(), port.handled), (6, []))
        self.assert_held_on(chat, self.last_error())
        reads = port.reads
        self.notified(chat)
        self.assertEqual((port.reads, self.turns()), (reads, 6))

    def test_a_notify_during_the_backoff_starts_no_check(self):
        self.allow_retries(1)
        port = tc.Port([tc.event(1)], {})
        chat = self.chat(port, FAIL, REPLY)
        self.settle(chat)
        self.scheduled(5.0)
        reads = port.reads
        self.notified(chat)
        self.assertEqual(port.reads, reads)
        self.fire(chat)
        self.assertEqual(port.handled, [1])

    def test_writing_during_the_backoff_runs_now_and_the_late_timer_does_nothing(self):
        self.allow_retries(2)
        port = tc.Port([tc.event(1)], {})
        chat = self.chat(port, FAIL, REPLY, REPLY)
        self.settle(chat)
        self.scheduled(5.0)
        self.assertEqual(chat.send("hello"), (True, ""))
        self.settle(chat)
        self.assertEqual((self.turns(), port.handled), (3, [1]))
        reads = port.reads
        self.fire(chat)
        self.assertEqual((port.reads, self.turns()), (reads, 3))
        self.scheduled(5.0)

    def test_a_failed_feed_read_is_read_again(self):
        self.allow_retries(1)
        port = tc.Port([tc.event(1)], {})
        port.pending_error = OSError("feed_down")
        chat = self.chat(port, REPLY)
        self.settle(chat)
        self.scheduled(5.0)
        self.assertEqual(self.turns(), 0)
        port.pending_error = None
        self.fire(chat)
        self.assertEqual((self.turns(), port.handled), (1, [1]))

    def test_a_failed_ack_runs_the_turn_again(self):
        self.allow_retries(1)
        port = tc.Port([tc.event(1)], {})
        port.handle_error = OSError("feed_down")
        chat = self.chat(port, REPLY)
        self.settle(chat)
        self.scheduled(5.0)
        self.assertEqual((self.turns(), port.handled), (1, []))
        port.handle_error = None
        self.fire(chat)
        self.assertEqual((self.turns(), port.handled), (2, [1]))


class HoldWithoutRetry(RetryCase):
    def test_writing_a_message_releases_the_hold_and_the_kept_events_run(self):
        self.allow_retries(1)
        port = tc.Port([tc.event(1)], {})
        chat = self.chat(port, FAIL, FAIL, REPLY, REPLY)
        self.settle(chat)
        self.fire(chat)
        self.assert_held_on(chat, self.last_error())
        self.assertEqual(chat.send("hello"), (True, ""))
        self.settle(chat)
        self.assertEqual((self.turns(), port.handled), (4, [1]))

    def test_a_project_without_an_accepted_profile_holds_after_the_first_failure(self):
        chat = self.chat(tc.Port([tc.event(1)], {}), FAIL)
        self.settle(chat)
        self.scheduled()
        self.assertEqual(self.turns(), 1)
        self.assert_held_on(chat, self.last_error())

    def test_a_rejected_login_is_not_retried(self):
        self.allow_retries(3)
        chat = self.chat(tc.Port([tc.event(1)], {}), {"lines": tc.OPENING, "stderr": "401 Unauthorized", "exit": 1})
        self.settle(chat)
        self.scheduled()
        self.assertEqual(self.turns(), 1)
        self.assert_held_on(chat, adapter.CAUSE_AUTH)

    def test_a_missing_login_is_not_retried(self):
        self.allow_retries(3)
        self.remove_login()
        chat = self.chat(tc.Port([tc.event(1)], {}), REPLY)
        self.settle(chat)
        self.scheduled()
        self.assertEqual(self.turns(), 0)
        self.assert_held(chat)
        self.assertIn("login", chat.state.note)

    def test_a_login_gone_from_a_resumed_thread_is_not_retried(self):
        self.allow_retries(3)
        port = tc.Port([tc.event(1)], {})
        chat = self.chat(port, REPLY)
        self.settle(chat)
        self.assertEqual(port.handled, [1])
        self.remove_login()
        port.events = [tc.event(2)]
        self.notified(chat)
        self.scheduled()
        self.assertEqual(self.turns(), 1)
        self.assert_held(chat)

    def test_an_event_turn_the_owner_cancelled_is_not_retried(self):
        self.allow_retries(3)
        chat = self.chat(tc.Port([tc.event(1)], {}), {"lines": tc.OPENING, "release": str(self.root / "never")})
        self.assertTrue(self.drain_until(self.gate, lambda: chat.turn_running and self.fixture.calls()), chat.state)
        self.assertTrue(chat.cancel())
        self.settle(chat)
        self.scheduled()
        self.assertEqual(self.turns(), 1)
        self.assert_held_on(chat, adapter.CAUSE_CANCELLED)

    def test_an_owner_turn_that_fails_is_never_retried(self):
        self.allow_retries(3)
        port = tc.Port([], {})
        chat = self.chat(port, FAIL)
        self.settle(chat)
        self.assertEqual(chat.send("hello"), (True, ""))
        self.settle(chat)
        self.scheduled()
        self.assertEqual(self.turns(), 1)
        self.assertEqual(chat.state.note, self.last_error())


class RealTimer(unittest.TestCase):
    def test_call_later_runs_the_call_on_a_daemon_thread_of_its_own(self):
        seen, done = [], threading.Event()

        def call():
            seen.append(threading.current_thread())
            done.set()

        chat_module.call_later(0.0, call)
        self.assertTrue(done.wait(5))
        self.assertIsNot(seen[0], threading.current_thread())
        self.assertTrue(seen[0].daemon)


if __name__ == "__main__":
    unittest.main()
