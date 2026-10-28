"""A3b: the architect's read tools as a stdio MCP server, driven through a real subprocess over a temporary git repo.

Interpretations (the task leaves them open):
- Bad tool arguments (missing, wrongly typed or unknown) and an unknown tool name are JSON-RPC errors -32602, not tool
  errors: only a `Blocked` of project_read becomes `isError: true`, so no new catalog family is raised.
- A request object without `id` is a notification (no reply, even for an unknown method)."""

import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import unittest

import terminal_planner
from terminal_planner import bridge, project_read

ROOT = Path(__file__).resolve().parent.parent
IDENTITY = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@localhost",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@localhost"}
CODE = ("import sys; sys.path.insert(0, %s); from terminal_planner.architect_tools import main; "
        "sys.exit(main(sys.argv[1:]))" % json.dumps(str(ROOT)))


class ToolsTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.project = Path(temp.name).resolve() / "proj"
        self.project.mkdir()
        (self.project / "a.py").write_text("one\ntwo\nthree\n")
        (self.project / ".env").write_text("TOKEN=abc\n")
        env = {**os.environ, **IDENTITY}
        subprocess.run(["git", "-C", str(self.project), "init", "-q", "-b", "main"], check=True, env=env)
        subprocess.run(["git", "-C", str(self.project), "add", "-A"], check=True, env=env)  # the tools read HEAD
        subprocess.run(["git", "-C", str(self.project), "commit", "-q", "-m", "x"], check=True, env=env)
        self.proc = subprocess.Popen([sys.executable, "-I", "-c", CODE, "--project", str(self.project)],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self.close)
        self.next_id = 0

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=10)
        self.proc.stdout.close()
        self.proc.stderr.close()

    def raw(self, data):
        self.proc.stdin.write(data)
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline())

    def rpc(self, method, params=None):
        self.next_id += 1
        message = {"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params or {}}
        reply = self.raw(json.dumps(message).encode() + b"\n")
        self.assertEqual(reply["id"], self.next_id)
        return reply

    def call(self, name, arguments):
        return self.rpc("tools/call", {"name": name, "arguments": arguments})

    # C1
    def test_protocol_and_a_read(self):
        reply = self.rpc("initialize", {"protocolVersion": "2025-03-26"})
        self.assertEqual(reply["result"], {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}},
                                           "serverInfo": {"name": "zplan", "version": terminal_planner.__version__}})
        # Codex's MCP client (rmcp) refuses the handshake without serverInfo.version (live check 2026-10-25).
        self.proc.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        tools = self.rpc("tools/list")["result"]["tools"]
        self.assertEqual([t["name"] for t in tools],
                         ["zplan_list_files", "zplan_read_file", "zplan_search", "zplan_state", "zplan_state_update",
                          "zplan_status", "zplan_start",
                          "zplan_stop", "zplan_approve_plan", "zplan_resume", "zplan_rebrief", "zplan_edit_plan",
                          "zplan_merge", "zplan_propose_commit"])
        for tool in tools:
            self.assertEqual(tool["inputSchema"]["type"], "object")
        result = self.call("zplan_read_file", {"path": "a.py"})["result"]
        self.assertNotIn("isError", result)
        self.assertEqual(json.loads(result["content"][0]["text"]),
                         project_read.read_file(str(self.project), str(self.project), "a.py"))
        listed = json.loads(self.call("zplan_list_files", {})["result"]["content"][0]["text"])
        self.assertEqual(listed["paths"], ["a.py"])
        hits = json.loads(self.call("zplan_search", {"text": "two"})["result"]["content"][0]["text"])
        self.assertEqual(hits["hits"][0]["line"], 2)

    # C2
    def test_a_refusal_is_a_tool_error_and_the_server_goes_on(self):
        result = self.call("zplan_read_file", {"path": ".env"})["result"]
        self.assertTrue(result["isError"])
        self.assertTrue(result["content"][0]["text"].startswith("read.credential: "))
        result = self.call("zplan_read_file", {"path": "a.py", "root": "/"})["result"]
        self.assertTrue(result["content"][0]["text"].startswith("read.outside_project: "))
        self.assertEqual(self.rpc("ping")["result"], {})

    # A8a C4: the STATE tools work over the real server without a Controller; a refusal is a tool error.
    def test_state_tools_without_a_controller(self):
        good = "".join("## %s\n" % name for name in ("Now", "Next", "Open", "Decisions"))
        self.assertEqual(self.call("zplan_state", {})["result"]["content"][0]["text"], "")
        self.assertNotIn("isError", self.call("zplan_state_update", {"text": good})["result"])
        self.assertEqual(self.call("zplan_state", {})["result"]["content"][0]["text"], good)
        refused = self.call("zplan_state_update", {"text": good + "## Fifth\n"})["result"]
        self.assertTrue(refused["isError"])
        self.assertEqual(self.call("zplan_state", {})["result"]["content"][0]["text"], good)

    def test_protocol_errors_keep_the_loop_going(self):
        self.assertEqual(self.rpc("nope")["error"]["code"], -32601)
        self.assertEqual(self.raw(b"{not json\n")["error"]["code"], -32700)
        big = self.raw(b'{"jsonrpc":"2.0","id":1,"method":"ping","params":{"x":"' + b"a" * (1 << 20) + b'"}}\n')
        self.assertEqual(big["error"]["code"], -32700)
        self.assertEqual(self.call("zplan_read_file", {})["error"]["code"], -32602)
        self.assertEqual(self.call("zplan_read_file", {"path": 1})["error"]["code"], -32602)
        self.assertEqual(self.call("zplan_write_file", {})["error"]["code"], -32602)
        self.assertEqual(self.rpc("ping")["result"], {})


class ActionToolsTest(unittest.TestCase):
    """A5t1 C2: the action tools over the real MCP server and a live `bridge.Endpoint` (a stand-in for the
    Controller). Every result, error and timeout must name the request id the tool used."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.project = Path(temp.name).resolve() / "proj"
        self.project.mkdir()
        subprocess.run(["git", "-C", str(self.project), "init", "-q", "-b", "main"], check=True,
                       env={**os.environ, **IDENTITY})
        self.seen = []
        self.answer = ({"done": True}, None)

        def dispatch(request):
            self.seen.append(request)
            return self.answer

        self.endpoint = bridge.Endpoint(dispatch)
        self.addCleanup(self.endpoint.close)
        self.path = self.endpoint.start()
        self.proc = None
        self.next_id = 0

    def server(self, controller):
        argv = [sys.executable, "-I", "-c", CODE, "--project", str(self.project)]
        if controller is not None:
            argv += ["--controller", controller]
        self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self.close)
        return self.proc

    def close(self):
        if self.proc is None:
            return
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            self.proc.kill()
        for pipe in (self.proc.stdout, self.proc.stderr):
            try:
                pipe.close()
            except OSError:
                pass
        self.proc = None

    def rpc(self, method, params=None):
        self.next_id += 1
        message = {"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params or {}}
        self.proc.stdin.write(json.dumps(message).encode() + b"\n")
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline())

    def send(self, name, arguments):
        """Write one `tools/call` and return its id, without reading the reply (the caller matches it)."""
        self.next_id += 1
        message = {"jsonrpc": "2.0", "id": self.next_id, "method": "tools/call",
                   "params": {"name": name, "arguments": arguments}}
        self.proc.stdin.write(json.dumps(message).encode() + b"\n")
        self.proc.stdin.flush()
        return self.next_id

    @staticmethod
    def pump(stream, box):
        for line in iter(stream.readline, b""):
            if line.strip():
                box.put(json.loads(line))

    def action(self, name, arguments):
        result = self.rpc("tools/call", {"name": name, "arguments": arguments})["result"]
        return json.loads(result["content"][0]["text"]), bool(result.get("isError"))

    def test_a_success_names_the_id_and_reaches_the_controller_with_the_same_request(self):
        self.server(self.path)
        payload, broken = self.action("zplan_start", {"milestone": "M1", "revision": 2})
        self.assertFalse(broken)
        self.assertEqual(payload["tool"], "zplan_start")
        self.assertEqual(payload["ok"], {"done": True})
        self.assertEqual(self.seen[-1], {"id": payload["id"], "tool": "zplan_start",
                                         "args": {"milestone": "M1", "revision": 2}})

    def test_a5t2a_the_approve_resume_and_rebrief_tools_reach_the_controller_with_the_id(self):
        """A5t2a/A5t2b C2: approve, resume, rebrief, edit_plan and merge are action tools like start and stop; each
        whole request (token and the full plan included) travels to the Controller and its result names the request
        id it used."""
        self.server(self.path)
        token = {"milestone": "M1", "plan_revision": 1, "attempt": 1, "run_id": "r1", "status": "failed",
                 "outcome": None, "delivery": "none"}
        proposal = {"requirements": [], "milestones": [], "slices": []}
        for name, arguments in (("zplan_approve_plan", {"revision": 1}),
                                ("zplan_resume", {"milestone": "M1", "token": token}),
                                ("zplan_rebrief", {"milestone": "M1", "token": token, "note": "use the fixture path"}),
                                ("zplan_edit_plan", {"revision": 1, "plan": proposal}),
                                ("zplan_merge", {"milestone": "M1", "token": token})):
            with self.subTest(tool=name):
                payload, broken = self.action(name, arguments)
                self.assertFalse(broken)
                self.assertEqual(payload["tool"], name)
                self.assertEqual(self.seen[-1], {"id": payload["id"], "tool": name, "args": arguments})

    def test_a_refusal_is_a_tool_error_that_still_names_the_id(self):
        self.answer = (None, {"family": "autonomy.ask", "message": "владелец"})
        self.server(self.path)
        payload, broken = self.action("zplan_stop", {"milestone": "M1", "run_id": "r-1"})
        self.assertTrue(broken)
        self.assertEqual(payload["error"], {"family": "autonomy.ask", "message": "владелец"})
        self.assertTrue(payload["id"])

    def test_without_a_controller_the_tools_answer_unavailable(self):
        self.server(None)
        payload, broken = self.action("zplan_status", {})
        self.assertTrue(broken)
        self.assertEqual(payload["error"]["family"], "architect.controller_unavailable")
        self.assertTrue(payload["id"])

    def test_a_held_action_does_not_hold_up_a_later_status(self):
        """Regression (A5t1 C2): an action waiting for the Controller must not delay a later `zplan_status` - the
        MCP loop keeps reading and answers the status while the action is still held."""
        entered, gate = threading.Event(), threading.Event()

        def dispatch(request):
            self.seen.append(request)
            if request["tool"] == "zplan_start":
                entered.set()
                gate.wait(10)
            return {"held": request["tool"]}, None

        endpoint = bridge.Endpoint(dispatch)
        self.addCleanup(endpoint.close)
        self.server(endpoint.start())
        replies = queue.Queue()
        start_pump = threading.Thread(target=self.pump, args=(self.proc.stdout, replies), daemon=True)
        start_pump.start()
        start_id = self.send("zplan_start", {"milestone": "M1", "revision": 1})
        self.assertTrue(entered.wait(5))          # the action is admitted and waiting for the Controller
        status_id = self.send("zplan_status", {})
        first = replies.get(timeout=5)            # the status answers at once, before the held action ends
        self.assertEqual(first["id"], status_id)
        self.assertIn("result", first)
        gate.set()
        second = replies.get(timeout=10)
        self.assertEqual(second["id"], start_id)
        self.assertIn("result", second)


if __name__ == "__main__":
    unittest.main()
