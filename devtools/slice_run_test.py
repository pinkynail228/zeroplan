"""Offline tests for the slice runner: a fake `claude` on PATH plays the worker and the reviewer."""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import slice_run as sr

FAKE = r'''#!/usr/bin/env python3
"""Plays one scripted step per invocation. Worker steps edit the tree; review steps return a verdict."""
import json, os, pathlib, signal, sys, time
root = pathlib.Path(os.environ["SLICE_FAKE_SCENARIO"])
steps = json.loads((root / "steps.json").read_text())
n = int((root / "n").read_text()) if (root / "n").exists() else 0
(root / "n").write_text(str(n + 1))
step = steps[n] if n < len(steps) else {"result": "out of script"}
stdin = "" if sys.stdin.isatty() else (sys.stdin.read() if "--no-session-persistence" in sys.argv else "")
with open(root / "calls.jsonl", "a") as f:
    f.write(json.dumps({"argv": sys.argv[1:], "stdin": stdin, "cwd": os.getcwd(), "env": sorted(os.environ)}) + "\n")
def emit(o):
    print(json.dumps(o), flush=True)
emit({"type": "system", "subtype": "init", "session_id": "s%d" % n})
usage = {"input_tokens": 3, "cache_creation_input_tokens": 1000, "cache_read_input_tokens": 500, "output_tokens": 100}
if step.get("hang"):
    (root / "worker.pid").write_text(str(os.getpid()))
    time.sleep(600)
if step.get("die"):
    os.kill(os.getpid(), signal.SIGKILL)
if step.get("limit"):
    emit({"type": "assistant", "error": "rate_limit", "isApiErrorMessage": True, "message": {"id": "m%d" % n, "content": [{"type": "text", "text": step["limit"]}]}})
    emit({"type": "result", "subtype": "success", "is_error": True, "result": step["limit"], "total_cost_usd": 0})
    sys.exit(1)
for rel, text in (step.get("edit") or {}).items():
    p = pathlib.Path(rel); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text)
emit({"type": "assistant", "message": {"id": "m%d" % n, "usage": usage, "content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": "calc.py"}}]}})
result = {"type": "result", "subtype": step.get("subtype", "success"), "is_error": bool(step.get("is_error")), "result": step.get("result", "done"), "total_cost_usd": step.get("cost", 0.1), "permission_denials": []}
if "verdict" in step:
    result["structured_output"] = {"verdict": step["verdict"], "findings": step.get("findings", [])}
emit(result)
'''
GOOD = "def add(a, b):\n    return a + b\n"
BAD = "def add(a, b):\n    return a - b\n"
ACCEPT = {"verdict": "accept"}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="slice-test.")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.dir = self.tmp / "slices" / "t1"
        (self.dir / "contracts").mkdir(parents=True)
        self.fake = self.tmp / "fake"
        self.fake.mkdir()
        bin_path = self.fake / "claude"
        bin_path.write_text(FAKE.replace("#!/usr/bin/env python3", f"#!{sys.executable}"))
        bin_path.chmod(bin_path.stat().st_mode | stat.S_IEXEC)
        env = {"SLICE_NO_OSA": "1", "SLICE_PATH_PREFIX": f"{self.fake}:", "SLICE_FAKE_SCENARIO": str(self.fake)}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        for args in (("init", "-q", "-b", "dev"), ("config", "user.name", "t"), ("config", "user.email", "t@t")):
            self.git(*args)
        (self.repo / "calc.py").write_text("def add(a, b):\n    return 0\n")
        (self.repo / ".gitignore").write_text("__pycache__\n")
        (self.repo / "frozen.txt").write_text("frozen\n")
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        self.run_toml()

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True, check=True).stdout.strip()

    def run_toml(self, queue=("S1",), **extra):
        cfg = {"run": "t1", "repo": str(self.repo), "base": "dev", "queue": list(queue), "tick_s": 0.02, "min_battery_pct": 0, "protected": ["frozen.txt"], "link": [], "limit_default_wait_s": 0.1, "lane_gate": "none: the fixture has no test lane",
               "contract_review": False, **extra}
        lines = [f"{k} = {json.dumps(v)}" for k, v in cfg.items()]
        (self.dir / "run.toml").write_text("\n".join(lines) + "\n")

    def contract(self, sid="S1", acceptance=True, **extra):
        cfg = {"title": "add", "files": ["calc.py"], "check": f"PYTHONPATH=.slice:. {sys.executable} -m unittest acc_test", "brief": "Make add correct.", "max_rounds": 2, "idle_timeout_s": 30, **extra}
        (self.dir / "contracts" / f"{sid}.toml").write_text("\n".join(f"{k} = {json.dumps(v)}" for k, v in cfg.items()) + "\n")
        if acceptance:
            root = self.dir / "contracts" / sid
            root.mkdir(exist_ok=True)
            (root / "acc_test.py").write_text(textwrap.dedent("""
                import unittest, calc
                class T(unittest.TestCase):
                    def test_add(self):
                        self.assertEqual(calc.add(2, 3), 5)
                """))

    def steps(self, *steps):
        (self.fake / "steps.json").write_text(json.dumps(list(steps)))
        (self.fake / "n").unlink(missing_ok=True)

    def go(self):
        return sr.main(["run", str(self.dir)])

    def events(self, kind=None):
        rows = [json.loads(x) for x in (self.dir / "ledger.jsonl").read_text().splitlines()]
        return [r for r in rows if kind is None or r["event"] == kind]

    def calls(self):
        path = self.fake / "calls.jsonl"
        return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []


class Flow(Base):
    def test_pass_lands_on_integration_and_leaves_dev_alone(self):
        self.contract()
        self.steps({"edit": {"calc.py": GOOD}}, ACCEPT)
        dev = self.git("rev-parse", "dev")
        self.assertEqual(self.go(), 0)
        self.assertEqual(self.git("rev-parse", "dev"), dev)
        self.assertIn("a + b", self.git("show", "slices/t1:calc.py"))
        self.assertNotIn("acc_test.py", self.git("ls-tree", "-r", "--name-only", "slices/t1").split(), "the check is not kept")
        self.assertEqual(self.events("slice_pass")[0]["rounds"], 1)
        self.assertEqual(self.events("wake")[0]["reason"], "queue_done")
        self.assertFalse((self.repo / ".worktrees/slice-t1-S1").exists())

    def test_empty_integration_branch_follows_a_moved_base(self):
        self.contract()
        self.git("branch", "slices/t1", "dev")
        (self.repo / "note.txt").write_text("harness fix\n")
        self.git("add", "note.txt")
        self.git("commit", "-qm", "fix")
        self.steps({"edit": {"calc.py": GOOD}}, ACCEPT)
        self.assertEqual(self.go(), 0)
        self.assertEqual(self.events("integration_moved")[0]["new"], self.git("rev-parse", "dev"))
        self.assertIn("harness fix", self.git("show", "slices/t1:note.txt"))

    def test_integration_branch_with_landed_work_is_not_moved(self):
        self.contract()
        self.git("checkout", "-qb", "slices/t1")
        (self.repo / "landed.txt").write_text("landed\n")
        self.git("add", "landed.txt")
        self.git("commit", "-qm", "landed")
        self.git("checkout", "-q", "dev")
        landed = self.git("rev-parse", "slices/t1")
        (self.repo / "note.txt").write_text("other\n")
        self.git("add", "note.txt")
        self.git("commit", "-qm", "base moved")
        self.steps({"edit": {"calc.py": GOOD}}, ACCEPT)
        self.go()
        self.assertEqual(self.events("integration_moved"), [])
        self.assertEqual(self.git("merge-base", "--is-ancestor", landed, "slices/t1") , "")

    def test_check_that_passes_on_base_is_refused_before_any_worker(self):
        self.contract(check="true", acceptance=False)
        self.steps({"edit": {"calc.py": GOOD}})
        self.assertEqual(self.go(), 10)
        self.assertEqual(self.events("slice_fail")[0]["reason"], "contract_invalid")
        self.assertEqual(self.calls(), [])

    def test_red_for_another_reason_is_refused(self):
        self.contract(red_contains="test_never_named")
        self.steps({"edit": {"calc.py": GOOD}})
        self.assertEqual(self.go(), 10)
        self.assertEqual(self.events("slice_fail")[0]["reason"], "contract_invalid")
        self.assertEqual(self.calls(), [])

    def test_green_is_rerun_by_the_supervisor_and_failure_reaches_a_fresh_worker(self):
        self.contract()
        self.steps({"edit": {"calc.py": BAD}, "result": "all tests pass"}, {"edit": {"calc.py": GOOD}}, ACCEPT)
        self.assertEqual(self.go(), 0)
        self.assertEqual(self.events("slice_pass")[0]["rounds"], 2)
        first, second = self.calls()[0], self.calls()[1]
        self.assertNotEqual(first["argv"][first["argv"].index("--session-id") + 1], second["argv"][second["argv"].index("--session-id") + 1])
        self.assertIn("test_add", second["argv"][1])

    def test_same_failure_twice_stops_before_the_round_limit(self):
        self.contract(max_rounds=5)
        self.steps({"edit": {"calc.py": BAD}}, {"edit": {"calc.py": BAD + "# again\n"}}, {"edit": {"calc.py": GOOD}})
        self.assertEqual(self.go(), 10)
        self.assertEqual(self.events("slice_fail")[0]["reason"], "same_failure")
        self.assertEqual(len(self.calls()), 2)
        self.assertTrue((self.repo / ".worktrees/slice-t1-S1").exists(), "the tree stays for the architect")

    def test_a_tampered_acceptance_check_never_decides_and_frozen_paths_are_rejected_even_if_the_sandbox_failed(self):
        self.contract()
        tampered = "import unittest\nclass T(unittest.TestCase):\n    def test_add(self):\n        pass\n"
        self.steps({"edit": {"calc.py": BAD, ".slice/acc_test.py": tampered}}, {"edit": {"calc.py": BAD, "frozen.txt": "x"}})
        self.assertEqual(self.go(), 10)
        gates = [e["gate"] for e in self.events("round_failed")]
        self.assertEqual(gates, ["green", "locked_path"], "the contract's own check runs again, so the tampered copy fails")
        self.assertEqual(self.events("slice_pass"), [])

    def test_file_outside_the_contract_and_oversized_diff_are_rejected(self):
        self.contract(max_diff_lines=3)
        self.steps({"edit": {"calc.py": GOOD, "other.py": "x = 1\n"}}, {"edit": {"calc.py": GOOD + "# pad\n" * 9}})
        self.go()
        self.assertEqual([e["gate"] for e in self.events("round_failed")], ["outside_files", "outside_files"])
        self.steps()
        shutil.rmtree(self.repo / ".worktrees/slice-t1-S1")
        self.git("worktree", "prune")
        sr.main(["retry", str(self.dir), "S1", "test"])
        self.git("branch", "-qD", "slice/t1/S1")
        self.steps({"edit": {"calc.py": GOOD + "# pad\n" * 9}}, {"edit": {"calc.py": GOOD + "# pad\n" * 8}})
        self.go()
        self.assertEqual(self.events("round_failed")[-1]["gate"], "diff_too_big")

    def test_reviewer_gets_contract_and_diff_only_and_can_reject(self):
        self.contract()
        finding = {"requirement": "R1", "file": "calc.py", "scenario": "negative numbers"}
        self.steps({"edit": {"calc.py": GOOD}, "result": "WORKER-NARRATIVE"}, {"verdict": "reject", "findings": [finding]}, {"edit": {"calc.py": GOOD + "# fixed\n"}}, ACCEPT)
        self.assertEqual(self.go(), 0)
        review = self.calls()[1]
        self.assertIn("Make add correct.", review["stdin"])
        self.assertIn("+    return a + b", review["stdin"])
        self.assertNotIn("WORKER-NARRATIVE", review["stdin"])
        self.assertEqual(review["argv"][review["argv"].index("--tools") + 1], "")
        self.assertIn("negative numbers", self.calls()[2]["argv"][1])

    def test_reviewer_without_a_verdict_wakes_the_architect(self):
        self.contract()
        self.steps({"edit": {"calc.py": GOOD}}, {"result": "cannot review"})
        self.assertEqual(self.go(), 10)
        self.assertEqual(self.events("slice_fail")[0]["reason"], "review_error")

    def test_blocked_reply_stops_without_gates(self):
        self.contract()
        self.steps({"result": "BLOCKED: the contract contradicts itself"})
        self.assertEqual(self.go(), 10)
        self.assertEqual(self.events("slice_fail")[0]["reason"], "blocked")

    def test_worker_budget_stops_the_slice(self):
        self.contract()
        self.steps({"is_error": True, "subtype": "error_max_budget_usd", "result": "budget"})
        self.assertEqual(self.go(), 10)
        self.assertEqual(self.events("slice_fail")[0]["reason"], "budget")

    def test_night_budget_stops_before_the_next_worker(self):
        self.run_toml(queue=("S1", "S2"), night_budget_usd=0.15)
        self.contract("S1")
        self.contract("S2", check=f"PYTHONPATH=. {sys.executable} -c \"import calc;assert calc.add(1,1)==3\"", acceptance=False)
        self.steps({"edit": {"calc.py": GOOD}, "cost": 0.2}, ACCEPT)
        self.assertEqual(self.go(), 10)
        failed = self.events("slice_fail")[0]
        self.assertEqual((failed["slice"], failed["reason"]), ("S2", "budget_night"))
        self.assertEqual(len(self.calls()), 2)

    def test_owner_slice_is_deferred_with_its_dependents_and_the_queue_continues(self):
        self.run_toml(queue=("S1", "S2", "S3"))
        self.contract("S1", needs_owner="client text")
        self.contract("S2", depends=["S1"])
        self.contract("S3")
        self.steps({"edit": {"calc.py": GOOD}}, ACCEPT)
        self.assertEqual(self.go(), 0)
        self.assertEqual([e["slice"] for e in self.events("deferred")], ["S1", "S2"])
        self.assertEqual([e["slice"] for e in self.events("slice_pass")], ["S3"])

    def test_wake_after_n_passed_then_ack_and_restart_continue(self):
        self.run_toml(queue=("S1", "S2", "S3"), wake_after_passed=2)
        (self.repo / "calc2.py").write_text("x = 0\n")
        self.git("add", ".")
        self.git("commit", "-qm", "more")
        self.contract("S1", check=f"PYTHONPATH=. {sys.executable} -c \"import calc;assert calc.add(2,3)==5\"", acceptance=False)
        self.contract("S2", check=f"PYTHONPATH=. {sys.executable} -c \"import calc2;assert calc2.x==1\"", files=["calc2.py"], acceptance=False)
        self.contract("S3", check=f"PYTHONPATH=. {sys.executable} -c \"import calc2;assert calc2.x==2\"", files=["calc2.py"], acceptance=False,
                      supersedes=["S2"])  # S3 changes S2's behaviour on purpose, so S2's check is not rerun
        self.steps({"edit": {"calc.py": GOOD}}, ACCEPT, {"edit": {"calc2.py": "x = 1\n"}}, ACCEPT, {"edit": {"calc2.py": "x = 2\n"}}, ACCEPT)
        self.assertEqual(self.go(), 0)
        self.assertEqual(self.events("wake")[0]["reason"], "passed 2")
        self.assertEqual(len(self.events("slice_pass")), 2)
        sr.main(["ack", str(self.dir)])
        self.assertEqual(self.go(), 0)
        self.assertEqual([e["slice"] for e in self.events("slice_pass")], ["S1", "S2", "S3"])
        self.assertIn("x = 2", self.git("show", "slices/t1:calc2.py"))


class Acceptance(Base):
    def test_the_acceptance_check_is_never_committed(self):
        """W0 design 3.3: the check is the slice's oracle in `.slice/`, not a test to keep; only the change lands."""
        self.contract(commit="[q S1] Fix add")
        cache = self.dir / "contracts/S1/__pycache__"
        cache.mkdir()
        (cache / "acc_test.pyc").write_bytes(b"x")
        self.steps({"edit": {"calc.py": GOOD}}, ACCEPT)
        self.assertEqual(self.go(), 0)
        names = self.git("log", "--name-only", "--format=", "dev..slices/t1").split()
        self.assertEqual(names, ["calc.py"])
        self.assertEqual(self.git("log", "--format=%s", "dev..slices/t1").splitlines(), ["[q S1] Fix add"])

    def test_start_refuses_a_queue_without_a_lane_gate(self):
        self.run_toml(lane_gate="")
        self.contract()
        self.assertTrue(any("lane_gate" in p for p in sr.contract_problems(sr.Run(self.dir))))
        self.run_toml(lane_gate="none")
        self.assertTrue(any("lane_gate" in p for p in sr.contract_problems(sr.Run(self.dir))), "an opt-out names its reason")
        self.run_toml(lane_gate="none: no lane in this fixture")
        self.assertFalse(any("lane_gate" in p for p in sr.contract_problems(sr.Run(self.dir))))

    def test_the_run_lane_gate_runs_after_the_contract_gates(self):
        """A pin in a module the contract did not list fails the slice, not only the next full lane (S1b); the
        contract's own gates come first, and a lane failure tells the worker to stop on a test outside its files."""
        self.run_toml(lane_gate="test ! -e lane.flag")
        self.contract(files=["calc.py", "lane.flag", "gate.flag"], gates=["test ! -e gate.flag"])
        self.steps({"edit": {"calc.py": GOOD, "lane.flag": "x"}}, {"edit": {"calc.py": GOOD, "lane.flag": "x", "gate.flag": "x"}})
        self.go()
        self.assertEqual([e["gate"] for e in self.events("round_failed")], ["gate:test ! -e lane.flag", "gate:test ! -e gate.flag"])
        self.assertIn("BLOCKED", " ".join(self.calls()[1]["argv"]), "the repair worker is told to stop on a test outside its files")


class Foundation(Base):
    """F0 (docs/DEVELOPMENT.md 2.6): the oracle cannot be bypassed, the lane has a baseline, a later slice keeps an
    earlier one's behaviour, and the committed tree is the tree that passed."""

    def test_a_rejected_contract_stops_before_any_worker(self):
        self.run_toml(contract_review=True)
        self.contract(red_contains="AssertionError")
        finding = {"kind": "paths", "file": "calc.py", "line": 1, "scenario": "sub() applies the same rule"}
        self.steps({"verdict": "reject", "findings": [finding]})
        self.assertEqual(self.go(), 10)
        fail = self.events("slice_fail")[0]
        self.assertEqual(fail["reason"], "contract_rejected")
        self.assertIn("sub() applies the same rule", fail["detail"])
        calls = self.calls()
        self.assertEqual(len(calls), 1, "no worker is spent on a rejected contract")
        argv = calls[0]["argv"]
        self.assertEqual(argv[argv.index("--tools") + 1], "Read,Grep,Glob")
        self.assertIn("Make add correct.", calls[0]["stdin"], "the reviewer reads the contract")
        self.assertIn("calc.add(2, 3)", calls[0]["stdin"], "and its acceptance check")

    def test_an_accepted_contract_lets_the_worker_run(self):
        self.run_toml(contract_review=True)
        self.contract()
        self.steps({"verdict": "accept"}, {"edit": {"calc.py": GOOD}}, ACCEPT)
        self.assertEqual(self.go(), 0)
        self.assertEqual([e["verdict"] for e in self.events("contract_review")], ["accept"])
        self.assertEqual(len(self.events("slice_pass")), 1)

    def test_a_staged_slice_folder_is_a_locked_path(self):
        self.contract()
        unignored = {"calc.py": GOOD, ".slice/.gitignore": "", ".slice/acc_test.py": "x = 1\n"}
        self.steps({"edit": unignored}, {"edit": unignored})
        self.assertEqual(self.go(), 10)
        self.assertEqual([e["gate"] for e in self.events("round_failed")], ["locked_path"] * 2)

    def test_a_lane_red_on_the_base_stops_before_any_worker(self):
        self.run_toml(lane_gate="false")
        self.contract(red_contains="AssertionError")
        self.steps({"edit": {"calc.py": GOOD}}, ACCEPT)
        self.assertEqual(self.go(), 10)
        self.assertEqual(self.events("slice_fail")[0]["reason"], "lane_red_on_base")
        self.assertEqual(self.calls(), [], "no worker is spent on a red base")

    def test_the_lane_runs_once_per_tree_and_after_the_contract_gates(self):
        count = self.tmp / "lane.count"
        self.run_toml(queue=("S1", "S2"), lane_gate=f"echo x >> {count}")
        (self.repo / "calc2.py").write_text("x = 0\n")
        self.git("add", ".")
        self.git("commit", "-qm", "more")
        self.contract("S1")
        self.contract("S2", check=f"PYTHONPATH=. {sys.executable} -c \"import calc2;assert calc2.x==1\"", files=["calc2.py"],
                      acceptance=False)
        self.steps({"edit": {"calc.py": GOOD}}, ACCEPT, {"edit": {"calc2.py": "x = 1\n"}}, ACCEPT)
        self.assertEqual(self.go(), 0)
        self.assertEqual(len(count.read_text().split()), 3, "S1's base, S1, S2: S2's base is the tree S1 passed")

    def test_a_check_that_changes_the_tree_fails_the_slice(self):
        self.contract(gates=["touch made.by.check"])
        self.steps({"edit": {"calc.py": GOOD}}, {"edit": {"calc.py": GOOD}})
        self.assertEqual(self.go(), 10)
        self.assertEqual([e["gate"] for e in self.events("round_failed")], ["tree_changed", "outside_files"],
                         "the file the check wrote stays in the tree, so the next round is refused for it too")

    def test_a_check_that_cannot_import_its_own_module_is_an_invalid_contract(self):
        self.contract(check=f"{sys.executable} -m unittest acc_test")
        self.steps({"edit": {"calc.py": GOOD}}, ACCEPT)
        self.assertEqual(self.go(), 10)
        self.assertEqual(self.events("slice_fail")[0]["reason"], "contract_invalid")
        self.assertEqual(self.calls(), [])

    def test_a_later_slice_that_breaks_an_earlier_one_fails_unless_it_supersedes_it(self):
        self.run_toml(queue=("S1", "S2"))
        self.contract("S1")
        self.contract("S2", check=f"PYTHONPATH=. {sys.executable} -c \"import calc;assert calc.add(2,3)==6\"", acceptance=False)
        six = GOOD.replace("a + b", "a + b + 1")
        self.steps({"edit": {"calc.py": GOOD}}, ACCEPT, {"edit": {"calc.py": six}}, {"edit": {"calc.py": six}})
        self.assertEqual(self.go(), 10)
        self.assertEqual([e["gate"] for e in self.events("round_failed")], ["check:S1"] * 2)


class ContractChange(Base):
    def test_an_edited_acceptance_check_changes_the_recorded_digest(self):
        self.contract()
        run = sr.Run(self.dir)
        before = sr.contract_digest(run.contract("S1"))
        path = self.dir / "contracts/S1/acc_test.py"
        path.write_text(path.read_text() + "# stronger\n")
        self.assertNotEqual(before, sr.contract_digest(run.contract("S1")))


class Faults(Base):
    def test_hung_worker_is_killed_with_its_group(self):
        self.contract(idle_timeout_s=0.3, max_rounds=1)
        self.steps({"hang": True})
        t0 = time.time()
        self.assertEqual(self.go(), 10)
        self.assertLess(time.time() - t0, 15)
        end = self.events("agent_end")[0]
        self.assertEqual(end["outcome"], "hung")
        pid = int((self.fake / "worker.pid").read_text())
        time.sleep(0.2)
        self.assertFalse(sr.pid_alive(pid))

    def test_killed_worker_is_seen_and_retried_once(self):
        self.contract()
        self.steps({"die": True}, {"edit": {"calc.py": GOOD}}, ACCEPT)
        self.assertEqual(self.go(), 0)
        self.assertEqual(self.events("agent_end")[0]["outcome"], "killed")
        self.assertEqual(self.events("slice_pass")[0]["rounds"], 2)

    def test_two_kills_in_a_row_stop(self):
        self.contract(max_rounds=5)
        self.steps({"die": True}, {"die": True}, {"edit": {"calc.py": GOOD}})
        self.assertEqual(self.go(), 10)
        self.assertEqual(self.events("slice_fail")[0]["reason"], "same_failure")

    def test_subscription_limit_waits_and_does_not_spend_a_round(self):
        self.contract(max_rounds=1)
        self.steps({"limit": "You've hit your session limit"}, {"edit": {"calc.py": GOOD}}, ACCEPT)
        self.assertEqual(self.go(), 0)
        self.assertEqual(len(self.events("limit")), 1)
        self.assertEqual(self.events("slice_pass")[0]["rounds"], 1)

    def test_a_low_battery_waits_for_power_and_spends_no_round(self):
        self.run_toml(min_battery_pct=101, power_poll_s=0.02)
        self.contract()
        self.steps({"edit": {"calc.py": GOOD}}, ACCEPT)
        reads = iter(["battery 15%", "battery 14%"])
        with mock.patch.object(sr, "battery_stop", side_effect=lambda run: next(reads, "")):
            self.assertEqual(self.go(), 0)
        self.assertEqual([e["event"] for e in self.events() if e["event"].startswith("power_")], ["power_wait", "power_back"])
        self.assertEqual(self.events("slice_pass")[0]["rounds"], 1)

    def test_limit_with_a_long_reset_wakes_the_architect(self):
        self.run_toml(limit_max_wait_s=1)
        self.contract()
        self.steps({"limit": "You've hit your session limit · resets 3:40pm (Europe/Moscow)"})
        self.assertEqual(self.go(), 10)
        self.assertEqual(self.events("slice_fail")[0]["reason"], "limit_too_long")

    def test_clock_gap_is_not_read_as_a_hang(self):
        self.contract(idle_timeout_s=50, max_rounds=1)
        self.steps({"hang": True})
        real, offset = time.time, {"v": 0.0, "n": 0}

        def jumpy():
            offset["n"] += 1
            if offset["n"] == 40:
                offset["v"] = 120.0
            return real() + offset["v"]

        with mock.patch.object(sr, "now", jumpy):
            run = sr.Run(self.dir)
            run.git("branch", run.integration, "dev")
            c = run.contract("S1")
            wt, _ = sr.prepare(run, c)
            agent = sr.Agent(run, "x.worker", "claude-haiku-5-5", ["claude", "-p", "x"], wt, None, c["idle_timeout_s"], 3600)
            threading_stop = sr.threading.Timer(1.5, lambda: sr.kill_group(agent.proc))
            threading_stop.start()
            outcome = agent.execute()
            threading_stop.cancel()
        self.assertEqual(outcome, "killed", "the gap must not produce hung")
        self.assertEqual(self.events("clock_gap")[0]["seconds"], 120)

    @unittest.skipIf(os.environ.get("SLICE_GATE") == "1", "a seatbelt forbids the setuid ps the orphan check uses; runs at integration")
    def test_restart_after_a_crash_reruns_the_slice_and_kills_the_orphan_once(self):
        self.contract()
        self.steps({"edit": {"calc.py": GOOD}}, ACCEPT)
        run = sr.Run(self.dir)
        sleeper = subprocess.Popen(["/bin/bash", "-c", "exec -a claude-orphan sleep 60"], start_new_session=True)
        self.addCleanup(sleeper.kill)
        run.event("run_start", pid=999999)
        run.event("slice_start", slice="S1")
        run.event("agent_start", name="S1.r1.a1.worker", pid=sleeper.pid)
        self.assertEqual(self.go(), 0)
        self.assertEqual(self.events("orphan_killed")[0]["pid"], sleeper.pid)
        self.assertEqual(sleeper.wait(timeout=5), -signal.SIGKILL)
        self.assertEqual(len(self.events("slice_pass")), 1)

    def test_slice_started_twice_without_outcome_stops(self):
        self.contract()
        run = sr.Run(self.dir)
        for _ in range(2):
            run.event("run_start", pid=999999)
            run.event("slice_start", slice="S1")
        self.assertEqual(self.go(), 10)
        self.assertEqual(self.events("slice_fail")[0]["reason"], "restarts")


class StartChecks(Base):
    def test_start_refuses_a_contract_the_worker_could_never_satisfy(self):
        for name, write in (
                ("unparsable", lambda: (self.dir / "contracts" / "S1.toml").write_text('brief = "a \\q b"\n')),
                ("protected", lambda: self.contract(files=["frozen.txt"], red_contains="AssertionError")),
                ("oversized", lambda: self.contract(brief="x" * 4000, red_contains="AssertionError")),
                ("no red reason", lambda: self.contract()),
                ("red reason is the module name", lambda: self.contract(red_contains="acc_test"))):
            with self.subTest(name):
                write()
                with mock.patch.object(sr.subprocess, "run") as tmux:
                    self.assertEqual(sr.main(["start", str(self.dir)]), 2)
                tmux.assert_not_called()
                self.assertFalse((self.dir / "ledger.jsonl").exists())

    def test_a_valid_contract_has_no_problems(self):
        self.contract(red_contains="AssertionError")
        self.assertEqual(sr.contract_problems(sr.Run(self.dir)), [])

    def test_start_inside_herdr_needs_a_live_slice_monitor(self):
        self.contract(red_contains="AssertionError")
        beat = self.dir.parent / sr.MONITOR_BEAT
        env = {k: v for k, v in os.environ.items() if k != "SLICE_NO_MONITOR"}
        with mock.patch.dict(os.environ, {**env, "HERDR_ENV": "1"}, clear=True):
            for name, write in (("none", lambda: None),
                                ("stale", lambda: beat.write_text(json.dumps({"pid": os.getpid(), "ts": time.time() - 120})))):
                with self.subTest(name), mock.patch.object(sr.subprocess, "run") as tmux:
                    write()
                    self.assertEqual(sr.main(["start", str(self.dir)]), 2)
                    tmux.assert_not_called()
            beat.write_text(json.dumps({"pid": os.getpid(), "ts": time.time(), "agent": "arch"}))
            with mock.patch.object(sr.subprocess, "run") as tmux:
                self.assertEqual(sr.main(["start", str(self.dir)]), 0)
                tmux.assert_called()


class Sandbox(Base):
    @unittest.skipIf(os.environ.get("SLICE_GATE") == "1", "inside a gate seatbelt a nested profile cannot apply; runs at integration")
    def test_checks_cannot_write_outside_the_tree_or_reach_the_network(self):
        self.contract(acceptance=False, check="true")
        run = sr.Run(self.dir)
        run.git("branch", run.integration, "dev")
        c = run.contract("S1")
        wt, _ = sr.prepare(run, c)
        outside = pathlib.Path.home() / f"slice-test-{os.getpid()}"
        self.addCleanup(outside.unlink, True)
        code, _ = sr.run_gate(run, c, wt, f"echo x > {outside}", "t1")
        self.assertNotEqual(code, 0)
        self.assertFalse(outside.exists())
        code, _ = sr.run_gate(run, c, wt, "echo x > frozen.txt", "t2")
        self.assertNotEqual(code, 0)
        self.assertEqual((wt / "frozen.txt").read_text(), "frozen\n")
        code, _ = sr.run_gate(run, c, wt, "curl -sS --max-time 3 -o /dev/null https://example.com", "t3")
        self.assertNotEqual(code, 0)
        code, _ = sr.run_gate(run, c, wt, "echo x > ok.txt", "t4")
        self.assertEqual(code, 0)

    def test_a_gate_inside_a_gate_does_not_nest_a_seatbelt(self):
        self.contract(acceptance=False, check="true")
        run = sr.Run(self.dir)
        run.git("branch", run.integration, "dev")
        c = run.contract("S1")
        wt, _ = sr.prepare(run, c)
        seen = []
        real = subprocess.Popen
        def spy(cmd, *a, **k):
            seen.append(cmd[0])
            return real(cmd, *a, **k)
        with mock.patch.dict(os.environ, {"SLICE_GATE": "1"}), mock.patch.object(sr.subprocess, "Popen", spy):
            code, _ = sr.run_gate(run, c, wt, "true", "nested")
        self.assertEqual((code, seen), (0, ["/bin/bash"]))
        with mock.patch.dict(os.environ, {"SLICE_GATE": ""}), mock.patch.object(sr.subprocess, "Popen", spy):
            sr.run_gate(run, c, wt, "true", "outer")
        self.assertEqual(seen[-1], "sandbox-exec")

    def test_worker_env_has_no_secrets_or_session_markers(self):
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "k", "ANTHROPIC_API_KEY": "k", "CLAUDECODE": "1", "JIVO_TOKEN": "k"}):
            env = sr.clean_env()
        for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "CLAUDECODE", "JIVO_TOKEN"):
            self.assertNotIn(name, env)

    def test_worker_settings_lock_acceptance_and_frozen_paths(self):
        self.contract()
        run = sr.Run(self.dir)
        c = run.contract("S1")
        wt = self.repo / ".worktrees/x"
        s = sr.worker_settings(run, c, wt)
        self.assertIn(str(wt / ".slice"), s["sandbox"]["filesystem"]["denyWrite"])
        self.assertIn(str(wt / "frozen.txt"), s["sandbox"]["filesystem"]["denyWrite"])
        self.assertIn(f"Edit(//{str(wt).lstrip('/')}/frozen.txt)", s["permissions"]["deny"])
        self.assertEqual(s["sandbox"]["network"]["allowedDomains"], [])
        self.assertFalse(s["sandbox"]["allowUnsandboxedCommands"])
        self.assertNotIn(str(self.repo), s["sandbox"]["filesystem"]["denyWrite"], "the worktree lives inside the repo")


class Watchdog(Base):
    def supervisor_gone(self):
        run = sr.Run(self.dir)
        run.event("run_start", pid=999999)
        run.heartbeat.write_text(json.dumps({"pid": 999999, "ts": time.time() - 500}))
        return run

    def test_dead_supervisor_alerts_and_restarts_once(self):
        run = self.supervisor_gone()
        with mock.patch.object(sr, "cmd_start") as start:
            sr.watch_run(run, None)
            sr.watch_run(run, None)
        start.assert_called_once()
        self.assertEqual(len([e for e in self.events("alert") if e["key"].startswith("dead:")]), 1)

    def test_frozen_supervisor_alerts_without_a_restart(self):
        run = sr.Run(self.dir)
        run.event("run_start", pid=os.getpid())
        run.heartbeat.write_text(json.dumps({"pid": os.getpid(), "ts": time.time() - 500}))
        with mock.patch.object(sr, "cmd_start") as start:
            sr.watch_run(run, None)
        start.assert_not_called()
        self.assertTrue(any(e["key"].startswith("stalled:") for e in self.events("alert")))

    def test_silent_architect_is_alerted_and_resumed_once(self):
        self.run_toml(architect_session="abc", ack_timeout_s=0)
        run = sr.Run(self.dir)
        run.logs.mkdir()
        run.event("run_start", pid=999999)
        run.event("run_end", reason="queue_done", code=0)
        run.event("wake", seq=1, reason="queue_done")
        with mock.patch.object(sr.subprocess, "Popen") as popen:
            popen.return_value.pid = 4242
            sr.watch_run(run, None)
            sr.watch_run(run, None)
        popen.assert_called_once()
        argv = popen.call_args[0][0]
        self.assertEqual(argv[argv.index("--resume") + 1], "abc")
        self.assertEqual(len(self.events("architect_resume")), 1)

    def test_acknowledged_wake_is_quiet_and_closed_run_is_ignored(self):
        self.run_toml(ack_timeout_s=0, report_every_s=100000)
        run = sr.Run(self.dir)
        run.event("run_start", pid=999999)
        run.event("run_end", reason="queue_done", code=0)
        run.event("wake", seq=1, reason="queue_done")
        run.event("ack", seq=1)
        sr.watch_run(run, None)
        self.assertEqual([e["key"] for e in self.events("alert")], ["report"])
        run.event("closed")
        sr.watch_run(run, 5000)
        self.assertEqual(len(self.events("alert")), 1)

    def test_sleep_gap_is_reported_on_the_next_tick(self):
        run = self.supervisor_gone()
        with mock.patch.object(sr, "cmd_start"):
            sr.watch_run(run, 3000)
        self.assertTrue(any(e["key"].startswith("slept:") for e in self.events("alert")))

    def test_wait_returns_on_wake_and_on_a_silent_supervisor(self):
        run = sr.Run(self.dir)
        run.event("run_start", pid=999999)
        run.heartbeat.write_text(json.dumps({"pid": 999999, "ts": time.time() - 500}))
        self.assertEqual(sr.main(["wait", str(self.dir), "--poll", "0.01"]), 11)
        run.event("run_end", reason="x", code=0)
        run.event("wake", seq=1, reason="x")
        self.assertEqual(sr.main(["wait", str(self.dir), "--poll", "0.01"]), 0)


class Helpers(unittest.TestCase):
    def test_signature_names_failing_tests_and_ignores_numbers(self):
        self.assertEqual(sr.signature("FAIL: test_b (x.T)\nERROR: test_a (x.T)\nRan 2 tests in 0.1s\n"), "test_a,test_b")
        self.assertEqual(sr.signature("boom at line 12\n\n"), sr.signature("boom at line 99\n"))

    def test_reset_wait_reads_the_real_message(self):
        ts = time.mktime((2026, 11, 3, 14, 0, 0, 0, 0, -1))
        self.assertAlmostEqual(sr.reset_wait("You've hit your session limit · resets 3:40pm (Europe/Moscow)", 1800, ts), 6000 + 120, delta=2)
        self.assertAlmostEqual(sr.reset_wait("resets 1am (Europe/Moscow)", 1800, ts), 11 * 3600 + 120, delta=2)
        self.assertEqual(sr.reset_wait("limit reached", 1800, ts), 1800)


if __name__ == "__main__":
    unittest.main()
