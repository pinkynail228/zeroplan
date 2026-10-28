"""Native control-flow qualification of the milestone driver graph (orchestrator, Linux test host).

Runs the pinned native binary against a scripted synthetic Responses provider on loopback.
Answers are scripted per node (dispatch by the last `ZPLAN_NODE=<name>` marker in the request)
and validated against that request's output schema; nothing calls a real provider. This proves
graph control flow only, not agent behaviour.

Scenarios a..j run the graph through the bare CLI. Adapter scenarios (k_adapter_*..m_adapter_*) drive
the production lifecycle (MilestoneRuns + NativeDriver) against the same provider: bounded polling to
done, export and merge; a lost force-stop resent on reopen; a recoverable failure resumed from its
checkpoint. The plan approval before them is scripted (no planner run).

    PYTHONPATH=. python3 devtools/driver_qual.py --binary "$ZEROSHOT_TEST_BINARY" [SCENARIO ...]
    devtools/linux-test.sh --py devtools/driver_qual.py

Event shapes follow tests/provider_transport_fixture.py (the pinned Codex release in toolchain.DEFAULT).
"""

import argparse
from contextlib import contextmanager
import http.server
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from terminal_planner import milestone  # noqa: E402
from terminal_planner.authority import Authority, Blocked, atomic_state, canonical, decode  # noqa: E402
from terminal_planner.engine import NativeEngine, fixture_proposal  # noqa: E402
from terminal_planner.runs import SLICE, TERMINAL, MilestoneRuns, NativeDriver  # noqa: E402
from terminal_planner.setup import default_roles, tool_paths  # noqa: E402


MARKER = re.compile(r"ZPLAN_NODE=([a-z_]+)")
REVIEWERS = ("acceptance_review", "code_review")
SCHEMA_KEYWORDS = {"type", "properties", "required", "additionalProperties", "items", "enum", "anyOf", "description"}
TYPES = {"null": lambda v: v is None, "boolean": lambda v: isinstance(v, bool), "string": lambda v: isinstance(v, str),
         "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
         "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
         "object": lambda v: isinstance(v, dict), "array": lambda v: isinstance(v, list)}


class QualError(Exception):
    pass


def valid(schema, value):
    """JSON Schema subset emitted by the pinned response contract (native_v2_runner/response.rs)."""
    unknown = set(schema) - SCHEMA_KEYWORDS
    if unknown:
        raise QualError("unsupported schema keywords: %s" % sorted(unknown))
    if "anyOf" in schema:
        return any(valid(option, value) for option in schema["anyOf"])
    kind = schema.get("type")
    if kind is not None and not TYPES[kind](value):
        return False
    if "enum" in schema and value not in schema["enum"]:
        return False
    if kind == "object":
        properties = schema.get("properties", {})
        if any(name not in value for name in schema.get("required", [])):
            return False
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            return False
        return all(valid(properties[name], item) for name, item in value.items() if name in properties)
    if kind == "array":
        return all(valid(schema["items"], item) for item in value)
    return True


def strings(schema, node, count):
    if schema.get("type") != "object" or any(p.get("type") != "string" for p in schema["properties"].values()):
        raise QualError("%s: synthetic answers fill string records only" % node)
    return {name: "%s %s #%s" % (node, name, count) for name in schema["properties"]}


class Provider:
    """Scripted answers: verifiers consume labels in order; steps get synthetic string records.

    `hooks` (node -> callable) stand in for an agent's workspace edits: a hook runs outside the lock before its
    node is answered. Nodes in `broken` get a schema-violating answer (the node fails natively) and run no hook.
    `repeat` reuses a verifier's last scripted label instead of failing on an unexpected call (resumed runs)."""

    def __init__(self, script, hooks=None, broken=(), repeat=False):
        self.script = {node: list(entries) for node, entries in script.items()}
        self.hooks, self.broken, self.repeat = dict(hooks or {}), set(broken), repeat
        self.calls, self.errors = [], []
        self.lock = threading.Lock()

    def answer(self, request):
        with self.lock:
            node, response = self.scripted(request)
        hook = self.hooks.get(node) if response is not None else None
        if hook is not None:
            try:
                hook()
            except Exception as error:
                raise QualError("%s hook: %s" % (node, error)) from error
        return {} if response is None else response

    def scripted(self, request):
        """(node, response) under the lock; response None means the deliberately malformed answer."""
        markers = MARKER.findall(json.dumps(request))
        if not markers:
            raise QualError("request without a ZPLAN_NODE marker")
        node = markers[-1]
        schema = request.get("text", {}).get("format", {}).get("schema")
        if not isinstance(schema, dict):
            raise QualError("%s: request has no output schema" % node)
        if node in self.broken:
            self.calls.append((node, "malformed"))
            return node, None
        count = sum(name == node for name, _ in self.calls) + 1
        contract = schema["properties"]["response"]
        label = None
        if "signals" in contract.get("properties", {}):
            entries = self.script.get(node)
            if not entries:
                raise QualError("%s: unexpected call #%s" % (node, count))
            entry = entries.pop(0) if len(entries) > 1 or not self.repeat else entries[0]
            entry = entry if isinstance(entry, dict) else {"label": entry}
            label = entry["label"]
            signals = list(contract["properties"]["signals"]["properties"])
            if len(signals) != 1:
                raise QualError("%s: expected one signal" % node)
            diagnostic = strings(contract["properties"]["diagnostic"], node, count)
            diagnostic.update({k: v for k, v in entry.items() if k != "label"})
            response = {"output": None, "signals": {signals[0]: label}, "diagnostic": diagnostic}
        else:
            if node in self.script:
                raise QualError("%s: scripted labels for a step" % node)
            response = strings(contract, node, count)
        if not valid(schema, {"response": response}):
            raise QualError("%s: scripted answer #%s violates the request schema" % (node, count))
        self.calls.append((node, label))
        return node, response

    def leftovers(self):
        return {node: entries for node, entries in self.script.items() if entries}


def events(response):
    return [
        {"type": "response.created", "response": {"id": "qual-response"}},
        {"type": "response.output_item.done", "item": {"type": "message", "role": "assistant", "id": "qual-message",
         "content": [{"type": "output_text", "text": json.dumps({"response": response})}]}},
        {"type": "response.completed", "response": {"id": "qual-response", "usage": {
         "input_tokens": 0, "output_tokens": 0, "total_tokens": 0}}},
    ]


def serve(provider):
    """Loopback HTTP/SSE server; returns (server, port). Never logs requests."""

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def reply(self, status, body, kind="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()

        def do_GET(self):
            if self.headers.get("Upgrade", "").lower() == "websocket":
                self.reply(404, b'{"error":"websocket transport not scripted"}')
                return
            self.reply(200, b'{"models":[],"data":[]}')

        def do_POST(self):
            size = int(self.headers.get("Content-Length", "0"))
            try:
                if not 0 < size <= 4 * 1048576:
                    raise QualError("request size")
                response = provider.answer(json.loads(self.rfile.read(size)))
            except (QualError, ValueError, KeyError, TypeError, AttributeError) as error:
                with provider.lock:
                    provider.errors.append(str(error) if isinstance(error, QualError) else type(error).__name__)
                self.reply(500, b'{"error":"driver qualification script rejected the request"}')
                return
            body = b"".join(b"data: " + json.dumps(e).encode() + b"\n\n" for e in events(response))
            self.reply(200, body, "text/event-stream")

    class Server(http.server.ThreadingHTTPServer):
        daemon_threads = True

        def handle_error(self, request, client_address):
            pass

    server = Server(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


# Scenarios -----------------------------------------------------------------

def task(rounds):
    return ["select", "select_verify"] + ["worker", *REVIEWERS] * rounds + ["steward_apply", "steward_decide"]


def output(signal_, message, **extra):
    return {"signal": signal_, "message": message, **extra}


OWNER = {"label": "needs_owner", "question": "Approve the scope change?", "proposal": "Split T1 into T1-a and T1-b."}
AMENDMENT = {"label": "needs_owner", "question": "The validator rejected a seventh added task. Approve a new plan revision?",
             "proposal": "Add task X7 (seventh addition; the driver allows six)."}
OUTER = milestone.outer_iterations(1)
SCENARIOS = {
    "a_two_tasks_done": dict(
        tasks=2, script={"select_init": ["open"], "acceptance_review": ["accepted"] * 2, "code_review": ["accepted"] * 2,
                         "steward_decide": ["continue", "done"], "final_verify": ["accepted"]},
        order=["preflight", "select_init"] + task(1) * 2 + ["final_verify"], output=output("done", "final_verify message #1")),
    "b_review_repair": dict(
        tasks=1, script={"select_init": ["open"], "acceptance_review": ["rejected", "accepted"],
                         "code_review": ["accepted", "accepted"], "steward_decide": ["done"], "final_verify": ["accepted"]},
        order=["preflight", "select_init"] + task(2) + ["final_verify"], output=output("done", "final_verify message #1")),
    "c_needs_owner": dict(
        tasks=2, script={"select_init": ["open"], "acceptance_review": ["accepted"], "code_review": ["accepted"],
                         "steward_decide": [OWNER]},
        order=["preflight", "select_init"] + task(1), output=output("needs_owner", "steward_decide message #1",
                                                       question=OWNER["question"], proposal=OWNER["proposal"])),
    "d_review_exhausted": dict(
        tasks=1, script={"select_init": ["open"], "acceptance_review": ["rejected"] * milestone.TASK_ITERATIONS,
                         "code_review": ["rejected"] * milestone.TASK_ITERATIONS, "steward_decide": ["blocked"]},
        order=["preflight", "select_init"] + task(milestone.TASK_ITERATIONS), output=output("blocked", "steward_decide message #1")),
    "e_empty_queue": dict(
        tasks=1, script={"select_init": ["empty"], "empty_final_verify": ["accepted"]},
        order=["preflight", "select_init", "empty_final_verify"], output=output("done", "empty_final_verify message #1")),
    "f_outer_exhausted": dict(
        tasks=1, script={"select_init": ["open"], "acceptance_review": ["accepted"] * OUTER,
                         "code_review": ["accepted"] * OUTER, "steward_decide": ["continue"] * OUTER},
        order=["preflight", "select_init"] + task(1) * OUTER, output=output("blocked", "steward_decide message #%s" % OUTER)),
    "g_final_repair": dict(
        tasks=1, script={"select_init": ["open"], "acceptance_review": ["accepted"], "code_review": ["accepted"],
                         "steward_decide": ["done"], "final_verify": ["rejected"], "scope_verify": ["accepted"],
                         "final_reverify": ["accepted"]},
        order=["preflight", "select_init"] + task(1) + ["final_verify", "repair", "scope_verify", "final_reverify"],
        output=output("done", "final_reverify message #1")),
    "h_final_exhausted": dict(
        tasks=1, script={"select_init": ["open"], "acceptance_review": ["accepted"], "code_review": ["accepted"],
                         "steward_decide": ["done"], "final_verify": ["rejected"],
                         "scope_verify": ["accepted"] * milestone.FINAL_REPAIRS,
                         "final_reverify": ["rejected"] * milestone.FINAL_REPAIRS},
        order=["preflight", "select_init"] + task(1) + ["final_verify"] + ["repair", "scope_verify", "final_reverify"] * milestone.FINAL_REPAIRS,
        output=output("blocked", "final_reverify message #%s" % milestone.FINAL_REPAIRS)),
    # The validator rejection itself is unit-tested (check_amendments); here the steward reports it.
    "i_forbidden_amendment": dict(
        tasks=1, script={"select_init": ["open"], "acceptance_review": ["accepted", "accepted"],
                         "code_review": ["rejected", "accepted"], "steward_decide": [AMENDMENT]},
        order=["preflight", "select_init"] + task(2), output=output("needs_owner", "steward_decide message #1",
                                                       question=AMENDMENT["question"], proposal=AMENDMENT["proposal"])),
    # A failed selection (missing checker, corrupt manifest) ends the run before any writer.
    "j_selection_invalid": dict(
        tasks=1, script={"select_init": ["open"], "select_verify": ["invalid"]},
        order=["preflight", "select_init", "select", "select_verify"],
        terminal={"status": "failed", "reason": "selection_invalid"}),
    # A brief the preflight calls contradictory ends the run before any worker (C1); a conflicting review verdict ends
    # it after the worker that produced the reviewed change (C2). The prefixes n_/o_ are free: each scenario's scratch
    # directory is named by its prefix, which i_/j_ (the scenarios above) already use.
    "n_preflight_conflict": dict(
        tasks=1, script={"preflight": ["conflict"]}, order=["preflight"],
        terminal={"status": "failed", "reason": "preflight_conflict"}),
    "o_review_conflict": dict(
        tasks=1, script={"select_init": ["open"], "acceptance_review": ["conflict"], "code_review": ["accepted"]},
        order=["preflight", "select_init", "select", "select_verify", "worker", *REVIEWERS],
        terminal={"status": "failed", "reason": "review_conflict"}),
}
for _scenario in SCENARIOS.values():
    # Every task iteration passes the read-only selection gate unless a scenario scripts it.
    _scenario["script"].setdefault("select_verify", ["selected"] * _scenario["order"].count("select"))
    _scenario["script"].setdefault("preflight", ["ready"])


def normalize(names):
    """Parallel reviewers may answer in either order."""
    result, run = [], []
    for name in list(names) + [None]:
        if name in REVIEWERS:
            run.append(name)
            continue
        result += sorted(run)
        run = []
        if name is not None:
            result.append(name)
    return result


def repairs_after_acceptance(calls):
    """Names of repair calls that follow an accepted review round or an accepted final verification."""
    found, verdicts = [], {}
    for name, label in calls:
        if name in ("worker", "repair", "empty_repair") and (
                (name == "worker" and verdicts.get("acceptance_review") == verdicts.get("code_review") == "accepted")
                or (name != "worker" and verdicts.get("final") == "accepted")):
            found.append(name)
        if name in REVIEWERS:
            verdicts[name] = label
        elif name in ("select", "worker"):
            verdicts.pop("acceptance_review", None)
            verdicts.pop("code_review", None)
        elif name.endswith("final_verify"):
            verdicts["final"] = label
        elif name.endswith("scope_verify"):
            verdicts["scope"] = label
        elif name.endswith("final_reverify"):
            verdicts["final"] = label if verdicts.get("scope") == "accepted" else "rejected"
    return found


def proposal(tasks):
    value = fixture_proposal()
    value["milestones"][0]["slices"][0]["tasks"] = [
        {"id": "T1" if i == 1 else "T1-%s" % i, "title": "Synthetic task %s" % i, "checks": ["Synthetic check %s" % i]}
        for i in range(1, tasks + 1)]
    return value


def documents(scenario):
    baseline, _ = milestone.build_manifest(proposal(scenario["tasks"]), "M1", 1)
    return (milestone.milestone_graph(len(baseline["tasks"])), milestone.milestone_runtime(default_roles()),
            milestone.milestone_input(baseline))


def check(scenario, provider, terminal):
    """Failures as short strings; empty when the scenario passed."""
    problems = list(provider.errors)
    names = [name for name, _ in provider.calls]
    if normalize(names) != normalize(scenario["order"]):
        problems.append("node order %s != expected %s" % (normalize(names), normalize(scenario["order"])))
    if provider.leftovers():
        problems.append("unused script entries %s" % provider.leftovers())
    if repairs_after_acceptance(provider.calls):
        problems.append("repair after acceptance")
    if terminal != scenario.get("terminal", {"status": "succeeded", "output": scenario.get("output")}):
        problems.append("root result %s" % json.dumps(terminal)[:400])
    return problems


# Native run ----------------------------------------------------------------

def git(project, *args):
    subprocess.run(["git", "-C", str(project), "-c", "user.name=zplan", "-c", "user.email=zplan@localhost", *args],
                   check=True, capture_output=True, timeout=60)


def terminate(process, state):
    """Kill the CLI process group (if any) and every process carrying this scenario's isolated state dir."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            if process is not None:
                os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass
        marker = ("ZEROSHOT_STATE_DIR=%s" % state).encode()
        for entry in Path("/proc").glob("[0-9]*") if Path("/proc").is_dir() else []:
            try:
                if int(entry.name) != os.getpid() and marker in (entry / "environ").read_bytes().split(b"\0"):
                    os.kill(int(entry.name), sig)
            except (OSError, ValueError):
                pass
        time.sleep(1)


def setup_work(work, binary, provider):
    """Scratch project (Git, GitHub origin, local identity), loopback provider and CODEX_HOME; (project, env, server)."""
    project, codex_home, home = work / "project", work / "codex", work / "home"
    for path in (project, codex_home, home, work / "s", work / "config"):
        path.mkdir(parents=True)
    git(project, "init", "-q", "-b", "main")
    # Merges (adapter scenarios) need a configured identity; the scratch HOME has no global one.
    git(project, "config", "user.name", "zplan qual")
    git(project, "config", "user.email", "zplan-qual@localhost")
    (project / "README.md").write_text("Driver qualification fixture.\n")
    git(project, "add", ".")
    git(project, "commit", "-qm", "fixture")
    # Identity parsing only; nothing fetches or pushes.
    git(project, "remote", "add", "origin", "https://github.com/zplan-qual/fixture.git")
    server, port = serve(provider)
    # Loopback provider, dummy key, no web search, no sandbox keys (see local_identity.rs:115).
    (codex_home / "config.toml").write_text(
        'model_provider = "zplan_qual"\nweb_search = "disabled"\n[model_providers.zplan_qual]\n'
        'name = "zplan driver qualification"\nbase_url = "http://127.0.0.1:%s/v1"\n'
        'env_key = "OPENAI_API_KEY"\nwire_api = "responses"\n' % port)
    codex = tool_paths(Path(binary).resolve().parent)[1]
    env = {"PATH": "%s:%s" % (codex.parent, os.environ.get("PATH", "/usr/bin:/bin")), "HOME": str(home),
           "CODEX_HOME": str(codex_home), "OPENAI_API_KEY": "zplan-qual-dummy", "LANG": "C.UTF-8"}
    return project, env, server


def run_native(name, scenario, binary, root, timeout):
    work = root / name.split("_")[0]  # short: the controller socket lives under the state dir
    provider = Provider(scenario["script"])
    project, env, server = setup_work(work, binary, provider)
    state = work / "s"
    for kind, value in zip(("graph", "runtime", "input"), documents(scenario)):
        (work / (kind + ".json")).write_text(json.dumps(value))
    env.update(ZEROSHOT_STATE_DIR=str(state), ZEROSHOT_CONFIG_DIR=str(work / "config"))
    process = subprocess.Popen([str(binary), "run", "--title", "driver-qual " + name, "--graph", str(work / "graph.json"),
                                "--runtime-config", str(work / "runtime.json"), "--input", str(work / "input.json"),
                                "--no-environment"], cwd=project, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        stdout, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        return ["timeout after %ss; calls %s" % (timeout, [n for n, _ in provider.calls][-6:])] + provider.errors
    finally:
        terminate(process, state)
        server.shutdown()
        server.server_close()
    terminal = None
    for line in stdout.decode("utf-8", "replace").splitlines():
        try:
            status = json.loads(line).get("status", {})
        except (ValueError, AttributeError):
            continue
        if isinstance(status, dict) and status.get("phase") == "finished":
            terminal = status.get("terminalResult")
    return check(scenario, provider, terminal)


# Adapter scenarios ---------------------------------------------------------
# The production lifecycle adapter (MilestoneRuns + NativeDriver) against the same scripted provider.
# Scripted agents edit nothing, so provider hooks stand in for the workspace edits: the worker writes a
# product file, steward_apply accepts the next open manifest task.

class LostStop(NativeDriver):
    """The first force-stop never reaches native (lost request); later ones go to the binary."""

    lost = True

    def force_stop(self, r):
        if self.lost:
            self.lost = False
            raise Blocked("Native force-stop не ответил; run остаётся stopping, наблюдайте его.")
        super().force_stop(r)


def need(ok, text):
    if not ok:
        raise QualError(text)


def approve(project, binary, state, version=None):
    """Approved native plan revision 1 with proposal(1), without a planner run: the planner CLI answers are
    scripted, only `--version` reaches the binary. The authority lives under the current HOME. `version` is the
    `zeroshot X.Y.Z` the binary must print (None: the default toolchain's; a candidate names its own)."""
    head = subprocess.run(["git", "-C", str(project), "rev-parse", "HEAD"], check=True, capture_output=True,
                          text=True).stdout.strip()

    def projection(status, cursor):
        return {"runId": "qual-plan", "subscriptionId": "qual-plan-watch", "title": "Terminal roadmap revision 1",
                "source": {"repository": "zplan-qual/fixture", "branch": "main", "revision": head},
                "size": "medium", "cursor": cursor, "status": status}

    round_ = {"round": 1, "verdict": "accepted", "findings": "Scripted plan review.", "response": "Scripted reply."}
    terminal = {"status": "succeeded", "output": {
        "schemaVersion": "2", "proposal": canonical(proposal(1)), "planVerdict": "accepted",
        "planFindings": round_["findings"], "planResponse": round_["response"],
        "discussion": canonical({"version": 1, "rounds": [round_]})}}
    answers = [[{"valid": True}], [{"runId": "qual-plan"}],
               [projection({"phase": "running", "activeExecutions": [{"node": "critic", "execution": "q1"}]}, "v2:1"),
                projection({"phase": "finished", "terminalResult": terminal}, "v2:2")]]

    def call(argv, **kwargs):
        if argv[1:] == ["--version"]:
            return subprocess.run(argv, **kwargs)
        stdout = "".join(json.dumps(value) + "\n" for value in answers.pop(0))
        return subprocess.CompletedProcess(argv, 0, stdout, "")

    with Authority(None, project) as a:
        a.begin("Driver qualification goal", default_roles(), "native")
        NativeEngine(binary, state, call=call, version=version).proposal(a, lambda _: None)
        a.approve(1)


class Adapter:
    """One adapter scenario's paths, hooks and bounded polling."""

    def __init__(self, work, binary, env, provider, deadline, version=None):
        self.project, self.state, self.worktrees = work / "project", (work / "s").resolve(), work / "worktrees"
        self.binary, self.env, self.provider, self.deadline = binary, env, provider, deadline
        self.version = version
        self.force_stops = 0
        self.sources = []  # every `source` a watched projection carried (10.12 adds the optional `remote`)
        self.held, self.release = threading.Event(), threading.Event()

    def call(self, argv, **kwargs):
        self.force_stops += argv[1:2] == ["force-stop"]
        try:
            result = subprocess.run(argv, **kwargs)
        except subprocess.TimeoutExpired as error:
            # A bounded watch slice ends by timing out; its stdout still carries whole records, and the
            # trailing partial line is simply re-read by the next slice. Record them before re-raising.
            self.record_sources(argv, getattr(error, "stdout", None))
            raise
        self.record_sources(argv, result.stdout)
        return result

    def record_sources(self, argv, stdout):
        """Remember every `source` a watched projection carried (10.12 adds the optional `remote`)."""
        if argv[1:2] == ["watch"] and isinstance(stdout, (bytes, str)):
            text = stdout.decode("utf-8", "replace") if isinstance(stdout, bytes) else stdout
            for line in text.splitlines():
                try:
                    value = json.loads(line)
                except ValueError:
                    continue
                if isinstance(value, dict) and isinstance(value.get("source"), dict):
                    self.sources.append(value["source"])

    def second_remote(self):
        """A second valid remote: 10.12 fails an upstream-less branch then (AmbiguousRemote)."""
        git(self.project, "remote", "add", "backup", "https://github.com/zplan-qual/backup.git")

    def check_source(self, r):
        """The run must have been submitted from `origin` on zplan's own working branch and base commit."""
        need(self.sources, "no watched projection carried a source")
        wanted = {"repository": "zplan-qual/fixture", "branch": r["branch"], "revision": r["destination"]["base"]}
        for source in self.sources:
            seen = {key: source.get(key) for key in wanted}
            need(seen == wanted, "watched source %s != %s" % (seen, wanted))

    @contextmanager
    def session(self, kind=NativeDriver):
        """A fresh authority session and controller, as on every zplan start."""
        with Authority(None, self.project) as a:
            yield MilestoneRuns(a, kind(self.binary, self.state, call=self.call, environment=self.env,
                                 version=self.version),
                                worktrees=self.worktrees)

    def worktree(self):
        found = sorted(self.worktrees.iterdir()) if self.worktrees.is_dir() else []
        need(len(found) == 1, "expected one milestone worktree, found %s" % len(found))
        return found[0]

    def produce(self):
        (self.worktree() / "qual-M1.txt").write_text("Driver qualification product.\n")

    def accept(self):
        path = self.worktree() / milestone.MANIFEST
        manifest = decode(path.read_text())
        task = next((t for t in manifest["tasks"] if t["status"] == "open"), None)
        if task is not None:
            task["status"] = "done"
            manifest["progress"].append({"seq": len(manifest["progress"]) + 1, "task": task["id"], "phase": "accepted",
                                         "text": "Scripted steward acceptance."})
            atomic_state(path, manifest)

    def hold(self):
        self.held.set()
        self.release.wait(max(0, self.deadline - time.monotonic()))

    def follow(self, runs, r, done=None):
        """Bounded poll slices (the UI's) until `done()` (default: r is terminal); returns (slices, display lines)."""
        done = done or (lambda: r["status"] in TERMINAL)
        mark, slices, lines = None, 0, []
        while not done():
            need(time.monotonic() < self.deadline, "timeout in status %s; calls %s"
                 % (r["status"], [n for n, _ in self.provider.calls][-6:]))
            started = time.monotonic()
            found, mark = runs.poll(r, mark)
            spent = time.monotonic() - started
            need(spent < SLICE + 10, "poll slice took %ss" % int(spent))
            slices += 1
            lines += found
            if spent < 0.5:
                time.sleep(0.5)
        return slices, lines

    def deliver(self, runs, r):
        need(r["status"] == "finished" and r["outcome"] == "done",
             "attempt ended %s/%s: %s" % (r["status"], r["outcome"], r["diagnostic"]))
        runs.finish(r)
        need(r["delivery"] == "awaiting_merge", "export ended in delivery %s" % r["delivery"])
        runs.merge(r)
        need(r["delivery"] == "integrated", "merge ended in delivery %s" % r["delivery"])
        need((self.project / "qual-M1.txt").is_file(), "the product file is not on main after the merge")
        need(not runs.waiting("M2"), "M2 still waits for M1 after the merge")


def adapter_done_merge(q):
    q.second_remote()
    with q.session() as runs:
        r = runs.start("M1", 1, default_roles())
        need(r["status"] == "submitted", "start ended in %s: %s" % (r["status"], r["diagnostic"]))
        slices, lines = q.follow(runs, r)
        need(slices > 1, "the run ended within one poll slice; bounded polling not exercised")
        need(lines, "no progress lines across %s poll slices" % slices)
        q.deliver(runs, r)
        q.check_source(r)


def adapter_lost_stop(q):
    with q.session(LostStop) as runs:
        r = runs.start("M1", 1, default_roles())
        q.follow(runs, r, q.held.is_set)
        try:
            runs.stop(r)
        except Blocked:
            pass
        else:
            raise QualError("the lost force-stop did not surface")
        need(r["status"] == "stopping" and q.force_stops == 0, "after the lost stop: %s, %s sent" % (r["status"], q.force_stops))
    with q.session() as runs:
        # Reopen: the persisted stop request is resent, never forgotten.
        r = runs.reconcile()
        need(r is not None and r["status"] == "stopping", "reconcile returned %s" % (r and r["status"]))
        need(q.force_stops == 1, "reconcile sent %s force-stops" % q.force_stops)
        q.follow(runs, r)
        need(r["status"] == "stopped", "stop ended in %s: %s" % (r["status"], r["diagnostic"]))
        need(runs.active() is None, "a writer is still active after the stop")


def adapter_resume(q):
    with q.session() as runs:
        r = runs.start("M1", 1, default_roles())
        q.follow(runs, r)
        need(r["status"] == "failed", "the broken steward_apply ended in %s/%s" % (r["status"], r["outcome"]))
        need(r["recoverable"] is True, "native reports the failure (%s) as not recoverable" % r["diagnostic"])
        with q.provider.lock:
            q.provider.broken.clear()
        successor = runs.resume(r)
        need(successor["predecessor"] == r["run_id"] and successor["status"] == "submitted",
             "resume created %s" % {k: successor[k] for k in ("predecessor", "status")})
        q.follow(runs, successor)
        detached = subprocess.run(["git", "-C", str(q.worktree()), "symbolic-ref", "-q", "HEAD"], capture_output=True)
        need(detached.returncode == 1, "the resumed worktree is not on a detached checkpoint HEAD")
        q.deliver(runs, successor)


DONE_SCRIPT = {"select_init": ["open"], "select_verify": ["selected"], "acceptance_review": ["accepted"],
               "code_review": ["accepted"], "steward_decide": ["done"], "final_verify": ["accepted"]}
WORK_HOOKS = {"worker": "produce", "steward_apply": "accept"}
ADAPTER = {
    "k_adapter_done_merge": dict(script=DONE_SCRIPT, hooks=WORK_HOOKS, drive=adapter_done_merge),
    "l_adapter_lost_stop": dict(script={"select_init": ["open"], "select_verify": ["selected"]},
                                hooks={"worker": "hold"}, drive=adapter_lost_stop),
    "m_adapter_resume": dict(script=DONE_SCRIPT, hooks=WORK_HOOKS, broken=["steward_apply"], drive=adapter_resume),
}
for _scenario in ADAPTER.values():
    _scenario["script"] = {"preflight": ["ready"], **_scenario["script"]}


def run_adapter(name, scenario, binary, root, timeout, version=None):
    work = root / name.split("_")[0]
    provider = Provider(scenario["script"], broken=scenario.get("broken", ()), repeat=True)
    project, env, server = setup_work(work, binary, provider)
    q = Adapter(work, binary, env, provider, time.monotonic() + timeout, version)
    provider.hooks = {node: getattr(q, method) for node, method in scenario["hooks"].items()}
    home = os.environ.get("HOME")
    # Production authority and lock roots follow HOME: keep them in the scratch home.
    os.environ["HOME"] = env["HOME"]
    try:
        approve(project, binary, q.state, version)
        scenario["drive"](q)
        problems = []
    except Exception as error:  # every failure is a scenario result, not a harness crash
        problems = ["%s: %s" % (type(error).__name__, str(error)[:400])]
    finally:
        q.release.set()
        terminate(None, q.state / "runs")
        server.shutdown()
        server.server_close()
        if home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = home
    return problems + [e for e in provider.errors if e not in problems]


ALL = {**SCENARIOS, **ADAPTER}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("scenarios", nargs="*", help="default: all of %s" % ", ".join(sorted(ALL)))
    parser.add_argument("--binary", default=os.environ.get("ZEROSHOT_TEST_BINARY") or str(tool_paths()[0]))
    parser.add_argument("--zeroshot-version", help="X.Y.Z the binary prints for --version (default: the default toolchain's;"
                        " a candidate toolchain names its own)")
    parser.add_argument("--timeout", type=int, default=0, help="per-scenario seconds (default: by call count)")
    parser.add_argument("--keep", action="store_true", help="keep the scratch directory")
    args = parser.parse_args(argv)
    names = args.scenarios or sorted(ALL)
    version = "zeroshot " + args.zeroshot_version if args.zeroshot_version else None
    if set(names) - set(ALL):
        parser.error("unknown scenarios: %s" % ", ".join(sorted(set(names) - set(ALL))))
    if not Path(args.binary).is_file() or not tool_paths(Path(args.binary).resolve().parent)[1].is_file():
        print("SKIP: pinned zeroshot/codex not found next to %s" % args.binary)
        return 2
    # /tmp, not TMPDIR: adapter state roots hold STATE/runs/runs/<uuid>/controller.sock (< 108 bytes on Linux),
    # and a test-host TMPDIR under a temporary home directory is too deep for that.
    root = Path(tempfile.mkdtemp(prefix="zq-", dir="/tmp")).resolve()
    failed = 0
    try:
        for name in names:
            started = time.monotonic()
            if name in ADAPTER:
                problems = run_adapter(name, ADAPTER[name], args.binary, root, args.timeout or 900, version)
            else:
                scenario = SCENARIOS[name]
                problems = run_native(name, scenario, args.binary, root, args.timeout or 120 + 20 * len(scenario["order"]))
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
