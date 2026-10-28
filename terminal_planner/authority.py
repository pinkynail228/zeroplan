"""One authority for proposals and approval, with no execution scheduler."""

import copy
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import uuid

from . import live, toolchain


class Blocked(RuntimeError):
    """A refusal shown to the owner. `family` is a stable ID of terminal_planner.catalog.ERRORS; None means the
    failure has no catalog entry and is shown as `unknown_error`."""
    family = None

    def __init__(self, *args, family=None):
        super().__init__(*args)
        if family is not None:
            self.family = family


class Rejected(Blocked):
    """A certain, deterministic refusal (non-zero exit), as opposed to a timeout or crash."""


class PersistenceError(OSError):
    """Fixed public cause with the original OS exception chained for diagnosis."""
    family = "store.write_failed"

    def __init__(self, stage):
        super().__init__("Authority persistence failed: " + stage)
        self.stage = stage


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def decode(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def invalid(_):
        raise ValueError("Non-finite JSON number")

    def finite(text):
        value = float(text)
        if not math.isfinite(value):
            invalid(text)
        return value

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid, parse_float=finite)
    except (ValueError, TypeError, RecursionError) as error:
        raise Blocked("Invalid JSON envelope.", family="store.invalid") from error


def require(ok, message="Incompatible planning state/envelope.", family="store.invalid"):
    if not ok:
        raise Blocked(message, family=family)




# Every persisted plan revision status (the catalog documents each one).
OVERRIDE_REASON = (10, 500)  # characters of the owner's typed reason for approving a rejected plan gate
PLAN_STATUSES = ("planning", "submission_unknown", "observing", "observation_blocked", "detached", "run_failed",
                 "proposal_invalid", "review_exhausted", "proposed", "approved", "stopped")

# New intents use only efforts native static admission accepts. Historical
# records keep loading with their frozen values; never map them silently.
NATIVE_EFFORTS = {"low", "medium", "high", "xhigh", "max"}
HISTORICAL_EFFORTS = NATIVE_EFFORTS | {"none", "minimal", "ultra"}


def require_native_efforts(roles):
    for role, binding in roles.items():
        require(binding["effort"] in NATIVE_EFFORTS,
                "%s effort %s is not accepted by native; choose one of: %s." % (role, binding["effort"], ", ".join(sorted(NATIVE_EFFORTS))))


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def atomic_state(path, value):
    stage, name = "temp_write", None
    try:
        fd, name = tempfile.mkstemp(dir=path.parent, prefix=".planning-")
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(canonical(value) + "\n")
            stream.flush()
            stage = "file_fsync"
            os.fsync(stream.fileno())
        stage = "replace"
        os.replace(name, path)
        stage = "directory_fsync"
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError as error:
        raise PersistenceError(stage) from error
    finally:
        if name is not None:
            try:
                os.unlink(name)
            except OSError:
                # Cleanup cannot replace the original write/fsync/replace cause.
                pass



def common_directory(project):
    raw = Path(git(project, "rev-parse", "--git-common-dir").decode().strip())
    return (project / raw).resolve() if not raw.is_absolute() else raw.resolve()


def directory_identity(path):
    """Local object identity, stable across ordinary Git directory updates."""
    try:
        info = path.stat()
        require(path.is_dir(), "Git common directory is unavailable.", family="project.unreadable")
    except OSError as error:
        raise Blocked("Git common directory is unavailable; resuming is refused.", family="project.unreadable") from error
    identity = {"device": info.st_dev, "inode": info.st_ino}
    if hasattr(info, "st_birthtime"):
        identity["birthtime_ns"] = int(info.st_birthtime * 10**9)
    return identity



def production_root():
    # 0.3 state lives in its own namespace; 0.2 stores at the parent root are never read or written.
    base = Path.home() / ("Library/Application Support" if sys.platform == "darwin" else ".local/state")
    return base / "PlanningKit/production/v3"


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def git(project, *args):
    # Observation must not execute repository hooks or refresh the target index.
    result = subprocess.run(["git", "--no-optional-locks", "-c", "diff.autoRefreshIndex=false",
                             "-c", "core.fsmonitor=false", "-C", str(project), *args], capture_output=True,
                            start_new_session=True)
    if result.returncode:
        raise Blocked("Could not read the Git project; an existing commit is required.", family="project.unreadable")
    return result.stdout


def discover(path):
    path = Path(path).expanduser().resolve()
    return Path(git(path, "rev-parse", "--show-toplevel").decode().strip()).resolve()


def normalize_origin_upstream(workspace, branch=None):
    """Pin the submitted branch of `workspace` to `origin` before a native run.

    Zeroshot 10.12 resolves a run's source from the submitted branch's own upstream config (`branch.<b>.remote`
    and `branch.<b>.merge`) and, without one, from the single remote with a valid URL; several valid remotes then
    fail (`AmbiguousRemote`). zplan always submits through `origin`, so it names it explicitly. Idempotent, also
    after a reused worktree. Only this branch's config is written (the worktree's shared `.git/config`); the user's
    checkout, its branch and every other branch's config are never touched. A detached worktree has no branch and
    is left alone unless `branch` is given."""
    if branch is None:
        try:
            branch = git(workspace, "symbolic-ref", "--quiet", "--short", "HEAD").decode().strip()
        except Blocked:
            return None
    require(nonempty(branch), "No working branch for the submission.", family="engine.checkout")
    git(workspace, "config", "branch.%s.remote" % branch, "origin")
    git(workspace, "config", "branch.%s.merge" % branch, "refs/heads/" + branch)
    return branch


def require_workspace_outside_state(workspace, state_root, family):
    """Refuse a submitted workspace that contains or lies inside the native run state.

    Zeroshot 10.12 rejects a workspace overlapping the effective `ZEROSHOT_STATE_DIR` (zplan points it at
    `<native_state_root>/runs`, `NativeEngine.native_environment`); upstream `native_v2_local/workspace.rs`
    (v10.12 workspace.rs:23-34) refuses containment in either direction after resolving paths, and its refusal is generic.
    zplan compares the same pair before submission and gives the remedy itself. Both paths are resolved (existing
    symlinks followed, a missing tail kept), so an existing or a not-yet-created workspace is checked alike;
    `state_root` is the native state root, not the whole tools directory."""
    state = (Path(state_root).expanduser() / "runs").resolve()
    workspace = Path(workspace).expanduser().resolve()
    require(not (workspace == state or state in workspace.parents or workspace in state.parents),
            "Workspace %s overlaps native state %s; Zeroshot 10.12 forbids this. "
            "Set --native-state-dir outside the work trees and do not point "
            "XDG_DATA_HOME inside native state." % (workspace, state), family=family)
    return workspace


BASELINE_PREFIX = "v2:"


def baseline(project):
    """The identity of what the planner, the checks and the runs see: the commit and the branch (the working tree is
    the user's and never part of it). Hash evidence without persisting source, diffs, or secret file contents."""
    return BASELINE_PREFIX + _head_digest(project).hexdigest()


def _head_digest(project):
    h = hashlib.sha256()
    h.update(git(project, "rev-parse", "HEAD"))
    # Detached HEAD is valid; HEAD already supplies its identity.
    h.update(subprocess.run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false",
                             "-C", str(project), "symbolic-ref", "--quiet", "--short", "HEAD"],
                            capture_output=True, start_new_session=True).stdout)
    return h


def baseline_matches(recorded, project):
    """True when the record's baseline is the project's now. A record without the `v2:` prefix (0.7.0) is checked with
    the formula it was made with: HEAD, branch and the working-tree state."""
    if recorded.startswith(BASELINE_PREFIX):
        return recorded == baseline(project)
    return recorded == _legacy_baseline(project)


def _legacy_baseline(project):
    h = _head_digest(project)
    h.update(git(project, "status", "--porcelain=v1", "-z", "--untracked-files=all"))
    h.update(git(project, "diff", "--no-ext-diff", "--no-textconv", "--binary", "HEAD"))
    for raw in git(project, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0"):
        if not raw:
            continue
        path = project / os.fsdecode(raw)
        h.update(raw + b"\0")
        if path.is_symlink():
            h.update(os.fsencode(os.readlink(path)))
        elif path.is_file():
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(65536), b""):
                    h.update(chunk)
        else:
            raise Blocked("Unsupported untracked file in the project.", family="project.unreadable")
    return h.hexdigest()


BRIEF_KEYS = ("goal", "why", "reuse", "write_set", "criteria", "non_goals", "risk", "dod")
BRIEF_RISKS = ("low", "medium", "high")


def brief_problem(brief):
    """Why `brief` (the optional `brief` of a plan task) is invalid, or None. One validator for the proposal, the
    baseline and the manifest."""
    def text(value, empty=False):
        return isinstance(value, str) and (empty or bool(value.strip())) and len(value) <= 8192

    if not isinstance(brief, dict) or set(brief) != set(BRIEF_KEYS):
        return "brief: fields"
    if not (text(brief["goal"]) and text(brief["why"]) and text(brief["dod"]) and text(brief["reuse"], empty=True)):
        return "brief: goal/why/reuse/dod"
    write_set = brief["write_set"]
    if not (isinstance(write_set, list) and 0 < len(write_set) <= 32 and all(text(p) for p in write_set)):
        return "brief: write_set"
    parts = [Path(p).parts for p in write_set]
    if any(Path(p).is_absolute() or ".." in q or not q for p, q in zip(write_set, parts)) or len(set(parts)) != len(parts):
        return "brief: write_set — repository-relative paths without .. and without repeats"
    criteria = brief["criteria"]
    if not (isinstance(criteria, list) and 0 < len(criteria) <= 5):
        return "brief: criteria"
    for item in criteria:
        if not (isinstance(item, dict) and set(item) == {"id", "text", "example"} and all(text(v) for v in item.values())):
            return "brief: criterion"
    if len({item["id"] for item in criteria}) != len(criteria):
        return "brief: criterion ids"
    non_goals = brief["non_goals"]
    if not (isinstance(non_goals, list) and len(non_goals) <= 16 and all(text(g) for g in non_goals)):
        return "brief: non_goals"
    if brief["risk"] not in BRIEF_RISKS:
        return "brief: risk"
    return None


def validate_proposal(plan):
    """Reject missing coverage, cycles, dangling dependencies, and executable claims."""
    def require(ok, reason):
        if not ok:
            raise Blocked("Invalid proposal: " + reason, family="plan.invalid_proposal")

    def text(value):
        return isinstance(value, str) and 0 < len(value.strip()) <= 8192

    def records(value, fields, limit, optional=()):
        require(isinstance(value, list) and 0 < len(value) <= limit, "list size")
        for item in value:
            require(isinstance(item, dict) and set(fields) <= set(item) <= set(fields) | set(optional), "record fields")
        return value

    require(isinstance(plan, dict) and set(plan) == {"requirements", "milestones"}, "roadmap fields")
    requirements = records(plan["requirements"], ["id", "text"], 64)
    ids = set()
    for req in requirements:
        require(text(req["id"]) and text(req["text"]) and req["id"] not in ids, "requirements")
        ids.add(req["id"])
    milestones = records(plan["milestones"], ["id", "title", "depends_on", "slices"], 32)
    mids, entities, coverage = set(), set(ids), {key: 0 for key in ids}
    for milestone in milestones:
        mid = milestone["id"]
        require(text(mid) and mid not in entities and text(milestone["title"]), "milestone ID/title")
        entities.add(mid)
        mids.add(mid)
        deps = milestone["depends_on"]
        require(isinstance(deps, list) and all(text(d) for d in deps) and len(deps) == len(set(deps)), "dependencies")
        for slice_ in records(milestone["slices"], ["id", "title", "requirements", "tasks"], 32):
            sid = slice_["id"]
            require(text(sid) and sid not in entities and text(slice_["title"]), "slice ID/title")
            entities.add(sid)
            owned = slice_["requirements"]
            require(isinstance(owned, list) and owned and all(text(r) and r in ids for r in owned), "coverage references")
            require(len(set(owned)) == len(owned), "duplicate ownership")
            for rid in owned:
                coverage[rid] += 1
            for task in records(slice_["tasks"], ["id", "title", "checks"], 32, optional=["brief"]):
                tid = task["id"]
                require(text(tid) and tid not in entities and text(task["title"]), "task ID/title")
                entities.add(tid)
                checks = task["checks"]
                require(isinstance(checks, list) and 0 < len(checks) <= 32 and all(text(c) for c in checks), "task checks")
                if "brief" in task:
                    problem = brief_problem(task["brief"])
                    require(problem is None, "task %s: %s" % (tid, problem))
    require(all(count == 1 for count in coverage.values()), "each requirement must have exactly one slice owner")
    edges = {m["id"]: m["depends_on"] for m in milestones}
    visited, visiting = set(), set()

    def visit(mid):
        require(mid in mids and mid not in visiting, "cycle or unknown dependency")
        if mid in visited:
            return
        visiting.add(mid)
        for dep in edges[mid]:
            visit(dep)
        visiting.remove(mid)
        visited.add(mid)

    for mid in mids:
        visit(mid)
    return plan


# The milestone driver runs at most this many initial tasks (all slices of one milestone together).
MAX_MILESTONE_TASKS = 12


def check_bounds(plan):
    """A new proposal must be runnable: every milestone within the driver task bound. Stored revisions are only
    checked by validate_proposal, so a record from before this bound stays readable (but is never approved)."""
    for milestone in plan["milestones"]:
        count = sum(len(slice_["tasks"]) for slice_ in milestone["slices"])
        if count > MAX_MILESTONE_TASKS:
            raise Blocked("Invalid proposal: milestone %s holds %s tasks, the driver runs at most %s; "
                          "split the milestone." % (milestone["id"], count, MAX_MILESTONE_TASKS), family="plan.invalid_proposal")
    return plan


PLANNING_ROLES = ("planner", "plan_verifier")

# Plan revisions: execution version 1 (no `execution` key: planner + `plan_verifier`, output schema "1") is frozen
# forever; a new revision runs `planner graph 2` (planner + `critic`, bounded discussion, output schema "2").
PLAN_EXECUTION = 2
PLAN_ROUNDS_MAX = 5
TASK_ROUNDS_MAX = 10  # limits.task_rounds: the same upper bound the profile resolver enforces
DEFAULT_PLAN_ROUNDS = 3
RULES_LIMIT = 64 * 1024  # UTF-8 bytes of all frozen rules together
DISCUSSION_TEXT = 4000  # characters of one finding / response
DISCUSSION_BYTES = 32 * 1024
SHA256 = "0123456789abcdef"
DISCUSSION_SUBJECT = "plan checks"  # the gate a discussion/override belongs to; a gate names its own
STALE_TEMPLATE = ("Cannot approve: the check is out of date — the process settings or rules changed after the "
                  "%s. [r] revise rebuilds the plan and checks it again.")
STALE_APPROVAL = ("The project changed after planning: cannot approve. "
                  "Next: [r] revise — rebuilds the plan and checks it again.")


def gate_stale(subject="plan checks"):
    """The shared refusal of an action whose gate no longer matches the live artifact, configuration or HEAD;
    every gate names its own subject (the plan gate: "plan checks")."""
    return STALE_TEMPLATE % subject


class Authority:
    """Exclusive interactive session; immutable revision history in one atomic document."""

    def __init__(self, root, project, fixture_id=None):
        self.project = discover(project)
        self.common_dir = common_directory(self.project)
        self.common_identity = directory_identity(self.common_dir)
        self.project_id = hashlib.sha256(str(self.common_dir).encode()).hexdigest()
        self.fixture_id = fixture_id
        if fixture_id is not None:
            require(nonempty(fixture_id) and all(c.isalnum() or c in "_-" for c in fixture_id), "An explicit fixture ID is required.", family="usage.invalid_option")
            base = Path(root).expanduser().resolve() if root else production_root().parent.parent
            self.directory = base / "v3" / "fixtures" / fixture_id / self.project_id
        else:
            require(root is None, "Production --state-dir is forbidden; the canonical Git authority is used.", family="usage.invalid_option")
            self.directory = production_root() / self.project_id
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / "planning.json"
        self.lock = None
        self.project_lock = None
        # Keyed by canonical Git common-directory identity, outside the checkout.
        # A state-root override must not create a second concurrent project owner.
        namespace = "fixture-" + fixture_id if fixture_id else "production"
        self.lock_dir = production_root() / ".locks" / self.project_id / namespace
        self.lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.state = None
        self._store_bytes = None
        # Set by feed.bootstrap on a session whose store does not exist yet: the save that first creates the store
        # starts from an empty feed (A6b1).
        self.feed_pending = False
        # The session's process.Profile (None: no profile; new revisions freeze a default configuration).
        self.profile = None

    def __enter__(self):
        self.state = None
        self._store_bytes = None
        self.feed_pending = False
        self.project_lock = (self.lock_dir / "session.lock").open("a")
        self.lock = (self.directory / "session.lock").open("a")
        try:
            fcntl.flock(self.project_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if self.path.exists():
                self.load_projection(self.path.read_bytes())
        except BaseException as error:
            self.__exit__()
            if isinstance(error, BlockingIOError):
                raise Blocked("Another terminal already manages this project's plan.", family="store.locked") from error
            raise
        return self

    def load_projection(self, raw):
        self._store_bytes = raw
        try:
            self.state = decode(raw.decode("utf-8"))
        except UnicodeError as error:
            raise Blocked("Invalid authority UTF-8.", family="store.invalid") from error
        self.validate_state()

    def __exit__(self, *_):
        if self.lock:
            self.lock.close()
            self.lock = None
        if self.project_lock:
            self.project_lock.close()
            self.project_lock = None

    def check_project(self):
        require(common_directory(self.project) == self.common_dir, "Git common directory changed; resuming is refused.")
        require(directory_identity(self.common_dir) == self.common_identity,
                "Git directory object was replaced; resuming is refused.")

    def empty_state(self):
        return {"schema": 2, "project_id": self.project_id, "common_dir": str(self.common_dir),
                "common_identity": self.common_identity,
                "namespace": "fixture:" + self.fixture_id if self.fixture_id else "production",
                "revisions": [], "legacy_history": None}

    def validate_state(self):
        self.check_project()
        state = self.state
        require(isinstance(state, dict))
        schema = state.get("schema")
        require(type(schema) is int and schema == 2,
                "Unknown planning.json schema (%s): this zplan reads only the planning-only schema 2 in store v3; the file is unchanged."
                % (schema if type(schema) is int else "?"))
        expected = self.empty_state()
        # Milestone runs, task gates, merge critics and the architect's feed extend schema 2 with the optional
        # `runs`, `gates`, `critics` and `feed` keys; stores without them still load, and a store without any of them
        # stays byte-identical.
        require(set(state) - {"runs", "gates", "critics", "feed"} == set(expected))
        require(all(state[k] == expected[k] for k in ("project_id", "common_dir", "common_identity", "namespace")),
                "State belongs to another authority/Git directory object; resuming is refused.")
        require(isinstance(state["revisions"], list) and state["legacy_history"] is None)
        for index, revision in enumerate(state["revisions"], 1):
            self.validate_revision(revision, index)
        if "runs" in state:
            from .runs import validate_runs
            validate_runs(self, state["runs"])
        if "gates" in state:
            from .task_gate import validate_gates
            validate_gates(state)
        if "critics" in state:
            from .merge_critic import validate_critics
            validate_critics(state)
        if "feed" in state:
            from . import feed
            feed.validate_feed(state["feed"])

    @staticmethod
    def validate_roles(roles):
        # Planning needs only its own roles; worker/reviewer/steward bindings join the revision record in later steps.
        require(isinstance(roles, dict) and set(roles) == set(PLANNING_ROLES))
        for binding in roles.values():
            require(isinstance(binding, dict) and set(binding) == {"model", "effort"})
            require(nonempty(binding["model"]) and isinstance(binding["effort"], str) and binding["effort"] in HISTORICAL_EFFORTS)

    @staticmethod
    def validate_frozen(r):
        frozen = r["frozen"]
        require(type(r["execution"]) is int and r["execution"] == PLAN_EXECUTION, "Unknown execution version of the plan.")
        # A revision of planner graph 2 always freezes plan_rounds, the rules and the configuration digest; a
        # revision built after the review bar (C0a) also freezes task_rounds, the milestone review loop's repair
        # bound `runs.review_rounds` reads. Older revisions and the unprofiled default simply do not carry it.
        require(isinstance(frozen, dict)
                and {"plan_rounds", "rules", "config_digest"} <= set(frozen)
                <= {"plan_rounds", "task_rounds", "rules", "config_digest"})
        require(type(frozen["plan_rounds"]) is int and 1 <= frozen["plan_rounds"] <= PLAN_ROUNDS_MAX)
        require("task_rounds" not in frozen
                or (type(frozen["task_rounds"]) is int and 1 <= frozen["task_rounds"] <= TASK_ROUNDS_MAX))
        require(isinstance(frozen["config_digest"], str) and len(frozen["config_digest"]) == 64
                and set(frozen["config_digest"]) <= set(SHA256))
        rules = frozen["rules"]
        require(isinstance(rules, list) and len(rules) <= 8)
        total = 0
        for rule in rules:
            require(isinstance(rule, dict) and set(rule) == {"path", "sha256", "text"} and nonempty(rule["path"])
                    and isinstance(rule["text"], str) and isinstance(rule["sha256"], str)
                    and len(rule["sha256"]) == 64 and set(rule["sha256"]) <= set(SHA256))
            total += len(rule["text"].encode("utf-8"))
        require(total <= RULES_LIMIT, "The frozen rules exceed the limit.")

    @staticmethod
    def execution(r):
        """The execution version of a plan revision: 1 for every record that predates planner graph 2."""
        return r.get("execution", 1)

    @staticmethod
    def snapshot(r):
        """The single frozen configuration a revision's runtime, input and evidence are built from. Version 1 has no
        rounds or rules of its own (its graph is fixed)."""
        if "execution" not in r:
            return {"execution": 1, "roles": copy.deepcopy(r["roles"])}
        frozen = copy.deepcopy(r["frozen"])
        return {"execution": r["execution"], "roles": copy.deepcopy(r["roles"]), **frozen}

    @staticmethod
    def check_frozen_rules(r):
        """Before dispatch: each frozen rule's text still has the hash it was frozen with (the snapshot itself, never
        the live files)."""
        for rule in r.get("frozen", {}).get("rules", ()):
            if hashlib.sha256(rule["text"].encode("utf-8")).hexdigest() != rule["sha256"]:
                raise Blocked("The frozen rules %s do not match their hash; starting is refused. Begin a new "
                              "plan revision." % rule["path"], family="engine.intent_changed")

    def validate_revision(self, r, version):
        fields = {"version", "goal", "roles", "engine", "feedback", "baseline", "worktree", "status", "proposal", "approval",
                  "submission_key", "run_id", "receipt", "intent", "native_binding", "native_documents", "native_prepared",
                  "observation_cursor", "observation_envelope", "terminal_cursor", "terminal_envelope", "evidence", "diagnostic"}
        # `live` is optional observation metadata written only by the planning watch; older stores have none.
        # `execution` + `frozen` exist together on revisions of planner graph 2; a revision without them is v1 forever.
        # `override` is the owner's record of approving a rejected plan gate anyway; absent on every other revision.
        # `draft` is the full proposal of an owner edit that the plan run must present unchanged; absent otherwise.
        require(isinstance(r, dict) and set(r) - {"live", "execution", "frozen", "override", "stop", "draft"} == fields
                and ("live" not in r or live.valid(r["live"])) and (("execution" in r) == ("frozen" in r)))
        if "draft" in r:
            require("execution" in r, "Editing a plan requires a second-version plan check.")
            validate_proposal(r["draft"])
        if "execution" in r:
            self.validate_frozen(r)
        require(type(r["version"]) is int and r["version"] == version)
        require(nonempty(r["goal"]) and len(r["goal"]) <= 8192 and nonempty(r["baseline"]) and nonempty(r["worktree"]))
        require(Path(r["worktree"]).resolve() == Path(r["worktree"]))
        require(common_directory(Path(r["worktree"])) == self.common_dir, "Revision worktree/common-dir changed.")
        self.validate_roles(r["roles"])
        require(isinstance(r["engine"], str) and r["engine"] == ("fixture" if self.fixture_id else "native"), "Fixture and production evidence are incompatible.")
        require(isinstance(r["status"], str) and r["status"] in PLAN_STATUSES and isinstance(r["feedback"], str) and isinstance(r["diagnostic"], str))
        require(nonempty(r["submission_key"]) and type(r["native_prepared"]) is bool)
        for key in ("observation_cursor", "terminal_cursor", "run_id", "approval"):
            require(r[key] is None or nonempty(r[key]))
        # `stop` is the owner's persisted stop request of a run under observation: its timestamp and nothing else.
        stop = r.get("stop")
        require(stop is None or (isinstance(stop, dict) and set(stop) == {"at"} and isinstance(stop["at"], str)
                                 and bool(live.TIME.fullmatch(stop["at"])) and r["run_id"] is not None),
                "Invalid planner stop request.")
        if r["receipt"] is not None:
            validate_receipt(r["receipt"])
            require(r["receipt"]["runId"] == r["run_id"])
            require(r["native_prepared"], "The receipt requires a previously saved prepared intent.")
        else:
            require(r["run_id"] is None)
        if r["status"] in {"observing", "observation_blocked", "detached", "run_failed", "proposal_invalid", "review_exhausted", "proposed", "approved", "stopped"}:
            require(r["receipt"] is not None)
        if r["status"] == "submission_unknown":
            require(r["receipt"] is None and r["native_prepared"])
        if r["native_prepared"]:
            require(isinstance(r["native_documents"], dict) and set(r["native_documents"]) == {"graph", "runtime", "input"})
            require(all(nonempty(v) for v in r["native_documents"].values()))
            require(isinstance(r["native_binding"], dict) and isinstance(r["intent"], dict))
            binding = r["native_binding"]
            if r["engine"] == "fixture":
                require(binding == {"fixture_id": self.fixture_id})
            else:
                # By shape only: a record of an older toolchain stays readable and is never rewritten.
                require(toolchain.valid_binding(binding))
            require(r["intent"] == self.intent_identity(r), "Frozen goal/configuration/source changed.")
        else:
            require(r["intent"] is None and r["native_documents"] is None and r["native_binding"] is None)
        if r["proposal"] is not None:
            validate_proposal(r["proposal"])
        if r["observation_envelope"] is not None:
            status = validate_projection(r["observation_envelope"], r["run_id"])
            require(status["phase"] != "finished" and r["observation_cursor"] == r["observation_envelope"]["cursor"])
            self.check_terminal_origin(r, r["observation_envelope"])
        if r["terminal_envelope"] is not None:
            validate_projection(r["terminal_envelope"], r["run_id"])
            self.check_terminal_origin(r)
            require(r["terminal_envelope"]["status"]["phase"] == "finished")
            require(r["terminal_cursor"] == r["terminal_envelope"]["cursor"])
        else:
            # An incomplete observation checkpoint is recoverable only by full retained history;
            # it confers no terminal evidence or approval.
            require(r["terminal_cursor"] is None or (r["evidence"] is None and r["status"] in {"observing", "observation_blocked", "detached"}))
        if r["evidence"] is not None:
            require(r["status"] in {"proposed", "approved", "review_exhausted"})
            self.check_evidence(r)
        override = r.get("override")
        if r["status"] in {"proposed", "approved", "review_exhausted"}:
            require(r["evidence"] is not None)
            verdict = r["evidence"]["verdict"]
            if r["status"] == "approved":
                # Only an owner override approves a rejected verdict.
                require(verdict == "accepted" or (verdict == "rejected" and override is not None))
            else:
                require(verdict == ("rejected" if r["status"] == "review_exhausted" else "accepted"))
        if override is not None:
            self.validate_override(r, override)
        if r["status"] == "run_failed":
            require(r["terminal_envelope"] is not None and r["terminal_envelope"]["status"]["terminalResult"]["status"] == "failed")
        if r["status"] == "stopped":
            # A stop request is honoured on whatever terminal ends the run: the force-stopped failure and a run that
            # finished successfully before the request reached the engine both keep their terminal evidence.
            require(r.get("stop") is not None and r["terminal_envelope"] is not None,
                    "Stopped plan without a stop request.")
        if r["status"] == "proposal_invalid":
            require(r["terminal_envelope"] is not None and r["terminal_envelope"]["status"]["terminalResult"]["status"] == "succeeded" and r["evidence"] is None)
        if r["status"] in {"planning", "submission_unknown", "observing", "observation_blocked", "detached"}:
            require(r["terminal_envelope"] is None and r["proposal"] is None)
        if r["status"] == "approved":
            require(r["approval"] == self.approval_identity(r))
        else:
            require(r["approval"] is None)

    @staticmethod
    def validate_override(r, override):
        """The owner record is valid only on an approved plan of execution 2 whose gate was rejected, and binds the
        verdict and the digest of exactly the evidence it overrode."""
        require(r["status"] == "approved" and "execution" in r and r["evidence"] is not None
                and r["evidence"]["verdict"] == "rejected" and r["evidence"].get("critic_verdict") == "rejected")
        override_matches(r["evidence"], override)

    @staticmethod
    def intent_identity(r):
        identity = {k: copy.deepcopy(r[k]) for k in ("version", "goal", "roles", "engine", "feedback", "baseline", "worktree", "submission_key", "native_documents", "native_binding")}
        if "execution" in r:  # version 1 records keep their identity byte for byte
            identity.update(execution=r["execution"], frozen_digest=digest(r["frozen"]))
        if "draft" in r:  # a revision without an edit keeps its identity byte for byte
            identity["draft"] = copy.deepcopy(r["draft"])
        return identity

    def review_evidence(self, r, cursor, output):
        """(proposal, evidence) of a finished review of this revision, from its frozen snapshot: the output must be
        of the revision's own execution version; a version 2 gate also carries the gate fields."""
        v2 = "execution" in r
        limit = r["frozen"]["plan_rounds"] if v2 else PLAN_ROUNDS_MAX
        require(isinstance(output, dict) and output.get("schemaVersion") == ("2" if v2 else "1"),
                "Output does not match the plan's execution version.")
        proposal, verdict, findings, _, discussion = read_review(output, limit)
        # An edit is judged, never rewritten: whatever the verdict, the proposal is the owner's draft.
        require("draft" not in r or canonical(proposal) == canonical(r["draft"]), "the planner changed the edit")
        evidence = {"kind": r["engine"], "run_id": r["run_id"], "terminal_cursor": cursor,
                    "output_digest": digest(output), "proposal_digest": digest(proposal),
                    "intent_digest": digest(r["intent"]), "verdict": verdict, "findings": findings}
        if v2:
            evidence.update(gate="plan", artifact_digest=digest(proposal),
                            resolved_config_digest=r["frozen"]["config_digest"], head=r["baseline"],
                            rounds_used=len(discussion["rounds"]), rounds_limit=limit, discussion=discussion,
                            critic_verdict=verdict)
        return proposal, evidence

    def check_evidence(self, r):
        require(r["native_prepared"] and r["intent"] == self.intent_identity(r))
        envelope = r["terminal_envelope"]
        require(isinstance(envelope, dict))
        validate_projection(envelope, r["run_id"])
        self.check_terminal_origin(r)
        require(envelope["status"]["phase"] == "finished" and envelope["cursor"] == r["terminal_cursor"])
        terminal = envelope["status"]["terminalResult"]
        require(terminal["status"] == "succeeded")
        proposal, expected = self.review_evidence(r, r["terminal_cursor"], terminal["output"])
        require(r["evidence"] == expected and r["proposal"] == proposal, "Review evidence/proposal identity mismatch.")
        return expected

    def check_terminal_origin(self, r, envelope=None):
        if r["engine"] != "native":
            return
        # The source commit is frozen in the hashed submission input, not derived
        # from the mutable target HEAD or an editable saved watch projection.
        path = self.directory / ("revision-%s" % r["version"]) / "input.json"
        require(path.is_file(), "Frozen native input is lost.")
        document = decode(path.read_text())
        require(digest(document) == r["native_documents"]["input"], "Frozen native input changed.")
        require(isinstance(document, dict) and isinstance(document.get("task"), str))
        task = decode(document["task"])
        require(isinstance(task, dict) and nonempty(task.get("source_revision")), "Frozen source identity is missing.")
        envelope = r["terminal_envelope"] if envelope is None else envelope
        require(envelope["source"]["revision"] == task["source_revision"], "Terminal source mismatch.")
        require(envelope["title"] == "Terminal roadmap revision %s" % r["version"] and envelope["size"] == "medium",
                "Terminal intent projection mismatch.")

    @staticmethod
    def approval_identity(r):
        identity = {"intent": r["intent"], "evidence": r["evidence"], "proposal": r["proposal"]}
        if r.get("override") is not None:  # records without an override keep their approval digest byte for byte
            identity["override"] = r["override"]
        return digest(identity)

    def assert_store_fresh(self):
        require(self.lock is not None, "State mutation requires session lock.", family="action.refused")
        raw = self.path.read_bytes() if self.path.exists() else None
        require(raw == self._store_bytes, "Authority physical bytes changed; reload under lock.")

    def save(self):
        require(self.lock is not None, "A state mutation requires the session lock.")
        self.assert_store_fresh()
        self.check_project()
        from . import feed
        # A session bootstrapped while its store did not exist yet starts from an empty feed here; then every save
        # captures the run records' state transitions before writing (A6b1) so an event is never written without its
        # cause and no transition between two saves is folded.
        if self.feed_pending and self.state is not None:
            self.feed_pending = False
            self.state.setdefault("feed", feed.empty())
        self.validate_state()
        snapshot = feed.capture(self)
        encoded = (canonical(self.state) + "\n").encode("utf-8")
        try:
            atomic_state(self.path, self.state)
        except PersistenceError as error:
            # Replace succeeded but its directory durability is uncertain: track the visible bytes.
            if error.stage == "directory_fsync":
                try:
                    if self.path.read_bytes() == encoded:
                        self._store_bytes = encoded
                except OSError:
                    pass
            else:
                # The write failed before the replace: undo this save's state capture so a caller that then removes
                # its record leaves no event behind.
                feed.restore(self, snapshot)
            raise
        self._store_bytes = encoded

    def live_profile_digest(self):
        """The configuration digest the session's bound profile resolves to now, or None when no profile is bound
        (an explicitly unprofiled session: no comparison). A postponed profile is bound too: its sidecar snapshot
        answers, and an unusable one resolves to "" so it never equals a gate's digest. A pure read."""
        return self.profile.live_digest() if self.profile is not None else None

    def begin(self, goal, roles, engine, feedback="", execution=PLAN_EXECUTION, draft=None):
        """The one freeze point of a plan revision: its roles, rounds, rules and configuration digest are taken here,
        once, from the session's profile (else `roles` and the defaults), and everything the revision later runs on
        is built from that snapshot. `execution=1` makes a legacy revision (tests of the v1 graph only). `draft` is
        the full proposal of an owner edit: the plan run must return it unchanged (execution 2 only)."""
        self.check_project()
        # The lifecycle precondition of this mutation, before anything is read from the profile or written: one
        # active milestone writer blocks a new revision (the same "active" notion `Runs.active` uses).
        from .runs import active_run  # runs imports this module at load: shared predicate, no copy of the status set
        busy = active_run(self.state.get("runs", [])) if self.state else None
        require(busy is None, "Milestone %s is still running; a new plan revision is possible after it finishes or stops."
                % (busy and busy["milestone"]), family="action.refused")
        require(nonempty(goal) and len(goal) <= 8192)
        require(execution in (1, PLAN_EXECUTION))
        if draft is not None:
            require(execution == PLAN_EXECUTION, "Editing a plan requires a second-version plan check.", family="action.refused")
            check_bounds(validate_proposal(draft))
        frozen = None
        if execution == PLAN_EXECUTION and self.profile is not None:
            roles, frozen = self.profile.freeze_plan()
        require(isinstance(roles, dict) and all(role in roles for role in PLANNING_ROLES))
        roles = {role: copy.deepcopy(roles[role]) for role in PLANNING_ROLES}
        self.validate_roles(roles)
        require_native_efforts(roles)
        if execution == PLAN_EXECUTION and frozen is None:
            frozen = {"plan_rounds": DEFAULT_PLAN_ROUNDS, "rules": [],
                      "config_digest": digest({"unprofiled": True, "roles": roles})}
        require(engine == ("fixture" if self.fixture_id else "native"), "A fixture authority cannot submit native runs.")
        if self.state is None:
            self.state = self.empty_state()
        # A revision still "planning" without a receipt never reached submission (status turns submission_unknown
        # before dispatch), so a new revision may supersede it; the old one stays in history unchanged.
        if self.state["revisions"] and (self.current["status"] in {"submission_unknown", "observing", "observation_blocked", "detached"}
                                        or self.current["status"] == "planning" and self.current["run_id"] is not None):
            raise Blocked("The planner of this plan is already submitted; open [p] plan to watch it.", family="action.refused")
        revision = {
            "version": len(self.state["revisions"]) + 1,
            "goal": goal, "roles": roles, "engine": engine,
            "feedback": feedback, "baseline": baseline(self.project),
            "status": "planning", "proposal": None, "approval": None,
            "submission_key": "zplan-" + str(uuid.uuid4()), "run_id": None,
            "worktree": str(self.project), "receipt": None, "intent": None,
            "native_binding": None, "native_documents": None, "native_prepared": False,
            "observation_cursor": None, "observation_envelope": None, "terminal_cursor": None, "terminal_envelope": None,
            "evidence": None, "diagnostic": "",
        }
        if frozen is not None:
            revision.update(execution=execution, frozen=frozen)
        if draft is not None:
            revision["draft"] = copy.deepcopy(draft)
        self.state["revisions"].append(revision)
        self.save()
        return revision

    def amended_feedback(self, request):
        """The feedback of a revision that amends the current one. Requests made since the latest proposal all
        reach the planner, each once: while the current revision has no proposal (unsent, renewed, failed) its
        feedback already holds them; a proposal absorbs them and the new request stands alone."""
        current = self.current
        if current["proposal"] is None and current["feedback"]:
            return current["feedback"] + "\n\n" + request
        return request

    @property
    def current(self):
        if not self.state or not self.state["revisions"]:
            raise Blocked("No saved plan. Choose Plan.", family="action.refused")
        return self.state["revisions"][-1]

    def commit_terminal(self, envelope):
        r = self.current
        validate_projection(envelope, r["run_id"])
        require(envelope["status"]["phase"] == "finished")
        r.update(terminal_cursor=envelope["cursor"], terminal_envelope=copy.deepcopy(envelope))
        terminal = envelope["status"]["terminalResult"]
        if r.get("stop") is not None:
            # A run the owner asked to stop ends as `stopped`, not as a failure and not as a proposal: a completion
            # racing the request is a stop. Only the status changes; the terminal evidence stays retained.
            r.update(status="stopped", diagnostic=terminal.get("reason") or "")
        elif terminal["status"] == "failed":
            r.update(status="run_failed", diagnostic=terminal["reason"])
        else:
            try:
                proposal, evidence = self.review_evidence(r, envelope["cursor"], terminal["output"])
                check_bounds(proposal)
                require(r["intent"] == self.intent_identity(r) and self.fresh(), "Frozen source/configuration are out of date.")
                r.update(proposal=proposal, status="proposed" if evidence["verdict"] == "accepted" else "review_exhausted")
                r["evidence"] = evidence
            except Blocked as error:
                r.update(status="proposal_invalid", diagnostic=str(error), proposal=None, evidence=None)
        self.save()

    def approve(self, version):
        """A plan gate of execution 2 is valid only while the session's bound profile resolves to the gate's
        configuration digest. That digest is read here, from the bound provider (`live_profile_digest`), never from
        the caller: no caller can disable or replace the comparison. A refusal writes nothing."""
        current = self.current
        self.validate_state()
        if current["status"] != "proposed" or version != current["version"]:
            raise Blocked("Only the current proposed revision can be approved.", family="action.refused")
        if not baseline_matches(current["baseline"], self.project):
            raise Blocked(STALE_APPROVAL, family="plan.stale")
        self.check_evidence(current)
        require(current["evidence"]["verdict"] == "accepted")
        if "execution" in current:
            gate = current["evidence"]
            require(gate["gate"] == "plan" and gate["critic_verdict"] == "accepted", "No accepted plan check.",
                    family="action.refused")
            live = self.live_profile_digest()
            if live is not None and live != gate["resolved_config_digest"]:
                raise Blocked(gate_stale(), family="plan.gate_stale")
        check_bounds(current["proposal"])
        if current["engine"] == "native":
            # Also checks exact executable identity and frozen documents on disk.
            from .engine import recorded_engine
            recorded_engine(current["native_binding"]).prepare(self)
        current["approval"] = self.approval_identity(current)
        current["status"] = "approved"
        self.save()

    def override(self, version, reason):
        """The owner approves a plan whose gate ended rejected (execution 2, `review_exhausted`) with a typed
        reason. The critic's verdict and evidence stay as they were; the record binds both and the approval binds
        the record. The live configuration digest is `approve`'s, from the bound provider; a refusal writes
        nothing."""
        reason = override_reason(reason)
        current = self.current
        self.validate_state()
        if current["status"] != "review_exhausted" or version != current["version"]:
            raise Blocked("Only the current plan that the check did not accept can be approved despite the check.",
                          family="action.refused")
        require("execution" in current, "A first-version plan has no check to approve it despite.",
                family="action.refused")
        if not baseline_matches(current["baseline"], self.project):
            raise Blocked(STALE_APPROVAL, family="plan.stale")
        self.check_evidence(current)
        gate = current["evidence"]
        require(gate["gate"] == "plan" and gate["verdict"] == "rejected" and gate["critic_verdict"] == "rejected",
                "No rejected plan check.", family="action.refused")
        live = self.live_profile_digest()
        if live is not None and live != gate["resolved_config_digest"]:
            raise Blocked(gate_stale(), family="plan.gate_stale")
        check_bounds(current["proposal"])
        if current["engine"] == "native":
            from .engine import recorded_engine
            recorded_engine(current["native_binding"]).prepare(self)
        current["override"] = {"reason": reason, "verdict": gate["verdict"], "evidence_digest": digest(gate)}
        current["approval"] = self.approval_identity(current)
        current["status"] = "approved"
        self.save()

    def fresh(self):
        self.check_project()
        require(self.current["worktree"] == str(self.project), "The plan requires a frozen target worktree.")
        return baseline_matches(self.current["baseline"], self.project)


def override_reason(text):
    """The reason of an owner override: stripped, one line, 10..500 characters; nothing else is accepted."""
    reason = text.strip() if isinstance(text, str) else ""
    low, high = OVERRIDE_REASON
    require(low <= len(reason) <= high and reason.isprintable(),
            "A reason is required: one line, %d to %d characters." % (low, high), family="action.refused")
    return reason


def override_matches(evidence, override, verdict_field="verdict", subject="plan checks"):
    """The owner override record of one gate's evidence: {reason, verdict, evidence_digest} with a typed reason,
    the evidence's own verdict and the digest of exactly that evidence. Shared by every gate; only the verdict
    field and the subject of the refusal text differ."""
    require(isinstance(override, dict) and set(override) == {"reason", "verdict", "evidence_digest"})
    reason = override["reason"]
    require(isinstance(reason, str) and reason == reason.strip()
            and OVERRIDE_REASON[0] <= len(reason) <= OVERRIDE_REASON[1] and reason.isprintable(),
            "The override reason is invalid.")
    require(override["verdict"] == evidence[verdict_field] and override["evidence_digest"] == digest(evidence),
            "The override does not match the %s." % subject)


def validate_receipt(value):
    require(isinstance(value, dict) and set(value) == {"runId"} and nonempty(value["runId"]), "No unambiguous native receipt; submission_unknown.")


def validate_source_remote(remote):
    """The optional `source.remote` of a 10.12 envelope, by the upstream schema only
    (`ResolvedGitRemote`: `url` required; optional `connection` and `forge`). zplan never uses the values: a
    remote URL cannot contradict the project's origin (the planner submits from a disposable clone, whose origin
    is the project's)."""
    require(isinstance(remote, dict) and "url" in remote and set(remote) <= {"url", "connection", "forge"},
            "Unsupported source.remote.")
    require(nonempty(remote["url"]))
    require(remote.get("connection") is None or nonempty(remote["connection"]))
    forge = remote.get("forge")
    require(forge is None or (isinstance(forge, dict) and set(forge) == {"provider", "repository"}
                              and all(nonempty(forge[key]) for key in ("provider", "repository"))),
            "Unsupported source.remote.forge.")


# The optional 10.16 `context` of a failed terminal result (upstream `FailureContext`): both the planning envelope
# (`validate_projection`) and a stored run terminal (`runs.validate_terminal`) accept it through the same validator.
FAILURE_CONTEXT_FIELDS = frozenset({"incomplete", "primary", "recorded"})
FAILURE_DIAGNOSTIC_FIELDS = frozenset({"message", "cursor", "execution"})
FAILURE_MESSAGE_CHARS = 16384  # characters of one diagnostic `message`
FAILURE_RECORDED_MAX = 5  # diagnostics of one `recorded` list
_CONTROL_CHAR = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def valid_active_execution(value):
    """One `{execution, node}` pair of the native wire, both nonempty strings: the `activeExecutions` item of a
    running/stopping status and a failure diagnostic's `execution` share this exact shape."""
    return isinstance(value, dict) and set(value) == {"node", "execution"} and all(nonempty(v) for v in value.values())


def valid_failure_diagnostic(value):
    """A 10.16 `FailureDiagnostic`: a required `message` (a string of at most 16384 characters without control
    characters), an optional `cursor` string or null and an optional `execution` pair or null; no other keys."""
    if not isinstance(value, dict) or "message" not in value or not set(value) <= FAILURE_DIAGNOSTIC_FIELDS:
        return False
    message = value["message"]
    if not isinstance(message, str) or len(message) > FAILURE_MESSAGE_CHARS or _CONTROL_CHAR.search(message):
        return False
    if "cursor" in value and value["cursor"] is not None and not isinstance(value["cursor"], str):
        return False
    return value.get("execution") is None or valid_active_execution(value["execution"])


def valid_failure_context(value):
    """The 10.16 `FailureContext` of a failed terminal result: all keys optional -- `incomplete` a bool, `primary`
    one diagnostic or null, `recorded` at most five diagnostics; no other keys at any level. Absent and null are
    valid too (10.12 and older carried no `context`), so records of the older toolchain load unchanged."""
    if value is None:
        return True
    if not isinstance(value, dict) or not set(value) <= FAILURE_CONTEXT_FIELDS:
        return False
    if "incomplete" in value and type(value["incomplete"]) is not bool:
        return False
    if value.get("primary") is not None and not valid_failure_diagnostic(value["primary"]):
        return False
    if "recorded" in value:
        recorded = value["recorded"]
        if (not isinstance(recorded, list) or len(recorded) > FAILURE_RECORDED_MAX
                or not all(valid_failure_diagnostic(item) for item in recorded)):
            return False
    return True


def require_terminal_result(value, message="Incompatible planning state/envelope."):
    """The one validator of a native terminal result, shared by the planning envelope's finished phase and a stored
    run terminal: `{status, output}` for a success; `{status, reason}` plus the optional 10.16 `context` (absent,
    null or the `FailureContext` shape) for a failure. Anything else is refused with `message`."""
    require(isinstance(value, dict), message)
    if value.get("status") == "succeeded":
        require(set(value) == {"status", "output"}, message)
        return
    require(set(value) <= {"status", "reason", "context"} and value.get("status") == "failed"
            and nonempty(value.get("reason")) and valid_failure_context(value.get("context")), message)


def validate_projection(value, run_id, watch=True, source_optional=False):
    cursor = "cursor" if watch else "atCursor"
    fields = {"runId", "title", "source", "size", cursor, "status"} | ({"subscriptionId"} if watch else set())
    # A run submitted from a checkout with no attached branch (the merge critic detaches at the unreferenced
    # candidate) resolves no source upstream (`native_v2_local/source.rs`), so its envelope omits `source` or carries
    # it as null. `source_optional` is that one contract; every other caller keeps the source required and validated.
    required = fields - {"source"} if source_optional else fields
    allowed = fields | (set() if watch else {"workspaceRecovery"})
    require(isinstance(value, dict) and required <= set(value) and set(value) <= allowed, "Unsupported observation envelope.")
    require(value["runId"] == run_id and nonempty(run_id) and nonempty(value[cursor]) and nonempty(value["title"]))
    require(isinstance(value["size"], str) and value["size"] in {"small", "medium", "large"})
    if watch:
        require(nonempty(value["subscriptionId"]))
    elif "workspaceRecovery" in value:
        recovery = value["workspaceRecovery"]
        require(isinstance(recovery, dict) and {"recoverable"} <= set(recovery) <= {
            "recoverable", "connectionRequirements", "resumedFrom", "successorRunId"})
        require(type(recovery["recoverable"]) is bool)
        for key in ("resumedFrom", "successorRunId"):
            require(recovery.get(key) is None or isinstance(recovery[key], str))
        connections = recovery.get("connectionRequirements", {})
        require(isinstance(connections, dict))
        import re
        for key, names in connections.items():
            require(isinstance(key, str) and 1 <= len(key.encode()) <= 128 and
                    re.search(r"[\x00-\x1f\x7f-\x9f]", key) is None)
            require(isinstance(names, list) and all(isinstance(name, str) and len(name) <= 128 and
                    re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is not None for name in names))
    source = value.get("source")
    if source is not None:
        identity = {"repository", "branch", "revision"}
        # `remote` is the 10.12 addition and stays optional; a 10.11 envelope (no `remote`) is unchanged.
        require(isinstance(source, dict) and identity <= set(source) <= identity | {"remote"},
                "Unsupported observation envelope.")
        require(all(nonempty(source[k]) for k in identity))
        if source.get("remote") is not None:
            validate_source_remote(source["remote"])
        import re
        require(re.fullmatch(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+", source["repository"]) is not None)
        require(re.fullmatch(r"[0-9a-f]{40}", source["revision"]) is not None)
    else:
        require(source_optional, "Unsupported observation envelope.")
    status = value["status"]
    require(isinstance(status, dict) and isinstance(status.get("phase"), str))
    phase = status["phase"]
    if phase == "admitted":
        require(set(status) == {"phase"})
    elif phase in {"running", "stopping"}:
        require(set(status) == {"phase", "activeExecutions"} and isinstance(status["activeExecutions"], list))
        for active in status["activeExecutions"]:
            require(valid_active_execution(active))
    elif phase == "finished":
        require({"phase", "terminalResult"} <= set(status) <= {"phase", "terminalResult", "metadata"})
        if "metadata" in status:
            metadata = status["metadata"]
            require(isinstance(metadata, dict) and set(metadata) <= {"tokenUsage"})
            if metadata.get("tokenUsage") is not None:
                usage = metadata["tokenUsage"]
                required = {"inputTokens", "outputTokens", "complete"}
                optional = {"cacheReadInputTokens", "cacheCreationInputTokens"}
                require(isinstance(usage, dict) and required <= set(usage) <= required | optional)
                require(type(usage["complete"]) is bool)
                require(all(type(v) is int and 0 <= v <= 2**53 - 1 for k, v in usage.items() if k != "complete" and v is not None))
                require(all(type(usage[k]) is int for k in ("inputTokens", "outputTokens")))
        terminal = status["terminalResult"]
        require_terminal_result(terminal)
    else:
        raise Blocked("Unknown native phase.", family="engine.bad_output")
    return status


def bad_discussion(reason, subject=DISCUSSION_SUBJECT):
    return Blocked("Invalid discussion of the %s: %s" % (subject, reason), family="engine.bad_output")


def read_discussion(text, rounds_limit, final, subject=DISCUSSION_SUBJECT):
    """The critic-reported discussion of one gate output, validated against its own final result (`final` is the
    (verdict, findings, response) triple the last round must equal). This shows the reported rounds are well-formed
    and end at the signalled verdict; it does not prove earlier rounds unchanged (the critic wrote them). The
    parsing is shared by every gate; only the subject of the refusal text differs."""
    if len(text.encode("utf-8")) > DISCUSSION_BYTES:
        raise bad_discussion("larger than %d KB" % (DISCUSSION_BYTES // 1024), subject)
    try:
        value = decode(text)
    except Blocked as error:
        raise bad_discussion("not JSON", subject) from error
    if not isinstance(value, dict) or set(value) != {"version", "rounds"} or type(value["version"]) is not int \
            or value["version"] != 1:
        raise bad_discussion("unknown version or fields", subject)
    rounds = value["rounds"]
    if not isinstance(rounds, list) or not 1 <= len(rounds) <= rounds_limit:
        raise bad_discussion("rounds must number 1 to %d" % rounds_limit, subject)
    for index, item in enumerate(rounds, 1):
        if not isinstance(item, dict) or set(item) != {"round", "verdict", "findings", "response"}:
            raise bad_discussion("fields of round %d" % index, subject)
        if type(item["round"]) is not int or item["round"] != index:
            raise bad_discussion("round numbers are not consecutive (round %d)" % index, subject)
        if item["verdict"] not in ("accepted", "rejected") or (index < len(rounds) and item["verdict"] != "rejected"):
            raise bad_discussion("verdict of round %d" % index, subject)
        for key in ("findings", "response"):
            if not isinstance(item[key], str) or len(item[key]) > DISCUSSION_TEXT:
                raise bad_discussion("%s of round %d: text longer than %d characters" % (key, index, DISCUSSION_TEXT), subject)
    last = rounds[-1]
    if (last["verdict"], last["findings"], last["response"]) != tuple(final):
        raise bad_discussion("the last round does not match the final verdict, findings and reply", subject)
    return value


def read_review(output, rounds_limit=PLAN_ROUNDS_MAX):
    """(proposal, verdict, findings, response, discussion) of a completed review, output schema "1" (planVerdict,
    planFindings) or "2" (also planResponse and the bounded discussion). Version 1 has no response/discussion."""
    require(isinstance(output, dict) and output.get("schemaVersion") in ("1", "2"), "Unsupported review schema/verdict.")
    version = output["schemaVersion"]
    fields = {"schemaVersion", "proposal", "planVerdict", "planFindings"} | ({"planResponse", "discussion"} if version == "2" else set())
    require(set(output) == fields and all(isinstance(v, str) for v in output.values()), "Malformed completed review output.")
    require(output["planVerdict"] in {"accepted", "rejected"}, "Unsupported review schema/verdict.")
    proposal = validate_proposal(decode(output["proposal"]))
    if version == "1":
        return proposal, output["planVerdict"], output["planFindings"], None, None
    final = (output["planVerdict"], output["planFindings"], output["planResponse"])
    return proposal, output["planVerdict"], output["planFindings"], output["planResponse"], \
        read_discussion(output["discussion"], rounds_limit, final)


def completed_review(output, rounds_limit=PLAN_ROUNDS_MAX):
    """(proposal, verdict, findings) of an output of schema "1" or "2"."""
    return read_review(output, rounds_limit)[:3]
