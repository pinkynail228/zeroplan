"""A9 parallel core: several milestone attempts run at once, admitted by disjoint write-sets.

One smoke test per criterion (C1 admission, C2 resume/follow-up, C3 per-attempt reconcile, C4 independence)
plus the invariants the admission rule can break: the `MAX_RUNS` cap, the same-milestone refusal and the
fail-closed task that has no write-set. Runs the real fixture project, the fixture driver and the delivery
service both UIs build.

Interpretations (the reviewers never see the worker's summary; none of them waives a stated requirement):
- C1's example needs M1..M4 to be independent: the fixture plan's own M2 depends on M1, so beside M1 an M2 would
  read `waits for M1` and could not start. `parallel_plan()` clears the dependencies and gives each task a brief whose
  `write_set` is the example's own: M1 {a.py, src/x.py}, M2 {b.py}, M3 {a.py} (the C1/C2 overlap), M4 {./src/}
  (the normalized directory prefix), M5 {c.py} (the accepted candidate's base), M6 without a brief (fail closed)
  and M7 {d.py} (the fourth disjoint attempt of the `MAX_RUNS` cap).
- C2's "a new attempt/answer of a milestone, through `start`" is read as the C1/C2 joint example the brief states:
  an attempt that follows an earlier one of the same milestone (the accepted candidate of M5) is admitted by the
  same `admit` as a first attempt; only `resume` additionally names the resumed record to `exclude`.
- The write-set of an "accepted candidate" is the union over the candidate's task list; a task without a brief has
  no write-set and fails closed, exactly as C1 states.
- C3's two crash windows (an unknown submission and an unsent stop) are produced the way the existing crash tests
  do: the submission and the force-stop of the fixture driver are patched to raise mid-start and mid-stop.
"""

import json
import subprocess
import unittest
from unittest.mock import patch

from terminal_planner import milestone, planning, process, runs
from terminal_planner.authority import Blocked, canonical, decode
from terminal_planner.delivery import Delivery
from terminal_planner.engine import FixtureEngine
from terminal_planner.runs import FixtureDriver
from test_runs import Crash, ROLES, RunsTest


# (milestone id, write-set); None means the task carries no brief, so its attempt fails closed over the whole repo.
SPECS = (("M1", ["a.py", "src/x.py"]), ("M2", ["b.py"]), ("M3", ["a.py"]), ("M4", ["./src/"]),
         ("M5", ["c.py"]), ("M6", None), ("M7", ["d.py"]))


def brief(write_set):
    return {"goal": "Reach the increment.", "why": "The goal needs it.", "reuse": "", "write_set": list(write_set),
            "criteria": [{"id": "C1", "text": "The increment works.", "example": "Given x, it runs."}],
            "non_goals": [], "risk": "low", "dod": "The module's own tests are green."}


def plan_task(task_id, write_set):
    task = {"id": task_id, "title": "Work %s" % task_id, "checks": ["Check %s" % task_id]}
    if write_set is not None:
        task["brief"] = brief(write_set)
    return task


def parallel_plan():
    """The seven independent milestones of SPECS, each task briefed except the fail-closed M6."""
    requirements, milestones = [], []
    for index, (mid, write_set) in enumerate(SPECS, 1):
        rid = "R%s" % index
        requirements.append({"id": rid, "text": "Requirement %s." % mid})
        milestones.append({"id": mid, "title": mid, "depends_on": [], "slices": [
            {"id": "S%s" % index, "title": mid, "requirements": [rid], "tasks": [plan_task("T%s" % index, write_set)]}]})
    return {"requirements": requirements, "milestones": milestones}


def added_candidate(plan, milestone_id, new_id, write_set):
    """A steward task-list candidate for `milestone_id`: its baseline tasks plus one added task on `write_set`."""
    baseline = milestone.build_baseline(plan, milestone_id, 1)
    manifest = milestone.initial_manifest(baseline)
    manifest["tasks"].append({"id": new_id, "title": "Extra", "checks": ["Extra check"], "status": "open",
                              "origin": "amendment", "notes": "", "brief": brief(write_set)})
    manifest["amendments"].append({"seq": 1, "kind": "add", "tasks": [new_id], "parents": [], "reason": "Add it."})
    return {"tasks": manifest["tasks"], "amendments": manifest["amendments"]}


class ParallelRunsTest(RunsTest):
    def approve_parallel(self, authority, plan=None):
        plan = plan or parallel_plan()
        with patch("terminal_planner.engine.fixture_proposal", return_value=plan):
            authority.begin("Parallel goal", ROLES, "fixture")
            self.propose(authority)
            authority.approve(authority.current["version"])
        return plan

    def active_ids(self, controller):
        return [r["milestone"] for r in controller.runs if r["status"] in runs.ACTIVE]

    def bind_slots(self, authority, max_runs=3):
        """An accepted `zplan.default/2` profile with `autonomy.max_runs`, bound to the session, so
        `Delivery.slots()` reads it and a start through the delivery service is admitted up to that bound. The file
        stays out of the tree the milestone start requires clean (`git/info/exclude`), as `test_process` keeps it."""
        (self.project / process.PROFILE_FILE).write_text(json.dumps(
            {"preset": process.PRESET_V2, "autonomy": {"level": "manual", "max_runs": max_runs}}))
        with (self.project / ".git" / "info" / "exclude").open("a", encoding="utf-8") as handle:
            handle.write("\n%s\n" % process.PROFILE_FILE)
        authority.profile = process.Profile.of(authority)
        authority.profile.accept()
        return authority.profile


class AdmissionTests(ParallelRunsTest):
    def test_c1_admission_by_disjoint_write_sets_and_the_exact_refusals(self):
        with self.fixture_authority() as a:
            self.approve_parallel(a)
            controller = self.fixture_runs(a)
            r1 = controller.start("M1", 1, ROLES)
            r2 = controller.start("M2", 1, ROLES)
            self.assertEqual((runs.run_state(r1), runs.run_state(r2)), ("running", "running"))
            self.assertEqual(self.active_ids(controller), ["M1", "M2"])
            with self.assertRaisesRegex(Blocked, r"Milestone M1 is already running \(attempt 1\)"):
                controller.start("M1", 1, ROLES)
            with self.assertRaisesRegex(Blocked, r"Milestone M3 overlaps with M1 \(a\.py\): it waits for it to finish\."):
                controller.start("M3", 1, ROLES)
            with self.assertRaisesRegex(Blocked, r"Milestone M4 overlaps with M1 \(src\): it waits for it to finish\."):
                controller.start("M4", 1, ROLES)
            self.assertEqual(self.active_ids(controller), ["M1", "M2"])   # every refusal persisted nothing

    def test_c1_the_max_runs_cap_refuses_the_fourth_disjoint_attempt(self):
        with self.fixture_authority() as a:
            self.approve_parallel(a)
            controller = self.fixture_runs(a)
            for mid in ("M1", "M2", "M5"):
                controller.start(mid, 1, ROLES)
            self.assertEqual(self.active_ids(controller), ["M1", "M2", "M5"])
            with self.assertRaisesRegex(Blocked, r"limit of parallel milestone runs \(3\)"):
                controller.start("M7", 1, ROLES)
            self.assertEqual(self.active_ids(controller), ["M1", "M2", "M5"])

    def test_c1_a_task_without_a_write_set_overlaps_an_active_record(self):
        with self.fixture_authority() as a:
            self.approve_parallel(a)
            controller = self.fixture_runs(a)
            controller.start("M1", 1, ROLES)
            with self.assertRaisesRegex(Blocked, r"Milestone M6 overlaps with M1 \(a\.py\)"):
                controller.start("M6", 1, ROLES)

    def test_c1_a_task_without_a_write_set_is_admitted_only_alone(self):
        with self.fixture_authority() as a:
            self.approve_parallel(a)
            controller = self.fixture_runs(a)
            alone = controller.start("M6", 1, ROLES)
            self.assertEqual(runs.run_state(alone), "running")
            with self.assertRaisesRegex(Blocked, r"Milestone M1 overlaps with M6 \(a\.py\)"):
                controller.start("M1", 1, ROLES)

    def test_c2_a_recoverable_failure_resumes_beside_a_running_attempt(self):
        with self.fixture_authority() as a:
            self.approve_parallel(a)
            controller = self.fixture_runs(a)
            controller.start("M1", 1, ROLES)
            failed = self.fixture_runs(a, outcome="failed_recoverable").start("M2", 1, ROLES)
            failed = self.fixture_runs(a, outcome="failed_recoverable").observe(failed)
            self.assertEqual((failed["status"], failed["recoverable"]), ("failed", True))
            successor = self.fixture_runs(a).resume(failed)
            self.assertEqual(successor["status"], "submitted")
            self.assertEqual(self.active_ids(controller), ["M1", "M2"])

    def test_c2_an_accepted_candidate_adding_an_overlapping_task_is_refused(self):
        with self.fixture_authority() as a:
            self.approve_parallel(a)
            controller = self.fixture_runs(a)
            controller.start("M1", 1, ROLES)
            first = controller.observe(controller.start("M5", 1, ROLES))
            self.assertEqual(first["outcome"], "done")
            candidate = added_candidate(parallel_plan(), "M5", "T5x", ["a.py"])
            context = {"kind": "proposal", "source": 1, "text": "Add the step.", "candidate": candidate}
            with self.assertRaisesRegex(Blocked, r"Milestone M5 overlaps with M1 \(a\.py\)"):
                controller.start("M5", 1, ROLES, context)


class ReconcileTests(ParallelRunsTest):
    def crashed(self, authority, plan):
        """M1 `submission_unknown` (its submission crashed) and M2 `stopping` (its force-stop crashed)."""
        self.approve_parallel(authority, plan)
        controller = self.fixture_runs(authority)
        with patch.object(FixtureDriver, "submit", side_effect=Crash):
            with self.assertRaises(Crash):
                controller.start("M1", 1, ROLES)
        r2 = controller.start("M2", 1, ROLES)
        with patch.object(FixtureDriver, "force_stop", side_effect=Crash):
            with self.assertRaises(Crash):
                controller.stop(r2)
        return controller

    def test_c3_reconcile_settles_every_active_record_its_own(self):
        with self.fixture_authority() as a:
            self.crashed(a, parallel_plan())
            self.assertEqual([r["status"] for r in a.state["runs"]], ["submission_unknown", "stopping"])
        with self.fixture_authority() as a:
            controller = self.fixture_runs(a)
            self.assertIs(controller.reconcile(), a.state["runs"][0])   # the first record still active
            self.assertEqual([r["status"] for r in a.state["runs"]], ["submitted", "stopping"])
            self.assertTrue(controller.driver().load(a.state["runs"][1]["run_id"])["stopping"])   # M2's stop resent

    def test_c3_a_refusal_of_one_attempt_waits_for_the_others(self):
        with self.fixture_authority() as a:
            self.crashed(a, parallel_plan())
        with self.fixture_authority() as a:
            first = a.state["runs"][0]
            subprocess.run(["git", "-C", first["worktree"], "-c", "user.name=w", "-c", "user.email=w@example.invalid",
                            "commit", "-q", "--allow-empty", "-m", "writer"], check=True)   # M1's replay no longer holds
            controller = self.fixture_runs(a)
            with self.assertRaisesRegex(Blocked, "replay forbidden"):
                controller.reconcile()
            self.assertEqual(a.state["runs"][0]["status"], "submission_unknown")
            self.assertTrue(controller.driver().load(a.state["runs"][1]["run_id"])["stopping"])   # M2 was still tried


class LegacyRecordTests(ParallelRunsTest):
    """Admission and resume of a P3-shaped store: `validate_run` accepts records without any EXTENSION field and
    `extended(r)` supplies their defaults, so admission (C1) and resume (C2) must read the defaulted view, not the
    raw record -- `test_runs` deletes the same fields from a real store."""

    def strip_extension(self, a):
        """The store an older writer left: every EXTENSION field removed, as `test_runs` deletes them."""
        state = decode(a.path.read_text())
        for r in state["runs"]:
            for key in runs.EXTENSION:
                r.pop(key, None)
        a.path.write_text(canonical(state) + "\n")

    def test_c1_a_legacy_active_record_admits_a_disjoint_milestone(self):
        with self.fixture_authority() as a:
            self.approve_parallel(a)
            self.fixture_runs(a).start("M1", 1, ROLES)
            self.strip_extension(a)
        with self.fixture_authority() as a:
            self.assertNotIn("context", a.state["runs"][0])   # a P3 record: no EXTENSION field on disk
            controller = self.fixture_runs(a)
            controller.start("M2", 1, ROLES)   # used to read the absent `context` directly and raise KeyError
            self.assertEqual(self.active_ids(controller), ["M1", "M2"])

    def test_c2_a_legacy_recoverable_failure_resumes_beside_a_running_attempt(self):
        with self.fixture_authority() as a:
            self.approve_parallel(a)
            self.fixture_runs(a).start("M1", 1, ROLES)
            failed = self.fixture_runs(a, outcome="failed_recoverable").start("M2", 1, ROLES)
            failed = self.fixture_runs(a, outcome="failed_recoverable").observe(failed)
            self.assertEqual((failed["status"], failed["recoverable"]), ("failed", True))
            self.strip_extension(a)
        with self.fixture_authority() as a:
            failed = next(r for r in a.state["runs"] if r["milestone"] == "M2")
            self.assertNotIn("context", failed)   # a P3 record: no EXTENSION field on disk
            controller = self.fixture_runs(a)
            successor = controller.resume(failed)   # used to read the absent `context` directly and raise KeyError
            self.assertEqual(successor["status"], "submitted")
            self.assertEqual(self.active_ids(controller), ["M1", "M2"])


class IndependenceTests(ParallelRunsTest):
    def test_c4_two_attempts_are_observed_delivered_and_stopped_independently(self):
        with self.fixture_authority() as a:
            self.approve_parallel(a)
            self.bind_slots(a, 2)  # two slots: the delivery service admits M1 and M2 side by side
            controller = self.fixture_runs(a)
            service = Delivery(a, controller, planning.Planning(a, controller, lambda *_: FixtureEngine()))
            r1 = service.start(service.preview("M1", ROLES), ROLES)
            r2 = service.start(service.preview("M2", ROLES), ROLES)
            self.assertEqual((runs.run_state(r1), runs.run_state(r2)), ("running", "running"))
            self.assertEqual({i["id"]: i["state"] for i in controller.overview()}["M1"], "running")
            self.assertEqual({i["id"]: i["state"] for i in controller.overview()}["M2"], "running")
            while service.step(r2).active:   # M2 runs to done while M1 is still running
                pass
            self.assertEqual(r2["outcome"], "done")
            service.end(r2)
            self.assertEqual(runs.run_state(r2), "awaiting_merge")
            service.merge(r2)
            self.assertEqual(r2["delivery"], "integrated")
            self.assertEqual(runs.run_state(r1), "running")
            service.stop(r1)
            controller.observe(r1)
            self.assertEqual(runs.run_state(r1), "stopped")
            rows = {i["id"]: i["state"] for i in controller.overview()}
            self.assertEqual((rows["M1"], rows["M2"]), ("stopped", "integrated"))
            self.assertEqual(r2["delivery"], "integrated")   # M1's stop never touched M2


if __name__ == "__main__":
    unittest.main()
