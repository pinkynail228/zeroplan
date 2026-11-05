# tests/test_attempt_budget.py
"""Without the owner, a milestone gets at most two new attempts (docs/PRODUCT_CONTRACT.md section 2, Delegation;
roadmap D2b). The architect's event-turn re-brief that would start a fourth attempt of one milestone in one plan
revision is refused and starts nothing; the owner then decides. A done attempt whose merge failed (a check on the
candidate, a critic block, a conflict) is re-briefed under the same cap, and an event turn never starts a milestone
that already has an attempt in the plan revision."""
import unittest
from unittest.mock import patch

from terminal_planner import autonomy, process
from terminal_planner.engine import FixtureEngine
from terminal_planner.runs import FixtureDriver, MilestoneRuns

import test_bridge as tb
import test_terminal_planner as tp

NOTE = "try again"
FAILING = [{"name": "unit", "argv": ["false"], "timeout_s": 60}]
BLOCK = {"schemaVersion": "1", "verdict": "block", "findings": "risky"}


class BudgetBase(tp.ProjectTest):
    """The live-controller helpers of test_bridge.BridgeCase, borrowed without its own tests."""
    def setUp(self):
        super().setUp()
        self.driver = FixtureDriver(self.root / "fixture-runs")

    attempt = tb.BridgeCase.attempt
    finish = staticmethod(tb.BridgeCase.finish)
    write_auto_profile = tb.BridgeCase.write_auto_profile
    write_profile = tb.BridgeCase.write_profile
    awaiting_merge = tb.BridgeCase.awaiting_merge
    controller = tb.BridgeCase.controller
    controller_stop = tb.BridgeCase.controller_stop
    _controllers = tb.BridgeCase._controllers
    call = tb.BridgeCase.call
    rows = tb.BridgeCase.rows

    def m1(self):
        return next(item for item in self.rows()["rows"] if item["id"] == "M1")

    def rebrief(self, rid, turn=None):
        return self.call("zplan_rebrief", {"milestone": "M1", "token": self.m1()["token"], "note": NOTE}, rid=rid,
                         turn=turn)


class AttemptBudget(BudgetBase):
    def failed_attempts(self, count):
        """M1 with `count` failed attempts in plan revision 1: the first started, the others re-briefed."""
        record = self.attempt("failed")
        with tp.Authority(self.state, self.project) as authority:
            runs = MilestoneRuns(authority, self.driver, worktrees=authority.directory / "worktrees")
            for _ in range(count - 1):
                record = self.finish(runs, runs.retry(record, "another way"))
        return record

    def test_a_third_new_attempt_from_an_event_turn_is_refused_and_starts_nothing(self):
        self.write_auto_profile()
        self.failed_attempts(3)
        self.controller(profile=True)
        self.assertEqual((self.m1()["state"], self.m1()["attempt"]), ("failed", 3))
        with patch.object(autonomy, "AUTOMATIC", True):
            refused = self.rebrief("rb4")
        self.assertNotIn("ok", refused, refused)
        self.assertEqual(refused["error"], "action.refused", refused)
        self.assertIn("owner", refused["message"].lower(), refused)
        self.assertEqual(self.m1()["attempt"], 3)

    def test_the_second_new_attempt_is_still_the_architects(self):
        self.write_auto_profile()
        self.failed_attempts(2)
        self.controller(profile=True)
        with patch.object(autonomy, "AUTOMATIC", True):
            reply = self.rebrief("rb3")
        self.assertEqual(reply.get("ok", {}).get("attempt"), 3, reply)


class MergeFailure(BudgetBase):
    """Real Git, the live Controller and bridge socket, the fixture engine; no provider."""

    def refused_merge(self, family):
        reply = self.call("zplan_merge", {"milestone": "M1", "token": self.m1()["token"]}, rid="mg")
        self.assertEqual(reply.get("ok", {}).get("kind"), "refused", reply)
        result = self.call("zplan_status")["ok"]["results"][-1]
        self.assertEqual((result["operation"], result["family"]), ("merge", family), result)

    def failed_check(self):
        """M1's first attempt done and exported, its merge refused by a check on the integrated candidate."""
        record = self.awaiting_merge(checks=FAILING)
        controller = self.controller(profile=True)
        self.refused_merge("merge.checks_failed")
        return record, controller

    def conflicted(self):
        """M1's first attempt done and exported, its merge conflicting with an owner commit (checks would pass)."""
        self.awaiting_merge()
        (self.project / "ZPLAN_FIXTURE.md").write_text("owner version\n")
        self.git("add", "ZPLAN_FIXTURE.md")
        self.git("commit", "-qm", "owner change")
        self.controller(profile=True)
        reply = self.call("zplan_merge", {"milestone": "M1", "token": self.m1()["token"]}, rid="mg")
        self.assertEqual(reply.get("ok", {}).get("kind"), "open", reply)
        self.assertEqual(self.m1()["state"], "conflict")

    def done_after_failures(self, failures):
        """M1 with `failures` failed attempts, then a done and exported one whose candidate check will fail."""
        self.write_profile(level="auto", merge="required", checks=FAILING)
        self.driver = FixtureDriver(self.root / "fixture-runs", outcome=("failed",) * failures + ("done",))
        with tp.Authority(self.state, self.project) as authority:
            authority.profile = process.Profile.of(authority)
            self.begin(authority)
            self.propose(authority)
            authority.approve(1)
            runs = MilestoneRuns(authority, self.driver, worktrees=authority.directory / "worktrees")
            record = self.finish(runs, runs.start("M1", 1, tb.ROLES))
            for _ in range(failures):
                record = self.finish(runs, runs.retry(record, "another way"))
            runs.finish(record)
        self.controller(profile=True)
        self.refused_merge("merge.checks_failed")

    def assert_new_attempt(self, reply, attempt=2):
        """The reply names the new attempt, and the store holds it with the architect's note."""
        self.assertEqual(reply.get("ok", {}).get("attempt"), attempt, reply)
        self.controller_stop()
        with tp.Authority(self.state, self.project) as authority:
            newest = authority.state["runs"][-1]
            self.assertEqual((newest["attempt"], newest["context"]["kind"], newest["context"]["text"]),
                             (attempt, "answer", NOTE))

    def assert_refused(self, reply, attempt=1):
        self.assertEqual(reply.get("error"), "action.refused", reply)
        self.assertEqual(self.m1()["attempt"], attempt)

    def test_a_failed_check_on_the_candidate_is_rebriefed_by_the_architect(self):
        self.failed_check()
        self.assert_new_attempt(self.rebrief("rb"))

    def test_a_critic_block_is_rebriefed_by_the_architect(self):
        self.awaiting_merge(tier="high")
        self.controller(profile=True, engine_factory=lambda *_: FixtureEngine(terminal_output=BLOCK))
        self.refused_merge("milestone.critic_blocked")
        self.assert_new_attempt(self.rebrief("rb"))

    def test_a_merge_conflict_is_rebriefed_by_the_architect(self):
        self.conflicted()
        self.assert_new_attempt(self.rebrief("rb"))

    def test_a_failed_merge_on_the_second_attempt_still_gets_the_architects_last_attempt(self):
        self.done_after_failures(1)
        self.assert_new_attempt(self.rebrief("rb"), attempt=3)

    def test_a_failed_merge_on_the_third_attempt_is_past_the_cap(self):
        self.done_after_failures(2)
        self.assert_refused(self.rebrief("rb"), attempt=3)

    def test_a_done_attempt_with_no_failed_merge_is_not_rebriefed(self):
        self.awaiting_merge()
        self.controller(profile=True)
        self.assert_refused(self.rebrief("rb"))

    def test_an_attempt_merged_by_hand_after_its_failed_check_is_not_rebriefed(self):
        record, _ = self.failed_check()
        self.controller_stop()
        self.git("merge", "-q", "--no-edit", record["result"]["branch"])
        with tp.Authority(self.state, self.project) as authority:
            MilestoneRuns(authority, self.driver, worktrees=authority.directory / "worktrees").refresh()
        self.controller(profile=True)
        self.assertEqual(self.m1()["state"], "integrated")
        self.assert_refused(self.rebrief("rb"))

    def test_an_event_turn_start_of_a_milestone_with_a_failed_attempt_is_refused(self):
        self.write_auto_profile()
        self.attempt("failed")
        self.controller(profile=True)
        self.assert_refused(self.call("zplan_start", {"milestone": "M1", "revision": 1}, rid="st"))

    def test_an_event_turn_start_after_a_merge_conflict_is_refused(self):
        self.conflicted()
        self.assert_refused(self.call("zplan_start", {"milestone": "M1", "revision": 1}, rid="st"))

    def test_an_owner_turn_rebrief_of_a_failed_merge_stays_refused(self):
        _, controller = self.failed_check()
        turn = controller.begin_turn("Try it", 4)
        try:
            reply = self.rebrief("rb", turn)
        finally:
            controller.end_turn(turn)
        self.assert_refused(reply)

    def test_an_owner_turn_still_starts_a_milestone_that_has_an_attempt(self):
        self.write_auto_profile()
        self.attempt("failed")
        controller = self.controller(profile=True)
        turn = controller.begin_turn("Start it", 4)
        try:
            reply = self.call("zplan_start", {"milestone": "M1", "revision": 1}, rid="st", turn=turn)
        finally:
            controller.end_turn(turn)
        self.assertEqual(reply.get("ok", {}).get("attempt"), 2, reply)


if __name__ == "__main__":
    unittest.main()
