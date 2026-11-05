"""The architect's tools as a stdio MCP server (newline-delimited JSON-RPC 2.0).

Codex runs it as `python -I -c <code> --project ABS_DIR [--controller SOCKET [--turn TOKEN]]` (see `architect.build_argv`). The
process lives outside the Codex sandbox, so this module is the boundary. It exposes the read functions of
`project_read` and the action tools (`zplan_status`, `zplan_start`, `zplan_stop`, `zplan_approve_plan`,
`zplan_resume`, `zplan_rebrief`, `zplan_plan`, `zplan_edit_plan`, `zplan_merge`, `zplan_propose_commit`, `zplan_settings`) that reach the live
Controller over its socket (`--controller`, and the owner turn's token `--turn`, sent in the envelope and never by the model); it turns every `Blocked` into a tool error, never into a crash. The one file it writes is the project
STATE (`zplan_state_update`, see `project_state`: four sections, at most 6 KB, scrubbed, hidden from git); it needs no
Controller. There are no other file-writing tools: an action only asks the Controller, whose gates and autonomy
policy decide. Every action result, error and timeout names the request id it
used; an action runs on its own thread, so a later `zplan_status` answers at once even while the action waits for
the Controller."""

import json
import os
import sys
import threading
import uuid

from . import __version__, bridge, catalog, project_read, project_state
from .authority import BRIEF_KEYS, BRIEF_RISKS, MAX_MILESTONE_TASKS, PLAN_EXAMPLE, Blocked, PersistenceError, canonical
from .engine import PLAN_FORMAT

MAX_LINE = 1 << 20           # one request line
PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, INTERNAL_ERROR = -32700, -32600, -32601, -32602, -32603
DEFAULT_PROTOCOL = "2025-06-18"

_ROOT = {"type": "string", "description": "The project (default) or one of its git worktrees."}
# The identity of one attempt as a `zplan_status` row carries it (`terminal_planner.delivery.Token`): the token an
# action tool takes names the exact attempt the architect looked at. `additionalProperties=false` like every schema.
_TOKEN = {"type": "object", "additionalProperties": False,
          "properties": {"milestone": {"type": "string"}, "plan_revision": {"type": "integer"},
                         "attempt": {"type": "integer"}, "run_id": {"type": ["string", "null"]},
                         "status": {"type": "string"}, "outcome": {"type": ["string", "null"]},
                         "delivery": {"type": "string"}},
          "required": ["milestone", "plan_revision", "attempt", "run_id", "status", "outcome", "delivery"]}


def _schema(properties, required=()):
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


_TEXT = {"type": "string", "minLength": 1, "maxLength": 8192}


def _list(items, most, least=1):
    return {"type": "array", "items": items, "minItems": least, "maxItems": most}


# The plan tools declare the whole plan type: Codex renders a tool's input schema as its declaration, and a bare
# `plan: object` made the model learn the shape from refusals (101 in 14 plan-writing turns on the rig). This mirrors
# the validator in authority.py (the brief keys, risks and the per-milestone task cap are imported from it, one
# source); the rules a schema cannot say (unique ids, coverage, an acyclic order) stay in PLAN_FORMAT.
_BRIEF = _schema({"goal": _TEXT, "why": _TEXT, "reuse": {"type": "string", "maxLength": 8192},
                  "write_set": _list(_TEXT, 32),
                  "criteria": _list(_schema({"id": _TEXT, "text": _TEXT, "example": _TEXT}, ["id", "text", "example"]), 5),
                  "non_goals": _list(_TEXT, 16, 0),
                  "risk": {"type": "string", "enum": list(BRIEF_RISKS)}, "dod": _TEXT}, BRIEF_KEYS)
_TASK = _schema({"id": _TEXT, "title": _TEXT, "checks": _list(_TEXT, 32), "brief": _BRIEF},
                ["id", "title", "checks", "brief"])
_SLICE = _schema({"id": _TEXT, "title": _TEXT, "requirements": _list(_TEXT, 64),
                  "tasks": _list(_TASK, MAX_MILESTONE_TASKS)}, ["id", "title", "requirements", "tasks"])
_MILESTONE = _schema({"id": _TEXT, "title": _TEXT, "depends_on": _list(_TEXT, 32, 0), "slices": _list(_SLICE, 32)},
                     ["id", "title", "depends_on", "slices"])
PLAN_SCHEMA = _schema({"requirements": _list(_schema({"id": _TEXT, "text": _TEXT}, ["id", "text"]), 64),
                       "milestones": _list(_MILESTONE, 32)}, ["requirements", "milestones"])


TOOLS = [
    {"name": "zplan_list_files", "description": "List the files of the project's last commit (no credential files); `note` names uncommitted paths.",
     "inputSchema": _schema({"prefix": {"type": "string", "description": "Only paths starting with this."},
                             "root": _ROOT})},
    {"name": "zplan_read_file", "description": "Read lines of one project file.",
     "inputSchema": _schema({"path": {"type": "string"}, "start": {"type": "integer", "minimum": 1},
                             "count": {"type": "integer", "minimum": 0}, "root": _ROOT}, ["path"])},
    {"name": "zplan_search", "description": "Case-sensitive substring search over the project's files.",
     "inputSchema": _schema({"text": {"type": "string"}, "root": _ROOT}, ["text"])},
    {"name": "zplan_state",
     "description": "Read the project STATE file (.zplan/STATE.md): your plan, next step, open questions and "
                    "decisions from earlier sessions; empty when none was written.",
     "inputSchema": _schema({})},
    {"name": "zplan_state_update",
     "description": "Replace the project STATE file with `text`: at most %d bytes, with exactly the sections %s (each "
                    "a `## ` heading) in this order. The whole file is replaced; secrets are masked."
                    % (project_state.MAX_BYTES, ", ".join(project_state.SECTIONS)),
     "inputSchema": _schema({"text": {"type": "string"}}, ["text"])},
    {"name": "zplan_status",
     "description": "Report this session's architect requests (queued, running, done with a result), the current "
                    "plan revision with its status, gate verdict and the critic's findings, and the approved plan's milestones with their "
                    "state, attempt, run id and token. Answers at once.",
     "inputSchema": _schema({})},
    {"name": "zplan_start",
     "description": "Ask the live Controller to start a run for a milestone at the current plan revision. The "
                    "Controller re-checks freshness and the autonomy policy: it may refuse or ask the owner.",
     "inputSchema": _schema({"milestone": {"type": "string"},
                             "revision": {"type": "integer", "minimum": 1}}, ["milestone", "revision"])},
    {"name": "zplan_stop",
     "description": "Ask the live Controller to stop the milestone's current attempt, named by its run id. The "
                    "Controller re-checks freshness: it stops only the latest attempt, otherwise it refuses.",
     "inputSchema": _schema({"milestone": {"type": "string"}, "run_id": {"type": "string"}}, ["milestone", "run_id"])},
    {"name": "zplan_approve_plan",
     "description": "Ask the live Controller to approve the current plan revision. The Controller re-checks "
                    "freshness and the autonomy policy: it may refuse or ask the owner (an approval over a rejected "
                    "critic stays the owner's).",
     "inputSchema": _schema({"revision": {"type": "integer", "minimum": 1}}, ["revision"])},
    {"name": "zplan_resume",
     "description": "Ask the live Controller to resume a recoverable attempt named by its status row's token. The "
                    "Controller re-checks freshness and the autonomy policy: it may refuse or ask the owner.",
     "inputSchema": _schema({"milestone": {"type": "string"}, "token": _TOKEN}, ["milestone", "token"])},
    {"name": "zplan_rebrief",
     "description": "Ask the live Controller for a new attempt of a failed milestone with a note (the brief itself "
                    "is unchanged; a needs_owner attempt is answered). The Controller re-checks freshness and the "
                    "autonomy policy: it may refuse or ask the owner.",
     "inputSchema": _schema({"milestone": {"type": "string"}, "token": _TOKEN, "note": {"type": "string"}},
                            ["milestone", "token", "note"])},
    {"name": "zplan_plan",
     "description": "Ask the live Controller to save the plan you wrote for a goal as a new revision, only in a turn "
                    "the owner started: `goal` is the owner's words or your "
                    "restatement of them; `plan` is the full plan, with a brief on every task; `request` quotes the "
                    "owner's words it answers. There is no planner: the plan is validated and a fresh reader checks "
                    "it (it retells the plan, a critic judges it); events turns are refused. The plan's approval is "
                    "a separate, gated action (zplan_approve_plan). The plan format: " + PLAN_FORMAT
                    # A0 S2b: the model guessed the shape from refusals (6.3 per plan turn): show one valid plan first.
                    + " A minimal valid plan, to copy the shape from: " + canonical(PLAN_EXAMPLE),
     "inputSchema": _schema({"goal": {"type": "string"}, "plan": PLAN_SCHEMA, "request": {"type": "string"}},
                            ["goal", "plan"])},
    {"name": "zplan_edit_plan",
     "description": "Ask the live Controller to save an edited plan as a new revision of the current one: `plan` is "
                    "the full edited plan (the current revision's plan, changed). The Controller refuses when "
                    "`revision` is not current, the plan is invalid, or the edit changes nothing; otherwise the new "
                    "revision gets the same review as a first plan; its approval is a separate, gated action "
                    "(zplan_approve_plan). `response` answers each finding of the earlier review in one line, "
                    "fixed: how / disputed: why; `request` quotes the owner's words this revision answers. "
                    "The plan format: " + PLAN_FORMAT,
     "inputSchema": _schema({"revision": {"type": "integer", "minimum": 1}, "plan": PLAN_SCHEMA,
                             "response": {"type": "string"}, "request": {"type": "string"}},
                            ["revision", "plan"])},
    {"name": "zplan_merge",
     "description": "Ask the live Controller to merge the attempt named by its status row's token into the "
                    "milestone's destination. The Controller re-checks freshness and the autonomy policy: it may "
                    "refuse or ask the owner. A refusal naming merge.critic_pending means call merge again with the "
                    "same token.",
     "inputSchema": _schema({"milestone": {"type": "string"}, "token": _TOKEN}, ["milestone", "token"])},
    {"name": "zplan_propose_commit",
     "description": "Offer the owner to commit their own uncommitted files: `paths` (files, relative to the project) "
                    "and `message` (what the change is, for the commit log). Nothing is committed until the owner "
                    "answers the card in zplan; credential files are refused. The result is the diff stat and a "
                    "scrubbed, bounded diff of what the live git status lets through; zplan_status then shows the "
                    "answer under `commit`.",
     "inputSchema": _schema({"paths": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                             "message": {"type": "string"}}, ["paths", "message"])},
    {"name": "zplan_settings",
     "description": "Ask the live Controller to change the process profile, only in a turn the owner started (their "
                    "message asks for the change): `level`, `max_runs` (parallel runs), `merge` (the merge gate), "
                    "`roles` ({name: {model, effort}}) and `checks` ([{name, argv, timeout_s}], the project checks; "
                    "with `merge: required` they gate merges), at least one, exactly what the owner asked. Events turns are "
                    "refused. The change waits for the owner's yes on a card: the call answers awaiting_owner and "
                    "nothing changes until he answers. A profile in the project's own file is refused with the proposed change. Running "
                    "attempts keep their profile: the change applies to what starts next.",
     "inputSchema": _schema({"level": {"type": "string"}, "max_runs": {"type": "integer"}, "merge": {"type": "string"},
                             "roles": {"type": "object",
                                       "additionalProperties": _schema({"model": {"type": "string"},
                                                                        "effort": {"type": "string"}})},
                             "checks": {"type": "array",
                                        "items": _schema({"name": {"type": "string"},
                                                          "argv": {"type": "array", "items": {"type": "string"}},
                                                          "timeout_s": {"type": "integer"}},
                                                         ["name", "argv", "timeout_s"])}})},
]

# The tools that act through the live Controller: their whole call travels over the socket, and every result, error
# and timeout names the bridge request id so the architect can follow it in `zplan_status`.
ACTION_TOOLS = ("zplan_status", "zplan_start", "zplan_stop", "zplan_approve_plan", "zplan_resume",
                "zplan_rebrief", "zplan_plan", "zplan_edit_plan", "zplan_merge",
                "zplan_propose_commit", "zplan_settings")
CLIENT_TIMEOUT = bridge.CLIENT_TIMEOUT  # the socket client waits past the server's own action bound


class _Invalid(Exception):
    """The request's parameters do not fit the tool's schema (a JSON-RPC error, not a tool error)."""


def _argument(arguments, name, kind, default=None, required=False):
    if name not in arguments:
        if required:
            raise _Invalid("Missing argument: %s." % name)
        return default
    value = arguments[name]
    if not isinstance(value, kind) or isinstance(value, bool):
        raise _Invalid("Bad argument type: %s." % name)
    return value


def _call(project, name, arguments):
    if name in ("zplan_state", "zplan_state_update"):
        unknown = set(arguments) - ({"text"} if name == "zplan_state_update" else set())
        if unknown:
            raise _Invalid("Unknown argument: %s." % sorted(unknown)[0])
        if name == "zplan_state":
            return project_state.read(project)
        text = _argument(arguments, "text", str, required=True)
        try:
            return "STATE saved: %d bytes." % len(project_state.write(project, text).encode("utf-8"))
        except PersistenceError as error:
            raise Blocked(str(error), family="store.write_failed") from error
    unknown = set(arguments) - {"prefix", "path", "start", "count", "text", "root"}
    if unknown:
        raise _Invalid("Unknown argument: %s." % sorted(unknown)[0])
    root = _argument(arguments, "root", str, project)
    if name == "zplan_list_files":
        return project_read.list_files(project, root, _argument(arguments, "prefix", str, ""))
    if name == "zplan_read_file":
        return project_read.read_file(project, root, _argument(arguments, "path", str, required=True),
                                      _argument(arguments, "start", int, 1), _argument(arguments, "count", int, project_read.MAX_LINES))
    if name == "zplan_search":
        return project_read.search(project, root, _argument(arguments, "text", str, required=True))
    raise _Invalid("Unknown tool: %s." % name)


def _tool_result(text, error=False):
    result = {"content": [{"type": "text", "text": text}]}
    if error:
        result["isError"] = True
    return result


def _bounded(error):
    text = str(error)
    return text[:256] + ("…" if len(text) > 256 else "")


def _action(controller, name, arguments, turn=None):
    """(payload, is_error) of one action tool call: the payload always names the bridge request id it used.
    `turn` is the owner-turn token this server was started with (`--turn`): the envelope carries it, never the
    model's arguments.

    The id is this process's own; it travels to the Controller and back, and `zplan_status` later reports the same
    id with its state, so a timeout is not the end of the request."""
    rid = uuid.uuid4().hex
    try:
        request = {"id": rid, "tool": name, "args": arguments}
        if turn:
            request["turn"] = turn
        reply = bridge.call(controller, request, timeout=CLIENT_TIMEOUT)
    except Blocked as error:
        return {"id": rid, "tool": name, "error": {"family": catalog.family(error), "message": _bounded(error)}}, True
    except (OSError, ValueError) as error:
        return {"id": rid, "tool": name,
                "error": {"family": "architect.controller_unavailable", "message": _bounded(error)}}, True
    ident = reply.get("id") or rid
    if "error" in reply:
        return {"id": ident, "tool": name,
                "error": {"family": reply["error"], "message": reply.get("message", "")}}, True
    return {"id": ident, "tool": name, "ok": reply.get("ok")}, False


def handle(project, message, controller=None, turn=None):
    """(result, error) of one request object; error is a (code, text) pair."""
    method, params = message.get("method"), message.get("params")
    params = params if isinstance(params, dict) else {}
    if method == "initialize":
        version = params.get("protocolVersion")
        return {"protocolVersion": version if isinstance(version, str) else DEFAULT_PROTOCOL,
                "capabilities": {"tools": {}}, "serverInfo": {"name": "zplan", "version": __version__}}, None
    if method == "ping":
        return {}, None
    if method == "tools/list":
        return {"tools": TOOLS}, None
    if method == "tools/call":
        arguments = params.get("arguments", {})
        if not isinstance(params.get("name"), str) or not isinstance(arguments, dict):
            return None, (INVALID_PARAMS, "tools/call needs a tool name and an arguments object.")
        try:
            if params["name"] in ACTION_TOOLS:
                payload, broken = _action(controller, params["name"], arguments, turn)
                return _tool_result(json.dumps(payload, ensure_ascii=False), error=broken), None
            value = _call(project, params["name"], arguments)
            return _tool_result(value if isinstance(value, str) else json.dumps(value)), None
        except _Invalid as error:
            return None, (INVALID_PARAMS, str(error))
        except Blocked as error:
            return _tool_result("%s: %s" % (error.family or "unknown_error", error), True), None
        except (OSError, ValueError) as error:
            return _tool_result("read.failed: %s" % error, True), None
    return None, (METHOD_NOT_FOUND, "Method not found: %s." % method)


def _send(out, message_id, result=None, error=None):
    message = {"jsonrpc": "2.0", "id": message_id}
    if error is not None:
        message["error"] = {"code": error[0], "message": error[1]}
    else:
        message["result"] = result
    out.write(json.dumps(message).encode("utf-8") + b"\n")
    out.flush()


def _read_line(stream):
    """(line, too_long); a line over MAX_LINE is skipped to its end. (None, False) at end of input."""
    line = stream.readline(MAX_LINE + 1)
    if not line:
        return None, False
    if len(line) > MAX_LINE and not line.endswith(b"\n"):
        while True:
            more = stream.readline(MAX_LINE + 1)
            if not more or more.endswith(b"\n"):
                break
        return b"", True
    return line, False


def _is_action(message):
    """True for a `tools/call` of an action tool: the one request kind that waits for the Controller."""
    params = message.get("params")
    return (message.get("method") == "tools/call" and isinstance(params, dict)
            and params.get("name") in ACTION_TOOLS)


def serve(project, stdin, stdout, controller=None, turn=None):
    out_lock = threading.Lock()  # the action threads and the read loop share one stdout

    def dispatch(message):
        try:
            result, error = handle(project, message, controller, turn)
        except Exception as exc:  # the loop must go on whatever one call did
            result, error = None, (INTERNAL_ERROR, "Internal error: %s" % type(exc).__name__)
        with out_lock:  # whole lines, never interleaved
            _send(stdout, message["id"], result, error)

    while True:
        line, too_long = _read_line(stdin)
        if line is None:
            return
        if too_long:
            _send(stdout, None, error=(PARSE_ERROR, "Request line is over %d bytes." % MAX_LINE))
            continue
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except ValueError:
            _send(stdout, None, error=(PARSE_ERROR, "Parse error."))
            continue
        if not isinstance(message, dict) or not isinstance(message.get("method"), str):
            if isinstance(message, dict) and "method" not in message:
                continue  # a response from the client; this server sends no requests
            _send(stdout, None, error=(INVALID_REQUEST, "Invalid request."))
            continue
        if "id" not in message:
            continue  # a notification gets no reply
        if _is_action(message):
            # An action waits for the Controller (up to its own bound); a later `zplan_status` must still answer at
            # once, so it runs on its own thread while the read loop keeps reading (the reply lock keeps lines whole).
            threading.Thread(target=dispatch, args=(message,), name="zplan-mcp-action", daemon=True).start()
        else:
            dispatch(message)


def main(argv):
    usage = "usage: architect_tools --project ABS_DIR [--controller SOCKET [--turn TOKEN]]\n"
    if len(argv) not in (2, 4, 6) or argv[0] != "--project" or not os.path.isabs(argv[1]) or not os.path.isdir(argv[1]):
        sys.stderr.write(usage)
        return 2
    controller = turn = None
    if len(argv) >= 4:
        if argv[2] != "--controller" or not os.path.isabs(argv[3]):
            sys.stderr.write(usage)
            return 2
        controller = argv[3]
    if len(argv) == 6:
        if argv[4] != "--turn" or not argv[5]:
            sys.stderr.write(usage)
            return 2
        turn = argv[5]
    serve(argv[1], sys.stdin.buffer, sys.stdout.buffer, controller, turn)
    return 0
