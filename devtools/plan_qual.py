"""Native qualification of the argued plan gate (orchestrator, Linux test host).

Runs the production planner adapter (NativeEngine over an Authority revision of planner graph 2) against the pinned
native binary and a scripted synthetic Responses provider on loopback. Answers are scripted per node (dispatch by
the last `ZPLAN_NODE=<name>` marker in the request) and validated against that request's output schema; nothing
calls a real provider. This proves the graph's control flow, the critic's one-conversation continuity and the
adapter boundary, not model behaviour.

Scenarios: a_accept_r1, b_reject_repair_accept, c_dispute_accepted, d_exhausted (2 frozen rounds), e_critic_error
(native `critic_failed`), f_planner_error (`planner_failed`), g_malformed_discussion (adapter refuses; no evidence).
Every later call of a node must carry that node's earlier answer as an assistant turn of its transport conversation (or
the previous response id): a critic switched to `sessionScope: execution` starts a fresh conversation and fails.

    PYTHONPATH=. python3 devtools/plan_qual.py --binary "$ZEROSHOT_TEST_BINARY" [SCENARIO ...]
    devtools/linux-test.sh --py devtools/plan_qual.py
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devtools import driver_qual as dq  # noqa: E402
from terminal_planner.authority import Authority, Blocked, canonical, digest  # noqa: E402
from terminal_planner.engine import NativeEngine, SliceEnded, fixture_proposal  # noqa: E402
from terminal_planner.setup import default_roles, tool_paths  # noqa: E402

NODES = ("planner", "critic")


class Tagged(dict):
    """A response that remembers the transport id it is sent under."""
    response_id = "qual-response"


def tagged_events(response, events=dq.events):
    """The driver qualification's SSE events, under this answer's own response id."""
    ident = getattr(response, "response_id", "qual-response")
    found = events(response)
    for event in found:
        if event["type"] in ("response.created", "response.completed"):
            event["response"]["id"] = ident
    return found


def install():
    """Serve per-answer response ids through driver_qual's loopback server (idempotent)."""
    if dq.events is not tagged_events:
        dq.events = tagged_events


class PlanProvider:
    """Scripted planner and critic.

    `script` lists the critic's rounds as (verdict, findings, response); the planner answers with the round's
    response text. The critic reports the cumulative discussion in its output, as its instructions say.
    `broken` nodes get a schema-violating answer (they fail natively); `discussion` (callable: rounds -> text)
    replaces the critic's reported discussion."""

    def __init__(self, script, broken=(), discussion=None):
        self.script = list(script)
        self.broken, self.discussion = set(broken), discussion
        self.calls, self.errors, self.problems = [], [], []
        self.lock = threading.Lock()
        self.tokens = {node: [] for node in NODES}   # per node: (answer token, response id) of each answer
        self.reported = []                           # the rounds the scripted critic has reported
        self.answered = None                         # the planResponse of the current round

    def answer(self, request):
        with self.lock:
            return self.scripted(request)

    def scripted(self, request):
        markers = dq.MARKER.findall(json.dumps(request))
        if not markers:
            raise dq.QualError("request without a ZPLAN_NODE marker")
        node = markers[-1]
        if node not in NODES:
            raise dq.QualError("unexpected node %s" % node)
        schema = request.get("text", {}).get("format", {}).get("schema")
        if not isinstance(schema, dict):
            raise dq.QualError("%s: request has no output schema" % node)
        count = self.calls.count(node) + 1
        if node in self.broken:
            self.calls.append(node)
            return Tagged()  # {} violates the contract: a native `malformed` error of the node
        if not self.continued(node, request):
            self.problems.append("%s call #%s did not continue its own conversation" % (node, count))
        if count > len(self.script):
            raise dq.QualError("%s: unexpected call #%s" % (node, count))
        verdict, findings, response = self.script[count - 1]
        token = "%s-%s-%s" % (node[0], count, uuid.uuid4().hex[:8])
        contract = schema["properties"]["response"]
        if node == "planner":
            self.answered = "%s [%s]" % (response, token)
            answer = {"proposal": canonical(fixture_proposal()), "planResponse": self.answered}
            self.check_fields(node, contract, answer)
        else:
            text = "%s [%s]" % (findings, token)
            self.reported.append({"round": count, "verdict": verdict, "findings": text, "response": self.answered})
            signals = list(contract["properties"]["signals"]["properties"])
            if signals != ["verdict"]:
                raise dq.QualError("critic: expected the single signal verdict, got %s" % signals)
            reported = self.discussion(self.reported) if self.discussion else canonical(
                {"version": 1, "rounds": self.reported})
            answer = {"output": {"discussion": reported}, "signals": {"verdict": verdict},
                      "diagnostic": {"message": text}}
            self.check_fields(node, contract, answer, whole=True)
        if not dq.valid(schema, {"response": answer}):
            raise dq.QualError("%s: scripted answer #%s violates the request schema" % (node, count))
        ident = "qual-%s-%s-%s" % (node, count, uuid.uuid4().hex[:6])
        self.tokens[node].append((token, ident))
        self.calls.append(node)
        tagged = Tagged(answer)
        tagged.response_id = ident
        return tagged

    @staticmethod
    def check_fields(node, contract, answer, whole=False):
        properties = contract.get("properties", {})
        if whole:
            output = properties.get("output", {})
            if "properties" not in output or set(output["properties"]) != {"discussion"}:
                raise dq.QualError("critic: its output contract is not {discussion}: %s" % list(output)[:6])
        elif set(properties) != set(answer):
            raise dq.QualError("%s: output contract %s != %s" % (node, sorted(properties), sorted(answer)))

    def continued(self, node, request):
        """The node's earlier answer is an assistant turn of this request's own conversation (replayed input) or
        its previous response id: one provider conversation across the rounds. The token is looked for in assistant
        items only; the bound inputs (discussion) repeat the same words in the user turn of a fresh conversation."""
        if not self.tokens[node]:
            return True
        token, ident = self.tokens[node][-1]
        if request.get("previous_response_id") == ident:
            return True
        items = request.get("input")
        return isinstance(items, list) and any(
            isinstance(item, dict) and item.get("role") == "assistant" and token in json.dumps(item) for item in items)

    def leftovers(self):
        return max(0, len(self.script) - self.calls.count("critic"))


def rounds(*entries):
    return [(verdict, "F%d %s" % (n, verdict), "reply %d" % n) for n, verdict in enumerate(entries, 1)]


def bad_last_round(reported):
    """A discussion whose last round says something else than the signalled result."""
    changed = [dict(item) for item in reported]
    changed[-1]["response"] = "a response the planner never gave"
    return canonical({"version": 1, "rounds": changed})


# `rounds`: frozen plan_rounds of the revision; `order`: node calls; `status`/`diagnostic`/`used`/`verdict`: result.
SCENARIOS = {
    # a_accept_r1's target carries a second valid remote: planning submits from its own disposable clone, whose
    # source must stay the project's origin identity (10.12 resolves an upstream-less branch from the single
    # valid remote and fails on several).
    "a_accept_r1": dict(rounds=3, script=rounds("accepted"), order=["planner", "critic"], status="proposed",
                        used=1, verdict="accepted", second_remote=True),
    "b_reject_repair_accept": dict(rounds=3, script=rounds("rejected", "accepted"),
                                   order=["planner", "critic"] * 2, status="proposed", used=2, verdict="accepted"),
    "c_dispute_accepted": dict(rounds=3, script=[("rejected", "F1 the second milestone looks redundant", "reply 1"),
                                                 ("accepted", "dispute accepted: the milestone is the independent check",
                                                  "F1 disputed: it is the independent check")],
                               order=["planner", "critic"] * 2, status="proposed", used=2, verdict="accepted"),
    "d_exhausted": dict(rounds=2, script=rounds("rejected", "rejected"), order=["planner", "critic"] * 2,
                        status="review_exhausted", used=2, verdict="rejected"),
    "e_critic_error": dict(rounds=3, script=rounds("accepted"), broken=["critic"], order=["planner", "critic"],
                           status="run_failed", diagnostic="critic_failed"),
    "f_planner_error": dict(rounds=3, script=rounds("accepted"), broken=["planner"], order=["planner"],
                            status="run_failed", diagnostic="planner_failed"),
    "g_malformed_discussion": dict(rounds=3, script=rounds("accepted"), discussion=bad_last_round,
                                   order=["planner", "critic"], status="proposal_invalid"),
}


class Frozen:
    """The profile stand-in of a qualification session: the revision's frozen rounds and no rules."""

    def __init__(self, rounds, roles):
        self.rounds, self.roles = rounds, roles

    def freeze_plan(self):
        return self.roles, {"plan_rounds": self.rounds, "rules": [],
                            "config_digest": digest({"qualification": self.rounds})}


def check(scenario, provider, authority, blocked):
    """Failures as short strings; empty when the scenario passed."""
    problems = list(provider.errors) + list(provider.problems)
    current = authority.current
    calls = list(provider.calls)
    if scenario.get("broken"):
        # Native retries a failed provider turn ("provider failed; continuing once"), so the broken node may be
        # called more than once; nothing may run after it.
        while len(calls) > len(scenario["order"]) and calls[-1] == calls[-2] == scenario["order"][-1]:
            calls.pop()
    if calls != scenario["order"]:
        problems.append("node order %s != expected %s" % (provider.calls, scenario["order"]))
    if current["status"] != scenario["status"]:
        problems.append("status %s != %s" % (current["status"], scenario["status"]))
    if "diagnostic" in scenario and current["diagnostic"] != scenario["diagnostic"]:
        problems.append("diagnostic %r != %r" % (current["diagnostic"], scenario["diagnostic"]))
    evidence = current["evidence"]
    if "verdict" in scenario:
        if evidence is None:
            problems.append("no gate evidence")
        else:
            seen = (evidence.get("gate"), evidence.get("rounds_used"), evidence.get("rounds_limit"),
                    evidence.get("critic_verdict"), len(evidence.get("discussion", {}).get("rounds", ())))
            want = ("plan", scenario["used"], scenario["rounds"], scenario["verdict"], scenario["used"])
            if seen != want:
                problems.append("gate %s != %s" % (seen, want))
            if evidence.get("resolved_config_digest") != current["frozen"]["config_digest"]:
                problems.append("gate digest is not the frozen configuration's")
        if blocked is not None:
            problems.append("unexpected refusal: %s" % blocked)
    else:
        if evidence is not None:
            problems.append("evidence exists after a failed run")
        if blocked is None:
            problems.append("the run was not refused")
    if scenario.get("second_remote") and current.get("terminal_envelope") is not None:
        head = subprocess.run(["git", "-C", str(authority.project), "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
        source = current["terminal_envelope"]["source"]
        seen = {key: source[key] for key in ("repository", "branch", "revision")}
        want = {"repository": "zplan-qual/fixture", "branch": "main", "revision": head}
        if seen != want:
            problems.append("observed source %s != %s" % (seen, want))
    return problems


def run_scenario(name, scenario, binary, root, timeout, version=None):
    work = root / name.split("_")[0]  # short: the controller socket lives under the state dir
    provider = PlanProvider(scenario["script"], scenario.get("broken", ()), scenario.get("discussion"))
    project, env, server = dq.setup_work(work, binary, provider)
    if scenario.get("second_remote"):
        dq.git(project, "remote", "add", "backup", "https://github.com/zplan-qual/backup.git")
    state = (work / "s").resolve()
    home = os.environ.get("HOME")
    os.environ["HOME"] = env["HOME"]  # the production authority and lock roots follow HOME
    deadline = time.monotonic() + timeout
    problems, blocked = [], None
    try:
        with Authority(None, project) as authority:
            authority.profile = Frozen(scenario["rounds"], default_roles())
            authority.begin("Plan qualification goal", default_roles(), "native")
            engine = NativeEngine(binary, state, environment=env, version=version)
            try:
                while True:
                    try:
                        engine.proposal(authority, lambda _: None, slice=10)
                        break
                    except SliceEnded:  # observation continues until the deadline
                        if time.monotonic() > deadline:
                            raise dq.QualError("timeout; calls %s" % provider.calls[-6:])
                    except Blocked as error:
                        blocked = str(error)
                        break
            finally:
                problems = check(scenario, provider, authority, blocked)
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
    return problems + [e for e in provider.errors if e not in problems]


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
    install()
    root = Path(tempfile.mkdtemp(prefix="zq-", dir="/tmp")).resolve()
    failed = 0
    try:
        for name in names:
            started = time.monotonic()
            scenario = SCENARIOS[name]
            problems = run_scenario(name, scenario, args.binary, root,
                                    args.timeout or 180 + 90 * scenario["rounds"], version)
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
