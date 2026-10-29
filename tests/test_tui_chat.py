"""U3b: the architect chat of the full-screen shell. One conversation per project, one turn per owner message.

A scripted fake codex (the same fixture shape as test_architect) stands behind the adapter; the app is driven by
Textual Pilot over a real temporary Git repository. No provider, no network, no login. Textual tests skip without
the wheels of ZPLAN_TEST_WHEELHOUSE; the chat's own unit tests need no Textual at all.

i2 note: this module's checks of the old *main* key bar (the reserved `[c]`/`[t]` labels and the `[ctrl+q] выход`
hint) are retired here, because i2 replaced the main screen's row with the shared `activity.Bar` (checked in
`tests/test_tui_commands.py`, A3). The bar-only tests were deleted and the mixed ones kept only their behaviour
checks (`goal_draft_to_open()`/`answer_draft_to_open()`, the [c]/[t] keys opening a form) — the draft keys
themselves do not change; the later card runs (i3a/i3d) own the draft UI that replaces them."""

import collections
import asyncio
import contextlib
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from terminal_planner import architect as adapter
from terminal_planner import catalog, engine, milestone, process, setup, toolchain
from terminal_planner import planning as planning_module, runs as runs_module
from terminal_planner.architect import Architect, ArchitectStore
from terminal_planner.authority import Authority as RealAuthority, Blocked, atomic_state, canonical, decode
from terminal_planner.delivery import Delivery, Token
from terminal_planner.engine import NativeEngine, fixture_proposal
from terminal_planner.runs import MilestoneRuns, NativeDriver
from terminal_planner.tui import controller as controller_module
from terminal_planner.tui import chat as chat_module
from test_architect import MCP_LIST
from test_tui import Readiness, check
from test_terminal_planner import ROLES
from test_tui_milestones import DIRTY, MilestoneShell
from tui_support import HAVE_TEXTUAL, screen_lines, screen_text

# The reason the other TUI modules give when Textual is missing: without it the TUI test classes below are
# still declared (unittest discovery must see them) and skipped, never hidden.
TEXTUAL_REASON = "Textual недоступен: нужен ZPLAN_TEST_WHEELHOUSE с wheels textual 8.2.8"


def short_root(prefix="z"):
    """A short private state root for the native controller/watch sockets, independent of `tempfile.gettempdir()`.

    The long-TMPDIR qualification runs this whole module with an intentionally long TMPDIR, and `mkdtemp` would
    inherit it: the controller socket path (`<root>/runs/runs/<36 digits>/controller.sock`, 63 bytes on top of the
    root) then stops fitting macOS' 104-byte limit and the native watch tests fail on a path nobody chose. `/tmp`
    is the shortest writable base on both hosts the suite runs on (macOS resolves it to `/private/tmp`), so the
    root stays short whatever the process TMPDIR is — and still private to this process."""
    return Path(tempfile.mkdtemp(prefix=prefix, dir="/tmp")).resolve()


def tui_module():
    """The TUI app module, imported lazily: it needs Textual (and rich), which the pure tests must not require."""
    from terminal_planner.tui import app as module
    return module


CLOCK = re.compile(r" \u00b7 \d\d:\d\d")


def chat_band(app):
    """The chat pane's part of the screen, with the pane's wrap breaks and i9's two renderer marks taken out.

    `screen_text` is row by row and interleaves the two panes: a header line the pane wrapped sits on two rows, and
    the plan pane's text comes between its halves. Cutting every row at the pane boundary and flattening what is
    left reads the chat as the user sees it, wherever the renderer broke a line. Three marks the renderer draws
    interleave with the text and are not part of it: the architect message's magenta left bar (`\u258c`, one per row
    of the message), the author line's clock (`\u00b7 HH:MM`, which the wall clock decides, not the test) and the
    `#chat` scroll's own vertical bar (Textual's `\u2581`..`\u2587` thumb, at the right end of a scrollable history).
    All three are taken out so a test can name a message by its author and body alone; the author line itself is
    checked as drawn in `tests/test_tui_look.py`."""
    band = []
    right = app.query_one("#chat-pane").region.right  # the pane's own right edge: the canvas frame begins there
    for line in screen_lines(app):
        band.append(line[:right].strip(" │▌▁▂▃▄▅▆▇"))
    return " ".join(CLOCK.sub("", " ".join(band)).split())


FAKE = r'''#!%(python)s
import json, os, signal, subprocess, sys, time
here = os.path.dirname(os.path.abspath(__file__))
scenario = json.load(open(os.path.join(here, "scenario.json")))
if "--help" in sys.argv:
    print(scenario.get("help", "exec --json --sandbox --cd --model --config"))
    sys.exit(0)
''' + MCP_LIST + r'''if scenario.get("ignore_term"):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)  # the whole group: only SIGKILL ends it
calls = os.path.join(here, "calls.jsonl")
index = sum(1 for _ in open(calls)) if os.path.exists(calls) else 0
prompt = sys.stdin.read()
with open(calls, "a") as stream:
    stream.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(), "stdin": prompt}) + "\n")
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
if step.get("release"):
    # An explicit handshake, not a timer: emit the whole reply, then keep the process alive until the test
    # creates the release file. The turn therefore completes exactly when the test decides, never on a sleep.
    end = time.time() + step.get("release_timeout", 30)
    while not os.path.exists(step["release"]) and time.time() < end:
        time.sleep(0.02)
if step.get("hang"):
    time.sleep(step["hang"])
sys.exit(step.get("exit", 0))
'''

THREAD = "0199aaaa-bbbb-cccc-dddd-eeeeffff0001"
OPENING = [{"type": "thread.started", "thread_id": THREAD}, {"type": "turn.started"}]
REPLY = OPENING + [{"type": "item.completed", "item": {"id": "item_0", "type": "agent_message", "text": "Привет."}},
                   {"type": "turn.completed", "usage": {"input_tokens": 10, "cached_input_tokens": 2,
                                                        "output_tokens": 5}}]
# A reply whose text carries a terminal control sequence: the model supplies the chat text, so it must never reach
# the screen as an escape (the pane takes the sequence out per L-2, before anything else looks at the text).
ESCAPED = OPENING + [{"type": "item.completed", "item": {"id": "item_0", "type": "agent_message",
                                                         "text": "начало\x1b[2Jконец"}},
                     {"type": "turn.completed", "usage": {"output_tokens": 1}}]
PARTIAL = OPENING + [{"type": "item.completed", "item": {"id": "item_0", "type": "agent_message",
                                                         "text": "Начало ответа"}}]
HEADER = chat_module.ChatHeader(home="~/.codex", provider="openai", model="gpt-6.1-sol", effort="high")


def says(text, usage=3):
    """A completed turn whose final agent message is `text` (the final reply, never the streamed partial)."""
    return OPENING + [{"type": "item.completed", "item": {"id": "item_0", "type": "agent_message", "text": text}},
                      {"type": "turn.completed", "usage": {"output_tokens": usage}}]


def goal_block(body):
    """One fenced goal draft exactly as the protocol defines it (the opener, the body, the closer)."""
    return "```zplan-goal\n" + body + "\n```"


def answer_block(milestone, body):
    """One fenced answer draft for `milestone`, exactly as the protocol defines it."""
    return "```zplan-answer " + milestone + "\n" + body + "\n```"


WATCH = r'''#!%(python)s
import os, signal, subprocess, sys, time
here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "watch.calls"), "a") as stream:
    stream.write(" ".join(sys.argv[1:]) + "\n")
signal.signal(signal.SIGTERM, signal.SIG_IGN)  # a watcher only SIGKILL ends, on the watcher and the child it made
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
with open(os.path.join(here, "watch.pids"), "w") as stream:
    stream.write("%%d %%d" %% (os.getpid(), child.pid))
time.sleep(300)
'''


# A watch that writes one complete JSONL record and then a truncated one (no trailing newline, invalid JSON), the
# shape `cut_watches` leaves behind: a normal quit cuts the observer while it is still writing a record. A real
# record without a trailing newline is still valid JSON, so the tail here is genuinely incomplete.
CUT_WATCH = r'''#!%(python)s
import json, os, sys, time
here = os.path.dirname(os.path.abspath(__file__))
sys.stdout.write(json.dumps({"cursor": "c1", "phase": "running"}) + "\n")
sys.stdout.write('{"cursor": "c2", "phase": "run')
sys.stdout.flush()
open(os.path.join(here, "cut.ready"), "w").close()
time.sleep(300)
'''


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def gone(pid, timeout=6.0):
    """Wait until the process (or the group leader) is gone; True when it is."""
    end = time.monotonic() + timeout
    while alive(pid) and time.monotonic() < end:
        time.sleep(0.05)
    return not alive(pid)


class GatedStore(ArchitectStore):
    """A store whose (armed) transcript read blocks until the test releases it: the window where a cancel lands
    after Enter but before the Codex process exists."""

    def __init__(self, project):
        super().__init__(project)
        self.armed = False
        self.inside = threading.Event()
        self.release = threading.Event()

    def transcript(self):
        if self.armed:
            self.armed = False
            self.inside.set()
            self.release.wait(5)
        return super().transcript()


class StampPausedStore(ArchitectStore):
    """A store whose timestamp reader (the `zplan-chat-stamp` thread) stops right after it read a transcript that
    holds the owner row, handing back that (soon stale) read only when the test releases it."""

    def __init__(self, project):
        super().__init__(project)
        self.inside = threading.Event()
        self.release = threading.Event()

    def transcript(self):
        rows = super().transcript()
        if threading.current_thread().name == "zplan-chat-stamp" and not self.inside.is_set() \
                and any(row.get("role") == "owner" for row in rows):
            self.inside.set()
            self.release.wait(10)
        return rows


class Deferred:
    """A hand_over that parks the UI callbacks instead of running them, so a test can watch the bounded inbox."""

    def __init__(self):
        self.pending = collections.deque()
        self.wakes = 0

    def hand_over(self, call):
        self.wakes += 1
        self.pending.append(call)

    def drain(self):
        while self.pending:
            self.pending.popleft()()


class Fixture:
    """The scripted codex of one project, as the tests and both prepares use it."""

    def __init__(self, root, project):
        self.root, self.project = Path(root), Path(project)
        self.bin = self.root / "codex-bin"
        self.bin.mkdir(exist_ok=True)
        self.codex = self.bin / "codex"
        self.codex.write_text(FAKE % {"python": sys.executable})
        self.codex.chmod(0o755)
        home = self.root / "codex-home"
        home.mkdir(exist_ok=True)
        (home / "auth.json").write_text("{}\n")  # a login: the turn home check (R-5) judges presence only
        self.env = {"PATH": os.environ.get("PATH", ""), "CODEX_HOME": str(home)}
        self.script([{"lines": REPLY}])

    def script(self, steps, **extra):
        (self.bin / "scenario.json").write_text(json.dumps({"steps": steps, **extra}))

    def calls(self):
        path = self.bin / "calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def store(self, cls=ArchitectStore):
        return cls(self.project)

    def architect(self, store=None, project=None):
        return Architect(self.codex, self.env, project or self.project, "gpt-6.1-sol", "high",
                         store=store or self.store())

    def binding(self, model="gpt-6.1-sol", effort="high"):
        """The effective architect role the chat re-reads before every turn (the app hands it the project, the chat
        calls it without one); the default keeps `HEADER`'s model and effort truthful."""
        return lambda project=None: (model, effort)

    def prepare(self, store=None, project=None, delay=0.0):
        """The prepare the app gets: the scripted codex as the architect of `project` (the app's by default).

        The chat calls it with no argument, the app hands it its own project, so `passed` wins when present."""
        def build(passed=None):
            if delay:
                time.sleep(delay)
            return self.architect(store=store, project=passed or project), HEADER
        return build

    def files(self):
        """The store's bytes without the lock file: what a refused operation must leave untouched."""
        directory = self.store().directory
        return {path.name: path.read_bytes() for path in directory.iterdir() if path.name != "lock"} \
            if directory.exists() else {}


def turn_starts(spy):
    """The Popen calls of `spy` that launch a turn: the server check (`codex mcp list`) before it is not one."""
    return [call for call in spy.call_args_list if call.args[0][1:3] != ["mcp", "list"]]


class ChatUnitTests(unittest.TestCase):
    """The chat without Textual: threads, the store lock, the bounded inbox and the reset session."""

    def setUp(self):
        from test_terminal_planner import ProjectTest
        case = ProjectTest("run")
        case.setUp()
        self.addCleanup(case.doCleanups)
        self.project, self.state, self.root = case.project, case.state, case.root
        self.fixture = Fixture(self.root, self.project)

    def chat(self, **kw):
        store = kw.pop("store", None)
        project = kw.pop("project", None)
        gate = kw.pop("gate", None)
        # The fixture's own role: the production binding would read the machine's configuration and spawn git,
        # which the process-counting tests (C-5) must not see; the tests that exercise it pass it explicitly.
        kw.setdefault("binding", self.fixture.binding())
        instance = chat_module.ArchitectChat(project or self.project, self.fixture.prepare(store=store, project=project),
                                             **kw)
        self.addCleanup(instance.close)
        instance.start()
        end = time.monotonic() + 5
        while instance.state.phase == "preparing" and time.monotonic() < end:
            if gate is not None:
                gate.drain()  # a parked hand_over needs its callbacks run by the test
            time.sleep(0.005)
        self.assertNotEqual(instance.state.phase, "preparing", instance.state)
        return instance

    @staticmethod
    def wait(condition, timeout=5.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if condition():
                return True
            time.sleep(0.01)
        return bool(condition())

    def drain_until(self, gate, condition, timeout=10.0):
        """Run a `Deferred` hand-over's parked UI callbacks until `condition` holds; the test is the only drainer."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            gate.drain()
            if condition():
                return True
            time.sleep(0.01)
        return bool(condition())

    # C-6 -----------------------------------------------------------------------

    def test_i9_a5_a_running_turn_stamps_its_owner_line_from_the_store(self):
        """i9/A5 repair: the line a send posts is optimistic — the row it reconciles with does not exist yet, so it
        carries no time — and the reply then waits (a gated fixture turn). The store row the turn writes
        before Codex starts must reach the line while the turn still runs: the re-read the turn starts (`chat.py`'s
        `_stamp_owner_line`) stamps the optimistic entry with the stored `ts` at the same place, so the entry can
        stand behind its time line before the turn ends, not only after it."""
        release = self.root / "release"
        self.fixture.script([{"lines": OPENING, "release": str(release), "release_timeout": 30}])
        gate = Deferred()
        chat = self.chat(hand_over=gate.hand_over, gate=gate)
        try:
            self.assertTrue(chat.send("вопрос")[0])
            self.assertEqual(chat.state.entries[-1].at, "")  # the optimistic line: no stored time yet
            self.assertTrue(self.drain_until(gate, lambda: chat.state.entries[-1].at), chat.state)
            rows = [row for row in self.fixture.store().transcript() if row["role"] == "owner"]
            self.assertEqual([row["text"] for row in rows], ["вопрос"])
            self.assertEqual(chat.state.entries[-1].at, rows[0]["ts"])
            self.assertTrue(chat.busy)  # the reply still waits: the clock came from the turn's own row
        finally:
            release.write_text("go")
            chat.close()

    def test_i9_a5_a_late_timestamp_read_never_drops_the_reply_that_landed_meanwhile(self):
        """i9-look-fix F2 (regression): the stamp reader read the transcript while it held only the owner row and was
        held there; the reply then completed and its events drained; only then was the reader released. Its stale
        read must stamp the owner line alone — a whole-history replacement would put `[owner]` over
        `[owner, architect]` and lose «Привет.» from the UI (it stays in the store). The final history is both
        entries, in order, and the owner line carries its stored `ts`. No interpretation beyond the task's example."""
        store = StampPausedStore(self.project)
        gate = Deferred()
        chat = self.chat(store=store, hand_over=gate.hand_over, gate=gate)
        try:
            self.assertTrue(chat.send("ordinary question")[0])
            self.assertTrue(store.inside.wait(5))  # the reader holds its read of [owner]
            self.assertTrue(self.drain_until(gate, lambda: not chat.busy
                                             and [e.role for e in chat.state.entries] == ["owner", "architect"]),
                            chat.state)
            store.release.set()
            self.assertTrue(self.wait(lambda: not any(t.name == "zplan-chat-stamp" for t in threading.enumerate())))
            gate.drain()  # the released reader's stamp reaches the UI after the reply did
            self.assertEqual([(e.role, e.text) for e in chat.state.entries],
                             [("owner", "ordinary question"), ("architect", "Привет.")])
            self.assertRegex(chat.state.entries[0].at, r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        finally:
            store.release.set()
            chat.close()

    def test_c6_two_windows_take_turns_and_each_reloads_the_other_history(self):
        first, second = self.chat(), self.chat()
        self.assertTrue(first.ready and second.ready)
        self.assertTrue(first.send("первый")[0])
        self.assertTrue(first.wait(10) and self.wait(lambda: not first.busy))
        self.assertTrue(second.send("второй")[0])
        self.assertTrue(second.wait(10) and self.wait(lambda: not second.busy))
        self.assertEqual([row["role"] for row in self.fixture.store().transcript()],
                         ["owner", "architect", "owner", "architect"])
        self.assertEqual([entry.text for entry in second.state.entries if entry.role == "owner"],
                         ["первый", "второй"])  # the second window reloaded the first window's turn
        self.assertEqual(self.fixture.calls()[1]["argv"][:3], ["exec", "resume", THREAD])  # same thread id

    def test_c6_a_send_while_the_other_window_holds_the_lock_is_refused_and_writes_nothing(self):
        before = self.fixture.files()
        chat = self.chat(store=self.fixture.store())
        with self.fixture.store().lock_path.open("w") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)  # the other window's turn
            self.assertTrue(chat.send("первый")[0])
            self.assertTrue(self.wait(lambda: not chat.busy, 6), chat.state)
        self.assertIn("architect.locked", chat.state.note)
        self.assertEqual(self.fixture.files(), before)   # refused and wrote nothing
        self.assertEqual(self.fixture.calls(), [])

    def test_c6_reset_takes_the_lock_too_and_writes_nothing_when_it_is_held(self):
        store = self.fixture.store()
        with store.lock_path.open("w") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(Blocked) as raised:
                self.fixture.architect(store=store).reset()
        self.assertEqual(catalog.family(raised.exception), "architect.locked")
        self.assertFalse(store.session_path.exists())
        self.assertFalse(store.transcript_path.exists())

    def test_c6_reset_forgets_the_thread_and_the_transcript_keeps_a_reset_entry(self):
        chat = self.chat()
        chat.send("первый")
        self.assertTrue(self.wait(lambda: not chat.busy, 6))
        self.assertEqual(self.fixture.store().load()["thread_id"], THREAD)
        self.assertTrue(chat.reset()[0])
        self.assertTrue(self.wait(lambda: not chat.busy, 6))
        self.assertIsNone(self.fixture.store().load()["thread_id"])
        self.assertEqual([row["role"] for row in self.fixture.store().transcript()][-1], "reset")
        self.assertTrue([entry for entry in chat.state.entries if entry.role == "reset"])

    def test_c6_reset_is_refused_while_a_turn_runs(self):
        self.fixture.script([{"lines": PARTIAL, "hang": 2.0}, {"lines": REPLY}])
        chat = self.chat()
        self.assertTrue(chat.send("долгий")[0])
        self.assertTrue(self.wait(lambda: chat.busy))
        accepted, line = chat.reset()
        self.assertFalse(accepted)
        self.assertIn("architect.busy", line)

    # C-6b ----------------------------------------------------------------------

    def test_c6b_a_flood_of_events_keeps_the_inbox_and_the_history_bounded(self):
        flood = OPENING + [{"type": "item.completed", "item": {"id": "i%d" % index, "type": "agent_message",
                                                              "text": "флуд %d" % index}}
                           for index in range(4000)] + [{"type": "turn.completed", "usage": {"output_tokens": 1}}]
        self.fixture.script([{"lines": flood}])
        gate = Deferred()
        chat = self.chat(pending=16, hand_over=gate.hand_over, gate=gate)
        self.assertTrue(chat.send("вопрос")[0])
        # 4000 events arrive while the UI callbacks are parked: the inbox must stay capped and wakes coalesced.
        self.assertTrue(self.wait(lambda: chat.queued >= 16, 10), chat.state)
        self.assertLessEqual(chat.queued, 16)
        time.sleep(0.3)  # the flood keeps arriving: without the cap the inbox would grow past `pending`
        self.assertLessEqual(chat.queued, 16)
        self.assertEqual(len(gate.pending), 1)  # one outstanding drain request, not one per event
        end = time.monotonic() + 30
        while chat.busy and time.monotonic() < end:  # only the UI thread can finish the turn
            gate.drain()
            time.sleep(0.01)
        self.assertFalse(chat.busy, chat.state)
        self.assertLessEqual(chat.queued, 16)
        self.assertLessEqual(len(chat.state.entries), chat_module.HISTORY)

    def test_c6b_a_flood_of_events_never_evicts_the_rebind_header_of_the_turn(self):
        """A ready chat follows the profile across turns; a turn that streams a flood of events must not evict the
        control messages (the rebind header, the turn's end) that carry the current role: the header must end on the
        model the finished turn actually used, never on the one the chat was prepared with."""
        flood = OPENING + [{"type": "item.completed", "item": {"id": "i%d" % index, "type": "agent_message",
                                                              "text": "флуд %d" % index}} for index in range(200)] \
            + [{"type": "turn.completed", "usage": {"output_tokens": 1}}]
        self.fixture.script([{"lines": REPLY}, {"lines": flood}])
        with self.roles_root():
            self.write_role("first-model", "high")
            gate = Deferred()
            chat = self.chat(binding=self.profile_binding(), hand_over=gate.hand_over, pending=16, gate=gate)
            self.assertTrue(chat.send("первый")[0])
            self.assertTrue(self.drain_until(gate, lambda: not chat.busy, 20), chat.state)
            self.assertIn("first-model/high", chat.state.header)
            self.write_role("second-model", "low")
            self.assertTrue(chat.send("второй")[0])
            # The UI is delayed until the streamed ring is full, so the flood has to drop the oldest events.
            end = time.monotonic() + 20
            while chat.queued < chat.pending and time.monotonic() < end:
                time.sleep(0.01)
            self.assertEqual(chat.queued, chat.pending)
            self.assertTrue(self.drain_until(gate, lambda: not chat.busy, 20), chat.state)
        self.assertIn("second-model/low", chat.state.header)
        self.assertNotIn("gpt-6.1-sol/high", chat.state.header)
        argv = self.fixture.calls()[1]["argv"]
        self.assertEqual(argv[argv.index("-m") + 1], "second-model")  # the turn really used the new role

    def test_c6b_the_displayed_history_keeps_only_the_bounded_tail_of_the_store(self):
        store = self.fixture.store()
        for index in range(100):
            store.append("owner", text="строка %d" % index)
        chat = self.chat(store=store, history=5)
        self.assertEqual([entry.text for entry in chat.state.entries],
                         ["строка %d" % index for index in range(95, 100)])
        self.assertEqual(len(store.transcript()), 100)  # the store keeps the whole transcript

    def test_c6b_the_usage_counters_come_from_the_stored_session(self):
        chat = self.chat()
        chat.send("первый")
        self.assertTrue(self.wait(lambda: not chat.busy, 6))
        # input 10 (cached_input 2 is inside it) + output 5: the counters are not summed over every usage key, and
        # the state keeps the two integers (the row is laid out from them, not parsed back out of a line)
        self.assertEqual(chat.state.usage, (1, 15))

    # C-7 -----------------------------------------------------------------------

    def prepare_patches(self, config=None):
        """The production preparation with the tools stubbed out: the fixture's scripted codex is the installed one
        and the user's configuration lives under `config` (default: this test's own directory)."""
        config = config or (self.root / "roles-config")
        config.mkdir(exist_ok=True)
        home = setup.codex_home(self.fixture.env)
        home.mkdir(parents=True, exist_ok=True)
        (home / "auth.json").write_text("{}", encoding="utf-8")  # a login, so only the role can fail
        return (patch.object(process, "config_root", lambda: config),
                patch.object(setup, "check_installation", return_value=self.fixture.bin),
                patch.object(setup, "tool_paths", return_value=(None, self.fixture.codex)),
                patch.object(setup, "native_environment", return_value=self.fixture.env))

    def test_c7_an_invalid_architect_role_is_refused_with_its_remedy(self):
        """A roles.json that cannot be read must never be answered with the preset: the chat shows the catalog
        refusal and its remedy instead of a ready architect nobody chose."""
        with contextlib.ExitStack() as stack:
            for patcher in self.prepare_patches():
                stack.enter_context(patcher)
            (self.root / "roles-config" / "roles.json").write_text(
                json.dumps({"architect": {"model": "", "effort": "high"}}), encoding="utf-8")
            with self.assertRaises(Blocked) as raised:
                chat_module.default_prepare(self.project)
            self.assertEqual(catalog.family(raised.exception), "readiness.roles")
            self.assertIn("zplan roles", str(raised.exception))
            instance = chat_module.ArchitectChat(self.project, lambda: chat_module.default_prepare(self.project))
            self.addCleanup(instance.close)
            instance.start()  # the same refusal reaches the chat, which shows it instead of a ready architect
            self.assertTrue(self.wait(lambda: instance.state.phase != "preparing", 5), instance.state)
            self.assertEqual(instance.state.phase, "blocked")
            self.assertIn("readiness.roles", instance.state.refusal)
            self.assertIn("zplan roles", instance.state.refusal)

    def test_c7_a_malformed_project_profile_is_refused_with_its_remedy(self):
        """A zplan.process.json whose architect role is invalid (an empty model) is a broken *effective* profile:
        the chat must show the catalog refusal (process.invalid) with its remedy, never the silent preset."""
        with contextlib.ExitStack() as stack:
            for patcher in self.prepare_patches():
                stack.enter_context(patcher)
            (self.project / "zplan.process.json").write_text(
                json.dumps({"roles": {"architect": {"model": "", "effort": "high"}}}), encoding="utf-8")
            with self.assertRaises(Blocked) as raised:
                chat_module.default_prepare(self.project)
            self.assertEqual(catalog.family(raised.exception), "process.invalid")
            self.assertIn("Give a model ID", str(raised.exception))  # the remedy travels with the refusal
            instance = chat_module.ArchitectChat(self.project, lambda: chat_module.default_prepare(self.project))
            self.addCleanup(instance.close)
            instance.start()  # the same refusal reaches the chat, which shows it instead of a ready architect
            self.assertTrue(self.wait(lambda: instance.state.phase != "preparing", 5), instance.state)
            self.assertEqual(instance.state.phase, "blocked")
            self.assertIn("process.invalid", instance.state.refusal)

    def test_c7_a_blocked_chat_prepares_again_once_retried(self):
        """A refused chat is not stuck: `retry()` (what the app calls once readiness is fixed) prepares it again on
        its own thread and without a turn, so a fixed toolchain, login or role is picked up without a restart; a
        ready chat is left alone."""
        calls = []
        build = self.fixture.prepare()

        def flaky(project=None):
            calls.append(project)
            if len(calls) == 1:
                raise Blocked("Нет входа Codex; выполните zplan login.", family="readiness.auth")
            return build(project)

        instance = chat_module.ArchitectChat(self.project, flaky)
        self.addCleanup(instance.close)
        instance.start()
        self.assertTrue(self.wait(lambda: instance.state.phase != "preparing", 5), instance.state)
        self.assertEqual(instance.state.phase, "blocked")
        self.assertIn("login", instance.state.refusal)
        instance.retry()
        self.assertTrue(self.wait(lambda: instance.state.phase == "ready", 5), instance.state)
        self.assertEqual(len(calls), 2)
        instance.retry()  # a ready chat is not prepared a third time
        time.sleep(0.05)
        self.assertEqual(len(calls), 2)

    def roles_root(self):
        """The user configuration root of this test: an accepted project profile never reads the machine's
        roles.json, so the binding tests stay deterministic."""
        config = self.root / "roles-config"
        config.mkdir(exist_ok=True)
        return patch.object(process, "config_root", lambda: config)

    def write_role(self, model, effort):
        """The effective project profile (zplan.process.json) with one architect role."""
        profile = self.project / process.PROFILE_FILE
        profile.write_text(json.dumps({"roles": {"architect": {"model": model, "effort": effort}}}),
                           encoding="utf-8")

    def profile_binding(self):
        """The production binding of this project: what a ready chat re-reads before every turn."""
        return lambda: chat_module.architect_binding(self.project)

    def test_c7_the_effective_architect_role_is_reread_before_every_turn(self):
        """A ready chat follows the current profile (docs/PROCESS_PROFILE.md:75): a role edited between turns reaches
        Codex with the new model and effort, never the one the chat was prepared with, and the header follows it."""
        with self.roles_root():
            self.write_role("first-model", "high")
            chat = self.chat(binding=self.profile_binding())
            self.assertTrue(chat.send("первый")[0])
            self.assertTrue(self.wait(lambda: not chat.busy, 6))
            self.assertIn("first-model/high", chat.state.header)
            self.write_role("second-model", "low")
            self.assertTrue(chat.send("второй")[0])
            self.assertTrue(self.wait(lambda: not chat.busy, 6))
        argv = self.fixture.calls()[1]["argv"]
        self.assertEqual(argv[argv.index("-m") + 1], "second-model")  # not the prepared first-model
        self.assertIn("model_reasoning_effort=low", argv)
        self.assertIn("second-model/low", chat.state.header)
        first = self.fixture.calls()[0]["argv"]  # the very first turn uses the profile too, not the prepared model
        self.assertEqual(first[first.index("-m") + 1], "first-model")

    def test_c7_a_profile_broken_between_turns_is_refused_before_any_process(self):
        """A profile that goes invalid after the chat was prepared (an empty architect model) ends the next turn as
        the catalog refusal of its family: no Codex process starts and the store is not written."""
        with self.roles_root():
            self.write_role("first-model", "high")
            chat = self.chat(binding=self.profile_binding())
            self.write_role("", "high")
            self.assertTrue(chat.send("вопрос")[0])  # Enter is accepted, the turn starts ...
            self.assertTrue(self.wait(lambda: not chat.busy, 6))
        self.assertEqual(self.fixture.calls(), [])  # ... but Codex was never invoked
        self.assertIn("process.invalid", chat.state.note)
        self.assertIn("Give a model ID", chat.state.note)
        store = self.fixture.store()
        self.assertFalse(store.transcript_path.exists())
        self.assertFalse(store.session_path.exists())

    def test_c9_the_header_provider_follows_the_codex_config_of_the_turn(self):
        """The header shows the provider the turn's own Codex process selects (docs/PROCESS_PROFILE.md:75): another
        `model_provider` in CODEX_HOME/config.toml reaches the next turn, so the chat re-reads it on the turn thread
        and hands the refreshed header to the UI instead of keeping the one of the preparation."""
        home = Path(self.fixture.env["CODEX_HOME"])
        home.mkdir(exist_ok=True)
        (home / "config.toml").write_text('model_provider = "openai"\n', encoding="utf-8")
        chat = self.chat()
        self.assertIn("provider openai", chat.state.header)  # the provider the chat was prepared with
        (home / "config.toml").write_text(
            'model_provider = "corp-proxy"\n'
            '[model_providers.corp-proxy]\nname = "proxy"\nbase_url = "https://corp.invalid/v1"\n',
            encoding="utf-8")
        self.assertTrue(chat.send("вопрос")[0])
        self.assertTrue(self.wait(lambda: not chat.busy, 6))
        self.assertIn("provider corp-proxy", chat.state.header)
        self.assertNotIn("provider openai", chat.state.header)

    # C-5 -----------------------------------------------------------------------

    def test_c5_a_cancel_landing_before_the_reservation_still_starts_no_process(self):
        """The window the reviewers stopped the chat thread on: the "is it cancelled?" check passed, the architect
        has not reserved the turn yet. The reservation now happens under the chat lock, so a cancel cannot slip in
        between; the turn ends cancelled and no Codex process is ever started."""
        store = self.fixture.store()
        chat = self.chat(store=store)
        reached, release = threading.Event(), threading.Event()
        begin = adapter.Architect.begin

        def gated(self):
            reached.set()          # inside the reservation, with the chat lock held
            release.wait(5)
            return begin(self)

        popen = adapter.subprocess.Popen
        with patch.object(adapter.Architect, "begin", gated), \
                patch.object(adapter.subprocess, "Popen", wraps=popen) as starts:
            self.assertTrue(chat.send("поздний ход")[0])
            self.assertTrue(reached.wait(5))
            canceller = threading.Thread(target=chat.cancel)  # blocks on the chat lock the reservation holds
            canceller.start()
            time.sleep(0.1)
            release.set()          # the reservation finishes; the lock falls and the cancel proceeds
            canceller.join(5)
            self.assertTrue(self.wait(lambda: not chat.busy, 8), chat.state)
            self.assertEqual(turn_starts(starts), [], "a cancel before the reservation was lost; a process started")
        self.assertEqual(self.fixture.calls(), [])  # Codex was never invoked
        self.assertIn("cancelled", chat.state.note)

    def test_c5_send_and_reset_are_refused_once_quit_began(self):
        """From the moment [ctrl+q] is pressed no new turn is accepted, so a stuck process cannot be started while
        the app is leaving."""
        chat = self.chat()
        chat.shutdown()
        accepted, line = chat.send("ещё")
        self.assertFalse(accepted)
        self.assertIn("architect.closing", line)
        accepted, line = chat.reset()
        self.assertFalse(accepted)
        self.assertIn("architect.closing", line)
        self.assertFalse(chat.busy)
        self.assertEqual(self.fixture.calls(), [])

    def test_c5_a_cancel_between_the_reservation_and_the_launch_starts_no_process(self):
        """The window `Architect.send` reserves the turn in but has not reached Popen yet (a slow session write): the
        cancel must win there too, so no Codex process is ever started."""
        store = self.fixture.store()
        chat = self.chat(store=store)
        reached, release = threading.Event(), threading.Event()
        original = store.save

        def save(session):
            reached.set()
            release.wait(5)
            return original(session)

        popen = adapter.subprocess.Popen
        with patch.object(store, "save", save), patch.object(adapter.subprocess, "Popen", wraps=popen) as starts:
            self.assertTrue(chat.send("поздний ход")[0])
            self.assertTrue(reached.wait(5))  # the turn is inside the session write, past the reservation
            self.assertTrue(chat.cancel())
            release.set()
            self.assertTrue(self.wait(lambda: not chat.busy, 8), chat.state)
            self.assertEqual(turn_starts(starts), [], "cancelled before Popen but a process was launched anyway")
        self.assertIn("cancelled", chat.state.note)
        self.assertEqual(self.fixture.calls(), [])  # Codex was never invoked

    def test_c5_a_cancel_racing_the_launch_never_returns_before_the_process_is_decided(self):
        """The window the reviewers stopped the turn in: the pre-launch cancel check has passed and Popen is about
        to run. The launch, the process and its publication are one critical section with `cancel`, so a cancel
        racing it wins either before the process exists (nothing is launched) or on the published one (killed); it
        never returns while a new process could still appear after it."""
        store = self.fixture.store()
        chat = self.chat(store=store)
        entered, release = threading.Event(), threading.Event()
        popen = adapter.subprocess.Popen

        def gated(*args, **kwargs):  # stops the turn inside its launch, before the process exists
            if args[0][1:3] == ["mcp", "list"]:  # the server check before the launch is not the launch
                return popen(*args, **kwargs)
            entered.set()
            release.wait(5)
            return popen(*args, **kwargs)

        with patch.object(adapter.subprocess, "Popen", gated):
            self.assertTrue(chat.send("гонка с запуском")[0])
            self.assertTrue(entered.wait(5))
            cancel = threading.Thread(target=chat.cancel)
            cancel.start()
            time.sleep(0.2)
            self.assertTrue(cancel.is_alive(), "the cancel returned while the launch was still undecided")
            release.set()
            cancel.join(5)
            self.assertFalse(cancel.is_alive())
            self.assertTrue(self.wait(lambda: not chat.busy, 8), chat.state)
        self.assertIn("cancelled", chat.state.note)

    def test_c5_a_store_read_that_fails_still_releases_busy(self):
        """A store read that raises during a turn must not leave the pane on "thinking…" with every send refused."""
        store = self.fixture.store()
        chat = self.chat(store=store)
        broken = OSError("transcript unavailable")
        self.assertTrue(chat.send("вопрос")[0])

        def failing(*_, **__):
            raise broken

        with patch.object(store, "transcript", failing):
            self.assertTrue(self.wait(lambda: not chat.busy, 8), chat.state)
        self.assertFalse(chat.busy)
        self.assertTrue(chat.state.note)  # the refusal took the place of the reload it could not do

    def test_c5_a_cut_between_the_popen_and_the_registration_still_kills_the_watcher(self):
        """The controller may close while a watcher is launching: a cut that lands after the Popen but before the
        registration still ends that observer (it registers into a cut epoch and kills itself), so no watching
        child survives the exit and a bounded join afterwards finds nothing alive."""
        binary = self.root / "zeroshot-watch"
        binary.write_text(WATCH % {"python": sys.executable})
        binary.chmod(0o755)
        entered, release = threading.Event(), threading.Event()
        real, seen = engine._register_watch, []

        def gated(process, epoch):  # hold native_run between its Popen and its registration
            seen.append(process.pid)
            entered.set()
            release.wait(5)
            return real(process, epoch)

        with patch.object(engine, "_register_watch", gated):
            thread = threading.Thread(target=lambda: engine.native_run(
                [str(binary), "watch", "run-1"], cwd=str(self.root), env=dict(os.environ), timeout=30,
                start_new_session=True))
            thread.start()
            self.assertTrue(entered.wait(5))
            engine.cut_watches()  # the controller closed while this watcher was still launching
            release.set()
            thread.join(10)
            self.assertFalse(thread.is_alive())
        self.assertTrue(seen)
        self.assertTrue(gone(seen[0]), "a watcher launched across the cut outlived the closing controller")
        self.assertRaises(ProcessLookupError, os.killpg, seen[0], 0)

    def test_f3_an_interrupt_inside_the_slice_ends_and_reaps_the_watcher_before_the_registry_forgets_it(self):
        """F-3 (regression, u3b-chat-fix3). A Ctrl+C that lands while a `zeroshot watch` slice is inside its
        `communicate` must end and reap that observer, exactly as a slice timeout does, before the registry
        forgets it, and the original exception must propagate unchanged. Before the fix the interrupt unwound
        straight through the `finally` that only drops the registration: the watcher (and the run it reads)
        stayed alive and the quit that followed had nothing left to cut. The interrupted watcher is a real child
        in its own session, so the guard is on the real kill and reap (`engine._reap_watch`), not on a stand-in.

        Interpretation (G-5): the interrupt is deliberately treated like any other exception here instead of
        being routed through the cut machinery (`cut_watches`/`WatchCut`) -- entering cut bookkeeping from a
        signal handler at an arbitrary point is injection territory; ending and reaping the child already in our
        hand is the whole requirement, and a later `close()` cuts whatever remains. Demonstrated in a scratch
        copy: without that branch the watcher's second `communicate` never ran and its child outlived the
        interrupt."""
        binary = self.root / "zeroshot-watch"
        binary.write_text(WATCH % {"python": sys.executable})
        binary.chmod(0o755)
        engine.open_watching()
        self.addCleanup(engine.cut_watches)
        real_popen = subprocess.Popen
        held = {}

        class Interrupted:
            """The watcher `native_run` holds when the interrupt lands: its first `communicate` is that Ctrl+C."""

            def __init__(self, child):
                self.child, self.pid, self.calls = child, child.pid, 0

            def communicate(self, timeout=None):
                self.calls += 1
                if self.calls == 1:
                    raise KeyboardInterrupt
                return self.child.communicate()

        def fake_popen(argv, **kwargs):
            held["watcher"] = Interrupted(real_popen(argv, **kwargs))
            return held["watcher"]

        with patch.object(engine.subprocess, "Popen", fake_popen):
            self.assertRaises(KeyboardInterrupt, engine.native_run, [str(binary), "watch", "run-1"],
                              cwd=str(self.root), env=dict(os.environ), timeout=30, start_new_session=True)
        watcher = held["watcher"]
        self.assertEqual(watcher.calls, 2, "the interrupted watcher was dropped without a reap")
        self.assertNotIn(watcher, engine._WATCHING, "the interrupted watcher stayed in the registry")
        self.assertTrue(gone(watcher.pid), "the watcher outlived the interrupt that cut it")

    def test_c5_a_watch_starting_after_the_cut_never_outlives_the_stop(self):
        """`stop` cuts the watching registry and then joins the slice in flight; a slice already inside its call --
        past the closing check, before it spawns -- must not register a fresh observer after that cut. Closing the
        controller closes watching too, so the late watcher is killed and no process survives the stop. The cut test
        above only covers the window between the Popen and the registration; this one covers the later start."""
        from terminal_planner.runs import FixtureDriver
        binary = self.root / "zeroshot-watch"
        binary.write_text(WATCH % {"python": sys.executable})
        binary.chmod(0o755)
        native = short_root()  # short root: the watch socket must fit macOS whatever TMPDIR is
        self.addCleanup(shutil.rmtree, native, ignore_errors=True)
        entered, release = threading.Event(), threading.Event()
        real_run, real_register, real_cut = engine.native_run, engine._register_watch, engine.cut_watches

        def gated(argv, **kwargs):  # hold the slice before its spawn, after the closing check it already passed
            entered.set()
            release.wait(5)
            return real_run(argv, **kwargs)

        watch = NativeEngine(str(binary), native, call=gated)
        controller = controller_module.Controller.for_project(
            self.project, self.state, fixture_id="test",
            driver_factory=lambda _: FixtureDriver(self.root / "fixture-runs"))
        controller.start()
        self.addCleanup(controller.stop)
        seen = []

        def recording(process, epoch):
            seen.append(process.pid)
            return real_register(process, epoch)

        def cutting(timeout=2.0):  # release the slice the moment the registry was cut: the reported window
            count = real_cut(timeout)
            release.set()
            return count

        self.addCleanup(lambda: engine.cut_watches())
        with patch.object(engine, "_register_watch", recording), patch.object(engine, "cut_watches", cutting):
            self.assertTrue(controller.post("observe", lambda app: watch.invoke(
                str(self.project), "watch", "run-1", slice=20)))
            self.assertTrue(entered.wait(5))
            controller.stop(timeout=0.5)  # closes watching, cuts the registry, joins the slice in flight
            end = time.monotonic() + 5
            while not seen and time.monotonic() < end:
                time.sleep(0.02)
        self.assertTrue(seen, "the late observe slice never reached its launch")
        self.assertTrue(gone(seen[0], 2.0), "a watcher started after the cut outlived the stop")
        self.assertRaises(ProcessLookupError, os.killpg, seen[0], 0)

    def test_c5_a_deliberate_cut_drops_the_truncated_tail_and_is_a_detach(self):
        """A quit cuts the observing `zeroshot watch` (`cut_watches`) mid-record, so its output ends with an
        incomplete line. That tail is a deliberate cut, not a broken answer: the complete records are kept and the
        slice ends as a detach (`SliceEnded`), never as `engine.bad_output` (which would record a false
        `observation_blocked`). This is the shape of a normal Ctrl+Q during an observe slice."""
        binary = self.root / "zeroshot-cut"
        binary.write_text(CUT_WATCH % {"python": sys.executable})
        binary.chmod(0o755)
        native = short_root()  # short root: the watch socket must fit macOS whatever TMPDIR is
        self.addCleanup(shutil.rmtree, native, ignore_errors=True)
        engine.open_watching()  # a controller's `start` opens watching; this raw slice must spawn like one
        instance = NativeEngine(str(binary), native)
        seen, ended = [], {}
        self.addCleanup(lambda: engine.cut_watches())

        def observer():  # a slice in flight, past its spawn, with its first record already written
            try:
                for record in instance.invoke(str(self.project), "watch", "run-1", slice=20):
                    seen.append(record)
                ended["error"] = None
            except Blocked as error:
                ended["error"] = error

        thread = threading.Thread(target=observer)
        thread.start()
        ready = self.root / "cut.ready"
        end = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < end:
            time.sleep(0.02)
        self.assertTrue(ready.exists(), "the watcher never wrote its first record")
        engine.cut_watches()  # the quit: the observer is cut while it is still writing a record
        thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(seen, [{"cursor": "c1", "phase": "running"}])  # the complete record survives the cut
        self.assertIsInstance(ended["error"], engine.SliceEnded)        # a cut ends the slice, not a bad answer

    def test_c5_cancel_right_after_send_starts_no_process_and_ends_cancelled(self):
        store = GatedStore(self.project)
        chat = self.chat(store=store)
        store.armed = True
        self.assertTrue(chat.send("поздний")[0])
        self.assertTrue(store.inside.wait(5))  # the turn is in its first store read
        self.assertTrue(chat.cancel())
        store.release.set()
        self.assertTrue(self.wait(lambda: not chat.busy, 6), chat.state)
        self.assertIn("not sent", chat.state.note)
        self.assertEqual(self.fixture.calls(), [])       # no Codex process was ever started
        self.assertFalse(store.transcript_path.exists())


def event(seq, state="awaiting_merge", previous="running", wake=True, milestone="M1", attempt=1, **extra):
    """One feed state event as A6b1 stores it (`feed.STATE_KEYS`), for the chat's injected port."""
    value = {"seq": seq, "kind": "state", "key": "1/%s/%d/-" % (milestone, attempt), "milestone": milestone,
             "plan_revision": 1, "attempt": attempt, "run_id": "r", "state": state, "previous": previous,
             "wake": wake, "at": "2026-01-01T00:00:00Z"}
    value.update(extra)
    return value


class Port:
    """The chat's injected feed port for a test: a scripted pending list, a snapshot and the recorded behaviour.

    `pending()`/`snapshot()` raise `pending_error`/`snapshot_error` when set; `handle` raises `handle_error`,
    otherwise it records the ack and drops everything up to `seq`. `hold`, when set, makes the next `pending()`
    read its list and then wait on the event before returning it — the window in which a wake event is written
    *during* a check."""

    def __init__(self, events=(), snapshot=None):
        self.events = list(events)
        self.snapshot_value = snapshot
        self.pending_error = None
        self.snapshot_error = None
        self.status_value = {"requests": [], "revision": 1, "rows": [{"id": "M1", "state": "awaiting_merge"}]}
        self.status_error = None
        self.handle_error = None
        self.handled = []
        self.reads = 0
        self.hold = None
        self._lock = threading.Lock()

    def pending(self):
        with self._lock:
            self.reads += 1
            if self.pending_error is not None:
                raise self.pending_error
            events, hold, self.hold = list(self.events), self.hold, None
        if hold is not None:
            hold.wait(10)
        return events

    def snapshot(self):
        if self.snapshot_error is not None:
            raise self.snapshot_error
        return self.snapshot_value

    def status(self):
        if self.status_error is not None:
            raise self.status_error
        return self.status_value

    def handle(self, seq):
        if self.handle_error is not None:
            raise self.handle_error
        with self._lock:
            self.handled.append(seq)
            self.events = [e for e in self.events if e["seq"] > seq]


class EventTurnTests(ChatUnitTests):
    """A6b2a C2-C4: the chat's event turns behind the injected feed port — catch-up on ready, the wake rule, the
    failure hold and the owner-first rule.

    Interpretations recorded for the reviewers (each the reading closest to the task's example):
    - The batch and the message are `feed.batch`/`feed.summary` (`tests/test_feed.py` pins them); the chat sends the
      whole summary as the event turn's message, and the adapter stores it as the `role "events"` row.
    - "A turn that did not complete" holds the checks for both an event turn and the owner's own turn; a completed
      owner turn (or a reset) releases them. The hold only gates event checks, never the owner's own turns.
    - A bare feed check (no turn running) is not cancellable: `cancel` returns False, matching "cancel the running
      turn only"."""

    def test_c2_c3_catch_up_on_ready_runs_one_event_turn_and_acks_its_batch(self):
        """C2/C3: with a port, becoming ready checks the feed; one batch holding a wake event runs one event turn,
        whose message is the summary and whose transcript row is the events author's; on completion it acks the
        batch's last seq."""
        port = Port([event(1, state="awaiting_merge", previous="running")], {"project": "p"})
        chat = self.chat(feed=port)
        self.assertTrue(self.wait(lambda: port.handled == [1] and not chat.busy, 10), (chat.state, port.handled))
        self.assertEqual(port.handled, [1])
        stdin = self.fixture.calls()[0]["stdin"]
        self.assertIn("Events since the last turn:", stdin)
        self.assertIn("M1 attempt 1: running -> awaiting_merge", stdin)
        rows = self.fixture.store().transcript()
        self.assertEqual([row["role"] for row in rows], ["events", "architect"])
        self.assertTrue(rows[0]["text"].startswith("Events since the last turn:"))
        entries = chat.state.entries
        self.assertEqual([entry.role for entry in entries], ["events", "architect"])
        self.assertEqual(entries[0].role, "events")  # its own role, never the owner's line

    def test_c1a_an_event_turn_carries_the_status_and_one_that_cannot_be_read_still_goes_out(self):
        """C1a C1/C2/C5: the event turn's stdin holds the port's status after the events (M1's row with its state);
        a status that raises or is `stale` is one line saying so and the turn still goes out and acknowledges; an
        owner turn carries no status block.
        Interpretation: a `stale` payload is treated as unavailable (its rows may name a state that has moved on)."""
        port = Port([event(1, state="awaiting_merge", previous="running")], {})
        chat = self.chat(feed=port)
        self.assertTrue(self.wait(lambda: port.handled == [1] and not chat.busy, 10), chat.state)
        stdin = self.fixture.calls()[0]["stdin"]
        self.assertIn('"id":"M1","state":"awaiting_merge"', stdin)
        self.assertLess(stdin.index("M1 attempt 1"), stdin.index("Status:"))
        shown = chat.state.entries[0].text  # the pane shows the events, not the status JSON the architect reads
        self.assertIn("M1 attempt 1", shown)
        self.assertNotIn("Status:", shown)
        self.assertNotIn("Assess them", shown)  # U1b C2: nor the closing instruction; the architect still got both
        self.assertIn("Assess them", stdin)
        self.assertEqual(shown.splitlines()[0], "Events since the last turn:")
        for broken in (OSError("нет связи"), None):
            port.status_error, port.status_value = broken, {"rows": [{"id": "M1"}], "stale": True}
            port.events = [event(len(port.handled) + 1)]
            self.fixture.script([{"lines": REPLY}])
            chat.notify()
            count = len(self.fixture.calls())
            self.assertTrue(self.wait(lambda: len(self.fixture.calls()) > count and not chat.busy, 10), chat.state)
            stdin = self.fixture.calls()[-1]["stdin"]
            self.assertIn("status unavailable: call zplan_status", stdin)
            self.assertNotIn("Status:", stdin)
        self.assertEqual(port.handled, [1, 2, 3])
        self.fixture.script([{"lines": REPLY}])
        self.assertTrue(chat.send("привет")[0])
        self.assertTrue(self.wait(lambda: not chat.busy, 8), chat.state)
        owner = self.fixture.calls()[-1]["stdin"]
        self.assertNotIn("Status:", owner)
        self.assertNotIn("status unavailable", owner)

    def test_c2_the_events_role_is_wired_into_the_row_vocabulary(self):
        """C2: `ROLES` gains "events", and an events row is its own entry — never the owner's line."""
        self.assertIn("events", chat_module.ROLES)
        entry = chat_module.entries_of([{"role": "events", "text": "ход"}])[0]
        self.assertEqual(entry.role, "events")
        self.assertNotEqual(entry.role, chat_module.entries_of([{"role": "owner", "text": "ход"}])[0].role)

    def test_c3_a_batch_without_a_wake_event_starts_no_turn_and_no_ack(self):
        """C3: a check whose batch holds no wake event starts no turn and acknowledges nothing; nothing is written
        and no Codex process runs."""
        port = Port([event(1, state="running", previous="preparing", wake=False)], {})
        chat = self.chat(feed=port)
        self.assertTrue(self.wait(lambda: port.reads >= 1, 6), port.reads)
        time.sleep(0.3)
        self.assertFalse(chat.busy, chat.state)
        self.assertEqual(port.handled, [])
        self.assertEqual(self.fixture.calls(), [])
        self.assertEqual(chat.state.entries, ())

    def test_c3_a_failed_event_turn_holds_the_checks_until_an_owner_turn_completes(self):
        """C3: an event turn that did not complete is a note and acknowledges nothing; the checks are held, so a
        later `notify` starts nothing until the owner's next completed turn releases them."""
        port = Port([event(1)], {})
        self.fixture.script([{"lines": OPENING, "exit": 2}, {"lines": REPLY}])
        chat = self.chat(feed=port)
        self.assertTrue(self.wait(lambda: not chat.busy, 8), chat.state)
        self.assertEqual(port.handled, [])
        self.assertTrue(chat.state.note)
        port.events = []  # A6b3 owns the retry/backoff for the still-pending event
        chat.notify()
        time.sleep(0.3)
        self.assertEqual(port.reads, 1)  # held: the notify started no check
        self.assertTrue(chat.send("привет")[0])
        self.assertTrue(self.wait(lambda: not chat.busy, 8), chat.state)
        self.assertTrue(self.wait(lambda: port.reads >= 2, 6), port.reads)

    def test_c3_a_failed_ack_holds_the_checks_until_an_owner_turn_completes(self):
        """C3: an ack (`handle`) that raises is a note, acknowledges nothing further, and holds the checks until an
        owner turn completes."""
        port = Port([event(1)], {})
        port.handle_error = OSError("нет связи")
        self.fixture.script([{"lines": REPLY}, {"lines": REPLY}])
        chat = self.chat(feed=port)
        self.assertTrue(self.wait(lambda: not chat.busy, 8), chat.state)
        self.assertEqual(port.handled, [])
        self.assertTrue(chat.state.note)
        port.events = []
        port.handle_error = None
        chat.notify()
        time.sleep(0.3)
        self.assertEqual(port.reads, 1)
        self.assertTrue(chat.send("привет")[0])
        self.assertTrue(self.wait(lambda: not chat.busy, 8), chat.state)
        self.assertTrue(self.wait(lambda: port.reads >= 2, 6), port.reads)

    def test_c3_a_port_error_holds_the_checks_until_an_owner_turn_completes(self):
        """C3: `pending` raising is a note and starts no turn; a later `notify` starts no check until an owner turn
        completes."""
        port = Port([event(1)], {})
        port.pending_error = OSError("нет связи")
        self.fixture.script([{"lines": REPLY}, {"lines": REPLY}])
        chat = self.chat(feed=port)
        self.assertTrue(self.wait(lambda: port.reads >= 1 and not chat.busy, 6), chat.state)
        self.assertTrue(chat.state.note)
        port.pending_error = None
        port.events = []
        chat.notify()
        time.sleep(0.3)
        self.assertEqual(port.reads, 1)
        self.assertTrue(chat.send("привет")[0])
        self.assertTrue(self.wait(lambda: not chat.busy, 8), chat.state)
        self.assertTrue(self.wait(lambda: port.reads >= 2, 6), port.reads)

    def test_c3_a_snapshot_error_is_a_note_and_starts_no_turn(self):
        """C3: `snapshot` raising is a note and no turn; nothing is acknowledged and no Codex process runs."""
        port = Port([event(1)], {})
        port.snapshot_error = OSError("нет связи")
        chat = self.chat(feed=port)
        self.assertTrue(self.wait(lambda: not chat.busy, 6), chat.state)
        self.assertEqual(port.handled, [])
        self.assertEqual(self.fixture.calls(), [])
        self.assertTrue(chat.state.note)

    def test_c3_a_reset_releases_the_held_checks(self):
        """C3: a reset releases the held checks — after it, a check runs again."""
        port = Port([event(1)], {})
        port.pending_error = OSError("нет связи")
        self.fixture.script([{"lines": REPLY}])
        chat = self.chat(feed=port)
        self.assertTrue(self.wait(lambda: port.reads >= 1 and not chat.busy, 6), chat.state)
        port.pending_error = None
        port.events = []
        chat.notify()
        time.sleep(0.3)
        self.assertEqual(port.reads, 1)  # held
        self.assertTrue(chat.reset()[0])
        self.assertTrue(self.wait(lambda: not chat.busy, 6), chat.state)
        self.assertTrue(self.wait(lambda: port.reads >= 2, 6), port.reads)

    def test_c3_a_notify_during_a_check_that_found_nothing_runs_a_second_check(self):
        """C3: a wake event written while a check reads an empty list is not missed — the notify is remembered and
        one more check runs right after, finding it."""
        port = Port([], {})
        hold = threading.Event()
        port.hold = hold
        chat = self.chat(feed=port)
        self.assertTrue(self.wait(lambda: port.reads >= 1, 6), port.reads)  # the first check read [] and waits
        port.events = [event(2, state="integrated", previous="awaiting_merge")]  # written during the check
        chat.notify()
        hold.set()
        self.assertTrue(self.wait(lambda: port.handled == [2], 10), (chat.state, port.handled))
        self.assertGreaterEqual(port.reads, 2)  # the second check found the wake event the first one missed

    def test_u1b_c1_a_bare_check_is_busy_but_not_a_turn_and_the_event_turn_it_starts_is(self):
        """U1b C1: `turn_running` (what the bar's «архитектор отвечает» reads) is False while a check waits in
        `pending()` with `busy` True, True once the check promoted its batch into an event turn, False after.
        Interpretation: a reset's turns count as turns (`/new` runs a real handoff turn)."""
        release = str(self.root / "release-event")
        port = Port([event(1)], {})
        hold = threading.Event()
        port.hold = hold
        self.fixture.script([{"lines": REPLY, "release": release}])
        chat = self.chat(feed=port)
        self.assertTrue(self.wait(lambda: port.reads >= 1, 6), port.reads)  # the check waits in `pending()`
        self.assertTrue(chat.busy)
        self.assertFalse(chat.turn_running)
        hold.set()
        self.assertTrue(self.wait(lambda: self.fixture.calls() and chat.turn_running, 8), chat.state)
        self.assertTrue(chat.busy)
        open(release, "w").close()
        self.assertTrue(self.wait(lambda: not chat.busy, 10), chat.state)
        self.assertFalse(chat.turn_running)

    def test_u1b_c1_a_queued_owner_turn_has_its_own_start_after_the_event_turn(self):
        """U1b C1: the owner message queued behind an event turn begins in the same UI step that ends the event
        turn, so `turn_running` is never seen False between them; `turn_started` still moves to the owner turn's own
        start (the bar's clock counts from it)."""
        first, second = str(self.root / "release-event"), str(self.root / "release-owner")
        port = Port([event(1)], {})
        self.fixture.script([{"lines": REPLY, "release": first}, {"lines": REPLY, "release": second}])
        chat = self.chat(feed=port)
        self.assertTrue(self.wait(lambda: chat.turn_running and self.fixture.calls(), 8), chat.state)
        started = chat.turn_started
        self.assertEqual(chat.send("стоп"), (True, ""))
        time.sleep(0.05)
        open(first, "w").close()
        self.assertTrue(self.wait(lambda: port.handled == [1] and len(self.fixture.calls()) == 2, 10), chat.state)
        self.assertTrue(chat.turn_running)
        self.assertGreater(chat.turn_started, started)
        open(second, "w").close()
        self.assertTrue(self.wait(lambda: not chat.busy, 10), chat.state)

    def test_c4_while_an_event_turn_runs_the_owner_message_waits_and_runs_next(self):
        """C4: while an event turn runs the owner's message is accepted at once (with the waiting note); a second
        one is refused as busy; when the event turn ends the waiting message runs before any further check."""
        release = str(self.root / "release-event")
        port = Port([event(1)], {})
        self.fixture.script([{"lines": REPLY, "release": release}, {"lines": REPLY}])
        chat = self.chat(feed=port)
        self.assertTrue(self.wait(lambda: chat.busy and self.fixture.calls(), 8), chat.state)
        self.assertEqual(chat.send("стоп"), (True, ""))
        self.assertEqual(chat.state.note, chat_module.WAITING)
        accepted, line = chat.send("ещё")
        self.assertFalse(accepted)
        self.assertIn("architect.busy", line)
        self.assertEqual(port.handled, [])  # the event turn has not finished yet
        open(release, "w").close()
        self.assertTrue(self.wait(lambda: not chat.busy, 10), chat.state)
        self.assertEqual(port.handled, [1])  # the event turn acked before the owner's turn ran
        self.assertEqual([row["role"] for row in self.fixture.store().transcript()][-2:], ["owner", "architect"])
        self.assertTrue(self.fixture.calls()[1]["stdin"].endswith("стоп"))

    def test_c4_cancel_ends_the_event_turn_and_the_waiting_message_still_runs(self):
        """C4: esc cancels the running event turn only; the owner message waiting behind it still runs after."""
        release = str(self.root / "release-event")
        port = Port([event(1)], {})
        self.fixture.script([{"lines": OPENING, "release": release}, {"lines": REPLY}])
        chat = self.chat(feed=port)
        self.assertTrue(self.wait(lambda: chat.busy and self.fixture.calls(), 8), chat.state)
        self.assertEqual(chat.send("стоп"), (True, ""))
        self.assertTrue(chat.cancel())
        port.events = []  # the cancelled event stays pending; A6b3 owns backoff, this checks the owner-first rule
        self.assertTrue(self.wait(lambda: not chat.busy, 10), chat.state)
        self.assertEqual(port.handled, [])
        self.assertEqual([row["role"] for row in self.fixture.store().transcript()][-2:], ["owner", "architect"])

    def test_c4_a_message_sent_during_a_blocked_check_runs_before_the_event_turn(self):
        """C4 (regression): an owner message sent while a check is blocked in `pending()` (before the check can
        promote its batch into an event turn) is accepted at once and runs as the very next turn, before the event
        turn; nothing is acknowledged then, so the events reach the architect on the check the owner's turn asks
        for. The transcript order is owner, architect, events, architect — never events first."""
        hold = threading.Event()
        port = Port([event(1)], {})
        port.hold = hold
        self.fixture.script([{"lines": REPLY}, {"lines": REPLY}])
        chat = self.chat(feed=port)
        self.assertTrue(self.wait(lambda: port.reads >= 1 and chat.busy, 6), (chat.state, port.reads))
        self.assertFalse(self.fixture.calls())  # the check has run no turn yet: it waits in `pending()`
        self.assertEqual(chat.send("стоп"), (True, ""))
        self.assertEqual(chat.state.note, chat_module.WAITING)
        hold.set()
        self.assertTrue(self.wait(lambda: not chat.busy and port.handled == [1], 10), (chat.state, port.handled))
        self.assertEqual([row["role"] for row in self.fixture.store().transcript()],
                         ["owner", "architect", "events", "architect"])
        self.assertTrue(self.fixture.calls()[0]["stdin"].endswith("стоп"))  # the owner ran first

    def test_c3_a_check_in_flight_when_quit_began_starts_no_event_turn(self):
        """C3/C-5 (regression): a bare feed check blocked in `pending()` when quit begins must not promote its batch
        into an event turn after `close()` returned. Shutdown is honoured under the same lock as the promotion, so
        the check releases the activity without launching — `cancel()` cannot reach a bare check (it has no turn) —
        and no Codex process starts once the chat is closing."""
        hold = threading.Event()
        port = Port([event(1)], {})
        port.hold = hold
        chat = self.chat(feed=port)
        self.assertTrue(self.wait(lambda: port.reads >= 1 and chat.busy, 6), (chat.state, port.reads))
        self.assertFalse(self.fixture.calls())  # the check waits in `pending()`, no turn yet
        chat.shutdown()
        self.assertFalse(chat.cancel())         # a bare check has no turn to cancel
        chat.close(timeout=0.01)                # the bounded wait gives up while the check still waits
        hold.set()
        self.assertTrue(self.wait(lambda: not chat.busy, 6), chat.state)
        self.assertEqual(port.handled, [])      # nothing acknowledged
        self.assertEqual(self.fixture.calls(), [])  # no Codex process was ever started after shutdown

    def test_c2_c3_without_a_port_no_check_runs_and_no_text_changes(self):
        """C3: without a port `notify` starts nothing and the chat stays exactly owner-only — no events row, no
        check, no extra Codex process."""
        chat = self.chat()
        chat.notify()
        self.assertTrue(chat.send("привет")[0])
        self.assertTrue(self.wait(lambda: not chat.busy, 8), chat.state)
        self.assertEqual([row["role"] for row in self.fixture.store().transcript()], ["owner", "architect"])
        self.assertEqual(len(self.fixture.calls()), 1)


class TempdirTests(unittest.TestCase):
    """The long-path checks of this task only mean something when the interpreter really uses the given TMPDIR:
    `tempfile` silently falls back to another directory (an unset or unusable TMPDIR) and the long path would then
    never be exercised, so the qualification of the task fails instead of passing on a path nobody chose."""

    def test_the_environment_tmpdir_is_the_one_in_use(self):
        tmpdir = os.environ.get("TMPDIR")
        if not tmpdir:
            self.skipTest("TMPDIR is not set on this host: nothing to pin")
        self.assertEqual(Path(tempfile.gettempdir()).resolve(), Path(tmpdir).resolve())


if HAVE_TEXTUAL:
    from rich.cells import cell_len
    from textual.widgets import Static

    from terminal_planner.tui import app as app_module
    from terminal_planner.tui.chat_input import ChatInput
    from test_layout import text_oracle


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class ChatShell(MilestoneShell):
    """The shell with the scripted codex behind the architect chat; the plan and milestone machinery is the
    same fixture shell the other TUI tests use."""

    def setUp(self):
        super().setUp()
        self.fixture = Fixture(self.root, self.project)

    def shell(self, controller=None, size=(120, 40), follow=False, chat_prepare=None, store=None, delay=0.0):
        return super().shell(controller, size, follow,
                             chat_prepare if chat_prepare is not None
                             else self.fixture.prepare(store=store, delay=delay),
                             chat_binding=self.fixture.binding())

    async def say(self, pilot, text):
        """Put `text` in the chat input and press Enter (letters in the input are text, never panel keys)."""
        field = self.query("#input")
        field.focus()
        field.value = text
        await pilot.press("enter")

    def query(self, selector):
        return self.app.query_one(selector, ChatInput)

    async def chat_done(self, pilot, timeout=10.0):
        await self.until(pilot, lambda: self.app.chat is not None and not self.app.chat.busy, timeout)

    async def pids(self, pilot, path):
        await self.until(pilot, path.exists, 10.0)
        await pilot.pause()
        return [int(value) for value in path.read_text().split()]

    @property
    def native(self):
        """A short native state root (see `short_root`): the controller socket path must stay under 104 bytes
        on macOS, and `self.root / "native"` is longer than a sibling of `self.root` made by `short_root`."""
        if not hasattr(self, "_native"):
            self._native = short_root()
            self.addCleanup(shutil.rmtree, self._native, ignore_errors=True)
        return self._native


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class ChatJourneyTests(ChatShell):
    # C-1
    async def test_c1_send_shows_the_final_reply_and_a_restarted_app_rebuilds_the_history(self):
        async with self.shell() as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            await self.say(pilot, "что дальше")
            self.assertIn("что дальше", chat_band(self.app))
            await self.chat_done(pilot)
            await self.until(pilot, lambda: "Привет." in chat_band(self.app))
            self.assertIn("Привет.", chat_band(self.app))
        rows = [(row["role"], row.get("text")) for row in self.fixture.store().transcript()]
        self.assertIn(("owner", "что дальше"), rows)
        self.assertIn(("architect", "Привет."), rows)
        async with self.shell() as pilot:  # an app restart shows the same history
            await self.loaded(pilot)
            await self.until(pilot, lambda: self.app.chat.state.phase == "ready" and self.app.chat.state.entries)
            text = chat_band(self.app)
            self.assertIn("что дальше", text)
            self.assertIn("Привет.", text)

    async def test_c1_the_prompt_carries_the_goal_from_the_immutable_snapshot(self):
        """The turn's preamble is built from the UI's frozen snapshot: the goal is the overview's first line
        ("Goal: ..."), so the architect is told what the project is about (not the plan status line)."""
        self.approve(running=False)  # an approved plan: the overview's first line is its goal
        async with self.shell() as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            self.assertIn("Goal: Requested feature", self.app.chat_snapshot()["plan_summary"])
            await self.say(pilot, "что дальше")
            await self.chat_done(pilot)
        prompt = self.fixture.calls()[0]["stdin"]
        self.assertIn("Plan summary: Goal: Requested feature", prompt)

    async def test_c1_the_live_line_shows_the_streamed_text_while_the_turn_runs(self):
        self.fixture.script([{"lines": OPENING + [{"type": "item.completed",
                                                   "item": {"id": "i1", "type": "agent_message",
                                                            "text": "Печатаю ответ"}}], "hang": 4}])
        async with self.shell() as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            await self.say(pilot, "вопрос")
            await self.until(pilot, lambda: "Печатаю ответ" in screen_text(self.app), 10.0)
            text = screen_text(self.app)
            self.assertIn("thinking…", text)  # the live line carries the streamed text
            self.assertIn("0:0", text)      # ... and the elapsed time on the same line

    async def test_c1_the_idle_seconds_never_repaint_the_screen_once_it_unloads(self):
        """The 0.2s idle timer advances the live "thinking…" seconds while a turn runs. Leaving the app unloads
        the screen's widgets, and that unmount awaits, so a tick lands inside it; the tick then painted a
        screen whose widgets were already gone (`NoMatches`) and took the whole app — with the running turn —
        down at exit. The turn is still running when this context leaves, and the timer really ticked inside
        the unloading window (`ticks` would stay empty if it did not)."""
        self.fixture.script([{"lines": OPENING + [{"type": "item.completed",
                                                   "item": {"id": "i1", "type": "agent_message",
                                                            "text": "Печатаю ответ"}}], "hang": 30}])
        state = {"unloading": False, "ticks": 0}
        waiting = app_module.ZplanApp.quit_when_idle

        def counted(app):
            if state["unloading"]:
                state["ticks"] += 1
            waiting(app)

        async def slow_unmount(self_, event):
            # Let the idle timer tick inside the unmount window instead of guessing at its phase.
            state["unloading"] = True
            end = time.monotonic() + 5.0
            while state["ticks"] < 2 and time.monotonic() < end:
                await asyncio.sleep(0.02)
            state["unloading"] = False

        with patch.object(app_module.MainScreen, "on_unmount", slow_unmount, create=True), \
                patch.object(app_module.ZplanApp, "quit_when_idle", counted):
            async with self.shell() as pilot:
                await self.loaded(pilot)
                await self.chat_ready(pilot)
                await self.say(pilot, "вопрос")
                await self.until(pilot, lambda: "Печатаю ответ" in screen_text(self.app), 10.0)
                self.assertTrue(self.app.chat.busy)  # the app leaves with the turn still running
        self.assertGreaterEqual(state["ticks"], 2, "the idle timer never ticked inside the unmount")

    # C-2
    async def test_c2_a_turn_runs_on_its_own_thread_and_the_observe_loop_keeps_advancing(self):
        self.approve(running=True)
        self.driver.gate.clear()  # hold the first observe slice: the controller worker parks inside it
        self.fixture.script([{"lines": PARTIAL, "hang": 6}])
        async with self.shell(size=(120, 40), follow=True) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            await self.until(pilot, lambda: self.driver.live, 10.0)
            await self.say(pilot, "долгий вопрос")
            self.assertTrue(self.app.chat.busy)
            turn = self.app.chat.turn_thread
            self.assertIsNotNone(turn)
            self.assertEqual(turn.name, "zplan-chat-turn")
            self.assertIsNot(turn, self.app.controller._thread)  # never the controller worker
            self.assertTrue(self.driver.live)  # the worker is still inside the held slice, not the turn
            slices = self.driver.slices
            self.driver.gate.set()  # release: the observe loop must keep advancing while the turn runs
            await self.until(pilot, lambda: self.driver.slices > slices, timeout=8.0)
            self.assertTrue(self.app.chat.busy)  # slices advanced while the turn still runs
            await self.chat_done(pilot, 20)

    # C-3
    async def test_c3_cancel_kills_the_group_marks_the_partial_and_leaves_the_milestone_alone(self):
        self.approve(running=True)
        child_file = self.root / "cancel.pids"
        self.fixture.script([{"lines": PARTIAL, "child": str(child_file), "hang": 30}, {"lines": REPLY}],
                            ignore_term=True)
        async with self.shell() as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            await self.say(pilot, "долгий вопрос")
            parent, child = await self.pids(pilot, child_file)
            self.assertIn("thinking…", screen_text(self.app))
            await pilot.press("escape")  # the cancel key works while the input has focus
            await self.chat_done(pilot)
            self.assertTrue(gone(parent), "the architect process outlived the cancel")
            self.assertTrue(gone(child), "a child of the architect's group outlived the cancel")
            await self.until(pilot, lambda: "(interrupted)" in screen_text(self.app), 5.0)
            text = screen_text(self.app)
            self.assertIn("(interrupted)", text)
            self.assertIn("Начало ответа", text)
            self.assertEqual(self.driver.stopped, [])  # never a milestone stop
            self.assertTrue(any(row.state == "running" for row in self.app.snapshot.rows))
            await self.say(pilot, "ещё")  # the next send works
            await self.chat_done(pilot)
            self.assertIn("Привет.", chat_band(self.app))

    # C-4
    async def test_c4_a_second_send_and_a_reset_wait_for_the_running_turn(self):
        self.fixture.script([{"lines": PARTIAL, "hang": 3.0}, {"lines": REPLY}])
        async with self.shell() as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            await self.say(pilot, "первый")
            await self.until(pilot, lambda: self.app.chat.busy)
            await self.say(pilot, "второй")
            self.assertIn("The architect is already answering", screen_text(self.app))
            self.assertEqual(self.query("#input").value, "второй")  # nothing queued, text kept
            await self.until(pilot, lambda: len(self.fixture.calls()) == 1, 5.0)  # the first turn reached Codex
            await self.command(pilot, "/new")
            await pilot.pause()
            self.assertIn("The architect is answering: the new conversation", screen_text(self.app))
            self.assertNotIn("reset", [row["role"] for row in self.fixture.store().transcript()])
            await self.chat_done(pilot)
            await self.command(pilot, "/new")
            await self.chat_done(pilot)
            # A8b: Ctrl+R now hands off before the reset and warms up after it, so the reset row is not the last one
            self.assertIn("reset", [row["role"] for row in self.fixture.store().transcript()])
            self.assertIn("New conversation", screen_text(self.app))   # the reset entry's own text, no author

    # C-5
    async def test_c5_ctrl_q_cancels_the_turn_and_exits_within_the_deadline(self):
        """The cancelled turn's group is gone by the time the app goes to exit: the check runs at the exit
        itself, not after a tolerant `gone()` poll, so a wait that stopped doing its job (the group still alive
        when the app leaves) fails the test instead of being masked by the poll."""
        child_file = self.root / "quit.pids"
        self.fixture.script([{"lines": PARTIAL, "child": str(child_file), "hang": 30}], ignore_term=True)
        at_exit = []
        async with self.shell() as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            await self.say(pilot, "долгий вопрос")
            parent, child = await self.pids(pilot, child_file)
            real_exit = self.app.exit

            def exit_after_checks(code=0):  # the last step of the quit: nothing of the turn may be alive yet
                at_exit.append(alive(parent))
                real_exit(code)

            started = time.monotonic()
            with patch.object(self.app, "exit", exit_after_checks):
                await pilot.press("ctrl+q")
        self.assertLess(time.monotonic() - started, 5.0)
        self.assertEqual(at_exit[:1], [False],
                         "the cancelled group was still alive when the app went to exit")
        self.assertRaises(ProcessLookupError, os.killpg, parent, 0)  # the whole group is gone
        self.assertTrue(gone(child))

    async def test_c5_ctrl_q_with_a_mutating_job_cancels_the_turn_at_once(self):
        child_file = self.root / "job.pids"
        self.fixture.script([{"lines": PARTIAL, "child": str(child_file), "hang": 30}], ignore_term=True)
        controller = self.controller()
        release, started = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def job(app):
            started.set()
            release.wait(15)
        async with self.shell(controller) as pilot:
            await self.loaded(pilot)
            self.assertTrue(controller.post("test", job, mutating=True))
            await self.until(pilot, started.is_set)
            await self.chat_ready(pilot)
            await self.say(pilot, "долгий вопрос")
            parent, _ = await self.pids(pilot, child_file)
            await pilot.press("ctrl+q")
            await pilot.pause(0.2)
            self.assertTrue(self.app.quitting)  # the job's quit behaviour is unchanged
            self.assertEqual(self.app.screen.__class__.__name__, "FinishingScreen")
            self.assertTrue(gone(parent), "the turn was not cancelled at once")
            self.assertTrue(controller.mutating())  # the job is still running
            release.set()
        self.assertTrue(gone(parent))

    async def test_c5_ctrl_q_shares_one_budget_with_a_stuck_nonmutating_job(self):
        """The cancelled turn and a controller job quitting may cut share one deadline: the exit stays inside
        the 5 s the UI promises even when that job never returns on its own."""
        controller = self.controller()
        release, started = threading.Event(), threading.Event()
        child_file = self.root / "budget.pids"
        self.fixture.script([{"lines": PARTIAL, "child": str(child_file), "hang": 30}], ignore_term=True)

        def read(app):
            started.set()
            release.wait(15)

        try:
            async with self.shell(controller) as pilot:
                await self.loaded(pilot)
                await self.chat_ready(pilot)
                self.assertTrue(controller.post("check", read))
                await self.until(pilot, started.is_set)
                self.assertFalse(controller.mutating())  # a plain read: quitting may cut it
                await self.say(pilot, "долгий вопрос")
                parent, child = await self.pids(pilot, child_file)
                when = time.monotonic()
                await pilot.press("ctrl+q")
        finally:
            release.set()
        self.assertLess(time.monotonic() - when, 5.0)
        self.assertTrue(gone(parent), "the architect's group outlived the quit")
        self.assertTrue(gone(child))
        self.assertRaises(ProcessLookupError, os.killpg, parent, 0)

    async def test_c5_a_quit_cuts_the_watching_child_and_leaves_no_orphan(self):
        """A slice that only watches runs `zeroshot watch` in its own session, for longer than any exit budget:
        quitting cuts and reaps that observer at once instead of leaving it behind. The run it watched is
        untouched -- the only native call the app ever made is the watch itself."""
        binary = self.root / "zeroshot-watch"
        binary.write_text(WATCH % {"python": sys.executable})
        binary.chmod(0o755)
        watch = NativeEngine(str(binary), self.native)  # short root: the watch socket must fit macOS
        controller = self.controller()
        async with self.shell(controller) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            self.assertTrue(controller.post("observe", lambda app: watch.invoke(
                str(self.project), "watch", "run-1", slice=controller_module.TUI_SLICE * 6)))
            parent, child = await self.pids(pilot, self.root / "watch.pids")
            when = time.monotonic()
            await pilot.press("ctrl+q")
        self.assertLess(time.monotonic() - when, 5.0)
        self.assertFalse(alive(parent), "the watching child outlived the exit instead of being cut with it")
        self.assertTrue(gone(child))
        self.assertRaises(ProcessLookupError, os.killpg, parent, 0)
        self.assertEqual((self.root / "watch.calls").read_text().split(), ["watch", "run-1"])

    async def test_c5_no_new_turn_starts_after_the_quit_key(self):
        """From the start of quit no send is accepted: with a mutating job holding the app open, a message
        submitted after [ctrl+q] starts nothing (its process could otherwise outlive the exit)."""
        controller = self.controller()
        release, started = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def job(app):
            started.set()
            release.wait(15)

        async with self.shell(controller) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            self.assertTrue(controller.post("test", job, mutating=True))
            await self.until(pilot, started.is_set)
            await pilot.press("ctrl+q")
            await pilot.pause(0.2)
            self.assertTrue(self.app.quitting)              # the mutating job keeps its quit behaviour
            accepted, line = self.app.send_chat("позднее сообщение")
            self.assertFalse(accepted)
            self.assertIn("architect.closing", line)
            self.assertFalse(self.app.chat.busy)
            self.assertEqual(self.fixture.calls(), [])      # nothing was started
            release.set()

    async def test_c5_a_late_mutation_during_the_chat_cancel_is_refused(self):
        """Once [ctrl+q] began, no submission or export may be admitted while the app waits for the cancelled
        chat: the closing is decided before that first await, so a late mutating post is refused instead of
        holding the promised exit open without bound."""
        controller = self.controller()
        self.fixture.script([{"lines": PARTIAL, "hang": 30}], ignore_term=True)
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        async with self.shell(controller) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            await self.say(pilot, "долгий вопрос")
            real_wait = chat_module.ArchitectChat.wait

            def gated_wait(self_, timeout=None):  # park the quit inside its wait for the cancelled turn
                entered.set()
                release.wait(10)
                return real_wait(self_, timeout)

            with patch.object(chat_module.ArchitectChat, "wait", gated_wait):
                quit_task = asyncio.ensure_future(self.app.action_quit())
                await self.until(pilot, entered.is_set, 5.0)
                self.assertFalse(controller.post("поздний экспорт", lambda app: None, mutating=True),
                                 "a mutation was admitted behind the exit")
                release.set()
                await quit_task
        self.assertFalse(controller.running)

    # C-6b
    async def test_c6b_a_slow_preparation_never_blocks_a_key_and_shows_the_model_and_usage_in_the_bar(self):
        async with self.shell(chat_prepare=self.fixture.prepare(delay=1.5)) as pilot:
            await self.loaded(pilot)
            self.assertEqual(self.app.chat.state.phase, "preparing")
            self.assertIn(chat_module.PREPARING, screen_text(self.app))
            await self.command(pilot, "/setup")  # a command is handled while the chat is still preparing
            self.assertEqual(self.app.screen.__class__.__name__, "SettingsScreen")
            await pilot.press("escape")
            await self.until(pilot, lambda: self.app.chat.ready)
            self.assertIn("gpt-6.1-sol/high", screen_text(self.app))  # the bar's tail: model/effort (C2)
            await self.say(pilot, "вопрос")
            await self.chat_done(pilot)
            await pilot.pause()
            self.assertIn("gpt-6.1-sol/high · 15 tok", screen_text(self.app))

    async def test_c6b_the_bar_keeps_the_model_and_the_usage_over_a_long_history_and_a_new_turn(self):
        """The bar's tail (`model/effort · N tok`) is not tied to the conversation: it stays and carries the
        counters of the turn just ended although the stored transcript is longer than the pane."""
        store = self.fixture.store()
        for index in range(30):
            store.append("owner" if index % 2 == 0 else "architect", text="прежнее сообщение %d" % index)
        async with self.shell(size=(140, 40), store=store) as pilot:
            await self.loaded(pilot)
            await self.until(pilot, lambda: self.app.chat is not None and self.app.chat.ready)
            await self.say(pilot, "новый вопрос")
            await self.chat_done(pilot)
            await pilot.pause()
            self.assertIn("gpt-6.1-sol/high · 15 tok", screen_text(self.app))

    # G-2 / L-1..L-4: the layout at the terminal the TUI supports, with the whole boundary set at once.
    LONG_MODEL = "ft:gpt-6.1-sol:organization:architect-assistant-2026-10-17"
    LONG_PROVIDER = "o" * 60

    def max_home(self):
        """A valid CODEX_HOME of every shape the layout has to survive at once — long, wide glyphs, a ` · ` of
        its own, a tab and a line break (all legal in a directory name) — with a sixty-character provider
        selected in its config, as the boundary set asks."""
        # One path of four hundred-odd characters, in components a filesystem still accepts (a single name
        # is capped at 255 bytes): the wide glyphs, the ` · ` and the tab and the line break all inside names.
        home = (self.root / "codex-home-max" / ("домашний-каталог-数据 · " + "y" * 110)
                / ("z" * 110 + "\t" + "z" * 110) / ("хвост каталога\n" + "w" * 60))
        home.mkdir(parents=True)
        (home / "config.toml").write_text('model_provider = "%s"\n\n[model_providers."%s"]\n'
                                          'requires_openai_auth = true\n' % (self.LONG_PROVIDER, self.LONG_PROVIDER))
        (home / "auth.json").write_text("{}\n")  # the file login its provider needs for the turn check (R-5)
        self.fixture.env["CODEX_HOME"] = str(home)
        return home

    def max_store(self):
        """The session and the transcript at their maximum: 10**6 turns, 10**15 tokens, thirty one-line
        entries, four entries of ten lines and one entry taller than the whole pane."""
        store = self.fixture.store()
        store.save({"version": 1, "thread_id": None, "model": "gpt-6.1-sol", "created": "2026-01-01T00:00:00Z",
                    "turns": 10 ** 6, "usage": {"input_tokens": 10 ** 15, "output_tokens": 15}})
        for index in range(30):
            store.append("owner" if index % 2 == 0 else "architect", text="прежнее сообщение %d" % index)
        for index in range(4):
            store.append("architect", text="блок %d\n%s" % (index, "\n".join("строка %d" % line
                                                                            for line in range(9))))
        store.append("architect", text="\n".join("длинная запись %d" % line for line in range(60)))
        return store

    def max_binding(self):
        """The role of the boundary set: the longest valid model with the highest effort."""
        return patch.object(self.fixture, "binding",
                            lambda *args, **kw: (lambda project=None: (self.LONG_MODEL, "xhigh")))

    async def test_g2_at_80x24_the_maximum_data_leaves_the_newest_reply_and_the_input_visible(self):
        """G-2 idle (L-1..L-4): with every boundary value at once (the header rows are gone with C1, the data stays) — the 400-character CODEX_HOME of wide
        glyphs with a ` · `, a tab and a line break inside it, the longest valid model at xhigh effort, a
        sixty-character provider, 10**6 turns and 10**15 tokens, thirty entries, four ten-line entries and one
        taller than the pane — the newest reply row is still drawn and the input line under the pane stays."""
        self.max_home()
        store = self.max_store()
        with self.max_binding():
            async with self.shell(size=(80, 24), store=store) as pilot:
                await self.loaded(pilot)
                await self.chat_ready(pilot)
                await self.say(pilot, "максимум")
                await self.chat_done(pilot)
                # i9-look: the input moved into the chat pane, so the 80x24 conversation viewport is shorter; wait
                # for the pane's own refresh (the last entry's mount, then its scroll to the end) to settle before
                # reading the rows, or the newest reply's body falls one render behind the viewport's bottom.
                await self.until(pilot, lambda: "Привет." in screen_text(self.app), 5.0)
                text = screen_text(self.app)
                band = chat_band(self.app)
                rows = len(screen_lines(self.app))
        self.assertIn("Привет.", band)          # the newest reply row is drawn ...
        self.assertIn("Write to the architect… or / for commands", text)  # ... and the input line under the pane is not
        self.assertNotIn("CODEX_HOME", band)            # C1: the pane holds the conversation, not the header
        self.assertLessEqual(rows, 24)                  # ... inside the terminal it was drawn in

    async def test_g2_at_80x24_the_same_maximum_stays_readable_while_a_turn_runs(self):
        """G-2 with a running turn (L-4): the live line carries line breaks of its own (the model streams
        them), and the pane must still draw the newest history row and the input under it."""
        self.max_home()
        store = self.max_store()
        self.fixture.script([{"lines": OPENING + [{"type": "item.completed",
                                                   "item": {"id": "i1", "type": "agent_message",
                                                            "text": "строка\nдругая"}}], "hang": 30}])
        with self.max_binding():
            async with self.shell(size=(80, 24), store=store) as pilot:
                await self.loaded(pilot)
                await self.chat_ready(pilot)
                await self.say(pilot, "максимум")
                await self.until(pilot, lambda: "другая" in screen_text(self.app), 10.0)
                text = screen_text(self.app)
                band = chat_band(self.app)
        self.assertIn("максимум", band)              # the newest history row is drawn ...
        self.assertIn("другая", text)                   # ... the live line shows its streamed text ...
        self.assertIn("Write to the architect… or / for commands", text)  # ... and the input line under the pane stays

    async def test_g2_the_full_codex_home_stays_reachable_in_settings(self):
        """L-3/G-2: the header elides the effective CODEX_HOME in the middle, so the full path has to stay
        reachable somewhere — the settings screen's readiness pane scrolls and shows its whole doctor line,
        with every character of the combined boundary home (wide glyphs, a ` · ` of its own, a tab and a line
        break in the names), and not cut at 256 columns. The pane escapes that line the way L-2 escapes a
        header value, so a control character of a legal directory name is shown, not silently dropped from the
        path. The deterministic fixture drops the tool checks before the pane, so a check that survives its
        filter carries the line: the pane's rendering is what this covers."""
        home = str(self.max_home())              # the whole combined boundary, as a real directory
        doctor = "CODEX_HOME %s ($CODEX_HOME) · provider openai%s" % (home, " · tail" * 40)
        checks = [{"id": "git", "ok": True, "key": None, "line": "", "detail": "", "doctor": doctor}]
        controller = self.controller(readiness=lambda: [dict(check) for check in checks])
        async with self.shell(controller, size=(80, 24)) as pilot:
            await self.loaded(pilot)
            await self.command(pilot, "/setup")
            await pilot.pause(0.2)
            rendered = self.app.screen.query_one("#checks").content.plain
        self.assertNotIn("\x1b", rendered)
        self.assertIn(app_module.plain_value(home), rendered)  # the full path, losslessly escaped
        self.assertGreater(len(doctor), 256)  # ... and the line really is longer than summary's bound

    async def test_g2_a_failed_check_keeps_its_whole_codex_home_in_settings(self):
        """L-3/G-2, the failed branch next to the OK one above. A readiness check that fails keeps its whole
        text in the settings pane too, never `summary`'s 256-character cut: the real configuration failure is
        `codex_home` blocked by a `config.toml` Codex cannot read, and that error names the config file -- the
        resolved CODEX_HOME inside it -- so the full path has to stay reachable here, escaped the way L-2
        escapes a header value (the wide glyphs, the ` · `, the tab and the line break of a legal directory
        name all shown, not dropped). The expected row comes from tests/test_layout's independent L-2 oracle,
        never from the escape helper the screen uses.

        Interpretation (G-5): the item is the one the production resolution makes (`setup.codex_provider`'s
        own error through `setup.item`, then `controller.checks_of`, the conversion `got_checks` stores), and
        it is handed to the pane's own `render_state`. It is not delivered through the fixture controller's
        readiness because `planning.items("start")` drops every tool check (`FIXTURE_SKIPS`, `codex_home`
        among them) for the deterministic engine, so the fixture list can never carry this item; the pane's
        failed branch does not read the id, so this is the same code path production reaches. In the item
        `readiness` builds for this failure, further, the long text rides the
        `detail` row (the `line` is the short "Настройки Codex не читаются …"), so the detail row is where the
        path has to survive; putting `summary` back in that row in a scratch copy cut the line at 256 columns
        and this check failed on the missing path."""
        home = self.max_home()                         # the combined boundary home, now with a real config.toml
        config = home / "config.toml"
        config.write_bytes(b"\xff\xfe\x00 not utf-8")  # a UnicodeDecodeError names the file, with the home in it
        with patch.dict(os.environ, {"CODEX_HOME": str(home)}):
            items = setup.readiness(project=None, tools=True)  # the item list the settings screen really gets
        blocked = [item for item in items if item["id"] == "codex_home"]
        self.assertEqual([item["ok"] for item in blocked], [False], blocked)
        # The error names the config file, which carries the resolved CODEX_HOME; it is the detail row below.
        self.assertGreater(len(blocked[0]["detail"]), 256)  # longer than summary's bound
        controller = self.controller()
        async with self.shell(controller, size=(80, 24)) as pilot:
            await self.loaded(pilot)
            await self.command(pilot, "/setup")
            await pilot.pause(0.2)
            self.app.checks = controller_module.checks_of(items)
            self.app.screen.render_state()
            await pilot.pause()
            rendered = self.app.screen.query_one("#checks").content.plain
        self.assertNotIn("\x1b", rendered)
        self.assertIn(text_oracle(str(config)), rendered)  # the whole config path, losslessly escaped

    async def test_g3_a_late_update_during_the_unmount_is_dropped_and_never_renders(self):
        """G-3/L-5: once MainScreen has begun to unmount no further render runs and a late chat update is
        dropped instead of painting widgets that are already gone. The teardown is held at its first await —
        the flag the unmount sets is in place there — the update is delivered from the app's own loop while it
        is held, and then the teardown is released. The paints of the screen's ordinary life are counted first
        and only the paints after the unmount began are a violation. `is_running` is patched True on purpose:
        the heuristic is not the rule, a screen can still look alive while it is going away, and it is the
        unmount that must stop it. The chat body's own rebuild is called at the same point — the one a status
        change had scheduled — and it must neither render nor raise once the screen is going away."""
        delivered, renders, release = {}, [], asyncio.Event()
        real_unmount = app_module.MainScreen.on_unmount
        real_render = app_module.MainScreen.render_state

        async def held(self_):
            real_unmount(self_)           # the unmount path, whose first step sets the closing flag
            delivered["held"] = True      # the synchronisation point of the test
            delivered["painted"] = len(renders)  # everything painted so far is the screen's ordinary life
            try:
                self_.render_chat()       # the rebuild a status change had scheduled: dropped here too
            except Exception as error:    # L-5: nothing renders inside the unmount, and nothing raises —
                delivered["chat"] = error  # by now the screen's widgets are gone (NoMatches without the guard)
            await release.wait()

        def counted(self_):
            renders.append(self_)
            real_render(self_)

        async def late_update():
            while not delivered.get("held"):
                await asyncio.sleep(0.02)
            delivered["during"] = delivered.get("held", False)
            try:
                self.app.changed()        # the chat's own update path (`on_change`) — a late one
            except Exception as error:    # L-5: a late update never raises
                delivered["error"] = error
            release.set()                 # ... and only now does the teardown go on

        with patch.object(app_module.MainScreen, "on_unmount", held), \
                patch.object(app_module.MainScreen, "render_state", counted), \
                patch.object(app_module.MainScreen, "is_running", property(lambda self_: True)):
            async with self.shell(size=(80, 24)) as pilot:
                await self.loaded(pilot)
                await self.chat_ready(pilot)
                asyncio.ensure_future(late_update())
        self.assertTrue(delivered.get("held"), "the unmount never reached its synchronisation point")
        self.assertTrue(delivered.get("during"), "the update was not delivered inside the held unmount")
        self.assertIsNone(delivered.get("error"), "a late update raised: %r" % (delivered.get("error"),))
        self.assertEqual(len(renders), delivered.get("painted"),
                         "a screen that had begun to unmount was painted")
        self.assertIsNone(delivered.get("chat"),
                          "a rebuild inside the unmount raised: %r" % (delivered.get("chat"),))

    async def test_g2_a_status_line_growing_above_the_chat_does_not_crop_the_newest_reply(self):
        """L-1/L-4: the rows the chat draws are the ones its region really has. A status line above it grows
        (a planner line, a run note), so the region shrinks after the rows were built: the pane rebuilds them
        for the smaller region, and the newest reply row — which a stale budget would leave in a crop — is
        still drawn, with the input line under the pane."""
        async with self.shell(size=(80, 24)) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            await self.say(pilot, "привет")
            await self.chat_done(pilot)
            await pilot.pause()
            self.assertIn("Привет.", chat_band(self.app))
            self.app.run_note = "one\ntwo\nthree\nfour\nfive"  # the status box grows over the chat
            self.app.changed()
            await pilot.pause(0.2)
            band = chat_band(self.app)
            text = screen_text(self.app)
        self.assertIn("Привет.", band)          # the newest reply survived the smaller region
        self.assertIn("Write to the architect… or / for commands", text)  # ... and the input under the pane stays

    async def test_c4_c6_an_operation_the_other_window_refused_stays_visible_while_idle(self):
        """u3b-chat C-4/C-6 with L-4: while another window holds the project's lock, the send and the reset
        the chat refuses keep their line and catalog code on the screen. Both write nothing (C-6) and an idle
        chat has no state row (L-4), so the refusal is the pane's own line above the chat — not a note that
        disappears with the turn."""
        before = self.fixture.files()
        async with self.shell(size=(80, 24)) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            with self.fixture.architect()._lock():
                await self.say(pilot, "чужой замок")
                await self.chat_done(pilot)
                await pilot.pause()
                self.assertIn("architect.locked", self.app.chat.state.note)
                self.assertIn("architect.locked", screen_text(self.app))
                await self.command(pilot, "/new")   # the reset is refused by the same lock
                await self.chat_done(pilot)
                await pilot.pause()
                self.assertIn("architect.locked", screen_text(self.app))
        self.assertEqual(self.fixture.files(), before)  # both refusals wrote nothing (C-6)
        self.assertEqual(self.fixture.calls(), [])

    async def test_c6b_the_model_reply_is_rendered_without_terminal_control_sequences(self):
        """The model supplies the chat text, so it may carry a terminal control sequence. The live streamed
        line, the final reply and the history rebuilt from the store all get L-2's treatment before they are
        wrapped: the sequence is taken out whole, so the text reaches the screen (and the composer's output)
        without a single escape of it, never as a command and never as safe's `?` standing in for one."""
        self.fixture.script([{"lines": ESCAPED, "hang": 3}])
        async with self.shell() as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            await self.say(pilot, "вопрос")
            await self.until(pilot, lambda: "конец" in screen_text(self.app), 10.0)
            self.assertNotIn("\x1b", screen_text(self.app))  # the live streamed text is filtered
            await self.chat_done(pilot)
            await self.until(pilot, lambda: "началоконец" in screen_text(self.app), 5.0)
            final = screen_text(self.app)
            self.assertNotIn("\x1b", final)
            self.assertIn("началоконец", final)  # the CSI sequence went; the text on both sides of it stays
        async with self.shell() as pilot:  # the history rebuilt from the store is filtered too
            await self.loaded(pilot)
            await self.until(pilot, lambda: self.app.chat.state.phase == "ready" and self.app.chat.state.entries)
            await self.until(pilot, lambda: "началоконец" in screen_text(self.app), 5.0)
            restored = screen_text(self.app)
            self.assertNotIn("\x1b", restored)
            self.assertIn("началоконец", restored)

    async def test_c6b_a_cancelled_turn_marks_its_partial_without_terminal_control_sequences(self):
        """A cancelled turn's partial text is model text as well: the marked `(interrupted)` line is filtered, and
        the restart that rebuilds the partial from the store filters it the same way."""
        self.fixture.script([{"lines": ESCAPED, "hang": 30}, {"lines": REPLY}], ignore_term=True)
        async with self.shell() as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            await self.say(pilot, "долгий вопрос")
            await self.until(pilot, lambda: "конец" in screen_text(self.app), 10.0)
            await pilot.press("escape")  # cancel while the input has focus
            await self.chat_done(pilot)
            await self.until(pilot, lambda: "(interrupted)" in screen_text(self.app), 5.0)
            text = screen_text(self.app)
            self.assertNotIn("\x1b", text)
            self.assertIn("(interrupted)", text)
            self.assertIn("началоконец", text)
        async with self.shell() as pilot:  # the partial rebuilt from the store is filtered too
            await self.loaded(pilot)
            await self.until(pilot, lambda: self.app.chat.state.phase == "ready" and self.app.chat.state.entries)
            await self.until(pilot, lambda: "(interrupted)" in screen_text(self.app), 5.0)
            restored = screen_text(self.app)
            self.assertNotIn("\x1b", restored)
            self.assertIn("(interrupted)", restored)
            self.assertIn("началоконец", restored)

    async def test_c6b_the_status_box_shows_the_newest_planner_line_of_a_long_progress_log(self):
        """The status box fits at most 40% of the left pane: the tail must be cut to that, or the newest
        planner line is hidden behind the cap."""
        # I7: the box lives in the chat pane, which narrow mode hides whenever the canvas is shown — and this test
        # presses Tab to the panel to check the progress stays visible below it. So it runs wide (both panes), where
        # that layout exists; the 40% cap is read off the pane's own height, whatever the size.
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            pane = self.app.query_one("#chat-pane")
            self.app.watching = True
            for index in range(30):
                self.app.progress.append("шаг планировщика %d" % index)
            self.app.changed()
            await pilot.press("tab")  # the panel keeps the progress visible too, not only the chat
            await pilot.pause()
            self.assertIn("шаг планировщика 29", self.flat())
            self.assertLessEqual(self.app.query_one("#status").size.height,
                                 max(int(pane.size.height * 0.4), 1) + 1)

    # C-7
    async def test_c7_a_missing_install_shows_the_catalog_refusal_and_the_rest_still_works(self):
        async with self.shell(chat_prepare=False) as pilot:  # False: the production prepare
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            text = chat_band(self.app)
            self.assertIn("zplan setup", text)
            self.assertIn("setup.tools_invalid", text)
            await self.say(pilot, "вопрос")
            self.assertEqual(self.query("#input").value, "вопрос")
            await pilot.press("tab")  # back to the panel: its keys act again
            await self.command(pilot, "/setup")  # plan and milestone actions still work
            self.assertEqual(self.app.screen.__class__.__name__, "SettingsScreen")
            await pilot.press("escape")
            await self.command(pilot, "/view")  # no plan: the note, no screen opens (K1b)
            await self.until(pilot, lambda: "no plan yet — /plan <goal>" in self.flat())
            self.assertEqual(self.app.screen.__class__.__name__, "MainScreen")

    async def test_c7_the_catalog_refusal_and_the_remedy_stay_visible_beside_a_progress_or_run_line(self):
        """u3b-chat C-7/C-6: the area above the chat is the pane's own line, and while the planner observes or
        a run is watched it shows the planner's or the run's lines. The chat's refusal is the reason the chat
        reads as it does, so its remedy and its catalog code stay beside those lines — this area is the only
        place they have (a blocked chat's own state row is one elided line, and an idle chat has no row at
        all). A progress or run line must never become the one thing the area can say.

        Interpretation (G-5): the chat's lines are appended *after* the planner's or the run's own lines, so
        the area's 40% cap — which keeps the bottom rows — cuts the progress line first and the refusal last;
        and `chat_note`/`chat_outcome` are kept in every branch, not only the idle one, because they are the
        chat's line and the chat is the same object whatever the planner draws above it."""
        for mode in ("planner", "run_watch", "run_note"):
            with self.subTest(mode=mode):
                async with self.shell(size=(80, 24), chat_prepare=False) as pilot:
                    await self.loaded(pilot)
                    await self.chat_ready(pilot)
                    self.assertEqual(self.app.chat.state.phase, "blocked")
                    self.app.progress.clear()
                    self.app.run_watch, self.app.run_note, self.app.run_lines = None, "", ()
                    if mode == "planner":
                        self.app.note("Свежая строка планировщика")
                    elif mode == "run_watch":
                        self.app.run_watch, self.app.run_lines = "M1", ("Свежая строка планировщика",)
                    else:
                        self.app.run_note = "Свежая строка планировщика"
                    self.app.changed()
                    await pilot.pause()
                    await self.say(pilot, "почему нельзя")
                    await pilot.pause()
                    status = self.app.query_one("#status", Static).content.plain
                    self.assertIn("Свежая строка планировщика", status)
                    self.assertIn("zplan setup", status)
                    self.assertIn("setup.tools_invalid", status)
                    self.assertLess(status.index("Свежая строка планировщика"), status.index("zplan setup"))
                    text = screen_text(self.app)
                    self.assertIn("Свежая строка планировщика", text)
                    self.assertIn("zplan setup", text)
                    self.assertIn("setup.tools_invalid", text)

    async def test_c6_a_lock_refusal_stays_visible_beside_planner_progress(self):
        """u3b-chat C-6/C-7 with L-4: another window's project lock turns the send away with
        `architect.locked`, and an idle chat has no state row — the refusal is the pane's own line above the
        chat. It has to stay there while the planner's progress is what the area shows: the lock is the reason
        the chat answered nothing, and a progress line above it does not make that refusal go away."""
        async with self.shell(size=(80, 24)) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            self.app.note("Свежая строка планировщика")
            self.app.changed()
            await pilot.pause()
            with self.fixture.architect()._lock():
                await self.say(pilot, "чужой замок")
                await self.chat_done(pilot)
                await pilot.pause()
                self.assertIn("architect.locked", self.app.chat.state.note)
                status = self.app.query_one("#status", Static).content.plain
                self.assertIn("Свежая строка планировщика", status)
                self.assertIn("architect.locked", status)
                self.assertIn("architect.locked", screen_text(self.app))

    async def test_c7_a_fixed_readiness_lets_a_blocked_chat_prepare_again(self):
        """A chat that refused (a missing toolchain, login or role) must not stay blocked until a restart: once
        readiness is fixed (a successful setup or a recheck), the app retries its preparation off the event loop
        and a send then works."""
        fixed = threading.Event()
        calls = []
        build = self.fixture.prepare()

        def flaky(project=None):
            calls.append(project)
            if not fixed.is_set():
                raise Blocked("Инструменты zplan не установлены: выполните zplan setup.",
                              family="setup.tools_invalid")
            return build(project)

        async with self.shell(chat_prepare=flaky) as pilot:
            await self.loaded(pilot)
            await self.until(pilot, lambda: self.app.chat.state.phase == "blocked")
            self.assertIn("setup", self.app.chat.state.refusal)
            self.assertFalse(self.app.send_chat("пока нет")[0])
            before = len(calls)
            fixed.set()  # the toolchain is installed (zplan setup succeeded)
            self.app.got_checks((controller_module.Check("tools", True, "ok", "", "", None),), None)
            await self.until(pilot, lambda: self.app.chat.state.phase == "ready")
            self.assertGreater(len(calls), before)  # the blocked chat prepared again, no restart
            self.assertTrue(self.app.send_chat("теперь можно")[0])
            await self.chat_done(pilot)
            self.assertTrue(self.fixture.calls())

    # C-8
    async def test_c8_typing_and_focus_changes_start_no_turn(self):
        async with self.shell() as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            await pilot.press(*"psgr?")
            self.assertEqual(self.query("#input").value, "psgr?")  # letters and panel keys are text (D4: input focused)
            self.assertEqual(self.app.screen.__class__.__name__, "MainScreen")
            await pilot.press("tab", "tab")  # focus changes start nothing either
            await self.until(pilot, lambda: self.app.snapshot is not None)
            await pilot.pause(0.4)
            self.assertEqual(self.fixture.calls(), [])
            self.assertFalse(self.app.chat.busy)

    # C-9
    async def test_c9_the_placeholder_wording_is_gone_and_the_chat_keys_are_in_the_help(self):
        root = Path(__file__).resolve().parents[1]
        for name in ("README.md", "docs/USER_FLOW.md"):
            self.assertNotIn("появится в следующей версии", (root / name).read_text(encoding="utf-8"), name)
        async with self.shell(size=(140, 40)) as pilot:
            await self.loaded(pilot)
            await self.panel(pilot)  # D4: the pane's `?` needs the pane focused
            await self.command(pilot, "/help")
            text = screen_text(self.app)
            for action in ("tui_input.send", "tui_input.cancel", "tui_input.reset"):
                self.assertIn(catalog.action(action).hint, text, action)
            await pilot.press("escape")


class DraftDisplayTests(unittest.TestCase):
    """D-1/D-5 at the entry level, pure and without Textual: a stored reply's drafts as `entries_of` shows them.

    A draft is `actionable` only when its identity and the turn's success mark were persisted with the reply: a
    record without that metadata (a reply stored before drafts existed, or one whose drafts were stored without
    the mark) comes back as the copyable text it was stored with. `entries_of` never binds a stored draft to the
    current snapshot, so an old record cannot borrow it.

    Interpretations of the draft contract (u3b-drafts-data left these open; recorded here for the reviewers):

    - The pane line of one draft is `↳ <kind> draft: <text>`, with the milestone named for an answer
      (`answer draft M1: …`): kind, milestone, then the draft text, which stays copyable. No key is added.
    - `actionable` is the persisted success mark (`status == "completed"`) together with a stored identity that is
      not None. The string "no plan" is an identity (a turn sent with no plan is still provenance), a missing plan
      state is none, and a draft without an identity is shown but never actionable.
    - The identity is the plain data the adapter stored with the reply; the tests compare it as it is, never
      recomputed from the current screen."""

    MARK = {"status": "approved", "override": False}
    ROWS = [
        {"role": "owner", "text": "вопрос"},
        {"role": "architect", "text": "Вот черновики.", "status": "completed",
         "drafts": [{"kind": "goal", "text": "Цель", "milestone": None, "identity": [1, MARK]},
                    {"kind": "answer", "text": "Ответ", "milestone": "M1",
                     "identity": {"milestone": "M1", "attempt": 1}}]},
        {"role": "architect", "text": "Старый ответ",
         "drafts": [{"kind": "goal", "text": "Старое", "identity": [1, MARK]}]},
        {"role": "error", "text": "Сбой", "drafts": [{"kind": "goal", "text": "Нельзя", "identity": [1, MARK]}]},
    ]

    def test_a_stored_reply_shows_its_drafts_and_the_success_mark_makes_them_actionable(self):
        marked = chat_module.entries_of(self.ROWS)[1]
        self.assertEqual([(d.kind, d.text, d.milestone, d.actionable) for d in marked.drafts],
                         [("goal", "Цель", "", True), ("answer", "Ответ", "M1", True)])
        self.assertEqual(marked.drafts[0].identity, [1, self.MARK])          # the stored identity, as it is
        self.assertEqual(marked.drafts[1].identity, {"milestone": "M1", "attempt": 1})
        lines = [text for _kind, text in chat_module.entry_blocks(marked)]
        self.assertIn("↳ goal draft: Цель", lines)                        # a distinct, labelled item
        self.assertIn("↳ answer draft M1: Ответ", lines)                  # an answer names its milestone

    def test_a_record_without_the_success_mark_is_text_only(self):
        unmarked = chat_module.entries_of(self.ROWS)[2]                      # drafts stored, no success mark
        self.assertEqual([(d.kind, d.actionable) for d in unmarked.drafts], [("goal", False)])
        self.assertIn("↳ goal draft: Старое", [text for _kind, text in chat_module.entry_blocks(unmarked)])  # still shown
        self.assertEqual(chat_module.entries_of(self.ROWS)[3].drafts, ())    # only an architect reply drafts

    def test_a_draft_without_an_identity_and_an_unknown_kind_are_not_drafts(self):
        row = {"role": "architect", "text": "x", "status": "completed",
               "drafts": [{"kind": "goal", "text": "Цель", "identity": None},
                          {"kind": "bogus", "text": "Мимо", "identity": [1, self.MARK]}]}
        drafts = chat_module.entries_of([row])[0].drafts
        self.assertEqual([(d.kind, d.actionable) for d in drafts], [("goal", False)])


class DraftChoiceTests(unittest.TestCase):
    """U-3's choice (the retained-history source of [c]) and the goal draft's provenance re-check, pure and
    without Textual.

    Interpretations this task had to fix (recorded here because the worker's own summary never reaches the
    reviewers):

    - The choice is made from `ChatState.entries` (the retained history, `HISTORY` rows) and from nothing else —
      never from what the chat pane happens to show — and it is the newest *actionable* goal draft in it.
      "Actionable" is exactly the stored contract of u3b-drafts-data: kind `goal`, a stored identity that is not
      None, and the turn's success mark; an answer draft, an unmarked reply and a draft without an identity are
      not the choice, so a newer reply whose only goal draft is not actionable leaves an older actionable one the
      choice. An entry the retained window has dropped is not the choice either.
    - The refusal wording is `draft is outdated: <reason>` (what the owner sees after "Not done: "), with its
      reasons: "a plan appeared" when the draft was written with no plan and a plan exists now, "the plan is gone" for the
      reverse, "new revision" when the revision moved, and "plan state changed" for the same revision
      whose state moved on (submitted, plan ready, approved, override). An identity the draft cannot carry (None)
      is stale and is never read as "no plan"; two equal identities are not stale."""

    MARK = {"status": "approved", "override": False}

    @staticmethod
    def entries(*identities):
        """One marked architect reply per identity; identity None drops the draft's own provenance."""
        rows = [{"role": "architect", "text": "ответ %d" % index, "status": "completed",
                 "drafts": [{"kind": "goal", "text": "цель %d" % index, "identity": identity}]}
                for index, identity in enumerate(identities)]
        return chat_module.entries_of(rows)

    def test_the_choice_is_the_newest_actionable_goal_draft_of_the_retained_history(self):
        entries = self.entries("no plan", [1, self.MARK], "no plan")
        self.assertEqual(chat_module.newest_goal_draft(entries).text, "цель 2")

    def test_a_newer_non_actionable_draft_leaves_the_older_actionable_one_the_choice(self):
        rows = [{"role": "architect", "text": "a", "status": "completed",
                 "drafts": [{"kind": "goal", "text": "старая", "identity": "no plan"}]},
                {"role": "architect", "text": "b", "status": "completed",
                 "drafts": [{"kind": "goal", "text": "без идентичности"}]},              # stored, no identity
                {"role": "architect", "text": "c",
                 "drafts": [{"kind": "goal", "text": "без метки", "identity": "no plan"}]}]  # no success mark
        self.assertEqual(chat_module.newest_goal_draft(chat_module.entries_of(rows)).text, "старая")

    def test_only_a_goal_draft_is_a_choice(self):
        rows = [{"role": "architect", "text": "a", "status": "completed",
                 "drafts": [{"kind": "answer", "text": "ответ", "milestone": "M1",
                             "identity": {"milestone": "M1", "attempt": 1}}]}]
        self.assertIsNone(chat_module.newest_goal_draft(chat_module.entries_of(rows)))
        self.assertIsNone(chat_module.newest_goal_draft(()))

    def test_an_entry_the_retained_window_dropped_is_no_choice(self):
        rows = [{"role": "architect", "text": "черновик", "status": "completed",
                 "drafts": [{"kind": "goal", "text": "цель", "identity": "no plan"}]}]
        rows += [{"role": "owner", "text": "дальше"} for _ in range(chat_module.HISTORY)]
        self.assertEqual(len(chat_module.entries_of(rows)), chat_module.HISTORY)
        self.assertIsNone(chat_module.newest_goal_draft(chat_module.entries_of(rows)))

    def test_the_reasons_a_goal_draft_goes_stale(self):
        mark = self.MARK
        stale = chat_module.stale_reason
        self.assertEqual(stale("no plan", "no plan"), "")
        self.assertEqual(stale([1, mark], [1, mark]), "")
        self.assertEqual(stale("no plan", [1, mark]), "a plan appeared")
        self.assertEqual(stale([1, mark], "no plan"), "the plan is gone")
        self.assertEqual(stale([1, mark], [2, mark]), chat_module.NEW_REVISION)
        self.assertEqual(stale([1, mark], [1, {"status": "proposed", "override": False}]),
                         chat_module.STATE_CHANGED)
        self.assertEqual(stale(None, [1, mark]), chat_module.STATE_CHANGED)
        self.assertEqual(stale([1, mark], None), chat_module.STATE_CHANGED)
        self.assertNotIn(chat_module.STATE_CHANGED, chat_module.OUTDATED)


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class DraftJourneyTests(ChatShell):
    """D-0/D-5/D-6 through the real app: the scripted codex, the fixture store and the fixture plan.

    The identity a turn carries is the plain projection `chat_snapshot` froze at send time; the tests never
    recompute it from a later screen. The order of a turn and a refresh is an explicit handshake, never a timer:
    the fake codex emits the whole reply and then keeps its process alive until the test creates a release file
    (`release` in the scripted step), so the test can make the screen move on and only then free the turn
    (send -> a refresh whose snapshot differs -> release completion). The plan state, as the controller snapshot
    names it, is the pair (`status`, `override`): an owner override over a rejected gate keeps the `approved`
    status and differs only in `override`, which is why the pair, not the revision number alone, is the identity."""

    def plan_it(self, app):
        """The owner plans while a chat turn still runs: `begin` + the fixture proposal + approve, on the
        controller's worker — the one thread that holds the Authority lock (`ShellTest.approve` off the loop)."""
        self.begin(app.authority)
        self.propose(app.authority)
        app.authority.approve(1)

    def window(self):
        """A second chat window over the same store (the app itself cannot run twice in one process: one
        Authority lock); it reloads the transcript the app wrote, exactly as an app restart does."""
        instance = chat_module.ArchitectChat(self.project, self.fixture.prepare(), binding=self.fixture.binding())
        self.addCleanup(instance.close)
        instance.start()
        end = time.monotonic() + 5.0
        while instance.state.phase == "preparing" and time.monotonic() < end:
            time.sleep(0.005)
        self.assertNotEqual(instance.state.phase, "preparing", instance.state)
        return instance

    async def test_d0_a_resumed_turn_prompt_carries_the_draft_protocol(self):
        """A resumed turn (a saved thread id: `build_update`, not `build_preamble`) is told the draft protocol
        again — a saved thread id means the architect has a history, not that it remembers the format."""
        async with self.shell() as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            await self.say(pilot, "первый")
            await self.chat_done(pilot)
            await self.say(pilot, "второй")
            await self.chat_done(pilot)
        calls = self.fixture.calls()
        self.assertEqual(calls[0]["argv"][:2], ["exec", "--json"])              # the first turn: the preamble
        self.assertEqual(calls[1]["argv"][:3], ["exec", "resume", THREAD])      # the resumed turn: the update
        self.assertIn("```zplan-goal", calls[0]["stdin"])
        self.assertNotIn("Updated state snapshot (read-only):", calls[0]["stdin"])
        self.assertIn("Updated state snapshot (read-only):", calls[1]["stdin"])  # build_update, not the preamble
        self.assertNotIn("You are the zplan architect", calls[1]["stdin"])
        self.assertIn("```zplan-goal", calls[1]["stdin"])
        self.assertIn("```zplan-answer <milestone id>", calls[1]["stdin"])

    async def test_d0_the_identity_is_the_send_time_snapshot_not_a_later_refresh(self):
        """The turn's snapshot is taken once, at send: the goal draft of the reply carries "no plan" (the state
        at send), and the plan the owner approves while the turn still runs — a refresh the screen then shows —
        never rewrites it.

        The synchronisation is the explicit `release` handshake, not a sleep: the scripted codex writes the whole
        reply and then waits for a file this test creates only after it has observed the refresh change the
        screen. So the reply provably completes after the snapshot moved (the turn is still in flight — `busy` —
        while the screen already shows revision 1)."""
        release = self.root / "d0.release"
        self.fixture.script([{"lines": says("Вот черновик:\n" + goal_block("Сделать X")), "release": str(release)}])
        async with self.shell() as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            self.assertIsNone(self.app.chat_snapshot()["revision"])             # no plan when the turn is sent
            await self.say(pilot, "что дальше")
            await self.until(pilot, lambda: self.app.chat.busy)
            await self.post_and_wait(pilot, self.plan_it)                       # the owner approves a plan meanwhile
            self.app.request_refresh()
            await self.until(pilot, lambda: self.app.snapshot is not None and self.app.snapshot.version == 1)
            self.assertEqual(self.app.chat_snapshot()["revision"], 1)           # the screen moved on
            self.assertTrue(self.app.chat.busy)                                 # ... while the turn still runs
            release.write_text("go")                                           # explicit release: the reply ends now
            await self.chat_done(pilot, timeout=10.0)
        row = self.fixture.store().transcript()[-1]
        self.assertEqual(row["status"], "completed")
        self.assertEqual([d["kind"] for d in row["drafts"]], ["goal"])
        self.assertEqual(row["drafts"][0]["identity"], "no plan")               # the identity of the send-time state

    async def test_d0_a_screen_without_a_snapshot_names_no_plan_identity(self):
        """A screen that has no snapshot yet names an unknown plan state, never the confirmed absence of a plan:
        `chat_snapshot` omits `revision` altogether, so `architect.plan_identity` of that projection is None (not
        "no plan") and a goal draft of such a turn carries no identity. The reviewer reproduced the reverse
        through the app (a delayed first refresh was saved as "no plan", actionable=True); this pins the
        projection itself, while the parser and entry tests pin the rest of the chain (no `revision` -> identity
        None -> `actionable` False)."""
        async with self.shell() as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            current = self.app.snapshot
            self.app.snapshot = None                        # the first refresh has not arrived yet
            try:
                projection = self.app.chat_snapshot()
            finally:
                self.app.snapshot = current                 # restore at once: no await between the three lines
            self.assertNotIn("revision", projection)        # unknown, never "no plan"
            self.assertIsNone(adapter.plan_identity(projection))
            self.assertEqual([d["identity"] for d in adapter.parse_drafts(goal_block("X"), projection)], [None])

    async def test_d5_drafts_come_back_after_a_restart_and_in_a_second_window(self):
        """A reply's drafts are stored with the turn's success mark and their own identity: a restarted app and a
        second window rebuild exactly those drafts, still actionable, from the transcript alone."""
        self.approve(running=True)                     # plan r1, M1 running: the milestone carries an attempt token
        reply = "Вот черновики.\n" + goal_block("Цель черновика") + "\n" + answer_block("M1", "Ответ черновика")
        self.fixture.script([{"lines": says(reply)}])
        async with self.shell() as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            sent = self.app.chat_snapshot()
            await self.say(pilot, "вопрос")
            await self.chat_done(pilot)
            await pilot.pause()                            # the entry's widgets (time line, body) settle
            self.assertIn("goal draft: Цель черновика", chat_band(self.app))
            self.assertIn("answer draft M1: Ответ черновика", chat_band(self.app))
            second = self.window()
            await self.until(pilot, lambda: any(e.drafts for e in second.state.entries))
            other = [e for e in second.state.entries if e.role == "architect"][-1]
            self.assertEqual([(d.kind, d.actionable) for d in other.drafts], [("goal", True), ("answer", True)])
        row = self.fixture.store().transcript()[-1]
        self.assertEqual(row["status"], "completed")
        self.assertEqual(row["drafts"][0]["identity"], [1, sent["plan_state"]])
        self.assertEqual(row["drafts"][1]["identity"], sent["milestones"][0]["token"])
        async with self.shell() as pilot:              # an app restart rebuilds the same drafts, actionable
            await self.until(pilot, lambda: self.app.chat is not None and any(e.drafts for e in self.app.chat.state.entries))
            entry = [e for e in self.app.chat.state.entries if e.role == "architect"][-1]
            self.assertEqual([(d.kind, d.milestone, d.actionable) for d in entry.drafts],
                             [("goal", "", True), ("answer", "M1", True)])
            self.assertEqual(entry.drafts[0].identity, [1, sent["plan_state"]])
            self.assertEqual(entry.drafts[1].identity, sent["milestones"][0]["token"])
            await self.until(pilot, lambda: "answer draft M1: Ответ черновика" in chat_band(self.app), 5.0)

    async def test_d5_a_record_without_the_success_mark_comes_back_as_text_only(self):
        """A reply stored without the turn's success mark is copyable text: the pane shows its drafts' labelled
        lines but none is actionable, and a record stored before drafts existed carries none at all."""
        store = self.fixture.store()
        store.append("owner", text="вопрос")
        store.append("architect", text="Вот:\n" + goal_block("Цель без метки"),
                     drafts=[{"kind": "goal", "text": "Цель без метки", "milestone": None,
                              "identity": [1, {"status": "approved", "override": False}]}])
        async with self.shell() as pilot:
            await self.until(pilot, lambda: self.app.chat is not None and any(e.drafts for e in self.app.chat.state.entries))
            entry = [e for e in self.app.chat.state.entries if e.role == "architect"][-1]
            self.assertEqual([d.actionable for d in entry.drafts], [False])
            await self.until(pilot, lambda: "goal draft: Цель без метки" in chat_band(self.app), 5.0)
        self.assertEqual([e.drafts for e in chat_module.entries_of(store.transcript()) if e.role == "architect"],
                         [(chat_module.Draft("goal", "Цель без метки", "", [1, {"status": "approved", "override": False}], False),)])

    async def test_d6_a_reply_with_drafts_writes_no_authority_state_and_ends_no_run(self):
        """The architect is advisory: a reply that carries drafts appends to its own store and touches nothing
        else — no Authority write, no run finish, no branch export."""
        self.approve(running=False)
        authority_path = RealAuthority(self.state, self.project, fixture_id="test").path
        before = authority_path.read_bytes()
        self.fixture.script([{"lines": says(goal_block("Цель") + "\n" + answer_block("M1", "Ответ"))}])
        with patch("terminal_planner.export.create_branch") as exported, \
                patch("terminal_planner.runs.MilestoneRuns.finish") as finished, \
                patch("terminal_planner.authority.Authority.save", autospec=True) as saved:
            async with self.shell() as pilot:
                await self.loaded(pilot)
                await self.chat_ready(pilot)
                await self.say(pilot, "вопрос")
                await self.chat_done(pilot)
        self.assertEqual(authority_path.read_bytes(), before)   # the Authority store bytes are untouched
        saved.assert_not_called()
        finished.assert_not_called()
        exported.assert_not_called()
        self.assertEqual(self.fixture.store().transcript()[-1]["drafts"][0]["kind"], "goal")  # the reply was stored

@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class GoalDraftTests(ChatShell):
    """U-3/D-4b through the real app: the choice of the newest actionable goal draft, and the provenance re-check on
    the controller worker when the draft card's `/plan` sends it.

    K1b removed the goal form and its `[c]` key: a draft reaches the planner only from its card (the button or the
    typed `/plan`, `tests/test_tui_draft_card.py`), so the tests of the form (typed goal replaced only after asking,
    provenance across Esc and `/view`, the key being text in every editor) are gone with it.

    Interpretations:

    - The choice is `chat.newest_goal_draft(ChatState.entries)` — the retained history — never what the chat pane
      happens to show (see `DraftChoiceTests` for the contract and the stale reasons).
    - The refusal is "draft is outdated: <reason>" and is raised on the worker immediately before
      `planning.begin`; nothing is written and no export/finish runs. D-4b's synchronisation point is explicit:
      `controller.goal_identity` is patched to park the worker before it reads the plan identity, the test changes
      the plan identity on the same session, then releases it — so a check made when `/plan` was typed (UI
      thread) instead of on the worker would be missed. The card is open (and so the screen's own check passes)
      because the draft names the plan the screen shows when `/plan` is typed.
    - A draft line is `↳ goal draft: …` (0.6.3 V2 dropped the `reply N · arch ·` prefixes); the draft data
      contract (`chat.Draft`) is unchanged.
    """

    DRAFT = "Сделать X"
    MARK = {"status": "approved", "override": False}
    NO_PLAN = adapter.NO_PLAN  # "no plan": the plan identity of a snapshot that names no revision

    def seed_goal_draft(self, text="Сделать X", identity="no plan", status="completed", after=0):
        """One owner question and one architect reply carrying one goal draft in the store.

        `after` appends that many owner rows behind the reply (to push it out of the retained history); `status`
        other than "completed" drops the success mark, so the draft stops being actionable."""
        store = self.fixture.store()
        store.append("owner", text="вопрос")
        store.append("architect", text="Вот черновик.", status=status,
                     drafts=[{"kind": "goal", "text": text, "milestone": None, "identity": identity}])
        for index in range(after):
            store.append("owner", text="дальше %d" % index)
        return store

    def newest_draft(self):
        """The newest actionable goal draft of the retained history (what the draft card is built from)."""
        return chat_module.newest_goal_draft(self.app.chat.state.entries)

    async def settled(self, pilot, timeout=5.0):
        """The chat is ready and the retained history carries an actionable goal draft."""
        await self.loaded(pilot)
        await self.chat_ready(pilot)
        await self.until(pilot, lambda: self.newest_draft() is not None, timeout)

    async def open_draft(self, pilot):
        """The draft's card is on the main screen, ready for `/plan`."""
        await self.settled(pilot)
        await self.until(pilot, lambda: self.app.screen.draft_card_open())

    def seed_plan(self):
        """Revision 1, planning, before the shell starts: the plan the screen shows and a draft can name."""
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            self.begin(authority)

    def parked_identity(self):
        """A `controller.goal_identity` that parks the worker before it reads the plan identity of the re-check.

        Returns (gated, held, release): `held` is set when the worker reached the synchronisation point, and the
        test sets `release` only after it changed the plan identity on the same session."""
        real = controller_module.goal_identity
        held, release = threading.Event(), threading.Event()

        def gated(planning):
            held.set()
            if not release.wait(10.0):
                raise AssertionError("the provenance re-check was never released")
            return real(planning)
        return gated, held, release

    # U-3 ----------------------------------------------------------------------

    async def test_u3_the_newest_actionable_goal_draft_is_the_choice(self):
        """Several replies: the newest actionable goal draft is the one the screen carries, and a newer reply whose
        goal draft is not actionable (no identity, no success mark) leaves the older one the choice.

        i3a shrinks this test per `devtools/zeroshot/test-retire-0.5.2.md` (row i3a): the trigger it used to walk —
        `[c]` opening the goal form — is the draft card now, so the data assertion stays and the old-UI assertion is
        dropped; the card's own behaviour (show, «да», decline, a stale refusal) is `tests/test_tui_draft_card.py`.
        Interpretation: the card's key is opaque, so the draft the screen carries is compared as `Draft` data
        (`list(screen.draft_cards.values())`), never as a key string."""
        store = self.seed_goal_draft(text="Старая цель", identity="no plan")
        store.append("owner", text="ещё")
        store.append("architect", text="Ответ.", status="completed",
                     drafts=[{"kind": "goal", "text": "Цель без метки"}])   # stored, no identity: not actionable
        store.append("owner", text="и ещё")
        store.append("architect", text="Ответ.", status="completed",
                     drafts=[{"kind": "goal", "text": "Новая цель", "identity": "no plan"}])
        async with self.shell(size=(120, 40)) as pilot:
            await self.settled(pilot)
            await self.until(pilot, lambda: "goal draft: Новая цель" in chat_band(self.app), 5.0)
            self.assertIn("goal draft: Старая цель", chat_band(self.app))  # the labelled items, in the pane
            self.assertIn("goal draft: Новая цель", chat_band(self.app))
            draft = self.newest_draft()
            self.assertEqual(draft.text, "Новая цель")        # the newest actionable draft wins
            self.assertEqual(draft.identity, self.NO_PLAN)
            screen = self.app.screen
            self.assertEqual(type(screen).__name__, "MainScreen")
            self.assertEqual(tui_module().draft_card_of(self.app.chat)[1], draft)  # the same source
            self.assertTrue(screen.draft_card_open())         # and it is the one card the pane shows
            self.assertEqual(list(screen.draft_cards.values()), [draft])

    async def test_u3_a_draft_pushed_out_of_the_retained_history_loses_the_key(self):
        """The source of the choice is the retained history alone: once the reply is pushed out of `HISTORY`
        entries there is no choice any more, even though the transcript still holds the draft.

        i3a shrinks this test per `devtools/zeroshot/test-retire-0.5.2.md` (row i3a): the assertion that replaced the
        key's is the card's, which reads exactly the same source (`chat.newest_goal_draft`) — no card is shown."""
        self.seed_goal_draft(text="Цель", after=chat_module.HISTORY)
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            self.assertIsNone(self.newest_draft())
            screen = self.app.screen
            self.assertEqual(type(screen).__name__, "MainScreen")
            self.assertFalse(screen.draft_card_open())                     # the screen shows no card either
            self.assertEqual(screen.card_widgets, {})

    # D-4b ---------------------------------------------------------------------

    async def test_d4b_a_plan_that_appeared_under_the_draft_is_refused_on_the_worker(self):
        """The draft was written with no plan; the plan appears after `/plan` was typed and while the worker job
        is parked before the re-check, so the re-check reads it then and refuses. Nothing is written."""
        self.seed_goal_draft(text=self.DRAFT, identity=self.NO_PLAN)
        gated, held, release = self.parked_identity()
        authority_path = RealAuthority(self.state, self.project, fixture_id="test").path
        captured = {}
        with patch.object(controller_module, "goal_identity", gated):
            async with self.shell(size=(120, 40)) as pilot:
                await self.open_draft(pilot)
                await self.post_and_wait(pilot, lambda app: captured.update(app=app))
                await self.command(pilot, "/plan")
                await self.until(pilot, held.is_set)                        # parked before the re-check
                self.begin(captured["app"].authority)                       # the plan identity moves: none -> plan
                after_change = authority_path.read_bytes()
                release.set()
                await self.until(pilot, lambda: chat_module.OUTDATED in self.app.goal_message)
                self.assertIn("a plan appeared", self.app.goal_message)
        self.assertEqual(authority_path.read_bytes(), after_change)         # the refusal wrote nothing
        self.assertEqual([r["goal"] for r in json.loads(authority_path.read_text())["revisions"]],
                         ["Requested feature"])                             # only the test's own change

    async def test_d4b_the_same_revision_state_moved_on_is_refused_on_the_worker(self):
        """Same revision, different state (planning -> approved while the worker job is parked): the identity pair
        does not match and the re-check refuses."""
        identity = [1, {"status": "planning", "override": False}]
        self.seed_plan()                                                    # revision 1, planning: the draft is current
        self.seed_goal_draft(text=self.DRAFT, identity=identity)
        gated, held, release = self.parked_identity()
        authority_path = RealAuthority(self.state, self.project, fixture_id="test").path
        captured = {}
        with patch.object(controller_module, "goal_identity", gated):
            async with self.shell(size=(120, 40)) as pilot:
                await self.open_draft(pilot)
                await self.post_and_wait(pilot, lambda app: captured.update(app=app))
                await self.command(pilot, "/plan")
                await self.until(pilot, held.is_set)
                authority = captured["app"].authority
                self.propose(authority)
                authority.approve(1)                                        # revision 1, approved
                after_change = authority_path.read_bytes()
                release.set()
                await self.until(pilot, lambda: chat_module.OUTDATED in self.app.goal_message)
                self.assertIn(chat_module.STATE_CHANGED, self.app.goal_message)
                self.assertNotIn(chat_module.NEW_REVISION, self.app.goal_message)
        self.assertEqual(authority_path.read_bytes(), after_change)

    async def test_d4b_a_new_revision_is_refused_on_the_worker(self):
        """The plan moved to another revision while the worker job was parked: the re-check refuses with the new
        revision named, and the store keeps only the test's own revisions."""
        identity = [1, {"status": "planning", "override": False}]
        self.seed_plan()                                                    # revision 1, planning: the draft is current
        self.seed_goal_draft(text=self.DRAFT, identity=identity)
        gated, held, release = self.parked_identity()
        authority_path = RealAuthority(self.state, self.project, fixture_id="test").path
        captured = {}
        with patch.object(controller_module, "goal_identity", gated):
            async with self.shell(size=(120, 40)) as pilot:
                await self.open_draft(pilot)
                await self.post_and_wait(pilot, lambda app: captured.update(app=app))
                await self.command(pilot, "/plan")
                await self.until(pilot, held.is_set)
                authority = captured["app"].authority
                self.begin(authority)                                       # revision 2
                after_change = authority_path.read_bytes()
                release.set()
                await self.until(pilot, lambda: chat_module.OUTDATED in self.app.goal_message)
                self.assertIn(chat_module.NEW_REVISION, self.app.goal_message)
        self.assertEqual(authority_path.read_bytes(), after_change)
        self.assertEqual(len(json.loads(authority_path.read_text())["revisions"]), 2)


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class AnswerDraftTests(ChatShell):
    """U3b/D-3/D-3b/D-4/D-6a/D-9 through the real app: the [t] answer-draft key, the read-only open of the attempt
    a draft was written for, and the send that keeps the draft's original token.

    Interpretations this task had to fix (the worker's own summary never reaches the reviewers, so they are
    recorded here):

    - "[t] opens the newest actionable answer draft for the milestone selected in the plan pane": the choice is
      `chat.newest_answer_draft(ChatState.entries, app.selection().id)`, so a draft of another milestone is no
      choice at all — no `[t]` in the key bar and `t` does nothing. Several answer drafts in one reply keep the
      reply's own order and the newest wins.
    - The guard is the shared `app.draft_keys_ready` the goal key uses (the plan pane focused, no modal on top):
      `t` is a plain letter in the chat input, the goal TextArea and the answer form, and inert under any other
      modal. No new focusable widget is added for it.
    - "The identity survives opening and editing the modal": the form's send callback closes over the draft's own
      `identity`, never over the token of the view the screen happens to show, so a refresh cannot swap a fresh
      attempt in behind the draft; a refusal reopens the same form with the same text (still copyable).
    - Repair after the rejected acceptance review: the field is the owner's and only the identity is the draft's.
      Every reopen — a stale refusal, the readiness gate, an empty send — carries the text that send was made with,
      so an edited answer is never replaced by the draft's original prefill. Covered by
      `test_a_stale_send_keeps_the_edited_answer_not_the_draft_prefill` and
      `test_a_readiness_refusal_keeps_the_edited_answer`, whose oracle is a literal the test writes into the field;
      in a scratch copy with the reopen falling back to `draft.text` both fail ('Ответ черновика' != the literal).
    - Opening is read-only and starts nothing: on the worker the plain identity is rebuilt into a `Token`,
      `resolve(exact=True)` runs first, and only then `Delivery.view` (never `Delivery.end`) — so a finished, not
      yet exported attempt is not exported by the open. A mismatch, an active attempt, a view without `answer` and
      a malformed identity are refused before any view is built, and a malformed identity is refused by the same
      plain-data rebuild the draft carries (`controller.token_identity`; checked directly for its shapes too).
    - The stale refusal is «draft is outdated: <reason>» with family `draft.stale`, raised on the worker right
      before the answer path and with no `_end`/`Delivery.end`: the typed-answer path keeps its own `_acting`
      branch untouched, the draft path has its own Changed branch with no export, so a stale draft never exports a
      finished attempt. The typed answer's own `_acting` still ends one.
    - D-4's synchronisation point is explicit and on the worker: `controller.token_identity` (called first in both
      draft jobs, before `resolve`) is patched to park the worker; the test then changes the plan or the attempt
      on the app's own session and only then releases it, so a check made when the key was pressed (UI thread)
      instead of on the worker would be missed. Checked in a scratch copy of the checkout, never in the worktree:
      with `delivery.resolve(token, exact=True)` replaced by a raw `delivery.latest(token.milestone)` (no re-check
      at all) the eight D-4 tests fail — the open never shows «draft is outdated» and the send never refuses, so the
      refusal assertions and the store-byte comparisons fail; with the same call weakened to `exact=False` the
      finished-milestone open and send and the changed-outcome open fail instead, while the new-attempt open still
      passes, because the plan/attempt part of the re-check (`exact=False` keeps it) already catches that case.
    - D-4's cases, as the state machine offers them: (a) a new attempt started -> «another attempt started»;
      a new revision — including one that no longer names the draft's milestone, since that is the same revision
      mismatch -> «plan revised»; a still-running attempt driven to its end, and an answerable attempt whose
      outcome/delivery moved on (the milestone finished) -> «attempt progressed». The send half is exercised for
      every case whose attempt can be *opened* into the form first: a still-active attempt is refused at open
      (D-3b), so its running->finished transition is covered on the open path, while the finished-milestone case
      on send is the answerable attempt's outcome/delivery moving to done — the same `attempt progressed`
      reason, and one that leaves the store a valid one the app would accept.
    - "Same records as a typed answer": the draft send ends in exactly `Delivery.answer` (`runs.answer`), proven
      by a spy that reads the record the answer was created from (attempt 1, the draft's own) and its text; the
      stored attempt 2 then carries the same answer context a typed answer writes.
    - D-9's "plan identity" is the pair (revision, `plan_state`) the chat snapshot names, asserted before and after
      the send; the milestone status is deliberately not asserted (the send starts a new attempt, which is its own
      change) and the identity of the goal draft is the send-time snapshot's.
    """

    DRAFT = "Ответ черновика"
    GOAL = "Цель черновика"
    GOAL_IDENTITY = [1, {"status": "approved", "override": False}]

    # Fixtures ------------------------------------------------------------------

    def runs(self, authority):
        """The `MilestoneRuns` of a session over the test's own fixture driver (the controller's driver)."""
        return MilestoneRuns(authority, self.driver, worktrees=authority.directory / "worktrees")

    def seed_plan(self, authority):
        """An approved fixture plan r1 (M1 ready, M2 waits for it); never a second revision."""
        if authority.state and authority.state.get("revisions"):
            return
        self.begin(authority)
        self.propose(authority)
        authority.approve(1)

    def seed_attempt(self, outcome="needs_owner", milestone="M1"):
        """An approved plan and one attempt of `milestone` driven to `outcome` (no UI, no screen).

        Returns the attempt's plain token identity — exactly what an answer draft of it carries
        (`app.token_fields` of `Token.of` the record). The run is advanced with the service's own observation, so
        the stored record is a real finished attempt; the plan is seeded at most once, so a test that calls this
        twice reuses the same revision instead of adding one behind the draft's identity."""
        self.driver.outcomes = (outcome,)
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            self.seed_plan(authority)
            runs = self.runs(authority)
            record = runs.start(milestone, 1, ROLES)
            runs.observe(record)
            return tui_module().token_fields(Token.of(record))

    def seed_other_milestone_attempt(self, milestone="M2", outcome="needs_owner"):
        """A real, stored attempt of another milestone of the plan than M1 (the fixture plan's M2 waits for M1).

        Only the plan's own dependency is bypassed for the fixture (`MilestoneRuns.waiting` is stubbed to no
        waiters), so the store holds a genuine attempt of `milestone` whose own token resolves and whose end offers
        `answer` — exactly the attempt a draft that names M1 must never open or answer. The attempt is advanced
        with the service's own observation, like `seed_attempt`, so its record is a real finished attempt."""
        self.driver.outcomes = (outcome,)
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            self.seed_plan(authority)
            runs = self.runs(authority)
            with patch.object(MilestoneRuns, "waiting", return_value=[]):
                record = runs.start(milestone, 1, ROLES)
            runs.observe(record)
            return tui_module().token_fields(Token.of(record))

    def seed_running(self, milestone="M1"):
        """An approved plan and one attempt of `milestone` left *running*: its plain token identity."""
        self.driver.outcomes = ("done",)
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            self.seed_plan(authority)
            return tui_module().token_fields(Token.of(self.runs(authority).start(milestone, 1, ROLES)))

    def seed_exported_done(self, milestone="M1"):
        """An approved plan and one finished, exported attempt of `milestone` (awaiting a merge).

        The export is the service's own (`MilestoneRuns.finish`, exactly what `Delivery.end` calls), so the stored
        record is `awaiting_merge` and its token — taken after the export — is the draft's identity. Such an end
        view offers `merge` and `diff`, never `answer`."""
        self.driver.outcomes = ("done",)
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            self.seed_plan(authority)
            runs = self.runs(authority)
            record = runs.start(milestone, 1, ROLES)
            runs.observe(record)
            runs.finish(record)
            return tui_module().token_fields(Token.of(record))

    def seed_drafts(self, drafts, text="Вот черновики.", status="completed", after=0):
        """One owner question and one architect reply carrying `drafts` (the draft data contract's plain shape).

        `status` other than "completed" drops the turn's success mark, so the drafts stop being actionable; `after`
        appends that many owner rows behind the reply (to push it out of the retained history)."""
        store = self.fixture.store()
        store.append("owner", text="вопрос")
        store.append("architect", text=text, status=status, drafts=drafts)
        for index in range(after):
            store.append("owner", text="дальше %d" % index)
        return store

    def seed_answer_draft(self, identity, text=None, milestone="M1", **kw):
        """One architect reply whose only draft is an answer draft of `milestone` with `identity`."""
        return self.seed_drafts([{"kind": "answer", "text": text or self.DRAFT, "milestone": milestone,
                                  "identity": identity}], **kw)

    def running_identity(self):
        """M1's token of the running attempt `approve(running=True)` started (before any app is open)."""
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            return tui_module().token_fields(Token.of(authority.state["runs"][-1]))

    # Driving --------------------------------------------------------------------

    @staticmethod
    def answer_text(app):
        """The answer form's TextArea: `app.query_one` searches the app's main screen, so the top screen is asked."""
        return app.screen.query_one("#note-text").text

    @staticmethod
    def form_note(app):
        """The note of the answer form on top, or None (the form has none, or the top screen is not that form)."""
        screen = app.screen
        if type(screen).__name__ != "NoteScreen":
            return None
        found = list(screen.query("#note-note"))
        if not found:
            return None
        value = found[0].content
        return getattr(value, "plain", None) or str(value)

    def plan_identity(self):
        """The plan identity the chat snapshot names right now: the pair (revision, plan_state)."""
        snapshot = self.app.chat_snapshot()
        return (snapshot["revision"], snapshot["plan_state"])

    async def settled(self, pilot, timeout=5.0):
        """The chat is ready and the retained history has reached `app.answer_draft_to_open`."""
        await self.loaded(pilot)
        await self.chat_ready(pilot)
        await self.until(pilot, lambda: self.app.answer_draft_to_open() is not None, timeout)

    async def focus_panel(self, pilot):
        """The plan pane's focus: the existing Tab cycle from the chat input; the draft keys' own guard."""
        for _ in range(3):
            if tui_module().draft_keys_ready(self.app):
                return
            await pilot.press("tab")
        self.assertTrue(tui_module().draft_keys_ready(self.app))

    async def open_draft(self, pilot):
        """[t] from the plan pane, waiting for the answer form it opens."""
        await self.settled(pilot)
        await self.focus_panel(pilot)
        await self.command(pilot, "/answer")
        await self.until(pilot, lambda: type(self.app.screen).__name__ == "NoteScreen")

    async def capture_session(self, pilot):
        """The worker's own session object (its Authority lock is held by the app): mutations run on it directly."""
        captured = {}
        await self.post_and_wait(pilot, lambda app: captured.update(app=app))
        return captured["app"]

    def parked_identity(self):
        """A `controller.token_identity` that parks the worker right before the draft's provenance re-check.

        Returns (gated, held, release): `held` is set when the worker reached the synchronisation point — after the
        identity was read, before `resolve(exact=True)` — and the test sets `release` only after it changed the
        state on the app's own session."""
        real = controller_module.token_identity
        held, release = threading.Event(), threading.Event()

        def gated(identity):
            held.set()
            if not release.wait(10.0):
                raise AssertionError("the provenance re-check was never released")
            return real(identity)
        return gated, held, release

    @staticmethod
    def refused(app, reason):
        """The pane's note is a draft refusal naming `reason` and the `draft.stale` family."""
        note = app.run_note
        return chat_module.OUTDATED in note and reason in note and "draft.stale" in note

    # Mutations, on the app's own session, while the worker is parked before `resolve` -------------

    @staticmethod
    def start_new_attempt(session):
        """A second attempt of M1: the draft's attempt moved on («another attempt started»)."""
        session.controller.retry(session.delivery.latest("M1"), "", ROLES)

    @staticmethod
    def new_revision(session):
        """A new plan revision (which no longer names the draft's milestone): «plan revised»."""
        session.authority.begin("Requested feature, revised", ROLES, "fixture")

    @staticmethod
    def finish_attempt(session):
        """Drive the running attempt of M1 to its scripted end: the milestone finishes («attempt progressed»)."""
        session.controller.observe(session.delivery.latest("M1"))

    @staticmethod
    def advance_outcome(session, outcome="blocked"):
        """The same attempt's outcome moved on («attempt progressed»).

        Written through the session's own Authority so the store stays one the app accepts: only the outcome and the
        matching `output.signal` change, the attempt, run id and delivery stay."""
        record = session.delivery.latest("M1")
        record["outcome"] = record["output"]["signal"] = outcome
        record["output"]["question"] = record["output"]["proposal"] = None
        session.authority.save()

    @staticmethod
    def finish_as_done(session):
        """The answerable attempt reaches its end without an answer: outcome, status and delivery move to done.

        The milestone finished («attempt progressed»). The manifest is completed the way the driver would (an
        accepted progress record per task), so the store stays one the app's own validation accepts."""
        record = session.delivery.latest("M1")
        manifest = record["manifest"]
        for task in manifest["tasks"]:
            if task["status"] != "done":
                manifest["progress"].append({"seq": len(manifest["progress"]) + 1, "task": task["id"],
                                             "phase": "accepted", "text": "Fixture: accepted."})
                task["status"] = "done"
        record["outcome"] = record["output"]["signal"] = "done"
        record["output"]["question"] = record["output"]["proposal"] = None
        session.authority.save()

    # The two D-4 halves, shared by every stale case --------------------------------

    async def stale_open(self, seed, mutate, reason):
        """D-4's open half: the key is pressed, the worker is parked before `resolve(exact=True)`, `mutate` moves
        the state on the app's own session, and the released open then shows the stale refusal in the pane.

        Nothing opens, the store keeps exactly the test's own change (byte comparison) and the refusal writes it no
        further."""
        seed()
        path = RealAuthority(self.state, self.project, fixture_id="test").path
        gated, held, release = self.parked_identity()
        async with self.shell(size=(120, 40)) as pilot:
            session = await self.capture_session(pilot)
            await self.settled(pilot)
            await self.focus_panel(pilot)
            with patch.object(controller_module, "token_identity", gated):
                await self.command(pilot, "/answer")
                await self.until(pilot, held.is_set)
                mutate(session)
                changed = path.read_bytes()
                runs = len(json.loads(changed)["runs"])
                release.set()
                await self.until(pilot, lambda: self.refused(self.app, reason))
                self.assertEqual(type(self.app.screen).__name__, "MainScreen")   # nothing opened
            self.assertEqual(path.read_bytes(), changed)
        self.assertEqual(len(self.stored()["runs"]), runs)

    async def stale_send(self, seed, mutate, reason):
        """D-4's send half: the form is opened while the draft is still the attempt's, the send's worker is parked
        before `resolve(exact=True)`, `mutate` moves the state on, and the released send refuses in the form.

        The draft's text stays copyable, nothing is sent, no export, finish or Authority write runs during the
        refusal (D-6a), and the store keeps exactly the test's own change."""
        seed()
        path = RealAuthority(self.state, self.project, fixture_id="test").path
        async with self.shell(size=(120, 40)) as pilot:
            session = await self.capture_session(pilot)
            await self.open_draft(pilot)
            self.assertEqual(self.answer_text(self.app), self.DRAFT)
            gated, held, release = self.parked_identity()
            with patch.object(controller_module, "token_identity", gated), \
                    patch("terminal_planner.export.create_branch") as exported, \
                    patch("terminal_planner.runs.MilestoneRuns.finish") as finished:
                await self.press_button(pilot, "send")
                await self.until(pilot, held.is_set)
                mutate(session)
                changed = path.read_bytes()
                runs = len(json.loads(changed)["runs"])
                with patch("terminal_planner.authority.Authority.save", autospec=True) as saved:
                    release.set()
                    await self.until(pilot, lambda: chat_module.OUTDATED in (self.form_note(self.app) or ""))
                    saved.assert_not_called()
                self.assertIn(reason, self.form_note(self.app))
                self.assertIn(self.DRAFT, self.answer_text(self.app))    # the text stays copyable
                exported.assert_not_called()
                finished.assert_not_called()
            self.assertEqual(path.read_bytes(), changed)                 # the refusal wrote nothing
        self.assertEqual(len(self.stored()["runs"]), runs)               # only the test's own attempt

    # D-3 -------------------------------------------------------------------------

    async def test_d3_an_answer_draft_opens_prefilled_and_sends_with_the_original_token(self):
        """[t] on a milestone that needs an answer opens the existing form prefilled from the draft and editable;
        Ctrl+G sends it through the existing answer path with the draft's own attempt (a spy on `Delivery.answer`
        sees attempt 1, never a fresh token), so attempt 2 carries the same answer context a typed answer writes."""
        identity = self.seed_attempt("needs_owner")
        self.seed_answer_draft(identity)
        real = Delivery.answer
        seen = {}

        def spy(inner, record, text):
            seen["attempt"], seen["text"] = record["attempt"], text
            return real(inner, record, text)

        async with self.shell(size=(120, 40)) as pilot:
            with patch.object(Delivery, "answer", spy):
                await self.open_draft(pilot)
                self.assertEqual(self.answer_text(self.app), self.DRAFT)      # prefilled from the draft
                await self.type(pilot, " edit")                               # ... and editable
                self.assertIn(self.DRAFT, self.answer_text(self.app))
                sent = self.answer_text(self.app).strip()
                await self.press_button(pilot, "send")
                await self.until(pilot, lambda: any("new attempt started" in line
                                                    for line in self.app.run_lines))
        self.assertEqual(seen["attempt"], 1)                                  # the draft's original token
        self.assertEqual(seen["text"], sent)
        runs = self.stored()["runs"]
        self.assertEqual((runs[1]["attempt"], runs[1]["milestone"], runs[1]["plan_revision"]), (2, "M1", 1))
        self.assertEqual((runs[1]["context"]["kind"], runs[1]["context"]["source"]), ("answer", 1))
        self.assertEqual(runs[1]["context"]["text"], sent)                    # the typed answer's own records

    # D-3b ------------------------------------------------------------------------

    async def test_d3b_the_answer_letter_is_text_in_every_editor_and_the_command_opens_the_form(self):
        """K1a: `t` is no key any more — it is text in the chat input and the answer form, and
        does nothing under another modal; `/answer` (typed in the chat) opens the answer form of the selected
        milestone's newest draft."""
        identity = self.seed_attempt("needs_owner")
        self.seed_drafts([{"kind": "goal", "text": self.GOAL, "milestone": None, "identity": self.GOAL_IDENTITY},
                          {"kind": "answer", "text": self.DRAFT, "milestone": "M1", "identity": identity}])
        async with self.shell(size=(120, 40)) as pilot:
            await self.settled(pilot)
            await self.focus_panel(pilot)
            self.assertTrue(tui_module().draft_keys_ready(self.app))          # the plan pane, no modal on top
            await pilot.press("t")                                            # the pane binds no `t`
            self.assertEqual(type(self.app.screen).__name__, "MainScreen")
            field = self.query("#input")
            field.focus()
            await pilot.pause()
            self.assertFalse(tui_module().draft_keys_ready(self.app))         # the input line is not the guard
            await pilot.press("t")
            self.assertEqual(field.value, "t")                                # text, no draft opens
            field.value = ""
            await self.focus_panel(pilot)
            await self.command(pilot, "/answer")                              # the answer form, from the command
            await self.until(pilot, lambda: type(self.app.screen).__name__ == "NoteScreen")
            self.assertFalse(tui_module().draft_keys_ready(self.app))
            await pilot.press("t")
            self.assertIn("t", self.answer_text(self.app))                    # text in the answer form
            await pilot.press("escape")
            await self.until(pilot, lambda: type(self.app.screen).__name__ == "MainScreen")
            self.app.push_screen(tui_module().ConfirmScreen("Replace the goal?"))
            await pilot.pause()
            await pilot.press("t")                                            # any other modal: inert
            self.assertEqual(type(self.app.screen).__name__, "ConfirmScreen")
            await self.press_button(pilot, "no")
            await self.until(pilot, lambda: type(self.app.screen).__name__ == "MainScreen")

    async def test_d3b_a_draft_for_another_milestone_offers_no_key_and_does_nothing(self):
        """[t] answers the milestone the plan pane selects: an answer draft naming another milestone is no choice
        while M1 is selected — the milestone id alone decides it — so the key bar names no [t] and `t` opens
        nothing."""
        self.seed_answer_draft(self.seed_attempt("needs_owner"), milestone="M2")
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            await self.until(pilot, lambda: self.app.selection() is not None)
            self.assertEqual(self.app.selection().id, "M1")
            self.assertIsNone(self.app.answer_draft_to_open())
            await self.focus_panel(pilot)
            await self.command(pilot, "/answer")
            await pilot.pause()
            self.assertEqual(type(self.app.screen).__name__, "MainScreen")

    async def test_d3b_the_newest_answer_draft_of_the_selected_milestone_wins(self):
        """Two answer drafts for M1 in one reply: several drafts of a reply count, and the newest of the reply's
        own order is what [t] opens."""
        identity = self.seed_attempt("needs_owner")
        self.seed_drafts([{"kind": "answer", "text": "старый", "milestone": "M1", "identity": identity},
                          {"kind": "answer", "text": "новый", "milestone": "M1", "identity": identity}])
        async with self.shell(size=(120, 40)) as pilot:
            await self.open_draft(pilot)
            self.assertEqual(self.answer_text(self.app), "новый")

    async def test_d3b_a_malformed_identity_is_refused_at_open_and_writes_nothing(self):
        """Opening refuses an identity that rebuilds no token — a mapping missing fields, or not a mapping — and
        writes nothing; the plain-data rebuild rejects each shape on its own too."""
        self.assertIsNone(controller_module.token_identity("не идентичность"))
        self.assertIsNone(controller_module.token_identity({"milestone": "M1"}))
        self.assertIsNone(controller_module.token_identity(
            {"milestone": "M1", "plan_revision": True, "attempt": 1, "run_id": None, "status": "running",
             "outcome": None, "delivery": "none"}))
        identity = self.seed_attempt("needs_owner")
        self.seed_answer_draft(identity, text="годный")
        self.seed_answer_draft({"milestone": "M1"}, text="битый")             # the newest: no token to rebuild
        path = RealAuthority(self.state, self.project, fixture_id="test").path
        before = path.read_bytes()
        async with self.shell(size=(120, 40)) as pilot:
            await self.settled(pilot)
            await self.focus_panel(pilot)
            await self.command(pilot, "/answer")
            await self.until(pilot, lambda: "not opened" in self.app.run_note)
            self.assertEqual(type(self.app.screen).__name__, "MainScreen")    # nothing opened
            self.assertIn(controller_module.ANSWER_DRAFT_MALFORMED, self.app.run_note)
            self.assertIn("draft.malformed", self.app.run_note)        # its own catalog family, not the generic one
            await pilot.pause()
            self.assertEqual(path.read_bytes(), before)                       # refused at open wrote nothing

    async def test_d3b_a_draft_and_its_token_must_name_the_same_milestone(self):
        """F-1: the draft's own milestone and the milestone of the token it carries are checked against each other
        on the worker, before `resolve`, so a retained draft that names M1 while its identity is a well-formed,
        resolving token of M2 neither opens nor answers M2 while M1 is selected.

        Class: the milestone `chat.newest_answer_draft` selected the draft by and the milestone the stored identity
        names are one piece of provenance; a draft where they disagree is refused as `draft.malformed` — the same
        refusal as any identity that cannot be rebuilt — with no `resolve`, no view, no answer, no write and no
        export. Domain checked: an M1 draft whose identity is M2's real, resolving token (of the same plan, the same
        revision), at open ([t] with M1 selected) and at send (the form's send callback driven directly with the
        draft), with the store bytes and the `export.create_branch`/`MilestoneRuns.finish`/`Authority.save` spies
        compared around both.

        Interpretations recorded for the reviewers:

        - The plan's M2 waits for M1, so no M2 attempt can be started through the plan's own gate; the fixture
          stubs only `MilestoneRuns.waiting` (`seed_other_milestone_attempt`) to store a genuine M2 attempt — the
          same shape the plan would store for M2 once M1 is merged — so "a well-formed token of M2" is the token of
          an attempt that really resolves, not a hand-made dict.
        - The send half drives `app.send_answer_draft` (the callback the answer form is built with) directly with
          the draft, because a draft whose open is refused never has a form; the screen's own `end` is only read for
          its milestone there, so a stand-in carrying the draft's milestone is passed.
        - R-3: the `draft.malformed` wording and catalog text still match — a record whose draft milestone and
          identity milestone disagree is exactly a "chat record written by another version, or a hand-edited or
          truncated draft identity" — so no catalog entry, reference line or wording changed."""
        self.seed_attempt("needs_owner")                  # M1's answerable attempt: the milestone the pane selects
        m2 = self.seed_other_milestone_attempt("M2")      # a genuine M2 attempt of the same plan, its token resolves
        self.seed_answer_draft(m2, milestone="M1")        # the retained draft names M1; its identity is M2's token
        path = RealAuthority(self.state, self.project, fixture_id="test").path
        before, runs = path.read_bytes(), len(self.stored()["runs"])
        async with self.shell(size=(120, 40)) as pilot:
            await self.settled(pilot)
            self.assertEqual(self.app.selection().id, "M1")
            await self.focus_panel(pilot)
            with patch("terminal_planner.export.create_branch") as exported, \
                    patch("terminal_planner.runs.MilestoneRuns.finish") as finished, \
                    patch("terminal_planner.authority.Authority.save", autospec=True) as saved:
                await self.command(pilot, "/answer")
                await self.until(pilot, lambda: "not opened" in self.app.run_note
                                 or type(self.app.screen).__name__ != "MainScreen")
                self.assertEqual(type(self.app.screen).__name__, "MainScreen")   # M2 opens no more than M1
                self.assertIn(controller_module.ANSWER_DRAFT_MALFORMED, self.app.run_note)
                self.assertIn("draft.malformed", self.app.run_note)
                await pilot.pause()
                self.assertEqual(path.read_bytes(), before)                      # the refusal wrote nothing
                exported.assert_not_called()
                finished.assert_not_called()
                saved.assert_not_called()

                draft = self.app.answer_draft_to_open()                          # the form's own send callback, driven
                self.assertIsNotNone(draft)
                end = collections.namedtuple("End", ["milestone"])(draft.milestone)
                self.app.send_answer_draft(draft, end, "ответ")
                await self.until(pilot, lambda: self.form_note(self.app) is not None or bool(self.app.run_lines))
                self.assertIn(controller_module.ANSWER_DRAFT_MALFORMED, self.form_note(self.app) or "")
                self.assertIn("draft.malformed", self.form_note(self.app) or "")
                exported.assert_not_called()
                finished.assert_not_called()
                saved.assert_not_called()
            self.assertEqual(path.read_bytes(), before)
        self.assertEqual(len(self.stored()["runs"]), runs)                        # no attempt was created
        self.assertIsNotNone(controller_module.token_identity(m2))                # the M2 token itself is well formed
        self.assertIsNone(controller_module.draft_token(m2, "M1"))                # ... it is just not an M1 token

    async def test_d3b_an_active_attempt_is_refused_at_open_and_writes_nothing(self):
        """A draft of an attempt that still runs is refused at open (there is no end view to answer yet), and
        nothing is written."""
        self.seed_answer_draft(self.seed_running())
        path = RealAuthority(self.state, self.project, fixture_id="test").path
        before = path.read_bytes()
        async with self.shell(size=(120, 40)) as pilot:
            await self.settled(pilot)
            await self.focus_panel(pilot)
            await self.command(pilot, "/answer")
            await self.until(pilot, lambda: "not opened" in self.app.run_note)
            self.assertEqual(type(self.app.screen).__name__, "MainScreen")
            self.assertIn(controller_module.ANSWER_DRAFT_ACTIVE % "M1", self.app.run_note)
            self.assertIn("draft.active", self.app.run_note)
            await pilot.pause()
            self.assertEqual(path.read_bytes(), before)

    async def test_d3b_a_running_drafts_attempt_finishing_turns_a_later_open_into_a_stale_refusal(self):
        """A draft of a still-running attempt is refused at open (`draft.active`); once that same attempt finishes,
        the same key is refused as stale — never opened.

        Class: the catalog's answer-draft refusal reasons must match the lifecycle, so the `draft.active` remedy
        may not promise that [t] opens such a draft again. Domain checked: one draft identity followed across
        running -> finished, at open, with the store bytes compared after each press. Interpretation (P3): a
        still-running attempt gives `draft.active` and the *same* attempt after it ends gives `draft.stale`
        («attempt progressed»), so the fresh-draft path is the chat (a new architect reply) — a finished
        milestone is answered from its own end screen, not from the draft."""
        self.seed_answer_draft(self.seed_running())
        path = RealAuthority(self.state, self.project, fixture_id="test").path
        before = path.read_bytes()
        async with self.shell(size=(120, 40)) as pilot:
            session = await self.capture_session(pilot)
            await self.settled(pilot)
            await self.focus_panel(pilot)
            await self.command(pilot, "/answer")
            await self.until(pilot, lambda: "not opened" in self.app.run_note)
            self.assertEqual(type(self.app.screen).__name__, "MainScreen")
            self.assertIn("draft.active", self.app.run_note)          # still running: no end to answer yet
            self.assertEqual(path.read_bytes(), before)
            self.finish_attempt(session)                                      # the same attempt reaches its end
            finished = path.read_bytes()
            await self.focus_panel(pilot)
            await self.command(pilot, "/answer")
            await self.until(pilot, lambda: self.refused(self.app, "attempt progressed"))
            self.assertEqual(type(self.app.screen).__name__, "MainScreen")    # never opened
            self.assertEqual(path.read_bytes(), finished)                     # the refusal wrote nothing
        self.assertEqual(path.read_bytes(), finished)

    # D-4 -------------------------------------------------------------------------

    async def test_d4_open_refuses_a_new_attempt_started_while_parked(self):
        """A new attempt barely started while the worker is parked before `resolve` refuses the open with
        «draft is outdated: another attempt started», opening nothing and writing nothing further."""
        await self.stale_open(lambda: self.seed_answer_draft(self.seed_attempt("needs_owner")),
                              self.start_new_attempt, "another attempt started")

    async def test_d4_send_refuses_a_new_attempt_started_while_parked(self):
        """The send half of the same case: the form was opened while the draft still matched the attempt, and the
        attempt moving on during the parked send refuses it — nothing is sent, the text stays copyable."""
        await self.stale_send(lambda: self.seed_answer_draft(self.seed_attempt("needs_owner")),
                              self.start_new_attempt, "another attempt started")

    async def test_d4_open_refuses_a_new_revision_while_parked(self):
        """A revision that no longer names the draft's milestone (a new revision is the same mismatch) refuses the
        open with «draft is outdated: plan revised»."""
        await self.stale_open(lambda: self.seed_answer_draft(self.seed_attempt("needs_owner")),
                              self.new_revision, "plan revised")

    async def test_d4_send_refuses_a_new_revision_while_parked(self):
        """The send half of the revision case: the plan moved to another revision during the parked send."""
        await self.stale_send(lambda: self.seed_answer_draft(self.seed_attempt("needs_owner")),
                              self.new_revision, "plan revised")

    async def test_d4_open_refuses_a_milestone_that_finished_while_parked(self):
        """A draft written for a still-running attempt: the attempt finishes while the worker is parked before
        `resolve`, so the open refuses with «draft is outdated: attempt progressed»."""
        await self.stale_open(lambda: self.seed_answer_draft(self.seed_running()),
                              self.finish_attempt, "attempt progressed")

    async def test_d4_send_refuses_a_milestone_that_finished_while_parked(self):
        """The milestone finished while the form was open and the send's worker parked before `resolve`: the
        answerable attempt's outcome/delivery moved to done, so the send refuses with «draft is outdated: attempt
        progressed» and nothing is sent."""
        await self.stale_send(lambda: self.seed_answer_draft(self.seed_attempt("needs_owner")),
                              self.finish_as_done, "attempt progressed")

    async def test_d4_open_refuses_a_changed_outcome_of_the_same_attempt(self):
        """A status/outcome change of the very same attempt (no new attempt, the same run id) refuses the open with
        «draft is outdated: attempt progressed»."""
        await self.stale_open(lambda: self.seed_answer_draft(self.seed_attempt("needs_owner")),
                              self.advance_outcome, "attempt progressed")

    async def test_d4_send_refuses_a_changed_outcome_of_the_same_attempt(self):
        """The send half of the changed-outcome case: the same attempt's outcome moved on during the parked
        send."""
        await self.stale_send(lambda: self.seed_answer_draft(self.seed_attempt("needs_owner")),
                              self.advance_outcome, "attempt progressed")

    # D-6a ------------------------------------------------------------------------

    async def test_d6a_opening_a_finished_unexported_attempt_exports_nothing_and_writes_nothing(self):
        """A draft of a finished (done, not yet exported) attempt: the open refuses it as the declared
        `draft.unavailable` — the attempt's own state names an end that offers no answer, so the read-only `view`
        is never even built and nothing export-dependent is assembled — and no `Delivery.end`, no export, no run
        finish and no Authority write runs; the store keeps exactly the seed's bytes.

        Interpretation: the refusal is decided from the state alone (the same `END_ACTIONS` table `Delivery.view`
        builds its menu from), so the "The result is not exported yet." refusal of `Delivery.view` -> `runs.diff` is
        never the answer an answer draft gets; `Delivery.view` itself is spied on to pin that an end without an
        answer never reaches it, and the family and wording stay the declared `draft.unavailable` contract
        (`terminal_planner/catalog.py`, the `draft.unavailable` row of `docs/REFERENCE.md`)."""
        self.seed_answer_draft(self.seed_attempt("done"))
        path = RealAuthority(self.state, self.project, fixture_id="test").path
        before = path.read_bytes()
        async with self.shell(size=(120, 40)) as pilot:
            with patch("terminal_planner.export.create_branch") as exported, \
                    patch("terminal_planner.runs.MilestoneRuns.finish") as finished, \
                    patch("terminal_planner.delivery.Delivery.view") as viewed, \
                    patch("terminal_planner.authority.Authority.save", autospec=True) as saved:
                await self.settled(pilot)
                await self.focus_panel(pilot)
                await self.command(pilot, "/answer")
                await self.until(pilot, lambda: "not opened" in self.app.run_note)
                self.assertEqual(type(self.app.screen).__name__, "MainScreen")     # nothing opened
                self.assertIn(controller_module.ANSWER_DRAFT_UNAVAILABLE % "M1", self.app.run_note)
                self.assertIn("draft.unavailable", self.app.run_note)
                viewed.assert_not_called()                                        # no view for an end without an answer
                exported.assert_not_called()
                finished.assert_not_called()
                saved.assert_not_called()
            self.assertEqual(path.read_bytes(), before)                       # the open wrote nothing
        self.assertEqual(path.read_bytes(), before)

    async def test_d3b_an_end_without_an_answer_is_refused_at_open_and_writes_nothing(self):
        """A finished, exported attempt (awaiting a merge): the open builds the read-only view, which offers
        `merge` and `diff` but no `answer`, and refuses — without exporting anything again or writing."""
        self.seed_answer_draft(self.seed_exported_done())
        path = RealAuthority(self.state, self.project, fixture_id="test").path
        before = path.read_bytes()
        async with self.shell(size=(120, 40)) as pilot:
            with patch("terminal_planner.export.create_branch") as exported, \
                    patch("terminal_planner.runs.MilestoneRuns.finish") as finished:
                await self.settled(pilot)
                await self.focus_panel(pilot)
                await self.command(pilot, "/answer")
                await self.until(pilot, lambda: "not opened" in self.app.run_note)
                self.assertEqual(type(self.app.screen).__name__, "MainScreen")
                self.assertIn(controller_module.ANSWER_DRAFT_UNAVAILABLE % "M1", self.app.run_note)
                self.assertIn("draft.unavailable", self.app.run_note)
                exported.assert_not_called()
                finished.assert_not_called()
            self.assertEqual(path.read_bytes(), before)
        self.assertEqual(path.read_bytes(), before)

    # D-9 -------------------------------------------------------------------------

    async def test_d9_both_drafts_of_one_reply_survive_a_restart_and_the_answer_is_sent(self):
        """D-9: one scripted reply with a goal draft and an answer draft -> an app restart -> both drafts stay
        actionable with their original identity -> the answer is sent as in D-3 (a new attempt, the plan identity
        unchanged) and `c` then opens the original goal draft. The plan identity is asserted before and after the
        send, never the milestone status."""
        identity = self.seed_attempt("needs_owner")
        reply = "Вот черновики.\n" + goal_block(self.GOAL) + "\n" + answer_block("M1", self.DRAFT)
        self.fixture.script([{"lines": says(reply)}])
        async with self.shell(size=(120, 40)) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            sent = self.app.chat_snapshot()
            await self.say(pilot, "вопрос")
            await self.chat_done(pilot)
        row = self.fixture.store().transcript()[-1]
        self.assertEqual(row["status"], "completed")
        self.assertEqual([d["kind"] for d in row["drafts"]], ["goal", "answer"])
        self.assertEqual(row["drafts"][0]["identity"], [1, sent["plan_state"]])
        self.assertEqual(row["drafts"][1]["identity"], identity)

        async with self.shell(size=(120, 40)) as pilot:                       # an app restart
            await self.loaded(pilot)
            await self.until(pilot, lambda: self.app.chat is not None and any(e.drafts
                                                                             for e in self.app.chat.state.entries))
            entry = [e for e in self.app.chat.state.entries if e.role == "architect"][-1]
            self.assertEqual([(d.kind, d.milestone, d.actionable) for d in entry.drafts],
                             [("goal", "", True), ("answer", "M1", True)])
            self.assertEqual(entry.drafts[0].identity, [1, sent["plan_state"]])
            self.assertEqual(entry.drafts[1].identity, identity)
            before = self.plan_identity()
            await self.open_draft(pilot)
            self.assertEqual(self.answer_text(self.app), self.DRAFT)          # prefilled from the draft
            await self.press_button(pilot, "send")
            await self.until(pilot, lambda: any("new attempt started" in line for line in self.app.run_lines))
            self.assertEqual(self.plan_identity(), before)                    # the plan identity is unchanged
        runs = self.stored()["runs"]
        self.assertEqual([(r["attempt"], (r["context"] or {}).get("kind")) for r in runs], [(1, None), (2, "answer")])


    # Repair (rejected acceptance review): the owner's edits survive every refusal --------------------

    EDIT = "Правленый ответ владельца"

    async def edit_answer(self, pilot, text):
        """`text` becomes the form's content the way its send reads it: the answer modal keeps the answer in its own
        TextArea and the send button sends that widget's value, so writing it is exactly what typing leaves behind here."""
        self.app.screen.query_one("#note-text").text = text
        await pilot.pause()
        self.assertEqual(self.answer_text(self.app), text)

    async def test_a_stale_send_keeps_the_edited_answer_not_the_draft_prefill(self):
        """The rejected candidate's defect as a class: every reopen of the draft's answer form must carry the text
        the owner sent in that very call — the field is the owner's, only the identity is the draft's — and no
        refusal path may fall back to `draft.text`.

        Domain checked here: the stale refusal on the worker (`draft.stale`, a new attempt started while the parked
        send held the edited text) and the empty send. An empty field keeps the owner's own (empty) text too,
        mirroring the goal form, which shows what the owner has and never re-prefills the draft. Interpretation:
        the requirement is read as "the form shows the owner's current text, the identity stays the draft's", so
        the previous prefill-on-refusal (and the prefill after an empty send) was the defect, not a feature. The
        oracle is the literal below, written by the test and read back from the form, never the production opener
        that pushed it."""
        identity = self.seed_attempt("needs_owner")
        self.seed_answer_draft(identity)
        path = RealAuthority(self.state, self.project, fixture_id="test").path
        async with self.shell(size=(120, 40)) as pilot:
            session = await self.capture_session(pilot)
            await self.open_draft(pilot)
            self.assertEqual(self.answer_text(self.app), self.DRAFT)          # the draft's own prefill, once
            await self.edit_answer(pilot, self.EDIT)
            gated, held, release = self.parked_identity()
            with patch.object(controller_module, "token_identity", gated), \
                    patch("terminal_planner.export.create_branch") as exported, \
                    patch("terminal_planner.runs.MilestoneRuns.finish") as finished:
                await self.press_button(pilot, "send")
                await self.until(pilot, held.is_set)                          # past the edit, before `resolve`
                self.start_new_attempt(session)
                changed = path.read_bytes()
                release.set()
                await self.until(pilot, lambda: chat_module.OUTDATED in (self.form_note(self.app) or ""))
                self.assertEqual(self.answer_text(self.app), self.EDIT)       # the edit, not the prefill
                self.assertNotIn(self.DRAFT, self.form_note(self.app))        # the note is the refusal alone
                exported.assert_not_called()
                finished.assert_not_called()
            self.assertEqual(path.read_bytes(), changed)                      # the refusal wrote nothing

            await self.edit_answer(pilot, "")                                 # an empty field keeps the owner's text
            await self.press_button(pilot, "send")
            await self.until(pilot, lambda: "Empty answer" in (self.form_note(self.app) or ""))
            self.assertEqual(self.answer_text(self.app), "")
            self.assertEqual(self.form_note(self.app), "Empty answer: no new attempt was started.")
        self.assertEqual(len(self.stored()["runs"]), 2)                       # the test's own attempt only

    async def test_a_readiness_refusal_keeps_the_edited_answer(self):
        """The same class on the other refusal path the code review named: the readiness gate (`blocked`) after an
        edit reopens the form with the edited text and only the marked checks added. The oracle is again the
        literal the test wrote into the field (`edit_answer`), read back from the form."""
        identity = self.seed_attempt("needs_owner")
        self.seed_answer_draft(identity)
        readiness = Readiness(check("git"), check("branch", False, DIRTY, key="d"))
        async with self.shell(self.controller(readiness), size=(120, 40)) as pilot:
            await self.open_draft(pilot)
            await self.edit_answer(pilot, self.EDIT)
            await self.press_button(pilot, "send")
            await self.until(pilot, lambda: "Not started" in (self.form_note(self.app) or ""))
            self.assertEqual(self.answer_text(self.app), self.EDIT)
            self.assertNotIn(self.DRAFT, self.form_note(self.app))

@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class EntrypointBudgetTests(unittest.TestCase):
    """The outer `tui.run` cleanup shares the app's exit budget: the whole way out stays inside the 5 s the
    UI promises, even when a non-mutating controller read never returns."""

    def test_c5_the_entrypoint_cleanup_shares_the_exit_budget(self):
        from terminal_planner import tui
        from terminal_planner.tui import app as tui_app

        class Controller:
            project = None

            def __init__(self):
                self.calls = []

            def stop(self, timeout=None):
                self.calls.append(timeout)

        controller = Controller()
        spent = {"deadline": None}

        def spent_run(self):
            self.quit_deadline = time.monotonic()  # the app already used the whole budget on its way out

        with patch.object(tui, "Controller") as factory, patch.object(tui_module().ZplanApp, "run", spent_run):
            factory.for_project.return_value = controller
            self.assertEqual(tui.run("proj", "state"), 0)
        self.assertEqual(len(controller.calls), 1)
        self.assertIsNotNone(controller.calls[0])          # not the default full wait
        self.assertLessEqual(controller.calls[0], 0.5)     # only what is left of the budget
        with patch.object(tui, "Controller") as factory, patch.object(tui_module().ZplanApp, "run", lambda self: None):
            factory.for_project.return_value = controller
            self.assertEqual(tui.run("proj", "state"), 0)
        self.assertEqual(controller.calls[1], None)        # no quit key: the usual default applies


DONE = {"signal": "done", "message": "Milestone complete.", "question": None, "proposal": None}


@unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
class LifecycleGuardChatTests(ChatShell):
    """A-3 (TUI, rel04-lifecycle-guard): a chat goal handed over with Ctrl+G while M1 is active is refused by the
    R-1 guard, and the run still delivers through the existing actions.

    This pilot runs the *production* entry point, not a fixture session: `fixture_id=None`, a bound accepted profile
    (`profile=True` over a real `zplan.process.json`), the *production* readiness list (`setup.readiness`, the callable
    `cli` hands the TUI; asserted to pass in full), and the real controller/Planning wiring. The session is checked
    to be the production one — the store lives outside any `fixtures/` directory, the approved revision's engine is
    `"native"` and the bound profile reaches the UI (`Snapshot.profile is not None`), where an earlier version left
    `fixture_id="test"`, `engine="fixture"` and `profile=None`. Only the external dependencies are fakes: the
    scripted codex behind the architect chat (the provider), native engine/driver doubles standing in for the pinned
    `zeroshot` CLI (the plan review that approves r1, and the milestone run), and readiness' own external boundary —
    the pinned toolchain's installation receipt and binaries (faked exactly as `test_tui_polish` does), with
    `CODEX_HOME` a fixture login. The git/project/roles/identity checks run for real against this clean project.

    M1 is held active by explicit Event barriers: its native `watch` is gated, so the fake run cannot finish until
    the test releases it. The controller is following it (`follow=True`), so the slice is genuinely parked on the
    fake run while the goal draft is handed over — the run is provably still `submitted`/`running` then, and the
    refusal is R-1's, never a timing, readiness, stale-draft or profile failure (a clean project, an accepted,
    current profile and the matching draft identity make all of those pass). Releasing the gate delivers a running
    slice (M1 stays active through the refusal); releasing the run then lets its result export and merge.

    The lifecycle identity is read *before* Ctrl+G and the hand-over is awaited on the controller worker itself (a
    marker job queued behind it), so the assertions below never depend on elapsed time: on the base `Planning.begin`
    has no owner guard, so Ctrl+G creates revision r2 and the revision-identity assertion is the named failure
    (the base fails on that assertion, not on a wait timeout).

    Interpretations recorded here (the worker summary never reaches the reviewers): "each refused ACTIVE case that
    Planning.begin/renew reaches is a named failure on the base" holds for the goal-form hand-over, as above; the
    all-terminal/outcome action matrix lives in `test_lifecycle_guard`, not here. The readiness double is the
    toolchain boundary only — `Readiness(check("git"))`, an internal all-green stub that made the profile and the
    plan gate unexercised, is gone."""

    def setUp(self):
        super().setUp()
        self.worktrees = self.root / "worktrees"
        home = self.root / "codex-home"
        home.mkdir(exist_ok=True)  # the Fixture already made it; this only adds the login
        (home / "auth.json").write_text("{}\n")  # a fixture login: readiness judges presence, never validity
        patcher = patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.root / "config"),
                                          "XDG_DATA_HOME": str(self.root / "data"),
                                          "CODEX_HOME": str(home)})
        patcher.start()
        self.addCleanup(patcher.stop)
        # i6: this class isolates the config root, so the process-wide `ru` pin `tests/tui_support.py` sets does
        # not reach it. Store `ru` where the UI string catalog reads the language: a store keeps the first-run
        # language chooser from covering this production-wired shell, and keeps its main screen Russian.
        ui = self.root / "config" / "planning-kit" / "ui.json"
        ui.parent.mkdir(parents=True, exist_ok=True)
        ui.write_text('{"language": "ru"}\n', encoding="utf-8")
        self.tools = self.root / "tools"           # the pinned toolchain is an external boundary: faked whole
        self.tools.mkdir()
        for name in ("zeroshot", "codex"):
            binary = self.tools / name
            binary.write_text("#!/bin/sh\nexit 0\n")
            binary.chmod(0o700)
        for target, value in (("tool_paths", (self.tools / "zeroshot", self.tools / "codex")),
                              ("check_installation", self.tools)):
            tools_patcher = patch.object(setup, target, return_value=value)
            tools_patcher.start()
            self.addCleanup(tools_patcher.stop)
        self.native_root = short_root()            # short regardless of the process TMPDIR: readiness judges the socket path
        self.addCleanup(shutil.rmtree, str(self.native_root), ignore_errors=True)
        self.hold = threading.Event()     # the held slice parks on it until the hand-over is decided
        self.finish = threading.Event()   # the held native run may finish only after this is set
        self.entered = threading.Event()  # a live watch slice reached the gated fake run
        self.record = {}
        with (self.project / ".git" / "info" / "exclude").open("a", encoding="utf-8") as handle:
            handle.write("\n%s\n" % process.PROFILE_FILE)  # the accepted profile is kept out of the clean tree
        self.accept_profile()
        self.approve_native()
        self.driver = self.native_driver()
        self.start_active()

    # --- the bound accepted profile and the approved native plan -----------------

    def accept_profile(self):
        """A real accepted `zplan.process.json`, through a production session: the profile the pilot enforces."""
        with RealAuthority(None, self.project) as authority:
            process.Profile.of(authority).accept()

    def fake_engine(self, responses, watch=None):
        """A native engine double: `--version` is the qualified contract, `watch` a custom slice, the rest are the
        scripted JSON answers in order. Only an external dependency (the pinned `zeroshot` CLI) is faked."""
        version = toolchain.current().zeroshot_version
        binary = self.root / "zeroshot-fixture"
        binary.write_text("#!/bin/sh\nprintf '%s\\n'\n" % version)
        binary.chmod(0o700)

        def call(argv, **kwargs):
            if argv[1:] == ["--version"]:
                return subprocess.CompletedProcess(argv, 0, version + "\n", "")
            if watch is not None and argv[1] == "watch":
                return watch(argv, **kwargs)
            result = responses.pop(0)
            stdout = "".join(json.dumps(v) + "\n" for v in result) if isinstance(result, tuple) \
                else json.dumps(result) + "\n"
            return subprocess.CompletedProcess(argv, 0, stdout, "")

        return NativeEngine(binary, self.native_root, call=call, sleep=lambda _: None)

    def plan_projection(self, status, cursor="v2:10"):
        return {"runId": "fixture-native-run", "subscriptionId": "sub", "title": "Terminal roadmap revision 1",
                "source": {"repository": "example/fixture",
                           "branch": self.git("branch", "--show-current").decode().strip(),
                           "revision": self.git("rev-parse", "HEAD").decode().strip()},
                "size": "medium", "cursor": cursor, "status": status}

    def plan_terminal(self):
        output = {"schemaVersion": "1", "proposal": canonical(fixture_proposal()), "planVerdict": "accepted",
                  "planFindings": "Final"}
        output.update(schemaVersion="2", planResponse="ok",
                      discussion=canonical({"version": 1, "rounds": [{"round": 1, "verdict": "accepted",
                                                                      "findings": "Final", "response": "ok"}]}))
        return self.plan_projection({"phase": "finished",
                                     "terminalResult": {"status": "succeeded", "output": output}})

    def approve_native(self):
        """One approved native revision (M1 delivered later; M2 depends on it), from the fake planner engine."""
        engine = self.fake_engine([{"valid": True}, {"runId": "fixture-native-run"},
                                   (self.plan_projection({"phase": "running", "activeExecutions": []}),
                                    self.plan_terminal())])
        with RealAuthority(None, self.project) as authority:
            authority.begin("Requested feature", ROLES, "native")
            engine.proposal(authority, lambda _: None)
            authority.approve(1)

    # --- the Event-held native run ----------------------------------------------

    def envelope(self, record, status, cursor="v2:5"):
        return {"runId": record["run_id"], "title": runs_module.title(record), "size": "medium",
                "source": {"repository": "example/fixture", "branch": record["branch"],
                           "revision": record["destination"]["base"]},
                "subscriptionId": "sub", "cursor": cursor, "status": status}

    def projection(self, record, phase, cursor):
        status = ({"phase": phase, "activeExecutions": []} if phase == "running"
                  else {"phase": phase, "terminalResult": {"status": "succeeded", "output": DONE}})
        return self.envelope(record, status, cursor)

    def complete(self, record):
        """What the finished native run leaves in its worktree: every task accepted, plus one change to export."""
        path = Path(record["worktree"]) / milestone.MANIFEST
        manifest = decode(path.read_text())
        for task in manifest["tasks"]:
            task["status"] = "done"
            manifest["progress"].append({"seq": len(manifest["progress"]) + 1, "task": task["id"],
                                         "phase": "accepted", "text": "ok"})
        atomic_state(path, manifest)
        (Path(record["worktree"]) / "PRODUCT.md").write_text("result\n")

    def native_driver(self):
        """A native driver whose `watch` is parked on `hold` and whose slice only returns the run's result after
        `finish`: the run cannot end until the test decides, and the refusal is decided while it is still active."""
        def watch(argv, **kwargs):
            self.entered.set()
            self.hold.wait(kwargs.get("timeout") or 5)
            if self.finish.is_set():
                self.complete(self.record["r"])
                value = self.projection(self.record["r"], "finished", "v2:9")
            else:
                value = self.projection(self.record["r"], "running", "v2:6")
            return subprocess.CompletedProcess(argv, 0, json.dumps(value) + "\n", "")

        def status(argv, **kwargs):
            phase, cursor = ("finished", "v2:9") if self.finish.is_set() else ("running", "v2:6")
            value = dict(self.projection(self.record["r"], phase, cursor))
            value["atCursor"] = value.pop("cursor")
            value.pop("subscriptionId", None)
            return subprocess.CompletedProcess(argv, 0, json.dumps(value) + "\n", "")

        engine = self.fake_engine([{"valid": True}, {"runId": "m-run"}])

        def call(argv, **kwargs):
            return watch(argv, **kwargs) if argv[1] == "watch" else (
                status(argv, **kwargs) if argv[1] == "status" else engine.call(argv, **kwargs))
        return NativeDriver(engine.executable, engine.state_root, call=call, sleep=lambda _: None)

    def start_active(self):
        """M1 submitted (a real ACTIVE writer): held, because its watch cannot finish before `finish` is set."""
        with RealAuthority(None, self.project) as authority:
            record = MilestoneRuns(authority, self.driver, worktrees=self.worktrees) \
                .start("M1", authority.current["version"], ROLES)
            self.record["r"] = record
            self.assertEqual(record["status"], "submitted")

    # --- the pilot -------------------------------------------------------------

    def readiness(self):
        """The production readiness list (`setup.readiness`, exactly the callable `cli` hands the TUI and the plain
        session): the real git/project/roles/identity checks of this clean project. Only the external boundaries are
        doubled, as the task allows for the provider and the native engine: the pinned toolchain's receipt/binaries
        (setUp) and `CODEX_HOME`."""
        return setup.readiness(self.project, self.native_root)

    def controller(self, readiness=None, **kw):
        from terminal_planner.tui.controller import Controller
        kw.setdefault("driver_factory", lambda _: self.driver)
        kw.setdefault("engine_factory", lambda *_: self.fake_engine([{"valid": True}]))
        kw.setdefault("worktrees", self.worktrees)
        controller = Controller.for_project(self.project, None, profile=True,
                                            readiness=readiness if readiness is not None else self.readiness,
                                            **kw)
        self.addCleanup(controller.stop)
        return controller

    def authority_path(self):
        with RealAuthority(None, self.project) as authority:
            return authority.path

    def seed_goal_draft(self, text="Сделать X", identity="no plan"):
        """One archived architect reply carrying one actionable goal draft (the draft card's source)."""
        store = self.fixture.store()
        store.append("owner", text="вопрос")
        store.append("architect", text="Вот черновик.", status="completed",
                     drafts=[{"kind": "goal", "text": text, "milestone": None, "identity": identity}])
        return store

    async def settled(self, pilot, timeout=5.0):
        await self.loaded(pilot)
        await self.chat_ready(pilot)
        await self.until(pilot, lambda: chat_module.newest_goal_draft(self.app.chat.state.entries) is not None,
                         timeout)

    async def focus_panel(self, pilot):
        for _ in range(3):
            if tui_module().draft_keys_ready(self.app):
                return
            await pilot.press("tab")
        self.assertTrue(tui_module().draft_keys_ready(self.app))

    async def open_draft(self, pilot):
        await self.settled(pilot)
        await self.until(pilot, lambda: self.app.screen.draft_card_open())

    @staticmethod
    def identities(state):
        return [(r["run_id"], r["milestone"], r["attempt"], r["plan_revision"], r["approval"])
                for r in state["runs"]]

    async def test_a3_a_chat_goal_handed_over_while_m1_is_active_is_refused_and_the_run_still_delivers(self):
        self.seed_goal_draft(text="Новая цель", identity=[1, {"status": "approved", "override": False}])
        path = self.authority_path()
        async with self.shell(self.controller(), size=(120, 40), follow=True) as pilot:
            await self.settled(pilot)
            self.assertIsNotNone(self.app.snapshot.profile)           # the accepted profile is bound and enforced
            self.assertNotIn("fixtures", path.parts)                   # the production store, not the fixture one
            self.assertEqual(json.loads(path.read_text())["revisions"][0]["engine"], "native")
            items = self.readiness()                                  # the session's readiness is production's ...
            self.assertEqual({i["id"] for i in items} & set(planning_module.NEEDS["plan"]),
                             set(planning_module.NEEDS["plan"]), [i["id"] for i in items])
            self.assertTrue(all(i["ok"] for i in items), [i for i in items if not i["ok"]])  # ... and it passes in full
            before = json.loads(path.read_text())                     # the identity to preserve, read *before* the hand-over
            identities = self.identities(before)
            self.assertIn(before["runs"][0]["status"], runs_module.ACTIVE)  # M1 is provably a live writer here
            await self.open_draft(pilot)                              # the draft card is open
            self.app.screen.run_command("/plan")                      # ... and its goal is handed over (the card's
            await pilot.pause()                                       # button path: a running M1 keeps state `running`)
            await self.until(pilot, self.entered.is_set)              # a live slice parked on the held native run
            self.assertFalse(self.finish.is_set())                    # ... and cannot have finished
            self.hold.set()                                           # the held slice returns a running projection
            await self.post_and_wait(pilot, lambda app: None)         # the hand-over action is provably finished
            await self.until(pilot, lambda: "M1" in self.app.goal_message)
            after = json.loads(path.read_text())
            self.assertEqual(after["revisions"], before["revisions"])       # revision/approval identity unchanged
            self.assertEqual(self.identities(after), identities)           # run identity unchanged
            self.assertEqual(len(after["runs"]), 1)                   # no second revision, no dropped run
            self.assertIn("M1", self.app.goal_message)         # R-1's message names the running milestone ...
            self.assertNotIn(chat_module.OUTDATED, self.app.goal_message)   # ... not a stale draft
            await self.focus_panel(pilot)
            await self.shows(pilot, "M1")
            self.assertIn("M1", self.flat())                          # M1 still on home
            self.finish.set()                                         # release the run: its watch returns the result
            await self.open_merge_end(pilot)  # i3c: the stage-done card replaces the automatic end screen
            await self.press_button(pilot, "merge")
            await self.shows(pilot, "Merge the result of M1 into main?")
            await self.press_button(pilot, "yes")
            await self.shows(pilot, "Merged: M1 → main.")
        self.assertEqual(json.loads(path.read_text())["runs"][0]["delivery"], "integrated")


if __name__ == "__main__":
    unittest.main()
