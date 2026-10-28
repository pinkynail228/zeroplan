"""A2b: a plan edit is a new revision whose plan run must present the owner's draft unchanged (C1..C4).

Real temporary Git repositories, the fixture engine and the scripted native binary of test_terminal_planner; no
provider, no network. One smoke test per acceptance criterion, plus the refusal that must write nothing.

Interpretations (none changes a stated requirement):
- An edit revision's `feedback` is empty: the draft, not a request text, is what the planner gets (the prior proposal
  stays in the context as `prior_proposal`).
- The planner and critic instructions of the v2 graph gain the edit sentences only for a revision with a draft
  (`planner_graph_v2(rounds, edit=True)`); the graph of every other revision, hence every golden hash, is unchanged.
- Refusals use family `action.refused` (wrong version, no proposal, unchanged plan) or the proposal validator's own
  `plan.invalid_proposal`; all of them leave the store bytes as they were.
"""

import copy
import io
import unittest

from terminal_planner import authority as auth, cli, engine
from terminal_planner.authority import Authority as RealAuthority, Blocked, canonical, digest
from terminal_planner.engine import FixtureEngine, planner_graph_v2, planner_input_v2
from terminal_planner.process import Profile
from terminal_planner.runs import FixtureDriver
import test_plan_gate as tpg
import test_process as tpr
from test_terminal_planner import ROLES, ScriptedTerminal, fixture_proposal


def edited(**brief):
    """The fixture proposal with a brief on T1, `brief` overriding its fields (a different write_set by default)."""
    plan = fixture_proposal()
    task = plan["milestones"][0]["slices"][0]["tasks"][0]
    task["brief"] = {"goal": "Implement it", "why": "The goal needs it", "reuse": "", "write_set": ["src/a.py"],
                     "criteria": [{"id": "C1", "text": "It works", "example": "input -> output"}],
                     "non_goals": [], "risk": "low", "dod": "python3.13 -m unittest", **brief}
    return plan


class ReturnsChanged(FixtureEngine):
    """A planner that returns the proposal with one title changed, whatever the draft says."""

    def output(self, authority):
        output = super().output(authority)
        plan = auth.decode(output["proposal"])
        plan["milestones"][0]["title"] += " (changed)"
        return {**output, "proposal": canonical(plan)}


class EditTests(tpr.ProfileTest):
    def session(self):
        """An App over a locked fixture authority holding a proposed revision 1."""
        self.write({})
        self.accept_file()
        manager = self.app()
        app = manager.__enter__()
        self.addCleanup(manager.__exit__, None, None, None)
        app.planning.begin("Goal", app.roles)
        FixtureEngine().proposal(app.authority, lambda _: None)
        return app

    def test_an_edit_is_a_new_revision_with_its_draft_and_refusals_write_nothing(self):
        """C1: the edited plan becomes revision N+1 (status as after `revise`); the draft is a copy; every refusal
        leaves the store untouched; revision 1 keeps its identity and has no draft."""
        app = self.session()
        authority, plan = app.authority, edited()
        before = authority.path.read_bytes()
        old = copy.deepcopy(authority.current)
        refused = [(2, plan), (1, copy.deepcopy(authority.current["proposal"])), (1, {"requirements": []}),
                   (1, edited(write_set=[]))]
        for version, bad in refused:
            with self.subTest(version=version):
                with self.assertRaises(Blocked):
                    app.planning.edit(version, bad)
                self.assertEqual(authority.path.read_bytes(), before)
        result = app.planning.edit(1, plan)
        self.assertEqual(result.kind, "ready")
        current = authority.current
        self.assertEqual((current["version"], current["status"], current["draft"]), (2, "planning", plan))
        plan["milestones"][0]["title"] = "mutated later"
        self.assertNotEqual(current["draft"], plan)
        self.assertNotIn("draft", old)
        self.assertNotIn("draft", authority.intent_identity(old))
        self.assertEqual(authority.state["revisions"][0], old)
        self.assertEqual(authority.intent_identity(current)["draft"], current["draft"])

    def test_an_unchanged_edit_is_accepted_and_approved(self):
        """C3 (positive): the planner returns the draft as it is -> `proposed`, and `approve` works."""
        app = self.session()
        app.planning.edit(1, edited())
        FixtureEngine().proposal(app.authority, lambda _: None)
        current = app.authority.current
        self.assertEqual((current["status"], current["proposal"]), ("proposed", current["draft"]))
        app.planning.approve(2)
        self.assertEqual(app.authority.current["status"], "approved")

    def test_a_planner_that_changed_the_edit_leaves_no_proposal_and_no_evidence(self):
        """C3: any verdict; the check is repeated when the evidence is validated on load."""
        app = self.session()
        app.planning.edit(1, edited())
        ReturnsChanged().proposal(app.authority, lambda _: None)
        current = app.authority.current
        self.assertEqual(current["status"], "proposal_invalid")
        self.assertIn("the planner changed the edit", current["diagnostic"])
        self.assertIsNone(current["proposal"])
        self.assertIsNone(current["evidence"])

    def test_evidence_of_a_proposal_that_is_not_the_draft_does_not_validate(self):
        """C3: the equality is checked again when the evidence is validated (load, approve)."""
        app = self.session()
        app.planning.edit(1, edited(write_set=["src/b.py"]))
        FixtureEngine().proposal(app.authority, lambda _: None)
        stored = app.authority.state["revisions"][-1]
        stored["draft"] = edited(write_set=["src/c.py"])
        # The identity follows the draft, so only the proposal/draft equality is left to refuse the evidence.
        stored["intent"] = app.authority.intent_identity(stored)
        stored["evidence"]["intent_digest"] = digest(stored["intent"])
        with self.assertRaisesRegex(Blocked, "the planner changed the edit"):
            app.authority.check_evidence(stored)
        with self.assertRaisesRegex(Blocked, "the planner changed the edit"):
            app.planning.approve(2)

    def test_renew_and_restart_keep_the_draft(self):
        """C4: a renewed (stale) or restarted edit revision carries the same draft."""
        app = self.session()
        plan = edited()
        app.planning.edit(1, plan)
        renewed = app.planning.renew()
        self.assertEqual((renewed["version"], renewed["draft"]), (3, plan))
        self.assertIsNot(renewed["draft"], app.authority.state["revisions"][1]["draft"])


class NativePromptTests(tpg.GateBase):
    def test_the_plan_input_and_the_instructions_carry_the_draft_only_for_an_edit(self):
        """C2: `task.draft` reaches the native input of an edit revision, with the sentences telling both nodes the
        draft is returned unchanged; a revision without a draft has the graph and context it always had."""
        plan = edited()
        first = self.terminal(proposal=fixture_proposal())
        second = self.terminal(proposal=plan)
        second["title"] = "Terminal roadmap revision 2"
        native, calls = self.engine([{"valid": True}, {"runId": "fixture-native-run"}, first,
                                     {"valid": True}, {"runId": "fixture-native-run"}, second])
        with self.authority() as authority:
            authority.begin("Requested feature", ROLES, "native")
            native.proposal(authority, lambda _: None)
            plain = self.documents(calls[1][1])
            self.assertNotIn("draft", auth.decode(plain["input"]["task"]))
            self.assertEqual(plain["graph"], planner_graph_v2(3))
            authority.begin("Requested feature", ROLES, "native", draft=plan)
            native.proposal(authority, lambda _: None)
            documents = self.documents(calls[4][1])
            self.assertEqual(auth.decode(documents["input"]["task"])["draft"], plan)
            self.assertEqual(documents["graph"], planner_graph_v2(3, edit=True))
            self.assertIn(engine.EDIT_PLANNER, canonical(documents["graph"]).replace("\\n", "\n").replace('\\"', '"'))
            self.assertEqual(authority.current["status"], "proposed")
            authority.approve(2)


if __name__ == "__main__":
    unittest.main()
