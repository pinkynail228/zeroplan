"""H1: real stores/Git/controller/Architect; only provider and engine transport are fixtures."""
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

from terminal_planner.application import ApplicationService, SendMessageRequest, ToolDecision, request_snapshot
from terminal_planner.architect import Architect, ArchitectStore
from terminal_planner.authority import Blocked
from terminal_planner import bridge, process
from terminal_planner.engine import FixtureEngine, fixture_draft
from terminal_planner.tui.controller import Controller
from test_architect import FAKE, completes
from test_application import FakeArchitect
import test_terminal_planner as tp


# The provider reads its own MCP configuration, exactly as the real adapter passes it.
# No real provider executable, credential or network is used (only the local bridge socket).
TOOLS = r'''
import socket, tomllib
config = next(a for a in sys.argv if a.startswith("mcp_servers="))
args = tomllib.loads(config)["mcp_servers"]["zplan"]["args"]
for tool in step.get("tools", []):
    request = dict(tool)
    if "--turn" in args:
        request["turn"] = args[args.index("--turn") + 1]
    with open(os.path.join(here, "requests.jsonl"), "a") as stream:
        stream.write(json.dumps(request) + "\n")
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(args[args.index("--controller") + 1])
    sock.sendall(json.dumps(request).encode() + b"\n")
    with sock.makefile("rb") as stream:
        reply = json.loads(stream.readline())
    sock.close()
    with open(os.path.join(here, "results.jsonl"), "a") as stream:
        stream.write(json.dumps(reply) + "\n")
'''


class ScriptProvider:
    def __init__(self, root, project, tools):
        self.root = root / "provider"
        self.root.mkdir()
        executable = self.root / "codex"
        executable.write_text((FAKE % {"python": sys.executable}).replace(
            'for line in step.get("lines", []):', TOOLS + '\nfor line in step.get("lines", []):'))
        executable.chmod(0o755)
        (self.root / "scenario.json").write_text(json.dumps({"steps": [
            {"tools": tools, "lines": completes("Initial dispatch recorded.")},
            {"lines": completes("Waiting for the owner.")}]}))
        home = self.root / "home"
        home.mkdir()
        (home / "auth.json").write_text("{}")  # synthetic fixture, never owner auth
        self.architect = Architect(executable, {"PATH": os.environ["PATH"], "CODEX_HOME": str(home)},
                                   project, "fixture-model", "high",
                                   store=ArchitectStore(project, root=root / "architect"))

    def rows(self, name):
        path = self.root / (name + ".jsonl")
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def plan_tool(rid="plan-child"):
    return {"id": rid, "tool": "zplan_plan", "args": {"goal": "Plan a small useful change", "plan": fixture_draft()}}


class DispatchTests(tp.ProjectTest):
    def controller(self, **kwargs):
        kwargs.setdefault("engine_factory", lambda *_: FixtureEngine())
        controller = Controller.for_project(self.project, self.state, fixture_id="test", **kwargs)
        self.addCleanup(controller.stop)
        controller.start()
        return controller

    def records(self, service):
        return [json.loads(line) for line in service.operations_path.read_text().splitlines()]

    def test_owner_plan_dispatch_and_replay_without_screen(self):
        provider = ScriptProvider(self.root, self.project, [plan_tool()])
        controller = self.controller()
        service = ApplicationService(provider.architect, controller=controller)
        # Existing unbound and legacy chat results share the same file with application-issued linkage.
        service.tool_request({"id": "legacy-unbound", "tool": "zplan_approve_plan", "args": {"revision": 98}})
        token = controller.begin_turn("Approve the old plan", 0)
        service.tool_request({"id": "legacy-chat", "tool": "zplan_approve_plan",
                              "args": {"revision": 99}, "turn": token})
        controller.end_turn(token)
        request = service.new_request("Plan a small useful change")
        self.assertIsNone(request.snapshot["revision"])
        result = service.send_message(request)
        self.assertEqual(result.status, "completed")
        self.assertNotIn("error", provider.rows("results")[0])
        child = [r for r in self.records(service) if r["operation_id"] == "plan-child"][-1]
        self.assertEqual(child["parent_operation_id"], request.operation_id)
        self.assertEqual(child["turn_id"], request.turn_id)
        self.assertEqual(child["conversation_id"], request.conversation_id)
        self.assertTrue(child["result"]["detail"]["dispatch"]["run_id"])
        results = controller.results()
        self.assertEqual(len(results), 3)
        self.assertNotIn("turn", results[0])
        self.assertEqual(results[1]["turn"], {"text": "Approve the old plan", "occurrence": 0})
        self.assertEqual(results[2]["turn"], {"text": request.text, "occurrence": 0,
                         "parent_operation_id": request.operation_id, "conversation_id": request.conversation_id,
                         "turn_id": request.turn_id, "message_id": request.message_id,
                         "shown_plan": None})
        before = service.operations_path.read_bytes()
        self.assertTrue(service.send_message(request).replayed)
        self.assertTrue(service.tool_request(provider.rows("requests")[0]).replayed)
        self.assertEqual(service.operations_path.read_bytes(), before)
        controller.stop()
        with tp.Authority(self.state, self.project) as authority:
            self.assertEqual(authority.current["run_id"], child["result"]["detail"]["dispatch"]["run_id"])
            self.assertEqual(len(authority.state["revisions"]), 1)
            self.assertEqual(authority.current["status"], "proposed")
        controller = self.controller()
        reopened = ApplicationService(provider.architect, controller=controller)
        self.assertTrue(reopened.send_message(request).replayed)
        self.assertTrue(reopened.tool_request(provider.rows("requests")[0]).replayed)
        self.assertEqual(len(provider.rows("calls")), 1)
        self.assertEqual([r["role"] for r in service.store.transcript()], ["owner", "architect"])
        status = reopened.tool_request({"id": "reopened-status", "tool": "zplan_status", "args": {}})
        self.assertEqual(status.detail["results"], results)
        reopened.tool_request({"id": "later-result", "tool": "zplan_approve_plan", "args": {"revision": 100}})
        controller.stop()
        with tp.Authority(self.state, self.project) as authority:
            stored = json.loads((authority.directory / "results.json").read_text())["results"]
        self.assertEqual(stored[:-1], results)
        self.assertGreater(stored[-1]["seq"], results[-1]["seq"])
        controller = self.controller()
        reopened = ApplicationService(provider.architect, controller=controller)
        status = reopened.tool_request({"id": "second-reopen", "tool": "zplan_status", "args": {}})
        self.assertEqual(status.detail["results"], stored)

    def test_tool_admission_conflicts_remain_linked_failures_through_cli_replay(self):
        provider = ScriptProvider(self.root, self.project,
                                  [plan_tool("parent"), plan_tool("parent"), plan_tool("occupied")])
        store = ArchitectStore(self.project, root=self.state / "architect" / "test")
        provider.architect.store = store
        previous = ApplicationService(FakeArchitect(store))
        previous.submit_message("occupied", "Earlier owner message")
        occupied = previous.operations_path.read_bytes().splitlines(keepends=True)
        controller = self.controller()
        service = ApplicationService(provider.architect, controller=controller)
        result = service.submit_message("parent", "Plan a small useful change")
        self.assertEqual(result.status, "completed")
        replies = provider.rows("results")
        self.assertEqual(len(replies), 3)
        self.assertTrue(all(row.get("error") == "operation.conflict" for row in replies), replies)
        projection = service.message_outcome(result)
        self.assertEqual(projection["model"]["status"], "completed")
        self.assertEqual((projection["outcome"], projection["exit_code"]), ("failed", 1))
        self.assertEqual(len(projection["children"]), 2)  # repeated refusal is idempotent
        for child in projection["children"]:
            self.assertEqual(child["category"], "failed/refused")
            self.assertEqual(child["error"]["family"], "operation.conflict")
            for key in ("conversation_id", "turn_id"):
                self.assertEqual(child[key], projection[key])
            self.assertEqual(child["parent_operation_id"], "parent")
        self.assertEqual([line for line in service.operations_path.read_bytes().splitlines(keepends=True)
                          if json.loads(line)["operation_id"] == "occupied"], occupied)
        before = service.operations_path.read_bytes()
        # The direct service still raises, and expired capability cannot attach another failure to the parent.
        with self.assertRaises(Blocked) as conflict:
            service.tool_request(provider.rows("requests")[0])
        self.assertEqual(conflict.exception.family, "operation.conflict")
        self.assertEqual(service.operations_path.read_bytes(), before)
        controller.stop()
        with tp.Authority(self.state, self.project) as authority:
            self.assertIsNone(authority.state)  # no plan or engine dispatch was created
        goal = self.root / "goal.md"
        goal.write_text("Plan a small useful change")
        output = subprocess.run([sys.executable, "-m", "terminal_planner.cli", "exec", "--goal", str(goal),
                                 "--operation-id", "parent", "--project", str(self.project),
                                 "--fixture", "test", "--state-dir", str(self.state)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(output.returncode, 1, output.stderr)
        replay = json.loads(output.stdout)
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["model"]["status"], "completed")
        self.assertEqual(replay["outcome"], "failed")
        self.assertEqual(replay["children"], [dict(child, replayed=True) for child in projection["children"]])
        self.assertEqual(service.operations_path.read_bytes(), before)
        self.assertEqual(len(provider.rows("calls")), 1)
        self.assertEqual(len([row for row in store.transcript() if row["role"] == "owner"]), 2)

    def test_malformed_result_does_not_discard_other_results_on_reopen_or_write(self):
        with tp.Authority(self.state, self.project) as authority:
            path = authority.directory / "results.json"
        legacy = {"seq": 4, "operation": "approve", "subject": {"revision": 98}, "outcome": "refused",
                  "family": "action.refused", "lines": ["The plan changed."], "origin": "owner",
                  "via": "chat", "turn": {"text": "Approve", "occurrence": None}}
        linked = dict(legacy, seq=5, subject={"revision": 99}, turn=dict(legacy["turn"],
                      parent_operation_id="parent", conversation_id="conversation", turn_id="turn", message_id="message"))
        invalid = [None, dict(legacy, turn=dict(legacy["turn"], turn_id=42)),
                   dict(legacy, turn=dict(legacy["turn"], message_id="")),
                   dict(legacy, turn={"text": "Missing occurrence"}),
                   dict(legacy, turn=dict(legacy["turn"], occurrence=True))]
        path.write_text(json.dumps({"results": [invalid[0], legacy, *invalid[1:], linked]}))
        service = ApplicationService(FakeArchitect(ArchitectStore(self.project)), controller=self.controller())
        status = service.tool_request({"id": "mixed-status", "tool": "zplan_status", "args": {}})
        self.assertEqual(status.detail["results"], [legacy, linked])
        service.tool_request({"id": "new-result", "tool": "zplan_approve_plan", "args": {"revision": 100}})
        stored = json.loads(path.read_text())["results"]
        self.assertEqual(stored[:-1], [legacy, linked])
        self.assertEqual(stored[-1]["seq"], 6)

    def test_git_change_before_submission_is_a_durable_refusal_without_dispatch(self):
        dispatches = []

        class RecordingEngine(FixtureEngine):
            def proposal(engine, *args, **kwargs):
                dispatches.append(1)
                return super().proposal(*args, **kwargs)

        # Readiness is an external boundary. Change real Git only once a revision has been persisted,
        # so the real Planning freshness check (not a mocked verdict) refuses the submission.
        changed = []
        with tp.Authority(self.state, self.project) as authority:
            planning_path = authority.path

        def readiness():
            if not changed and planning_path.exists():
                state = json.loads(planning_path.read_text())
                if state.get("revisions"):
                    (self.project / "source.txt").write_text("Owner changed the project\n")
                    self.git("add", "source.txt")
                    self.git("commit", "-qm", "owner change before readiness")
                    changed.append(1)
            return []

        provider = ScriptProvider(self.root, self.project, [plan_tool()])
        controller = self.controller(readiness=readiness, engine_factory=lambda *_: RecordingEngine())
        service = ApplicationService(provider.architect, controller=controller)
        request = service.new_request("Plan a small useful change")
        self.assertEqual(service.send_message(request).status, "completed")  # provider completion is not dispatch
        child = provider.rows("requests")[0]
        result = service.tool_request(child)
        self.assertEqual(changed, [1])
        self.assertEqual(dispatches, [])
        self.assertEqual(result.category, "failed/refused")
        self.assertIsNone(result.decision)
        self.assertEqual(result.detail["status"], "stale")
        self.assertEqual(result.error["family"], "action.refused")
        projection = controller.results()[-1]
        self.assertEqual(projection["outcome"], "refused")
        self.assertEqual(projection["family"], result.error["family"])
        self.assertEqual(projection["lines"], [result.error["message"]])
        self.assertEqual(provider.rows("results")[0]["error"], result.error["family"])
        self.assertEqual(provider.rows("results")[0]["message"], result.error["message"])
        terminal = [row for row in self.records(service) if row["operation_id"] == child["id"]][-1]
        self.assertEqual(terminal["result"], asdict(replace(result, replayed=False)))
        before = service.operations_path.read_bytes()
        self.assertEqual(service.tool_request(child), result)
        self.assertTrue(service.send_message(request).replayed)
        controller.stop()
        with tp.Authority(self.state, self.project) as authority:
            self.assertIsNone(authority.current["run_id"])
            self.assertEqual(len(authority.state["revisions"]), 1)
        reopened = ApplicationService(provider.architect, controller=self.controller())
        self.assertEqual(reopened.tool_request(child), result)
        self.assertTrue(reopened.send_message(request).replayed)
        self.assertEqual(reopened.operations_path.read_bytes(), before)
        self.assertEqual(len(provider.rows("calls")), 1)
        self.assertEqual(dispatches, [])

    def test_snapshot_is_captured_input_and_unknown_differs_from_no_plan(self):
        service = ApplicationService(FakeArchitect(ArchitectStore(self.project)), controller=self.controller())
        snapshot = {"revision": None, "milestones": [{"id": "M1"}]}
        request = service.new_request("hello", snapshot)
        fingerprint = service.fingerprint(request)
        snapshot["revision"] = 3
        request.snapshot["milestones"][0]["id"] = "changed"
        self.assertEqual(service.fingerprint(request), fingerprint)
        self.assertIsNone(request.snapshot["revision"])
        self.assertNotIn("revision", request_snapshot(None, "project"))
        self.assertNotEqual(fingerprint, service.fingerprint(replace(request, snapshot={"milestones": []})))

    def test_mutation_refusal_decision_and_identity_contract(self):
        with tp.Authority(self.state, self.project) as authority:
            process.Profile.of(authority).accept()
        tools = [{"id": "settings", "tool": "zplan_settings", "args": {"level": "manual"}}, plan_tool(),
                 {"id": "stale", "tool": "zplan_approve_plan", "args": {"revision": 99}}]
        provider = ScriptProvider(self.root, self.project, tools)
        controller = self.controller(profile=True)
        service = ApplicationService(provider.architect, controller=controller)
        service.send_message(service.new_request("Switch to manual and plan"))
        settings, plan, stale = provider.rows("requests")
        self.assertEqual(service.tool_request(settings).category, "awaiting_owner")
        refused = service.tool_request(stale)
        self.assertEqual(refused.category, "failed/refused")
        self.assertEqual(refused.error["family"], "action.refused")
        with self.assertRaises(Blocked) as conflict:
            service.tool_request(dict(settings, args={"level": "auto"}))
        self.assertEqual(conflict.exception.family, "operation.conflict")
        # Expired/forged capabilities and a plain origin field cannot grant owner authority.
        for token in (settings["turn"], "owner", None):
            denied = service.tool_request({"id": "forged-" + str(token), "tool": "zplan_settings",
                                           "args": {"level": "auto"}, "turn": token, "origin": "owner"})
            self.assertEqual((denied.category, denied.error["family"]), ("failed/refused", "autonomy.ask"))
        decision = service.tool_request({"id": "approve", "tool": "zplan_approve_plan", "args": {"revision": 1}})
        self.assertEqual(decision.category, "awaiting_owner")
        self.assertIsInstance(decision.decision, ToolDecision)
        self.assertEqual(decision.decision.subject, {"revision": 1})
        self.assertFalse(decision.decision.restorable)
        other = service.tool_request({"id": "approve-again", "tool": "zplan_approve_plan", "args": {"revision": 1}})
        self.assertFalse(other.replayed)  # identical args with a fresh id are a fresh operation
        self.assertEqual(other.category, "awaiting_owner")
        controller.stop()
        reopened = ApplicationService(provider.architect)
        replay = reopened.tool_request({"id": "approve", "tool": "zplan_approve_plan", "args": {"revision": 1}})
        self.assertEqual(replay.decision, decision.decision)

    def test_timeout_and_reopen_never_repeat_a_continuing_effect(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        calls = []

        class SlowEngine(FixtureEngine):
            def proposal(engine, *args, **kwargs):
                calls.append(1)
                result = super().proposal(*args, **kwargs)
                entered.set()
                if not release.wait(10):
                    raise RuntimeError("test did not release fixture transport")
                return result

        provider = ScriptProvider(self.root, self.project, [plan_tool()])
        controller = self.controller(engine_factory=lambda *_: SlowEngine())
        service = ApplicationService(provider.architect, controller=controller)
        request = service.new_request("plan now")  # the short tool deadline must not bound snapshot admission
        with patch.object(bridge, "TIMEOUT", 0.1):
            self.assertEqual(service.send_message(request).status, "completed")
        self.assertTrue(entered.wait(5))
        child = provider.rows("requests")[0]
        self.assertEqual(service.tool_request(child).category, "running")
        reopened = ApplicationService(provider.architect)
        self.assertEqual(reopened.tool_request(child).category, "indeterminate")
        self.assertEqual(provider.rows("results")[0]["error"], bridge.TIMEOUT_FAMILY)
        release.set()
        end = time.monotonic() + 5
        while time.monotonic() < end:
            result = reopened.tool_request(child)
            if result.category == "completed":
                break
            time.sleep(0.01)
        self.assertEqual(result.category, "completed")
        self.assertEqual(calls, [1])

    def test_torn_terminal_write_never_turns_an_effect_into_a_retry(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        class HeldEngine(FixtureEngine):
            def proposal(engine, *args, **kwargs):
                self.assertGreater(kwargs["slice"], 0)  # zero means unbounded at the engine contract
                result = super().proposal(*args, **kwargs)
                entered.set()
                if not release.wait(10):
                    raise RuntimeError("test did not release fixture transport")
                return result

        provider = ScriptProvider(self.root, self.project, [plan_tool()])
        controller = self.controller(engine_factory=lambda *_: HeldEngine())
        service = ApplicationService(provider.architect, controller=controller)
        request = service.new_request("plan now")
        with patch.object(bridge, "TIMEOUT", 0.1):
            service.send_message(request)
        self.assertTrue(entered.wait(5))
        child = provider.rows("requests")[0]
        with service.operations_path.open("ab") as stream:
            stream.write(b'{"operation_id":"torn-completion"')
        before = service.operations_path.read_bytes()
        release.set()
        controller.stop()  # waits for the admitted mutation and its completion attempt
        reopened = ApplicationService(provider.architect)
        self.assertEqual(reopened.tool_request(child).category, "indeterminate")
        self.assertEqual(reopened.send_message(request).status, "completed")
        with self.assertRaises(Blocked) as refused:
            service.tool_request(dict(child, id="new-child"))
        self.assertEqual(refused.exception.family, "operation.store_invalid")
        self.assertEqual(service.operations_path.read_bytes(), before)

    def test_registry_eviction_and_nested_evidence_do_not_change_replay(self):
        architect = FakeArchitect(ArchitectStore(self.project))
        service = ApplicationService(architect, controller=self.controller())
        first = {"id": "first", "tool": "zplan_settings", "args": {"level": "manual"}}
        result = service.tool_request(first)
        for number in range(bridge.MAX_REQUESTS + 1):
            service.tool_request(dict(first, id="later-%s" % number))
        before = service.operations_path.read_bytes()
        self.assertEqual(service.tool_request(first), replace(result, replayed=True))
        self.assertEqual(service.operations_path.read_bytes(), before)
        # Legacy evidence can contain nested provider strings: replay scrubs without rewriting history.
        records = self.records(service)
        terminal = next(row for row in records if row["operation_id"] == "first" and row["state"] == "terminal")
        secret = "sk-syntheticabcdefghijklmnop"
        terminal["result"]["detail"] = {"nested": {"items": [secret]}}
        with service.operations_path.open("a") as stream:
            stream.write(json.dumps(terminal) + "\n")
        before = service.operations_path.read_bytes()
        self.assertNotIn(secret, json.dumps(asdict(service.tool_request(first))))
        self.assertEqual(service.operations_path.read_bytes(), before)

    def test_process_crash_after_engine_effect_leaves_both_operations_indeterminate(self):
        # The subprocess dies after the fixture engine saved its real receipt, before child completion.
        script = r'''
import json, os, sys
from pathlib import Path
from dataclasses import asdict
from terminal_planner import bridge
from terminal_planner.application import ApplicationService
from terminal_planner.architect import ArchitectStore
from terminal_planner.engine import FixtureEngine, fixture_draft
from terminal_planner.tui.controller import Controller
from test_application import FakeArchitect
root, project, state = map(Path, sys.argv[1:])
class CrashEngine(FixtureEngine):
    def proposal(self, *args, **kwargs):
        super().proposal(*args, **kwargs)
        (root / "effect").write_text("dispatched")
        os._exit(91)
c = Controller.for_project(project, state, fixture_id="test", engine_factory=lambda *_: CrashEngine())
c.start()
a = FakeArchitect(ArchitectStore(project, root=root / "architect"))
def send(text, **kwargs):
    child = {"id": "crash-child", "tool": "zplan_plan", "args": {"goal": text, "plan": fixture_draft()}, "turn": kwargs["turn"]}
    (root / "child.json").write_text(json.dumps(child))
    bridge.call(bridge.path_for(project), child)
    return a.result
a.send = send
s = ApplicationService(a, controller=c)
r = s.new_request("crash after dispatch")
data = asdict(r); data.pop("_snapshot_json")
(root / "parent.json").write_text(json.dumps(data))
s.send_message(r)
'''
        completed = subprocess.run([sys.executable, "-c", script, str(self.root), str(self.project), str(self.state)],
                                   timeout=20, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 91, completed.stderr)
        self.assertEqual((self.root / "effect").read_text(), "dispatched")
        architect = FakeArchitect(ArchitectStore(self.project, root=self.root / "architect"))
        service = ApplicationService(architect, controller=self.controller())
        request = SendMessageRequest(**json.loads((self.root / "parent.json").read_text()))
        child = json.loads((self.root / "child.json").read_text())
        self.assertEqual(service.send_message(request).status, "indeterminate")
        self.assertEqual(service.tool_request(child).category, "indeterminate")
        self.assertEqual(architect.calls, [])
        self.assertEqual(len(service.store.transcript()), 1)
        snapshot = service.new_request("inspect only").snapshot
        self.assertEqual(snapshot["revision"], 1)
        self.assertEqual(snapshot["plan_state"]["status"], "proposed")
