"""U5: live run visibility inside the full-screen UI and in the line UI: the running panel, the journal, the
activity tail, pending feedback, "Дальше:", key bars and the screens' wording.

Textual Pilot over real temporary Git repositories, the fixture store and a stepping fixture driver: every watch
slice waits for the test, costs the seconds the test names and may be quiet, a replay or a lost observation. The
wall clock is fake. No provider, no network. They need Textual (the interpreter's own, or the wheels of
ZPLAN_TEST_WHEELHOUSE) and skip without it."""

import json
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import types
import unittest
from unittest.mock import patch

from terminal_planner import bridge, catalog, engine, live, planning, process
from terminal_planner.authority import Rejected
from terminal_planner.delivery import END_ACTIONS, Token
from terminal_planner.tui import slash
from terminal_planner.tui.controller import Outcome
from terminal_planner.engine import FixtureEngine, ObservationDetached
from terminal_planner.runs import FixtureDriver, MilestoneRuns
from test_live import Clock, START
from test_parallel_runs import parallel_plan
from test_terminal_planner import Authority, ProjectTest, ROLES
from test_tui import Readiness, check
from test_tui_milestones import START_KEYS, Gated, MilestoneShell
from test_tui_planning import DIRTY, GOAL, PlanningShell
from tui_support import HAVE_TEXTUAL, screen_lines, screen_text


class Stepper(Gated):
    """A gated driver whose slices are paced by the test: `turn.set()` lets exactly one real slice through, `modes`
    says what it does ("advance" a scripted record, "quiet", "replay" the last record, "detach") and how many
    seconds the fake clock moves first. Between turns a slice is a short empty one at no cost, so the controller
    stays free for refreshes, details and the tail, as it is between real slices. `submit_gate` and `stop_gate`
    hold a submission or a force-stop."""

    def __init__(self, root, clock, **kw):
        super().__init__(root, **kw)
        self.clock, self.modes, self.last = clock, [], None
        self.turn, self.free, self.finished, self.lost = threading.Event(), False, 0, False
        self.submit_gate, self.stop_gate = threading.Event(), threading.Event()
        self.submit_gate.set()
        self.stop_gate.set()
        self.log_threads = []

    def release(self):
        self.free = True
        for gate in (self.turn, self.submit_gate, self.stop_gate, self.gate):
            gate.set()

    def submit(self, r, paths):
        self.submit_gate.wait(10)
        return super().submit(r, paths)

    def force_stop(self, r):
        self.stop_gate.wait(10)
        super().force_stop(r)

    def watch(self, r, after, seconds=None):
        self.slices += 1
        self.entered.set()
        if not self.free:
            if not self.turn.is_set():
                time.sleep(0.05)
                if self.lost:  # a watch that cannot reach Zeroshot keeps failing until it can
                    raise ObservationDetached()
                return []
            self.turn.clear()
        mode, spent = self.modes.pop(0) if self.modes else ("advance", 1)
        self.clock.advance(spent)
        self.lost = mode == "detach"
        try:
            if mode == "quiet" or (mode == "replay" and self.last is None):
                return []
            if mode == "detach":
                raise ObservationDetached()
            if mode == "replay":
                return [self.last]
            values = FixtureDriver.watch(self, r, after, seconds)
            self.last = values[-1]
            return values
        finally:
            self.finished += 1

    def log_tail(self, binding, run_id, cwd, lines=live.TAIL_LINES, **options):
        self.log_threads.append(threading.current_thread())
        return FixtureDriver.log_tail(self, binding, run_id, cwd, lines, **options)


def bar_items(line):
    """(key, label) of every `[key] label` item of a key bar line."""
    return [(m.group(1), (m.group(2) or "").strip())
            for m in re.finditer(r"\[([^\]]+)\](?: ([^\[]*?))?(?=\s{2,}\[|\s*$)", line)]


def known_item(key, label):
    """True when `label` is, whole, a label or short label of an action that has `key`."""
    for a in catalog.ACTIONS.values():
        if key not in (a.key,) + tuple(a.alt):
            continue
        for text in (a.label, a.short, ""):
            if label == text or ("%s" in text and re.fullmatch(re.escape(text).replace("%s", ".+"), label)):
                return True
    return False


STALE_PART = engine.STALE.split(". ")[1]  # the sentence naming the moved baseline (engine.py's text, whatever its language)


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is unavailable: ZPLAN_TEST_WHEELHOUSE with textual 8.2.8 wheels is needed")
class LiveShell(MilestoneShell):
    def setUp(self):
        super().setUp()
        self.clock = Clock()
        for module in ("terminal_planner.runs.now", "terminal_planner.delivery.now"):
            patcher = patch(module, self.clock)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.driver = Stepper(self.root / "fixture-runs", self.clock)
        self.addCleanup(self.driver.release)

    def main(self):
        return next(s for s in self.app.screen_stack if type(s).__name__ == "MainScreen")

    @staticmethod
    def worker_steps(text):
        """How many journal entries name task T1's first worker step: every `T1: ` entry that is not a review one
        (live.py's own wording of the step, whatever its language)."""
        reviews = [live.ROLES["acceptance_review"], live.ROLES["code_review"]]
        return text.count("T1: ") - sum(text.count("T1: " + word) for word in reviews)

    def pane(self):
        """The plan panel's logical lines, as one text (wraps and the neighbouring pane do not interleave)."""
        return "\n".join(self.main().plan_lines)

    def reconnect_lines(self):
        """The panel lines that offer `/attempt` apart from the `Next:` hint: the detached stamp's reconnect key
        (live.py's wording of it, whatever its language)."""
        return [line for line in self.pane().splitlines() if "/attempt" in line and not line.lstrip().startswith("Next:")]

    async def step(self, pilot):
        """One watch slice through, then the panel refreshed."""
        done = self.driver.finished
        self.driver.turn.set()
        await self.until(pilot, lambda: self.driver.finished > done)
        self.app.request_refresh()
        self.app.request_check()
        await pilot.pause(0.3)

    async def start_held(self, pilot):
        await self.loaded(pilot)
        await self.begin_run(pilot)
        await self.until(pilot, self.driver.entered.is_set)

    async def until_pane(self, pilot, text, timeout=20.0):
        """Wait, for up to `timeout` real monotonic seconds and yielding to the UI through Pilot, until `text`
        shows in the plan pane; on timeout report the pane as it stands. `start_held` waits only for
        `driver.entered`, which proves that a watch slice began — not that the running snapshot has reached the
        panel: `ZplanApp.got_snapshot` → `changed` paints it through the UI thread's hand-over, so an immediate
        pane assertion can race that delivery. The fake clock is not advanced and no turn, refresh or sleep is
        added."""
        end = time.monotonic() + timeout
        while not (text.search(self.pane()) if hasattr(text, "search") else text in self.pane()):
            if time.monotonic() >= end:
                self.fail("did not wait for %r in the pane for %.1f s:\n%s" % (text, timeout, self.pane()))
            await pilot.pause(0.05)



class SlowPaneTests(unittest.IsolatedAsyncioTestCase):
    """K1d C5: `until_pane` waits 20 s by default (3 load flakes on 2026-10-25 waited 5 s beside a run); the clock is
    fake, the text shows at 6 fake seconds."""

    async def test_c5_until_pane_waits_20_seconds_by_default(self):
        clock = [0.0]

        class Pilot:
            async def pause(self, delay):
                clock[0] += delay

        shown = types.SimpleNamespace(pane=lambda: "running 0 s" if clock[0] >= 6.0 else "", fail=self.fail,
                                      until_pane=LiveShell.until_pane)
        with patch.object(sys.modules[__name__], "time", types.SimpleNamespace(monotonic=lambda: clock[0])):
            await shown.until_pane(shown, Pilot(), "running 0 s")
            clock[0] = 0.0
            with self.assertRaises(AssertionError):
                await shown.until_pane(shown, Pilot(), "no such text")
            self.assertGreaterEqual(clock[0], 20.0)


class PanelTests(LiveShell):
    async def test_la1_the_panel_follows_slow_records_a_quiet_gap_replays_and_a_lost_observation(self):
        """Regression (tui-live-la1-flake): the observed flake was `AssertionError: 'идёт 0 с' not found` on the
        first pane assertion, in alternating runs on the Linux host, while the pane still showed
        «… запускаю M1…». Cause: `start_held` only waits for `driver.entered` — the moment a watch slice begins —
        but the running snapshot reaches `ZplanApp.got_snapshot` and repaints the pane through `changed()` on the
        UI thread, a hand-over the driver-entry event does not order against. So it is a test-side ordering race,
        not a production defect: the panel does appear once the snapshot is delivered. The fix keeps the entry
        wait, then waits up to 5 real monotonic seconds for the pane text, yielding to Pilot, and keeps the
        original assertion. No production file changed.

        R-2 audit (only demonstrated matches fixed): every other PanelTests method (la2, la3) steps past the first
        slice before touching the pane, so la1 is the only driver-entry → immediate-pane-assert ordering:
        none beyond LA1.

        Interpretations: the review's control "replace until_pane's body with `return`" would leave it a
        non-coroutine, so `await self.until_pane(...)` would raise TypeError instead of reaching la1's original
        assertion; mutation B below therefore uses the awaitable no-op (body `pass`). The task wording, the
        assertion text and the wait bound were otherwise explicit.

        A-2 ordering harness (scratch copy only; never committed). The running-M1 snapshots (those whose
        `snapshot.panel` carries the "идёт …" line, i.e. delivered after startup) are deferred at `got_snapshot`.
        The release is driven by the *real* helper: its own predicate (`self.pane`) is the first to see the text
        absent, and the deferred snapshots are flushed on the next UI turn — the very `pilot.pause` the helper
        awaits — through the bounded `gate`. The harness `finally` unconditionally restores both hooks, opens
        `gate` and drains every snapshot still deferred. Complete injection, `tests/test_la1_inject.py`:
          # A-2 ordering harness (scratch copy only; never committed).
          import sys
          import threading
          import unittest

          from terminal_planner.tui.app import ZplanApp
          from test_tui_live import LiveShell, PanelTests
          from tui_support import HAVE_TEXTUAL

          deferred, gate, state = [], threading.Event(), {}
          _got, _wait = ZplanApp.got_snapshot, LiveShell.until_pane

          def _running(s):
              return any("идёт" in line for line in (getattr(s, "panel", ()) or ()))

          def _got2(self, s, e):
              if not e and s is not None and _running(s) and not gate.is_set():
                  deferred.append(s)  # a running-M1 snapshot delivered after startup is withheld
                  state["withheld"] = state.get("withheld", 0) + 1
                  return
              return _got(self, s, e)

          def _flush(app):
              gate.set()  # open the barrier first: nothing is withheld once a release has begun
              todo, deferred[:] = list(deferred), []
              for s in todo:
                  try:
                      _got(app, s, None)
                  except Exception:
                      pass

          async def _wait2(self, pilot, text, timeout=5.0):
              # release on the real helper's own predicate (self.pane) observed false, on the next UI turn (pause)
              real_pane, real_pause = self.pane, pilot.pause

              def pane():
                  value = real_pane()
                  if not state.get("observed") and text not in value:
                      state["observed"] = True
                      state["pane_before_release"] = value
                  return value

              async def pause(*a, **k):
                  result = await real_pause(*a, **k)  # the helper's yield: a subsequent UI turn
                  if state.get("observed") and not state.get("released"):
                      state["released"] = True
                      state["deferred_at_release"] = len(deferred)
                      _flush(self.app)
                  return result

              self.pane, pilot.pause = pane, pause
              try:
                  return await _wait(self, pilot, text, timeout)
              finally:
                  self.pane, pilot.pause = real_pane, real_pause

          ZplanApp.got_snapshot, LiveShell.until_pane = _got2, _wait2

          @unittest.skipUnless(HAVE_TEXTUAL, "Textual недоступен")
          class Harness(PanelTests):
              async def test_la1_deferred_ordering(self):
                  try:
                      await self.test_la1_the_panel_follows_slow_records_a_quiet_gap_replays_and_a_lost_observation()
                  finally:
                      ZplanApp.got_snapshot, LiveShell.until_pane = _got, _wait
                      _flush(self.app)  # unconditional: open the gate and drain any snapshot still deferred
                      print("LA1-HARNESS: withheld=%s observed=%s released=%s deferred_at_release=%s deferred_left=%d"
                            % (state.get("withheld"), state.get("observed"), state.get("released"),
                               state.get("deferred_at_release"), len(deferred)), file=sys.stderr)
                  self.assertEqual(state.get("observed"), True, "the helper predicate never saw the pane without text")
                  self.assertEqual(state.get("released"), True, "the release never happened")
                  self.assertNotIn("идёт 0 с", state.get("pane_before_release") or "", "pane had the text early")
        Exact commands (short `TMPDIR`; the harness file is written in the copy, run with `PYTHONPATH=.:tests`):
          python3.13 -c 'import shutil,sys; shutil.copytree(".", sys.argv[1], ignore=shutil.ignore_patterns(".git",".tools","__pycache__"))' /tmp/zs-agent-XXXXXX/repo
          cd /tmp/zs-agent-XXXXXX/repo   # write tests/test_la1_inject.py as above, then:
          TMPDIR=/tmp/zs-agent-XXXXXX PYTHONPATH=.:tests python3.13 -m unittest -v test_la1_inject.Harness.test_la1_deferred_ordering
          # mutation B: the helper body becomes an awaitable no-op (its predicate loop is gone), same unittest:
          python3.13 -c 'p="tests/test_tui_live.py"; s=open(p).read(); i=s.index("    async def until_pane(self, pilot, text, timeout=5.0):"); j=s.index("\nclass PanelTests", i); open(p,"w").write(s[:i] + "    async def until_pane(self, pilot, text, timeout=5.0):\n        pass\n" + s[j:])'
          # mutation C: only the new wait call is removed, same unittest:
          python3.13 -c 'p="tests/test_tui_live.py"; s=open(p).read(); s2=s.replace("            await self.until_pane(pilot, \"идёт 0 с\")\n", "", 1); assert s2 != s; open(p, "w").write(s2)'
        Outcomes. A, wait restored: `LA1-HARNESS: withheld=1 observed=True released=True deferred_at_release=1
        deferred_left=0` and `Ran 1 test ... OK` — driver.entered had been reached with the pane still lacking the
        text; the real predicate saw it absent, the release happened on the following `pilot.pause` turn (one
        withheld snapshot flushed) and the complete la1 passed. B, helper body → `pass`: `withheld=1 observed=None
        released=None deferred_left=0` and `AssertionError: 'идёт 0 с' not found in …` at the original assertion —
        with the predicate loop gone nothing was observed or released, and the withheld snapshot was drained only
        by `finally`. C, wait call removed: identical `withheld=1 observed=None released=None deferred_left=0` and
        the same original-assertion failure. In B and C `finally` left `deferred_left=0` (gate opened, queue
        drained), the UI loop kept running throughout and both hooks were restored; the injection was never
        committed."""
        self.approve(running=False)
        self.driver.modes = [("advance", 20), ("quiet", 600), ("replay", 30), ("advance", 5), ("detach", 60),
                             ("quiet", 5)]
        async with self.shell(size=(120, 40), follow=True) as pilot:
            await self.start_held(pilot)
            await self.until_pane(pilot, re.compile(r"(?<!\d)" + re.escape(live.duration(0))))  # the elapsed part, not "20 s"
            self.assertIn(live.duration(0), self.pane())
            await self.step(pilot)  # the worker record, 20 s in
            self.assertIn(live.ROLES["worker"], self.pane())
            self.assertIn(live.ROLES["worker"], screen_text(self.app))
            self.assertIn(live.duration(20), self.pane())
            self.assertIn(live.duration(0), self.pane())
            self.assertIn(live.clock(self.clock()), self.pane())
            self.clock.advance(40)  # nothing arrives; a refresh only reads
            self.app.request_refresh()
            self.app.request_check()
            await pilot.pause(0.3)
            self.assertIn(live.duration(60), self.pane())
            self.assertIn(live.duration(40), self.pane())
            await self.step(pilot)  # a quiet gap of ten minutes: still alive, nothing new
            self.assertIn(live.duration(600), self.pane())
            self.assertIn(live.clock(self.clock()), self.pane())
            await self.step(pilot)  # the watch replays the record: not a new event
            self.assertIn(live.duration(660), self.pane())
            self.assertIn(live.clock(self.clock()), self.pane())
            await self.step(pilot)  # two reviewers at once: both named
            self.assertIn(", ".join((live.ROLES["acceptance_review"], live.ROLES["code_review"])), self.pane())
            self.assertIn(live.duration(0), self.pane())
            await self.step(pilot)  # the observation is lost: shown as such, no heartbeat claimed
            self.assertIn(live.clock(self.clock()), self.pane())  # the detached stamp replaces the heartbeat
            self.assertTrue(self.reconnect_lines(), self.pane())
            await self.step(pilot)  # Zeroshot answers again: the heartbeat is back
            self.assertFalse(self.reconnect_lines(), self.pane())
            self.assertIn(live.clock(self.clock()), self.pane())

    async def test_la2_the_journal_survives_the_modal_and_a_restart(self):
        self.approve(running=False)
        self.driver.modes = [("advance", 5), ("advance", 5), ("replay", 5)]
        async with self.shell(size=(120, 40), follow=True) as pilot:
            await self.start_held(pilot)
            await self.step(pilot)
            await self.step(pilot)
            await self.step(pilot)  # replay
            await self.command(pilot, "/details")
            await self.shows(pilot, "Journal M1 (attempt 1):")
            first = self.flat()
            self.assertEqual(self.worker_steps(first), 1)
            self.assertIn("T1: " + live.ROLES["acceptance_review"], first)
            await pilot.press("escape")  # closing the modal keeps the journal
            await pilot.pause(0.2)
            await self.command(pilot, "/details")
            await self.shows(pilot, "Journal M1 (attempt 1):")
            self.assertEqual(self.worker_steps(self.flat()), 1)
            await pilot.press("escape")
        # restart: a new controller over the same store, nothing observed any more
        async with self.shell(self.controller(), size=(120, 40), follow=False) as pilot:
            await self.loaded(pilot)
            await self.panel(pilot)  # D4: the input has the start focus; [i] is a pane key
            self.assertIn(", ".join((live.ROLES["acceptance_review"], live.ROLES["code_review"])), self.pane())
            await self.command(pilot, "/details")
            await self.shows(pilot, "Journal M1 (attempt 1):")
            self.assertEqual(self.worker_steps(self.flat()), 1)
            self.assertIn("T1: " + live.ROLES["code_review"], self.flat())
        entries = self.stored()["runs"][0]["live"]["journal"]
        self.assertLessEqual(len(entries), live.JOURNAL_LIMIT)

    async def test_la3_the_tail_is_read_on_the_worker_only_when_asked_in_the_tui_and_the_plain_ui(self):
        self.approve(running=False)
        async with self.shell(size=(120, 40), follow=True) as pilot:
            await self.start_held(pilot)
            await self.step(pilot)
            for _ in range(3):  # refreshes, checks and the observation never read the log
                self.app.request_refresh()
                self.app.request_check()
                await pilot.pause(0.2)
            self.assertEqual(self.driver.log_threads, [])
            await self.command(pilot, "/log")
            await self.shows(pilot, "Journal M1 · attempt 1")
            self.assertIn("fixture log " + self.driver.sent[0] + ":", self.flat())
            self.assertEqual(len(self.driver.log_threads), 1)
            self.assertIsNot(self.driver.log_threads[0], threading.main_thread())  # the controller's worker
            self.assertEqual(self.driver.log_threads[0].name, self.app.controller._thread.name)
            await pilot.press("escape")
        run_id = self.driver.sent[0]
        self.driver.log_threads.clear()
        output = self.plain("e\nq\n")  # the line UI: the same tail, on request
        self.assertEqual(len(self.driver.log_threads), 1)
        self.assertIn("fixture log %s:" % run_id, output)


class PendingTests(LiveShell):
    async def test_la4_a_confirmed_start_shows_pending_blocks_a_repeat_and_clears_on_error(self):
        self.approve(running=False)
        self.driver.submit_gate.clear()
        async with self.shell(size=(120, 40), follow=True) as pilot:
            await self.loaded(pilot)
            await self.begin_run(pilot)
            await self.shows(pilot, "starting M1…")
            self.assertNotIn("Next:", self.pane())  # the pending line replaces the old next step
            await self.command(pilot, "/run")  # the same action again: refused, nothing is sent twice
            await self.shows(pilot, "Already in progress: starting M1…")
            self.assertEqual(self.driver.sent, [])
            self.driver.submit_gate.set()
            await self.until(pilot, lambda: len(self.driver.sent) == 1)
            self.driver.release()
            await self.until(pilot, lambda: "starting M1…" not in self.pane())
        self.assertEqual(len(self.driver.sent), 1)

    async def test_la4_a_failed_start_clears_the_pending_line(self):
        self.approve(running=False)

        def refuse(r, paths):
            raise Rejected("Zeroshot refused.", family="milestone.lost")  # certain: the attempt ends as failed
        self.driver.validate = refuse
        async with self.shell(size=(120, 40), follow=True) as pilot:
            await self.loaded(pilot)
            await self.begin_run(pilot)
            await self.until(pilot, lambda: self.app.pending is None and "Not started" in self.flat())
            self.assertNotIn("starting M1…", self.flat())
            self.assertEqual(self.driver.sent, [])
            # the next step is the new attempt, not a stale start (the Plan tab drops the letter-key line, i10/P3)
            await self.until(pilot, lambda: any("[g] new attempt M1" in line for line in self.app.snapshot.lines))
            await self.command(pilot, "/run")  # the owner can try again at once
            await self.shows(pilot, "New attempt M1")
            await pilot.press("escape")

    async def test_la4_stop_shows_pending_and_while_stopping_g_checks_and_never_starts(self):
        self.approve(running=False)
        async with self.shell(size=(120, 40), follow=True) as pilot:
            await self.start_held(pilot)
            await self.step(pilot)
            self.driver.stop_gate.clear()
            await self.command(pilot, "/stop")
            await self.shows(pilot, "Stop the run M1")
            await self.press_button(pilot, "yes")
            await self.plan_shows(pilot, "stopping M1…")
            await self.command(pilot, "/stop")  # repeated stop: refused while the first is pending
            await self.shows(pilot, "Already in progress: stopping M1…")
            self.assertEqual(self.driver.stopped, [])
            self.driver.stop_gate.set()
            await self.until(pilot, lambda: self.driver.stopped != [])
            await self.until(pilot, lambda: self.app.snapshot.rows[0].state == "stopping")
            self.assertEqual(len(self.driver.stopped), 1)
            await pilot.pause(0.3)
            sent = len(self.driver.sent)
            await self.command(pilot, "/run")  # [g] reconciles; it never offers a start while the stop is not confirmed
            await pilot.pause(0.5)
            self.assertNotIn("Start M1", self.flat())
            self.assertNotIn("Start M2", self.flat())
            self.assertEqual(len(self.driver.sent), sent)
            self.driver.release()


class NextStepTests(LiveShell):
    async def check_outcome(self, outcome, key, command):
        self.driver.outcomes = (outcome,)
        self.driver.release()  # the run goes straight through
        self.approve(running=False)
        output = self.plain(START_KEYS + "q\nq\n")
        plain = [l for l in output.splitlines() if l.startswith("Next:")]
        self.assertTrue(plain, output)
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            lines = [l for l in self.main().plan_lines if l.startswith("Next:")]
            # K1a: the line the Plan tab shows names the `/` command that does the step, never the line UI's letter
            self.assertEqual(len(lines), 1, lines)
            self.assertTrue(lines[0].startswith("Next: " + command), lines)
            self.assertNotRegex(lines[0], r"\[[a-z]\]")
            self.assertIn("[%s]" % key, plain[-1])  # the line UI still names it, from the same table
            self.assertIn(command, [c.name for c in slash.COMMANDS])
            if outcome == "failed_recoverable":  # p4a: the resume acts at once, no screen opens for it
                resumed = []
                original = FixtureDriver.resume
                with patch.object(FixtureDriver, "resume",
                                  lambda driver, r, run_id: (resumed.append(run_id), original(driver, r, run_id))[1]):
                    await self.command(pilot, command)
                    await self.until(pilot, lambda: len(resumed) == 1)
                self.assertNotIn(type(self.app.screen).__name__, ("ConfirmScreen", "EnterConfirmScreen"))
                return
            await self.command(pilot, command)  # the command it names works from home
            await pilot.pause(0.5)
            self.assertNotEqual(type(self.app.screen).__name__, "MainScreen", self.flat())

    async def test_la4_done_names_the_end_screen(self):
        await self.check_outcome("done", "o", "/attempt")

    async def test_la4_needs_owner_names_the_end_screen(self):
        await self.check_outcome("needs_owner", "o", "/attempt")

    async def test_la4_blocked_names_the_end_screen(self):
        await self.check_outcome("blocked", "o", "/attempt")

    async def test_la4_failed_names_a_new_attempt(self):
        await self.check_outcome("failed", "g", "/run")

    async def test_la4_failed_recoverable_names_resume(self):
        await self.check_outcome("failed_recoverable", "g", "/run")

    def test_the_table_has_a_catalog_action_behind_every_end_screen_entry(self):
        for state, actions in END_ACTIONS.items():
            for name, action_id in actions:
                self.assertIn(action_id, catalog.ACTIONS, (state, name))


class KeyBarTests(LiveShell):
    def assert_intact(self, line, where):
        items = bar_items(line)
        self.assertTrue(items, (where, line))
        for key, label in items:
            self.assertTrue(known_item(key, label), (where, key, label, line))  # no word cut mid-way

    async def test_la5_no_bar_cuts_a_word_and_the_modal_actions_are_labelled(self):
        """i2: the bars still built by `catalog.bar` — the plan screen, a details/text
        modal and the help — cut no word and keep every label. Interpretation: the home and running legs this test
        used to pin (`[g] запустить` on the panel bar, `[x] остановить` while a stage runs) named the old *main*
        key bar, which i2 replaced with `activity.Bar`; the new main row is checked in `tests/test_tui_commands.py`
        (A3), so only the non-main bars are checked here."""
        self.approve(running=False)

        def whole(label):
            """The bottom bar is complete: it carries `label` and every item of it is a whole known item."""
            line = screen_lines(self.app)[-1]
            return label in line and all(known_item(key, text) for key, text in bar_items(line))
        for size in ((80, 24), (120, 40)):
            with self.subTest(size=size):
                async with self.shell(self.controller(), size=size, follow=True) as pilot:
                    await self.loaded(pilot)
                    await self.panel(pilot)  # D4: the input has the start focus; [g] is a pane key
                    await self.command(pilot, "/view")
                    await self.until(pilot, lambda: type(self.app.screen).__name__ == "PlanScreen")
                    await self.until(pilot, lambda: whole("[esc] " + catalog.label("tui_plan.back")))
                    plan = screen_lines(self.app)[-1]
                    self.assert_intact(plan, "plan")
                    self.assertIn("[esc] " + catalog.label("tui_plan.back"), plan)
                    await pilot.press("escape")
                    await self.until(pilot, lambda: type(self.app.screen).__name__ == "MainScreen")
                    await self.panel(pilot)  # R-A: the input has the focus after the plan screen
                    await self.command(pilot, "/run")  # [g] starts the focused milestone; p4a: no confirmation
                    await self.until(pilot, lambda: self.app.run_watch is not None)
                    await self.command(pilot, "/details")
                    await self.until(pilot, lambda: type(self.app.screen).__name__ == "TextScreen")
                    # the modal paints its own bar on mount/resize, a hand-over that is not ordered against the push
                    await self.until(pilot, lambda: bar_items((screen_lines(self.app) or [""])[-1])
                                     == [("↑↓", catalog.label("tui_details.scroll")), ("esc", catalog.label("tui_details.close"))])
                    modal = screen_lines(self.app)[-1]
                    self.assert_intact(modal, "details")
                    self.assertEqual(bar_items(modal), [("↑↓", catalog.label("tui_details.scroll")), ("esc", catalog.label("tui_details.close"))])
                    await pilot.press("escape")
                    await self.until(pilot, lambda: type(self.app.screen).__name__ == "MainScreen")
                    await self.command(pilot, "/help")
                    await self.until(pilot, lambda: type(self.app.screen).__name__ == "HelpScreen")
                    await self.until(pilot, lambda: whole("[esc] " + catalog.label("tui_help.close")))
                    self.assert_intact(screen_lines(self.app)[-1], "help")
                    self.assertIn("[esc] " + catalog.label("tui_help.close"), screen_lines(self.app)[-1])
                    await pilot.press("escape")
                    self.driver.release()
                self.driver.free = False
                self.driver.turn.clear()
                # a fresh approved store for the next size
                self.state = self.root / ("state-%s" % size[0])
                self.approve(running=False)
                self.driver = Stepper(self.root / ("runs-%s" % size[0]), self.clock)
                self.addCleanup(self.driver.release)

    async def test_la5_the_bar_text_is_whole_for_every_screen_at_every_width(self):
        """i2: every bar `catalog.bar` still builds — the modal and other-screen bars — is whole at every width
        and cuts no word. The main screen's own catalog screens (`tui_input`, `tui_panel`) are skipped: i2 replaced
        the main row with `activity.Bar`, so their `catalog.bar` text is no longer drawn anywhere."""
        for screen in sorted({a.screen for a in catalog.ACTIONS.values()}):
            if not screen.startswith("tui_") or screen in ("tui_input", "tui_panel"):
                continue
            for width in (40, 60, 80, 100, 120):
                text = catalog.bar(screen, None, width, primary=())
                for key, label in bar_items(text):
                    self.assertTrue(known_item(key, label), (screen, width, key, label))
                self.assertLessEqual(len(text), max(width, len(catalog.bar(screen, None, 10))))


class LeftPaneTests(LiveShell):
    async def test_item2_a_planner_finish_does_not_stay_over_a_milestone_run(self):
        """i9-look: the old chat pane title (`chat.title_run`, `Прогон M1`) is gone with the header look, so the
        milestone run's own status line (`M1 запущен · …`, `run_lines`) is what marks the transition here."""
        self.approve(running=False)
        async with self.shell(size=(120, 40), follow=True) as pilot:
            await self.loaded(pilot)
            self.app.progress.append("Demo plan: no model was called.")
            self.app.finish_note = "The planner finished: [p] open the plan."
            self.app.changed()
            await self.shows(pilot, "The planner finished")  # nothing else runs: the planner's last word stays
            await self.begin_run(pilot)
            await self.until(pilot, lambda: "The planner finished" not in self.flat())
            await self.shows(pilot, "M1 started")
            self.assertNotIn("Demo plan", self.flat())
            self.driver.release()


class WordingTests(LiveShell):
    async def test_item8_merge_confirm_names_the_result_not_the_branch_and_details_keep_the_branch(self):
        self.approve(running=False)
        self.driver.release()
        async with self.shell(size=(120, 40), follow=True) as pilot:
            await self.loaded(pilot)
            await self.begin_run(pilot)
            await self.open_merge_end(pilot)  # i3c: the card replaces the automatic end screen
            await pilot.press("escape")
            await pilot.pause(0.3)
            await self.command(pilot, "/details")
            await self.shows(pilot, "Details")
            details = "\n".join(self.app.screen.lines)
            found = re.search(r"[Bb]ranch:?\s+(\S+)", details)
            self.assertIsNotNone(found, details)  # the branch name belongs to the details
            branch = found.group(1)
            await pilot.press("escape")
            await pilot.pause(0.3)
            await self.command(pilot, "/attempt")
            await self.run_button(pilot, "merge")
            await self.press_button(pilot, "merge")
            await self.shows(pilot, "Merge the result of M1 into main?")
            self.assertNotIn(branch, self.flat())  # the confirmation names the result, not a branch
            await self.press_button(pilot, "no")

    async def test_item8_new_attempt_form_explains_names_its_field_and_its_confirm_key(self):
        self.driver.outcomes = ("failed",)
        self.approve(running=False)
        self.driver.release()
        async with self.shell(size=(120, 40), follow=True) as pilot:
            await self.loaded(pilot)
            await self.to_end(pilot)
            await self.press_button(pilot, "new_attempt")
            await self.shows(pilot, "New attempt M1")
            text = self.flat()
            self.assertIn("This is a new run of the stage: the model will be started again.", text)
            self.assertIn("Note for the new attempt (optional", text)
            await pilot.press("escape")  # the form is left unchanged: no attempt starts
            await pilot.pause(0.3)
            self.assertEqual(len(self.driver.sent), 1)

    async def test_item8_settings_without_a_log_say_what_to_press_and_escape_goes_one_level_back(self):
        self.approve(running=False)
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            await self.panel(pilot)  # D4: the input has the start focus; [s] is a pane key
            await self.command(pilot, "/setup")
            from terminal_planner.tui.app import LOG_PLACEHOLDER
            await self.shows(pilot, LOG_PLACEHOLDER)  # K1d: buttons
            await pilot.press("escape")
            await pilot.pause(0.2)
            self.assertEqual(type(self.app.screen).__name__, "MainScreen")
            await self.panel(pilot)  # R-A: the input has the focus after Settings
            await self.command(pilot, "/view")
            await pilot.pause(0.3)
            await pilot.press("question_mark")  # K1c2: the plan screen has no help key
            await pilot.pause(0.3)
            self.assertEqual(type(self.app.screen).__name__, "PlanScreen")
            await pilot.press("escape")
            await pilot.pause(0.2)
            self.assertEqual(type(self.app.screen).__name__, "MainScreen")

    async def test_item8_help_is_a_command_on_the_main_screen_and_no_key_on_the_screens_above_it(self):
        """K1a/K1c2: the main screen has no help key (its help is `/help`); the plan screen and Settings answer
        no `?` either (their buttons are their keys); F1 is bound nowhere."""
        self.approve(running=False)
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            await self.command(pilot, "/help")
            await pilot.pause(0.2)
            self.assertIn("Keys", screen_text(self.app))
            await pilot.press("escape")
            await pilot.pause(0.2)
            for command, screen in (("/view", "PlanScreen"), ("/setup", "SettingsScreen")):
                await self.command(pilot, command)
                await pilot.pause(0.2)
                await pilot.press("f1", "question_mark")
                await pilot.pause(0.2)
                self.assertNotIn("Keys", screen_text(self.app), command)
                self.assertEqual(type(self.app.screen).__name__, screen, command)
                await pilot.press("escape")
                await pilot.pause(0.2)
                self.assertEqual(type(self.app.screen).__name__, "MainScreen", command)


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is unavailable: ZPLAN_TEST_WHEELHOUSE with textual 8.2.8 wheels is needed")
class HangingIndentTests(unittest.TestCase):
    def test_item8_a_wrapped_status_line_hangs_under_its_text(self):
        from terminal_planner.tui import app as tui_app
        line = "  M1 · running: task T1 of 2, stage acceptance; last event 3 min ago, the watch goes on"
        (first, rest), = tui_app.hang([line], 40)
        self.assertTrue(rest)
        self.assertEqual(first, first[:40])
        self.assertTrue(first.startswith("  M1"))
        for piece in rest:  # the continuation sits two columns under the line's own indent
            self.assertTrue(piece.startswith(" " * 4), repr(piece))
            self.assertFalse(piece.startswith(" " * 5), repr(piece))
            self.assertLessEqual(len(piece), 40)
        words = " ".join(piece.strip() for piece in (first,) + rest).split()
        self.assertEqual(words, line.split())  # nothing cut or lost
        self.assertEqual(tui_app.wrapped(["short"], 40), ["short"])
        self.assertEqual(tui_app.wrapped([line], 40), [first] + list(rest))


class PlanScreenTests(PlanningShell):
    async def test_item6_a_fixed_tree_drops_the_blocked_message_a_moved_baseline_stays_with_n(self):
        self.plan()
        self.commit_change()  # the project moved on after the unsent revision: a real stale baseline
        readiness = Readiness(check("git"), check("branch", False, DIRTY, key="d"))
        with patch("terminal_planner.tui.app.BLOCK_RECHECK_SECONDS", 0.2):
            async with self.shell(self.controller(readiness), size=(120, 40)) as pilot:
                await self.loaded(pilot)
                await self.panel(pilot)  # D4: the input has the start focus; [p]/[g] are pane keys
                await self.command(pilot, "/view")
                await self.shows(pilot, STALE_PART)
                await self.press_button(pilot, "run")
                from terminal_planner.tui.card_kinds import NOT_STARTED_BELOW  # Rich at import: not at module level
                await self.shows(pilot, NOT_STARTED_BELOW)
                text = screen_text(self.app)
                self.assertIn("! Target", text)
                self.assertNotIn("above", text)  # the marked items are below the message
                before = readiness.calls
                readiness.fix("branch")  # the owner fixed it; the screen looks again by itself
                await self.until(pilot, lambda: "Not started" not in screen_text(self.app), timeout=6)
                self.assertGreater(readiness.calls, before)
                text = screen_text(self.app)
                self.assertNotIn("! Target", text)
                self.assertIn(STALE_PART, text)  # the real stale baseline stays
                self.assertTrue(self.app.screen.query("#plan-buttons-renew"))
        self.assertEqual(self.planner.sent, [])  # nothing was submitted by looking again
        self.assertEqual(len(self.stored()["revisions"]), 1)  # and nothing was renewed

    async def test_item6_refresh_and_looking_never_renew_or_submit(self):
        self.plan()
        self.commit_change()
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            await self.panel(pilot)  # D4: the input has the start focus; [p] is a pane key
            await self.command(pilot, "/view")
            await self.shows(pilot, STALE_PART)
            for _ in range(3):
                self.app.request_refresh()
                self.app.request_check()
                await pilot.pause(0.2)
            await self.press_button(pilot, "info")
            await self.press_button(pilot, "info")
            await pilot.pause(0.2)
        self.assertEqual(self.planner.sent, [])
        self.assertEqual(len(self.stored()["revisions"]), 1)

    async def test_item8_the_plan_screen_does_not_repeat_the_finish_line_and_i_toggles(self):
        self.planner.running = False
        async with self.shell(size=(120, 40)) as pilot:
            await self.open_plan(pilot)
            await self.shows(pilot, "r1 · 2")
            self.assertNotIn("The planner finished", screen_text(self.app))  # the plan screen says it itself
            await self.press_button(pilot, "info")
            await self.shows(pilot, "S1 Implement the smallest useful path")
            await self.press_button(pilot, "info")  # the same button closes what it opened
            await pilot.pause(0.3)
            self.assertNotIn("S1 Implement the smallest useful path", screen_text(self.app))

    async def test_item2_approval_removes_the_planner_finish_from_the_left_pane(self):
        self.propose()
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            await self.panel(pilot)  # D4: the input has the start focus; [p] is a pane key
            self.app.finish_note = "The planner finished: [p] open the plan."
            self.app.changed()
            await self.shows(pilot, "The planner finished")
            await self.command(pilot, "/view")
            await self.shows(pilot, "r1 · 2")
            await self.press_button(pilot, "approve")  # p4a: the button is the consent, nothing asks again
            await self.until(pilot, lambda: self.app.finish_note == "")
            await pilot.press("escape")
            await pilot.pause(0.3)
            self.assertNotIn("The planner finished", self.flat())

    async def test_item8_a_confirm_over_the_plan_screen_leaves_the_plan_text_visible(self):
        self.propose()
        for size in ((80, 24), (120, 40)):
            async with self.shell(size=size) as pilot:
                await self.loaded(pilot)
                await self.panel(pilot)  # D4: the input has the start focus; [p]/[a] are pane keys
                await self.command(pilot, "/view")
                await self.shows(pilot, "r1 · 2")
                await self.press_button(pilot, "reject")  # p4a: approve acts at once; reject still asks
                await self.shows(pilot, "Reject proposal r1?")
                text = screen_text(self.app)
                for line in ("r1 · 2", planning.goal_line("", 100, "home.details") + "Add a README paragraph", "M1 First usable increment",
                             "T1 Implement the agreed behavior", "M2 Independent verification",
                             "T2 Acceptance and code review"):
                    self.assertIn(line, text, size)  # the confirmation sits below the plan it asks about
                await self.press_button(pilot, "no")


if __name__ == "__main__":
    unittest.main()


class MilestoneStepper(Stepper):
    """`Stepper` with the hand kept per milestone (`open_attempts`): a released attempt runs its real slices at
    once, every other attempt keeps bouncing on the base gate's short empty slice, so one attempt is advanced to
    its end while another is held mid-flight. Slices run on the controller's one worker, so the flag is serial."""

    def __init__(self, root, clock):
        super().__init__(root, clock)
        self.open_attempts = set()

    def watch(self, r, after, seconds=None):
        if r["milestone"] in self.open_attempts:
            self.free = True
            try:
                return Stepper.watch(self, r, after, seconds)
            finally:
                self.free = False
        self.slices += 1
        self.entered.set()
        time.sleep(0.05)
        if self.lost:
            raise ObservationDetached()
        return []


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is unavailable: ZPLAN_TEST_WHEELHOUSE with textual 8.2.8 wheels is needed")
class ParallelWatchTests(LiveShell):
    def setUp(self):
        super().setUp()
        self.driver = MilestoneStepper(self.root / "fixture-runs", self.clock)
        self.addCleanup(self.driver.release)

    def prepare(self, max_runs=2, level="manual"):
        """Two independent attempts (M1, M2) running side by side under an accepted profile of `max_runs` slots
        and autonomy `level`: the very first snapshot the app takes has to start one watch chain for each running
        row."""
        plan = parallel_plan()
        (self.project / process.PROFILE_FILE).write_text(json.dumps(
            {"preset": process.PRESET_V2, "autonomy": {"level": level, "max_runs": max_runs}}))
        self.git("add", process.PROFILE_FILE)
        self.git("commit", "-qm", "parallel profile")
        with Authority(self.state, self.project) as authority:
            authority.profile = process.Profile.of(authority)
            authority.profile.accept()
            self.begin(authority)
            with patch("terminal_planner.engine.fixture_proposal", return_value=plan):
                self.propose(authority)
            authority.approve(1)
            runs = MilestoneRuns(authority, self.driver, worktrees=authority.directory / "worktrees")
            for milestone in ("M1", "M2"):
                self.assertEqual(runs.start(milestone, 1, ROLES)["status"], "submitted")

    async def test_c4_every_running_attempt_is_observed_and_w_switches_the_shown_one(self):
        """C4 of A9t: `follow_runs` gives every running row its own chain of watch slices, [w] on another running
        row switches the shown attempt (the same row keeps «Наблюдение … уже идёт»), and an attempt that finishes
        while another is shown is concluded without a key, leaving the shown attempt untouched.

        Interpretation: the two attempts are started before the app opens (an independent plan and a two-slot
        profile), so the first snapshot exercises `follow_runs` itself; the per-milestone hand of the fixture
        driver then finishes M2 while M1 keeps running. `run_chain`/`run_watch` are the app's own chain bookkeeping
        the criterion names, not its wording, so they are read directly here."""
        self.prepare()
        async with self.shell(self.controller(profile=True), size=(120, 40), follow=True) as pilot:
            await self.loaded(pilot)
            await self.until(pilot, lambda: self.app.run_chain == {"M1", "M2"})
            self.assertEqual((self.app.run_watch, self.app.run_last), ("M1", "M1"))  # the first running row
            await self.panel(pilot)
            self.app.selected = "M2"  # [w] on the other running row switches the shown attempt
            await self.command(pilot, "/attempt")
            await self.until(pilot, lambda: (self.app.run_watch, self.app.run_last) == ("M2", "M2"))
            self.app.selected = "M2"
            await self.command(pilot, "/attempt")  # the same row: its observation just goes on
            await self.shows(pilot, "M2 is running; watching continues.")
            self.app.selected = "M1"
            await self.command(pilot, "/attempt")  # a different row switches the shown attempt
            await self.until(pilot, lambda: self.app.run_watch == "M1")
            self.assertEqual(self.app.run_chain, {"M1", "M2"})  # M2 kept its own chain across the switch
            self.app.selected = "M3"  # C2: [g] on a ready row behind the full slots names the slots and the actives
            await self.command(pilot, "/run")
            await self.until(pilot, lambda: self.app.run_note != "")
            self.assertEqual(self.app.run_note,
                             "All 2 slots are busy (M1, M2): a new start, a continuation and a new attempt wait. "
                             "/attempt watch, /run check.")
            self.driver.open_attempts.add("M2")  # M2 finishes while M1 is the shown attempt
            await self.until(pilot, lambda: self.app.snapshot.row("M2").state == "awaiting_merge", timeout=15)
            self.assertEqual(self.app.snapshot.row("M1").state, "running")  # M1 stayed observed and untouched
            self.assertIn("M1", self.app.run_chain)
            self.assertEqual(self.app.run_watch, "M1")
            self.assertEqual(type(self.app.screen).__name__, "MainScreen")  # no end screen for the hidden attempt

    async def test_c4_a_rebriefed_attempt_shows_its_own_lines_not_the_finished_attempts(self):
        """C4 (A9t repair): `follow_runs` gives an attempt the app did not start -- an architect rebrief -- its own
        observation state and its own, empty lines, so switching [w] to it never shows the finished attempt's
        buffered lines.

        Reproduction: M1 runs and is shown while M2's first attempt runs out to a terminal failure (its own phase
        lines land in its buffer); the production `Controller._rebrief_tool`, through its bridge job exactly as the
        architect's tool reaches it, opens M2's second attempt, whose observation slices are held empty; [w] on M2
        must show the new attempt's own lines (empty), never attempt 1's.

        Interpretation: the profile's autonomy is "auto" so the policy lets the rebrief run, and the second
        attempt's slices are held empty by the per-milestone hand (the lever the neighbouring test uses) -- the
        repair reproduction's "hold the new attempt's observation slices empty". `run_buffers`/`run_lines` are the
        app's own bookkeeping the criterion names, not its wording, so they are read directly."""
        from terminal_planner.tui.controller import token_fields
        self.driver.outcomes = ("failed", "done")  # M2's first attempt fails; the rebrief's own attempt is held
        self.prepare(max_runs=2, level="auto")
        async with self.shell(self.controller(profile=True), size=(120, 40), follow=True) as pilot:
            await self.loaded(pilot)
            await self.panel(pilot)
            await self.until(pilot, lambda: self.app.run_chain == {"M1", "M2"})
            self.assertEqual(self.app.run_watch, "M1")  # M1 is the shown attempt
            self.driver.open_attempts.add("M2")  # M2's first attempt runs out to a terminal failure
            await self.until(pilot, lambda: self.app.snapshot.row("M2").state == "failed", timeout=15)
            self.assertEqual(self.app.run_watch, "M1")  # the shown attempt never moved
            old = list(self.app.run_buffers.get("M2", ()))
            self.assertTrue(old, "the failed attempt left its own phase lines")  # what the bug would have shown
            self.driver.open_attempts.discard("M2")  # the rebriefed attempt's observation slices stay empty
            row = self.app.snapshot.row("M2")
            ok, error = self.app.controller._bridge_action(
                "c4-rebrief", "zplan_rebrief",
                {"milestone": "M2", "token": token_fields(row.token), "note": "try the fixture path again"})
            self.assertIsNone(error, error)
            self.assertEqual((ok["milestone"], ok["attempt"]), ("M2", 2))
            await self.until(pilot, lambda: self.app.snapshot.row("M2").state in ("running", "stopping"), timeout=8)
            self.app.selected = "M2"
            await self.command(pilot, "/attempt")  # [w] switches the shown attempt to the rebriefed M2
            await self.until(pilot, lambda: self.app.run_watch == "M2")
            await pilot.pause(0.3)
            # the new attempt's own lines: not the finished one's, only the start line F9 gives an architect's start
            self.assertEqual(list(self.app.run_lines), ["M2 started · plan r1 · attempt 2"])
            self.assertNotEqual(list(self.app.run_lines), old)

    async def test_c4_a_failure_card_retry_is_observed_beside_the_shown_attempt(self):
        """C4 (A9t repair): the failure card's `/retry` starts a new attempt while another milestone keeps the
        shown place -- the new attempt is observed under its own identity, its lines land in its own, empty buffer
        (never the shown attempt's) and its own slices carry it to the end, so its row leaves `running`.

        Reproduction: the card's retry used to append its note to the *shown* attempt's buffer (M1's) and start
        observation with the finished attempt's run id; once `follow_runs` adopted the new attempt, the pending
        slice carrying the old id was dropped as the finished attempt's and left the chain marked with nothing
        scheduled, so M2 stayed `running` forever and the note leaked into M1's buffer.

        Interpretation: the profile is "manual" so only the owner's own `/retry` acts; M2's first attempt is driven
        to its terminal failure by the per-milestone hand and the retried attempt's slices are held empty (the
        lever the neighbouring tests use), so its own buffer can be read before it emits anything; the card's view
        is fetched through the production `failed_card_view`, the very call the card source makes. `run_chain`,
        `run_watch` and `run_buffers` are the app's own bookkeeping the criterion names, not its wording."""
        from terminal_planner.tui.card_kinds import failed_card_key
        self.driver.outcomes = ("failed", "done")  # M2's first attempt fails; its retry's own attempt is held
        self.prepare(max_runs=2, level="manual")
        async with self.shell(self.controller(profile=True), size=(120, 40), follow=True) as pilot:
            await self.loaded(pilot)
            await self.panel(pilot)
            await self.until(pilot, lambda: self.app.run_chain == {"M1", "M2"})
            self.assertEqual(self.app.run_watch, "M1")  # M1 is the shown attempt
            self.driver.open_attempts.add("M2")  # M2's first attempt runs out to a terminal failure
            await self.until(pilot, lambda: self.app.snapshot.row("M2").state == "failed", timeout=15)
            self.assertEqual(self.app.run_watch, "M1")  # the shown attempt never moved
            self.driver.open_attempts.discard("M2")  # the retried attempt's observation slices stay empty
            row = self.app.snapshot.row("M2")
            key = failed_card_key(row, self.app.snapshot.version)
            main = self.main()
            main.failed_card_view(key, row)  # the card fetches its view off the loop, exactly as the source does
            await self.until(pilot, lambda: key in main.failed_cards()["views"], timeout=8)
            main.run_command("/retry", "", key)
            await self.until(pilot, lambda: self.app.snapshot.row("M2").state in ("running", "stopping"), timeout=8)
            await self.until(pilot, lambda: "M2: new attempt started." in self.app.run_buffers.get("M2", ()))
            self.assertIn("M2", self.app.run_chain)  # the new attempt has a chain of its own (C4)
            self.assertEqual(list(self.app.run_buffers["M2"]), ["M2: new attempt started."])  # its own lines
            self.assertEqual([line for line in self.app.run_buffers.get("M1", ()) if "M2" in line], [])
            self.driver.open_attempts.add("M2")  # release the retried attempt: its own slices conclude it
            await self.until(pilot, lambda: self.app.snapshot.row("M2").state == "awaiting_merge", timeout=15)
            self.assertEqual(self.app.snapshot.row("M1").state, "running")  # M1 keeps running beside it
            self.assertIn("M1", self.app.run_chain)  # and keeps its own observation
            self.assertEqual([line for line in self.app.run_buffers.get("M1", ()) if "M2" in line], [])

    async def test_c4_opening_an_attempt_adopts_the_identity_the_outcome_carries(self):
        """C4 (A9t repair): [o] on an attempt whose milestone moved on -- `open_run` found a later attempt the
        screen has not refreshed yet -- attaches *that* attempt: the outcome's own run id is adopted, so observation
        never reuses the predecessor's buffer or identity.

        Reproduction (the one the code review names): an active outcome carrying `new-run` while the milestone's
        lines still belong to `old-run` and show `M2 attempt 1: old phase`, with M1 remaining the shown attempt.
        `opened` used to call `watch_run` alone, leaving `run_buffer_id["M2"]` at `old-run` and its buffered lines in
        place; both assertions below fail then. The delivery is a plan of the app's own bookkeeping (`run_buffer_id`,
        `run_lines`/`run_buffers`), read directly as the neighbouring C4 tests read it."""
        self.prepare(max_runs=2, level="auto")
        async with self.shell(self.controller(profile=True), size=(120, 40), follow=True) as pilot:
            await self.loaded(pilot)
            await self.panel(pilot)
            await self.until(pilot, lambda: self.app.run_chain == {"M1", "M2"})
            self.assertEqual(self.app.run_watch, "M1")  # M1 keeps the shown place; the open is on M2
            old = self.app.run_buffer_id["M2"]
            self.assertIsNotNone(old)
            self.assertNotEqual(old, "new-run")
            self.app.run_buffer("M2").append("M2 attempt 1: old phase")
            self.app.opened("M2", Outcome("active", data=Token("M2", 1, 2, "new-run", "running", None, "pending")),
                            None)
            await pilot.pause(0.3)
            self.assertEqual(self.app.run_buffer_id["M2"], "new-run")  # the outcome's attempt, never the old id
            self.assertEqual(list(self.app.run_lines), [])  # the new attempt's own, empty lines
            self.assertNotIn("M2 attempt 1: old phase", list(self.app.run_lines))


class MergeEvidenceTests(ProjectTest):
    """RS6 C1: a `zplan_status` row in `awaiting_merge` carries the evidence the architect merges on, so it never
    asks the owner for a path; rows in other states keep their shape.

    A real `Controller` over a fixture session answers the status socket (as the A5t1 bridge tests drive it).
    Interpretations: "changed files against the destination" is `git diff --name-only` from the attempt's
    destination base to the result commit (the diff the end screen shows); `decision` is `autonomy.decide` on the
    profile read of the same rows job; `more` is the count of changed files beyond the 20 named."""

    def attempt(self, level="auto", export=True, tier=None):
        profile = {"preset": process.PRESET_V2, "autonomy": {"level": level},
                   "gates": {"merge": "required"}, "checks": [{"name": "unit", "argv": ["true"], "timeout_s": 60}]}
        if tier is not None:
            profile["risk"] = {"rules": [{"paths": ["**"], "tier": tier}]}
        (self.project / process.PROFILE_FILE).write_text(json.dumps(profile))
        with Authority(self.state, self.project) as authority:
            process.Profile.of(authority).accept()
        self.git("add", process.PROFILE_FILE)
        self.git("commit", "-qm", "process profile")
        self.driver = FixtureDriver(self.root / "fixture-runs", outcome="done")
        with Authority(self.state, self.project) as authority:
            authority.profile = process.Profile.of(authority)
            self.begin(authority)
            self.propose(authority)
            authority.approve(1)
            runs = MilestoneRuns(authority, self.driver, worktrees=authority.directory / "worktrees")
            record = runs.start("M1", 1, ROLES)
            if export:
                mark = None
                while record["status"] in ("submitted", "running", "stopping"):
                    _, mark = runs.poll(record, mark)
                runs.finish(record)
                self.assertEqual(record["delivery"], "awaiting_merge")
        return record

    def row(self):
        from terminal_planner.tui.controller import Controller
        controller = Controller.for_project(self.project, self.state, fixture_id="test",
                                            driver_factory=lambda _: self.driver,
                                            engine_factory=lambda *_: FixtureEngine(), profile=True)
        controller.start()
        self.addCleanup(controller.stop)
        reply = bridge.call(bridge.path_for(self.project), {"id": "r", "tool": "zplan_status", "args": {}}, timeout=20)
        self.assertNotIn("stale", reply["ok"])
        return next(item for item in reply["ok"]["rows"] if item["id"] == "M1")

    def test_c1_an_awaiting_merge_row_carries_the_merge_evidence_and_the_policy_decision(self):
        record = self.attempt()
        row = self.row()
        self.assertEqual(row["state"], "awaiting_merge")
        merge = row["merge"]
        self.assertEqual((merge["commit"], merge["branch"], merge["destination"]),
                         (record["result"]["commit"], record["result"]["branch"], "main"))
        shown = subprocess.check_output(["git", "-C", str(self.project), "diff", "--name-only",
                                         record["destination"]["base"], record["result"]["commit"]], text=True).split()
        self.assertTrue(shown)
        self.assertEqual(merge["files"], shown)
        self.assertEqual((merge["more"], merge["gate"], merge["checks"], merge["decision"]),
                         (0, "required", ["unit"], "allow"))

    def test_c1_the_decision_is_the_policy_for_the_level_and_the_risk(self):
        """p2a A4: the row's `decision` follows the merge matrix: supervised asks on a high-risk change and allows a
        low-risk one, manual asks whatever the risk (every path is put at one tier by a `**` rule)."""
        for level, tier, decision in (("supervised", "high", "ask"), ("supervised", "low", "allow"),
                                      ("manual", "low", "ask")):
            with self.subTest(level=level, tier=tier):
                self.setUp()
                self.attempt(level=level, tier=tier)
                self.assertEqual(self.row()["merge"]["decision"], decision)

    def test_c1_files_are_cut_at_twenty_and_the_rest_counted(self):
        from terminal_planner.tui import controller as controller_module
        self.attempt()
        names = ["f%02d.txt" % number for number in range(25)]
        listing = types.SimpleNamespace(returncode=0, stdout="\0".join(names).encode())
        with patch.object(controller_module, "git_call", return_value=listing):
            merge = self.row()["merge"]
        self.assertEqual((merge["files"], merge["more"]), (names[:20], 5))

    def test_c1_rows_in_other_states_have_no_merge(self):
        self.attempt(export=False)
        row = self.row()
        self.assertEqual(row["state"], "running")
        self.assertNotIn("merge", row)
