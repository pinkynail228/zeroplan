# tests/test_proposal_refusals.py
"""A refused plan says what to fix. The architect writes the plan itself; when the format check refuses it, the
refusal names the fields it expected and the ones it found, so the architect can fix them and send the plan again in
the same turn. A real run stopped for the owner because the refusal said only "Invalid proposal: roadmap fields"."""

import copy
import unittest

from terminal_planner import architect
from terminal_planner.authority import PLAN_EXAMPLE, Blocked, canonical, check_draft, validate_proposal


def good_plan():
    return {"requirements": [{"id": "R1", "text": "Print the count."}],
            "milestones": [{"id": "M1", "title": "Count", "depends_on": [],
                            "slices": [{"id": "S1", "title": "CLI", "requirements": ["R1"],
                                        "tasks": [{"id": "T1", "title": "Implement",
                                                   "checks": ["python3 -m unittest"]}]}]}]}


class ProposalRefusalTests(unittest.TestCase):
    def refusal(self, plan):
        with self.assertRaises(Blocked) as caught:
            validate_proposal(plan)
        self.assertEqual(caught.exception.family, "plan.invalid_proposal")
        message = str(caught.exception)
        self.assertTrue(message.startswith("Invalid proposal: "), message)
        return message

    def test_a_valid_plan_still_passes(self):
        self.assertEqual(validate_proposal(good_plan()), good_plan())

    def test_an_extra_top_level_field_is_named_beside_the_expected_ones(self):
        message = self.refusal(dict(good_plan(), goal="Count words"))
        for name in ("goal", "requirements", "milestones"):
            self.assertIn(name, message)

    def test_a_missing_top_level_field_is_named(self):
        plan = good_plan()
        del plan["requirements"]
        self.assertIn("requirements", self.refusal(plan))

    def test_a_task_with_an_unknown_field_names_the_list_and_the_field(self):
        plan = good_plan()
        plan["milestones"][0]["slices"][0]["tasks"][0]["acceptance"] = "x"
        message = self.refusal(plan)
        self.assertIn("acceptance", message)
        self.assertIn("T1", message)

    def test_a_milestone_without_a_field_names_the_list_and_the_field(self):
        plan = good_plan()
        del plan["milestones"][0]["depends_on"]
        message = self.refusal(plan)
        self.assertIn("depends_on", message)
        self.assertIn("M1", message)

    def test_an_optional_brief_is_never_called_unexpected(self):
        plan = good_plan()
        plan["milestones"][0]["slices"][0]["tasks"][0]["brief"] = 42  # a bad brief fails its own check, not the fields
        self.assertNotIn("unexpected", self.refusal(plan))

    def test_one_refusal_names_every_problem_and_a_valid_plan(self):
        plan = good_plan()
        plan["requirements"].append({"id": "R2", "text": ""})
        plan["milestones"][0]["slices"][0]["requirements"].append("R2")
        plan["milestones"].append({"id": "M2", "title": "More", "slices": []})
        plan["milestones"][0]["slices"][0]["tasks"][0]["checks"] = []
        with self.assertRaises(Blocked) as caught:
            check_draft(plan)
        message = str(caught.exception)
        self.assertEqual(caught.exception.family, "action.refused")
        for name in ("R2", "M2", "T1"):
            self.assertIn(name, message)
        self.assertIn(canonical(PLAN_EXAMPLE), message)
        self.assertEqual(check_draft(copy.deepcopy(PLAN_EXAMPLE)), PLAN_EXAMPLE)

    def test_the_architect_is_told_to_fix_a_refused_plan_and_send_it_again(self):
        rules = "\n".join(architect.TOOL_RULES).lower()
        self.assertIn("invalid proposal", rules)


if __name__ == "__main__":
    unittest.main()
