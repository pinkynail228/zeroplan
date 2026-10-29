"""D4 (soak S3): every revision request of a goal reaches the next plan and outranks the goal text.

Fixture authority and fixture engine, no provider. One regression test per criterion R1, R3, R4 (R2 rides on R1's chain).

Interpretations:
- The feedback of a revision is its requests joined by a blank line; the plan screen splits it on blank lines, so a
  request that itself contains a blank line shows as two `Revision:` lines.
- An edit revision (empty feedback, a draft) is passed over; a revision with no feedback and no draft began the goal.
"""

import json
import unittest

from terminal_planner.engine import planner_graph_v2
from terminal_planner.planning import Planning
from terminal_planner.runs import MilestoneRuns
from test_terminal_planner import ProjectTest, ROLES, Authority, fixture_proposal


class RevisionRequestTests(ProjectTest):
    def test_every_request_of_a_goal_reaches_the_next_revision_in_order_and_a_new_goal_starts_empty(self):
        """R1: requests, a proposal in between and an edit revision in between lose none; R2: a new goal has none."""
        with Authority(self.state, self.project) as authority:
            self.begin(authority)
            self.propose(authority)
            runs = MilestoneRuns(authority, None)
            runs.revise_plan("drop 10x")
            self.propose(authority)  # the proposal that used to absorb the first request
            runs.revise_plan("100 MB")
            self.propose(authority)
            authority.begin("Requested feature", ROLES, "fixture", draft=fixture_proposal())  # an owner edit
            runs.revise_plan("five calls")
            self.assertEqual(authority.current["feedback"], "drop 10x\n\n100 MB\n\nfive calls")
            authority.begin("Other goal", ROLES, "fixture")
            self.assertEqual(authority.current["feedback"], "")

    def test_the_planner_is_told_the_requests_outrank_the_goal(self):
        """R3: the sentence, in the graph of a revision that carries requests; not the whole prompt."""
        self.assertIn("The revision feedback lists the owner's requests in order; each amends the goal, and a later "
                      "request wins over an earlier one and over the goal text.", json.dumps(planner_graph_v2(2, revised=True)))

    def test_the_plan_screen_lists_the_requests_latest_last_and_counts_the_earlier_ones(self):
        """R4: three requests, three lines; seven requests, the last five and the count of the others."""
        with Authority(self.state, self.project) as authority:
            self.begin(authority)
            self.propose(authority)
            planning = Planning(authority, None, lambda *_: None)
            requests = ["request %d" % n for n in range(1, 8)]
            for n, request in enumerate(requests, 1):
                authority.begin("Requested feature", ROLES, "fixture", feedback=authority.amended_feedback(request))
                self.propose(authority)
                lines = planning.proposal(authority.current)
                shown = [line for line in lines.lines if line.startswith("Revision:")]
                self.assertEqual(shown, ["Revision: " + r for r in requests[max(0, n - 5):n]])
                self.assertEqual("(%d earlier)" % (n - 5) in lines.lines, n > 5)


if __name__ == "__main__":
    unittest.main()
