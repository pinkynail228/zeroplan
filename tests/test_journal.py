"""A6a: the project journal -- the engine history reader (C1), duration-stamped steps (C2) and the store (C3).

A fake `zeroshot` script (a loopback HTTP server that prints the real `Zeroshot UI: <origin>/ui/` line) stands in for
the engine; no real `zeroshot`, no network beyond loopback, scratch paths only.

Interpretations: a listing stops at `complete`, or when `nextCursor` is missing or does not move (`/runs` has no
`complete` flag); a step whose completion has no earlier start (the history was read from a later cursor) is kept with
`start`/`duration` None; `append` refuses a kind outside step/action/learning and a learning without cause/defect/fix.
"""

from pathlib import Path
import shutil
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

from terminal_planner import catalog, journal
from terminal_planner.authority import Blocked
from terminal_planner.engine import NativeEngine

SERVER = '''#!%(python)s
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse
PAGES = {"v2:0": {"events": [{"cursor": "v2:1", "event": {"kind": "safe_log"}}], "nextCursor": "v2:1", "complete": False},
         "v2:1": {"events": [{"cursor": "v2:2", "event": {"kind": "terminal"}}], "nextCursor": "v2:2", "complete": True}}
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        after = parse_qs(url.query).get("after", ["v2:0"])[0]
        if url.path == "/ui/api/runs" and "after" in parse_qs(url.query):
            body, code = {"error": "invalid cursor"}, 400  # the real listing's cursor is a run id, not `v2:N`
        elif url.path == "/ui/api/runs":
            body, code = {"runs": [{"runId": "r1"}], "nextCursor": None}, 200
        elif url.path == "/ui/api/runs/r1/history":
            body, code = PAGES[after], 200
        elif url.path == "/ui/api/runs/moved/history":
            self.send_response(302); self.send_header("Location", "/ui/api/runs/r1/history"); self.end_headers(); return
        elif url.path == "/ui/api/runs/bad/history":
            self.send_response(200); self.end_headers(); self.wfile.write(b"not json"); return
        else:
            body, code = {"error": "unknown"}, 404
        self.send_response(code); self.end_headers(); self.wfile.write(json.dumps(body).encode())
    def log_message(self, *args): pass
if sys.argv[1:3] != ["ui", "--listen"]:
    sys.exit(2)
%(listen)s
'''
LISTEN = '''server = HTTPServer(("127.0.0.1", 0), Handler)
sys.stderr.write("Zeroshot UI: http://127.0.0.1:%d/ui/\\n" % server.server_port); sys.stderr.flush()
server.serve_forever()'''
SILENT = "import time; time.sleep(60)"
# The npm launcher shape: the server is the launcher's own child and a signal to the launcher is not passed on.
WRAPPED = '''import os, signal, subprocess
from pathlib import Path
if os.environ.get("ZJ_CHILD") is None:
    signal.signal(signal.SIGTERM, lambda *_: os._exit(143))
    subprocess.call([sys.executable, __file__, *sys.argv[1:]], env=dict(os.environ, ZJ_CHILD="1"))
    sys.exit(0)
Path(__file__).with_name("child.pid").write_text(str(os.getpid()))
''' + LISTEN


def log(timestamp):
    return {"event": {"kind": "safe_log", "timestamp": timestamp, "execution": "x"}}


def started(execution, node):
    return {"event": {"kind": "node_started", "reference": {"execution": execution, "node": node}}}


def completed(execution, node, status, message=""):
    outcome = {"status": status, "diagnostic": {"message": message}}
    return {"event": {"kind": "node_completed",
                      "completion": {"reference": {"execution": execution, "node": node}, "outcome": outcome}}}


def usage(execution, tokens_in, tokens_out):
    return {"event": {"kind": "token_usage_observed", "execution": execution,
                      "usage": {"inputTokens": tokens_in, "outputTokens": tokens_out}}}


class JournalTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="zj-", dir="/tmp"))
        self.addCleanup(shutil.rmtree, self.root, True)

    def engine(self, listen=LISTEN):
        binary = self.root / "zeroshot"
        binary.write_text(SERVER % {"python": sys.executable, "listen": listen})
        binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
        return NativeEngine(binary, self.root / "state", environment={"PATH": "/usr/bin:/bin"})

    def test_reader_follows_pages_and_stops_the_child(self):
        """C1: both pages in order, the run list, 404 and bad JSON are `journal.history_unavailable`, exit ends the child."""
        with journal.Reader(self.engine()) as reader:
            process = reader.process
            events = reader.history("r1")
            self.assertEqual([item["cursor"] for item in events], ["v2:1", "v2:2"])
            self.assertEqual(reader.runs(), [{"runId": "r1"}])
            for run in ("unknown", "bad", "moved"):  # a redirect is not followed, even to a valid history
                with self.assertRaises(Blocked) as raised:
                    reader.history(run)
                self.assertEqual(raised.exception.family, "journal.history_unavailable")
        self.assertIsNotNone(process.poll())
        self.assertIn("journal.history_unavailable", catalog.ERRORS)

    def test_exit_ends_the_server_behind_a_launcher(self):
        """C1: with the npm launcher shape, exit ends the launcher's child too, and does not hang."""
        import os, threading, time
        reader = journal.Reader(self.engine(WRAPPED))
        reader.start()
        self.assertEqual([item["cursor"] for item in reader.history("r1")], ["v2:1", "v2:2"])
        child = int((self.root / "child.pid").read_text())
        stopping = threading.Thread(target=reader.stop, daemon=True)
        stopping.start()
        stopping.join(20)
        self.assertFalse(stopping.is_alive(), "stop() hangs")
        for _ in range(40):
            try:
                os.kill(child, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            self.fail("the launcher's child survived the reader")

    def test_the_launcher_is_reaped_after_the_last_group_signal(self):
        """C1: every group signal goes out while the launcher is unreaped, so its pid (the group id) is not reused."""
        import os, signal
        reader = journal.Reader(self.engine(WRAPPED))
        reader.start()
        process, seen, real = reader.process, [], os.killpg
        def spy(group, number):
            seen.append((number, process.returncode))
            real(group, number)
        with patch.object(journal.os, "killpg", spy):
            reader.stop()
        self.assertEqual(seen, [(signal.SIGTERM, None), (signal.SIGKILL, None)])
        self.assertIsNotNone(process.returncode)

    def test_reader_without_an_origin_line_is_unavailable(self):
        """C1: no `Zeroshot UI:` line within the deadline -> `journal.history_unavailable`, child gone."""
        reader = journal.Reader(self.engine(SILENT))
        with patch.object(journal, "LISTEN_DEADLINE", 0.5), self.assertRaises(Blocked) as raised:
            reader.start()
        self.assertEqual(raised.exception.family, "journal.history_unavailable")
        self.assertIsNone(reader.process)

    def test_steps_of_the_a3c_shape(self):
        """C2: worker 1, acceptance 2, code 3 -> three steps with times, verdict, tokens."""
        events = [log(1000), started("e1", "worker"), log(1500), usage("e1", 10, 5), log(61000),
                  completed("e1", "worker", "verified", "done\nsecond line"),
                  started("e2", "acceptance"), started("e3", "code"), log(70000),
                  completed("e2", "acceptance", "verified", "ok password=hunter2 " + "x" * 300),
                  completed("e3", "code", "failed", ""), usage("e3", 1, 2), usage("nobody", 9, 9)]
        found = journal.steps(events)
        self.assertEqual([step["node"] for step in found], ["worker", "acceptance", "code"])
        worker = found[0]
        self.assertEqual((worker["status"], worker["start"], worker["end"], worker["duration"], worker["tokens"],
                          worker["verdict"]), ("verified", 1000, 61000, 60.0, 15, "done"))
        self.assertEqual((found[1]["start"], found[1]["end"], found[1]["duration"]), (61000, 70000, 9.0))
        self.assertLessEqual(len(found[1]["verdict"]), 200)
        self.assertNotIn("hunter2", found[1]["verdict"])
        self.assertEqual((found[2]["status"], found[2]["tokens"]), ("failed", 3))
        lone = journal.steps([started("e", "worker"), completed("e", "worker", "verified")])[0]
        self.assertEqual((lone["start"], lone["end"], lone["duration"]), (None, None, None))

    def test_store_appends_stamped_lines_and_skips_a_torn_one(self):
        """C3: a learning record and a torn last line -> `load` returns the one record."""
        path = self.root / "sub" / "journal.jsonl"
        stored = journal.append(path, {"kind": "learning", "cause": "c", "defect": "d", "fix": "f"})
        self.assertRegex(stored["at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        with open(path, "a") as handle:
            handle.write('{"kind": "step", "exec')
        self.assertEqual(journal.load(path), [stored])
        later = journal.append(path, {"kind": "action", "what": "next run"})  # appended after the torn tail
        self.assertEqual(journal.load(path), [stored, later])
        self.assertEqual(journal.load(self.root / "missing"), [])
        with self.assertRaises(ValueError):
            journal.append(path, {"kind": "note"})


if __name__ == "__main__":
    unittest.main()
