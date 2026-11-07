"""R1a S2a acceptance: architect plans and their revisions are goldfish draft revisions with origin, author,
responses and requests; a chain never mixes goals.

Design: docs/designs/2026-11-03-egm-planning.md 4.4 (entry paths, feedback, chain) and 4.6 (check_draft).
Real Git and stores, the fixture engine and the scripted native binary of test_terminal_planner; no provider.
"""

import copy
import unittest

from terminal_planner import authority as auth
from terminal_planner.authority import Blocked, canonical
from terminal_planner.engine import FixtureEngine
import test_plan_gate as tpg
import test_process as tpr
from test_goldfish_review import goldfish_output
from test_terminal_planner import ROLES, fixture_proposal

BRIEF = {"goal": "Implement it", "why": "The goal needs it", "reuse": "", "write_set": ["source.txt"],
         "criteria": [{"id": "C1", "text": "It works", "example": "input -> output"}],
         "non_goals": [], "risk": "low", "dod": "python3.13 -m unittest"}


def briefed(title=None):
    """The fixture proposal with a complete brief on every task (and a changed first title when given)."""
    plan = fixture_proposal()
    for milestone in plan["milestones"]:
        for slice_ in milestone["slices"]:
            for task in slice_["tasks"]:
                task["brief"] = copy.deepcopy(BRIEF)
    if title is not None:
        plan["milestones"][0]["title"] = title
    return plan


class PlanningTests(tpr.ProfileTest):
    def session(self):
        self.write({})
        self.accept_file()
        manager = self.app()
        app = manager.__enter__()
        self.addCleanup(manager.__exit__, None, None, None)
        return app

    def test_an_architect_plan_is_a_goldfish_revision_with_its_request(self):
        app = self.session()
        plan = briefed()
        result = app.planning.plan_draft("Goal", plan, request="Add X", by="owner")
        current = app.authority.current
        self.assertEqual(result.kind, "ready")
        self.assertEqual((current["frozen"]["review"], current["origin"], current["by"]), ("goldfish", "plan", "owner"))
        self.assertEqual((current["draft"], current["feedback"]), (plan, "Add X"))
        FixtureEngine().proposal(app.authority, lambda _: None)
        self.assertEqual(app.authority.current["status"], "proposed")

    def test_a_plan_without_briefs_or_too_large_is_refused_and_writes_nothing(self):
        app = self.session()
        app.planning.plan_draft("Goal", briefed())
        before = app.authority.path.read_bytes()
        huge = briefed()
        first = huge["milestones"][0]["slices"][0]
        for n in range(40):  # 40 extra requirements of 8000 characters, all owned by the first slice: > 256 KB
            huge["requirements"].append({"id": "XR%d" % n, "text": "x" * 8000})
            first["requirements"].append("XR%d" % n)
        self.assertGreater(len(canonical(huge).encode()), auth.DRAFT_BYTES)
        for bad in (fixture_proposal(), huge):
            with self.subTest(size=len(canonical(bad))):
                with self.assertRaises(Blocked) as raised:
                    app.planning.plan_draft("Goal", bad)
                self.assertEqual(raised.exception.family, "action.refused")
                self.assertEqual(app.authority.path.read_bytes(), before)

    def rejected(self, app, plan):
        app.planning.plan_draft("Goal", plan, request="r1")
        FixtureEngine("exhausted").proposal(app.authority, lambda _: None)
        self.assertEqual(app.authority.current["status"], "review_exhausted")
        return app.authority.current["version"]

    def test_a_dispute_only_revision_is_accepted_and_carries_the_response(self):
        app = self.session()
        plan = briefed()
        version = self.rejected(app, plan)
        result = app.planning.revise_draft(version, plan, response="F1 disputed: the scope is needed.",
                                           request="r2", by="architect")
        current = app.authority.current
        self.assertEqual(result.kind, "ready")
        self.assertEqual((current["origin"], current["by"], current["response"]),
                         ("edit", "architect", "F1 disputed: the scope is needed."))
        self.assertEqual(current["feedback"], "r1\n\nr2")
        self.assertEqual(current["frozen"]["review"], "goldfish")

    def test_an_unchanged_plan_without_a_response_after_a_review_is_refused(self):
        app = self.session()
        plan = briefed()
        version = self.rejected(app, plan)
        before = app.authority.path.read_bytes()
        with self.assertRaises(Blocked) as raised:
            app.planning.revise_draft(version, plan, by="architect")
        self.assertEqual(raised.exception.family, "action.refused")
        self.assertEqual(app.authority.path.read_bytes(), before)

    def test_an_unchanged_plan_without_evidence_can_be_sent_again(self):
        app = self.session()
        plan = briefed()
        app.planning.plan_draft("Goal", plan)
        version = app.authority.current["version"]
        app.planning.revise_draft(version, plan, by="architect")
        self.assertEqual((app.authority.current["version"], app.authority.current["draft"]), (version + 1, plan))

    def test_a_changed_plan_inherits_the_requests_and_the_old_revision_stays(self):
        app = self.session()
        version = self.rejected(app, briefed())
        old = copy.deepcopy(app.authority.current)
        app.planning.revise_draft(version, briefed("Changed"), by="architect")
        self.assertEqual(app.authority.current["feedback"], "r1")
        self.assertEqual(app.authority.state["revisions"][version - 1], old)

    def test_renew_keeps_the_goldfish_kind_draft_and_response(self):
        app = self.session()
        version = self.rejected(app, briefed())
        app.planning.revise_draft(version, briefed(), response="F1 fixed: split.", by="architect")
        renewed = app.planning.renew()
        self.assertEqual((renewed["frozen"]["review"], renewed["origin"], renewed["response"]),
                         ("goldfish", "renew", "F1 fixed: split."))
        self.assertEqual(renewed["draft"], briefed())

    def test_the_stored_fields_reopen(self):
        app = self.session()
        version = self.rejected(app, briefed())
        app.planning.revise_draft(version, briefed(), response="F1 fixed.", by="architect")
        app.authority.validate_state()

    def test_feedback_of_a_new_goal_starts_from_its_own_request(self):
        app = self.session()
        self.rejected(app, briefed())
        app.planning.plan_draft("Other goal", briefed(), request="b1")
        self.assertEqual(app.authority.current["feedback"], "b1")
        app.planning.revise_draft(app.authority.current["version"], briefed("Edited"), request="b2")
        self.assertEqual(app.authority.current["feedback"], "b1\n\nb2")  # an edit carries the chain's requests on


class ChainTests(tpg.GateBase):
    def test_a_new_goal_does_not_see_the_previous_goal_and_an_edit_sees_its_own_chain(self):
        def titled(n, projection):
            projection["title"] = "Terminal roadmap revision %d" % n  # the engine checks the run title per revision
            return projection

        terminals = [self.projection({"phase": "finished", "terminalResult": {
            "status": "succeeded", "output": goldfish_output(verdict="rejected", findings="F1", proposal=briefed())}})]
        terminals.append(self.projection({"phase": "finished", "terminalResult": {
            "status": "succeeded", "output": goldfish_output(proposal=briefed("B"))}}))
        terminals.append(self.projection({"phase": "finished", "terminalResult": {
            "status": "succeeded", "output": goldfish_output(proposal=briefed("B2"), response="F1 fixed: B2.")}}))
        terminals = [titled(n, t) for n, t in enumerate(terminals, 1)]
        responses = []
        for terminal in terminals:
            responses += [{"valid": True}, {"runId": "fixture-native-run"}, terminal]
        native, calls = self.engine(responses)
        with self.authority() as authority:
            authority.begin("Goal A", ROLES, "native", draft=briefed(), review="goldfish", origin="plan", by="owner")
            native.proposal(authority, lambda _: None)
            authority.begin("Goal B", ROLES, "native", draft=briefed("B"), review="goldfish", origin="plan", by="owner")
            native.proposal(authority, lambda _: None)
            task_b = auth.decode(self.documents(calls[4][1])["input"]["task"])
            self.assertIsNone(task_b.get("prior_proposal"))
            self.assertNotIn("prior_review", task_b)
            authority.begin("Goal B", ROLES, "native", draft=briefed("B2"), review="goldfish", origin="edit",
                            by="architect", response="F1 fixed: B2.")
            native.proposal(authority, lambda _: None)
            documents = self.documents(calls[7][1])
            self.assertEqual(auth.decode(documents["input"]["task"])["prior_proposal"], briefed("B"))
            self.assertEqual(documents["input"]["planResponse"], "F1 fixed: B2.")

    def test_origin_and_author_belong_to_goldfish_revisions_only(self):
        with self.authority() as authority:
            for kwargs in ({"origin": "plan", "by": "owner"}, {"response": "F1 fixed."},
                           {"draft": briefed(), "review": "goldfish", "origin": "plan", "by": "nobody"},
                           {"draft": briefed(), "review": "goldfish", "response": "x" * 3001}):
                with self.subTest(kwargs=sorted(kwargs)):
                    with self.assertRaises(Blocked):
                        authority.begin("Goal", ROLES, "native", **kwargs)


if __name__ == "__main__":
    unittest.main()
