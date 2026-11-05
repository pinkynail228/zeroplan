# tests/test_limit_resume.py
"""A provider limit pauses a recoverable attempt until an absolute `resume_at`; `Controller.resume_due` resumes what
is due, once, under the autonomy policy; a second limit of the same attempt goes to the architect.

Real Git, stores and the fixture driver, with the wall clock of `runs.now` under the test's hand. The classes without
a Controller need no socket; `ResumeDueTests` opens the bridge socket."""
from datetime import datetime, timedelta, timezone
import threading
import unittest
from unittest.mock import patch

from terminal_planner import engine, feed
from terminal_planner.authority import Blocked
from terminal_planner.runs import FixtureDriver, MilestoneRuns, run_state

import test_bridge as tb
import test_terminal_planner as tp
from test_terminal_planner import ROLES
from test_tui import Readiness, check

STAMP = "%Y-%m-%dT%H:%M:%SZ"
NOON = "2026-11-04T12:00:00Z"
RESET = "3:10pm (UTC)"
MOMENT = "2026-11-04T15:12:00Z"  # the reset plus the 120-second margin
JUST_BEFORE = "2026-11-04T15:11:59Z"
FALLBACK = "2026-11-04T12:30:00Z"  # thirty minutes after NOON
REAL_MESSAGE = "You've hit your limit · resets 3am (Europe/Moscow)"
MOSCOW = "3am (Europe/Moscow)"
MOMENTS = (
    (RESET, "2026-11-04T15:10:00Z"),
    ("11am (UTC)", "2026-11-05T11:00:00Z"),
    (MOSCOW, "2026-11-05T00:00:00Z"),
    ("Nov 6, 3pm (UTC)", "2026-11-06T15:00:00Z"),
    ("Jan 2, 3pm (UTC)", "2027-01-02T15:00:00Z"),
    ("Nov 4, 11am (UTC)", "2027-11-04T11:00:00Z"),
    ("12am (UTC)", "2026-11-05T00:00:00Z"),
    ("12pm (UTC)", "2026-11-05T12:00:00Z"),
)
IMPOSSIBLE = ("Feb 31, 3pm", "13:99pm", "13pm (UTC)", "0am (UTC)", "3pm (Mars/Olympus)")
UNUSABLE = (None,) + IMPOSSIBLE[:2] + (IMPOSSIBLE[4], "Nov 20, 3pm (UTC)")  # the last is over 8 days away


def local(stamp):
    moment = datetime.strptime(stamp, STAMP).replace(tzinfo=timezone.utc)
    return moment.astimezone().strftime("%Y-%m-%d %H:%M")


class ResetMomentTests(unittest.TestCase):
    def test_a_reset_value_becomes_its_first_moment_after_the_anchor(self):
        for value, expected in MOMENTS:
            with self.subTest(value):
                self.assertEqual(engine.reset_moment(value, NOON), expected)

    def test_an_impossible_value_has_no_moment(self):
        for value in IMPOSSIBLE:
            with self.subTest(value):
                self.assertIsNone(engine.reset_moment(value, NOON))

    def test_a_value_without_a_zone_is_read_in_local_time(self):
        anchor = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc).astimezone()
        expected = anchor.replace(hour=15, minute=10, second=0, microsecond=0)
        if expected <= anchor:
            expected += timedelta(days=1)
        self.assertEqual(engine.reset_moment("3:10pm", NOON), expected.astimezone(timezone.utc).strftime(STAMP))

    def test_the_real_limit_wording_is_a_limit_with_its_reset(self):
        self.assertEqual(engine.classify(REAL_MESSAGE), "limit")
        self.assertEqual(engine.reset_text(REAL_MESSAGE), MOSCOW)


class LimitBase(tp.ProjectTest):
    """The live-controller helpers of test_bridge.BridgeCase, borrowed without its own tests, and a clock."""
    def setUp(self):
        super().setUp()
        self.now = NOON
        clock = patch("terminal_planner.runs.now", lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)
        self.driver = FixtureDriver(self.root / "fixture-runs")

    attempt = tb.BridgeCase.attempt
    finish = staticmethod(tb.BridgeCase.finish)
    write_profile = tb.BridgeCase.write_profile
    controller = tb.BridgeCase.controller
    controller_stop = tb.BridgeCase.controller_stop
    _controllers = tb.BridgeCase._controllers
    call = tb.BridgeCase.call
    rows = tb.BridgeCase.rows

    def limited(self, cause="limit", reset=None, after_resume="done", recoverable=True):
        """The approved fixture plan with the feed on and one M1 attempt that ended on a scripted provider limit."""
        self.driver = FixtureDriver(self.root / "fixture-runs", outcome="failed_limit")
        self.driver.cause, self.driver.reset, self.driver.after_resume = cause, reset, after_resume
        if not recoverable:
            real = self.driver.status
            self.driver.status = lambda r, run_id: {**real(r, run_id), "workspaceRecovery": {"recoverable": False}}
        with tp.Authority(self.state, self.project) as authority:
            self.begin(authority)
            self.propose(authority)
            authority.approve(1)
            feed.bootstrap(authority)
            runs = MilestoneRuns(authority, self.driver, worktrees=authority.directory / "worktrees")
            return self.finish(runs, runs.start("M1", 1, ROLES))

    def stored(self):
        """(the run records, the unhandled feed events); the session lock must be free."""
        with tp.Authority(self.state, self.project) as authority:
            return list(authority.state["runs"]), feed.pending(authority, None)[0]

    def state_events(self, state):
        return [event for event in self.stored()[1] if event["kind"] == "state" and event["state"] == state]


class LimitPauseTests(LimitBase):
    def test_a_limit_pauses_until_the_stated_reset_plus_the_margin(self):
        record = self.limited(reset=RESET)
        self.assertEqual(run_state(record), "paused")
        self.assertEqual(record["resume_at"], MOMENT)
        self.assertEqual(record["cause"], "limit")

    def test_the_pause_does_not_wake_the_architect(self):
        self.limited(reset=RESET)
        paused = self.state_events("paused")
        self.assertEqual([event["wake"] for event in paused], [False])
        self.assertEqual(self.state_events("failed"), [])
        self.assertEqual(self.state_events("failed_recoverable"), [])

    def test_an_unusable_reset_waits_thirty_minutes(self):
        for reset in UNUSABLE:
            with self.subTest(reset):
                self.setUp()
                record = self.limited(reset=reset)
                self.assertEqual((run_state(record), record["resume_at"]), ("paused", FALLBACK))

    def test_a_quota_failure_pauses_for_thirty_minutes(self):
        record = self.limited(cause="quota")
        self.assertEqual((run_state(record), record["cause"], record["resume_at"]), ("paused", "quota", FALLBACK))

    def test_a_limit_that_cannot_recover_stays_failed(self):
        record = self.limited(reset=RESET, recoverable=False)
        self.assertEqual((run_state(record), record["cause"]), ("failed", "limit"))
        self.assertNotIn("resume_at", record)

    def test_another_recoverable_failure_does_not_pause(self):
        record = self.attempt("failed_recoverable")
        self.assertEqual(run_state(record), "failed_recoverable")
        self.assertNotIn("resume_at", record)

    def test_the_store_refuses_a_resume_at_beside_another_cause(self):
        self.attempt("failed_recoverable")
        with tp.Authority(self.state, self.project) as authority:
            runs = MilestoneRuns(authority, self.driver, worktrees=authority.directory / "worktrees")
            record = runs.current_record("M1")
            record["resume_at"] = MOMENT
            with self.assertRaises(Blocked):
                runs.save(record)

    def test_the_store_refuses_a_resume_at_that_is_no_time(self):
        self.limited(reset=RESET)
        with tp.Authority(self.state, self.project) as authority:
            runs = MilestoneRuns(authority, self.driver, worktrees=authority.directory / "worktrees")
            record = runs.current_record("M1")
            record["resume_at"] = "soon"
            with self.assertRaises(Blocked):
                runs.save(record)

    def test_a_second_limit_of_the_attempt_goes_to_the_architect(self):
        """An early resume by hand uses up the attempt's one automatic chance as well."""
        self.limited(reset=RESET, after_resume="failed_limit")
        with tp.Authority(self.state, self.project) as authority:
            runs = MilestoneRuns(authority, self.driver, worktrees=authority.directory / "worktrees")
            successor = self.finish(runs, runs.resume(runs.current_record("M1")))
        self.assertEqual(run_state(successor), "failed_recoverable")
        self.assertNotIn("resume_at", successor)
        self.assertEqual([event["wake"] for event in self.state_events("failed_recoverable")], [True])


class ResumeDueTests(LimitBase):
    def m1(self):
        return next(item for item in self.rows()["rows"] if item["id"] == "M1")

    def job(self, call, *args):
        """One controller job, answered: its result; a job that failed fails the test."""
        event, box = threading.Event(), {}

        def done(result, error):
            box.update(result=result, error=error)
            event.set()

        self.assertTrue(call(*args, done))
        self.assertTrue(event.wait(30))
        self.assertIsNone(box["error"], box)
        return box["result"]

    def tick(self, controller):
        self.job(controller.resume_due)

    def on_worker(self, controller, work):
        return self.job(lambda done: controller.post("limit_read", work, done))

    def paused_session(self, level="auto", **script):
        self.write_profile(level=level)
        self.limited(**script)
        return self.controller(profile=True)

    def test_nothing_is_resumed_before_the_moment_and_one_successor_after_it(self):
        controller = self.paused_session(reset=RESET)
        row = self.m1()
        self.assertEqual(row["state"], "paused")
        self.tick(controller)
        self.now = JUST_BEFORE
        self.tick(controller)
        self.assertEqual(self.m1()["run_id"], row["run_id"])
        self.now = MOMENT
        self.tick(controller)
        resumed = self.m1()
        self.assertNotEqual(resumed["run_id"], row["run_id"])
        self.assertEqual(resumed["attempt"], 1)
        self.tick(controller)
        self.assertEqual(self.m1()["run_id"], resumed["run_id"])
        self.controller_stop()
        records, _ = self.stored()
        self.assertEqual([record["predecessor"] for record in records], [None, row["run_id"]])
        with tp.Authority(self.state, self.project) as authority:
            runs = MilestoneRuns(authority, self.driver, worktrees=authority.directory / "worktrees")
            successor = self.finish(runs, runs.current_record("M1"))
        self.assertEqual(run_state(successor), "awaiting_merge")

    def test_a_reopened_session_resumes_what_came_due_while_it_was_closed(self):
        self.paused_session(reset=RESET)
        self.controller_stop()
        self.now = MOMENT
        controller = self.controller(profile=True)
        self.tick(controller)
        self.tick(controller)
        self.controller_stop()
        self.assertEqual(len(self.stored()[0]), 2)

    def test_auto_and_supervised_resume_without_a_card(self):
        for level in ("auto", "supervised"):
            with self.subTest(level):
                self.setUp()
                controller = self.paused_session(level=level, reset=RESET)
                before = self.m1()["run_id"]
                self.now = MOMENT
                self.tick(controller)
                self.assertIsNone(controller.consent_request)
                self.assertNotEqual(self.m1()["run_id"], before)
                self.controller_stop()

    def test_manual_asks_once_when_due_and_the_owners_yes_resumes(self):
        controller = self.paused_session(level="manual", reset=RESET)
        before = self.m1()["run_id"]
        self.tick(controller)
        self.assertIsNone(controller.consent_request)
        self.now = MOMENT
        self.tick(controller)
        request = controller.consent_request
        self.assertEqual((request.action, request.state), ("resume", "awaiting"))
        self.assertEqual((self.m1()["state"], self.m1()["run_id"]), ("paused", before))
        self.tick(controller)
        self.assertEqual(controller.consent_request.id, request.id)
        self.job(controller.consent, request.id)
        self.assertNotEqual(self.m1()["run_id"], before)

    def test_manual_asks_again_after_a_reopen(self):
        self.paused_session(level="manual", reset=RESET)
        self.now = MOMENT
        self.controller_stop()
        controller = self.controller(profile=True)
        self.assertIsNone(controller.consent_request)
        self.tick(controller)
        self.assertEqual(controller.consent_request.state, "awaiting")

    def test_the_owners_no_ends_the_pause_and_wakes_the_architect(self):
        controller = self.paused_session(level="manual", reset=RESET)
        before = self.m1()["run_id"]
        self.now = MOMENT
        self.tick(controller)
        request = controller.consent_request
        self.job(controller.decline, request.id)
        self.assertEqual(self.m1()["state"], "failed_recoverable")
        self.tick(controller)
        self.assertEqual((controller.consent_request.id, controller.consent_request.state), (request.id, "declined"))
        self.assertEqual(self.m1()["run_id"], before)
        self.controller_stop()
        self.assertNotIn("resume_at", self.stored()[0][0])
        self.assertEqual([event["wake"] for event in self.state_events("failed_recoverable")], [True])

    def test_an_event_turn_may_not_act_on_a_paused_attempt_but_the_owners_turn_may(self):
        controller = self.paused_session(reset=RESET)
        row = self.m1()
        resume = {"milestone": "M1", "token": row["token"]}
        for tool, args in (("zplan_resume", resume), ("zplan_rebrief", dict(resume, note="again"))):
            refused = self.call(tool, args, rid=tool)
            self.assertEqual(refused.get("error"), "action.refused", refused)
        self.assertEqual(self.m1()["run_id"], row["run_id"])
        turn = controller.begin_turn("Continue M1", 3)
        reply = self.call("zplan_resume", resume, rid="own", turn=turn)
        self.assertEqual(reply.get("ok", {}).get("attempt"), 1, reply)
        self.assertNotEqual(self.m1()["run_id"], row["run_id"])

    def test_the_automatic_resume_costs_the_architect_no_attempt(self):
        self.write_profile(level="auto")
        self.limited(reset=RESET, after_resume="failed")
        self.driver.outcomes = ("failed_limit", "failed", "failed")
        controller = self.controller(profile=True)
        self.now = MOMENT
        self.tick(controller)
        self.controller_stop()
        with tp.Authority(self.state, self.project) as authority:
            runs = MilestoneRuns(authority, self.driver, worktrees=authority.directory / "worktrees")
            record = self.finish(runs, runs.current_record("M1"))
            self.finish(runs, runs.retry(record, "another way"))
        self.controller(profile=True)
        row = self.m1()
        self.assertEqual((row["state"], row["attempt"]), ("failed", 2))
        reply = self.call("zplan_rebrief", {"milestone": "M1", "token": row["token"], "note": "again"}, rid="rb")
        self.assertEqual(reply.get("ok", {}).get("attempt"), 3, reply)

    def test_a_readiness_refusal_keeps_the_pause_and_the_next_tick_resumes(self):
        self.write_profile(level="auto")
        self.limited(reset=RESET)
        readiness = Readiness(check("git", False))
        controller = self.controller(profile=True, readiness=readiness)
        before = self.m1()["run_id"]
        self.now = MOMENT
        self.tick(controller)
        self.assertEqual((self.m1()["state"], self.m1()["run_id"]), ("paused", before))
        readiness.fix("git")
        self.tick(controller)
        self.assertNotEqual(self.m1()["run_id"], before)

    def test_a_run_that_can_no_longer_recover_goes_to_the_architect(self):
        controller = self.paused_session(reset=RESET)
        before = self.m1()["run_id"]
        state = self.driver.load(before)
        state["recoverable"] = False
        self.driver.store(state)
        self.now = MOMENT
        self.tick(controller)
        self.assertEqual((self.m1()["state"], self.m1()["run_id"]), ("failed_recoverable", before))
        last = self.call("zplan_status")["ok"]["results"][-1]
        self.assertEqual((last["operation"], last["origin"], last["outcome"]), ("resume", "zplan", "refused"))
        self.controller_stop()
        self.assertNotIn("resume_at", self.stored()[0][0])
        self.assertEqual([event["wake"] for event in self.state_events("failed_recoverable")], [True])

    def test_the_owner_hears_of_the_automatic_resume_once(self):
        controller = self.paused_session(reset=RESET)
        seen = []
        controller.on_result = seen.append
        self.now = MOMENT
        self.tick(controller)
        self.tick(controller)
        self.assertEqual([(item["operation"], item["origin"], item["outcome"]) for item in seen],
                         [("resume", "zplan", "done")])

    def test_a_paused_row_names_its_time_and_stays_reachable(self):
        controller = self.paused_session(reset=RESET)
        home = self.on_worker(controller, lambda app: app.delivery.home())
        self.assertEqual(home.focus.id, "M1")
        self.assertIn("home.open", home.ids)
        row = next(item for item in home.rows if item.id == "M1")
        self.assertEqual(row.state, "paused")
        self.assertIn(local(MOMENT), row.text)
        view = self.on_worker(controller, lambda app: app.delivery.view(app.delivery.latest("M1")))
        self.assertEqual((view.state, view.actions), ("paused", ()))
        self.assertTrue(any(local(MOMENT) in line for line in view.body))
        self.assertIn(local(MOMENT), self.m1()["reason"]["body"])


if __name__ == "__main__":
    unittest.main()
