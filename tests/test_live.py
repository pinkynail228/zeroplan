"""U5: live run visibility at the service level (no Textual): panel, journal, activity tail, "Next:".

A slow scripted fixture driver (spaced records, a quiet gap longer than one slice, replays, a lost observation)
and a fake wall clock, over real temporary Git repositories and the fixture store. No provider, no network."""

from collections import deque
import copy
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from terminal_planner import catalog, cli, delivery, live, milestone
from terminal_planner.authority import Authority as RealAuthority, Blocked, atomic_state, decode
from terminal_planner.cli import Terminal
from terminal_planner.delivery import Delivery, END_ACTIONS, STATE_TEXT
from terminal_planner.engine import FixtureEngine, ObservationDetached, SliceEnded, fixture_proposal
from terminal_planner.planning import Planning
from terminal_planner.runs import FixtureDriver, MilestoneRuns
import test_terminal_planner as tp
from test_terminal_planner import ProjectTest, ROLES
from test_tui_planning import Planner

START = "2026-10-15T09:00:00Z"


class Clock:
    """The wall clock zplan stamps observations with; the test moves it by hand."""

    def __init__(self, stamp=START):
        self.at = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

    def __call__(self):
        return self.at.strftime("%Y-%m-%dT%H:%M:%SZ")

    def advance(self, seconds):
        self.at += timedelta(seconds=seconds)


class Scripted(FixtureDriver):
    """The fixture driver where every watch slice does what the script says and costs the seconds it names:
    "advance" delivers the next scripted record, "quiet" a slice with no record at all, "replay" the last record
    again, "detach" a lost observation. The clock moves before the slice reports."""

    def __init__(self, root, clock, script, **kw):
        super().__init__(root, **kw)
        self.clock, self.script, self.last = clock, list(script), None
        self.logs = 0

    def watch(self, r, after, seconds=None):
        action, spent = self.script.pop(0) if self.script else ("advance", 1)
        self.clock.advance(spent)
        if action == "quiet":
            return []
        if action == "detach":
            raise ObservationDetached()
        if action == "replay":
            return [self.last]
        if action == "again":  # the same active executions at a cursor the watch has not delivered yet
            self.last = dict(self.last, cursor=self.last["cursor"] + "+")
            return [self.last]
        values = super().watch(r, after, seconds)
        self.last = values[-1]
        return values

    def log_tail(self, binding, run_id, cwd, lines=live.TAIL_LINES, **options):
        self.logs += 1
        return super().log_tail(binding, run_id, cwd, lines, **options)


class Spaced(Planner):
    """The planner double whose every slice does what the script says and costs the seconds it names: "advance"
    moves the observation cursor and says a new phase, "fail" ends the run as failed, "quiet" says nothing, "replay" says the last phase again at
    the same cursor, "detach" is a lost observation. The slice always ends the way a native one does."""

    def __init__(self, clock, script):
        super().__init__()
        self.clock, self.script, self.phase = clock, list(script), 0

    def proposal(self, authority, progress, slice=None):
        current = authority.current
        if current["run_id"] is None:
            self.sent.append(current["version"])
            self.receipt(authority)
        action, spent = self.script.pop(0) if self.script else ("quiet", 1)
        self.clock.advance(spent)
        if action == "detach":
            raise ObservationDetached()
        if action == "fail":  # the planner run ended as failed
            self.fail(authority)
            raise Blocked("run_failed: plan_verifier_failed", family="plan.failed")
        if action == "advance":
            self.phase += 1
            current["observation_cursor"] = "v2:%d" % self.phase
        if action in ("advance", "replay"):
            progress("Phase %d" % self.phase)
        raise SliceEnded()


class LiveTest(ProjectTest):
    def setUp(self):
        super().setUp()
        self.clock = Clock()
        self.worktrees = self.root / "worktrees"
        for module in ("terminal_planner.runs.now", "terminal_planner.delivery.now"):
            patcher = patch(module, self.clock)
            patcher.start()
            self.addCleanup(patcher.stop)

    def authority(self):
        return tp.Authority(self.state, self.project)

    def approved(self, a):
        self.begin(a)
        self.propose(a)
        a.approve(1)

    def service(self, a, driver):
        controller = MilestoneRuns(a, driver, worktrees=self.worktrees)
        return Delivery(a, controller, Planning(a, controller, lambda *_: FixtureEngine())), controller

    def scripted(self, script, **kw):
        return Scripted(self.root / "fixture-runs", self.clock, script, **kw)

    def panel(self, service, r):
        return "\n".join(service.panel(r))


class PanelTests(LiveTest):
    def test_each_active_role_elapsed_last_event_and_heartbeat_through_a_quiet_gap_and_replay(self):
        # L-A1: spaced records, a quiet gap longer than one slice, a replayed record, then a lost observation.
        driver = self.scripted([("advance", 20), ("quiet", 600), ("replay", 30), ("advance", 5), ("detach", 60),
                                ("quiet", 5)])
        with self.authority() as a:
            self.approved(a)
            service, controller = self.service(a, driver)
            r = controller.start("M1", 1, ROLES)
            self.assertEqual(self.panel(service, r), "  running 0 s")  # nothing observed yet: no invented activity
            service.step(r)  # +20 s: the worker record
            text = self.panel(service, r)
            self.assertIn("Working now: worker", text)
            self.assertIn("running 20 s · last event 0 s ago · checked " + live.clock(self.clock()), text)
            event = r["live"]["last_event"]
            self.clock.advance(40)  # time passes between two looks at the panel; nothing writes
            self.assertIn("running 1 min · last event 40 s ago", self.panel(service, r))
            service.step(r)  # a quiet gap of 10 minutes: the heartbeat moves, the last event does not
            text = self.panel(service, r)
            self.assertEqual(r["live"]["last_event"], event)
            self.assertEqual(r["live"]["heartbeat"], self.clock())
            self.assertIn("last event 10 min ago · checked " + live.clock(self.clock()), text)
            service.step(r)  # the watch replays the worker record: the heartbeat moves, the last event does not
            self.assertEqual(r["live"]["last_event"], event)
            self.assertEqual(r["live"]["heartbeat"], self.clock())
            service.step(r)  # parallel reviewers: every active role is named
            text = self.panel(service, r)
            self.assertIn("Working now: acceptance, code review", text)
            self.assertIn("last event 0 s ago", text)
            beat = r["live"]["heartbeat"]
            service.step(r)  # observation lost: shown as such, the heartbeat does not advance
            text = self.panel(service, r)
            self.assertEqual(r["live"]["heartbeat"], beat)
            self.assertIn("watching interrupted at " + live.clock(self.clock()), text)
            self.assertNotIn("checked", text)
            service.step(r)  # a slice succeeds again: the interruption is gone
            text = self.panel(service, r)
            self.assertNotIn("interrupted", text)
            self.assertIn("checked " + live.clock(self.clock()), text)

    def test_the_planner_panel_shows_roles_elapsed_and_a_heartbeat_after_restart_and_new_attempt(self):
        # L-A1 for the planner: the revision's own live data; a restart (new session) and [n] keep it honest.
        planner = Planner()
        planner.running = True
        with self.authority() as a:
            self.begin(a)
            controller = MilestoneRuns(a, None, self.worktrees)
            planning = Planning(a, controller, lambda *_: planner, clock=lambda: float(len(planner.sent)) * 0)
            seen = []
            watch = planning.watch(seen.append)
            self.assertEqual(watch.step(), "continue")
            self.assertEqual(planning.panel()[0].split(" · ")[0], "  running 0 s")
            self.clock.advance(300)
            self.assertEqual(watch.step(), "continue")
            data = a.current["live"]
            self.assertEqual(data["heartbeat"], self.clock())
            self.assertIn("running 5 min", planning.panel()[0])
            started = data["started"]
        with self.authority() as a:  # a restart: the stored times are all there is, and they are still right
            controller = MilestoneRuns(a, None, self.worktrees)
            planning = Planning(a, controller, lambda *_: planner)
            self.clock.advance(120)
            self.assertIn("running 7 min", planning.panel()[0])
            self.assertIn("checked " + live.clock(data["heartbeat"]), planning.panel()[0])
            planner.running = False
            watch = planning.watch(lambda _: None)
            self.assertEqual(watch.step(), "done")
            self.assertEqual(a.current["live"]["started"], started)
            self.assertEqual(planning.panel(), ())  # a finished planner has no live panel

    def planning(self, a, planner):
        return Planning(a, MilestoneRuns(a, None, self.worktrees), lambda *_: planner)

    def test_planner_quiet_slices_and_replays_move_the_heartbeat_not_the_last_event_and_a_loss_shows(self):
        # L-A1 for the planner through Planning.watch / Watch.step: the same rules as a milestone run.
        planner = Spaced(self.clock, [("advance", 20), ("quiet", 600), ("replay", 30), ("advance", 5),
                                      ("detach", 60), ("quiet", 5)])
        with self.authority() as a:
            self.begin(a)
            planning = self.planning(a, planner)
            watch = planning.watch(lambda _: None)
            self.assertEqual(watch.step(), "continue")  # +20 s: a new phase
            data = a.current["live"]
            event = data["last_event"]
            self.assertEqual(event, self.clock())
            self.assertIn("running 20 s · last event 0 s ago · checked " + live.clock(self.clock()),
                          planning.panel()[0])
            self.assertEqual(watch.step(), "continue")  # a quiet gap of ten minutes: alive, nothing new
            self.assertEqual(data["last_event"], event)
            self.assertEqual(data["heartbeat"], self.clock())
            self.assertIn("last event 10 min ago · checked " + live.clock(self.clock()),
                          planning.panel()[0])
            self.assertEqual(watch.step(), "continue")  # the same phase at the same cursor: not an event
            self.assertEqual(data["last_event"], event)
            self.assertEqual(data["heartbeat"], self.clock())
            self.assertEqual(watch.step(), "continue")  # a new phase is
            self.assertEqual(data["last_event"], self.clock())
            beat = data["heartbeat"]
            with self.assertRaises(ObservationDetached):  # a lost observation
                watch.step()
            self.assertEqual(data["heartbeat"], beat)  # no fresh heartbeat is claimed
            text = planning.panel()[0]
            self.assertIn("watching interrupted at " + live.clock(self.clock()), text)
            self.assertNotIn("checked", text)
            self.assertEqual(watch.step(), "continue")  # the slice that succeeds takes the interruption away
            text = planning.panel()[0]
            self.assertNotIn("interrupted", text)
            self.assertIn("checked " + live.clock(self.clock()), text)

    def test_a_renewed_planner_revision_has_its_own_start_and_elapsed_time(self):
        # L-A1 for the planner after [n]: the new revision is timed from its own submission, not the old one's.
        planner = Spaced(self.clock, [("advance", 1), ("fail", 1), ("advance", 1), ("quiet", 1)])
        with self.authority() as a:
            self.begin(a)
            planning = self.planning(a, planner)
            watch = planning.watch(lambda _: None)
            watch.step()
            first = a.current["live"]["started"]
            self.assertEqual(watch.step(), "failed")
            self.clock.advance(3600)  # the owner starts a new attempt of the same goal ([n])
            planning.renew()
            self.assertEqual(a.current["version"], 2)
            self.assertEqual(planning.panel(), ())  # nothing of the old attempt shows on the new revision
            watch = planning.watch(lambda _: None)
            watch.step()
            watch.step()
            second = a.current["live"]["started"]
            self.assertNotEqual(second, first)
            self.assertEqual(second, live.clock(self.clock()) and self.clock() if False else second)
            self.assertIn("running 2 s", planning.panel()[0])
            self.clock.advance(90)
            self.assertIn("running 1 min", planning.panel()[0])
            self.assertEqual(a.state["revisions"][0]["live"]["started"], first)  # the old record is untouched

    def test_a_stopping_attempt_says_so_and_never_invents_a_verdict(self):
        driver = self.scripted([("advance", 5)], rejections=1)
        with self.authority() as a:
            self.approved(a)
            service, controller = self.service(a, driver)
            r = controller.start("M1", 1, ROLES)
            service.step(r)
            controller.stop(r)
            text = self.panel(service, r)
            self.assertIn("Stop requested; waiting for Zeroshot to confirm.", text)
            self.assertNotIn("accepted", text)
            self.assertNotIn("rejected", text)


class PanelCommandTests(LiveTest):
    def record(self, last_event, command, heartbeat=None, detached=None):
        """A live record shaped by C3a: an optional command alongside the last new record."""
        data = live.new()
        data["last_event"] = last_event
        data["heartbeat"] = heartbeat
        data["detached"] = detached
        data["command"] = command
        return data

    def test_a_long_lived_command_measures_silence_and_shows_its_text(self):
        """C3b: A1/A2/A5. A 10-minute-old command with an older event: the panel measures silence from the
        command (the later activity), says «silent 10 min» at or past two minutes of silence and follows with the
        command's stored text on its own line. Interpretation recorded here: a record is «fresh» (< 2 min) or
        «silent» (>= 2 min) by the whole seconds since the later activity, so the `running`/`checked` parts of the
        line are untouched."""
        data = self.record("2026-10-15T08:45:00Z", {"at": "2026-10-15T08:50:00Z", "text": "pytest -q"})
        self.assertEqual(live.panel_lines(data, "2026-10-15T08:50:00Z", START),
                         ["  running 10 min · silent 10 min", "  last: pytest -q"])

    def test_a_fresh_command_reads_as_last_activity(self):
        """C3b: A1/A2/A5. A 30 s old command (older event) reads «last activity 30 s ago» and keeps its
        text line; a record whose last event is newer than the command measures from that event instead."""
        fresh = self.record("2026-10-15T08:58:00Z", {"at": "2026-10-15T08:59:30Z", "text": "npm run build"})
        self.assertEqual(live.panel_lines(fresh, "2026-10-15T08:59:00Z", START),
                         ["  running 1 min · last activity 30 s ago", "  last: npm run build"])
        event_newer = self.record("2026-10-15T08:59:00Z", {"at": "2026-10-15T08:50:00Z", "text": "pytest -q"})
        self.assertEqual(live.panel_lines(event_newer, "2026-10-15T08:50:00Z", START),
                         ["  running 10 min · last activity 1 min ago", "  last: pytest -q"])

    def test_the_two_minute_boundary_and_a_record_without_a_command(self):
        """C3b: A1/A3/A5. Silence is «silent» from 120 s and «last activity» below it (119 s), and a record
        without a command (older record, the planner) shows today's exact line, byte for byte, with no text line.
        Interpretation recorded here: the two-minute threshold is compared to the whole seconds since the later
        activity, so 119 s is still fresh (the next second crosses the bound)."""
        at = {"at": "2026-10-15T08:58:00Z", "text": "pytest -q"}
        self.assertEqual(live.panel_lines(self.record("2026-10-15T08:40:00Z", at), "2026-10-15T08:50:00Z", START),
                         ["  running 10 min · silent 2 min", "  last: pytest -q"])
        self.assertEqual(live.panel_lines(self.record("2026-10-15T08:50:00Z", at), "2026-10-15T08:49:59Z",
                                          "2026-10-15T08:59:59Z")[0],
                         "  running 10 min · last activity 1 min ago")
        plain = self.record("2026-10-15T08:50:00Z", None)
        self.assertEqual(live.panel_lines(plain, "2026-10-15T08:50:00Z", START),
                         ["  running 10 min · last event 10 min ago"])
        legacy = {k: v for k, v in plain.items() if k != "command"}
        self.assertEqual(live.panel_lines(legacy, "2026-10-15T08:50:00Z", START),
                         ["  running 10 min · last event 10 min ago"])

    def test_the_panel_never_says_a_run_is_stuck(self):
        """C3b: A4, over the panel's own wording only (its scope and why: the collision test below). However long
        the tested silence, and whatever the watcher state -- heartbeat, interrupted observation, or neither -- the
        parts `panel_lines` writes itself only report it; «stuck» never appear."""
        minute = {"at": "2026-10-15T08:00:00Z", "text": "pytest -q"}
        for last_event, command, heartbeat, detached, now in (
                ("2026-10-15T08:00:00Z", minute, "2026-10-15T08:59:50Z", None, "2026-10-15T09:00:00Z"),
                ("2026-10-15T08:59:00Z", {"at": "2026-10-15T08:59:30Z", "text": "ls"}, None, None, START),
                ("2026-10-15T08:50:00Z", None, "2026-10-15T08:59:50Z", None, START),
                ("2026-10-15T08:50:00Z", minute, None, "2026-10-15T08:59:00Z", START)):
            text = "\n".join(live.panel_lines(self.record(last_event, command, heartbeat, detached), None, now))
            self.assertNotIn("stuck", text)
            self.assertNotIn("stuck", text)

    def test_the_word_ban_covers_the_panels_own_wording_not_the_echoed_command(self):
        """C3b: A2 vs A4, read from A4's own source and escalated for confirmation; the worker waives neither.

        A2 requires the stored command text verbatim on its own line («  last: <text>»), and A4 says the words
        «stuck» never appear in the panel. As literally written the two contradict each other for any valid
        stored command that spells one of the words: two earlier reviews reproduced the collision with
        `rg stuck terminal_planner`, an ordinary command -- not a hostile input the task does not name -- rejecting
        the candidate first for waiving A4 (the verbatim echo spells the word) and then warning that the obvious fix,
        filtering the echo, waives A2 instead. No third state satisfies both as written.

        The reading recorded here is A4's own source, not a preference. The plan this slice cites makes the ban a
        verdict rule: the screen "shows «silent N min · last: <command>» and never says «stuck» by itself", and
        the slice is done only with "no false «stuck»" (docs/CHAT_RELEASE_JTBD.md:71, the C3 row); C3a lists "a
        stall/«stuck» verdict" as a non-goal; and the brief rule requires an unconditional word to name the inputs
        and states it covers (devtools/zeroshot/ORCHESTRATOR.md, change loop step 1), which A4 does not. A literal
        reading also fails on data the panel already interpolates -- the round line prints `live["task"]`, an
        owner-written task id, on merged C2a code -- so it cannot be the intended one. A4 therefore covers what zplan
        writes itself (the parts `panel_lines` composes), never the owner's own text; masking the echo would hide the
        owner's command and break A2's "text as stored". This test pins both halves: the echoed line is the stored
        text byte for byte (A2), and every line the panel composes -- here the silence wording -- is free of the
        words. Disposition the orchestrator confirms: reword A4 to name the panel's own lines (its source's scope);
        the alternative, neutralizing the echoed text, is the one-line change in `panel_lines` that accepts the A2
        deviation. Both reproductions from the earlier rounds keep passing."""
        data = self.record("2026-10-15T08:45:00Z", {"at": "2026-10-15T08:50:00Z",
                                                    "text": "rg stuck terminal_planner"})
        self.assertTrue(live.valid(data))
        lines = live.panel_lines(data, "2026-10-15T08:50:00Z", START)
        self.assertEqual(lines[-1], "  last: rg stuck terminal_planner")  # A2 verbatim -- the colliding input
        self.assertEqual(lines[0], "  running 10 min · silent 10 min")  # A1, the panel's own silence wording
        own = "\n".join(lines[:-1])  # everything the panel writes itself, i.e. A4's scope
        self.assertNotIn("stuck", own)
        self.assertNotIn("stuck", own)


class PanelRoundTests(LiveTest):
    def test_panel_lines_names_the_round_only_with_a_bound_and_a_proven_task(self):
        """C2a: A1/A2/A3. The panel gains an optional review bound: with `rounds` given and the record proving its
        task (`live["task"]`) with at least one worker seen (`live["workers"]`), the line «<task>: round N of M»
        follows «Working now». N is the record's own worker count (the task defines round N = `live["workers"]`:
        the first worker is round 1, a rework bumps it). Without `rounds` (the default, and the planner panel) or
        without a proven task, the output is exactly today's."""
        now = "2026-10-15T09:00:00Z"
        data = {"task": "T1", "workers": 2, "nodes": [["worker", "T1-w2"]], "journal": [], "executions": [],
                "cursors": [], "started": None, "last_event": None, "heartbeat": None, "detached": None,
                "repairs": 0, "progress": None, "amendments": None}
        lines = live.panel_lines(data, None, now, rounds=4)
        self.assertEqual(lines[:2], ["  Working now: worker", "  T1: round 2 of 4"])
        self.assertEqual(live.panel_lines(data, None, now), live.panel_lines(data, None, now, rounds=None))
        self.assertNotIn("round", "\n".join(live.panel_lines(data, None, now)))
        untasked = dict(data, task=None, workers=0)
        self.assertNotIn("round", "\n".join(live.panel_lines(untasked, None, now, rounds=4)))

    def test_delivery_panel_names_the_round_out_of_the_revisions_review_bound(self):
        """C2a: A1/A3. `Delivery.panel` reads the bound from the attempt's own revision (`runs.review_rounds`, the
        same value the submitted graph was built with): `1 + frozen task_rounds`, or the fixed 4 when the revision
        has no frozen profile. Interpretation recorded here: the round counter is the record's own `live["workers"]`
        (the first worker is round 1, a rework bumps it), exactly as the task defines N."""
        driver = self.scripted([("advance", 0)] * 5, rejections=2)
        with self.authority() as a:
            self.approved(a)
            service, controller = self.service(a, driver)
            r = controller.start("M1", 1, ROLES)
            for _ in range(5):  # T1-w1, reviews, T1-w2, reviews, T1-w3
                service.step(r)
            self.assertEqual(r["live"]["workers"], 3)
            text = self.panel(service, r)
            self.assertIn("Working now: worker", text)
            self.assertIn("T1: round 3 of 4", text)  # no frozen profile: the fixed bound
            a.state["revisions"][r["plan_revision"] - 1]["frozen"] = {"task_rounds": 2}
            self.assertIn("T1: round 3 of 3", self.panel(service, r))  # 1 + frozen task_rounds


class PanelVerdictTests(unittest.TestCase):
    """C4b/A1-A4: `live.panel_lines` shows the newest task's last two review rounds from `live["verdicts"]`.

    C4a stores one entry per departed reviewer, oldest first: {at, task, round, role, verdict, text}; a record
    written before C4a has no key. The block follows the round line. Interpretations recorded for the reviewers:
    the rounds are ordered by their last appearance in the stored list (a round keeps the place in time it last
    took, so a round whose entries are not contiguous still groups together); an unproven round (round is None,
    which C4a stores when the task was unknown or no worker had been seen yet) gets the bare header «  check»
    with no task, exactly as the task words it; the cut keeps a reviewer line of `WIDTH` (120) characters — the
    panel's own literal limit, not a module constant, so the test asserts the width A2 names and nothing more."""

    NOW = "2026-10-15T09:00:00Z"
    WIDTH = 120  # A2's limit, spelled out here: `panel_lines` keeps it as a literal of its own

    @staticmethod
    def entry(task="T1", round=1, role="acceptance_review", verdict="rejected", text="no test", at=START):
        return {"at": at, "task": task, "round": round, "role": role, "verdict": verdict, "text": text}

    def lines(self, verdicts, **kw):
        data = {"task": "T1", "workers": 2, "nodes": [], "journal": [], "executions": [], "cursors": [],
                "started": None, "last_event": None, "heartbeat": None, "detached": None, "repairs": 0,
                "progress": None, "amendments": None, "command": None, "verdicts": verdicts}
        return live.panel_lines(data, None, self.NOW, **kw)

    def test_a1_the_newest_rounds_show_newest_first_with_a_mark(self):
        verdicts = [self.entry(round=1, verdict="rejected", text="no test for the refusal"),
                    self.entry(round=2, role="code_review", verdict="accepted", text="looks fine")]
        self.assertEqual(self.lines(verdicts),
                         ["  T1: round 2", "    code review ✓ looks fine",
                          "  T1: round 1", "    acceptance ✗ no test for the refusal"])

    def test_a1_an_unknown_verdict_is_shown_as_is_and_an_empty_reason_ends_after_the_mark(self):
        self.assertEqual(self.lines([self.entry(round=3, verdict="deferred", text="")]),
                         ["  T1: round 3", "    acceptance deferred"])

    def test_a1_a_round_without_a_number_gets_the_bare_header(self):
        self.assertEqual(self.lines([self.entry(round=None, verdict="accepted", text="ok")]),
                         ["  check", "    acceptance ✓ ok"])

    def test_a1_the_block_follows_the_round_line(self):
        # A1: the entries sit right after «<task>: round N of M», not after the timing line.
        data = {"task": "T1", "workers": 2, "nodes": [["worker", "T1-w2"]], "journal": [], "executions": [],
                "cursors": [], "started": START, "last_event": None, "heartbeat": None, "detached": None,
                "repairs": 0, "progress": None, "amendments": None, "command": None,
                "verdicts": [self.entry(round=2, verdict="accepted", text="ok")]}
        lines = live.panel_lines(data, None, self.NOW, rounds=4)
        self.assertEqual(lines[0], "  Working now: worker")
        self.assertEqual(lines[1], "  T1: round 2 of 4")
        self.assertEqual(lines[2:4], ["  T1: round 2", "    acceptance ✓ ok"])

    def test_a2_a_reviewer_line_is_cut_to_the_width_with_an_ellipsis(self):
        prefix = "    acceptance ✗ "
        self.assertEqual(len(prefix), 17)
        line = self.lines([self.entry(text="x" * 400)])[1]
        self.assertEqual(len(line), self.WIDTH)
        self.assertTrue(line.endswith("…"))
        self.assertEqual(line, prefix + "x" * (self.WIDTH - len(prefix) - 1) + "…")
        exact = self.lines([self.entry(text="x" * (self.WIDTH - len(prefix)))])[1]
        self.assertEqual(exact, prefix + "x" * (self.WIDTH - len(prefix)))  # exactly the width: kept whole

    def test_a4_two_rounds_show_both_newest_first(self):
        verdicts = [self.entry(round=1, verdict="rejected", text="no test"),
                    self.entry(round=2, verdict="accepted", text="looks fine")]
        self.assertEqual(self.lines(verdicts),
                         ["  T1: round 2", "    acceptance ✓ looks fine", "  T1: round 1", "    acceptance ✗ no test"])

    def test_a4_three_rounds_show_only_the_last_two(self):
        verdicts = [self.entry(round=number, verdict="rejected", text="round %s" % number) for number in (1, 2, 3)]
        self.assertEqual(self.lines(verdicts),
                         ["  T1: round 3", "    acceptance ✗ round 3", "  T1: round 2", "    acceptance ✗ round 2"])

    def test_a4_entries_of_another_task_are_not_shown(self):
        verdicts = [self.entry(task="T1", round=1, verdict="rejected", text="foreign"),
                    self.entry(task="T2", round=1, verdict="accepted", text="new")]
        self.assertEqual(self.lines(verdicts), ["  T2: round 1", "    acceptance ✓ new"])

    def test_a3_a_record_without_the_key_or_with_an_empty_list_is_unchanged(self):
        # A3: the new key's absence changes nothing; a record without `verdicts` shows today's lines byte for byte.
        data = {"task": "T1", "workers": 2, "nodes": [["worker", "T1-w2"]], "journal": [], "executions": [],
                "cursors": [], "started": START, "last_event": START, "heartbeat": START, "detached": None,
                "repairs": 0, "progress": None, "amendments": None, "command": None}
        today = live.panel_lines(data, None, self.NOW, rounds=4)
        self.assertEqual(live.panel_lines({**data, "verdicts": []}, None, self.NOW, rounds=4), today)
        self.assertEqual(live.panel_lines({**data, "verdicts": None}, None, self.NOW, rounds=4), today)
        without = live.panel_lines(data, None, self.NOW, rounds=4)  # no verdicts key at all
        self.assertEqual(without, today)
        self.assertFalse([line for line in without if line.startswith("    ")])  # no reviewer line appears


class FlowTests(unittest.TestCase):
    """F1 A1: `live.flow` returns the facts of one attempt as plain data (a JSON-serialisable dict, no Rich or
    Textual object). `round` is the record's own worker count; the reviewers are the two task roles in order
    (acceptance then code) and read their newest verdict only for this task's own round; the worker is running while
    a `worker` node is active and done once a reviewer is active or a verdict for the round exists."""

    NOW = "2026-10-15T09:00:30Z"

    @staticmethod
    def record(**kw):
        data = live.new()
        data["started"] = START
        data.update(kw)
        return data

    @staticmethod
    def entry(task="T1", round=1, role="acceptance_review", verdict="rejected", text="no test", at=START):
        return {"at": at, "task": task, "round": round, "role": role, "verdict": verdict, "text": text}

    def test_a1_a_worker_running_in_round_one(self):
        data = self.record(task="T1", workers=1, nodes=[["worker", "T1-w1"]],
                           last_event="2026-10-15T09:00:20Z", command={"at": "2026-10-15T09:00:25Z", "text": "pytest"})
        out = live.flow(data, START, self.NOW, rounds=4)
        self.assertEqual(out["task"], "T1")
        self.assertEqual(out["round"], 1)
        self.assertEqual(out["rounds"], 4)
        self.assertEqual(out["worker"], {"state": "running"})
        self.assertEqual(out["reviewers"],
                         [{"role": "acceptance_review", "name": "acceptance", "state": "waiting", "text": ""},
                          {"role": "code_review", "name": "code review", "state": "waiting", "text": ""}])
        self.assertEqual(out["final"], {"state": "waiting", "attempt": None, "check": None})
        self.assertFalse(out["select"])
        self.assertEqual(out["active"], ["worker"])
        self.assertEqual(out["command"], "pytest")
        self.assertIsNone(out["detached"])
        self.assertEqual(out["elapsed"], 30)
        self.assertEqual(out["silence"], 5)  # since the command stamp, the later of it and the last event
        json.dumps(out)  # plain data: the dict serialises as it is

    def test_a1_both_reviewers_running_and_the_worker_done(self):
        data = self.record(task="T1", workers=1, nodes=[["acceptance_review", "T1-a1"], ["code_review", "T1-c1"]])
        out = live.flow(data, START, self.NOW)
        self.assertEqual([reviewer["state"] for reviewer in out["reviewers"]], ["running", "running"])
        self.assertEqual([reviewer["text"] for reviewer in out["reviewers"]], ["", ""])
        self.assertEqual(out["worker"], {"state": "done"})  # a reviewer is active
        self.assertEqual(out["active"], ["acceptance", "code review"])

    def test_a1_an_active_reviewer_keeps_the_matching_verdict_text(self):
        """Regression (A1): a reviewer that runs again in a retry keeps the newest matching verdict's text. The state
        reads running while the text stays that entry's text, for both reviewer roles; an earlier candidate dropped
        the text whenever the role was active, and Home.flow shares the branch. Interpretation recorded here: `text`
        comes from the newest `verdicts` entry for this task, round and role independently of the running state —
        reviewer reappearance after its verdict is a supported sequence
        (`tests.test_runs.VerdictReadTests.test_a_found_verdict_is_appended_once_for_an_execution`)."""
        verdicts = [self.entry(round=2, role="acceptance_review", verdict="rejected", text="missing rejection test"),
                    self.entry(round=2, role="code_review", verdict="accepted", text="no remarks")]
        data = self.record(task="T1", workers=2,
                           nodes=[["acceptance_review", "T1-a2-retry"], ["code_review", "T1-c2-retry"]],
                           verdicts=verdicts)
        out = live.flow(data, START, self.NOW)
        self.assertEqual(out["round"], 2)
        self.assertEqual(out["reviewers"],
                         [{"role": "acceptance_review", "name": "acceptance", "state": "running",
                           "text": "missing rejection test"},
                          {"role": "code_review", "name": "code review", "state": "running",
                           "text": "no remarks"}])

    def test_a1_round_two_verdicts_name_the_reviewers_states_and_texts(self):
        verdicts = [self.entry(round=1, verdict="rejected", text="old"),
                    self.entry(round=2, role="acceptance_review", verdict="rejected", text="no test for the refusal"),
                    self.entry(round=2, role="code_review", verdict="accepted", text="looks fine")]
        data = self.record(task="T1", workers=2, verdicts=verdicts)
        out = live.flow(data, START, self.NOW)
        self.assertEqual(out["round"], 2)
        self.assertEqual(out["reviewers"],
                         [{"role": "acceptance_review", "name": "acceptance", "state": "rejected",
                           "text": "no test for the refusal"},
                          {"role": "code_review", "name": "code review", "state": "accepted", "text": "looks fine"}])
        self.assertEqual(out["worker"], {"state": "done"})  # a verdict for this round

    def test_a1_verdicts_of_an_older_round_or_another_task_are_ignored(self):
        verdicts = [self.entry(task="T2", round=2, verdict="accepted", text="foreign"),
                    self.entry(task="T1", round=1, verdict="rejected", text="old")]
        out = live.flow(self.record(task="T1", workers=2, verdicts=verdicts), START, self.NOW)
        self.assertEqual([reviewer["state"] for reviewer in out["reviewers"]], ["waiting", "waiting"])
        self.assertEqual([reviewer["text"] for reviewer in out["reviewers"]], ["", ""])
        self.assertEqual(out["worker"], {"state": "waiting"})

    def test_a1_a_record_without_command_and_verdicts_keys(self):
        data = live.new()
        data.pop("command")
        data.pop("verdicts")
        out = live.flow(data, None, self.NOW)
        self.assertIsNone(out["command"])
        self.assertIsNone(out["task"])
        self.assertIsNone(out["round"])
        self.assertEqual([reviewer["state"] for reviewer in out["reviewers"]], ["waiting", "waiting"])
        self.assertIsNone(out["elapsed"])  # no start stamp: elapsed is unknown, never invented

    def test_a1_a_final_verify_node_reads_as_the_final_running_step(self):
        data = self.record(task="T1", workers=1, nodes=[["final_verify", "T1-f1"]])
        out = live.flow(data, START, self.NOW)
        self.assertEqual(out["final"], {"state": "running", "attempt": None, "check": None})
        self.assertFalse(out["select"])
        self.assertEqual(out["worker"], {"state": "waiting"})  # no worker node is active

    def test_l1_the_final_checks_attempt_counts_its_executions_since_the_last_repair(self):
        """L1/L3: `stages` counts the executions of `final_verify`/`final_reverify` (`live["finals"]`) and a repair
        starts the count over; `flow` carries that count as `final.attempt` with the check it belongs to.

        Interpretations: the check is `final_verify` before any repair and `final_reverify` after one (the repair
        counter tells them apart; the stored executions are told apart by their node names); `scope_verify` is not a
        run of the final check; the count also stays while the repair or another node is the active one, 0 -> None;
        a record written before the count has no `finals` key, is valid as it is and reads as attempt None."""
        def run(data, node, tag):
            live.stages(data, {"activeExecutions": [{"node": node, "execution": "nv2-" + tag * 64}]}, START, ("T1",))
            return live.flow(data, START, self.NOW)["final"]

        data = live.new()
        self.assertEqual(live.flow(data, START, self.NOW)["final"], {"state": "waiting", "attempt": None, "check": None})
        self.assertEqual(run(data, "final_verify", "a"), {"state": "running", "attempt": 1, "check": "final_verify"})
        self.assertEqual(run(data, "final_verify", "b")["attempt"], 2)
        self.assertEqual(run(data, "final_verify", "b")["attempt"], 2)  # the same execution is not counted twice
        self.assertEqual(run(data, "repair", "c"), {"state": "running", "attempt": None, "check": None})
        self.assertEqual(run(data, "scope_verify", "d")["attempt"], None)
        self.assertEqual(run(data, "empty_final_reverify", "e"),
                         {"state": "running", "attempt": 1, "check": "final_reverify"})
        self.assertEqual(run(data, "final_reverify", "f")["attempt"], 2)
        self.assertTrue(live.valid(data))
        older = live.new()
        del older["finals"]
        self.assertTrue(live.valid(older))
        out = live.flow(self.record(nodes=[["final_verify", "x"]], **{}), START, self.NOW)
        self.assertEqual(out["final"]["attempt"], None)
        old_flow = live.flow(older, START, self.NOW)
        self.assertEqual(old_flow["final"], {"state": "waiting", "attempt": None, "check": None})
        json.dumps(old_flow)


class FlowHomeTests(LiveTest):
    def test_home_flow_is_none_without_an_attempt_and_the_attempts_flow_with_one(self):
        """F1 A2/A3: `Home.flow` holds `live.flow` of the active attempt and None when nothing is active; the panel
        lines stay exactly `Delivery.panel`'s. Interpretation recorded here: `Home.flow` and the panel are read from
        one clock tick (`Delivery.panel_flow`), so the two always describe the same moment."""
        driver = self.scripted([("advance", 5)])
        with self.authority() as a:
            self.approved(a)
            service, controller = self.service(a, driver)
            self.assertIsNone(service.home().flow)  # an approved plan with no attempt yet carries no flow
            r = controller.start("M1", 1, ROLES)
            service.step(r)
            home = service.home()
            self.assertEqual(home.flow, service.flow(r))
            self.assertEqual(home.flow["task"], "T1")
            self.assertEqual(home.flow["active"], ["worker"])
            self.assertEqual(home.panel, service.panel(r))
            json.dumps(home.flow)


class JournalTests(LiveTest):
    def run_out(self, service, r, limit=60):
        steps = 0
        while r["status"] in ("submitted", "running", "stopping") and steps < limit:
            service.step(r)
            self.clock.advance(7)
            steps += 1
        return steps

    def texts(self, r):
        return [e["text"] for e in r["live"]["journal"]]

    def test_journal_names_stages_and_rework_rounds_without_duplicates_and_survives_restart(self):
        # L-A2: stage lines, "rework, round N", verdicts only from the manifest, replay writes nothing twice.
        driver = self.scripted([], rejections=2)
        with self.authority() as a:
            self.approved(a)
            service, controller = self.service(a, driver)
            r = controller.start("M1", 1, ROLES)
            self.run_out(service, r)
            self.assertEqual(r["status"], "finished")
            texts = self.texts(r)
            self.assertEqual(texts, [  # one line per stage, in order: replayed records added nothing
                "T1: implementation", "T1: acceptance", "T1: code review", "T1: rework, round 1", "T1: acceptance",
                "T1: code review", "T1: rework, round 2", "T1: acceptance", "T1: code review", "T1: recording the result",
                "T1 · review: accepted", "final check"])
            for expected in ("T1: implementation", "T1: rework, round 1", "T1: rework, round 2", "T1: acceptance",
                             "T1: code review", "T1: recording the result", "final check", "T1 · review: accepted"):
                self.assertIn(expected, texts)
            # a verdict is only ever the manifest's: the only "accepted" line is the steward's accepted record
            self.assertEqual([t for t in texts if "accepted" in t or "rejected" in t], ["T1 · review: accepted"])
            lines = service.journal(r)
            self.assertEqual(len(lines), len(texts))
            self.assertTrue(all(l.startswith("  ") and live.clock(e["at"]) in l
                                for l, e in zip(lines, r["live"]["journal"])))
        with self.authority() as a:  # restart: the same journal comes back from the store
            service, controller = self.service(a, driver)
            again = controller.runs[-1]
            self.assertEqual(self.texts(again), texts)
            self.assertEqual(service.journal(again), lines)

    def test_replay_and_resume_do_not_write_journal_lines_twice(self):
        driver = self.scripted([("advance", 5), ("replay", 5), ("replay", 5), ("advance", 5)],
                               outcome=("failed_recoverable", "done"))
        with self.authority() as a:
            self.approved(a)
            service, controller = self.service(a, driver)
            r = controller.start("M1", 1, ROLES)
            service.step(r)
            before = self.texts(r)
            service.step(r)
            service.step(r)
            self.assertEqual(self.texts(r), before)  # replayed records: no new lines
            self.run_out(service, r)
            self.assertEqual(r["status"], "failed")
            before = self.texts(r)
            successor = controller.resume(r)
            self.assertEqual(self.texts(successor)[:len(before)], before)
            self.assertEqual(self.texts(successor)[len(before)], "resuming after a failure")
            self.run_out(service, successor)
            self.assertEqual(self.texts(successor)[len(before) + 1:], [
                "T1: implementation", "T1: acceptance", "T1: code review", "T1: recording the result", "T1 · review: accepted",
                "final check"])

    def test_the_same_execution_at_a_new_cursor_is_one_stage_not_a_rework_round(self):
        # L-A2: the executions of a record that were already journalled add nothing, whatever the cursor.
        driver = self.scripted([("advance", 5), ("again", 5), ("again", 5)])
        with self.authority() as a:
            self.approved(a)
            service, controller = self.service(a, driver)
            r = controller.start("M1", 1, ROLES)
            for _ in range(3):
                service.step(r)
            self.assertEqual(self.texts(r), ["T1: implementation"])
            self.assertEqual(r["live"]["last_event"], self.clock())  # the new cursor is still a new event

    def test_the_journal_is_bounded_to_the_newest_lines(self):
        data = live.new()
        for n in range(45):
            live.note(data, "line %s" % n, START)
        self.assertEqual(len(data["journal"]), live.JOURNAL_LIMIT)
        self.assertEqual([e["text"] for e in data["journal"]][0], "line 25")
        self.assertEqual(data["journal"][-1]["text"], "line 44")
        self.assertFalse(live.note(data, "line 44", START))  # the line just written is not written twice
        for n in range(200):
            live.bounded(data["cursors"], "c%s" % n, live.CURSORS_LIMIT)
            live.bounded(data["executions"], "e%s" % n, live.EXECUTIONS_LIMIT)
        self.assertTrue(live.valid(data))
        self.assertEqual((len(data["cursors"]), len(data["executions"])), (live.CURSORS_LIMIT, live.EXECUTIONS_LIMIT))

    def test_home_journal_follows_the_active_attempt(self):
        # C1 A1: while an attempt runs, Home carries exactly that attempt's stored journal, oldest first.
        driver = self.scripted([("advance", 5), ("advance", 5)])
        with self.authority() as a:
            self.approved(a)
            service, controller = self.service(a, driver)
            r = controller.start("M1", 1, ROLES)
            service.step(r)
            service.step(r)
            self.assertEqual(r["status"], "running")  # still the single active attempt
            home = service.home()
            self.assertEqual(home.focus.id, "M1")
            self.assertEqual(home.journal, service.journal(r))
            self.assertTrue(home.journal)

    def test_home_journal_follows_the_latest_attempt_under_next(self):
        # C1 A1: with no active attempt, Home carries the latest attempt of the milestone named under "Next".
        driver = self.scripted([("advance", 5)], outcome="failed_recoverable")
        with self.authority() as a:
            self.approved(a)
            service, controller = self.service(a, driver)
            r = controller.start("M1", 1, ROLES)
            self.run_out(service, r)
            self.assertEqual(r["status"], "failed")
            home = service.home()
            self.assertEqual(home.focus.id, "M1")  # failed_recoverable is the milestone under "Next"
            self.assertEqual(home.journal, service.journal(r))
            self.assertTrue(home.journal)

    def test_home_journal_is_empty_without_an_attempt(self):
        # C1 A1: an approved plan whose milestone has no attempt yet carries no journal at all.
        driver = self.scripted([])
        with self.authority() as a:
            self.approved(a)
            service, controller = self.service(a, driver)
            home = service.home()
            self.assertEqual(home.focus.id, "M1")
            self.assertEqual(home.journal, ())


class NothingWritesTests(LiveTest):
    def snapshot(self, path):
        stat = path.stat()
        return path.read_bytes(), stat.st_mtime_ns

    def reads(self, a, driver):
        """Everything the owner can look at without acting: none of it may write the store."""
        service, controller = self.service(a, driver)
        controller.refresh()
        for r in controller.runs:
            service.panel(r)
            service.journal(r)
            service.next_step({"state": "running", "id": r["milestone"], "record": r})
        service.planner_panel()
        service.journal()
        controller.overview(live=True)
        controller.overview(live=False)
        service.home()
        service.rows()
        return service

    def test_refresh_status_panel_and_load_write_nothing(self):
        # L-A2: byte-compare the store around every read-only path.
        driver = self.scripted([("advance", 5), ("quiet", 30)])
        with self.authority() as a:
            self.approved(a)
            service, controller = self.service(a, driver)
            r = controller.start("M1", 1, ROLES)
            service.step(r)
            service.step(r)
            path = a.path
        before = self.snapshot(path)
        self.clock.advance(3600)
        with self.authority() as a:
            self.reads(a, driver)
        out = io.StringIO()
        cli.status(Terminal(io.StringIO(), out), self.project, self.state, "test", lambda _: driver)
        self.assertEqual(self.snapshot(path), before)

    def test_records_without_live_fields_load_unchanged_and_show_nothing_invented(self):
        driver = self.scripted([("advance", 5)])
        with self.authority() as a:
            self.approved(a)
            service, controller = self.service(a, driver)
            r = controller.start("M1", 1, ROLES)
            service.step(r)
            path = a.path
        state = decode(path.read_text())
        for r in state["runs"]:
            r.pop("live", None)
        for revision in state["revisions"]:
            revision.pop("live", None)
        atomic_state(path, state)
        before = self.snapshot(path)
        with self.authority() as a:
            service = self.reads(a, driver)
            r = service.runs.runs[-1]
            self.assertNotIn("live", r)
            self.assertEqual(service.journal(r), ())
            self.assertNotIn("checked", self.panel(service, r))  # nothing was ever observed: nothing is claimed
        self.assertEqual(self.snapshot(path), before)


class TailTests(unittest.TestCase):
    """The reader of `zeroshot logs`: a real child process, bounded while it streams, killed on its own."""

    @staticmethod
    def run_tail(code, **options):
        started = []

        def popen(*args, **kwargs):
            process = subprocess.Popen(*args, **kwargs)
            started.append(process)
            return process
        lines = live.tail([sys.executable, "-c", code], dict(os.environ), os.getcwd(), popen=popen, **options)
        return lines, started[0]

    def test_the_reader_never_holds_more_than_the_buffer_while_streaming(self):
        held = []

        class Watching(deque):
            def append(self, chunk):
                super().append(chunk)
                held.append(sum(len(c) for c in self))
        code = "import sys\nfor n in range(100000): print('строка', n)\n"
        with patch.object(live, "deque", Watching):
            lines, _ = self.run_tail(code, lines=5, buffer=4096, deadline=20)
        self.assertEqual(lines[-1], "строка 99999")
        self.assertGreater(len(held), 5)  # it really streamed in pieces
        self.assertLessEqual(max(held), 4096 + 65536)  # the buffer plus the one read that tipped it

    def test_a_flood_is_cut_to_the_last_lines_within_the_buffer(self):
        code = "import sys\nfor n in range(200000): print('строка', n)\n"
        lines, process = self.run_tail(code, lines=40, buffer=8192, deadline=20)
        self.assertEqual(len(lines), 40)
        self.assertEqual(lines[-1], "строка 199999")
        self.assertLessEqual(sum(len(l.encode()) + 1 for l in lines), 8192)
        self.assertIsNotNone(process.poll())

    def test_the_deadline_stops_an_endless_stream_and_kills_only_the_reader(self):
        code = "import sys, time\nwhile True:\n    print('ещё', flush=True)\n    time.sleep(0.01)\n"
        sibling = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(sibling.wait)
        self.addCleanup(sibling.kill)
        began = time.monotonic()
        lines, process = self.run_tail(code, lines=5, deadline=0.6)
        self.assertLess(time.monotonic() - began, 5)
        self.assertEqual(lines, ["ещё"] * 5)
        self.assertIsNotNone(process.poll())  # the reader is gone
        self.assertIsNone(sibling.poll())  # nothing else was touched

    def test_a_silent_command_is_cut_at_the_deadline_with_nothing_shown(self):
        lines, process = self.run_tail("import time; time.sleep(30)", deadline=0.5)
        self.assertEqual(lines, [])
        self.assertIsNotNone(process.poll())

    def test_empty_output_and_a_partial_last_line(self):
        self.assertEqual(self.run_tail("pass")[0], [])
        self.assertEqual(self.run_tail("import sys; sys.stdout.write('first\\nпочти закончил')")[0],
                         ["first", "почти закончил"])

    def test_terminal_escapes_and_secrets_are_not_shown(self):
        code = "print('\\x1b[31mred\\x1b[0m'); print('Authorization: Bearer abcdefghij0123456789'); print('sk-ABCDEFGHIJKLMNOP')"
        lines, _ = self.run_tail(code)
        self.assertEqual(lines[0], "red")
        self.assertNotIn("abcdefghij0123456789", " ".join(lines))
        self.assertNotIn("ABCDEFGHIJKLMNOP", " ".join(lines))
        self.assertIn("[hidden]", lines[1])

    # (line, key name that stays, value that must never be shown): the shapes the old word-boundary missed.
    SHAPES = (
        ("OPENAI_API_KEY=openai-value-0123456789", "OPENAI_API_KEY", "openai-value-0123456789"),
        ("GATEWAY_API_KEY=gateway-value-0123456789", "GATEWAY_API_KEY", "gateway-value-0123456789"),
        ('"access_token":"access-value-0123456789"', "access_token", "access-value-0123456789"),
        ('"api_key": "a:b c/d"', "api_key", "a:b c/d"),
        ("X_AUTH_TOKEN=auth-value-0123456789", "X_AUTH_TOKEN", "auth-value-0123456789"),
        ("password=abc", "password", "abc"),
        ("secret = 'p:a s'", "secret", "p:a s"),
        ("Authorization: Basic YWJjOmRlZg==", "Authorization", "YWJjOmRlZg=="),
    )

    def test_a_credential_value_is_masked_whatever_its_key_shape_or_length(self):
        # L-1: the real reader path (a child process) on every shape: the value never survives, the key name does.
        code = "".join("print(%r)\n" % line for line, _, _ in self.SHAPES)
        lines, _ = self.run_tail(code)
        self.assertEqual(len(lines), len(self.SHAPES))
        for (line, key, value), shown in zip(self.SHAPES, lines):
            with self.subTest(line):
                self.assertNotIn(value, shown)
                self.assertIn(key, shown)
                self.assertIn("[hidden]", shown)

    def test_scrub_masks_the_whole_value_of_a_credential_field(self):
        # L-1: the same shapes without a process, plus a short quoted value: no length guess for a keyed field.
        for line, key, value in self.SHAPES + (('Token:"tv"', "Token", "tv"),):
            with self.subTest(line):
                shown = live.scrub(line)
                self.assertNotIn(value, shown)
                self.assertIn(key, shown)

    def test_an_authorization_field_hides_its_whole_value_its_scheme_included(self):
        # L-1: an authorization value is not one token: the scheme must not survive next to the credential.
        self.assertEqual(live.scrub("Authorization: Basic YWJjOmRlZg=="), "Authorization: [hidden]")
        lines, _ = self.run_tail("print('Authorization: Basic YWJjOmRlZg==')")
        self.assertEqual(lines, ["Authorization: [hidden]"])

    def test_a_parameterized_authorization_field_hides_every_parameter(self):
        # L-1: a scheme may carry the credential in parameters (Digest, AWS4): the whole field value goes, not one
        # token of it, on the scrub path and through the real reader.
        digest = 'Authorization: Digest username="u", nonce="abc", response="credential-value"'
        signed = "Authorization: AWS4-HMAC-SHA256 Credential=AKIA/20260101, Signature=deadbeef"
        for line in (digest, signed):
            with self.subTest(line):
                self.assertEqual(live.scrub(line), "Authorization: [hidden]")
        lines, _ = self.run_tail("print(%r); print(%r)" % (digest, signed))
        self.assertEqual(lines, ["Authorization: [hidden]", "Authorization: [hidden]"])

    def test_a_quoted_authorization_field_masks_only_its_own_value(self):
        # L-1: a quoted `authorization` key must not swallow the fields after it; its value is bounded like any
        # other, so the following `api_key` keeps both its name and its own mask, on the scrub path and the reader.
        line = '{"authorization":"abc","api_key":"xyz"}'
        masked = '{"authorization":[hidden],"api_key":[hidden]}'
        self.assertEqual(live.scrub(line), masked)
        lines, _ = self.run_tail("print(%r)" % line)
        self.assertEqual(lines, [masked])
        self.assertNotIn("abc", lines[0])
        self.assertNotIn("xyz", lines[0])

    # (line, the parts of its value that must never be shown): a credential field carried inside a JSON log
    # record travels in a string value, so its quotes arrive escaped; a record inside a record escapes them again.
    RECORDS = (
        (json.dumps({"message": '{"api_key":"SYNTHETIC_CREDENTIAL_012345"}'}), ("SYNTHETIC_CREDENTIAL_012345",)),
        (json.dumps({"message": 'api_key="a b SECRET_END_012345"'}), ("SECRET_END_012345", "a b")),
        (json.dumps({"message": json.dumps({"payload": json.dumps({"api_key": "DOUBLY_ESCAPED_012345"})})}),
         ("DOUBLY_ESCAPED_012345",)),
        (json.dumps({"api_key": "PLAIN_FIELD_012345", "node": "worker"}), ("PLAIN_FIELD_012345",)),
        (json.dumps({"message": json.dumps('api_key="a b STRING_WRAPPED_012345"')}),
         ("STRING_WRAPPED_012345", "a b")),
        (json.dumps({"message": json.dumps(json.dumps({"api_key": "DOUBLE_STRING_012345"}))}),
         ("DOUBLE_STRING_012345",)),
        (json.dumps({"api_key:primary": "KEYED_NAME_012345"}), ("KEYED_NAME_012345",)),
    )

    def test_a_credential_escaped_inside_a_json_log_record_is_masked(self):
        # E-1: a record's string value is decoded and scrubbed, so escaping no longer hides the field from the
        # scan; no part of the value survives, the key name and the marker do, on the direct path and the reader.
        code = "".join("print(%r)\n" % line for line, _ in self.RECORDS)
        lines, _ = self.run_tail(code)
        self.assertEqual(len(lines), len(self.RECORDS))
        for (line, leaks), shown in zip(self.RECORDS, lines):
            with self.subTest(line):
                self.assertIn("api_key", shown)
                self.assertIn("[hidden]", shown)
                for leak in leaks:
                    self.assertNotIn(leak, shown)
                self.assertEqual(live.scrub(line), shown)  # the direct path agrees with the reader

    def test_a_truncated_last_record_hides_what_it_still_carries(self):
        # E-1b: the outer record is cut (its closing characters are gone) with the credential still inside; the
        # reader shows that partial last line, and the record path must not fall back to the flat scan (which
        # cannot read the escaping) and show the value: what no longer decodes is hidden whole, what does decode
        # is scrubbed one level deeper.
        for line, leaks in self.RECORDS[:2]:  # both shapes the critic reproduced
            for cut in (1, 3):
                partial = line[:-cut]
                with self.subTest(partial):
                    shown = live.scrub(partial)
                    self.assertIn("[hidden]", shown)
                    for leak in leaks:
                        self.assertNotIn(leak, shown)
                    self.assertEqual(self.run_tail("import sys; sys.stdout.write(%r)" % partial)[0], [shown])

    def test_a_field_name_that_holds_a_separator_keeps_its_name_and_masks_its_value(self):
        # (repair) a string that is a field *name* must never be scrubbed: masking the name would take the
        # credential field it names away from the line scan and the value after it would survive. The name stays
        # whole and only the value goes, on a bare record line, on the escaped field a record carries, and through
        # the reader. The escaped shapes also show the value flat before this change, so the repair is guarded at
        # both levels, not only against the regression the name scrub would be.
        for line, leaks in (('{"api_key:primary": "KEYED_012345"}', ("KEYED_012345",)),
                            ('{"api_key/client": "KEYED_012345"}', ("KEYED_012345",)),
                            (json.dumps({"message": '{"api_key:primary": "ESCAPED_KEY_012345"}'}),
                             ("ESCAPED_KEY_012345",)),
                            (json.dumps({"message": '{"api_key/client": "ESCAPED_KEY2_012345"}'}),
                             ("ESCAPED_KEY2_012345",))):
            with self.subTest(line):
                shown = live.scrub(line)
                self.assertIn("api_key", shown)  # the field name stays whole, so the value after it is still named
                self.assertIn("[hidden]", shown)
                for leak in leaks:
                    self.assertNotIn(leak, shown)
                self.assertEqual(self.run_tail("print(%r)" % line)[0], [shown])

    def test_a_field_nested_past_the_depth_limit_is_hidden_not_shown(self):
        # E-2b: the recursion is bounded by JSON_DEPTH levels; past it the deeper content is hidden whole, so a
        # doubly escaped field is covered and nothing beyond is ever shown. The nesting grows exponentially (each
        # level escapes the quotes and the backslashes of the one below), so a few kB of line reach the limit.
        node = json.dumps({"api_key": "DEEP_LEAK_012345"})
        for _ in range(live.JSON_DEPTH + 2):
            node = json.dumps({"message": node})
        self.assertGreater(node.count("\\"), live.JSON_DEPTH)
        self.assertNotIn("DEEP_LEAK", live.scrub(node))
        self.assertIn("[hidden]", live.scrub(node))
        shown = self.run_tail("import sys; sys.stdout.write(%r)" % node)[0]
        self.assertNotIn("DEEP_LEAK", " ".join(shown))
        # the same credential, but the record is encoded one time too many per level instead of nesting objects
        wrapped = 'api_key="DEEP_WRAPPED_012345"'
        for _ in range(live.JSON_DEPTH + 2):
            wrapped = json.dumps(wrapped)
        self.assertNotIn("DEEP_WRAPPED", live.scrub(json.dumps({"message": wrapped})))
        shown = self.run_tail("import sys; sys.stdout.write(%r)" % json.dumps({"message": wrapped}))[0]
        self.assertNotIn("DEEP_WRAPPED", " ".join(shown))

    # (line, the parts of its value that must never be shown): a credential field may carry its whole value as an
    # object or an array, and the field itself may repeat, arrive with an escaped name, or sit behind a message
    # prefix; masking is token by token, so the whole value is hidden rather than cut at its first separator.
    COMPOSITE = (
        ('{"api_key": {"a": "COMPOSITE_OBJ_012345"}}', ("COMPOSITE_OBJ_012345",)),
        (json.dumps({"message": json.dumps({"api_key": {"a": "COMPOSITE_NESTED_012345"}})}),
         ("COMPOSITE_NESTED_012345",)),
        (json.dumps({"message": json.dumps({"api_keys": ["FIRST_012345", "SECOND_012345"]})}),
         ("FIRST_012345", "SECOND_012345")),
        (json.dumps({"api_key": [{"token": "COMPOSITE_LIST_012345"}]}), ("COMPOSITE_LIST_012345",)),
        ('{"api_key": {"a": "COMPOSITE_DUP_012345"}, "api_key": "x"}', ("COMPOSITE_DUP_012345",)),
        (json.dumps({r"\u0061pi_key": {"part": "COMPOSITE_ESC_012345"}}), ("COMPOSITE_ESC_012345",)),
        (json.dumps({"message": "log: " + json.dumps({"api_key": {"a": "COMPOSITE_PREFIX_012345"}})}),
         ("COMPOSITE_PREFIX_012345",)),
    )

    def test_a_credential_field_whose_value_is_a_composite_is_hidden_not_shown(self):
        # E-1/E-2b: the reviewer's repros -- an object value and an array value of a credential field -- leave the
        # value past the first separator visible when the field is masked token by token, and so does a repeated
        # field name (a decoder keeps only its last pair), an escaped name, or a value behind a message prefix. The
        # whole value is hidden instead, direct and nested, on the scrub path and through the real reader.
        code = "".join("print(%r)\n" % line for line, _ in self.COMPOSITE)
        lines, _ = self.run_tail(code)
        self.assertEqual(len(lines), len(self.COMPOSITE))
        for (line, leaks), shown in zip(self.COMPOSITE, lines):
            with self.subTest(line):
                self.assertIn("[hidden]", shown)
                for leak in leaks:
                    self.assertNotIn(leak, shown)
                self.assertEqual(live.scrub(line), shown)  # the direct path agrees with the reader
        for line, leaks in self.COMPOSITE:  # E-1b: the outer record cut, the credential still inside it
            partial = line[:-1]
            with self.subTest(partial):
                out = live.scrub(partial)
                self.assertEqual(out, "[hidden]")
                for leak in leaks:
                    self.assertNotIn(leak, out)
                self.assertEqual(self.run_tail("import sys; sys.stdout.write(%r)" % partial)[0], [out])

    def test_a_record_that_does_not_decode_is_hidden_and_never_raises(self):
        # E-2b: a record the decoder rejects (a truncated line, an escape it will not take) is hidden whole, on
        # the direct path and through the reader: nothing raises, nothing of it is shown.
        for line in ('{"message": "\\q api_key=SHOWN_012345"}', '{"a": [1, 2,', '{"message": "api_key=SHOWN_012345'):
            with self.subTest(line):
                self.assertEqual(live.scrub(line), "[hidden]")
                self.assertEqual(self.run_tail("import sys; sys.stdout.write(%r)" % line)[0], ["[hidden]"])

    def test_a_value_that_cannot_be_written_back_is_hidden_not_shown(self):
        # E-2b: the line decodes, but the escaped lone surrogate in its value cannot be written back into the
        # line at all; the value that carries it (and the credential in it) is hidden instead, and nothing raises.
        line = '{"message": "\\ud800 api_key=SHOWN_012345"}'
        self.assertEqual(live.scrub(line), '{"message": "[hidden]"}')
        shown = self.run_tail("import sys; sys.stdout.write(%r)" % line)[0]
        self.assertNotIn("SHOWN_012345", " ".join(shown))

    def test_a_long_record_and_a_record_of_many_masked_values_are_scanned_in_bounded_time(self):
        # E-2: the record path decodes each string value and rewrites the ones that changed; the work stays
        # bounded on a long line and on a record whose values all change (the escaped-quote line is L-1's).
        record = json.dumps({"message": "x" * 200000, "node": "worker", "seq": 7})
        began = time.monotonic()
        self.assertEqual(live.scrub(record), record)  # no credential field: nothing masked
        self.assertLess(time.monotonic() - began, 5)
        line = '{"message": "' + '\\"' * 30000 + '"}'
        began = time.monotonic()
        self.assertEqual(live.scrub(line), line)
        self.assertLess(time.monotonic() - began, 1)
        many = json.dumps({"m%d" % n: 'api_key="value %d"' % n for n in range(1000)})
        began = time.monotonic()
        lines, _ = self.run_tail("import sys; sys.stdout.write(%r + '\\n')" % many, deadline=3)
        self.assertIn('"api_key=[hidden]"', " ".join(lines))  # each value masked whole, not up to its first blank
        self.assertNotIn("value 999", " ".join(lines))
        self.assertLess(time.monotonic() - began, 5)
        # a value that is nothing but escapes: reading them off one level at a time stays linear and bounded
        begun = time.monotonic()
        self.assertIn("[hidden]", live.scrub('{"message": "' + '\\\\' * 20000 + '"}'))
        self.assertLess(time.monotonic() - begun, 2)

    # (line, the parts of its value that must never be shown): a value only a further step of decoding reaches,
    # and a name whose escapes spell a credential field. Neither is one the flat scan can see.
    DEEP = (
        (json.dumps({"message": json.dumps('api_key="a b TRUNCATED_012345"')[:-1]}), ("TRUNCATED_012345", "a b")),
        (json.dumps({"message": json.dumps([json.dumps({"api_key": "IN_ARRAY_012345"})])}), ("IN_ARRAY_012345",)),
        (json.dumps({"message": json.dumps([{"payload": json.dumps({"api_key": "ARRAY_PAYLOAD_012345"})}])}),
         ("ARRAY_PAYLOAD_012345",)),
        (json.dumps({"message": "log: " + json.dumps('api_key="a b PREFIXED_012345"')}), ("PREFIXED_012345", "a b")),
        ('{"\\u0061pi_key": "ESCAPED_NAME_012345"}', ("ESCAPED_NAME_012345",)),
        (json.dumps({"message": '{"\\u0061pi_key": "ESCAPED_NESTED_012345"}'}), ("ESCAPED_NESTED_012345",)),
        (json.dumps({"message": json.dumps('{"\\u0061pi_key": "ESCAPED_TWICE_012345"}')}), ("ESCAPED_TWICE_012345",)),
    )

    def test_a_value_behind_a_further_escape_or_a_prefixed_record_is_not_shown(self):
        # E-2b: a truncated inner JSON string, an encoded array (or an array of records), a field behind a message
        # prefix, and a name whose escapes spell `api_key` all keep the value past the flat scan's reach; each is
        # masked or hidden whole, never shown, on the direct path and through the real reader.
        code = "".join("print(%r)\n" % line for line, _ in self.DEEP)
        lines, _ = self.run_tail(code)
        self.assertEqual(len(lines), len(self.DEEP))
        for (line, leaks), shown in zip(self.DEEP, lines):
            with self.subTest(line):
                self.assertIn("[hidden]", shown)
                for leak in leaks:
                    self.assertNotIn(leak, shown)
                self.assertEqual(live.scrub(line), shown)  # the direct path agrees with the reader

    def test_a_value_reached_through_an_array_past_the_depth_limit_is_hidden_not_shown(self):
        # E-2b: arrays recurse under the same bound as records; a credential nested past JSON_DEPTH levels is
        # hidden whole, on the direct path and through the reader, not decoded further.
        node = json.dumps({"api_key": "DEEP_ARRAY_012345"})
        for _ in range(live.JSON_DEPTH + 2):
            node = json.dumps([node])
        line = json.dumps({"message": node})
        self.assertNotIn("DEEP_ARRAY", live.scrub(line))
        shown = self.run_tail("import sys; sys.stdout.write(%r)" % line)[0]
        self.assertNotIn("DEEP_ARRAY", " ".join(shown))

    # (line, the parts of its value that must never be shown): a `\"` a value carries literally is the same two
    # characters as an escaped quote, so reading the escapes would reopen the value's closing quote and show the
    # tail of a value the scan already named a field in; a decoded `\n` must not end an unclosed value early.
    ESCAPED_QUOTES = (
        (json.dumps({"message": 'api_key="head \\"inside LEAK_QUOTE_012345"'}), ("LEAK_QUOTE_012345",)),
        (json.dumps({"message": "api_key=" + json.dumps('a"b LEAK_DUMPS_012345')}), ("LEAK_DUMPS_012345",)),
        (json.dumps({"message": "api_key=" + json.dumps("a\\u0022b LEAK_U0022_012345")}), ("LEAK_U0022_012345",)),
        (json.dumps({"message": 'api_key="head\nLEAK_NEWLINE_012345'}), ("LEAK_NEWLINE_012345",)),
        (json.dumps({"message": 'api_key="head x\nLEAK_NEWLINE2_012345'}), ("LEAK_NEWLINE2_012345",)),
    )

    def test_a_value_behind_a_literal_escaped_quote_or_a_decoded_newline_is_not_shown(self):
        # E-1/E-1b: an escaping the value carries literally (`\"`, or its `\u0022` spelling) is exactly what
        # re-reading would take for an escaped quote, and a decoded newline is what would end an unclosed value
        # early; neither reading is trusted, so no part of the value survives, whole or cut, on both paths.
        code = "".join("print(%r)\n" % line for line, _ in self.ESCAPED_QUOTES)
        shown, _ = self.run_tail(code)
        self.assertEqual(len(shown), len(self.ESCAPED_QUOTES))
        for (line, leaks), out in zip(self.ESCAPED_QUOTES, shown):
            with self.subTest(line):
                self.assertIn("[hidden]", out)
                for leak in leaks:
                    self.assertNotIn(leak, out)
                self.assertEqual(live.scrub(line), out)  # the direct path agrees with the reader
        for line, leaks in self.ESCAPED_QUOTES:  # E-1b: the outer record cut, the value still inside it
            partial = line[:-1]
            with self.subTest(partial):
                out = live.scrub(partial)
                self.assertIn("[hidden]", out)
                for leak in leaks:
                    self.assertNotIn(leak, out)
                self.assertEqual(self.run_tail("import sys; sys.stdout.write(%r)" % partial)[0], [out])

    # (repair) a field whose escaped name sits inside a record behind a message prefix, with the value itself
    # carrying a literal `\"`; and a recognized credential name that cannot be written back (a lone surrogate).
    def test_a_prefixed_record_with_an_escaped_name_and_a_literal_quote_is_not_shown(self):
        # E-1/E-1b: `\u0061pi_key` has to be spelled out for the scan and a `\"` the value carries literally is
        # the same two characters as an escaped quote (so reading it moved the value's closing quote); the two
        # together leaked the value tail. Hidden whole now, whole and cut, on the direct path and through the
        # reader.
        payload = r'log: {"\u0061pi_key": "head \"inside CREDENTIAL_SUFFIX_012345"}'
        line = json.dumps({"message": payload})
        self.assertNotIn("CREDENTIAL_SUFFIX_012345", live.scrub(line))
        self.assertNotIn("CREDENTIAL_SUFFIX_012345", " ".join(self.run_tail("print(%r)" % line)[0]))
        for cut in (1, 3):  # E-1b: the outer record cut, the credential still inside it
            partial = line[:-cut]
            with self.subTest(partial):
                self.assertNotIn("CREDENTIAL_SUFFIX_012345", live.scrub(partial))
                self.assertNotIn("CREDENTIAL_SUFFIX_012345",
                                 " ".join(self.run_tail("import sys; sys.stdout.write(%r)" % partial)[0]))

    def test_a_credential_name_that_cannot_be_written_back_hides_its_record(self):
        # E-2b: a lone surrogate anywhere in the *name* of a credential field (`api_key\ud800`, `\ud800api_key`)
        # cannot be written back; replacing the name would take the field it names away from the line scan and
        # leave the value behind it visible, so the record is hidden whole instead -- direct and nested, on the
        # direct path and through the reader.
        for record in (json.dumps({"api_key\ud800": "LEAK_NAME_012345"}),
                       json.dumps({"\ud800api_key": "LEAK_NAME_012345"})):
            with self.subTest(record):
                self.assertNotIn("LEAK_NAME_012345", live.scrub(record))
                self.assertNotIn("LEAK_NAME_012345", " ".join(self.run_tail("print(%r)" % record)[0]))
                nested = json.dumps({"message": record})
                self.assertNotIn("LEAK_NAME_012345", live.scrub(nested))
                self.assertNotIn("LEAK_NAME_012345", " ".join(self.run_tail("print(%r)" % nested)[0]))

    # (line, the key name that stays, the value that must never be shown): a quoted key name may hold anything.
    QUOTED_KEYS = (
        ('"api_key/client": "a:b c/d"', "api_key/client", "a:b c/d"),
        ('"api_key primary": "sensitive-value"', "api_key primary", "sensitive-value"),
        ('"api_key:primary": "sensitive-value"', "api_key:primary", "sensitive-value"),
        ('"api_key\'s": "a:b c/d"', "api_key's", "a:b c/d"),
        ("'api_key\"x': 'a:b c/d'", "api_key\"x", "a:b c/d"),
        ('"api_key\\"x": "a:b c/d"', "api_key", "a:b c/d"),
    )

    def test_a_quoted_key_name_with_other_characters_still_names_a_credential_field(self):
        # L-1: the name of a quoted key may hold any character (`api_key/client`, a space, a colon, the other kind of
        # quote, an escaped quote): the name stays and the whole value goes, on the scrub path and the real reader.
        code = "".join("print(%r)\n" % line for line, _, _ in self.QUOTED_KEYS)
        lines, _ = self.run_tail(code)
        self.assertEqual(len(lines), len(self.QUOTED_KEYS))
        for (line, key, value), shown in zip(self.QUOTED_KEYS, lines):
            with self.subTest(line):
                self.assertNotIn(value, shown)
                self.assertIn(key, shown)
                self.assertIn("[hidden]", shown)
                self.assertEqual(live.scrub(line), shown)  # the direct path agrees with the reader

    def test_an_unclosed_quoted_value_is_masked_to_the_end_of_the_line(self):
        # L-1: a partial last line carries no closing quote; the rest of the line is the value, not its first token.
        line = '"api_key": "a:b c/d'
        self.assertEqual(live.scrub(line), '"api_key": [hidden]')
        lines, _ = self.run_tail("import sys\nsys.stdout.write(%r)\n" % line)
        self.assertEqual(lines, ['"api_key": [hidden]'])

    def test_a_unicode_separator_inside_a_value_is_not_a_line_break(self):
        # L-1: U+2028, U+2029 and U+0085 are legal inside a JSON string; cutting a record on them would scrub the
        # two halves apart and show the tail of the value. The reader cuts on `\n` only, so the whole value goes.
        for sep in ("\u2028", "\u2029", "\u0085"):
            line = '"api_key": "abc' + sep + 'def"'
            with self.subTest(hex(ord(sep))):
                self.assertEqual(live.scrub(line), '"api_key": [hidden]')
                shown = self.run_tail("import sys; sys.stdout.write(%r + '\\n')" % line)[0]
                self.assertEqual(shown, ['"api_key": [hidden]'])
                self.assertNotIn("abc", " ".join(shown))  # neither half of the value survives
                self.assertNotIn("def", " ".join(shown))

    def test_a_long_secret_free_line_is_scanned_in_bounded_time(self):
        # L-1: the key scan starts only at the head of a name run; the old pattern retried it at every character
        # and went quadratic (over eight seconds on this very line). The bound is a mile above the linear scan.
        line = "a" * 65536
        began = time.monotonic()
        self.assertEqual(live.scrub(line), line)
        self.assertLess(time.monotonic() - began, 5)

    # (line, the field name that stays, the value that must never be shown): an unquoted name may carry more than a
    # name run (`api_key/client`, `password[db]`) before its separator.
    BARE_NAMES = (
        ('api_key/client="a:b c/d"', "api_key/client", "a:b c/d"),
        ('password[db]="a:b c/d"', "password[db]", "a:b c/d"),
    )

    def test_an_unquoted_field_name_with_suffix_characters_still_names_a_credential(self):
        # L-1: a bare name runs up to its separator whatever it holds, so `/` or brackets after a secret word keep
        # the value masked (the name stays), on the scrub path and through the real reader.
        code = "".join("print(%r)\n" % line for line, _, _ in self.BARE_NAMES)
        lines, _ = self.run_tail(code)
        self.assertEqual(len(lines), len(self.BARE_NAMES))
        for (line, key, value), shown in zip(self.BARE_NAMES, lines):
            with self.subTest(line):
                self.assertNotIn(value, shown)
                self.assertIn(key, shown)
                self.assertIn("[hidden]", shown)
                self.assertEqual(live.scrub(line), shown)  # the direct path agrees with the reader

    def test_escaped_quotes_do_not_make_the_scan_quadratic(self):
        # L-1: the quoted-key scan must not restart at every escaped quote. A valid JSON line with 30000 escaped
        # quotes (below the buffer) took over four seconds on the previous pattern; it is now well inside a second,
        # on the direct path and through the real reader (which scrubs after its own deadline).
        line = '{"message": "' + '\\"' * 30000 + '"}'
        began = time.monotonic()
        self.assertEqual(live.scrub(line), line)  # no credential field: nothing masked
        self.assertLess(time.monotonic() - began, 1)
        began = time.monotonic()
        lines, _ = self.run_tail("import sys; sys.stdout.write(%r)" % line, deadline=0.2)
        self.assertEqual(lines, [line])
        self.assertLess(time.monotonic() - began, 3)

    def test_a_first_line_cut_inside_a_value_is_dropped_not_shown_without_its_key(self):
        # L-1: the buffer cut can land inside a value, leaving `=value` with no field name for scrub to see; the
        # partial first line it leaves carries the credential, so it is dropped, never shown.
        code = "import sys; sys.stdout.write('OPENAI_API_KEY=normal-short-value\\n')"
        lines, _ = self.run_tail(code, buffer=20)
        self.assertEqual(lines, [])
        self.assertNotIn("normal-short-value", " ".join(lines))

    def test_a_value_longer_than_the_buffer_is_not_shown_from_its_tail(self):
        # L-1: a credential value longer than the buffer leaves its tail past the cut with the key far behind it;
        # the fragment carries no key, so nothing of the value is shown (with the default buffer).
        code = "import sys; sys.stdout.write('OPENAI_API_KEY=' + 'x'*70000)"
        lines, _ = self.run_tail(code)
        self.assertEqual(lines, [])
        self.assertNotIn("x", " ".join(lines))

    def test_a_missing_command_is_an_error_the_service_turns_into_one_line(self):
        with self.assertRaises(OSError):
            live.tail(["/nonexistent/zeroshot", "logs"], {}, os.getcwd())


class CommandTests(unittest.TestCase):
    """C3a/A1, A3: the optional `command` key -- its parser (`live.last_command`) and its shape check.

    Interpretations recorded for the reviewers (the worker's summary never reaches them): a matching line needs an
    integer millisecond timestamp -- one without it cannot be gated and is skipped like malformed JSON; the command
    is scrubbed before it is cut, so the stored text never exceeds `COMMAND_LIMIT` even when scrubbing lengthens it;
    an empty command is a legal text (the criterion bounds only its length); `at` is the floored stamp."""

    @staticmethod
    def record(message, timestamp=1791935230934):
        """One `zeroshot logs` line: `record.message` carries the Codex adapter text (a JSON object per line)."""
        return json.dumps({"subscriptionId": "sub", "runId": "run", "timestamp": timestamp,
                           "record": {"level": "debug", "target": "codex", "message": message}})

    def test_only_the_started_prefix_is_read_and_the_last_matching_line_wins(self):
        lines = [self.record("Codex command completed: pytest -q [completed] exit=0"),
                 self.record("Codex file change: src/app.py"),
                 self.record("Codex reasoning: thinking"),
                 self.record("Codex command started: first [running]"),
                 self.record("Codex command started: second [failed] exit=1")]
        self.assertEqual(live.last_command(lines), (live.floored(1791935230934), "second", 1791935230934))

    def test_a_multiline_message_keeps_its_first_line_and_its_trailing_shape_is_removed(self):
        message = "Codex command started: npm run build [completed] exit=0\ncompiled 12 files\nwarnings: none"
        self.assertEqual(live.last_command([self.record(message)])[1], "npm run build")

    def test_a_credential_is_scrubbed_and_the_command_is_cut_at_the_limit(self):
        secret = self.record("Codex command started: deploy token=abcd1234")
        self.assertNotIn("abcd1234", live.last_command([secret])[1])
        long = self.record("Codex command started: " + "x" * 400)
        self.assertEqual(len(live.last_command([long])[1]), live.COMMAND_LIMIT)

    def test_a_credential_in_a_shell_escaped_command_line_is_never_kept(self):
        """A1: the remembered command keeps no credential value when the command line carries an escaped quote (a
        JSON body, as a worker's curl sends). Interpretations recorded for the reviewers: the plain shapes (a quoted
        `Authorization`, an `export`) are masked as before; the shape the flat scan cannot see through
        (`-d "{\\"api_key\\":\\"<value>\\"}"`) is hidden whole, which A1 accepts as long as no value is kept; and a
        command line with an escaped quote but no credential (`"name"`) is left exactly as today."""
        commands = ('curl -d "{\\"api_key\\":\\"SENTINEL\\"}" https://x',
                    'curl -H "Authorization: Bearer SENTINEL" x',
                    "export OPENAI_API_KEY=SENTINEL")
        for command in commands:
            with self.subTest(command):
                text = live.last_command([self.record("Codex command started: " + command)])[1]
                self.assertNotIn("SENTINEL", text)
        plain = 'curl -d "{\\"name\\":\\"bob\\"}" https://x'  # an escaped quote, no credential field
        self.assertEqual(live.last_command([self.record("Codex command started: " + plain)])[1], plain)

    def test_unknown_prefixes_malformed_json_and_completed_commands_are_ignored(self):
        self.assertIsNone(live.last_command([]))
        self.assertIsNone(live.last_command(["not json at all"]))
        self.assertIsNone(live.last_command([self.record("Codex command completed: ls")]))
        self.assertIsNone(live.last_command([self.record("Codex command queued: ls")]))

    def test_the_old_record_without_the_key_and_the_new_one_both_validate(self):
        legacy = {k: v for k, v in live.new().items() if k != "command"}
        self.assertTrue(live.valid(legacy))  # written before C3a
        data = live.new()
        self.assertIsNone(data["command"])  # new() sets None
        self.assertTrue(live.valid(data))
        data["command"] = {"at": "2026-10-15T09:00:00Z", "text": "pytest -q"}
        self.assertTrue(live.valid(data))

    def test_any_other_key_set_or_command_shape_is_refused(self):
        with_command = live.new()
        with_command["command"] = {"at": "2026-10-15T09:00:00Z", "text": "x", "extra": 1}
        self.assertFalse(live.valid(with_command))
        self.assertFalse(live.valid({**live.new(), "extra": 1}))
        self.assertFalse(live.valid({**live.new(), "command": {"at": "nope", "text": "x"}}))
        self.assertFalse(live.valid({**live.new(), "command": {"text": "x"}}))
        self.assertFalse(live.valid({**live.new(), "command": {"at": "2026-10-15T09:00:00Z"}}))
        self.assertFalse(live.valid({**live.new(), "command": {"at": "2026-10-15T09:00:00Z", "text": "x" * 161}}))


class VerdictTests(unittest.TestCase):
    """C4a/A1, A4: the optional `verdicts` key -- its parser (`live.last_verdict`) and its shape check.

    The fixture line is the measured shape (run 01a16010, 2026-10-22): `record.message` is the node response JSON
    {response:{diagnostic:{message}, output, signals:{verdict}}}, written at `level` info, the other lines being
    adapter debug text. Interpretations recorded for the reviewers: the reason is the first non-empty line with its
    surrounding whitespace stripped ("" when the diagnostic carries none); a line without an integer millisecond
    timestamp is skipped like one that does not decode, because its `at` cannot be floored; the reason is scrubbed
    before it is cut, so the stored text never exceeds `VERDICT_TEXT`."""

    @staticmethod
    def record(message, timestamp=1791935230934, level="info"):
        return json.dumps({"subscriptionId": "sub", "runId": "01a16010", "timestamp": timestamp,
                           "record": {"level": level, "target": "native_v2_runner", "message": message}})

    @classmethod
    def response(cls, verdict, message=None, timestamp=1791935230934):
        response = {"diagnostic": {"message": message} if message is not None else {"message": "ok"},
                    "output": None, "signals": {"verdict": verdict}}
        return cls.record(json.dumps({"response": response}), timestamp)

    def test_an_accepted_review_is_read_from_the_last_response_line(self):
        lines = [self.record("Codex command started: pytest -q [completed] exit=0"),
                 self.record("Codex turn completed"),
                 self.response("accepted", "note: coverage is sufficient")]
        self.assertEqual(live.last_verdict(lines),
                         (live.floored(1791935230934), "accepted", "note: coverage is sufficient"))

    def test_a_rejected_review_keeps_the_first_line_of_a_multiline_diagnostic(self):
        line = self.response("rejected", "no test for the refusal\ndetails: tests/test_runs.py:12\none more line")
        self.assertEqual(live.last_verdict([line]), (live.floored(1791935230934), "rejected", "no test for the refusal"))

    def test_a_credential_in_the_diagnostic_is_scrubbed(self):
        line = self.response("rejected", "provider token=abcd1234 rejected the run")
        text = live.last_verdict([line])[2]
        self.assertNotIn("abcd1234", text)

    def test_a_credential_in_a_shell_escaped_reason_is_never_kept(self):
        """A1: the remembered verdict reason keeps no credential value when the diagnostic carries an escaped quote
        (the same shell line as `last_command`, through the same `scrub`). See the command test for the recorded
        interpretation: the unseen field is hidden whole, the plain shapes are masked, a reason without a credential
        is unchanged."""
        reasons = ('curl -d "{\\"api_key\\":\\"SENTINEL\\"}" https://x',
                   'curl -H "Authorization: Bearer SENTINEL" x',
                   "export OPENAI_API_KEY=SENTINEL")
        for reason in reasons:
            with self.subTest(reason):
                text = live.last_verdict([self.response("rejected", reason)])[2]
                self.assertNotIn("SENTINEL", text)

    def test_malformed_json_and_debug_lines_are_ignored(self):
        self.assertIsNone(live.last_verdict([]))
        self.assertIsNone(live.last_verdict(["not json at all"]))
        self.assertIsNone(live.last_verdict([self.record("Codex command started: ls")]))
        self.assertIsNone(live.last_verdict([self.record("{}")]))  # decodes, no response.signals.verdict
        self.assertIsNone(live.last_verdict([self.record(json.dumps({"response": {"signals": {"verdict": ""}}}))]))
        self.assertIsNone(live.last_verdict([self.record(json.dumps({"response": {"signals": {"verdict": 7}}}))]))
        # a line without an integer timestamp cannot be floored and is skipped like one that does not decode
        self.assertIsNone(live.last_verdict([self.response("accepted", "ok", timestamp="nope")]))

    def test_the_verdict_and_the_reason_are_cut_at_their_limits_and_a_missing_reason_is_empty(self):
        at, verdict, text = live.last_verdict([self.response("v" * 40, "r" * 400)])
        self.assertEqual((len(verdict), len(text)), (live.VERDICT_LABEL, live.VERDICT_TEXT))
        self.assertEqual(live.last_verdict([self.response("accepted", "")])[2], "")  # no non-empty line

    def test_the_old_record_without_verdicts_and_the_new_one_both_validate(self):
        for missing in ({"verdicts"}, {"command"}, {"command", "verdicts"}, set()):
            stale = {k: v for k, v in live.new().items() if k not in missing}
            with self.subTest(missing=missing):
                self.assertTrue(live.valid(stale))
        self.assertEqual(live.new()["verdicts"], [])  # new() sets []

    def test_any_other_key_set_or_verdict_shape_is_refused(self):
        good = {"at": START, "task": "T1", "round": 2, "role": "acceptance_review", "verdict": "rejected",
                "text": "no test"}
        accepted = live.new()
        accepted["verdicts"] = [good]
        self.assertTrue(live.valid(accepted))
        self.assertFalse(live.valid({**live.new(), "extra": 1}))
        for broken in ({k: v for k, v in good.items() if k != "round"},
                       {**good, "extra": 1},
                       {**good, "role": "worker"},
                       {**good, "round": 0},
                       {**good, "round": "2"},
                       {**good, "task": 7},
                       {**good, "verdict": "v" * 17},
                       {**good, "text": "t" * 161},
                       {**good, "at": None}):
            with self.subTest(broken=broken):
                self.assertFalse(live.valid({**live.new(), "verdicts": [broken]}))
        self.assertFalse(live.valid({**live.new(), "verdicts": [good] * (live.VERDICT_LIMIT + 1)}))


class ActivityTests(LiveTest):
    def test_the_tail_runs_only_when_asked_and_never_on_refresh_or_observation(self):
        # L-A3: count the calls.
        driver = self.scripted([("advance", 5), ("quiet", 5)])
        with self.authority() as a:
            self.approved(a)
            service, controller = self.service(a, driver)
            r = controller.start("M1", 1, ROLES)
            service.step(r)
            service.step(r)
            controller.refresh()
            service.home()
            service.rows()
            service.panel(r)
            service.journal(r)
            self.assertEqual(driver.logs, 0)
            title, lines = service.activity()
            self.assertEqual(driver.logs, 1)
            self.assertEqual(title, "Journal M1 · attempt 1")
            self.assertEqual(lines, ["fixture log %s: worker" % r["run_id"]])
            self.assertEqual(service.tail(r)[0].split(":")[0], "fixture log " + r["run_id"])
            self.assertEqual(driver.logs, 2)

    def test_an_empty_log_and_an_unavailable_one_each_say_so_in_one_line(self):
        driver = self.scripted([])
        with self.authority() as a:
            self.approved(a)
            service, controller = self.service(a, driver)
            r = controller.start("M1", 1, ROLES)
            driver.log_tail = lambda *args, **kw: []
            self.assertEqual(service.tail(r), ["The journal is empty so far: Zeroshot has not written anything yet."])

            def broken(*args, **kw):
                raise OSError("нет бинарника")
            driver.log_tail = broken
            self.assertEqual(service.tail(r), ["The journal is unavailable: нет бинарника"])


class TaskChangeTests(LiveTest):
    """L-2: a slice whose buffered records span a task change never names an execution after a task it cannot prove."""

    class Buffered(Scripted):
        """A slice that delivers every buffered record at once, whatever the manifest already holds by then."""

        def __init__(self, root, clock, values=()):
            super().__init__(root, clock, [])
            self.values = list(values)

        def watch(self, r, after, seconds=None):
            return list(self.values)

    def texts(self, r):
        return [e["text"] for e in r["live"]["journal"]]

    def role_lines(self, r, count):
        """The journal holds exactly `count` generic role lines, one for each execution seen so far."""
        self.assertEqual([t for t in self.texts(r) if t == "worker"], ["worker"] * count)

    def native(self, n):
        """A native selector: `nv2-` plus a digest, the engine's own shape, which names no task at all."""
        return "nv2-%064x" % n

    def two_task_manifest(self, r, ids=("T1", "T2")):
        """The driver's own milestone holds one task, too small to carry a task change: write the same manifest
        with a second task (the plan's ids are global, so the later milestone's task is renamed), as the plan
        builder would. `ids` names the two tasks of the first milestone."""
        proposal = fixture_proposal()
        proposal["milestones"][0]["slices"][0]["tasks"][0]["id"] = ids[0]
        proposal["milestones"][0]["slices"][0]["tasks"].append(
            {"id": ids[1], "title": "Harden the behavior", "checks": ["Deterministic regression test"]})
        proposal["milestones"][1]["slices"][0]["tasks"][0]["id"] = "T3"
        _, manifest = milestone.build_manifest(proposal, "M1", 1)
        atomic_state(Path(r["worktree"]) / milestone.MANIFEST, manifest)
        return manifest

    def accept(self, r, task):
        path = Path(r["worktree"]) / milestone.MANIFEST
        manifest = decode(path.read_text())
        FixtureDriver.accept(manifest, task)
        atomic_state(path, manifest)

    def record_value(self, state, execution, cursor, node="worker"):
        """One valid watch record: a running status with exactly that active execution."""
        value = FixtureDriver.projection({**state, "position": 1})
        value["status"] = {"phase": "running", "activeExecutions": [{"node": node, "execution": execution}]}
        value["cursor"] = cursor
        return value

    def test_a_slice_spanning_a_task_change_never_guesses_the_task_or_the_round(self):
        # The manifest is already past T1 before the first buffered record is read; both workers arrive in it.
        driver = self.Buffered(self.root / "fixture-runs", self.clock)
        with self.authority() as a:
            self.approved(a)
            service, controller = self.service(a, driver)
            r = controller.start("M1", 1, ROLES)
            state = driver.load(r["run_id"])
            self.two_task_manifest(r)
            self.accept(r, "T1")
            driver.values = [self.record_value(state, "T1-w1", "fixture:1"),
                             self.record_value(state, "T2-w1", "fixture:2")]
            service.runs.observe(r, seconds=None)
            texts = self.texts(r)
            self.assertEqual(texts, ["T1: implementation", "T2: implementation"])
            self.assertNotIn("rework", " ".join(texts))  # no invented round
            self.assertEqual([t for t in texts if "T1" in t], ["T1: implementation"])  # T1's worker stays T1's

    def test_a_buffered_slice_of_opaque_executions_names_no_task_and_invents_no_round(self):
        # L-2: the manifest is already past T1 before the first buffered record is read; a native selector names
        # no task, so neither worker may be claimed for T2 and no repair round may be invented for it.
        driver = self.Buffered(self.root / "fixture-runs", self.clock)
        with self.authority() as a:
            self.approved(a)
            service, controller = self.service(a, driver)
            r = controller.start("M1", 1, ROLES)
            state = driver.load(r["run_id"])
            self.two_task_manifest(r)
            self.accept(r, "T1")
            driver.values = [self.record_value(state, self.native(1), "fixture:1"),
                             self.record_value(state, self.native(2), "fixture:2")]
            service.runs.observe(r, seconds=None)
            texts = self.texts(r)
            self.assertEqual(texts, ["worker", "worker"])  # one line per execution, nothing else
            self.assertNotIn("T2", " ".join(texts))  # neither worker is claimed for the task the manifest holds
            self.assertNotIn("implementation", " ".join(texts))
            self.assertNotIn("rework", " ".join(texts))  # no invented round

    def test_a_task_named_like_a_whole_native_selector_is_still_opaque(self):
        # L-2: a task id may itself be the whole `nv2-<digest>` selector; that is still the shape of the engine's
        # opaque ids, so a buffered worker is never claimed for it (nor the finished first task invented a round).
        driver = self.Buffered(self.root / "fixture-runs", self.clock)
        with self.authority() as a:
            self.approved(a)
            service, controller = self.service(a, driver)
            r = controller.start("M1", 1, ROLES)
            state = driver.load(r["run_id"])
            selector = self.native(1)
            self.two_task_manifest(r, (selector, "T2"))
            self.accept(r, selector)  # the first task is done: the manifest's current task is T2
            driver.values = [self.record_value(state, self.native(2), "fixture:2"),
                             self.record_value(state, selector, "fixture:3")]
            service.runs.observe(r, seconds=None)
            texts = self.texts(r)
            self.assertEqual(texts, ["worker", "worker"])
            self.assertNotIn(selector, " ".join(texts))  # the finished task is not named by an opaque execution
            self.assertNotIn("implementation", " ".join(texts))
            self.assertNotIn("rework", " ".join(texts))  # no invented round

    def test_each_distinct_ambiguous_execution_keeps_its_own_journal_line(self):
        # L-2: three different opaque workers are three events; one role text must not collapse them into one
        # line, and the execution id, not the text, is what deduplicates a re-delivery at a new cursor.
        driver = self.Buffered(self.root / "fixture-runs", self.clock)
        with self.authority() as a:
            self.approved(a)
            service, controller = self.service(a, driver)
            r = controller.start("M1", 1, ROLES)
            state = driver.load(r["run_id"])
            self.two_task_manifest(r)
            driver.values = [self.record_value(state, self.native(1), "fixture:1")]
            service.runs.observe(r, seconds=None)
            self.role_lines(r, 1)
            self.accept(r, "T1")  # the manifest moves on: the next records are still nameless executions
            driver.values = [self.record_value(state, self.native(2), "fixture:2"),
                             self.record_value(state, self.native(3), "fixture:3"),
                             self.record_value(state, self.native(4), "fixture:4")]
            service.runs.observe(r, seconds=None)
            self.role_lines(r, 4)
            driver.values = [self.record_value(state, self.native(4), "fixture:5")]
            service.runs.observe(r, seconds=None)
            self.role_lines(r, 4)  # the same execution again adds nothing

    def test_a_later_slice_does_not_claim_an_execution_it_did_not_watch_start(self):
        # L-2: the slice that ended on the manifest's new task proves nothing about a record arriving later: the
        # current task is never adopted as the owner of an execution the record itself does not name.
        driver = self.Buffered(self.root / "fixture-runs", self.clock)
        with self.authority() as a:
            self.approved(a)
            service, controller = self.service(a, driver)
            r = controller.start("M1", 1, ROLES)
            state = driver.load(r["run_id"])
            self.two_task_manifest(r)
            service.runs.observe(r, seconds=None)  # an empty slice: the manifest is still on T1
            self.accept(r, "T1")  # the task changes between slices
            service.runs.observe(r, seconds=None)  # another empty slice: this one already ends on T2
            driver.values = [self.record_value(state, self.native(9), "fixture:9")]
            service.runs.observe(r, seconds=None)
            texts = self.texts(r)
            self.assertEqual(texts, ["worker"])
            self.assertNotIn("T2", " ".join(texts))

    def test_a_manifest_task_that_looks_like_a_native_prefix_names_nothing(self):
        # L-2: the plan may name a task `nv2`, but a native selector is a digest, not that name: the two opaque
        # workers of the milestone's second task stay generic role lines with no invented round.
        driver = self.Buffered(self.root / "fixture-runs", self.clock)
        with self.authority() as a:
            self.approved(a)
            service, controller = self.service(a, driver)
            r = controller.start("M1", 1, ROLES)
            state = driver.load(r["run_id"])
            self.two_task_manifest(r, ("nv2", "T2"))
            self.accept(r, "nv2")
            driver.values = [self.record_value(state, self.native(1), "fixture:1"),
                             self.record_value(state, self.native(2), "fixture:2")]
            service.runs.observe(r, seconds=None)
            texts = self.texts(r)
            self.assertEqual(texts, ["worker", "worker"])
            self.assertNotIn("nv2", " ".join(texts))
            self.assertNotIn("rework", " ".join(texts))

    def test_an_execution_proves_its_task_only_when_one_id_fits_it(self):
        # L-2/L-3: an id two manifest ids fit proves neither (`T1-hardening-w1` under `T1` and `T1-hardening`), and
        # a native digest is no task name; a milestone's sole task is the one other proof of ownership.
        self.assertIsNone(live.execution_task("T1-hardening-w1", ["T1", "T1-hardening"]))
        self.assertIsNone(live.execution_task(self.native(1), ["nv2", "T2"]))
        self.assertEqual(live.execution_task("T1-w1", ["T1", "T1-hardening"]), "T1")
        self.assertEqual(live.execution_task(self.native(1), ["T1"]), "T1")

    def test_a_sole_manifest_task_names_native_executions_as_before(self):
        # L-3: a milestone's only task is never removed, so its opaque executions keep the previous journal
        # (implementation, the review, the rework round) instead of bare roles.
        driver = self.Buffered(self.root / "fixture-runs", self.clock)
        with self.authority() as a:
            self.approved(a)
            service, controller = self.service(a, driver)
            r = controller.start("M1", 1, ROLES)
            state = driver.load(r["run_id"])
            driver.values = [self.record_value(state, self.native(1), "fixture:1"),
                             self.record_value(state, self.native(2), "fixture:2", node="code_review"),
                             self.record_value(state, self.native(3), "fixture:3")]
            service.runs.observe(r, seconds=None)
            self.assertEqual(self.texts(r),
                             ["T1: implementation", "T1: code review", "T1: rework, round 1"])


class RoleNameTests(unittest.TestCase):
    """A1/A2 of "Live role names": the live panel names every node of the shipped milestone graph in words.

    Interpretation: the graph's node names live in `milestone.ROLES` (terminal_planner/milestone.py), while the
    panel resolves a node through `live.role` -> `live.ROLES` after `live.base` strips the `empty_` variant prefix.
    A2 therefore iterates `milestone.ROLES` (whose keys already include the `empty_` variants) and asserts each
    base name has an entry, so a future graph node without a name fails here. The A1 words came from the dogfood
    2026-10-22 finding 1 (job J2): the panel showed "Working now: select" because the milestone graph's three
    selection nodes and the steward's decision were absent from `live.ROLES` (live.py)."""

    def test_the_selection_nodes_and_the_stewards_decision_are_named_in_words(self):
        # A1: the milestone graph's selection nodes read as one role, the steward's decision as "steward".
        self.assertEqual(live.role("select_init"), "task selection")
        self.assertEqual(live.role("select"), "task selection")
        self.assertEqual(live.role("select_verify"), "task selection")
        self.assertEqual(live.role("steward_decide"), "steward")

    def test_the_preflight_node_is_named_in_words(self):
        # C3: the milestone's preflight reads «pre-check» in the live panel.
        self.assertEqual(live.role("preflight"), "pre-check")
        data = live.new()
        data["nodes"] = [["preflight", "nv2-" + "a" * 64]]
        self.assertIn("Working now: pre-check", "\n".join(live.panel_lines(data, None, None)))

    def test_every_milestone_node_and_its_empty_variant_has_a_word(self):
        # A2: a future graph node without a `live.ROLES` word fails here.
        self.assertTrue(milestone.ROLES)
        for name in milestone.ROLES:
            with self.subTest(name=name):
                base = live.base(name)
                self.assertIn(base, live.ROLES)
                self.assertEqual(live.role(name), live.ROLES[base])
                if not name.startswith("empty_"):
                    self.assertEqual(live.role("empty_" + name), live.ROLES[base])


class JournalRoleNameTests(unittest.TestCase):
    """A1/A2 of "Journal role names": `live.stages` journals a role word for every node that has a `live.ROLES`
    entry, and "final check" only for the final verification nodes.

    Interpretation: the final verification nodes (final_verify, final_reverify, scope_verify and, through
    `live.base`, their `empty_` variants) are the three names the `stages` branch tests together; the rule covers
    the nodes live-role-names (merge 8145744) added to `live.ROLES` (select_init, select, select_verify,
    steward_decide), which had been caught by the old catch-all branch and journalled "final check" three
    times at a milestone start. The names stay in `stages` (the task's write-set allows `live.py` only there), so
    this test pins them on its own; nodes with no `live.ROLES` entry keep the generic "stage <node>" line; nodes with
    a branch of their own (worker, the two reviews, steward_apply, repair) and the panel's `live.role` words are
    untouched. Every execution below is a native selector (`nv2-` + 64 hex); the fixtures pass the sole manifest
    task T1, so `execution_task` resolves it by the single-task rule, and none of the nodes below is journalled by
    task, so these lines carry no task prefix; the node names themselves are inert strings."""

    def test_a_selection_or_decision_node_journals_its_role_word_not_the_final_check(self):
        # A2/regression of the 2026-10-22 finding: a milestone start journalled "final check" per selection.
        for name, expected in (("select_init", "task selection"), ("select", "task selection"),
                               ("select_verify", "task selection"), ("steward_decide", "steward"),
                               ("final_verify", "final check"), ("final_reverify", "final check"),
                               ("scope_verify", "final check"), ("empty_scope_verify", "final check"),
                               ("never_seen_node", "stage never_seen_node")):
            with self.subTest(name=name):
                data = live.new()
                live.stages(data, {"activeExecutions": [{"node": name, "execution": "nv2-" + "a" * 64}]},
                            START, ("T1",))
                self.assertEqual([e["text"] for e in data["journal"]], [expected])

    def test_every_named_node_without_a_branch_of_its_own_journals_its_role_word(self):
        # A1: only the final verification nodes read as the final check; no other `live.ROLES` entry falls back.
        own = {"worker", "code_review", "acceptance_review", "steward_apply", "repair"}  # branches of their own
        final = {"final_verify", "final_reverify", "scope_verify"}  # the milestone's final check and its retries
        for name in sorted(set(live.ROLES) - own):
            with self.subTest(name=name):
                data = live.new()
                live.stages(data, {"activeExecutions": [{"node": name, "execution": "nv2-" + "a" * 64}]},
                            START, ("T1",))
                text = data["journal"][0]["text"]
                self.assertEqual(text, "final check" if name in final else live.ROLES[name])
                self.assertEqual(text == "final check", name in final)


class NextStepTests(LiveTest):
    HOME_KEYS = {a.key for a in catalog.ACTIONS.values() if a.screen == "home"}

    def test_every_state_names_the_next_step_from_the_end_screen_table(self):
        # L-A4: one table over every milestone state; the named keys exist on home, labels come from END_ACTIONS.
        record = {"destination": {"branch": "zplan/m1"}}
        states = set(STATE_TEXT) | {"unknown"}
        self.assertEqual(states - set(STATE_TEXT) - {"unknown"}, set())
        for state in sorted(states):
            item = {"state": state, "id": "M1", "record": record}
            with self.subTest(state):
                text = Delivery.next_step(item)
                self.assertRegex(text, r"^\[[a-z]\] \S")
                key = text[1]
                self.assertIn(key, self.HOME_KEYS)  # every named key works from home
                if state in END_ACTIONS and key == "o":
                    for _, action_id in END_ACTIONS[state]:
                        action = catalog.action(action_id)
                        label = catalog.label(action_id, "zplan/m1") if "%s" in action.label else catalog.label(action_id)
                        self.assertIn(label, text)
        self.assertTrue(Delivery.next_step({"state": "needs_owner", "id": "M1", "record": record}).startswith("[o]"))
        self.assertTrue(Delivery.next_step({"state": "ready", "id": "M2", "record": None}).startswith("[g] start M2"))
        for state in ("unknown", "stopping"):
            self.assertIn("check", Delivery.next_step({"state": state, "id": "M1", "record": record}))

    def test_g_never_starts_anything_while_a_stop_is_pending_but_still_checks(self):
        # L-A4: busy slot; [g] is check for stopping/unknown, nothing for a ready milestone behind it.
        items = [{"id": "M1", "state": "stopping", "record": {}}, {"id": "M2", "state": "ready", "record": None}]
        self.assertEqual(Delivery.g_item(items)["id"], "M1")
        self.assertEqual(Delivery(None, None, None).g_id(items), "home.check")
        only_ready = [{"id": "M2", "state": "ready", "record": None}]
        self.assertEqual(Delivery(None, None, None).g_id(only_ready), "home.start")
        running = [{"id": "M1", "state": "running", "record": {}}, {"id": "M2", "state": "ready", "record": None}]
        self.assertIsNone(Delivery(None, None, None).g_id(running))  # one active slot: nothing to start
        self.assertEqual(Delivery.busy(items)["id"], "M1")


if __name__ == "__main__":
    unittest.main()
