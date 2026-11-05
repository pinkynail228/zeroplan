"""Send-only automation contracts: real stores, Git and controller; fixture/provider boundary only."""
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

from terminal_planner.application import ApplicationService, ToolResult
from terminal_planner.architect import ArchitectStore
from terminal_planner.authority import Blocked
from test_application import FakeArchitect
import test_terminal_planner as tp


class ExecTests(tp.ProjectTest):
    def command(self, *extra):
        goal = self.root / "goal.md"
        if not goal.exists():
            goal.write_text("Plan a small useful change", encoding="utf-8")
        return [sys.executable, "-m", "terminal_planner.cli", "exec", "--goal", str(goal),
                "--operation-id", "submission-1", "--project", str(self.project),
                "--fixture", "test", "--state-dir", str(self.state), *extra]

    def run_exec(self, *extra):
        return subprocess.run(self.command(*extra), capture_output=True, text=True, timeout=30)

    def test_fixture_send_and_process_reopen_preserve_history_and_identity(self):
        first = self.run_exec()
        self.assertEqual(first.returncode, 0, first.stderr)
        data = json.loads(first.stdout)
        self.assertFalse(data["replayed"])
        self.assertEqual(data["model"]["status"], "completed")
        self.assertEqual(data["verification"]["state"], "not_run")
        self.assertEqual(data["merge"]["state"], "not_requested")
        self.assertTrue(data["children"][0]["detail"]["dispatch"]["run_id"])
        journals = list(self.state.rglob("operations.jsonl"))
        self.assertEqual(len(journals), 1)
        before = journals[0].read_bytes()
        rows_path = journals[0].parent / "transcript.jsonl"
        rows = [json.loads(line) for line in rows_path.read_text().splitlines()]
        self.assertEqual([r["role"] for r in rows], ["owner", "architect"])
        for key in ("operation_id", "conversation_id", "turn_id"):
            self.assertEqual(rows[0][key], data[key])
        self.assertEqual(rows[0]["id"], data["message_id"])
        self.assertEqual(rows[1]["turn_id"], data["turn_id"])
        second = self.run_exec()
        self.assertEqual(second.returncode, 0, second.stderr)
        replay = json.loads(second.stdout)
        self.assertTrue(replay["replayed"])
        for key in ("operation_id", "message_id", "conversation_id", "turn_id", "model"):
            self.assertEqual(replay[key], data[key])
        self.assertEqual(journals[0].read_bytes(), before)
        self.assertEqual(len(rows_path.read_text().splitlines()), 2)
        (self.root / "goal.md").write_text("Different goal")
        conflict = self.run_exec()
        self.assertEqual(conflict.returncode, 1)
        self.assertEqual(conflict.stdout, "")
        self.assertIn("operation.conflict", conflict.stderr)
        self.assertEqual(journals[0].read_bytes(), before)
        self.assertEqual(len(rows_path.read_text().splitlines()), 2)

    def test_interrupted_admission_and_torn_completion_never_resend(self):
        # Die in a real CLI process, after the running claim/owner insert, before provider work.
        crash = '''
import os, sys
from terminal_planner.architect import FixtureArchitect
from terminal_planner.cli import main
FixtureArchitect.send = lambda *a, **k: os._exit(91)
main(sys.argv[1:])
'''
        cmd = self.command()
        result = subprocess.run([sys.executable, "-c", crash, *cmd[3:]], capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 91, result.stderr)
        journal, = self.state.rglob("operations.jsonl")
        with journal.open("ab") as stream:
            stream.write(b'{"operation_id":"submission-1","state":"completed"')
        before = journal.read_bytes()
        result = self.run_exec()
        self.assertEqual(result.returncode, 3, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["model"]["status"], "indeterminate")
        self.assertTrue(data["replayed"])
        self.assertEqual(journal.read_bytes(), before)
        self.assertEqual(len((journal.parent / "transcript.jsonl").read_text().splitlines()), 1)
        result = self.run_exec("--operation-id", "new-id")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("operation.store_invalid", result.stderr)

    def test_accepted_and_accepting_records_do_not_start_a_provider(self):
        self.command()  # create the goal file
        store = ArchitectStore(self.project, root=self.state / "architect" / "test")
        service = ApplicationService(FakeArchitect(store))
        request = replace(service.new_request("Plan a small useful change"), operation_id="submission-1")
        service.accept_message(request)
        for accepting in (False, True):
            if accepting:
                rows = service.operations_path.read_bytes().splitlines(keepends=True)
                service.operations_path.write_bytes(rows[0])
            before = service.operations_path.read_bytes()
            result = self.run_exec()
            self.assertEqual(result.returncode, 3, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data["message_id"], request.message_id)
            self.assertEqual(data["conversation_id"], request.conversation_id)
            self.assertEqual(data["model"]["status"], "indeterminate")
            self.assertEqual(service.operations_path.read_bytes(), before)
            self.assertEqual(len(store.transcript()), 1)

    def test_usage_and_store_errors_never_print_completed_json(self):
        cmd = self.command()
        cases = [cmd[:cmd.index("--operation-id")] + cmd[cmd.index("--operation-id") + 2:],
                 cmd + ["--goal", str(self.root / "missing")],
                 cmd + ["--goal", str(self.root)]]
        for argv in cases:
            result = subprocess.run(argv, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertFalse(self.state.exists())
        for raw in (b"", b"   \n", b"\xff", b"hello\x00world", b"x" * ((1 << 20) + 1)):
            (self.root / "goal.md").write_bytes(raw)
            result = self.run_exec()
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertFalse(self.state.exists())
        (self.root / "goal.md").write_text("hello")
        store = ArchitectStore(self.project, root=self.state / "architect" / "test")
        (store.directory / "operations.jsonl").write_text("not json\n")
        result = self.run_exec()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("operation.store_invalid", result.stderr)
        self.assertEqual(store.transcript(), [])

    def test_cli_reports_failed_partial_and_awaiting_owner_without_inferred_checks(self):
        self.command()
        store = ArchitectStore(self.project, root=self.state / "architect" / "test")
        architect = FakeArchitect(store)
        service = ApplicationService(architect)
        for status, child_category, code in (("failed", None, 1), ("partial", None, 1),
                                             ("completed", "failed/refused", 1),
                                             ("completed", "awaiting_owner", 4),
                                             ("failed", "running", 3)):
            with self.subTest(status=status, child=child_category):
                operation_id = status + str(child_category)
                architect.result.status = status
                result = service.submit_message(operation_id, "Plan a small useful change")
                if child_category:
                    child = ToolResult("child-" + operation_id, "zplan_plan", child_category,
                                       parent_operation_id=operation_id)
                    with service.operations_path.open("a") as stream:
                        stream.write(json.dumps({"operation_id": child.operation_id, "kind": "architect_tool",
                                                 "parent_operation_id": operation_id, "state": "terminal",
                                                 "result": asdict(child)}) + "\n")
                output = self.run_exec("--operation-id", operation_id)
                self.assertEqual(output.returncode, code, output.stderr)
                data = json.loads(output.stdout)
                self.assertEqual(data["model"]["status"], status)
                self.assertEqual(data["verification"]["state"], "not_run")
                self.assertEqual(data["merge"]["state"], "not_requested")
                self.assertEqual(data["turn_id"], result.turn_id)

    def test_cli_replay_scrubs_structured_credentials_without_rewriting_legacy_evidence(self):
        self.command()
        store = ArchitectStore(self.project, root=self.state / "architect" / "test")
        service = ApplicationService(FakeArchitect(store))
        parent = service.submit_message("submission-1", "Plan a small useful change")
        credentials = {key: "synthetic-plain-" + str(index) for index, key in enumerate(
            ("password", "api_key", "OPENAI_API-KEY", "access_token", "client_secret", "Authorization", "token"))}
        detail = {"nested": [{**credentials, "api_keys": ["synthetic-composite-value"],
                              "refresh_token": {"value": "synthetic-nested-credential"},
                              "node": "worker", "attempt": 2, "ready": True}], "status": "accepted",
                  "usage": {"input_tokens": 12, "output_tokens": 4, "cached_input_tokens": 3}}
        from terminal_planner.delivery import Token
        detail["rows"] = [{"token": asdict(Token("M1", 1, 1, "run-1", "failed", None, "pending"))},
                          {"token": None}, {"token": {"value": "synthetic-token-object"}}]
        child = ToolResult("legacy-child", "zplan_plan", "completed", parent_operation_id=parent.operation_id,
                           conversation_id=parent.conversation_id, turn_id=parent.turn_id, detail=detail)
        with service.operations_path.open("a") as stream:
            stream.write(json.dumps({"operation_id": child.operation_id, "kind": "architect_tool",
                                     "parent_operation_id": parent.operation_id, "state": "terminal",
                                     "result": asdict(child)}) + "\n")
        before = service.operations_path.read_bytes()
        output = self.run_exec()
        self.assertEqual(output.returncode, 0, output.stderr)
        data = json.loads(output.stdout)
        self.assertTrue(data["replayed"])
        for secret in [*credentials.values(), "synthetic-composite-value", "synthetic-nested-credential",
                       "synthetic-token-object"]:
            self.assertNotIn(secret, output.stdout + output.stderr)
        shown = data["children"][0]["detail"]
        self.assertEqual(shown["status"], "accepted")
        self.assertEqual(shown["rows"][:2], detail["rows"][:2])
        self.assertEqual(shown["usage"], detail["usage"])
        self.assertEqual({key: shown["nested"][0][key] for key in ("node", "attempt", "ready")},
                         {"node": "worker", "attempt": 2, "ready": True})
        self.assertEqual(set(shown["nested"][0]), set(detail["nested"][0]))
        self.assertLess(len(output.stdout.encode()), 256 * 1024)
        self.assertEqual(service.operations_path.read_bytes(), before)

    def test_completed_tool_dispatch_of_a_running_graph_is_not_overall_completion(self):
        from test_application_dispatch import ScriptProvider, plan_tool
        from terminal_planner.engine import FixtureEngine, SliceEnded
        from terminal_planner.tui.controller import Controller
        class ContinuingEngine(FixtureEngine):
            def output(self, authority):
                # FixtureEngine has saved its real receipt, but transport has no terminal result yet.
                raise SliceEnded()
        provider = ScriptProvider(self.root, self.project, [plan_tool()])
        controller = Controller.for_project(self.project, self.state, fixture_id="test",
                                            engine_factory=lambda *_: ContinuingEngine())
        self.addCleanup(controller.stop)
        controller.start()
        service = ApplicationService(provider.architect, controller=controller)
        result = service.submit_message("ongoing", "Plan a small useful change")
        projection = service.message_outcome(result)
        self.assertEqual(projection["model"]["status"], "completed")
        self.assertEqual(projection["children"][0]["category"], "completed", projection)
        self.assertEqual(projection["children"][0]["detail"]["dispatch"]["state"], "active_run")
        self.assertEqual(projection["exit_code"], 3)
        reopened = ApplicationService(provider.architect)
        self.assertEqual(reopened.message_outcome(reopened.submit_message("ongoing", "Plan a small useful change"))
                         ["exit_code"], 3)
        self.assertEqual(len(provider.rows("calls")), 1)

    def test_provider_exception_after_dispatch_preserves_aggregate_exit_and_replay(self):
        # Fault only the external provider/engine transport; admission, dispatch and persistence stay real.
        script = '''
import sys
from terminal_planner.architect import FixtureArchitect
from terminal_planner.engine import FixtureEngine, SliceEnded
from terminal_planner.cli import main
original = FixtureArchitect.send
def fail(self, *args, **kwargs):
    original(self, *args, **kwargs)
    raise RuntimeError("provider transport failed: sk-syntheticabcdefghijklmnop")
def continuing(self, authority):
    raise SliceEnded()
FixtureArchitect.send = fail
FixtureEngine.output = continuing
raise SystemExit(main(sys.argv[1:]))
'''
        cmd = self.command()
        first = subprocess.run([sys.executable, "-c", script, *cmd[3:]],
                               capture_output=True, text=True, timeout=30)
        self.assertEqual(first.returncode, 3, first.stderr)
        data = json.loads(first.stdout)
        self.assertEqual(data["model"]["status"], "failed")
        self.assertIn("provider transport failed", data["model"]["failure"])
        self.assertNotIn("sk-syntheticabcdefghijklmnop", first.stdout + first.stderr)
        self.assertFalse(data["replayed"])
        self.assertEqual(data["children"][0]["detail"]["dispatch"]["state"], "active_run")
        self.assertEqual(data["verification"]["state"], "not_run")
        self.assertEqual(data["merge"]["state"], "not_requested")
        journal, = self.state.rglob("operations.jsonl")
        before = journal.read_bytes()
        replay = self.run_exec()
        self.assertEqual(replay.returncode, 3, replay.stderr)
        repeated = json.loads(replay.stdout)
        self.assertTrue(repeated["replayed"])
        for key in ("operation_id", "message_id", "conversation_id", "turn_id", "model"):
            self.assertEqual(repeated[key], data[key])
        self.assertEqual(journal.read_bytes(), before)

    def test_production_cli_composition_uses_scripted_provider_and_replays_without_probes(self):
        from test_application_dispatch import ScriptProvider
        provider = ScriptProvider(self.root, self.project, [])
        scenario_path = provider.root / "scenario.json"
        scenario = json.loads(scenario_path.read_text())
        scenario["help"] = "--json --sandbox --cd --model --config"
        scenario_path.write_text(json.dumps(scenario))
        script = '''
import os, sys
from pathlib import Path
from terminal_planner import setup
from terminal_planner.cli import main
provider = Path(sys.argv[1])
def probe():
    if os.environ.get("NO_PROBES"):
        raise AssertionError("replay must not prepare a provider")
    return provider
setup.check_installation = probe
setup.tool_paths = lambda *a: (provider / "unused-engine", provider / "codex")
setup.native_environment = lambda: {"PATH": os.environ["PATH"], "CODEX_HOME": str(provider / "home")}
raise SystemExit(main(sys.argv[2:]))
'''
        cmd = self.command()
        argv = cmd[3:cmd.index("--fixture")]
        env = dict(os.environ, XDG_DATA_HOME=str(self.root / "data"), XDG_CONFIG_HOME=str(self.root / "config"))
        command = [sys.executable, "-c", script, str(provider.root), *argv]
        first = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(first.returncode, 0, first.stderr)
        data = json.loads(first.stdout)
        journal, = (self.root / "data").rglob("operations.jsonl")
        before = journal.read_bytes()
        second = subprocess.run(command, env=dict(env, NO_PROBES="1"), capture_output=True, text=True, timeout=30)
        self.assertEqual(second.returncode, 0, second.stderr)
        replay = json.loads(second.stdout)
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["turn_id"], data["turn_id"])
        self.assertEqual(journal.read_bytes(), before)
        self.assertEqual(len(provider.rows("calls")), 1)
        self.assertEqual(len(provider.rows("mcp_calls")), 2)
        rows = [json.loads(line) for line in (journal.parent / "transcript.jsonl").read_text().splitlines()]
        self.assertEqual([row["role"] for row in rows], ["owner", "architect"])
        self.assertEqual(rows[0]["turn_id"], rows[1]["turn_id"])

    def test_fixture_requires_neither_textual_nor_provider_auth(self):
        script = '''
import importlib.abc, sys
class NoScreen(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname == "textual" or fullname.startswith("textual.") or fullname == "terminal_planner.tui.app":
            raise AssertionError("screen dependency: " + fullname)
sys.meta_path.insert(0, NoScreen())
from terminal_planner import setup, architect
from terminal_planner.cli import main
def forbidden(*a, **k):
    raise AssertionError("provider/auth boundary reached")
setup.native_environment = setup.check_installation = architect.check_home = architect.verify_cli = forbidden
raise SystemExit(main(sys.argv[1:]))
'''
        cmd = self.command()
        result = subprocess.run([sys.executable, "-S", "-c", script, *cmd[3:]],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["model"]["status"], "completed")


class SubmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.store = ArchitectStore(root, root=root / "state")
        self.architect = FakeArchitect(self.store)
        self.service = ApplicationService(self.architect)

    def test_snapshot_identity_and_fingerprint_survive_reopen_and_text_conflict(self):
        request = replace(self.service.new_request("hello", {"revision": 17}), operation_id="stable")
        self.service.send_message(request)
        before = self.service.operations_path.read_bytes()
        other = ApplicationService(self.architect)
        result = other.submit_message("stable", "hello")
        self.assertEqual((result.message_id, result.turn_id, result.conversation_id),
                         (request.message_id, request.turn_id, request.conversation_id))
        self.assertEqual(self.architect.calls[0]["snapshot"], {"revision": 17})
        with self.assertRaises(Blocked) as error:
            other.submit_message("stable", "changed")
        self.assertEqual(error.exception.family, "operation.conflict")
        self.assertEqual(other.operations_path.read_bytes(), before)
        self.assertEqual(len(self.architect.calls), 1)
        self.assertEqual(len(self.store.transcript()), 1)

    def test_concurrent_same_key_claims_one_provider_call_and_one_owner_row(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        original = self.architect.send
        def held(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("test did not release provider")
            return original(*args, **kwargs)
        self.architect.send = held
        answers = []
        thread = threading.Thread(target=lambda: answers.append(self.service.submit_message("same", "hello")))
        thread.start()
        try:
            self.assertTrue(entered.wait(5))
            replay = ApplicationService(self.architect).submit_message("same", "hello")
            self.assertEqual(replay.status, "indeterminate")
            with self.assertRaises(Blocked) as error:
                ApplicationService(self.architect).submit_message("same", "different")
            self.assertEqual(error.exception.family, "operation.conflict")
        finally:
            release.set()
            thread.join(5)
        self.assertEqual(len(self.architect.calls), 1)
        self.assertEqual(len(self.store.transcript()), 1)
        self.assertEqual(answers[0].message_id, replay.message_id)

    def test_parent_child_exit_precedence_and_bounded_scrubbed_projection(self):
        result = self.service.submit_message("parent", "hello")
        secret = "sk-syntheticabcdefghijklmnop"
        children = []
        def child(category):
            value = ToolResult("child-" + str(len(children)), "zplan_plan", category,
                               parent_operation_id=result.operation_id,
                               conversation_id=result.conversation_id, turn_id=result.turn_id,
                               detail={"nested": [secret, "x" * 10000]})
            children.append(value)
            with self.service.operations_path.open("a") as stream:
                stream.write(json.dumps({"operation_id": value.operation_id, "kind": "architect_tool",
                                         "parent_operation_id": result.operation_id, "state": "terminal",
                                         "result": asdict(value)}) + "\n")
        def check(parent, expected):
            projection = self.service.message_outcome(replace(result, status=parent))
            self.assertEqual(projection["model"]["status"], parent)
            self.assertEqual(projection["exit_code"], expected)
            self.assertEqual(projection["verification"]["state"], "not_run")
            self.assertEqual(projection["merge"]["state"], "not_requested")
            encoded = json.dumps(projection)
            self.assertNotIn(secret, encoded)
            self.assertLess(len(encoded), 256 * 1024)
        check("completed", 0)
        for status in ("failed", "partial", "refused", "cancelled", "lost_session"):
            check(status, 1)
        for _ in range(33):
            child("completed")
        child("failed/refused")  # even children omitted from presentation determine the exit
        check("completed", 1)
        child("awaiting_owner")
        check("failed", 4)
        child("indeterminate")
        check("completed", 3)
        check("running", 3)

    def test_failed_partial_terminal_replay_keeps_factual_model_status(self):
        for status in ("failed", "partial", "refused"):
            self.architect.result.status = status
            self.architect.result.partial = "unfinished answer"
            result = self.service.submit_message(status, "hello")
            replay = ApplicationService(self.architect).submit_message(status, "hello")
            self.assertEqual(replay.status, status)
            self.assertEqual(replay.turn.partial, result.turn.partial)
            self.assertEqual(self.service.message_outcome(replay)["exit_code"], 1)

    def test_accepted_submission_is_not_resent_but_explicit_tui_dispatch_still_works(self):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            store = ArchitectStore(Path(root), root=Path(root) / "state")
            architect = FakeArchitect(store)
            service = ApplicationService(architect)
            request = service.new_request("hello", {"revision": 1})
            service.accept_message(request)
            result = service.submit_message(request.operation_id, "hello")
            self.assertEqual((result.status, result.replayed), ("indeterminate", True))
            self.assertEqual(architect.calls, [])
            self.assertEqual(service.send_message(request).status, "completed")
            replay = ApplicationService(architect).submit_message(request.operation_id, "hello")
            self.assertEqual(replay.message_id, request.message_id)
            self.assertEqual(replay.conversation_id, request.conversation_id)
            self.assertEqual(len(architect.calls), 1)
            self.assertEqual(len(store.transcript()), 1)
