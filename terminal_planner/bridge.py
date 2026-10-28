"""The live Controller as a local endpoint for the architect's action tools.

The architect's Codex runs the stdio MCP server (`architect_tools.py`) in its own process, and the project's store
is locked to the running TUI process (`authority.py`), so an action the architect asks for must reach that
process's Controller and its gates. This module is the one boundary: the Controller serves an AF_UNIX socket in a
fresh 0700 directory under `/tmp` (a short path, under macOS' 104-byte limit), removed on stop. One JSON line
request `{"id", "tool", "args"}` gets one JSON line reply `{"id", "ok"}` or
`{"id", "error": family, "message"}`; both the read and the write are bounded.

Nothing here imports Textual, the delivery service or the lifecycle modules: the Controller owns the tools and
passes `dispatch(request) -> (ok, error)` in. `publish`/`path_for` hand the socket path to the chat in the same
process (the chat builds the architect's argv with `--controller`); the MCP server process never discovers it."""

import json
import os
import shutil
import socket
import tempfile
import threading
import time

from .authority import Blocked

TIMEOUT = 120.0              # seconds an action waits for its job before `architect.controller_timeout`
CLIENT_TIMEOUT = TIMEOUT + 30.0  # the client waits longer than the server, so the server's own answer wins
MAX_LINE = 1 << 20           # one request or reply line
READ_TIMEOUT = 10.0          # seconds the endpoint waits for a whole request line (the client sends it at once)
MAX_ID = 128                 # characters of a request id
MAX_REQUESTS = 64            # registry entries kept; the oldest finished ones go first
TMP_BASE = "/tmp"            # a short base: macOS' AF_UNIX limit is 104 bytes including the trailing NUL
PREFIX = "zplan-bridge-"
SOCKET = "controller.sock"
MAX_PATH = 100               # AF_UNIX path bytes we allow, leaving room under the platform limit

# The families this boundary raises or reports (catalog.ERRORS: the same IDs the catalog documents).
UNAVAILABLE = "architect.controller_unavailable"
TIMEOUT_FAMILY = "architect.controller_timeout"
CLOSING = "architect.closing"
INVALID = "architect.request_invalid"

_published = {}
_published_lock = threading.Lock()


def publish(project, path):
    """Remember the socket path of the Controller serving `project` in this process (the chat reads it)."""
    with _published_lock:
        _published[str(project)] = path


def unpublish(project):
    with _published_lock:
        _published.pop(str(project), None)


def path_for(project):
    """The socket path published for `project` in this process, or None (no live Controller here)."""
    with _published_lock:
        return _published.get(str(project))


def _read_line(conn, limit=MAX_LINE, timeout=READ_TIMEOUT):
    """One bounded line from `conn`: at most `limit` bytes, up to the first newline, within `timeout` seconds for
    the whole line (not per `recv`: a byte-by-byte sender cannot hold the thread); None at end of input."""
    data = bytearray()
    deadline = time.monotonic() + timeout
    while len(data) <= limit:
        left = deadline - time.monotonic()
        if left <= 0:
            break
        try:
            conn.settimeout(left)
            chunk = conn.recv(4096)
        except OSError:
            break
        if not chunk:
            break
        data += chunk
        if b"\n" in data:
            break
    if not data:
        return None
    return bytes(data).split(b"\n", 1)[0]


class Registry:
    """The session's request registry: one entry per action request, kept after a timeout.

    `open` registers a request when it is posted, `running` when the worker starts it, `finish` when its callback
    returns; a request that timed out keeps its last state instead of being dropped, so a later `zplan_status`
    still shows it and its result once the job ran. Thread-safe: written on the worker and read on the socket
    thread."""

    def __init__(self):
        self._lock = threading.Lock()
        self._items = {}

    def open(self, rid, tool):
        """Register `rid`; False (nothing registered) when the id is already known or every kept entry is still
        unfinished. Bounded so the status reply fits one line: only finished entries are dropped, oldest first."""
        with self._lock:
            if rid in self._items:
                return False
            while len(self._items) >= MAX_REQUESTS:
                old = next((key for key, item in self._items.items() if item.get("done")), None)
                if old is None:
                    return False
                del self._items[old]
            self._items[rid] = {"id": rid, "tool": tool, "state": "queued", "done": False, "ok": None, "error": None}
            return True

    def running(self, rid):
        with self._lock:
            item = self._items.get(rid)
            if item is not None and item["state"] == "queued":
                item["state"] = "running"

    def finish(self, rid, ok=None, error=None):
        with self._lock:
            item = self._items.get(rid)
            if item is None:  # never registered: nothing to record
                return
            item["state"], item["ok"], item["error"], item["done"] = "done", ok, error, True

    def snapshot(self):
        """Plain entries, in registration order: `{id, tool, state}` plus `ok` or `error` once done."""
        with self._lock:
            found = []
            for item in self._items.values():
                entry = {"id": item["id"], "tool": item.get("tool"), "state": item["state"]}
                if item.get("done"):
                    if item.get("error") is not None:
                        entry["error"] = item["error"]
                    else:
                        entry["ok"] = item.get("ok")
                found.append(entry)
            return found


class Endpoint:
    """The Controller's AF_UNIX endpoint: a listener thread accepts one connection per request and answers it.

    `dispatch(request)` runs on a per-request thread and returns `(ok, error)`; `error` is a `{family, message}`
    dict or None. `close` stops accepting and removes the directory; it never joins a request thread (one may be
    inside `dispatch`, up to its own bound), and the quit never waits for the endpoint, only for its own jobs."""

    def __init__(self, dispatch, timeout=TIMEOUT):
        self._dispatch = dispatch
        self.timeout = timeout
        self._dir = None
        self._path = None
        self._server = None
        self._closed = threading.Event()

    def start(self):
        """Create the directory and socket and start accepting; returns the socket path. Idempotent."""
        if self._server is not None:
            return self._path
        base = tempfile.mkdtemp(prefix=PREFIX, dir=TMP_BASE)
        os.chmod(base, 0o700)
        path = os.path.join(base, SOCKET)
        if len(path.encode("utf-8")) >= MAX_PATH:
            shutil.rmtree(base, ignore_errors=True)
            raise Blocked("The architect socket path is too long: %s." % path,
                          family="architect.controller_unavailable")
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(path)
            server.listen(16)
        except OSError as error:
            server.close()
            shutil.rmtree(base, ignore_errors=True)
            raise Blocked("The Controller could not open the socket: %s." % error,
                          family="architect.controller_unavailable") from error
        self._dir, self._path, self._server = base, path, server
        threading.Thread(target=self._accept, name="zplan-bridge", daemon=True).start()
        return path

    @property
    def path(self):
        return self._path

    def close(self):
        """Stop accepting and remove the socket directory. Never joins a request thread."""
        self._closed.set()
        server, self._server = self._server, None
        if server is not None:
            try:
                server.close()
            except OSError:
                pass
        if self._path:
            try:
                os.unlink(self._path)
            except OSError:
                pass
        if self._dir:
            shutil.rmtree(self._dir, ignore_errors=True)
        self._path = self._dir = None

    def _accept(self):
        while not self._closed.is_set():
            server = self._server
            if server is None:
                return
            try:
                conn, _ = server.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), name="zplan-bridge-request", daemon=True).start()

    def _serve(self, conn):
        try:
            line = _read_line(conn)
            answer = self._reply(line)
            reply = json.dumps(answer, ensure_ascii=False).encode("utf-8")
            if len(reply) > MAX_LINE:  # the client reads one bounded line: a longer one would arrive cut
                reply = json.dumps(self._failure(answer.get("id"), INVALID, "The reply is longer than %d bytes." % MAX_LINE),
                                   ensure_ascii=False).encode("utf-8")
            conn.settimeout(self.timeout + 5.0)
            conn.sendall(reply + b"\n")
        except (OSError, ValueError):
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _reply(self, line):
        """One reply line: `{"id", "ok"}` on success, `{"id", "error": family, "message"}` on any failure."""
        if line is None:
            return self._failure(None, INVALID, "Empty request.")
        if len(line) > MAX_LINE:
            return self._failure(None, INVALID, "The request line is longer than %d bytes." % MAX_LINE)
        try:
            request = json.loads(line)
        except ValueError:
            return self._failure(None, INVALID, "The request is not JSON.")
        if not isinstance(request, dict) or not isinstance(request.get("tool"), str):
            ident = request.get("id") if isinstance(request, dict) else None
            return self._failure(ident, INVALID, "An object {id, tool, args} is required.")
        ident = request.get("id")
        if not isinstance(ident, str) or not ident or len(ident) > MAX_ID:  # checked before any job is admitted
            return self._failure(None, INVALID, "A request id is required: a non-empty string of up to %d characters." % MAX_ID)
        try:
            ok, error = self._dispatch(request)
        except Exception as exc:  # a bug in one dispatch must not take the endpoint down
            return self._failure(request["id"], "unknown_error", "%s: %s" % (type(exc).__name__, exc))
        if error is None:
            return {"id": request["id"], "ok": ok}
        return self._failure(request["id"], error["family"], error["message"])

    @staticmethod
    def _failure(ident, family, message):
        """A failure reply; the id is echoed only when it is a valid one (a str of at most MAX_ID characters)."""
        good = isinstance(ident, str) and 0 < len(ident) <= MAX_ID
        return {"id": ident if good else None, "error": family, "message": message[:4000]}


def call(path, request, timeout=CLIENT_TIMEOUT):
    """One request/reply against the Controller's socket; returns the parsed reply dict.

    Raises `Blocked(family="architect.controller_unavailable")` when there is no Controller to reach: no path, a
    missing or refused socket, no reply, or a reply that is not a JSON object."""
    if not path:
        raise Blocked("The live Controller is unavailable: no socket is set.", family="architect.controller_unavailable")
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout)
        sock.connect(path)
        sock.sendall(json.dumps(request, ensure_ascii=False).encode("utf-8") + b"\n")
        line = _read_line(sock, timeout=timeout)
    except OSError as error:
        raise Blocked("The live Controller is unavailable: %s." % (error.strerror or error),
                     family="architect.controller_unavailable") from error
    finally:
        try:
            sock.close()
        except OSError:
            pass
    if not line:
        raise Blocked("The Controller did not answer.", family="architect.controller_unavailable")
    try:
        reply = json.loads(line)
    except ValueError as error:
        raise Blocked("The Controller's reply could not be parsed.", family="architect.controller_unavailable") from error
    if not isinstance(reply, dict):
        raise Blocked("The Controller's reply is not an object.", family="architect.controller_unavailable")
    return reply
