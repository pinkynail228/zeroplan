"""Offline tests for the Herdr monitor: a fake `herdr` on PATH reports the architect's state and records prompts."""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import stat
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import slice_monitor as sm
import slice_run as sr

FAKE = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
root = pathlib.Path(os.environ["FAKE_HERDR"])
with open(root / "calls.jsonl", "a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\n")
if sys.argv[1:3] == ["agent", "get"]:
    status = (root / "status").read_text().strip()
    if status == "missing":
        print(json.dumps({"error": "agent_not_found"}), file=sys.stderr); sys.exit(1)
    print(json.dumps({"result": {"agent": {"agent_status": status}, "type": "agent"}}))
else:
    print(json.dumps({"result": {}}))
'''


class Monitor(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="slice-monitor.")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        fake = self.tmp / "bin" / "herdr"
        fake.parent.mkdir()
        fake.write_text(FAKE.replace("#!/usr/bin/env python3", f"#!{sys.executable}"))
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        patcher = mock.patch.dict(os.environ, {"FAKE_HERDR": str(self.tmp), "PATH": f"{fake.parent}:{os.environ['PATH']}", "SLICE_NO_OSA": "1"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.root = self.tmp / "slices"
        self.dir = self.root / "r1"
        (self.dir / "contracts").mkdir(parents=True)
        (self.dir / "run.toml").write_text(f'run = "r1"\nrepo = "{self.tmp}"\nqueue = ["S1"]\n')
        self.run = sr.Run(self.dir)
        sm._notified.clear()
        self.status("idle")

    def status(self, value):
        (self.tmp / "status").write_text(value)

    def tick(self):
        sm.main(["watch", "--agent", "arch", "--root", str(self.root), "--once"])

    def prompts(self):
        path = self.tmp / "calls.jsonl"
        rows = [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []
        return [r for r in rows if r[:2] == ["agent", "prompt"]]

    def notifications(self):
        path = self.tmp / "calls.jsonl"
        return [json.loads(x) for x in path.read_text().splitlines() if '"notification"' in x] if path.exists() else []

    def ended_with_wake(self, reason="passed 3"):
        self.run.event("run_start", pid=os.getpid())
        self.run.event("run_end", reason=reason, code=0)
        sr.wake(self.run, reason)

    def test_wake_waits_for_an_idle_architect_then_prompts_once(self):
        self.ended_with_wake()
        self.status("working")
        self.tick()
        self.assertEqual(self.prompts(), [])
        self.status("idle")
        self.tick()
        self.tick()
        self.assertEqual(len(self.prompts()), 1)
        text = self.prompts()[0][3]
        self.assertIn("WAKE 1: passed 3", text)
        self.assertIn("ack", text)
        self.assertEqual([e["key"] for e in self.run.events() if e["event"] == "architect_prompted"], ["wake:1"])

    def test_acknowledged_wake_is_not_prompted(self):
        self.ended_with_wake()
        sr.main(["ack", str(self.dir)])
        self.tick()
        self.assertEqual(self.prompts(), [])

    def test_a_new_wake_after_an_ack_is_prompted_again(self):
        self.ended_with_wake()
        self.tick()
        sr.main(["ack", str(self.dir)])
        self.ended_with_wake("S2:same_failure")
        self.tick()
        self.assertEqual([p[3].split(":")[0] for p in self.prompts()], ["[slices r1] WAKE 1", "[slices r1] WAKE 2"])

    def test_blocked_or_missing_architect_tells_the_owner_and_prompts_nothing(self):
        self.ended_with_wake()
        for state in ("blocked", "missing"):
            self.status(state)
            self.tick()
        self.tick()
        self.assertEqual(self.prompts(), [])
        self.assertEqual(len(self.notifications()), 2, "one per state, the repeat is throttled")

    def test_silent_supervisor_is_reported_once(self):
        self.run.event("run_start", pid=999999)
        self.tick()
        self.tick()
        self.assertEqual(len(self.prompts()), 1)
        self.assertIn("supervisor silent", self.prompts()[0][3])

    def test_board_says_plainly_what_is_going_on(self):
        self.assertIn("r1: \u0435\u0449\u0451 \u043d\u0435 \u0437\u0430\u043f\u0443\u0441\u043a\u0430\u043b\u0441\u044f", sm.board_text(self.root))
        self.ended_with_wake("S1:blocked")
        self.assertIn("\u0436\u0434\u0451\u0442 \u0440\u0435\u0448\u0435\u043d\u0438\u044f \u0430\u0440\u0445\u0438\u0442\u0435\u043a\u0442\u043e\u0440\u0430: S1:blocked", sm.board_text(self.root))
        sr.main(["ack", str(self.dir)])
        sr.main(["close", str(self.dir)])
        text = sm.board_text(self.root)
        self.assertIn("\u0437\u0430\u043a\u0440\u044b\u0442\u044b\u0435: r1 \u27130", text)
        self.assertIn("\u0430\u043a\u0442\u0438\u0432\u043d\u044b\u0445 \u043f\u0440\u043e\u0433\u043e\u043d\u043e\u0432 \u043d\u0435\u0442", text)
        self.assertNotIn("DEAD", text)

    def test_board_flags_a_silent_supervisor(self):
        self.run.event("run_start", pid=999999)
        self.assertIn("\u0421\u0423\u041f\u0415\u0420\u0412\u0418\u0417\u041e\u0420 \u041d\u0415 \u041e\u0422\u0412\u0415\u0427\u0410\u0415\u0422", sm.board_text(self.root))

    def test_each_tick_leaves_a_heartbeat_that_lets_a_run_start(self):
        self.assertTrue(sr.monitor_problem(self.root))
        self.tick()
        self.assertEqual(sr.monitor_problem(self.root), "")
        beat = json.loads((self.root / sr.MONITOR_BEAT).read_text())
        beat["ts"] -= 3 * sr.MONITOR_STALE_S
        (self.root / sr.MONITOR_BEAT).write_text(json.dumps(beat))
        self.assertTrue(sr.monitor_problem(self.root))

    def test_closed_run_is_ignored(self):
        self.ended_with_wake()
        sr.main(["close", str(self.dir)])
        self.tick()
        self.assertEqual(self.prompts(), [])


if __name__ == "__main__":
    unittest.main()
