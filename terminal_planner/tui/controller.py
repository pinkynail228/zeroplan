"""The controller worker behind the TUI: one thread owns the Authority session and everything that touches it.

The UI never calls Authority, MilestoneRuns, Git, setup or login directly. It posts a named action; the worker
runs actions and refresh slices one at a time and hands back immutable snapshots. A refresh slice is the same
read-only overview as the plain home screen (workspace + overview/status): it never polls, submits or dispatches.
This module does not import Textual."""

import collections
import contextlib
from dataclasses import dataclass, replace
import json
from pathlib import Path
import queue
import secrets
import threading
import time
from typing import Optional, Tuple
import uuid

from .. import autonomy, bridge, catalog, engine, feed, live, planning as planning_module, process, setup, user_commit
from ..architect import NO_PLAN, ArchitectStore
from ..application import ApplicationService, request_snapshot
from ..authority import Authority, Blocked, FormatRefused, atomic_state, chain_approved, chain_budget
from ..cli import App, fixture_driver, refusal, safe, summary
from ..delivery import ACTIVE, ApprovedPlan, CRITIC_SLICE, Changed, END_ACTIONS, Row, Token
from ..planning import PlanView
from ..process import Profile, ProfileChanged
from ..runs import MilestoneRuns, extended, git_call, run_state
from . import chat as chat_module

REFRESH, CHECK, SETUP, OBSERVE, OBSERVE_RUN = "refresh", "check", "setup", "observe", "observe_run"
ROWS = "bridge_rows"  # the architect status tool's rows snapshot: read-only, posted and waited for by each status
MESSAGE_LINE = 200  # characters of the owner's message an owner-bound request keeps (its first line, scrubbed)
STATUS_WAIT = 2.0  # seconds the architect's status waits for its rows job before it answers the last rows, stale
FEED_PENDING, FEED_HANDLE = "feed_pending", "feed_handle"  # A6b2b: the chat's feed port jobs (a read, an ack)
OBSERVATIONS = frozenset((OBSERVE, OBSERVE_RUN))  # a watch slice: quitting may skip one once it has closed
# RS5: the jobs that change state without writing a plan or run event the architect could act on: the feed ack and
# the silent bootstrap. Every other job outside CUTTABLE (an approval, a start, an edit, ...) may have saved one.
NO_WAKE = frozenset((FEED_HANDLE, "feed_bootstrap"))
TUI_SLICE = 5  # seconds per planner or milestone watch slice: input and quit stay responsive between slices
MERGE_PACE = 0.05  # seconds one pacing job of a waiting merge sleeps before it requeues itself behind the queued jobs
STOP_WAIT = TUI_SLICE + 3  # quitting waits at most this long for the slice in flight; a watching child is cut at once
# Jobs that change nothing, or only observe: quitting may cut these. Every other job (prepare, submission, start,
# merge, setup, ...) changes state or starts model work and is always allowed to finish. Two pieces of work inside
# a normally cuttable job are not: the first planner slice of an accepted submission (`observe(..., dispatch=True)`)
# prepares the checkout, sends the revision and saves the receipt, and a call that renders an end view exports an
# accepted attempt (`_end`). Both register as mutating -- the dispatching slice when it is posted (`post(mutating=
# True)`, so a quit that finds it queued waits for it), an export when it starts (`_mutation`, so a quit that finds
# it running waits for it and one that has already closed refuses it). Neither is ever cut, and both keep their
# count until the result reached the UI: quitting shows a submission or an export before the app may exit.
CUTTABLE = frozenset((REFRESH, CHECK, OBSERVE, OBSERVE_RUN, "open_run", "diff", "details", "record", "changes",
                     "tail", "open_answer_draft", "request_snapshot", ROWS, FEED_PENDING))
# The action tools' argument keys, exactly their schemas (`architect_tools.TOOLS`, additionalProperties=false):
# a request carrying anything else is an invalid argument, refused before freshness and the policy, never ignored.
TOOL_ARGUMENTS = {"zplan_start": frozenset(("milestone", "revision")),
                  "zplan_stop": frozenset(("milestone", "run_id")),
                  "zplan_approve_plan": frozenset(("revision",)),
                  "zplan_resume": frozenset(("milestone", "token")),
                  "zplan_rebrief": frozenset(("milestone", "token", "note")),
                  "zplan_plan": frozenset(("goal", "plan", "request")),
                  "zplan_edit_plan": frozenset(("revision", "plan", "response", "request")),
                  "zplan_merge": frozenset(("milestone", "token")),
                  "zplan_propose_commit": frozenset(("paths", "message")),
                  "zplan_settings": frozenset(("level", "max_runs", "merge", "roles"))}

# The action tools whose admission is one `_plan_job` (`Planning.edit` is the plan service's own rule; `zplan_plan`
# is the owner's own start-planning work, only on the owner's word): they are
# posted through the Controller's plan-job path from the socket thread itself, exactly as the owner's own submit and
# revise are, never as the generic bridge job and never as a job nested inside another.
ARCHITECT_ATTEMPTS = 2  # the new attempts an event turn may start per milestone and plan revision; then the owner decides
RESULTS = 20  # the results a status keeps (the last ones), and the subjects results.json keeps
RESULTS_FILE = "results.json"  # beside the store, never in planning.json (V2c)
RESULT_LINES = 4  # the lines one result carries
AT_WORD = {"start": "Started", "resume": "Continued", "rebrief": "Started a new attempt", "approve": "Approved",
           "merge": "Merged", "plan": "Planned", "settings": "Changed settings"}  # what an owner turn's call says it did, "<verb> at your word: «message»"
PLAN_TOOLS = {"zplan_plan": "plan", "zplan_edit_plan": "edit"}
# The plan format refusals one owner turn allows (one owner line, at the cap); then both plan tools refuse, quietly.
# A runaway bound only: caps of 3 and 6 cut converging plans off (A0 rig: 9 of 16 and 8 of 15 plan turns missed);
# with no cap every plan turn saved a plan (0 of 8, about 7 refusals per turn).
FORMAT_REFUSALS = 25
LATE_WAKE = ("zplan_merge", "zplan_start", "zplan_rebrief")  # R3d: a job of these that ends after its wait wakes the architect


class Release:
    """The release of one mutating job (its count falls exactly once). The worker releases it right after a
    delivery that is not a UI hand-over; a hand-over takes it (Controller.take_release) and releases it when the
    UI handler returned, raised, or its delivery was dropped."""

    def __init__(self, controller):
        self.controller = controller
        self._once = threading.Lock()
        self._spent = False

    def release(self):
        """Lower Controller.mutating() for this job, from either thread. False when it was already released."""
        with self._once:
            if self._spent:
                return False
            self._spent = True
        self.controller.released()
        return True

    def __call__(self):
        return self.release()


class Releases:
    """Everything one job's delivery owes: the job's own count and the counts of the mutations admitted inside it
    (an export). One callable for a hand-over, which runs it when its handler returned, raised or was dropped, so
    every count falls exactly once."""

    def __init__(self, releases):
        self._releases = tuple(releases)

    def __call__(self):
        for release in self._releases:
            release.release()


@dataclass(frozen=True)
class Check:
    """One readiness item (setup.readiness()), as the Settings screen shows it. `severity` is "ok", "warn" or
    "block" (setup.severity); a warning keeps ok=True and shows as a yellow `! ` row, never a block (R-4)."""
    id: str
    ok: bool
    line: str
    detail: str
    doctor: str
    key: Optional[str]
    severity: str = "ok"


@dataclass(frozen=True)
class Snapshot:
    """Everything the main screen shows, frozen: the project header and the plan panel."""
    project: str
    branch: Optional[str]
    clean: bool
    version: Optional[int]  # current plan revision, None without a plan
    status: Optional[str]
    lines: Tuple[str, ...]  # the plain overview body, line for line
    roles: Tuple[Tuple[str, str, str], ...]
    error: str = ""
    plan: Optional[PlanView] = None  # the plan screen of the current revision (planning service)
    rows: Tuple[Row, ...] = ()  # the milestones of an approved plan (delivery service), in plan order
    focus: Optional[str] = None  # the milestone the service names under "Next"
    g: Optional[str] = None  # the catalog action [g] has on home (the delivery service's decision), None: nothing
    g_milestone: Optional[str] = None  # the milestone [g] acts on
    busy: Optional[str] = None  # the first active milestone when every parallel slot is taken, else None
    slots: int = 1  # the live profile's parallel bound (C1): the panel's own refusal names it
    panel: Tuple[str, ...] = ()  # live lines (roles, elapsed, last event, heartbeat) of the observed run
    journal: Tuple[str, ...] = ()  # stored journal entries of the observed attempt, oldest first (nothing rendered yet)
    flow: Optional[dict] = None  # structured facts of the active attempt for the Now drawing (F2); None without one
    graph: Optional[dict] = None  # the frozen Zeroshot root of that attempt, not a UI-rebuilt template
    profile: Optional[process.View] = None  # the process profile as the screens show it (None: not enforced)
    plan_state: Optional[object] = None  # the plan identity state of `version` (plain data; None: no plan)
    uncommitted: Tuple[str, ...] = ()  # the paths the last commit does not hold (the planner and the runs see HEAD)
    approved: Optional[ApprovedPlan] = None  # the last approved plan and its progress (None: never approved)
    scripted: bool = False  # the architect is the fixture script: it never approves, the owner does
    goldfish: bool = False  # the plan is a Goldfish one: no planner runs, the owner's texts say "plan check"
    chain_approved: bool = False  # a later revision of a chain the owner approved: the architect may approve it

    @property
    def stale(self):
        """An unsent revision the project has moved away from: [n] prepares a new one."""
        return self.plan is not None and self.plan.kind == "stale"

    @property
    def first_row(self):
        """Index in `lines` of the first milestone row: goal line, plan summary line, then one line per row."""
        return 2

    def row(self, milestone_id):
        return next((r for r in self.rows if r.id == milestone_id), None)

    @property
    def observing(self):
        """A planner run with a receipt: observation (re)starts on its own."""
        return self.plan is not None and self.plan.kind == "observing"


@dataclass(frozen=True)
class Outcome:
    """What a planning action did, for the screen to show: `kind` is the service verdict (blocked / ready /
    stale / sent / done / failed / continue), `checks` the readiness items behind a block, `lines` any text."""
    kind: str
    checks: Tuple[Check, ...] = ()
    lines: Tuple[str, ...] = ()
    data: object = None  # a service result the screen renders (EndView, Preview, Token)


class Capture:
    """A terminal that only remembers what the plain UI would print."""

    def __init__(self, role_preferences=None):
        self.lines = []
        if role_preferences is not None:
            self.role_preferences = role_preferences

    def show(self, value=""):
        self.lines.extend(safe(value).split("\n"))


def approved_line(version, despite=False):
    """The result line of an approval: what happened, nothing about what comes next (the snapshot shows that)."""
    return "Plan r%s approved%s." % (version, " despite the check" if despite else "")


def checks_of(items):
    return tuple(Check(i["id"], bool(i["ok"]), i["line"], i["detail"], i["doctor"], i["key"],
                       i.get("severity") or ("ok" if i["ok"] else "block")) for i in items)


def plan_state(plan):
    """The plan identity state of one revision as plain data: the status word the controller snapshot names, and
    whether the owner approved the plan over a rejected gate.

    A chat draft keeps this with its reply; the revision number alone is not enough, because the state of one
    revision changes without a new revision (submitted, plan ready, approved) and an owner override keeps the
    `approved` status while being a state of its own. None without a plan."""
    if not isinstance(plan, dict):
        return None
    return {"status": str(plan.get("status") or ""), "override": bool(plan.get("override"))}


def goal_identity(planning):
    """The plan identity of the session right now, as a goal draft carries it: "no plan", or [revision, state].

    Read on the controller worker from the session's own plan — the same source `take_snapshot` projects — and read
    when the job runs, so the provenance re-check compares a draft against the state at that moment, not against
    the state when the owner pressed the key. None when the plan is there but names no identity."""
    plan = planning.plan()
    if not plan:
        return NO_PLAN
    state = plan_state(plan)
    if state is None or plan.get("version") is None:
        return None
    return [plan["version"], state]


# The plain fields of a delivery `Token`, in the shape `app.token_fields` flattens one into an answer draft's
# identity: the field name and the type its value must have (None: the value may be a string or None).
TOKEN_FIELDS = (("milestone", str), ("plan_revision", int), ("attempt", int), ("run_id", None),
                ("status", str), ("outcome", None), ("delivery", str))


def token_identity(identity):
    """The delivery `Token` an answer draft's stored identity carries, or None when there is not one to rebuild.

    The architect adapter has no lifecycle imports, so an answer draft travels as plain data: the app flattens a
    `Token` into `app.token_fields` once, at send time. It is rebuilt here, on the worker, and only from exactly
    those fields: a draft whose identity is not a mapping, misses one of them, carries an unknown one, or holds a
    value of the wrong type has no token, and a draft without a token is refused before anything else runs. `bool`
    is not an int here (`isinstance(True, int)` would pass a token built from `true`), and a string field must be
    the string itself, not a number the display could have spelled."""
    if not isinstance(identity, dict) or set(identity) != {name for name, _ in TOKEN_FIELDS}:
        return None
    for name, kind in TOKEN_FIELDS:
        value = identity[name]
        if kind is None:
            if value is not None and not isinstance(value, str):
                return None
        elif type(value) is not kind:
            return None
    return Token(**identity)


def token_fields(token):
    """The `Token` of one attempt as the plain object the status payload carries and the action tools take back:
    exactly `TOKEN_FIELDS`, so the token a status row shows is the one `token_identity` rebuilds for an action.
    None without an attempt."""
    return None if token is None else {name: getattr(token, name) for name, _ in TOKEN_FIELDS}


PLAN_FINDINGS = 4000  # the characters of the evidence's findings a status plan carries


def plan_fields(plan, revisions=None):
    """The current plan revision as the status payload names it: its version, status, gate verdict and the
    evidence's findings (at most `PLAN_FINDINGS`, "" without evidence), or None without a revision. The verdict is the evidence's own `verdict` (accepted / rejected), the same word the plan
    screen prints; None while the plan has no verdict yet. A Goldfish plan also carries `revisions_left`: the
    plan revisions the architect may still make, counted from `revisions` (the plan revision chain), None when
    there is no budget."""
    if not isinstance(plan, dict):
        return None
    evidence = plan.get("evidence")
    findings = evidence.get("findings") if isinstance(evidence, dict) else None
    findings = findings if isinstance(findings, str) else ""
    fields = {"version": plan.get("version"), "status": plan.get("status") or "",
              "verdict": evidence.get("verdict") if isinstance(evidence, dict) else None,
              "findings": findings if len(findings) <= PLAN_FINDINGS else findings[:PLAN_FINDINGS - 1] + "…",
              "proposal": plan.get("proposal")}
    if is_goldfish(plan):  # the evidence's paraphrase, and the architect's plan before a review has produced a proposal
        fields["paraphrase"] = evidence.get("paraphrase") if isinstance(evidence, dict) else None
        fields["draft"] = plan.get("draft") if plan.get("proposal") is None else None
        budget = chain_budget(revisions)
        fields["revisions_left"] = None if budget is None else max(budget[1] - budget[0], 0)
    return fields


def is_goldfish(revision):
    """Whether a plan revision is a Goldfish (planner-free) one."""
    return revision.get("frozen", {}).get("review") == "goldfish"


REASON_STATES = ("blocked", "failed", "failed_recoverable", "needs_owner", "conflict", "stopped", "paused")
REASON_LINES = 12   # the lines of a stopped attempt's reason a status row carries
REASON_WIDTH = 300  # the characters of each of them


def cut_lines(lines, last=False):
    """`lines` (strings, split on newlines) as the status carries text: at most `REASON_LINES` lines (the first
    ones, the last ones for `last`) of at most `REASON_WIDTH` characters, every line scrubbed like the architect's
    other reads."""
    def cut(line):
        line = live.scrub(line.rstrip())
        return line if len(line) <= REASON_WIDTH else line[:REASON_WIDTH - 1] + "…"
    lines = [part for text in lines for part in str(text).split("\n")]
    return "\n".join(cut(line) for line in (lines[-REASON_LINES:] if last else lines[:REASON_LINES]))


def reason_fields(view):
    """Why an attempt stopped, as the status row carries it: the owner's end view (heading, status, family) with its
    body cut by `cut_lines`."""
    return {"heading": live.scrub(view.heading), "status": live.scrub(view.status),
            "body": cut_lines(view.body), "family": view.family}


def reason_of(app, row):
    """`reason_fields` of the row's latest attempt, built by `Delivery.view` (it exports nothing, unlike `end`);
    None when the row has no attempt."""
    r = app.delivery.latest(row.id)
    return None if r is None else reason_fields(app.delivery.view(r))


MERGE_FILES = 20  # the changed files a status row names before it only counts the rest


def changed_paths(app, r):
    """The files the attempt's result changes against its destination base (as the end screen lists them), all of
    them; [] for an attempt not exported yet, None when Git cannot list them."""
    result, destination = extended(r)["result"] or {}, r["destination"]
    commit = result.get("commit")
    if commit is None:
        return []
    listing = git_call(app.authority.project, "diff", "--name-only", "--no-renames", "-z", destination["base"], commit)
    if listing.returncode:
        return None
    return [name for name in listing.stdout.decode(errors="replace").split("\0") if name]


def merge_tier(status, paths):
    """The risk tier the merge policy decides on: `process.risk_of` over the candidate's `paths` under the profile
    read `status`. A profile without a `risk` section, no profile and paths that cannot be listed (None) are "high"
    (fail closed)."""
    resolved = getattr(status, "resolved", None)
    if resolved is None or paths is None or "risk" not in resolved.config:
        return "high"
    return process.risk_of(resolved.config, paths)["tier"]


def merge_fields(app, row, status):
    """What the architect needs to decide a merge from `zplan_status` alone: the result commit, its branch, the
    destination branch, the files the result changes against the destination (at most `MERGE_FILES`, then
    `more`), the live profile's merge gate and check names, the autonomy policy's own `decision` for a merge
    under them (`status` is the one profile read of the rows job, as `_merge_tool` reads it), the attempt's `tasks`
    count and the stored `gate_result` of this result. `files` is None when Git cannot list them; an attempt not
    exported yet has no commit and no files."""
    r = app.delivery.latest(row.id)
    result, destination = extended(r)["result"] or {}, r["destination"]
    names = changed_paths(app, r)
    files, more = (None, 0) if names is None else (names[:MERGE_FILES], max(0, len(names) - MERGE_FILES))
    resolved = getattr(status, "resolved", None)
    gate = autonomy.merge_gate(status)
    return {"commit": result.get("commit"), "branch": result.get("branch"), "destination": destination["branch"],
            "files": files, "more": more, "gate": gate,
            "checks": [c["name"] for c in resolved.config["checks"]] if resolved is not None else [],
            "decision": autonomy.decide(autonomy.level_of(status), "merge", gate, merge_tier(status, names)),
            "tasks": tasks_count(app, r), "gate_result": gate_result(app, r, result.get("commit"))}


def tasks_count(app, r):
    """`{"done", "total"}` of the attempt's manifest as `Delivery.tasks_lines` counts it (dropped tasks excluded);
    None when the manifest is unavailable."""
    manifest = app.delivery.runs.manifest(r)
    if not manifest:
        return None
    tasks = [t for t in manifest["tasks"] if t["status"] != "dropped"]
    return {"done": sum(t["status"] == "done" for t in tasks), "total": len(tasks)}


def gate_result(app, r, commit):
    """The stored merge gate of the attempt's current result `commit`, as the architect reads it after a refused
    merge: the outcome, each check's name, status and tail (its last lines), and the critic's verdict and findings.
    Only stored records are read; None when no gate was built or it was built for another result."""
    gate = r.get("gate")
    if not isinstance(gate, dict) or commit is None or gate.get("result") != commit:
        return None
    evidence = gate["evidence"]
    critic = next((c for c in app.authority.state.get("critics", []) if c["id"] == gate.get("critic")), None)
    return {"outcome": evidence["outcome"],
            "checks": [{"name": c["name"], "status": c["status"], "tail": cut_lines([c["tail"]], last=True)}
                       for c in evidence["checks"]],
            "critic": None if critic is None else
            {"verdict": critic["verdict"],
             "findings": None if critic["findings"] is None else cut_lines([critic["findings"]])}}


def profile_fields(status):
    """The effective profile as `zplan_status` shows it, from the one `autonomy.status_of` read: its state, short
    digest, autonomy level and parallel runs. None without a status (no profile, or one that cannot be read)."""
    if status is None:
        return None
    resolved = status.resolved
    config = resolved.config if resolved is not None else {}
    return {"state": status.state, "digest": resolved.short if resolved is not None else None,
            "level": autonomy.level_of(status),
            "parallel_runs": process.parallel_runs(config.get("autonomy", {}).get("max_runs"))}


def readiness_fields(app):
    """The start gate's blocking readiness items for `zplan_status`: `{"id", "line", "fix"}` (`fix` is the item's
    `detail`), scrubbed; `[]` when nothing blocks or there is no readiness check."""
    return [{"id": i["id"], "line": live.scrub(i["line"]), "fix": live.scrub(i["detail"])}
            for i in app.planning.items("start") if setup.severity(i) == "block"]


def draft_token(identity, milestone):
    """The `Token` of an answer draft's stored identity, or None when the draft has none to rebuild or one that
    names another milestone than the draft's.

    `chat.newest_answer_draft` chooses a draft by its own `milestone`, so the draft's identity has to name that
    same milestone: a well-formed token of another milestone is one the draft's own milestone never selected, and
    it is refused like any other malformed identity — before `resolve`, so nothing is looked up, viewed, answered
    or written for it."""
    token = token_identity(identity)
    if token is None or token.milestone != milestone:
        return None
    return token


# The three refusals of an answer draft that is not stale; each is its own catalog family, so the pane's code
# (`[code: draft.…]`) is the one the reference explains and the owner can act on.
ANSWER_DRAFT_MALFORMED = "The answer draft has no valid attempt identity: it cannot be opened."
ANSWER_DRAFT_ACTIVE = "%s: the attempt is still running; an answer draft answers only a finished one."
ANSWER_DRAFT_UNAVAILABLE = "%s: this outcome offers no answer; an answer draft does not apply."


def draft_stale(error):
    """The refusal of a draft whose identity moved on: «the draft is outdated» and the service's own reason.

    One wording for both draft kinds (`chat.OUTDATED`); the reason is the delivery service's, taken from the
    `Changed` it raised, so the goal and the answer refusal name a stale state the same way."""
    return "%s: %s" % (chat_module.OUTDATED, error.what)


def job_label(label):
    """The class of a job whose label carries a per-milestone suffix (the watch slice of one attempt): every key
    that reads a label -- coalescing, cutting -- reads the class, while the label itself stays unique, so two
    running attempts never coalesce each other's slice away."""
    return label.split(":", 1)[0]


def frozen_graph(app):
    """The active attempt's exact frozen Zeroshot root, or None when no readable active graph exists."""
    record = app.delivery.active_run()
    if record is None:
        return None
    try:
        document = json.loads(app.delivery.runs.frozen(record)["graph"].read_text(encoding="utf-8"))
        return document.get("root") if isinstance(document, dict) and isinstance(document.get("root"), dict) else None
    except (Blocked, OSError, ValueError, KeyError, TypeError):
        return None


def take_snapshot(app, name):
    """Plain `home` of the session, frozen. Read-only: the overview only detects integration (ancestry)."""
    branch, clean = app.controller.workspace()
    home = app.delivery.home()  # the same lines the plain home prints
    approved = app.delivery.approved()
    plan = app.plan()
    roles = tuple((role, b["model"], b["effort"]) for role, b in app.roles.items() if b)
    try:
        view = app.planning.view() if plan else None
    except (Blocked, OSError, ValueError):
        view = None  # the overview lines above still describe the plan
    return Snapshot(name, branch, clean, plan["version"] if plan else None, plan["status"] if plan else None,
                    tuple(safe(line) for line in home.lines), roles, plan=view, rows=home.rows,
                    focus=home.focus.id if home.focus else None, g=home.g, g_milestone=home.g_milestone,
                    busy=home.busy, slots=home.slots, panel=tuple(safe(line) for line in home.panel),
                    journal=tuple(safe(line) for line in home.journal), flow=home.flow, graph=frozen_graph(app),
                    profile=process.view(app.profile) if app.profile is not None else None,
                    plan_state=plan_state(plan), uncommitted=tuple(app.controller.uncommitted()), approved=approved,
                    goldfish=bool(plan and is_goldfish(plan)),
                    chain_approved=chain_approved(getattr(getattr(app, "authority", None), "state", None) and
                                                  app.authority.state.get("revisions") or []))


@dataclass(frozen=True)
class CommitProposal:
    """The architect's proposal to commit the owner's own files, as the card shows it. It commits nothing: only the
    owner's «yes» does (`Controller.commit_files`). `requested` are the proposed paths as the architect named them (the
    live selection is made again at «yes»), `selection` what they came to when proposed, `state` is `awaiting`,
    `committed`, `declined` or `failed`, and `lines` the receipt the card and the architect's status show."""
    id: str
    requested: Tuple[str, ...]
    message: str
    selection: object
    stat: str
    state: str = "awaiting"
    lines: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ConsentRequest:
    """An architect action the autonomy level leaves to the owner, kept until the owner answers it: `action` is
    `start`, `resume` or `rebrief`, `args` the tool's own arguments, `digest` the profile digest the policy read
    (None: no profile), `preview` the start's `Preview` as it was built. It runs nothing: only the owner's answer
    does (`Controller.consent`, `Controller.decline`). `state` is `awaiting`, `done`, `declined`, `stale` (the
    profile, plan or attempt moved: nothing ran) or `failed`, and `lines` what the card and the architect's status
    show (while awaiting, a settings change's "key: old -> new" lines)."""
    id: str
    action: str
    milestone: str
    args: dict
    digest: Optional[str]
    preview: object = None
    state: str = "awaiting"
    lines: Tuple[str, ...] = ()


class Controller:
    """Serialized access to one planning session. Callbacks run on the worker thread; the UI marshals them."""

    def __init__(self, open_session, name, readiness=None, install=None, login=None, driver_factory=None,
                 can_plan=True, project=None):
        """`open_session(stack)` enters the Authority context on the worker and returns the headless cli.App;
        `readiness()` returns setup.readiness() items (None: nothing to check), `install(show)` is setup,
        `login()` the Codex login (run by the UI under suspend); None means the action is unavailable here.
        `can_plan` is False when no planner engine is wired (nothing may be submitted)."""
        self.open_session, self.name, self.can_plan = open_session, name, can_plan
        self.project = project  # the project directory (None: unknown), for the architect chat of this window
        self.scripted = False  # the architect is the fixture script (`for_project(scripted=True)`)
        self.readiness, self.install, self.login = readiness, install, login
        self.driver_factory = driver_factory
        self.error = ""
        self.family = catalog.UNKNOWN  # catalog family of `error`
        self.running = None  # label of the action in progress (worker writes, UI reads)
        self._queue = queue.Queue()
        self._pending = set()
        self._guard = threading.Lock()
        self._thread = None
        self._watch = None  # (revision, Watch): the planner observation of this session, worker-owned
        self._marks = {}  # run id -> observation cursor of a milestone attempt, worker-owned
        self.closing = False  # the UI is going: results of jobs finishing now are not delivered
        self.sealed = False  # a quit began: no new mutation is admitted (set before the quit's first await)
        self._mutating = 0  # queued or running jobs outside CUTTABLE (guarded)
        self._released = []  # worker thread: what the job being delivered right now owes (its own count, an export)
        self._bridge = None  # the live endpoint for the architect's action tools (None: not serving)
        self._registry = bridge.Registry()  # the architect's action requests, by id, kept after a timeout
        self._format_refusals = {}  # owner turn (_turn_key) -> the plan format refusals it has had
        self._revised_in = set()  # (occurrence, text) of each owner message that created a Goldfish revision
        self._turns = {}  # token -> the owner's message reference, for each owner turn running now (`_turn_guard`)
        self._turn_guard = threading.Lock()
        self._results = collections.deque(maxlen=RESULTS)  # V2a: one receipt per approval call, written by its job
        self._result_seq = 0
        self._result_guard = threading.Lock()
        self._kept = []  # V2c: the last result of each subject, oldest first, at most RESULTS (the file's content)
        self._results_path = None  # V2c: results.json beside the store, set when the session opens
        self._rows = None  # (approved revision, rows, current plan, readiness, profile) of the last status snapshot; None: none yet
        # Optional presentation of an application-driven initial dispatch. No callback is needed to
        # save the revision or receipt; a TUI may continue observing after this notification.
        self.on_plan_submission = None
        # D4c: the architect's proposal to commit the owner's files (None: none yet). The worker sets it, the app
        # shows its card (`on_commit_proposal`, worker-callable) and runs «yes» on the UI thread (`commit_files`).
        # `_project_op` is the lock merges and that commit share: a commit never runs beside a landing merge.
        self.commit_proposal = None
        self.on_commit_proposal = None
        self._project_op = threading.Lock()
        # P6: an action the level leaves to the owner. A start, resume or rebrief becomes one stored request (None:
        # none yet) the owner answers (`consent`, `decline`); an approve or a merge stays the owner's own card or
        # command, and `asked` records that the architect asked for it ("approve": the plan version, "merge": the
        # milestone). The worker sets both; the app shows them through the worker-callable hooks.
        self.consent_request = None
        self.asked = {}
        self.on_consent_request = None
        self.on_asked = None
        # A6b2b: the architect chat's wake-up. The app sets `on_observed` to `chat.notify` (called on the worker after
        # each completed observation job; it only marks a request and hands over, never waits) and `snapshot_source`
        # to `chat_snapshot` (what the feed port's `snapshot()` returns, called off the UI thread like the chat's own
        # sends). `_feed` is the requested port: its presence makes the worker bootstrap the feed once the session opens.
        self.on_observed = None
        self.snapshot_source = None
        self.on_result = None  # the screen's hook: the architect's merge or start result, once (V2b, V2d)
        self.on_merge_wait = None  # the screen's hook: the milestone whose merge waits for the critic, None at its end
        self.on_start_wait = None  # the screen's hook: (milestone, "begin"/"done"/"failed") of a start the architect's tool makes
        self._feed = None
        self._opened = False  # the session open (and the feed bootstrap, when requested) is over; guarded
        # Lazy: a fixture shell with chat disabled must not open an architect store at startup.
        self.application = None

    @classmethod
    def for_project(cls, project, state_root, fixture_id=None, driver_factory=None, worktrees=None, readiness=None,
                    install=None, login=None, role_preferences=None, engine_factory=None, profile=False,
                    scripted=False):
        """The production wiring: the same Authority/MilestoneRuns/App objects as the plain session, opened
        (and locked) on the worker thread. `engine_factory(name, terminal)` is the plain session's planner."""
        def no_engine(*_):
            raise Blocked("The planner is unavailable in this session.", family="action.refused")

        factory = driver_factory or (fixture_driver if fixture_id is not None else (lambda _: None))

        def open_session(stack):
            authority = stack.enter_context(Authority(state_root, project, fixture_id=fixture_id))
            nonlocal worktrees
            trees = worktrees if worktrees is not None else (authority.directory / "worktrees"
                                                              if fixture_id is not None else None)
            return App(Capture(role_preferences), authority, engine_factory or no_engine, factory(authority), trees,
                       readiness=readiness, driver_factory=factory,
                       profile=Profile.of(authority) if profile else None)
        controller = cls(open_session, project.name, readiness, install, login, factory,
                         can_plan=engine_factory is not None, project=Path(project).expanduser().resolve())
        controller.scripted = scripted  # a `--fixture ID` session: the plan card asks the owner, never the script
        return controller

    # Worker --------------------------------------------------------------------

    def start(self):
        if self._thread is None:
            engine.open_watching()  # this session watches again: a previous close (another app in this process) is over
            self._thread = threading.Thread(target=self._run, name="zplan-controller", daemon=True)
            self._thread.start()
        if self._bridge is None and self.project is not None:
            # The architect's action tools reach this session only through this endpoint; publish its path so the
            # chat (same process) can build the architect's argv with `--controller`.
            self._bridge = bridge.Endpoint(self._bridge_request)
            bridge.publish(self.project, self._bridge.start())

    def mutating(self):
        """True while a job that changes state (or starts model work) is queued or running: quitting must wait."""
        with self._guard:
            return self._mutating > 0

    def quit_begun(self):
        """True once a quit decided it (`begin_closing`, before the quit's first await): no new mutation is
        admitted from then on, and the UI admits no new readiness work either — a slice queued behind the exit
        would run for nobody (C-3b). Read-only, so a timer may ask without sealing anything itself."""
        with self._guard:
            return self.sealed

    def take_release(self):
        """Hand the current job's releases to a UI hand-over (called on the worker thread from the delivery path).
        The hand-over owns them and must release them when the handler returned, raised or was dropped. None when
        the job owes nothing (a cuttable job that changed nothing) or the callback is not a hand-over."""
        releases, self._released = self._released, []
        return Releases(releases) if releases else None

    def released(self):
        """Drop one mutating job's count (Release.release owns the once-only guard)."""
        with self._guard:
            self._mutating -= 1

    @contextlib.contextmanager
    def _mutation(self):
        """A permit for a mutation that starts inside an already-running job (an export). It is registered under
        the same guard as the closing decision, so the race has exactly two outcomes: the job takes the permit
        first (the count is up before quitting looked, and quitting then waits for the mutation to end) or the
        controller is already closing (the permit is refused and the job must not start the mutation). Yields
        whether it was admitted. The count stays up until that job's delivery is over: the worker hands it out with
        the job's own count (take_release) and drops it itself when the job has no hand-over."""
        with self._guard:
            if self.sealed:
                admitted = False
            else:
                self._mutating += 1
                self._released.append(Release(self))
                admitted = True
        yield admitted

    def begin_closing(self):
        """Refuse any new mutation now, under the guard that admits one, without waiting for the worker and without
        dropping deliveries: quitting decides this *before* its first await, so a submission or export cannot be
        registered behind the exit and then waited for without bound, while the job that is finishing still shows
        its view (`stop` is what stops deliveries). Watching is closed with it, so an observe slice already inside
        its call cannot launch a fresh `zeroshot watch` after `stop` cut the registry. Idempotent; returns whether
        a mutation is still in flight (a job that must not be cut)."""
        with self._guard:
            self.sealed = True
            waiting = self._mutating > 0
        engine.close_watching()
        return waiting

    def stop(self, timeout=STOP_WAIT):
        """End the worker after its current job; results of jobs finishing now are not delivered (the UI is going).
        A watch slice is bounded by TUI_SLICE, which can outlast the exit budget [ctrl+q] started: its
        `zeroshot watch` child is cut and reaped here, so a slice never leaves an orphan behind (the run it
        watched keeps going; watching is read-only). A mutating job is never cut: the wait for it has no bound (the
        process must not end in the middle of a submission, merge, setup or export). Admission is decided under the
        same guard that admits a mutation (in `begin_closing`), so a quit that wins the race refuses the mutation
        instead of being cut by it."""
        self.begin_closing()  # idempotent: quitting may already have refused new mutations before its first await
        with self._guard:
            self.closing = True  # the UI is going: no delivery reaches it from here
            waiting = self._mutating > 0
            # Publishing under the same guard as the closing decision keeps registration and the queue in one
            # order: `stop` cannot put its sentinel before a job it has already admitted to (C-3b). The queue is
            # unbounded, so `put` never waits.
            self._queue.put(None)
        # The endpoint's teardown is file I/O (close, unlink, rmtree) and must not sit between `begin_closing` and
        # `closing`: the delivery hand-over re-checks `closing` on the UI thread, so any window between the seal and
        # it is a window where a job finishing now still reaches the going screen. Close it after the seal, before
        # the wait below -- a request thread is never joined here either way.
        if self._bridge is not None:
            bridge.unpublish(self.project)
            self._bridge.close()
            self._bridge = None
        if self._thread is not None:
            if waiting:
                self._thread.join(None)
            else:
                engine.cut_watches()  # an observer is cut at once: waiting TUI_SLICE for it would outlive the app
                self._thread.join(timeout)

    def _run(self):
        with contextlib.ExitStack() as stack:
            try:
                app = self.open_session(stack)
            except (Blocked, OSError, ValueError) as error:
                app, self.error, self.family = None, summary(error), catalog.family(error)
            if app is not None:
                try:
                    self._seed_results(app.authority.directory / RESULTS_FILE)
                except Exception:  # results are never in the way: no name for the file leaves none
                    pass
            with self._guard:
                self._opened = True
            booted = app is None
            while True:
                job = self._queue.get()
                if job is None:
                    return
                label, work, done, protect, cut = job
                if self.closing and cut:
                    continue  # nobody is left to see a watch slice; quitting waits for mutations and the one slice
                self.running = label
                if not booted and self._feed_due(label, protect):
                    booted = True
                    self._bootstrap_feed(app)
                try:
                    result, error = work(app), None
                except (Blocked, OSError, ValueError) as caught:
                    result, error = None, refusal(caught)
                except Exception as caught:  # a bug in one action must not kill the worker or the UI
                    result, error = None, "%s: %s%s" % (type(caught).__name__, summary(caught),
                                                         catalog.tag(catalog.UNKNOWN))
                with self._guard:
                    self._pending.discard(label)
                self.running = None
                if protect:
                    self._released.append(Release(self))
                if done is not None:
                    try:
                        done(result, error)
                    except Exception:  # the UI went away
                        pass
                releases, self._released = self._released, []
                for release in releases:
                    release.release()  # no hand-over took it: `done` is None or the callback is not a hand-over
                kind = job_label(label)
                if (kind in OBSERVATIONS or (protect and kind not in NO_WAKE)) and self.on_observed is not None:
                    try:
                        # A6b2b: a state event may have been written (RS5: by a mutating job too, e.g. the owner's
                        # approval); the chat decides on the UI thread
                        self.on_observed()
                    except Exception:  # the UI went away
                        pass

    def _feed_due(self, label, protect):
        """Worker: whether the feed (when the port was requested) must exist before this job: the first watch slice
        (an observation) bootstraps it, so no state event is lost to a feed that does not exist yet. Every other job,
        mutating or read-only (a panel refresh, a draft, the chat's `pending`, the feed ack, which all read an absent
        feed as empty), leaves the store byte-identical, as it was before the port existed."""
        return self._feed is not None and job_label(label) in OBSERVATIONS

    @staticmethod
    def _bootstrap_feed(app):
        """Worker: create the feed once (A6b1 `bootstrap`; a no-op on an existing feed). A store that refuses the
        write leaves the feed absent, which `feed.pending` reads as an empty queue: the session itself stays usable."""
        try:
            feed.bootstrap(app.authority)
        except (Blocked, OSError, ValueError):
            pass

    def feed_port(self):
        """A6b2b: the port `ArchitectChat(feed=)` injects: `pending()`/`handle(seq)` post one job each to the worker
        (the Authority is worker-owned) and wait for it, bounded by `bridge.TIMEOUT`, on the caller's thread;
        `snapshot()` is the app's `chat_snapshot`. Asking for the port makes the worker bootstrap the feed once the
        session is open and before the first observation job (queued behind it); a session that never asks (no
        architect) never bootstraps. Asked after the session opened, the bootstrap is a job of its own."""
        with self._guard:
            self._feed = port = self._feed or FeedPort(self)
            late = self._opened
        if late:
            self.post("feed_bootstrap", self._bootstrap_feed)
        return port

    def _feed_call(self, label, work):
        """One feed job and its bounded wait on a thread that is not the worker -> its result. A refused post, a
        closing controller, a timeout and the job's own error are `Blocked` (a chat note)."""
        if threading.current_thread() is self._thread:
            raise Blocked("The event feed is unavailable from a worker thread.", family="action.refused")
        event, box = threading.Event(), {}

        def done(result, error):
            box["result"], box["error"] = result, error
            event.set()

        closing = Blocked("The interface is closing: the event feed is unavailable.", family=bridge.CLOSING)
        if self.closing or not self.post(label, work, done):
            raise closing
        deadline = time.monotonic() + bridge.TIMEOUT
        while not event.wait(max(0.0, min(0.2, deadline - time.monotonic()))):
            if self.closing:
                raise closing
            if time.monotonic() >= deadline:
                raise Blocked("The event feed did not answer in time.", family=bridge.TIMEOUT_FAMILY)
        if box["error"] is not None:
            raise Blocked(box["error"], family=catalog.UNKNOWN)
        return box["result"]

    def post(self, label, work, done=None, coalesce=False, mutating=False):
        """Queue `work(app)` for the worker; `done(result, error)` is called afterwards on the worker thread.
        A coalesced label is queued once while one is still waiting; a job that changes state is never coalesced
        away. `mutating` marks a job whose label is normally cuttable as one that changes state or starts model work
        anyway: the slice that submits an accepted plan to the planner. A mutating job is refused once closing has
        begun (no new mutation starts then, whatever the caller) and is never skipped. Returns False when it was
        dropped."""
        kind = job_label(label)  # a watch slice's label carries its milestone; its class is what the tables hold
        protect = kind not in CUTTABLE or mutating  # counted as mutating for its whole duration, queue included
        with self._guard:
            if protect and self.sealed:  # a quit began: no submission or export starts behind the exit
                return False
            if coalesce and label in self._pending and not mutating:
                return False
            self._pending.add(label)
            if protect:
                self._mutating += 1
            # Publishing under the same guard as the closing decision keeps registration and the queue in one
            # order: `stop` cannot put its sentinel before a job it has already admitted to (C-3b). The queue is
            # unbounded, so `put` never waits.
            self._queue.put((label, work, done, protect, kind in OBSERVATIONS and not mutating))
        return True

    def origin_fix(self):
        """The readiness item's fix text for a project whose `origin` is not a GitHub repository ("" when it is one,
        or the project is unknown). Read from `setup.check_target`, the item the plan block shows."""
        if self.project is None:
            return ""
        from .. import setup  # lazily, like the other readiness callers
        for found in setup.check_target(self.project):
            if found["id"] == "origin":
                return "" if found["ok"] else found["detail"]
        return ""

    # Bridge: the architect's action tools --------------------------------------
    # The MCP server of the architect's Codex runs in its own process (the store is locked to this one); it reaches
    # these tools over the endpoint's socket. `zplan_status` posts the rows job and waits, bounded, on the socket
    # thread; an action posts a mutating job and waits, on the socket thread, for its callback. The worker never joins a request thread.

    def request_snapshot(self):
        """Capture the common projection on the owning worker, without a Textual screen."""
        return self._feed_call("request_snapshot", lambda app: request_snapshot(take_snapshot(app, self.name), self.name))

    def begin_turn(self, message, occurrence=None, identity=None):
        """Mint the token of one owner turn, before its Codex starts; the turn's MCP server sends it with every
        request. It stands for the owner's message: its first line, scrubbed, at most `MESSAGE_LINE` characters, and
        `occurrence`, the message's place in the architect's store. `end_turn` closes it."""
        token = secrets.token_hex(16)
        reference = {"text": live.scrub(live.first_line(message))[:MESSAGE_LINE], "occurrence": occurrence,
                     **(identity or {})}
        with self._turn_guard:
            self._turns[token] = reference
        return token

    def end_turn(self, token):
        """Close a turn's token: a request that arrives with it afterwards is bound to the events."""
        with self._turn_guard:
            self._turns.pop(token, None)

    def _binding(self, token):
        """`("owner", reference)` when `token` is one `begin_turn` minted and `end_turn` has not closed, else
        `("events", None)`: no token, an unknown one and a closed one alike."""
        with self._turn_guard:
            reference = self._turns.get(token) if isinstance(token, str) else None
        return ("owner", dict(reference)) if reference is not None else ("events", None)

    def _bridge_request(self, request):
        """`(ok, error)` of one request; runs on the endpoint's socket thread. `error` is a {family, message} dict."""
        if self.application is None and self.project is not None:
            with self._guard:
                if self.application is None:
                    ApplicationService(None, store=ArchitectStore(self.project), controller=self)
        if self.application is not None:
            try:
                return self.application.tool_request(request).envelope()
            except Blocked as error:
                return None, {"family": error.family, "message": str(error)}
        tool, args = request.get("tool"), request.get("args")
        args = args if isinstance(args, dict) else {}
        if tool == "zplan_status":
            return self._bridge_status(), None
        if tool in TOOL_ARGUMENTS:
            return self._bridge_action(request.get("id"), tool, args, request.get("turn"))
        return None, {"family": "architect.request_invalid", "message": "Unknown tool: %s." % tool}

    def _bridge_status(self):
        """The request registry, the rows a rows job has just read and the current plan revision. The job is posted
        and waited for, bounded by `STATUS_WAIT`, on the requesting socket thread, never the worker: an answer is
        the state of now. When the worker is busy past the bound (or refuses the job) the answer is the last rows
        with `"stale": true`; `rows unavailable` / `plan unavailable` only when no job has ever run. The rows name
        the approved plan (with each attempt's token), `plan` names the current revision whether or not it is
        approved."""
        event, box = threading.Event(), {}

        def done(result, error):
            box["error"] = error
            event.set()

        fresh = self.post(ROWS, self._rows_job, done) and event.wait(STATUS_WAIT) and box["error"] is None
        rows = self._rows
        payload = {"requests": self._registry.snapshot(), "revision": rows[0] if rows else None,
                   "rows": rows[1] if rows else "rows unavailable",
                   "plan": rows[2] if rows else "plan unavailable",
                   "readiness": rows[3] if rows else [], "profile": rows[4] if rows else None}
        proposal = self.commit_proposal
        if proposal is not None:
            payload["commit"] = {"state": proposal.state, "paths": list(proposal.selection.paths),
                                 "lines": list(proposal.lines)}
        request = self.consent_request
        if request is not None:
            payload["consent"] = {"id": request.id, "action": request.action, "milestone": request.milestone,
                                  "state": request.state, "lines": list(request.lines)}
        if self.asked:
            payload["asked"] = dict(self.asked)
        payload["results"] = self.results()
        if not fresh:
            payload["stale"] = True
        return payload

    def _rows_job(self, app):
        """Read-only snapshot of the current plan for the architect status tool: the approved plan's rows, each with
        its attempt's token (an `awaiting_merge` row also its `merge` evidence), and the current revision (version,
        status and gate verdict, also when it is not approved), the start gate's blocking readiness items and the
        profile, read once (`status_of`) for the profile and the rows' merge evidence alike."""
        self._need(app)
        home = app.delivery.home()
        status = autonomy.status_of(app.profile)
        if home.kind == "approved":
            revision = app.authority.current["version"]
            rows = tuple({"id": row.id, "state": row.state, "attempt": row.token.attempt if row.token else None,
                          "run_id": row.token.run_id if row.token else None, "token": token_fields(row.token),
                          **({"merge": merge_fields(app, row, status)}
                             if row.state == "awaiting_merge" and row.token else {}),
                          **({"reason": reason_of(app, row)} if row.state in REASON_STATES and row.token else {})}
                         for row in home.rows)
        else:
            revision, rows = None, ()
        self._rows = (revision, rows, plan_fields(app.delivery.plan(), app.authority.state["revisions"] if app.authority.state else None), readiness_fields(app), profile_fields(status))
        return None

    def _bridge_action(self, rid, tool, args, turn=None, complete=None, application=None, admitted_binding=None):
        """Post `tool` as one job and wait, bounded, for its callback. `(ok, error)`.

        `Planning.edit` (`zplan_edit_plan`) is the plan service's own rule, so it is admitted as one `_plan_job`
        through the Controller's plan path, exactly as the owner's own submit and revise are; the socket thread
        posts that job directly, so nothing is nested inside another job. Every other action runs in the bridge's
        own `mutating=True` job. Both carry the request's bookkeeping (`open`/`running`/`finish`) inside the job.

        `post` refusing (the interface is leaving) is an immediate refusal with no job; otherwise the socket
        thread waits on the callback's Event, never the worker, so quitting joins no request thread.

        The request's binding is fixed here, at admission, from the `turn` token it arrived with, and stays in its
        registry entry: a job that runs after its turn ended is still the owner turn's."""
        event, box = threading.Event(), {}
        lock = threading.Lock()
        job = {"app": None, "expired": False, "finished": False}  # R3d: the wait and the job meet under `lock`
        binding, message = admitted_binding if admitted_binding is not None else self._binding(turn)
        if not self._registry.open(rid, tool, binding, message):
            error = {"family": bridge.INVALID,
                     "message": "Request %s not accepted: the id is taken or %d requests are not finished yet."
                                % (rid, bridge.MAX_REQUESTS)}
            if complete is not None:
                complete(None, error)
            return None, error

        def done(result, error):
            if error is not None and not box:
                # The job refused before `work` ran (the plan job's own session check, `_need`): the request fails
                # with that refusal, never ends as a success.
                box["error"] = {"family": self.family, "message": self.error or str(error)}
            if complete is not None:
                try:
                    complete(box.get("ok"), box.get("error"))
                except Exception:
                    # An effect may already exist. Leave its durable claim unfinished, not retryable.
                    box.clear()
                    box["error"] = {"family": bridge.TIMEOUT_FAMILY, "message": "outcome unknown"}
            if "error" in box:
                self._registry.finish(rid, error=box["error"])
            else:
                self._registry.finish(rid, ok=box.get("ok"))
            with lock:
                expired = job["expired"]
                job["finished"] = True
            if expired and tool in LATE_WAKE and job["app"] is not None:
                self._late_result(job["app"], rid, tool, box.get("error"))
            event.set()

        def work(app, planning=None):
            job["app"] = app
            self._registry.running(rid)  # queued -> running, visible to a status while the job runs
            app.authority.architect_acting = True  # the events this job's saves capture do not wake the architect
            failure = None
            seen = None
            try:
                if application is not None:
                    self._need(app)
                    if tool in PLAN_TOOLS:
                        application.prepare_tool(app)
                box["ok"] = self._run_tool(app, tool, args, planning, rid)
                if tool in PLAN_TOOLS:
                    box["ok"], seen = box["ok"]  # the plan tool's submission verdict, checks included
                    if application is not None:
                        # Engine observations must still wake later TUI event turns. The architect's
                        # revision creation above is marked separately by the existing feed.
                        app.authority.architect_acting = False
                        box["ok"]["dispatch"] = application.advance_plan(app, seen)
                        if seen.kind == "ready":
                            # Presentation only: the receipt exists before this hook can run.
                            self._notify(self.on_plan_submission, Outcome("dispatched", lines=tuple(
                                box["ok"]["dispatch"].get("lines", ()))))
            except Blocked as error:
                box["error"] = {"family": catalog.family(error), "message": summary(error)}
                failure = error
            except (OSError, ValueError) as error:
                box["error"] = {"family": catalog.UNKNOWN, "message": summary(error)}
                failure = error
            except Exception as error:
                box["error"] = {"family": catalog.UNKNOWN,
                                "message": "%s: %s" % (type(error).__name__, summary(error))}
                failure = error
            finally:
                app.authority.architect_acting = False
            if tool not in PLAN_TOOLS:
                return None
            if failure is not None:  # the plan job's own end writes the result; the request's entry is in `box`
                raise failure
            return seen if seen is not None else Outcome(box["ok"]["status"])

        posted = (self._plan_job(tool, work, done, PLAN_TOOLS[tool], rid) if tool in PLAN_TOOLS
                  else self.post(tool, work, done, mutating=True))
        if not posted:
            error = {"family": "architect.closing", "message": "The interface is closing: the action was not started."}
            if complete is not None:
                complete(None, error)
            self._registry.finish(rid, error=error)
            return None, error
        if not event.wait(bridge.TIMEOUT):
            with lock:
                job["expired"] = not job["finished"]
                gave_up = job["expired"]
            if gave_up:
                return None, {"family": "architect.controller_timeout", "message": "outcome unknown"}
        if "error" in box:
            return None, box["error"]
        return box.get("ok"), None

    def _late_result(self, app, rid, tool, error):
        """R3d: the job of request `rid` ended after its wait gave up: the feed gets one result event, which wakes the
        architect by the autonomy level. The outcome is the call's own result (`_result`); a request refused before
        the tool left one is a failure with the refusal."""
        with self._result_guard:
            kept = next((result for result in reversed(self._results) if result.get("request") == rid), None)
        if kept is not None:
            outcome, family, lines = kept["outcome"], kept["family"], list(kept["lines"])
        else:
            error = error or {}
            outcome, family = "failed", error.get("family") or catalog.UNKNOWN
            lines = [live.scrub(error.get("message") or "")]
        try:
            feed.late_result(app.authority, rid, tool.removeprefix("zplan_"), outcome, family, lines)
        except (Blocked, OSError, ValueError):
            pass

    @staticmethod
    def _argument(args, name, kind):
        """One tool argument of `kind` (int not bool, else str); a missing or wrongly typed one is a refusal."""
        if name not in args:
            raise Blocked("Missing argument %s." % name, family="architect.request_invalid")
        value = args[name]
        good = not isinstance(value, bool) and isinstance(value, kind)
        if not good or (kind is str and not value.strip()):
            raise Blocked("Invalid argument %s." % name, family="architect.request_invalid")
        return value

    @staticmethod
    def _plan_argument(args):
        """The `plan` argument: an object, or the JSON text of one (the model often sends the plan as text: the first
        call of most plan turns on the A0 rig). Anything else is the model's format error, kept from the owner."""
        value = args.get("plan")
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                value = None
        if not isinstance(value, dict):
            raise FormatRefused("Invalid argument plan: send the plan as a JSON object, not as text.", family="action.refused")
        return value

    @staticmethod
    def _text_argument(args, name):
        """An optional string argument ("" when absent); an empty string is allowed, a non-string is invalid."""
        value = args.get(name, "")
        if isinstance(value, bool) or not isinstance(value, str):
            raise Blocked("Invalid argument %s." % name, family="architect.request_invalid")
        return value

    def _run_tool(self, app, tool, args, planning=None, request=None):
        """One action tool, on the worker inside one job: validate the arguments, then the freshness, then the
        Controller's gates and the autonomy policy. `planning` is the plan service of the job that admitted the
        tool (the `zplan_edit_plan` plan job); None for the tools the bridge job admits itself. `request` is the
        bridge request id, which the approval's result names."""
        self._need(app)
        allowed = TOOL_ARGUMENTS.get(tool)
        if allowed is None:
            raise Blocked("Unknown tool: %s." % tool, family="architect.request_invalid")
        unknown = sorted(set(args) - allowed)  # the tool schemas are additionalProperties=false: never ignored
        if unknown:
            raise Blocked("Unknown argument %s." % unknown[0], family="architect.request_invalid")
        if tool == "zplan_start":
            milestone = self._argument(args, "milestone", str)
            revision = self._argument(args, "revision", int)
            if revision < 1:  # the tool schema's own minimum: a lower one never names the current revision
                raise Blocked("Invalid argument revision.", family="architect.request_invalid")
            self._start_wait(milestone, "begin")
            try:
                # a call without a bridge request id (a test's stand-in) is the three-argument form
                started = (self._start_tool(app, milestone, revision) if request is None
                           else self._start_tool(app, milestone, revision, request))
            except BaseException:
                self._start_wait(milestone, "failed")
                raise
            self._start_wait(milestone, "done")
            return started
        if tool == "zplan_stop":
            return self._stop_tool(app, self._argument(args, "milestone", str),
                                   self._argument(args, "run_id", str), request)
        if tool == "zplan_approve_plan":
            revision = self._argument(args, "revision", int)
            if revision < 1:  # the tool schema's own minimum: a lower one never names the current revision
                raise Blocked("Invalid argument revision.", family="architect.request_invalid")
            return self._approve_tool(app, revision, request)
        if tool == "zplan_resume":
            milestone = self._argument(args, "milestone", str)
            return self._resume_tool(app, milestone, self._token_argument(args, milestone), request)
        if tool == "zplan_rebrief":
            milestone = self._argument(args, "milestone", str)
            return self._rebrief_tool(app, milestone, self._token_argument(args, milestone),
                                      self._argument(args, "note", str), request)
        if tool == "zplan_plan":
            return self._plan_tool(app, planning, self._argument(args, "goal", str), request,
                                   self._plan_argument(args) if "plan" in args else None,
                                   self._text_argument(args, "request"))
        if tool == "zplan_edit_plan":
            revision = self._argument(args, "revision", int)
            if revision < 1:  # the tool schema's own minimum: a lower one never names the current revision
                raise Blocked("Invalid argument revision.", family="architect.request_invalid")
            return self._edit_tool(app, planning, revision, self._plan_argument(args), request,
                                   self._text_argument(args, "response"), self._text_argument(args, "request"))
        if tool == "zplan_merge":
            milestone = self._argument(args, "milestone", str)
            with self._project_op:
                return self._merge_tool(app, milestone, self._token_argument(args, milestone), request)
        if tool == "zplan_propose_commit":
            return self._propose_commit_tool(app, args)
        if tool == "zplan_settings":
            return self._settings_tool(app, args, request)
        raise Blocked("Unknown tool: %s." % tool, family="architect.request_invalid")

    @staticmethod
    def _token_argument(args, milestone):
        """The `token` argument as the `delivery.Token` of a status row: exactly the row's own fields. A missing,
        non-object or malformed one, or one of another milestone than `milestone`, is a bad argument, refused before
        the freshness and the policy."""
        value = args.get("token")
        token = token_identity(value) if isinstance(value, dict) else None
        if token is None or token.milestone != milestone:
            raise Blocked("Invalid argument token.", family="architect.request_invalid")
        return token

    def _start_tool(self, app, milestone, revision, request=None):
        """Preview then start in one job. The current revision is required (else today's `Changed`); the policy
        decides on the very profile digest the preview was built on, so a profile that moved after the preview is
        today's `ProfileChanged` refusal rather than a policy answer read from another profile, and
        `Delivery.start`'s own final digest check is kept. A start the level leaves to the owner becomes a
        `ConsentRequest` holding that preview. The call leaves one result, whichever way it ends."""
        attempt = self._next_attempt(app.delivery, milestone)
        turn = self._owner_turn(request)
        try:
            answer = self._start_decided(app, milestone, revision, turn)
        except Exception as error:
            outcome, family = self._fate(error)
            origin, via = self._bound(turn)
            self._result("start", {"milestone": milestone, "attempt": attempt}, origin, outcome, family,
                         summary(error).split("\n"), request, via)
            raise
        if answer["status"] == "awaiting_owner":
            origin, via = self._bound(turn)
            self._result("start", {"milestone": milestone, "attempt": attempt}, origin, "asked", "",
                         ["The start of %s waits for the owner: answer request %s." % (milestone, answer["request"])],
                         request, via)
        else:
            origin, lead, via = self._at_word("start", turn)
            self._result("start", {"milestone": milestone, "attempt": answer["attempt"]}, origin, "done", "",
                         lead + [self._started_line(answer)], request, via)
        return answer

    def _owner_turn(self, request):
        """The owner's message reference when the bridge request `request` was bound to an owner turn at admission
        (V6a), else None: an events binding, a call without a request id."""
        entry = next((item for item in self._registry.snapshot() if item["id"] == request), None)
        return entry["message"] if entry is not None and entry["binding"] == "owner" else None

    @staticmethod
    def _at_word(operation, turn):
        """`(origin, leading lines, turn)` of the result of a call that went through: one bound to an owner turn
        (`turn`, the owner's message reference) is the owner's, via the chat, and says at whose word; any other is the
        architect's."""
        if turn is None:
            return "architect", [], None
        return "owner", ["%s at your word: «%s»" % (AT_WORD[operation], turn["text"])], turn

    @staticmethod
    def _bound(turn):
        """`(origin, turn)` of any other result of a call (refused, failed, asked): the owner's own, via the chat,
        when the call is bound to an owner turn, else the architect's."""
        return ("architect", None) if turn is None else ("owner", turn)

    def _start_decided(self, app, milestone, revision, turn=None):
        delivery = app.delivery
        plan = delivery.plan()  # a session without a plan names no current revision: today's `Changed`, no crash
        if plan is None or plan.get("version") != revision:
            raise Changed("the plan was revised")
        blocked = Controller._blocked(app, "start")
        if blocked:
            raise Blocked("Not ready to start: " + "; ".join(check.line for check in blocked.checks),
                          family="action.refused")
        preview = delivery.preview(milestone, app.roles)
        status = autonomy.status_of(app.profile)  # the policy's own read, once, so it and the preview share a digest
        if status is not None and preview.profile and status.digest != preview.profile:
            raise ProfileChanged("The process profile changed after the preview: check the new values and "
                                 "confirm the start again.")
        by_owner = False
        if autonomy.decide(autonomy.level_of(status), "start") == "ask":
            args = {"milestone": milestone, "revision": revision}
            if turn is None:
                return self._request("start", milestone, args, status, preview)
            by_owner, r = True, self._as_owner(app, "start", milestone, args, status, preview)
        else:
            if turn is None and Controller._attempts(delivery, milestone, revision):
                raise Blocked("%s already has an attempt in plan revision %s: use zplan_rebrief." % (milestone, revision),
                              family="action.refused")
            r = delivery.start(preview, app.roles)
            if turn is not None:
                self._settle_awaiting("start", milestone, {"milestone": milestone, "revision": revision}, r)
        answer = {"milestone": r["milestone"], "plan_revision": r["plan_revision"], "attempt": r["attempt"],
                  "run_id": r["run_id"], "status": r["status"]}
        return dict(answer, origin="owner") if by_owner else answer

    def _as_owner(self, app, action, milestone, args, status, preview=None):
        """An owner turn's `action` the level would ask about, run at once as the owner's own: the service call and
        guards of the owner's yes (`_grant`) on the policy's read `status`, no request stored; an awaiting request for the
        same action, milestone and arguments is settled `done`. Returns the attempt it ran."""
        request = ConsentRequest("", action, milestone, args, status.digest if status is not None else None, preview)
        lines, res = self._grant(app, request)
        self._settle_awaiting(action, milestone, args, res, lines)
        return res

    def _settle_awaiting(self, action, milestone, args, res, lines=None):
        """An owner turn ran `action` (the attempt `res`): an awaiting request for the same action, milestone and
        arguments is settled `done` with the action's receipt lines; a different awaiting request stays."""
        awaiting = self.consent_request
        if (awaiting is not None and awaiting.state == "awaiting"
                and (awaiting.action, awaiting.milestone, awaiting.args) == (action, milestone, args)):
            if lines is None:
                lines = (self._receipt(action, res),)
            self._settled(awaiting, "done", lines)  # the owner's turn did what the events turn's request asked

    @staticmethod
    def _receipt(action, res):
        verb = {"start": "started", "resume": "continued", "rebrief": "new attempt"}[action]
        return Controller._attempt_line(verb, res["milestone"], res["plan_revision"], res["attempt"])

    @staticmethod
    def _next_attempt(delivery, milestone):
        """The attempt number a start of `milestone` would create under the current plan revision: the one a
        preview names (a start that fails before its preview exists still names it)."""
        plan = delivery.plan()
        if plan is None:  # no plan: nothing started under it, and the call itself is refused as `Changed`
            return 1
        revision = plan.get("version")
        return 1 + sum(r["plan_revision"] == revision and r["milestone"] == milestone and r["predecessor"] is None
                       for r in delivery.runs.runs)

    @staticmethod
    def _fate(error):
        """`(outcome, family)` of a call that raised: a refusal (readiness, a moved plan, attempt or profile) is
        `refused` with its family, any other error `failed`."""
        if isinstance(error, Blocked):
            return "refused", catalog.family(error)
        return "failed", catalog.UNKNOWN

    @staticmethod
    def _started_line(res):
        return "%s started · plan r%s · attempt %s" % (res["milestone"], res["plan_revision"], res["attempt"])

    def _stop_tool(self, app, milestone, run_id, request=None):
        """Stop the milestone's latest attempt, named by its run id; another attempt's run id is refused. A session
        without a current plan has no latest attempt to stop: the same `Changed` refusal, never a crash. The call
        leaves one result, whichever way it ends: a stop is requested here, the attempt reaches `stopped` later."""
        delivery = app.delivery
        attempt = 0  # the attempt the run id names; none for an unknown id or a session without a plan
        try:
            if delivery.plan() is not None:
                attempt = next((r["attempt"] for r in delivery.runs.runs
                                if r["milestone"] == milestone and r["run_id"] == run_id), 0)
            r = delivery.latest(milestone) if delivery.plan() is not None else None
            if r is None or r["run_id"] != run_id:
                raise Changed("another attempt was started")
            delivery.stop(r)
        except Exception as error:
            outcome, family = self._fate(error)
            self._result("stop", {"milestone": milestone, "attempt": attempt}, "architect", outcome, family,
                         summary(error).split("\n"), request)
            raise
        self._result("stop", {"milestone": milestone, "attempt": attempt}, "architect", "requested", "",
                     [self._stop_line(milestone)], request)
        return {"milestone": r["milestone"], "attempt": r["attempt"], "run_id": r["run_id"], "status": r["status"]}

    @staticmethod
    def _stop_line(milestone):
        return "Stop of %s requested; the run ends shortly." % milestone

    @staticmethod
    def _attempt_line(verb, milestone, revision, attempt):
        return "%s %s · plan r%s · attempt %s" % (milestone, verb, revision, attempt)

    def _approve_tool(self, app, revision, request=None):
        """Approve the current plan revision in one job. A revision that is not the current one is today's `Changed`;
        the policy decides on the very profile digest the revision's gate was argued under, so a profile that moved
        is today's `ProfileChanged` (never an approval the live configuration no longer backs). `Authority.approve`
        keeps the verifier pass, the plan gate and its own digest check. An approval the level leaves to the owner
        is recorded as asked and left to the plan card. The call leaves one result, whichever way it ends."""
        turn = self._owner_turn(request)
        try:
            answer = self._approve_decided(app, revision, turn)
        except Exception as error:
            outcome, family = self._fate(error)
            origin, via = self._bound(turn)
            self._result("approve", {"revision": revision}, origin, outcome, family,
                         summary(error).split("\n"), request, via)
            raise
        asked = answer["status"] == "awaiting_owner"
        origin, via = self._bound(turn)
        lead = [] if asked else self._at_word("approve", turn)[1]
        self._result("approve", {"revision": revision}, origin, "asked" if asked else "done", "",
                     ["Plan r%s waits for the owner: approve it on the plan card." % revision] if asked
                     else lead + [approved_line(revision)], request, via)
        return answer

    def _approve_decided(self, app, revision, turn=None):
        delivery = app.delivery
        plan = delivery.plan()  # a session without a plan names no current revision: today's `Changed`, no crash
        if plan is None or plan.get("version") != revision:
            raise Changed("the plan was revised")
        status = autonomy.status_of(app.profile)  # the policy's own read, once
        gate = (plan.get("evidence") or {}).get("resolved_config_digest")
        if status is not None and gate and status.digest != gate:
            raise ProfileChanged("The process profile changed after the plan check: check the configuration and "
                                 "approve again.")
        level = autonomy.level_of(status)
        if turn is not None and turn.get("shown_plan") != revision:
            turn = None  # a word approves only the plan the screen showed when the owner wrote
        asked = not autonomy.approves_alone(level, chain_approved(app.authority.state["revisions"]))
        if asked and turn is None:
            return self._ask("approve", revision, "plan")
        app.planning.approve(revision)
        self._answered("approve", revision)
        answer = {"revision": revision, "status": "approved"}
        return dict(answer, origin="owner") if asked else answer

    def _result(self, operation, subject, origin, outcome, family, lines, request=None, turn=None, notify=True):
        """Keep one result of a call: the Controller is the one writer, from the job that ran the call; `subject`
        names what it was about. The architect's reaches the owner once through `on_result`; the owner's own is not
        repeated, their screen already says it, except an owner turn's call that ran as the owner's own (`turn`, the
        owner's message reference: the result is `via` "chat"). No feed event and no wake. Returns a copy."""
        lines = [live.scrub(line) for line in lines if line.strip()][:RESULT_LINES]
        with self._result_guard:
            self._result_seq += 1
            result = {"seq": self._result_seq, "operation": operation, "subject": dict(subject),
                      "outcome": outcome, "family": family, "lines": lines, "origin": origin}
            if request is not None:
                result["request"] = request
            if turn is not None:
                result["via"], result["turn"] = "chat", dict(turn)
            self._results.append(result)
            self._keep(result)
            result = self._copied(result)
        if notify and (origin in ("architect", "zplan") or turn is not None):
            self._notify(self.on_result, result)
        return result

    def _keep(self, result):
        """V2c: the last result of its subject replaces the earlier one and goes to the end; the file follows, in the
        job that wrote the result. A write that fails leaves the result, and the call's own outcome, as they are."""
        key = self._subject_key(result)
        self._kept = [kept for kept in self._kept if self._subject_key(kept) != key][-(RESULTS - 1):]
        self._kept.append(self._copied(result))
        if self._results_path is not None:
            try:
                atomic_state(self._results_path, {"results": self._kept})
            except OSError:
                pass

    @staticmethod
    def _copied(result):
        copy = dict(result, subject=dict(result["subject"]), lines=list(result["lines"]))
        if "turn" in copy:
            copy["turn"] = dict(copy["turn"])
        return copy

    @staticmethod
    def _subject_key(result):
        return result["operation"], tuple(sorted(result["subject"].items()))

    @staticmethod
    def _turn_shaped(turn):
        """Legacy message references plus optional application-issued owner linkage."""
        required = {"text", "occurrence"}
        linkage = {"parent_operation_id", "conversation_id", "turn_id", "message_id"}
        return (isinstance(turn, dict) and required <= set(turn) <= required | linkage | {"shown_plan"}
                and (turn.get("shown_plan") is None
                     or (isinstance(turn["shown_plan"], int) and not isinstance(turn["shown_plan"], bool)))
                and isinstance(turn["text"], str)
                and (turn["occurrence"] is None
                     or (isinstance(turn["occurrence"], int) and not isinstance(turn["occurrence"], bool)))
                and all(isinstance(turn[key], str) and turn[key] for key in linkage & set(turn)))

    def _seed_results(self, path):
        """Worker, at session open: load valid results independently, retaining legacy and linked entries.
        A missing, unreadable or malformed container gives none; one malformed entry cannot hide its valid peers.
        The file is left alone until the next result writes it."""
        kept = []
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(stored, dict) or not isinstance(stored.get("results"), list):
                raise ValueError("results.json is not a list of results")
            shape = {"seq": int, "operation": str, "subject": dict, "outcome": str, "family": str, "lines": list,
                     "origin": str}
            for result in stored["results"]:
                if not (isinstance(result, dict) and set(result) - {"request", "via", "turn"} == set(shape)
                        and all(type(result[name]) is kind for name, kind in shape.items())
                        and all(isinstance(line, str) for line in result["lines"])
                        and all(value is None or (isinstance(value, (int, str)) and not isinstance(value, bool))
                                for value in result["subject"].values())
                        and isinstance(result.get("request", ""), str)
                        and ("via" in result) == ("turn" in result)
                        and (("via" not in result) or (result["via"] == "chat" and self._turn_shaped(result["turn"])))):
                    continue
                kept.append(result)
        except (OSError, ValueError, KeyError, TypeError):
            kept = []
        with self._result_guard:
            for result in kept:
                self._results.append(result)
                self._keep(result)  # no path yet: nothing is rewritten before the next result
            self._results_path = path
            self._result_seq = max([result["seq"] for result in kept], default=0)

    def results(self):
        """The kept results, oldest first, as copies (a status reads them on the socket thread)."""
        with self._result_guard:
            return [self._copied(result) for result in self._results]

    def _owner_decision(self, operation, version, act, line):
        """The owner's own approve or override in its plan job: `act()` then one result, `done` with the
        result's own `line` or `refused` with the refusal's family and text (the job still fails as before)."""
        try:
            act()
        except Exception as error:
            outcome, family = self._fate(error)
            self._result(operation, {"revision": version}, "owner", outcome, family, summary(error).split("\n"))
            raise
        self._result(operation, {"revision": version}, "owner", "done", "", [line])
        self._answered("approve", version)

    def _resume_tool(self, app, milestone, token, request=None):
        """Resume the exact attempt a status row named, in one job. The call leaves one result, whichever way it
        ends (V2f)."""
        turn = self._owner_turn(request)
        try:
            answer = self._resume_decided(app, milestone, token, turn)
        except Exception as error:
            outcome, family = self._fate(error)
            origin, via = self._bound(turn)
            self._result("resume", {"milestone": token.milestone, "attempt": token.attempt}, origin, outcome,
                         family, summary(error).split("\n"), request, via)
            raise
        self._architect_attempt("resume", "continued", milestone, token, answer, request, turn)
        return answer

    def _architect_attempt(self, operation, verb, milestone, token, answer, request, turn=None):
        subject = {"milestone": token.milestone, "attempt": token.attempt}
        if answer["status"] == "awaiting_owner":
            origin, via = self._bound(turn)
            self._result(operation, subject, origin, "asked", "",
                         ["The %s of %s waits for the owner: answer request %s." % (operation, milestone,
                                                                                    answer["request"])], request, via)
        else:
            origin, lead, via = self._at_word(operation, turn)
            self._result(operation, dict(subject, created=answer["attempt"]), origin, "done", "",
                         lead + [self._attempt_line(verb, answer["milestone"], answer["plan_revision"],
                                                    answer["attempt"])], request, via)

    def _resume_decided(self, app, milestone, token, turn=None, due=False):
        """The exact attempt is resolved (an attempt that moved is today's `Changed`), then today's readiness gate
        `resume`, the autonomy policy and the milestone profile guard, enforced before the dispatch and bound to the
        policy's own read. A resume the level leaves to the owner becomes a `ConsentRequest`. An attempt paused on a
        provider limit is resumed only by `resume_due` (`due`) or in the owner's turn: an event turn is refused."""
        delivery = app.delivery
        r = delivery.resolve(token, exact=True)
        if turn is None and not due and r.get("resume_at"):
            raise Blocked("%s is paused on a provider limit: zplan continues it by itself when the limit resets."
                          % milestone, family="action.refused")
        blocked = Controller._blocked(app, "resume")
        if blocked:
            raise Blocked("Not ready to continue: " + "; ".join(check.line for check in blocked.checks),
                          family="action.refused")
        status = autonomy.status_of(app.profile)  # the policy's own read, once
        by_owner = False
        if autonomy.decide(autonomy.level_of(status), "resume") == "ask":
            args = {"milestone": milestone, "token": token_fields(token)}
            if turn is None:
                return self._request("resume", milestone, args, status)
            by_owner, res = True, self._as_owner(app, "resume", milestone, args, status)
        else:
            Controller._action_status(app, "milestone", status)  # the guard the owner's own resume applies, before it
            res = delivery.resume(r)
            if turn is not None:
                self._settle_awaiting("resume", milestone, {"milestone": milestone, "token": token_fields(token)}, res)
        answer = {"milestone": res["milestone"], "plan_revision": res["plan_revision"], "attempt": res["attempt"],
                  "run_id": res["run_id"], "status": res["status"]}
        return dict(answer, origin="owner") if by_owner else answer

    def _rebrief_tool(self, app, milestone, token, note, request=None):
        """A new attempt with the owner's note, in one job. The call leaves one result, whichever way it ends
        (V2f)."""
        turn = self._owner_turn(request)
        try:
            answer = self._rebrief_decided(app, milestone, token, note, turn)
        except Exception as error:
            outcome, family = self._fate(error)
            origin, via = self._bound(turn)
            self._result("rebrief", {"milestone": token.milestone, "attempt": token.attempt}, origin, outcome,
                         family, summary(error).split("\n"), request, via)
            raise
        self._architect_attempt("rebrief", "new attempt", milestone, token, answer, request, turn)
        return answer

    def _rebrief_decided(self, app, milestone, token, note, turn=None):
        """A new attempt with the owner's note, in one job. The token is resolved exactly (an attempt that moved is
        today's `Changed`), then today's readiness gate `start`, the autonomy policy and the milestone profile
        guard, and `check_followup` inside the service. A `needs_owner` attempt is answered, any other unsuccessful
        attempt gets a new attempt; the note is added to the attempt's task notes, the brief itself unchanged. The
        attempt's roles come from the same profile read the policy decided on, so the two never disagree. A rebrief
        the level leaves to the owner becomes a `ConsentRequest`, also in an owner turn when it answers a
        `needs_owner` question (the owner writes that answer on the card); any other rebrief the owner's turn asked
        for runs as the owner's own."""
        delivery = app.delivery
        r = delivery.resolve(token, exact=True)
        if turn is None and r.get("resume_at"):
            raise Blocked("%s is paused on a provider limit: zplan continues it by itself when the limit resets."
                          % milestone, family="action.refused")
        if turn is None:
            attempts = Controller._attempts(delivery, r["milestone"], r["plan_revision"])
            if attempts >= ARCHITECT_ATTEMPTS + 1:
                raise Blocked("%s has had %d attempts in plan revision %s; the owner decides now."
                              % (r["milestone"], attempts, r["plan_revision"]), family="action.refused")
        blocked = Controller._blocked(app, "start")
        if blocked:
            raise Blocked("Not ready for a new attempt: " + "; ".join(check.line for check in blocked.checks),
                          family="action.refused")
        status = autonomy.status_of(app.profile)  # the policy's own read, once
        by_owner = False
        level = autonomy.level_of(status)
        answers = turn is not None and r["outcome"] == "needs_owner" and level in ("supervised", "manual")
        if answers or autonomy.decide(level, "rebrief") == "ask":
            args = {"milestone": milestone, "token": token_fields(token), "note": note}
            if turn is None or answers:
                return self._request("rebrief", milestone, args, status)
            by_owner, res = True, self._as_owner(app, "rebrief", milestone, args, status)
        else:
            res = Controller._rebrief_attempt(app, r, note, status, after_merge=turn is None)
            if turn is not None:
                self._settle_awaiting("rebrief", milestone,
                                      {"milestone": milestone, "token": token_fields(token), "note": note}, res)
        answer = {"milestone": res["milestone"], "plan_revision": res["plan_revision"], "attempt": res["attempt"],
                  "run_id": res["run_id"], "status": res["status"]}
        return dict(answer, origin="owner") if by_owner else answer

    @staticmethod
    def _attempts(delivery, milestone, revision):
        """The number of attempts the milestone has in plan revision `revision`."""
        return sum(1 for run in delivery.runs.runs if run["milestone"] == milestone and run["plan_revision"] == revision
                   and "resume_at" not in run)  # the attempt zplan itself continued after a limit costs no attempt

    @staticmethod
    def _rebrief_attempt(app, r, note, status, after_merge=False):
        """The new attempt of `r` with the owner's note, after the policy read `status` allowed it or the owner
        granted it: the profile the attempt runs under is bound to that read, and the cap guard comes first."""
        delivery = app.delivery
        enforced = Controller._action_status(app, "milestone", status)  # the profile the attempt itself runs under
        roles = enforced.resolved.roles() if enforced is not None else None
        delivery.admission()  # C3: the same cap guard the owner's own paths take, before the attempt is created
        if after_merge and r["outcome"] == "done":  # an event turn after a failed merge
            return delivery.runs.answer(r, note, roles, after_merge=True)
        return (delivery.runs.answer(r, note, roles) if r["outcome"] == "needs_owner"
                else delivery.runs.retry(r, note, roles))

    def _brake(self, app, request=None):
        """A10: the architect gets one automatic revision after a rejection. A current revision the plan check
        rejected (`review_exhausted`) that an architect tool made is the owner's to decide: both plan tools refuse,
        nothing written. The mark lives in the feed of the planning store, so it holds after a restart.

        A current Goldfish revision has the chain budget instead: an event turn is refused when the chain's
        architect revisions are spent or the owner stopped the run; an owner turn may create one revision per owner
        message."""
        current = app.authority.current
        if is_goldfish(current):
            turn = self._owner_turn(request)
            if turn is None:
                budget = chain_budget(app.authority.state["revisions"])
                if current["status"] == "stopped" or (budget is not None and budget[0] >= budget[1]):
                    raise Blocked("The plan check rejected revision %s; the owner decides now." % current["version"],
                                  family="action.refused")
            elif self._turn_key(turn) in self._revised_in:
                raise Blocked("This message already produced a revision; the owner's next message can revise again.",
                              family="action.refused")
            return
        if current["status"] == "review_exhausted" and feed.architect_made(app.authority, current["version"]):
            raise Blocked("The plan check rejected revision %s; the owner decides now." % current["version"],
                          family="action.refused")

    @staticmethod
    def _turn_key(turn):
        return turn["occurrence"], turn["text"]

    def _format_cap(self, request):
        """In an owner turn that had FORMAT_REFUSALS plan format refusals, both plan tools refuse before any work."""
        turn = self._owner_turn(request)
        if turn is not None and self._format_refusals.get(self._turn_key(turn), 0) >= FORMAT_REFUSALS:
            raise FormatRefused("The plan could not be written in this turn: tell the owner what blocks it.",
                                family="action.refused")

    def _plan_tool(self, app, planning, goal, request, plan=None, note=""):
        """Save the architect's own plan for the goal as a Goldfish revision, inside the one `_plan_job` the bridge
        admitted it as (`Planning.plan_draft`: the plan is validated and reviewed, no planner). Only in a turn the
        owner started (V6a): any other request is refused, nothing written; so is a call without `plan`. The
        Application Service advances a ready revision before any presentation hook; the approval of the plan stays
        the level's rules."""
        self._format_cap(request)
        if self._owner_turn(request) is None:
            raise Blocked("A plan starts only on the owner's word: the owner asks for it in the chat.",
                          family="autonomy.ask")
        if plan is None:  # the architect writes the plan: there is no planner to ask
            raise Blocked("The plan is missing: write the plan and pass it as `plan`.", family="action.refused")
        if not planning.valid_goal(goal):
            raise Blocked(planning_module.GOAL_PROBLEM, family="usage.invalid_option")
        return self._revised(app, request,
                             lambda: planning.plan_draft(goal, plan, note, by="owner", roles=app.roles))

    def _revised(self, app, request, create):
        """The result of a tool that creates a Goldfish revision with `create`; an owner turn's message is marked as
        having produced one, for the brake."""
        turn = self._owner_turn(request)
        before = app.authority.current["version"] if app.authority.state and app.authority.state["revisions"] else 0
        try:
            outcome = verdict(create())
        finally:
            if turn is not None and app.authority.state and app.authority.state["revisions"] \
                    and app.authority.current["version"] != before:
                self._revised_in.add(self._turn_key(turn))
        return {"revision": app.authority.current["version"], "status": outcome.kind}, outcome

    def _edit_tool(self, app, planning, revision, plan, request=None, response="", note=""):
        """Save an edited plan as a new Goldfish revision, inside the one `_plan_job` the bridge admitted it as.
        `Planning.revise_draft` is the whole rule (not current, invalid or unchanged refuses as `action.refused`
        before anything is written); its verdict is advanced by the Application Service before
        `on_plan_submission` presents it. This only proposes a revision: approval remains gated."""
        self._format_cap(request)
        self._brake(app, request)
        by = "owner" if self._owner_turn(request) is not None else "architect"
        return self._revised(app, request, lambda: planning.revise_draft(revision, plan, response, note, by=by))

    def _settings_tool(self, app, args, request=None):
        """Ask for a change of the level, parallel runs, merge gate or roles of the accepted profile, only in the
        owner's turn (V6a): an events request is refused, nothing changed. The change never applies here (what the
        architect reads could ask for one): it becomes the owner's consent card naming each change as "old -> new",
        and his yes applies it (`_grant`). A project file as the source, a value the profile refuses (`Profile.preview`,
        the /setup editor's own rule) or a change already in place is refused at once. The call leaves one result."""
        turn = self._owner_turn(request)
        origin, via = self._bound(turn)
        subject = {"keys": ",".join(sorted(args))}
        try:
            if turn is None:
                raise Blocked("Settings change only on the owner's word: the owner asks for it in the chat.",
                              family="autonomy.ask")
            changes = self._settings_changes(args)
            if app.profile is None:
                raise Blocked("The process profile is not used in this session.", family="action.refused")
            before = self._profile_config(app.profile.status())
            after = app.profile.preview(changes).config
            shown = self._setting_lines(changes, before, after)
            if not shown:
                raise Blocked("The settings are already as asked.", family="action.refused")
            answer = self._request("settings", "", dict(args), autonomy.status_of(app.profile), lines=tuple(shown))
        except Exception as error:
            outcome, family = self._fate(error)
            self._result("settings", subject, origin, outcome, family, summary(error).split("\n"), request, via)
            raise
        room = RESULT_LINES - 1  # the first line is the lead; the changes beyond the room share the last
        lines = list(shown)
        if len(lines) > room:
            lines = lines[:room - 1] + ["; ".join(lines[room - 1:])]
        self._result("settings", subject, origin, "asked", "",
                     ["The settings change waits for your yes on the card."] + lines, request, via)
        return dict(answer, changes=shown)

    @staticmethod
    def _settings_changes(args):
        """The `changes` of `Profile.revise` from the tool's arguments: at least one key, each of its own type (the
        values themselves are the profile's to judge). Anything else is an invalid argument."""
        if not args:
            raise Blocked("Missing argument: at least one of level, max_runs, merge, roles.",
                          family="architect.request_invalid")
        changes = {}
        for name, kind in (("level", str), ("max_runs", int), ("merge", str), ("roles", dict)):
            if name in args:
                changes[name] = Controller._argument(args, name, kind)
        roles = changes.get("roles")
        if roles is not None and (not roles or not all(isinstance(bound, dict) and bound for bound in roles.values())):
            raise Blocked("Invalid argument roles.", family="architect.request_invalid")
        return changes

    @staticmethod
    def _profile_config(status):
        return status.resolved.config if status.resolved is not None else {}

    @staticmethod
    def _setting_lines(changes, before, after):
        """One "key: old -> new" line per changed setting, only for the values that really differ."""
        where = {"level": ("autonomy", "level"), "max_runs": ("autonomy", "max_runs"), "merge": ("gates", "merge")}
        lines = []
        for key, (section, name) in where.items():
            old, new = before.get(section, {}).get(name), after.get(section, {}).get(name)
            if key in changes and old != new:
                lines.append("%s: %s -> %s" % (key, old, new))
        parts = []
        for role, bound in sorted(changes.get("roles", {}).items()):
            for field in sorted(bound):
                old = before.get("roles", {}).get(role, {}).get(field)
                new = after.get("roles", {}).get(role, {}).get(field)
                if old != new:
                    parts.append("%s.%s: %s -> %s" % (role, field, old, new))
        if parts:
            lines.append("roles: " + "; ".join(parts))
        return lines

    def _propose_commit_tool(self, app, args):
        """Offer the owner a commit of their own files; commit nothing. The paths are checked against the live
        status now (the same rules as at «yes»), the card gets the stat, and the architect gets the stat and a
        scrubbed, bounded diff -- never raw content. It is never automatic: no autonomy level lets this run
        without the owner's «yes»."""
        paths = args.get("paths")
        if (not isinstance(paths, list) or not paths or len(paths) > user_commit.MAX_PATHS
                or not all(isinstance(path, str) and path for path in paths)):
            raise Blocked("Invalid argument paths.", family="architect.request_invalid")
        message = user_commit.clean_message(args.get("message"))
        project = app.authority.project
        user_commit.preflight(project)
        selection = user_commit.select(project, paths)
        if not selection.paths:
            raise Blocked("%s: %s." % (user_commit.NOTHING, selection.refusal_line() or "the path list is empty"),
                          family="commit.refused")
        proposal = CommitProposal(uuid.uuid4().hex[:12], tuple(paths), message, selection,
                                  user_commit.stat_text(project, selection))
        self.commit_proposal = proposal
        if self.on_commit_proposal is not None:
            self.on_commit_proposal(proposal)
        return {"status": "awaiting_owner", "paths": list(selection.paths),
                "refused": [{"path": path, "reason": reason} for path, reason in selection.refused],
                "stat": proposal.stat, "diff": user_commit.diff_text(project, selection)}

    def commit_files(self, proposal_id, terminal=True):
        """The owner's «yes»: commit the proposal's files (`user_commit.commit`). Runs on the caller's thread --
        the UI's, under its terminal suspend, as the login does, so hooks and signing may ask the owner. Takes the
        lock merges take; a merge being landed refuses it. Returns the `Committed`; a refusal is a `Blocked`
        and leaves the tree, HEAD and index as they were. The proposal's state records either."""
        proposal = self.commit_proposal
        if self.project is None:
            raise Blocked("No project is selected.", family="commit.refused")
        self._need(None if self.error else self.project)  # the session did not open: its own refusal
        if proposal is None or proposal.id != proposal_id or proposal.state != "awaiting":
            raise Blocked("This commit proposal is no longer valid: ask the architect to propose it again.",
                          family="commit.refused")
        if not self._project_op.acquire(blocking=False):
            raise Blocked("A merge is in progress; repeat the commit after it.", family="commit.refused")
        try:
            result = user_commit.commit(self.project, proposal.requested, proposal.message, terminal)
        except Blocked as error:
            self.commit_proposal = replace(proposal, state="failed", lines=(summary(error),))
            raise
        finally:
            self._project_op.release()
        self.commit_proposal = replace(proposal, state="committed", lines=tuple(result.lines()))
        return result

    def decline_commit(self, proposal_id):
        """The owner's «no»: the proposal is dropped; nothing is run."""
        proposal = self.commit_proposal
        if proposal is not None and proposal.id == proposal_id and proposal.state == "awaiting":
            self.commit_proposal = replace(proposal, state="declined", lines=("The owner declined the commit.",))

    def consent(self, request_id, done=None):
        """The owner's «yes» to the architect's request: run the stored action through the existing operations and
        their checks, as one job (the closing guard of every mutation applies). The profile, the plan revision and
        the attempt must be those the architect asked about; when one moved the request is `stale` and nothing
        ran. A request that is not awaiting any more is left as it is: its «yes» does nothing. Returns what `post`
        returns."""
        def work(app, delivery):
            request = self.consent_request
            if request is None or request.id != request_id:
                raise Blocked("This request is no longer valid: ask the architect again.", family="action.refused")
            if request.state != "awaiting":
                return Outcome(request.state, lines=request.lines, data=request)
            failure = unexpected = None
            try:
                lines, res = self._grant(app, request)
                state = "done"
            except (Changed, ProfileChanged) as error:
                state, lines, failure, res = "stale", (summary(error),), error, None
            except (Blocked, OSError, ValueError) as error:
                state, lines, failure, res = "failed", (summary(error),), error, None
            except Exception as error:  # any other error leaves its result too, then reaches the caller
                state, lines, failure, res, unexpected = "failed", (summary(error),), error, None, error
            outcome, family = ("done", "") if failure is None else self._fate(failure)
            if request.action == "start":  # V2d: the owner's yes is a start call of its own
                subject = {"milestone": request.milestone, "attempt": request.preview.attempt}
            elif request.action == "settings":
                subject = {"keys": ",".join(sorted(request.args))}
            else:  # V2f: so is the yes to a resume or a rebrief, on the attempt the architect's status row named
                token = self._token_argument(request.args, request.milestone)
                subject = {"milestone": token.milestone, "attempt": token.attempt}
                if res:
                    subject["created"] = res["attempt"]
            self._result(request.action, subject, "owner", outcome, family, lines, request.id)
            if unexpected is not None:
                raise unexpected
            return self._settled(request, state, lines)
        return self._job("consent", work, done)

    def decline(self, request_id, done=None):
        """The owner's «no» to the architect's request: it is dropped and nothing runs; a request that is not
        awaiting stays as it is. Runs as one job like `consent`."""
        def work(app, delivery):
            request = self.consent_request
            if request is None or request.id != request_id or request.state != "awaiting":
                return Outcome("ignored")
            if request.action == "resume":
                self._unpause(delivery, request)  # the owner's no ends the pause: the architect decides now
            return self._settled(request, "declined", ("The owner declined the architect's request.",))
        return self._job("decline", work, done)

    def _unpause(self, delivery, request):
        """The owner declined to continue an attempt paused on a limit: it stays a recoverable failure and wakes
        the architect. An attempt that moved, or was never paused, is left as it is."""
        try:
            r = delivery.resolve(self._token_argument(request.args, request.milestone), exact=True)
        except Blocked:
            return
        if "resume_at" in r:
            del r["resume_at"]
            delivery.runs.save(r)

    # Paused attempts ----------------------------------------------------------

    # The refusals that leave a due attempt paused: it is tried again at the next tick.
    STAYS_PAUSED = frozenset(("action.refused", "autonomy.ask", "process.changed", "readiness.tools"))

    def resume_due(self, done=None):
        """Resume, once, every attempt paused on a provider limit whose moment has come, under the autonomy policy
        (the architect's own `resume`): one job, run by the app's tick and at a reopen. The level may leave it to the
        owner (one request); a refusal that is only for now leaves the pause; any other refusal ends it, and the
        architect is woken by the failure it was."""
        def work(app, delivery):
            for r in delivery.runs.due():
                self._resume_paused(app, delivery, r)
            return Outcome("resumed")
        return self._job("limit_resume", work, done)

    def _resume_paused(self, app, delivery, r):
        subject = {"milestone": r["milestone"], "attempt": r["attempt"]}
        asked = self.consent_request
        try:
            answer = self._resume_decided(app, r["milestone"], Token.of(r), None, due=True)
        except Blocked as error:
            if error.family in self.STAYS_PAUSED:
                return
            r.pop("resume_at", None)
            delivery.runs.save(r)
            outcome, family = self._fate(error)
            self._result("resume", subject, "zplan", outcome, family, summary(error).split("\n"))
            return
        if answer["status"] == "awaiting_owner":
            if self.consent_request is not asked:  # the owner is told once, however many ticks find it due
                self._result("resume", subject, "zplan", "asked", "",
                             ["The continuation of %s after the provider limit waits for the owner: answer request %s."
                              % (r["milestone"], answer["request"])])
            return
        self._result("resume", dict(subject, created=answer["attempt"]), "zplan", "done", "",
                     ["%s continued after the provider limit (attempt %s)" % (r["milestone"], answer["attempt"])])

    def _settled(self, request, state, lines):
        """The request ends in `state`: stored, shown by the hook and returned for the owner's card."""
        request = replace(request, state=state, lines=tuple(lines))
        self.consent_request = request
        self._notify(self.on_consent_request, request)
        return Outcome(state, lines=request.lines, data=request)

    def _grant(self, app, request):
        """Run the action the owner granted: the same readiness gate, profile guard and service call the architect's
        own tool makes at a level that allows it, on the profile the policy read when the architect asked. A
        profile that moved since is `ProfileChanged`, a start whose attempt or plan revision moved is the
        service's `Changed`, a token that moved is `Changed`; nothing has run then. Returns `(receipt lines, the attempt it ran)`."""
        delivery = app.delivery
        status = autonomy.status_of(app.profile)
        if (status.digest if status is not None else None) != request.digest:
            raise ProfileChanged("The process profile changed after the architect asked: nothing was done. Ask the "
                                 "architect again.")
        args, milestone = request.args, request.milestone
        if request.action == "settings":  # exactly what the card showed: the digest above is the profile it was read on
            changes = self._settings_changes(args)
            before = self._profile_config(app.profile.status())
            after = self._profile_config(app.profile.revise(changes))
            lead = "Changed settings at your yes. It applies to what starts next; running attempts keep their profile."
            room = RESULT_LINES - 1
            shown = self._setting_lines(changes, before, after)
            if len(shown) > room:
                shown = shown[:room - 1] + ["; ".join(shown[room - 1:])]
            return tuple([lead] + shown), None
        r = None
        if request.action != "start":  # the exact attempt the architect's status row named
            r = delivery.resolve(self._token_argument(args, milestone), exact=True)
        blocked = self._blocked(app, "resume" if request.action == "resume" else "start")
        if blocked:
            raise Blocked("Not ready: " + "; ".join(check.line for check in blocked.checks), family="action.refused")
        if request.action == "start":
            res = delivery.start(request.preview, app.roles)
        elif request.action == "resume":
            Controller._action_status(app, "milestone", status)  # the guard the owner's own resume applies
            res = delivery.resume(r)
        else:
            res = Controller._rebrief_attempt(app, r, args["note"], status)
        return (self._receipt(request.action, res),), res

    def _merge_tool(self, app, milestone, token, request=None):
        """Merge the exact attempt a status row named, in one job. The token is resolved exactly (an attempt that
        moved is today's `Changed`), then the autonomy policy decides on the same profile read the merge is bound to:
        `Delivery.merge` gets the digest the policy saw as `expected`, so a profile that moved to another one, before or
        during the merge, is `process.changed` and nothing is merged. Without the merge gate the tier is judged
        again on the integrated candidate's own paths right before landing (`vet`): a high one asks like the estimate.
        The decision follows the level and the candidate's risk tier (auto allows, supervised asks on high risk, manual asks); the merge gate only decides whether checks and the critic
        run. The result is `Delivery.merge`'s own (`kind` and `line`); a landed merge without the gate says that no
        merge check or critic ran."""
        subject = {"milestone": token.milestone, "attempt": token.attempt}
        turn = self._owner_turn(request)
        try:
            answer, merged = self._merge_decided(app, milestone, token, turn)
        except Exception as error:
            outcome, family = self._fate(error)
            origin, via = self._bound(turn)
            self._result("merge", subject, origin, outcome, family, summary(error).split("\n"), request, via)
            raise
        if merged is None:
            origin, via = self._bound(turn)
            self._result("merge", subject, origin, "asked", "",
                         ["The merge of %s waits for the owner: use the merge card." % milestone], request, via)
        else:
            landed = merged.kind == "integrated"
            origin, via = self._bound(turn)
            lead = self._at_word("merge", turn)[1] if landed else []
            self._result("merge", subject, origin, "done" if landed else "refused", "" if landed else merged.family,
                         lead + [answer["line"]] + list(merged.paths), request, via)
        return answer

    def _merge_decided(self, app, milestone, token, turn=None):
        """`(answer, merge)` of the architect's merge: `merge` is `Delivery.merge`'s verdict, None for an ask. In an
        owner turn (`turn`) a merge the level would ask about runs as the owner's own, unless the candidate's tier is
        high or unknown: that stays the owner's card (here and in `vet`)."""
        delivery = app.delivery
        r = delivery.resolve(token, exact=True)
        status = autonomy.status_of(app.profile)  # the policy's own read, once
        gate, level = autonomy.merge_gate(status), autonomy.level_of(status)
        # A conversational owner turn is not consent to an unverified merge. Only the
        # deterministic owner merge card may opt in, irrespective of risk or autonomy.
        if gate != "required":
            return self._ask("merge", milestone, "merge"), None

        def asks(tier):
            return autonomy.decide(level, "merge", gate, tier) == "ask" and (turn is None or tier not in ("low", "medium"))

        tier = merge_tier(status, changed_paths(app, r))
        if asks(tier):
            return self._ask("merge", milestone, "merge"), None
        by_owner = turn is not None and autonomy.decide(level, "merge", gate, tier) == "ask"

        def vet(paths):  # the tier of the candidate that lands, not of the result branch (a rename on main can raise it)
            if asks(merge_tier(status, paths)):
                raise Blocked("The merge candidate changes files the profile rates high risk: the owner decides.",
                              family="autonomy.ask")

        merged = delivery.merge(r, expected=status.digest if status is not None else None, vet=vet,
                                allow_unverified=False)
        if merged.family == "autonomy.ask":
            return self._ask("merge", milestone, "merge"), None
        if merged.kind == "integrated":
            self._answered("merge", milestone)
        answer = {"milestone": r["milestone"], "kind": merged.kind, "line": merged.line}
        return (dict(answer, origin="owner") if by_owner else answer), merged

    def _notify(self, hook, *args):
        """Tell the screen (a worker-callable hook); a screen that went away is not the job's failure."""
        if hook is not None:
            try:
                hook(*args)
            except Exception:  # the UI went away
                pass

    def _request(self, action, milestone, args, status, preview=None, lines=()):
        """The architect's `action` at "ask": store one `ConsentRequest` and answer `awaiting_owner` with its id; the
        owner's answer is what acts. The same request again is the same id; another one while a request awaits is
        refused naming the awaiting one. `status` is the policy's read, whose digest the owner's answer is checked
        against."""
        request = self.consent_request
        if request is not None and request.state == "awaiting":
            if (request.action, request.args) != (action, args):
                raise Blocked("Request %s (%s %s) is waiting for the owner: wait for the answer before asking "
                              "for another action." % (request.id, request.action, request.milestone),
                              family="autonomy.ask")
            return {"status": "awaiting_owner", "request": request.id}
        request = ConsentRequest(uuid.uuid4().hex[:12], action, milestone, args,
                                 status.digest if status is not None else None, preview, lines=tuple(lines))
        self.consent_request = request
        self._notify(self.on_consent_request, request)
        return {"status": "awaiting_owner", "request": request.id}

    def _ask(self, action, value, card):
        """Record that the architect asked for `action` ("approve": the plan version, "merge": the milestone), which
        stays the owner's own card or command, and answer the architect with the card that holds it."""
        self.asked[action] = value
        self._notify(self.on_asked, dict(self.asked))
        return {"status": "awaiting_owner", "card": card, "decision": {"action": action, "subject": value}}

    def _answered(self, action, value):
        """The owner's own card or command (or an allowed action) did what the architect asked for `value`: the ask
        is over."""
        if self.asked.get(action) == value:
            del self.asked[action]
            self._notify(self.on_asked, dict(self.asked))

    @staticmethod
    def _action_status(app, kind, status):
        """The profile the action itself must run under, bound to the policy's read `status`: `delivery.guard(kind)`
        is exactly the guard `live_roles` applies, read here once after the decision, so a profile the owner moved
        between the decision and the action is today's `ProfileChanged`, never an action the policy no longer backs.
        Returns the Status whose roles the action must use (None without a profile), so the action reads the profile
        no third time; raises the guard's own refusal otherwise."""
        enforced = app.delivery.guard(kind)
        if (enforced is None) != (status is None) or (enforced is not None and enforced.digest != status.digest):
            raise ProfileChanged("The process profile changed after the policy decision: check the new values and "
                                 "repeat the action.")
        return enforced

    # Actions -------------------------------------------------------------------

    def _need(self, app):
        """The open session, or the refusal that explains why there is none."""
        if app is None:
            raise Blocked(self.error, family=self.family)

    def refresh(self, done):
        """Read-only plan slice -> Snapshot."""
        def work(app):
            self._need(app)
            snapshot = take_snapshot(app, self.name)
            return replace(snapshot, scripted=True) if self.scripted else snapshot
        return self.post(REFRESH, work, done, coalesce=True)

    def check(self, done):
        """Readiness slice -> tuple of Check. Attaches the milestone driver once everything is ready, as the
        plain readiness screen does."""
        return self.post(CHECK, lambda app: self._check(app), done, coalesce=True)

    def check_queued(self):
        """True while the readiness job is posted but the worker has not entered it yet (R-4 scheduling): nothing
        has been read at that point, so a request arriving now is still satisfied by that very slice, while a job
        already executing (or finished and waiting for its delivery) is not."""
        with self._guard:
            return CHECK in self._pending and self.running != CHECK

    def _check(self, app):
        items = (app.planning.items("start") if app is not None
                 else self.readiness() if self.readiness is not None else [])
        if app is not None and all(i["ok"] for i in items):
            app.planning.attach_driver()
        return checks_of(items)

    def setup(self, emit, done):
        """Install the pinned tools, streaming each output line to `emit`, then re-check -> tuple of Check."""
        if self.install is None:
            raise Blocked("Installing tools is unavailable here.", family="action.refused")

        def work(app):
            self.install(lambda value="": [emit(line) for line in str(value).split("\n")])
            return self._check(app)
        return self.post(SETUP, work, done, coalesce=True)

    # Planning --------------------------------------------------------------------
    # Every rule below is the service's (terminal_planner.planning); these jobs only order its calls on the worker.

    def _plan_job(self, label, work, done, operation=None, request=None):
        """One plan job. An `operation` (plan, send, restart, revise, edit, stop_planner) makes the job leave one
        result from its own end (V2g), whichever way it ends; `request` is the bridge request id of an architect's
        tool (origin architect), none for the owner's own."""
        def run(app):
            try:
                self._need(app)
                value = work(app, app.planning)
            except Exception as error:
                if operation is not None:
                    self._plan_ended(operation, app, request, error=error)
                raise
            if operation is not None:
                self._plan_ended(operation, app, request, value=value)
            return value
        return self.post(label, run, done)

    def _plan_ended(self, operation, app, request, value=None, error=None):
        """The one result of a plan operation (V2g): `value` is the job's Outcome, `error` what it raised. The subject
        is the revision the plan service holds after the job (None when none). A `sent` or `ready` verdict is sent,
        a readiness block is unsent with the failing checks' lines, the planner's stop is requested, a revision that
        moved on is refused as `Changed`. The architect's `zplan_plan` bound to an owner turn is the owner's own, via
        the chat, and says at whose word when it sent."""
        turn = self._owner_turn(request) if operation == "plan" else None
        try:
            revision = app.authority.current["version"]
            goldfish = is_goldfish(app.authority.current)
        except (AttributeError, Blocked):
            revision, goldfish = None, False
        if error is not None:
            outcome, family = self._fate(error)
            lines = summary(error).split("\n")
        else:
            kind = value.data.kind if value.kind == "plan" else value.kind  # `to_plan` wraps the submission verdict
            if kind in ("sent", "ready"):
                outcome, family = "sent", ""
                lines = ["Plan r%s sent to the %s." % (revision, "plan check" if goldfish else "planner")]
                if turn is not None:
                    lines.insert(0, self._at_word("plan", turn)[1][0])
            elif kind in ("unsent", "blocked"):
                outcome, family = "unsent", ""
                lines = [check.line for check in value.checks] or ["The plan was not sent."]
            elif kind == "stopping":
                outcome, family = "requested", ""
                lines = ["The %s stop was requested." % ("plan check" if goldfish else "planner")]
            elif kind == "stale":
                outcome, family = "refused", Changed.family
                lines = list(value.lines) or ["The plan was revised: it was not sent."]
            else:
                outcome, family, lines = "failed", catalog.UNKNOWN, ["Unexpected plan outcome: %s." % kind]
        notify = True
        if isinstance(error, FormatRefused) and operation in ("plan", "edit"):
            notify = False
            owner_turn = self._owner_turn(request)
            if owner_turn is not None:
                key = self._turn_key(owner_turn)
                count = self._format_refusals.get(key, 0)
                if count < FORMAT_REFUSALS:
                    count = self._format_refusals[key] = count + 1
                    if count == FORMAT_REFUSALS:
                        notify = True
                        lines = ["The plan could not be written: " + lines[0]]
        self._result(operation, {"revision": revision}, "owner" if request is None or turn is not None else "architect",
                     outcome, family, lines, request, turn, notify)

    def decide_profile(self, accept, done, changes=None):
        """The first-start choice of the process profile: accept (records the snapshot, no file; `changes` are the
        editor's values set on it) or later -> the new View."""
        def work(app, planning):
            if app.profile is None:
                raise Blocked("The process profile is not used in this session.", family="action.refused")
            if accept:
                app.profile.accept(changes)
            else:
                app.profile.defer()
            return Outcome("profile", data=process.view(app.profile))
        return self._plan_job("profile", work, done)

    def edit_profile(self, changes, done):
        """/setup «profile»: the editor's `changes` on the accepted profile (its snapshot; a project file is the source and refuses)
        -> the new View. A refused value raises its reason and writes nothing."""
        def work(app, planning):
            if app.profile is None:
                raise Blocked("The process profile is not used in this session.", family="action.refused")
            app.profile.revise(changes)
            return Outcome("profile", data=process.view(app.profile))
        return self._plan_job("profile", work, done)

    def start_planning(self, goal, done, draft=None, card=False):
        """A goal and the current role bindings: readiness first, then a new unsent revision (saved even when the
        check blocks) and the submission verdict -> Outcome (unsent / ready / stale / sent).

        `draft` is the plan identity of the goal draft the form was opened from (None: the owner typed the goal).
        On the worker and immediately before `planning.begin`, that identity is re-checked against the plan
        identity read now: a draft whose plan moved on is refused (`draft.stale`) and writes nothing — no revision,
        no run, no export.

        `card` marks the submission of the goal-draft card's own `/plan`: a readiness refusal there answers `unsent`
        with the gate's checks and writes nothing — the draft stays usable and the plan identity does not move, so a
        retry after the owner fixed readiness still matches the card. The goal form (`card` False) keeps saving the
        unsent revision."""
        return self._plan_job("start", self._start_work(goal, draft, card), done, "plan")

    @staticmethod
    def _start_work(goal, draft=None, card=False):
        """The worker function of `start_planning`, also the architect's `zplan_plan` (`_plan_tool`)."""
        def work(app, planning):
            if not planning.valid_goal(goal):
                raise Blocked(planning_module.GOAL_PROBLEM, family="usage.invalid_option")
            planning.guard()  # an undecided or broken profile refuses before anything is saved or checked
            gate = planning.gate(action="plan")
            if draft is not None:
                reason = chat_module.stale_reason(draft, goal_identity(planning))
                if reason:
                    raise Blocked("%s: %s" % (chat_module.OUTDATED, reason), family="draft.stale")
            if card and not gate.ok:
                return Outcome("unsent", checks_of(gate.missing))
            # The goal is saved whatever the check says, as the plain flow does: quitting never loses it.
            planning.begin(goal, app.roles)
            if not gate.ok:
                return Outcome("unsent", checks_of(gate.missing))
            result = verdict(planning.submission())
            # Readiness failed between the check and the submission: the goal is saved as an unsent revision.
            return Outcome("unsent", result.checks) if result.kind == "blocked" else result
        return work

    def submit_plan(self, done):
        """[g] on the unsent revision; a stale one is renewed and sent by the service (a sent one never is)."""
        def work(app, planning):
            notes = []
            result = planning.send(announce=lambda old, new: notes.append(
                planning_module.renewed_line(old, new["version"])))
            return Outcome(result.kind, checks_of(i for i in result.items if not i["ok"]), lines=tuple(notes))
        return self._plan_job("submit", work, done, "send")

    def restart_plan(self, done):
        return self._plan_job("restart", lambda app, planning: verdict(planning.restart()), done, "restart")

    def stop_planner(self, done):
        """The confirmed stop of the running planner: `Planning.stop()` once, on the worker. A refusal is the
        service's `Blocked`, which the job reports as the error."""
        def work(app, planning):
            planning.stop()
            return Outcome("stopping")
        return self._plan_job("stop_planner", work, done, "stop_planner")

    def revise_plan(self, feedback, done):
        return self._plan_job("revise", lambda app, planning: verdict(planning.revise(feedback)), done, "revise")

    def renew_plan(self, done):
        def work(app, planning):
            planning.renew()
            return Outcome("renewed")
        return self._plan_job("renew", work, done)

    def approve_plan(self, version, done):
        def work(app, planning):
            line = approved_line(version)
            self._owner_decision("approve", version, lambda: planning.approve(version), line)
            return Outcome("approved", lines=(line,))
        return self._plan_job("approve", work, done)

    def override_plan(self, version, reason, done):
        def work(app, planning):
            line = approved_line(version, despite=True)
            self._owner_decision("override", version, lambda: planning.override(version, reason), line)
            return Outcome("overridden", lines=(line,))
        return self._plan_job("override", work, done)

    def details(self, done):
        """The lines under [i] of the plan screen: the requirements, or the details with diagnostics of a failure."""
        return self._plan_job("details", lambda app, planning: Outcome("details", lines=app.delivery.plan_info()), done)

    def plan_record(self, done):
        """[i] on the main screen: the same outcome-first text as the plain [i]."""
        return self._plan_job("record", lambda app, planning: Outcome("details", lines=app.delivery.details()), done)

    def changes(self, done):
        """`git status --short` of the project, as the plain readiness screen's [d] shows it."""
        return self._plan_job("changes", lambda app, planning: Outcome("changes", lines=tuple(app.controller.changes())),
                              done)

    def observe(self, emit, done, dispatch=False):
        """One bounded slice of the planner watch -> Outcome("continue" / "done" / "stale" / "failed"). New
        phases go to `emit(line)` on the worker; the UI posts the next slice while the answer is "continue".
        `dispatch` marks the first slice of an accepted submission: it prepares the checkout, sends the revision
        and saves the receipt, so it is registered as a mutating job (quitting waits for it and never cuts it).
        Every later slice only observes and stays cuttable."""
        def work(app):
            self._need(app)
            version = app.authority.current["version"]
            if self._watch is None or self._watch[0] != version:
                self._watch = (version, app.planning.watch(emit, slice=TUI_SLICE))
            try:
                result = self._watch[1].step()
            except BaseException:
                self._watch = None
                raise
            if result != "continue":
                self._watch = None
            return Outcome(result, data=is_goldfish(app.authority.current))
        return self.post(OBSERVE, work, done, coalesce=True, mutating=dispatch)

    # Milestones ------------------------------------------------------------------
    # Every rule is the delivery service's (terminal_planner.delivery); these jobs only order its calls on the
    # worker. A job that acts on an attempt carries the Token its screen was built from: when the attempt, run,
    # plan revision or delivery moved, the service refuses and the job answers "stale" with the fresh end view.

    def _job(self, label, work, done, coalesce=False):
        def run(app):
            self._need(app)
            return work(app, app.delivery)
        return self.post(label, run, done, coalesce)

    def _end(self, delivery, milestone_id):
        """The end view of the latest attempt of a milestone, or None while it is active or has no attempt. An
        accepted attempt is exported here (`Delivery.end`), so the call takes a mutation permit: a quit that is
        already decided refuses the export (the attempt stays unexported and the next open exports it) and a quit
        arriving while the export runs waits for it -- and for its delivery, so the end view is shown first."""
        r = delivery.latest(milestone_id)
        if r is None or run_state(r) in ACTIVE:
            return None
        with self._mutation() as admitted:
            return delivery.end(r) if admitted else None

    def _acting(self, token, work, exact=True):
        def run(app, delivery):
            try:
                r = delivery.resolve(token, exact)
            except Changed as error:
                return Outcome("stale", lines=(summary(error),), data=self._end(delivery, token.milestone))
            return work(app, delivery, r)
        return run

    @staticmethod
    def _blocked(app, action="start"):
        """The readiness gate right before an action that starts model work (the checks `action` needs): the
        block as an Outcome, else None."""
        gate = app.planning.gate(action=action)
        return None if gate.ok else Outcome("blocked", checks_of(gate.missing))

    def preview_start(self, milestone_id, done):
        """Readiness, then what a start would create -> Outcome("preview", data=Preview) or ("blocked", with the
        checks' lines). A preview that is only shown leaves no result (V2d); a start that is refused or fails
        here leaves the owner's one."""
        def work(app, delivery):
            attempt = self._next_attempt(delivery, milestone_id)
            try:
                blocked = self._blocked(app)
                if blocked:
                    lines = tuple(summary(check.line) for check in blocked.checks)
                    self._result("start", {"milestone": milestone_id, "attempt": attempt}, "owner", "refused",
                                 "action.refused", lines)
                    return Outcome("blocked", blocked.checks, lines)
                preview = delivery.preview(milestone_id, app.roles)
            except Exception as error:
                outcome, family = self._fate(error)
                self._result("start", {"milestone": milestone_id, "attempt": attempt}, "owner", outcome, family,
                             summary(error).split("\n"))
                raise
            return Outcome("preview", lines=(delivery.start_text(preview),), data=preview)
        return self._job("preview", work, done)

    def start_run(self, preview, done):
        """The confirmed start of the previewed attempt (refused when the plan or the attempt number moved). The
        call leaves the owner's one result, whichever way it ends."""
        def work(app, delivery):
            subject = {"milestone": preview.milestone, "attempt": preview.attempt}
            try:
                res = delivery.start(preview, app.roles)
            except ProfileChanged as error:
                # The profile moved after the preview: the owner confirms the new values, nothing was started.
                self._result("start", subject, "owner", "refused", catalog.family(error), [refusal(error)])
                fresh = delivery.preview(preview.milestone, app.roles)
                return Outcome("changed", lines=(refusal(error), delivery.start_text(fresh)), data=fresh)
            except Exception as error:
                outcome, family = self._fate(error)
                self._result("start", subject, "owner", outcome, family, summary(error).split("\n"))
                raise
            self._result("start", subject, "owner", "done", "", [self._started_line(res)])
            return Outcome("started", data=Token.of(res))
        return self._job("start_run", work, done)

    def observe_run(self, milestone_id, emit, done, run_id=None):
        """One bounded slice of a milestone attempt's observation -> Outcome("continue") or ("ended", data=EndView).
        The only caller of the mutating poll; the panel refresh stays read-only. The poll stays cuttable (quitting
        never leaves an orphaned watch child); the end view may export an accepted attempt and is permitted
        separately (see `_end`). `run_id` is the attempt the caller's slice belongs to; it is part of the label, so
        a slice of one attempt is never coalesced away by a still pending slice of another (the caller's own
        coalescing table), and the worker checks it against the milestone's current attempt before it polls: a slice
        whose attempt the milestone has left behind ends without touching the successor (the callbacks already carry
        the identity the caller compares)."""
        def work(app, delivery):
            r = delivery.latest(milestone_id)
            if run_id is not None and (r is None or r["run_id"] != run_id):
                # C4: the milestone has left this attempt behind (a successor attempt, an architect rebrief among
                # them). The successor has its own chain and its own cursor, so this slice never polls it and never
                # builds its end view -- its events are never read, let alone emitted, through these callbacks.
                return Outcome("ended")
            if r is None or run_state(r) not in ACTIVE:
                return Outcome("ended", data=self._end(delivery, milestone_id))
            step = delivery.step(r, self._marks.get(r["run_id"]), TUI_SLICE)
            self._marks[r["run_id"]] = step.mark
            for line in step.events:
                emit(line)
            if step.active:
                return Outcome("continue")
            self._marks.pop(r["run_id"], None)
            return Outcome("ended", data=self._end(delivery, milestone_id))
        # C4: the label names the milestone *and* the attempt, so each running attempt has its own chain of slices
        # and its own mark (keyed by run id); two attempts never coalesce each other's slice away (a coalesced
        # submission is always the same attempt, still scheduled) and a result is never attributed to another
        # attempt (`done` is bound to this milestone and this run id).
        return self._job("%s:%s:%s" % (OBSERVE_RUN, milestone_id, run_id), work, done, coalesce=True)

    def open_run(self, milestone_id, done):
        """[o]: the end view of the latest attempt; "active" when it still runs (observation attaches again). The
        end view exports an accepted attempt, so that call is under a mutation permit: a quit already decided
        refuses the export (no view comes back; the attempt stays as it is) and a quit arriving while it runs waits
        for it."""
        def work(app, delivery):
            r = delivery.latest(milestone_id)
            if r is None:
                return Outcome("none", lines=("%s: no runs." % milestone_id,))
            if run_state(r) in ACTIVE:
                return Outcome("active", data=Token.of(r))
            with self._mutation() as admitted:
                return Outcome("end", data=delivery.end(r)) if admitted else Outcome("end")
        return self._job("open_run", work, done)

    def open_answer_draft(self, identity, milestone, done):
        """[t]: the read-only end view of the attempt an answer draft of `milestone` was written for -> Outcome.

        On the worker, in this order: the draft's plain identity is rebuilt into its `Token` and has to name the
        draft's own `milestone` (a missing, malformed or other-milestone identity is refused at once), the token is
        re-checked against the latest attempt with `resolve(exact=True)`, and only then is the view built — a view
        of a newer attempt than the draft's is never assembled, let alone shown. The view is `Delivery.view`, never
        `Delivery.end`: opening a draft exports nothing, so a finished but unexported attempt stays as it is (D-6a).
        An attempt that is still active, or one whose end offers no `answer` (a finished one, one that never ran),
        is refused before the view is built: the attempt's state alone names the end's owner actions, so a state
        that offers no answer never reaches the export-dependent parts of the view; the view's own `answer` check
        stays as the guard behind it.
        Each refusal is its own catalog family — `draft.malformed`, `draft.stale`, `draft.active`,
        `draft.unavailable` — so the pane's code explains itself in the reference. Read-only throughout: the job
        changes no state and is cuttable like the other read-only opens."""
        def work(app, delivery):
            token = draft_token(identity, milestone)
            if token is None:
                raise Blocked(ANSWER_DRAFT_MALFORMED, family="draft.malformed")
            try:
                r = delivery.resolve(token, exact=True)
            except Changed as error:
                raise Blocked(draft_stale(error), family="draft.stale")
            state = run_state(r)
            if state in ACTIVE:
                raise Blocked(ANSWER_DRAFT_ACTIVE % token.milestone, family="draft.active")
            if not any(name == "answer" for name, _ in END_ACTIONS.get(state, ())):
                raise Blocked(ANSWER_DRAFT_UNAVAILABLE % token.milestone, family="draft.unavailable")
            view = delivery.view(r)
            if "answer" not in view.names:
                raise Blocked(ANSWER_DRAFT_UNAVAILABLE % token.milestone, family="draft.unavailable")
            return Outcome("end", data=view)
        return self._job("open_answer_draft", work, done)

    def answer_draft(self, identity, milestone, text, done):
        """Sending an answer draft of `milestone`: the existing answer path behind the draft's own provenance check.

        The token is rebuilt from the draft's identity — refused as `draft.malformed` when it cannot be rebuilt or
        names another milestone than the draft's — and re-checked with `resolve(exact=True)` on the worker, right
        before the answer is created; only then does the typed answer's own path run (`Delivery.answer` under the
        same readiness gate), so the attempt, note and records are exactly a typed answer's. A draft whose plan,
        attempt, run, status, outcome or delivery moved on is refused with `draft.stale` and sends nothing, and a
        malformed identity with `draft.malformed`. Unlike the typed answer, that refusal has no end view and never
        calls `_end`: it must not export an accepted attempt behind an answer the owner did not send (the owner can
        still open it with [o])."""
        def work(app, delivery):
            token = draft_token(identity, milestone)
            if token is None:
                raise Blocked(ANSWER_DRAFT_MALFORMED, family="draft.malformed")
            try:
                r = delivery.resolve(token, exact=True)
            except Changed as error:
                raise Blocked(draft_stale(error), family="draft.stale")
            blocked = self._blocked(app, "start")
            if blocked:
                return blocked
            return Outcome("attempt", data=Token.of(delivery.answer(r, text)))
        return self._job("answer_draft", work, done)

    def tail(self, done, target=None):
        """[e]: the last lines of `zeroshot logs` of the running or failed attempt (the planner when there is no
        approved plan) -> Outcome("tail", lines, data=title). On the worker with the reader's own deadline; never
        from a refresh and never parsed for lifecycle."""
        def work(app, delivery):
            title, lines = delivery.activity(target)
            return Outcome("tail", lines=tuple(safe(line) for line in lines), data=title)
        return self._job("tail", work, done, coalesce=True)

    def tail_run(self, token, done):
        """[e] in the end-of-run modal: the tail of exactly the attempt the modal shows."""
        def work(app, delivery, r):
            return Outcome("tail", lines=tuple(safe(line) for line in delivery.tail(r)),
                           data="Log %s · attempt %s" % (token.milestone, token.attempt))
        return self._job("tail", self._acting(token, work, exact=False), done, coalesce=True)

    def stop_run(self, token, done):
        """The confirmed stop; the identity check is coarse (a stop never depends on how far the attempt got)."""
        def work(app, delivery, r):
            delivery.stop(r)
            return Outcome("stopping", data=Token.of(r))
        acting = self._acting(token, work, exact=False)

        subject = {"milestone": token.milestone, "attempt": token.attempt}

        def run(app, delivery):
            """The call leaves the owner's one result: requested, or refused (the attempt moved, or a refusal)
            / failed; the screen's `run_note` is worded from the same lines."""
            try:
                outcome = acting(app, delivery)
            except Exception as error:
                fate, family = self._fate(error)
                self._result("stop", subject, "owner", fate, family, summary(error).split("\n"))
                raise
            if outcome.kind == "stale":
                self._result("stop", subject, "owner", "refused", Changed.family, list(outcome.lines))
                return outcome
            self._result("stop", subject, "owner", "requested", "", [self._stop_line(token.milestone)])
            return outcome
        return self._job("stop_run", run, done)

    def check_run(self, token, done):
        """[g] on an interrupted attempt: reconcile with native (an unconfirmed submission is never resent)."""
        def work(app, delivery, r):
            delivery.reconcile()
            now = delivery.latest(token.milestone)
            if run_state(now) in ACTIVE:
                return Outcome("active", data=Token.of(now))
            return Outcome("end", data=delivery.end(now))
        return self._job("check_run", self._acting(token, work, exact=False), done)

    def diff(self, token, done):
        def work(app, delivery, r):
            return Outcome("diff", lines=tuple(delivery.diff_text(r).splitlines()))
        return self._job("diff", self._acting(token, work, exact=False), done)

    def merge(self, token, done):
        """The confirmed merge of the exact attempt the owner looked at. A merge critic that did not finish in its
        slice is not a verdict: the same merge is posted again, slice after slice, until it lands or is refused for
        another reason, and only that last answer reaches `done`. The critic's pending refusal is recognised by its
        family, never by its text. Two calls of one wait start at least one `CRITIC_SLICE` apart: a pending refusal
        that returns at once is paced by short jobs that requeue themselves, so the project lock is free and the
        jobs queued meanwhile run before the next call. `on_merge_wait(milestone)` tells the screen while it waits
        and `(None)` when it ended."""
        began, family, raised = [None], [""], [None]
        subject = {"milestone": token.milestone, "attempt": token.attempt}

        def work(app, delivery, r):
            repeat = began[0] is not None
            began[0] = time.monotonic()
            # A repeat is a new mutation: the permit is taken here, after the token resolved, so a quit that began
            # meanwhile refuses it (admitted before the seal, quitting waits for it). The first call is the owner's.
            with self._mutation() if repeat else contextlib.nullcontext(True) as admitted:
                if not admitted:
                    return Outcome("closing")
                with self._project_op:
                    merged = delivery.merge(r, allow_unverified=True)
            if merged.kind == "refused" and merged.family == "merge.critic_pending":
                return Outcome("waiting")
            family[0] = merged.family
            return Outcome(merged.kind, lines=((merged.line,) if merged.line else ()) + tuple(merged.paths),
                           data=self._end(delivery, token.milestone))
        acting = self._acting(token, work)

        def run(app):
            try:
                self._need(app)
                delivery = app.delivery
                remaining = CRITIC_SLICE - (time.monotonic() - began[0]) if began[0] is not None else 0
                if remaining > 0:
                    time.sleep(min(remaining, MERGE_PACE))
                    return Outcome("pacing")
                if began[0] is not None and self.quit_begun():  # a repeat queued before the quit: it merges for nobody
                    return Outcome("closing")
                return acting(app, delivery)
            except Exception as caught:  # the worker turns it into the caller's text; the result keeps its fate
                raised[0] = caught
                raise

        def settle(outcome, error):
            closing = False
            if error is None and outcome.kind in ("waiting", "pacing", "closing"):
                if outcome.kind == "waiting":
                    self._merge_wait(token.milestone)
                if outcome.kind != "closing" and self.post("merge", run, settle):
                    return
                outcome, error, closing = None, "zplan is closing; the merge was not repeated.", True
            self._merge_wait(None)
            if not closing:  # V2b: the call's one result, from its last answer only
                if error is not None:
                    fate, code = self._fate(raised[0])
                    self._result("merge", subject, "owner", fate, code, error.split("\n"))
                elif outcome.kind == "integrated":
                    self._result("merge", subject, "owner", "done", "", outcome.lines)
                else:  # stale (the attempt moved), a refusal, a conflict, an overlap or an open attempt
                    self._result("merge", subject, "owner", "refused",
                                 Changed.family if outcome.kind == "stale" else family[0], outcome.lines)
            if error is None and outcome.kind == "integrated":
                self._answered("merge", token.milestone)
            if done is not None:
                done(outcome, error)
        return self.post("merge", run, settle)

    def _start_wait(self, milestone, state):
        if self.on_start_wait is not None:
            try:
                self.on_start_wait(milestone, state)
            except Exception:  # the UI went away
                pass

    def _merge_wait(self, milestone):
        if self.on_merge_wait is not None:
            try:
                self.on_merge_wait(milestone)
            except Exception:  # the UI went away
                pass

    def _creating(self, token, make, done, label, action="start", operation=None):
        """Owner actions that create an attempt or a revision: readiness first, then `make(delivery, r)`. With an
        `operation` (resume, rebrief, answer) the call leaves the owner's one result (V2f), whichever way it ends."""
        def work(app, delivery, r):
            blocked = self._blocked(app, action)
            if blocked:
                return blocked
            return make(app, delivery, r)
        acting = self._acting(token, work)
        if operation is None:
            return self._job(label, acting, done)

        subject = {"milestone": token.milestone, "attempt": token.attempt}

        def run(app, delivery):
            try:
                outcome = acting(app, delivery)
            except Exception as error:
                kind, family = self._fate(error)
                self._result(operation, subject, "owner", kind, family, summary(error).split("\n"))
                raise
            if outcome.kind == "attempt":
                made = outcome.data
                self._result(operation, dict(subject, created=made.attempt), "owner", "done", "",
                             [self._attempt_line(self._VERBS[operation], made.milestone, made.plan_revision,
                                                 made.attempt)])
                return outcome
            if outcome.kind == "blocked":  # the readiness gate: the checks' lines are what the screen shows
                outcome = replace(outcome, lines=tuple(summary(check.line) for check in outcome.checks))
            self._result(operation, subject, "owner", "refused",
                         Changed.family if outcome.kind == "stale" else "action.refused", outcome.lines)
            return outcome
        return self._job(label, run, done)

    _VERBS = {"resume": "continued", "rebrief": "new attempt", "answer": "answered"}

    def answer(self, token, text, done):
        return self._creating(token, lambda app, d, r: Outcome("attempt", data=Token.of(d.answer(r, text))),
                              done, "answer", operation="answer")

    def new_attempt(self, token, note, done):
        return self._creating(token, lambda app, d, r: Outcome("attempt", data=Token.of(d.new_attempt(r, note))),
                              done, "new_attempt", operation="rebrief")

    def resume_run(self, token, done):
        return self._creating(token, lambda app, d, r: Outcome("attempt", data=Token.of(d.resume(r))), done, "resume",
                              action="resume", operation="resume")

    def accept(self, token, done):
        def make(app, delivery, r):
            kind, value = delivery.accept(r)
            if kind == "attempt":
                return Outcome("attempt", data=Token.of(value))
            sent = verdict(app.planning.submission())
            return Outcome("plan", sent.checks, ("The proposal changes the plan: revision r%s was created; it needs approval."
                                                 % value["version"],), data=sent)
        return self._creating(token, make, done, "accept")

    def to_plan(self, token, feedback, done):
        """A scope change: the request becomes a plan revision and goes to the planner (blocked -> unsent, as plain).
        The job leaves one result, whichever way it ends (V2g)."""
        def work(app, delivery, r):
            value = delivery.to_plan(r, feedback)
            sent = verdict(app.planning.submission())
            return Outcome("plan", sent.checks, ("Plan change: revision r%s was created; it needs approval."
                                                 % value["version"],), data=sent)
        acting = self._acting(token, work)

        def run(app, delivery):
            try:
                outcome = acting(app, delivery)
            except Exception as error:
                self._plan_ended("feedback", app, None, error=error)
                raise
            self._plan_ended("feedback", app, None, value=outcome)
            return outcome
        return self._job("to_plan", run, done)

    def leave(self, token, done):
        def work(app, delivery, r):
            return Outcome("left", lines=(delivery.leave_line(r),))
        return self._job("leave", self._acting(token, work), done)



class FeedPort:
    """The chat's feed port (A6b2b): the contract in `chat`'s docstring, over the Controller worker."""

    def __init__(self, controller):
        self.controller = controller

    def pending(self):
        return self.controller._feed_call(FEED_PENDING, lambda app: feed.pending(app.authority, limit=None)[0])

    def handle(self, seq):
        self.controller._feed_call(FEED_HANDLE, lambda app: feed.handle(app.authority, seq))

    def status(self):
        """C1a: what `zplan_status` answers now (`Controller._bridge_status`, bounded by `STATUS_WAIT`; `stale` when
        the worker stayed busy). Called off the worker thread, like the other port calls."""
        return self.controller._bridge_status()

    def begin_turn(self, message, occurrence=None):
        """The token of one owner turn (`Controller.begin_turn`); the chat sends it to the turn's MCP server."""
        return self.controller.begin_turn(message, occurrence)

    def end_turn(self, token):
        self.controller.end_turn(token)

    def snapshot(self):
        source = self.controller.snapshot_source
        if source is None:
            raise Blocked("The snapshot for the architect is unavailable.", family="action.refused")
        return source()


def verdict(result):
    """A service Submission as the Outcome the screen shows."""
    return Outcome(result.kind, checks_of(i for i in result.items if not i["ok"]))
