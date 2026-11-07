"""R1a S1 acceptance: a Goldfish review is a draft revision of execution 2 reviewed by a planner-free graph.

Design: docs/designs/2026-11-03-egm-planning.md sections 4.1-4.3. Real Git and stores, the fixture engine and the
scripted native binary of test_terminal_planner; the pinned zeroshot binary for admission when it is installed.
"""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from terminal_planner import authority as auth, engine
from terminal_planner.authority import Blocked, canonical
from terminal_planner.engine import FixtureEngine
import test_plan_gate as tpg
from test_milestone import nodes, pinned_binary
from test_terminal_planner import ROLES, Authority, ProjectTest, fixture_proposal

PARAPHRASE = "It adds one milestone that changes source.txt and checks it."


def goldfish_output(paraphrase=PARAPHRASE, verdict="accepted", findings="ok", response="", proposal=None):
    rounds = [{"round": 1, "verdict": verdict, "findings": findings, "response": response}]
    return {"schemaVersion": "2", "proposal": canonical(proposal or fixture_proposal()), "planVerdict": verdict,
            "planFindings": findings, "planResponse": response, "discussion": canonical({"version": 1, "rounds": rounds}),
            "paraphrase": paraphrase}


class GraphTests(unittest.TestCase):
    def test_the_goldfish_graph_has_no_planner_and_the_reader_sees_only_its_own_input(self):
        graph = engine.goldfish_graph()
        by_name = {n.get("name"): n for n in nodes(graph["root"])}
        self.assertNotIn("planner", by_name)
        self.assertIn("comprehension", by_name)
        self.assertIn("critic", by_name)
        reader = by_name["comprehension"]
        self.assertEqual([b["value"]["path"] for b in reader["inputBindings"]], [["reader"]])
        self.assertEqual(engine.goldfish_runtime(ROLES)["nodes"]["comprehension"]["sessionScope"], "execution")
        self.assertEqual(engine.goldfish_runtime(ROLES)["nodes"]["critic"]["model"], ROLES["plan_verifier"]["model"])


class FrozenDocumentTests(unittest.TestCase):
    def test_the_plan_check_documents_are_byte_identical_to_0_14(self):
        """0.15 F3: the Goldfish graph, runtime and input for one fixed context (a chain's second revision with an
        earlier request, a response and a red base) hash as they did in 0.14.0. A deliberate change of the plan
        check updates these digests in its own commit, which says why."""
        import hashlib
        context = {"goal": "Goal", "feedback": "An earlier request.", "roles": ROLES, "version": 2,
                   "draft": engine.fixture_draft(), "response": "A reply.",
                   "base": {"outcome": "failed", "failed": ["unit"], "refused": "", "tail": "1 failed"}}
        documents = {"graph": engine.goldfish_graph(), "runtime": engine.goldfish_runtime(ROLES),
                     "input": engine.goldfish_input(context)}
        digests = {name: hashlib.sha256(canonical(value).encode()).hexdigest() for name, value in documents.items()}
        self.assertEqual(digests, {
            "graph": "188772bd93c0b704b447fa4d6fa26f4f7c1f00ffe692c4295e68f6fd1dd845b3",
            "runtime": "9819cce7205901d2d4d8cec107a5f3f157319dc9d244cc92db954d4c8cb818f2",
            "input": "996d6c9fedb9c918f94492f6a8ecf9de5e674413c56619269c41c994d8446f94"})


@unittest.skipUnless(pinned_binary(), "pinned zeroshot binary absent (set ZEROSHOT_TEST_BINARY)")
class AdmissionTests(unittest.TestCase):
    def test_the_goldfish_documents_pass_native_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            for args in (["init", "-q", "-b", "main"], ["commit", "-q", "--allow-empty", "-m", "fixture"]):
                subprocess.run(["git", "-C", str(project), "-c", "user.name=t", "-c", "user.email=t@localhost", *args],
                               check=True, capture_output=True)
            context = {"goal": "Goal", "feedback": "", "roles": ROLES, "version": 1, "draft": fixture_proposal()}
            documents = {"graph": engine.goldfish_graph(), "runtime": engine.goldfish_runtime(ROLES),
                         "input": engine.goldfish_input(context)}
            for name, value in documents.items():
                (root / (name + ".json")).write_text(json.dumps(value))
            env = dict(os.environ, ZEROSHOT_STATE_DIR=str(root / "state"), ZEROSHOT_CONFIG_DIR=str(root / "config"))
            result = subprocess.run([str(pinned_binary()), "run", "--title", "goldfish admission",
                                     "--graph", str(root / "graph.json"), "--runtime-config", str(root / "runtime.json"),
                                     "--input", str(root / "input.json"), "--no-environment", "--validate-only"],
                                    cwd=project, env=env, capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stderr[-2000:])
            self.assertIs(json.loads(result.stdout)["valid"], True)


class StoreTests(ProjectTest):
    def test_a_goldfish_revision_is_stored_and_reopens(self):
        with Authority(self.state, self.project) as authority:
            authority.begin("Goal", ROLES, "fixture", draft=fixture_proposal(), review="goldfish")
            self.assertEqual(authority.current["frozen"]["review"], "goldfish")
        with Authority(self.state, self.project) as authority:
            self.assertEqual(authority.current["frozen"]["review"], "goldfish")
            self.assertEqual(authority.current["draft"], fixture_proposal())

    def test_a_goldfish_review_without_a_draft_is_refused_and_writes_nothing(self):
        with Authority(self.state, self.project) as authority:
            self.begin(authority)
            before = authority.path.read_bytes()
            with self.assertRaises(Blocked):
                authority.begin("Goal", ROLES, "fixture", review="goldfish")
            self.assertEqual(authority.path.read_bytes(), before)

    def test_a_revision_without_review_keeps_its_frozen_keys(self):
        with Authority(self.state, self.project) as authority:
            authority.begin("Goal", ROLES, "fixture", draft=fixture_proposal())
            self.assertNotIn("review", authority.current["frozen"])


class FixtureReviewTests(ProjectTest):
    def review(self, scenario):
        with Authority(self.state, self.project) as authority:
            plan = fixture_proposal()
            authority.begin("Goal", ROLES, "fixture", draft=plan, review="goldfish")
            FixtureEngine(scenario).proposal(authority, lambda _: None)
            return authority.current, plan

    def test_an_accepted_review_is_proposed_with_the_paraphrase_and_can_be_approved(self):
        current, plan = self.review("accept")
        self.assertEqual(current["status"], "proposed")
        self.assertEqual(current["proposal"], plan)
        self.assertTrue(current["evidence"]["paraphrase"].strip())
        self.assertEqual(current["evidence"]["rounds_used"], 1)
        with Authority(self.state, self.project) as authority:
            authority.approve(current["version"])
            self.assertEqual(authority.current["status"], "approved")

    def test_a_rejecting_critic_ends_the_review_after_one_round(self):
        current, _ = self.review("exhausted")
        self.assertEqual(current["status"], "review_exhausted")
        self.assertEqual(current["evidence"]["rounds_used"], 1)
        self.assertEqual(current["evidence"]["critic_verdict"], "rejected")


class OutputTests(unittest.TestCase):
    def test_a_long_paraphrase_is_clipped_never_rejected_and_the_read_is_deterministic(self):
        output = goldfish_output(paraphrase="x" * 5000)
        first = auth.read_goldfish_review(output)
        second = auth.read_goldfish_review(json.loads(json.dumps(output)))
        self.assertEqual(first, second)
        self.assertEqual(first[-1], "x" * auth.PARAPHRASE_LIMIT)
        self.assertEqual(auth.PARAPHRASE_LIMIT, 3000)

    def test_an_output_without_a_paraphrase_is_not_a_goldfish_review(self):
        output = goldfish_output()
        del output["paraphrase"]
        with self.assertRaises(Blocked):
            auth.read_goldfish_review(output)


class NativeDocumentTests(tpg.GateBase):
    def test_a_goldfish_revision_submits_the_goldfish_documents_and_records_the_paraphrase(self):
        plan = fixture_proposal()
        terminal = self.projection({"phase": "finished", "terminalResult": {
            "status": "succeeded", "output": goldfish_output(proposal=plan)}})
        native, calls = self.engine([{"valid": True}, {"runId": "fixture-native-run"}, terminal])
        with self.authority() as authority:
            authority.begin("Requested feature", ROLES, "native", draft=plan, review="goldfish")
            native.proposal(authority, lambda _: None)
            documents = self.documents(calls[1][1])
            self.assertEqual(documents["graph"], engine.goldfish_graph())
            reader = auth.decode(documents["input"]["reader"])
            self.assertEqual((reader["goal"], reader["plan"]), ("Requested feature", plan))
            self.assertEqual(authority.current["status"], "proposed")
            self.assertEqual(authority.current["evidence"]["paraphrase"], PARAPHRASE)

    def prepared_task(self, settled):
        plan = fixture_proposal()
        terminal = self.projection({"phase": "finished", "terminalResult": {
            "status": "succeeded", "output": goldfish_output(proposal=plan)}})
        native, calls = self.engine([{"valid": True}, {"runId": "fixture-native-run"}, terminal])
        with self.authority() as authority:
            authority.begin("Requested feature", ROLES, "native", draft=plan, review="goldfish")
            if settled:
                head = subprocess.check_output(["git", "-C", str(self.project), "rev-parse", "HEAD"], text=True).strip()
                tree = subprocess.check_output(["git", "-C", str(self.project), "rev-parse", "HEAD^{tree}"], text=True).strip()
                authority.current["base_checks"] = {"commit": head, "tree": tree, "checks_digest": "d" * 64,
                                                    "outcome": "failed", "failed": ["unit"], "refused": "",
                                                    "tail": "AssertionError: 1 != 2"}
                authority.save()
            native.proposal(authority, lambda _: None)
            documents = self.documents(calls[1][1])
        critic = next(n for n in nodes(documents["graph"]["root"]) if n["name"] == "critic")
        return auth.decode(documents["input"]["task"]), critic["instructions"]

    def test_a_settled_revision_gives_the_critic_the_base_result_and_the_readiness_rules(self):
        """0.13 G2: a revision settled before its documents are prepared gives the critic `input.task.base` for its
        W2 rule, beside the readiness rules F1, F2, F4, W1 and W2."""
        task, instructions = self.prepared_task(settled=True)
        self.assertEqual(task["base"], {"outcome": "failed", "failed": ["unit"], "refused": "",
                                        "tail": "AssertionError: 1 != 2"})
        for rule in ("readiness:", "(W1)", "never commits, pushes, rewrites history, deploys", "(W2) the task's base field"):
            self.assertIn(rule, instructions)

    def test_a_revision_without_base_checks_prepares_no_base(self):
        task, _ = self.prepared_task(settled=False)
        self.assertNotIn("base", task)

if __name__ == "__main__":
    unittest.main()
