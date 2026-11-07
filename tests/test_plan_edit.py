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
