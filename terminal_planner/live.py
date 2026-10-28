"""Live observation metadata of one attempt and the bounded activity tail.

`live` is a small optional field of a planner revision or a milestone run: when the watcher last looked, when the
watch last saw a new record, which native nodes were active, the bounded timeline of the planner graph's steps, and
a bounded journal of what happened. It is written only by the shared services while they observe
(`runs.MilestoneRuns.observe`, `planning.Watch.step`) with zplan's own clock; every reader (panel, journal, refresh,
status, load) only reads it. A record without the field loads unchanged and simply shows nothing about the live run.

No terminal, no Textual, no store: pure helpers over plain dicts, plus the one bounded log-tail reader."""

from collections import deque
from datetime import datetime, timezone
import json
import os
import re
import select
import subprocess
import time

JOURNAL_LIMIT = 20  # journal lines kept per attempt
EXECUTIONS_LIMIT = 48  # remembered native execution ids (replay/resume dedupe)
CURSORS_LIMIT = 32  # remembered watch cursors
TAIL_LINES = 40  # lines of `zeroshot logs` shown on request
TAIL_DEADLINE = 6.0  # seconds the reader may run
TAIL_BUFFER = 64 * 1024  # bytes kept while streaming
RECORD_DEADLINE = 30.0  # seconds the diagnosis reader of a failed run may run (R-6)
RECORD_BUFFER = 256 * 1024  # bytes of a failed run's `zeroshot logs` kept while streaming (R-6)
TIME = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")
COMMAND_PREFIX = "Codex command started: "  # the debug line the Codex adapter writes when a command starts (C3a)
COMMAND_LIMIT = 160  # characters of a remembered command kept (C3a)
COMMAND_STATUS = re.compile(r" \[[^\[\]]*\]$")  # the trailing ` [<status>]` of a command line
COMMAND_EXIT = re.compile(r" exit=-?\d+$")  # the trailing ` exit=<n>` of a command line
VERDICT_LIMIT = 8  # reviewer verdicts kept per attempt (C4a): oldest dropped
VERDICT_ROLES = ("acceptance_review", "code_review")  # the task reviewers whose verdict is remembered (C4a)
VERDICT_LABEL = 16  # characters of a remembered verdict signal kept (C4a)
VERDICT_TEXT = 160  # characters of a remembered one-line reason kept (C4a)
VERDICT_KEYS = frozenset({"at", "task", "round", "role", "verdict", "text"})  # one stored verdict's keys (C4a)
STEPS_LIMIT = 16  # planner graph steps kept per attempt (P2a): oldest dropped
KEYS = frozenset({"started", "last_event", "heartbeat", "detached", "nodes", "journal", "executions", "cursors",
                  "task", "workers", "repairs", "progress", "amendments", "command", "verdicts", "steps"})
# A live record written before C3a has no `command` key, one written before C4a no `verdicts` and one written before
# P2a no `steps`; every older shape is accepted, anything else is refused.
ACCEPTED_KEYS = tuple(KEYS - set(missing) for missing in (
    (), ("command",), ("verdicts",), ("steps",), ("command", "verdicts"), ("command", "steps"),
    ("verdicts", "steps"), ("command", "verdicts", "steps")))
# Native node (any graph) -> the role the owner reads. Unknown nodes keep their raw name.
ROLES = {"worker": "worker", "code_review": "code review", "acceptance_review": "acceptance",
         "steward_apply": "steward", "final_verify": "final check", "final_reverify": "final check",
         "scope_verify": "final check", "repair": "final-check repair", "planner": "planner",
         "plan_verifier": "plan check", "critic": "plan check", "preflight": "pre-check",
         "select_init": "task selection",
         "select": "task selection", "select_verify": "task selection", "steward_decide": "steward"}
PLANNER_ROLES = dict(ROLES, repair="plan rework")


def new():
    return {"started": None, "last_event": None, "heartbeat": None, "detached": None, "nodes": [], "journal": [],
            "executions": [], "cursors": [], "task": None, "workers": 0, "repairs": 0, "progress": None,
            "amendments": None, "command": None, "verdicts": [], "steps": []}


def valid(value):
    """Shape check used by the store validators."""
    def stamp(v):
        return v is None or isinstance(v, str) and bool(TIME.fullmatch(v))

    def strings(v, limit):
        return isinstance(v, list) and len(v) <= limit and all(isinstance(s, str) and s for s in v)

    def counter(v):
        return v is None or type(v) is int and v >= 0

    def command(v):
        return v is None or (isinstance(v, dict) and set(v) == {"at", "text"} and stamp(v["at"]) and v["at"] is not None
                             and isinstance(v["text"], str) and len(v["text"]) <= COMMAND_LIMIT)

    def steps(v):
        def entry(e):
            return (isinstance(e, list) and len(e) == 4 and all(isinstance(s, str) and s for s in e[:2])
                    and stamp(e[2]) and e[2] is not None and stamp(e[3]))
        return isinstance(v, list) and len(v) <= STEPS_LIMIT and all(entry(e) for e in v)

    def verdicts(v):
        def entry(e):
            return (isinstance(e, dict) and set(e) == VERDICT_KEYS and stamp(e["at"]) and e["at"] is not None
                    and (e["task"] is None or isinstance(e["task"], str))
                    and (e["round"] is None or type(e["round"]) is int and e["round"] >= 1)
                    and e["role"] in VERDICT_ROLES
                    and isinstance(e["verdict"], str) and len(e["verdict"]) <= VERDICT_LABEL
                    and isinstance(e["text"], str) and len(e["text"]) <= VERDICT_TEXT)
        return isinstance(v, list) and len(v) <= VERDICT_LIMIT and all(entry(e) for e in v)

    return (isinstance(value, dict) and set(value) in ACCEPTED_KEYS
            and all(stamp(value[k]) for k in ("started", "last_event", "heartbeat", "detached"))
            and isinstance(value["nodes"], list) and len(value["nodes"]) <= 16
            and all(isinstance(n, list) and len(n) == 2 and all(isinstance(s, str) and s for s in n)
                    for n in value["nodes"])
            and isinstance(value["journal"], list) and len(value["journal"]) <= JOURNAL_LIMIT
            and all(isinstance(e, dict) and set(e) == {"at", "text"} and stamp(e["at"]) and e["at"] is not None
                    and isinstance(e["text"], str) and e["text"] for e in value["journal"])
            and strings(value["executions"], EXECUTIONS_LIMIT) and strings(value["cursors"], CURSORS_LIMIT)
            and (value["task"] is None or isinstance(value["task"], str))
            and all(counter(value[k]) for k in ("workers", "repairs", "progress", "amendments"))
            and command(value.get("command"))
            and ("verdicts" not in value or verdicts(value["verdicts"]))
            and ("steps" not in value or steps(value["steps"])))


def base(node):
    """The node's own name: no graph path prefix, no `empty_` variant prefix."""
    node = node.rsplit("/", 1)[-1]
    return node[len("empty_"):] if node.startswith("empty_") else node


def role(node, roles=ROLES):
    return roles.get(base(node), base(node))


# Writing (services only) ---------------------------------------------------------------------------------------

def bounded(items, value, limit):
    items.append(value)
    del items[:-limit]


def touch(live, stamp, event=False):
    """A slice completed: the watcher looked at `stamp`; `event` when it delivered a record the watch had not seen."""
    live["heartbeat"], live["detached"] = stamp, None
    if event:
        live["last_event"] = stamp


def detach(live, stamp):
    """The observation failed at `stamp`: it shows as such until a slice succeeds again."""
    live["detached"] = stamp


def note(live, text, stamp):
    """One journal line; the line just written is not written twice."""
    if live["journal"] and live["journal"][-1]["text"] == text:
        return False
    bounded(live["journal"], {"at": stamp, "text": text}, JOURNAL_LIMIT)
    return True


def append(live, text, stamp):
    """One journal line per event, even when it reads like the line before it.

    `note` collapses a repeated phase line (the planner saying the same thing again); an execution line must
    survive that, because two different executions of the same role are two events and `stages` deduplicates
    them by their ids, never by their text."""
    bounded(live["journal"], {"at": stamp, "text": text}, JOURNAL_LIMIT)


def timeline(live, active, stamp, ended=False):
    """Update the planner step timeline `live["steps"]` (P2a) from one watch record; returns nothing.

    `active` is the record's `status.activeExecutions` (the same list the record's `nodes` are made of). Every
    execution on it the timeline does not carry yet is appended as `[node_base, execution, first, end]` with
    `first` = `stamp`; every open step (`end` None) whose execution is no longer on it gets `end` = `stamp`. An
    `ended` record is the one that finishes the run: nothing is active any more, so no step is added there and
    every open step is closed at `stamp` (the envelope kept beside a finished run may still list executions).
    The timeline keeps at most `STEPS_LIMIT` steps, oldest dropped."""
    kept = live.setdefault("steps", [])
    current = {entry["execution"] for entry in active}
    for step in kept:
        if step[3] is None and (ended or step[1] not in current):
            step[3] = stamp
    if ended:
        return
    known = {step[1] for step in kept}
    for entry in active:
        if entry["execution"] not in known:
            bounded(kept, [base(entry["node"]), entry["execution"], stamp, None], STEPS_LIMIT)


NATIVE = re.compile(r"nv2-[0-9a-f]{64}\Z")  # a native selector: opaque, it names no task, whatever a task is called
DIGEST = re.compile(r"[0-9a-f]{32,}\Z")  # the tail of one: a task id plus a digest names no task either


def names(execution, task):
    """The execution id names this task: it is the id, or the id plus a separator and a name suffix."""
    tail = execution[len(task):] if execution.startswith(task) else None
    return (execution == task
            or (tail is not None and tail[:1] in "-_" and not DIGEST.match(tail[1:])))


def execution_task(execution, tasks):
    """The task an execution provably belongs to, or None.

    A watch record proves its task through the execution id itself (`T1-w1` names `T1`). A native selector
    (`nv2-` plus a digest) names no task however the manifest's ids look, not even when a task id is that very
    selector; an id two task ids fit (`T1-hardening-w1` under `T1` and `T1-hardening`) proves neither: neither the
    current task nor the last task the journal named says anything about a buffered record, so none of them is ever
    used to guess one. A milestone with a single task is the other proof: manifest tasks are never removed
    (`milestone.validate_transition`), so every execution it observes belongs to that one task."""
    if len(tasks) == 1:
        return tasks[0]
    if NATIVE.match(execution):
        return None
    found = [task for task in tasks if names(execution, task)]
    return found[0] if len(found) == 1 else None


def stages(live, status, stamp, tasks=()):
    """Journal the executions of one watch record that were not seen before: stage changes, a worker that returns
    after a review is "rework, round N", and report the task reviewers that just left the record. An execution is
    named by its task only when the record proves it (`execution_task`); an unprovable one is journalled by its role
    alone, without a guessed task or round, and a verdict is never written here: accepted/rejected comes from the
    manifest (`note`) only.

    Returns the departed reviewers as `(role, execution)` pairs, role the node base, oldest first: a
    `acceptance_review`/`code_review` execution of the previous `live["nodes"]` that this record no longer lists.
    The caller queues them (C4a); `stages` itself persists nothing but the stage journal and the new `live["nodes"]`."""
    previous = live["nodes"]
    live["nodes"] = [[a["node"], a["execution"]] for a in status.get("activeExecutions", [])]
    current = {execution for _, execution in live["nodes"]}
    departed = [(base(node), execution) for node, execution in previous
                if base(node) in VERDICT_ROLES and execution not in current]
    for active in status.get("activeExecutions", []):
        execution, node = active["execution"], base(active["node"])
        if execution in live["executions"]:
            continue
        bounded(live["executions"], execution, EXECUTIONS_LIMIT)
        owner = execution_task(execution, tasks)
        if node == "worker":
            if owner is None:
                text = ROLES["worker"]
            else:
                if live["task"] != owner:
                    live.update(task=owner, workers=0)
                live["workers"] += 1
                text = ("%s: implementation" % owner if live["workers"] == 1
                        else "%s: rework, round %s" % (owner, live["workers"] - 1))
        elif node in ("code_review", "acceptance_review"):
            text = "%s: %s" % (owner, ROLES[node]) if owner is not None else ROLES[node]
        elif node == "steward_apply":
            text = "%s: recording the result" % owner if owner is not None else "recording the result"
        elif node == "repair":
            live["repairs"] += 1
            text = "final check: repair %s" % live["repairs"]
        elif node in ("final_verify", "final_reverify", "scope_verify"):  # the milestone's final check and its retries
            text = "final check"
        elif node in ROLES:
            text = ROLES[node]
        else:
            text = "stage " + node
        append(live, text, stamp)
    return departed


# Reading ------------------------------------------------------------------------------------------------------

def parse(stamp):
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def seconds_between(earlier, later):
    """Whole seconds from `earlier` to `later` (both stored stamps), never negative; None when unknown."""
    if not earlier or not later:
        return None
    return max(0, int((parse(later) - parse(earlier)).total_seconds()))


def duration(seconds):
    minutes = seconds // 60
    return "%s min" % minutes if minutes else "%s s" % seconds


def clock(stamp):
    """HH:MM:SS of a stored UTC stamp in the owner's local time."""
    return parse(stamp).astimezone().strftime("%H:%M:%S")


def panel_lines(live, started, now, roles=ROLES, nodes=None, rounds=None):
    """The live part of the running panel, plain lines: active roles (parallel ones all shown), time since the
    attempt started (`started`: stored stamp or None), time since the last activity and the watcher heartbeat.
    `nodes` overrides the stored active nodes (a planner reads them from its observation envelope). `rounds` is the
    bound of the task review loop; when it is given and the record proves its task (`live["task"]`) with at least one
    worker seen (`live["workers"]`), the panel also names the round the task is in («<task>: round N of M»). The
    default (`rounds=None`) keeps the output without it.

    A record that carries a command (C3a) measures its silence from the later of `live["last_event"]` and
    `live["command"]["at"]`: below two minutes the time part reads «last activity N ago», at or above it
    «silent N min», and «last: <text>» follows on its own line (the stored text verbatim). A record without a
    command (older records, the planner) keeps «last event N ago». The panel's own wording never says
    «stuck»; the echoed command text is the owner's and is not masked.

    A record with a non-empty `verdicts` (C4a) adds, right after that line, the newest task's last two review rounds
    (C4b): one header per round («<task>: round N», or «check» for a round that could not be proven, i.e. None),
    newest round first, then one line per reviewer of the round — the role's word, ✓ for accepted and ✗ for rejected
    (any other verdict string is shown as it is), then the one-line reason when it is not empty. A reviewer line
    longer than 120 characters is cut to it with a trailing ellipsis. A record without the key, or with an empty
    list, shows exactly the lines of the versions before it."""
    live = live or new()
    active = live["nodes"] if nodes is None else nodes
    lines = []
    if active:
        seen = []
        for node, _ in active:
            label = role(node, roles)
            if label not in seen:
                seen.append(label)
        lines.append("  Working now: " + ", ".join(seen))
    if rounds is not None and live["task"] and live["workers"] >= 1:
        lines.append("  %s: round %s of %s" % (live["task"], live["workers"], rounds))
    entries = live.get("verdicts") or []
    if entries:
        marks = {"accepted": "✓", "rejected": "✗"}
        task = entries[-1]["task"]
        mine = [entry for entry in entries if entry["task"] == task]
        order = []
        for entry in mine:  # by last appearance: the newest round ends the list
            if entry["round"] in order:
                order.remove(entry["round"])
            order.append(entry["round"])
        for number in order[-2:][::-1]:  # the latest two rounds, newest first
            lines.append("  check" if number is None else "  %s: round %s" % (task, number))
            for entry in mine:
                if entry["round"] != number:
                    continue
                mark = marks.get(entry["verdict"], entry["verdict"])
                line = "    %s %s" % (role(entry["role"], roles), mark)
                if entry["text"]:
                    line += " " + entry["text"]
                lines.append(line if len(line) <= 120 else line[:119] + "…")
    parts = []
    elapsed = seconds_between(started, now)
    if elapsed is not None:
        parts.append("running %s" % duration(elapsed))
    silence = 120  # seconds of no activity above which the time part says «silent» instead of «last activity» (C3b)
    command = live.get("command")
    activity = live["last_event"]
    if command is not None and (not activity or parse(command["at"]) > parse(activity)):
        activity = command["at"]
    quiet = seconds_between(activity, now)
    if quiet is not None:
        if command is None:
            parts.append("last event %s ago" % duration(quiet))
        elif quiet < silence:
            parts.append("last activity %s ago" % duration(quiet))
        else:
            parts.append("silent %s" % duration(quiet))
    if live["detached"]:
        parts.append("watching interrupted at %s - [w] reconnect" % clock(live["detached"]))
    elif live["heartbeat"]:
        parts.append("checked %s" % clock(live["heartbeat"]))
    if parts:
        lines.append("  " + " · ".join(parts))
    if command is not None:
        lines.append("  last: %s" % command["text"])
    return lines


def flow(live, started, now, rounds=None):
    """The facts of one attempt as plain data for the Now drawing (F1): a JSON-serialisable dict, no Rich or
    Textual object, nothing drawn.

    `live` is the stored live metadata (an older record without the `command`/`verdicts` keys is accepted), `started`
    its stamp and `now` the current stamp; `rounds` is the task review loop's bound (`runs.review_rounds`, None when
    unknown). The result carries the task and, once the record proves a task with a worker seen, its round
    (`live["workers"]`) alongside that bound; the worker's state is running while a `worker` node is active, done once
    a task reviewer is active or a matching verdict exists for the task's own round, and waiting before either; the
    two task reviewers (acceptance then code, exactly two) each read running while active, otherwise the newest
    `verdicts` entry for this task, round and role, otherwise waiting, with that matching entry's one-line text kept
    available whenever it exists (a reviewer can reappear for a later retry while its verdict is still stored) or "";
    the last step (a `final_verify`/`final_reverify`/`scope_verify`/`repair` node) and whether a task-picking node
    is active;
    the ROLES words of the active nodes in order and without duplicates; the seconds since `started` and since the
    later of `live["last_event"]` and the command's stamp (never negative, None when a stamp is unknown); the echoed
    command text; and the detachment stamp."""
    live = live or new()
    nodes = live["nodes"]
    verdicts = live.get("verdicts") or []
    task, workers = live["task"], live["workers"]
    number = workers if task and workers >= 1 else None
    bases = [base(node) for node, _ in nodes]

    def on(*names):
        return any(name in names for name in bases)

    def newest(role_name):
        for entry in reversed(verdicts):
            if entry["task"] == task and entry["round"] == number and entry["role"] == role_name:
                return entry
        return None

    if on("worker"):
        worker_state = "running"
    elif task is not None and (on(*VERDICT_ROLES)
                               or any(e["task"] == task and e["round"] == number for e in verdicts)):
        worker_state = "done"
    else:
        worker_state = "waiting"

    reviewers = []
    for role_name in VERDICT_ROLES:
        entry = newest(role_name)
        text = entry["text"] if entry is not None else ""
        if on(role_name):
            state = "running"
        elif entry is not None:
            state = entry["verdict"]
        else:
            state = "waiting"
        reviewers.append({"role": role_name, "name": ROLES.get(role_name, role_name), "state": state, "text": text})

    seen = []
    for node, _ in nodes:
        word = role(node)
        if word not in seen:
            seen.append(word)

    command = live.get("command")
    activity = live["last_event"]
    if command is not None and (not activity or parse(command["at"]) > parse(activity)):
        activity = command["at"]

    return {"task": task or None, "round": number, "rounds": rounds, "worker": {"state": worker_state},
            "reviewers": reviewers,
            "final": {"state": "running" if on("final_verify", "final_reverify", "scope_verify", "repair")
                      else "waiting"},
            "select": on("select_init", "select", "select_verify", "steward_apply", "steward_decide"),
            "active": seen, "elapsed": seconds_between(started, now), "silence": seconds_between(activity, now),
            "command": command["text"] if command is not None else None, "detached": live["detached"]}


# Activity tail ---------------------------------------------------------------------------------------------------

def tail(argv, env, cwd, lines=TAIL_LINES, deadline=TAIL_DEADLINE, buffer=TAIL_BUFFER, popen=subprocess.Popen,
         clock=time.monotonic):
    """The last `lines` lines of a streaming command, read while it streams.

    The reader's output goes through a bounded deque of the last `buffer` bytes, never a capture that is trimmed
    afterwards; when the command ends, closes its output or `deadline` passes, only that reader process is killed
    (its own session; nothing else). Empty output gives []; a partial last line is shown as it is. Raises OSError
    when the command cannot start."""
    data, _ = stream(argv, env, cwd, deadline, buffer, popen, clock)
    return _shown(data)[-lines:]


def records(argv, env, cwd, deadline=RECORD_DEADLINE, buffer=RECORD_BUFFER, popen=subprocess.Popen,
            clock=time.monotonic):
    """The retained lines of a streaming command and whether it ended cleanly: (lines, complete).

    The same bounded read as `tail` (the last `buffer` bytes kept while the command streams, the leading partial
    line of an overflow dropped, the line cut on `\n` only) and nothing else: the lines are classified, never
    shown, so they are returned exactly as the command wrote them and no credential can reach the screen through
    them. `complete` is True only when the command started, exited 0 inside `deadline` and its stdout was read to
    the end; a deadline that passes first, a nonzero exit and a read failure all give False (R-6). Raises OSError
    when the command cannot start."""
    data, code = stream(argv, env, cwd, deadline, buffer, popen, clock)
    return [line for line in data.decode("utf-8", errors="replace").split("\n") if line.strip()], code == 0


def stream(argv, env, cwd, deadline, buffer, popen, clock):
    """(the last `buffer` bytes of the command's stdout, its exit code or None) read while it streams.

    The output goes through a bounded deque, never a capture that is trimmed afterwards; when the command ends,
    closes its output or `deadline` passes, only that reader process is killed (its own session; nothing else).
    The exit code is None when the deadline passed before the command ended; a partial last line is kept as it is
    (the caller drops it if it cannot use it). Raises OSError when the command cannot start."""
    process = popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                    start_new_session=True)
    chunks, size, end = deque(), 0, clock() + deadline
    dropped = b""  # the byte just before the kept window: a line starts here only after a newline (or at the stream head)
    drained = False  # stdout was read to its end: a real EOF, never just the command's own exit
    expired = False  # the deadline passed before the read really ended: latched once, never cleared (R-6)
    try:
        fd = process.stdout.fileno()
        while True:
            left = end - clock()
            if left <= 0:
                expired = True  # the deadline passed before the output ended: the read is incomplete (R-6)
                break
            ready, _, _ = select.select([fd], [], [], min(left, 0.2))
            if not ready:
                continue  # nothing readable yet: wait for data or a real EOF until the deadline (R-6)
            data = os.read(fd, 65536)
            if not data:
                drained = True  # EOF: the command closed its output
                expired = clock() >= end  # an EOF that itself arrives after the deadline is not a complete read
                break
            chunks.append(data)
            size += len(data)
            while size > buffer:  # trim exactly the excess bytes from the oldest chunk, never a whole chunk that fits
                chunk = chunks.popleft()
                excess = size - buffer
                if len(chunk) > excess:
                    # The retained window is the last `buffer` bytes (A-3): only the oldest chunk's head goes, so a
                    # complete record that starts inside the window is kept whole.
                    dropped = chunk[excess - 1:excess]
                    chunks.appendleft(chunk[excess:])
                    size -= excess
                else:
                    dropped = chunk[-1:]
                    size -= len(chunk)
    except OSError:
        pass  # a read error (R-6): no EOF, so the shared cleanup below still counts the read as incomplete
    finally:
        # The deadline holds through the exit too (R-6): a deadline that passed before stdout reached its end is an
        # incomplete read whatever the exit status (`drained`), and a command that closed its output but keeps
        # running is waited for only until the deadline, then counted as expired and killed -- output read after the
        # deadline is not evidence. A command that exits right after its output is not killed for it.
        if not drained:
            expired = True  # no real EOF: the exit status alone is not a complete read
        left = end - clock()
        if left > 0:
            try:
                process.wait(timeout=left)
            except subprocess.TimeoutExpired:
                expired = True  # the command did not end inside the deadline
            else:
                # The exit code arrived, but the clock may have crossed the deadline while it was awaited: the
                # same rule as the EOF above -- a read that ends after the deadline is incomplete (R-6), and the
                # deadline stays latched once it has passed.
                expired = expired or clock() >= end
        else:
            # The clock is already at or past the deadline: the exit status can no longer prove an exit inside it,
            # whether or not the command has ended by now.
            expired = True
        if process.poll() is None:
            expired = True  # the command did not end inside the deadline: only its output was read
            try:
                process.kill()  # the reader only: the run itself is another process and keeps going
            except OSError:
                pass
        try:
            process.stdout.close()
            process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            pass
    # Records are cut on `\n` only: a Unicode separator (U+2028, U+0085) inside a value is part of that value, and
    # splitting there would scrub the two halves apart and show the credential's tail. The buffer bounds what is
    # kept, and a cut inside a line leaves a fragment whose key is gone (`=value` with no field name to recognise):
    # that partial first line is dropped, never shown -- or classified -- with what it still carries.
    data = b"".join(chunks)
    if dropped and dropped != b"\n":
        data = data.split(b"\n", 1)[1] if b"\n" in data else b""
    return data, None if expired else process.returncode


def _shown(data):
    """A retained window as display lines: an escaped line without control sequences, scrubbed of credentials."""
    text = data.decode("utf-8", errors="replace")
    result = [scrub(re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", line).rstrip()) for line in text.split("\n")]
    return [line for line in result if line.strip()]


# A credential field: the key name (with any prefix like OPENAI_ or access_, quoted or not) is kept, only the
# value after `=` or `:` is replaced. A bare key is one run of name characters (any but whitespace, a quote or the
# separator itself, so `api_key/client=` and `password[db]=` are whole names); the lookahead proves the run carries
# a secret word, and the leading boundary starts it only at its first character, which is what keeps `scrub` linear
# on a long ordinary line instead of retrying the whole run at every character. A quoted key is one quoted string
# closed by its own quote, whatever it holds (`"api_key/client"`, `"api_key's"`, `'api_key"x'`), and the lookahead
# proves it carries a secret word before the name is kept; the opening quote is not an escaped one, so the escaped
# quotes inside a value never start a scan (the pattern could otherwise rescan a long run of them at every one).
# A credential value is a quoted string, an unclosed quote (a partial last line, or a value a decoded `\n` left
# open: everything left of it is still the value, line breaks included), a scheme carrying its parameters, or one
# bare token. An `authorization` value after a bare key is the whole rest of the line (`Digest`, `AWS4-HMAC-SHA256`
# carry the credential after the scheme); after a quoted key the value is bounded like any other, so a neighbouring
# field keeps its name.
AUTHORIZATION = "authorization"
SECRET_KEY = r"api[_-]?key|token|secret|password|" + AUTHORIZATION
NAME = r"[^\s\"'=:]"  # one field-name character: a bare name runs up to its `=`/`:` (`api_key/client`, `password[db]`)
KEY_FIELD = (r"(?<!" + NAME + r")"  # a bare name starts where its run starts ...
             r"(?=" + NAME + r"*(?:%s))"  # ... the run it starts carries a secret word ...
             + NAME + r"+\s*[:=]\s*")  # ... and the run ends at its `=` or `:`
QUOTED_KEY = (r'(?:(?<!\\)"(?=[^"\\]*(?:\\.[^"\\]*)*(?:%s))[^"\\]*(?:\\.[^"\\]*)*"'
              r"|(?<!\\)'(?=[^'\\]*(?:\\.[^'\\]*)*(?:%s))[^'\\]*(?:\\.[^'\\]*)*')\s*[:=]\s*")
CREDENTIAL = (r'"[^"\\]*(?:\\.[^"\\]*)*"'
              r"|'[^'\\]*(?:\\.[^'\\]*)*'"
              r'|["\'][\s\S]*'
              r"|(?:basic|bearer|digest|negotiate|ntlm|aws4-hmac-sha256)\s+\S.*"
              r"|\S+")
SECRET = re.compile(r"(?i)"
                    r"(?P<qkey0>" + QUOTED_KEY % (AUTHORIZATION, AUTHORIZATION) + r")(?P<qval0>" + CREDENTIAL + r")"
                    r"|(?P<key>" + KEY_FIELD % AUTHORIZATION + r")(?P<value>[\s\S]*)"
                    r"|(?P<qkey>" + QUOTED_KEY % (SECRET_KEY, SECRET_KEY) + r")(?P<qval>" + CREDENTIAL + r")"
                    r"|(?P<key2>" + KEY_FIELD % SECRET_KEY + r")(?P<value2>" + CREDENTIAL + r")"
                    r"|(?P<bearer>\bbearer\s+)(?P<token>[A-Za-z0-9._~+/=-]{8,})"
                    r"|\bsk-[A-Za-z0-9_-]{12,}")


# `zeroshot logs` writes one JSON record per line and the original text travels inside its string values, so a
# credential field in that text arrives with its quotes escaped (`\"api_key\":\"...\"`) and the flat scan above
# cannot see through the escaping; unescaping the whole line into one flat text would lose which level a field
# belongs to. So a line that is a JSON record is scrubbed level by level: every string *value* is decoded and
# scrubbed as its own text and only then the line's own fields are masked. A value that is itself a record or an
# array recurses, and so does a value that wraps one again as a JSON string (a doubly encoded log event), each
# step one level deeper and never past JSON_DEPTH levels: what is deeper is hidden whole, so the decoder stays
# bounded. A field *name* is never scrubbed: it is the name that is kept, and masking it would take the
# credential field it names away from the line scan (the value after it would survive); a name that arrived
# escaped (`\"\u0061pi_key\"`) is written out decoded so the line scan still recognizes the field it names. Text
# that is not JSON is scanned with one level of escaping read off first, so a field behind an escaped quote (or
# behind a message prefix) does not stay hidden from the scan. A log record is a JSON object, so a line whose
# first character is `{` but that no decoder accepts is a truncated record and is hidden whole, never scanned
# flat (the escaped value it still carries would survive that scan); other lines keep the flat scan.
JSON_DEPTH = 8
JSON_STRING = re.compile(r'"(?:[^"\\]|\\.)*"')
JSON_COLON = re.compile(r"\s*:")  # what follows a string that is a field name, not a value
JSON_SPACE = re.compile(r"\s*")  # the space between a field name's `:` and its value
HIDDEN = "[hidden]"
FIELD_NAME = re.compile(r"(?i)" + SECRET_KEY)  # a field name carrying a secret word, once its escapes are read
ESCAPE = re.compile(r'\\(u([0-9a-fA-F]{4})|["\\/])')  # the JSON escapes a credential can hide behind
# A value that had to be scrubbed is held out of the line scan as a stand-in while the line's own fields are
# masked, so the scan cannot read into it and cut it short, and takes its place again afterwards. The stand-in
# carries a raw `\0`, a byte no JSON text can hold, so it is never mistaken for a value of the line itself.
HOLD = "\x00"
HOLD_PATTERN = re.compile(r'"\x00(\d+)\x00"')
# A credential field whose value is a whole object or array is hidden as that value written out as a JSON string,
# so the line scan masks the field whole (a bare marker would let the scan read into the bracket that follows).
MASKED = json.dumps(HIDDEN, ensure_ascii=False)
RAW_DECODER = json.JSONDecoder()


def _hide(match):
    """The match with the field name kept and the value replaced by the marker."""
    keep = (match.group("qkey0") or match.group("key") or match.group("qkey") or match.group("key2")
            or match.group("bearer") or "")
    return keep + HIDDEN


def scrub(line):
    """A log line without a credential value: the tail is shown on screen.

    The whole value of a credential field is masked, whatever its length or characters (a short `password=abc`,
    a quoted `"api_key": "a:b c/d"`, an `Authorization: Basic <value>`), including the rest of a partial last line
    whose value quote never closes and a field carried escaped inside a JSON log record (any nesting depth: masked,
    or hidden whole past the depth limit); an authorization field keeps none of its parameters (`Digest ...
    nonce=... response=...`); only free text keeps the old guess (`bearer <value>`, `sk-<value>`).

    A line that is not a record but carries a readable escape (`\\"`, `\\uXXXX`) is not trusted to the flat scan: a
    field behind the escape (`\\"api_key\\":\\"<value>\\"`) is one the scan cannot see, and the escapes are read to
    find it (`_read`). Reading cannot be trusted to mask -- a value's own literal `\\"` reads as an escaped quote
    and would move the value's closing quote, showing its tail -- so when reading reveals a credential that the
    flat scan does not mask, the line is hidden whole, never shown. A line whose escapes read to no credential the
    scan misses (an escaped quote inside a name the scan already sees, or no secret at all) is scanned as before."""
    if line.lstrip()[:1] == "{":
        return _record(line, 0)
    if "\\" in line:
        read = _read(line)
        if read != line and SECRET.sub(_hide, read) != read:
            return HIDDEN
    return SECRET.sub(_hide, line)


def _record(text, depth):
    """A JSON record line without a credential value: its own fields and any value that hides one deeper.

    A record that does not decode (a truncated last line, an escape the decoder rejects) is hidden whole."""
    if depth > JSON_DEPTH:
        return HIDDEN
    try:
        json.loads(text)
    except (ValueError, RecursionError):
        return HIDDEN
    text = _hide_composites(text)
    bodies = []
    unwritable = []  # a recognized field name that cannot be written back hides the whole record

    def hold(match):
        token = match.group(0)
        if token == MASKED:  # a composite value already hidden: the line scan masks the field whole
            return token
        content = json.loads(token)
        if JSON_COLON.match(text, match.end()):  # a field name: kept whole, but an escaped spelling is written out
            if not isinstance(content, str):
                return token
            name = _read(content)
            if not FIELD_NAME.search(name):
                return token
            named = _writable(name)  # writing the name decoded lets the line scan see the field it names
            if named is None:  # a name that cannot be written back would take the field it names away from the scan
                unwritable.append(True)
                return token
            return named if named != token else token
        masked = _content(content, depth + 1)
        if masked == content:
            return token
        bodies.append(_body(masked))
        return '"' + HOLD + str(len(bodies) - 1) + HOLD + '"'

    masked = SECRET.sub(_hide, JSON_STRING.sub(hold, text))
    if unwritable:
        return HIDDEN
    return HOLD_PATTERN.sub(lambda match: bodies[int(match.group(1))], masked)


def _hide_composites(text):
    """The text with every credential field whose value is a whole object or array hidden as that value.

    Masking is token by token, so the field's value -- the object or the array itself -- would be cut at its first
    separator and the rest shown; the value is replaced by the marker written as a JSON string, so the line scan
    then masks the field whole. The scan is positional, so a repeated field name and an escaped spelling of one
    (`\\u0061pi_key`) are each read for what they are, and a value the decoder cannot take is hidden to the end of
    the text -- masked or hidden, never scanned flat -- and it stays linear (no recursion)."""
    out = []
    pos = 0
    for name in JSON_STRING.finditer(text):
        if name.start() < pos:  # a name inside a value that was already hidden
            continue
        colon = JSON_COLON.match(text, name.end())
        if colon is None:
            continue
        try:
            key = json.loads(name.group(0))
        except ValueError:
            continue
        if not isinstance(key, str) or not FIELD_NAME.search(_read(key)):
            continue
        start = JSON_SPACE.match(text, colon.end()).end()
        if text[start:start + 1] not in "{[":
            continue
        try:
            _, end = RAW_DECODER.raw_decode(text, start)
        except (ValueError, RecursionError):
            end = len(text)  # a value the decoder cannot take: the rest of the text is hidden too
        out.append(text[pos:start])
        out.append(MASKED)
        pos = end
    if not out:
        return text
    out.append(text[pos:])
    return "".join(out)


def _content(content, depth):
    """The decoded string with any credential it hides masked, at its own level.

    A record or an array it holds recurses, and so does the text inside a JSON string it wraps (a value that was
    encoded one time too many), each step one level deeper; other text is scanned with one level of escaping read
    off first. Past JSON_DEPTH levels the whole content is hidden, so the decoder never runs away."""
    if depth > JSON_DEPTH:
        return HIDDEN
    head = content.lstrip()[:1]
    if head in "{[":
        return _record(content, depth)
    if head == '"':
        try:
            inner = json.loads(content)
        except (ValueError, RecursionError):
            inner = None
        if isinstance(inner, str):
            masked = _content(inner, depth + 1)
            return content if masked == inner else _body(masked)
    return _text(content)


def _text(content):
    """A text value without a credential: the flat scan, or the whole value once a readable escape is read off.

    An escaped quote is what the flat scan cannot see through (a field escaped inside a message is the same field
    behind a plain quote), but reading the escapes cannot be trusted either: a `\"` the value carries literally is
    the same two characters as an escaped quote, so decoding moves a value's closing quote and shows its tail
    (reading the read text again moves it once more, one level deeper). So a value that carries a readable escape
    is hidden whole -- masked or hidden, never shown -- while a value whose backslashes read to nothing is scanned
    as it is, since an escape the reader does not know is no escape at all and hides no field from the scan."""
    if _read(content) != content:
        return HIDDEN
    return SECRET.sub(_hide, _hide_composites(content))


def _read(text):
    """The text with one level of JSON escaping read off: `\\"` -> `"`, `\\\\` -> `\\`, `\\uXXXX` -> its character.

    Linear and total: an escape it does not know is left as it is, so a readable escape is the only thing that
    makes the result differ from the text."""
    return ESCAPE.sub(lambda match: chr(int(match.group(2), 16)) if match.group(2) else match.group(1), text)


def _body(content):
    """The scrubbed text as a JSON string value: `HIDDEN` when a lone surrogate makes it unwritable."""
    body = _writable(content)
    return json.dumps(HIDDEN, ensure_ascii=False) if body is None else body


def _writable(content):
    """`content` as a JSON string value, or None when a lone surrogate makes it unwritable."""
    body = json.dumps(content, ensure_ascii=False)
    try:
        body.encode("utf-8")  # a lone surrogate from a `\uXXXX` escape cannot be written back at all
    except UnicodeEncodeError:
        return None
    return body


# Codex command (C3a) ---------------------------------------------------------------------------------------------

def floored(ms):
    """The `TIME` stamp of an epoch-millisecond timestamp, floored to whole seconds."""
    return datetime.fromtimestamp(ms // 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def last_command(lines):
    """(at, text, ms) of the last `Codex command started` record in `lines`, or None when there is none.

    One line is one JSON record (`record.message` carries the adapter text); a line whose message does not start
    with `COMMAND_PREFIX` -- a completed command, another phase, an unknown prefix -- is ignored, and so is a line
    that does not decode or names no message or no millisecond timestamp. The command is the first line of the
    rest of the message, with a trailing ` [<status>]` and ` exit=<n>` removed, scrubbed with `scrub` (a credential
    never reaches the caller) and then cut to `COMMAND_LIMIT` characters. `at` is the record's `timestamp` (ms
    epoch) floored to whole seconds, `ms` the raw timestamp the caller gates the replacement on; the last matching
    line of the read wins."""
    found = None
    for line in lines:
        try:
            value = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if not isinstance(value, dict) or not isinstance(value.get("record"), dict):
            continue
        message, timestamp = value["record"].get("message"), value.get("timestamp")
        if not isinstance(message, str) or not message.startswith(COMMAND_PREFIX) or type(timestamp) is not int:
            continue
        try:
            at = floored(timestamp)
        except (OverflowError, OSError, ValueError):
            continue
        text = message[len(COMMAND_PREFIX):].split("\n", 1)[0]
        text = scrub(COMMAND_STATUS.sub("", COMMAND_EXIT.sub("", text)))[:COMMAND_LIMIT]
        found = (at, text, timestamp)
    return found


# Reviewer verdict (C4a) ------------------------------------------------------------------------------------------

def first_line(message):
    """The first non-empty line of `message`, stripped, or "" when there is none.

    A diagnostic is one line by contract but may carry more; the reason kept is the first line that has content, so
    a leading blank line never hides it."""
    for line in message.split("\n"):
        if line.strip():
            return line.strip()
    return ""


def last_verdict(lines):
    """(at, verdict, text) of the last reviewer verdict in `lines`, or None when there is none.

    One line is one JSON record; the record's `message` is itself a JSON node response text. The last line whose
    `message` decodes to an object carrying `response.signals.verdict` as a non-empty string wins; its diagnostic
    reason is the first non-empty line of `response.diagnostic.message` ("" when absent), scrubbed with `scrub` (a
    credential never reaches the caller) and cut to `VERDICT_TEXT` characters, and `verdict` is the signal cut to
    `VERDICT_LABEL`. A line that does not decode, one that names no object or no message, one without an integer
    millisecond `timestamp` (its `at` cannot be floored) or one whose response lacks a non-empty string verdict is
    ignored."""
    found = None
    for line in lines:
        try:
            value = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if not isinstance(value, dict) or not isinstance(value.get("record"), dict):
            continue
        message, timestamp = value["record"].get("message"), value.get("timestamp")
        if not isinstance(message, str) or type(timestamp) is not int:
            continue
        try:
            body = json.loads(message)
        except (ValueError, RecursionError):
            continue
        response = body.get("response") if isinstance(body, dict) else None
        signals = response.get("signals") if isinstance(response, dict) else None
        verdict = signals.get("verdict") if isinstance(signals, dict) else None
        if not isinstance(verdict, str) or not verdict:
            continue
        try:
            at = floored(timestamp)
        except (OverflowError, OSError, ValueError):
            continue
        diagnostic = response.get("diagnostic")
        detail = diagnostic.get("message") if isinstance(diagnostic, dict) else None
        text = first_line(detail) if isinstance(detail, str) else ""
        found = (at, verdict[:VERDICT_LABEL], scrub(text)[:VERDICT_TEXT])
    return found
