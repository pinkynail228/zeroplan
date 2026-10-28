"""P1a: stopping a running planner from the `zplan` plan screen, with the cause kept (0.6.0, run p1a).

Fixture native store and a scripted native CLI (no provider, no network): the planner run R1 is under observation,
`[s]` asks the engine to force-stop it and the observation then concludes it as `stopped`, not as a failure.

Interpretations (the worker's summary never reaches a reviewer):

* "saves a stop request with its time before calling native force-stop" is read as *durable*: `A1` reads the store
  file from inside the fake `force-stop` call, so the request is already persisted when the call happens (not only
  in memory). "A refused call keeps the revision as it was" is read as removing only the request *this* call added:
  a first refusal leaves no request (so a later natural failure is not mislabelled `stopped`, `A5`), while a retry
  the engine refuses or never answers keeps an already confirmed request and its time untouched.
* The stop time is the stored UTC stamp (`runs.now()`, pinned), shown as `HH:MM` in the local zone (P2b): `A2`
  pins `TZ=UTC` for «Plan r1 was stopped by you at 01:40.», and `A2b` shows «… at 04:40.» under `TZ=Europe/Moscow`
  while the stored stamp stays UTC.
* "fixture planner observing r1, run R1" is read as the deterministic test double of `A1`'s joint example: a real
  native revision whose run id is `R1` and whose engine is a scripted native CLI. `R1` is the run id string, not
  the projection helper's own `fixture-native-run`.
* `A4`'s "r2 is submitted" is read at the service boundary: `Planning.restart()` only prepares and returns `ready`
  (the engine submits inside `proposal`), so the test drives `proposal` for r2 and checks the `--detach` call.
* "a revision with a stop request becomes `stopped`" is read as *whenever the observation ends the run*: the
  request wins on a force-stopped failure and equally on a run that finished successfully before the request
  reached the engine (upstream permits a force-stop against an already-terminal run, so completion racing the
  request is realistic). The native terminal evidence is retained either way; a succeeded terminal that raced the
  stop never becomes a `proposed` plan.
* The native lifecycle requirement is read like a milestone stop's `check_binding`: `force_stop` validates the
  frozen binding before dispatching, so a planner reopened with another `--native-state-dir` refuses instead of
  sending `force-stop` into the wrong `<state_root>/runs`.
"""

import io
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from terminal_planner import catalog
from terminal_planner.authority import Authority as RealAuthority, Blocked, decode
from terminal_planner.cli import Terminal, session
from terminal_planner.planning import Planning
from terminal_planner.runs import MilestoneRuns
import test_terminal_planner as tp
from test_setup import Steps

RUN = "R1"
NEXT = "R2"
STOP_AT = "2026-10-24T01:40:00Z"
STOPPED_LINE = "Plan r1 was stopped by you at 01:40."


class PlanStopTest(tp.ProjectTest):
    """The shared fixture: a native store, a scripted native CLI and helpers over both."""

    native = tp.NativeTests.native
    engine = tp.NativeTests.engine
    projection = tp.NativeTests.projection
    terminal = tp.NativeTests.terminal

    def setUp(self):
        super().setUp()
        self.zone("UTC")  # the stop line is local time (P2b): the fixtures read it in UTC unless a test sets another

    def authority(self):
        return RealAuthority(None, self.project)

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

    def zone(self, name):
        """The process time zone set to `name` until the test ends."""
        before = os.environ.get("TZ")

        def restore():
            if before is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = before
            time.tzset()
        self.addCleanup(restore)
        os.environ["TZ"] = name
        time.tzset()

    def finished(self, run_id, version, reason="force_stopped"):
        """The failed terminal envelope of `run_id` (the run of revision `version`, ended by force)."""
        return {"runId": run_id, "subscriptionId": "fixture-subscription",
                "title": "Terminal roadmap revision %s" % version,
                "source": {"repository": "example/fixture", "branch": self.git("branch", "--show-current").decode().strip(),
                           "revision": self.git("rev-parse", "HEAD").decode().strip()},
                "size": "medium", "cursor": "v2:9",
                "status": {"phase": "finished", "terminalResult": {"status": "failed", "reason": reason}}}

    def succeeded(self, run_id, version=1):
        """The succeeded terminal envelope of `run_id`: a run that finished with a valid review before the owner's
        stop request reached the engine (the race the stop must still win)."""
        envelope = self.finished(run_id, version)
        review = self.terminal()  # a valid execution-2 plan review output
        envelope["status"]["terminalResult"] = review["status"]["terminalResult"]
        return envelope

    def journey(self, engine, *steps):
        output = io.StringIO()
        session(Terminal(Steps(*steps), output), self.project, None, lambda *_: engine)
        return output.getvalue()

    def stored(self, path):
        return decode(path.read_text())

    def capture(self, engine, path, seen):
        """Wrap the engine's call so the persisted revision is read at the moment `force-stop` is sent."""
        inner = engine.call

        def call(argv, **kwargs):
            if argv[1:2] == ["force-stop"]:
                seen.append(self.stored(path)["revisions"][-1].get("stop"))
            return inner(argv, **kwargs)
        engine.call = call
        return engine

    def force_stops(self, calls):
        return [c[0][1:] for c in calls if c[0][1:2] == ["force-stop"]]


class StopServiceTests(PlanStopTest):
    def test_a1_the_request_is_saved_before_the_call_and_the_force_stop_is_sent_once(self):
        engine, calls = self.engine([subprocess.CompletedProcess([], 0, "", "")])
        path = self.revision(engine)
        seen = []
        self.capture(engine, path, seen)
        with self.authority() as authority, mock.patch("terminal_planner.runs.now", return_value=STOP_AT):
            planning = self.planning(authority, engine)
            self.assertIn("stop", planning.view().actions)
            self.assertEqual(planning.stop(), "Stop requested.")
        self.assertEqual(self.force_stops(calls), [["force-stop", RUN]])
        self.assertEqual(seen, [{"at": STOP_AT}])  # the store already held the request when force-stop ran
        stored = self.stored(path)["revisions"][-1]
        self.assertEqual(stored["stop"], {"at": STOP_AT})
        self.assertEqual((stored["status"], stored["run_id"], stored["receipt"]), ("observing", RUN, {"runId": RUN}))

    def test_a2_a_stopped_run_shows_the_cause_and_offers_restart_not_a_failure(self):
        engine, _ = self.engine([subprocess.CompletedProcess([], 0, "", ""), (self.finished(RUN, 1),)])
        self.revision(engine)
        with self.authority() as authority, mock.patch("terminal_planner.runs.now", return_value=STOP_AT):
            planning = self.planning(authority, engine)
            planning.stop()
            engine.proposal(authority, lambda line: None)
            view = planning.view()
            self.assertEqual((view.kind, view.status), ("stopped", "stopped"))
            self.assertIn(STOPPED_LINE, view.lines)
            self.assertEqual(view.actions, ("restart", "details"))
            self.assertNotIn("did not finish", " ".join(view.lines))
            current = authority.current
            self.assertEqual((current["goal"], current["receipt"], current["stop"]),
                             ("Requested feature", {"runId": RUN}, {"at": STOP_AT}))

    def test_a2b_the_stop_time_is_shown_in_the_local_zone_and_stored_in_utc(self):
        engine, _ = self.engine([subprocess.CompletedProcess([], 0, "", ""), (self.finished(RUN, 1),)])
        self.revision(engine)
        self.zone("Europe/Moscow")
        with self.authority() as authority, mock.patch("terminal_planner.runs.now", return_value=STOP_AT):
            planning = self.planning(authority, engine)
            planning.stop()
            engine.proposal(authority, lambda line: None)
            self.assertIn(STOPPED_LINE.replace("01:40", "04:40"), planning.view().lines)
            self.assertEqual(authority.current["stop"], {"at": STOP_AT})

    def test_a3_the_cause_survives_reopening_the_store(self):
        engine, _ = self.engine([subprocess.CompletedProcess([], 0, "", ""), (self.finished(RUN, 1),)])
        self.revision(engine)
        with self.authority() as authority, mock.patch("terminal_planner.runs.now", return_value=STOP_AT):
            planning = self.planning(authority, engine)
            planning.stop()
            engine.proposal(authority, lambda line: None)
        with self.authority() as reopened:
            view = self.planning(reopened, engine).view()
        self.assertEqual(view.kind, "stopped")
        self.assertIn(STOPPED_LINE, view.lines)
        self.assertEqual(view.actions, ("restart", "details"))

    def test_a4_restart_submits_r2_with_a_new_key_and_never_resubmits_r1(self):
        engine, calls = self.engine([subprocess.CompletedProcess([], 0, "", ""), (self.finished(RUN, 1),),
                                     {"valid": True}, {"runId": NEXT}, (self.finished(NEXT, 2),)])
        self.revision(engine)
        with self.authority() as authority:
            planning = self.planning(authority, engine)
            planning.stop()
            engine.proposal(authority, lambda line: None)
            stopped = authority.current
            self.assertEqual(stopped["status"], "stopped")
            old_key = stopped["submission_key"]
            result = planning.restart()
            self.assertEqual((result.kind, result.renewed), ("ready", True))
            renewed = authority.current
            self.assertEqual((renewed["version"], renewed["status"], renewed["run_id"]), (2, "planning", None))
            self.assertNotEqual(renewed["submission_key"], old_key)
            # The submission happens inside `proposal` before the scripted run ends as failed: the point here is
            # that r2 is dispatched under its own key, not the run's outcome.
            with self.assertRaises(Blocked):
                engine.proposal(authority, lambda line: None)
            self.assertEqual((authority.current["version"], authority.current["status"]), (2, "run_failed"))
        detaches = [c[0] for c in calls if "--detach" in c[0]]
        self.assertEqual(len(detaches), 1)
        self.assertEqual(detaches[0][detaches[0].index("--submission-key") + 1], renewed["submission_key"])
        self.assertNotIn(old_key, " ".join(part for call, _ in calls for part in call))
        self.assertEqual(self.force_stops(calls), [["force-stop", RUN]])

    def test_a5_a_refused_force_stop_leaves_the_revision_as_it_was_and_the_stop_retries(self):
        engine, calls = self.engine([subprocess.CompletedProcess([], 1, "", "")])
        path = self.revision(engine)
        with self.authority() as authority:
            planning = self.planning(authority, engine)
            with self.assertRaisesRegex(Blocked, "force-stop was rejected"):
                planning.stop()
            self.assertEqual(self.force_stops(calls), [["force-stop", RUN]])
            stored = self.stored(path)["revisions"][-1]
            self.assertIsNone(stored.get("stop"))
            self.assertEqual(stored["status"], "observing")
            self.assertIn("stop", planning.view().actions)  # [s] is offered again
            # A later, confirmed attempt still works: the removed request never blocked a second try. The
            # binding probe (`--version`) still goes through the scripted call, only force-stop is re-scripted.
            inner = engine.call
            engine.call = lambda argv, **kwargs: (inner(argv, **kwargs) if argv[1:] == ["--version"]
                                                  else subprocess.CompletedProcess(argv, 0, "", ""))
            with mock.patch("terminal_planner.runs.now", return_value=STOP_AT):
                self.assertEqual(planning.stop(), "Stop requested.")
        self.assertEqual(self.stored(path)["revisions"][-1]["stop"], {"at": STOP_AT})

    def test_a_first_unanswered_force_stop_keeps_the_request(self):
        """Critic p1a-merge finding 1: a first force-stop that times out may still have stopped the run, so the
        request stays and the terminal observation concludes `stopped`, not `run_failed`."""
        engine, calls = self.engine([subprocess.TimeoutExpired("zeroshot", 120)])
        path = self.revision(engine)
        with self.authority() as authority:
            planning = self.planning(authority, engine)
            with mock.patch("terminal_planner.runs.now", return_value=STOP_AT), \
                    self.assertRaisesRegex(Blocked, "force-stop did not answer"):
                planning.stop()
            stored = self.stored(path)["revisions"][-1]
            self.assertEqual(stored.get("stop"), {"at": STOP_AT})
            self.assertEqual(stored["status"], "observing")
            self.assertIn("stop", planning.view().actions)

    def test_a_refused_or_timed_out_retry_keeps_the_earlier_confirmed_stop_request(self):
        """A2/A3/A5 (regression): a later [s] the engine refuses or never answers must not destroy an earlier
        confirmed request or its time. Reproduces the data loss: stop 0 -> stop 1 (exit 1) used to pop the stored
        `{at: ...}` and the revision went on to render `run_failed`."""
        engine, calls = self.engine([subprocess.CompletedProcess([], 0, "", ""),
                                     subprocess.CompletedProcess([], 1, "", ""),
                                     subprocess.TimeoutExpired("zeroshot", 120)])
        path = self.revision(engine)
        with self.authority() as authority:
            planning = self.planning(authority, engine)
            with mock.patch("terminal_planner.runs.now", return_value=STOP_AT):
                self.assertEqual(planning.stop(), "Stop requested.")
            for reason in ("force-stop was rejected", "force-stop did not answer"):
                with self.subTest(reason=reason), self.assertRaisesRegex(Blocked, reason):
                    planning.stop()
                stored = self.stored(path)["revisions"][-1]
                self.assertEqual(stored.get("stop"), {"at": STOP_AT})  # request and time survive the retry
                self.assertEqual(stored["status"], "observing")
            self.assertIn("stop", planning.view().actions)
        self.assertEqual(self.force_stops(calls), [["force-stop", RUN]] * 3)

    def test_a_record_frozen_on_another_state_root_is_refused_before_any_force_stop(self):
        """Native lifecycle (regression): `stop()` validates the frozen binding like a milestone stop. A planner
        reopened with another `--native-state-dir` (the same executable, another state root) refuses before any
        dispatch instead of sending `force-stop` into the wrong `<state_root>/runs`."""
        engine, calls = self.engine([subprocess.CompletedProcess([], 0, "", "")])
        path = self.revision(engine)  # the binding is frozen on self.native
        # Another private state root, short enough for a native socket (as `--native-state-dir` would name one).
        other = Path(tempfile.mkdtemp(prefix="z")).resolve()
        self.addCleanup(shutil.rmtree, other, ignore_errors=True)
        with self.authority() as authority:
            planning = self.planning(authority, engine)
            engine.state_root = other  # the same executable, another state root
            with self.assertRaisesRegex(Blocked, "binary/state"):
                planning.stop()
            self.assertEqual(self.force_stops(calls), [])  # nothing reached native force-stop
            stored = self.stored(path)["revisions"][-1]
            self.assertIsNone(stored.get("stop"))
            self.assertEqual(stored["status"], "observing")

    def test_a_succeeded_terminal_racing_the_stop_still_becomes_stopped(self):
        """A2 (regression): the stop request wins whenever the observation ends the run. A valid succeeded terminal
        arriving after the request used to leave `proposed` with a reviewed plan; it is now `stopped` with its
        native terminal evidence retained, never a proposal."""
        engine, _ = self.engine([subprocess.CompletedProcess([], 0, "", ""), (self.succeeded(RUN, 1),)])
        self.revision(engine)
        with self.authority() as authority, mock.patch("terminal_planner.runs.now", return_value=STOP_AT):
            planning = self.planning(authority, engine)
            planning.stop()
            engine.proposal(authority, lambda line: None)
            view = planning.view()
            self.assertEqual((view.kind, view.status), ("stopped", "stopped"))
            self.assertIn(STOPPED_LINE, view.lines)
            self.assertEqual(view.actions, ("restart", "details"))
            current = authority.current
            self.assertEqual((current["proposal"], current["evidence"]), (None, None))
            self.assertEqual(current["stop"], {"at": STOP_AT})
            self.assertEqual(current["terminal_envelope"]["status"]["terminalResult"]["status"], "succeeded")
        with self.authority() as reopened:
            again = self.planning(reopened, engine).view()
        self.assertEqual(again.kind, "stopped")
        self.assertIn(STOPPED_LINE, again.lines)

    def test_a6_a_corrupt_stop_request_is_refused_by_the_store(self):
        engine, _ = self.engine([])
        path = self.revision(engine)
        for stop in ({"at": "yesterday"}, {"at": STOP_AT, "run": RUN}, "now"):
            with self.subTest(stop=stop):
                data = self.stored(path)
                data["revisions"][-1]["stop"] = stop
                path.write_text(json.dumps(data))
                with self.assertRaises(Blocked):
                    with self.authority():
                        pass


class StopScreenTests(PlanStopTest):
    """The plain plan screen: the only whole-app journeys of this task, one per screen behaviour."""

    def test_a1_to_a3_stop_watch_and_reopen_show_the_same_cause_line(self):
        engine, calls = self.engine([subprocess.CompletedProcess([], 0, "", ""), (self.finished(RUN, 1),)])
        path = self.revision(engine)
        seen = []
        self.capture(engine, path, seen)
        with mock.patch("terminal_planner.runs.now", return_value=STOP_AT):
            output = self.journey(engine, "p", "s", "w", "q", "q")
        self.assertIn("[s] stop planning", output)
        self.assertIn("Stop requested.", output)
        self.assertEqual(self.force_stops(calls), [["force-stop", RUN]])
        self.assertEqual(seen, [{"at": STOP_AT}])
        self.assertIn(STOPPED_LINE, output)
        self.assertIn("[g] start the planner again", output)
        self.assertNotIn("planning did not finish", output)
        # A3: reopening the same store shows the same line.
        again = self.journey(self.engine([])[0], "p", "q", "q")
        self.assertIn(STOPPED_LINE, again)

    def test_a5_a_refused_force_stop_is_shown_and_the_plan_screen_offers_s_again(self):
        engine, calls = self.engine([subprocess.CompletedProcess([], 1, "", "")])
        path = self.revision(engine)
        output = self.journey(engine, "p", "s", "q", "q")
        self.assertEqual(self.force_stops(calls), [["force-stop", RUN]])
        self.assertIn("Not done: ", output)
        self.assertIn("plan.stop_unconfirmed", output)
        self.assertGreaterEqual(output.count("[s] stop planning"), 2)  # offered before and after
        stored = self.stored(path)["revisions"][-1]
        self.assertIsNone(stored.get("stop"))
        self.assertEqual(stored["status"], "observing")


class StopCatalogTests(unittest.TestCase):
    def test_the_stop_action_and_status_are_catalogued(self):
        action = catalog.action("plan.stop")
        self.assertEqual((action.key, action.label), ("s", "stop planning"))
        self.assertIn("stopped", catalog.PLAN_STATUS)
        self.assertIn("plan.stop_unconfirmed", catalog.ERRORS)


if __name__ == "__main__":
    unittest.main()
