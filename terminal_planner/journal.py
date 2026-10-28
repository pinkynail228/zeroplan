"""The project journal (A6a): the engine's run history, duration-stamped steps, and the journal's own store.

Three small pieces, none wired into the Controller or the TUI yet (A5t/A6b/A10):

- `Reader`: the `zeroshot ui` HTTP projection of the run history -- a child process on loopback, never the private
  run store. `runs()` lists the engine's runs, `history()` reads one run's events page by page.
- `steps`: pure; one step per execution from a run's events. Only `safe_log` events carry time, so a step's start and
  end are the latest `safe_log` timestamp at or before the started/completed event.
- `append` / `load`: a JSON-lines file of `step`, `action` and `learning` records, each stamped on receipt.

No engine state is kept here: the engine owns planning and lifecycle, the journal only remembers what it reported."""

from datetime import datetime, timezone
from http.client import HTTPException
import json
import os
import re
import signal
import subprocess
import threading
from urllib import error, parse, request

from .authority import Blocked
from .live import scrub

LISTEN_DEADLINE = 10.0  # seconds to the "Zeroshot UI: <origin>" line
STOP_DEADLINE = 5.0  # seconds a terminated child may take before it is killed
HTTP_DEADLINE = 15.0  # seconds one request may take
PAGE_LIMIT = 50  # pages followed per listing
BODY_LIMIT = 16 * 1024 * 1024  # bytes of one response read
VERDICT_LIMIT = 200  # characters of a step's verdict
FIRST_CURSOR = "v2:0"
KINDS = ("step", "action", "learning")
ORIGIN = re.compile(r"Zeroshot UI: (http://127\.0\.0\.1:\d+)/ui/")
UNAVAILABLE = "Journal unavailable: the Zeroshot run history could not be read (%s)."


def unavailable(cause):
    return Blocked(UNAVAILABLE % cause, family="journal.history_unavailable")


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None  # urllib then raises the 3xx as an HTTPError


class Reader:
    """The engine's run history over `zeroshot ui --listen 127.0.0.1:0`; a context manager that owns the child."""

    def __init__(self, engine):
        self.engine = engine
        self.process = None
        self.thread = None
        self.origin = None
        # Loopback only: never through a proxy, and a redirect is an error rather than a request to another origin.
        self.opener = request.build_opener(request.ProxyHandler({}), NoRedirect)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()

    def start(self):
        try:
            self.process = subprocess.Popen([self.engine.executable, "ui", "--listen", "127.0.0.1:0"],
                                            env=self.engine.native_environment(), stdin=subprocess.DEVNULL,
                                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                                            start_new_session=True)
        except OSError as problem:
            raise unavailable("did not start") from problem
        found = threading.Event()
        # The reader keeps draining stderr after the origin line, so a chatty child never blocks on a full pipe.
        self.thread = threading.Thread(target=self.watch, args=(self.process.stderr, found), daemon=True)
        self.thread.start()
        if not found.wait(LISTEN_DEADLINE):
            self.stop()
            raise unavailable("no address within %d s" % LISTEN_DEADLINE)

    def watch(self, stream, found):
        try:
            for line in stream:
                match = ORIGIN.search(line)
                if match and self.origin is None:
                    self.origin = match.group(1)
                    found.set()
        except (OSError, ValueError):
            pass

    def stop(self):
        """Ends the child's whole process group: the npm `zeroshot` launcher runs the native binary as its own child
        and does not pass a signal on, so terminating the launcher alone would leave the server running. The launcher
        is reaped only after the last group signal: until then its pid, the group id, cannot be reused."""
        process, self.process = self.process, None
        thread, self.thread = self.thread, None
        if process is None:
            return
        self.signal(process, signal.SIGTERM)
        if thread is not None:
            thread.join(STOP_DEADLINE)  # stderr ends once every process holding it is gone
        self.signal(process, signal.SIGKILL)  # whatever of the group is left, the launcher's own child included
        process.wait()
        if thread is not None:
            thread.join(STOP_DEADLINE)
            if thread.is_alive():
                return  # closing stderr under a blocked reader would block too
        if process.stderr is not None:
            process.stderr.close()

    @staticmethod
    def signal(process, number):
        try:
            os.killpg(process.pid, number)  # `start_new_session`: the group id is the child's pid
        except (ProcessLookupError, PermissionError):
            pass

    def get(self, path, after=None):
        if self.origin is None:
            raise unavailable("server not running")
        url = self.origin + path + ("" if after is None else "?" + parse.urlencode({"after": after}))
        try:
            with self.opener.open(url, timeout=HTTP_DEADLINE) as response:
                body = response.read(BODY_LIMIT + 1)
            if len(body) > BODY_LIMIT:
                raise unavailable("reply too large")
            page = json.loads(body)
        except (error.URLError, OSError, ValueError, HTTPException) as problem:  # HTTPError (404) is a URLError
            raise unavailable(type(problem).__name__) from problem
        if not isinstance(page, dict):
            raise unavailable("unexpected reply")
        return page

    def pages(self, path, key, after=None):
        """The `key` items of every page from `after` (None: the first page), following `nextCursor` until
        `complete` (or the end)."""
        items = []
        for _ in range(PAGE_LIMIT):
            page = self.get(path, after)
            part = page.get(key, [])
            if not isinstance(part, list):
                raise unavailable("unexpected reply")
            items.extend(part)
            following = page.get("nextCursor")
            if page.get("complete") or not isinstance(following, str) or following == after:
                break
            after = following
        return items

    def runs(self):
        return self.pages("/ui/api/runs", "runs")  # its cursor is a run id: the first page takes no `after`

    def history(self, run_id, after=FIRST_CURSOR):
        return self.pages("/ui/api/runs/%s/history" % parse.quote(str(run_id), safe=""), "events", after)


def steps(events):
    """One step per execution of a run's history events (items `{"cursor", "event"}`), in start order.

    `start`/`end` are the latest `safe_log` timestamp (ms) at or before the started/completed event, `None` if there is
    none; `duration` is their difference in seconds; `verdict` is the first line of the diagnostic, scrubbed."""
    found, order, clock = {}, [], None
    for item in events:
        event = item.get("event") if isinstance(item, dict) else None
        if not isinstance(event, dict):
            continue
        kind = event.get("kind")
        if kind == "safe_log":
            stamp = event.get("timestamp")
            clock = stamp if isinstance(stamp, (int, float)) else clock
        elif kind == "node_started":
            reference = event.get("reference") or {}
            execution = reference.get("execution")
            if execution not in found:
                order.append(execution)
                found[execution] = {"execution": execution, "node": reference.get("node"), "start": clock,
                                    "end": None, "duration": None, "status": None, "verdict": "", "tokens": 0}
        elif kind == "node_completed":
            completion = event.get("completion") or {}
            reference = completion.get("reference") or {}
            execution = reference.get("execution")
            step = found.setdefault(execution, {"execution": execution, "node": reference.get("node"), "start": None,
                                                "end": None, "duration": None, "status": None, "verdict": "",
                                                "tokens": 0})
            if execution not in order:
                order.append(execution)
            outcome = completion.get("outcome") or {}
            message = (outcome.get("diagnostic") or {}).get("message") or ""
            step["status"] = outcome.get("status")
            step["verdict"] = scrub(message.strip().split("\n", 1)[0])[:VERDICT_LIMIT]
            step["end"] = clock
            if step["start"] is not None and clock is not None:
                step["duration"] = (clock - step["start"]) / 1000
        elif kind == "token_usage_observed":
            step = found.get(event.get("execution"))
            usage = event.get("usage") or {}
            if step is not None:
                step["tokens"] += (usage.get("inputTokens") or 0) + (usage.get("outputTokens") or 0)
    return [found[execution] for execution in order]


def append(path, entry):
    """Add one JSON line to the journal at `path`, stamped `at` (ISO UTC) on receipt; returns the stored record."""
    if entry.get("kind") not in KINDS:
        raise ValueError("journal kind must be one of %s" % ", ".join(KINDS))
    if entry["kind"] == "learning" and not all(entry.get(name) for name in ("cause", "defect", "fix")):
        raise ValueError("a learning record names its cause, defect and fix")
    record = dict(entry, at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with open(path, "a+b") as handle:
        # A torn last line has no newline: start on a fresh line so the new record stays readable.
        size = handle.seek(0, os.SEEK_END)
        if size:
            handle.seek(size - 1)
            if handle.read(1) != b"\n":
                line = "\n" + line
        handle.write(line.encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())
    return record


def load(path):
    """The journal's records, oldest first; a missing file is empty and a torn or foreign line is skipped."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except FileNotFoundError:
        return []
    records = []
    for line in text.split("\n"):
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records
