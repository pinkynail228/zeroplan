"""Architect adapter: argv/env, session store, JSONL turns, failures and cancel, driven by a scripted fake codex."""

import json
import os
import re
import shutil
from pathlib import Path
import stat
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from terminal_planner import architect
from terminal_planner.architect import (Architect, ArchitectStore, build_argv, build_preamble, build_update,
                                        mcp_overrides, mcp_servers_config, verify_cli)
from terminal_planner.authority import Blocked

# The server listing every turn runs first (`codex mcp list --json`), answered by every fake codex without counting it
# as a turn call (it logs to mcp_calls.jsonl). Scenario keys: `mcp` = one listing (default: zplan enabled only),
# `mcp_lists` = one listing per call in order (the last repeats; a string is sent raw), `mcp_exit` = a failing exit,
# `mcp_hang` = seconds to sleep before answering. Needs `json`, `os`, `sys`, `time` and `here`, `scenario` in scope.
MCP_LIST = r'''if sys.argv[1:3] == ["mcp", "list"]:
    log = os.path.join(here, "mcp_calls.jsonl")
    seen = sum(1 for _ in open(log)) if os.path.exists(log) else 0
    with open(log, "a") as stream:
        stream.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(), "env": dict(os.environ)}) + "\n")
    time.sleep(scenario.get("mcp_hang", 0))
    if scenario.get("mcp_exit"):
        sys.exit(scenario["mcp_exit"])
    lists = scenario.get("mcp_lists") or [scenario.get("mcp", [{"name": "zplan", "enabled": True}])]
    chosen = lists[min(seen, len(lists) - 1)]
    sys.stdout.write(chosen if isinstance(chosen, str) else json.dumps(chosen))
    sys.exit(0)
'''

FAKE = r'''#!%(python)s
import json, os, signal, subprocess, sys, time
here = os.path.dirname(os.path.abspath(__file__))
scenario = json.load(open(os.path.join(here, "scenario.json")))
if "--help" in sys.argv:
    print(scenario.get("help", ""))
    sys.exit(scenario.get("help_exit", 0))
''' + MCP_LIST + r'''calls = os.path.join(here, "calls.jsonl")
index = sum(1 for _ in open(calls)) if os.path.exists(calls) else 0
prompt = sys.stdin.read()
with open(calls, "a") as stream:
    stream.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(), "env": dict(os.environ), "stdin": prompt}) + "\n")
step = scenario["steps"][min(index, len(scenario["steps"]) - 1)]
for line in step.get("lines", []):
    sys.stdout.write((line if isinstance(line, str) else json.dumps(line)) + "\n")
    sys.stdout.flush()
if step.get("stderr"):
    sys.stderr.write(step["stderr"])
    sys.stderr.flush()
if step.get("child"):
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    with open(step["child"], "w") as stream:
        stream.write("%%d %%d" %% (os.getpid(), child.pid))
if step.get("hang"):
    time.sleep(step["hang"])
if step.get("kill_self"):
    os.kill(os.getpid(), signal.SIGKILL)
sys.exit(step.get("exit", 0))
'''

THREAD = "0199aaaa-bbbb-cccc-dddd-eeeeffff0001"
OK = [{"type": "thread.started", "thread_id": THREAD}, {"type": "turn.started"},
      {"type": "item.completed", "item": {"id": "item_0", "type": "agent_message", "text": "Привет."}},
      {"type": "turn.completed", "usage": {"input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 5}}]

# The plain attempt token of M1 as `app.token_fields` flattens it; the chat snapshot of a turn carries it verbatim.
TOKEN = {"milestone": "M1", "plan_revision": 2, "attempt": 1, "run_id": "run-1", "status": "running",
         "outcome": None, "delivery": "none"}
SNAPSHOT = {"project": "proj", "branch": "main", "revision": 2,
            "plan_state": {"status": "approved", "override": False},
            "milestones": [{"id": "M1", "state": "running", "token": TOKEN},
                           {"id": "M2", "state": "ready", "token": None}]}


def completes(text):
    """The JSONL lines of a turn that completes with `text` as its final agent message."""
    return [{"type": "thread.started", "thread_id": THREAD}, {"type": "turn.started"},
            {"type": "item.completed", "item": {"id": "item_0", "type": "agent_message", "text": text}},
            {"type": "turn.completed", "usage": {"output_tokens": 3}}]


def goal(body):
    return "```zplan-goal\n" + body + "\n```"


def answer(milestone, body):
    return "```zplan-answer " + milestone + "\n" + body + "\n```"


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def tree(root):
    return sorted((str(p.relative_to(root)), p.read_bytes() if p.is_file() else None) for p in Path(root).rglob("*"))


class ArchitectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="zs-arch-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        home = self.root / "home"
        self.data = self.root / "data"
        patcher = patch.dict(os.environ, {"HOME": str(home), "XDG_DATA_HOME": str(self.data), "XDG_CONFIG_HOME": str(self.root / "config")})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.project = self.root / "proj"
        self.project.mkdir()
        (self.project / "README.md").write_text("hello\n")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.codex = self.bin / "codex"
        self.codex.write_text(FAKE % {"python": sys.executable})
        self.codex.chmod(0o755)
        home = self.root / "codex-home"
        home.mkdir()
        (home / "auth.json").write_text("{}\n")  # a login: the turn home check (R-5) judges presence only
        self.env = {"PATH": os.environ.get("PATH", ""), "CODEX_HOME": str(home), "ZPLAN_MARK": "kept"}
        self.events = []
        self.script([{"lines": OK}])

    def script(self, steps, **extra):
        (self.bin / "scenario.json").write_text(json.dumps({"steps": steps, **extra}))

    def calls(self):
        path = self.bin / "calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def architect(self, **kwargs):
        return Architect(self.codex, self.env, self.project, "gpt-6.1-sol", "high", on_event=self.events.append, **kwargs)

    def store_dir(self):
        return ArchitectStore(self.project).directory

    # A1
    def test_first_and_resume_argv_exact_env_and_cwd(self):
        arch = self.architect()
        first = arch.send("Что делать?", snapshot={"project": "proj", "branch": "main"})
        self.assertEqual(first.status, "completed")
        second = arch.send("А дальше?")
        self.assertEqual(second.status, "completed")
        one, two = self.calls()
        self.assertEqual(one["argv"], ["exec", "--json", "-s", "read-only", "-C", str(self.project), "-m", "gpt-6.1-sol",
                                       "-c", "model_reasoning_effort=high", "-c", 'approval_policy="never"',
                                       *mcp_overrides(str(self.project)), "-"])
        self.assertEqual(two["argv"], ["exec", "resume", THREAD, "--json", "-m", "gpt-6.1-sol",
                                       "-c", 'sandbox_mode="read-only"', "-c", 'approval_policy="never"',
                                       "-c", "model_reasoning_effort=high", *mcp_overrides(str(self.project)), "-"])
        for call in (one, two):
            for flag in ("--last", "--ephemeral", "--full-auto", "--dangerously-bypass-approvals-and-sandbox",
                         "--yolo", "--add-dir", "danger-full-access", "workspace-write"):
                self.assertNotIn(flag, call["argv"])
            self.assertFalse([a for a in call["argv"] if a.startswith("--dangerously")])
            self.assertEqual(Path(call["cwd"]).resolve(), self.project)
            for key, value in self.env.items():
                self.assertEqual(call["env"].get(key), value)
        self.assertIn("lead delivery", one["stdin"])
        self.assertIn(architect.method(), one["stdin"])
        self.assertNotIn(architect.method(), two["stdin"])  # a resumed turn does not repeat the method
        self.assertTrue(one["stdin"].endswith("Что делать?"))
        # D-0: a resumed turn (saved thread id, so `build_update` not the preamble) still carries the draft
        # protocol and the state update, appended to the owner message.
        self.assertIn("Updated state snapshot (read-only):", two["stdin"])
        self.assertIn("```zplan-goal", two["stdin"])
        self.assertIn("```zplan-answer", two["stdin"])
        self.assertNotIn("You are the zplan architect", two["stdin"])
        self.assertTrue(two["stdin"].endswith("А дальше?"))

    # A3b C3
    def test_mcp_config_is_one_inline_table_and_escapes_the_project(self):
        """Interpretation: the argv value is TOML (Codex reads `-c` that way), so the test parses it with tomllib; the
        project path holds a quote, a backslash and a tab."""
        import tomllib
        project = '/tmp/we"ird\\dir\tx'
        for thread in (None, THREAD):
            argv = build_argv(self.codex, project, "gpt", "high", thread)
            configs = [a for a in argv if a.startswith("mcp_servers=")]
            self.assertEqual(len(configs), 1)
            server = tomllib.loads(configs[0])["mcp_servers"]
            self.assertEqual(list(server), ["zplan"])
            server = server["zplan"]
            self.assertEqual(server["command"], sys.executable)
            self.assertEqual(server["default_tools_approval_mode"], "approve")
            self.assertEqual(server["args"][:2], ["-I", "-c"])
            self.assertEqual(server["args"][3:], ["--project", project])
            self.assertTrue(server["args"][2].startswith("import sys; sys.path.insert(0, "))
            self.assertIn("architect_tools import main", server["args"][2])

    # A5t1 C2
    def test_the_mcp_config_carries_the_controller_socket_and_omits_it_without_one(self):
        """The architect's argv points its own MCP server at the live Controller's socket (`--controller`); without
        one the tool answers `architect.controller_unavailable` from the server itself."""
        import tomllib
        for thread, controller in ((None, None), (THREAD, None), (None, "/tmp/zs-bridge-abc/controller.sock")):
            with self.subTest(controller=controller):
                argv = build_argv(self.codex, self.project, "gpt", "high", thread, controller=controller)
                config = [a for a in argv if a.startswith("mcp_servers=")][0]
                args = tomllib.loads(config)["mcp_servers"]["zplan"]["args"]
                self.assertEqual(args[:2], ["-I", "-c"])
                self.assertEqual(args[3:5], ["--project", str(self.project)])
                if controller:
                    self.assertEqual(args[5:], ["--controller", controller])
                else:
                    self.assertEqual(args[5:], [])

    def test_the_prompt_lists_the_action_tools_and_says_the_controller_decides(self):
        """A5t1/A5t2a/A5t2b C5: every prompt that starts a turn (the preamble and the resumed-turn update) lists the
        tools and leaves the decision to the Controller, so an `autonomy.ask` is not a surprise; automatic actions
        follow the autonomy level."""
        for text in (build_preamble(SNAPSHOT), build_update(SNAPSHOT)):
            for name in ("zplan_status", "zplan_start", "zplan_stop", "zplan_approve_plan", "zplan_resume",
                         "zplan_rebrief", "zplan_edit_plan", "zplan_merge", "zplan_propose_commit"):
                self.assertIn(name, text)
            self.assertIn("merge", text)
            self.assertIn("the owner's", text)  # an approval over a rejected critic and every merge are the owner's
            self.assertIn("Controller", text)
            self.assertIn("autonomy", text)  # automatic actions follow the autonomy level

    def test_c5_tool_rules_name_edit_and_merge_but_no_override_or_reject(self):
        """A5t2b C4: TOOL_RULES names each A5t2b tool on its own line (edit_plan, merge), leaves an override, a
        rejection, a push, tags and deleting branches with unmerged work to the owner, and says automatic actions
        follow the autonomy level; no override or reject tool is offered (none exists)."""
        rules = architect.TOOL_RULES
        for name in ("zplan_approve_plan", "zplan_resume", "zplan_rebrief", "zplan_edit_plan", "zplan_merge"):
            self.assertEqual(sum(name in line for line in rules), 1, name)
        text = "\n".join(rules)
        for forbidden in ("zplan_override", "zplan_reject"):
            self.assertNotIn(forbidden, text)
        for owned in ("override", "reject", "push", "tags", "unmerged"):
            self.assertIn(owned, text)
        self.assertIn("autonomy level", text)
        self.assertIn("merge.critic_pending", text)  # the retry instruction is stated

    def test_c2_the_rules_forbid_asking_for_a_yes_in_the_chat_under_a_project_method_and_on_updates(self):
        """C2 K2: the rule that an action the level leaves to the owner is never asked for in the chat is in
        TOOL_RULES, so the first prompt under a project `zplan.architect.md` and the resumed-turn update carry it."""
        (self.project / "zplan.architect.md").write_text("# Our method\n- Small slices.")
        for text in (build_preamble(SNAPSHOT, self.project), build_update(SNAPSHOT)):
            self.assertIn("never ask for a yes in the chat", text)

    def test_a8_f4_the_rules_send_a_rejected_check_to_revise_and_keep_edit_for_the_owners_text(self):
        """A8 F4: the tool rules say to read the findings in zplan_status after a rejected check and call
        zplan_revise_plan naming them, and to use zplan_edit_plan only for an edit whose exact text the owner gave."""
        text = " ".join(" ".join(architect.TOOL_RULES).split())
        self.assertIn("After a rejected check, read the findings in zplan_status (plan.findings) and call it naming "
                      "them", text)
        self.assertIn("Use it only for an edit whose exact text the owner gave", text)

    def test_a10_b5_the_rules_forbid_an_approval_of_a_rejected_plan_and_point_to_the_card(self):
        """A10 B5: on review_exhausted the architect never calls zplan_approve_plan; it says the check rejected the
        plan and points to the card on the main screen; a revision it made that is rejected again is the owner's."""
        text = " ".join(" ".join(architect.TOOL_RULES).split())
        self.assertIn("When the plan status is review_exhausted never call it: say the check rejected the plan and "
                      "point to the card on the main screen", text)
        self.assertIn("A revision you made that the check rejects again is the owner's to decide", text)

    def mcp_calls(self):
        path = self.bin / "mcp_calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    # A3c C1 + C2
    def test_foreign_servers_are_disabled_in_the_turn_and_proved_off(self):
        """Interpretation: the listing is `codex mcp list --json` in the project directory with the turn's env; the
        first one carries only `features.plugins=false` and `features.apps=false`, the second the turn's own overrides. A name that needs TOML
        quoting (`odd name`) is quoted as a key. Both a new and a resumed turn are checked."""
        import tomllib
        listing = [{"name": "node_repl", "enabled": True}, {"name": "odd name", "enabled": True},
                   {"name": "off", "enabled": False}, {"name": "zplan", "enabled": True}]
        self.script([{"lines": OK}, {"lines": OK}], mcp_lists=[listing, [{"name": "zplan", "enabled": True}]] * 2)
        arch = self.architect()
        for _ in range(2):
            self.assertEqual(arch.send("привет").status, "completed")
        first, second = self.calls()
        self.assertEqual(second["argv"][:3], ["exec", "resume", THREAD])
        listings = self.mcp_calls()
        self.assertEqual(len(listings), 4)
        self.assertEqual(listings[0]["argv"], ["mcp", "list", "--json", "-c", "features.plugins=false", "-c", "features.apps=false"])
        for call in (first, second):
            argv = call["argv"]
            self.assertIn("features.plugins=false", argv)
            self.assertIn("features.apps=false", argv)
            config = [a for a in argv if a.startswith("mcp_servers=")]
            self.assertEqual(len(config), 1)
            servers = tomllib.loads(config[0])["mcp_servers"]
            self.assertEqual(servers["node_repl"], {"enabled": False})
            self.assertEqual(servers["odd name"], {"enabled": False})
            self.assertNotIn("off", servers)
            self.assertEqual(servers["zplan"]["default_tools_approval_mode"], "approve")
        self.assertEqual(listings[1]["argv"], ["mcp", "list", "--json", "-c", "features.plugins=false", "-c", "features.apps=false",
                                                 "-c", config[0]])
        for listing_call in listings:
            self.assertEqual(Path(listing_call["cwd"]).resolve(), self.project)
            self.assertEqual(listing_call["env"].get("ZPLAN_MARK"), "kept")

    def test_a_server_that_stays_enabled_refuses_the_turn_and_writes_nothing(self):
        """One case per way the proof can fail: the second listing still shows `node_repl`, zplan's own is missing,
        a non-zero exit, a timeout (LIST_TIMEOUT patched down), unparsable JSON and a listing of the wrong shape. Each
        is `architect.foreign_tools`, starts no turn process and leaves the store and transcript byte-identical."""
        zplan = {"name": "zplan", "enabled": True}
        node = {"name": "node_repl", "enabled": True}
        cases = [({"mcp_lists": [[node, zplan], [node, zplan]]}, "node_repl"),
                 ({"mcp_lists": [[node], [{"name": "node_repl", "enabled": False}]]}, "zplan"),
                 ({"mcp_exit": 3}, "3"), ({"mcp": "not json"}, "JSON"), ({"mcp": {"name": "zplan"}}, "shape"),
                 ({"mcp_hang": 5}, "timeout")]
        for extra, named in cases:
            with self.subTest(extra=extra):
                self.script([{"lines": OK}], **extra)
                arch = self.architect()
                before = tree(arch.store.directory) if arch.store.directory.exists() else None
                with patch.object(architect, "LIST_TIMEOUT", 2 if "mcp_hang" in extra else 10), \
                        self.assertRaises(Blocked) as raised:
                    arch.send("привет")
                self.assertEqual(raised.exception.family, "architect.foreign_tools")
                self.assertIn(named, str(raised.exception))
                self.assertEqual(self.calls(), [])
                after = tree(arch.store.directory) if arch.store.directory.exists() else None
                self.assertEqual([e for e in (after or []) if e[0] != "lock"], [e for e in (before or []) if e[0] != "lock"])
                (self.bin / "mcp_calls.jsonl").unlink(missing_ok=True)

    def test_verify_cli_requires_the_mcp_list_flags(self):
        self.script([], help="exec resume --json --sandbox --cd --model --config")
        self.assertEqual(verify_cli(self.codex, self.env), [])
        self.script([], help="exec resume --json --sandbox --cd --model")
        self.assertIn("mcp list --config", verify_cli(self.codex, self.env))

    def test_build_argv_rejects_option_injection(self):
        with self.assertRaises(Blocked):
            build_argv(self.codex, self.project, "gpt", "high", "--last")
        with self.assertRaises(Blocked):
            build_argv(self.codex, self.project, "-m", "high")

    # A2
    def test_thread_persisted_before_turn_finishes_and_reopened(self):
        self.script([{"lines": [OK[0], {"type": "turn.started"}], "exit": 3}, {"lines": OK[1:]}])
        arch = self.architect()
        result = arch.send("первое")
        self.assertEqual(result.status, "failed")
        self.assertEqual(json.loads((self.store_dir() / "session.json").read_text())["thread_id"], THREAD)
        reopened = self.architect()
        self.assertEqual(reopened.thread_id, THREAD)
        reopened.send("второе")
        self.assertEqual(self.calls()[1]["argv"][:3], ["exec", "resume", THREAD])

    def test_thread_persisted_when_process_is_killed(self):
        self.script([{"lines": [OK[0]], "kill_self": True}])
        result = self.architect().send("x")
        self.assertEqual(result.status, "failed")
        self.assertIn("signal", result.cause)
        self.assertEqual(self.architect().thread_id, THREAD)

    def test_thread_id_written_as_soon_as_event_arrives(self):
        seen = []

        def callback(event):
            if event["kind"] == "thread":
                seen.append(json.loads((self.store_dir() / "session.json").read_text())["thread_id"])

        Architect(self.codex, self.env, self.project, "m", "high", on_event=callback).send("x")
        self.assertEqual(seen, [THREAD])

    # A3
    def test_events_aggregated_and_noise_tolerated(self):
        big = "я" * (architect.MAX_TEXT + 500)
        lines = [OK[0], {"type": "turn.started"}, "not json at all", "[1, 2]", '{"no_type": 1}', {"type": "future.event", "x": 1},
                 {"type": "item.started", "item": {"id": "m1", "type": "agent_message", "text": ""}},
                 {"type": "item.updated", "item": {"id": "m1", "type": "agent_message", "text": "част"}},
                 {"type": "item.completed", "item": {"id": "m1", "type": "agent_message", "text": "Первое."}},
                 {"type": "item.started", "item": {"id": "c1", "type": "command_execution", "command": "ls", "status": "in_progress"}},
                 {"type": "item.completed", "item": {"id": "c1", "type": "command_execution", "command": "ls",
                                                     "aggregated_output": "a\n", "exit_code": 0, "status": "completed"}},
                 {"type": "item.completed", "item": {"id": "r1", "type": "reasoning", "text": "думаю"}},
                 {"type": "item.completed", "item": "broken"},
                 {"type": "item.completed", "item": {"id": "m2", "type": "agent_message", "text": big}},
                 {"type": "turn.completed", "usage": {"input_tokens": 7, "output_tokens": 3, "bad": "x", "flag": True}},
                 {"type": "turn.completed", "usage": {"input_tokens": 9, "output_tokens": 4}}]
        self.script([{"lines": lines, "stderr": "e" * 50000}])
        result = self.architect().send("вопрос")
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.messages[0], "Первое.")
        self.assertEqual(len(result.messages), 2)
        self.assertEqual(result.text, result.messages[-1])
        self.assertLess(len(result.text), architect.MAX_TEXT + 100)
        self.assertTrue(result.text.endswith("[truncated]"))
        self.assertEqual(result.usage, {"input_tokens": 9, "output_tokens": 4})   # the last report, not the sum
        self.assertEqual(result.malformed_lines, 4)   # not json, list, no type, broken item
        self.assertEqual(result.unknown_events, 1)
        self.assertLessEqual(len(result.stderr_tail), architect.MAX_STDERR)
        kinds = [e["kind"] for e in self.events]
        for kind in ("thread", "turn", "message", "command", "reasoning", "usage", "unknown"):
            self.assertIn(kind, kinds)
        self.assertTrue(all(len(e.get("text", "")) <= architect.MAX_EVENT_TEXT + 20 for e in self.events))
        session = json.loads((self.store_dir() / "session.json").read_text())
        self.assertEqual(session["usage"], {"input_tokens": 9, "output_tokens": 4})
        self.assertEqual(session["turns"], 1)

    def test_usage_is_the_thread_total_and_each_row_carries_the_turn_own_usage(self):
        """RS4 C1-C5: Codex reports the thread's running total on every `turn.completed`. The session keeps the last
        total (C1), the architect row the difference to the session total before the turn (C2), a new thread counts
        from zero after `reset()` while `turns` goes on (C3), and a failed turn leaves the usage alone so the next
        total covers it (C5). C4 is `test_events_aggregated_and_noise_tolerated`'s last-report-wins.
        Interpretations: the row of a turn whose total is below the session total (not after a reset) is clamped to 0
        per key; the session keeps the reported total whatever it is."""
        def turn(input_tokens, output_tokens):
            return {"lines": [OK[0], OK[1], OK[2], {"type": "turn.completed", "usage": {
                "input_tokens": input_tokens, "output_tokens": output_tokens}}]}
        failing = {"lines": [{"type": "turn.failed", "error": {"message": "boom"}}], "exit": 1}
        self.script([turn(100, 20), turn(250, 50), failing, turn(400, 90), turn(40, 10)])
        arch = self.architect()
        rows = lambda: [e["usage"] for e in ArchitectStore(self.project).transcript() if e["role"] == "architect"]
        self.assertEqual(arch.send("раз").status, "completed")
        self.assertEqual(arch.session()["usage"], {"input_tokens": 100, "output_tokens": 20})
        self.assertEqual(arch.send("два").status, "completed")
        self.assertEqual(arch.session()["usage"], {"input_tokens": 250, "output_tokens": 50})
        self.assertEqual(rows(), [{"input_tokens": 100, "output_tokens": 20}, {"input_tokens": 150, "output_tokens": 30}])
        self.assertEqual(arch.send("три").status, "failed")
        self.assertEqual(arch.session()["usage"], {"input_tokens": 250, "output_tokens": 50})
        self.assertEqual(arch.send("четыре").status, "completed")
        self.assertEqual(arch.session()["usage"], {"input_tokens": 400, "output_tokens": 90})
        self.assertEqual(rows()[-1], {"input_tokens": 150, "output_tokens": 40})
        arch.reset()
        self.assertEqual(arch.send("пять").status, "completed")
        self.assertEqual(arch.session()["usage"], {"input_tokens": 40, "output_tokens": 10})
        self.assertEqual(rows()[-1], {"input_tokens": 40, "output_tokens": 10})
        self.assertEqual(arch.session()["turns"], 5)

    def test_oversized_line_is_dropped_not_fatal(self):
        huge = '{"type":"item.completed","item":{"id":"x","type":"agent_message","text":"' + "a" * (architect.MAX_LINE + 10) + '"}}'
        self.script([{"lines": [OK[0], huge] + OK[1:]}])
        result = self.architect().send("x")
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.malformed_lines, 1)
        self.assertEqual(result.text, "Привет.")

    def test_callback_failure_does_not_break_turn(self):
        def broken(_):
            raise RuntimeError("ui")

        result = Architect(self.codex, self.env, self.project, "m", "high", on_event=broken).send("x")
        self.assertEqual(result.status, "completed")

    # A4
    def test_failures_have_cause_and_are_not_retried(self):
        cases = [
            ([{"lines": [OK[0]], "exit": 2, "stderr": "boom"}], "failed", "code 2"),
            ([{"lines": [OK[0], {"type": "turn.failed", "error": {"message": "model overloaded"}}], "exit": 1}], "failed", "model overloaded"),
            ([{"lines": [{"type": "error", "message": "401 Unauthorized: please log in"}], "exit": 1}], "failed", "zplan login"),
            ([{"lines": [], "exit": 0}], "failed", "without a turn result"),
        ]
        for steps, status, cause in cases:
            with self.subTest(cause=cause):
                before = len(self.calls())
                for name in ("session.json", "transcript.jsonl"):
                    (self.store_dir() / name).unlink(missing_ok=True)
                self.script(steps)
                result = self.architect().send("x")
                self.assertEqual(result.status, status)
                self.assertIn(cause, result.cause)
                self.assertEqual(len(self.calls()), before + 1)  # exactly one invocation, no retry
                last = ArchitectStore(self.project).transcript()[-1]
                self.assertEqual(last["role"], "error")
                self.assertEqual(last["status"], status)

    def test_transient_error_event_does_not_fail_completed_turn(self):
        self.script([{"lines": [OK[0], {"type": "error", "message": "Reconnecting 1/5"}] + OK[1:]}])
        self.assertEqual(self.architect().send("x").status, "completed")

    def test_missing_executable_refuses_the_turn_at_the_server_check(self):
        """A3c: the listing is the first launch of a turn, so an executable that cannot start is refused there."""
        arch = Architect(self.bin / "nope", self.env, self.project, "m", "high")
        with self.assertRaises(Blocked) as raised:
            arch.send("x")
        self.assertEqual(raised.exception.family, "architect.foreign_tools")
        self.assertFalse(arch.running)

    def test_vanished_thread_is_lost_session_and_reset_starts_new_thread(self):
        new = "0199aaaa-bbbb-cccc-dddd-eeeeffff0002"
        self.script([{"lines": OK},
                     {"lines": [{"type": "error", "message": "thread/resume failed: no rollout found for thread id " + THREAD}],
                      "exit": 1},
                     {"lines": [dict(OK[0], thread_id=new)] + OK[1:]}])
        arch = self.architect()
        self.assertEqual(arch.send("раз").status, "completed")
        lost = arch.send("два")
        self.assertEqual(lost.status, "lost_session")
        self.assertIn("reset", lost.cause)
        self.assertEqual(arch.thread_id, THREAD)        # kept until the owner resets
        self.assertEqual(len(self.calls()), 2)          # no automatic retry
        arch.reset()
        self.assertIsNone(arch.thread_id)
        roles_before = [e["role"] for e in ArchitectStore(self.project).transcript()]
        self.assertIn("owner", roles_before)
        self.assertEqual(arch.send("три").status, "completed")
        third = self.calls()[2]
        self.assertEqual(third["argv"][:2], ["exec", "--json"])   # a fresh first turn, not a resume
        self.assertEqual(arch.thread_id, new)
        transcript = ArchitectStore(self.project).transcript()
        self.assertEqual([e["role"] for e in transcript][:len(roles_before)], roles_before)
        self.assertEqual(sum(1 for e in transcript if e["role"] == "owner"), 3)
        self.assertEqual(arch.session()["turns"], 3)

    def test_first_turn_never_reports_lost_session(self):
        self.script([{"lines": [{"type": "error", "message": "no rollout found"}], "exit": 1}])
        self.assertEqual(self.architect().send("x").status, "failed")

    def test_blocked_inputs(self):
        arch = self.architect()
        with self.assertRaises(Blocked):
            arch.send("   ")
        self.assertEqual(self.calls(), [])
        (self.store_dir() / "session.json").write_text("{broken")
        with self.assertRaises(Blocked):
            arch.send("x")
        self.assertEqual(self.calls(), [])

    def test_second_process_cannot_share_the_project_thread(self):
        import fcntl
        arch = self.architect()
        descriptor = os.open(arch.store.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        self.addCleanup(os.close, descriptor)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        with self.assertRaises(Blocked):
            arch.send("x")
        self.assertEqual(self.calls(), [])
        self.assertFalse(arch.running)

    # A5
    def test_cancel_kills_the_process_group_and_records_cancelled(self):
        pids = self.root / "pids"
        self.script([{"lines": [OK[0]], "child": str(pids), "hang": 120}])
        arch = self.architect()
        outcome = []
        worker = threading.Thread(target=lambda: outcome.append(arch.send("долго")))
        worker.start()
        deadline = time.time() + 20
        while not pids.exists() and time.time() < deadline:
            time.sleep(0.05)
        self.assertTrue(pids.exists())
        time.sleep(0.2)
        parent, child = (int(x) for x in pids.read_text().split())
        self.assertTrue(alive(parent) and alive(child))
        self.assertTrue(arch.cancel())
        worker.join(20)
        self.assertFalse(worker.is_alive())
        self.assertEqual(outcome[0].status, "cancelled")
        deadline = time.time() + 10
        while (alive(child) or alive(parent)) and time.time() < deadline:
            time.sleep(0.05)
        self.assertFalse(alive(child))
        self.assertFalse(alive(parent))
        last = ArchitectStore(self.project).transcript()[-1]
        self.assertEqual((last["role"], last["status"]), ("error", "cancelled"))
        self.assertEqual(arch.thread_id, THREAD)
        self.assertFalse(arch.cancel())
        self.assertFalse(arch.running)

    def test_cancel_does_not_touch_unrelated_processes(self):
        bystander = __import__("subprocess").Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(bystander.wait)
        self.addCleanup(bystander.kill)
        pids = self.root / "pids"
        self.script([{"lines": [OK[0]], "child": str(pids), "hang": 120}])
        arch = self.architect()
        worker = threading.Thread(target=lambda: arch.send("x"))
        worker.start()
        while not pids.exists():
            time.sleep(0.05)
        arch.cancel()
        worker.join(20)
        self.assertIsNone(bystander.poll())

    # A6
    def test_store_private_and_project_untouched(self):
        before = tree(self.project)
        arch = self.architect()
        arch.send("a")
        arch.send("b")
        arch.reset()
        self.assertEqual(tree(self.project), before)
        directory = self.store_dir()
        self.assertEqual(directory.parent.parent, self.data / "planning-kit")
        self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        names = {p.name for p in directory.iterdir()}
        self.assertTrue({"session.json", "transcript.jsonl"} <= names)
        for path in directory.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600, path.name)
        self.assertFalse([n for n in names if n.startswith(".")])  # no temp files left behind
        session = json.loads((directory / "session.json").read_text())
        self.assertEqual(set(session) & {"thread_id", "model", "created", "turns", "usage"},
                         {"thread_id", "model", "created", "turns", "usage"})
        roles = [json.loads(l)["role"] for l in (directory / "transcript.jsonl").read_text().splitlines()]
        self.assertEqual(roles, ["owner", "architect", "owner", "architect", "reset"])
        self.assertFalse(list(self.root.glob("proj/**/planning.json")))

    def test_projects_get_separate_stores(self):
        other = self.root / "other"
        other.mkdir()
        self.assertNotEqual(ArchitectStore(self.project).directory, ArchitectStore(other).directory)

    # context
    def test_preamble_is_pure_and_states_the_boundaries(self):
        snapshot = {"project": "demoapp", "branch": "main", "plan_summary": "План r2",
                    "milestones": [{"id": "M1", "title": "Счёт", "state": "merged"}, {"id": "M2", "state": "running"}]}
        text = build_preamble(snapshot)
        self.assertEqual(text, build_preamble(json.loads(json.dumps(snapshot))))
        for needle in ("lead delivery", "read-only", "Controller", "zplan_list_files", "zplan_read_file", "zplan_search",
                       "zplan_status", "zplan_start", "zplan_stop", "zplan_approve_plan", "zplan_resume",
                       "zplan_rebrief", "zplan_state_update", "zplan_state", "own key", "demoapp", "main",
                       "План r2", "M1 Счёт: merged", "M2: running"):
            self.assertIn(needle, text)
        for gone in ("advisory", "There are no file-writing tools"):
            self.assertNotIn(gone, text)
        self.assertIn("(no approved plan yet)", build_preamble(None))
        many = build_preamble({"milestones": [{"id": "M%d" % i, "state": "x"} for i in range(80)]})
        self.assertIn("… 30 more", many)

    def prompts(self, content):
        """The first and the second prompt of one new thread with `content` (bytes; None for no file) in
        `zplan.architect.md` at the project root."""
        path = self.project / "zplan.architect.md"
        for stale in (self.bin / "calls.jsonl", path):
            stale.unlink(missing_ok=True)
        shutil.rmtree(self.store_dir(), ignore_errors=True)
        if content is not None:
            path.write_bytes(content)
        arch = self.architect()
        self.assertEqual(arch.send("Первый").status, "completed")
        self.assertEqual(arch.send("Второй").status, "completed")
        one, two = self.calls()
        return one["stdin"], two["stdin"]

    def test_a12_a_project_method_file_replaces_the_shipped_method_on_the_first_turn_only(self):
        """A12 C1/C2/C3: `<project>/zplan.architect.md` with text replaces the shipped method in the first prompt
        of a new conversation; a resumed prompt carries neither; no file, an empty or whitespace-only file give the
        shipped method; invalid UTF-8 bytes are replaced and the rest is carried.
        Interpretation: a file that cannot be read (a directory in its place) counts as no file."""
        shipped = architect.method()
        first, second = self.prompts(b"# Our method\n- Small slices.")
        self.assertIn("Small slices.", first)
        self.assertNotIn("At most 5 acceptance criteria", first)
        self.assertLess(first.index("lead delivery"), first.index("Small slices."))
        self.assertLess(first.index("Small slices."), first.index("Tools (your only actions"))
        self.assertNotIn("Small slices.", second)
        self.assertNotIn("At most 5 acceptance criteria", second)
        for content in (None, b"", b"\n  \n"):
            first, second = self.prompts(content)
            self.assertIn(shipped, first)
            self.assertNotIn("At most 5 acceptance criteria", second)
        first, _ = self.prompts(b"# M\n\xff ok")
        self.assertIn("# M\n\ufffd ok", first)
        self.assertNotIn("At most 5 acceptance criteria", first)
        (self.project / "zplan.architect.md").unlink()
        (self.project / "zplan.architect.md").mkdir()
        self.assertIn(shipped, build_preamble(SNAPSHOT, self.project))

    def test_a11_the_first_turn_carries_the_shipped_method_between_the_role_and_the_tools(self):
        """A11 C1/C2/C4: the first prompt holds the whole packaged method after the role lines and before the tool
        list; a resumed turn's update does not repeat it; the shipped text stays a generic preset.
        Interpretation: "no date" is any digit-form date; "no path under devtools/" is the substring `devtools/`."""
        text, update, method = build_preamble(SNAPSHOT), build_update(SNAPSHOT), architect.method()
        raw = (Path(architect.__file__).parent / "resources" / "architect_method.md").read_bytes()
        self.assertEqual(method, raw.decode("utf-8").strip())
        self.assertIn("## Brief", text)
        self.assertIn("At most 5 acceptance criteria", text)
        self.assertLess(text.index("lead delivery"), text.index(method))
        self.assertLess(text.index(method), text.index("Tools (your only actions"))
        self.assertNotIn("At most 5 acceptance criteria", update)
        self.assertNotIn("## Brief", update)
        self.assertLessEqual(len(raw), 4600)
        self.assertNotIn("devtools/", method)
        self.assertNotIn("new and changed tests", method)
        self.assertIn("Done = the task's DoD passes, not the suite.", method)
        self.assertIsNone(re.search(r"\d{4}-\d{2}-\d{2}|\d{1,2}[./]\d{1,2}[./]\d{4}", method))
        for text in (text, update):
            self.assertIn("zplan_state_update", text)

    def test_rs6_the_method_merges_on_status_evidence_and_leaves_an_approved_plan_alone(self):
        """RS6 C2-C5: the shipped method names the merge action and what decides it, the plan-event actions, and the
        two rules the delivery smoke broke (an approved plan, a refused action); it stays within 4600 bytes.
        Interpretation: the rules are pinned by the tool names and the key phrases of each rule, not by whole
        sentences, so the wording around them stays free."""
        method = " ".join(architect.method().split())  # the file's line wrapping is not the rule
        merge = method.split("## Merge")[1].split(" ## ")[0]
        for needle in ("`merge` in zplan_status", "never ask the owner for paths", "`zplan_merge`",
                       "never wait for a green candidate first", "Decision ask", "in one line"):
            self.assertIn(needle, merge)
        for needle in ("zplan_approve_plan", "zplan_start", "Planning failed: report it",
                       "Change an approved plan only on the owner's request or a run's evidence",
                       "refused action as refused", "never as done"):
            self.assertIn(needle, method)
        self.assertLessEqual(len(architect.method().encode("utf-8")), 4600)

    def test_p3a_the_role_tells_the_architect_which_words_the_owner_sees(self):
        """P3a C1/C2: the method as the first prompt carries one Role rule that names what the owner sees and bans
        the internal names; the rule is one line of at most 300 bytes and the file stays within 4600 bytes.
        Interpretation: the rule is pinned by the banned names and the seen words, not by whole sentences."""
        role = build_preamble(SNAPSHOT).split("## Role")[1].split("\n## ")[0]
        rules = [line for line in role.splitlines() if line.startswith("- In replies to the owner")]
        self.assertEqual(len(rules), 1)
        self.assertLessEqual(len(rules[0].encode("utf-8")), 300)
        for needle in ("zplan", "the plan", "a milestone", "a run", "a check", "a merge",
                       "Never Controller, socket, manifest, preset, zplan_* tool names or status fields"):
            self.assertIn(needle, rules[0])
        self.assertLessEqual(len(architect.method().encode("utf-8")), 4600)

    def test_r1_the_role_tells_the_architect_to_reply_in_short_markdown_that_ends_with_the_next_step(self):
        """R1 C1/C3: the Role holds one reply-style rule of at most 300 bytes: short markdown in the owner's language,
        each reply ends with the next step and when the owner hears back (or the one question only they can answer),
        an action is named by its real state and a requested one says when. Removing the line fails this test.
        Interpretation: the rule is pinned by key phrases of the whitespace-normalized Role section, not whole sentences."""
        role = " ".join(build_preamble(SNAPSHOT).split("## Role")[1].split("\n## ")[0].split())
        rules = [rule for rule in role.split(" - ") if rule.lstrip("- ").startswith("Reply:")]
        self.assertEqual(len(rules), 1)
        self.assertLessEqual(len(rules[0].encode("utf-8")), 300)
        for needle in ("short markdown", "owner's language", "code in fences", "ends with the next step",
                       "when they hear back", "the one question only they can answer", "real state",
                       "requested (say when), started, done, refused"):
            self.assertIn(needle, rules[0])

    def test_c1a_the_method_and_the_tool_rules_serve_an_event_turn_with_an_attached_status(self):
        """C1a C3/C4: the shipped method says an event turn carries the status (act on it; `zplan_status` only to
        confirm an action just asked for) and that STATE is updated only on a change, once per turn; TOOL_RULES
        names the Codex code tool's call form with the `mcp__zplan__` prefix, so the model never lists `ALL_TOOLS`.
        Interpretation: the rules are pinned by key phrases of the whitespace-normalized text, not whole sentences."""
        method = " ".join(architect.method().split())
        for needle in ("On an event turn act on the attached status",
                       "call zplan_status only to confirm an action you just asked for",
                       "Update only when a decision, the plan or the next step changed, at most once per turn",
                       # rules outside the rewritten lines stay word for word
                       "ask only what only the owner can decide", "races, cleanup) and extra checks", "(search them)"):
            self.assertIn(needle, method)
        text = "\n".join(architect.TOOL_RULES)
        self.assertIn("await tools.mcp__zplan__zplan_status({})", text)
        self.assertIn("prefix for every zplan tool", " ".join(text.split()))
        self.assertIn("tools.mcp__zplan__zplan_status", build_preamble(SNAPSHOT))
        self.assertIn("tools.mcp__zplan__zplan_status", build_update(SNAPSHOT))

    def test_module_has_no_lifecycle_dependencies(self):
        source = Path(architect.__file__).read_text()
        body = source.split('"""', 2)[2]
        for name in ("MilestoneRuns", "Authority", "runs", "milestone"):
            self.assertFalse(any(line.startswith(("import ", "from ")) and name in line for line in body.splitlines()), name)
        self.assertNotIn("planning.json", body)

    # drafts: a completed turn only, persisted with the reply
    def test_a_completed_turn_carries_drafts_and_persists_them_with_the_success_mark(self):
        self.script([{"lines": completes("Вот:\n" + goal("Сделать X") + "\n" + answer("M1", "Ответ"))}])
        result = self.architect().send("вопрос", snapshot=SNAPSHOT)
        self.assertEqual(result.status, "completed")
        self.assertEqual([d["kind"] for d in result.drafts], ["goal", "answer"])
        self.assertEqual(result.drafts[0]["identity"], [2, {"status": "approved", "override": False}])
        self.assertEqual(result.drafts[1]["identity"], TOKEN)
        self.assertEqual(result.drafts[1]["milestone"], "M1")
        row = ArchitectStore(self.project).transcript()[-1]
        self.assertEqual(row["role"], "architect")
        self.assertEqual(row["status"], "completed")           # the success mark of the turn
        self.assertEqual(row["drafts"], result.drafts)         # the identity is stored with the reply
        self.assertEqual(row["text"], result.text)

    def test_a_failed_or_unfinished_turn_carries_no_drafts(self):
        """The streamed text of a turn that never completed is not parsed: the partial reply keeps its fences."""
        streamed = goal("Напечатано по частям")
        self.script([{"lines": [OK[0], {"type": "turn.started"},
                                {"type": "item.updated", "item": {"id": "m1", "type": "agent_message", "text": streamed}}],
                      "exit": 1}])
        result = self.architect().send("вопрос", snapshot=SNAPSHOT)
        self.assertEqual(result.status, "failed")
        self.assertIn(streamed, result.partial)
        self.assertEqual(result.drafts, [])                    # streamed text is never a draft
        row = ArchitectStore(self.project).transcript()[-1]
        self.assertEqual(row["role"], "error")
        self.assertNotIn("drafts", row)
        # a cancelled turn is the same: the fence of its partial text is not a draft either
        pids = self.root / "pids"
        self.script([{"lines": [OK[0], {"type": "turn.started"},
                                {"type": "item.updated", "item": {"id": "m1", "type": "agent_message", "text": streamed}}],
                      "child": str(pids), "hang": 120}])
        cancelled = self.architect()
        outcome = []
        worker = threading.Thread(target=lambda: outcome.append(cancelled.send("вопрос", snapshot=SNAPSHOT)))
        worker.start()
        deadline = time.time() + 20
        while not pids.exists() and time.time() < deadline:
            time.sleep(0.05)
        self.assertTrue(pids.exists())
        self.assertTrue(cancelled.cancel())
        worker.join(20)
        self.assertFalse(worker.is_alive())
        self.assertEqual(outcome[0].status, "cancelled")
        self.assertIn(streamed, outcome[0].partial)
        self.assertEqual(outcome[0].drafts, [])                # cancelled text is never a draft
        row = ArchitectStore(self.project).transcript()[-1]
        self.assertEqual((row["role"], row["status"]), ("error", "cancelled"))
        self.assertNotIn("drafts", row)

    def test_a_resumed_turn_is_told_the_protocol_without_a_snapshot(self):
        """D-0: the resumed branch never falls back to a bare message. A saved thread id means the turn is sent
        with `build_update` and the draft protocol with it, whether or not the caller passed a snapshot."""
        self.script([{"lines": completes("Привет.")}, {"lines": completes("Ещё раз.")}])
        arch = self.architect()
        self.assertEqual(arch.send("первый", snapshot=SNAPSHOT).status, "completed")
        self.assertEqual(arch.send("второй", snapshot=None).status, "completed")
        calls = self.calls()
        self.assertEqual(calls[0]["argv"][:2], ["exec", "--json"])            # the first turn: the preamble
        self.assertEqual(calls[1]["argv"][:3], ["exec", "resume", THREAD])    # the resumed turn: the update
        self.assertIn("Updated state snapshot (read-only):", calls[1]["stdin"])
        self.assertIn("```zplan-goal", calls[1]["stdin"])
        self.assertIn("```zplan-answer <milestone id>", calls[1]["stdin"])
        self.assertNotIn("You are the zplan architect", calls[1]["stdin"])
        self.assertTrue(calls[1]["stdin"].endswith("второй"))                 # the owner message is still the tail

    def test_an_unknown_plan_state_is_not_no_plan_and_is_persisted_as_such(self):
        """A snapshot that does not say which revision it is (no `revision` key: a screen whose first refresh has
        not arrived) names no identity at all. The draft is stored with identity None — never with "no plan",
        which is the confirmed absence (`revision: None`) — so a reload keeps it text only (`chat.drafts_of`:
        actionable is the success mark and an identity that is not None)."""
        self.script([{"lines": completes(goal("Цель"))}])
        unknown = {"project": "proj", "branch": "main"}
        result = self.architect().send("вопрос", snapshot=unknown)
        self.assertEqual(result.status, "completed")
        self.assertEqual([(d["kind"], d["identity"]) for d in result.drafts], [("goal", None)])
        row = ArchitectStore(self.project).transcript()[-1]
        self.assertEqual(row["status"], "completed")           # the success mark is there ...
        self.assertIsNone(row["drafts"][0]["identity"])        # ... the identity is not: the draft is text only
        # the same reply against a snapshot that confirms there is no plan carries the other identity
        self.script([{"lines": completes(goal("Цель"))}])
        confirmed = self.architect().send("вопрос", snapshot={"project": "proj", "branch": "main", "revision": None})
        self.assertEqual([d["identity"] for d in confirmed.drafts], ["no plan"])
        last = ArchitectStore(self.project).transcript()[-1]
        self.assertEqual(last["drafts"][0]["identity"], "no plan")

    # fail-closed flag probe
    def test_verify_cli_reports_missing_flags(self):
        full = "--json --sandbox --cd --model --config"
        self.script([{"lines": []}], help=full)
        self.assertEqual(verify_cli(self.codex, self.env), [])
        self.script([{"lines": []}], help="--json --model")
        missing = verify_cli(self.codex, self.env)
        self.assertIn("exec --sandbox", missing)
        self.assertIn("exec resume --config", missing)
        self.script([{"lines": []}], help=full, help_exit=2)
        self.assertTrue(verify_cli(self.codex, self.env))

    # A6b2a C2
    def test_c2_the_role_names_the_transcript_row_of_a_turn(self):
        """C2: `send`/`run` write their message under `role` (default `"owner"`, today's row); an event-driven turn
        passes `role="events"` and its message is stored as a `role "events"` row."""
        arch = self.architect()
        self.assertEqual(arch.send("вопрос").status, "completed")                 # the default role
        arch.begin()                                                              # `run` drives the same row
        try:
            self.assertEqual(arch.run("событ", role="events").status, "completed")
        finally:
            arch.finish()
        roles = [row["role"] for row in ArchitectStore(self.project).transcript()]
        self.assertEqual(roles, ["owner", "architect", "events", "architect"])

    # T2/U4
    def test_u4_the_reply_language_follows_the_owner_and_event_turns_are_english(self):
        """U4: the first-turn prompt tells the architect to answer in the language of the owner's last message, so a
        Russian owner message (kept verbatim as the tail) is answered in Russian; it names the English «yes» button.
        An event turn (`feed.summary`) and the `/new` warm-up and handoff prompts have no owner message: their text
        and the instructions around them carry no Cyrillic.

        Interpretation: the rule is one static sentence of the preamble (built once, on the first turn), which also
        says that a turn without an owner message is answered in English; the test reads the real stdin of the turn.
        """
        from terminal_planner import feed
        from terminal_planner.tui import chat
        cyrillic = re.compile("[\u0400-\u04ff]")
        owner = self.architect()
        self.assertEqual(owner.send("привет").status, "completed")
        stdin = self.calls()[0]["stdin"]
        self.assertIn("in the language of the owner's last message", stdin)
        self.assertIn("answered in English", stdin)
        self.assertIn("only their «yes» commits", stdin)
        self.assertTrue(stdin.endswith("привет"))
        self.assertIsNone(cyrillic.search(stdin[:-len("привет")]), "the instructions are English")
        for name in ("session.json", "transcript.jsonl"):
            (self.store_dir() / name).unlink(missing_ok=True)
        batch = [{"wake": True, "kind": "plan", "plan_revision": 1, "previous": "proposed", "status": "approved"}]
        arch = self.architect()
        arch.begin()
        try:
            self.assertEqual(arch.run(feed.summary(batch, 2, {"rows": []}), role="events").status, "completed")
        finally:
            arch.finish()
        self.assertIsNone(cyrillic.search(self.calls()[-1]["stdin"]), self.calls()[-1]["stdin"])
        for prompt in (chat.HANDOFF_MESSAGE, chat.WARMUP_MESSAGE % ("STATE", "screen")):
            self.assertIsNone(cyrillic.search(prompt), prompt)


class DraftTests(unittest.TestCase):
    """D-1: the draft protocol of `architect.parse_drafts` and the identities of `architect.plan_identity`.

    Every rule of `DRAFT_RULES` has a case here, including the boundary values (0/1/5/6 drafts, an empty body and
    bodies of 4000 and 4001 characters). The parser is pure: the snapshot is ordinary data (`app.chat_snapshot`'s
    projection), so the same call is the one that runs in a turn and in a reload.

    Interpretations of the format (u3b-drafts-data left these open; recorded here for the reviewers):

    - The five-draft budget counts accepted drafts, not blocks seen: a malformed or oversized block does not spend
      the quota, so a reply with one bad block and five good ones still yields five drafts. The rule says the
      blocks after the fifth "stay plain text", which this keeps true for the good ones.
    - "An unclosed fence is plain text" is read as ending the scan: the unclosed opener and everything after it is
      ordinary text, so a closed block that follows an unclosed one is not a draft either (the fence never closed,
      and reading past it would take the body's own closer as its end).
    - Only a line that is exactly the opener (no indentation, no trailing space, `zplan-answer` with exactly one
      space before the id) opens a draft; a near miss is ordinary text, and its body is then scanned on its own."""

    def kinds(self, text, snapshot=SNAPSHOT):
        return [(d["kind"], d["milestone"], d["text"]) for d in architect.parse_drafts(text, snapshot)]

    def test_one_and_several_drafts_and_a_goal_with_an_answer_in_one_reply(self):
        self.assertEqual(self.kinds(goal("Один")), [("goal", None, "Один")])
        self.assertEqual(self.kinds(answer("M1", "Первый")), [("answer", "M1", "Первый")])
        both = "Вот план.\n" + goal("Цель X") + "\nи ответ:\n" + answer("M1", "Ответ M1") + "\nконец"
        drafts = architect.parse_drafts(both, SNAPSHOT)
        self.assertEqual([(d["kind"], d["text"]) for d in drafts], [("goal", "Цель X"), ("answer", "Ответ M1")])
        self.assertEqual(drafts[0]["identity"], [2, {"status": "approved", "override": False}])
        self.assertEqual(drafts[1]["identity"], TOKEN)
        many = "".join(answer("M1", "A%d" % i) + "\n" for i in range(3))
        self.assertEqual([d["text"] for d in architect.parse_drafts(many, SNAPSHOT)], ["A0", "A1", "A2"])

    def test_boundary_zero_one_five_and_six_drafts(self):
        self.assertEqual(architect.parse_drafts("просто текст", SNAPSHOT), [])
        self.assertEqual(architect.parse_drafts("", SNAPSHOT), [])
        blocks = "".join(goal("G%d" % i) + "\n" for i in range(6))
        self.assertEqual([d["text"] for d in architect.parse_drafts(blocks, SNAPSHOT)],
                         ["G0", "G1", "G2", "G3", "G4"])  # the sixth stays ordinary text

    def test_body_empty_and_the_size_boundary(self):
        """The boundary is 4000 characters of the body as it stands between the fences, spelled out as literals
        (not the production constant: a check that moved with `MAX_DRAFT_TEXT` would stay green while the limit
        itself was wrong). Whitespace counts towards it: a space and 4000 characters is over the limit, while a
        body of spaces alone is empty."""
        self.assertEqual(architect.parse_drafts("```zplan-goal\n\n```", SNAPSHOT), [])
        self.assertEqual(architect.parse_drafts("```zplan-goal\n   \n```", SNAPSHOT), [])
        for size, taken in ((4000, True), (4001, False)):
            with self.subTest(size=size):
                drafts = architect.parse_drafts(goal("я" * size), SNAPSHOT)
                self.assertEqual(bool(drafts), taken)
        self.assertEqual([d["text"] for d in architect.parse_drafts(goal("я" * 4000), SNAPSHOT)], ["я" * 4000])
        self.assertEqual(architect.parse_drafts("```zplan-goal\n " + "я" * 4000 + "\n```", SNAPSHOT), [])
        self.assertEqual(architect.parse_drafts("```zplan-goal\n" + "я" * 4000 + " \n```", SNAPSHOT), [])
        self.assertEqual(architect.parse_drafts("```zplan-goal\n\t" + "я" * 4000 + "\n```", SNAPSHOT), [])

    def test_an_unclosed_fence_is_not_a_draft(self):
        self.assertEqual(architect.parse_drafts("```zplan-goal\nНе закрыто", SNAPSHOT), [])
        self.assertEqual(architect.parse_drafts("до\n```zplan-goal\nA\n```\nпосле\n```zplan-goal\nB", SNAPSHOT),
                         architect.parse_drafts("```zplan-goal\nA\n```", SNAPSHOT))  # only the closed block

    def test_an_unknown_milestone_is_not_a_draft(self):
        self.assertEqual(architect.parse_drafts(answer("M9", "Не туда"), SNAPSHOT), [])
        self.assertEqual(architect.parse_drafts(answer("M1", "Туда"), SNAPSHOT)[0]["milestone"], "M1")
        # a milestone of the snapshot without any attempt keeps its draft, but has no identity to carry
        drafts = architect.parse_drafts(answer("M2", "Ответ M2"), SNAPSHOT)
        self.assertEqual([(d["kind"], d["milestone"], d["identity"]) for d in drafts], [("answer", "M2", None)])

    def test_a_zplan_fence_inside_another_fenced_block_is_quoted_text(self):
        quoted = "Смотри:\n```python\n```zplan-goal\nсделать X\n```\n" + goal("Настоящий")
        self.assertEqual([d["text"] for d in architect.parse_drafts(quoted, SNAPSHOT)], ["Настоящий"])
        self.assertEqual(architect.parse_drafts("```\n```zplan-answer M1\nнет\n```\n", SNAPSHOT), [])

    def test_the_opener_line_must_be_exact(self):
        for line in (" ```zplan-goal", "```zplan-goal ", "```zplan-goalx", "```zplan-answer", "```zplan-answer M1 x",
                     "```zplan-answer  M1"):
            with self.subTest(line=line):
                self.assertEqual(architect.parse_drafts(line + "\nтело\n```", SNAPSHOT), [])
        self.assertEqual([d["milestone"] for d in architect.parse_drafts(answer("M1", "тело"), SNAPSHOT)], ["M1"])

    def test_plan_identity_names_plan_no_plan_and_the_state_of_a_revision(self):
        self.assertEqual(architect.plan_identity({"revision": None}), "no plan")
        self.assertEqual(architect.plan_identity(SNAPSHOT), [2, {"status": "approved", "override": False}])
        # the state of one revision, not its number alone: a submitted, ready or overridden plan differs
        override = dict(SNAPSHOT, plan_state={"status": "approved", "override": True})
        self.assertNotEqual(architect.plan_identity(override), architect.plan_identity(SNAPSHOT))
        self.assertNotEqual(architect.plan_identity(dict(SNAPSHOT, revision=3)), architect.plan_identity(SNAPSHOT))
        # a missing snapshot or a missing state names no identity at all
        self.assertIsNone(architect.plan_identity(None))
        self.assertIsNone(architect.plan_identity({"revision": 2}))
        self.assertIsNone(architect.plan_identity({"revision": 2, "plan_state": None}))
        self.assertEqual([d["identity"] for d in architect.parse_drafts(goal("X"), None)], [None])
        # an unknown state is not the confirmed absence of a plan: a snapshot without `revision` at all (the
        # projection of a screen whose first refresh has not arrived) names no identity, not "no plan"
        self.assertIsNone(architect.plan_identity({"project": "proj", "branch": "main"}))
        self.assertIsNone(architect.plan_identity({"project": "proj", "branch": "main", "milestones": []}))
        self.assertEqual(architect.plan_identity({"revision": None}), "no plan")

    def test_rc1_the_goal_rule_keeps_merging_into_main_out_of_the_goal(self):
        """C3: the first-turn preamble (and the resumed update) tells the architect a goal is the product change only
        and that merging into main is the owner's /merge step."""
        for text in (build_preamble(SNAPSHOT), build_update(SNAPSHOT)):
            self.assertIn("merging into main is the owner's /merge step and never goal text", text)

    def test_the_draft_protocol_is_in_the_preamble_and_in_the_update_of_a_resumed_turn(self):
        for text in (build_preamble(SNAPSHOT), build_update(SNAPSHOT)):
            self.assertIn("```zplan-goal", text)
            self.assertIn("```zplan-answer <milestone id>", text)
        self.assertEqual(build_update(SNAPSHOT),
                         build_update(json.loads(json.dumps(SNAPSHOT))))  # pure and deterministic


if __name__ == "__main__":
    unittest.main()
