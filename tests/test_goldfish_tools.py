# tests/test_goldfish_tools.py
"""R1a S3a acceptance: the architect's plan tools create goldfish revisions; one budget per chain brakes the
architect's own revisions; a rejection wakes the architect while the chain has budget; the status shows the
paraphrase and, before a review, the draft, and how many revisions the architect has left.

Design: docs/designs/2026-11-03-egm-planning.md 4.4, 4.5. Real Git, stores, the live Controller and bridge socket,
the fixture engine; no provider.
"""

from unittest.mock import patch

from terminal_planner import architect, feed
from terminal_planner.engine import FIXTURE_PARAPHRASE, FixtureEngine
from terminal_planner.runs import FixtureDriver
import test_terminal_planner as tp
import test_bridge as tb
from test_goldfish_planning import briefed
from test_runs import ROLES, RunsTest
from test_terminal_planner import ROLES as TP_ROLES


def goldfish(authority, origin, by, title=None, response="", reject=True):
    """One goldfish revision of the goal, rejected by the fixture critic unless `reject` is False."""
    authority.begin("Requested feature", TP_ROLES, "fixture", draft=briefed(title), review="goldfish", origin=origin,
                    by=by, response=response)
    if reject:
        FixtureEngine("exhausted").proposal(authority, lambda _: None)


class ToolBase(tp.ProjectTest):
    """The live-controller helpers of test_bridge.BridgeCase, borrowed without its own 75 tests."""
    def setUp(self):
        super().setUp()
        self.driver = FixtureDriver(self.root / "fixture-runs")

    controller = tb.BridgeCase.controller
    controller_stop = tb.BridgeCase.controller_stop
    _controllers = tb.BridgeCase._controllers
    call = tb.BridgeCase.call
    plan_until = tb.BridgeCase.plan_until


class ToolTests(ToolBase):
    def test_an_owner_turn_plan_with_a_plan_is_a_goldfish_revision(self):
        controller = self.controller(engine_factory=lambda *_: FixtureEngine("exhausted"))
        token = controller.begin_turn("Plan: add a changelog", 3)
        reply = self.call("zplan_plan", {"goal": "Add a changelog", "plan": briefed(), "request": "Keep it short"},
                          rid="ow", turn=token)
        self.assertEqual(reply.get("ok", {}).get("revision"), 1, reply)
        self.controller_stop()
        with tp.Authority(self.state, self.project) as authority:
            current = authority.current
            self.assertEqual((current["frozen"]["review"], current["origin"], current["by"], current["feedback"]),
                             ("goldfish", "plan", "owner", "Keep it short"))
            self.assertEqual(current["draft"], briefed())

    def test_an_event_turn_edit_with_a_response_is_the_architects_revision(self):
        with tp.Authority(self.state, self.project) as authority:
            goldfish(authority, "plan", "owner")
        self.controller(engine_factory=lambda *_: FixtureEngine("exhausted"))
        reply = self.call("zplan_edit_plan", {"revision": 1, "plan": briefed(), "response": "F1 disputed: needed.",
                                              "request": ""}, rid="ev")
        self.assertEqual(reply.get("ok", {}).get("revision"), 2, reply)
        self.controller_stop()
        with tp.Authority(self.state, self.project) as authority:
            current = authority.current
            self.assertEqual((current["origin"], current["by"], current["response"]),
                             ("edit", "architect", "F1 disputed: needed."))

    def test_the_chain_budget_brakes_the_architect_and_lets_one_owner_revision_through(self):
        with tp.Authority(self.state, self.project) as authority:
            goldfish(authority, "plan", "owner")
            for n in range(3):  # three architect revisions: the default budget (plan_rounds 3)
                goldfish(authority, "edit", "architect", title="Try %d" % n)
        controller = self.controller(engine_factory=lambda *_: FixtureEngine("exhausted"))
        refused = self.call("zplan_edit_plan", {"revision": 4, "plan": briefed("Again")}, rid="ev")
        self.assertEqual(refused.get("error"), "action.refused", refused)
        self.assertIn("the owner decides now", refused["message"])
        self.assertEqual(self.plan_until(lambda plan: plan["version"] == 4)["status"], "review_exhausted")
        token = controller.begin_turn("Narrow the plan to the parser", 9)
        reply = self.call("zplan_edit_plan", {"revision": 4, "plan": briefed("Owner"), "request": "parser only"},
                          rid="ow", turn=token)
        self.assertEqual(reply.get("ok", {}).get("revision"), 5, reply)
        again = self.call("zplan_edit_plan", {"revision": 5, "plan": briefed("Owner 2")}, rid="ow2", turn=token)
        self.assertEqual(again.get("error"), "action.refused", again)
        self.controller_stop()
        with tp.Authority(self.state, self.project) as authority:
            self.assertEqual((authority.current["version"], authority.current["by"]), (5, "owner"))

    def test_the_status_shows_the_paraphrase_and_the_draft_before_a_review(self):
        with tp.Authority(self.state, self.project) as authority:
            goldfish(authority, "plan", "owner")
        self.controller()
        plan = self.plan_until(lambda plan: plan["version"] == 1)
        self.assertEqual(plan["paraphrase"], FIXTURE_PARAPHRASE)
        self.controller_stop()
        with tp.Authority(self.state, self.project) as authority:
            goldfish(authority, "edit", "architect", title="Unsent", reject=False)
        self.controller()
        plan = self.plan_until(lambda plan: plan["version"] == 2)
        self.assertIsNone(plan["proposal"])
        self.assertEqual(plan["draft"], briefed("Unsent"))


class RevisionsLeftTests(ToolBase):
    """zplan_status says how many revisions the architect has left in the chain, under the default plan_rounds 3."""

    def chain(self, architect_revisions):
        """A rejected owner plan, then `architect_revisions` rejected architect revisions; the current version."""
        with tp.Authority(self.state, self.project) as authority:
            goldfish(authority, "plan", "owner")
            for n in range(architect_revisions):
                goldfish(authority, "edit", "architect", title="Try %d" % n)
        return architect_revisions + 1

    def left(self, version):
        return self.plan_until(lambda plan: plan["version"] == version)["revisions_left"]

    def test_one_rejected_architect_revision_leaves_two(self):
        version = self.chain(1)
        self.controller()
        self.assertEqual(self.left(version), 2)

    def test_a_spent_budget_leaves_none(self):
        version = self.chain(3)
        self.controller()
        self.assertEqual(self.left(version), 0)

    def test_the_count_never_goes_below_zero(self):
        version = self.chain(4)
        self.controller()
        self.assertEqual(self.left(version), 0)

    def test_a_new_plan_starts_a_new_count(self):
        version = self.chain(3)
        with tp.Authority(self.state, self.project) as authority:
            goldfish(authority, "plan", "owner", title="Another goal")
        self.controller()
        self.assertEqual(self.left(version + 1), 3)

    def test_fixing_a_rejected_plan_from_an_event_turn_spends_one_revision(self):
        version = self.chain(0)
        self.controller(engine_factory=lambda *_: FixtureEngine("exhausted"))
        self.assertEqual(self.left(version), 3)
        reply = self.call("zplan_edit_plan", {"revision": version, "plan": briefed(), "response": "F1 fixed: narrowed."},
                          rid="ev")
        self.assertEqual(reply.get("ok", {}).get("revision"), version + 1, reply)
        self.assertEqual(self.left(version + 1), 2)

    def test_an_older_planner_revision_has_no_count(self):
        with tp.Authority(self.state, self.project) as authority:
            self.begin(authority)
            FixtureEngine("exhausted").proposal(authority, lambda _: None)
        self.controller()
        plan = self.plan_until(lambda plan: plan["version"] == 1)
        self.assertIsNone(plan.get("revisions_left"))

    def test_every_prompt_ties_the_rejected_plan_rule_to_the_count(self):
        (self.project / "zplan.architect.md").write_text("# Our method\n- Small slices.")
        for text in (architect.build_preamble(None), architect.build_preamble(None, self.project),
                     architect.build_update(None)):
            self.assertIn("plan.revisions_left", text)


class WakeTests(RunsTest):
    def plan_events(self, authority):
        return [e for e in authority.state["feed"]["events"] if e["kind"] == "plan"]

    def test_a_rejection_wakes_the_architect_until_the_chain_budget_is_spent(self):
        with patch("terminal_planner.autonomy.level", return_value="auto"), self.fixture_authority() as a:
            feed.bootstrap(a)
            goldfish(a, "plan", "owner")
            for n in range(3):
                a.architect_acting = True  # the architect's own tool call creates the revision
                a.begin("Goal", ROLES, "fixture", draft=briefed("Try %d" % n), review="goldfish", origin="edit",
                        by="architect")
                a.architect_acting = False
                FixtureEngine("exhausted").proposal(a, lambda _: None)
            exhausted = [(e["plan_revision"], e["wake"]) for e in self.plan_events(a)
                         if e["status"] == "review_exhausted"]
            self.assertEqual(exhausted, [(1, True), (2, True), (3, True), (4, False)])
