"""Merge critic core (A7b): the trigger rule, the durable record, its graph and its run.

Why: `runs.MilestoneRuns.gate_merge` (A7a) classifies the risk of a candidate; a risky merge needs a fresh critic
whose BLOCK stops it. This module is the core: it takes the risk classification and the semantic `facts` as input,
and the merge gate (`runs.py`, `delivery.py`) raises the critic and checks its record through it.

Reused from the task gate (`task_gate.py`): the durable-record validation style (a strictly validated optional
list in the store, one entry per run, never rewritten in place), the store round-trip helpers (`persistable`,
`too_deep`, `escaped`) and the namespace check of a binding (`validate_binding`). The record schema is NOT the task
gate's generalised: a task gate is bound to an approved plan revision and its repair loop, while a merge critic is
bound to the *candidate identity of one merge* and is never re-dispatched to repair a plan.

The trigger rule (`reasons`, C1) is the pure classification the wiring feeds: the tier and the path triggers come
from `process.risk_of` over the changed paths, and the three path-less preset triggers (`data_loss`, `process_kill`,
`disagreement`; process.py PRESET_V2) come from the semantic `facts` a later slice gathers -- `risk_of` matches
paths only, so it can never raise them. A fact that is omitted or `False` raises nothing; only `True` does.

The identity (C2) is the full merge identity a later `allows` compares: milestone, plan revision, attempt, the
destination ref and its base, the result and candidate commits, the candidate tree, the configuration digest, the
semantic input digest and the risk. It is stored whole in `state["critics"]` and strictly validated on every load.
"""

import copy
import re
import uuid

from . import process, task_gate
from .authority import Blocked, canonical, decode, digest, nonempty, require, validate_receipt

SCHEMA = "1"  # the critic output schemaVersion
SIZE = "medium"  # the runtime's own `size`, frozen into the documents (like `task_gate.SIZE`)
VERDICTS = ("go", "block")
STATUSES = task_gate.STATUSES  # the submission protocol's own statuses, shared with the task gate
TERMINAL = task_gate.TERMINAL
DOCUMENTS = ("graph", "runtime", "input")
# R-5 style: a record whose evidence the store cannot hold (a decoded lone surrogate, a nesting the reader cannot
# walk) is refused at the writer rather than crashing it or leaving a store the reader refuses.
UNPRINTABLE = "Invalid merge check result: it cannot be saved to the store."
# The path-less preset triggers: the /2 preset's `risk.triggers` whose `paths` are empty. `risk_of` raises a trigger
# only by path, so these three are the gatekeeper's named triggers and are raised by the semantic `facts` instead.
PRESET_TRIGGERS = tuple(t["name"] for t in process.PRESETS[process.PRESET_V2]["risk"]["triggers"] if not t["paths"])
IDENTITY_FIELDS = ("milestone", "plan_revision", "attempt", "destination", "base", "result", "candidate", "tree",
                   "config_digest", "input_digest", "risk")
RISK_FIELDS = ("tier", "triggers", "unmatched")
FIELDS = ("schemaVersion", "verdict", "findings")
RECORD_KEYS = frozenset({"id", "identity", "reasons", "binding", "documents", "submission_key", "status", "run_id",
                         "receipt", "terminal", "output_digest", "verdict", "findings", "diagnostic"})
HEX = re.compile(r"[0-9a-f]{64}")
SHA = re.compile(r"[0-9a-f]{40}")
UUID4 = r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"  # version 4, RFC 4122 variant
ID = re.compile(r"merge-critic-" + UUID4)
KEY = re.compile(r"zplan-critic-" + UUID4)
INVALID = "Invalid merge check record; store rejected."


def reasons(risk, facts):
    """The sorted trigger names of one merge (C1): `tier:high` for a high tier, every matched path trigger of
    `risk` and every path-less preset trigger `facts` marks true. `facts` is the semantic input the wiring gathers; a
    path-less trigger it omits or marks `False` is not raised, so a low-risk merge with no fact raises nothing."""
    found = set(risk["triggers"])
    if risk["tier"] == "high":
        found.add("tier:high")
    found.update(name for name in PRESET_TRIGGERS if facts.get(name) is True)
    return sorted(found)


def input_digest(names, paths, briefs):
    """The digest of the semantic input a critic judges besides the pinned identity: the reasons, the changed paths
    and the milestone's frozen briefs. Bound into the identity so a changed brief or path set voides a stale `go`."""
    return digest({"reasons": list(names), "paths": list(paths), "briefs": briefs})


def freezes(documents):
    """The digests a record stores for its three documents; the values themselves are never persisted."""
    return {name: digest(value) for name, value in documents.items()}


def submitted_title(candidate):
    """The run title `critic_run` submits, in the one place the observation's projection check reads too."""
    return "Merge critic %s" % candidate[:12]


def terminal(status):
    """True for the statuses that end a record's lifecycle; only a rerun appends a new record."""
    return status in TERMINAL


def persistable(record):
    """True while `record` survives the store's own round trip as one entry of `state["critics"]` (R-5 style),
    reusing the task gate's store round-trip check at the critics envelope depth."""
    return task_gate.persistable({"critics": [record]})


def record(identity, names, binding, documents):
    """A new merge-critic record in status `preparing`: the identity, the reasons, the frozen documents' digests and
    the binding are taken once; every field a later status fills starts empty or None. The input document must
    describe exactly this identity and these reasons, and its paths and briefs must be the ones `input_digest` bound
    into the identity: a `go` on one candidate's input can never allow another identity."""
    require(described(identity, names, documents), "The merge check input does not match its identity.",
            family="engine.intent_changed")
    return {"id": "merge-critic-" + str(uuid.uuid4()), "identity": copy.deepcopy(identity), "reasons": list(names),
            "binding": copy.deepcopy(binding), "documents": freezes(documents),
            "submission_key": "zplan-critic-" + str(uuid.uuid4()), "status": "preparing", "run_id": None,
            "receipt": None, "terminal": None, "output_digest": None, "verdict": None, "findings": None,
            "diagnostic": ""}


def described(identity, names, documents):
    """True when the frozen input document judges `identity` with the reasons `names`, and its paths and briefs
    digest to the identity's `input_digest`."""
    value = documents.get("input") if isinstance(documents, dict) else None
    try:
        return (isinstance(value, dict) and value.get("identity") == canonical(identity)
                and value.get("reasons") == canonical(list(names))
                and identity.get("input_digest") == input_digest(names, decode(value["paths"]), decode(value["briefs"])))
    except (Blocked, KeyError, TypeError, ValueError):
        return False


def read_verdict(output):
    """(verdict, findings) of a completed merge-critic output. The output shape is checked here and the findings must
    be persistable: a decoded lone surrogate is refused, never written into the store."""
    require(isinstance(output, dict) and set(output) == set(FIELDS) and all(isinstance(output[k], str) for k in FIELDS)
            and output["schemaVersion"] == SCHEMA, "Malformed completed merge critic output.")
    require(output["verdict"] in VERDICTS, "Unsupported merge critic verdict.")
    require(task_gate.persistable(output["findings"]), UNPRINTABLE)
    return output["verdict"], output["findings"]


def parse_evidence(entry):
    """(verdict, findings) parsed from the record's own succeeded output; a malformed output is `store.invalid`,
    never a crash."""
    try:
        return read_verdict(entry["terminal"]["output"])
    except (Blocked, KeyError, TypeError, ValueError, RecursionError) as error:
        raise Blocked(INVALID, family="store.invalid") from error


def concluded(record, terminal_result):
    """The one terminal outcome of one critic run, written into `record` exactly as `validate_critics` reads it back.
    A failed native run is `native_failed` -- its reason escaped when the store cannot hold it -- and a succeeded one
    is `concluded` only when its output parses to a persistable verdict and findings. A refused output is
    `output_invalid` with no verdict; an output the store cannot hold at all leaves no terminal, so the record stays
    loadable."""
    if terminal_result.get("status") != "succeeded":
        reason = task_gate.escaped(str(terminal_result.get("reason", "")))
        record.update(status="native_failed", terminal={"status": "failed", "reason": reason}, output_digest=None,
                      verdict=None, findings=None, diagnostic=reason)
        return record
    output = terminal_result["output"]
    record["terminal"] = {"status": "succeeded", "output": output}
    # R-5: the record is written as one entry of `state["critics"]`, so the output must survive the store's own
    # round trip at that depth -- a surrogate, or a nesting the writer or the reader cannot walk, is refused here.
    if not persistable(record) or task_gate.too_deep(output):
        record.update(status="output_invalid", terminal=None, output_digest=None, verdict=None, findings=None,
                      diagnostic=UNPRINTABLE)
        return record
    record["output_digest"] = digest(output)
    try:
        verdict, findings = read_verdict(output)
    except Blocked as error:
        record.update(status="output_invalid", verdict=None, findings=None, diagnostic=str(error))
        return record
    record.update(status="concluded", verdict=verdict, findings=findings, diagnostic=findings)
    return record


def allows(record, identity):
    """C5: the merge is allowed by this record only for a `go` verdict and the exact identity it judged. A `block`,
    an error, no verdict yet, or any change of the identity (another candidate, tree, base, config or risk) is not
    an allowance. Pure: it reads neither the store nor the repository."""
    return record["verdict"] == "go" and record["identity"] == identity


def validate_critics(state):
    """R-5 style: strict validation of `state["critics"]` on every load. An unknown or missing key, a bad enum, a
    duplicate id, inconsistent terminal fields, a record that does not belong to its own approved revision and
    milestone, a binding that does not match the store's namespace, or a persisted verdict that contradicts its own
    terminal output refuses the whole store -- `store.invalid`, never a crash."""
    critics = state.get("critics")
    require(isinstance(critics, list) and critics, INVALID)
    ids = set()
    for entry in critics:
        try:
            validate_critic(state, entry, ids)
        except Blocked:
            raise
        except (KeyError, TypeError, ValueError, AttributeError, RecursionError) as error:
            raise Blocked(INVALID, family="store.invalid") from error


def validate_critic(state, entry, ids):
    from .runs import validate_terminal  # function-level: runs imports engine, which imports this module
    require(isinstance(entry, dict) and set(entry) == RECORD_KEYS, INVALID)
    require(persistable(entry), INVALID)
    require(isinstance(entry["id"], str) and ID.fullmatch(entry["id"]) and entry["id"] not in ids, INVALID)
    ids.add(entry["id"])
    validate_identity(state, entry["identity"])
    require(isinstance(entry["reasons"], list) and entry["reasons"] == sorted(set(entry["reasons"]))
            and all(isinstance(name, str) and nonempty(name) for name in entry["reasons"]), INVALID)
    require(isinstance(entry["binding"], dict), INVALID)
    task_gate.validate_binding(state, entry["binding"])
    require(isinstance(entry["documents"], dict) and set(entry["documents"]) == set(DOCUMENTS)
            and all(isinstance(value, str) and HEX.fullmatch(value) for value in entry["documents"].values()), INVALID)
    require(isinstance(entry["submission_key"], str) and KEY.fullmatch(entry["submission_key"]), INVALID)
    validate_status(entry, validate_terminal)
    require(isinstance(entry["diagnostic"], str), INVALID)


def validate_identity(state, identity):
    """The critic's identity must name a milestone of its own approved revision and carry a well-formed candidate,
    configuration, input and risk."""
    require(isinstance(identity, dict) and set(identity) == set(IDENTITY_FIELDS), INVALID)
    require(type(identity["plan_revision"]) is int and 1 <= identity["plan_revision"] <= len(state["revisions"]),
            INVALID)
    revision = state["revisions"][identity["plan_revision"] - 1]
    require(revision.get("status") == "approved", INVALID)
    proposal = revision.get("proposal")
    milestones = proposal.get("milestones") if isinstance(proposal, dict) else None
    require(isinstance(identity["milestone"], str) and nonempty(identity["milestone"]) and isinstance(milestones, list)
            and any(isinstance(m, dict) and m.get("id") == identity["milestone"] for m in milestones), INVALID)
    require(type(identity["attempt"]) is int and identity["attempt"] >= 1, INVALID)
    require(isinstance(identity["destination"], str) and identity["destination"].startswith("refs/heads/")
            and len(identity["destination"]) > len("refs/heads/"), INVALID)
    for name in ("base", "result", "candidate", "tree"):
        require(isinstance(identity[name], str) and SHA.fullmatch(identity[name]), INVALID)
    for name in ("config_digest", "input_digest"):
        require(isinstance(identity[name], str) and HEX.fullmatch(identity[name]), INVALID)
    validate_risk(identity["risk"])


def validate_risk(risk):
    """The risk a critic judged is exactly the `process.risk_of` shape: a tier, the sorted path triggers and the
    unmatched paths."""
    require(isinstance(risk, dict) and set(risk) == set(RISK_FIELDS), INVALID)
    require(isinstance(risk["tier"], str) and risk["tier"] in process.RISK_TIERS, INVALID)
    require(isinstance(risk["triggers"], list) and risk["triggers"] == sorted(set(risk["triggers"]))
            and all(isinstance(name, str) and nonempty(name) for name in risk["triggers"]), INVALID)
    require(isinstance(risk["unmatched"], list) and all(isinstance(path, str) for path in risk["unmatched"]), INVALID)


def validate_status(entry, validate_terminal):
    """The status and the terminal fields must agree, exactly as `task_gate.validate_status` reads its own: a record
    before dispatch has no run id or receipt, a dispatched one has a receipt naming its run id, and a terminal one
    carries the terminal result whose status matches (`native_failed` failed, `concluded`/`output_invalid`
    succeeded) with `output_digest` exactly its output. A `concluded` record's persisted verdict and findings must
    equal what its own output parses to, and an `output_invalid` record's output must be the one the parser refuses:
    the stored verdict never contradicts the terminal output it is bound to (C2)."""
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
        require(entry["verdict"] in VERDICTS and isinstance(entry["findings"], str), INVALID)
        verdict, findings = parse_evidence(entry)
        require(verdict == entry["verdict"] and findings == entry["findings"], INVALID)
    else:
        require(entry["verdict"] is None and entry["findings"] is None, INVALID)
        if status == "output_invalid" and succeeded:
            try:
                read_verdict(terminal_result["output"])
            except (Blocked, KeyError, TypeError, ValueError):
                pass
            else:
                raise Blocked(INVALID, family="store.invalid")
