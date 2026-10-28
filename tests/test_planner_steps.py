"""P2a: the planner graph steps of one round, recorded as data (0.6.0, run p2a).

A scripted native CLI (no provider, no network) feeds the planner watch one observation record per slice: the watch
stores the step timeline of the revision's `live` metadata (`live.timeline` from `Watch.record`) and `Planning.steps`
reads it back as plain tuples. Only the data is recorded and returned here; nothing draws it.

Interpretations (the worker's summary never reaches a reviewer):

* A step is identified by its *role word* (`live.role`), not by the raw graph node name: the planner node reads as
  «planner» and both the `plan_verifier` of planner graph 1 and the `critic` of graph 2 read as «plan
  check», so one step is one role of the graph and the criteria's `plan_verifier` is the same slot. The round is the
  number of `planner` executions the timeline holds, `max(1, ...)`: the joint example's planner `e3` after verifier
  `e2` opens round 2 even though `e2` belonged to round 1, because one graph loop iteration is one round.
* A "record" is one bounded watch slice: `Watch.step` closes exactly one `live` record per slice (`Watch.record`),
  which is the granularity the criteria name. The stamps are the ones `runs.now()` returns when the slice ends;
  the test moves that clock by hand and never lets real time leak into a stamp.
* A4's "reopening the store" is read literally: the authority (and its lock) is closed and reopened between two
  records, so the persisted `first`/`end` values are the ones read, never values recomputed from a live watch.
* "the revision's run ends" is read as the terminal observation (`terminal_envelope` is committed): the record taken
  after it closes every open step, even though the last running envelope may still list executions.
"""

import json
import subprocess
import unittest
from unittest import mock

from terminal_planner import live
from terminal_planner.planning import Planning
from terminal_planner.runs import MilestoneRuns
import test_terminal_planner as tp

RUN = "R1"
T0 = "2026-10-24T01:00:00Z"
T1 = "2026-10-24T01:03:00Z"
T2 = "2026-10-24T01:04:00Z"
T3 = "2026-10-24T01:06:00Z"
T4 = "2026-10-24T01:07:00Z"
T5 = "2026-10-24T01:06:30Z"  # A2's `now`, between the fourth record and the run's end
VERIFIER = "plan check"


class Clock:
    """The wall clock the watch stamps records with; the test moves it by hand."""

    def __init__(self):
        self.at = T0

    def __call__(self):
        return self.at


class PlannerStepsTest(tp.ProjectTest):
    """The shared fixture: a native store and a scripted native CLI whose watch says one record per slice."""

    native = tp.NativeTests.native
    authority = tp.NativeTests.authority
    engine = tp.NativeTests.engine
    terminal = tp.NativeTests.terminal

    def projection(self, status, cursor="v2:10"):
        """The native projection of this run: `tp`'s shape for the revision's own run id."""
        return dict(tp.NativeTests.projection(self, status, cursor), runId=RUN)

    def planning(self, authority, engine):
        return Planning(authority, MilestoneRuns(authority, None, self.root / "worktrees"), lambda *_: engine)

    def revision(self, engine, run_id=RUN):
        """A native revision whose planner run `run_id` carries a receipt and is under observation."""
        with self.authority() as a:
            self.begin(a, "native")
            engine.prepare(a)
            a.current.update(run_id=run_id, receipt={"runId": run_id}, status="observing")
            a.save()
            return a.path

    def active(self, cursor, node, execution):
        """One running projection of the planner run with a single active execution."""
        return self.projection({"phase": "running", "activeExecutions": [{"node": node, "execution": execution}]},
                               cursor)

    def scripted(self, records, terminal):
        """`watch` hook: one running projection per call, each ending its slice as a timeout; then the terminal."""
        pending = list(records)

        def watch(argv, kwargs):
            if pending:
                raise subprocess.TimeoutExpired(argv, kwargs["timeout"],
                                                output=(json.dumps(pending.pop(0)) + "\n").encode())
            return subprocess.CompletedProcess(argv, 0, json.dumps(terminal) + "\n", b"")

        return watch


class StepCriteriaTests(PlannerStepsTest):
    """A1, A2, A4, A5 over the criteria's joint example: records at 01:00 [planner e1], 01:03 [plan_verifier e2],
    01:04 [planner e3], 01:06 [plan_verifier e4] and the run's end at 01:07."""

    def joint(self, records):
        engine, _ = self.engine([], watch=self.scripted(records, self.terminal()))
        self.revision(engine)
        return engine

    def test_a1_the_current_round_reads_the_planner_running_and_the_verifier_waiting(self):
        engine = self.joint([self.active("v2:1", "planner", "e1"), self.active("v2:2", "plan_verifier", "e2"),
                             self.active("v2:3", "planner", "e3")])
        with self.authority() as a:
            planning = self.planning(a, engine)
            clock = Clock()
            watch = planning.watch(lambda _: None)
            with mock.patch("terminal_planner.runs.now", clock):
                for stamp in (T0, T1, T2):
                    clock.at = stamp
                    self.assertEqual(watch.step(), "continue")
                self.assertEqual(planning.steps(now="2026-10-24T01:05:00Z"),
                                 (("planner", "running", 60, 2), (VERIFIER, "waiting", None, 2)))

    def test_a2_the_next_record_turns_the_planner_done_and_the_verifier_running(self):
        engine = self.joint([self.active("v2:1", "planner", "e1"), self.active("v2:2", "plan_verifier", "e2"),
                             self.active("v2:3", "planner", "e3"), self.active("v2:4", "plan_verifier", "e4")])
        with self.authority() as a:
            planning = self.planning(a, engine)
            clock = Clock()
            watch = planning.watch(lambda _: None)
            with mock.patch("terminal_planner.runs.now", clock):
                for stamp in (T0, T1, T2, T3):
                    clock.at = stamp
                    self.assertEqual(watch.step(), "continue")
                self.assertEqual(planning.steps(now=T5),
                                 (("planner", "done", 120, 2), (VERIFIER, "running", 30, 2)))

    def test_a4_reopening_the_store_keeps_the_first_and_end_stamps_of_the_records(self):
        engine = self.joint([self.active("v2:1", "planner", "e1"), self.active("v2:2", "plan_verifier", "e2"),
                             self.active("v2:3", "planner", "e3")])
        clock = Clock()
        with mock.patch("terminal_planner.runs.now", clock), self.authority() as a:
            watch = self.planning(a, engine).watch(lambda _: None)
            for stamp in (T0, T1):
                clock.at = stamp
                self.assertEqual(watch.step(), "continue")
            written = [list(step) for step in a.current["live"]["steps"]]
        self.assertEqual(written, [["planner", "e1", T0, T1], ["plan_verifier", "e2", T1, None]])
        with mock.patch("terminal_planner.runs.now", clock), self.authority() as a:
            planning = self.planning(a, engine)
            self.assertEqual([list(step) for step in planning.plan()["live"]["steps"]], written)  # persisted
            clock.at = T2
            self.assertEqual(planning.watch(lambda _: None).step(), "continue")
            self.assertEqual([list(step) for step in a.current["live"]["steps"]],
                             [["planner", "e1", T0, T1], ["plan_verifier", "e2", T1, T2],
                              ["planner", "e3", T2, None]])

    def test_a3_a_store_written_before_p2a_loads_and_reads_as_two_waiting_nodes_of_round_one(self):
        engine, _ = self.engine([])
        self.revision(engine)
        with self.authority() as a:
            older = live.new()
            del older["steps"]  # the shape written before P2a
            a.current["live"] = older
            a.save()
        with self.authority() as a:
            planning = self.planning(a, engine)
            self.assertNotIn("steps", a.current["live"])  # an older record is read as it was, never rewritten
            self.assertEqual(planning.steps(), (("planner", "waiting", None, 1), (VERIFIER, "waiting", None, 1)))

    def test_a5_the_run_end_closes_open_steps_and_the_last_round_is_kept(self):
        engine = self.joint([self.active("v2:1", "planner", "e1"), self.active("v2:2", "plan_verifier", "e2"),
                             self.active("v2:3", "planner", "e3"), self.active("v2:4", "plan_verifier", "e4")])
        with self.authority() as a:
            planning = self.planning(a, engine)
            clock = Clock()
            watch = planning.watch(lambda _: None)
            with mock.patch("terminal_planner.runs.now", clock):
                for stamp in (T0, T1, T2, T3):
                    clock.at = stamp
                    self.assertEqual(watch.step(), "continue")
                clock.at = T4
                self.assertEqual(watch.step(), "done")  # the terminal observation ends the run
                self.assertEqual(planning.steps(now=T4),
                                 (("planner", "done", 120, 2), (VERIFIER, "done", 60, 2)))
                self.assertEqual([list(step) for step in a.current["live"]["steps"]][-1],
                                 ["plan_verifier", "e4", T3, T4])

    def test_a5_a_run_the_owner_stopped_closes_its_open_steps_the_same_way(self):
        # the criterion's "(also `stopped` from p1a)": the terminal observation that concludes an owner stop.
        engine, _ = self.engine([], watch=self.scripted([self.active("v2:1", "planner", "e1")],
                                                        self.terminal(failed=True)))
        self.revision(engine)
        with self.authority() as a:
            planning = self.planning(a, engine)
            clock = Clock()
            watch = planning.watch(lambda _: None)
            with mock.patch("terminal_planner.runs.now", clock):
                clock.at = T0
                self.assertEqual(watch.step(), "continue")
                a.current["stop"] = {"at": T1}  # p1a: the owner asked to stop the run under observation
                a.save()
                clock.at = T4
                watch.step()  # the terminal observation concludes the stop and the record closes the steps
                self.assertEqual(a.current["status"], "stopped")
                self.assertEqual(planning.steps(now=T4),
                                 (("planner", "done", 420, 1), (VERIFIER, "waiting", None, 1)))


class TimelineTests(unittest.TestCase):
    """The timeline invariant the criteria drive indirectly: bounded steps and steps that close when they leave."""

    def test_the_timeline_keeps_the_newest_steps_and_closes_a_step_whose_execution_left(self):
        data = live.new()
        live.timeline(data, [{"node": "planner", "execution": "e0"}], T0)
        self.assertEqual(data["steps"], [["planner", "e0", T0, None]])
        live.timeline(data, [{"node": "plan_verifier", "execution": "e1"}], T1)
        self.assertEqual(data["steps"], [["planner", "e0", T0, T1], ["plan_verifier", "e1", T1, None]])
        live.timeline(data, [], T3, ended=True)  # the run ended: no execution is active any more
        self.assertEqual(data["steps"][-1], ["plan_verifier", "e1", T1, T3])
        for n in range(2, live.STEPS_LIMIT + 2):
            live.timeline(data, [{"node": "planner", "execution": "e%d" % n}], "2026-10-24T02:%02d:00Z" % n)
        self.assertEqual(len(data["steps"]), live.STEPS_LIMIT)  # oldest dropped
        self.assertEqual((data["steps"][0][1], data["steps"][-1][1]),
                         ("e2", "e%d" % (live.STEPS_LIMIT + 1)))
        self.assertTrue(live.valid(data))


if __name__ == "__main__":
    unittest.main()
