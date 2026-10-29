"""A5t1 C1-C4: the live Controller as the architect's action-tool endpoint (socket bridge, status, start, stop,
autonomy policy).

A real `Controller` runs a fixture session over an approved plan and serves `bridge.Endpoint`; the tests drive it
with the raw socket client (`bridge.call`) and, for the tool contract, through the real stdio MCP server
(`architect_tools`) as a subprocess with `--controller`.

Interpretations (the brief leaves them open):
- The wire reply is `{"id", "ok"}` on success and `{"id", "error": <family>, "message": <text>}` on failure
  (C1's `{id, error: family, message}`); the *status* payload nests a request's own error as `{"family",
  "message"}`; `zplan_status` answers `{"requests", "revision", "rows"}`.
- A status posts the rows job and waits for it (bounded, 2 s, on the socket thread); "rows unavailable" is only
  what a status answers when no rows job has ever finished within the bound, and then it carries `stale`. A snapshot
  of an approved plan names the milestone state, attempt and run id, and a session without an approved plan still
  answers rows `()` with `revision` None.
- The "closing after admission" case holds one action inside its job with a gated `Delivery.preview`, so the job is
  admitted and running when `begin_closing` lands; the quit then waits for it as for any admitted job.
- The policy is decided from the live profile the delivery service enforces (`Delivery.guard`, the same read the
  preview is built on), never from a value in the request; the level is read once on the worker, in the same job
  right after the preview, and its digest is bound to the preview's, so a profile that moved in between is the
  `ProfileChanged` refusal (not a policy answer read from the new profile).
- The endpoint's own teardown is file I/O (close, unlink, rmtree), so `stop` seals and sets `closing` first and
  removes the socket after that: the UI-side hand-over re-checks `closing`, and any window before it is a window
  where a job finishing now still reaches a screen that is going away (pinned by a test).

A5t2b note (interpretations):
- "`Planning.edit` in one `_plan_job`" (C1): the bridge admits `zplan_edit_plan` as exactly one `_plan_job` (the
  plan service's own job, as the owner's submit/revise use). The endpoint's socket thread posts that job itself,
  so it is never nested inside the bridge job (which would deadlock the serial worker); its request bookkeeping
  (`open`/`running`/`finish`) and the "ready" hand-off ride that same job.
- The "ready" verdict reaches the UI through `Controller.on_plan_submission` (the app sets it to a
  worker-callable that shows it with `after_submission`, so the planner watch dispatches the revision); the
  controller-side tests here install their own recorder to pin that hand-off, and the app wiring lives in
  `ZplanApp.plan_submission`."""

import copy
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

from terminal_planner import autonomy, bridge, delivery, milestone, process
from terminal_planner.authority import Blocked, decode
from terminal_planner.engine import FixtureEngine
from terminal_planner.runs import FixtureDriver, MilestoneRuns
import test_terminal_planner as tp
from test_terminal_planner import ROLES
from test_parallel_runs import parallel_plan

ROOT = Path(__file__).resolve().parent.parent
CODE = ("import sys; sys.path.insert(0, %s); from terminal_planner.architect_tools import main; "
        "sys.exit(main(sys.argv[1:]))" % json.dumps(str(ROOT)))


class BridgeCase(tp.ProjectTest):
    def setUp(self):
        super().setUp()
        self.driver = FixtureDriver(self.root / "fixture-runs")

    # Setup ---------------------------------------------------------------------

    def plan(self, attempts=0, profile=False):
        """The approved fixture plan. `attempts` extra M1 attempts are created; every one but the last is stopped,
        so the last is the running latest attempt (attempts=0 leaves M1 ready). `profile` binds the accepted profile
        (an already-`write_auto_profile`d file) while the plan is frozen, so its gate digest is the profile's."""
        with tp.Authority(self.state, self.project) as authority:
            if profile:
                authority.profile = process.Profile.of(authority)
            self.begin(authority)
            self.propose(authority)
            authority.approve(1)
            runs = MilestoneRuns(authority, self.driver, worktrees=authority.directory / "worktrees")
            made = []
            for index in range(attempts):
                record = runs.start("M1", 1, ROLES)
                if index < attempts - 1:
                    runs.stop(record)
                    self.finish(runs, record)
                made.append(record)
            return made

    def proposed(self, profile=False):
        """The fixture plan left as a current `proposed` revision awaiting approval (no attempt): what the approve
        tool acts on. `profile` as in `plan`."""
        with tp.Authority(self.state, self.project) as authority:
            if profile:
                authority.profile = process.Profile.of(authority)
            self.begin(authority)
            self.propose(authority)

    def two_revisions(self):
        """Revision 1 approved and revision 2 `proposed` and current: the status row's tokens and the current plan
        revision name different revisions (C1's proposed-over-approved example)."""
        with tp.Authority(self.state, self.project) as authority:
            self.begin(authority)
            self.propose(authority)
            authority.approve(1)
            authority.begin("Second goal", ROLES, "fixture")
            self.propose(authority)

    def attempt(self, outcome):
        """The approved fixture plan with one M1 attempt driven by `outcome` to its terminal state; the driver used
        is `outcome`'s (the controller reads the same one)."""
        self.driver = FixtureDriver(self.root / "fixture-runs", outcome=outcome)
        with tp.Authority(self.state, self.project) as authority:
            self.begin(authority)
            self.propose(authority)
            authority.approve(1)
            runs = MilestoneRuns(authority, self.driver, worktrees=authority.directory / "worktrees")
            record = runs.start("M1", 1, ROLES)
            self.finish(runs, record)
            return record

    @staticmethod
    def finish(runs, record):
        mark = None
        for _ in range(200):
            if record["status"] not in ("submitted", "running", "stopping"):
                return record
            _, mark = runs.poll(record, mark)
        raise AssertionError("the fixture run did not finish")

    def write_auto_profile(self):
        """An accepted `zplan.default/2` profile with `autonomy.level` auto: the /2 preset plus the file as its
        source, committed so the milestone start sees a clean project."""
        (self.project / process.PROFILE_FILE).write_text(json.dumps({"preset": process.PRESET_V2,
                                                                     "autonomy": {"level": "auto"}}))
        with tp.Authority(self.state, self.project) as authority:
            process.Profile.of(authority).accept()
        self.git("add", process.PROFILE_FILE)
        self.git("commit", "-qm", "process profile")

    def write_profile(self, level="auto", merge="off", checks=None):
        """An accepted `zplan.default/2` profile at `level` with `gates.merge` and optional frozen checks, committed
        so the merge sees a clean, current project (the A5t2b merge tests)."""
        profile = {"preset": process.PRESET_V2, "autonomy": {"level": level}, "gates": {"merge": merge}}
        if checks is not None:
            profile["checks"] = checks
        (self.project / process.PROFILE_FILE).write_text(json.dumps(profile))
        with tp.Authority(self.state, self.project) as authority:
            process.Profile.of(authority).accept()
        self.git("add", process.PROFILE_FILE)
        self.git("commit", "-qm", "process profile")

    def moves_the_profile_to(self, level):
        """A `side_effect` for a patched `autonomy.status_of`: it answers the read as it was, then changes and
        commits the accepted profile to `level`, so the very next profile read sees another digest."""
        read = autonomy.status_of

        def owner_changes_profile(profile):
            status = read(profile)
            (self.project / process.PROFILE_FILE).write_text(json.dumps(
                {"preset": process.PRESET_V2, "autonomy": {"level": level}}))
            self.git("add", process.PROFILE_FILE)
            self.git("commit", "-qm", "owner changes autonomy to %s" % level)
            return status

        return owner_changes_profile

    def moves_the_profile_on_the_policy_read(self):
        """A `side_effect` for a patched `autonomy.status_of`: it answers the read as it was, then changes and
        commits the accepted profile from auto to manual, so the very next profile read — the one the action
        itself enforces — sees another digest. The A5t2a C4 race the binding must refuse."""
        read = autonomy.status_of

        def owner_changes_profile(profile):
            status = read(profile)
            (self.project / process.PROFILE_FILE).write_text(json.dumps(
                {"preset": process.PRESET_V2, "autonomy": {"level": "manual"}}))
            self.git("add", process.PROFILE_FILE)
            self.git("commit", "-qm", "owner changes autonomy to manual")
            return status

        return owner_changes_profile

    def controller(self, **kw):
        from terminal_planner.tui.controller import Controller
        kw.setdefault("driver_factory", lambda _: self.driver)
        kw.setdefault("engine_factory", lambda *_: FixtureEngine())
        controller = Controller.for_project(self.project, self.state, fixture_id="test", **kw)
        controller.start()
        self._controllers.append(controller)
        self.addCleanup(controller.stop)
        return controller

    def controller_stop(self):
        """Stop every controller this test started (releasing the session lock before reading the store)."""
        while self._controllers:
            self._controllers.pop().stop()

    @property
    def _controllers(self):
        controllers = getattr(self, "_started_controllers", None)
        if controllers is None:
            controllers = self._started_controllers = []
        return controllers

    def call(self, tool, args=None, rid="req"):
        return bridge.call(bridge.path_for(self.project), {"id": rid, "tool": tool, "args": args or {}}, timeout=20)

    def entry(self, rid):
        status = self.call("zplan_status")["ok"]
        return next(entry for entry in status["requests"] if entry["id"] == rid)

    def rows(self, timeout=8.0):
        payload = self.call("zplan_status")["ok"]  # the status itself waits for a fresh rows job
        self.assertNotIn("stale", payload)
        return payload

    def plan_until(self, predicate, timeout=8.0):
        """The status `plan` once it satisfies `predicate` (its rows job runs behind a coalesced refresh)."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            plan = self.call("zplan_status")["ok"]["plan"]
            if plan != "plan unavailable" and predicate(plan):
                return plan
            time.sleep(0.05)
        raise AssertionError("the plan never matched")

    def awaiting_merge(self, level="auto", merge="required", checks=None):
        """The approved fixture plan with M1 finished and exported (delivery awaiting_merge) under an accepted
        profile that `level`/`merge`/`checks` configure, ready for the architect's merge tool.

        `checks` default to one trivial passing check, which a `gates.merge: required` merge runs on its candidate
        (a required gate with no checks is refused by the gate itself)."""
        if checks is None and merge == "required":
            checks = [{"name": "unit", "argv": ["true"], "timeout_s": 60}]
        self.write_profile(level=level, merge=merge, checks=checks)
        self.driver = FixtureDriver(self.root / "fixture-runs", outcome="done")
        with tp.Authority(self.state, self.project) as authority:
            authority.profile = process.Profile.of(authority)
            self.begin(authority)
            self.propose(authority)
            authority.approve(1)
            runs = MilestoneRuns(authority, self.driver, worktrees=authority.directory / "worktrees")
            record = runs.start("M1", 1, ROLES)
            self.finish(runs, record)
            runs.finish(record)  # export the accepted result: delivery awaiting_merge
            self.assertEqual(record["delivery"], "awaiting_merge")
        return record

    # C1 ------------------------------------------------------------------------

    def test_c1_the_endpoint_is_a_short_private_socket_and_removes_it_on_stop(self):
        controller = self.controller()
        path = bridge.path_for(self.project)
        self.assertTrue(os.path.isabs(path) and path.startswith("/tmp"))
        self.assertLess(len(path.encode("utf-8")), 100)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.dirname(path)).st_mode), 0o700)
        reply = self.call("zplan_status", rid="one")
        self.assertEqual(reply["id"], "one")
        self.assertIn("requests", reply["ok"])
        directory = os.path.dirname(path)
        controller.stop()
        self.assertFalse(os.path.exists(directory))
        self.assertFalse(os.path.exists(path))
        self.assertIsNone(bridge.path_for(self.project))

    def test_c1_closing_before_admission_refuses_without_a_job(self):
        controller = self.controller()
        controller.begin_closing()
        reply = self.call("zplan_start", {"milestone": "M1", "revision": 1}, rid="x")
        self.assertEqual(reply["id"], "x")
        self.assertEqual(reply["error"], "architect.closing")
        self.assertFalse(controller.mutating())
        self.assertEqual(controller._pending, set())  # no job was posted
        self.assertEqual(self.entry("x")["error"]["family"], "architect.closing")

    def test_c1_the_seal_is_up_before_the_endpoint_is_torn_down(self):
        """Regression (A5t1): `stop` seals and sets `closing` before the endpoint's file I/O, so a job finishing
        now is dropped by the UI-side hand-over whatever the teardown costs (the first ordering let a delivery
        reach the going screen)."""
        controller = self.controller()
        seen = {}
        real_close = bridge.Endpoint.close

        def close(endpoint):
            seen["closing"] = controller.closing  # the UI-side guard is already up when the teardown runs
            return real_close(endpoint)

        with patch.object(bridge.Endpoint, "close", close):
            controller.stop()
        self.assertTrue(seen["closing"])
        self.assertFalse(controller.mutating())

    def test_c1_closing_after_admission_lets_the_job_finish(self):
        self.plan(0)
        controller = self.controller()
        entered, gate = threading.Event(), threading.Event()
        reply = {}
        real_preview = delivery.Delivery.preview

        def gated(self, milestone, roles):
            entered.set()
            gate.wait(10)
            return real_preview(self, milestone, roles)

        with patch.object(delivery.Delivery, "preview", gated):
            thread = threading.Thread(target=lambda: reply.setdefault("v", self.call(
                "zplan_start", {"milestone": "M1", "revision": 1}, rid="a")))
            thread.start()
            self.assertTrue(entered.wait(5))       # admitted into its job and running
            controller.begin_closing()             # the quit begins while the job runs
            gate.set()
            controller.stop()                      # quitting waits for the admitted job, as for any
            thread.join(10)
        self.assertTrue(reply.get("v"), "the admitted job's reply never arrived")
        self.assertEqual(reply["v"]["error"], "autonomy.ask")  # the job ran to its policy decision
        self.assertFalse(controller.mutating())

    def test_c1_the_wait_is_bounded_and_status_follows_queued_running_done(self):
        self.plan(0)
        controller = self.controller()
        hold, gate, entered = threading.Event(), threading.Event(), threading.Event()
        controller.post("hold", lambda app: hold.wait(10))  # the worker is busy, so the action stays queued
        with patch.object(bridge, "TIMEOUT", 0.2):
            reply = self.call("zplan_start", {"milestone": "M1", "revision": 1}, rid="X")
        self.assertEqual(reply["error"], "architect.controller_timeout")
        self.assertEqual(reply["message"], "outcome unknown")
        self.assertEqual(self.entry("X")["state"], "queued")

        real_preview = delivery.Delivery.preview

        def gated(self, milestone, roles):
            entered.set()
            gate.wait(10)
            return real_preview(self, milestone, roles)

        with patch.object(delivery.Delivery, "preview", gated):
            hold.set()
            self.assertTrue(entered.wait(5))
            self.assertEqual(self.entry("X")["state"], "running")  # released into the job
            gate.set()
            end = time.monotonic() + 8
            while self.entry("X")["state"] != "done" and time.monotonic() < end:
                time.sleep(0.05)
        entry = self.entry("X")
        self.assertEqual(entry["state"], "done")
        self.assertEqual(entry["error"]["family"], "autonomy.ask")  # done, with its result

    def test_c1_shutdown_never_joins_a_blocked_request_thread(self):
        entered, gate = threading.Event(), threading.Event()

        def dispatch(request):
            entered.set()
            gate.wait(10)
            return {"never": True}, None

        endpoint = bridge.Endpoint(dispatch)
        path = endpoint.start()
        self.addCleanup(gate.set)
        threading.Thread(target=lambda: bridge.call(path, {"id": "z", "tool": "zplan_status"}, timeout=20),
                         daemon=True).start()
        self.assertTrue(entered.wait(5))
        start = time.monotonic()
        endpoint.close()
        self.assertLess(time.monotonic() - start, 2.0)  # close did not wait for the request thread
        self.assertIsNone(endpoint.path)
        gate.set()

    # C2 ------------------------------------------------------------------------

    def test_c2_the_mcp_server_reaches_the_controller_and_every_result_carries_the_id(self):
        self.plan(0)
        self.controller()
        proc = subprocess.Popen([sys.executable, "-I", "-c", CODE, "--project", str(self.project),
                                 "--controller", bridge.path_for(self.project)],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self._close, proc)
        self._rpc(proc, "initialize", {"protocolVersion": "2025-06-18"})
        tools = self._rpc(proc, "tools/list", {})["result"]["tools"]
        self.assertEqual([t["name"] for t in tools],
                         ["zplan_list_files", "zplan_read_file", "zplan_search", "zplan_state", "zplan_state_update",
                          "zplan_status", "zplan_start",
                          "zplan_stop", "zplan_approve_plan", "zplan_resume", "zplan_rebrief", "zplan_edit_plan",
                          "zplan_revise_plan", "zplan_merge", "zplan_propose_commit"])
        status = json.loads(self._call(proc, "zplan_status", {})["result"]["content"][0]["text"])
        self.assertTrue(status["id"])
        self.assertIn("ok", status)
        stale = json.loads(self._call(proc, "zplan_start", {"milestone": "M1", "revision": 9})["result"]
                           ["content"][0]["text"])
        self.assertEqual(stale["error"]["family"], "action.refused")
        request_id = stale["id"]
        found = self.entry(request_id)
        self.assertEqual(found["state"], "done")
        self.assertEqual(found["error"]["family"], "action.refused")

    @staticmethod
    def _close(proc):
        try:
            proc.stdin.close()
            proc.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            proc.kill()
        finally:
            for pipe in (proc.stdout, proc.stderr):
                try:
                    pipe.close()
                except OSError:
                    pass

    @staticmethod
    def _rpc(proc, method, params):
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode() + b"\n")
        proc.stdin.flush()
        return json.loads(proc.stdout.readline())

    @classmethod
    def _call(cls, proc, name, arguments):
        return cls._rpc(proc, "tools/call", {"name": name, "arguments": arguments})

    def test_c2_status_answers_at_once_with_rows_of_the_approved_plan(self):
        self.plan(1)
        self.controller()
        payload = self.call("zplan_status", rid="R")["ok"]  # C2: the first status already answers real rows
        self.assertNotIn("stale", payload)
        self.assertEqual(payload["revision"], 1)
        row = next(item for item in payload["rows"] if item["id"] == "M1")
        self.assertEqual(row["state"], "running")
        self.assertEqual(row["attempt"], 1)
        self.assertTrue(row["run_id"])

    def test_rc3_status_is_fresh_after_a_state_change_and_stale_when_the_worker_is_held(self):
        """RC3 C1/C3 (regression of the 0.6.0 smoke): a status answers from the rows job it has just posted, so a
        state change is seen by the very next status; with the worker held past the bound it answers the last rows
        plus `stale: true` within the bound, and the worker is not blocked by it.

        Interpretation: the bound is `controller.STATUS_WAIT` (2 s), patched down here so the test stays fast."""
        from terminal_planner.tui import controller as controller_module
        self.awaiting_merge()
        controller = self.controller()
        payload = self.rows()
        row = next(item for item in payload["rows"] if item["id"] == "M1")
        self.assertEqual((row["state"], row["token"]["milestone"]), ("awaiting_merge", "M1"))  # same answer
        hold = threading.Event()
        controller.post("hold", lambda app: hold.wait(10))
        self.addCleanup(hold.set)
        with patch.object(controller_module, "STATUS_WAIT", 0.3):
            started = time.monotonic()
            held = self.call("zplan_status")["ok"]
            self.assertLess(time.monotonic() - started, 3)
        self.assertIs(held["stale"], True)
        self.assertEqual(held["rows"], payload["rows"])  # the last rows, no exception
        hold.set()
        self.assertNotIn("stale", self.call("zplan_status")["ok"])

    # C3 ------------------------------------------------------------------------

    def test_c3_a_start_for_another_revision_is_refused_with_changed(self):
        self.plan(0)
        self.controller()
        reply = self.call("zplan_start", {"milestone": "M1", "revision": 99}, rid="q")
        self.assertEqual(reply["error"], "action.refused")
        self.assertIn("the plan was revised", reply["message"])

    def test_c3_a_stale_run_id_is_refused_and_the_latest_attempt_keeps_running(self):
        first, second = self.plan(2)
        self.controller()
        reply = self.call("zplan_stop", {"milestone": "M1", "run_id": first["run_id"]}, rid="z")
        self.assertEqual(reply["error"], "action.refused")
        self.assertIn("another attempt was started", reply["message"])
        row = next(item for item in self.rows()["rows"] if item["id"] == "M1")
        self.assertEqual(row["run_id"], second["run_id"])  # B was not stopped
        self.assertEqual(row["state"], "running")
        self.assertEqual(row["attempt"], 2)

    def test_c3_stopping_the_latest_attempt_is_allowed(self):
        first, second = self.plan(2)
        self.controller()
        reply = self.call("zplan_stop", {"milestone": "M1", "run_id": second["run_id"]}, rid="y")
        self.assertIn("ok", reply)
        self.assertEqual(reply["ok"]["run_id"], second["run_id"])
        self.assertEqual(reply["ok"]["attempt"], 2)

    def test_c3_a_stop_without_a_current_plan_is_refused_with_changed(self):
        """Regression (A5t1 C3): a fresh session has no plan, so `Delivery.latest` has no revision to index; the
        stop must be today's `Changed` refusal, never an internal error."""
        self.controller()  # no approved plan in this session
        reply = self.call("zplan_stop", {"milestone": "M1", "run_id": "old-attempt"}, rid="n")
        self.assertEqual(reply["error"], "action.refused")
        self.assertIn("another attempt was started", reply["message"])

    def test_c3_a_start_without_a_current_plan_is_refused_with_changed(self):
        """Regression (A5t1 C3): a fresh session has no plan, and `Delivery.plan()` is the nullable lookup; the
        start must be today's `Changed` refusal ("the plan was revised"), never the empty-store read of
        `Authority.current` (which raises before any check) nor another message."""
        self.controller()  # no approved plan in this session
        reply = self.call("zplan_start", {"milestone": "M1", "revision": 1}, rid="np")
        self.assertEqual(reply["error"], "action.refused")
        self.assertIn("the plan was revised", reply["message"])

    def test_c3_the_profile_changed_refusal_of_a_start_is_kept(self):
        self.write_auto_profile()
        self.plan(0)
        self.controller(profile=True)

        def changed(self, preview, roles):
            raise process.ProfileChanged("The process profile changed after the preview: confirm again.")

        with patch.object(delivery.Delivery, "start", changed), patch.object(autonomy, "AUTOMATIC", True):
            reply = self.call("zplan_start", {"milestone": "M1", "revision": 1}, rid="c")
        self.assertEqual(reply["error"], "process.changed")
        self.assertIn("The process profile changed", reply["message"])

    def test_c3_a_real_profile_change_after_the_preview_is_refused_with_process_changed(self):
        """Regression (A5t1 C3/C4): the policy reads the profile the preview was built on, so a profile that moves
        between the preview and the decision is today's `ProfileChanged` refusal - not a policy answer read from the
        new profile (auto -> manual would otherwise be `autonomy.ask`)."""
        self.write_auto_profile()
        self.plan(0)
        self.controller(profile=True)
        case = self
        real_preview = delivery.Delivery.preview

        def move_after_preview(delivery_self, milestone, roles):
            preview = real_preview(delivery_self, milestone, roles)
            (case.project / process.PROFILE_FILE).write_text(
                json.dumps({"preset": process.PRESET_V2, "autonomy": {"level": "manual"}}))
            return preview

        with patch.object(delivery.Delivery, "preview", move_after_preview), \
                patch.object(autonomy, "AUTOMATIC", True):
            reply = self.call("zplan_start", {"milestone": "M1", "revision": 1}, rid="moved")
        self.assertEqual(reply["error"], "process.changed")
        self.assertIn("changed", reply["message"])

    # C4 ------------------------------------------------------------------------

    def test_c4_a_current_start_asks_the_owner_without_a_profile(self):
        """A5t1 C4/A5t2b C3: no profile is the manual level, so a current start still asks the owner even with the
        release gate on (the chosen reading: a session without a profile can never be the architected one)."""
        self.plan(0)
        self.controller()
        reply = self.call("zplan_start", {"milestone": "M1", "revision": 1}, rid="p")
        self.assertEqual(reply["error"], "autonomy.ask")
        self.assertIn("by the owner in the zplan interface", reply["message"])

    def test_c4_invalid_arguments_are_refused_before_the_revision_check(self):
        self.plan(0)
        self.controller()
        for arguments in ({"milestone": "M1"}, {"milestone": "M1", "revision": True}, {"milestone": "", "revision": 1}):
            with self.subTest(arguments=arguments):
                reply = self.call("zplan_start", arguments, rid="i")
                self.assertEqual(reply["error"], "architect.request_invalid")

    def test_c4_a_revision_below_one_is_refused_as_request_invalid(self):
        """Regression (A5t1 C4): the tool schema's minimum is 1, so a lower revision is a bad argument, refused
        before the freshness check (it can never name the approved revision)."""
        self.plan(0)
        self.controller()
        for revision in (0, -1):
            with self.subTest(revision=revision):
                reply = self.call("zplan_start", {"milestone": "M1", "revision": revision}, rid="r0")
                self.assertEqual(reply["error"], "architect.request_invalid")

    def test_c4_an_unknown_argument_refuses_a_start_before_the_revision_check(self):
        """Regression (A5t1 C4): the tool schema is `additionalProperties=false`, so an extra key (here `run_id`,
        which only `zplan_stop` takes) is an invalid argument, refused before freshness - not a `Changed`."""
        self.plan(0)
        self.controller()
        reply = self.call("zplan_start", {"milestone": "M1", "revision": 1, "run_id": "x"}, rid="ux")
        self.assertEqual(reply["error"], "architect.request_invalid")
        self.assertIn("Unknown argument", reply["message"])

    def test_c4_an_unknown_argument_refuses_a_stop_without_stopping_the_attempt(self):
        """Regression (A5t1 C4): the same refusal for `zplan_stop`; the extra key must not reach an action, so
        the running attempt is left running."""
        made = self.plan(1)
        self.controller()
        reply = self.call("zplan_stop", {"milestone": "M1", "run_id": made[-1]["run_id"], "revision": 1}, rid="us")
        self.assertEqual(reply["error"], "architect.request_invalid")
        self.assertIn("Unknown argument", reply["message"])
        row = next(item for item in self.rows()["rows"] if item["id"] == "M1")
        self.assertEqual(row["run_id"], made[-1]["run_id"])
        self.assertEqual(row["state"], "running")  # the attempt was not touched

    def test_c1_a_request_without_an_id_is_refused_before_any_job(self):
        """Regression (critic a5t1-merge P2): a raw request with no id must not reach an action (the reply would
        have nowhere to go): refused at the envelope, the running attempt is left running."""
        made = self.plan(1)
        self.controller()
        path = bridge.path_for(self.project)
        for request in ({"tool": "zplan_stop", "args": {"milestone": "M1", "run_id": made[-1]["run_id"]}},
                        {"id": "x" * (bridge.MAX_ID + 1), "tool": "zplan_stop",
                         "args": {"milestone": "M1", "run_id": made[-1]["run_id"]}}):
            reply = bridge.call(path, request, timeout=20)
            self.assertEqual(reply["error"], "architect.request_invalid")
            self.assertIsNone(reply["id"])
        row = next(item for item in self.rows()["rows"] if item["id"] == "M1")
        self.assertEqual(row["state"], "running")
        self.assertEqual(self.call("zplan_status")["ok"]["requests"], [])

    def test_c2_the_registry_is_bounded_so_status_stays_one_readable_line(self):
        """Regression (critic a5t1-merge P2): many long-id requests must not grow the status reply past the
        client's line bound: status still parses, the registry keeps the newest MAX_REQUESTS entries."""
        self.plan()
        self.controller()
        for index in range(bridge.MAX_REQUESTS + 6):
            rid = ("%03d" % index) + "y" * (bridge.MAX_ID - 3)
            self.call("zplan_start", {"milestone": "M1", "revision": 99}, rid=rid)
        requests = self.call("zplan_status")["ok"]["requests"]
        self.assertEqual(len(requests), bridge.MAX_REQUESTS)
        self.assertTrue(requests[-1]["id"].startswith("%03d" % (bridge.MAX_REQUESTS + 5)))
        self.assertTrue(requests[0]["id"].startswith("006"))

    def test_c2_a_full_registry_of_unfinished_requests_refuses_before_admission(self):
        """Regression (critic a5t1-merge2 P2): only finished entries are dropped; when every kept entry is still
        unfinished, or the id is already known, `open` refuses (no job), and `finish` never re-creates an entry."""
        registry = bridge.Registry()
        for index in range(bridge.MAX_REQUESTS):
            self.assertTrue(registry.open("r%d" % index, "zplan_start"))
        self.assertFalse(registry.open("late", "zplan_start"))
        self.assertFalse(registry.open("r1", "zplan_stop"))
        registry.finish("late", ok=1)
        ids = [entry["id"] for entry in registry.snapshot()]
        self.assertEqual(len(ids), bridge.MAX_REQUESTS)
        self.assertEqual(ids[0], "r0")
        registry.finish("r5", ok=1)
        self.assertTrue(registry.open("late", "zplan_start"))
        ids = [entry["id"] for entry in registry.snapshot()]
        self.assertNotIn("r5", ids)
        self.assertEqual(len(ids), bridge.MAX_REQUESTS)

    def test_c1_an_oversized_reply_keeps_the_request_id(self):
        """Regression (critic a5t1-merge2 P2): a reply over the line bound becomes a bounded failure that still
        carries the validated request id."""
        endpoint = bridge.Endpoint(lambda request: ("z" * (bridge.MAX_LINE + 10), None))
        path = endpoint.start()
        self.addCleanup(endpoint.close)
        reply = bridge.call(path, {"id": "request-x", "tool": "zplan_status", "args": {}}, timeout=20)
        self.assertEqual(reply["id"], "request-x")
        self.assertEqual(reply["error"], "architect.request_invalid")

    def test_c1_a_slow_request_line_is_cut_by_one_deadline(self):
        """Regression (critic a5t1-merge P2): the read deadline covers the whole line, not each recv: a sender
        trickling a byte faster than any per-recv timeout is still cut at the deadline."""
        import socket
        left, right = socket.socketpair()
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        stop = threading.Event()

        def trickle():
            while not stop.is_set():
                try:
                    left.send(b"x")
                except OSError:
                    return
                time.sleep(0.02)

        threading.Thread(target=trickle, daemon=True).start()
        began = time.monotonic()
        line = bridge._read_line(right, limit=200, timeout=0.3)  # a broken deadline reads 200 bytes in ~4 s
        spent = time.monotonic() - began
        stop.set()
        self.assertLess(spent, 1.5)
        self.assertTrue(line)  # what arrived before the deadline, never a wait for the newline

    def test_c4_with_automatic_and_an_auto_profile_the_run_starts_and_rows_show_it(self):
        self.write_auto_profile()
        self.plan(0)
        self.controller(profile=True)
        with patch.object(autonomy, "AUTOMATIC", True):
            reply = self.call("zplan_start", {"milestone": "M1", "revision": 1}, rid="s")
        self.assertIn("ok", reply)
        self.assertEqual(reply["ok"]["milestone"], "M1")
        self.assertEqual(reply["ok"]["attempt"], 1)
        self.assertTrue(reply["ok"]["run_id"])
        row = next(item for item in self.rows()["rows"] if item["id"] == "M1")
        self.assertEqual(row["run_id"], reply["ok"]["run_id"])
        self.assertEqual(row["state"], "running")

    # A5t2a C1 -------------------------------------------------------------------

    def test_c1_the_status_carries_each_rows_token_and_the_current_revision(self):
        """A5t2a C1: every row carries its attempt's `Token` as a plain object (None without an attempt), and the
        payload names the current revision's version, status and gate verdict.

        Interpretation: before the first rows job the payload answers `plan unavailable`, like `rows unavailable`
        for the rows, when no rows job has finished; an empty rows list is the JSON list `[]`, not an empty tuple."""
        self.plan(1)
        self.controller()
        payload = self.rows()
        row = next(item for item in payload["rows"] if item["id"] == "M1")
        token = row["token"]
        self.assertEqual(set(token), {"milestone", "plan_revision", "attempt", "run_id", "status", "outcome",
                                      "delivery"})
        self.assertEqual((token["milestone"], token["attempt"]), ("M1", 1))
        self.assertEqual(token["run_id"], row["run_id"])
        self.assertEqual({k: v for k, v in payload["plan"].items() if k != "proposal"},
                         {"version": 1, "status": "approved", "verdict": "accepted", "findings": "Fixture only; no semantic model review."})
        self.assertIsInstance(payload["plan"]["proposal"], dict)  # the full current proposal (A5t2b C1)
        waiting = next(item for item in payload["rows"] if item["id"] == "M2")
        self.assertIsNone(waiting["token"])  # no attempt yet

    def test_c1_a_proposed_revision_over_an_approved_one_is_named(self):
        """A5t2a C1: when revision 2 is proposed over an approved revision 1, `plan` names 2 `proposed` (with its
        gate verdict), even though the approved plan's rows name no current revision."""
        self.two_revisions()
        self.controller()
        payload = self.rows()
        self.assertEqual({k: v for k, v in payload["plan"].items() if k != "proposal"},
                         {"version": 2, "status": "proposed", "verdict": "accepted", "findings": "Fixture only; no semantic model review."})
        self.assertEqual(payload["rows"], [])
        self.assertIsNone(payload["revision"])  # the rows name the approved plan, and there is none current

    def test_c1_a_rejected_gate_is_named_with_its_verdict(self):
        """A5t2a C1: a current revision the plan gate rejected still carries its version, status and gate verdict."""
        with tp.Authority(self.state, self.project) as authority:
            self.begin(authority)
            FixtureEngine(scenario="exhausted").proposal(authority, lambda _: None)
            findings = authority.current["evidence"]["findings"]
        self.controller()
        self.assertEqual({k: v for k, v in self.rows()["plan"].items() if k != "proposal"},
                         {"version": 1, "status": "review_exhausted", "verdict": "rejected", "findings": findings})
        self.assertIn("the plan is still too broad", findings)  # F1: the architect reads why it was rejected

    def test_a10_b1_the_architect_gets_one_revision_after_a_rejection_then_the_owner_decides(self):
        """A10 B1: owner r1 rejected -> `zplan_revise_plan` makes r2; r2 rejected -> both revise and edit refuse
        ("the owner decides now") with nothing written, also after a restart; the owner's r3 rejected -> the
        architect may revise once more (r4). Interpretation: r2's and r3's rejections are written by the test (the
        fixture planner is not run); the brake reads only the store."""
        from terminal_planner.tui.controller import OBSERVE

        def session():  # the architect's session: its feed port asked, the first observation bootstraps the feed
            controller = self.controller()
            controller.feed_port()
            controller.post(OBSERVE, lambda app: None, lambda result, error: None)
            self.rows()

        def reject(feedback=None):
            with tp.Authority(self.state, self.project) as authority:
                if feedback:
                    authority.begin("Requested feature", ROLES, "fixture", feedback=feedback)  # the owner's revision
                FixtureEngine(scenario="exhausted").proposal(authority, lambda _: None)
        with tp.Authority(self.state, self.project) as authority:
            self.begin(authority)
        reject()
        session()
        self.assertEqual(self.call("zplan_revise_plan", {"revision": 1, "feedback": "narrow it"})["ok"]["revision"], 2)
        self.controller_stop()
        reject()  # the planner rejects the architect's r2
        for restart in range(2):  # the second pass runs on a fresh controller
            session()
            for tool, args in (("zplan_revise_plan", {"revision": 2, "feedback": "narrow it more"}),
                               ("zplan_edit_plan", {"revision": 2, "plan": {"requirements": []}})):
                reply = self.call(tool, args, rid="%s%d" % (tool, restart))
                self.assertEqual(reply["error"], "action.refused", reply)
                self.assertIn("the owner decides now", reply["message"])
            # nothing written: the current revision is still r2
            self.assertEqual(self.plan_until(lambda plan: plan["version"] == 2)["status"], "review_exhausted")
            self.controller_stop()
        reject("the owner asks")  # the owner's r3, rejected
        session()
        self.assertEqual(self.call("zplan_revise_plan", {"revision": 3, "feedback": "once"}, rid="again")["ok"]["revision"], 4)

    # A5t2a C2 -------------------------------------------------------------------

    def test_c2_the_new_tools_are_mutating_jobs_and_every_result_names_the_id(self):
        """A5t2a C2: approve, resume and rebrief travel as `mutating=True` jobs through the live bridge, and their
        results and errors name the request id they used."""
        self.plan(0)
        controller = self.controller()
        reply = self.call("zplan_approve_plan", {"revision": 1}, rid="ap")
        self.assertEqual(reply["id"], "ap")
        self.assertEqual(reply["error"], "autonomy.ask")  # current revision, but the release gate asks the owner
        entry = self.entry("ap")
        self.assertEqual((entry["state"], entry["error"]["family"]), ("done", "autonomy.ask"))
        controller.begin_closing()  # a mutating job is refused once quitting began, never cut like a slice
        closed = self.call("zplan_approve_plan", {"revision": 1}, rid="ap2")
        self.assertEqual(closed["error"], "architect.closing")
        self.assertNotIn("zplan_approve_plan", controller._pending)  # no job was posted for the refusal

    def test_c2_a_rebrief_starts_a_new_attempt_carrying_the_note(self):
        """A5t2a C2: rebrief of a failed attempt with the note "use the fixture path" starts a new attempt whose
        task notes hold that text; the brief itself is unchanged (the note travels as the owner answer)."""
        self.write_auto_profile()
        self.attempt("failed")
        controller = self.controller(profile=True)
        row = next(item for item in self.rows()["rows"] if item["id"] == "M1")
        self.assertEqual(row["state"], "failed")
        with patch.object(autonomy, "AUTOMATIC", True):
            reply = self.call("zplan_rebrief", {"milestone": "M1", "token": row["token"],
                                                "note": "use the fixture path"}, rid="rb")
        self.assertIn("ok", reply)
        self.assertEqual((reply["ok"]["milestone"], reply["ok"]["attempt"]), ("M1", 2))
        controller.stop()  # release the session lock before reading the stored attempt
        with tp.Authority(self.state, self.project) as authority:
            fresh = authority.state["runs"][-1]
            self.assertEqual((fresh["attempt"], fresh["context"]["kind"], fresh["context"]["text"]),
                             (2, "answer", "use the fixture path"))
            manifest = decode((Path(fresh["worktree"]) / milestone.MANIFEST).read_text())
            self.assertIn("use the fixture path", manifest["tasks"][0]["notes"])

    def test_c3_a_rebrief_is_refused_when_every_slot_is_full(self):
        """A9t C3: the architect's `zplan_rebrief` opens its attempt through `runs.answer`/`retry` directly, so it
        takes the same cap guard the owner's own [g] does. With a single-slot profile and M1 already running, a
        rebrief of the failed M2 is refused with the cap line and creates no attempt.

        Interpretation: M1 and M2 must be independent for both to exist (M2's failure is a second milestone's
        record, not M1's own), so the plan-gate fixture is replaced by the disjoint plan `test_parallel_runs`
        builds; the rebrief's own policy keeps the release gate on, as the neighbouring rebrief test patches it."""
        plan = parallel_plan()
        with patch("terminal_planner.engine.fixture_proposal", return_value=plan):
            with tp.Authority(self.state, self.project) as authority:
                self.begin(authority)
                self.propose(authority)
                authority.approve(1)
        (self.project / process.PROFILE_FILE).write_text(json.dumps(
            {"preset": process.PRESET_V2, "autonomy": {"level": "auto", "max_runs": 1}}))
        with tp.Authority(self.state, self.project) as authority:
            process.Profile.of(authority).accept()
        self.git("add", process.PROFILE_FILE)
        self.git("commit", "-qm", "single-slot profile")
        with tp.Authority(self.state, self.project) as authority:
            trees = authority.directory / "worktrees"
            MilestoneRuns(authority, self.driver, worktrees=trees).start("M1", 1, ROLES)  # M1 running: slot taken
            failing = MilestoneRuns(authority, FixtureDriver(self.root / "fixture-runs", "failed"), worktrees=trees)
            failed = failing.start("M2", 1, ROLES)
            self.finish(failing, failed)
            self.assertEqual(delivery.run_state(failed), "failed")
        controller = self.controller(profile=True)
        row = next(item for item in self.rows()["rows"] if item["id"] == "M2")
        self.assertEqual(row["state"], "failed")
        with patch.object(autonomy, "AUTOMATIC", True):
            reply = self.call("zplan_rebrief", {"milestone": "M2", "token": row["token"],
                                                "note": "try the fixture path again"}, rid="cap")
        self.assertEqual(reply["error"], "action.refused")
        self.assertIn("The profile's limit of parallel milestone runs (1) is reached", reply["message"])
        controller.stop()  # release the session lock before reading the stored runs
        with tp.Authority(self.state, self.project) as authority:
            self.assertEqual([r["attempt"] for r in authority.state["runs"] if r["milestone"] == "M2"], [1])

    def test_c2_a_resume_needs_the_exact_token_and_the_policy(self):
        """A5t2a C2/C4: resume of a recoverable failed attempt by the row's own token asks while the release gate is
        off and resumes the attempt under AUTOMATIC with an auto profile."""
        self.write_auto_profile()
        self.attempt("failed_recoverable")
        self.controller(profile=True)
        row = next(item for item in self.rows()["rows"] if item["id"] == "M1")
        self.assertEqual(row["state"], "failed_recoverable")
        with patch.object(autonomy, "AUTOMATIC", False):  # the release gate as A5t1 shipped it: ask
            asked = self.call("zplan_resume", {"milestone": "M1", "token": row["token"]}, rid="rs")
            self.assertEqual(asked["error"], "autonomy.ask")
        reply = self.call("zplan_resume", {"milestone": "M1", "token": row["token"]}, rid="rs2")
        self.assertIn("ok", reply)
        # resume keeps the attempt number: it continues the same attempt with a fresh run id
        self.assertEqual((reply["ok"]["milestone"], reply["ok"]["attempt"]), ("M1", 1))
        self.assertNotEqual(reply["ok"]["run_id"], row["run_id"])
        self.assertEqual(reply["ok"]["status"], "submitted")

    def test_c3_a_followup_refuses_a_token_of_another_milestone(self):
        """A5t2a C3: resume or rebrief naming M2 with M1's current token is a bad argument, refused before the
        freshness and the policy; M1's attempt is untouched."""
        self.write_auto_profile()
        self.attempt("failed_recoverable")
        self.controller(profile=True)
        row = next(item for item in self.rows()["rows"] if item["id"] == "M1")
        with patch.object(autonomy, "AUTOMATIC", True):
            resumed = self.call("zplan_resume", {"milestone": "M2", "token": row["token"]}, rid="x1")
            rebriefed = self.call("zplan_rebrief", {"milestone": "M2", "token": row["token"], "note": "n"}, rid="x2")
        self.assertEqual((resumed["error"], rebriefed["error"]),
                         ("architect.request_invalid", "architect.request_invalid"))
        after = next(item for item in self.rows()["rows"] if item["id"] == "M1")
        self.assertEqual((after["state"], after["run_id"]), ("failed_recoverable", row["run_id"]))

    # A5t2a C3 -------------------------------------------------------------------

    def test_c3_approve_refuses_a_revision_that_is_not_current_with_changed(self):
        """A5t2a C3: approving revision 1 while revision 2 is current is today's `Changed` (the "plan was revised" text)."""
        self.two_revisions()
        self.controller()
        reply = self.call("zplan_approve_plan", {"revision": 1}, rid="c1")
        self.assertEqual(reply["error"], "action.refused")
        self.assertIn("the plan was revised", reply["message"])

    def test_c3_a_bad_token_or_empty_note_is_refused_before_freshness(self):
        """A5t2a C2/C3: a malformed token and an empty note are bad arguments, refused before the freshness (and,
        with the release gate on, before the policy), so nothing is resolved or started."""
        self.plan(0)
        self.controller()
        good = {"milestone": "M1", "plan_revision": 1, "attempt": 1, "run_id": None, "status": "failed",
                "outcome": None, "delivery": "none"}
        for index, token in enumerate(({}, {"milestone": "M1"}, dict.fromkeys(good), dict(good, attempt="1"))):
            with self.subTest(token=token):
                reply = self.call("zplan_resume", {"milestone": "M1", "token": token}, rid="bad%d" % index)
                self.assertEqual(reply["error"], "architect.request_invalid")
        for index, note in enumerate(("", "   ")):
            with self.subTest(note=note):
                reply = self.call("zplan_rebrief", {"milestone": "M1", "token": good, "note": note},
                                  rid="note%d" % index)
                self.assertEqual(reply["error"], "architect.request_invalid")

    def test_c3_a_token_that_advanced_is_refused_with_changed(self):
        """A5t2a C3: resume and rebrief resolve the given token exactly; the same attempt advanced since the status
        read (its status moved) is today's `Changed` ("attempt progressed") even with the release gate on."""
        self.write_auto_profile()
        self.attempt("failed")
        self.controller(profile=True)
        row = next(item for item in self.rows()["rows"] if item["id"] == "M1")
        stale = dict(row["token"], status="running")
        with patch.object(autonomy, "AUTOMATIC", True):
            for tool, args in (("zplan_resume", {"milestone": "M1", "token": stale}),
                               ("zplan_rebrief", {"milestone": "M1", "token": stale, "note": "again"})):
                with self.subTest(tool=tool):
                    reply = self.call(tool, args, rid="st-" + tool)
                    self.assertEqual(reply["error"], "action.refused")
                    self.assertIn("attempt progressed", reply["message"])

    # A5t2a C4 -------------------------------------------------------------------

    def test_c4_approve_asks_until_the_gate_is_on_then_approves_and_status_shows_it(self):
        """A5t2a C4: with an auto profile a current approve asks while `AUTOMATIC` is off (A5t2b shipped it on, so
        the gate is patched off); with it on it approves, and the status `plan` names the approved revision."""
        self.write_auto_profile()
        self.proposed(profile=True)
        self.controller(profile=True)
        with patch.object(autonomy, "AUTOMATIC", False):
            asked = self.call("zplan_approve_plan", {"revision": 1}, rid="p1")
            self.assertEqual(asked["error"], "autonomy.ask")
            self.assertIn("by the owner in the zplan interface", asked["message"])
        reply = self.call("zplan_approve_plan", {"revision": 1}, rid="p2")
        self.assertIn("ok", reply)
        self.assertEqual(reply["ok"], {"revision": 1, "status": "approved"})
        self.assertEqual({k: v for k, v in self.rows()["plan"].items() if k != "proposal"},
                         {"version": 1, "status": "approved", "verdict": "accepted", "findings": "Fixture only; no semantic model review."})

    def test_c4_approve_refuses_when_the_profile_moved_since_the_gate(self):
        """A5t2a C4: the policy decides on the very digest the revision's gate was argued under, so a profile that
        moved since then is today's `ProfileChanged`, never an approval the live configuration no longer backs."""
        self.write_auto_profile()
        self.proposed(profile=True)
        self.controller(profile=True)
        (self.project / process.PROFILE_FILE).write_text(
            json.dumps({"preset": process.PRESET_V2, "autonomy": {"level": "manual"}}))
        with patch.object(autonomy, "AUTOMATIC", True):
            reply = self.call("zplan_approve_plan", {"revision": 1}, rid="moved")
        self.assertEqual(reply["error"], "process.changed")
        self.assertIn("The process profile changed", reply["message"])

    def test_c4_a_rebrief_binds_the_policy_to_the_profile_the_attempt_runs_under(self):
        """A5t2a C4 (regression): the rebrief decides the level on one profile read and must run under that same
        digest. The review's reproduction — the owner changing and committing the accepted profile auto->manual the
        moment the policy reads it — refuses with today's `ProfileChanged` and submits nothing, on the new-attempt
        (`failed`) branch.

        Interpretation: the drift is refused before the action, so no successor attempt exists afterwards."""
        self.write_auto_profile()
        self.attempt("failed")
        controller = self.controller(profile=True)
        row = next(item for item in self.rows()["rows"] if item["id"] == "M1")
        with patch.object(autonomy, "AUTOMATIC", True), patch.object(
                autonomy, "status_of", side_effect=self.moves_the_profile_on_the_policy_read()):
            reply = self.call("zplan_rebrief", {"milestone": "M1", "token": row["token"],
                                                "note": "use the fixture path"}, rid="drift")
        self.assertEqual(reply["error"], "process.changed")
        self.assertIn("The process profile changed", reply["message"])
        controller.stop()  # release the session lock before reading the stored runs
        with tp.Authority(self.state, self.project) as authority:
            self.assertEqual([r["attempt"] for r in authority.state["runs"]], [1])  # nothing submitted

    def test_c4_a_rebrief_binds_the_policy_on_the_needs_owner_branch(self):
        """A5t2a C4 (regression): the same profile drift is refused on the answer (`needs_owner`) branch, so the two
        branches the rebrief chooses between never diverge on which profile is in effect."""
        self.write_auto_profile()
        self.attempt("needs_owner")
        controller = self.controller(profile=True)
        row = next(item for item in self.rows()["rows"] if item["id"] == "M1")
        self.assertEqual(row["state"], "needs_owner")
        with patch.object(autonomy, "AUTOMATIC", True), patch.object(
                autonomy, "status_of", side_effect=self.moves_the_profile_on_the_policy_read()):
            reply = self.call("zplan_rebrief", {"milestone": "M1", "token": row["token"],
                                                "note": "use the fixture path"}, rid="drift-answer")
        self.assertEqual(reply["error"], "process.changed")
        controller.stop()  # release the session lock before reading the stored runs
        with tp.Authority(self.state, self.project) as authority:
            self.assertEqual([r["attempt"] for r in authority.state["runs"]], [1])  # nothing submitted

    def test_c3_a_resume_enforces_the_profile_guard_before_dispatch(self):
        """A5t2a C3 (regression): resume must pass the milestone profile guard before it dispatches. The owner
        making the accepted profile require the task gate (`gates.task=required`) left the old code submitting a
        successor; the guard's own refusal (`process.unbuilt`) now precedes the dispatch."""
        self.write_auto_profile()
        self.attempt("failed_recoverable")
        controller = self.controller(profile=True)
        row = next(item for item in self.rows()["rows"] if item["id"] == "M1")
        (self.project / process.PROFILE_FILE).write_text(json.dumps(
            {"preset": process.PRESET_V2, "autonomy": {"level": "auto"}, "gates": {"task": "required"}}))
        self.git("add", process.PROFILE_FILE)
        self.git("commit", "-qm", "owner requires the task gate")
        with patch.object(autonomy, "AUTOMATIC", True):
            reply = self.call("zplan_resume", {"milestone": "M1", "token": row["token"]}, rid="guard")
        self.assertEqual(reply["error"], "process.unbuilt")
        controller.stop()  # release the session lock before reading the stored runs
        with tp.Authority(self.state, self.project) as authority:
            self.assertEqual([r["attempt"] for r in authority.state["runs"]], [1])  # no successor dispatched

    # A5t2b C1 -------------------------------------------------------------------

    def test_c1_the_status_names_the_current_proposal_and_an_edit_asks_the_planner(self):
        """A5t2b C1: `plan` carries the current revision's full proposal (the source the architect edits);
        `zplan_edit_plan {revision, plan}` saves the edit as revision n+1, whose verdict is "ready" - the planner
        watch (in the app) dispatches it, and the status then names the new revision planning."""
        self.proposed()
        self.controller()
        proposal = self.rows()["plan"]["proposal"]
        self.assertIsInstance(proposal, dict)
        self.assertEqual([m["id"] for m in proposal["milestones"]], ["M1", "M2"])
        proposal["milestones"][0]["title"] = "First usable increment (edited)"
        reply = self.call("zplan_edit_plan", {"revision": 1, "plan": proposal}, rid="ed")
        self.assertIn("ok", reply, reply)
        self.assertEqual(reply["ok"], {"revision": 2, "status": "ready"})
        plan = self.plan_until(lambda plan: plan["version"] == 2)
        self.assertEqual(plan["status"], "planning")
        self.assertIsNone(plan["proposal"])  # the planner has not produced one yet (the app's watch dispatches it)
        self.assertEqual(self.entry("ed")["state"], "done")
        self.controller_stop()
        with tp.Authority(self.state, self.project) as authority:  # the edit is the new revision's own draft
            draft = authority.current["draft"]
            self.assertEqual((authority.current["version"], draft["milestones"][0]["title"]),
                             (2, "First usable increment (edited)"))

    def test_c1_a_ready_edit_reaches_the_ui_hook_and_a_refusal_does_not(self):
        """A5t2b C1: a "ready" verdict is handed to the UI hook (the app's `on_plan_submission`, which shows it
        through `after_submission` and starts the planner watch), exactly once, with the service's own Outcome; a
        refusal (here "unchanged") never reaches it. The hook runs on the worker, as the owner's submission callback
        does."""
        self.proposed()
        controller = self.controller()
        seen = []
        controller.on_plan_submission = seen.append
        current = self.rows()["plan"]["proposal"]
        edited = copy.deepcopy(current)
        edited["milestones"][0]["title"] = "Edited by the architect"
        unchanged = self.call("zplan_edit_plan", {"revision": 1, "plan": current}, rid="noop")
        self.assertEqual(unchanged["error"], "action.refused")
        self.assertEqual(seen, [])  # a refusal writes nothing and shows nothing
        reply = self.call("zplan_edit_plan", {"revision": 1, "plan": edited}, rid="ok")
        self.assertIn("ok", reply, reply)
        self.assertEqual(len(seen), 1)
        outcome = seen[0]
        self.assertEqual(outcome.kind, "ready")
        self.assertEqual(outcome.checks, ())

    def test_c1_an_edit_refuses_not_current_invalid_and_unchanged(self):
        """A5t2b C1: `Planning.edit`'s refusals stay - a revision that is not current, a proposal the validator
        refuses and an edit that changes nothing are all `action.refused`, with nothing written."""
        self.proposed()
        self.controller()
        current = self.rows()["plan"]["proposal"]
        edited = copy.deepcopy(current)
        edited["milestones"][0]["title"] = "Changed"
        for name, arguments in (("not current", {"revision": 9, "plan": edited}),
                                ("invalid", {"revision": 1, "plan": {"requirements": []}}),
                                ("unchanged", {"revision": 1, "plan": current})):
            with self.subTest(name=name):
                reply = self.call("zplan_edit_plan", arguments, rid="ref-" + name.split()[0])
                self.assertEqual(reply["error"], "action.refused", reply)
        self.assertEqual(self.rows()["plan"]["version"], 1)  # no new revision
        self.assertEqual(self.rows()["plan"]["status"], "proposed")

    def test_c1_the_edit_is_admitted_as_exactly_one_plan_job(self):
        """A5t2b C1: `zplan_edit_plan` runs `Planning.edit` inside exactly one `_plan_job` - the plan service's own
        job, as the owner's submit and revise use - posted by the socket thread itself, never nested inside the
        bridge job. The request's own bookkeeping still rides that job: the entry ends done and the revision is
        saved."""
        from terminal_planner.tui.controller import Controller
        self.proposed()
        self.controller()
        edited = copy.deepcopy(self.rows()["plan"]["proposal"])
        edited["milestones"][0]["title"] = "Admitted as a plan job"
        labels, original = [], Controller._plan_job

        def spy(controller, label, work, done):
            labels.append(label)
            return original(controller, label, work, done)

        with patch.object(Controller, "_plan_job", spy):
            reply = self.call("zplan_edit_plan", {"revision": 1, "plan": edited}, rid="pj")
        self.assertIn("ok", reply, reply)
        self.assertEqual(labels, ["zplan_edit_plan"])  # one plan job, nothing nested
        self.assertEqual(self.entry("pj")["state"], "done")
        plan = self.plan_until(lambda plan: plan["version"] == 2)
        self.assertEqual(plan["status"], "planning")

    def test_c1_an_edit_without_an_open_session_fails_with_the_session_refusal(self):
        """A5t2b C1 (critic a5t2b-merge P2): the plan job refuses before the tool runs when the session did not open;
        the request ends failed with that refusal and its family, never as a success."""
        from terminal_planner.tui.controller import Controller

        def broken(stack):
            raise Blocked("The session did not open.", family="action.refused")

        controller = Controller.for_project(self.project, self.state, fixture_id="test",
                                            driver_factory=lambda _: self.driver,
                                            engine_factory=lambda *_: FixtureEngine())
        controller.open_session = broken
        controller.start()
        self._controllers.append(controller)
        self.addCleanup(controller.stop)
        reply = self.call("zplan_edit_plan", {"revision": 1, "plan": {}}, rid="ns")
        self.assertNotIn("ok", reply, reply)
        self.assertEqual(reply["error"], "action.refused", reply)
        entry = self.entry("ns")
        self.assertEqual(entry["error"]["family"], "action.refused", entry)
        self.assertNotIn("ok", entry)

    def test_a8_f1_the_status_plan_findings_are_bounded_and_empty_without_evidence(self):
        """A8 F1: `findings` is the evidence's text cut at 4000 characters with "…", "" without evidence."""
        from terminal_planner.tui.controller import plan_fields
        long = "x" * 5000
        cut = plan_fields({"version": 2, "status": "review_exhausted", "evidence": {"verdict": "rejected", "findings": long}})
        self.assertEqual((len(cut["findings"]), cut["findings"][-1]), (4000, "…"))
        self.assertEqual(plan_fields({"version": 1, "status": "planning", "evidence": None})["findings"], "")

    def test_a8_f3_revise_plan_asks_the_planner_in_one_plan_job_and_refuses_what_is_not_current(self):
        """A8 F3: `zplan_revise_plan {revision, feedback}` is `Planning.revise` in exactly one `_plan_job`, like
        edit: the current revision with non-empty feedback -> {revision: n+1, status: "ready"}, the hook gets the
        "ready" verdict and the feedback is the new revision's; a revision that is not current, or empty or missing
        feedback, is refused with nothing written. Interpretation: none."""
        from terminal_planner.tui.controller import Controller
        self.proposed()
        controller = self.controller()
        seen, labels, original = [], [], Controller._plan_job
        controller.on_plan_submission = seen.append

        def spy(self_, label, work, done):
            labels.append(label)
            return original(self_, label, work, done)

        with patch.object(Controller, "_plan_job", spy):
            for rid, arguments, family in (("old", {"revision": 2, "feedback": "add examples"}, "action.refused"),
                                           ("blank", {"revision": 1, "feedback": "  "}, "architect.request_invalid"),
                                           ("none", {"revision": 1}, "architect.request_invalid")):
                with self.subTest(rid=rid):
                    self.assertEqual(self.call("zplan_revise_plan", arguments, rid=rid)["error"], family)
            self.assertEqual((seen, self.rows()["plan"]["version"]), ([], 1))
            reply = self.call("zplan_revise_plan", {"revision": 1, "feedback": "add examples"}, rid="ok")
        self.assertEqual(reply["ok"], {"revision": 2, "status": "ready"})
        self.assertEqual((len(seen), seen[0].kind), (1, "ready"))
        self.assertEqual(labels.count("zplan_revise_plan"), 4)  # each call is its own single plan job
        self.assertEqual(self.plan_until(lambda plan: plan["version"] == 2)["status"], "planning")
        self.controller_stop()
        with tp.Authority(self.state, self.project) as authority:
            self.assertIn("add examples", authority.current["feedback"])

    # A5t2b C2 -------------------------------------------------------------------

    def test_c2_merge_resolves_the_token_and_needs_the_required_gate(self):
        """A5t2b C2: `zplan_merge {milestone, token}` resolves the token exactly (a token of another milestone is a
        bad argument) and, with `gates.merge: required` and auto, runs `Delivery.merge`: an awaiting_merge attempt's
        checks and its (absent) critic let it land, and the result is `Delivery.merge`'s own kind and line."""
        self.awaiting_merge()
        self.controller(profile=True)
        row = next(item for item in self.rows()["rows"] if item["id"] == "M1")
        self.assertEqual(row["state"], "awaiting_merge")
        wrong = self.call("zplan_merge", {"milestone": "M2", "token": row["token"]}, rid="wrong")
        self.assertEqual(wrong["error"], "architect.request_invalid")
        self.assertEqual(next(item for item in self.rows()["rows"] if item["id"] == "M1")["state"], "awaiting_merge")
        reply = self.call("zplan_merge", {"milestone": "M1", "token": row["token"]}, rid="mg")
        self.assertIn("ok", reply, reply)
        self.assertEqual(reply["ok"]["milestone"], "M1")
        self.assertEqual(reply["ok"]["kind"], "integrated")
        self.assertIn("Merged: M1", reply["ok"]["line"])
        self.assertEqual(self.entry("mg")["state"], "done")

    def test_c2_a_merge_asks_without_the_required_gate(self):
        """A5t2b C2/C3: with `gates.merge` off (the default profile) even auto asks the owner: the attempt stays
        awaiting_merge and nothing is merged."""
        self.awaiting_merge(merge="off")
        self.controller(profile=True)
        row = next(item for item in self.rows()["rows"] if item["id"] == "M1")
        reply = self.call("zplan_merge", {"milestone": "M1", "token": row["token"]}, rid="ask")
        self.assertEqual(reply["error"], "autonomy.ask", reply)
        self.assertIn("by the owner in the zplan interface", reply["message"])
        self.assertEqual(next(item for item in self.rows()["rows"] if item["id"] == "M1")["state"], "awaiting_merge")

    def test_c2_autonomy_ask_refusals_name_the_owners_step_and_that_a_chat_reply_does_not_do_it(self):
        """C2 K1 (walk W1): each `autonomy.ask` refusal names the owner's command or card and says a chat reply does
        not do the action; a merge under a profile without the merge check says that is why it is the owner's.
        Interpretation: with the merge check required and the level not auto, the "no merge check" sentence is left out."""
        self.awaiting_merge(merge="off")
        self.controller(profile=True)
        row = next(item for item in self.rows()["rows"] if item["id"] == "M1")
        reply = self.call("zplan_merge", {"milestone": "M1", "token": row["token"]}, rid="m")
        self.assertEqual(reply["error"], "autonomy.ask", reply)
        for part in ("merge card", "/merge", "no merge check", "A chat reply does not"):
            self.assertIn(part, reply["message"])
        with patch.object(autonomy, "AUTOMATIC", False):
            for tool, args, expect in (("zplan_approve_plan", {"revision": 1}, ("/approve", "plan card")),
                                       ("zplan_resume", {"milestone": "M1", "token": row["token"]}, ("/run",)),
                                       ("zplan_rebrief", {"milestone": "M1", "token": row["token"], "note": "x"},
                                        ("/attempt",)),
                                       ("zplan_start", {"milestone": "M1", "revision": 1}, ("/run",))):
                with self.subTest(tool=tool):
                    reply = self.call(tool, args, rid="a-" + tool)
                    self.assertEqual(reply["error"], "autonomy.ask", reply)
                    for part in expect + ("A chat reply does not",):
                        self.assertIn(part, reply["message"])

    def test_c2_the_merge_is_bound_to_the_profile_the_policy_read(self):
        """A5t2b C2 (regression, main 4d4fa55): a profile that moves between the policy read and the merge's own read
        is `process.changed` and nothing is merged - the merge lands on the very profile the policy decided on."""
        self.awaiting_merge()
        self.controller(profile=True)
        row = next(item for item in self.rows()["rows"] if item["id"] == "M1")
        with patch.object(autonomy, "status_of", side_effect=self.moves_the_profile_on_the_policy_read()):
            reply = self.call("zplan_merge", {"milestone": "M1", "token": row["token"]}, rid="moved")
        self.assertIn("ok", reply, reply)
        self.assertEqual(reply["ok"]["kind"], "refused")           # Delivery.merge renders the refusal, not raises
        self.assertIn("The process profile changed", reply["ok"]["line"])
        self.assertEqual(next(item for item in self.rows()["rows"] if item["id"] == "M1")["state"], "awaiting_merge")

    # A5t2b C3 -------------------------------------------------------------------

    def test_c3_a_supervised_start_is_allowed_and_its_gated_merge_asks(self):
        """A5t2b C3: with the release gate on, supervised lets the architect start without asking, but even with
        `gates.merge: required` a supervised merge asks the owner (only auto may merge by itself)."""
        self.plan(0)
        self.write_profile(level="supervised", merge="required",
                           checks=[{"name": "unit", "argv": ["true"], "timeout_s": 60}])
        self.controller(profile=True)
        started = self.call("zplan_start", {"milestone": "M1", "revision": 1}, rid="sup-start")
        self.assertIn("ok", started, started)
        row = next(item for item in self.rows()["rows"] if item["id"] == "M1")
        self.assertEqual(row["state"], "running")
        # the row's own token resolves, but a supervised merge asks the owner even with gates.merge required
        asked = self.call("zplan_merge", {"milestone": "M1", "token": row["token"]}, rid="sup-merge")
        self.assertEqual(asked["error"], "autonomy.ask", asked)

    def test_c3_a_manual_start_asks(self):
        """A5t2b C3: a manual profile asks the owner for the start just as it does for every other action, with the
        release gate already on."""
        self.plan(0)
        self.write_profile(level="manual")
        self.controller(profile=True)
        reply = self.call("zplan_start", {"milestone": "M1", "revision": 1}, rid="manual")
        self.assertEqual(reply["error"], "autonomy.ask", reply)
        self.assertIn("by the owner in the zplan interface", reply["message"])


if __name__ == "__main__":
    unittest.main()
