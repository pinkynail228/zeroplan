"""A7b merge critic core: the trigger rule, the durable record, the read-only graph and its run lifecycle.

Nothing here is reachable from a user action: the merge wiring (`gate_merge`, Delivery) is A7b2. Deterministic
fixtures and real temporary Git repositories only; no provider, no network. The native crash protocol is injected
through the scripted `NativeEngine` harness; the fixture driver produces the scripted verdict.

Interpretations (nothing in the parent text fixes them; kept here for the reviewers):
- `reasons` raises a path-less trigger only for a fact that is exactly `True` (p2c, owner decision F1); an omitted,
  `False` or any other value raises nothing, so a low-risk merge without facts needs no critic.
- The critic output is schemaVersion "1" with exactly `verdict` (go|block) and `findings`; the parent fixes the
  verdict names and that the parser reproduces them, not the output's field names.
- The identity's `input_digest` digests the semantic input the critic judges besides the pinned merge identity (the
  reasons, the changed paths and the milestone's briefs); its `risk` is exactly the `process.risk_of` shape
  {tier, triggers, unmatched}. `allows` compares the whole identity by `==` (no type-preserving trick is needed:
  every identity field has one JSON type).
- The graph's success terminals are `critic_go`/`critic_block` and its failure `critic_failed` (the parent names
  only the failure); the node keeps one session per execution (`sessionScope: execution`, as the plan critic).
- The critic's checkout is detached at the *candidate* (not the destination head) because the candidate commit is
  unreferenced in the project and reachable only by its SHA; `critic_prepare` reuses the task gate's clone/detach/
  verify shape (`checks._prepare`'s behaviour) without importing `checks` (test_checks pins its one caller).
- A run submitted from that detached checkout resolves no source upstream (`native_v2_local/source.rs`), so its
  watch projection omits `source` (or carries it as null). The observation accepts both forms and, when a source is
  present, still requires its revision to name the candidate; the candidate is otherwise pinned by the frozen
  checkout (`critic_prepare` verifies `HEAD` and `HEAD^{tree}`), never by the projection.
- The record is saved by its caller before `critic_run` (as `runs`/Delivery save a task gate before `gate_run`); a
  crash before that save is out of this core's scope.
"""

import copy
import json
import os
from pathlib import Path
import subprocess
import unittest

from terminal_planner import engine, merge_critic
from terminal_planner.authority import Authority as RealAuthority, Blocked, canonical
from terminal_planner.engine import FixtureEngine
from terminal_planner.setup import tool_paths
import test_process as tpr
import test_terminal_planner as tp
from test_terminal_planner import ROLES


def pinned_binary():
    """The installed pinned zeroshot binary, or None (the native admission skips)."""
    path = Path(os.environ.get("ZEROSHOT_TEST_BINARY") or tool_paths()[0])
    return path if path.is_file() else None


class CriticBase(tpr.ProfileTest):
    """A fixture session: an accepted profile and one approved M1 plan revision (plan revision 1)."""

    def reset(self):
        """A fresh state directory, so a test that wrote a malformed store starts from nothing."""
        import shutil
        shutil.rmtree(self.state, ignore_errors=True)
        self.state.mkdir(parents=True)

    def approved(self):
        self.approved_plan()

    def head(self):
        return self.git("rev-parse", "HEAD").decode().strip()

    def tree(self, commit):
        return self.git("rev-parse", commit + "^{tree}").decode().strip()

    def identity(self, **over):
        base = self.head()
        value = {"milestone": "M1", "plan_revision": 1, "attempt": 1, "destination": "refs/heads/main",
                 "base": base, "result": base, "candidate": base, "tree": self.tree(base),
                 "config_digest": "a" * 64, "input_digest": merge_critic.input_digest(["tier:high"], [], []),
                 "risk": {"tier": "medium", "triggers": [], "unmatched": []}}
        value.update(over)
        return value

    def documents(self, identity, reasons=("tier:high",), paths=(), briefs=()):
        roles = {"critic": {"model": "gpt-6.1-sol", "effort": "high"}}
        return engine.merge_critic_documents(roles, identity, list(reasons), list(paths), list(briefs))

    def build(self, identity=None, reasons=("tier:high",), binding=None, documents=None):
        identity = identity or self.identity(input_digest=merge_critic.input_digest(list(reasons), [], []))
        documents = documents or self.documents(identity, reasons=reasons)
        return merge_critic.record(identity, list(reasons), binding or {"fixture_id": "test"}, documents)

    def conclude(self, record, verdict="go", findings="No open findings."):
        record.update(run_id="fixture-critic", receipt={"runId": "fixture-critic"}, status="observing")
        merge_critic.concluded(record, {"status": "succeeded",
                                        "output": {"schemaVersion": "1", "verdict": verdict, "findings": findings}})
        return record

    def store(self, record):
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            authority.state.setdefault("critics", []).append(record)
            authority.save()

    def stored(self):
        """The store file and its parsed state, read back for an out-of-band mutation (the load-validation path)."""
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            return authority.path, copy.deepcopy(authority.state)

    def load(self):
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            return copy.deepcopy(authority.state["critics"])

    def assert_refused(self, family="store.invalid"):
        with self.assertRaises(Blocked) as raised:
            with RealAuthority(self.state, self.project, fixture_id="test"):
                pass
        self.assertEqual(raised.exception.family, family)

    def rejects(self, mutate):
        """Store a valid concluded critic, mutate its stored bytes, and assert the whole store is refused on load."""
        self.reset()
        self.approved()
        self.store(self.conclude(self.build(), verdict="block"))
        path, state = self.stored()
        mutate(state["critics"][0])
        path.write_text(canonical(state) + "\n", encoding="utf-8")
        self.assert_refused()


# C1 -------------------------------------------------------------------------------------------------------------

class ReasonsTests(unittest.TestCase):
    """`reasons(risk, facts)` -> the sorted trigger names of one merge (C1)."""

    def test_a_low_risk_merge_with_no_facts_raises_nothing(self):
        """p2c A1: no tier, no path trigger and no fact -> no reason, so no critic."""
        self.assertEqual(merge_critic.reasons({"tier": "low", "triggers": [], "unmatched": []}, {}), [])
        self.assertEqual(merge_critic.reasons({"tier": "medium", "triggers": [], "unmatched": []}, {}), [])

    def test_a_high_tier_adds_tier_high_and_path_triggers_are_kept(self):
        """p2c A2: `tier:high` and matched path triggers raise the critic, with or without facts."""
        self.assertEqual(merge_critic.reasons({"tier": "high", "triggers": ["installer"], "unmatched": []}, {}),
                         ["installer", "tier:high"])
        self.assertEqual(merge_critic.reasons({"tier": "low", "triggers": ["packaging"], "unmatched": []},
                                              {"disagreement": False}),
                         ["packaging"])

    def test_the_three_preset_triggers_are_the_path_less_ones(self):
        self.assertEqual(sorted(merge_critic.PRESET_TRIGGERS), ["data_loss", "disagreement", "process_kill"])

    def test_only_a_true_fact_raises_a_path_less_trigger(self):
        """p2c A2: an omitted or `False` fact raises nothing; exactly `True` raises its trigger (`0` is not `True`)."""
        for facts, expected in (({"data_loss": False}, []),
                                ({"data_loss": True}, ["data_loss"]),
                                ({"data_loss": True, "process_kill": True, "disagreement": False},
                                 ["data_loss", "process_kill"]),
                                ({}, []),
                                ({"process_kill": 0}, [])):
            with self.subTest(facts=facts):
                self.assertEqual(merge_critic.reasons({"tier": "low", "triggers": [], "unmatched": []}, facts),
                                 expected)


# C2 -------------------------------------------------------------------------------------------------------------

class RecordTests(CriticBase):
    """The durable critic record in `state["critics"]` and its strict validation on load (C2)."""

    def test_a_concluded_record_loads_with_all_its_frozen_fields(self):
        self.approved()
        record = self.conclude(self.build(reasons=("data_loss", "tier:high")), verdict="block", findings="risky path")
        self.store(record)
        loaded = self.load()
        self.assertEqual(len(loaded), 1)
        stored = loaded[0]
        self.assertEqual(stored["id"], record["id"])
        self.assertEqual(stored["verdict"], "block")
        self.assertEqual(stored["findings"], "risky path")
        self.assertEqual(stored["status"], "concluded")
        self.assertEqual(set(stored["identity"]), set(merge_critic.IDENTITY_FIELDS))
        self.assertEqual(stored["reasons"], ["data_loss", "tier:high"])
        self.assertEqual(stored["documents"], record["documents"])

    def test_the_parser_reproduces_the_verdict_and_the_findings(self):
        """A stored output that says `block` under a persisted verdict `go` refuses the store (the C2 example)."""
        self.rejects(lambda record: record.update(verdict="go"))
        self.rejects(lambda record: record.update(findings="another finding"))

    def test_each_malformation_is_refused(self):
        mutations = {
            "unknown key": lambda r: r.update(extra=1),
            "missing key": lambda r: r.pop("diagnostic"),
            "bad id": lambda r: r.update(id="critic-1"),
            "duplicate id": None,  # handled separately below
            "unsorted reasons": lambda r: r.update(reasons=["tier:high", "data_loss"]),
            "bad attempts": lambda r: r["identity"].update(attempt=0),
            "bad candidate": lambda r: r["identity"].update(candidate="not-a-sha"),
            "unknown milestone": lambda r: r["identity"].update(milestone="M9"),
            "bad risk tier": lambda r: r["identity"].update(risk={"tier": "huge", "triggers": [], "unmatched": []}),
            "native binding in a fixture store": lambda r: r.update(binding={"executable": "/x"}),
            "missing document": lambda r: r["documents"].pop("runtime"),
            "bad submission key": lambda r: r.update(submission_key="nope"),
            "verdict on a non-concluded status": lambda r: r.update(status="detached", verdict="go", findings="f",
                                                                    terminal=None),
        }
        for label, mutate in mutations.items():
            if mutate is None:
                continue
            with self.subTest(case=label):
                self.rejects(mutate)

    def test_a_record_refuses_documents_that_describe_another_input(self):
        """critic a7b-merge P1: the frozen input must judge exactly the record's identity, reasons and digested
        paths/briefs, so a `go` on one candidate's input can never allow another identity."""
        identity = self.identity()
        other = self.identity(candidate="c" * 40)
        cases = {"other identity": (identity, ["tier:high"], self.documents(other)),
                 "other reasons": (identity, ["secrets"], self.documents(identity)),
                 "other paths": (identity, ["tier:high"], self.documents(identity, paths=["a.py"])),
                 "other briefs": (identity, ["tier:high"], self.documents(identity, briefs=[{"id": "T9"}]))}
        for name, (value, names, documents) in cases.items():
            with self.subTest(name), self.assertRaises(Blocked) as raised:
                merge_critic.record(value, names, {"fixture_id": "test"}, documents)
            self.assertEqual(raised.exception.family, "engine.intent_changed")
        self.assertEqual(merge_critic.record(identity, ["tier:high"], {"fixture_id": "test"},
                                             self.documents(identity))["identity"], identity)

    def test_a_duplicate_id_is_refused(self):
        self.approved()
        first, second = self.conclude(self.build()), self.conclude(self.build())
        second["id"] = first["id"]
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            authority.state.setdefault("critics", []).append(first)
            authority.save()
            path = authority.path
        state = json.loads(path.read_text())
        state["critics"].append(second)
        path.write_text(json.dumps(state) + "\n", encoding="utf-8")
        self.assert_refused()

    def test_a_store_without_critics_still_loads(self):
        self.approved()
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            self.assertNotIn("critics", authority.state)


# C3 -------------------------------------------------------------------------------------------------------------

def nodes(root):
    found, pending = [], [root]
    while pending:
        node = pending.pop()
        found.append(node)
        for child in node.get("children", []):
            pending.append(child)
        if "otherwise" in node:
            pending.append(node["otherwise"])
        for branch in node.get("branches", []):
            pending.append(branch["node"])
    return found


def entry(graph, name):
    return next(node for node in nodes(graph["root"]) if node["name"] == name)


class GraphTests(unittest.TestCase):
    """The merge-critic graph, runtime and input: one read-only verifier (C3)."""

    def test_one_verifier_node_judges_the_identity_with_a_go_block_signal(self):
        graph = engine.merge_critic_graph()
        critic = entry(graph, "critic")
        self.assertEqual(critic["kind"], "verifier")
        self.assertEqual(critic["attempts"], 1)
        self.assertEqual(set(critic["input"]["fields"]), {"identity", "reasons", "paths", "briefs"})
        self.assertEqual(set(critic["signals"]), {"verdict"})
        self.assertEqual(critic["signals"]["verdict"], ["go", "block"])
        self.assertNotIn("ZPLAN_NODE", critic["instructions"])  # H1: the qualification adds its marker
        self.assertEqual([b["value"]["channel"] for b in critic["writeBindings"]], ["signal", "diagnostic"])
        self.assertEqual([b["target"] for b in critic["writeBindings"]], [["verdict"], ["findings"]])
        self.assertEqual([n["name"] for n in nodes(graph["root"]) if n["kind"] == "fail"], ["critic_failed"])
        self.assertEqual(sorted(n["name"] for n in nodes(graph["root"]) if n["kind"] == "succeed"),
                         ["critic_block", "critic_go"])
        guards = entry(graph, "critic_result")["branches"]
        self.assertEqual([g["when"]["labels"] for g in guards],
                         [["timeout", "crash", "malformed", "refusal"], ["go"], ["block"]])

    def test_the_runtime_binds_the_plan_verifier_role_in_an_execution_session(self):
        runtime = engine.merge_critic_runtime({"critic": {"model": "gpt-6.1-sol", "effort": "high"}})
        self.assertEqual(set(runtime["nodes"]), {"critic"})
        self.assertEqual(runtime["size"], "medium")
        self.assertEqual(runtime["nodes"]["critic"]["sessionScope"], "execution")
        self.assertEqual(runtime["nodes"]["critic"]["model"], "gpt-6.1-sol")

    def test_the_input_carries_the_identity_and_defaults_to_block(self):
        identity = {"milestone": "M1", "candidate": "c" * 40}
        document = engine.merge_critic_input(identity, ["tier:high"], ["a.py"], [{"id": "T1"}])
        self.assertEqual(document["schemaVersion"], "1")
        self.assertEqual(json.loads(document["identity"]), identity)
        self.assertEqual(json.loads(document["reasons"]), ["tier:high"])
        self.assertEqual(json.loads(document["paths"]), ["a.py"])
        self.assertEqual(json.loads(document["briefs"]), [{"id": "T1"}])
        self.assertEqual(document["verdict"], "block")
        documents = engine.merge_critic_documents({"critic": {"model": "m", "effort": "high"}}, identity, ["r"], [],
                                                  [])
        self.assertEqual(set(documents), set(merge_critic.DOCUMENTS))


@unittest.skipUnless(pinned_binary(), "pinned zeroshot binary absent (set ZEROSHOT_TEST_BINARY)")
class AdmissionTests(unittest.TestCase):
    """The frozen merge-critic documents pass the pinned native admission (validate-only: no provider, no run)."""

    def test_the_merge_critic_documents_pass_native_admission(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            for args in (["init", "-q", "-b", "main"], ["commit", "-q", "--allow-empty", "-m", "fixture"]):
                subprocess.run(["git", "-C", str(project), "-c", "user.name=t", "-c", "user.email=t@localhost", *args],
                               check=True, capture_output=True)
            identity = {"milestone": "M1", "plan_revision": 1, "attempt": 1, "destination": "refs/heads/main",
                        "base": "0" * 40, "result": "0" * 40, "candidate": "0" * 40, "tree": "0" * 40,
                        "config_digest": "a" * 64, "input_digest": "b" * 64,
                        "risk": {"tier": "high", "triggers": [], "unmatched": []}}
            documents = engine.merge_critic_documents({"critic": {"model": "gpt-6.1-sol", "effort": "high"}},
                                                      identity, ["tier:high"], ["a.py"], [{"id": "T1"}])
            for kind, value in documents.items():
                (root / (kind + ".json")).write_text(json.dumps(value))
            result = subprocess.run([str(pinned_binary()), "run", "--title", "zplan merge critic admission",
                                     "--graph", str(root / "graph.json"), "--runtime-config", str(root / "runtime.json"),
                                     "--input", str(root / "input.json"), "--no-environment", "--validate-only"],
                                    cwd=project, env=dict(os.environ, ZEROSHOT_STATE_DIR=str(root / "state")),
                                    capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stderr[-2000:])
            self.assertIs(json.loads(result.stdout)["valid"], True)


# C4 -------------------------------------------------------------------------------------------------------------

class FixtureRunTests(CriticBase):
    """The fixture driver scripts the critic's verdict (C4)."""

    def run_fixture(self, **options):
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            record = self.build()
            authority.state.setdefault("critics", []).append(record)
            authority.save()
            FixtureEngine(**options).critic_run(authority, record, {}, lambda _: None)
            return record

    def test_the_fixture_driver_scripts_the_verdict(self):
        self.approved()
        self.assertEqual(self.run_fixture()["status"], "concluded")
        self.assertEqual(self.run_fixture()["verdict"], "go")
        blocked = self.run_fixture(terminal_output={"schemaVersion": "1", "verdict": "block", "findings": "risky"})
        self.assertEqual((blocked["status"], blocked["verdict"], blocked["findings"]),
                         ("concluded", "block", "risky"))

    def test_a_native_failure_is_not_a_block(self):
        self.approved()
        failed = self.run_fixture(failure="boom")
        self.assertEqual((failed["status"], failed["verdict"]), ("native_failed", None))


def critic_terminal(candidate, verdict="go", findings="No open findings.", run_id="critic-run", failed=False):
    """The finished projection of one merge-critic run as the pinned native run emits it: its own title, size and
    verdict, but *no* `source`. The critic's checkout is detached at the unreferenced candidate, so the native run
    resolves no source (`native_v2_local/source.rs`) and omits the field entirely; a test that wants the other forms
    adds one itself (`{**critic_terminal(c), "source": None}` or a dict)."""
    output = {"schemaVersion": "1", "verdict": verdict, "findings": findings}
    terminal = ({"status": "failed", "reason": "critic_failed"} if failed
                else {"status": "succeeded", "output": output})
    return {"runId": run_id, "subscriptionId": "fixture-subscription",
            "title": merge_critic.submitted_title(candidate), "size": "medium", "cursor": "v2:10",
            "status": {"phase": "finished", "terminalResult": terminal}}


class ScriptedEngine:
    """`tp.NativeTests.engine`'s scripted binary for a merge critic: its own dictionary of calls and dispatches."""

    def __init__(self, test, responses):
        self.engine, self.calls = tp.NativeTests.engine(test, responses)

    def dispatched(self):
        return [argv for argv, _ in self.calls if argv[1] == "run" and "--detach" in argv]


class NativeRunTests(CriticBase):
    """The critic's native lifecycle: the crash boundaries and the read-only candidate checkout (C4)."""

    native = tp.NativeTests.native
    projection = tp.NativeTests.projection

    def setUp(self):
        super().setUp()
        self.approved_native_plan()

    def approved_native_plan(self):
        plan_engine, _ = tp.NativeTests.engine(self, [{"valid": True}, {"runId": "fixture-native-run"},
                                                      tp.NativeTests.terminal(self)])
        with tp.NativeTests.authority(self) as authority:
            authority.begin("Requested feature", ROLES, "native")
            plan_engine.proposal(authority, lambda _: None)
            authority.approve(1)

    def candidate_commit(self):
        """A real commit that main is then reset away from, so the candidate is unreferenced in the project."""
        base = self.head()
        (self.project / "source.txt").write_text("candidate\n")
        self.git("add", "source.txt")
        self.git("commit", "-qm", "candidate")
        candidate, tree = self.head(), self.tree("HEAD")
        self.git("reset", "--hard", "-q", base)
        return candidate, tree

    def native_identity(self, candidate, tree):
        return {"milestone": "M1", "plan_revision": 1, "attempt": 1, "destination": "refs/heads/main",
                "base": self.head(), "result": candidate, "candidate": candidate, "tree": tree,
                "config_digest": "a" * 64,
                "input_digest": merge_critic.input_digest(["tier:high"], ["source.txt"], [{"id": "T1"}]),
                "risk": {"tier": "high", "triggers": [], "unmatched": []}}

    def native_record(self, authority, scripted, candidate, tree):
        """A native critic record (with `scripted`'s own binding) already durable in `authority`."""
        identity = self.native_identity(candidate, tree)
        documents = engine.merge_critic_documents({"critic": {"model": "gpt-6.1-sol", "effort": "high"}}, identity,
                                                  ["tier:high"], ["source.txt"], [{"id": "T1"}])
        record = merge_critic.record(identity, ["tier:high"], scripted.engine.critic_binding(authority), documents)
        authority.state.setdefault("critics", []).append(record)
        authority.save()
        return record, documents

    def test_a_crash_after_the_receipt_observes_the_same_run_without_resubmitting(self):
        candidate, tree = self.candidate_commit()
        with tp.NativeTests.authority(self) as authority:
            scripted = ScriptedEngine(self, [{"valid": True}, {"runId": "critic-run"}, KeyboardInterrupt()])
            record, documents = self.native_record(authority, scripted, candidate, tree)
            with self.assertRaises(KeyboardInterrupt):
                scripted.engine.critic_run(authority, record, documents, lambda _: None)
        with tp.NativeTests.authority(self) as authority:
            parked = copy.deepcopy(authority.state["critics"][0])
            self.assertEqual((parked["status"], parked["run_id"], parked["receipt"]),
                             ("detached", "critic-run", {"runId": "critic-run"}))
            restart = ScriptedEngine(self, [critic_terminal(candidate)])
            result = restart.engine.critic_run(authority, authority.state["critics"][0], None, lambda _: None)
            self.assertEqual((result["id"], result["run_id"], result["status"]),
                             (parked["id"], "critic-run", "concluded"))
            self.assertEqual(result["verdict"], "go")
            self.assertEqual([argv[1] for argv, _ in restart.calls], ["watch"])
            self.assertEqual(len(scripted.dispatched() + restart.dispatched()), 1)

    def test_a_crash_before_the_receipt_refuses_and_never_dispatches_again(self):
        candidate, tree = self.candidate_commit()
        with tp.NativeTests.authority(self) as authority:
            scripted = ScriptedEngine(self, [{"valid": True}, KeyboardInterrupt()])
            record, documents = self.native_record(authority, scripted, candidate, tree)
            with self.assertRaises(KeyboardInterrupt):
                scripted.engine.critic_run(authority, record, documents, lambda _: None)
            self.assertEqual(len(scripted.dispatched()), 1)
        with tp.NativeTests.authority(self) as authority:
            parked = copy.deepcopy(authority.state["critics"][0])
            self.assertEqual((parked["status"], parked["run_id"], parked["receipt"]),
                             ("submission_unknown", None, None))
            restart = ScriptedEngine(self, [critic_terminal(candidate)])
            with self.assertRaises(Blocked) as raised:
                restart.engine.critic_run(authority, authority.state["critics"][0], None, lambda _: None)
            self.assertEqual(raised.exception.family, "submission.unknown")
            self.assertEqual(restart.calls, [])

    def test_the_checkout_is_detached_at_the_candidate_with_its_tree_verified(self):
        candidate, tree = self.candidate_commit()
        with tp.NativeTests.authority(self) as authority:
            scripted = ScriptedEngine(self, [{"valid": True}, {"runId": "critic-run"}, critic_terminal(candidate)])
            record, documents = self.native_record(authority, scripted, candidate, tree)
            scripted.engine.critic_run(authority, record, documents, lambda _: None)
            self.assertEqual((record["status"], record["verdict"]), ("concluded", "go"))
            checkout = authority.directory / "critics" / record["id"] / "checkout"
            for revision in ("HEAD", "HEAD^{tree}"):
                self.assertEqual(subprocess.run(["git", "-C", str(checkout), "rev-parse", revision],
                                                capture_output=True, text=True).stdout.strip(),
                                 candidate if revision == "HEAD" else tree)
            # The candidate is unreferenced in the project: only the clone's copied object makes the detach possible.
            reachable = subprocess.run(["git", "-C", str(self.project), "merge-base", "--is-ancestor", candidate, "main"],
                                       capture_output=True)
            self.assertNotEqual(reachable.returncode, 0)

    def test_a_source_free_native_projection_concludes_the_critic(self):
        """Regression (C4): the detached candidate leaves the native run no source, so its finished projection omits
        `source`; the observation still concludes the record from the frozen checkout and the intent, never the source."""
        candidate, tree = self.candidate_commit()
        projection = critic_terminal(candidate)
        self.assertNotIn("source", projection)
        with tp.NativeTests.authority(self) as authority:
            scripted = ScriptedEngine(self, [{"valid": True}, {"runId": "critic-run"}, projection])
            record, documents = self.native_record(authority, scripted, candidate, tree)
            scripted.engine.critic_run(authority, record, documents, lambda _: None)
            self.assertEqual((record["status"], record["verdict"]), ("concluded", "go"))

    def test_a_null_source_projection_also_concludes_the_critic(self):
        """The other form of the same native contract (`source: null`) is accepted too."""
        candidate, tree = self.candidate_commit()
        projection = {**critic_terminal(candidate), "source": None}
        with tp.NativeTests.authority(self) as authority:
            scripted = ScriptedEngine(self, [{"valid": True}, {"runId": "critic-run"}, projection])
            record, documents = self.native_record(authority, scripted, candidate, tree)
            scripted.engine.critic_run(authority, record, documents, lambda _: None)
            self.assertEqual((record["status"], record["verdict"]), ("concluded", "go"))

    def test_recovery_observes_the_source_free_run_without_resubmitting(self):
        """Regression (C4): a crash after the receipt is durable, and the recovering call observes the recorded run
        whose projection carries no source -- one dispatch only, no resend."""
        candidate, tree = self.candidate_commit()
        with tp.NativeTests.authority(self) as authority:
            scripted = ScriptedEngine(self, [{"valid": True}, {"runId": "critic-run"}, KeyboardInterrupt()])
            record, documents = self.native_record(authority, scripted, candidate, tree)
            with self.assertRaises(KeyboardInterrupt):
                scripted.engine.critic_run(authority, record, documents, lambda _: None)
        with tp.NativeTests.authority(self) as authority:
            restart = ScriptedEngine(self, [critic_terminal(candidate)])
            result = restart.engine.critic_run(authority, authority.state["critics"][0], None, lambda _: None)
            self.assertEqual((result["status"], result["verdict"]), ("concluded", "go"))
            self.assertEqual([argv[1] for argv, _ in restart.calls], ["watch"])
            self.assertEqual(len(scripted.dispatched() + restart.dispatched()), 1)

    def test_a_present_source_of_another_revision_is_still_refused(self):
        """When the projection does carry a source it must still name the candidate, so a foreign source is refused."""
        candidate, tree = self.candidate_commit()
        projection = {**critic_terminal(candidate),
                      "source": {"repository": "example/fixture", "branch": "main", "revision": "f" * 40}}
        with tp.NativeTests.authority(self) as authority:
            scripted = ScriptedEngine(self, [{"valid": True}, {"runId": "critic-run"}, projection])
            record, documents = self.native_record(authority, scripted, candidate, tree)
            with self.assertRaises(Blocked) as raised:
                scripted.engine.critic_run(authority, record, documents, lambda _: None)
            self.assertEqual(raised.exception.family, "engine.intent_changed")

    def test_a_wrong_tree_refuses_the_checkout(self):
        candidate, tree = self.candidate_commit()
        with tp.NativeTests.authority(self) as authority:
            scripted = ScriptedEngine(self, [])
            identity = self.native_identity(candidate, "f" * 40)
            documents = engine.merge_critic_documents({"critic": {"model": "m", "effort": "high"}}, identity,
                                                      ["tier:high"], ["source.txt"], [{"id": "T1"}])
            record = merge_critic.record(identity, ["tier:high"], scripted.engine.critic_binding(authority), documents)
            authority.state.setdefault("critics", []).append(record)
            authority.save()
            with self.assertRaises(Blocked) as raised:
                scripted.engine.critic_prepare(authority, record, documents)
            self.assertEqual(raised.exception.family, "engine.checkout")


# C5 -------------------------------------------------------------------------------------------------------------

class AllowsTests(CriticBase):
    """`allows` only for a `go` and the exact identity (C5)."""

    def test_only_a_go_with_the_same_identity_allows(self):
        self.approved()
        identity = self.identity()
        record = self.conclude(self.build(identity=identity), verdict="go")
        self.assertTrue(merge_critic.allows(record, copy.deepcopy(identity)))
        for label, other in (("candidate", self.identity(candidate="c" * 40)),
                             ("tree", self.identity(tree="d" * 40)),
                             ("config", self.identity(config_digest="e" * 64)),
                             ("risk", self.identity(risk={"tier": "high", "triggers": [], "unmatched": []})),
                             ("attempt", self.identity(attempt=2))):
            with self.subTest(field=label):
                self.assertFalse(merge_critic.allows(record, other))

    def test_a_block_or_no_verdict_never_allows(self):
        self.approved()
        identity = self.identity()
        self.assertFalse(merge_critic.allows(self.conclude(self.build(identity=identity), verdict="block"), identity))
        self.assertFalse(merge_critic.allows(self.build(identity=identity), identity))  # no verdict yet

    def test_an_errored_record_never_allows(self):
        self.approved()
        identity = self.identity()
        record = self.build(identity=identity)
        record.update(run_id="fixture-critic", receipt={"runId": "fixture-critic"}, status="observing")
        merge_critic.concluded(record, {"status": "failed", "reason": "critic_failed"})
        self.assertFalse(merge_critic.allows(record, identity))


class ParserTests(unittest.TestCase):
    """The critic output parser at its own boundary (C2)."""

    def refused(self, output):
        with self.assertRaises(Blocked) as raised:
            merge_critic.read_verdict(output)
        self.assertEqual(raised.exception.family, "store.invalid")

    def test_a_well_formed_output_parses_and_every_other_shape_is_refused(self):
        self.assertEqual(merge_critic.read_verdict({"schemaVersion": "1", "verdict": "go", "findings": "ok"}),
                         ("go", "ok"))
        for label, output in (("not a dict", "go"),
                              ("wrong version", {"schemaVersion": "2", "verdict": "go", "findings": "ok"}),
                              ("extra field", {"schemaVersion": "1", "verdict": "go", "findings": "ok", "x": 1}),
                              ("bad verdict", {"schemaVersion": "1", "verdict": "maybe", "findings": "ok"}),
                              ("non-string findings", {"schemaVersion": "1", "verdict": "go", "findings": 1})):
            with self.subTest(case=label):
                self.refused(output)

    def test_the_stored_output_is_what_validate_reads(self):
        self.assertTrue(callable(merge_critic.parse_evidence))
        self.assertEqual(merge_critic.parse_evidence(
            {"terminal": {"status": "succeeded", "output": {"schemaVersion": "1", "verdict": "block", "findings": "f"}}}),
            ("block", "f"))


if __name__ == "__main__":
    unittest.main()
