"""The plan qualification script's scripted provider and scenario tables, against the production validators.

The native half (`devtools/plan_qual.py` on the Linux host) needs the pinned binary; this module proves the script
itself: its answers fit the request contracts, its scenarios end where they claim through `read_review`, and a
critic that does not continue its own conversation is caught.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devtools import driver_qual as dq  # noqa: E402
from devtools import plan_qual  # noqa: E402
from devtools.plan_qual import PlanProvider, SCENARIOS  # noqa: E402
from terminal_planner.authority import Blocked, read_review  # noqa: E402
from terminal_planner.engine import planner_graph_v2  # noqa: E402
from test_plan_gate import nodes  # noqa: E402


def record(*names):
    return {"type": "object", "properties": {n: {"type": "string"} for n in names}, "required": list(names),
            "additionalProperties": False}


def planner_node():
    return next(n for n in nodes(planner_graph_v2(2)["root"]) if n["name"] == "planner")


def contract(node):
    if node == "planner":
        # Derived from the graph, so the request contract follows the planner's node kind (step: the bare output).
        graph_node = planner_node()
        output = record(*graph_node["output"]["fields"])
        if graph_node["kind"] != "verifier":
            return output
        return {"type": "object", "required": ["output", "signals", "diagnostic"], "additionalProperties": False,
                "properties": {"output": output,
                               "signals": {"type": "object", "required": sorted(graph_node["signals"]),
                                           "additionalProperties": False,
                                           "properties": {k: {"type": "string", "enum": v}
                                                          for k, v in graph_node["signals"].items()}},
                               "diagnostic": record(*graph_node["diagnostic"]["fields"])}}
    return {"type": "object", "required": ["output", "signals", "diagnostic"], "additionalProperties": False,
            "properties": {"output": record("discussion"),
                           "signals": {"type": "object", "required": ["verdict"], "additionalProperties": False,
                                       "properties": {"verdict": {"type": "string", "enum": ["accepted", "rejected"]}}},
                           "diagnostic": record("message")}}


def request(node, history=(), previous=None):
    """A request as the transport shows it: the marker turn, then the node's earlier answers as assistant turns."""
    items = [{"role": "user", "content": [{"type": "input_text", "text": "ZPLAN_NODE=%s\nbound inputs" % node}]}]
    items += [{"role": "assistant", "content": [{"type": "output_text", "text": json.dumps({"response": answer})}]}
              for answer in history]
    body = {"input": items, "text": {"format": {"schema": {"type": "object", "required": ["response"],
                                                           "additionalProperties": False,
                                                           "properties": {"response": contract(node)}}}}}
    if previous is not None:
        body["previous_response_id"] = previous
    return body


def play(scenario, continue_critic=True):
    """(provider, outcome): the graph's loop played against the scripted provider, as native would run it."""
    provider = PlanProvider(scenario["script"], scenario.get("broken", ()), scenario.get("discussion"))
    history = {"planner": [], "critic": []}
    last = {}
    for _ in range(scenario["rounds"]):
        answers = {}
        for node in ("planner", "critic"):
            shown = history[node] if node == "planner" or continue_critic else []
            answers[node] = provider.answer(request(node, shown))
            if not answers[node]:
                return provider, "failed"
            history[node].append(dict(answers[node]))
        last = answers
        if last["critic"]["signals"]["verdict"] == "accepted":
            break
    output = {"schemaVersion": "2", "proposal": last["planner"]["output"]["proposal"],
              "planResponse": last["planner"]["output"]["planResponse"], "planVerdict": last["critic"]["signals"]["verdict"],
              "planFindings": last["critic"]["diagnostic"]["message"],
              "discussion": last["critic"]["output"]["discussion"]}
    try:
        _, verdict, _, _, discussion = read_review(output, scenario["rounds"])
    except Blocked:
        return provider, "invalid"
    return provider, (verdict, len(discussion["rounds"]))


class ScenarioTests(unittest.TestCase):
    def test_every_scenario_ends_where_it_claims(self):
        for name, scenario in SCENARIOS.items():
            with self.subTest(name):
                provider, outcome = play(scenario)
                self.assertEqual(provider.problems, [])
                self.assertEqual(provider.errors, [])
                expected = scenario["status"]
                if expected == "run_failed":
                    self.assertEqual(outcome, "failed")
                elif expected == "proposal_invalid":
                    self.assertEqual(outcome, "invalid")
                else:
                    self.assertEqual(outcome, (scenario["verdict"], scenario["used"]))
                    self.assertEqual(expected, "proposed" if scenario["verdict"] == "accepted" else "review_exhausted")
                self.assertEqual(provider.calls, scenario["order"])

    def test_scenario_covers_the_required_set(self):
        self.assertEqual({name.split("_")[0] for name in SCENARIOS}, set("abcdefg"))
        self.assertEqual({SCENARIOS[n]["status"] for n in SCENARIOS},
                         {"proposed", "review_exhausted", "run_failed", "proposal_invalid"})
        self.assertEqual({s.get("diagnostic") for s in SCENARIOS.values()} - {None}, {"critic_failed", "planner_failed"})

    def test_a_critic_that_loses_its_conversation_is_caught(self):
        scenario = SCENARIOS["b_reject_repair_accept"]
        provider, _ = play(scenario, continue_critic=False)
        self.assertEqual(len(provider.problems), 1)
        self.assertIn("critic call #2", provider.problems[0])

    def test_the_token_must_be_an_assistant_turn(self):
        """A bound input repeating the earlier findings (the discussion) is not continuity."""
        provider = PlanProvider(SCENARIOS["b_reject_repair_accept"]["script"])
        first = provider.answer(request("planner"))
        critic = provider.answer(request("critic"))
        provider.answer(request("planner", [dict(first)]))
        replay = request("critic")
        replay["input"][0]["content"][0]["text"] += json.dumps(critic)  # the user turn quotes the answer
        provider.answer(replay)
        self.assertEqual(len(provider.problems), 1)
        self.assertIn("critic call #2", provider.problems[0])

    def test_previous_response_id_also_continues(self):
        provider = PlanProvider(SCENARIOS["b_reject_repair_accept"]["script"])
        provider.answer(request("planner"))
        critic = provider.answer(request("critic"))
        provider.answer(request("planner", [{"proposal": "", "planResponse": ""}]))
        provider.answer(request("critic", previous=critic.response_id))
        self.assertEqual(len(provider.problems), 1)  # only the planner's replay lacked its own answer

    def test_the_planner_is_answered_as_a_verifier_with_empty_signals_and_an_output(self):
        """R3: the planner's request contract is taken from planner_graph_v2's planner node, a verifier without
        signals, so the scripted answer carries the proposal in output, no signal and a diagnostic. With the node a
        step again the contract is the bare record and the provider cannot answer it."""
        self.assertEqual((planner_node()["kind"], planner_node()["signals"]), ("verifier", {}))
        provider = PlanProvider(SCENARIOS["a_accept_r1"]["script"])
        answer = provider.answer(request("planner"))
        self.assertEqual(set(answer["output"]), {"proposal", "planResponse"})
        self.assertEqual((answer["signals"], set(answer["diagnostic"])), ({}, {"message"}))

    def test_answers_are_checked_against_the_request_schema(self):
        provider = PlanProvider(SCENARIOS["a_accept_r1"]["script"])
        bad = request("critic")
        bad["text"]["format"]["schema"]["properties"]["response"]["properties"]["signals"]["properties"][
            "verdict"]["enum"] = ["open"]
        with self.assertRaises(dq.QualError):
            provider.answer(bad)

    def test_requests_without_a_marker_or_schema_are_refused(self):
        provider = PlanProvider(SCENARIOS["a_accept_r1"]["script"])
        with self.assertRaises(dq.QualError):
            provider.answer({"input": []})
        with self.assertRaises(dq.QualError):
            provider.answer({"input": [{"role": "user", "content": "ZPLAN_NODE=critic"}]})

    def test_unexpected_extra_call_is_an_error(self):
        provider = PlanProvider(SCENARIOS["a_accept_r1"]["script"])
        provider.answer(request("planner"))
        provider.answer(request("critic"))
        with self.assertRaises(dq.QualError):
            provider.answer(request("critic", []))


class CheckTests(unittest.TestCase):
    def gate(self, scenario, **over):
        discussion = {"version": 1, "rounds": [{}] * scenario["used"]}
        current = {"status": scenario["status"], "diagnostic": "", "frozen": {"config_digest": "d" * 64},
                   "evidence": {"gate": "plan", "rounds_used": scenario["used"], "rounds_limit": scenario["rounds"],
                                "critic_verdict": scenario["verdict"], "discussion": discussion,
                                "resolved_config_digest": "d" * 64}}
        current.update(over)
        return SimpleNamespace(current=current)

    def provider(self, scenario):
        provider = PlanProvider(scenario["script"])
        provider.calls = list(scenario["order"])
        return provider

    def test_a_matching_result_passes(self):
        scenario = SCENARIOS["d_exhausted"]
        self.assertEqual(plan_qual.check(scenario, self.provider(scenario), self.gate(scenario), None), [])

    def test_deviations_are_named(self):
        scenario = SCENARIOS["d_exhausted"]
        authority = self.gate(scenario)
        authority.current["evidence"]["rounds_used"] = 1
        authority.current["evidence"]["resolved_config_digest"] = "e" * 64
        provider = self.provider(scenario)
        provider.calls.pop()
        problems = plan_qual.check(scenario, provider, authority, "refused")
        self.assertTrue(any("node order" in p for p in problems))
        self.assertTrue(any(p.startswith("gate ") for p in problems))
        self.assertTrue(any("digest" in p for p in problems))
        self.assertTrue(any("unexpected refusal" in p for p in problems))

    def test_a_failed_run_must_leave_no_evidence(self):
        scenario = SCENARIOS["e_critic_error"]
        authority = self.gate(dict(SCENARIOS["a_accept_r1"], status="run_failed"), diagnostic="critic_failed")
        provider = self.provider(scenario)
        problems = plan_qual.check(scenario, provider, authority, "run_failed: critic_failed")
        self.assertEqual(problems, ["evidence exists after a failed run"])
        authority.current["evidence"] = None
        self.assertEqual(plan_qual.check(scenario, provider, authority, "run_failed: critic_failed"), [])
        authority.current["diagnostic"] = "planner_failed"
        self.assertEqual(len(plan_qual.check(scenario, provider, authority, "x")), 1)

    def test_a_second_remote_scenario_verifies_the_observed_source(self):
        # a_accept_r1 now carries a second remote; its gate must confirm the observed source stayed the origin
        # identity (the point of the two-remote regression). A foreign revision is caught.
        scenario = dict(SCENARIOS["a_accept_r1"])
        source = {"repository": "zplan-qual/fixture", "branch": "main", "revision": "a" * 40}
        authority = self.gate(scenario, terminal_envelope={"source": source})
        with tempfile.TemporaryDirectory() as work:
            project = Path(work) / "project"
            project.mkdir()
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=project, check=True)
            subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                            "commit", "-q", "--allow-empty", "-m", "root"], cwd=project, check=True)
            source["revision"] = subprocess.run(["git", "-C", str(project), "rev-parse", "HEAD"],
                                                capture_output=True, text=True, check=True).stdout.strip()
            authority.project = project
            self.assertEqual(plan_qual.check(scenario, self.provider(scenario), authority, None), [])
            source["revision"] = "b" * 40
            problems = plan_qual.check(scenario, self.provider(scenario), authority, None)
            self.assertTrue(any("observed source" in p for p in problems), problems)


class FrozenTests(unittest.TestCase):
    def test_freezes_the_scenarios_rounds_without_rules(self):
        roles, frozen = plan_qual.Frozen(2, {"planner": {}}).freeze_plan()
        self.assertEqual(roles, {"planner": {}})
        self.assertEqual((frozen["plan_rounds"], frozen["rules"]), (2, []))
        self.assertEqual(len(frozen["config_digest"]), 64)


if __name__ == "__main__":
    unittest.main()
