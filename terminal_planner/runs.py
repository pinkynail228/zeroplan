"""Durable milestone runs: one native driver run per milestone attempt.

Records live in the locked authority store (planning.json, schema 2 `runs`). Every state
that can outlive a crash is persisted before the side effect it describes: `preparing`
before the worktree exists, `submission_unknown` before dispatch, `stopping` before
force-stop and `resume_pending` before resume. Reopening settles every active record,
each its own, and never creates a second writer for one attempt: an unknown submission is
replayed with the identical frozen documents and submission key, a pending resume is adopted
only through the native successor lineage. Several milestone attempts run at once (A9): `MAX_RUNS` bounds
how many are active, and admission keeps their write-sets pairwise disjoint.

Delivery is separate from the native lifecycle: a done attempt freezes its product tree at
acceptance, persists `exporting` before it creates the result branch, waits for the owner's
merge and is integrated only while its result commit is an ancestor of the destination branch.
A dependent milestone is ready only when every dependency is integrated into its start base.
"""

import copy
from datetime import datetime, timezone
import hashlib
import json
import os
import posixpath
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import time
import uuid

from . import checks, feed, live, merge_critic, milestone, project_read, project_state, toolchain
from .authority import (NATIVE_EFFORTS, Blocked, Rejected, atomic_state, canonical, common_directory, decode, digest, git,
                        nonempty, normalize_origin_upstream, require, require_workspace_outside_state,
                        require_terminal_result, validate_projection, validate_receipt)
from .engine import (CAUSE_NAMES, CAUSE_UNKNOWN, LOG_LIMIT, NativeEngine, ObservationDetached,
                     SliceEnded, binding_identity, check_socket_path, observed_cause, reset_value)
from .export import IDENTITY, OPTIONS, create_branch, environment, tracked
from .export import run_git as export_git
from .process import RISK_TIERS, risk_of
from .snapshot import listed


STATUSES = ("preparing", "submission_unknown", "submitted", "running", "stopping", "resume_pending",
            "finished", "failed", "stopped")
# What the home screen shows per milestone: run_state() of its latest attempt, or waiting/ready before one exists.
MILESTONE_STATES = ("waiting", "ready", "running", "stopping", "unknown", "stopped", "conflict", "integrated",
                    "awaiting_merge", "needs_owner", "blocked", "failed_recoverable", "failed")
ACTIVE = frozenset(STATUSES[:6])
UNDISPATCHED = frozenset({"preparing", "submission_unknown", "resume_pending"})
TERMINAL = frozenset({"finished", "failed", "stopped"})


# A9: the admission bound -- how many milestone attempts may be active at once. Admission keeps their write-sets
# pairwise disjoint (the gated merge stays the integrity guard of each attempt, not admission).
MAX_RUNS = 3


def active_run(records):
    """The first active milestone writer among `records`, or None. This is the shared "active" notion: `Runs.active`
    and the lifecycle guard of `Authority.begin` read it, never a private copy of the status set."""
    return next((r for r in records if r["status"] in ACTIVE), None)


def attempt_write_set(manifest):
    """The normalized union write-set of a bootstrap manifest: a frozenset of repository paths, or None when a task
    has no write-set -- fail closed, it overlaps every attempt (and is admitted only alone). Paths are
    `posixpath.normpath`ed with only their trailing "/" dropped; "." is the whole repository."""
    paths = set()
    for task in manifest.get("tasks", ()):
        brief = task.get("brief") if isinstance(task, dict) else None
        write_set = brief.get("write_set") if isinstance(brief, dict) else None
        if not isinstance(write_set, list) or not write_set:
            return None
        paths.update(posixpath.normpath(path) for path in write_set)
    return frozenset(paths)


def write_set_overlap(one, other):
    """The path two normalized write-sets share -- one path equal to, or a directory prefix (`p + "/"`) of, a path
    of the other -- or None. `None` for a set means the whole repository and overlaps everything ("." names it)."""
    if one is None or other is None:
        if one is None and other is None:
            return "."
        found = other if one is None else one
        return sorted(found)[0] if found else "."
    if "." in one or "." in other:
        return "."
    for p in sorted(one):
        for q in sorted(other):
            if p == q or q.startswith(p + "/"):
                return p
            if p.startswith(q + "/"):
                return q
    return None


DOCUMENTS = ("graph", "runtime", "input", "baseline")
EXECUTION_ROLES = ("worker", "reviewer", "steward")
OUTCOMES = milestone.SIGNALS + ("invalid",)
FIELDS = frozenset({"plan_revision", "approval", "milestone", "attempt", "engine", "destination", "branch", "worktree",
                    "submission_key", "roles", "checker", "documents", "binding", "run_id", "predecessor", "status",
                    "cursor", "recoverable", "terminal", "output", "outcome", "manifest", "diagnostic", "created",
                    "updated"})
# Owner context, bootstrap manifest and delivery joined the record in P4. A P3 record has none of these
# fields and reads as a plain bootstrap with delivery "none"; a newer record has all of them.
EXTENSION = {"context": None, "bootstrap": None, "delivery": "none", "result": None, "integration": None}
# The diagnosis of a failed attempt (R-2/R-4): written on a failed conclude and absent -- unknown, no reset -- in
# every record made before it, so the store accepts both shapes. `gate` is the merge gate's record (A7a): absent
# until a merge with `gates.merge: required` built a candidate.
OPTIONAL = frozenset({"cause", "reset", "gate"})
# Seconds the one read of a failed run's logs may take (R-6).
LOG_DEADLINE = 30.0
# C3a: at most one execution-log read per this many seconds per run, and the reader's own deadline.
COMMAND_INTERVAL = 30
COMMAND_DEADLINE = 1.0
# C4a: the departed reviewers' queue kept in memory per run and the deadline of the one read that closes it.
VERDICT_QUEUE_LIMIT = 8
VERDICT_DEADLINE = 2.0
DELIVERIES = ("none", "exporting", "awaiting_merge", "conflict", "integrated")
EXPORTED = frozenset(DELIVERIES[2:])
CONTEXTS = {"answer": "Owner answer", "proposal": "Owner accepted proposal"}
# zplan's control files at the worktree root: never part of a product tree or a result branch.
CONTROL = (".zplan",)
# A resumed successor shares everything that defines the submission with its predecessor.
LINEAGE = ("plan_revision", "approval", "milestone", "attempt", "engine", "destination", "branch", "worktree",
           "submission_key", "roles", "checker", "documents", "binding", "context", "bootstrap")
GATE = frozenset({"destination", "head", "result", "candidate", "tree", "config_digest", "checks", "evidence",
                  "risk", "critic"})
# A gate record written before A7b2 has no `critic`: the field is optional on read and always written now.
GATE_LEGACY = GATE - {"critic"}
SHA = re.compile(r"[0-9a-f]{40}")
TREE = re.compile(r"candidate_[0-9a-f]{64}")
HEX = re.compile(r"[0-9a-f]{64}")
KEY = re.compile(r"zplan-run-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
TIME = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")
FIXTURE_OUTCOMES = ("done", "needs_owner", "blocked", "failed_recoverable", "failed")
FIXTURE_CURSOR = "fixture:terminal"
# One observation slice: short enough for the UI to react to keys between slices.
SLICE = 3
INVALID = "Invalid milestone run record; the store is rejected."


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def clock():
    """Monotonic seconds for in-memory throttles (C3a): unrounded and immune to wall-clock jumps; never persisted."""
    return time.monotonic()


def component(milestone_id):
    """Path/ref-safe milestone component: short slug plus a hash of the exact id."""
    slug = re.sub(r"[^a-z0-9]+", "-", milestone_id.lower()).strip("-")[:16].strip("-") or "m"
    return slug + "-" + hashlib.sha256(milestone_id.encode()).hexdigest()[:6]


def names(project_id, approval, milestone_id, attempt):
    """(working branch, worktree directory name); kept short for macOS socket paths."""
    plan, part = approval[:8], component(milestone_id)
    return "zplan-work/%s/%s/a%s" % (plan, part, attempt), "%s-%s-%s-a%s" % (project_id[:8], plan, part, attempt)


def title(r):
    return "Milestone %s attempt %s (plan revision %s)" % (r["milestone"], r["attempt"], r["plan_revision"])


def result_branch(r):
    return "zplan/%s-r%s-%s-a%s" % (component(r["milestone"]), r["plan_revision"], r["approval"][:8], r["attempt"])


def extended(r):
    """Read view of a record with the P4 defaults filled in for a P3 record."""
    return {**EXTENSION, **r}


def lineage(r):
    x = extended(r)
    return {k: x[k] for k in LINEAGE}


def product_tree(project, worktree, base):
    """Identity of the exportable product files, the paths export commits: every path tracked at `base` (also when
    now ignored or deleted) plus untracked files not ignored by the tree's ignore rules. Ignored dependency caches
    (node_modules, pnpm's hardlinked store) are not product and never read; zplan's control files never count."""
    with tempfile.TemporaryDirectory(prefix="zplan-tree-") as scratch:
        index = {"GIT_INDEX_FILE": str(Path(scratch) / "index")}
        export_git(project, "read-tree", base, env=index)
        listing = export_git(project, "ls-files", "-z", "--cached", "--others", "--exclude-standard",
                             env=index, work_tree=worktree)
    try:
        paths = [p for p in listing.decode().split("\0") if p]
    except UnicodeError as error:
        raise Blocked("The product tree contains non-UTF-8 paths; the identity was not computed.", family="project.unreadable") from error
    return listed(worktree, [p for p in paths if not any(p == c or p.startswith(c + "/") for c in CONTROL)])


def bootstrap_manifest(baseline, context):
    """First manifest of an attempt: every task open. A structured accepted proposal replaces the task list and
    amendments (its done tasks reopen: a fresh attempt starts from destination HEAD); the owner's text becomes a
    note on every open task. Validated against the frozen baseline."""
    manifest = milestone.initial_manifest(baseline)
    if context is None:
        return manifest
    try:
        if context["candidate"] is not None:
            manifest.update(tasks=copy.deepcopy(context["candidate"]["tasks"]),
                            amendments=copy.deepcopy(context["candidate"]["amendments"]))
        note = "%s (attempt %s): %s" % (CONTEXTS[context["kind"]], context["source"], context["text"])
        for task in manifest["tasks"]:
            if isinstance(task, dict) and task.get("status") == "done":
                task["status"] = "open"
            if isinstance(task, dict) and task.get("status") == "open":
                task["notes"] = (task["notes"] + "\n" if task.get("notes") else "") + note
        return milestone.validate(baseline, manifest)
    except (KeyError, TypeError, AttributeError) as error:
        raise milestone.Invalid("candidate: malformed task list") from error


def structured(proposal):
    """A steward proposal that is a well-formed task-list candidate {"tasks", "amendments"}, or None for any other
    text, including a candidate whose tasks or amendments do not have the manifest shape."""
    try:
        value = decode(proposal) if isinstance(proposal, str) else None
    except Blocked:
        return None
    if not (isinstance(value, dict) and set(value) == {"tasks", "amendments"}):
        return None
    try:
        milestone.check(isinstance(value["tasks"], list), "candidate: tasks")
        for task in value["tasks"]:
            milestone.validate_task(task)
        milestone.validate_records(value["amendments"], {"seq", "kind", "tasks", "parents", "reason"}, "amendment")
        for item in value["amendments"]:
            milestone.check(item["kind"] in milestone.KINDS and milestone.text(item["reason"])
                            and all(isinstance(item[k], list) and all(isinstance(t, str) for t in item[k])
                                    for k in ("tasks", "parents")), "candidate: amendment %s" % item["seq"])
    except milestone.Invalid:
        return None
    return value


def scope(proposal, milestone_id):
    """Everything that defines a milestone except the revision number; None when it cannot run."""
    try:
        baseline = milestone.build_baseline(proposal, milestone_id, 0)
    except Blocked:
        return None
    baseline.pop("plan_revision")
    return baseline


def carried(old, new, milestone_id, memo=None):
    """An integrated milestone of an older approved proposal still counts under `new` only when its full scope
    and, transitively, the scope of every dependency are unchanged. `memo` caches answers (and scopes) for one
    refresh: a dense DAG with shared ancestors is compared once per (proposal pair, milestone)."""
    memo = {} if memo is None else memo
    key = ("carried", id(old), id(new), milestone_id)
    if key not in memo:
        def cached(proposal):
            k = ("scope", id(proposal), milestone_id)
            if k not in memo:
                memo[k] = scope(proposal, milestone_id)
            return memo[k]
        before = cached(old)
        memo[key] = (before is not None and before == cached(new)
                     and all(carried(old, new, d, memo) for d in before["milestone"]["depends_on"]))
    return memo[key]


def owner_actions(r):
    """Owner choices the UI offers for one attempt; the controller methods enforce the rest."""
    x = extended(r)
    if r["status"] in {"submitted", "running"}:
        return ("observe", "stop")
    if r["status"] == "stopping":
        # reconcile resends a force-stop that never reached native, or concludes a finished run as stopped.
        return ("observe", "reconcile")
    if r["status"] in ACTIVE:
        return ("reconcile",)
    if r["outcome"] == "done":
        return {"none": ("finish",), "exporting": ("finish",), "awaiting_merge": ("merge",), "conflict": ("merge",),
                "integrated": ()}[x["delivery"]]
    if r["outcome"] == "needs_owner":
        return ("accept_proposal", "answer", "revise")
    if r["status"] == "failed" and r["recoverable"]:
        return ("resume", "answer", "revise")
    return ("answer", "revise")


def run_state(r):
    """Owner-facing state of one attempt (home screen): native status, outcome and delivery folded together."""
    if r["status"] in {"submitted", "running"}:
        return "running"
    if r["status"] == "stopping":
        return "stopping"
    if r["status"] in ACTIVE or (r["status"] == "finished" and r["outcome"] is None):
        return "unknown"
    if r["status"] == "stopped":
        return "stopped"
    if r["outcome"] == "done":
        return {"conflict": "conflict", "integrated": "integrated"}.get(extended(r)["delivery"], "awaiting_merge")
    if r["outcome"] in ("needs_owner", "blocked"):
        return r["outcome"]
    return "failed_recoverable" if r["status"] == "failed" and r["recoverable"] else "failed"


def outdated(r, revision):
    """The one refusal of a record outside the current approved revision (`check_current`, `check_followup`)."""
    return ("Revision %s is stale (current revision %s, %s): new actions on its milestone runs are forbidden."
            % (r["plan_revision"], revision["version"], revision["status"]))


def read_manifest(r):
    """The worktree manifest when it is structurally valid (display only); None otherwise."""
    try:
        value = decode((Path(r["worktree"]) / milestone.MANIFEST).read_text())
        return milestone.validate(value["baseline"], value)
    except (Blocked, OSError, UnicodeError, KeyError, TypeError, ValueError, AttributeError, IndexError):
        return None


def current_task(manifest):
    """(position, count, id) of the first open task, or None."""
    tasks = [t for t in manifest["tasks"] if t["status"] != "dropped"] if manifest else []
    return next(((i, len(tasks), t["id"]) for i, t in enumerate(tasks, 1) if t["status"] == "open"), None)


def node_label(node, task, workers=1, repairs=0):
    """Display text of one active native node of the milestone graph, or None for bookkeeping nodes."""
    base = node[len("empty_"):] if node.startswith("empty_") else node
    if base == "preflight":
        # A4b's preflight node; the owner's word for it (`tui/strings.py` role.preflight, live.ROLES).
        return "pre-check"
    if base == "worker":
        return (task + " · implementation" if workers <= 1 else
                "%s · review: rejected, repair %s/%s" % (task, workers - 1, milestone.TASK_ITERATIONS - 1))
    if base in {"acceptance_review", "code_review"}:
        return task + " · review"
    if base == "steward_apply":
        return task + " · recording the result"
    if base == "repair":
        return "final check: repair %s/%s" % (max(repairs, 1), milestone.FINAL_REPAIRS)
    if base in {"final_verify", "final_reverify", "scope_verify"}:
        return "final check"
    return None


def progress_text(item):
    text = " ".join(item["text"].split())
    if item["phase"] == "accepted":
        return "%s · review: accepted" % item["task"]
    return "%s · %s%s" % (item["task"], item["phase"], ": " + text[:100] if text else "")


def amendment_text(item):
    tasks, parents = ", ".join(item["tasks"]), ", ".join(item["parents"])
    return {"add": "+%s (add)" % tasks, "split": "+%s (split %s)" % (tasks, parents),
            "drop": "−%s (cancel)" % tasks, "reword": "%s reworded" % tasks,
            "reorder": "task order changed"}[item["kind"]]


def activity(manifest, statuses, mark=None):
    """(display lines, new mark) for native statuses seen in one slice and manifest records newer than `mark`."""
    progress = manifest["progress"] if manifest else []
    amendments = manifest["amendments"] if manifest else []
    if mark is None:
        mark = {"progress": len(progress), "amendments": len(amendments), "task": None, "workers": [], "repairs": [],
                "label": None}
    mark = copy.deepcopy(mark)
    found = current_task(manifest)
    # No open task left: the steward just accepted the last one (latest progress record).
    task = found[2] if found else progress[-1]["task"] if progress else "task"
    lines = []
    for status in statuses:
        label = None
        for active in status.get("activeExecutions", []):
            node = active["node"]
            base = node[len("empty_"):] if node.startswith("empty_") else node
            if base == "worker":
                if mark["task"] != task:
                    mark.update(task=task, workers=[])
                if active["execution"] not in mark["workers"]:
                    mark["workers"].append(active["execution"])
            elif base == "repair" and active["execution"] not in mark["repairs"]:
                mark["repairs"].append(active["execution"])
            # Reviews and the steward belong to the task the worker last implemented (it may be done by now).
            label = node_label(node, mark["task"] or task, len(mark["workers"]), len(mark["repairs"])) or label
        if status["phase"] == "stopping":
            label = "stopping…"
        if label and label != mark["label"]:
            lines.append(label)
            mark["label"] = label
    lines += ["plan: " + amendment_text(a) for a in amendments[mark["amendments"]:]]
    lines += [progress_text(p) for p in progress[mark["progress"]:]]
    mark.update(progress=len(progress), amendments=len(amendments))
    return lines, mark


def diagnostic_commands(r):
    """Ready-to-copy native status/logs commands for a dispatched native record: its frozen executable and the
    isolated state of its binding (the same environment NativeEngine uses). Fixture records have none."""
    if r["engine"] != "native" or r["run_id"] is None:
        return []
    root = Path(r["binding"]["state_root"])
    prefix = "ZEROSHOT_STATE_DIR=%s ZEROSHOT_CONFIG_DIR=%s %s" % (
        shlex.quote(str(root / "runs")), shlex.quote(str(root / "config")), shlex.quote(r["binding"]["executable"]))
    return ["%s %s %s" % (prefix, verb, shlex.quote(r["run_id"])) for verb in ("status", "logs")]


def checker_command():
    """Absolute, shell-quoted validator using this interpreter and this package, independent of the target PATH."""
    require(Path(sys.executable).is_absolute(), "The Python interpreter path is unknown; the checker cannot be frozen.", family="milestone.preflight")
    root = Path(milestone.__file__).resolve().parent.parent
    code = ("import sys; sys.path.insert(0, %s); from terminal_planner.milestone import main; sys.exit(main())"
            % json.dumps(str(root)))
    return shlex.join([sys.executable, "-I", "-c", code])


def review_rounds(revision):
    """The milestone review loop's bound for `revision`: `1 + the frozen limits.task_rounds` of its process profile,
    or the fixed `milestone.TASK_ITERATIONS` when it has no frozen profile. A version 1 revision has no snapshot at
    all and the unprofiled snapshot carries no `task_rounds`, so both keep the fixed bound (A2: "the current 4
    stays"); a later change of the process profile never reaches it, exactly as it never reaches the planner's frozen
    rounds and roles."""
    frozen = revision.get("frozen") if isinstance(revision, dict) else None
    return milestone.review_iterations(frozen.get("task_rounds") if isinstance(frozen, dict) else None)


def build_documents(proposal, milestone_id, plan_revision, roles, checker, rounds=milestone.TASK_ITERATIONS):
    baseline, _ = milestone.build_manifest(proposal, milestone_id, plan_revision)
    return {"graph": milestone.milestone_graph(len(baseline["tasks"]), rounds=rounds, tool=checker),
            "runtime": milestone.milestone_runtime(roles),
            "input": milestone.milestone_input(baseline, tool=checker), "baseline": baseline}


def validate_terminal(value):
    """The stored run terminal: `require_terminal_result` (authority) with this store's refusal text, so the
    planning envelope and the stored record accept exactly the same native terminal result."""
    require_terminal_result(value, INVALID)


def validate_output(value):
    require(isinstance(value, dict) and {"signal", "message"} <= set(value) <= {"signal", "message", "question", "proposal"}
            and value["signal"] in milestone.SIGNALS and isinstance(value["message"], str)
            and all(value.get(k) is None or isinstance(value[k], str) for k in ("question", "proposal")),
            "The root output of the milestone run does not match the driver contract.")
    return value


def validate_roles(roles):
    require(isinstance(roles, dict) and set(roles) == set(EXECUTION_ROLES), INVALID)
    for binding in roles.values():
        require(isinstance(binding, dict) and set(binding) == {"model", "effort"} and nonempty(binding["model"])
                and binding["effort"] in NATIVE_EFFORTS, INVALID)


def validate_run(authority, r, earlier):
    require(isinstance(r, dict) and set(r) - {"live"} - OPTIONAL in (FIELDS, FIELDS | set(EXTENSION)), INVALID)
    require("cause" not in r or r["cause"] in CAUSE_NAMES, INVALID)
    # G-2: the reset predicate itself (language and length), only beside a limit cause. The value is compared with
    # what the predicate returns, so a value it refuses -- including a present null, or any value whose accepted
    # form is not the value itself -- never satisfies the store.
    require("reset" not in r or (r.get("cause") == "limit" and isinstance(r["reset"], str)
                                 and reset_value(r["reset"]) == r["reset"]),
            INVALID)
    require("live" not in r or live.valid(r["live"]), INVALID)
    revisions = authority.state["revisions"]
    require(type(r["plan_revision"]) is int and 1 <= r["plan_revision"] <= len(revisions), INVALID)
    revision = revisions[r["plan_revision"] - 1]
    require(revision["status"] == "approved" and r["approval"] == revision["approval"],
            "The milestone run does not belong to the approved revision; the store is rejected.")
    require(r["engine"] == revision["engine"], "Fixture and production runs are incompatible.")
    # Readiness (dependencies integrated into the start base) is checked at start; ancestry is not store state.
    require(any(m["id"] == r["milestone"] for m in revision["proposal"]["milestones"]), INVALID)
    require(type(r["attempt"]) is int and r["attempt"] >= 1, INVALID)
    branch, name = names(authority.project_id, r["approval"], r["milestone"], r["attempt"])
    worktree = Path(r["worktree"]) if isinstance(r["worktree"], str) else None
    require(r["branch"] == branch and worktree is not None and worktree.is_absolute() and worktree.name == name
            and worktree.parent.name == "worktrees", INVALID)
    destination = r["destination"]
    require(isinstance(destination, dict) and set(destination) == {"branch", "base"} and nonempty(destination["branch"])
            and isinstance(destination["base"], str) and SHA.fullmatch(destination["base"]), INVALID)
    require(isinstance(r["submission_key"], str) and KEY.fullmatch(r["submission_key"]) and nonempty(r["checker"]), INVALID)
    validate_roles(r["roles"])
    documents = r["documents"]
    require(isinstance(documents, dict) and set(documents) == set(DOCUMENTS)
            and all(isinstance(v, str) and HEX.fullmatch(v) for v in documents.values()), INVALID)
    binding = r["binding"]
    if r["engine"] == "fixture":
        require(binding == {"fixture_id": authority.fixture_id}, INVALID)
    else:
        require(toolchain.valid_binding(binding), INVALID)  # by shape: older toolchains stay readable
    status = r["status"]
    require(status in STATUSES, INVALID)
    # Only an undispatched record, or a preparation that failed before dispatch, has no run id.
    if r["run_id"] is None:
        require(status in UNDISPATCHED or (status == "failed" and r["terminal"] is None), INVALID)
    else:
        require(nonempty(r["run_id"]) and status not in UNDISPATCHED, INVALID)
        require(all(e["run_id"] != r["run_id"] for e in earlier), INVALID)
    identity = lineage(r)
    if r["predecessor"] is None:
        prior = [e for e in earlier if e["plan_revision"] == r["plan_revision"] and e["milestone"] == r["milestone"]
                 and e["predecessor"] is None]
        require(r["attempt"] == len(prior) + 1, INVALID)
        require(all(e["submission_key"] != r["submission_key"] for e in earlier), INVALID)
    else:
        parent = [e for e in earlier if e["run_id"] == r["predecessor"]]
        require(len(parent) == 1 and parent[0]["status"] == "failed" and parent[0]["recoverable"] is True
                and lineage(parent[0]) == identity, "The resume lineage is invalid; the store is rejected.")
        require(all(e["predecessor"] != r["predecessor"] for e in earlier), "The run was resumed twice; the store is rejected.")
    require(r["cursor"] is None or nonempty(r["cursor"]), INVALID)
    require(r["recoverable"] is None or (type(r["recoverable"]) is bool and status == "failed"), INVALID)
    if status in TERMINAL and r["run_id"] is not None:
        validate_terminal(r["terminal"])
        require(status != "finished" or r["terminal"]["status"] == "succeeded", INVALID)
        require(status != "failed" or r["terminal"]["status"] == "failed", INVALID)
    else:
        require(r["terminal"] is None, INVALID)
    if status == "finished":
        require(r["output"] is None and r["outcome"] in (None, "invalid") or validate_output(r["output"]) is r["output"], INVALID)
        require(r["outcome"] is None or r["outcome"] in OUTCOMES, INVALID)
    else:
        require(r["output"] is None and r["outcome"] is None, INVALID)
    if r["outcome"] is not None and r["outcome"] != "invalid":
        require(r["output"] is not None and r["output"]["signal"] == r["outcome"], INVALID)
    if r["manifest"] is not None:
        require(r["outcome"] is not None, INVALID)
        try:
            milestone.validate(r["manifest"]["baseline"], r["manifest"])
        except (Blocked, KeyError, TypeError) as error:
            raise Blocked(INVALID, family="store.invalid") from error
        require(digest(r["manifest"]["baseline"]) == documents["baseline"], INVALID)
    if r["outcome"] == "done":
        require(r["manifest"] is not None and all(t["status"] != "open" for t in r["manifest"]["tasks"]), INVALID)
    require(isinstance(r["diagnostic"], str), INVALID)
    require(all(isinstance(r[k], str) and TIME.fullmatch(r[k]) for k in ("created", "updated")), INVALID)
    validate_extension(revision, r, earlier)


def validate_extension(revision, r, earlier):
    """Owner context, bootstrap, delivery state, result identity and integration evidence (P4 fields)."""
    x = extended(r)
    context = x["context"]
    if context is not None:
        require(isinstance(context, dict) and set(context) == {"kind", "source", "text", "candidate"}
                and context["kind"] in CONTEXTS and type(context["source"]) is int and nonempty(context["text"])
                and (context["candidate"] is None) == (context["kind"] == "answer")
                and any(e["plan_revision"] == r["plan_revision"] and e["milestone"] == r["milestone"]
                        and e["attempt"] == context["source"] < r["attempt"] for e in earlier), INVALID)
    if x["bootstrap"] is not None or context is not None:
        try:
            baseline = milestone.build_baseline(revision["proposal"], r["milestone"], r["plan_revision"])
            reproduced = digest(bootstrap_manifest(baseline, context)) == x["bootstrap"]
        except Blocked:
            reproduced = False
        require(reproduced, INVALID)
    delivery, result, integration = x["delivery"], x["result"], x["integration"]
    require(delivery in DELIVERIES, INVALID)
    if result is not None:
        require(r["outcome"] == "done" and isinstance(result, dict) and set(result) == {"branch", "tree", "commit"}
                and result["branch"] == result_branch(r) and isinstance(result["tree"], str)
                and TREE.fullmatch(result["tree"])
                and (result["commit"] is None or isinstance(result["commit"], str) and SHA.fullmatch(result["commit"])),
                INVALID)
    exported = result is not None and result["commit"] is not None
    require((delivery != "exporting" or result is not None) and exported == (delivery in EXPORTED), INVALID)
    if integration is None:
        require(delivery not in {"conflict", "integrated"}, INVALID)
    else:
        require(exported and isinstance(integration, dict)
                and set(integration) - {"landing"} == {"destination", "commit", "conflicts", "aborted"}
                and (integration.get("landing") is None or nonempty(integration["landing"]))
                and integration["destination"] == "refs/heads/" + r["destination"]["branch"]
                and (integration["commit"] is None or isinstance(integration["commit"], str)
                     and SHA.fullmatch(integration["commit"]))
                and isinstance(integration["conflicts"], list) and all(nonempty(p) for p in integration["conflicts"])
                and (integration["aborted"] is None or type(integration["aborted"]) is bool), INVALID)
        require((integration["commit"] is not None) == (delivery == "integrated")
                and (delivery != "conflict" or integration["conflicts"]), INVALID)
    if "gate" in r:
        validate_gate(r)


def validate_gate(r):
    """The merge gate's record of the candidate it tested (A7a): only on an exported result, naming that result and
    its destination, with the frozen checks, their evidence and the risk. A record from before A7b2 carries no
    `critic` and still loads; `critic` is the id of the merge-critic record that judged this candidate, or None."""
    gate, result = r["gate"], extended(r)["result"]
    require(isinstance(gate, dict) and set(gate) in (GATE, GATE_LEGACY) and result is not None
            and result["commit"] is not None
            and gate["destination"] == "refs/heads/" + r["destination"]["branch"] and gate["result"] == result["commit"]
            and all(isinstance(gate[key], str) and SHA.fullmatch(gate[key]) for key in ("head", "result", "candidate", "tree"))
            and isinstance(gate["config_digest"], str) and HEX.fullmatch(gate["config_digest"])
            and (gate.get("critic") is None
                 or isinstance(gate["critic"], str) and merge_critic.ID.fullmatch(gate["critic"]))
            and isinstance(gate["risk"], dict) and gate["risk"].get("tier") in RISK_TIERS, INVALID)
    # The evidence is of exactly this candidate and these checks: one entry per frozen check, in order, and the
    # outcome follows from their statuses.
    frozen, evidence = gate["checks"], gate["evidence"]
    require(isinstance(frozen, list) and frozen and all(isinstance(c, dict) and isinstance(c.get("name"), str)
                                                        and isinstance(c.get("argv"), list) for c in frozen)
            and isinstance(evidence, dict) and set(evidence) == {"checks_digest", "checks", "outcome", "commit", "tree"}
            and (evidence["commit"], evidence["tree"], evidence["checks_digest"]) == (gate["candidate"], gate["tree"], digest(frozen))
            and isinstance(evidence["checks"], list) and len(evidence["checks"]) == len(frozen)
            and all(isinstance(e, dict) and (e.get("name"), e.get("argv_digest")) == (c["name"], digest(c["argv"]))
                    for e, c in zip(evidence["checks"], frozen))
            and evidence["outcome"] == ("passed" if all(e.get("status") == 0 for e in evidence["checks"]) else "failed"),
            INVALID)


def critic_identity(r, gate, paths, names, briefs):
    """The identity one merge critic judges (A7b2): the pinned gate fields (destination, base = the gate's head,
    result, candidate, tree, config digest) plus the milestone, its plan revision and attempt, the candidate's risk
    and the semantic input digest of the reasons, the changed paths and the milestone's frozen briefs."""
    return {"milestone": r["milestone"], "plan_revision": r["plan_revision"], "attempt": r["attempt"],
            "destination": gate["destination"], "base": gate["head"], "result": gate["result"],
            "candidate": gate["candidate"], "tree": gate["tree"], "config_digest": gate["config_digest"],
            "input_digest": merge_critic.input_digest(names, paths, briefs), "risk": copy.deepcopy(gate["risk"])}


def reusable_gate(gate, ref, head, result, pinned):
    """The stored gate record a gated merge may reuse (C1): it names this destination, head, result and configuration
    digest and its evidence `passed`, so its candidate commit and check evidence are exactly this merge's. Any other
    head, result, config or evidence is not this candidate and a new one is built."""
    return gate if (isinstance(gate, dict) and gate.get("destination") == ref and gate.get("head") == head
                    and gate.get("result") == result and gate.get("config_digest") == pinned
                    and isinstance(gate.get("evidence"), dict) and gate["evidence"].get("outcome") == "passed") else None


def gate_paths(project, head, tree):
    """The changed paths of one merge candidate, from its head to its tree (`--no-renames` lists a rename's old path
    too). Read again for a reused candidate so the critic's input digest matches the identity it built."""
    changed = git_call(project, "diff", "--name-only", "--no-renames", "-z", head, tree)
    require(changed.returncode == 0, "Git did not show the candidate's changed files; the state is unchanged.",
            family="milestone.merge_refused")
    return [p for p in changed.stdout.decode(errors="replace").split("\0") if p]


def commit_candidate(project, r, tree, head, result, identity, trailer=None):
    """The merge commit of `tree` over (head, result), made off-tree with `commit-tree` under the owner's identity;
    `trailer` is an optional second message paragraph."""
    name, email = identity
    message = ["-m", "Merge %s: %s" % (r["result"]["branch"], title(r))] + (["-m", trailer] if trailer else [])
    made = git_call(project, "commit-tree", tree, "-p", head, "-p", result, *message,
                    env={"GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email,
                         "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email})
    candidate = made.stdout.decode().strip()
    require(made.returncode == 0 and SHA.fullmatch(candidate), "Git did not create the candidate commit; the state is unchanged.",
            family="milestone.merge_refused")
    return candidate


class Overlap(Blocked):
    """Landing refused: the merge would write over files of the owner's tree. Nothing was merged or touched; the
    result branch is kept (`paths` are what is in the way)."""
    family = "milestone.merge_overlap"

    def __init__(self, paths, branch):
        super().__init__("Not merged: your files outside the commit are in the way of the merge (%s). Branch %s is kept."
                         % (project_read.shown_paths(paths), branch))
        self.paths = tuple(paths)


def dirty_entries(project):
    """The owner's dirty set: every `git status` entry of the tree (staged, modified, untracked; a rename also
    holds its origin) as «XY path» strings. Ignored files are not in it."""
    out = git(project, "status", "--porcelain=v1", "-z", "--untracked-files=all").split(b"\0")
    entries, index = set(), 0
    while index < len(out):
        entry = out[index]
        index += 1
        if len(entry) > 3:
            entries.add(os.fsdecode(entry))
            if entry[:1] in b"RC" and index < len(out):
                entries.add(os.fsdecode(entry[:3]) + os.fsdecode(out[index]))  # the origin of a rename or copy
                index += 1
    return entries


def entry_path(entry):
    return entry[3:]


def tracked_paths(project):
    """The index's files and the directories holding at least one of them."""
    files = set(os.fsdecode(p) for p in git(project, "ls-files", "-z").split(b"\0") if p)
    return files, {"/".join(f.split("/")[:i]) for f in files for i in range(1, f.count("/") + 1)}


def overlapping_paths(project, candidate, dirty):
    """The paths in the way of landing `candidate` on HEAD: a path the commit changes (`diff --no-renames`), or a
    parent of one, that exists on disk as untracked, ignored or modified (`dirty` holds the untracked and modified
    ones; an ignored one, also inside a directory the commit replaces by a file, is found on disk). A non-empty parent
    directory holding no tracked file is untracked or ignored and is reported itself. Sorted; empty when the owner's changes lie elsewhere."""
    changed = git_call(project, "diff", "--no-renames", "--name-only", "-z", "HEAD", candidate)
    require(changed.returncode == 0, "Git did not show the candidate's changed files; the state is unchanged.",
            family="milestone.merge_refused")
    paths = [os.fsdecode(p) for p in changed.stdout.split(b"\0") if p]
    marks = {entry_path(e) for e in dirty}
    below = {"/".join(m.split("/")[:i]) for m in marks for i in range(1, m.count("/") + 1)}  # dirs holding a dirty path
    tracked, held, found = None, None, set()
    for path in paths:
        parts = path.split("/")
        chain = ["/".join(parts[:i]) for i in range(1, len(parts) + 1)]
        for index, part in enumerate(chain):
            here = os.path.join(project, part)
            if part in marks or (index == len(chain) - 1 and part in below):
                found.add(part)
            elif index < len(chain) - 1 and os.path.isdir(here) and not os.path.islink(here):
                if tracked is None:
                    tracked, held = tracked_paths(project)
                if part not in held and os.listdir(here):  # untracked or ignored directory: git lists it as `?? d/`, `!! d/`
                    found.add(part)
            elif os.path.lexists(here) and (os.path.islink(here) or not os.path.isdir(here)
                                            or index == len(chain) - 1):
                if tracked is None:
                    tracked, held = tracked_paths(project)
                if os.path.isdir(here) and not os.path.islink(here):
                    # A directory where the commit puts a file: only what the index holds goes away cleanly; an
                    # ignored file inside it (untracked ones are in `dirty`) would be lost.
                    if any(os.path.relpath(os.path.join(root, name), project).replace(os.sep, "/") not in tracked
                           for root, _, names in os.walk(here) for name in names):
                        found.add(part)
                elif part not in tracked:  # not in the index and not dirty: an ignored file in the way
                    found.add(part)
    return sorted(f for f in found if not any(o.startswith(f + "/") for o in found))  # the file, not its directory


def validate_runs(authority, runs):
    require(isinstance(runs, list), INVALID)
    for index, r in enumerate(runs):
        validate_run(authority, r, runs[:index])
    require(sum(r["status"] in ACTIVE for r in runs) <= MAX_RUNS,
            "More than %s active milestone writers; the store is rejected." % MAX_RUNS)


def git_call(project, *args, env=None):
    # Sanitized like export: no hooks, user config or credential prompts.
    try:
        return subprocess.run(["git", "--no-optional-locks", *OPTIONS, "-C", str(project), *args], capture_output=True,
                              timeout=300, start_new_session=True, env={**environment(), **(env or {})})
    except (OSError, subprocess.TimeoutExpired) as error:
        raise Blocked("Git did not answer (%s); the operation was interrupted." % args[0], family="git.failed") from error


def run_git(project, *args):
    result = git_call(project, *args)
    if result.returncode:
        raise Rejected("Git refused (%s); the operation was interrupted." % args[0], family="git.failed")
    return result.stdout.decode().strip()


def resolve_ref(project, ref):
    result = subprocess.run(["git", "-C", str(project), "rev-parse", "--verify", "--quiet", ref + "^{commit}"],
                            capture_output=True, start_new_session=True, timeout=60, env=environment())
    return result.stdout.decode().strip() if result.returncode == 0 else None


def is_ancestor(project, commit, tip):
    result = git_call(project, "merge-base", "--is-ancestor", commit, tip)
    require(result.returncode in (0, 1), "Git did not check the ancestry of %s; the state is unchanged." % commit[:12])
    return result.returncode == 0


def has_commit(project, commit):
    """False when the commit object is gone (branch deleted and pruned); never raises."""
    return git_call(project, "cat-file", "-e", commit + "^{commit}").returncode == 0


def integration_commit(project, commit, tip):
    """First commit of the destination's first-parent chain that contains `commit`: the merge commit, or the
    result itself when it was fast-forwarded. Containment is monotonic along that chain, so bisect it."""
    chain = run_git(project, "rev-list", "--first-parent", "--reverse", tip, "^" + commit).split()
    if not chain:
        return commit
    low, high = 0, len(chain) - 1
    while low < high:
        middle = (low + high) // 2
        if is_ancestor(project, commit, chain[middle]):
            high = middle
        else:
            low = middle + 1
    return commit if run_git(project, "rev-parse", chain[low] + "^1") == commit else chain[low]


def configured_identity(project):
    """The owner's configured Git user (repository, then global config), or None."""
    values = []
    for key in ("user.name", "user.email"):
        result = subprocess.run(["git", "-C", str(project), "config", "--get", key], capture_output=True,
                                start_new_session=True, timeout=60)
        values.append(result.stdout.decode().strip() if result.returncode == 0 else "")
    return tuple(values) if all(values) else None


class MilestoneRuns:
    """Lifecycle of milestone attempts; the caller holds the authority session lock."""

    def __init__(self, authority, engine, worktrees=None):
        from .setup import data_root
        self.authority = authority
        self.engine = engine
        self.worktrees = Path(worktrees or data_root() / "worktrees").expanduser().resolve()
        # C3a: in-memory throttle of the command read, keyed by run id (never persisted: A5).
        self.commands = {}
        # C4a: in-memory queue of departed reviewers, keyed by run id (never persisted: A2/A5).
        self.verdicts = {}

    def driver(self):
        """The milestone driver. It is None until the pinned tools pass the readiness check; every action that
        needs it then stops with the readiness.tools remedy instead of failing on a missing driver."""
        if self.engine is None:
            raise Blocked("The zplan tools are not installed or are damaged: [u] install on the readiness screen, or zplan setup.",
                          family="readiness.tools")
        return self.engine

    @property
    def runs(self):
        require(self.authority.state is not None, "There is no saved plan.", family="action.refused")
        return self.authority.state.get("runs", [])

    def active(self):
        return active_run(self.runs)

    def admit(self, milestone_id, plan_revision, context=None, exclude=None):
        """Admission of a new attempt of `milestone_id` (start or resume) under the parallel rule (A9): refused with
        `action.refused` when the active records -- `ACTIVE`, in store order, `exclude` left out -- number `MAX_RUNS`
        or more, when one of them is the same milestone, or when this attempt's write-set (the union over the tasks
        of the bootstrap manifest it runs) overlaps an active one's (equal or a directory prefix; a task without a
        write-set fails closed). Admission only schedules; each attempt's gated merge stays its integrity guard."""
        active = [r for r in self.runs if r["status"] in ACTIVE and r is not exclude]
        require(len(active) < MAX_RUNS, "The limit of parallel milestone runs (%s) is reached: %s are already running."
                % (MAX_RUNS, len(active)), family="action.refused")
        same = next((r for r in active if r["milestone"] == milestone_id), None)
        require(same is None, "Milestone %s is already running (attempt %s): a new attempt waits for it to finish."
                % (milestone_id, same["attempt"] if same else None), family="action.refused")
        mine = attempt_write_set(self.gate_manifest(milestone_id, plan_revision, context))
        for r in active:
            shared = write_set_overlap(mine, attempt_write_set(self.gate_manifest(r["milestone"], r["plan_revision"],
                                                                                 extended(r)["context"])))
            require(shared is None, "Milestone %s overlaps with %s (%s): it waits for it to finish."
                    % (milestone_id, r["milestone"], shared), family="action.refused")
        return None

    def save(self, r):
        r["updated"] = now()
        self.authority.save()

    def critic_briefs(self, r):
        """The milestone's frozen briefs (A7b2): the task briefs of the merge's own plan revision, from the bootstrap
        manifest that revision validates (`gate_manifest`), never the live project."""
        manifest = self.gate_manifest(r["milestone"], r["plan_revision"], None)
        return [task["brief"] for task in manifest["baseline"]["tasks"] if "brief" in task]

    def gate_manifest(self, milestone_id, plan_revision, context):
        """The bootstrap manifest a task gate reviews (R-2): exactly `bootstrap_manifest(build_documents(...)
        ["baseline"], context)` as `start` computes it, from the approved revision's proposal, with no git read,
        refresh or persistence."""
        revision = self.authority.state["revisions"][plan_revision - 1]
        baseline, _ = milestone.build_manifest(revision["proposal"], milestone_id, plan_revision)
        return bootstrap_manifest(baseline, context)

    # Start -------------------------------------------------------------------

    def start(self, milestone_id, plan_revision, roles, context=None, destination=None):
        """Begin attempt n+1 of a milestone from destination HEAD: persist, prepare the worktree, submit.

        `context` (owner answer or accepted candidate) is frozen with the bootstrap manifest digest before
        anything is prepared; `destination` pins the branch a fresh attempt must start from."""
        a = self.authority
        a.check_project()
        require(a.state is not None and a.state["revisions"], "There is no approved plan.", family="action.refused")
        revision = a.current
        require(plan_revision == revision["version"],
                "Revision %s is stale: the current revision is %s. Starting a milestone is forbidden." % (plan_revision, revision["version"]),
                family="action.refused")
        require(revision["status"] == "approved" and revision["approval"] == a.approval_identity(revision),
                "Revision %s is not approved; starting a milestone is forbidden." % plan_revision, family="action.refused")
        require(not (revision["engine"] == "fixture" and self.driver().name != "fixture"),
                "A fixture approval does not allow native submission.", family="action.refused")
        require(revision["engine"] == self.driver().name, "The fixture driver does not run for a production plan.", family="usage.invalid_option")
        found = next((m for m in revision["proposal"]["milestones"] if m["id"] == milestone_id), None)
        require(found is not None, "Milestone %s is not in the approved plan." % milestone_id, family="action.refused")
        self.admit(milestone_id, plan_revision, context)
        project_state.exclude_caches(a.project)  # a tool cache is neither dirt nor part of the attempt's commit
        try:
            current = git(a.project, "symbolic-ref", "--quiet", "--short", "HEAD").decode().strip()
        except Blocked as error:
            raise Blocked("HEAD is detached; switch to a branch (git switch <branch>) before starting a milestone.", family="readiness.branch") from error
        base = git(a.project, "rev-parse", "HEAD").decode().strip()
        require(destination is None or destination == current,
                "A new attempt starts from the HEAD of branch %s; switch to it (git switch %s)." % (destination, destination),
                family="readiness.branch")
        require(not tracked(a.project, base, CONTROL),
                "The project tracks .zplan/ (zplan's service directory); remove it from Git before starting a milestone.", family="export.reserved_path")
        # Record manual merges and resets first: readiness reads confirmed integration only.
        self.refresh()
        waiting = self.waiting(milestone_id, base)
        require(not waiting, "Milestone %s is waiting for %s: the result is not merged into %s." % (milestone_id, ", ".join(waiting), current),
                family="action.refused")
        require(isinstance(roles, dict) and all(role in roles for role in EXECUTION_ROLES), "The worker/reviewer/steward roles are required.", family="action.refused")
        roles = {role: copy.deepcopy(roles[role]) for role in EXECUTION_ROLES}
        try:
            validate_roles(roles)
        except Blocked as error:
            raise Blocked("Invalid model/effort of the worker/reviewer/steward roles.", family="action.refused") from error
        attempt = 1 + sum(r["plan_revision"] == plan_revision and r["milestone"] == milestone_id and r["predecessor"] is None
                          for r in self.runs)
        branch, name = names(a.project_id, revision["approval"], milestone_id, attempt)
        checker = checker_command()
        documents = build_documents(revision["proposal"], milestone_id, plan_revision, roles, checker,
                                    rounds=review_rounds(revision))
        bootstrap = digest(bootstrap_manifest(documents["baseline"], context))
        driver = self.driver()
        binding = driver.binding(a)
        if "executable" in binding:  # R-1: a native attempt records the home it starts in; the fixture binding stays
            binding = {**binding, "codex_home": str(driver.codex_home())}
        stamp = now()
        r = {"plan_revision": plan_revision, "approval": revision["approval"], "milestone": milestone_id,
             "attempt": attempt, "engine": revision["engine"], "destination": {"branch": current, "base": base},
             "branch": branch, "worktree": str(self.worktrees / name), "submission_key": "zplan-run-" + str(uuid.uuid4()),
             "roles": roles, "checker": checker, "documents": {k: digest(v) for k, v in documents.items()},
             "binding": binding, "run_id": None, "predecessor": None, "status": "preparing", "cursor": None,
             "recoverable": None, "terminal": None, "output": None, "outcome": None, "manifest": None,
             "diagnostic": "", "created": stamp, "updated": stamp,
             **copy.deepcopy(EXTENSION), "context": copy.deepcopy(context), "bootstrap": bootstrap}
        a.state.setdefault("runs", []).append(r)
        # Persist intent (attempt, key, paths) before any worktree, branch or bootstrap exists.
        try:
            self.save(r)
        except BaseException:
            a.state["runs"].pop()
            raise
        self.settle(r, self.prepare, self.dispatch)
        return r

    def settle(self, r, *steps):
        """Run pre-dispatch steps; a certain refusal ends the attempt as failed (nothing was dispatched)."""
        try:
            for step in steps:
                step(r)
        except Rejected as error:
            if r["status"] in {"preparing"}:
                r.update(status="failed", diagnostic=str(error)[:300])
                self.save(r)
            raise

    def directory(self, r):
        return self.authority.directory / "runs" / Path(r["worktree"]).name

    def frozen(self, r, regenerate=False):
        """Paths of the frozen submission documents; regenerate only while nothing was dispatched."""
        directory = self.directory(r)
        if regenerate:
            revision = self.authority.state["revisions"][r["plan_revision"] - 1]
            documents = build_documents(revision["proposal"], r["milestone"], r["plan_revision"], r["roles"],
                                        r["checker"], rounds=review_rounds(revision))
            require({k: digest(v) for k, v in documents.items()} == r["documents"], "The frozen submission cannot be reproduced.")
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            for key, value in documents.items():
                path = directory / (key + ".json")
                if not path.is_file() or path.read_text() != canonical(value) + "\n":
                    atomic_state(path, value)
        paths = {key: directory / (key + ".json") for key in DOCUMENTS}
        for key, path in paths.items():
            try:
                ok = digest(decode(path.read_text())) == r["documents"][key]
            except (OSError, UnicodeError, Blocked):
                ok = False
            require(ok, "The frozen submission %s was lost or changed; resubmission is forbidden." % key)
        return paths

    def check_worktree(self, r, at_base, action="preparation interrupted"):
        """Read-only identity check: repository, working branch and (at_base) the frozen HEAD; never resets."""
        worktree = Path(r["worktree"])
        require(worktree.is_dir(), "The milestone worktree %s was lost; resubmission is forbidden." % worktree)
        require(common_directory(worktree) == self.authority.common_dir
                and Path(git(worktree, "rev-parse", "--show-toplevel").decode().strip()).resolve() == worktree.resolve(),
                "The milestone worktree belongs to another repository; %s." % action)
        symbolic = git_call(worktree, "symbolic-ref", "--quiet", "HEAD")
        if symbolic.returncode or symbolic.stdout.decode().strip() != "refs/heads/" + r["branch"]:
            # A native checkpoint resume leaves this worktree on a detached HEAD. Only a verified resume lineage
            # (validate_run checks predecessor) may finish there, and only on a commit that descends from the base.
            head = git(worktree, "rev-parse", "HEAD").decode().strip()
            require(not at_base and r["predecessor"] is not None and symbolic.returncode == 1
                    and is_ancestor(worktree, r["destination"]["base"], head),
                    "The milestone worktree is not on the working branch %s; %s." % (r["branch"], action))
        if at_base:
            head = git(worktree, "rev-parse", "HEAD").decode().strip()
            require(head == r["destination"]["base"], "The milestone worktree HEAD (%s) is not on base commit %s; %s."
                    % (head[:12], r["destination"]["base"][:12], action), family="action.refused")

    def prepare(self, r):
        """Idempotent: worktree from the destination base on the working branch, bootstrap, checker preflight."""
        require(r["status"] == "preparing", "Preparation is possible only before submission.", family="action.refused")
        paths = self.frozen(r, regenerate=True)
        worktree = Path(r["worktree"])
        project = self.authority.project
        if not worktree.exists():
            worktree.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            tip = resolve_ref(project, "refs/heads/" + r["branch"])
            if tip is None:
                run_git(project, "worktree", "add", "--quiet", "-b", r["branch"], str(worktree), r["destination"]["base"])
            else:
                # Crash after the branch was created: reuse it only at the frozen base.
                if tip != r["destination"]["base"]:
                    raise Rejected("Branch %s already exists and is not on base; preparation interrupted." % r["branch"], family="milestone.branch_exists")
                run_git(project, "worktree", "prune")
                run_git(project, "worktree", "add", "--quiet", str(worktree), r["branch"])
        self.check_worktree(r, at_base=True)
        # 10.12 resolves the submitted source from the branch's upstream config; the worktree's own branch names
        # origin explicitly, so several remotes on the target cannot make the run ambiguous.
        normalize_origin_upstream(worktree, r["branch"])
        baseline = decode(paths["baseline"].read_text())
        for relative, value in ((milestone.BASELINE, baseline), (milestone.MANIFEST, self.bootstrap(r, baseline))):
            path = worktree / relative
            if not path.is_file() or path.read_text() != canonical(value) + "\n":
                path.parent.mkdir(exist_ok=True)
                atomic_state(path, value)
        self.preflight(r, paths)

    @staticmethod
    def bootstrap(r, baseline):
        """The frozen first manifest of the attempt, reproduced from the record (also after a crash)."""
        x = extended(r)
        manifest = bootstrap_manifest(baseline, x["context"])
        require(x["bootstrap"] is None or digest(manifest) == x["bootstrap"], "The frozen bootstrap manifest cannot be reproduced.")
        return manifest

    def preflight(self, r, paths):
        worktree = Path(r["worktree"])
        command = "%s check %s --baseline %s" % (r["checker"], milestone.MANIFEST, milestone.BASELINE)
        try:
            result = subprocess.run(["/bin/sh", "-c", command], cwd=worktree, capture_output=True, text=True,
                                    timeout=120, start_new_session=True)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise Blocked("The checker preflight did not run in the milestone worktree.", family="milestone.preflight") from error
        if result.returncode:
            # Deterministic: the frozen checker cannot run here, so the attempt ends before any dispatch.
            message = (result.stderr.strip().splitlines() or ["exit %s" % result.returncode])[-1][:300]
            r.update(status="failed", diagnostic="Checker preflight failed: " + message)
            self.save(r)
            raise Blocked("The checker failed preflight in the milestone worktree: " + message, family="milestone.preflight")
        workspace = decode((worktree / milestone.BASELINE).read_text())
        frozen_input = decode(paths["input"].read_text())
        require(digest(workspace) == r["documents"]["baseline"] and frozen_input["baseline"] == canonical(workspace),
                "The baseline in the worktree does not match the frozen submission.")

    def check_binding(self, r):
        # An older toolchain's record is acted on with its own executable (toolchain.mismatch when it is gone).
        engine = self.driver().engine_for(r["binding"])
        # R-2: the four identity fields only (a fixture binding, without `executable`, is compared exactly).
        require(engine.binding(self.authority) == binding_identity(r["binding"]),
                "The native binary/state changed; use the original isolated paths.")

    def dispatch(self, r):
        paths = self.frozen(r)
        self.check_binding(r)
        self.driver().validate(r, paths)
        # Commit uncertainty BEFORE dispatch: a crash cannot make an unreceipted submission retryable as new.
        r["status"] = "submission_unknown"
        self.save(r)
        self.adopt_submission(r, paths)

    def adopt_submission(self, r, paths):
        receipt = self.driver().submit(r, paths)
        r.update(run_id=receipt["runId"], status="submitted", diagnostic="")
        self.save(r)

    # Reopen ------------------------------------------------------------------

    def reconcile(self):
        """Settle the crash window of every active record, in store order, each its own (A9); returns the first
        record still active, or None. A refusal of one attempt never skips the others: all are tried, the first
        refusal is raised after."""
        for r in self.runs:
            if r["status"] == "finished" and r["outcome"] is None:
                self.evaluate(r)
        try:
            self.refresh()
        except Blocked:
            pass  # a delivery-evidence failure must never block crash recovery of the active writers
        refusal = None
        for r in list(self.runs):
            if r["status"] not in ACTIVE:
                continue
            try:
                self.settle_active(r)
            except Blocked as error:
                if refusal is None:
                    refusal = error
        if refusal is not None:
            raise refusal
        return self.active()

    def settle_active(self, r):
        """Settle one active record's crash window: `preparing`, `submission_unknown`, `stopping` and
        `resume_pending` as before, each its own. A refusal is left to the caller to raise after the other records
        were tried."""
        if r["status"] == "preparing":
            self.driver()  # nothing is prepared on disk for a run that cannot be dispatched
            self.settle(r, self.prepare, self.dispatch)
        elif r["status"] == "submission_unknown":
            # Replay the identical frozen submission; native idempotence returns the existing run id.
            # Bootstrap files and a possibly live worktree are never rewritten or reset.
            # The worktree must still be the frozen one: same repository, working branch and base HEAD.
            paths = self.frozen(r)
            self.check_binding(r)
            self.check_worktree(r, at_base=True, action="replay forbidden, the worktree is unchanged")
            self.driver().validate(r, paths)
            self.adopt_submission(r, paths)
        elif r["status"] == "stopping":
            # The stop request is persisted before force-stop is sent; resend it until the run is terminal.
            value = self.status(r)
            if value["status"]["phase"] == "finished":
                self.conclude(r, value["status"]["terminalResult"])
            else:
                self.check_binding(r)
                self.driver().force_stop(r)
        elif r["status"] == "resume_pending":
            self.adopt_successor(r)

    # Observe -----------------------------------------------------------------

    def observe(self, r, seconds=None, seen=None):
        """One bounded watch from the stored cursor; detach is simply not observing again.

        `seconds` bounds the watch to a short slice (the UI polls between keys); `seen` receives every validated
        non-terminal native status (active nodes) in order."""
        require(r["run_id"] is not None and r["status"] in {"submitted", "running", "stopping"},
                "Only a submitted active milestone run can be watched.")
        detached = None
        try:
            for value in self.driver().watch(r, r["cursor"], seconds):
                status = validate_projection(value, r["run_id"])
                require(value["title"] == title(r) and value["size"] == "medium"
                        and value["source"]["revision"] == r["destination"]["base"], "Native run identity mismatch.")
                if status["phase"] == "finished":
                    # C4a: the record that finishes the run ends the watch, so this slice's pending reviewers are
                    # queued (a finished projection lists no active execution) and its one bounded verdict read runs
                    # here, before the run closes: a finished run is never observed again and a queued verdict would
                    # otherwise stay unread.
                    self.record(r, status)
                    self.read_verdict(r)
                    self.save(r)
                    self.conclude(r, status["terminalResult"])
                    return r
                # A cursor the watch already delivered is a replay: it moves nothing back and is no new event.
                known = r.get("live", {}).get("cursors", []) + [r["cursor"]]
                if value["cursor"] in known:
                    if seen is not None:
                        seen(status)
                    continue
                r.update(cursor=value["cursor"], status="stopping" if r["status"] == "stopping" else "running")
                self.record(r, status, value["cursor"], event=True)
                self.save(r)
                if seen is not None:
                    seen(status)
        except SliceEnded:
            pass  # the bounded slice ran its time out: a normal end
        except ObservationDetached:
            detached = True
        if detached:
            r.setdefault("live", live.new())
            live.detach(r["live"], now())
        else:
            self.record(r)  # the slice completed, with or without records: the watcher looked
            # C4a: a departed reviewer takes this slice's single read; with none queued, C3a reads a command.
            if not self.read_verdict(r):
                self.track_command(r)  # C3a: remember the last Codex command the active executions logged
        self.save(r)
        return r

    def queue_verdict(self, r, role, execution, task, round):
        """Queue one reviewer that just left `live["nodes"]` (C4a/A2), with the task and round of that moment.

        The queue lives in memory per run id, is bounded (`VERDICT_QUEUE_LIMIT`, oldest dropped) and holds no
        duplicates: an execution already queued or already appended is skipped, so nothing but `live["verdicts"]` is
        ever persisted. `role` is the reviewer's node base (the caller read it off the departed node)."""
        state = self.verdicts.setdefault(r["run_id"], {"queue": [], "reads": {}, "seen": set()})
        if execution in state["seen"] or any(item["execution"] == execution for item in state["queue"]):
            return
        state["queue"].append({"execution": execution, "role": role, "task": task, "round": round})
        del state["queue"][:-VERDICT_QUEUE_LIMIT]

    def read_verdict(self, r):
        """One bounded read of the oldest queued reviewer's log (C4a/A3-A5); True when it ran.

        With an empty queue nothing is read (False, the caller lets C3a apply). Otherwise one
        `zeroshot logs RUN --execution REF` (deadline `VERDICT_DEADLINE`, buffer `LOG_LIMIT`) is read for the oldest
        queued execution whatever `complete` says, and the queue is closed one step: the entry is dropped after a
        read that finds its response or after its second read that finds none, and an OSError (the reader cannot
        start, or any other failure of the read) is one such read. A found verdict appends one entry, bounded and
        deduplicated in memory by execution id; no exception escapes."""
        state = self.verdicts.get(r["run_id"])
        if not state or not state["queue"]:
            return False
        entry = state["queue"][0]
        reference = entry["execution"]
        try:
            lines, _ = self.driver().log_records(r["binding"], r["run_id"], r["worktree"], execution=reference,
                                                 deadline=VERDICT_DEADLINE, buffer=LOG_LIMIT)
        except (Blocked, OSError, ValueError):
            lines = None
        found = live.last_verdict(lines) if lines is not None else None
        if found is None:
            state["reads"][reference] = state["reads"].get(reference, 0) + 1
            if state["reads"][reference] >= 2:
                state["queue"].pop(0)
            return True
        at, verdict, text = found
        live.bounded(r["live"].setdefault("verdicts", []),
                     {"at": at, "task": entry["task"], "round": entry["round"], "role": entry["role"],
                      "verdict": verdict, "text": text}, live.VERDICT_LIMIT)
        # A6b1: the same save also carries the architect's feed event for this verdict, identified by the reviewer's
        # execution reference; the bounded display list above never bounds the feed.
        feed.verdict(self.authority, r, reference, entry, verdict, text)
        state["seen"].add(reference)
        state["queue"].pop(0)
        return True

    def track_command(self, r):
        """Remember the last Codex command among the active executions' logs (C3a, data half of C3).

        With at least one active execution in `live["nodes"]`, at most one bounded read per `COMMAND_INTERVAL`
        seconds per run, over the active executions in `live["nodes"]` order, round-robin across read attempts:
        one `zeroshot logs RUN --execution REF` that follows the run and normally ends on its own deadline
        (`complete` False). The retained lines are read whatever `complete` says; only the parser's rules
        (`live.last_command`) decide the stored value, so an unreadable log, an OSError (the reader cannot start)
        or no matching line leaves `live["command"]` as it was and never escapes `observe`. The throttle -- the last
        attempt's monotonic time (failed ones too), the round-robin position and the last accepted millisecond
        timestamp -- lives in memory on this controller, keyed by run id; nothing but `command` is persisted
        (A2-A5). The attempt time is `clock()`, an unrounded monotonic reading, so the interval is real seconds and
        not the second-floored `now()` stamp: a 29.1 s gap stays throttled instead of flooring to 30 s."""
        nodes = (r.get("live") or {}).get("nodes") or []
        if not nodes:
            return
        state = self.commands.setdefault(r["run_id"], {"at": None, "next": 0, "ms": None})
        stamp = clock()
        if state["at"] is not None and stamp - state["at"] < COMMAND_INTERVAL:
            return
        state["at"] = stamp
        order = [execution for _, execution in nodes]
        reference = order[state["next"] % len(order)]
        state["next"] += 1
        try:
            lines, _ = self.driver().log_records(r["binding"], r["run_id"], r["worktree"], execution=reference,
                                                 deadline=COMMAND_DEADLINE, buffer=LOG_LIMIT)
        except (Blocked, OSError, ValueError):
            return
        found = live.last_command(lines)
        if found is None:
            return
        at, text, ms = found
        command = r["live"].get("command")
        if state["ms"] is not None:
            if ms <= state["ms"]:
                return
        elif command is not None and at < command["at"]:
            return
        state["ms"] = ms
        r["live"]["command"] = {"at": at, "text": text}

    def record(self, r, status=None, cursor=None, event=False):
        """Live metadata of an attempt, written only while observing: heartbeat, last new event, active nodes and
        journal lines for stages and for manifest progress/amendments not written before."""
        data = r.setdefault("live", live.new())
        stamp = now()
        live.touch(data, stamp, event)
        if status is None:
            return
        if cursor:
            live.bounded(data["cursors"], cursor, live.CURSORS_LIMIT)
        manifest = read_manifest(r)
        progress = manifest["progress"] if manifest else []
        amendments = manifest["amendments"] if manifest else []
        # C4a: the task and round of the moment before `stages` moves them are the ones the departed reviewers were
        # reviewing; queue every reviewer that leaves this record.
        task, workers = data["task"], data["workers"]
        for node, execution in live.stages(data, status, stamp, [t["id"] for t in manifest["tasks"]] if manifest else ()):
            self.queue_verdict(r, node, execution, task, workers if task is not None and workers else None)
        if r["status"] == "stopping":
            live.note(data, "stop requested", stamp)
        for key, items, text in (("amendments", amendments, lambda a: "plan: " + amendment_text(a)),
                                 ("progress", progress, progress_text)):
            # History present when observation first started is not replayed into the journal.
            for item in items[len(items) if data[key] is None else data[key]:]:
                live.note(data, text(item), stamp)
            data[key] = len(items)

    def poll(self, r, mark=None, seconds=SLICE):
        """One observation slice for the UI: returns (events, mark) and updates `r` in place.

        Events are display lines (Russian) for new manifest progress and amendments and for native node changes
        since `mark` (None: from now on, no history replay). The UI only prints them and sends actions; every
        lifecycle decision stays here."""
        statuses = []
        if r["status"] in {"submitted", "running", "stopping"}:
            self.observe(r, seconds=seconds, seen=statuses.append)
        return activity(read_manifest(r), statuses, mark)

    def manifest(self, r):
        """The attempt's live manifest (worktree) or, once evaluated, the accepted one; None when unreadable."""
        return r["manifest"] or read_manifest(r)

    def status(self, r):
        """Public native status of the stored run id (read-only)."""
        require(r["run_id"] is not None, "The run has not been submitted yet.", family="action.refused")
        value = self.driver().status(r, r["run_id"])
        validate_projection(value, r["run_id"], watch=False)
        return value

    def failure_cause(self, r):
        """(cause, reset) of a failed attempt from its own run logs (R-3/R-4/R-6), or (None, None) when they do not
        say.

        Exactly one bounded read of the public `zeroshot logs <run_id>`, during a failed conclude and through the
        record's frozen binding, run id and worktree; a fixture record and a record without a run id read nothing.
        A nonzero exit, a timeout or a read failure leaves the cause unknown. Diagnosis only: nothing is retried,
        resumed or restarted because of it (R-7).

        The reset is the value G-2's one predicate accepts, re-checked here before it is persisted (extraction,
        the store and the surfaces apply the same predicate): a value the language does not carry is dropped whole
        and the cause alone is kept."""
        if r["engine"] != "native" or r["run_id"] is None:
            return None, None
        try:
            lines, complete = self.driver().log_records(r["binding"], r["run_id"], r["worktree"],
                                                        deadline=LOG_DEADLINE, buffer=LOG_LIMIT)
        except (Blocked, OSError, ValueError):
            return None, None
        if not complete:
            return None, None  # an incomplete read gives unknown, whatever its lines contain
        cause, reset = observed_cause(lines)
        return cause, reset_value(reset)

    def conclude(self, r, terminal):
        # Persist the native terminal result and root output first; manifest evaluation can be redone.
        if r["status"] == "stopping":
            r.update(status="stopped", terminal=copy.deepcopy(terminal),
                     diagnostic=terminal.get("reason", "Stopped on request."))
            self.save(r)
            return
        if terminal["status"] == "failed":
            r.update(status="failed", terminal=copy.deepcopy(terminal), diagnostic=terminal["reason"])
            self.save(r)
            try:
                recovery = self.status(r).get("workspaceRecovery") or {}
                r["recoverable"] = recovery.get("recoverable") is True
            except Blocked:
                pass  # the diagnosis below does not depend on the recovery status being readable
            # R-2/R-6: one bounded read of the frozen run's logs names the cause the terminal reason does not.
            cause, reset = self.failure_cause(r)
            r["cause"] = cause or CAUSE_UNKNOWN
            if reset is not None:
                r["reset"] = reset
            self.save(r)
            return
        try:
            output = validate_output(terminal["output"])
        except Blocked as error:
            r.update(status="finished", terminal=copy.deepcopy(terminal), output=None, outcome="invalid", diagnostic=str(error))
            self.save(r)
            return
        r.update(status="finished", terminal=copy.deepcopy(terminal), output=copy.deepcopy(output))
        self.save(r)
        self.evaluate(r)

    def evaluate(self, r):
        """done needs a baseline-consistent manifest with no open tasks; needs_owner/blocked keep diagnostics."""
        output = r["output"]
        manifest, problem = None, ""
        try:
            frozen = decode(self.frozen(r)["baseline"].read_text())
            worktree = Path(r["worktree"])
            milestone.check(canonical(decode((worktree / milestone.BASELINE).read_text())) == canonical(frozen),
                            "workspace baseline differs from the frozen submission baseline")
            manifest = milestone.validate(frozen, decode((worktree / milestone.MANIFEST).read_text()))
        except (Blocked, OSError, UnicodeError, KeyError, TypeError, ValueError) as error:
            problem = str(error) or type(error).__name__
        if output["signal"] == "done":
            remaining = [t["id"] for t in manifest["tasks"] if t["status"] == "open"] if manifest else []
            if manifest is None or remaining:
                r.update(outcome="invalid", manifest=manifest,
                         diagnostic="done without a valid manifest: " + (problem or "open tasks " + ", ".join(remaining)))
            else:
                r.update(outcome="done", manifest=manifest, diagnostic=output["message"])
                self.upgrade(r)
                # Freeze the product tree at acceptance; finish refuses a tree edited after this point.
                try:
                    r["result"] = {"branch": result_branch(r), "tree": self.product_tree(r), "commit": None}
                except Blocked as error:
                    r.update(outcome="invalid", result=None,
                             diagnostic="done, but the product tree is not frozen: %s" % (str(error) or "Blocked"))
        else:
            # An invalid manifest here is diagnostic evidence, not an adapter error.
            r.update(outcome=output["signal"], manifest=manifest,
                     diagnostic=output["message"] + ("; manifest: " + problem if problem else ""))
        self.save(r)

    # Control -----------------------------------------------------------------

    def stop(self, r):
        """Explicit owner request: persist stopping, then force-stop; observe until finished → stopped."""
        require(r["run_id"] is not None and r["status"] in {"submitted", "running", "stopping"},
                "Only a submitted active milestone run can be stopped.")
        self.check_binding(r)
        r["status"] = "stopping"
        self.save(r)
        self.driver().force_stop(r)
        return r

    def resume(self, r):
        """Resume a recoverable failed run once; the successor keeps the original submission and worktree."""
        require(r["status"] == "failed" and r["run_id"] is not None, "Resume is possible only for a failed run.", family="action.refused")
        self.check_current(r)
        require(all(e["predecessor"] != r["run_id"] for e in self.runs), "The run was already resumed; a repeated resume is forbidden.", family="action.refused")
        self.admit(r["milestone"], r["plan_revision"], extended(r)["context"], exclude=r)
        self.check_binding(r)
        recovery = self.status(r).get("workspaceRecovery") or {}
        require(recovery.get("recoverable") is True and not recovery.get("successorRunId"),
                "The run is not recoverable; a new attempt is needed.")
        r["recoverable"] = True
        stamp = now()
        successor = {**copy.deepcopy(EXTENSION), **copy.deepcopy(lineage(r)), "run_id": None, "predecessor": r["run_id"],
                     "status": "resume_pending", "cursor": None, "recoverable": None, "terminal": None, "output": None,
                     "outcome": None, "manifest": None, "diagnostic": "", "created": stamp, "updated": stamp}
        # The journal continues across the resume; the watch bookkeeping starts again for the new native run.
        successor["live"] = {**live.new(), "journal": copy.deepcopy(r.get("live", live.new())["journal"])}
        live.note(successor["live"], "resuming after a failure", stamp)
        self.authority.state["runs"].append(successor)
        # Persist the pending resume with its predecessor before dispatch.
        self.save(successor)
        receipt = self.driver().resume(successor, r["run_id"])
        successor.update(run_id=receipt["runId"], status="submitted")
        self.save(successor)
        return successor

    def adopt_successor(self, r):
        predecessor = r["predecessor"]
        value = self.driver().status(r, predecessor)
        validate_projection(value, predecessor, watch=False)
        successor = (value.get("workspaceRecovery") or {}).get("successorRunId")
        require(nonempty(successor), "The resume is not confirmed by native (no successorRunId); a repeated resume is forbidden. "
                "Check commands: [i] details.", family="milestone.lost")
        child = self.driver().status(r, successor)
        validate_projection(child, successor, watch=False)
        require((child.get("workspaceRecovery") or {}).get("resumedFrom") == predecessor,
                "The successor lineage is not confirmed; resume_pending is kept.")
        r.update(run_id=successor, status="submitted")
        self.save(r)

    # Delivery ----------------------------------------------------------------

    def product_tree(self, r):
        return product_tree(self.authority.project, r["worktree"], r["destination"]["base"])

    @staticmethod
    def upgrade(r):
        """Give a P3 record the P4 fields before the first delivery write."""
        for key, value in EXTENSION.items():
            r.setdefault(key, copy.deepcopy(value))

    def check_current(self, r):
        """New owner actions only on runs of the current approved revision -- or on the carried attempt the current
        revision selects (`carried_attempt`): its work is still to deliver, so finish/export and merge stay today's.
        Every other old record stays as it is."""
        a = self.authority
        a.check_project()
        revision = a.current
        current = (revision["status"] == "approved" and revision["approval"] == a.approval_identity(revision)
                   and r["plan_revision"] == revision["version"] and r["approval"] == revision["approval"])
        require(current or self.carried_attempt(r, revision), outdated(r, revision))
        return revision

    def finish(self, r):
        """Export a done attempt as one commit on its result branch; ends with delivery awaiting_merge.

        The record already holds the accepted manifest (task results, amendments, notes). Before the export intent
        is persisted the worktree must still hold exactly that manifest, the frozen baseline and the product tree
        frozen at acceptance; after a crash only a branch with exactly that tree on the base is adopted."""
        self.check_current(r)
        require(r["status"] == "finished" and r["outcome"] == "done", "Export is possible only for an accepted (done) attempt.", family="action.refused")
        self.upgrade(r)
        if r["delivery"] not in {"none", "exporting"}:
            return r
        project, worktree, base = self.authority.project, Path(r["worktree"]), r["destination"]["base"]
        require(not tracked(project, base, CONTROL), "The base commit tracks .zplan/ (zplan's service directory); export is forbidden.", family="export.reserved_path")
        self.check_worktree(r, at_base=False, action="export forbidden")
        if r["delivery"] == "none":
            frozen = decode(self.frozen(r)["baseline"].read_text())
            try:
                same = (canonical(decode((worktree / milestone.BASELINE).read_text())) == canonical(frozen)
                        and canonical(milestone.validate(frozen, decode((worktree / milestone.MANIFEST).read_text())))
                        == canonical(r["manifest"]))
            except (Blocked, OSError, UnicodeError, KeyError, TypeError, ValueError):
                same = False
            require(same, "The manifest or baseline in the worktree changed after acceptance; export is forbidden.", family="export.snapshot_changed")
            if r["result"] is None:
                # A record accepted before P4 has no frozen tree: freeze it now, before the export intent.
                r["result"] = {"branch": result_branch(r), "tree": self.product_tree(r), "commit": None}
            require(self.product_tree(r) == r["result"]["tree"], "The product tree changed after acceptance; export is forbidden.", family="export.snapshot_changed")
            r["delivery"] = "exporting"
            self.save(r)
        tree = r["result"]["tree"]
        message = ["zplan: %s" % title(r), "Plan approval %s; product tree %s." % (r["approval"][:8], tree)]
        sha, _ = create_branch(project, worktree, base, r["result"]["branch"], message,
                               lambda: self.product_tree(r) == tree, exclude=CONTROL)
        r["result"]["commit"] = sha
        r["delivery"] = "awaiting_merge"
        self.save(r)
        return r

    @staticmethod
    def merging(project):
        """True while the project has an unfinished merge (MERGE_HEAD)."""
        return git_call(project, "rev-parse", "-q", "--verify", "MERGE_HEAD").returncode == 0

    def merge(self, r, resolved=None, critic=None, slice=None):
        """Owner-confirmed merge of the result commit into its destination branch.

        Only on a target whose HEAD is that branch, with the owner's configured Git user, and never while a merge is
        unfinished; uncommitted changes do not block it. Both paths build the merge commit off-tree (`merge_tree`,
        `commit_candidate`) and land it with `merge --ff-only` (`land`): a conflict is recorded from `merge-tree` and
        the owner's tree is never written, so nothing is aborted; a landing that would write over an untracked,
        ignored or modified file is refused (`Overlap`). With `gates.merge: required` in `resolved` the merge is
        gated (`gate_merge`). `critic(r, gate, paths)` runs the merge critic of one gated candidate
        after its checks passed and returns its record or raises a refusal; a raised-reason candidate lands only on a
        stored `go` for its exact identity (`gate_merge`); `slice` bounds the critic's observation."""
        self.check_current(r)
        self.upgrade(r)
        require(r["delivery"] in {"awaiting_merge", "conflict"}, "Merge is possible only for an exported result.", family="action.refused")
        project = self.authority.project
        require(not self.merging(project), "A merge is not finished in the project (MERGE_HEAD): finish it or run git merge --abort.",
                family="milestone.merge_refused")
        self.refresh()
        if r["delivery"] == "integrated":
            return r
        ref, sha = "refs/heads/" + r["destination"]["branch"], r["result"]["commit"]
        require(git_call(project, "symbolic-ref", "--quiet", "HEAD").stdout.decode().strip() == ref,
                "The merge goes into %s: switch to it (git switch %s)." % (ref[11:], ref[11:]), family="readiness.branch")
        identity = configured_identity(project)
        require(identity is not None, "Git user.name/user.email are not configured; merge forbidden (git config user.name ...).", family="readiness.identity")
        if resolved is not None and resolved.config["gates"]["merge"] == "required":
            return self.gate_merge(r, resolved, identity, critic, slice)
        head = run_git(project, "rev-parse", "HEAD")
        tree = self.merge_tree(r, ref, head, sha, project)
        if tree is None:  # a conflicted merge: recorded, the tree is untouched
            return r
        candidate = commit_candidate(project, r, tree, head, sha, identity)
        return self.land(r, ref, head, candidate, project)

    def merge_tree(self, r, ref, head, result, project):
        """The tree of the merge of (head, result), built off-tree by `merge-tree --write-tree`. A conflicting merge
        is recorded from `merge-tree` and returns None: nothing is written to the owner's tree, so nothing is aborted."""
        merged = git_call(project, "merge-tree", "--write-tree", "--name-only", "-z", head, result)
        fields = merged.stdout.decode(errors="replace").split("\0")
        conflicts = []
        for path in fields[1:]:
            if not path:
                break
            conflicts.append(path)
        if merged.returncode == 1 and conflicts:
            r.update(delivery="conflict", integration={"destination": ref, "commit": None,
                                                       "conflicts": sorted(set(conflicts)), "aborted": True})
            self.save(r)
            return None
        tree = fields[0]
        require(merged.returncode == 0 and SHA.fullmatch(tree), "Git did not build a conflict-free merge candidate; the state is unchanged.",
                family="milestone.merge_refused")
        return tree

    def land(self, r, ref, head, candidate, project, pinned=None):
        """Land an off-tree merge commit with `merge --ff-only`, beside the owner's uncommitted changes.

        Everything is re-read right before landing: the branch, HEAD, an unfinished merge, the profile (`pinned`)
        and the owner's dirty set. Landing is refused (`Overlap`, one refusal naming the paths) when a path the
        commit changes, or a parent of one, exists on disk as untracked, ignored or modified; changes that do not
        overlap never block. The dirty set must be the same right before and after the landing; if it is not, the
        merge stays landed and the difference is recorded on the run -- zplan never resets or checks out."""
        unchanged = (git_call(project, "symbolic-ref", "--quiet", "HEAD").stdout.decode().strip() == ref
                     and git_call(project, "rev-parse", "HEAD").stdout.decode().strip() == head
                     and not self.merging(project) and (pinned is None or self.authority.live_profile_digest() == pinned))
        require(unchanged, "The project or profile changed during the checks; the merge was not done: repeat it.",
                family="milestone.merge_refused")
        before = dirty_entries(project)
        overlap = overlapping_paths(project, candidate, before)
        if overlap:
            raise Overlap(overlap, r["result"]["branch"])
        landed = git_call(project, "merge", "--ff-only", "--no-squash", "--no-autostash", candidate)
        require(landed.returncode == 0 and git_call(project, "rev-parse", "HEAD").stdout.decode().strip() == candidate,
                "Git did not merge the verified candidate %s; check %s." % (candidate[:12], ref[11:]), family="milestone.merge_refused")
        after = dirty_entries(project)
        prior = r["integration"] or {"conflicts": [], "aborted": None}
        integration = {"destination": ref, "commit": candidate, "conflicts": prior["conflicts"], "aborted": prior["aborted"]}
        if after != before:
            changed = sorted({entry_path(e) for e in before ^ after})
            integration["landing"] = "The set of your changes in the tree changed during the merge (%s); commit %s is merged, " \
                "the tree was not touched: check git status." % (project_read.shown_paths(changed), candidate[:12])
        r.update(delivery="integrated", integration=integration)
        self.save(r)
        return r

    def gate_merge(self, r, resolved, identity, critic=None, slice=None):
        """The gated merge (A7a) with the merge critic (A7b2): a candidate commit of the destination head and the
        result is built without touching the tree, the project checks run on exactly that commit, then the merge
        critic judges the candidate and only its `go` for exactly that identity lets it land.

        The destination ref, head, result and configuration digest are read once and used as literal SHAs. A
        conflict is detected on the candidate (`merge-tree`), recorded and needs no abort. A stored gate that names
        this destination, head, result and configuration with `passed` evidence is reused: its candidate commit and
        check evidence are this merge's, so no second `commit-tree` is made and the checks do not run again. The gate
        record is saved before landing, whatever the checks found. A candidate whose risk classifies is judged by
        `critic` (`Delivery`'s merge-critic run), which returns its record for a `go` or raises a refusal -- a pending
        or blocked critic lands nothing. Landing (`land`) re-reads the project: if HEAD, its branch, an unfinished
        merge or the configuration changed during the checks or the critic, nothing is merged and a later merge builds
        a new candidate. The candidate's message states `passed` before the checks ran: the commit only lands if they
        did. Its risk is read from the diff of the head against the candidate's tree (the candidate's own diff, known
        before the message that carries the tier is written)."""
        project, config = self.authority.project, resolved.config
        ref, branch, result = "refs/heads/" + r["destination"]["branch"], r["result"]["branch"], r["result"]["commit"]
        head, pinned = run_git(project, "rev-parse", "HEAD"), resolved.digest
        gate = reusable_gate(r.get("gate"), ref, head, result, pinned)
        if gate is None:
            built = self.gate_candidate(r, config, ref, branch, result, head, pinned, identity, project)
            if built is None:  # a conflicted candidate: recorded, the tree is untouched
                return r
            gate, paths = built
        else:
            paths = gate_paths(project, head, gate["tree"])
        if gate["evidence"]["outcome"] != "passed":
            failed = next(c for c in gate["evidence"]["checks"] if c["status"] != 0)
            raise Blocked("The check '%s' failed (%s); the merge was not done." % (failed["name"], failed["status"]),
                          family="merge.checks_failed")
        names = merge_critic.reasons(gate["risk"], {})
        if names:
            # The landing itself requires a stored `go` for exactly this candidate: a missing callback, a None, a
            # `block` or another identity from it never lands.
            record = critic(r, gate, paths) if critic is not None else None
            identity = critic_identity(r, gate, paths, names, self.critic_briefs(r))
            stored = next((c for c in self.authority.state.get("critics", [])
                           if record is not None and c["id"] == record.get("id")), None)
            require(stored is not None and merge_critic.allows(stored, identity),
                    "The merge check did not allow merging candidate %s; the merge was not done." % gate["candidate"][:12],
                    family="merge.critic_failed")
            if gate.get("critic") != stored["id"]:
                gate["critic"] = stored["id"]
                self.save(r)
        return self.land(r, ref, head, gate["candidate"], project, pinned)

    def gate_candidate(self, r, config, ref, branch, result, head, pinned, identity, project):
        """Build the candidate commit of (head, result), run the project's checks on exactly it and store the gate
        record (A7a); a conflicting merge is recorded and returns None. The record is saved before its evidence is
        judged: a run that produced evidence keeps it whatever the checks found. The candidate and the changed paths
        are returned together, so the risk and the critic input read the same diff."""
        tree = self.merge_tree(r, ref, head, result, project)
        if tree is None:
            return None
        require(config["checks"], "The merge check is on but there are no checks: add checks to zplan.process.json.",
                family="merge.no_checks")
        paths = gate_paths(project, head, tree)
        risk = risk_of(config, paths) if "risk" in config else {"tier": "high", "triggers": [], "unmatched": []}
        candidate = commit_candidate(project, r, tree, head, result, identity,
                                     "Risk-Tier: %s\nChecks: %s passed" % (risk["tier"], digest(config["checks"])))
        from .setup import data_root
        try:
            evidence = checks.qualify(project, candidate, tree, config["checks"], data_root() / "checkouts")
        except ValueError as error:
            raise Blocked("The candidate checks did not start (%s); the merge was not done." % error, family="merge.checks_failed") from error
        if "outcome" not in evidence:
            raise Blocked("The candidate checks did not start: checkout refused (%s); the merge was not done." % evidence["refused"],
                          family="merge.checks_failed")
        r["gate"] = {"destination": ref, "head": head, "result": result, "candidate": candidate, "tree": tree,
                     "config_digest": pinned, "checks": copy.deepcopy(config["checks"]), "evidence": evidence,
                     "risk": risk, "critic": None}
        self.save(r)
        return r["gate"], paths

    def refresh(self):
        """Integration is ancestry now: record manual merges and branch resets for the current revision's results
        and for the older results of the milestones the current revision still carries -- a carried attempt is
        reconciled like a fresh one, so a manual merge stops holding its dependents back (and a branch reset takes
        the confirmation away again)."""
        runs = self.runs
        if not runs:
            return
        revision = self.authority.current
        project, version = self.authority.project, revision["version"]
        memo = {}
        for r in runs:
            x = extended(r)
            if (x["result"] is None or x["result"]["commit"] is None
                    or (r["plan_revision"] != version and not self.carried_scope(r, revision, memo))):
                continue
            ref, sha = "refs/heads/" + r["destination"]["branch"], x["result"]["commit"]
            tip = resolve_ref(project, ref)
            merged = tip is not None and has_commit(project, sha) and is_ancestor(project, sha, tip)
            prior = x["integration"] or {"conflicts": [], "aborted": None}
            if merged and x["delivery"] != "integrated":
                r.update(delivery="integrated", integration={"destination": ref, "commit": integration_commit(project, sha, tip),
                                                             "conflicts": prior["conflicts"], "aborted": prior["aborted"]})
                self.save(r)
            elif not merged and x["delivery"] == "integrated":
                r["delivery"] = "awaiting_merge"
                r["integration"]["commit"] = None
                self.save(r)

    def waiting(self, milestone_id, base=None, memo=None):
        """Dependencies of `milestone_id` not yet delivered into `base` (default HEAD) under the current approved
        revision; an older revision's result counts only when carried forward unchanged."""
        a = self.authority
        revision = a.current
        base = base or run_git(a.project, "rev-parse", "HEAD")
        memo = {} if memo is None else memo
        found = next(m for m in revision["proposal"]["milestones"] if m["id"] == milestone_id)
        return [d for d in found["depends_on"] if not any(self.delivered(r, d, revision, base, memo) for r in self.runs)]

    def delivered(self, r, milestone_id, revision, base, memo=None):
        """Confirmed integration only: delivery `integrated`, the result still an ancestor of its recorded destination
        branch, and an ancestor of `base`. A checked-out or reachable result branch alone never counts."""
        x = extended(r)
        if r["milestone"] != milestone_id or x["delivery"] != "integrated" or x["result"]["commit"] is None:
            return False
        if r["plan_revision"] != revision["version"]:
            old = self.authority.state["revisions"][r["plan_revision"] - 1]["proposal"]
            if not carried(old, revision["proposal"], milestone_id, memo):
                return False
        project, commit = self.authority.project, x["result"]["commit"]
        tip = resolve_ref(project, x["integration"]["destination"])
        return (tip is not None and has_commit(project, commit) and is_ancestor(project, commit, tip)
                and (base is None or is_ancestor(project, commit, base)))

    def carried_scope(self, r, revision, memo=None):
        """`carried(r's own revision's proposal, the current proposal, r's milestone)`: the milestone's whole scope
        and, transitively, its dependencies' scopes are unchanged since `r` was approved."""
        if revision["status"] != "approved" or not revision["proposal"]:
            return False
        old = self.authority.state["revisions"][r["plan_revision"] - 1]["proposal"]
        return carried(old, revision["proposal"], r["milestone"], memo)

    def current_record(self, milestone_id, revision=None, memo=None):
        """The one record of `milestone_id` under the current approved revision: its last attempt of this revision
        (`mine[-1]`, as before); else today's carried integrated result; else the carried attempt -- the last older
        revision's record in store order whose scope and, transitively, whose dependencies' scopes are unchanged
        and whose work is still to deliver (`run_state` `awaiting_merge`/`conflict`: finish/export or merge); else
        None (the row stays `ready`/`waiting`). `memo` is the one refresh's carried-comparison cache."""
        a = self.authority
        revision = revision or a.current
        mine = [r for r in self.runs if r["plan_revision"] == revision["version"] and r["milestone"] == milestone_id]
        if mine:
            return mine[-1]
        older = [r for r in self.runs if r["plan_revision"] != revision["version"] and r["milestone"] == milestone_id]
        integrated = next((r for r in reversed(older) if self.delivered(r, milestone_id, revision, None, memo)), None)
        if integrated is not None:
            return integrated
        return next((r for r in reversed(older) if run_state(r) in ("awaiting_merge", "conflict")
                     and self.carried_scope(r, revision, memo)), None)

    def carried_attempt(self, r, revision=None):
        """True while `r` is the older-revision attempt the current approved revision selects (`current_record`):
        its milestone's scope is unchanged and its work is still to deliver, so `check_current` lets today's
        actions through; every other older record keeps the `Revision N is stale` refusal."""
        revision = revision or self.authority.current
        if not (revision["status"] == "approved"
                and revision["approval"] == self.authority.approval_identity(revision)
                and r["plan_revision"] != revision["version"] and run_state(r) in ("awaiting_merge", "conflict")):
            return False
        selected = self.current_record(r["milestone"], revision)
        return (selected is not None and selected["plan_revision"] == r["plan_revision"]
                and selected["attempt"] == r["attempt"] and selected["run_id"] == r["run_id"])

    # Read views for the terminal UI ------------------------------------------

    def workspace(self):
        """(current branch or None when detached, clean) of the target project."""
        project = self.authority.project
        found = git_call(project, "symbolic-ref", "--quiet", "--short", "HEAD")
        clean = not git(project, "status", "--porcelain=v1", "--untracked-files=all").strip()
        return (found.stdout.decode(errors="replace").strip() or None) if found.returncode == 0 else None, clean

    def uncommitted(self):
        """The paths of the target project the last commit does not hold; nothing is changed."""
        return project_read.uncommitted_paths(self.authority.project)

    def changes(self, limit=50):
        """`git status --short` of the target project, at most `limit` lines; nothing is changed."""
        lines = git(self.authority.project, "status", "--short", "--untracked-files=all").decode(errors="replace").splitlines()
        return lines[:limit] + (["… %s more" % (len(lines) - limit)] if len(lines) > limit else [])

    def overview(self, live=True):
        """Home screen view of the current approved revision, one entry per milestone in plan order.

        Only integration is detected (refresh); nothing is dispatched, resumed, stopped or exported. Each entry
        holds the record the current revision selects for the milestone (`record` = `current_record`: its latest
        attempt or resume successor, an integrated older revision's result carried forward unchanged, or a carried
        attempt); `carried` names a record of an older revision; `state` is one of MILESTONE_STATES.
        `live=False` never asks native Zeroshot for the active node (the manifest progress is used instead)."""
        a = self.authority
        if not (a.state and a.state["revisions"]) or a.current["status"] != "approved":
            return []
        self.refresh()
        revision, memo, items = a.current, {}, []
        head = resolve_ref(a.project, "HEAD")
        for m in revision["proposal"]["milestones"]:
            record = self.current_record(m["id"], revision, memo)
            item = {"id": m["id"], "title": m["title"], "record": record,
                    "carried": record is not None and record["plan_revision"] != revision["version"],
                    "waiting": [], "task": None, "phase": None}
            if record is None:
                item["waiting"] = self.waiting(m["id"], head, memo) if head else list(m["depends_on"])
                item["state"] = "waiting" if item["waiting"] else "ready"
            else:
                item["state"] = run_state(record)
            if item["state"] == "running":
                item.update(self.activity_now(record, live))
            items.append(item)
        return items

    def activity_now(self, r, live=True):
        """Current task (i, n, id) and phase of an active attempt: the native active node (read-only status),
        else the latest manifest progress record."""
        manifest = read_manifest(r)
        found = current_task(manifest)
        phase = None
        if r["status"] == "stopping":
            phase = "stopping…"
        elif live and r["run_id"] is not None and self.engine is not None:
            try:
                nodes = [e["node"] for e in self.status(r)["status"].get("activeExecutions", [])]
            except (Blocked, OSError, KeyError, TypeError, AttributeError):
                nodes = []
            labels = [node_label(node, found[2] if found else "") for node in nodes]
            phase = next((label.split(" · ", 1)[-1] for label in labels if label), None)
        if phase is None and manifest and manifest["progress"]:
            phase = progress_text(manifest["progress"][-1])
        return {"task": found, "phase": phase}

    def preview(self, milestone_id, roles, attempt=None):
        """What a start would create, shown before the owner confirms; no side effects."""
        a = self.authority
        revision = a.current
        require(revision["status"] == "approved", "The plan is not approved.", family="action.refused")
        found = next((m for m in revision["proposal"]["milestones"] if m["id"] == milestone_id), None)
        require(found is not None, "Milestone %s is not in the approved plan." % milestone_id, family="action.refused")
        attempt = attempt or 1 + sum(r["plan_revision"] == revision["version"] and r["milestone"] == milestone_id
                                     and r["predecessor"] is None for r in self.runs)
        branch, name = names(a.project_id, revision["approval"], milestone_id, attempt)
        baseline = milestone.build_baseline(revision["proposal"], milestone_id, revision["version"])
        destination, _ = self.workspace()
        return {"milestone": found, "attempt": attempt, "worktree": str(self.worktrees / name), "branch": branch,
                "result": result_branch({"milestone": milestone_id, "plan_revision": revision["version"],
                                         "approval": revision["approval"], "attempt": attempt}),
                "destination": destination, "base": resolve_ref(a.project, "HEAD"),
                "roles": {role: copy.deepcopy(roles[role]) for role in EXECUTION_ROLES if role in roles},
                "tasks": len(baseline["tasks"]), "limits": baseline["limits"]}

    def diff(self, r, limit=None):
        """`git diff --stat` of an exported result against its base, or (limit) the bounded full diff."""
        x = extended(r)
        require(x["result"] is not None and x["result"]["commit"] is not None, "The result is not exported yet.", family="action.refused")
        options = ("--stat",) if limit is None else ("--no-color", "--no-ext-diff")
        result = git_call(self.authority.project, "diff", *options, r["destination"]["base"], x["result"]["commit"])
        require(result.returncode == 0, "Git did not show the diff of the result.", family="git.failed")
        text = result.stdout.decode(errors="replace").rstrip("\n")
        if limit is not None and len(text) > limit:
            text = text[:limit].rsplit("\n", 1)[0] + "\n… (truncated; in full: git diff %s %s)" % (
                r["destination"]["base"][:12], x["result"]["branch"])
        return text

    def merge_state(self, limit=20):
        """Bounded `git status` lines of the target (shown when a merge abort failed)."""
        lines = git(self.authority.project, "status", "--porcelain=v1").decode(errors="replace").splitlines()
        return lines[:limit] + (["…"] if len(lines) > limit else [])

    def retry(self, r, text="", roles=None):
        """New attempt after an unsuccessful one, from destination HEAD; the owner's note is optional. `roles` are
        the accepted profile's current roles; without them the attempt inherits the previous attempt's."""
        if nonempty(text):
            return self.answer(r, text, roles)
        self.check_followup(r)
        return self.start(r["milestone"], r["plan_revision"], roles or r["roles"], destination=r["destination"]["branch"])

    def revise_plan(self, text, roles=None):
        """Owner plan revision from home. `roles` as in `retry`; the no-active-writer precondition is the one
        `Authority.begin` enforces (the mutation that owns the state)."""
        require(nonempty(text), "Text is required: what to change in the plan.", family="action.refused")
        current = self.authority.current
        return self.authority.begin(current["goal"], roles or current["roles"], current["engine"],
                                    feedback=self.authority.amended_feedback(text))

    # Owner actions -----------------------------------------------------------

    def check_followup(self, r):
        """A fresh attempt or revision follows only the latest, unsuccessful attempt of the current revision."""
        revision = self.check_current(r)
        # check_current also passes the carried attempt; a follow-up never does (it starts work of its own).
        require(r["plan_revision"] == revision["version"], outdated(r, revision))
        require(r["status"] in TERMINAL and r["outcome"] != "done", "A new attempt is needed only after an unsuccessful attempt.", family="action.refused")
        later = [e for e in self.runs if e["plan_revision"] == r["plan_revision"] and e["milestone"] == r["milestone"]
                 and (e["attempt"] > r["attempt"] or r["run_id"] is not None and e["predecessor"] == r["run_id"])]
        require(not later, "Attempt %s is no longer the last; act on the last attempt." % r["attempt"])
        return revision

    def answer(self, r, text, roles=None):
        """Owner answer → fresh attempt from destination HEAD; the answer is a note on every (re)opened task."""
        require(nonempty(text), "The text of the answer is required.", family="action.refused")
        self.check_followup(r)
        return self.start(r["milestone"], r["plan_revision"], roles or r["roles"],
                          {"kind": "answer", "source": r["attempt"], "text": text, "candidate": None},
                          destination=r["destination"]["branch"])

    def candidate(self, r):
        """(candidate, None) when the steward proposal is a well-formed task list that fits the frozen milestone
        baseline; otherwise (None, diagnostic or None for plain text): accepting it only opens a plan revision."""
        proposal = (r["output"] or {}).get("proposal")
        candidate = structured(proposal)
        if candidate is None:
            try:
                value = decode(proposal) if isinstance(proposal, str) else None
            except Blocked:
                value = None
            return None, ("candidate: malformed task list" if isinstance(value, dict) else None)
        revision = self.authority.state["revisions"][r["plan_revision"] - 1]
        context = {"kind": "proposal", "source": r["attempt"], "text": "check", "candidate": candidate}
        try:
            bootstrap_manifest(milestone.build_baseline(revision["proposal"], r["milestone"], r["plan_revision"]), context)
        except Blocked as error:
            return None, str(error) or "candidate does not fit the milestone"
        return candidate, None

    def accept_proposal(self, r, roles=None):
        """needs_owner: a structured in-scope candidate → ("attempt", run); otherwise → ("plan", new revision)."""
        self.check_followup(r)
        require(r["outcome"] == "needs_owner" and nonempty(r["output"].get("proposal")), "There is no steward proposal to accept.", family="action.refused")
        output = r["output"]
        candidate, _ = self.candidate(r)
        if candidate is not None:
            text = next(v for v in (output.get("question"), output["message"], "Proposal accepted.") if nonempty(v))
            context = {"kind": "proposal", "source": r["attempt"], "text": text, "candidate": candidate}
            return "attempt", self.start(r["milestone"], r["plan_revision"], roles or r["roles"], context,
                                         destination=r["destination"]["branch"])
        question = output.get("question") or output["message"]
        return "plan", self.revise(r, "Steward question: %s\nAccepted proposal: %s" % (question, output["proposal"]), roles)

    def revise(self, r, text, roles=None):
        """Back to planning: plan begin with the owner's feedback (this compares the planning baseline)."""
        require(nonempty(text), "Text is required for revise.", family="action.refused")
        revision = self.check_followup(r)
        return self.authority.begin(revision["goal"], roles or revision["roles"], revision["engine"], feedback=self.authority.amended_feedback(
            "Milestone %s attempt %s: %s" % (r["milestone"], r["attempt"], text)))


class NativeDriver(NativeEngine):
    """Pinned public CLI for milestone runs, from inside the retained worktree."""

    def binding(self, authority):
        require(authority.fixture_id is None, "Fixture authority cannot submit native runs.", family="usage.invalid_option")
        return self.binary_identity()

    @staticmethod
    def arguments(r, paths):
        return ["run", "--title", title(r), "--graph", str(paths["graph"]), "--runtime-config", str(paths["runtime"]),
                "--input", str(paths["input"]), "--no-environment", "--submission-key", r["submission_key"]]

    def validate(self, r, paths):
        engine = self.engine_for(r["binding"])
        # 10.12 refuses a workspace overlapping `<native_state_root>/runs` (its ZEROSHOT_STATE_DIR); compare the
        # submitted worktree with the same state root before any native call, fresh submission and replay alike.
        require_workspace_outside_state(r["worktree"], engine.state_root, family="milestone.preflight")
        result = engine.invoke(r["worktree"], *self.arguments(r, paths), "--validate-only")
        if not (len(result) == 1 and isinstance(result[0], dict) and result[0].get("valid") is True):
            raise Rejected("Native admission rejected the frozen submission.", family="engine.rejected")

    def submit(self, r, paths):
        receipt = self.engine_for(r["binding"]).invoke(r["worktree"], *self.arguments(r, paths), "--detach")
        require(len(receipt) == 1, "There is no unambiguous receipt; submission_unknown.", family="submission.unknown")
        validate_receipt(receipt[0])
        return receipt[0]

    def watch(self, r, after, seconds=None):
        return self.engine_for(r["binding"]).invoke(r["worktree"], "watch", r["run_id"],
                                                    *(["--after", after] if after else []), slice=seconds)

    def status(self, r, run_id):
        result = self.engine_for(r["binding"]).invoke(r["worktree"], "status", run_id)
        require(len(result) == 1, "There is no unambiguous native status.", family="engine.bad_output")
        return result[0]

    def force_stop(self, r):
        # The force-stop output shape is not a qualified contract: only the exit status counts;
        # the stop is confirmed by observing the finished run.
        engine = self.engine_for(r.get("binding"))
        check_socket_path(engine.state_root)
        try:
            result = engine.call([engine.executable, "force-stop", r["run_id"]], cwd=r["worktree"],
                                 env=engine.native_environment(), capture_output=True, text=True, timeout=120,
                                 start_new_session=True)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise Blocked("Native force-stop did not answer; the run stays stopping, watch it.", family="milestone.stop_unconfirmed") from error
        require(result.returncode == 0, "Native force-stop was refused (exit %s); the run stays stopping." % result.returncode)

    def resume(self, r, run_id):
        result = self.engine_for(r["binding"]).invoke(r["worktree"], "resume", run_id)
        require(len(result) == 1 and isinstance(result[0], dict) and set(result[0]) == {"runId", "resumedFrom"}
                and nonempty(result[0]["runId"]) and result[0]["resumedFrom"] == run_id,
                "There is no unambiguous resume receipt; resume_pending is kept.")
        return result[0]


class FixtureDriver:
    """Deterministic driver engine for UX journeys: no binary, no model, scripted outcome.

    Submission persists a running state with a scripted step list under `state_root` (per open task: worker,
    reviews, `rejections` repairs of the first task, steward; then the final verification). Each bounded watch
    slice advances one step (an unbounded watch streams to the end, like native): the first worker step writes one
    uncommitted file, the steward step accepts the task in the manifest, the last step applies the outcome. A
    force-stop persists `stopping`; the next slice reports it and the run finishes as stopped.
    `outcome` may be a tuple: attempt n gets outcome[n-1] (the last one repeats).
    """

    name = "fixture"

    def __init__(self, state_root, outcome="done", proposal="Fixture: split the first task.", rejections=0, delay=0):
        outcomes = (outcome,) if isinstance(outcome, str) else tuple(outcome)
        require(outcomes and all(o in FIXTURE_OUTCOMES for o in outcomes), "Unknown fixture outcome.")
        self.state_root = Path(state_root).expanduser().resolve()
        self.outcomes = outcomes
        self.proposal = proposal
        self.rejections = rejections
        self.delay = delay

    @property
    def outcome(self):
        return self.outcomes[0]

    def binding(self, authority):
        require(authority.fixture_id is not None, "The fixture driver requires fixture authority.", family="usage.invalid_option")
        return {"fixture_id": authority.fixture_id}

    def engine_for(self, binding):
        return self

    def path(self, run_id):
        return self.state_root / (run_id + ".json")

    def load(self, run_id):
        try:
            return decode(self.path(run_id).read_text())
        except OSError as error:
            raise Blocked("Fixture run %s not found." % run_id, family="store.invalid") from error

    def store(self, state):
        self.state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        atomic_state(self.path(state["runId"]), state)

    def validate(self, r, paths):
        require(all(Path(p).is_file() for p in paths.values()), "Fixture admission: the frozen documents are missing.")

    def submit(self, r, paths):
        run_id = "fixture-" + hashlib.sha256(r["submission_key"].encode()).hexdigest()[:16]
        if not self.path(run_id).exists():
            # Same key, same run: mirrors native submission idempotence.
            self.begin(r, run_id, self.outcomes[min(r["attempt"], len(self.outcomes)) - 1], None)
        return {"runId": run_id}

    def begin(self, r, run_id, outcome, predecessor):
        manifest = decode((Path(r["worktree"]) / milestone.MANIFEST).read_text())
        steps = []
        for index, task in enumerate(t["id"] for t in manifest["tasks"] if t["status"] == "open"):
            rounds = 1 + (self.rejections if index == 0 and outcome == "done" else 0)
            for n in range(1, rounds + 1):
                steps.append({"nodes": [["worker", "%s-w%s" % (task, n)]], "action": "change"})
                if outcome.startswith("failed"):
                    break
                steps.append({"nodes": [["acceptance_review", "%s-a%s" % (task, n)], ["code_review", "%s-c%s" % (task, n)]],
                              "action": None})
            if outcome != "done":
                break
            steps.append({"nodes": [["steward_apply", "%s-s" % task]], "action": "accept:" + task})
        if outcome == "done":
            steps.append({"nodes": [["final_verify", "final-1"]], "action": None})
        self.store({"runId": run_id, "title": title(r), "branch": r["branch"], "revision": r["destination"]["base"],
                    "worktree": r["worktree"], "milestone": r["milestone"], "outcome": outcome, "steps": steps,
                    "position": 0, "stopping": False, "terminal": None, "recoverable": False,
                    "resumedFrom": predecessor, "successorRunId": None})

    def apply(self, state, action):
        worktree = Path(state["worktree"])
        if action == "change":
            path, line = worktree / "ZPLAN_FIXTURE.md", "Fixture driver change for milestone %s; no model ran.\n" % state["milestone"]
            before = path.read_text() if path.exists() else ""
            if line not in before:
                # One line per milestone: a later milestone's result differs from its base too.
                path.write_text(before + line)
        elif action and action.startswith("accept:"):
            manifest = decode((worktree / milestone.MANIFEST).read_text())
            self.accept(manifest, action[len("accept:"):])
            atomic_state(worktree / milestone.MANIFEST, manifest)

    @staticmethod
    def accept(manifest, task_id):
        for task in manifest["tasks"]:
            if task["id"] == task_id and task["status"] == "open":
                task["status"] = "done"
                manifest["progress"].append({"seq": len(manifest["progress"]) + 1, "task": task["id"],
                                             "phase": "accepted", "text": "Fixture: both reviews accepted."})

    def conclude(self, state):
        """The scripted outcome, applied once the steps run out."""
        outcome, worktree = state["outcome"], Path(state["worktree"])
        self.apply(state, "change")
        manifest = decode((worktree / milestone.MANIFEST).read_text())
        output = {"signal": outcome, "message": "Fixture driver: %s; no model ran." % outcome, "question": None, "proposal": None}
        if outcome == "done":
            for task in list(manifest["tasks"]):
                self.accept(manifest, task["id"])
        elif outcome in ("needs_owner", "blocked"):
            first = next((t for t in manifest["tasks"] if t["status"] == "open"), None)
            if first is not None:
                first["notes"] = "Fixture: %s." % outcome
            if outcome == "needs_owner":
                output.update(question="Fixture: approve the scope change?", proposal=self.proposal)
        atomic_state(worktree / milestone.MANIFEST, manifest)
        state["terminal"] = ({"status": "failed", "reason": "fixture_failed"} if outcome.startswith("failed")
                             else {"status": "succeeded", "output": output})
        state["recoverable"] = outcome == "failed_recoverable"

    @staticmethod
    def projection(state, watch=True):
        if state["terminal"] is not None:
            status, cursor = {"phase": "finished", "terminalResult": state["terminal"]}, FIXTURE_CURSOR
        else:
            step = state["steps"][state["position"] - 1] if state["position"] else {"nodes": [["select_init", "init"]]}
            status = {"phase": "stopping" if state["stopping"] else "running",
                      "activeExecutions": [] if state["stopping"] else
                      [{"node": node, "execution": execution} for node, execution in step["nodes"]]}
            cursor = "fixture:%s%s" % (state["position"], "s" if state["stopping"] else "")
        value = {"runId": state["runId"], "title": state["title"], "size": "medium",
                 "source": {"repository": "fixture/project", "branch": state["branch"], "revision": state["revision"]},
                 "status": status}
        if watch:
            value.update(subscriptionId="fixture", cursor=cursor)
        else:
            value["atCursor"] = cursor
            value["workspaceRecovery"] = {"recoverable": state["recoverable"], **{
                k: state[k] for k in ("resumedFrom", "successorRunId") if state[k] is not None}}
        return value

    def advance(self, state):
        """One step of the persisted script; returns the projection to report."""
        if state["terminal"] is None and state["stopping"]:
            # Reported once as stopping; the run is already finished as stopped for the next slice.
            state["terminal"] = {"status": "failed", "reason": "Stopped at the owner's request."}
            self.store(state)
            return self.projection({**state, "terminal": None})
        if state["terminal"] is None and state["position"] < len(state["steps"]):
            self.apply(state, state["steps"][state["position"]]["action"])
            state["position"] += 1
        elif state["terminal"] is None:
            self.conclude(state)
        self.store(state)
        return self.projection(state)

    def watch(self, r, after, seconds=None):
        if after == FIXTURE_CURSOR:
            return []
        if seconds and self.delay:
            time.sleep(min(self.delay, seconds))
        values = [self.advance(self.load(r["run_id"]))]
        while not seconds and values[-1]["status"]["phase"] != "finished":
            values.append(self.advance(self.load(r["run_id"])))
        return values

    def status(self, r, run_id):
        return self.projection(self.load(run_id), watch=False)

    def log_tail(self, binding, run_id, cwd, lines=live.TAIL_LINES, **options):
        """Deterministic stand-in for `zeroshot logs`: one line per executed step of the scripted run."""
        state = self.load(run_id)
        done = state["steps"][:state["position"]]
        text = ["fixture log %s: %s" % (run_id, ", ".join(node for node, _ in step["nodes"])) for step in done]
        return (text or ["fixture log %s: empty so far" % run_id])[-lines:]

    def log_records(self, binding, run_id, cwd, execution=None, **options):
        """A fixture run has no native logs: there is nothing to read and its failure cause stays unknown.
        `execution` (C3a) is accepted like the native read but there is no per-execution log to bound."""
        return [], True

    def force_stop(self, r):
        state = self.load(r["run_id"])
        if state["terminal"] is None and not state["stopping"]:
            state["stopping"] = True
            self.store(state)

    @staticmethod
    def checkpoint(worktree):
        """Like a native checkpoint resume: commit the worktree files on top of HEAD and detach HEAD there. The
        files and the working branch stay as they are; only HEAD and the worktree index move."""
        with tempfile.TemporaryDirectory(prefix="zplan-checkpoint-") as scratch:
            index = {"GIT_INDEX_FILE": str(Path(scratch) / "index")}
            export_git(worktree, "read-tree", "HEAD", env=index)
            export_git(worktree, "add", "-A", env=index)
            tree = export_git(worktree, "write-tree", env=index).decode().strip()
        commit = export_git(worktree, "commit-tree", tree, "-p", "HEAD", "-m", "fixture checkpoint",
                            env=IDENTITY).decode().strip()
        export_git(worktree, "update-ref", "--no-deref", "-m", "fixture checkpoint", "HEAD", commit)
        export_git(worktree, "read-tree", commit)

    def resume(self, r, run_id):
        state = self.load(run_id)
        require(state["recoverable"] and state["successorRunId"] is None, "The fixture run is not recoverable.")
        successor = run_id + "-r"
        # Like native, the successor is recorded on the predecessor before it starts.
        state["successorRunId"] = successor
        self.store(state)
        self.checkpoint(Path(r["worktree"]))
        self.begin(r, successor, "done", run_id)
        return {"runId": successor, "resumedFrom": run_id}
