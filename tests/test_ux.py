"""Plain words in a blocked reason and the planner/verifier prompt contract. (The line UI's journeys left with the
line UI in 0.15; the planner's causes and phases are tested in test_run_cause and test_tui_planning.)"""

import copy
import re
import unittest

from terminal_planner.authority import canonical
from terminal_planner.delivery import plain
from terminal_planner.engine import (DRIVER_MECHANICS, MAX_MILESTONE_TASKS, MILESTONE_ISOLATION, SMALL_PLAN,
                                     fixture_proposal, planner_graph, planner_graph_v2)
import test_terminal_planner as tp



class PlainTextTests(unittest.TestCase):
    def test_f10_blocked_reason_hides_internal_tokens(self):
        self.assertEqual(plain("Needs the export path; acceptanceVerdict=rejected; 4 open; manifest: T1 open"),
                         "Needs the export path")
        self.assertEqual(plain("Use the default."), "Use the default.")


class PromptTests(unittest.TestCase):
    run_graph = tp.GraphTests.run_graph

    def prompts(self):
        graph = planner_graph()
        found = {}

        def walk(node):
            if isinstance(node, dict):
                if node.get("name") in ("planner", "plan_verifier") and "instructions" in node:
                    found[node["name"]] = node["instructions"]
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)
        walk(graph)
        return found["planner"], found["plan_verifier"]

    def test_a7_both_prompts_exclude_driver_mechanics_and_keep_plans_small(self):
        planner, verifier = self.prompts()
        for prompt in (planner, verifier):
            self.assertIn(DRIVER_MECHANICS, prompt)
            self.assertIn(SMALL_PLAN, prompt)
            self.assertIn("a README paragraph -> 1 milestone, 1 task, 1-2 checks", prompt)
            self.assertIn("unless the goal explicitly asks for them", prompt)
            self.assertIn("in the repository as it is", prompt)
        self.assertIn("at most %s tasks per milestone" % MAX_MILESTONE_TASKS, planner)
        self.assertIn("more than %s tasks across its slices" % MAX_MILESTONE_TASKS, verifier)
        self.assertIn("Reject any task or check about those mechanics", verifier)
        self.assertIn("Reject any check that cannot be verified", verifier)
        self.assertNotIn("Include independent acceptance/code review", planner)

    def test_rc1_planner_and_verifier_prompts_isolate_the_milestone_from_main(self):
        """C1/C2: both graphs (v1 and v2) carry the one isolation constant in the planner and verifier prompts; the
        verifier also rejects a check that reads main and never rejects a plan for lacking a merge to main."""
        for graph in (planner_graph(), planner_graph_v2(3)):
            found = {}

            def walk(node):
                if isinstance(node, dict):
                    if node.get("name") in ("planner", "plan_verifier", "critic") and "instructions" in node:
                        found[node["name"]] = node["instructions"]
                    for value in node.values():
                        walk(value)
                elif isinstance(node, list):
                    for value in node:
                        walk(value)
            walk(graph)
            planner = found["planner"]
            verifier = found.get("plan_verifier") or found["critic"]
            self.assertIn(MILESTONE_ISOLATION, planner)
            self.assertIn(MILESTONE_ISOLATION, verifier)
            self.assertIn("never reject a plan for lacking a merge to main", verifier)
            for read in ("`git diff main`", "`git show main:`", "`git log main`"):
                self.assertIn(read, verifier)
        self.assertIn("address planFindings against the previous proposal", planner)

    def test_a7_rejected_mechanics_plan_goes_back_to_the_planner_with_findings(self):
        mechanics = fixture_proposal()  # M2 "Acceptance and code review": driver mechanics
        product = copy.deepcopy(mechanics)
        del product["milestones"][1]
        product["requirements"] = product["requirements"][:1]
        findings = "Reject: T2 plans the driver's acceptance and code review; remove mechanics tasks."
        result, calls = self.run_graph([(mechanics, "rejected", findings), (product, "accepted", "Product only.")])
        self.assertEqual([name for name, _ in calls], ["planner", "plan_verifier", "planner", "plan_verifier"])
        self.assertEqual(calls[2][1]["planFindings"], findings)
        self.assertEqual(calls[2][1]["proposal"], canonical(mechanics))
        self.assertEqual(result["output"]["proposal"], canonical(product))
        self.assertEqual(result["output"]["planVerdict"], "accepted")


if __name__ == "__main__":
    unittest.main()
