"""Milestone run adapter: durable records, crash windows, lifecycle and refusals with a fake native CLI."""

import copy
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import time
import unittest
from unittest.mock import patch

import test_terminal_planner as planner
from terminal_planner import live, milestone, runs, toolchain
from terminal_planner.authority import (Authority as RealAuthority, Blocked, atomic_state, canonical, decode, digest,
                                        require_terminal_result, require_workspace_outside_state)
from terminal_planner.engine import fixture_proposal
from terminal_planner.runs import FixtureDriver, MilestoneRuns, NativeDriver

ROLES = planner.ROLES
DONE = {"signal": "done", "message": "Milestone complete.", "question": None, "proposal": None}
OWNER = {"signal": "needs_owner", "message": "Scope question.", "question": "Split T1?", "proposal": "Split T1 into two tasks."}


class Crash(BaseException):
    """Process death at a precise point: nothing after it runs, no handler cleans up."""


class RunsTest(planner.ProjectTest):
    native = planner.NativeTests.native
    fake = planner.NativeTests.engine
    projection = planner.NativeTests.projection

    def setUp(self):
        super().setUp()
        self.worktrees = self.root / "worktrees"

    def head(self):
        return self.git("rev-parse", "HEAD").decode().strip()

    def config(self, repo, key):
        result = subprocess.run(["git", "-C", str(repo), "config", "--get", key], capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else None

    # Fixture authority ----------------------------------------------------

    def fixture_authority(self):
        return planner.Authority(self.state, self.project)

    def approve_fixture(self):
        with self.fixture_authority() as a:
            self.begin(a)
            self.propose(a)
            a.approve(1)

    def fixture_runs(self, a, outcome="done"):
        return MilestoneRuns(a, FixtureDriver(self.root / "fixture-runs", outcome), worktrees=self.worktrees)

    # Native authority -----------------------------------------------------

    def authority(self):
        return RealAuthority(None, self.project)

    def approve_native(self):
        engine, _ = self.fake([{"valid": True}, {"runId": "fixture-native-run"},
                               (planner.NativeTests.running(self), planner.NativeTests.terminal(self))])
        with self.authority() as a:
            self.begin(a, "native")
            engine.proposal(a, lambda _: None)
            a.approve(1)

    def driver(self, responses):
        engine, calls = self.fake(responses)
        return NativeDriver(engine.executable, engine.state_root, call=engine.call, sleep=lambda _: None), calls

    def native_runs(self, a, responses):
        driver, calls = self.driver(responses)
        return MilestoneRuns(a, driver, worktrees=self.worktrees), calls

    def started(self, run_id="m-run"):
        """Approved native plan with attempt 1 of M1 submitted; returns the saved record."""
        self.approve_native()
        with self.authority() as a:
            controller, calls = self.native_runs(a, [{"valid": True}, {"runId": run_id}])
            r = controller.start("M1", 1, ROLES)
            self.assertEqual([c[0][1] for c in calls], ["run", "run"])
            return copy.deepcopy(r)

    def envelope(self, r, status, cursor="v2:5", run_id=None, watch=True):
        value = {"runId": run_id or r["run_id"], "title": runs.title(r), "size": "medium",
                 "source": {"repository": "example/fixture", "branch": r["branch"], "revision": r["destination"]["base"]},
                 "status": status}
        if watch:
            value.update(subscriptionId="sub", cursor=cursor)
        else:
            value["atCursor"] = cursor
        return value

    def running(self, r, cursor="v2:5", phase="running"):
        return self.envelope(r, {"phase": phase, "activeExecutions": [{"node": "worker", "execution": "e1"}]}, cursor)

    def finished(self, r, output=None, reason=None, cursor="v2:9"):
        terminal = {"status": "failed", "reason": reason} if reason else {"status": "succeeded", "output": output}
        return self.envelope(r, {"phase": "finished", "terminalResult": terminal}, cursor)

    def status(self, r, recovery, run_id=None, reason="worker_failed"):
        return self.envelope(r, {"phase": "finished", "terminalResult": {"status": "failed", "reason": reason}},
                             "v2:9", run_id=run_id, watch=False) | {"workspaceRecovery": recovery}

    def complete(self, r):
        """What the native driver would leave: every task accepted, plus an uncommitted change."""
        path = Path(r["worktree"]) / milestone.MANIFEST
        manifest = decode(path.read_text())
        for task in manifest["tasks"]:
            task["status"] = "done"
            manifest["progress"].append({"seq": len(manifest["progress"]) + 1, "task": task["id"], "phase": "accepted", "text": "ok"})
        atomic_state(path, manifest)

    def stored(self, a):
        return decode(a.path.read_text()).get("runs", [])

    def live(self, r):
        """Non-terminal public status of a run (status --json shape)."""
        return self.envelope(r, {"phase": "running", "activeExecutions": [{"node": "worker", "execution": "e1"}]},
                             "v2:6", watch=False)

    def ledger(self, outcomes=(), lose_receipt=False):
        """Fake native CLI that keys submissions by digest (key, documents, cwd) like native idempotence:
        an identical replay returns the existing run id, anything else would be a new run."""
        engine, _ = self.fake([])
        calls, submissions, outcomes, lose = [], {}, list(outcomes), [lose_receipt]

        def call(argv, **kwargs):
            if argv[1:] == ["--version"]:
                return subprocess.CompletedProcess(argv, 0, toolchain.current().zeroshot_version + "\n", "")
            calls.append((argv, kwargs))
            self.assertTrue(argv[1] == "run" and argv[-1] in ("--validate-only", "--detach"), argv)
            if argv[-1] == "--validate-only":
                return subprocess.CompletedProcess(argv, 0, json.dumps({"valid": True}) + "\n", "")
            if outcomes:
                return outcomes.pop(0)
            key = digest([argv[argv.index("--submission-key") + 1], kwargs["cwd"]]
                         + [Path(argv[argv.index(flag) + 1]).read_text() for flag in ("--graph", "--runtime-config", "--input")])
            run_id = submissions.setdefault(key, "m-run-%s" % (len(submissions) + 1))
            if lose[0]:
                lose[0] = False
                raise Crash  # dispatched natively, receipt lost with the process
            return subprocess.CompletedProcess(argv, 0, json.dumps({"runId": run_id}) + "\n", "")

        driver = NativeDriver(engine.executable, engine.state_root, call=call, sleep=lambda _: None)
        return driver, calls, submissions

    def worktree_head(self, r):
        return subprocess.check_output(["git", "-C", r["worktree"], "rev-parse", "HEAD"]).decode().strip()

    def tree(self, commit):
        return self.git("ls-tree", "-r", "--name-only", commit).decode().split()

    def parents(self, commit):
        return self.git("rev-list", "--parents", "-n", "1", commit).decode().split()[1:]


class StoreTests(RunsTest):
    def test_old_store_without_runs_loads_and_forged_records_are_rejected(self):
        self.approve_fixture()
        with self.fixture_authority() as a:
            self.assertNotIn("runs", a.state)
            r = self.fixture_runs(a).start("M1", 1, ROLES)
            self.fixture_runs(a).observe(r)
            self.assertEqual(r["outcome"], "done")
            path, original = a.path, a.path.read_bytes()
        with self.fixture_authority() as a:
            self.assertEqual(a.state["runs"][0]["status"], "finished")
        good = decode(original.decode())
        successor = {**copy.deepcopy(good["runs"][0]), "predecessor": good["runs"][0]["run_id"], "run_id": "fixture-x"}
        forgeries = {
            "unknown field": lambda s: s["runs"][0].update(extra=1),
            "missing field": lambda s: s["runs"][0].pop("cursor"),
            "unknown status": lambda s: s["runs"][0].update(status="paused"),
            "forged approval": lambda s: s["runs"][0].update(approval="0" * 64),
            "unapproved revision": lambda s: s["runs"][0].update(plan_revision=2),
            "other milestone": lambda s: s["runs"][0].update(milestone="M2"),
            "partial extension": lambda s: s["runs"][0].pop("delivery"),
            "unknown delivery": lambda s: s["runs"][0].update(delivery="merged"),
            "exported without commit": lambda s: s["runs"][0].update(delivery="awaiting_merge"),
            "commit without export": lambda s: s["runs"][0]["result"].update(commit=good["runs"][0]["destination"]["base"]),
            "forged result branch": lambda s: s["runs"][0]["result"].update(branch="main"),
            "forged product tree": lambda s: s["runs"][0]["result"].update(tree="candidate_x"),
            "integrated without evidence": lambda s: (
                s["runs"][0].update(delivery="integrated"),
                s["runs"][0]["result"].update(commit=good["runs"][0]["destination"]["base"])),
            "forged bootstrap": lambda s: s["runs"][0].update(bootstrap="0" * 64),
            "context without earlier attempt": lambda s: s["runs"][0].update(
                context={"kind": "answer", "source": 1, "text": "x", "candidate": None}),
            "skipped attempt": lambda s: s["runs"][0].update(attempt=2),
            "foreign branch": lambda s: s["runs"][0].update(branch="main"),
            "relative worktree": lambda s: s["runs"][0].update(worktree="worktrees/x"),
            "bad key": lambda s: s["runs"][0].update(submission_key="zplan-run-1"),
            "bad base": lambda s: s["runs"][0]["destination"].update(base="HEAD"),
            "native binding": lambda s: s["runs"][0].update(binding={"fixture_id": "other"}),
            "run id while preparing": lambda s: s["runs"][0].update(status="preparing"),
            "done without manifest": lambda s: s["runs"][0].update(manifest=None),
            "done with open task": lambda s: s["runs"][0]["manifest"]["tasks"][0].update(status="open"),
            "forged manifest baseline": lambda s: s["runs"][0]["manifest"]["baseline"]["tasks"][0].update(title="x"),
            "output signal mismatch": lambda s: s["runs"][0].update(outcome="blocked"),
            "terminal on active": lambda s: s["runs"][0].update(status="running"),
            "unrecoverable predecessor": lambda s: s["runs"].append(copy.deepcopy(successor)),
            "two active writers": lambda s: s["runs"].extend([
                {**copy.deepcopy(good["runs"][0]), **dict.fromkeys(("run_id", "terminal", "output", "outcome", "manifest")),
                 "status": "preparing", "attempt": a, "submission_key": "zplan-run-%08d-0000-0000-0000-000000000000" % a,
                 "branch": runs.names(good["project_id"], good["runs"][0]["approval"], "M1", a)[0],
                 "worktree": str(self.worktrees / runs.names(good["project_id"], good["runs"][0]["approval"], "M1", a)[1])}
                for a in (2, 3)]),
            "runs not a list": lambda s: s.update(runs={}),
        }
        for name, mutate in forgeries.items():
            with self.subTest(name):
                state = copy.deepcopy(good)
                mutate(state)
                path.write_text(canonical(state) + "\n")
                with self.assertRaises(Blocked):
                    with self.fixture_authority():
                        pass
        path.write_bytes(original)
        with self.fixture_authority() as a:
            self.assertEqual(len(a.state["runs"]), 1)

    def test_p3_record_without_delivery_fields_loads_and_finishes(self):
        self.approve_fixture()
        with self.fixture_authority() as a:
            controller = self.fixture_runs(a)
            controller.observe(controller.start("M1", 1, ROLES))
            state = decode(a.path.read_text())
        for key in runs.EXTENSION:
            del state["runs"][0][key]
        a.path.write_text(canonical(state) + "\n")
        with self.fixture_authority() as a:
            r = a.state["runs"][0]
            self.assertNotIn("delivery", r)
            self.assertEqual(runs.owner_actions(r), ("finish",))
            self.fixture_runs(a).finish(r)
            self.assertEqual((r["delivery"], r["context"], r["bootstrap"]), ("awaiting_merge", None, None))
            self.assertEqual(r["result"]["tree"], runs.product_tree(a.project, r["worktree"], r["destination"]["base"]))
        with self.fixture_authority() as a:
            self.assertEqual(a.state["runs"][0]["result"]["commit"], r["result"]["commit"])


class RefusalTests(RunsTest):
    def assert_refused(self, a, controller, message, milestone_id="M1", revision=1):
        before = copy.deepcopy(a.state.get("runs"))
        with self.assertRaisesRegex(Blocked, message):
            controller.start(milestone_id, revision, ROLES)
        self.assertEqual(a.state.get("runs"), before)
        self.assertEqual(self.stored(a), before or [])
        self.assertFalse(self.worktrees.exists() and any(self.worktrees.iterdir()))

    def test_fixture_refusals_persist_nothing(self):
        with self.fixture_authority() as a:
            self.begin(a)
            self.propose(a)
            self.assert_refused(a, self.fixture_runs(a), "is not approved")
            a.approve(1)
            controller = self.fixture_runs(a)
            self.assert_refused(a, controller, "M2 is waiting for M1", "M2")
            self.assert_refused(a, controller, "is not in the approved plan", "M9")
            native, calls = self.native_runs(a, [])
            self.assert_refused(a, native, "A fixture approval does not allow native")
            self.assertEqual(calls, [])
            self.git("checkout", "-q", "--detach")
            self.assert_refused(a, controller, "HEAD is detached")
            self.git("checkout", "-q", "-")
            (self.project / ".zplan").mkdir()
            (self.project / ".zplan" / "note.txt").write_text("tracked\n")
            self.git("add", ".zplan")
            self.git("commit", "-qm", "track control dir")
            self.assert_refused(a, controller, "tracks \.zplan")
            self.git("rm", "-rq", ".zplan")
            self.git("commit", "-qm", "untrack control dir")
            # A newer revision makes revision 1 stale; the unapproved revision 2 is refused too.
            a.begin("Next goal", ROLES, "fixture")
            self.propose(a)
            self.assert_refused(a, controller, "is stale")
            self.assert_refused(a, controller, "is not approved", revision=2)

    def test_native_approval_refuses_fixture_driver_and_a_second_writer(self):
        r = self.started()
        with self.authority() as a:
            self.assertEqual(len(a.state["runs"]), 1)
            controller, calls = self.native_runs(a, [])
            with self.assertRaisesRegex(Blocked, "M1 is already running"):
                controller.start("M1", 1, ROLES)
            with self.assertRaisesRegex(Blocked, "The fixture driver does not run"):
                self.fixture_runs(a).start("M1", 1, ROLES)
            self.assertEqual(calls, [])
            self.assertEqual(self.stored(a), [r])


class NativeLifecycleTests(RunsTest):
    def test_submission_is_frozen_and_dispatched_from_the_worktree(self):
        self.approve_native()
        with self.authority() as a:
            controller, calls = self.native_runs(a, [{"valid": True}, {"runId": "m-run"}])
            r = controller.start("M1", 1, ROLES)
            worktree = Path(r["worktree"])
            self.assertEqual(r["status"], "submitted")
            self.assertEqual(r["run_id"], "m-run")
            self.assertEqual(r["destination"], {"branch": self.git("branch", "--show-current").decode().strip(), "base": self.head()})
            self.assertRegex(r["branch"], r"^zplan-work/[0-9a-f]{8}/m1-[0-9a-f]{6}/a1$")
            self.assertEqual(worktree.parent, self.worktrees.resolve())
            self.assertEqual(subprocess.check_output(["git", "-C", str(worktree), "rev-parse", "HEAD"]).decode().strip(), self.head())
            baseline, manifest = milestone.build_manifest(a.current["proposal"], "M1", 1)
            self.assertEqual(decode((worktree / milestone.BASELINE).read_text()), baseline)
            self.assertEqual(decode((worktree / milestone.MANIFEST).read_text()), manifest)
            self.assertEqual(r["documents"]["baseline"], digest(baseline))
            for (argv, options), flag in zip(calls, ("--validate-only", "--detach")):
                self.assertEqual(argv[-1], flag)
                self.assertEqual(options["cwd"], r["worktree"])
                self.assertIn("--no-environment", argv)
                self.assertEqual(argv[argv.index("--submission-key") + 1], r["submission_key"])
                self.assertEqual(argv[argv.index("--title") + 1], "Milestone M1 attempt 1 (plan revision 1)")
            checker = json.dumps(r["checker"])[1:-1]
            self.assertTrue(r["checker"].startswith(runs.sys.executable))
            self.assertIn(checker, Path(calls[1][0][calls[1][0].index("--graph") + 1]).read_text())
            frozen_input = json.loads(Path(calls[1][0][calls[1][0].index("--input") + 1]).read_text())
            self.assertIn(checker, frozen_input["milestone"])
            # The target checkout itself is untouched: the run writes only its own worktree.
            self.assertEqual(self.git("status", "--porcelain"), b"")

    def test_milestone_run_pins_its_worktree_branch_to_origin_despite_a_second_remote(self):
        # 10.12 resolves the submitted source from the branch's upstream config and fails on several valid remotes
        # without one. The worktree's own branch names origin, and the user's branch (here tracking another remote)
        # is never rewritten.
        self.git("remote", "add", "backup", "https://github.com/example/backup.git")
        self.git("config", "branch.main.remote", "backup")
        self.git("config", "branch.main.merge", "refs/heads/other")
        self.approve_native()
        with self.authority() as a:
            controller, _ = self.native_runs(a, [{"valid": True}, {"runId": "m-run"}])
            r = controller.start("M1", 1, ROLES)
        worktree = Path(r["worktree"])
        self.assertEqual(self.config(worktree, "branch.%s.remote" % r["branch"]), "origin")
        self.assertEqual(self.config(worktree, "branch.%s.merge" % r["branch"]), "refs/heads/" + r["branch"])
        self.assertEqual(self.config(self.project, "branch.main.remote"), "backup")
        self.assertEqual(self.config(self.project, "branch.main.merge"), "refs/heads/other")

    def test_milestone_submission_refuses_a_worktree_overlapping_the_native_state(self):
        # XDG_DATA_HOME (or --native-state-dir) pointed inside the live state: the milestone worktrees root lands
        # under <native_state_root>/runs and 10.12 forbids it. zplan refuses before any native call; a worktrees
        # root beside the state (the default) is unaffected.
        self.approve_native()
        driver, calls = self.driver([{"valid": True}, {"runId": "m-run"}])
        self.assertEqual(require_workspace_outside_state(self.worktrees / "m1", driver.state_root,
                                                        family="milestone.preflight"), (self.worktrees / "m1").resolve())
        with self.authority() as a:
            controller = MilestoneRuns(a, driver, worktrees=driver.state_root / "runs" / "worktrees")
            with self.assertRaisesRegex(Blocked, "overlaps"):
                controller.start("M1", 1, ROLES)
            self.assertEqual(calls, [])
            self.assertEqual(self.stored(a)[0]["status"], "preparing")

    def test_watch_to_done_detach_reattach_and_reopen(self):
        r = self.started()
        with self.authority() as a:
            controller, calls = self.native_runs(a, [
                subprocess.TimeoutExpired("watch", 120, output=canonical(self.running(r)) + "\n")])
            r = controller.observe(controller.active())
            self.assertEqual((r["status"], r["cursor"]), ("running", "v2:5"))
            self.assertEqual(calls[0][0][1:], ["watch", "m-run"])
        with self.authority() as a:
            self.complete(r)
            controller, calls = self.native_runs(a, [(self.running(r, "v2:6"), self.finished(r, DONE))])
            r = controller.reconcile()
            self.assertEqual(r["status"], "running")
            r = controller.observe(r)
            self.assertEqual(calls[0][0][1:], ["watch", "m-run", "--after", "v2:5"])
            self.assertEqual((r["status"], r["outcome"], r["output"]), ("finished", "done", DONE))
            self.assertTrue(all(t["status"] == "done" for t in r["manifest"]["tasks"]))
            self.assertIsNone(controller.reconcile())
            self.assertEqual(len(calls), 1)

    def test_done_requires_a_closed_manifest_and_owner_signals_keep_diagnostics(self):
        for output, damage, outcome in ((DONE, None, "invalid"), (OWNER, "corrupt", "needs_owner"),
                                        ({**DONE, "signal": "blocked"}, None, "blocked")):
            with self.subTest(outcome=outcome):
                planner.shutil.rmtree(self.root / "home", ignore_errors=True)
                planner.shutil.rmtree(self.worktrees, ignore_errors=True)
                self.git("worktree", "prune")
                for branch in self.git("branch", "--format=%(refname:short)").decode().split():
                    if branch.startswith("zplan-work/"):
                        self.git("branch", "-D", branch)
                r = self.started()
                if damage:
                    (Path(r["worktree"]) / milestone.MANIFEST).write_text("{broken")
                with self.authority() as a:
                    controller, _ = self.native_runs(a, [(self.finished(r, output),)])
                    r = controller.observe(controller.active())
                    self.assertEqual((r["status"], r["outcome"]), ("finished", outcome))
                    self.assertEqual(r["output"], output)
                    if damage:
                        self.assertIsNone(r["manifest"])
                        self.assertIn("manifest:", r["diagnostic"])
                    elif outcome == "invalid":
                        self.assertIn("open tasks T1", r["diagnostic"])

    def test_malformed_root_output_is_recorded_not_guessed(self):
        r = self.started()
        with self.authority() as a:
            controller, _ = self.native_runs(a, [(self.finished(r, {"signal": "done"}),)])
            r = controller.observe(controller.active())
            self.assertEqual((r["status"], r["outcome"], r["output"]), ("finished", "invalid", None))
            self.assertEqual(r["terminal"]["output"], {"signal": "done"})

    def test_stop_persists_stopping_before_force_stop_and_ends_stopped(self):
        r = self.started()
        with self.authority() as a:
            controller, calls = self.native_runs(a, [OSError("socket")])
            with self.assertRaisesRegex(Blocked, "force-stop did not answer"):
                controller.stop(controller.active())
            self.assertEqual(self.stored(a)[0]["status"], "stopping")
        with self.authority() as a:
            # Reopen resends the persisted stop for a run that is not terminal yet.
            controller, calls = self.native_runs(a, [self.live(r), subprocess.CompletedProcess([], 0, "", ""),
                                                     (self.running(r, "v2:7", "stopping"),
                                                      self.finished(r, reason="force_stopped"))])
            r = controller.reconcile()
            self.assertEqual(r["status"], "stopping")
            self.assertEqual([c[0][1:] for c in calls], [["status", "m-run"], ["force-stop", "m-run"]])
            r = controller.observe(r)
            self.assertEqual((r["status"], r["terminal"]["reason"]), ("stopped", "force_stopped"))
            with self.assertRaisesRegex(Blocked, "only for a failed run"):
                controller.resume(r)
            # A stopped milestone is not complete: no result, dependents keep waiting, the owner answers or replans.
            self.assertIsNone(r["result"])
            self.assertEqual(controller.waiting("M2"), ["M1"])
            self.assertEqual(runs.owner_actions(r), ("answer", "revise"))

    def test_resume_lineage_and_fresh_attempt_after_needs_owner(self):
        r = self.started()
        with self.authority() as a:
            controller, calls = self.native_runs(a, [
                (self.finished(r, reason="worker_failed"),), self.status(r, {"recoverable": True}),
                self.status(r, {"recoverable": True}), {"runId": "m-run-2", "resumedFrom": "m-run"}])
            r = controller.observe(controller.active())
            self.assertEqual((r["status"], r["recoverable"], r["diagnostic"]), ("failed", True, "worker_failed"))
            successor = controller.resume(r)
            self.assertEqual(calls[-1][0][1:], ["resume", "m-run"])
            self.assertEqual((successor["status"], successor["run_id"], successor["predecessor"]), ("submitted", "m-run-2", "m-run"))
            for key in runs.LINEAGE:
                self.assertEqual(successor[key], r[key])
            with self.assertRaisesRegex(Blocked, "already resumed"):
                controller.resume(r)
            self.assertEqual(len(calls), 4)
        with self.authority() as a:
            controller, calls = self.native_runs(a, [(self.envelope(successor, {"phase": "finished", "terminalResult": {
                "status": "succeeded", "output": OWNER}}, "v2:20"),)])
            successor = controller.observe(controller.reconcile())
            self.assertEqual((successor["outcome"], successor["output"]["proposal"]), ("needs_owner", OWNER["proposal"]))
            self.assertEqual(successor["manifest"]["baseline"], decode((Path(r["worktree"]) / milestone.BASELINE).read_text()))
        # The owner moves the destination on; a new attempt starts fresh from the then-current HEAD.
        (self.project / "source.txt").write_text("owner change\n")
        self.git("commit", "-qam", "owner change")
        with self.authority() as a:
            controller, calls = self.native_runs(a, [{"valid": True}, {"runId": "m-run-3"}])
            fresh = controller.start("M1", 1, ROLES)
            self.assertEqual((fresh["attempt"], fresh["destination"]["base"]), (2, self.head()))
            self.assertTrue(fresh["branch"].endswith("/a2"))
            self.assertNotEqual(fresh["worktree"], r["worktree"])
            self.assertNotEqual(fresh["submission_key"], r["submission_key"])
            self.assertTrue(Path(r["worktree"]).is_dir())
            self.assertEqual(len(a.state["runs"]), 3)

    def test_failed_terminal_with_the_10_16_context_is_stored_and_the_shared_validator_refuses_the_rest(self):
        """C1/C2 for the stored run terminal: the record accepts the same optional 10.16 `context` as the planning
        envelope, through one validator (`require_terminal_result`, re-exported as `runs.validate_terminal`). The C1
        example ends the run failed with diagnostic `node_failed` and its context survives in the stored record; a
        `recorded` of six, a diagnostic key `extra` and a diagnostic without `message` are refused at both sites
        with their own text (the store's `INVALID`, the envelope's default)."""
        r = self.started()
        context = {"incomplete": False, "primary": {"message": "timeout after 1200s", "cursor": None}, "recorded": []}
        terminal = {"status": "failed", "reason": "node_failed", "context": context}
        with self.authority() as a:
            controller, _ = self.native_runs(a, [
                (self.envelope(r, {"phase": "finished", "terminalResult": terminal}, "v2:20"),),
                self.status(r, {"recoverable": False}, reason="node_failed"),
                subprocess.CompletedProcess([], 0, "", "")])  # the bounded logs read names no cause
            r = controller.observe(controller.active())
            self.assertEqual((r["status"], r["diagnostic"], r["terminal"]), ("failed", "node_failed", terminal))
            stored = copy.deepcopy(a.state["runs"][-1])
        with self.authority() as a:  # reopening validates the stored terminal with its context, no migration
            self.assertEqual(a.state["runs"][-1], stored)
        accepted = [terminal, {**terminal, "context": None}, {"status": "failed", "reason": "node_failed"}]
        refused = [{"status": "failed", "reason": "node_failed", "context": {"recorded": [{"message": "m"}] * 6}},
                   {"status": "failed", "reason": "node_failed",
                    "context": {"primary": {"message": "m", "extra": 1}}},
                   {"status": "failed", "reason": "node_failed", "context": {"primary": {"cursor": None}}}]
        for index, value in enumerate(accepted):
            with self.subTest(accepted=index):
                runs.validate_terminal(value)
                require_terminal_result(value)
        for index, value in enumerate(refused):
            for validator, message in ((runs.validate_terminal, runs.INVALID),
                                       (require_terminal_result, "Incompatible planning state/envelope.")):
                with self.subTest(refused=index), self.assertRaises(Blocked) as caught:
                    validator(value)
                self.assertEqual(str(caught.exception), message)

    def test_a_run_record_written_without_context_validates_and_loads_unchanged(self):
        """C3: a stored record of the 10.12 era -- a failed terminal with no `context` -- keeps validating and loads
        byte-identically, with no migration and no rewrite."""
        r = self.started()
        with self.authority() as a:
            controller, _ = self.native_runs(a, [(self.finished(r, reason="worker_failed"),),
                                                 self.status(r, {"recoverable": False}),
                                                 subprocess.CompletedProcess([], 0, "", "")])
            r = controller.observe(controller.active())
            self.assertEqual((r["status"], r["terminal"]), ("failed", {"status": "failed", "reason": "worker_failed"}))
            path, raw = a.path, a.path.read_bytes()
        with self.authority() as a:
            self.assertEqual(a.state["runs"][-1]["terminal"], {"status": "failed", "reason": "worker_failed"})
        self.assertEqual(path.read_bytes(), raw)

    def test_details_prints_copyable_native_diagnostics_for_root_and_successor(self):
        from terminal_planner.cli import App, Terminal
        r = self.started()
        with self.authority() as a:
            controller, _ = self.native_runs(a, [
                (self.finished(r, reason="worker_failed"),), self.status(r, {"recoverable": True}),
                self.status(r, {"recoverable": True}), {"runId": "m-run-2", "resumedFrom": "m-run"}])
            controller.resume(controller.observe(controller.active()))
            output = io.StringIO()
            App(Terminal(io.StringIO(""), output), a, None, controller.engine, self.worktrees).details()
        text = output.getvalue()
        root = Path(r["binding"]["state_root"])
        prefix = "ZEROSHOT_STATE_DIR=%s ZEROSHOT_CONFIG_DIR=%s %s" % (
            shlex.quote(str(root / "runs")), shlex.quote(str(root / "config")), shlex.quote(r["binding"]["executable"]))
        self.assertIn("  Zeroshot diagnostics (root run):\n    %s status m-run\n    %s logs m-run\n" % (prefix, prefix), text)
        self.assertIn("  Zeroshot diagnostics (continuation of m-run):\n    %s status m-run-2\n    %s logs m-run-2\n"
                      % (prefix, prefix), text)
        # The tail's own words are English (the Zeroshot commands and identifiers stay as they are).
        self.assertIn("· run m-run ·", text)
        self.assertIn("  worktree %s · branch" % r["worktree"], text)
        self.assertNotIn("· прогон m-run", text)
        self.assertNotIn("  рабочее дерево ", text)
        # Ready to copy: the shell runs the actual executable with the isolated state (the fixture prints its version).
        command = "%s status m-run" % prefix
        result = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=self.root)
        self.assertEqual((result.returncode, result.stdout), (0, toolchain.current().zeroshot_version + "\n"))

    def test_unrecoverable_failure_is_never_resumed(self):
        r = self.started()
        with self.authority() as a:
            controller, calls = self.native_runs(a, [(self.finished(r, reason="worker_failed"),),
                                                     self.status(r, {"recoverable": False}), self.status(r, {"recoverable": False})])
            r = controller.observe(controller.active())
            self.assertIs(r["recoverable"], False)
            with self.assertRaisesRegex(Blocked, "not recoverable"):
                controller.resume(r)
            self.assertEqual(len(a.state["runs"]), 1)
            self.assertNotIn("resume", [c[0][1] for c in calls])


class FakeClock:
    """The monotonic clock the observer throttles against; the test moves it by hand (C3a, unrounded seconds)."""

    def __init__(self, seconds=1000.0):
        self.at = float(seconds)

    def __call__(self):
        return self.at

    def advance(self, seconds):
        self.at += seconds


class CommandReadTests(RunsTest):
    """C3a/A2-A5: the slice-end read of one active execution's logs, throttled and round-robin, and what it stores.

    A scripted `log_records` captures the `(execution, options)` it was called with; the retained lines are parsed
    into `live["command"]` whatever `complete` says, a failure changes nothing, and the throttle (once per 30 s,
    round-robin over the active executions, the last accepted timestamp) lives on the controller.

    Interpretations recorded for the reviewers: the 30 s interval is an inclusive lower bound -- a read is due once
    30 s have passed since the last attempt; a failed attempt still advances the round-robin position (it was an
    attempt); the read uses the same bounded buffer (`LOG_LIMIT`) as the other log reads, with the 1 s deadline."""

    @staticmethod
    def line(message, timestamp=1791935230934):
        return json.dumps({"subscriptionId": "sub", "runId": "m-run", "timestamp": timestamp,
                           "record": {"level": "debug", "target": "codex", "message": message}})

    def ran(self, r, executions=(("worker", "e1"),), cursor="v2:5"):
        return self.envelope(r, {"phase": "running",
                                 "activeExecutions": [{"node": node, "execution": execution}
                                                      for node, execution in executions]}, cursor)

    @staticmethod
    def scripted(controller, holder, complete=True, error=None):
        """A `log_records` double: it records `(execution, options)` and returns `holder["lines"]`."""
        reads = []

        def log_records(binding, run_id, cwd, execution=None, **options):
            reads.append((execution, dict(options)))
            if error is not None:
                raise error
            return list(holder["lines"]), complete

        controller.engine.log_records = log_records
        return reads

    def test_a_slice_stores_the_last_command_of_the_active_execution_whatever_complete_says(self):
        r = self.started()
        for complete in (True, False):
            with self.subTest(complete=complete):
                holder = {"lines": [self.line("Codex command started: make test [completed] exit=0")]}
                with self.authority() as a:
                    controller, _ = self.native_runs(a, [self.ran(r)])
                    reads = self.scripted(controller, holder, complete=complete)
                    record = controller.observe(controller.active())
                self.assertEqual(record["live"]["command"],
                                 {"at": live.floored(1791935230934), "text": "make test"})
                self.assertEqual(reads, [("e1", {"deadline": runs.COMMAND_DEADLINE, "buffer": runs.LOG_LIMIT})])

    def test_a_reader_that_cannot_start_or_a_read_without_a_command_changes_nothing(self):
        r = self.started()
        with self.authority() as a:
            controller, _ = self.native_runs(a, [self.ran(r)])
            self.scripted(controller, {"lines": []}, error=OSError("reader cannot start"))
            record = controller.observe(controller.active())
            self.assertEqual((record["status"], record["live"]["command"]), ("running", None))
        with self.authority() as a:
            controller, _ = self.native_runs(a, [self.ran(r)])
            holder = {"lines": [self.line("Codex command completed: ls")]}
            self.scripted(controller, holder)
            record = controller.observe(controller.active())
            self.assertEqual((record["status"], record["live"]["command"]), ("running", None))

    def test_a_slice_without_an_active_execution_reads_nothing(self):
        r = self.started()
        idle = self.envelope(r, {"phase": "running", "activeExecutions": []}, "v2:5")
        with self.authority() as a:
            controller, _ = self.native_runs(a, [idle])
            reads = self.scripted(controller, {"lines": [self.line("Codex command started: ls")]})
            record = controller.observe(controller.active())
        self.assertEqual((record["status"], record["live"]["nodes"], reads), ("running", [], []))

    def test_the_read_is_throttled_to_once_per_30s_and_round_robins_the_active_executions(self):
        """Two slices within 30 s read once; the next read, past the interval, targets the other active execution."""
        r = self.started()
        clock = FakeClock()
        status = self.ran(r, (("worker", "e1"), ("code_review", "e2")))
        with patch("terminal_planner.runs.clock", clock), self.authority() as a:
            controller, _ = self.native_runs(a, [status, status, status])
            reads = self.scripted(controller, {"lines": []})
            for spent in (0, 10, 25):
                clock.advance(spent)
                controller.observe(controller.active())
        # The first slice reads; the second (10 s later) is throttled; the third (35 s in) reads the other execution.
        self.assertEqual([execution for execution, _ in reads], ["e1", "e2"])

    def test_the_throttle_uses_unrounded_seconds_not_the_floored_stamp(self):
        """C3a/A2: the throttle must measure real elapsed seconds, not the second-floor of the wall-clock stamp.

        Regression for a read at 09:00:00.900 followed by one at 09:00:30.000: only 29.1 s apart, yet flooring each
        `now()` stamp to whole seconds made it look like a full 30 s and read early. The attempt time is an
        unrounded monotonic `clock()` reading kept in memory, so the second attempt stays throttled and the read
        resumes only once 30.0 s have actually elapsed. Interpretations recorded for the reviewers: the interval is
        an inclusive lower bound ("no attempt in the last 30 s"), and a throttled slice still round-robins the next
        attempt."""
        r = self.started()
        clock = FakeClock(1000.9)  # 09:00:00.900
        with patch("terminal_planner.runs.clock", clock), self.authority() as a:
            controller, _ = self.native_runs(a, [self.ran(r)] * 3)
            reads = self.scripted(controller, {"lines": []})
            clock.advance(0)  # 1000.9: the first slice reads
            controller.observe(controller.active())
            clock.advance(29.1)  # 1030.0: 29.1 s later, still inside the interval
            controller.observe(controller.active())
            clock.advance(0.9)  # 1030.9: 30.0 s after the first read, due again
            controller.observe(controller.active())
        self.assertEqual([execution for execution, _ in reads], ["e1", "e1"])

    def test_a_line_not_newer_than_the_last_accepted_timestamp_is_ignored(self):
        r = self.started()
        clock = FakeClock()
        holder = {"lines": [self.line("Codex command started: first", 1000)]}
        with patch("terminal_planner.runs.clock", clock), self.authority() as a:
            controller, _ = self.native_runs(a, [self.ran(r)] * 3)
            self.scripted(controller, holder)
            clock.advance(0)
            controller.observe(controller.active())  # accepts ms 1000
            clock.advance(30)
            holder["lines"] = [self.line("Codex command started: same", 1000)]
            record = controller.observe(controller.active())  # equal ms: ignored
            self.assertEqual(record["live"]["command"]["text"], "first")
            clock.advance(30)
            holder["lines"] = [self.line("Codex command started: newer", 2000)]
            record = controller.observe(controller.active())  # greater ms: replaces
        self.assertEqual(record["live"]["command"], {"at": live.floored(2000), "text": "newer"})

    def test_a_fresh_process_accepts_a_stamp_not_older_than_the_stored_one(self):
        r = self.started()
        with self.authority() as a:
            controller, _ = self.native_runs(a, [self.ran(r)])
            self.scripted(controller, {"lines": [self.line("Codex command started: first", 2000)]})
            controller.observe(controller.active())
        with self.authority() as a:  # a new controller: nothing in memory, the stored stamp decides
            controller, _ = self.native_runs(a, [self.ran(r)])
            self.scripted(controller, {"lines": [self.line("Codex command started: stale", 1000)]})
            record = controller.observe(controller.active())  # older than the stored stamp: ignored
            self.assertEqual(record["live"]["command"]["text"], "first")
        with self.authority() as a:
            controller, _ = self.native_runs(a, [self.ran(r)])
            self.scripted(controller, {"lines": [self.line("Codex command started: newer", 3000)]})
            record = controller.observe(controller.active())  # not older: replaces
        self.assertEqual(record["live"]["command"]["text"], "newer")


class VerdictReadTests(RunsTest):
    """C4a/A2-A5: a departed reviewer is queued and read once per slice, its verdict stored in `live["verdicts"]`.

    A scripted `log_records` captures the `(execution, options)` it was called with; a reviewer that leaves
    `live["nodes"]` is queued with the task and round of that moment, a worker that leaves is not, and the slice
    that closes a queued reviewer makes no C3a command read.

    Interpretations recorded for the reviewers: the reason is the first non-empty line stripped of its surrounding
    whitespace; the queue is drained one entry per slice (the oldest first) and an OSError (any failure of the read)
    is one read that found nothing, so an entry survives exactly one failed read."""

    @staticmethod
    def line(message, timestamp=1791935230934):
        return json.dumps({"subscriptionId": "sub", "runId": "m-run", "timestamp": timestamp,
                           "record": {"level": "info", "target": "native_v2_runner", "message": message}})

    @classmethod
    def response(cls, verdict="accepted", reason="ok", timestamp=1791935230934):
        body = {"response": {"diagnostic": {"message": reason}, "output": None, "signals": {"verdict": verdict}}}
        return cls.line(json.dumps(body), timestamp)

    @staticmethod
    def scripted(controller, holder, complete=True, error=None):
        """A `log_records` double: it records `(execution, options)` and returns `holder["lines"]`."""
        reads = []

        def log_records(binding, run_id, cwd, execution=None, **options):
            reads.append((execution, dict(options)))
            if error is not None:
                raise error
            return list(holder["lines"]), complete

        controller.engine.log_records = log_records
        return reads

    def active(self, r, executions, cursor):
        return self.envelope(r, {"phase": "running",
                                 "activeExecutions": [{"node": node, "execution": execution}
                                                      for node, execution in executions]}, cursor)

    def test_a_departed_reviewer_is_queued_with_its_task_and_round_and_read_once_per_slice(self):
        r = self.started()
        reviewed = self.active(r, (("worker", "w1"), ("acceptance_review", "a1"), ("code_review", "c1")), "v2:1")
        after = self.active(r, (("worker", "w1"),), "v2:2")
        with self.authority() as a:
            controller, _ = self.native_runs(a, [reviewed, after])
            holder = {"lines": [self.response("rejected", "no test for the refusal")]}
            reads = self.scripted(controller, holder)
            controller.observe(controller.active())  # a1, c1 appear
            record = controller.observe(controller.active())  # both leave; a1 is read this slice
        self.assertEqual(record["live"]["verdicts"],
                         [{"at": live.floored(1791935230934), "task": "T1", "round": 1,
                           "role": "acceptance_review", "verdict": "rejected", "text": "no test for the refusal"}])
        # The C3a command read ran on the first slice; the second slice read the departed reviewer, not a command.
        self.assertEqual([execution for execution, _ in reads], ["w1", "a1"])
        self.assertEqual(reads[-1], ("a1", {"deadline": runs.VERDICT_DEADLINE, "buffer": runs.LOG_LIMIT}))

    def test_a_worker_that_leaves_is_not_queued(self):
        r = self.started()
        working = self.active(r, (("worker", "w1"),), "v2:1")
        empty = self.active(r, (), "v2:2")
        with self.authority() as a:
            controller, _ = self.native_runs(a, [working, empty])
            reads = self.scripted(controller, {"lines": []})
            controller.observe(controller.active())
            controller.observe(controller.active())
        self.assertEqual(controller.verdicts.get("m-run", {"queue": []})["queue"], [])

    def test_an_oserror_twice_drops_the_queued_entry(self):
        r = self.started()
        reviewed = self.active(r, (("worker", "w1"), ("acceptance_review", "a1")), "v2:1")
        after = self.active(r, (("worker", "w1"),), "v2:2")
        again = self.active(r, (("worker", "w1"),), "v2:3")
        with self.authority() as a:
            controller, _ = self.native_runs(a, [reviewed, after, again])
            self.scripted(controller, {"lines": []}, error=OSError("reader cannot start"))
            controller.observe(controller.active())  # a1 appears
            controller.observe(controller.active())  # a1 leaves; first read fails
            self.assertEqual([item["execution"] for item in controller.verdicts["m-run"]["queue"]], ["a1"])
            record = controller.observe(controller.active())  # second read fails: dropped
        self.assertEqual(controller.verdicts["m-run"]["queue"], [])
        self.assertEqual(record["live"]["verdicts"], [])

    def test_a_found_verdict_is_appended_once_for_an_execution(self):
        r = self.started()
        reviewed = self.active(r, (("worker", "w1"), ("acceptance_review", "a1")), "v2:1")
        after = self.active(r, (("worker", "w1"),), "v2:2")
        back = self.active(r, (("worker", "w1"), ("acceptance_review", "a1")), "v2:3")
        gone = self.active(r, (("worker", "w1"),), "v2:4")
        with self.authority() as a:
            controller, _ = self.native_runs(a, [reviewed, after, back, gone])
            self.scripted(controller, {"lines": [self.response("accepted", "note: ok")]})
            for _ in range(4):
                record = controller.observe(controller.active())
        self.assertEqual(len(record["live"]["verdicts"]), 1)
        self.assertEqual(controller.verdicts["m-run"]["queue"], [])

    def test_a_run_that_finishes_in_the_same_slice_still_reads_its_queued_reviewers(self):
        """C4a/A3 regression: the record that finishes the run must not skip the slice's bounded verdict read.

        Reproduces the accepted defect: one `observe` delivers the worker and its two reviewers, then the writing
        and verification stages and finally `finished(done)`; the reviewers leave `live["nodes"]` while the run is
        still running, so the queue is full when the terminal record arrives, and the old terminal branch returned
        before the read. Interpretation recorded for the reviewers: the terminal record is itself a watch record,
        so a reviewer it no longer lists is queued there too (its log is complete and the run is never observed
        again); the slice still makes exactly its one bounded read (the oldest entry), so a second queued reviewer
        is left for a slice that can no longer run rather than reading twice."""
        r = self.started()
        self.complete(r)
        reviewed = self.active(r, (("worker", "w1"), ("acceptance_review", "a1"), ("code_review", "c1")), "v2:1")
        writing = self.active(r, (("steward_apply", "s1"),), "v2:2")
        verifying = self.active(r, (("final_verify", "f1"),), "v2:3")
        done = self.finished(r, DONE, cursor="v2:4")
        with self.authority() as a:
            controller, _ = self.native_runs(a, [(reviewed, writing, verifying, done)])
            reads = self.scripted(controller, {"lines": [self.response("rejected", "no test for the refusal")]})
            record = controller.observe(controller.active())
        self.assertEqual((record["status"], record["outcome"]), ("finished", "done"))
        self.assertEqual(record["live"]["verdicts"],
                         [{"at": live.floored(1791935230934), "task": "T1", "round": 1,
                           "role": "acceptance_review", "verdict": "rejected", "text": "no test for the refusal"}])
        # The terminal slice read the departed reviewer a1, and it made no C3a command read.
        self.assertEqual([execution for execution, _ in reads], ["a1"])
        self.assertNotIn("c1", [execution for execution, _ in reads])

    def test_a_reviewer_that_leaves_only_with_the_terminal_record_is_queued_and_read(self):
        """C4a/A2-A3 regression: the finished record queues a reviewer it no longer lists, then reads it.

        Same interpretation as the previous regression: `activeExecutions` absent from a finished projection means
        no execution is active, so a reviewer still in `live["nodes"]` when the run finishes has departed there."""
        r = self.started()
        self.complete(r)
        working = self.active(r, (("worker", "w1"), ("acceptance_review", "a1")), "v2:1")
        done = self.finished(r, DONE, cursor="v2:2")
        with self.authority() as a:
            controller, _ = self.native_runs(a, [(working, done)])
            reads = self.scripted(controller, {"lines": [self.response("accepted", "ok")]})
            record = controller.observe(controller.active())
        self.assertEqual((record["status"], record["outcome"]), ("finished", "done"))
        self.assertEqual([execution for execution, _ in reads], ["a1"])
        self.assertEqual(record["live"]["verdicts"],
                         [{"at": live.floored(1791935230934), "task": "T1", "round": 1,
                           "role": "acceptance_review", "verdict": "accepted", "text": "ok"}])



class CrashWindowTests(RunsTest):
    def crash_start(self, target, responses=()):
        self.approve_native()
        with self.authority() as a:
            controller, calls = self.native_runs(a, list(responses))
            with patch.object(*target, side_effect=Crash), self.assertRaises(Crash):
                controller.start("M1", 1, ROLES)
            saved = self.stored(a)
            self.assertEqual(len(saved), 1)
            return saved[0], calls

    def reopen_dispatches_once(self, r, responses=({"valid": True}, {"runId": "m-run"})):
        with self.authority() as a:
            controller, calls = self.native_runs(a, list(responses))
            with self.assertRaisesRegex(Blocked, "M1 is already running"):
                controller.start("M1", 1, ROLES)
            adopted = controller.reconcile()
            self.assertEqual((adopted["status"], adopted["run_id"]), ("submitted", "m-run"))
            self.assertEqual(adopted["submission_key"], r["submission_key"])
            self.assertEqual(len(a.state["runs"]), 1)
            self.assertIsNotNone(controller.reconcile())
            return adopted, calls

    def test_crash_before_worktree_creation(self):
        r, calls = self.crash_start((MilestoneRuns, "prepare"))
        self.assertEqual((r["status"], calls), ("preparing", []))
        self.assertFalse(Path(r["worktree"]).exists())
        _, calls = self.reopen_dispatches_once(r)
        self.assertEqual([c[0][-1] for c in calls], ["--validate-only", "--detach"])

    def test_crash_after_worktree_creation_and_with_branch_but_no_directory(self):
        r, _ = self.crash_start((MilestoneRuns, "check_worktree"))
        worktree = Path(r["worktree"])
        self.assertTrue(worktree.is_dir())
        self.assertFalse((worktree / milestone.MANIFEST).exists())
        # Worst case: the branch exists but the directory is gone; the branch is reused only at the base.
        planner.shutil.rmtree(worktree)
        self.reopen_dispatches_once(r)
        self.assertTrue((worktree / milestone.MANIFEST).is_file())
        listed = self.git("worktree", "list", "--porcelain").decode()
        self.assertEqual(listed.count(str(worktree)), 1)

    def test_branch_moved_off_base_blocks_preparation(self):
        r, _ = self.crash_start((MilestoneRuns, "check_worktree"))
        worktree = Path(r["worktree"])
        subprocess.run(["git", "-C", str(worktree), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                        "commit", "-q", "--allow-empty", "-m", "foreign"], check=True)
        planner.shutil.rmtree(worktree)
        with self.authority() as a:
            controller, calls = self.native_runs(a, [])
            with self.assertRaisesRegex(Blocked, "is not on base"):
                controller.reconcile()
            self.assertEqual(calls, [])
            self.assertEqual(self.stored(a)[0]["status"], "failed")
            self.assertIsNone(self.stored(a)[0]["run_id"])

    def test_milestone_worktree_branch_config_is_rewritten_on_a_reused_worktree(self):
        # A crash right after the worktree is created leaves the branch config unwritten (or foreign); the reused
        # worktree must be pinned to origin again, idempotently.
        self.git("remote", "add", "backup", "https://github.com/example/backup.git")
        r, _ = self.crash_start((MilestoneRuns, "check_worktree"))
        worktree = Path(r["worktree"])
        subprocess.run(["git", "-C", str(worktree), "config", "branch.%s.remote" % r["branch"], "backup"], check=True)
        subprocess.run(["git", "-C", str(worktree), "config", "branch.%s.merge" % r["branch"], "refs/heads/foreign"],
                       check=True)
        self.reopen_dispatches_once(r)
        self.assertEqual(self.config(worktree, "branch.%s.remote" % r["branch"]), "origin")
        self.assertEqual(self.config(worktree, "branch.%s.merge" % r["branch"]), "refs/heads/" + r["branch"])

    def refused_admission_settles_failed(self, response):
        self.approve_native()
        with self.authority() as a:
            controller, calls = self.native_runs(a, [response])
            with self.assertRaises(Blocked):
                controller.start("M1", 1, ROLES)
            r = self.stored(a)[0]
            self.assertEqual((r["status"], r["run_id"], r["terminal"]), ("failed", None, None))
            self.assertTrue(r["diagnostic"])
            controller, calls = self.native_runs(a, [{"valid": True}, {"runId": "m-run"}])
            second = controller.start("M1", 1, ROLES)
            self.assertEqual((second["attempt"], second["status"]), (2, "submitted"))
            self.assertEqual([c[0][-1] for c in calls], ["--validate-only", "--detach"])

    def test_native_exit_refusal_settles_failed_and_frees_the_project(self):
        self.refused_admission_settles_failed(subprocess.CompletedProcess([], 1, "", "invalid model"))

    def test_native_invalid_admission_settles_failed_and_frees_the_project(self):
        self.refused_admission_settles_failed({"valid": False})

    def test_crash_after_bootstrap(self):
        r, calls = self.crash_start((MilestoneRuns, "preflight"))
        self.assertEqual(calls, [])
        manifest = (Path(r["worktree"]) / milestone.MANIFEST).read_text()
        self.reopen_dispatches_once(r)
        self.assertEqual((Path(r["worktree"]) / milestone.MANIFEST).read_text(), manifest)

    def lost_receipt(self, outcomes=()):
        """Attempt 1 dispatched natively, receipt lost: (stored record, ledger driver, calls, submissions)."""
        self.approve_native()
        driver, calls, submissions = self.ledger(outcomes, lose_receipt=True)
        with self.authority() as a:
            with self.assertRaises(Crash):
                MilestoneRuns(a, driver, worktrees=self.worktrees).start("M1", 1, ROLES)
            r = self.stored(a)[0]
        self.assertEqual((r["status"], r["run_id"], len(submissions)), ("submission_unknown", None, 1))
        return r, driver, calls, submissions

    def test_crash_after_dispatch_before_receipt_replays_the_identical_submission(self):
        r, driver, calls, submissions = self.lost_receipt()
        # The live run may already have written its manifest: replay must not rewrite or reset it.
        self.complete(r)
        progressed = (Path(r["worktree"]) / milestone.MANIFEST).read_text()
        with self.authority() as a:
            controller = MilestoneRuns(a, driver, worktrees=self.worktrees)
            refused, _, _ = self.ledger([subprocess.CompletedProcess([], 3, "", "conflict")])
            with self.assertRaisesRegex(Blocked, "code 3"):
                MilestoneRuns(a, refused, worktrees=self.worktrees).reconcile()
            self.assertEqual(self.stored(a)[0]["status"], "submission_unknown")
            adopted = controller.reconcile()
        self.assertEqual((adopted["status"], adopted["run_id"]), ("submitted", "m-run-1"))
        self.assertEqual(len(submissions), 1)
        self.assertEqual((Path(r["worktree"]) / milestone.MANIFEST).read_text(), progressed)
        detach = [c for c in calls if c[0][-1] == "--detach"]
        self.assertEqual(len(detach), 2)
        self.assertEqual(detach[0][0], detach[1][0])
        self.assertEqual(detach[1][1]["cwd"], r["worktree"])

    def test_replay_after_head_moved_is_blocked_and_never_resets_the_worktree(self):
        r, driver, calls, submissions = self.lost_receipt()
        worktree = r["worktree"]
        # The live writer committed in its worktree: the frozen HEAD no longer holds.
        subprocess.run(["git", "-C", worktree, "-c", "user.name=w", "-c", "user.email=w@example.invalid",
                        "commit", "-q", "--allow-empty", "-m", "writer"], check=True)
        moved, sent = self.worktree_head(r), len(calls)
        with self.authority() as a:
            with self.assertRaisesRegex(Blocked, "is not on base commit.*replay forbidden, the worktree is unchanged"):
                MilestoneRuns(a, driver, worktrees=self.worktrees).reconcile()
            self.assertEqual(self.stored(a)[0]["status"], "submission_unknown")
        subprocess.run(["git", "-C", worktree, "checkout", "-q", "-b", "elsewhere"], check=True)
        with self.authority() as a:
            with self.assertRaisesRegex(Blocked, "is not on the working branch.*replay forbidden"):
                MilestoneRuns(a, driver, worktrees=self.worktrees).reconcile()
        self.assertEqual((self.worktree_head(r), len(calls), len(submissions)), (moved, sent, 1))

    def test_unknown_submission_never_replays_against_a_changed_binding(self):
        r, _ = self.crash_start((NativeDriver, "submit"), [{"valid": True}])
        with self.authority() as a:
            driver, calls = self.driver([])
            driver.state_root = Path("/zp-other")
            with self.assertRaisesRegex(Blocked, "binary/state"):
                MilestoneRuns(a, driver, worktrees=self.worktrees).reconcile()
            self.assertEqual(calls, [])

    def test_crash_during_resume_adopts_the_native_successor_only(self):
        r = self.started()
        with self.authority() as a:
            controller, _ = self.native_runs(a, [(self.finished(r, reason="worker_failed"),),
                                                 self.status(r, {"recoverable": True}), self.status(r, {"recoverable": True})])
            r = controller.observe(controller.active())
            with patch.object(NativeDriver, "resume", side_effect=Crash), self.assertRaises(Crash):
                controller.resume(r)
            pending = self.stored(a)[1]
            self.assertEqual((pending["status"], pending["predecessor"], pending["run_id"]), ("resume_pending", "m-run", None))
        with self.authority() as a:
            controller, calls = self.native_runs(a, [self.status(r, {"recoverable": True})])
            with self.assertRaisesRegex(Blocked, "no successorRunId"):
                controller.reconcile()
            with self.assertRaisesRegex(Blocked, "already resumed"):
                controller.resume(a.state["runs"][0])
            self.assertEqual(self.stored(a)[1]["status"], "resume_pending")
        with self.authority() as a:
            successor = self.status(r, {"recoverable": True, "resumedFrom": "m-run"}, run_id="m-run-2")
            controller, more = self.native_runs(a, [self.status(r, {"recoverable": True, "successorRunId": "m-run-2"}), successor])
            adopted = controller.reconcile()
            self.assertEqual((adopted["status"], adopted["run_id"], adopted["predecessor"]), ("submitted", "m-run-2", "m-run"))
        self.assertEqual([c[0][1:] for c in calls + more], [["status", "m-run"], ["status", "m-run"], ["status", "m-run-2"]])

    def test_successor_with_foreign_lineage_is_not_adopted(self):
        r = self.started()
        with self.authority() as a:
            controller, _ = self.native_runs(a, [(self.finished(r, reason="worker_failed"),), self.status(r, {"recoverable": True}),
                                                 self.status(r, {"recoverable": True}), OSError("lost")])
            r = controller.observe(controller.active())
            with self.assertRaises(Blocked):
                controller.resume(r)
        with self.authority() as a:
            foreign = self.status(r, {"recoverable": True, "resumedFrom": "other"}, run_id="m-run-2")
            controller, _ = self.native_runs(a, [self.status(r, {"recoverable": True, "successorRunId": "m-run-2"}), foreign])
            with self.assertRaisesRegex(Blocked, "lineage is not confirmed"):
                controller.reconcile()
            self.assertEqual(self.stored(a)[1]["status"], "resume_pending")

    def test_crash_after_stopping_before_force_stop(self):
        r = self.started()
        with self.authority() as a:
            controller, calls = self.native_runs(a, [])
            with patch.object(NativeDriver, "force_stop", side_effect=Crash), self.assertRaises(Crash):
                controller.stop(controller.active())
            self.assertEqual(self.stored(a)[0]["status"], "stopping")
        with self.authority() as a:
            # The stop request was persisted but never sent: reopen checks native status and sends it.
            controller, calls = self.native_runs(a, [self.live(r), subprocess.CompletedProcess([], 0, "", ""),
                                                     (self.finished(r, reason="force_stopped"),)])
            r = controller.reconcile()
            self.assertEqual(r["status"], "stopping")
            self.assertEqual(controller.observe(r)["status"], "stopped")
            self.assertEqual([c[0][1] for c in calls], ["status", "force-stop", "watch"])

    def test_unsent_stop_of_an_already_finished_run_concludes_without_force_stop(self):
        r = self.started()
        with self.authority() as a:
            controller, _ = self.native_runs(a, [])
            with patch.object(NativeDriver, "force_stop", side_effect=Crash), self.assertRaises(Crash):
                controller.stop(controller.active())
        with self.authority() as a:
            controller, calls = self.native_runs(a, [self.status(r, {"recoverable": False}, reason="worker_failed")])
            self.assertIsNone(controller.reconcile())
            self.assertEqual(self.stored(a)[0]["status"], "stopped")
            self.assertEqual([c[0][1] for c in calls], ["status"])


class FixtureDriverTests(RunsTest):
    def test_each_scripted_outcome(self):
        self.approve_fixture()
        expected = {"done": ("finished", "done"), "needs_owner": ("finished", "needs_owner"), "blocked": ("finished", "blocked"),
                    "failed_recoverable": ("failed", None), "failed": ("failed", None)}
        attempts = 0
        for outcome, (status, signal) in expected.items():
            with self.subTest(outcome):
                with self.fixture_authority() as a:
                    controller = self.fixture_runs(a, outcome)
                    r = controller.start("M1", 1, ROLES)
                    attempts += 1
                    self.assertEqual(r["attempt"], attempts)
                    self.assertEqual(r["run_id"], "fixture-" + runs.hashlib.sha256(r["submission_key"].encode()).hexdigest()[:16])
                    r = controller.observe(r)
                    self.assertEqual((r["status"], r["outcome"]), (status, signal))
                    worktree = Path(r["worktree"])
                    self.assertTrue((worktree / "ZPLAN_FIXTURE.md").is_file())
                    self.assertEqual(subprocess.check_output(["git", "-C", str(worktree), "rev-parse", "HEAD"]).decode().strip(),
                                     r["destination"]["base"])
                    self.assertIn(b"ZPLAN_FIXTURE.md", subprocess.check_output(
                        ["git", "-C", str(worktree), "status", "--porcelain", "--untracked-files=all"]))
                    self.assertEqual(self.git("status", "--porcelain"), b"")
                    if outcome == "done":
                        self.assertTrue(all(t["status"] == "done" for t in r["manifest"]["tasks"]))
                    if outcome == "needs_owner":
                        self.assertTrue(r["output"]["question"] and r["output"]["proposal"])
                    if status == "failed":
                        self.assertIs(r["recoverable"], outcome == "failed_recoverable")
                    if outcome == "failed_recoverable":
                        successor = controller.observe(controller.resume(r))
                        self.assertEqual((successor["outcome"], successor["predecessor"]), ("done", r["run_id"]))
                        with self.assertRaisesRegex(Blocked, "already resumed"):
                            controller.resume(r)
                    elif outcome == "failed":
                        with self.assertRaisesRegex(Blocked, "not recoverable"):
                            controller.resume(r)
        with self.fixture_authority() as a:
            self.assertEqual(len(a.state["runs"]), 6)

    def test_fixture_submission_is_idempotent(self):
        self.approve_fixture()
        with self.fixture_authority() as a:
            controller = self.fixture_runs(a)
            with patch.object(MilestoneRuns, "adopt_submission", side_effect=Crash), self.assertRaises(Crash):
                controller.start("M1", 1, ROLES)
        with self.fixture_authority() as a:
            controller = self.fixture_runs(a)
            r = controller.reconcile()
            self.assertEqual(r["status"], "submitted")
            first = r["run_id"]
            self.assertEqual(controller.engine.submit(r, controller.frozen(r))["runId"], first)
            self.assertEqual(sorted(p.name for p in (self.root / "fixture-runs").iterdir()), [first + ".json"])


def split_candidate(additions=2):
    """Steward task-list candidate for M1 of the fixture plan: split T1 into `additions` children."""
    children = ["T1.%s" % i for i in range(1, additions + 1)]
    return {"tasks": [{"id": "T1", "title": "Implement the agreed behavior", "checks": ["Deterministic interaction test"],
                       "status": "dropped", "origin": "plan", "notes": ""}]
            + [{"id": c, "title": "Part %s" % c, "checks": ["Deterministic interaction test"], "status": "open",
                "origin": "amendment", "notes": "", "parent": "T1"} for c in children],
            "amendments": [{"seq": 1, "kind": "split", "tasks": children, "parents": ["T1"], "reason": "Smaller steps."}]}


def roadmap(change=None):
    """Fixture plan with M3 depending on M2; `change` edits one milestone's scope."""
    plan = fixture_proposal()
    plan["requirements"].append({"id": "R3", "text": "Polish the result."})
    plan["milestones"].append({"id": "M3", "title": "Polish", "depends_on": ["M2"], "slices": [
        {"id": "S3", "title": "Polish", "requirements": ["R3"], "tasks": [
            {"id": "T3", "title": "Polish the result", "checks": ["Polish check"]}]}]})
    if change:
        found = next(m for m in plan["milestones"] if m["id"] == change)
        found["slices"][0]["tasks"][0]["title"] += " (changed)"
    return plan


class DeliveryTests(RunsTest):
    def done(self, a, milestone_id="M1", revision=1):
        controller = self.fixture_runs(a)
        r = controller.observe(controller.start(milestone_id, revision, ROLES))
        self.assertEqual(r["outcome"], "done")
        return controller, r

    def test_done_export_merge_makes_the_dependent_ready_from_the_merge_commit(self):
        self.approve_fixture()
        base = self.head()
        with self.fixture_authority() as a:
            controller, r = self.done(a)
            self.assertEqual((r["delivery"], r["result"]["commit"]), ("none", None))
            self.assertEqual(r["result"]["tree"], controller.product_tree(r))
            self.assertEqual(runs.owner_actions(r), ("finish",))
            controller.finish(r)
            sha = r["result"]["commit"]
            self.assertEqual((r["delivery"], r["result"]["branch"]), ("awaiting_merge", runs.result_branch(r)))
            self.assertRegex(r["result"]["branch"], r"^zplan/m1-[0-9a-f]{6}-r1-[0-9a-f]{8}-a1$")
            self.assertEqual(self.git("rev-parse", "refs/heads/" + r["result"]["branch"]).decode().strip(), sha)
            self.assertEqual(self.parents(sha), [base])
            self.assertEqual(self.tree(sha), ["ZPLAN_FIXTURE.md", "source.txt"])
            self.assertEqual((self.head(), self.git("status", "--porcelain")), (base, b""))
            self.assertIs(controller.finish(r), r)
            self.assertEqual(runs.owner_actions(r), ("merge",))
            with self.assertRaisesRegex(Blocked, "M2 is waiting for M1"):
                controller.start("M2", 1, ROLES)
            controller.merge(r)
            merge = self.head()
            self.assertEqual(self.parents(merge), [base, sha])
            self.assertEqual(self.git("log", "-1", "--format=%an <%ae>", merge).decode().strip(), "Fixture <fixture@example.invalid>")
            self.assertEqual((r["delivery"], r["integration"]), ("integrated", {
                "destination": "refs/heads/" + r["destination"]["branch"], "commit": merge, "conflicts": [], "aborted": None}))
            self.assertEqual(self.git("status", "--porcelain"), b"")
            m2 = controller.observe(controller.start("M2", 1, ROLES))
            self.assertEqual((m2["destination"]["base"], self.worktree_head(m2), m2["outcome"]), (merge, merge, "done"))
        with self.fixture_authority() as a:
            self.assertEqual(a.state["runs"][0]["delivery"], "integrated")

    def test_pruned_result_commit_is_not_merged_and_never_blocks_reconcile(self):
        self.approve_fixture()
        with self.fixture_authority() as a:
            controller, r = self.done(a)
            controller.finish(r)
            sha = r["result"]["commit"]
            self.git("branch", "-D", r["result"]["branch"])
            self.git("reflog", "expire", "--expire=now", "--all")
            self.git("gc", "-q", "--prune=now")
            self.assertNotEqual(subprocess.run(["git", "-C", str(self.project), "cat-file", "-e", sha + "^{commit}"],
                                               capture_output=True).returncode, 0)
            self.assertIsNone(controller.reconcile())
            self.assertEqual((r["delivery"], controller.waiting("M2")), ("awaiting_merge", ["M1"]))
            with self.assertRaisesRegex(Blocked, "M2 is waiting for M1"):
                controller.start("M2", 1, ROLES)

    def test_manual_merge_is_detected_unmerged_blocks_and_a_reset_removes_readiness(self):
        self.approve_fixture()
        base = self.head()
        with self.fixture_authority() as a:
            controller, r = self.done(a)
            controller.finish(r)
            sha = r["result"]["commit"]
            self.assertEqual(controller.waiting("M2"), ["M1"])
            self.git("merge", "--no-ff", "-q", "-m", "owner merge", sha)
            manual = self.head()
            self.assertIsNone(controller.reconcile())
            self.assertEqual((r["delivery"], r["integration"]["commit"]), ("integrated", manual))
            self.assertEqual(controller.waiting("M2"), [])
            self.git("reset", "-q", "--hard", base)
            controller.refresh()
            self.assertEqual((r["delivery"], r["integration"]["commit"]), ("awaiting_merge", None))
            self.assertEqual(controller.waiting("M2"), ["M1"])
            with self.assertRaisesRegex(Blocked, "M2 is waiting for M1"):
                controller.start("M2", 1, ROLES)
            # A fast-forward makes the result commit itself the integration point.
            self.git("merge", "--ff-only", "-q", sha)
            controller.refresh()
            self.assertEqual((r["delivery"], r["integration"]["commit"]), ("integrated", sha))
            self.assertEqual(controller.start("M2", 1, ROLES)["destination"]["base"], sha)

    def test_identity_is_the_exportable_files_and_an_ignored_hardlinked_dependency_keeps_acceptance(self):
        (self.project / ".gitignore").write_text("node_modules/\nbuild/\n")
        (self.project / "build").mkdir()
        (self.project / "build" / "keep.txt").write_text("tracked although ignored\n")
        self.git("add", ".gitignore")
        self.git("add", "-f", "build/keep.txt")
        self.git("commit", "-qm", "ignore dependencies")
        self.approve_fixture()
        store = self.root / "pnpm-store"
        store.mkdir()
        (store / "index.js").write_text("module.exports = 1;\n")
        with self.fixture_authority() as a:
            controller = self.fixture_runs(a)
            r = controller.start("M1", 1, ROLES)
            worktree = Path(r["worktree"])
            package = worktree / "node_modules" / "pkg"
            package.mkdir(parents=True)
            os.link(store / "index.js", package / "index.js")  # pnpm-style hardlink into a shared store
            controller.observe(r)
            self.assertEqual((r["status"], r["outcome"]), ("finished", "done"), r["diagnostic"])
            tree = r["result"]["tree"]
            (package / "cache.json").write_text("{}\n")
            self.assertEqual(controller.product_tree(r), tree)
            for path, text in ((worktree / "build" / "keep.txt", "edited\n"), (worktree / "notes.txt", "new file\n")):
                original = path.read_text() if path.exists() else None
                path.write_text(text)
                self.assertNotEqual(controller.product_tree(r), tree, path.name)
                path.write_text(original) if original is not None else path.unlink()
            controller.finish(r)
            self.assertEqual(r["delivery"], "awaiting_merge")
            self.assertEqual(self.tree(r["result"]["commit"]), [".gitignore", "ZPLAN_FIXTURE.md", "build/keep.txt", "source.txt"])

    def test_a_checked_out_result_branch_never_makes_the_dependent_ready(self):
        self.approve_fixture()
        with self.fixture_authority() as a:
            controller, r = self.done(a)
            controller.finish(r)
            self.git("checkout", "-q", r["result"]["branch"])
            self.assertEqual(controller.waiting("M2"), ["M1"])
            with self.assertRaisesRegex(Blocked, "M2 is waiting for M1"):
                controller.start("M2", 1, ROLES)
            self.assertEqual(r["delivery"], "awaiting_merge")

    def conflicted(self, a):
        controller, r = self.done(a)
        controller.finish(r)
        (self.project / "ZPLAN_FIXTURE.md").write_text("owner version\n")
        self.git("add", "ZPLAN_FIXTURE.md")
        self.git("commit", "-qm", "owner edit")
        return controller, r, self.head()

    def test_conflict_records_files_leaves_the_tree_alone_then_a_manual_merge_is_detected(self):
        self.approve_fixture()
        with self.fixture_authority() as a:
            controller, r, owner = self.conflicted(a)
            self.assertIs(controller.merge(r), r)
            self.assertEqual((r["delivery"], r["integration"]["conflicts"], r["integration"]["aborted"]),
                             ("conflict", ["ZPLAN_FIXTURE.md"], True))
            self.assertEqual((self.head(), self.git("status", "--porcelain")), (owner, b""))
            self.assertFalse((self.project / ".git" / "MERGE_HEAD").exists())
            self.assertEqual(runs.owner_actions(r), ("merge",))
            # The owner resolves it by hand and commits.
            subprocess.run(["git", "-C", str(self.project), "merge", "-q", r["result"]["commit"]], capture_output=True)
            (self.project / "ZPLAN_FIXTURE.md").write_text("resolved\n")
            self.git("add", "ZPLAN_FIXTURE.md")
            self.git("commit", "-q", "--no-edit")
            resolved = self.head()
            controller.refresh()
            self.assertEqual((r["delivery"], r["integration"]["commit"], r["integration"]["conflicts"]),
                             ("integrated", resolved, ["ZPLAN_FIXTURE.md"]))
        with self.fixture_authority() as a:
            self.assertEqual(a.state["runs"][0]["integration"]["commit"], resolved)

    def test_merge_refuses_wrong_branch_and_missing_identity(self):
        self.approve_fixture()
        with self.fixture_authority() as a:
            controller, r = self.done(a)
            with self.assertRaisesRegex(Blocked, "exported result"):
                controller.merge(r)
            controller.finish(r)
            head = self.head()
            self.git("checkout", "-q", "-b", "elsewhere")
            with self.assertRaisesRegex(Blocked, "git switch"):
                controller.merge(r)
            self.git("checkout", "-q", "-")
            self.git("config", "--unset", "user.name")
            with self.assertRaisesRegex(Blocked, "user.name"):
                controller.merge(r)
            self.assertEqual((self.head(), r["delivery"]), (head, "awaiting_merge"))

    def test_export_refuses_a_tree_or_manifest_edited_after_acceptance(self):
        self.approve_fixture()
        with self.fixture_authority() as a:
            controller, r = self.done(a)
            extra = Path(r["worktree"]) / "late.txt"
            extra.write_text("edited after acceptance\n")
            with self.assertRaisesRegex(Blocked, "The product tree changed after acceptance"):
                controller.finish(r)
            extra.unlink()
            path = Path(r["worktree"]) / milestone.MANIFEST
            accepted = path.read_text()
            manifest = decode(accepted)
            manifest["tasks"][0]["notes"] = "edited"
            atomic_state(path, manifest)
            with self.assertRaisesRegex(Blocked, "The manifest or baseline"):
                controller.finish(r)
            self.assertEqual((self.stored(a)[0]["delivery"], self.git("for-each-ref", "refs/heads/zplan")), ("none", b""))
            path.write_text(accepted)
            # Control files are outside the product tree and never reach the result branch.
            (Path(r["worktree"]) / ".zplan" / "scratch.json").write_text("{}\n")
            controller.finish(r)
            self.assertFalse([p for p in self.tree(r["result"]["commit"]) if p.startswith(".zplan")])

    def test_crash_after_branch_creation_adopts_only_the_matching_result(self):
        self.approve_fixture()
        real = runs.create_branch

        def created_then_crash(*args, **kwargs):
            real(*args, **kwargs)
            raise Crash

        with self.fixture_authority() as a:
            controller, r = self.done(a)
            with patch.object(runs, "create_branch", side_effect=created_then_crash), self.assertRaises(Crash):
                controller.finish(r)
            self.assertEqual(self.stored(a)[0]["delivery"], "exporting")
            tip = self.git("rev-parse", "refs/heads/" + r["result"]["branch"]).decode().strip()
        with self.fixture_authority() as a:
            r = a.state["runs"][0]
            (Path(r["worktree"]) / "late.txt").write_text("edited while exporting\n")
            with self.assertRaisesRegex(Blocked, "The snapshot does not match"):
                self.fixture_runs(a).finish(r)
            (Path(r["worktree"]) / "late.txt").unlink()
            self.fixture_runs(a).finish(r)
            self.assertEqual((r["delivery"], r["result"]["commit"]), ("awaiting_merge", tip))


class OwnerActionTests(RunsTest):
    def needs_owner(self, a, proposal):
        controller = MilestoneRuns(a, FixtureDriver(self.root / "fixture-runs", "needs_owner", proposal),
                                   worktrees=self.worktrees)
        r = controller.observe(controller.start("M1", 1, ROLES))
        self.assertEqual((r["outcome"], runs.owner_actions(r)), ("needs_owner", ("accept_proposal", "answer", "revise")))
        return controller, r

    def test_answer_starts_a_fresh_attempt_with_the_note_and_reopened_tasks_across_a_crash(self):
        r = self.started()
        self.complete(r)
        blocked = {"signal": "blocked", "message": "Need a decision.", "question": "Which API?", "proposal": None}
        with self.authority() as a:
            controller, _ = self.native_runs(a, [(self.finished(r, blocked),)])
            r = controller.observe(controller.active())
            self.assertEqual((r["outcome"], r["manifest"]["tasks"][0]["status"]), ("blocked", "done"))
            self.assertEqual(runs.owner_actions(r), ("answer", "revise"))
        (self.project / "source.txt").write_text("owner change\n")
        self.git("commit", "-qam", "owner change")
        with self.authority() as a:
            controller, calls = self.native_runs(a, [])
            with patch.object(MilestoneRuns, "preflight", side_effect=Crash), self.assertRaises(Crash):
                controller.answer(a.state["runs"][0], "Use the v2 API.")
            pending = self.stored(a)[1]
            self.assertEqual((pending["status"], pending["attempt"], pending["context"]), ("preparing", 2, {
                "kind": "answer", "source": 1, "text": "Use the v2 API.", "candidate": None}))
        with self.authority() as a:
            controller, calls = self.native_runs(a, [{"valid": True}, {"runId": "m-run-2"}])
            fresh = controller.reconcile()
            self.assertEqual((fresh["status"], fresh["attempt"], fresh["destination"]["base"]), ("submitted", 2, self.head()))
            manifest = decode((Path(fresh["worktree"]) / milestone.MANIFEST).read_text())
            self.assertEqual([(t["id"], t["status"], t["notes"]) for t in manifest["tasks"]],
                             [("T1", "open", "Owner answer (attempt 1): Use the v2 API.")])
            self.assertEqual(digest(manifest), fresh["bootstrap"])
            with self.assertRaisesRegex(Blocked, "no longer the last"):
                controller.answer(a.state["runs"][0], "Again.")

    def test_structured_in_scope_proposal_starts_an_attempt_from_the_candidate(self):
        self.approve_fixture()
        with self.fixture_authority() as a:
            controller, r = self.needs_owner(a, canonical(split_candidate()))
            controller.engine = FixtureDriver(self.root / "fixture-runs", "done")
            kind, fresh = controller.accept_proposal(r)
            self.assertEqual((kind, fresh["attempt"], fresh["context"]["kind"], fresh["context"]["candidate"]),
                             ("attempt", 2, "proposal", split_candidate()))
            fresh = controller.observe(fresh)
            self.assertEqual(fresh["outcome"], "done")
            self.assertEqual([(t["id"], t["status"]) for t in fresh["manifest"]["tasks"]],
                             [("T1", "dropped"), ("T1.1", "done"), ("T1.2", "done")])
            self.assertEqual(fresh["manifest"]["tasks"][1]["notes"],
                             "Owner accepted proposal (attempt 1): Fixture: approve the scope change?")
        with self.fixture_authority() as a:
            self.assertEqual(len(a.state["runs"]), 2)

    def test_bootstrap_reopens_done_tasks_of_a_structured_candidate_with_the_owner_note(self):
        baseline, _ = runs.milestone.build_manifest(fixture_proposal(), "M1", 1)
        candidate = split_candidate()
        candidate["tasks"][1]["status"] = "done"
        context = {"kind": "proposal", "source": 1, "text": "Fixture: approve?", "candidate": candidate}
        manifest = runs.bootstrap_manifest(baseline, context)
        self.assertEqual([(t["id"], t["status"]) for t in manifest["tasks"]],
                         [("T1", "dropped"), ("T1.1", "open"), ("T1.2", "open")])
        self.assertEqual(manifest["tasks"][1]["notes"], "Owner accepted proposal (attempt 1): Fixture: approve?")

    def test_out_of_scope_or_free_text_proposal_goes_to_plan_revision(self):
        for proposal in (canonical(split_candidate(runs.milestone.MAX_ADDITIONS + 1)), "Fixture: split the first task."):
            with self.subTest(proposal=proposal[:20]):
                planner.shutil.rmtree(self.state, ignore_errors=True)
                planner.shutil.rmtree(self.root / "fixture-runs", ignore_errors=True)
                self.approve_fixture()
                with self.fixture_authority() as a:
                    controller, r = self.needs_owner(a, proposal)
                    kind, revision = controller.accept_proposal(r)
                    self.assertEqual((kind, revision["version"], revision["status"]), ("plan", 2, "planning"))
                    self.assertIn(proposal, revision["feedback"])
                    self.assertEqual(len(a.state["runs"]), 1)
                    # The plan is being revised: revision 1's runs take no new actions.
                    with self.assertRaisesRegex(Blocked, "is stale"):
                        controller.answer(r, "Never mind.")

    def test_owner_actions_by_state(self):
        base = {"status": "finished", "outcome": "done", "recoverable": None}
        cases = [({"status": "running", "outcome": None}, ("observe", "stop")),
                 ({"status": "stopping", "outcome": None}, ("observe", "reconcile")),
                 ({"status": "submission_unknown", "outcome": None}, ("reconcile",)),
                 ({}, ("finish",)), ({"delivery": "exporting"}, ("finish",)), ({"delivery": "awaiting_merge"}, ("merge",)),
                 ({"delivery": "conflict"}, ("merge",)), ({"delivery": "integrated"}, ()),
                 ({"outcome": "needs_owner"}, ("accept_proposal", "answer", "revise")),
                 ({"outcome": "blocked"}, ("answer", "revise")), ({"outcome": "invalid"}, ("answer", "revise")),
                 ({"status": "stopped", "outcome": None}, ("answer", "revise")),
                 ({"status": "failed", "outcome": None, "recoverable": False}, ("answer", "revise")),
                 ({"status": "failed", "outcome": None, "recoverable": True}, ("resume", "answer", "revise"))]
        for change, expected in cases:
            with self.subTest(change):
                self.assertEqual(runs.owner_actions({**base, **change}), expected)


class CarryForwardTests(RunsTest):
    def test_carried_needs_the_full_scope_unchanged_with_transitive_cancel(self):
        old = roadmap()
        self.assertEqual([runs.carried(old, roadmap(), m) for m in ("M1", "M2", "M3")], [True, True, True])
        self.assertEqual([runs.carried(old, roadmap("M1"), m) for m in ("M1", "M2", "M3")], [False, False, False])
        self.assertEqual([runs.carried(old, roadmap("M2"), m) for m in ("M1", "M2", "M3")], [True, False, False])
        reworded = roadmap()
        reworded["requirements"][0]["text"] += " Now with logging."
        self.assertEqual([runs.carried(old, reworded, m) for m in ("M1", "M2", "M3")], [False, False, False])
        unrelated = roadmap()
        unrelated["requirements"].append({"id": "R9", "text": "Unrelated."})
        unrelated["milestones"].append({"id": "M9", "title": "Unrelated", "depends_on": [], "slices": [
            {"id": "S9", "title": "Unrelated", "requirements": ["R9"], "tasks": [
                {"id": "T9", "title": "Unrelated", "checks": ["Unrelated check"]}]}]})
        self.assertTrue(runs.carried(old, unrelated, "M2"))

    def approve(self, a, plan):
        with patch("terminal_planner.engine.fixture_proposal", return_value=plan):
            a.begin("Next goal", ROLES, "fixture")
            self.propose(a)
            a.approve(a.current["version"])

    def test_integrated_result_counts_under_a_new_revision_only_when_carried(self):
        with self.fixture_authority() as a:
            self.begin(a)
            with patch("terminal_planner.engine.fixture_proposal", return_value=roadmap()):
                self.propose(a)
            a.approve(1)
            controller = self.fixture_runs(a)
            r = controller.observe(controller.start("M1", 1, ROLES))
            controller.finish(r)
            controller.merge(r)
            merge = self.head()
            record = copy.deepcopy(r)
            self.approve(a, roadmap("M3"))
            self.assertEqual(controller.waiting("M2", merge), [])
            with self.assertRaisesRegex(Blocked, "is stale"):
                controller.merge(r)
            self.approve(a, roadmap("M1"))
            self.assertEqual(controller.waiting("M2"), ["M1"])
            with self.assertRaisesRegex(Blocked, "M2 is waiting for M1"):
                controller.start("M2", 3, ROLES)
            controller.refresh()
            self.assertEqual(self.stored(a)[0], record)
            self.approve(a, roadmap())
            m2 = controller.start("M2", 4, ROLES)
            self.assertEqual((m2["attempt"], m2["destination"]["base"]), (1, merge))

    def test_dense_dag_carry_forward_compares_each_milestone_once(self):
        # 32 milestones (the proposal limit), each depending on the two before it: unmemoized recursion is Fibonacci.
        plan = {"requirements": [{"id": "R%s" % i, "text": "Requirement %s." % i} for i in range(1, 33)],
                "milestones": [{"id": "M%s" % i, "title": "Milestone %s" % i,
                                "depends_on": ["M%s" % j for j in (i - 2, i - 1) if j >= 1], "slices": [
                                    {"id": "S%s" % i, "title": "Slice %s" % i, "requirements": ["R%s" % i], "tasks": [
                                        {"id": "T%s" % i, "title": "Task %s" % i, "checks": ["Check %s" % i]}]}]}
                               for i in range(1, 33)]}
        calls, real = [], runs.scope

        def counted(proposal, milestone_id):
            calls.append(milestone_id)
            if len(calls) > 500:
                raise AssertionError("carry-forward comparison is not memoized")
            return real(proposal, milestone_id)

        started = time.monotonic()
        with patch.object(runs, "scope", side_effect=counted):
            self.assertTrue(runs.carried(plan, copy.deepcopy(plan), "M32"))
        self.assertLessEqual(len(calls), 64)
        self.assertLess(time.monotonic() - started, 5)


class ObservationTests(RunsTest):
    """Controller-owned bounded observation: slices advance a persisted fixture run; the UI only prints events."""

    def test_fixture_run_advances_per_slice_with_progress_events_until_done(self):
        self.approve_fixture()
        with self.fixture_authority() as a:
            controller = MilestoneRuns(a, FixtureDriver(self.root / "fixture-runs", "done", rejections=1),
                                       worktrees=self.worktrees)
            r = controller.start("M1", 1, ROLES)
            self.assertEqual(r["status"], "submitted")
            self.assertFalse((Path(r["worktree"]) / "ZPLAN_FIXTURE.md").exists())
            events, mark, slices = [], None, 0
            while r["status"] in runs.ACTIVE:
                lines, mark = controller.poll(r, mark, seconds=1)
                events += lines
                slices += 1
                if slices == 1:
                    self.assertEqual(self.stored(a)[0]["status"], "running")
            self.assertGreater(slices, 5)
            self.assertEqual(events, ["T1 · implementation", "T1 · review", "T1 · review: rejected, repair 1/3", "T1 · review",
                                      "T1 · recording the result", "T1 · review: accepted", "final check"])
            self.assertEqual((r["status"], r["outcome"]), ("finished", "done"))

    def test_stop_persists_stopping_and_the_next_slices_end_stopped(self):
        self.approve_fixture()
        with self.fixture_authority() as a:
            controller = self.fixture_runs(a)
            r = controller.start("M1", 1, ROLES)
            controller.poll(r, None, seconds=1)
            controller.stop(r)
            self.assertEqual(r["status"], "stopping")
            lines, mark = controller.poll(r, None, seconds=1)
            self.assertEqual((r["status"], lines), ("stopping", ["stopping…"]))
            controller.poll(r, mark, seconds=1)
            self.assertEqual(r["status"], "stopped")

    def test_native_slice_timeout_keeps_complete_records_and_drops_the_cut_one(self):
        r = self.started()
        line = (json.dumps(self.running(r)) + "\n").encode()
        with self.authority() as a:
            controller, calls = self.native_runs(a, [subprocess.TimeoutExpired("watch", 2, output=line + b'{"runId":')])
            r = a.state["runs"][0]
            lines, _ = controller.poll(r, None, seconds=2)
            self.assertEqual((lines, r["status"], r["cursor"]), (["T1 · implementation"], "running", "v2:5"))
            self.assertEqual((calls[0][0][1], calls[0][1]["timeout"]), ("watch", 2))

    def test_activity_lines_for_amendments_repairs_and_final_stage(self):
        manifest = {"tasks": [{"id": "T3", "status": "open"}], "progress": [], "amendments": [
            {"seq": 1, "kind": "split", "tasks": ["T8"], "parents": ["T3"], "reason": "Too big."}]}
        mark = {"progress": 0, "amendments": 0, "task": None, "workers": [], "repairs": [], "label": None}
        statuses = [{"phase": "running", "activeExecutions": [{"node": n, "execution": e}]}
                    for n, e in (("worker", "1"), ("worker", "2"), ("empty_final_verify", "f"), ("repair", "r1"))]
        lines, _ = runs.activity(manifest, statuses, mark)
        self.assertEqual(lines, ["T3 · implementation", "T3 · review: rejected, repair 1/3", "final check",
                                 "final check: repair 1/3", "plan: +T8 (split T3)"])


if __name__ == "__main__":
    unittest.main()
