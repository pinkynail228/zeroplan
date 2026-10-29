"""The controller worker behind the TUI: one thread owns the Authority session and everything that touches it.

The UI never calls Authority, MilestoneRuns, Git, setup or login directly. It posts a named action; the worker
runs actions and refresh slices one at a time and hands back immutable snapshots. A refresh slice is the same
read-only overview as the plain home screen (workspace + overview/status): it never polls, submits or dispatches.
This module does not import Textual."""

import contextlib
from dataclasses import dataclass, replace
from pathlib import Path
import queue
import threading
import time
from typing import Optional, Tuple
import uuid

from .. import autonomy, bridge, catalog, engine, feed, planning as planning_module, process, user_commit
from ..architect import NO_PLAN
from ..authority import Authority, Blocked
from ..cli import App, fixture_driver, refusal, safe, summary
from ..delivery import ACTIVE, CRITIC_SLICE, Changed, END_ACTIONS, Row, Token
from ..planning import PlanView
from ..process import Profile, ProfileChanged
from ..runs import MilestoneRuns, extended, git_call, run_state
from . import chat as chat_module

REFRESH, CHECK, SETUP, OBSERVE, OBSERVE_RUN = "refresh", "check", "setup", "observe", "observe_run"
ROWS = "bridge_rows"  # the architect status tool's rows snapshot: read-only, posted and waited for by each status
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
                     "tail", "open_answer_draft", ROWS, FEED_PENDING))
# The action tools' argument keys, exactly their schemas (`architect_tools.TOOLS`, additionalProperties=false):
# a request carrying anything else is an invalid argument, refused before freshness and the policy, never ignored.
TOOL_ARGUMENTS = {"zplan_start": frozenset(("milestone", "revision")),
                  "zplan_stop": frozenset(("milestone", "run_id")),
                  "zplan_approve_plan": frozenset(("revision",)),
                  "zplan_resume": frozenset(("milestone", "token")),
                  "zplan_rebrief": frozenset(("milestone", "token", "note")),
                  "zplan_edit_plan": frozenset(("revision", "plan")),
                  "zplan_revise_plan": frozenset(("revision", "feedback")),
                  "zplan_merge": frozenset(("milestone", "token")),
                  "zplan_propose_commit": frozenset(("paths", "message"))}

# The action tools whose admission is one `_plan_job` (`Planning.edit` is the plan service's own rule): they are
# posted through the Controller's plan-job path from the socket thread itself, exactly as the owner's own submit and
# revise are, never as the generic bridge job and never as a job nested inside another.
PLAN_TOOLS = frozenset(("zplan_edit_plan", "zplan_revise_plan"))


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
    profile: Optional[process.View] = None  # the process profile as the screens show it (None: not enforced)
    plan_state: Optional[object] = None  # the plan identity state of `version` (plain data; None: no plan)
    uncommitted: Tuple[str, ...] = ()  # the paths the last commit does not hold (the planner and the runs see HEAD)

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


def plan_fields(plan):
    """The current plan revision as the status payload names it: its version, status, gate verdict and the
    evidence's findings (at most `PLAN_FINDINGS`, "" without evidence), or None without a revision. The verdict is the evidence's own `verdict` (accepted / rejected), the same word the plan
    screen prints; None while the plan has no verdict yet."""
    if not isinstance(plan, dict):
        return None
    evidence = plan.get("evidence")
    findings = evidence.get("findings") if isinstance(evidence, dict) else None
    findings = findings if isinstance(findings, str) else ""
    return {"version": plan.get("version"), "status": plan.get("status") or "",
            "verdict": evidence.get("verdict") if isinstance(evidence, dict) else None,
            "findings": findings if len(findings) <= PLAN_FINDINGS else findings[:PLAN_FINDINGS - 1] + "…",
            "proposal": plan.get("proposal")}


MERGE_FILES = 20  # the changed files a status row names before it only counts the rest


def merge_fields(app, row, status):
    """What the architect needs to decide a merge from `zplan_status` alone: the result commit, its branch, the
    destination branch, the files the result changes against the destination (at most `MERGE_FILES`, then
    `more`), the live profile's merge gate and check names, and the autonomy policy's own `decision` for a merge
    under them (`status` is the one profile read of the rows job, as `_merge_tool` reads it). `files` is None when
    Git cannot list them; an attempt not exported yet has no commit and no files."""
    r = app.delivery.latest(row.id)
    result, destination = extended(r)["result"] or {}, r["destination"]
    commit, files, more = result.get("commit"), [], 0
    if commit is not None:
        listing = git_call(app.authority.project, "diff", "--name-only", "--no-renames", "-z", destination["base"], commit)
        if listing.returncode:
            files = None
        else:
            names = [name for name in listing.stdout.decode(errors="replace").split("\0") if name]
            files, more = names[:MERGE_FILES], max(0, len(names) - MERGE_FILES)
    resolved = getattr(status, "resolved", None)
    gate = autonomy.merge_gate(status)
    return {"commit": commit, "branch": result.get("branch"), "destination": destination["branch"],
            "files": files, "more": more, "gate": gate,
            "checks": [c["name"] for c in resolved.config["checks"]] if resolved is not None else [],
            "decision": autonomy.decide(autonomy.level_of(status), "merge", gate)}


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


def take_snapshot(app, name):
    """Plain `home` of the session, frozen. Read-only: the overview only detects integration (ancestry)."""
    branch, clean = app.controller.workspace()
    home = app.delivery.home()  # the same lines the plain home prints
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
                    journal=tuple(safe(line) for line in home.journal), flow=home.flow,
                    profile=process.view(app.profile) if app.profile is not None else None,
                    plan_state=plan_state(plan), uncommitted=tuple(app.controller.uncommitted()))


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
        self._rows = None  # (approved revision, rows, current plan) of the last status snapshot; None: none yet
        # The TUI's hand-over for a plan verdict an architect tool produced (A5t2b): the app sets it to a
        # worker-callable that shows the outcome exactly as the owner's own submission does (`after_submission`),
        # so a `zplan_edit_plan` that reaches "ready" starts the planner watch that dispatches it. None in a
        # controller without a UI (the tool still saves the revision).
        self.on_plan_submission = None
        # D4c: the architect's proposal to commit the owner's files (None: none yet). The worker sets it, the app
        # shows its card (`on_commit_proposal`, worker-callable) and runs «yes» on the UI thread (`commit_files`).
        # `_project_op` is the lock merges and that commit share: a commit never runs beside a landing merge.
        self.commit_proposal = None
        self.on_commit_proposal = None
        self._project_op = threading.Lock()
        # A6b2b: the architect chat's wake-up. The app sets `on_observed` to `chat.notify` (called on the worker after
        # each completed observation job; it only marks a request and hands over, never waits) and `snapshot_source`
        # to `chat_snapshot` (what the feed port's `snapshot()` returns, called off the UI thread like the chat's own
        # sends). `_feed` is the requested port: its presence makes the worker bootstrap the feed once the session opens.
        self.on_observed = None
        self.snapshot_source = None
        self.on_merge_wait = None  # the screen's hook: the milestone whose merge waits for the critic, None at its end
        self.on_start_wait = None  # the screen's hook: (milestone, "begin"/"done"/"failed") of a start the architect's tool makes
        self._feed = None
        self._opened = False  # the session open (and the feed bootstrap, when requested) is over; guarded

    @classmethod
    def for_project(cls, project, state_root, fixture_id=None, driver_factory=None, worktrees=None, readiness=None,
                    install=None, login=None, role_preferences=None, engine_factory=None, profile=False):
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
        return cls(open_session, project.name, readiness, install, login, factory,
                   can_plan=engine_factory is not None, project=Path(project).expanduser().resolve())

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

    def _bridge_request(self, request):
        """`(ok, error)` of one request; runs on the endpoint's socket thread. `error` is a {family, message} dict."""
        tool, args = request.get("tool"), request.get("args")
        args = args if isinstance(args, dict) else {}
        if tool == "zplan_status":
            return self._bridge_status(), None
        if tool in TOOL_ARGUMENTS:
            return self._bridge_action(request.get("id"), tool, args)
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
                   "plan": rows[2] if rows else "plan unavailable"}
        proposal = self.commit_proposal
        if proposal is not None:
            payload["commit"] = {"state": proposal.state, "paths": list(proposal.selection.paths),
                                 "lines": list(proposal.lines)}
        if not fresh:
            payload["stale"] = True
        return payload

    def _rows_job(self, app):
        """Read-only snapshot of the current plan for the architect status tool: the approved plan's rows, each with
        its attempt's token (an `awaiting_merge` row also its `merge` evidence), and the current revision (version,
        status and gate verdict, also when it is not approved)."""
        self._need(app)
        home = app.delivery.home()
        if home.kind == "approved":
            revision = app.authority.current["version"]
            status = autonomy.status_of(app.profile) if any(r.state == "awaiting_merge" for r in home.rows) else None
            rows = tuple({"id": row.id, "state": row.state, "attempt": row.token.attempt if row.token else None,
                          "run_id": row.token.run_id if row.token else None, "token": token_fields(row.token),
                          **({"merge": merge_fields(app, row, status)}
                             if row.state == "awaiting_merge" and row.token else {})}
                         for row in home.rows)
        else:
            revision, rows = None, ()
        self._rows = (revision, rows, plan_fields(app.delivery.plan()))
        return None

    def _bridge_action(self, rid, tool, args):
        """Post `tool` as one job and wait, bounded, for its callback. `(ok, error)`.

        `Planning.edit` (`zplan_edit_plan`) is the plan service's own rule, so it is admitted as one `_plan_job`
        through the Controller's plan path, exactly as the owner's own submit and revise are; the socket thread
        posts that job directly, so nothing is nested inside another job. Every other action runs in the bridge's
        own `mutating=True` job. Both carry the request's bookkeeping (`open`/`running`/`finish`) inside the job.

        `post` refusing (the interface is leaving) is an immediate refusal with no job; otherwise the socket
        thread waits on the callback's Event, never the worker, so quitting joins no request thread."""
        event, box = threading.Event(), {}
        if not self._registry.open(rid, tool):  # refused before admission: no job, the registry keeps its entries
            return None, {"family": bridge.INVALID,
                          "message": "Request %s not accepted: the id is taken or %d requests are not finished yet."
                                     % (rid, bridge.MAX_REQUESTS)}

        def done(result, error):
            if error is not None and not box:
                # The job refused before `work` ran (the plan job's own session check, `_need`): the request fails
                # with that refusal, never ends as a success.
                box["error"] = {"family": self.family, "message": self.error or str(error)}
            if "error" in box:
                self._registry.finish(rid, error=box["error"])
            else:
                self._registry.finish(rid, ok=box.get("ok"))
            event.set()

        def work(app, planning=None):
            self._registry.running(rid)  # queued -> running, visible to a status while the job runs
            app.authority.architect_acting = True  # the events this job's saves capture do not wake the architect
            try:
                box["ok"] = self._run_tool(app, tool, args, planning)
            except Blocked as error:
                box["error"] = {"family": catalog.family(error), "message": summary(error)}
            except (OSError, ValueError) as error:
                box["error"] = {"family": catalog.UNKNOWN, "message": summary(error)}
            except Exception as error:
                box["error"] = {"family": catalog.UNKNOWN,
                                "message": "%s: %s" % (type(error).__name__, summary(error))}
            finally:
                app.authority.architect_acting = False
            return None

        posted = (self._plan_job(tool, work, done) if tool in PLAN_TOOLS
                  else self.post(tool, work, done, mutating=True))
        if not posted:
            error = {"family": "architect.closing", "message": "The interface is closing: the action was not started."}
            self._registry.finish(rid, error=error)
            return None, error
        if not event.wait(bridge.TIMEOUT):
            return None, {"family": "architect.controller_timeout", "message": "outcome unknown"}
        if "error" in box:
            return None, box["error"]
        return box.get("ok"), None

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

    def _run_tool(self, app, tool, args, planning=None):
        """One action tool, on the worker inside one job: validate the arguments, then the freshness, then the
        Controller's gates and the autonomy policy. `planning` is the plan service of the job that admitted the
        tool (the `zplan_edit_plan` plan job); None for the tools the bridge job admits itself."""
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
                started = self._start_tool(app, milestone, revision)
            except BaseException:
                self._start_wait(milestone, "failed")
                raise
            self._start_wait(milestone, "done")
            return started
        if tool == "zplan_stop":
            return self._stop_tool(app, self._argument(args, "milestone", str),
                                   self._argument(args, "run_id", str))
        if tool == "zplan_approve_plan":
            revision = self._argument(args, "revision", int)
            if revision < 1:  # the tool schema's own minimum: a lower one never names the current revision
                raise Blocked("Invalid argument revision.", family="architect.request_invalid")
            return self._approve_tool(app, revision)
        if tool == "zplan_resume":
            milestone = self._argument(args, "milestone", str)
            return self._resume_tool(app, milestone, self._token_argument(args, milestone))
        if tool == "zplan_rebrief":
            milestone = self._argument(args, "milestone", str)
            return self._rebrief_tool(app, milestone, self._token_argument(args, milestone),
                                      self._argument(args, "note", str))
        if tool == "zplan_edit_plan":
            revision = self._argument(args, "revision", int)
            if revision < 1:  # the tool schema's own minimum: a lower one never names the current revision
                raise Blocked("Invalid argument revision.", family="architect.request_invalid")
            return self._edit_tool(app, planning, revision, self._argument(args, "plan", dict))
        if tool == "zplan_revise_plan":
            revision = self._argument(args, "revision", int)
            if revision < 1:  # the tool schema's own minimum: a lower one never names the current revision
                raise Blocked("Invalid argument revision.", family="architect.request_invalid")
            return self._revise_tool(app, planning, revision, self._argument(args, "feedback", str))
        if tool == "zplan_merge":
            milestone = self._argument(args, "milestone", str)
            with self._project_op:
                return self._merge_tool(app, milestone, self._token_argument(args, milestone))
        if tool == "zplan_propose_commit":
            return self._propose_commit_tool(app, args)
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

    @staticmethod
    def _start_tool(app, milestone, revision):
        """Preview then start in one job. The current revision is required (else today's `Changed`); the policy
        decides on the very profile digest the preview was built on, so a profile that moved after the preview is
        today's `ProfileChanged` refusal rather than a policy answer read from another profile, and
        `Delivery.start`'s own final digest check is kept."""
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
        if autonomy.decide(autonomy.level_of(status), "start") == "ask":
            raise Blocked("Starting %s is done by the owner in the zplan interface (autonomy policy): /run, or its "
                          "card. A chat reply does not start it." % milestone, family="autonomy.ask")
        r = delivery.start(preview, app.roles)
        return {"milestone": r["milestone"], "plan_revision": r["plan_revision"], "attempt": r["attempt"],
                "run_id": r["run_id"], "status": r["status"]}

    @staticmethod
    def _stop_tool(app, milestone, run_id):
        """Stop the milestone's latest attempt, named by its run id; another attempt's run id is refused. A session
        without a current plan has no latest attempt to stop: the same `Changed` refusal, never a crash."""
        delivery = app.delivery
        r = delivery.latest(milestone) if delivery.plan() is not None else None
        if r is None or r["run_id"] != run_id:
            raise Changed("another attempt was started")
        delivery.stop(r)
        return {"milestone": r["milestone"], "attempt": r["attempt"], "run_id": r["run_id"], "status": r["status"]}

    @staticmethod
    def _approve_tool(app, revision):
        """Approve the current plan revision in one job. A revision that is not the current one is today's `Changed`;
        the policy decides on the very profile digest the revision's gate was argued under, so a profile that moved
        is today's `ProfileChanged` (never an approval the live configuration no longer backs). `Authority.approve`
        keeps the verifier pass, the plan gate and its own digest check."""
        delivery = app.delivery
        plan = delivery.plan()  # a session without a plan names no current revision: today's `Changed`, no crash
        if plan is None or plan.get("version") != revision:
            raise Changed("the plan was revised")
        status = autonomy.status_of(app.profile)  # the policy's own read, once
        gate = (plan.get("evidence") or {}).get("resolved_config_digest")
        if status is not None and gate and status.digest != gate:
            raise ProfileChanged("The process profile changed after the plan check: check the configuration and "
                                 "approve again.")
        if autonomy.decide(autonomy.level_of(status), "approve") == "ask":
            raise Blocked("Approving plan r%s is done by the owner in the zplan interface (autonomy policy): "
                          "/approve, or the plan card. A chat reply does not approve it." % revision,
                          family="autonomy.ask")
        app.planning.approve(revision)
        return {"revision": revision, "status": "approved"}

    @staticmethod
    def _resume_tool(app, milestone, token):
        """Resume the exact attempt a status row named, in one job. The token is resolved exactly (an attempt that
        moved is today's `Changed`), then today's readiness gate `resume`, the autonomy policy and the milestone
        profile guard, enforced before the dispatch and bound to the policy's own read."""
        delivery = app.delivery
        r = delivery.resolve(token, exact=True)
        blocked = Controller._blocked(app, "resume")
        if blocked:
            raise Blocked("Not ready to continue: " + "; ".join(check.line for check in blocked.checks),
                          family="action.refused")
        status = autonomy.status_of(app.profile)  # the policy's own read, once
        if autonomy.decide(autonomy.level_of(status), "resume") == "ask":
            raise Blocked("Continuing %s is done by the owner in the zplan interface (autonomy policy): /run, or its "
                          "card. A chat reply does not continue it." % milestone, family="autonomy.ask")
        Controller._action_status(app, "milestone", status)  # the guard the owner's own resume applies, before it
        res = delivery.resume(r)
        return {"milestone": res["milestone"], "plan_revision": res["plan_revision"], "attempt": res["attempt"],
                "run_id": res["run_id"], "status": res["status"]}

    @staticmethod
    def _rebrief_tool(app, milestone, token, note):
        """A new attempt with the owner's note, in one job. The token is resolved exactly (an attempt that moved is
        today's `Changed`), then today's readiness gate `start`, the autonomy policy and the milestone profile
        guard, and `check_followup` inside the service. A `needs_owner` attempt is answered, any other unsuccessful
        attempt gets a new attempt; the note is added to the attempt's task notes, the brief itself unchanged. The
        attempt's roles come from the same profile read the policy decided on, so the two never disagree."""
        delivery = app.delivery
        r = delivery.resolve(token, exact=True)
        blocked = Controller._blocked(app, "start")
        if blocked:
            raise Blocked("Not ready for a new attempt: " + "; ".join(check.line for check in blocked.checks),
                          family="action.refused")
        status = autonomy.status_of(app.profile)  # the policy's own read, once
        if autonomy.decide(autonomy.level_of(status), "rebrief") == "ask":
            raise Blocked("A new attempt of %s is made by the owner in the zplan interface (autonomy policy): "
                          "/attempt, or its card. A chat reply does not make it." % milestone,
                          family="autonomy.ask")
        enforced = Controller._action_status(app, "milestone", status)  # the profile the attempt itself runs under
        roles = enforced.resolved.roles() if enforced is not None else None
        delivery.admission()  # C3: the same cap guard the owner's own paths take, before the attempt is created
        res = (delivery.runs.answer(r, note, roles) if r["outcome"] == "needs_owner"
               else delivery.runs.retry(r, note, roles))
        return {"milestone": res["milestone"], "plan_revision": res["plan_revision"], "attempt": res["attempt"],
                "run_id": res["run_id"], "status": res["status"]}

    @staticmethod
    def _brake(app):
        """A10: the architect gets one automatic revision after a rejection. A current revision the plan check
        rejected (`review_exhausted`) that an architect tool made is the owner's to decide: both plan tools refuse,
        nothing written. The mark lives in the feed of the planning store, so it holds after a restart."""
        current = app.authority.current
        if current["status"] == "review_exhausted" and feed.architect_made(app.authority, current["version"]):
            raise Blocked("The plan check rejected revision %s; the owner decides now." % current["version"],
                          family="action.refused")

    def _edit_tool(self, app, planning, revision, plan):
        """Save an edited proposal as a new revision, inside the one `_plan_job` the bridge admitted it as (the same
        plan job the owner's own submit and revise use). `Planning.edit` is the whole rule (not current, invalid or
        unchanged refuses as `action.refused` before anything is written); it returns a `Submission`, whose verdict
        is shown exactly as the owner's own submission. A "ready" verdict reaches the UI through
        `on_plan_submission`, so the app's planner watch dispatches the new revision (`zplan_edit_plan` only
        proposes: the approval that lets it run stays the owner's, and `Planning.edit` itself runs the plan gate)."""
        self._brake(app)
        result = planning.edit(revision, plan)
        outcome = verdict(result)
        if outcome.kind == "ready" and self.on_plan_submission is not None:
            self.on_plan_submission(outcome)
        return {"revision": app.authority.current["version"], "status": outcome.kind}

    def _revise_tool(self, app, planning, revision, feedback):
        """Ask the planner for a new revision from written feedback, inside the one `_plan_job` the bridge admitted
        it as, exactly as `_edit_tool` does. Refused, with nothing written, unless `revision` is the current one;
        `Planning.revise` is the rest of the rule (a milestone writer being active refuses)."""
        if app.authority.current["version"] != revision:
            raise Blocked("Only the current revision can be revised.", family="action.refused")
        self._brake(app)
        result = planning.revise(feedback)
        outcome = verdict(result)
        if outcome.kind == "ready" and self.on_plan_submission is not None:
            self.on_plan_submission(outcome)
        return {"revision": app.authority.current["version"], "status": outcome.kind}

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

    @staticmethod
    def _merge_tool(app, milestone, token):
        """Merge the exact attempt a status row named, in one job. The token is resolved exactly (an attempt that
        moved is today's `Changed`), then the autonomy policy decides on the same profile read the merge is bound to:
        `Delivery.merge` gets the digest the policy saw as `expected`, so a profile that moved to another one is
        `process.changed` and nothing is merged. `merge` asks unless the profile requires the merge gate
        (`gates.merge: required`), where auto allows and supervised and manual ask; the result is `Delivery.merge`'s
        own (`kind` and `line`)."""
        delivery = app.delivery
        r = delivery.resolve(token, exact=True)
        status = autonomy.status_of(app.profile)  # the policy's own read, once
        gate = autonomy.merge_gate(status)
        if autonomy.decide(autonomy.level_of(status), "merge", gate) == "ask":
            why = "" if gate == "required" else " The profile has no merge check, so the merge is the owner's."
            raise Blocked("Merging %s is done by the owner in the zplan interface (autonomy policy): the merge card, "
                          "or /merge.%s A chat reply does not merge it." % (milestone, why),
                          family="autonomy.ask")
        merged = delivery.merge(r, expected=status.digest if status is not None else None)
        return {"milestone": r["milestone"], "kind": merged.kind, "line": merged.line}

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
            return take_snapshot(app, self.name)
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

    def _plan_job(self, label, work, done):
        def run(app):
            self._need(app)
            return work(app, app.planning)
        return self.post(label, run, done)

    def decide_profile(self, accept, done, changes=None):
        """The first-start choice of the process profile: accept (writes the file; `changes` are the editor's
        values set on it) or later -> the new View."""
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
        """/setup «profile»: the editor's `changes` on the accepted profile (its file is replaced and committed)
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
        return self._plan_job("start", work, done)

    def submit_plan(self, done):
        """[g] on the unsent revision; a stale one is renewed and sent by the service (a sent one never is)."""
        def work(app, planning):
            notes = []
            result = planning.send(announce=lambda old, new: notes.append(
                planning_module.renewed_line(old, new["version"])))
            return Outcome(result.kind, checks_of(i for i in result.items if not i["ok"]), lines=tuple(notes))
        return self._plan_job("submit", work, done)

    def restart_plan(self, done):
        return self._plan_job("restart", lambda app, planning: verdict(planning.restart()), done)

    def stop_planner(self, done):
        """The confirmed stop of the running planner: `Planning.stop()` once, on the worker. A refusal is the
        service's `Blocked`, which the job reports as the error."""
        def work(app, planning):
            planning.stop()
            return Outcome("stopping")
        return self._plan_job("stop_planner", work, done)

    def revise_plan(self, feedback, done):
        return self._plan_job("revise", lambda app, planning: verdict(planning.revise(feedback)), done)

    def renew_plan(self, done):
        def work(app, planning):
            planning.renew()
            return Outcome("renewed")
        return self._plan_job("renew", work, done)

    def approve_plan(self, version, done):
        def work(app, planning):
            planning.approve(version)
            return Outcome("approved")
        return self._plan_job("approve", work, done)

    def override_plan(self, version, reason, done):
        def work(app, planning):
            planning.override(version, reason)
            return Outcome("overridden")
        return self._plan_job("override", work, done)

    def reject_plan(self, version, done):
        def work(app, planning):
            planning.reject(version)
            return Outcome("rejected")
        return self._plan_job("reject", work, done)

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
            return Outcome(result)
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
        """Readiness, then what a start would create -> Outcome("preview", data=Preview) or ("blocked")."""
        def work(app, delivery):
            blocked = self._blocked(app)
            if blocked:
                return blocked
            preview = delivery.preview(milestone_id, app.roles)
            return Outcome("preview", lines=(delivery.start_text(preview),), data=preview)
        return self._job("preview", work, done)

    def start_run(self, preview, done):
        """The confirmed start of the previewed attempt (refused when the plan or the attempt number moved)."""
        def work(app, delivery):
            try:
                return Outcome("started", data=Token.of(delivery.start(preview, app.roles)))
            except ProfileChanged as error:
                # The profile moved after the preview: the owner confirms the new values, nothing was started.
                fresh = delivery.preview(preview.milestone, app.roles)
                return Outcome("changed", lines=(refusal(error), delivery.start_text(fresh)), data=fresh)
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
        return self._job("stop_run", self._acting(token, work, exact=False), done)

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
        began = [None]

        def work(app, delivery, r):
            repeat = began[0] is not None
            began[0] = time.monotonic()
            # A repeat is a new mutation: the permit is taken here, after the token resolved, so a quit that began
            # meanwhile refuses it (admitted before the seal, quitting waits for it). The first call is the owner's.
            with self._mutation() if repeat else contextlib.nullcontext(True) as admitted:
                if not admitted:
                    return Outcome("closing")
                with self._project_op:
                    merged = delivery.merge(r)
            if merged.kind == "refused" and merged.family == "merge.critic_pending":
                return Outcome("waiting")
            return Outcome(merged.kind, lines=((merged.line,) if merged.line else ()) + tuple(merged.paths),
                           data=self._end(delivery, token.milestone))
        acting = self._acting(token, work)

        def run(app, delivery):
            remaining = CRITIC_SLICE - (time.monotonic() - began[0]) if began[0] is not None else 0
            if remaining > 0:
                time.sleep(min(remaining, MERGE_PACE))
                return Outcome("pacing")
            if began[0] is not None and self.quit_begun():  # a repeat queued before the quit: it merges for nobody
                return Outcome("closing")
            return acting(app, delivery)

        def settle(outcome, error):
            if error is None and outcome.kind in ("waiting", "pacing", "closing"):
                if outcome.kind == "waiting":
                    self._merge_wait(token.milestone)
                if outcome.kind != "closing" and self._job("merge", run, settle):
                    return
                outcome, error = None, "zplan is closing; the merge was not repeated."
            self._merge_wait(None)
            if done is not None:
                done(outcome, error)
        return self._job("merge", run, settle)

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

    def _creating(self, token, make, done, label, action="start"):
        """Owner actions that create an attempt or a revision: readiness first, then `make(delivery, r)`."""
        def work(app, delivery, r):
            blocked = self._blocked(app, action)
            if blocked:
                return blocked
            return make(app, delivery, r)
        return self._job(label, self._acting(token, work), done)

    def answer(self, token, text, done):
        return self._creating(token, lambda app, d, r: Outcome("attempt", data=Token.of(d.answer(r, text))),
                              done, "answer")

    def new_attempt(self, token, note, done):
        return self._creating(token, lambda app, d, r: Outcome("attempt", data=Token.of(d.new_attempt(r, note))),
                              done, "new_attempt")

    def resume_run(self, token, done):
        return self._creating(token, lambda app, d, r: Outcome("attempt", data=Token.of(d.resume(r))), done, "resume",
                              action="resume")

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
        """A scope change: the request becomes a plan revision and goes to the planner (blocked -> unsent, as plain)."""
        def work(app, delivery, r):
            value = delivery.to_plan(r, feedback)
            sent = verdict(app.planning.submission())
            return Outcome("plan", sent.checks, ("Plan change: revision r%s was created; it needs approval."
                                                 % value["version"],), data=sent)
        return self._job("to_plan", self._acting(token, work), done)

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

    def snapshot(self):
        source = self.controller.snapshot_source
        if source is None:
            raise Blocked("The snapshot for the architect is unavailable.", family="action.refused")
        return source()


def verdict(result):
    """A service Submission as the Outcome the screen shows."""
    return Outcome(result.kind, checks_of(i for i in result.items if not i["ok"]))
