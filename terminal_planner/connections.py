"""R-6 store check: does the engine's native connection store back `key` with `fields`?

Pure module: exactly one `connection list` runs on the passed engine, with that engine's native environment. The
result is a `Connection(state, detail)` whose state is `ready`, `missing` or `unknown`, and whose detail is a
closed label (`""`, `missing`, `exit`, `timeout`, `io`, `decode`, `schema`) that never carries a value, an exit
code, stdout or stderr text. No family is raised here: a raised family needs a catalog entry, so s3a3 maps
`missing` to `lane.connection_missing` and `unknown` to `lane.connection_unknown`. `set`/`delete` and
`connections.json` are never touched, and `GATEWAY_*` policy is s3a3's.

Contract read at the Zeroshot version pinned in `toolchain.py`: crates/openengine-cluster-protocol/src/
native_v2_target.rs defines `ConnectionSummary {key, scope, kind, fields}` and `ConnectionListResult
{connections}`; `zeroshot connection list` prints that JSON envelope on stdout
(execution/connections.rs), from metadata only (local/connections.rs).
"""

from collections import namedtuple
import json
import subprocess

Connection = namedtuple("Connection", "state detail")

READY = "ready"
MISSING = "missing"
UNKNOWN = "unknown"

USER_SCOPE = "user"
TIMEOUT = 30


def connection_ready(engine, key, fields):
    """Check `key`/`fields` against `engine`'s native connection store (R-6).

    Exactly one `connection list` runs, in `engine.native_environment()`. Any store or envelope problem is
    `unknown`: a nonzero exit, a timeout, an OSError from `call`, a non-str stdout, a decode failure (ValueError
    incl. JSONDecodeError, UnicodeError, RecursionError) or a shape violation. Only failures from `call` are mapped:
    the engine's `executable`, `native_environment()` and `call` are resolved before the guarded invocation, so an
    exception from any of them is never suppressed (no bare `except`). Otherwise the result is `ready` iff some
    summary lists `key` in scope `user` with `set(fields) <= listed fields`, and `missing` otherwise (a missing
    key, a missing field, or an org-scope match only). Connection metadata readiness does not validate the stored
    base URL or provider access.
    """
    required = set(fields)
    argv = [engine.executable, "connection", "list"]
    environment = engine.native_environment()
    invoke = engine.call
    try:
        result = invoke(argv, capture_output=True, text=True, timeout=TIMEOUT, start_new_session=True,
                        stdin=subprocess.DEVNULL, env=environment)
    except subprocess.TimeoutExpired:
        return Connection(UNKNOWN, "timeout")
    except OSError:
        return Connection(UNKNOWN, "io")
    if result.returncode != 0:
        return Connection(UNKNOWN, "exit")
    if not isinstance(result.stdout, str):
        return Connection(UNKNOWN, "decode")
    try:
        envelope = json.loads(result.stdout)
    except (ValueError, UnicodeError, RecursionError):
        return Connection(UNKNOWN, "decode")
    summaries = _summaries(envelope)
    if summaries is None:
        return Connection(UNKNOWN, "schema")
    for summary in summaries:
        if summary["key"] == key and summary["scope"] == USER_SCOPE and required <= set(summary["fields"]):
            return Connection(READY, "")
    return Connection(MISSING, "missing")


def _summaries(envelope):
    """The validated summary list of a `ConnectionListResult`, or None for any shape violation.

    The envelope must be a JSON object with a list `connections`; other envelope keys are ignored. Each summary
    must be an object whose `key`, `scope` and `kind` are str and whose `fields` is a list of str; any violation
    makes the whole result `unknown`.
    """
    if not isinstance(envelope, dict):
        return None
    connections = envelope.get("connections")
    if not isinstance(connections, list):
        return None
    for summary in connections:
        if not isinstance(summary, dict):
            return None
        if not all(isinstance(summary.get(name), str) for name in ("key", "scope", "kind")):
            return None
        fields = summary.get("fields")
        if not isinstance(fields, list) or not all(isinstance(field, str) for field in fields):
            return None
    return connections
