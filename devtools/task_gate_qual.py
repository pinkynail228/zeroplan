"""Native qualification of the task gate (orchestrator, Linux test host).

Drives the production `Delivery.run_task_gate` (a NativeEngine over a gate record) against the pinned native binary
and a scripted synthetic Responses provider on loopback. The approved plan revision the gate needs is made first by
the same provider over the plan graph (`plan_qual.PlanProvider`); the task-gate graph (proposer, critic) then runs
and the stored record is checked. Answers are scripted per node (the last `ZPLAN_NODE=<name>` marker in the request)
and validated against that request's output schema; no model is called. The gate is driven with a bounded watch
slice (`delivery.run_task_gate("M1", slice=10)`), exactly as the plan qualification drives its own graph: a slice
that ends while the gate still runs is resumed, never a failed scenario, until the terminal state or the deadline.
The task critic must keep one conversation across the rounds (`sessionScope: node_instance`): its round-2 request
has to carry its round-1 answer.

Scenarios: a_accept_r1, b_reject_accept_r2, c_dispute_accepted, d_exhausted (task_rounds 2), e_critic_error,
f_proposer_error, g_malformed_discussion (output_invalid, no evidence), h_continuity.

    PYTHONPATH=. python3 devtools/task_gate_qual.py --binary "$ZEROSHOT_TEST_BINARY" [SCENARIO ...]
    devtools/linux-test.sh --py devtools/task_gate_qual.py
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devtools import driver_qual as dq  # noqa: E402
from devtools import plan_qual as pq  # noqa: E402
from terminal_planner.authority import Authority, Blocked, canonical  # noqa: E402
from terminal_planner.delivery import Delivery  # noqa: E402
from terminal_planner.engine import NativeEngine, SliceEnded  # noqa: E402
from terminal_planner.process import PROFILE_FILE, Profile  # noqa: E402
from terminal_planner.runs import MilestoneRuns  # noqa: E402
from terminal_planner.setup import default_roles, tool_paths  # noqa: E402

TASK_NODES = ("proposer", "critic")


class StandIn:
    """The two attributes `Delivery.run_task_gate` reads from its `planning`: a profile and an engine factory."""

    def __init__(self, profile, engine):
        self.profile, self.engine_factory, self.terminal = profile, (lambda *_: engine), None


class TaskProvider:
    """Scripted proposer and task critic on the task-gate schema (plan nodes: `pq.PlanProvider`).

    `script` lists the critic's rounds as (verdict, findings, response); the proposer answers the round's response
    text. The critic reports the cumulative discussion in its output, as its instructions say. `broken` nodes get a
    schema-violating answer (they fail natively); `discussion` (callable: rounds -> text) replaces the report."""

    continued = pq.PlanProvider.continued

    def __init__(self, script, broken=(), discussion=None):
        self.script, self.broken, self.discussion = list(script), set(broken), discussion
        self.calls, self.errors, self.problems, self.lock = [], [], [], threading.Lock()
        self.tokens, self.reported, self.answered = {n: [] for n in TASK_NODES}, [], None

    def answer(self, request):
        return self.scripted(request)

    def scripted(self, request):
        markers = dq.MARKER.findall(json.dumps(request))
        node = markers[-1] if markers else "?"
        if node not in TASK_NODES:
            raise dq.QualError("unexpected node %s" % node)
        schema = request.get("text", {}).get("format", {}).get("schema")
        # Both gate nodes are `verifier`s: their response is {output, signals, diagnostic} and `output` the record.
        contract = (schema.get("properties", {}).get("response", {}).get("properties", {}).get("output", {})
                    .get("properties")) if isinstance(schema, dict) else None
        if not isinstance(contract, dict):
            raise dq.QualError("%s: request has no output schema" % node)
        count = self.calls.count(node) + 1
        if node in self.broken:
            self.calls.append(node)
            return pq.Tagged()  # {} violates the contract: a native `malformed` error of the node
        if not self.continued(node, request):
            self.problems.append("%s call #%s did not continue its own conversation" % (node, count))
        if count > len(self.script):
            raise dq.QualError("%s: unexpected call #%s" % (node, count))
        verdict, findings, response = self.script[count - 1]
        token = "%s-%s-%s" % (node[0], count, uuid.uuid4().hex[:8])
        if node == "proposer":
            if set(contract) != {"taskResponse"}:
                raise dq.QualError("proposer: output contract is not {taskResponse}")
            self.answered = "%s [%s]" % (response, token)
            answer = {"output": {"taskResponse": self.answered}, "signals": {"verdict": verdict},
                      "diagnostic": {"message": "proposed %s" % verdict}}
        else:
            if set(contract) != {"discussion"}:
                raise dq.QualError("critic: output contract is not {discussion}")
            text = "%s [%s]" % (findings, token)
            self.reported.append({"round": count, "verdict": verdict, "findings": text, "response": self.answered})
            reported = self.discussion(self.reported) if self.discussion else canonical(
                {"version": 1, "rounds": self.reported})
            answer = {"output": {"discussion": reported}, "signals": {"verdict": verdict},
                      "diagnostic": {"message": text}}
        if not dq.valid(schema, {"response": answer}):
            raise dq.QualError("%s: scripted answer #%s violates the request schema" % (node, count))
        ident = "qual-%s-%s-%s" % (node, count, uuid.uuid4().hex[:6])
        self.tokens[node].append((token, ident))
        self.calls.append(node)
        tagged = pq.Tagged(answer)
        tagged.response_id = ident
        return tagged


class Both:
    """The task provider for gate requests, the plan provider for the plan graph the approval needs (one server)."""

    def __init__(self, plan, task):
        self.plan, self.task = plan, task
        self.errors, self.lock = [], threading.Lock()

    def answer(self, request):
        return self.task.answer(request) if "taskResponse" in json.dumps(request) else self.plan.answer(request)


def rounds(*verdicts):
    return [(verdict, "F%d %s" % (n, verdict), "reply %d" % n) for n, verdict in enumerate(verdicts, 1)]


def bad_last_round(reported):
    """A discussion whose last round says something else than the signalled result."""
    changed = [dict(item) for item in reported]
    changed[-1]["response"] = "a response the proposer never gave"
    return canonical({"version": 1, "rounds": changed})


ORDER = ["proposer", "critic"]
OK = {"status": "concluded", "critic_verdict": "accepted"}
FAIL = {"status": "native_failed", "terminal_status": "failed", "critic_verdict": None}
# `rounds`: frozen task_rounds; `order`: gate node calls; `expect`: the stored record's fields.
SCENARIOS = {
    "a_accept_r1": dict(rounds=2, script=rounds("accepted"), order=ORDER, expect={**OK, "rounds_used": 1}),
    "b_reject_accept_r2": dict(rounds=2, script=rounds("rejected", "accepted"), order=ORDER * 2,
                               expect={**OK, "rounds_used": 2}),
    "c_dispute_accepted": dict(rounds=2, order=ORDER * 2, expect={**OK, "rounds_used": 2},
                               script=[("rejected", "F1 the task names no verifiable check", "reply 1"),
                                       ("accepted", "dispute accepted: the check is the milestone's own",
                                        "F1 disputed: the briefs cannot carry a per-task check")]),
    "d_exhausted": dict(rounds=2, script=rounds("rejected", "rejected"), order=ORDER * 2,
                        expect={"status": "concluded", "critic_verdict": "rejected", "rounds_used": 2}),
    "e_critic_error": dict(rounds=2, script=rounds("accepted"), broken=["critic"], order=ORDER, expect=FAIL),
    "f_proposer_error": dict(rounds=2, script=rounds("accepted"), broken=["proposer"], order=["proposer"], expect=FAIL),
    "g_malformed_discussion": dict(rounds=2, script=rounds("accepted"), discussion=bad_last_round, order=ORDER,
                                   expect={"status": "output_invalid", "critic_verdict": None, "rounds_used": None}),
    "h_continuity": dict(rounds=2, script=rounds("rejected", "accepted"), order=ORDER * 2,
                         expect={**OK, "rounds_used": 2}, continuity=2),
}


def check(scenario, both, record, blocked):
    """Failures as short strings; empty when the scenario passed."""
    problems = list(both.errors + both.plan.errors + both.plan.problems + both.task.errors + both.task.problems)
    calls = list(both.task.calls)
    # Native retries a failed provider turn once, so a broken node may be called twice; nothing may follow it.
    while len(calls) > len(scenario["order"]) and calls[-1] == calls[-2] == scenario["order"][-1]:
        calls.pop()
    if calls != scenario["order"]:
        problems.append("node calls %s != %s" % (calls, scenario["order"]))
    if blocked is not None:
        return problems + ["unexpected refusal: %s" % blocked]
    if record is None:
        return problems + ["no stored gate record"]
    seen = {"status": record["status"], "critic_verdict": record["critic_verdict"], "rounds_used": record["rounds_used"],
            "terminal_status": (record["terminal"] or {}).get("status")}
    problems += ["%s: %s != %s" % (key, seen.get(key), value) for key, value in scenario["expect"].items()
                 if seen.get(key) != value]
    if record["status"] == "output_invalid" and (record["discussion"] is not None or record["critic_verdict"] is not None):
        problems.append("output_invalid stored evidence")
    if scenario.get("continuity") and len(both.task.tokens["critic"]) != scenario["continuity"]:
        problems.append("the critic did not answer %s rounds in one conversation" % scenario["continuity"])
    return problems


def run_scenario(name, scenario, binary, root, timeout, version=None):
    work = root / name.split("_")[0]  # short: the controller socket lives under the state dir
    plan = pq.PlanProvider([("accepted", "fixture plan accepted", "plan accepted")])
    task = TaskProvider(scenario["script"], scenario.get("broken", ()), scenario.get("discussion"))
    both = Both(plan, task)
    project, env, server = dq.setup_work(work, binary, both)
    state = (work / "s").resolve()
    home = os.environ.get("HOME")
    os.environ["HOME"] = env["HOME"]  # the production authority and lock roots follow HOME
    deadline = time.monotonic() + timeout
    problems, blocked, record = [], None, None
    try:
        with Authority(None, project) as authority:
            with (project / ".git/info/exclude").open("a", encoding="utf-8") as handle:
                handle.write("\n%s\n" % PROFILE_FILE)
            (project / PROFILE_FILE).write_text(json.dumps({"gates": {"task": "required"},
                                                            "limits": {"task_rounds": scenario["rounds"]}}))
            profile = Profile.of(authority)
            profile.accept()
            authority.profile = profile
            authority.begin("Qualify the task gate", default_roles(), "native")
            engine = NativeEngine(binary, state, environment=env, version=version)
            while True:  # approve the plan revision the gate needs, over the plan graph
                try:
                    engine.proposal(authority, lambda _: None, slice=10)
                    break
                except SliceEnded:
                    if time.monotonic() > deadline:
                        raise dq.QualError("plan approval timed out; plan calls %s" % plan.calls[-6:])
            authority.approve(1)
            runs = MilestoneRuns(authority, None, authority.directory / "worktrees")
            delivery = Delivery(authority, runs, StandIn(profile, engine))
            try:
                while True:
                    try:
                        record = delivery.run_task_gate("M1", slice=10)
                        break
                    except SliceEnded:  # a bounded observation slice ended: observe on until the deadline
                        if time.monotonic() > deadline:
                            raise dq.QualError("task gate timed out; gate calls %s" % both.task.calls[-6:])
                    except Blocked as error:
                        blocked = str(error)
                        break
            finally:
                problems = check(scenario, both, record, blocked)
    except Exception as error:  # every failure is a scenario result, not a harness crash
        problems = ["%s: %s" % (type(error).__name__, str(error)[:400])]
    finally:
        dq.terminate(None, state / "runs")
        server.shutdown()
        server.server_close()
        if home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = home
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("scenarios", nargs="*", help="default: all of %s" % ", ".join(sorted(SCENARIOS)))
    parser.add_argument("--binary", default=os.environ.get("ZEROSHOT_TEST_BINARY") or str(tool_paths()[0]))
    parser.add_argument("--zeroshot-version", help="X.Y.Z the binary prints for --version")
    parser.add_argument("--timeout", type=int, default=0, help="per-scenario seconds (default: by rounds)")
    parser.add_argument("--keep", action="store_true", help="keep the scratch directory")
    args = parser.parse_args(argv)
    names = args.scenarios or sorted(SCENARIOS)
    version = "zeroshot " + args.zeroshot_version if args.zeroshot_version else None
    if set(names) - set(SCENARIOS):
        parser.error("unknown scenarios: %s" % ", ".join(sorted(set(names) - set(SCENARIOS))))
    if not Path(args.binary).is_file() or not tool_paths(Path(args.binary).resolve().parent)[1].is_file():
        print("SKIP: pinned zeroshot/codex not found next to %s" % args.binary)
        return 2
    pq.install()
    root = Path(tempfile.mkdtemp(prefix="zq-", dir="/tmp")).resolve()
    failed = 0
    try:
        for name in names:
            started = time.monotonic()
            scenario = SCENARIOS[name]
            problems = run_scenario(name, scenario, args.binary, root,
                                    args.timeout or 240 + 90 * scenario["rounds"], version)
            failed += bool(problems)
            print("%s %s (%ss)%s" % ("FAIL" if problems else "PASS", name, int(time.monotonic() - started),
                                     "".join("\n  - " + p for p in problems)), flush=True)
    finally:
        if args.keep:
            print("scratch kept: %s" % root)
        else:
            shutil.rmtree(root, ignore_errors=True)
    print("%s/%s scenarios passed" % (len(names) - failed, len(names)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
