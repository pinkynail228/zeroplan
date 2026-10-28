"""A6b1: the architect's event feed -- a persisted run-event queue with its own handled mark.

Covers the four acceptance criteria with fixtures from `test_runs` (an isolated HOME/state root, a fixture or
scripted-native run):

- C1 shape and bootstrap: `feed.bootstrap` seeds `last`/`verdicts`/`events`, is a no-op on an existing feed, marks a
  session whose store does not exist yet (so its first plan and run are captured), captures nothing without a feed,
  and `validate_feed` refuses a malformed feed.
- C2 state events: every save captures one event per changed record, `wake` names the states that need the architect,
  no transition between two saves is folded, a resume successor gets its own key, and a save that fails before the
  replace rolls the capture back so a removed record leaves no event.
- C3 verdict events: a verdict recorded by the reviewer read appends one event in the same save, identified by the
  reader's execution reference, deduplicated per key and never bounded by the display list.
- C4 read and acknowledge: `pending` batches the oldest and counts the rest, `handle` advances the mark and drops
  handled events, a stale ack is a no-op and the queue is unbounded.

Interpretations recorded for the reviewers (each the reading closest to the task's own example):
- `bootstrap` on a session whose store does not exist yet writes nothing and marks the authority (`feed_pending`); the
  save that first creates the store starts from an empty feed (`last` {}), so that session's first run is captured by
  the ordinary state capture.
- A record whose key has no `last` entry yet captures an event with `previous` None (the first save after bootstrap).
- The verdict feed event carries the reviewer's execution reference, the task/round/role of the queued reviewer and
  the parsed verdict/text; the store-side dedupe keeps the last `VERDICT_BOUND` (32) executions per key.
"""

import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_terminal_planner as planner
from terminal_planner import feed, live, runs
from terminal_planner.authority import Blocked, PersistenceError, decode
from terminal_planner.runs import FixtureDriver, MilestoneRuns, NativeDriver
from test_runs import ROLES, RunsTest

STAMP = "2026-01-01T00:00:00Z"


def state_event(seq, key="1/M1/1/-", state="running", previous=None, milestone="M1", attempt=1, revision=1):
    return {"seq": seq, "kind": "state", "key": key, "milestone": milestone, "plan_revision": revision,
            "attempt": attempt, "run_id": "r", "state": state, "previous": previous,
            "wake": state in feed.WAKE, "at": STAMP}


def synthetic(count):
    """A well-formed feed of `count` state events (last one awaiting_merge) under the key `1/M1/1/-`."""
    events = [state_event(n, state="running" if n < count else "awaiting_merge",
                          previous="running" if n > 1 else None) for n in range(1, count + 1)]
    return {"seq": count, "handled": 0, "last": {"1/M1/1/-": "awaiting_merge"}, "verdicts": {}, "events": events}


def verdict_event(seq, milestone="M1", task="T2", round_=2, role="code_review", verdict="accepted", text="ok"):
    return {"seq": seq, "kind": "verdict", "key": "1/%s/1/-" % milestone, "milestone": milestone, "plan_revision": 1,
            "attempt": 1, "run_id": "r", "execution": "e%d" % seq, "task": task, "round": round_, "role": role,
            "verdict": verdict, "text": text, "wake": True, "at": STAMP}


class FeedShapeTests(RunsTest):
    def test_bootstrap_seeds_last_and_verdicts_and_is_a_no_op_when_the_feed_exists(self):
        """C1: bootstrap writes `{seq, handled, last, verdicts, events}` seeded from the records and saves; a second
        bootstrap on the same store changes nothing."""
        self.approve_fixture()
        with self.fixture_authority() as a:
            controller = self.fixture_runs(a)
            controller.start("M1", 1, ROLES)
            self.assertNotIn("feed", a.state)
            feed.bootstrap(a)
            expected = {"seq": 0, "handled": 0, "last": {"1/M1/1/-": "running"},
                        "verdicts": {"1/M1/1/-": []}, "events": [],
                        "plan": {"revision": 1, "status": "approved"}}  # RS5: recorded silently by the save
            self.assertEqual(a.state["feed"], expected)
            self.assertEqual(decode(a.path.read_text())["feed"], expected)  # saved, not only in memory
            raw = a.path.read_bytes()
            feed.bootstrap(a)  # exists: no-op, no save
            self.assertEqual(a.state["feed"], expected)
            self.assertEqual(a.path.read_bytes(), raw)

    def test_bootstrap_on_a_store_that_does_not_exist_marks_the_authority_and_captures_the_first_run(self):
        """C1: on a session without a store bootstrap writes nothing and marks the authority; the save that first
        creates the store starts from an empty feed, and the first plan and run of that session are captured."""
        with self.fixture_authority() as a:
            self.assertIsNone(a.state)
            feed.bootstrap(a)
            self.assertIsNone(a.state)  # nothing written
            self.assertTrue(a.feed_pending)
            self.begin(a)
            self.assertIsNotNone(a.state)
            self.assertFalse(a.feed_pending)
            self.assertEqual(a.state["feed"], {"seq": 0, "handled": 0, "last": {}, "verdicts": {}, "events": [],
                                               "plan": {"revision": 1, "status": "planning"}})
            self.propose(a)
            a.approve(1)
            controller = self.fixture_runs(a)
            controller.start("M1", 1, ROLES)
            queue = a.state["feed"]
            self.assertEqual(queue["last"], {"1/M1/1/-": "running"})
            events = [e for e in queue["events"] if e["kind"] == "state"]  # the plan events are RS5's
            self.assertEqual([e["state"] for e in events], ["running"])  # C1b: `unknown` is not captured
            self.assertIsNone(events[0]["previous"])  # no `last` yet: previous is None

    def test_without_a_feed_nothing_is_captured_and_the_store_stays_byte_identical(self):
        """C1: today's stores (no feed) never gain one and keep their bytes across a save."""
        self.approve_fixture()
        with self.fixture_authority() as a:
            controller = self.fixture_runs(a)
            controller.observe(controller.start("M1", 1, ROLES))
            self.assertNotIn("feed", a.state)
            raw = a.path.read_bytes()
        self.assertNotIn("feed", decode(raw.decode()))
        with self.fixture_authority() as a:
            self.assertNotIn("feed", a.state)
            a.save()
            self.assertEqual(a.path.read_bytes(), raw)

    def test_a_record_key_is_unique_across_resume_successors(self):
        """C1: the key is `plan_revision/milestone/attempt/predecessor-or-dash`, so a successor differs."""
        original = {"plan_revision": 3, "milestone": "M2", "attempt": 2, "predecessor": None}
        successor = dict(original, predecessor="m-run-7")
        self.assertEqual(feed.key(original), "3/M2/2/-")
        self.assertEqual(feed.key(successor), "3/M2/2/m-run-7")
        self.assertNotEqual(feed.key(original), feed.key(successor))

    def test_validate_feed_refuses_malformed_feeds_and_a_malformed_store_does_not_load(self):
        """C1: `validate_feed` rejects a wrong shape and a bad store is refused on load, leaving its bytes."""
        good = {"seq": 1, "handled": 0, "last": {"1/M1/1/-": "running"}, "verdicts": {"1/M1/1/-": []},
                "events": [state_event(1, state="running")]}
        feed.validate_feed(good)
        bad = [
            None, [], {"seq": 0},  # not a dict / wrong key set
            dict(good, seq=-1), dict(good, handled=5), dict(good, handled=-1),
            dict(good, last={"1/M1/1/-": "paused"}), dict(good, verdicts={"1/M1/1/-": ["x"] * 33}),
            dict(good, events=[dict(state_event(1), state="paused")]),
            dict(good, events=[dict(state_event(1), kind="other")]),
            dict(good, events=[dict(state_event(1), wake=True)]),  # running is not a wake state
            dict(good, events=[state_event(2)]),  # event seq beyond the counter
            dict(good, handled=1),  # an event not above the handled mark
        ]
        for value in bad:
            with self.subTest(value=value):
                with self.assertRaises(Blocked):
                    feed.validate_feed(value)
        # C1b C5: a quiet state event is valid for any state, a stored `unknown` last state and a wake-true verdict load
        feed.validate_feed(dict(good, events=[state_event(1, state="awaiting_merge") | {"wake": False}]))
        feed.validate_feed(dict(good, events=[state_event(1, state="running")], last={"1/M1/1/-": "unknown"}))
        feed.validate_feed(dict(good, events=[verdict_event(1, verdict="accepted")]))

        self.approve_fixture()
        with self.fixture_authority() as a:
            feed.bootstrap(a)
            path = a.path
        data = json.loads(path.read_text())
        data["feed"]["seq"] = -1
        path.write_text(json.dumps(data))
        raw = path.read_bytes()
        with self.assertRaises(Blocked):
            with self.fixture_authority():
                pass
        self.assertEqual(path.read_bytes(), raw)


class FeedStateTests(RunsTest):
    def done(self, a):
        """One fixture attempt observed to `done` (delivery `none`, so `run_state` is awaiting_merge)."""
        controller = self.fixture_runs(a)
        r = controller.observe(controller.start("M1", 1, ROLES))
        self.assertEqual(r["outcome"], "done")
        return controller, r

    def test_a_finished_run_captures_the_full_state_event_fields(self):
        """C1/C2/C1b C3: bootstrap with M1 running; the run observed finished appends one running -> awaiting_merge
        event with the full field set (the transient `unknown` is neither an event nor a stored last state)."""
        self.approve_fixture()
        with self.fixture_authority() as a:
            controller = self.fixture_runs(a)
            r = controller.start("M1", 1, ROLES)
            feed.bootstrap(a)
            self.assertEqual(a.state["feed"]["events"], [])
            controller.observe(r)
            queue = a.state["feed"]
            events = queue["events"]
            self.assertEqual([e["state"] for e in events], ["awaiting_merge"])
            self.assertEqual([e["previous"] for e in events], ["running"])
            self.assertEqual([e["wake"] for e in events], [True])
            self.assertEqual([e["seq"] for e in events], [1])
            for event in events:
                self.assertEqual(set(event), feed.STATE_KEYS)
                self.assertEqual((event["key"], event["milestone"], event["plan_revision"], event["attempt"]),
                                 ("1/M1/1/-", "M1", 1, 1))
                self.assertEqual(event["run_id"], r["run_id"])
                self.assertEqual(event["kind"], "state")
            self.assertEqual(queue["last"], {"1/M1/1/-": "awaiting_merge"})
            self.assertEqual(feed.pending(a), (events, 0))

    def test_c1b_c1_c3_an_architect_action_is_quiet_and_unknown_is_skipped(self):
        """C1b C1/C3/C4: the state events saved while the architect's own action runs carry wake false and still
        pend; the transient `unknown` is no event and no last state, so the event names the real previous state (C4's
        wake of a later observation is `test_a_finished_run_captures_the_full_state_event_fields`)."""
        self.approve_fixture()
        with self.fixture_authority() as a:
            controller = self.fixture_runs(a)
            r = controller.start("M1", 1, ROLES)
            feed.bootstrap(a)
            a.architect_acting = True
            controller.stop(r)  # the architect's own zplan_stop: running -> stopping
            a.architect_acting = False
            events = a.state["feed"]["events"]
            self.assertEqual([(e["state"], e["previous"], e["wake"]) for e in events], [("stopping", "running", False)])
            self.assertEqual(feed.pending(a)[0], events)  # it rides along with the next wake batch
            with patch("terminal_planner.runs.run_state", return_value="unknown"):  # finished, no outcome yet
                a.save()
            self.assertEqual(a.state["feed"]["last"], {"1/M1/1/-": "stopping"})
            self.assertEqual(len(a.state["feed"]["events"]), 1)
            feed.validate_feed(a.state["feed"])

    def test_integrated_and_unintegrated_transitions_are_not_folded(self):
        """C2: awaiting_merge -> integrated -> awaiting_merge gives two wake events after the bootstrap (one per
        save), never a single folded one."""
        self.approve_fixture()
        base = self.head()
        with self.fixture_authority() as a:
            controller, r = self.done(a)
            controller.finish(r)
            feed.bootstrap(a)
            self.assertEqual(a.state["feed"]["last"], {"1/M1/1/-": "awaiting_merge"})
            sha = r["result"]["commit"]
            self.git("merge", "--no-ff", "-q", "-m", "owner merge", sha)
            self.assertIsNone(controller.reconcile())
            self.git("reset", "-q", "--hard", base)
            controller.refresh()
            events = a.state["feed"]["events"]
            self.assertEqual([e["state"] for e in events], ["integrated", "awaiting_merge"])
            self.assertTrue(all(e["wake"] for e in events))
            self.assertEqual(a.state["feed"]["last"], {"1/M1/1/-": "awaiting_merge"})

    def test_a_resumed_failure_gives_the_successor_its_own_key_and_keeps_the_original(self):
        """C2: a failed M1 resumed captures the successor under `1/M1/1/m-run` while M1's own key and events stay."""
        r = self.started()
        with self.authority() as a:
            feed.bootstrap(a)
            self.assertEqual(list(a.state["feed"]["last"]), ["1/M1/1/-"])
            controller, calls = self.native_runs(a, [
                (self.finished(r, reason="worker_failed"),), self.status(r, {"recoverable": True}),
                self.status(r, {"recoverable": True}), {"runId": "m-run-2", "resumedFrom": "m-run"}])
            failed = controller.observe(controller.active())
            controller.resume(failed)
            queue = a.state["feed"]
            self.assertEqual(queue["last"]["1/M1/1/-"], "failed_recoverable")
            self.assertEqual(queue["last"]["1/M1/1/m-run"], "running")
            first = [e for e in queue["events"] if e["key"] == "1/M1/1/-"]
            successor = [e for e in queue["events"] if e["key"] == "1/M1/1/m-run"]
            self.assertIn("failed_recoverable", [e["state"] for e in first])
            self.assertEqual([e["state"] for e in successor], ["running"])

    def test_a_save_that_fails_before_the_replace_rolls_the_capture_back(self):
        """C2 rollback: a start whose save fails leaves no event and no `last` for the removed record; the next
        successful start captures only its own events."""
        self.approve_fixture()
        with self.fixture_authority() as a:
            feed.bootstrap(a)
            controller = self.fixture_runs(a)
            with patch("terminal_planner.authority.atomic_state", side_effect=PersistenceError("replace")):
                with self.assertRaises(PersistenceError):
                    controller.start("M1", 1, ROLES)
            self.assertEqual(a.state.get("runs", []), [])
            self.assertEqual(a.state["feed"]["events"], [])
            self.assertEqual(a.state["feed"]["last"], {})
            self.assertEqual(a.state["feed"]["seq"], 0)
            controller.start("M1", 1, ROLES)  # succeeds now
            events = a.state["feed"]["events"]
            self.assertEqual({e["key"] for e in events}, {"1/M1/1/-"})
            self.assertEqual([e["state"] for e in events], ["running"])


class FeedPlanTests(RunsTest):
    """RS5: plan transitions are captured by the same save as the run ones, keyed by revision.

    Interpretations: the feed's `plan` entry is `{"revision", "status"}` of the last captured current revision (None
    while the store has none); a new revision is an event with `previous` None; a store without the entry records the
    current revision silently, whether or not it has a revision."""

    def plan_events(self, a):
        return [e for e in a.state["feed"]["events"] if e["kind"] == "plan"]

    def test_c1_c2_c3_every_save_captures_the_plan_transition_once_and_every_approval_path_goes_through_it(self):
        """C1/C2/C3: each status change of the current revision is one event (`approve` and `override` both end in
        `Authority.save`); an `auto` session wakes on `proposed` and `approved` with one line each, `observing` rides
        along; a save with no change gives none; a new revision is an event, planning rides along.

        Interpretation: the level is patched at `autonomy.level` (the profile fixture of these tests is unprofiled,
        which reads as manual)."""
        with patch("terminal_planner.autonomy.level", return_value="auto"), self.fixture_authority() as a:
            feed.bootstrap(a)  # no store yet: the first save starts from an empty feed
            self.begin(a)
            self.assertEqual(self.plan_events(a), [])  # first save records r1 planning silently
            self.propose(a)
            a.save()  # nothing changed: no second event
            a.approve(1)
            events = self.plan_events(a)
            self.assertEqual([(e["previous"], e["status"], e["wake"]) for e in events],  # observing rides along
                             [("planning", "observing", False), ("observing", "proposed", True),
                              ("proposed", "approved", True)])
            self.assertEqual({e["plan_revision"] for e in events}, {1})
            self.assertEqual(set(events[0]), feed.PLAN_EVENT_KEYS)
            self.assertEqual(feed.summary(events, 0).splitlines()[1:4],
                             ["plan r1: observing -> proposed", "plan r1: proposed -> approved",
                              "Intermediate states without action: 1."])
            self.assertEqual(a.state["feed"]["plan"], {"revision": 1, "status": "approved"})
            self.begin(a)
            event = self.plan_events(a)[-1]
            self.assertEqual((event["plan_revision"], event["previous"], event["status"], event["wake"]),
                             (2, None, "planning", False))
            self.assertEqual(feed.summary([event], 0).splitlines()[1],
                             "Intermediate states without action: 1.")
            feed.validate_feed(a.state["feed"])
            # the status a restart reads is the captured one: no event repeats
            seq = a.state["feed"]["seq"]
        with self.fixture_authority() as a:
            a.save()
            self.assertEqual(a.state["feed"]["seq"], seq)

    def test_c1_the_plan_event_wakes_by_the_autonomy_level(self):
        """C1: the same transitions wake by level: auto wakes on proposed (approve) and approved (start), supervised
        only on approved (approve is the owner's), manual (no profile) on none; the event itself is always there."""
        for level, woke in (("auto", [True, True]), ("supervised", [False, True]), ("manual", [False, False])):
            with self.subTest(level=level):
                planner.shutil.rmtree(self.state, ignore_errors=True)  # a fresh store per level
                with patch("terminal_planner.autonomy.level", return_value=level), self.fixture_authority() as a:
                    feed.bootstrap(a)
                    self.begin(a)
                    self.propose(a)
                    a.approve(1)
                    events = [e for e in self.plan_events(a) if e["status"] in ("proposed", "approved")]
                    self.assertEqual([e["status"] for e in events], ["proposed", "approved"])
                    self.assertEqual([e["wake"] for e in events], woke)
                    feed.validate_feed(a.state["feed"])
        with self.fixture_authority() as a:  # unprofiled: the real `autonomy.level` answers manual
            self.assertEqual(a.profile, None)
            self.assertEqual(feed._plan_wakes(a, "proposed"), False)

    def test_c4_a_store_without_a_plan_entry_loads_and_records_silently_then_captures(self):
        """C4: a feed written before RS5 (approved r1, no `plan`) loads; its first save raises no event for the old
        approval; a later revision's transition raises one; the entry survives a restart without repeating."""
        self.approve_fixture()
        with self.fixture_authority() as a:
            feed.bootstrap(a)
            path = a.path
        data = json.loads(path.read_text())
        del data["feed"]["plan"]
        path.write_text(json.dumps(data))
        with self.fixture_authority() as a:
            self.assertNotIn("plan", a.state["feed"])
            a.save()
            self.assertEqual((a.state["feed"]["events"], a.state["feed"]["plan"]),
                             ([], {"revision": 1, "status": "approved"}))
            self.begin(a)
            self.propose(a)
            self.assertEqual([(e["plan_revision"], e["status"]) for e in self.plan_events(a)],
                             [(2, "planning"), (2, "observing"), (2, "proposed")])
        with self.fixture_authority() as a:
            a.save()
            self.assertEqual(len(self.plan_events(a)), 3)

    def test_c4_a_save_that_fails_before_the_replace_rolls_the_plan_capture_back(self):
        """C4 rollback: a failed write leaves no plan event and the previous `plan` entry; the retry captures it."""
        with self.fixture_authority() as a:
            feed.bootstrap(a)
            self.begin(a)
            with patch("terminal_planner.authority.atomic_state", side_effect=PersistenceError("replace")):
                with self.assertRaises(PersistenceError):
                    self.propose(a)
            self.assertEqual((a.state["feed"]["events"], a.state["feed"]["seq"], a.state["feed"]["plan"]),
                             ([], 0, {"revision": 1, "status": "planning"}))
            a.save()
            self.assertEqual([(e["previous"], e["status"]) for e in self.plan_events(a)],
                             [("planning", a.current["status"])])

    def test_c4_validate_feed_refuses_a_malformed_plan_event_and_plan_entry(self):
        """C4: a plan event with a wrong key set, status, wake or a bad `plan` entry refuses the store."""
        good_event = {"seq": 1, "kind": "plan", "key": "plan/1", "plan_revision": 1, "status": "proposed",
                      "previous": "planning", "wake": True, "at": STAMP}
        good = {"seq": 1, "handled": 0, "last": {}, "verdicts": {}, "events": [good_event],
                "plan": {"revision": 1, "status": "proposed"}}
        feed.validate_feed(good)
        feed.validate_feed({k: v for k, v in good.items() if k != "plan"})  # a feed written before RS5
        feed.validate_feed(dict(good, events=[dict(good_event, wake=False)]))  # the autonomy level kept it quiet
        bad = [dict(good, events=[dict(good_event, status="paused")]),
               dict(good, events=[dict(good_event, previous="paused")]),
               dict(good, events=[dict(good_event, status="planning", previous=None)]),  # planning never wakes
               dict(good, events=[dict(good_event, milestone="M1")]),  # a stray key
               dict(good, events=[{k: v for k, v in good_event.items() if k != "status"}]),
               dict(good, events=[dict(good_event, plan_revision=0)]),
               dict(good, plan={"revision": 1}), dict(good, plan={"revision": 1, "status": "paused"}),
               dict(good, plan={"revision": 0, "status": "proposed"})]
        for value in bad:
            with self.subTest(value=value):
                with self.assertRaises(Blocked):
                    feed.validate_feed(value)


class FeedVerdictTests(RunsTest):
    @staticmethod
    def line(message, timestamp=1791935230934):
        return json.dumps({"subscriptionId": "sub", "runId": "m-run", "timestamp": timestamp,
                           "record": {"level": "info", "target": "native_v2_runner", "message": message}})

    @classmethod
    def response(cls, verdict="accepted", reason="ok", timestamp=1791935230934):
        body = {"response": {"diagnostic": {"message": reason}, "output": None, "signals": {"verdict": verdict}}}
        return cls.line(json.dumps(body), timestamp)

    @staticmethod
    def scripted(controller, lines):
        def log_records(binding, run_id, cwd, execution=None, **options):
            return list(lines), True
        controller.engine.log_records = log_records

    def started_session(self, responses=None):
        """Approved native plan with M1 submitted, inside the caller's authority session.

        Returns (authority, controller, record) with an empty feed bootstrapped and no queued reviewers."""
        self.approve_native()
        self._session = self.authority()
        a = self._session.__enter__()
        self.addCleanup(self._session.__exit__, None, None, None)
        controller, _ = self.native_runs(a, responses or [{"valid": True}, {"runId": "m-run"}])
        r = controller.start("M1", 1, ROLES)
        r.setdefault("live", live.new())
        feed.bootstrap(a)
        return a, controller, r

    def queue(self, controller, executions):
        controller.verdicts["m-run"] = {
            "queue": [{"execution": execution, "role": "acceptance_review", "task": "T1", "round": 2}
                      for execution in executions], "reads": {}, "seen": set()}

    def test_a_recorded_verdict_appends_an_event_in_the_same_save(self):
        """C3: a verdict recorded by the reviewer read appends one `kind: verdict` event, in the record's save,
        carrying the execution reference, the task/round/role and the parsed verdict/text with wake True."""
        a, controller, r = self.started_session()
        self.scripted(controller, [self.response("rejected", "нет теста на отказ")])
        self.queue(controller, ["a1"])
        controller.read_verdict(r)
        controller.save(r)
        events = a.state["feed"]["events"]
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(set(event), feed.VERDICT_KEYS)
        self.assertEqual(event["kind"], "verdict")
        self.assertEqual((event["key"], event["milestone"], event["plan_revision"], event["attempt"]),
                         ("1/M1/1/-", "M1", 1, 1))
        self.assertEqual(event["run_id"], "m-run")
        self.assertEqual(event["execution"], "a1")
        self.assertEqual((event["task"], event["round"], event["role"]), ("T1", 2, "acceptance_review"))
        self.assertEqual(event["verdict"], "rejected")
        self.assertEqual(event["text"], "нет теста на отказ")
        self.assertIs(event["wake"], True)
        self.assertEqual(a.state["feed"]["verdicts"], {"1/M1/1/-": ["a1"]})

    def test_c1b_c2_only_a_verdict_that_is_not_accepted_wakes_and_an_architect_action_wakes_nothing(self):
        """C1b C2/C1: code_review accepted -> wake false, acceptance_review rejected -> wake true; the same rejected
        verdict captured while one of the architect's own actions runs (`authority.architect_acting`) is quiet."""
        a, controller, r = self.started_session()
        for execution, verdict, acting in (("a1", "accepted", False), ("a2", "rejected", False),
                                           ("a3", "rejected", True)):
            self.scripted(controller, [self.response(verdict, "x")])
            self.queue(controller, [execution])
            a.architect_acting = acting
            controller.read_verdict(r)
        a.architect_acting = False
        controller.save(r)
        events = [e for e in a.state["feed"]["events"] if e["kind"] == "verdict"]
        self.assertEqual([(e["verdict"], e["wake"]) for e in events],
                         [("accepted", False), ("rejected", True), ("rejected", False)])
        feed.validate_feed(a.state["feed"])

    def test_ten_verdicts_with_no_handled_turn_are_ten_pending(self):
        """C3: ten recorded verdicts are ten pending events even though the display list keeps only VERDICT_LIMIT
        (8) of them."""
        a, controller, r = self.started_session()
        self.scripted(controller, [self.response("accepted", "ok")])
        self.queue(controller, ["a%d" % n for n in range(1, 11)])
        for _ in range(10):
            controller.read_verdict(r)
        controller.save(r)
        self.assertLessEqual(len(r["live"]["verdicts"]), live.VERDICT_LIMIT)
        pending = [e for e in a.state["feed"]["events"] if e["kind"] == "verdict"]
        self.assertEqual(len(pending), 10)
        self.assertEqual(feed.pending(a)[1], 0)
        self.assertEqual([e["execution"] for e in feed.pending(a)[0]], ["a%d" % n for n in range(1, 11)])

    def test_a_repeated_execution_is_not_captured_twice(self):
        """C3: an execution already in `verdicts[key]` is not captured again."""
        a, controller, r = self.started_session()
        self.scripted(controller, [self.response("accepted", "ok")])
        self.queue(controller, ["a1", "a1"])
        controller.read_verdict(r)
        controller.read_verdict(r)
        controller.save(r)
        events = [e for e in a.state["feed"]["events"] if e["kind"] == "verdict"]
        self.assertEqual(len(events), 1)
        self.assertEqual(a.state["feed"]["verdicts"], {"1/M1/1/-": ["a1"]})


class FeedQueueTests(RunsTest):
    def session(self):
        """A fresh approved fixture session with an empty feed (no runs)."""
        self.approve_fixture()
        self._session = self.fixture_authority()
        a = self._session.__enter__()
        self.addCleanup(self._session.__exit__, None, None, None)
        feed.bootstrap(a)
        return a

    def test_pending_and_handle_without_a_feed_are_empty(self):
        """C4: `[]. 0` without a feed and `handle` is a no-op."""
        self.approve_fixture()
        with self.fixture_authority() as a:
            self.assertNotIn("feed", a.state)
            self.assertEqual(feed.pending(a), ([], 0))
            feed.handle(a, 7)
            self.assertNotIn("feed", a.state)

    def test_handle_advances_the_mark_and_a_stale_ack_is_a_no_op(self):
        """C4: handle(E2) then handle(E1) leaves nothing pending and handled = E2.seq; the late ack does not save."""
        a = self.session()
        a.state["feed"] = {"seq": 2, "handled": 0, "last": {}, "verdicts": {},
                           "events": [state_event(1, state="running"),
                                      state_event(2, state="awaiting_merge", previous="running")]}
        batch, rest = feed.pending(a, limit=50)
        self.assertEqual([e["seq"] for e in batch], [1, 2])
        self.assertEqual(rest, 0)
        feed.handle(a, 2)
        self.assertEqual(feed.pending(a), ([], 0))
        self.assertEqual(a.state["feed"]["handled"], 2)
        raw = a.path.read_bytes()
        feed.handle(a, 1)  # stale
        self.assertEqual(a.state["feed"]["handled"], 2)
        self.assertEqual(a.path.read_bytes(), raw)

    def test_an_ack_whose_write_fails_stays_pending_and_a_retry_writes(self):
        """C4: handle(E1) whose save fails before the replace leaves handled 0 and E1 pending in memory too, so the
        retried ack writes instead of returning as a stale no-op."""
        a = self.session()
        a.state["feed"] = {"seq": 1, "handled": 0, "last": {}, "verdicts": {}, "events": [state_event(1)]}
        with patch("terminal_planner.authority.atomic_state", side_effect=PersistenceError("replace")):
            with self.assertRaises(PersistenceError):
                feed.handle(a, 1)
        self.assertEqual(a.state["feed"]["handled"], 0)
        self.assertEqual([e["seq"] for e in feed.pending(a)[0]], [1])
        feed.handle(a, 1)
        self.assertEqual(json.loads(a.path.read_text())["feed"]["handled"], 1)

    def test_a_bootstrap_whose_write_fails_leaves_no_feed_and_a_retry_writes(self):
        """C1: bootstrap whose save fails before the replace leaves no feed in memory, so a retried bootstrap writes
        it instead of returning as a no-op."""
        self.approve_fixture()
        with self.fixture_authority() as a:
            with patch("terminal_planner.authority.atomic_state", side_effect=PersistenceError("replace")):
                with self.assertRaises(PersistenceError):
                    feed.bootstrap(a)
            self.assertNotIn("feed", a.state)
            feed.bootstrap(a)
            self.assertIn("feed", json.loads(a.path.read_text()))

    def test_an_event_appended_after_a_read_has_a_higher_seq_and_stays_pending(self):
        """C4: `pending` is a read, not an ack: an event appended later keeps a higher seq and stays pending."""
        a = self.session()
        a.state["feed"] = {"seq": 1, "handled": 0, "last": {}, "verdicts": {}, "events": [state_event(1)]}
        batch, rest = feed.pending(a)
        self.assertEqual([e["seq"] for e in batch], [1])
        a.state["feed"]["events"].append(state_event(2, state="awaiting_merge", previous="running"))
        a.state["feed"]["seq"] = 2
        batch, rest = feed.pending(a)
        self.assertEqual([e["seq"] for e in batch], [1, 2])

    def test_a_big_queue_batches_the_oldest_and_keeps_everything_before_its_ack(self):
        """C4: 501 events -> `pending(limit=50)` gives E1..E50 and 451; every event is read before its ack and only
        the batch is bounded."""
        a = self.session()
        a.state["feed"] = synthetic(501)
        batch, rest = feed.pending(a, limit=50)
        self.assertEqual([e["seq"] for e in batch], list(range(1, 51)))
        self.assertEqual(rest, 451)
        seen = []
        while True:
            batch, rest = feed.pending(a, limit=50)
            if not batch:
                break
            seen += [e["seq"] for e in batch]
            feed.handle(a, batch[-1]["seq"])
        self.assertEqual(seen, list(range(1, 502)))
        self.assertEqual(feed.pending(a), ([], 0))
        self.assertEqual(a.state["feed"]["handled"], 501)
        self.assertEqual(a.state["feed"]["seq"], 501)


class FeedSummaryTests(RunsTest):
    """A6b2a C1: the catch-up batch and the event turn's text (`feed.batch`, `feed.summary`) and the unbounded read.

    Interpretations recorded for the reviewers: the head, the idle count, the rest count and the closing line are
    the task's quoted literals; the one state line names the milestone, the attempt and the transition, the one
    verdict line names the milestone, the task, the round, the role, the verdict and the verdict text clipped to 300
    characters. `feed.batch` ends on the `BATCH`-th (50th) wake event, the non-wake events behind it riding along;
    `rest` is everything after the batch."""

    def session(self):
        self.approve_fixture()
        self._session = self.fixture_authority()
        a = self._session.__enter__()
        self.addCleanup(self._session.__exit__, None, None, None)
        feed.bootstrap(a)
        return a

    def test_c1_pending_with_no_limit_returns_the_whole_queue_with_nothing_left(self):
        """C1: `feed.pending(authority, limit=None)` reads all of it and reports rest 0; `limit=50` stays the
        default."""
        a = self.session()
        a.state["feed"] = synthetic(60)
        everything, rest = feed.pending(a, limit=None)
        self.assertEqual([e["seq"] for e in everything], list(range(1, 61)))
        self.assertEqual(rest, 0)
        batch, rest = feed.pending(a)  # the default limit
        self.assertEqual([e["seq"] for e in batch], list(range(1, 51)))
        self.assertEqual(rest, 10)

    def test_c1_the_batch_ends_on_the_fiftieth_wake_event(self):
        """C1: the batch is the prefix up to and including the 50th wake event; a shorter list is one whole batch;
        the non-wake events behind a wake one ride along."""
        fifty_one = [state_event(n, state="awaiting_merge", previous="running") for n in range(1, 52)]
        batch, rest = feed.batch(fifty_one)
        self.assertEqual([e["seq"] for e in batch], list(range(1, 51)))
        self.assertEqual(rest, 1)
        short = [state_event(1, state="running", previous="preparing"),
                 state_event(2, state="awaiting_merge", previous="running"),
                 state_event(3, state="running", previous="awaiting_merge")]
        batch, rest = feed.batch(short)
        self.assertEqual([e["seq"] for e in batch], [1, 2, 3])
        self.assertEqual(rest, 0)

    def test_c1a_the_summary_carries_the_status_after_the_events_or_says_it_is_unavailable(self):
        """C1a C1/C2: the status is one compact line between the events and the closing instruction; an empty or
        `stale` status is the one unavailable line; no status leaves the text as it was."""
        batch = [state_event(1, state="awaiting_merge", previous="running")]
        plain = feed.summary(batch, 0).split("\n")
        self.assertEqual(feed.summary(batch, 0, None).split("\n"), plain)
        status = {"requests": [], "revision": 1, "rows": [{"id": "M1", "state": "done", "token": {"attempt": 1}}],
                  "plan": {"version": 1, "status": "approved"}}
        lines = feed.summary(batch, 0, status).split("\n")
        self.assertEqual(lines[:-2], plain[:-1])
        self.assertEqual(lines[-1], plain[-1])
        self.assertTrue(lines[-2].startswith("Status: {"), lines)
        self.assertEqual(json.loads(lines[-2][len("Status: "):]), status)
        long = {**status, "plan": {**status["plan"], "proposal": {"title": "x" * 2000}}}  # the plan text stays out
        sent = json.loads(feed.summary(batch, 0, long).split("\n")[-2][len("Status: "):])
        self.assertEqual(sent["plan"], status["plan"])
        for unavailable in ({}, {"rows": [], "stale": True}):
            self.assertEqual(feed.summary(batch, 0, unavailable).split("\n")[-2], feed.STATUS_UNAVAILABLE)

    def test_c1_the_summary_names_the_wake_events_and_counts_the_rest(self):
        """C1: the task's example — a batch of one non-wake and two wake events with rest 3 is six lines: the head,
        the awaiting_merge line, the verdict line, the idle count, the rest count and the closing line."""
        batch = [state_event(1, state="running", previous="preparing"),
                 state_event(2, state="awaiting_merge", previous="running"),
                 verdict_event(3)]
        lines = feed.summary(batch, 3).split("\n")
        self.assertEqual(len(lines), 6)
        self.assertEqual(lines[0], "Events since the last turn:")
        self.assertIn("M1", lines[1])
        self.assertIn("running -> awaiting_merge", lines[1])
        for field in ("M1", "T2", "2", "code_review", "accepted", "ok"):
            self.assertIn(field, lines[2])
        self.assertEqual(lines[3], "Intermediate states without action: 1.")
        self.assertEqual(lines[4], "… and 3 more events.")
        self.assertEqual(lines[5], "Assess them against the snapshot and act by your rules; "
                         "if there is nothing to decide, answer briefly.")

    def test_c1_sixty_idle_events_and_one_wake_are_one_batch_of_one_wake_line(self):
        """C1: sixty non-wake events then one wake event is one batch of all 61, one wake line and the idle count,
        with no rest line (rest 0)."""
        events = [state_event(n, state="running", previous="preparing") for n in range(1, 61)] \
            + [state_event(61, state="awaiting_merge", previous="running")]
        batch, rest = feed.batch(events)
        self.assertEqual(len(batch), 61)
        self.assertEqual(rest, 0)
        lines = feed.summary(batch, rest).split("\n")
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0], "Events since the last turn:")
        self.assertIn("awaiting_merge", lines[1])
        self.assertEqual(lines[2], "Intermediate states without action: 60.")
        self.assertEqual(lines[3], "Assess them against the snapshot and act by your rules; "
                         "if there is nothing to decide, answer briefly.")

    def test_c1_the_verdict_text_is_clipped_to_three_hundred_characters(self):
        """C1: a verdict's text is clipped to 300 characters in its line."""
        long_text = "а" * 400
        lines = feed.summary([verdict_event(1, text=long_text)], 0).split("\n")
        self.assertIn("а" * 300, lines[1])
        self.assertNotIn("а" * 301, lines[1])

    def test_c1_a_multiline_verdict_text_is_normalized_to_one_line(self):
        """C1 (regression): an ordinary verdict text carrying a newline is normalized to one line, so the summary
        keeps its line count (head, one verdict line, the closing line); the 300-character bound still holds after
        the normalization."""
        lines = feed.summary([verdict_event(1, text="первая\nвторая")], 0).split("\n")
        self.assertEqual(len(lines), 3)
        self.assertIn("первая вторая", lines[1])
        clipped = feed.summary([verdict_event(1, text=("а" * 400) + "\nхвост")], 0).split("\n")
        self.assertEqual(len(clipped), 3)
        self.assertNotIn("а" * 301, clipped[1])
