"""G2-start core (S1a slice 1a): the task gate's pure projection, graph, identity and parser.

Nothing here is reachable from a user action: the durable record, the dispatch protocol and the start barrier are
the next slice, the UI/CLI adapters and docs the third. Deterministic fixtures and real temporary Git repositories
only; no provider, no network.

Interpretations (none fixed by the parent text; kept here for the reviewers):
- The gate output is schemaVersion "1" with fields taskResponse/taskVerdict/taskFindings/discussion; the parent
  fixes only the discussion shape and the record's field names, not the node output's.
- `task_gate_runtime(roles)` takes the graph's own node keys ("proposer", "critic"); the resolved profile bindings
  that fill them are the dispatch slice's business.
- The terminals are accepted_task_gate/exhausted_task_gate/proposer_failed/critic_failed (the parent names the
  outcomes only).
- `identity_matches` compares mappings keyed by artifact_digest/resolved_config_digest/head (built by
  `task_gate.identity`); the validity predicate is the record slice's. Exclusions are exactly the parent's:
  `plan_revision`, `progress`, `outcome` and, inside the baseline, `plan_revision` and `limits`.
- The task gate's refusal subject is "task checks"; the plan gate's bytes and messages are unchanged.
- The proposer is a `verifier` node and carries the read-only native contract; R-3 fixes "two read-only nodes",
  not their node kinds or worker labels, and the worker label is only a name (the milestone graph labels the same
  two kinds with its own refs). Its `verdict` signal is the proposed verdict and nothing binds it: only the
  critic's verdict is acceptance.
- The A-1 goldens of the stored revision, the preview and the home text mask the fixture's volatile identifiers
  (the checkout root, run ids and every hexadecimal run of six or more characters) so that they freeze the
  persisted field set and the wording of both configurations against the base.
"""

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from terminal_planner import engine, milestone, process, runs, task_gate
from terminal_planner.authority import Authority as RealAuthority, Blocked, canonical
from terminal_planner.engine import (fixture_proposal, planner_graph, planner_graph_v2, planner_input,
                                     planner_input_v2, planner_runtime, planner_runtime_v2)
from terminal_planner.setup import tool_paths
import test_process as tpr
import test_terminal_planner as tp
from test_plan_gate import GraphTests as PlanGraphTests, V1_GOLDEN, nodes, round_, sha
from test_terminal_planner import ROLES

# The fixture's volatile identifiers: run ids are uuids, the rest are hexadecimal digests, Git SHAs, the project
# id and its short branch prefixes.
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
VOLATILE_HEX = re.compile(r"[0-9a-f]{6,}")


def pinned_binary():
    """The installed pinned zeroshot binary, or None (the native checks skip)."""
    path = Path(os.environ.get("ZEROSHOT_TEST_BINARY") or tool_paths()[0])
    return path if path.is_file() else None

# sha256 of the canonical documents captured on the base (6e23523), except the two graph goldens: C0a (the review
# bar) adds the plan critic's bar to the v1 and v2 verifier text and A2a (the task brief) the brief fields to the
# planner and verifier text and RC1 the milestone-isolation sentence to both and H3 the dod sentence to the planner and H2 turns the v2 planner into a verifier (kind, empty signals, diagnostic) and H4 removes the dev marker from the node texts, rewrites DRIVER_MECHANICS and the critic's authority sentence and H5 words the final check once per milestone and D1 (the final check's repairs and re-checks), so a newly built graph carries it while the stored
# documents of already prepared, submitted or approved revisions keep their bytes. The runtime, input and the bare
# configuration are still the base's bytes.
BASE_GOLDEN = {
    "v2_graph_2": "5f9bc48d6b1ea11ab8055c4ba1e371e52a183f8f84f4966c538720e69125761b",
    "v2_graph_3": "aa17aedf731ad431ec1e3c314af22c32ada212a96808c7dcd0f69d5b5eefead7",
    "v2_runtime": "0f579a7650f32d8ca355a4129f4417e036e0a3d91f59c6a6da0d89775c448d00",
    "v2_input": "6caa2a7c3b63a299280836de9776f0003dc4d8ac26a8bd47e2c065f3bee0b2a1",
    "config_digest": "4cd20d1393ccd81f56cc118262e2be210bf9ab71bd3b27edb10960e9a84e407f",
}


def entry(graph, name):
    return next(n for n in nodes(graph["root"]) if n["name"] == name)


# A-1 ------------------------------------------------------------------------------------------------------------

class BaseTests(unittest.TestCase):
    """Off is identical: the plan runtime, input and the bare normalized configuration are the base's bytes (A-1); the
    two plan graphs moved only for C0a's review bar (the runtime, the input and the configuration did not)."""

    def test_the_plan_documents_and_the_normalized_configuration_are_the_base_bytes(self):
        self.assertEqual(sha(planner_graph()), V1_GOLDEN["graph"])
        self.assertEqual(sha(planner_runtime(PlanGraphTests.ROLES)), V1_GOLDEN["runtime"])
        self.assertEqual(sha(planner_input({"a": 1})), V1_GOLDEN["input"])
        self.assertEqual(sha(planner_graph_v2(2)), BASE_GOLDEN["v2_graph_2"])
        self.assertEqual(sha(planner_graph_v2(3)), BASE_GOLDEN["v2_graph_3"])
        self.assertEqual(sha(planner_runtime_v2(ROLES)), BASE_GOLDEN["v2_runtime"])
        self.assertEqual(sha(planner_input_v2({"goal": "g"})), BASE_GOLDEN["v2_input"])
        self.assertEqual(process.resolve(None, {}, None).digest, BASE_GOLDEN["config_digest"])


class OffTests(tpr.ProfileTest):
    def test_a_required_task_gate_still_refuses_a_start_as_unbuilt(self):
        """The lifecycle guard is untouched while the record contract is missing (A-1)."""
        self.accept_file({"gates": {"task": "required"}})
        self.approved_plan()
        with self.app() as app:
            with self.assertRaises(Blocked) as raised:
                app.delivery.preview("M1", app.roles)
            self.assertEqual(raised.exception.family, "process.unbuilt")


class OffIdenticalTests(tpr.ProfileTest):
    """A-1: with preset `/1` and with an explicit `gates.task: "off"` the whole journey is the base's bytes.

    The goldens were captured on the base commit (a clean `git archive HEAD` checkout): the stored plan revision
    (the whole revision record), the preview text and the home text. The fixture's volatile identifiers are masked
    before hashing (see `masked`), so the golden freezes the persisted field set and the wording; a persisted
    task-gate field added anywhere in the revision changes the stored bytes and fails this test for both
    configurations, which the graph/config goldens above did not catch. The profile file is accepted first: an
    unaccepted profile refuses the preview on G1a grounds, unrelated to the gate.
    D4a made the stored baseline `v2:` + the digest of HEAD and branch alone, so the revision golden was recaptured
    on that commit; the preview is the base's bytes still. The home was recaptured for the English interface (T1);
    it renders delivery.py's text too, so T3 re-pins it on the merged tree.
    T3b re-pinned the preview and the home on the merged 0.8.0 tree (zs-t3b-close, after c2bb5d0): the revision hash
    is unchanged there, so only the English text moved.
    """

    GOLDEN = {"revision": "e7016a1f044ca12ebe5f4bbfdcae5bdb5e21ee26c90d7fee2320fa893d65ac80",
              "preview": "ee22171e9ed0755eda7dc9632120e0c849eaefa698cce6eeb7f921db6ca3f53a",
              "home": "141954bd8f6fb110fc8240dec1de1ab66e0a6127cc00c6f3bd7f6748e40be2fb"}
    CONFIG = {"preset /1": {"preset": "zplan.default/1"},
              "explicit gates.task off": {"preset": "zplan.default/1", "gates": {"task": "off"}}}

    def masked(self, value):
        """The value with the fixture's volatile identifiers replaced by placeholders (see the module constants)."""
        if isinstance(value, str):
            return VOLATILE_HEX.sub("<hex>", UUID.sub("<uuid>", value.replace(str(self.root), "<root>")))
        if isinstance(value, dict):
            return {name: self.masked(item) for name, item in value.items()}
        if isinstance(value, list):
            return [self.masked(item) for item in value]
        return value

    def journey(self, configuration):
        """Accept the configuration, approve a fixture plan and digest the stored revision, the preview and home."""
        self.accept_file(self.CONFIG[configuration])
        self.approved_plan()
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            revision = copy.deepcopy(authority.state["revisions"][0])
        with self.app() as app:
            preview = "\n".join(app.delivery.preview("M1", app.roles).lines)
            home = "\n".join(app.delivery.home().lines)
        return (hashlib.sha256(canonical(self.masked(revision)).encode()).hexdigest(),
                hashlib.sha256(self.masked(preview).encode()).hexdigest(),
                hashlib.sha256(self.masked(home).encode()).hexdigest())

    def test_the_preset_journey_stores_the_base_revision_preview_and_home(self):
        self.assertEqual(self.journey("preset /1"),
                         (self.GOLDEN["revision"], self.GOLDEN["preview"], self.GOLDEN["home"]))

    def test_an_explicit_task_off_journey_stores_the_base_revision_preview_and_home(self):
        self.assertEqual(self.journey("explicit gates.task off"),
                         (self.GOLDEN["revision"], self.GOLDEN["preview"], self.GOLDEN["home"]))


# A-2 ------------------------------------------------------------------------------------------------------------

class GraphTests(unittest.TestCase):
    """The task-gate graph, runtime and input: the plan gate's shape with a proposer and a critic (A-2)."""

    def test_the_graph_bounds_the_loop_and_carries_the_briefs_with_an_empty_discussion(self):
        for rounds in (1, 2, 3, 10):
            with self.subTest(rounds=rounds):
                graph = engine.task_gate_graph(rounds)
                loop = entry(graph, "review_loop")
                self.assertEqual((loop["kind"], loop["maxIterations"]), ("loop", rounds))
                self.assertEqual([n["name"] for n in nodes(graph["root"]) if n["kind"] == "fail"],
                                 ["proposer_failed", "critic_failed"])
                self.assertEqual([n["name"] for n in nodes(graph["root"]) if n["kind"] == "succeed"],
                                 ["accepted_task_gate", "exhausted_task_gate"])
                self.assertEqual((entry(graph, "proposer")["kind"], set(entry(graph, "proposer")["output"]["fields"])),
                                 ("verifier", {"taskResponse"}))
                self.assertEqual((entry(graph, "critic")["kind"], set(entry(graph, "critic")["output"]["fields"])),
                                 ("verifier", {"discussion"}))
                self.assertEqual({g["value"]["name"] for g in loop["until"]["guards"]}, {"critic"})
        runtime = engine.task_gate_runtime({name: {"model": name, "effort": "high"} for name in ("proposer", "critic")})
        self.assertEqual(set(runtime["nodes"]), {"proposer", "critic"})
        for name in ("proposer", "critic"):
            self.assertEqual(runtime["nodes"][name]["sessionScope"], "node_instance")
        context = {"artifact": {"milestone": {"id": "M1"}}, "head": "0" * 40, "owner_rules": {"files": []}}
        document = engine.task_gate_input(context)
        self.assertEqual((document["schemaVersion"], json.loads(document["task"])), ("1", context))
        self.assertEqual(json.loads(document["discussion"]), {"version": 1, "rounds": []})

    def test_the_proposer_has_no_write_path_to_the_artifact(self):
        """The artifact (the `task` state) is read-only: the proposer writes only its own response."""
        graph = engine.task_gate_graph(3)
        self.assertEqual([b["target"] for b in entry(graph, "proposer")["writeBindings"]], [["taskResponse"]])
        targets = {t for node in nodes(graph["root"]) for b in node.get("writeBindings", []) for t in b["target"]}
        self.assertNotIn("task", targets)


class ProposerContractTests(unittest.TestCase):
    """R-3: the proposer is read-only, so its native contract must not tell it to install anything.

    The pinned runtime appends one role block to every agent node's prompt. A `step` node (the Worker contract)
    gets "Runtime-owned workspace setup guidance: Before returning, follow repository setup and install
    manifest/lockfile dependencies in the checkout ..."; a `verifier` node (the Verifier contract) gets
    "Runtime-owned verifier guidance: ... Do not run setup or dependency-install commands that rewrite the
    checkout ...". The proposer never installs and never changes the checkout, so the Worker text contradicts R-3
    and the proposer's own instructions. Interpretation: R-3 fixes "two read-only nodes", not their node kinds or
    worker labels, and the label is only a name (the milestone graph labels the same two kinds with its own refs,
    and the built-in `software-change` template carries a `verifier` kind on a `builtin.git-delivery.*` label), so
    the node's own kind - the only place its signals are declared - selects the contract, and the proposer is a
    `verifier` node. Its `verdict` signal carries the proposed verdict and nothing binds it; only the critic's
    verdict is authoritative.
    """

    def test_the_proposer_is_not_the_installing_step_worker(self):
        proposer = entry(engine.task_gate_graph(2), "proposer")
        self.assertEqual(proposer["kind"], "verifier")
        self.assertIn("diagnostic", proposer)

    def test_the_authored_proposer_contract_requires_the_round_two_classification(self):
        """R-3: from round 2 every finding is answered as fixed-impossible / disputed, with why."""
        text = entry(engine.task_gate_graph(2), "proposer")["instructions"]
        self.assertIn("from the second round", text)
        self.assertIn("answer every finding", text)
        self.assertIn("fixed-impossible", text)
        self.assertIn("disputed", text)
        self.assertIn("output.taskResponse", text)  # a verifier node answers with output, signals and diagnostic
        self.assertIn("diagnostic.message", text)
        self.assertIn("fixed (and how) or disputed (and why)",
                      entry(planner_graph_v2(2), "planner")["instructions"])  # the plan gate keeps its own words


@unittest.skipUnless(pinned_binary(), "pinned zeroshot binary absent (set ZEROSHOT_TEST_BINARY)")
class PinnedGuidanceTests(unittest.TestCase):
    """The pinned runtime's role guidance, read from the installed binary itself."""

    def test_only_the_worker_block_tells_the_node_to_install_dependencies(self):
        raw = pinned_binary().read_bytes()
        worker = raw.index(b"Runtime-owned workspace setup guidance:")
        verifier = raw.index(b"Runtime-owned verifier guidance:")
        self.assertLess(worker, verifier)
        worker_block = raw[worker:verifier]
        verifier_block = raw[verifier:verifier + 400]
        self.assertIn(b"install manifest/lockfile dependencies in the checkout", worker_block)
        self.assertIn(b"Wait for setup to finish and check exit status", worker_block)
        self.assertNotIn(b"install manifest/lockfile dependencies", verifier_block)
        self.assertIn(b"Do not run setup or dependency-install commands that rewrite the checkout", verifier_block)


@unittest.skipUnless(pinned_binary(), "pinned zeroshot binary absent (set ZEROSHOT_TEST_BINARY)")
class AdmissionTests(unittest.TestCase):
    """The frozen task-gate documents pass the pinned native admission (validate-only: no provider, no run).

    Admission covers the documents, not the graph's behavior: native behavioral qualification of the new graph
    stays with the orchestrator on the Linux host.
    """

    def test_the_task_gate_documents_pass_native_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            for args in (["init", "-q", "-b", "main"], ["commit", "-q", "--allow-empty", "-m", "fixture"]):
                subprocess.run(["git", "-C", str(project), "-c", "user.name=t", "-c", "user.email=t@localhost", *args],
                               check=True, capture_output=True)
            context = {"artifact": {"milestone": {"id": "M1"}}, "head": "0" * 40, "owner_rules": {"files": []}}
            documents = (engine.task_gate_graph(2),
                         engine.task_gate_runtime({"proposer": {"model": "gpt-6.1-sol", "effort": "medium"},
                                                   "critic": {"model": "gpt-6.1-sol", "effort": "high"}}),
                         engine.task_gate_input(context))
            for kind, value in zip(("graph", "runtime", "input"), documents):
                (root / (kind + ".json")).write_text(json.dumps(value))
            result = subprocess.run([str(pinned_binary()), "run", "--title", "zplan task gate admission",
                                     "--graph", str(root / "graph.json"), "--runtime-config", str(root / "runtime.json"),
                                     "--input", str(root / "input.json"), "--no-environment", "--validate-only"],
                                    cwd=project, env=dict(os.environ, ZEROSHOT_STATE_DIR=str(root / "state")),
                                    capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stderr[-2000:])
            self.assertIs(json.loads(result.stdout)["valid"], True)


class Interpreter(unittest.TestCase):
    """The authored task-gate graph executed with scripted answers (a control fixture, not a native scheduler)."""

    def run_graph(self, answers, rounds=3, error=None):
        """`answers`: per round (verdict, findings, response). The critic appends its round to the discussion it was
        given and the interpreter asserts the proposer sees exactly the previous findings and response, as its
        instructions say. Returns the terminal result."""
        graph = engine.task_gate_graph(rounds)
        channels = {}
        script = iter(answers)
        current = None

        def guard(g):
            if g["kind"] == "any":
                return any(guard(child) for child in g["guards"])
            selector = g["value"]
            value = channels.get((selector["name"], selector["source"]), {})
            return (value.get(selector["field"]) if selector.get("field") else value) in g["labels"]

        def bindings(items, state):
            result = {}
            for b in items:
                v = b["value"]
                source = state if v.get("source") == "state" else channels[(v["node"], v["channel"])]
                result[b["target"][0]] = source[v["path"][0]]
            return result

        def run(node, parent):
            nonlocal current
            kind, name = node["kind"], node["name"]
            state = copy.deepcopy(parent) if "state" in node else parent
            result = None
            if kind in {"step", "verifier"}:
                incoming = bindings(node["inputBindings"], state)
                channels[(name, "error")] = "crash" if error == name else None
                if error == name:
                    return None
                history = json.loads(incoming["discussion"])
                if name == "proposer":
                    current = next(script)
                    if history["rounds"]:
                        self.assertEqual(incoming["taskFindings"], history["rounds"][-1]["findings"])
                    channels[(name, "signal")] = {"verdict": current[0]}
                    channels[(name, "diagnostic")] = {"message": current[1]}
                    channels[(name, "out")] = {"taskResponse": current[2]}
                else:
                    self.assertEqual(incoming["taskResponse"], current[2])
                    history["rounds"].append({"round": len(history["rounds"]) + 1, "verdict": current[0],
                                              "findings": current[1], "response": incoming["taskResponse"]})
                    channels[(name, "signal")] = {"verdict": current[0]}
                    channels[(name, "diagnostic")] = {"message": current[1]}
                    channels[(name, "out")] = {"discussion": canonical(history)}
                state.update(bindings(node["writeBindings"], state))
            elif kind == "seq":
                for child in node["children"]:
                    result = run(child, state)
                    if result is not None:
                        break
            elif kind == "choice":
                chosen = next((b["node"] for b in node["branches"] if guard(b["when"])), node.get("otherwise"))
                self.assertIsNotNone(chosen)
                result = run(chosen, state)
            elif kind == "loop":
                for _ in range(node["maxIterations"]):
                    result = run(node["body"], state)
                    if result is not None or guard(node["until"]):
                        channels[(name, "group")] = {"terminated": "converged"}
                        break
                else:
                    channels[(name, "group")] = {"terminated": "exhausted"}
            elif kind == "succeed":
                result = {"status": "succeeded", "output": bindings(node["bindings"], state)}
            elif kind == "fail":
                result = {"status": "failed", "reason": node["reason"]}
            else:
                self.fail("unsupported node " + kind)
            for path in node.get("promotedStatePaths", []):
                parent[path[0]] = state[path[0]]
            return result

        context = {"artifact": {"milestone": {"id": "M1"}}, "head": "0" * 40, "owner_rules": {"files": []}}
        return run(graph["root"], engine.task_gate_input(context))


class InterpretedGraphTests(Interpreter):
    def test_a_rejection_then_a_reasoned_dispute_accepted_ends_accepted_and_is_readable(self):
        first = self.run_graph([("accepted", "ok", "accepted")], rounds=3)  # acceptance stops the loop in round 1
        self.assertEqual(len(json.loads(first["output"]["discussion"])["rounds"]), 1)
        answers = [("rejected", "F1", "r1"), ("accepted", "Dispute accepted: F1 holds.", "F1 disputed: the brief is needed.")]
        result = self.run_graph(answers, rounds=2)
        self.assertEqual((result["status"], result["output"]["taskVerdict"], result["output"]["taskResponse"]),
                         ("succeeded", "accepted", answers[1][2]))
        verdict, findings, response, discussion = task_gate.read_review(result["output"], 2)
        self.assertEqual((verdict, findings, response), ("accepted", "Dispute accepted: F1 holds.", answers[1][2]))
        self.assertEqual([r["findings"] for r in discussion["rounds"]], ["F1", "Dispute accepted: F1 holds."])

    def test_exhaustion_ends_rejected_after_exactly_the_frozen_rounds(self):
        for rounds in (1, 2, 10):
            with self.subTest(rounds=rounds):
                result = self.run_graph([("rejected", "F%d" % n, "r%d" % n) for n in range(1, rounds + 2)], rounds=rounds)
                self.assertEqual((result["status"], result["output"]["taskVerdict"]), ("succeeded", "rejected"))
                self.assertEqual(len(json.loads(result["output"]["discussion"])["rounds"]), rounds)

    def test_node_errors_fail_with_their_own_native_reasons(self):
        for node, reason in (("proposer", "proposer_failed"), ("critic", "critic_failed")):
            with self.subTest(node=node):
                self.assertEqual(self.run_graph([("accepted", "ok", "r")], error=node),
                                 {"status": "failed", "reason": reason})


# A-6b -----------------------------------------------------------------------------------------------------------

def task_output(value, **over):
    last = value["rounds"][-1] if value["rounds"] else {}
    output = {"schemaVersion": "1", "taskVerdict": last.get("verdict", "accepted"),
              "taskFindings": last.get("findings", "f"), "taskResponse": last.get("response", "r"),
              "discussion": canonical(value)}
    output.update(over)
    return output


def discussion_of(limit, total=None):
    """A well-formed discussion of exactly `limit` rounds; with `total`, of exactly that many canonical bytes."""
    rounds = [round_(n, response="a" * 4000 if total else "r") for n in range(1, limit + 1)]
    rounds[-1]["verdict"] = "accepted"
    if total is not None:
        rounds[-1]["response"] = ""
        rounds[-1]["response"] = "a" * (total - len(canonical({"version": 1, "rounds": rounds}).encode()))
        assert 0 <= len(rounds[-1]["response"]) <= 4000
    return {"version": 1, "rounds": rounds}


class ParserTests(unittest.TestCase):
    """The task-gate output and its bounded discussion at the parser (A-6b)."""

    def refused(self, output, limit=task_gate.DEFAULT_ROUNDS):
        with self.assertRaises(Blocked) as raised:
            task_gate.read_review(output, limit)
        self.assertEqual(raised.exception.family, "engine.bad_output")
        self.assertIn("task checks", str(raised.exception))

    def test_the_round_limit_bounds_the_discussion(self):
        for limit in (1, 2, 10):
            with self.subTest(limit=limit):
                task_gate.read_review(task_output(discussion_of(limit)), limit)
                self.refused(task_output(discussion_of(limit + 1)), limit)

    def test_malformed_or_inconsistent_discussions_are_refused(self):
        good = [round_(1), round_(2, "accepted", "fine", "fixed")]
        cases = {
            "not json": task_output({"version": 1, "rounds": good}, discussion="{broken"),
            "wrong version": {"version": 2, "rounds": good},
            "bool version": {"version": True, "rounds": good},
            "extra field": {"version": 1, "rounds": good, "x": 1},
            "no rounds": {"version": 1, "rounds": []},
            "gap in numbers": {"version": 1, "rounds": [round_(1), round_(3, "accepted")]},
            "non-final round not rejected": {"version": 1, "rounds": [round_(1, "accepted"), round_(2)]},
            "round field missing": {"version": 1, "rounds": [{"round": 1, "verdict": "accepted", "findings": "f"}]},
            "text too long": {"version": 1, "rounds": [round_(1, "accepted", "x" * 4001)]},
        }
        for label, value in cases.items():
            with self.subTest(case=label):
                self.refused(value if "discussion" in value else task_output(value))
        for key, value in (("taskVerdict", "rejected"), ("taskFindings", "other"), ("taskResponse", "other")):
            with self.subTest(inconsistent=key):
                self.refused(task_output({"version": 1, "rounds": good}, **{key: value}))

    def test_the_text_and_total_size_caps_hold_at_their_boundaries(self):
        for size, fresh in ((4000, True), (4001, False)):
            with self.subTest(characters=size):
                output = task_output({"version": 1, "rounds": [round_(1, "accepted", "f", "a" * size)]})
                (task_gate.read_review if fresh else self.refused)(output, 1)
        for total, fresh in ((32768, True), (32769, False)):
            with self.subTest(bytes=total):
                output = task_output(discussion_of(9, total))
                self.assertEqual(len(output["discussion"].encode()), total)
                (task_gate.read_review if fresh else self.refused)(output, 9)


# A-4p -----------------------------------------------------------------------------------------------------------

class ProjectionTests(unittest.TestCase):
    """The pure artifact projection and the (artifact, configuration, HEAD) identity (A-4p)."""

    def manifest(self, proposal=None, milestone_id="M1", context=None):
        baseline = milestone.build_baseline(proposal or fixture_proposal(), milestone_id, 0)
        return baseline, runs.bootstrap_manifest(baseline, context)

    def test_tasks_checks_a_candidate_and_an_owner_note_change_the_digest(self):
        baseline, manifest = self.manifest()
        base = task_gate.artifact_digest(manifest)
        for label, mutate in (("task", lambda m: m["tasks"][0].__setitem__("title", "Another title")),
                              ("checks", lambda m: m["tasks"][0].__setitem__("checks", ["Another check"]))):
            with self.subTest(change=label):
                changed = copy.deepcopy(manifest)
                mutate(changed)
                self.assertNotEqual(task_gate.artifact_digest(changed), base)
        tasks = copy.deepcopy(manifest["tasks"])
        tasks[0]["title"] = "Candidate title"
        contexts = {"candidate": {"kind": "proposal", "source": 1, "text": "Owner accepted a proposal.",
                                  "candidate": {"tasks": tasks, "amendments": [{"seq": 1, "kind": "reword",
                                                                               "tasks": ["T1"], "parents": [],
                                                                               "reason": "Reworded brief."}]}},
                    "owner note": {"kind": "answer", "source": 1, "text": "Owner answer.", "candidate": None}}
        for label, context in contexts.items():
            with self.subTest(change=label):
                self.assertNotEqual(task_gate.artifact_digest(runs.bootstrap_manifest(baseline, context)), base)
        other = fixture_proposal()  # another milestone changes its own briefs, not this artifact
        other["milestones"][1]["slices"][0]["tasks"][0]["checks"] = ["A different M2 check"]
        with self.subTest(change="another milestone"):
            self.assertEqual(task_gate.artifact_digest(self.manifest(other, "M1")[1]), base)

    def test_the_excluded_fields_do_not_change_the_artifact_digest(self):
        """Mutation target: inverting any exclusion (e.g. keeping plan_revision) makes this test fail."""
        _, manifest = self.manifest()
        base, artifact = task_gate.artifact_digest(manifest), task_gate.artifact(manifest)
        self.assertEqual(set(artifact), set(manifest) - set(task_gate.EXCLUDED))
        self.assertEqual(set(artifact["baseline"]), set(manifest["baseline"]) - set(task_gate.EXCLUDED_BASELINE))
        changed = copy.deepcopy(manifest)
        changed["plan_revision"] = changed["baseline"]["plan_revision"] = 7
        changed["baseline"]["limits"]["max_additions"] += 1
        changed["progress"] = [{"seq": 1, "kind": "note"}]
        changed["outcome"] = "done"
        self.assertEqual(task_gate.artifact_digest(changed), base)

    def test_identity_matches_accepts_only_equal_identities(self):
        """Mutation target: dropping any of the three comparisons makes one of these cases pass wrongly."""
        gate = task_gate.identity("artifact", "config", "head")
        self.assertTrue(task_gate.identity_matches(gate, task_gate.identity("artifact", "config", "head")))
        for label, live in (("artifact", task_gate.identity("other", "config", "head")),
                            ("config", task_gate.identity("artifact", "other", "head")),
                            ("head", task_gate.identity("artifact", "config", "other"))):
            with self.subTest(field=label):
                self.assertFalse(task_gate.identity_matches(gate, live))


class ConfigIdentityTests(tp.ProjectTest):
    """The resolved profile (rules and limits included) is part of the gate identity (A-4p, process.py docstring)."""

    def resolved(self, document=None, rules=None):
        if rules is not None:
            (self.project / "AGENTS.md").write_text(rules)
        return process.resolve(process.validate_profile(document or {}), {}, self.project)

    def test_a_rules_change_or_a_limit_change_moves_the_configuration_digest(self):
        rules = (self.resolved({"rules": ["AGENTS.md"]}, "one\n"), self.resolved({"rules": ["AGENTS.md"]}, "two\n"))
        limits = (self.resolved({"limits": {"task_rounds": 2}}), self.resolved({"limits": {"task_rounds": 10}}))
        for one, two in (rules, limits):
            self.assertNotEqual(one.digest, two.digest)
            self.assertFalse(task_gate.identity_matches(task_gate.identity("a", one.digest, "h"),
                                                        task_gate.identity("a", two.digest, "h")))


if __name__ == "__main__":
    unittest.main()
