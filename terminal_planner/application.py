"""Shared application operations for terminal and automation frontends.

Owner turns and controller-routed tools share the existing architect store's operation journal. Initial plan dispatch
uses the existing Planning/engine boundary and does not depend on a screen callback. Later observation/event turns and
restoring actionable consent remain separate gates, not an autonomous goal-to-merge claim.
A terminal operation replays without another effect; an unfinished operation is never automatically resent.
"""

from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from typing import Literal
import fcntl
import hashlib
import json
import os
import uuid

from .architect import TurnResult, project_key, prepare
from .authority import Blocked
from .delivery import Token
from . import bridge, feed, live


OPERATION = "send_message"
TERMINAL = frozenset({"completed", "failed"})
_UNSET = object()


def scrub(value):
    """Scrub nested tool evidence just like architect evidence, including legacy replay."""
    if isinstance(value, str):
        return live.scrub(value)
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            credential = live.FIELD_NAME.search(str(key))
            # The public attempt identity is not an auth token; MCP must be able to round-trip it.
            # Keep only that exact domain shape (and absent identity), not arbitrary token objects.
            if key == "token" and (item is None or isinstance(item, dict)
                                   and set(item) == {part.name for part in fields(Token)}):
                credential = False
            # Provider usage counters are quantities, not credentials. Strings remain untrusted.
            if key in ("input_tokens", "output_tokens", "cached_input_tokens") and type(item) is int:
                credential = False
            result[live.scrub(str(key))] = live.HIDDEN if credential else scrub(item)
        return result
    if isinstance(value, (list, tuple)):
        return [scrub(item) for item in value]
    return value


def request_snapshot(snapshot, project):
    """Freeze the common application projection, preserving unknown versus known no-plan."""
    if snapshot is None:
        return {"project": project, "branch": None, "milestones": []}
    lines = list(snapshot.lines)
    goal = lines[0] if lines else ""
    status = lines[1] if len(lines) > 1 and lines[1].startswith("Plan r") else ""
    return {"project": snapshot.project, "branch": snapshot.branch,
            "plan_summary": " · ".join(part for part in (goal, status) if part),
            "revision": snapshot.version, "plan_state": snapshot.plan_state,
            "uncommitted": list(snapshot.uncommitted),
            "milestones": [{"id": row.id, "title": row.title, "state": row.state,
                            "token": asdict(row.token) if row.token is not None else None}
                           for row in snapshot.rows]}


def shown_plan(snapshot):
    """The revision the owner's screen showed as waiting (plan_state status "proposed", not declined) in `snapshot`,
    else None: a yes in words approves only that plan."""
    state = snapshot.get("plan_state") if isinstance(snapshot, dict) else None
    if isinstance(state, dict) and state.get("status") == "proposed" and not state.get("declined"):
        return snapshot.get("revision")
    return None


@dataclass(frozen=True)
class ToolDecision:
    """A pending owner action. Restoring actionable consent is deliberately a later gate."""
    action: str
    subject: dict
    request_id: str | None = None
    restorable: bool = False


@dataclass(frozen=True)
class ToolResult:
    """Frontend-neutral outcome. Awaiting decisions are descriptive, not reopenable consent.

    MCP keeps its existing (ok, error) envelope; frontends consume this same detail and category.
    Running/indeterminate are nonterminal: a timeout is not a failed external effect.
    """
    operation_id: str
    tool: str
    category: Literal["completed", "failed/refused", "awaiting_owner", "running", "indeterminate"]
    parent_operation_id: str | None = None
    conversation_id: str | None = None
    turn_id: str | None = None
    subject: dict = field(default_factory=dict)
    detail: dict = field(default_factory=dict)
    error: dict | None = None
    decision: ToolDecision | None = None
    replayed: bool = False

    @classmethod
    def restore(cls, data, replayed=False):
        data = scrub(data)
        if isinstance(data.get("decision"), dict):
            data["decision"] = ToolDecision(**data["decision"])
        return cls(**dict(data, replayed=replayed))

    def envelope(self):
        if self.category in ("running", "indeterminate"):
            return None, {"family": bridge.TIMEOUT_FAMILY, "message": "outcome unknown"}
        if self.error is not None:
            return None, self.error
        # Preserve the existing MCP payload; these extra application facts are durable typed data.
        return {key: value for key, value in self.detail.items() if key not in ("dispatch", "decision")}, None


@dataclass(frozen=True)
class SendMessageRequest:
    """One owner message and its durable operation, conversation and turn identities."""

    operation_id: str
    message_id: str
    project_id: str
    conversation_id: str
    turn_id: str
    text: str
    snapshot: object = None
    _snapshot_json: str = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        try:
            encoded = json.dumps(self.snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as error:
            raise Blocked("The message snapshot is not serializable.", family="operation.invalid_request") from error
        object.__setattr__(self, "_snapshot_json", encoded)

    def __getattribute__(self, name):
        # Each reader gets its own JSON value. Neither caller nor provider can mutate request input.
        if name == "snapshot":
            try:
                return json.loads(object.__getattribute__(self, "_snapshot_json"))
            except AttributeError:
                pass  # construction, before __post_init__ captured it
        return object.__getattribute__(self, name)


@dataclass(frozen=True)
class MessageSubmission:
    """Automation supplies only the stable key and immutable owner text."""
    operation_id: str
    text: str


@dataclass(frozen=True)
class SendMessageResult:
    """The typed operation outcome; `turn` is the existing adapter's detailed result."""

    operation_id: str
    message_id: str
    turn_id: str
    status: str
    turn: TurnResult
    replayed: bool = False
    conversation_id: str | None = None


class ApplicationService:
    """Owner admission, durable tool outcomes and initial advancement over the existing services."""

    def __init__(self, architect, store=None, controller=None, owner_port=None, prepare_architect=prepare):
        self.architect = architect
        self.prepare_architect = prepare_architect
        self.store = store or architect.store
        self.controller = controller
        self.owner_port = controller if controller is not None else owner_port
        self.operations_path = self.store.directory / "operations.jsonl"
        self.operation_lock_path = self.store.directory / "operations.lock"
        if controller is not None:
            controller.application = self

    @staticmethod
    def _stamp():
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    @contextmanager
    def _locked(self, wait=True):
        descriptor = os.open(self.operation_lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        stream = os.fdopen(descriptor, "r+")
        try:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
            except BlockingIOError as error:
                raise Blocked("Another window is saving an architect operation; keep the input and retry.",
                              family="architect.busy") from error
            yield
        finally:
            stream.close()

    def conversation_id(self):
        """The stable project conversation id, created once in the existing session record."""
        with self._locked(wait=False):
            return self._conversation_id()

    def _conversation_id(self):
        # Caller owns operations.lock; session writers share their own short lock.
        def ensure_id(session):
            if session is None:
                session = {"version": 1, "thread_id": None, "model": getattr(self.architect, "model", None),
                           "created": self._stamp(), "turns": 0, "usage": {}}
            if not isinstance(session.get("conversation_id"), str) or not session["conversation_id"]:
                session["conversation_id"] = uuid.uuid4().hex
            return session

        return self.store.update_session(ensure_id)["conversation_id"]

    def new_request(self, text, snapshot=_UNSET):
        """Capture input now, never from the UI's later state when the provider starts."""
        if snapshot is _UNSET:
            snapshot = self.controller.request_snapshot() if self.controller is not None else None
        return SendMessageRequest(uuid.uuid4().hex, uuid.uuid4().hex, project_key(self.store.project),
                                  self.conversation_id(), uuid.uuid4().hex, text, snapshot)

    def fingerprint(self, request):
        """The exact semantic payload an operation id is allowed to replay."""
        value = {"kind": OPERATION, "message_id": request.message_id, "project_id": request.project_id,
                 "conversation_id": request.conversation_id, "turn_id": request.turn_id,
                 "text": request.text, "snapshot": request.snapshot}
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as error:
            raise Blocked("The message snapshot is not serializable.", family="operation.invalid_request") from error

    def _validate(self, request):
        if not isinstance(request, SendMessageRequest):
            raise Blocked("A typed SendMessageRequest is required.", family="operation.invalid_request")
        identifiers = (request.operation_id, request.message_id, request.project_id,
                       request.conversation_id, request.turn_id)
        if not all(isinstance(value, str) and value for value in identifiers):
            raise Blocked("Every message and operation id must be a nonempty string.", family="operation.invalid_request")
        if request.project_id != project_key(self.store.project):
            raise Blocked("The message belongs to another project.", family="operation.project_mismatch")
        if not isinstance(request.text, str) or not request.text.strip():
            raise Blocked("Empty message to the architect.", family="architect.empty_message")

    def _append(self, record):
        # Every caller holds operations.lock. Provider work releases that lock, so a
        # previous read cannot establish integrity for this write (including completion).
        self._latest(record["operation_id"])
        if self._torn_tail:
            raise Blocked("The operation journal has an incomplete final record; no record was appended.",
                          family="operation.store_invalid")
        line = (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        descriptor = os.open(self.operations_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(os.dup(descriptor), "wb") as stream:
                stream.write(line)
                stream.flush()
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _records(self):
        """Complete journal records only; all projections share corruption/torn-tail rules."""
        self._torn_tail = False
        try:
            with self.operations_path.open("rb") as stream:
                for line in stream:
                    # Only an unterminated final record is a torn write. Never append after it or
                    # trust it as a terminal outcome; complete earlier records remain replayable.
                    if not line.endswith(b"\n"):
                        self._torn_tail = True
                        break
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                        if not isinstance(record, dict) or not isinstance(record.get("operation_id"), str):
                            raise ValueError("invalid operation record")
                    except (ValueError, UnicodeError) as error:
                        raise Blocked("The operation journal is corrupted.", family="operation.store_invalid") from error
                    yield record
        except FileNotFoundError:
            return

    def _latest(self, operation_id):
        """Keep the original immutable request even when the terminal row contains only evidence."""
        latest = original = None
        for record in self._records():
            if record["operation_id"] == operation_id:
                if original is None and record.get("state") in ("accepting", "accepted", "running"):
                    original = record.get("request")
                latest = record
        return dict(latest, request=original) if latest is not None and original is not None else latest

    def _resolve_submission(self, submission, record):
        if record.get("kind") != OPERATION:
            raise Blocked("The operation id is already bound to another request.", family="operation.conflict")
        try:
            request = SendMessageRequest(operation_id=submission.operation_id, **record["request"])
            self._validate(request)
        except (KeyError, TypeError) as error:
            raise Blocked("The original message request is missing or invalid.",
                          family="operation.store_invalid") from error
        if request.text != submission.text:
            raise Blocked("The operation id is already bound to another request.", family="operation.conflict")
        self._replay(request, record)  # also validates the unchanged fingerprint format
        return request

    def submit_message(self, operation_id, text):
        """Send a new automation submission, never continue an existing accepted/running one.

        Resolution and the final novelty/admission decision are serialized with UI admission. No frontend
        journal lookup or regenerated request ids; explicit TUI send_message(request) may still continue acceptance.
        """
        return self.send_message(MessageSubmission(operation_id, text))

    @staticmethod
    def _turn(data):
        result = TurnResult()
        for key, value in (data or {}).items():
            if hasattr(result, key):
                setattr(result, key, value)
        return result

    @staticmethod
    def _turn_evidence(result):
        """The bounded replay contract, excluding raw provider messages and scrubbing process/provider text."""
        fields = ("status", "text", "partial", "usage", "cause", "detail", "thread_id", "drafts", "exit_code",
                  "stderr_tail", "unknown_events", "malformed_lines", "events")
        return {key: scrub(getattr(result, key)) for key in fields}

    def _replay(self, request, record):
        if record.get("fingerprint") != self.fingerprint(request) or record.get("kind") != OPERATION:
            raise Blocked("The operation id is already bound to another request.", family="operation.conflict")
        state = record.get("state")
        if state in TERMINAL and isinstance(record.get("turn"), dict):
            turn = self._turn(self._turn_evidence(self._turn(record["turn"])))
            return SendMessageResult(request.operation_id, request.message_id, request.turn_id,
                                     turn.status, turn, True, request.conversation_id)
        if state in TERMINAL and isinstance(record.get("error"), dict):
            turn = TurnResult()
            turn.cause = live.scrub(str(record["error"].get("message") or "The operation failed."))
            return SendMessageResult(request.operation_id, request.message_id, request.turn_id,
                                     "failed", turn, True, request.conversation_id)
        turn = TurnResult()
        turn.cause = "The previous operation has no terminal record; inspect it before retrying with a new operation id."
        return SendMessageResult(request.operation_id, request.message_id, request.turn_id,
                                 "indeterminate", turn, True, request.conversation_id)

    @contextmanager
    def _tool_admission(self, request):
        """Keep pre-effect refusals without claiming/overwriting the rejected operation id.

        Only a live application-issued capability can link a refusal to an owner turn. Repeated
        identical refusals in that turn share one record; the original bridge exception still escapes.
        """
        identity = None
        if self.controller is not None and isinstance(request, dict):
            _, identity = self.controller._binding(request.get("turn"))
        try:
            yield
        except Blocked as error:
            if identity and identity.get("parent_operation_id"):
                failure = scrub({"family": error.family, "message": str(error)})
                detail = scrub({"request_id": request.get("id")})
                tool = scrub(str(request.get("tool")))
                with self._locked():
                    repeated = any(
                        row.get("kind") == "architect_tool_refusal"
                        and row.get("parent_operation_id") == identity["parent_operation_id"]
                        and row.get("turn_id") == identity["turn_id"]
                        and row.get("result", {}).get("tool") == tool
                        and row.get("result", {}).get("detail") == detail
                        and row.get("result", {}).get("error") == failure
                        for row in self._records())
                    if not repeated:
                        record = {"operation_id": uuid.uuid4().hex, "kind": "architect_tool_refusal",
                                  "tool": tool, "state": "terminal", "created_at": self._stamp(),
                                  **{key: identity[key] for key in
                                     ("parent_operation_id", "conversation_id", "turn_id")}}
                        result = self._tool_result(record, "failed/refused", detail=detail, error=failure)
                        self._append(dict(record, result=asdict(result)))
            raise

    def tool_request(self, request):
        """Claim a bridge id durably before posting its effect to the existing serialized controller.

        The token is an application-issued capability, not an origin supplied in model arguments.
        Its digest binds replay even after expiry/reopen; raw capabilities never enter the journal.
        """
        with self._tool_admission(request):
            if not isinstance(request, dict):
                raise Blocked("A bridge request object is required.", family="architect.request_invalid")
            rid, tool, args = request.get("id"), request.get("tool"), request.get("args")
            if not isinstance(rid, str) or not 0 < len(rid) <= bridge.MAX_ID or not isinstance(tool, str):
                raise Blocked("A valid bridge request id and tool are required.", family="architect.request_invalid")
            token = request.get("turn")
            capability = hashlib.sha256(token.encode()).hexdigest() if isinstance(token, str) else None
            try:
                payload = json.dumps({"kind": "architect_tool", "tool": tool, "args": args,
                                      "capability": capability}, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"))
            except (TypeError, ValueError) as error:
                raise Blocked("Tool arguments must be JSON data.", family="architect.request_invalid") from error
            args = json.loads(payload)["args"]  # isolate queued execution from later caller mutation
            fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            with self._locked():
                existing = self._latest(rid)
                if existing is not None:
                    if existing.get("fingerprint") != fingerprint or existing.get("kind") != "architect_tool":
                        raise Blocked("The operation id is already bound to another request.", family="operation.conflict")
                    if existing.get("state") == "terminal" and isinstance(existing.get("result"), dict):
                        return ToolResult.restore(existing["result"], replayed=True)
                    active = self.controller is not None and any(
                        item["id"] == rid and item["state"] != "done" for item in self.controller._registry.snapshot())
                    return self._tool_result(existing, "running" if active else "indeterminate", replayed=True)
                if self.controller is None:
                    raise Blocked("The live Controller is unavailable.", family="architect.controller_unavailable")
                binding, message = self.controller._binding(token)
                identity = message or {}
                record = {"operation_id": rid, "kind": "architect_tool", "fingerprint": fingerprint,
                          "tool": tool, "state": "running", "created_at": self._stamp(),
                          "binding": binding, "parent_operation_id": identity.get("parent_operation_id"),
                          "conversation_id": identity.get("conversation_id"), "turn_id": identity.get("turn_id"),
                          "subject": scrub({key: value for key, value in (args.items() if isinstance(args, dict) else ())
                                            if key in ("revision", "milestone", "run_id")})}
                self._append(record)

        def complete(ok, error):
            detail = scrub(ok) if isinstance(ok, dict) else {}
            category = "failed/refused" if error else "completed"
            if (detail.get("kind") in ("refused", "conflict", "overlap")
                    or detail.get("dispatch", {}).get("outcome") in ("failed", "stale")):
                category = "failed/refused"
            if detail.get("status") in ("awaiting_owner", "unsent", "blocked") or detail.get("kind") == "open":
                category = "awaiting_owner"
            subject = dict(record["subject"])
            subject.update({key: detail[key] for key in ("revision", "milestone", "run_id") if key in detail})
            decision = (ToolDecision(tool.removeprefix("zplan_"), subject, detail.get("request"))
                        if category == "awaiting_owner" else None)
            result = self._tool_result(dict(record, subject=subject), category, detail=detail,
                                       error=scrub(error), decision=decision)
            with self._locked():
                self._append(dict(record, state="terminal", updated_at=self._stamp(), result=asdict(result)))
            return result

        if not isinstance(args, dict):
            return complete(None, {"family": bridge.INVALID, "message": "Tool arguments must be an object."})
        if tool == "zplan_status":
            return complete(self.controller._bridge_status(), None)
        # Completion runs on the controller worker, even if the socket wait timed out.
        # If terminal persistence fails, the running record stays indeterminate. Never re-execute it.
        self.controller._bridge_action(rid, tool, args, token, complete=complete, application=self,
                                       admitted_binding=(binding, message))
        with self._locked():
            latest = self._latest(rid)
        if latest.get("state") == "terminal" and isinstance(latest.get("result"), dict):
            return ToolResult.restore(latest["result"])
        active = any(item["id"] == rid and item["state"] != "done" for item in self.controller._registry.snapshot())
        return self._tool_result(record, "running" if active else "indeterminate")

    @staticmethod
    def _tool_result(record, category, **fields):
        return ToolResult(record["operation_id"], record["tool"], category,
                          record.get("parent_operation_id"), record.get("conversation_id"), record.get("turn_id"),
                          scrub(record.get("subject", {})), **fields)

    @staticmethod
    def prepare_tool(app):
        # Same feed/store used by later TUI event turns and the durable replan brake.
        feed.bootstrap(app.authority)

    def advance_plan(self, app, outcome):
        """Worker-only initial advancement. No screen, event pump, verification or merge.

        Planning/engine own dispatch uncertainty and the receipt. One bounded watch slice reuses
        that contract; a later observation may continue it, but a replay never invokes this method.
        """
        if outcome.kind == "stale":
            # Refuse before dispatch, through the same error/result path as other revised-plan actions.
            raise Blocked("The plan was revised: it was not sent.", family="action.refused")
        if outcome.kind != "ready":
            return {"state": "awaiting_owner", "checks": [asdict(item) for item in outcome.checks]}
        lines = []
        # A strictly positive slice is essential: the engine treats zero as an unbounded watch.
        result = app.planning.watch(lines.append, slice=1.0).step()
        current = app.authority.current
        return {"state": "active_run" if result == "continue" else "idle", "outcome": result,
                "revision": current["version"], "run_id": current.get("run_id"),
                "status": current["status"], "lines": lines}

    def accept_message(self, request):
        """Durably accept UI input before returning accepted, without starting provider work.

        No recovery path automatically sends accepted records. A crashed admission is indeterminate;
        only a complete accepted record can be explicitly dispatched with this exact request.
        """
        self._validate(request)
        fingerprint = self.fingerprint(request)
        with self._locked(wait=False):
            existing = self._latest(request.operation_id)
            if existing is not None:
                return self._replay(request, existing)
            if self._torn_tail:
                raise Blocked("The operation journal has an incomplete final record.",
                              family="operation.store_invalid")
            record = {"operation_id": request.operation_id, "kind": OPERATION, "fingerprint": fingerprint,
                      "state": "accepting", "created_at": self._stamp(),
                      "request": {"message_id": request.message_id, "project_id": request.project_id,
                                  "conversation_id": request.conversation_id, "turn_id": request.turn_id,
                                  "text": request.text, "snapshot": request.snapshot}}
            self._append(record)
            self.store.append("owner", text=request.text, id=request.message_id, project_id=request.project_id,
                              conversation_id=request.conversation_id, turn_id=request.turn_id,
                              operation_id=request.operation_id)
            self._append(dict(record, state="accepted"))

    def send_message(self, request, runner=None, on_event=None, turn=None, prepared_runner=None):
        """Persist an owner message before the provider call and exactly once for a durable operation id.

        `prepared_runner(token)` lets the TUI reserve its adapter for cancellation and rendering, with the
        application-issued owner capability. `runner()` remains the legacy adapter boundary. Without either,
        Architect.send reserves/releases itself. A terminal replay calls none of them.
        """
        submission = request if isinstance(request, MessageSubmission) else None
        snapshot = None
        if submission is not None:
            if (not isinstance(submission.operation_id, str) or not 0 < len(submission.operation_id) <= 128
                    or not submission.operation_id.strip()):
                raise Blocked("A submission id of 1-128 characters is required.", family="operation.invalid_request")
            if not isinstance(submission.text, str) or not submission.text.strip():
                raise Blocked("Empty message to the architect.", family="architect.empty_message")
            with self._locked():
                existing = self._latest(submission.operation_id)
                if existing is not None:
                    return self._replay(self._resolve_submission(submission, existing), existing)
                if self._torn_tail:
                    raise Blocked("The operation journal has an incomplete final record.",
                                  family="operation.store_invalid")
            # Never wait on the controller while holding the journal lock: a queued tool's completion
            # may need it. The final lock below rechecks novelty before creating identities or effects.
            snapshot = self.controller.request_snapshot() if self.controller is not None else None
        else:
            self._validate(request)
        with self._locked():
            existing = self._latest(request.operation_id)
            if submission is not None:
                if existing is not None:
                    return self._replay(self._resolve_submission(submission, existing), existing)
                if self._torn_tail:
                    raise Blocked("The operation journal has an incomplete final record.",
                                  family="operation.store_invalid")
                request = SendMessageRequest(submission.operation_id, uuid.uuid4().hex,
                                             project_key(self.store.project), self._conversation_id(),
                                             uuid.uuid4().hex, submission.text, snapshot)
                self._validate(request)
            fingerprint = self.fingerprint(request)
            if existing is not None:
                replay = self._replay(request, existing)  # validates the idempotency binding, even for accepted input
                if existing.get("state") != "accepted":
                    return replay
            if self._torn_tail:
                raise Blocked("The operation journal has an incomplete final record. Preserve it and inspect the "
                              "interrupted operation before recovery; no new operation was sent.",
                              family="operation.store_invalid")
            self._append({"operation_id": request.operation_id, "kind": OPERATION, "fingerprint": fingerprint,
                          "state": "running", "created_at": self._stamp(),
                          "request": {"message_id": request.message_id, "project_id": request.project_id,
                                      "conversation_id": request.conversation_id, "turn_id": request.turn_id,
                                      "text": request.text, "snapshot": request.snapshot}})
            if existing is None:
                self.store.append("owner", text=request.text, id=request.message_id, project_id=request.project_id,
                                  conversation_id=request.conversation_id, turn_id=request.turn_id,
                                  operation_id=request.operation_id)
        # The durable running record claims this id. Do not hold the journal lock during provider work:
        # another window must be able to save input, and a replay must remain indeterminate, not resend.
        token = None
        try:
            begin = getattr(self.owner_port, "begin_turn", None)
            if begin is not None:
                occurrence = next((i for i, row in enumerate(self.store.transcript())
                                   if row.get("id") == request.message_id and row.get("role") == "owner"), None)
                if occurrence is None:
                    raise Blocked("The accepted owner message is missing from the transcript.",
                                  family="operation.store_invalid")
                identity = {"parent_operation_id": request.operation_id, "conversation_id": request.conversation_id,
                            "turn_id": request.turn_id, "message_id": request.message_id,
                            "shown_plan": shown_plan(request.snapshot)}
                # Legacy feed adapters keep their two-argument port; the real controller binds durable ids.
                token = begin(request.text, occurrence, identity=identity) if self.controller is not None else begin(
                    request.text, occurrence)
            if self.architect is None:
                self.architect = self.prepare_architect(self.store.project)
            if self.controller is not None:
                self.architect.controller = bridge.path_for(self.controller.project)
            if prepared_runner is not None:
                result = prepared_runner(token)
            elif runner is None:
                result = self.architect.send(request.text, snapshot=request.snapshot, on_event=on_event,
                                             role="owner", turn=token if self.owner_port is not None else turn,
                                             recorded=True, turn_id=request.turn_id)
            else:
                result = runner()
        except Exception as error:
            family = getattr(error, "family", None)
            message = live.scrub((family + ": " if family else "") + str(error))[:1000]
            self.store.append("error", status="failed", text=message, partial="",
                              turn_id=request.turn_id, operation_id=request.operation_id)
            with self._locked():
                self._append({"operation_id": request.operation_id, "kind": OPERATION, "fingerprint": fingerprint,
                              "state": "failed", "updated_at": self._stamp(),
                              "error": {"type": type(error).__name__, "message": message}})
            if submission is not None:
                # Automation must aggregate the durable failure with any already-dispatched children.
                # Keep the explicit TUI request's exception contract; persistence failures above still raise.
                failed = TurnResult()
                failed.cause = message
                return SendMessageResult(request.operation_id, request.message_id, request.turn_id,
                                         "failed", failed, conversation_id=request.conversation_id)
            raise
        finally:
            if token is not None:
                self.owner_port.end_turn(token)
        data = self._turn_evidence(result)
        state = "completed" if result.status == "completed" else "failed"
        with self._locked():
            self._append({"operation_id": request.operation_id, "kind": OPERATION, "fingerprint": fingerprint,
                          "state": state, "updated_at": self._stamp(), "turn": data})
        return SendMessageResult(request.operation_id, request.message_id, request.turn_id,
                                 result.status, result, conversation_id=request.conversation_id)

    def message_outcome(self, result):
        """Common send-only projection. Model completion never hides a linked tool outcome.

        Aggregate over ALL children before bounding presentation. No verification or merge is performed
        by this operation, regardless of what a model says. Reopening never replays child effects.
        """
        latest = {}
        with self._locked():
            for record in self._records():
                if (record.get("parent_operation_id") == result.operation_id
                        and record.get("kind") in ("architect_tool", "architect_tool_refusal")):
                    latest[record["operation_id"]] = record
        active = {item["id"] for item in self.controller._registry.snapshot() if item["state"] != "done"} if self.controller else set()
        children = []
        for record in latest.values():
            if record.get("state") == "terminal" and isinstance(record.get("result"), dict):
                child = ToolResult.restore(record["result"], replayed=result.replayed)
            else:
                child = self._tool_result(record, "running" if record["operation_id"] in active else "indeterminate",
                                          replayed=result.replayed)
            children.append(child)
        categories = {child.category for child in children}
        # A completed tool call can have successfully dispatched a still-running engine graph.
        # Initial dispatch is not observation-to-completion; preserve that uncertainty in the aggregate.
        if any(child.detail.get("dispatch", {}).get("state") == "active_run" for child in children):
            categories.add("running")
        if result.status in ("running", "indeterminate", "accepted", "accepting") or categories & {"running", "indeterminate"}:
            code, outcome = 3, "indeterminate"
        elif "awaiting_owner" in categories:
            code, outcome = 4, "awaiting_owner"
        elif result.status != "completed" or categories - {"completed"}:
            code, outcome = 1, "failed"
        else:
            code, outcome = 0, "completed"
        model = {"status": result.status}
        for name, value in (("response", result.turn.text), ("partial", result.turn.partial),
                            ("failure", result.turn.cause), ("detail", result.turn.detail)):
            if value:
                model[name] = scrub(str(value))[:16000 if name in ("response", "partial") else 2000]
        shown = []
        for child in children[:32]:
            data = scrub(asdict(child))
            if len(json.dumps(data, ensure_ascii=False).encode("utf-8")) > 4096:
                data = {"operation_id": scrub(child.operation_id)[:128], "category": child.category,
                        "truncated": True}
            shown.append(data)
        return scrub({"operation_id": result.operation_id, "message_id": result.message_id,
                      "conversation_id": result.conversation_id, "turn_id": result.turn_id,
                      "replayed": result.replayed, "model": model, "outcome": outcome, "exit_code": code,
                      "children": shown, "children_omitted": max(0, len(children) - len(shown)),
                      "verification": {"state": "not_run"}, "merge": {"state": "not_requested"}})
