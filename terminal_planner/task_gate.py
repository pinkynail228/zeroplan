"""Task gate core (G2-start): the pure artifact projection, gate identity and output parsing.

The record slice of the task gate (0.5 item S1a, s1a1b1): the durable record in `state["gates"]`, its strict
validation, the evidence an override binds, and the pure artifact projection, gate identity and output parser the
first slice defined. The start barrier, the validity predicate and the override are the next slice; the UI/CLI
adapters and the docs the third. Guarding the lifecycle still stays with the plan gate's `process.unbuilt` until
that barrier lands, so no intermediate state lets an unguarded required start through.

The artifact is the pure projection of the *validated* `Runs.bootstrap_manifest(baseline, context)` the pending
start already uses (accepted candidate changes and owner notes included). Only the fields that cannot change the
work a start performs are excluded: the manifest's `plan_revision`, its `progress` and `outcome`, and inside the
baseline its own `plan_revision` and `limits`. HEAD is tracked separately as `head` and the resolved configuration
- limits included - as `resolved_config_digest`; `identity_matches` compares all three."""

import copy
import re
import uuid

from . import toolchain
from .authority import (Blocked, canonical, decode, digest, nonempty, override_matches, read_discussion,
                        require, validate_receipt)

SCHEMA = "1"
DEFAULT_ROUNDS = 2  # limits.task_rounds of the frozen preset (process.py PRESETS)
SUBJECT = "task checks"
SIZE = "medium"  # the runtime's own `size`, the one `task_gate_runtime` freezes into the documents (R-3/R-4)
UNPRINTABLE = "Invalid task check result: it cannot be saved to the store."
# R-4 input domain names the nesting depths 1, 400, 500 and 5000; a payload deeper than the deepest of them is
# never retained, because "reloadable" has to hold for the reader recursion budget too, not only for the writer:
# Python json reader gives up at a depth that depends on the interpreter and on how deep the call already is, so
# no fixed probe of it can be trusted at any depth.
OUTPUT_NESTING_LIMIT = 5000
FIELDS = ("schemaVersion", "taskVerdict", "taskFindings", "taskResponse", "discussion")
IDENTITY_FIELDS = ("artifact_digest", "resolved_config_digest", "head")
EXCLUDED = ("plan_revision", "progress", "outcome")
EXCLUDED_BASELINE = ("plan_revision", "limits")


def artifact(manifest):
    """The artifact a task gate reviews: the validated bootstrap manifest without the plan revision, the
    destination baseline's own plan_revision and limits, the progress and the outcome."""
    value = copy.deepcopy(manifest)
    for name in EXCLUDED:
        del value[name]
    for name in EXCLUDED_BASELINE:
        del value["baseline"][name]
    return value


def artifact_digest(manifest):
    """The digest of the projected artifact, through the shared `digest()`."""
    return digest(artifact(manifest))


def identity(artifact_sha, resolved_config_digest, head):
    """The (artifact, resolved configuration, HEAD) identity a gate is bound to; `head` is the destination
    commit at gate start."""
    return {"artifact_digest": artifact_sha, "resolved_config_digest": resolved_config_digest, "head": head}


def identity_matches(gate_identity, live):
    """True only when the gate's artifact, resolved configuration (rules included) and HEAD all equal the live
    ones. Pure: it reads neither the store nor the repository."""
    return all(gate_identity.get(name) == live.get(name) for name in IDENTITY_FIELDS)


def persistable(value):
    """True when `value` survives the store's own round trip -- the bytes `canonical` writes for it, in UTF-8, read
    back by the store's own `decode` (R-5). A JSON-escaped lone surrogate decodes to a character the writer cannot
    encode, and a payload nested past the *reader's* recursion limit can be written but never read back; either way
    evidence holding it can never be persisted and must be refused here rather than crash the writer or leave a
    store the reader refuses."""
    try:
        text = canonical(value)
        text.encode("utf-8")
        decode(text)
    except (UnicodeError, TypeError, ValueError, RecursionError, Blocked):
        return False
    return True


def too_deep(value, limit=OUTPUT_NESTING_LIMIT):
    """True when `value` nests more than `limit` containers deep (R-4/R-5). Scalars add no level, so a payload of
    exactly `limit` nested lists is not too deep. Iterative on purpose: measuring a hostile depth must not raise the
    very `RecursionError` it exists to avoid."""
    pending = [(value, 0)]
    while pending:
        node, depth = pending.pop()
        if not isinstance(node, (dict, list, tuple)):
            continue
        if depth + 1 > limit:
            return True
        children = node.values() if isinstance(node, dict) else node
        pending.extend((child, depth + 1) for child in children)
    return False


def escaped(text):
    """`text` as the store can hold it: an unpaired surrogate becomes its JSON escape, never a lost byte."""
    return text.encode("utf-8", "backslashreplace").decode("utf-8")


def submitted_title(milestone):
    """The run title `gate_run` submits (R-4), in the one place the observation's projection check reads too."""
    return "Task gate %s" % milestone


def read_review(output, rounds_limit=DEFAULT_ROUNDS):
    """(verdict, findings, response, discussion) of a completed task-gate output. The output shape is checked here
    and the bounded discussion is parsed by the shared plan-gate parser, whose refusal names this gate's subject. The
    evidence itself must be persistable: a decoded lone surrogate is refused (R-5), never written into the store."""
    require(isinstance(output, dict) and set(output) == set(FIELDS) and all(isinstance(output[k], str) for k in FIELDS)
            and output["schemaVersion"] == SCHEMA, "Malformed completed task gate output.")
    require(output["taskVerdict"] in {"accepted", "rejected"}, "Unsupported task gate verdict.")
    final = (output["taskVerdict"], output["taskFindings"], output["taskResponse"])
    discussion = read_discussion(output["discussion"], rounds_limit, final, SUBJECT)
    require(persistable(final) and persistable(discussion), UNPRINTABLE)
    return final + (discussion,)

# The durable gate record (R-2): one entry in `state["gates"]`, never rewritten in place. The statuses are the
# plan submission protocol's plus the gate's own terminal states; a record is `preparing` before its read-only
# checkout is made, `submission_unknown` while the detach receipt is missing, and a terminal status once the
# native run ended. Only `concluded` carries a usable verdict; `native_failed` and `output_invalid` are distinct.
GATE = "task"
STATUSES = ("preparing", "submission_unknown", "observing", "detached", "observation_blocked")
TERMINAL = ("concluded", "native_failed", "output_invalid")
CRITIC_VERDICTS = ("accepted", "rejected")
DOCUMENTS = ("graph", "runtime", "input")
RECORD_KEYS = frozenset({"gate", "id", "plan_revision", "approval", "milestone", "context", "identity", "config",
                         "rounds_limit", "documents", "binding", "submission_key", "status", "run_id", "receipt",
                         "terminal", "output_digest", "rounds_used", "discussion", "critic_verdict", "override",
                         "diagnostic", "created", "updated"})
EVIDENCE_KEYS = ("gate", "id", "plan_revision", "approval", "milestone", "identity", "rounds_used", "rounds_limit",
                 "discussion", "critic_verdict", "output_digest")
HEX = re.compile(r"[0-9a-f]{64}")
SHA = re.compile(r"[0-9a-f]{40}")
UUID4 = r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"  # version 4, RFC 4122 variant
ID = re.compile(r"task-gate-" + UUID4)
KEY = re.compile(r"zplan-gate-" + UUID4)
INVALID = "Invalid task check record; store rejected."


def terminal(status):
    """True for the statuses that end a record's lifecycle; only a rerun appends a new record."""
    return status in TERMINAL


def freezes(documents):
    """The digests a record stores for its three documents (R-2): the values themselves are never persisted."""
    return {name: digest(value) for name, value in documents.items()}


def record(plan_revision, approval, milestone, context, identity, config, documents, binding):
    """A new task-gate record (R-2) in status `preparing`: the identity triple, the frozen resolved configuration,
    the documents and the binding are taken once; every field a later status fills starts empty or None."""
    from .runs import now  # function-level import: runs imports engine, which imports this module
    stamp = now()
    return {"gate": GATE, "id": "task-gate-" + str(uuid.uuid4()), "plan_revision": plan_revision,
            "approval": approval, "milestone": milestone, "context": copy.deepcopy(context), "identity": identity,
            "config": copy.deepcopy(config), "rounds_limit": config["limits"]["task_rounds"],
            "documents": freezes(documents), "binding": binding,
            "submission_key": "zplan-gate-" + str(uuid.uuid4()), "status": "preparing", "run_id": None,
            "receipt": None, "terminal": None, "output_digest": None, "rounds_used": None, "discussion": None,
            "critic_verdict": None, "override": None, "diagnostic": "", "created": stamp, "updated": stamp}


def evidence(record):
    """The dict an override digest binds (`override_matches`): the record's identity, its verdict and its evidence."""
    return {key: copy.deepcopy(record[key]) for key in EVIDENCE_KEYS}


def concluded(record, terminal):
    """The one terminal outcome of one gate run (R-4), written into `record` exactly as `validate_gates` reads it
    back. A failed native run is `native_failed` -- its reason escaped when the store cannot hold it -- and a
    succeeded one is `concluded` only when its output parses to persistable evidence. A refused output is
    `output_invalid` with no verdict, no discussion and no round count; an output the store cannot hold at all --
    not writable, not readable, or nested past `OUTPUT_NESTING_LIMIT` -- leaves no terminal either, because the
    record must stay loadable (R-5)."""
    if terminal.get("status") != "succeeded":
        reason = escaped(str(terminal.get("reason", "")))
        record.update(status="native_failed", terminal={"status": "failed", "reason": reason}, diagnostic=reason)
        return record
    output = terminal["output"]
    record["terminal"] = {"status": "succeeded", "output": output}
    # R-5: the record is written as one entry of `state["gates"]`, so the output must survive the store's own round
    # trip at that depth -- a surrogate, or a nesting the writer or the reader cannot walk, is refused here rather
    # than crashing the write or leaving a store the reader refuses. The round trip runs on the whole record because
    # wrapping the output adds the depth of its envelope, and `digest` of an unwalkable output would raise the same
    # recursion; the nesting bound keeps the store shallow enough that the reader's own budget -- which depends on
    # the interpreter and on the calling stack -- cannot be smaller than the writer's.
    if not persistable({"gates": [record]}) or too_deep(output):
        record.update(status="output_invalid", terminal=None, output_digest=None, critic_verdict=None,
                      discussion=None, rounds_used=None, diagnostic=UNPRINTABLE)
        return record
    record["output_digest"] = digest(output)
    try:
        verdict, findings, _, discussion = read_review(output, record["rounds_limit"])
    except Blocked as error:
        record.update(status="output_invalid", critic_verdict=None, discussion=None, rounds_used=None,
                      diagnostic=str(error))
        return record
    record.update(status="concluded", critic_verdict=verdict, discussion=discussion,
                  rounds_used=len(discussion["rounds"]), diagnostic=findings)
    return record


def validate_gates(state):
    """R-5: strict validation of `state["gates"]` on every load. An unknown or missing key, a bad enum, a duplicate
    id, inconsistent terminal fields, a record that does not belong to its own approved revision and milestone, a
    binding that does not match the store's namespace (a fixture binding in a production store or a native one in a
    fixture store), an ill-shaped context and an ill-shaped override all refuse the whole store. A record whose
    persisted evidence contradicts its own terminal output is malformed too, and every malformed shape is
    `store.invalid`, never a crash."""
    gates = state.get("gates")
    require(isinstance(gates, list) and gates, INVALID)
    ids = set()
    for entry in gates:
        try:
            validate_gate(state, entry, ids)
        except Blocked:
            raise
        except (KeyError, TypeError, ValueError, AttributeError, RecursionError) as error:
            # R-5: a record whose shape makes a check itself raise -- an unhashable or non-string context kind, an
            # unpaired surrogate JSON-escaped into an output -- refuses the whole store exactly like a wrong value,
            # never a crash.
            raise Blocked(INVALID, family="store.invalid") from error


def validate_gate(state, entry, ids):
    from .process import complete  # function-level: process imports authority only
    from .runs import validate_terminal  # function-level: see `record`
    require(isinstance(entry, dict) and set(entry) == RECORD_KEYS, INVALID)
    # R-5: the record is read from the very bytes `canonical` writes, so a string the store cannot hold (a decoded
    # lone surrogate) refuses the whole store instead of crashing the next writer.
    require(persistable(entry), INVALID)
    require(entry["gate"] == GATE, INVALID)
    require(isinstance(entry["id"], str) and ID.fullmatch(entry["id"]) and entry["id"] not in ids, INVALID)
    ids.add(entry["id"])
    # R-2: the record names its own approved revision and a milestone of that revision; a wrong approval, an
    # absent revision and an absent milestone are malformed.
    require(type(entry["plan_revision"]) is int and 1 <= entry["plan_revision"] <= len(state["revisions"]), INVALID)
    revision = state["revisions"][entry["plan_revision"] - 1]
    require(revision.get("status") == "approved" and entry["approval"] == revision.get("approval"), INVALID)
    proposal = revision.get("proposal")
    milestones = proposal.get("milestones") if isinstance(proposal, dict) else None
    require(isinstance(entry["milestone"], str) and nonempty(entry["milestone"]) and isinstance(milestones, list)
            and any(isinstance(m, dict) and m.get("id") == entry["milestone"] for m in milestones), INVALID)
    validate_context(entry["context"])
    identity = entry["identity"]
    require(isinstance(identity, dict) and set(identity) == set(IDENTITY_FIELDS)
            and all(isinstance(identity[key], str) and HEX.fullmatch(identity[key]) for key in
                    ("artifact_digest", "resolved_config_digest"))
            and isinstance(identity["head"], str) and SHA.fullmatch(identity["head"]), INVALID)
    require(contextual_digest(entry, proposal) == identity["artifact_digest"], INVALID)
    config = entry["config"]
    try:
        complete(config)
    except (ValueError, Blocked) as error:
        raise Blocked(INVALID, family="store.invalid") from error
    require(type(entry["rounds_limit"]) is int and type(config["limits"]["task_rounds"]) is int
            and entry["rounds_limit"] == config["limits"]["task_rounds"], INVALID)
    require(isinstance(entry["documents"], dict) and set(entry["documents"]) == set(DOCUMENTS)
            and all(isinstance(v, str) and HEX.fullmatch(v) for v in entry["documents"].values()), INVALID)
    validate_binding(state, entry["binding"])
    require(isinstance(entry["submission_key"], str) and KEY.fullmatch(entry["submission_key"]), INVALID)
    validate_status(entry, validate_terminal)
    validate_override(entry)
    require(isinstance(entry["diagnostic"], str), INVALID)
    require(isinstance(entry["created"], str) and isinstance(entry["updated"], str), INVALID)


def validate_context(context):
    """The effective owner context of a gate (R-2): None, or the `{kind, source, text, candidate}` answer/candidate
    shape `runs` freezes for a start (`CONTEXTS`; its `bootstrap_manifest` reads the same fields). The kind is a
    string of the closed set and a proposal's candidate a dict, so nothing unhashable reaches a lookup (R-5)."""
    if context is None:
        return
    from .runs import CONTEXTS  # function-level: runs imports engine, which imports this module
    require(isinstance(context, dict) and set(context) == {"kind", "source", "text", "candidate"}
            and isinstance(context["kind"], str) and context["kind"] in CONTEXTS
            and type(context["source"]) is int and nonempty(context["text"])
            and (context["candidate"] is None or isinstance(context["candidate"], dict))
            and (context["candidate"] is None) == (context["kind"] == "answer"), INVALID)
    if context["kind"] == "proposal":
        validate_candidate(context["candidate"])


def validate_candidate(candidate):
    """A proposal context's candidate is exactly the `{"tasks", "amendments"}` task list `runs.structured` accepts
    (R-2/R-5): the closed shape is checked here because `bootstrap_manifest` reads only those two keys, so nothing
    else would refuse an extra one."""
    from .runs import structured  # function-level: runs imports engine, which imports this module
    try:
        require(isinstance(candidate, dict) and persistable(candidate)
                and structured(canonical(candidate)) is not None, INVALID)
    except (TypeError, ValueError, RecursionError) as error:
        raise Blocked(INVALID, family="store.invalid") from error


def contextual_digest(entry, proposal):
    """The artifact digest the record's own revision, milestone and context reproduce (R-2): a context whose
    candidate is not a well-formed task list of that milestone, or whose references do not resolve, is
    `store.invalid` -- never another family and never a crash (R-5)."""
    from . import milestone  # function-level: milestone imports authority only
    from .runs import bootstrap_manifest  # function-level: see `record`
    try:
        baseline, _ = milestone.build_manifest(proposal, entry["milestone"], entry["plan_revision"])
        return artifact_digest(bootstrap_manifest(baseline, entry["context"]))
    except (Blocked, KeyError, TypeError, ValueError, AttributeError, RecursionError) as error:
        raise Blocked(INVALID, family="store.invalid") from error


def validate_status(entry, validate_terminal):
    """The status and the terminal fields must agree (R-2): a record before dispatch has no run id or receipt, a
    dispatched one has a receipt naming its run id, and a terminal one carries the terminal result whose status
    matches (`native_failed` failed, `concluded`/`output_invalid` succeeded) with `output_digest` exactly its
    output. A `concluded` record's persisted verdict, discussion and round count must equal -- type-preservingly,
    compared by its own serialization because Python's `==` cannot tell `true` from `1` or `1.0` -- what its own
    output parses to, and an `output_invalid` record's output must be the one the parser refuses: evidence never
    contradicts the record it belongs to. An `output_invalid` record may carry no terminal at all: an output the
    store cannot hold is never written (R-5), so only its refusal is kept."""
    status, run_id, receipt, terminal_result = entry["status"], entry["run_id"], entry["receipt"], entry["terminal"]
    require(status in STATUSES + TERMINAL, INVALID)
    if status in ("preparing", "submission_unknown"):
        require(run_id is None and receipt is None and terminal_result is None, INVALID)
    elif status in ("observing", "detached", "observation_blocked"):
        require(nonempty(run_id) and receipt is not None and terminal_result is None, INVALID)
    else:
        require(nonempty(run_id) and receipt is not None, INVALID)
        if terminal_result is None:
            require(status == "output_invalid" and entry["output_digest"] is None, INVALID)
        else:
            require(isinstance(terminal_result, dict), INVALID)
            validate_terminal(terminal_result)
            require(terminal_result["status"] == ("failed" if status == "native_failed" else "succeeded"), INVALID)
    if receipt is not None:
        validate_receipt(receipt)
        require(receipt.get("runId") == run_id, INVALID)
    succeeded = isinstance(terminal_result, dict) and terminal_result.get("status") == "succeeded"
    require(entry["output_digest"] == (digest(terminal_result["output"]) if succeeded else None), INVALID)
    if status == "concluded":
        require(entry["critic_verdict"] in CRITIC_VERDICTS, INVALID)
        verdict, _, _, discussion = parse_evidence(entry)
        require(verdict == entry["critic_verdict"] and canonical(discussion) == canonical(entry["discussion"]),
                INVALID)
        require(type(entry["rounds_used"]) is int and entry["rounds_used"] == len(discussion.get("rounds", ())),
                INVALID)
    else:
        require(entry["critic_verdict"] is None and entry["discussion"] is None and entry["rounds_used"] is None,
                INVALID)
        if status == "output_invalid" and succeeded:
            try:
                read_review(terminal_result["output"], entry["rounds_limit"])
            except (Blocked, KeyError, TypeError, ValueError):
                pass
            else:
                raise Blocked(INVALID, family="store.invalid")


def parse_evidence(entry):
    """(verdict, findings, response, discussion) parsed from the record's own succeeded output under its frozen
    `rounds_limit`; a malformed output is `store.invalid`, never a crash (R-5)."""
    try:
        return read_review(entry["terminal"]["output"], entry["rounds_limit"])
    except (Blocked, KeyError, TypeError, ValueError, RecursionError) as error:
        raise Blocked(INVALID, family="store.invalid") from error


def validate_override(entry):
    """A well-formed override is accepted only on a `concluded` record whose verdict is `rejected` (R-2): the
    reason/verdict/evidence shape of `override_matches` binds exactly that record's `evidence`."""
    override = entry["override"]
    if override is None:
        return
    require(entry["status"] == "concluded" and entry["critic_verdict"] == "rejected", INVALID)
    try:
        override_matches(evidence(entry), override, verdict_field="critic_verdict", subject=SUBJECT)
    except Blocked as error:
        raise Blocked(INVALID, family="store.invalid") from error


def validate_binding(state, binding):
    """R-3: the binding must belong to the store's namespace -- a native binding (`binary_identity` plus
    `codex_home`) in a production store, exactly `{"fixture_id": ...}` in a fixture store. A binding whose shape
    makes `toolchain.valid_binding` raise (a non-dict, a missing or non-string version) is `store.invalid`, never
    a crash."""
    namespace = state.get("namespace")
    if namespace == "production":
        try:
            valid = (isinstance(binding, dict) and set(binding) == toolchain.BINDING_FIELDS | {"codex_home"}
                     and toolchain.valid_binding(binding))
        except (TypeError, ValueError, KeyError):
            valid = False
        require(valid, INVALID)
    else:
        require(isinstance(namespace, str) and namespace.startswith("fixture:"), INVALID)
        require(binding == {"fixture_id": namespace.split(":", 1)[1]}, INVALID)
