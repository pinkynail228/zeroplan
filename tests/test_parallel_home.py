"""A9t: the parallel bound of the live profile reaches the home screen and the delivery service.

One smoke test per criterion (C1 the slot count, C2 the full/busy notion and its two refusal texts, C3 the one
service cap guard on every path that creates an attempt) plus the reading the single slot keeps. C4's controller guard (a
queued slice never polls the successor attempt) is here, at the worker level; the rest of C4 (every running attempt
observed by its own chain, the shown attempt switching on [w]) drives the whole app and lives in
`tests/test_tui_live.py`.

Interpretations (the reviewers never see the worker's summary; none of them waives a stated requirement):
- C1's "the live profile read with `status(write=False)`" is read as the same read `task_gate_admission` uses: the
  bound `Authority.profile`, uncapped by the engine's `runs.MAX_RUNS` only after `min`. A profile whose read raises
  (a corrupt store, an unreadable file) is the single slot, never a crash -- today's behaviour, no example named it.
- "not accepted" covers the profile with no accepted record ("never"): its resolved proposal is not the live bound,
  so the single slot stands, as the preset /1 does.
- C2's "the active milestones (running, stopping, unknown)" is the delivery service's own `ACTIVE` plus "unknown",
  the same tuple `busy` names in its row order; the cap is `slots()`, not the engine's `MAX_RUNS`.
- C3's `accept` guard is only the attempt branch (`runs.candidate(r)` is a structured in-scope proposal), exactly
  as the requirement scopes it: a plan revision that accepting opens is not an attempt.
"""

import json
import threading
from types import SimpleNamespace
import unittest

from terminal_planner import planning, process, runs
from terminal_planner.authority import Blocked, canonical
from terminal_planner.delivery import Delivery, Slice, full_line
from terminal_planner.engine import FixtureEngine
from terminal_planner.tui import controller as tui_controller
from test_parallel_runs import ROLES, ParallelRunsTest, added_candidate, parallel_plan


class SlotsTests(ParallelRunsTest):
    def service(self, authority, controller):
        return Delivery(authority, controller, planning.Planning(authority, controller, lambda *_: FixtureEngine()))

    def record(self, authority, doc):
        """Bind `doc` as the accepted project profile (the file stays out of the tree the milestone start reads
        clean), as `bind_slots` does for the /2 preset."""
        (self.project / process.PROFILE_FILE).write_text(json.dumps(doc))
        with (self.project / ".git" / "info" / "exclude").open("a", encoding="utf-8") as handle:
            handle.write("\n%s\n" % process.PROFILE_FILE)
        authority.profile = process.Profile.of(authority)
        authority.profile.accept()
        return authority.profile

    def test_c1_slots_are_the_accepted_profiles_max_runs_capped_by_the_engine(self):
        with self.fixture_authority() as a:
            self.approve_parallel(a)
            service = self.service(a, self.fixture_runs(a))
            self.assertEqual(service.slots(), 1)  # no profile bound: today's single slot
            self.record(a, {"preset": process.PRESET_V2})  # the /2 preset's own max_runs: 3
            self.assertEqual(service.slots(), 3)
            self.bind_slots(a, 2)
            self.assertEqual(service.slots(), 2)
            self.bind_slots(a, 5)
            self.assertEqual(service.slots(), runs.MAX_RUNS)  # the engine's hard cap, regardless of the profile

    def test_c1_a_preset_without_autonomy_and_an_unaccepted_or_unreadable_profile_keep_one_slot(self):
        with self.fixture_authority() as a:
            self.approve_parallel(a)
            service = self.service(a, self.fixture_runs(a))
            self.record(a, {"preset": process.PRESET})  # the /1 preset: no autonomy section at all
            self.assertEqual(service.slots(), 1)
            a.profile = process.Profile.of(a)  # re-read: the file is present but no accepted record remains
            (a.directory / process.STATE_FILE).unlink(missing_ok=True)
            self.assertEqual(service.slots(), 1)
            a.profile = None
            self.assertEqual(service.slots(), 1)

            class Unreadable:
                def status(self, write=True):
                    raise OSError("store gone")
            a.profile = Unreadable()
            self.assertEqual(service.slots(), 1)  # a read that fails is the single slot, never a crash


class BusyTests(ParallelRunsTest):
    def service(self, authority, controller):
        return Delivery(authority, controller, planning.Planning(authority, controller, lambda *_: FixtureEngine()))

    def test_c2_busy_names_the_first_active_only_once_every_slot_is_taken(self):
        two = [{"id": "M1", "state": "running", "record": {}}, {"id": "M2", "state": "running", "record": {}}]
        self.assertIsNone(Delivery.busy(two, 3))  # a free slot: nothing is held back
        self.assertEqual(Delivery.busy(two, 2)["id"], "M1")
        self.assertEqual(Delivery.busy(two)["id"], "M1")  # the single slot, unchanged
        three = two + [{"id": "M3", "state": "unknown", "record": {}}]
        self.assertEqual(Delivery.busy(three, 3)["id"], "M1")
        self.assertIsNone(Delivery.busy(three, 4))  # "unknown" counts like running and stopping

    def test_c2_the_full_refusal_names_the_slots_and_the_active_milestones(self):
        self.assertIsNone(full_line(["M1"], 1))  # the single slot keeps its own line, byte for byte
        self.assertEqual(full_line(["M1", "M2"], 2),
                         "All 2 slots are busy (M1, M2): a new start, a continuation and a new attempt wait. "
                         "[w] watch, [g] check.")

    def test_c2_pick_and_home_start_below_the_cap_and_refuse_with_the_full_line_at_it(self):
        with self.fixture_authority() as a:
            self.approve_parallel(a)
            self.bind_slots(a, 3)
            controller = self.fixture_runs(a)
            service = self.service(a, controller)
            service.start(service.preview("M1", ROLES), ROLES)
            home = service.home()  # one of three slots taken: a ready milestone is startable
            self.assertEqual((home.slots, home.busy), (3, None))
            self.assertEqual(home.g, "home.start")
            self.assertEqual(service.pick("g", "M2", home).kind, "start")
            service.start(service.preview("M2", ROLES), ROLES)
            service.start(service.preview("M5", ROLES), ROLES)  # three disjoint attempts: the cap is reached
            full = service.home()
            self.assertEqual((full.slots, full.busy), (3, "M1"))
            self.assertIsNone(full.g)
            pick = service.pick("g", "M7", full)  # [g] on a ready milestone behind the full slots
            self.assertEqual(pick.kind, "message")
            self.assertEqual(pick.text, full_line(["M1", "M2", "M5"], 3))


class GuardTests(ParallelRunsTest):
    def test_c3_every_path_that_creates_an_attempt_is_refused_at_the_cap_before_any_record(self):
        with self.fixture_authority() as a:
            self.approve_parallel(a)
            self.bind_slots(a, 1)
            controller = self.fixture_runs(a)
            # a terminal attempt of M6 (fail-closed, alone) and a needs_owner of M1 with a structured candidate:
            # the records the follow-up paths act on, created before the single slot is taken
            controller.engine = runs.FixtureDriver(self.root / "fixture-runs", "failed_recoverable")
            failed = controller.observe(controller.start("M6", 1, ROLES))
            self.assertEqual(runs.run_state(failed), "failed_recoverable")
            controller.engine = runs.FixtureDriver(self.root / "fixture-runs", "needs_owner",
                                                   proposal=canonical(added_candidate(parallel_plan(), "M1", "T1x",
                                                                                      ["e.py"])))
            owner = controller.observe(controller.start("M1", 1, ROLES))
            self.assertEqual(owner["outcome"], "needs_owner")
            controller.engine = runs.FixtureDriver(self.root / "fixture-runs", "done")
            controller.start("M2", 1, ROLES)  # the one running attempt: the single slot is full
            service = Delivery(a, controller, planning.Planning(a, controller, lambda *_: FixtureEngine()))
            before = len(controller.runs)
            with self.assertRaisesRegex(Blocked, r"The profile's limit of parallel milestone runs \(1\) is reached"):
                service.start(service.preview("M5", ROLES), ROLES)
            for call in (lambda: service.new_attempt(owner), lambda: service.answer(owner, "Use the fixture path."),
                         lambda: service.resume(failed), lambda: service.accept(owner)):
                with self.assertRaisesRegex(Blocked, r"limit of parallel milestone runs \(1\) is reached"):
                    call()
            self.assertEqual(len(controller.runs), before)  # no refusal created a record

    def test_c3_below_the_cap_the_services_own_admission_refusal_is_what_surfaces(self):
        with self.fixture_authority() as a:
            self.approve_parallel(a)
            self.bind_slots(a, 2)
            controller = self.fixture_runs(a)
            service = Delivery(a, controller, planning.Planning(a, controller, lambda *_: FixtureEngine()))
            service.start(service.preview("M1", ROLES), ROLES)
            # one of two slots is free, so the guard lets it through and `admit` refuses the overlap itself
            with self.assertRaisesRegex(Blocked, r"Milestone M3 overlaps with M1 \(a\.py\): it waits for it to finish\."):
                service.start(service.preview("M3", ROLES), ROLES)
            self.assertEqual([r["milestone"] for r in controller.runs if r["status"] in runs.ACTIVE], ["M1"])


def run_record(milestone, attempt, run_id, status="running"):
    """One attempt record as `Delivery.latest` hands it to a watch slice: `run_state` reads `status`/`outcome`."""
    return {"milestone": milestone, "plan_revision": 1, "attempt": attempt, "run_id": run_id, "status": status,
            "outcome": None}


class ObserveIdentityTests(unittest.TestCase):
    """C4 (the A9t repair): a queued watch slice belongs to one attempt, and `Controller.observe_run` checks that
    identity on the worker before it polls -- so a slice of an attempt the milestone has left behind ends without
    polling the successor, without consuming its events and without emitting its lines through the predecessor's
    callback (the reproduction: queue M2's slice, stop and reconcile it, start a new attempt, then run the slice).

    The delivery is a fake whose `latest` names the milestone's current attempt: the guard under test is
    `observe_run`'s own identity check, exactly as the task scopes it, so no store, plan or fixture driver runs."""

    @staticmethod
    def fake_delivery(record):
        class FakeDelivery:
            def __init__(self):
                self.polled = []

            def latest(self, milestone_id):
                return record if milestone_id == record["milestone"] else None

            def step(self, r, mark, seconds):
                self.polled.append(r["run_id"])  # the mutating poll: the successor must never reach it
                return Slice(("T2 · implementation",), "cursor", True)

        return FakeDelivery()

    def controller(self, delivery):
        controller = tui_controller.Controller(lambda stack: SimpleNamespace(delivery=delivery), "identity")
        controller.start()
        self.addCleanup(controller.stop)
        return controller

    def observe(self, controller, milestone, run_id):
        """Post one slice and wait for its verdict (the worker thread calls `done`)."""
        events, verdict, reached = [], [], threading.Event()
        self.assertTrue(controller.observe_run(
            milestone, events.append,
            lambda outcome, error: (verdict.append((outcome, error)), reached.set()), run_id=run_id))
        self.assertTrue(reached.wait(5), "the slice's verdict never came back")
        return events, verdict[0]

    def test_c4_observe_run_never_polls_the_successor_of_a_left_behind_attempt(self):
        delivery = self.fake_delivery(run_record("M2", 2, "new-run"))
        events, (outcome, error) = self.observe(self.controller(delivery), "M2", "old-run")
        self.assertIsNone(error)
        self.assertEqual(delivery.polled, [])  # C4: the successor attempt was never polled for the old one's slice
        self.assertEqual(events, [])  # nor did its lines reach the old attempt's callback
        self.assertEqual(outcome.kind, "ended")

    def test_c4_observe_run_polls_the_attempt_the_slice_was_queued_for(self):
        delivery = self.fake_delivery(run_record("M2", 1, "run-1"))
        events, (outcome, error) = self.observe(self.controller(delivery), "M2", "run-1")
        self.assertIsNone(error)
        self.assertEqual(delivery.polled, ["run-1"])  # a matching identity is polled as before
        self.assertEqual(events, ["T2 · implementation"])
        self.assertEqual(outcome.kind, "continue")


if __name__ == "__main__":
    unittest.main()
