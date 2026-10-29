"""The planning service shared by the line UI and the full-screen UI.

Every rule that decides what may happen to a plan lives here: readiness is re-checked right before a submission,
a goal is kept when the check fails, a stale unsubmitted revision is replaced by [n] or, on [g], renewed once
readiness passes and sent in the same action, a revision with a receipt is observed and never resubmitted, an unconfirmed submission is shown and never resent, the planner is
watched in bounded slices, and approval/revision/rejection go through Authority and MilestoneRuns. The UIs ask
this module what to do next and only render the answer (`PlanView`) or call the named action.

No terminal, no Textual: it renders nothing but plain lines."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import os
import re
import shlex
import time
from typing import Optional, Tuple

from . import catalog, live, runs
from .authority import Blocked, canonical, check_bounds, validate_proposal
from .engine import STALE, STALE_BINDING, ObservationDetached, SliceEnded, Stale, binding_identity, recorded_home

PLANNER_SLICE = 15  # seconds per bounded planner watch: phases reach the owner while the planner runs
HEARTBEAT = 120  # seconds without a new phase before a "still working" line
GOAL_LIMIT = 8192
GOAL_PROBLEM = "A non-empty goal of up to 8192 characters is required."
OBSERVING = ("observing", "detached", "observation_blocked")  # a receipt exists; the planner may still run
FAILED = ("run_failed", "proposal_invalid")
OVERRIDDEN = "approved despite the check"  # the approved status word of a plan the owner approved over a rejection
# Planner failure cause (engine.CAUSES, else unknown) -> catalog family. The planner renders every class with its
# own wording, so the two classes it does not branch on of its own (R-2) are named for the same families.
PLANNER_FAMILY = {"limit": "planner.quota", "forbidden": "planner.auth", "auth": "planner.auth",
                  "quota": "planner.quota", "network": "planner.network", None: "planner.unknown"}
# R-2: the shared classifier's extra classes become the planner's own before any branch reads them.
PLANNER_CAUSE = {"limit": "quota", "forbidden": "auth"}
# Readiness items (setup.readiness ids) each model action needs; nothing else may block it.
TOOL_CHECKS = ("socket", "tools", "codex", "codex_home", "auth", "roles")
NEEDS = {
    # The planner works in a disposable clone of the last commit; it commits nothing, so no Git identity.
    "plan": TOOL_CHECKS + ("git", "repo", "branch", "origin"),
    # A new attempt commits in its worktree from the destination branch's HEAD; the tree may hold uncommitted changes.
    "start": TOOL_CHECKS + ("git", "identity", "repo", "branch", "origin"),
    # A resumed attempt continues in its own worktree.
    "resume": TOOL_CHECKS + ("git", "identity", "repo", "branch", "origin"),
}
FIXTURE_SKIPS = TOOL_CHECKS + ("origin",)  # the deterministic engine runs no tools and never looks at a remote


# Text helpers shared by every UI ---------------------------------------------------------------------------

def clean(value):
    """Stored diagnostics or an error as printable text: terminal control sequences (including OSC hyperlinks)
    taken out, what is left is what a screen may render."""
    text = re.sub(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)", "", str(value))
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    return "".join(c for c in text if c.isprintable())


def local_clock(stamp):
    """The `HH:MM` of a stored UTC stamp (`...Z`) in the local zone; a stamp that is not a full ISO one shows the
    `HH:MM` it stores."""
    try:
        return datetime.fromisoformat(stamp).astimezone().strftime("%H:%M")
    except (ValueError, OverflowError, OSError):
        return stamp[11:16]


def summary(value):
    """Bounded one-line projection of stored diagnostics or an error for display."""
    text = clean(value)
    return text[:256] + ("…" if len(text) > 256 else "")


def one_line(text, limit=100):
    """One line of at most `limit` characters, cut at a word boundary."""
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    cut = text[:limit - 1]
    space = cut.rfind(" ")
    return (cut[:space] if space > limit // 2 else cut).rstrip(" ,;:—-") + "…"


def goal_line(goal, limit, action_id):
    """`Goal: <one line>` plus, iff characters were dropped, the catalog hint naming the key that shows the whole
    stored goal on this screen (R-2, `action_id` is that screen's [i]). A literal final ellipsis in the goal is
    not evidence of truncation: only a normalized goal longer than `limit` is, the same normalization `one_line`
    applies. The limit itself is unchanged (100 on home, 200 on the plan screen)."""
    line = one_line(goal, limit)
    if len(" ".join(str(goal).split())) <= limit:
        return "Goal: " + line
    return "Goal: %s — %s" % (line, catalog.hint(action_id))


def plural(n, one, few, many):
    """`n` and its noun: `one` for 1, else `many` (`few` is the slot of the former Russian plural, kept so the
    callers' argument lists stay the same)."""
    return "%s %s" % (n, one if n == 1 else many)


def elapsed(seconds):
    minutes = int(seconds) // 60
    return "%s min" % minutes if minutes else "%s s" % int(seconds)


def renewed_line(old, new):
    """The one line that tells the owner the plan was rebuilt on the current project before it was sent."""
    return "Plan r%s is built on the current project state (r%s → r%s); the goal and settings are the same." % (new, old, new)


# Results -------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Gate:
    """The readiness check right before a model run: `items` are the setup.readiness() items as returned."""
    ok: bool
    items: tuple = ()

    @property
    def missing(self):
        return tuple(i for i in self.items if not i["ok"])


@dataclass(frozen=True)
class Submission:
    """What may happen to the current revision now. `kind`: sent (already has a receipt or is not unsent),
    blocked (readiness missing: `items`), stale (the project moved: [n]), ready (the planner may be started).
    `renewed` is True when a new revision was prepared before the verdict."""
    kind: str
    items: tuple = ()
    renewed: bool = False


@dataclass(frozen=True)
class PlanView:
    """One plan screen, frozen: the body lines exactly as the plain UI prints them, the owner actions it offers
    (service action names, menu order; [q] back is the UI's) and the catalog family behind a failure."""
    kind: str  # unsent | stale | unknown | observing | stopped | failed | proposal
    version: int
    status: str
    lines: Tuple[str, ...]
    actions: Tuple[str, ...]
    cause: Optional[str] = None  # failure cause: auth / quota / network, None when the logs do not say
    family: Optional[str] = None
    home: Optional[str] = None  # the Codex home the failed run recorded (auth failures): what [l] refreshes
    findings: str = ""  # the plan check's findings of a rejected (`review_exhausted`) proposal, one line


class Watch:
    """One observation of the planner in bounded slices: new phases and a rare heartbeat go to `emit`; what the
    owner needs to see that the run is alive (heartbeat, last new record, journal) is stored with the revision."""

    def __init__(self, planning, emit, slice=PLANNER_SLICE):
        a = planning.authority
        self.engine = planning.engine_factory(a.current["engine"], planning.terminal)
        self.planning, self.emit, self.slice = planning, emit, slice
        self.start = self.last = None  # the clock starts with the first slice
        self.shown = []
        self.event = False  # a phase reached the owner during this slice

    def progress(self, line):
        if not self.shown or self.shown[-1] != line:
            self.shown.append(line)
            self.last = self.planning.clock()
            self.event = True
            self.emit(line)
        data = self.planning.authority.current.setdefault("live", live.new())
        live.note(data, line, runs.now())

    def record(self, detached=False, cursor=None, begun=None):
        """Stamp the slice that just ended on the current revision (the shared service owns the clock).

        The same active executions the slice reported also update the planner graph timeline (`live.timeline`); the
        record that ends the run closes every step left open there, because the envelope kept beside a finished run
        may still list executions it observed while it was running."""
        a = self.planning.authority
        current = a.current
        data = current.setdefault("live", live.new())
        stamp = runs.now()
        if begun and data["started"] is None:
            data["started"] = begun
        if detached:
            live.detach(data, stamp)
        else:
            live.touch(data, stamp, self.event or current["observation_cursor"] != cursor)
            envelope = current["observation_envelope"] or {}
            active = envelope.get("status", {}).get("activeExecutions", [])
            data["nodes"] = [[e["node"], e["execution"]] for e in active][:16]
            live.timeline(data, active, stamp, ended=current["terminal_envelope"] is not None)
        self.event = False
        a.save()

    def step(self):
        """One slice: "continue" (the planner still works), "done" (a reviewed plan), "stale" (the project moved
        before submission) or "failed" (the run ended; the plan view explains why). Anything else is raised."""
        a = self.planning.authority
        if self.start is None:
            self.start = self.last = self.planning.clock()
        current = a.current
        cursor = current["observation_cursor"]
        # The attempt starts when this slice submits it; a run that already exists has no known start.
        begun = runs.now() if current["run_id"] is None and "live" not in current else None
        # The owner's [g] on an unconfirmed submission (`Planning.resubmission`) is consumed by this one slice.
        again = {"resubmit": True} if self.planning.resubmit == current["version"] else {}
        self.planning.resubmit = None
        try:
            self.engine.proposal(a, self.progress, slice=self.slice, **again)
        except SliceEnded:
            self.record(cursor=cursor, begun=begun)
            now = self.planning.clock()
            if now - self.last >= HEARTBEAT:
                self.last = now
                self.emit("…still working, %s elapsed" % elapsed(now - self.start))
            return "continue"
        except Stale:
            return "stale"
        except ObservationDetached:
            self.record(detached=True, cursor=cursor, begun=begun)
            raise
        except Blocked:
            if a.current["status"] in FAILED:
                self.record(cursor=cursor, begun=begun)
                return "failed"
            raise
        self.record(cursor=cursor, begun=begun)
        return "done"


class Planning:
    """Planning decisions over one locked Authority and its MilestoneRuns."""

    def __init__(self, authority, runs, engine_factory, readiness=None, driver_factory=None, terminal=None,
                 clock=time.monotonic):
        """`readiness` returns the setup.readiness() items (None: nothing to check); `driver_factory` supplies the
        milestone driver once tools are ready; `engine_factory(name, terminal)` the planner engine."""
        self.authority, self.runs = authority, runs
        self.engine_factory, self.readiness = engine_factory, readiness
        self.driver_factory, self.terminal, self.clock = driver_factory, terminal, clock
        self.profile = None  # process.Profile of the session (None: no profile enforcement, as in unit fixtures)
        self.causes = {}  # planner failure cause per revision, looked up once
        self.resubmit = None  # the version whose unconfirmed submission the owner asked to send again (E4)
        self.identities = {}  # native binary identity per (executable, state root, file stamp): hashed once

    # Reading -----------------------------------------------------------------

    def plan(self):
        a = self.authority
        return a.current if a.state and a.state["revisions"] else None

    def unsent(self):
        current = self.plan()
        return bool(current and current["status"] == "planning" and current["run_id"] is None)

    def binding_changed(self):
        """A prepared, unsent native revision frozen on another toolchain, binary or state directory than this
        session runs: the engine would refuse it (Stale) at submission. Unprepared or unverifiable: False."""
        current = self.plan()
        binding = current and current.get("native_binding")
        if not self.unsent() or current["engine"] != "native" or not binding or "executable" not in binding:
            return False
        try:
            engine = self.engine_factory(current["engine"], self.terminal)
            executable = Path(engine.executable)
            stamp = os.stat(executable)
            key = (str(executable), str(engine.state_root), stamp.st_mtime_ns, stamp.st_size, stamp.st_ino)
            if key not in self.identities:
                self.identities[key] = engine.binary_identity()
        except (Blocked, OSError, AttributeError):
            return False
        return self.identities[key] != binding_identity(binding)  # R-2: the recorded home is not an identity change

    def stale(self):
        """An unsent revision that cannot be sent as it is: the project moved on or the Zeroshot binding changed
        (the only state [n] applies to)."""
        return self.unsent() and (not self.authority.fresh() or self.binding_changed())

    # Readiness ---------------------------------------------------------------

    def items(self, action=None):
        """The readiness items `action` ("plan" / "start" / "resume") needs; None: every item (the home screen asks for "start")."""
        if self.readiness is None:
            return ()
        items = tuple(self.readiness())
        if action is None:
            return items
        needed = set(NEEDS[action])
        if self.authority.fixture_id:
            needed -= set(FIXTURE_SKIPS)
        return tuple(i for i in items if i["id"] in needed)

    def attach_driver(self):
        if self.runs.engine is None and self.driver_factory is not None:
            self.runs.engine = self.driver_factory(self.authority)

    def gate(self, ready=None, action="start"):
        """Readiness right before a model run, only the checks `action` needs. `ready(items)` is the UI's chance to
        let the owner fix what is missing and report True once it passes; without it the answer is the check."""
        if self.readiness is None:
            return Gate(True)
        items = self.items(action)
        if all(i["ok"] for i in items):
            self.attach_driver()
            return Gate(True, items)
        if ready is not None and ready(items) is True:
            self.attach_driver()
            return Gate(True, items)
        return Gate(False, items)

    # Goal and revisions ------------------------------------------------------

    @staticmethod
    def valid_goal(goal):
        return bool(goal) and len(goal) <= GOAL_LIMIT

    def guard(self):
        """The profile's refusal for a new planning action (before any revision, worktree or submission); the
        profile's Status when it is enforced, else None."""
        return self.profile.guard("plan") if self.profile is not None else None

    def begin(self, goal, roles):
        """Save the goal as a new unsent revision; it is kept whatever a readiness check said. With a profile the
        roles are the accepted profile's as they are now, not the caller's older copy."""
        a = self.authority
        status = self.guard()
        if status is not None:
            roles = status.resolved.roles()
        return a.begin(goal, roles, "fixture" if a.fixture_id else "native")

    def renew(self, draft=None):
        """A new unsent revision with the same goal and request; the old one stays as it was. With a profile the
        roles are the accepted profile's as they are now, else the old revision's. An edit revision keeps its draft;
        `draft` (from `edit`) starts a new edit, which has no request text."""
        status = self.guard()
        current = self.authority.current
        roles = status.resolved.roles() if status is not None else current["roles"]
        edit = draft if draft is not None else current.get("draft")
        return self.authority.begin(current["goal"], roles, current["engine"],
                                    feedback="" if draft is not None else current["feedback"], draft=edit)

    def submission(self, ready=None):
        """The only way to the planner: readiness right before it, never for a stale or already sent revision."""
        current = self.authority.current
        if current["status"] != "planning" or current["run_id"] is not None:
            return Submission("sent")
        self.guard()
        gate = self.gate(ready, "plan")
        if not gate.ok:
            return Submission("blocked", gate.items)
        if not self.authority.fresh() or self.binding_changed():
            return Submission("stale")
        return Submission("ready")

    def send(self, ready=None, announce=None):
        """[g] on an unsent revision. A revision that never reached the planner and whose project moved on is not a
        dead end: readiness first, then a new revision of the same goal and roles (`renew`) is prepared on the current
        project and submitted in the same action. `announce(old, new)` hears the renewal. An unconfirmed submission
        goes out again unchanged (`resubmission`); anything else is `submission`: a revision with a receipt is never
        resent."""
        current = self.plan()
        if current is not None and current["status"] == "submission_unknown" and current["run_id"] is None:
            return self.resubmission(ready)
        if not self.stale():
            return self.submission(ready)
        self.guard()
        gate = self.gate(ready, "plan")
        if not gate.ok:
            return Submission("blocked", gate.items)  # nothing is prepared or sent while readiness fails
        if not self.stale():
            return self.submission(ready)  # the owner's fix brought the project back to the baseline
        old = self.authority.current["version"]
        revision = self.renew()
        if announce is not None:
            announce(old, revision)
        result = self.submission(ready)
        return Submission(result.kind, result.items, renewed=True)

    def resubmission(self, ready=None):
        """[g] on a plan whose submission Zeroshot never confirmed (E4): readiness first, then the same frozen
        documents go out again under the same submission key. The engine recognises the key and the documents'
        digest, so a run it already took is answered with its own id and nothing is started twice; the next watch
        slice does the sending (`Watch.step`). Nothing is renewed, so the frozen intent is the one that was sent."""
        self.guard()
        gate = self.gate(ready, "plan")
        if not gate.ok:
            return Submission("blocked", gate.items)
        self.resubmit = self.authority.current["version"]
        return Submission("ready")

    def restart(self, ready=None, announce=None):
        """After a failed or owner-stopped planning: readiness first, then a new revision of the same goal goes to
        the planner. The stopped run keeps its receipt and is never resubmitted."""
        self.guard()
        gate = self.gate(ready, "plan")
        if not gate.ok:
            return Submission("blocked", gate.items)
        revision = self.renew()
        if announce is not None:
            announce(revision)
        result = self.submission(ready)
        return Submission(result.kind, result.items, renewed=True)

    def revise(self, feedback, ready=None):
        """A written revision request (refused while a milestone writer is active), then the planner."""
        status = self.guard()
        self.runs.revise_plan(feedback, status.resolved.roles() if status is not None else None)
        result = self.submission(ready)
        return Submission(result.kind, result.items, renewed=True)

    def edit(self, version, plan, ready=None):
        """An owner edit of the current proposal as a new revision (`plan` is the full edited proposal): the plan run
        presents it unchanged and the critic judges it, so the plan gate checks what the owner changed. Refused,
        with nothing written, unless `version` is the current revision with a proposal and `plan` is a valid,
        in-bounds proposal that differs from it."""
        current = self.authority.current
        if current["version"] != version or current["proposal"] is None:
            raise Blocked("Only the current revision with a proposed plan can be edited.", family="action.refused")
        try:
            check_bounds(validate_proposal(plan))
        except Blocked as error:
            raise Blocked(str(error), family="action.refused") from error
        if canonical(plan) == canonical(current["proposal"]):
            raise Blocked("The edit does not change the plan.", family="action.refused")
        self.renew(draft=plan)
        result = self.submission(ready)
        return Submission(result.kind, result.items, renewed=True)

    def approve(self, version):
        """The approval of the current plan; a gate argued under another configuration than the live one is stale.
        The live digest is Authority's own (the session-bound profile): no caller supplies or can disable it."""
        self.authority.approve(version)

    def override(self, version, reason):
        """The owner approves a plan the critic rejected, with a typed reason; the same live-configuration check as
        `approve`, likewise read from Authority's bound profile. Every UI path comes here; the rule is Authority's."""
        self.authority.override(version, reason)

    def reject(self, version):
        """Declining changes nothing: the proposal stays as it is, nothing is started."""
        current = self.authority.current
        if current["status"] != "proposed" or current["version"] != version:
            raise Blocked("Only the current proposed plan can be declined.", family="action.refused")

    # Observation -------------------------------------------------------------

    def watch(self, emit, slice=PLANNER_SLICE):
        return Watch(self, emit, slice)

    def stop(self):
        """[s] on the plan screen: the owner stops the running planner. The request is saved with its time before
        the native force-stop, so a confirmed stop survives reopening; a refused call leaves the revision as it was
        and raises with the reason, an unanswered one keeps the request (the engine may have taken it) and raises. An earlier confirmed request is never destroyed by a later
        refused retry: its time is kept as saved, and only a request this very call added is removed again. The stop
        itself is concluded by the observation: a revision with a request that ends the run becomes `stopped`, never
        `run_failed` -- also when the run finished successfully before the request reached the engine."""
        a = self.authority
        current = a.current
        if current["status"] not in OBSERVING or not current["run_id"]:
            raise Blocked("Only a running planner can be stopped.", family="action.refused")
        added = current.get("stop") is None
        if added:  # a retry keeps the first confirmed request and its time, never overwriting them
            current["stop"] = {"at": runs.now()}
            a.save()
        try:
            engine = self.engine_factory(current["engine"], self.terminal)
            engine.force_stop(current.get("native_binding"), current["run_id"], a.project)
        except Blocked as error:
            # Only a definite refusal (native answered non-zero) rolls back a request this call added. An unanswered
            # call (timeout, OSError: the cause is set) may have stopped the run, so the request stays and the
            # terminal observation still concludes `stopped`; an earlier request always stays as it was.
            if added and error.__cause__ is None:
                current.pop("stop", None)
                a.save()
            raise
        return "Stop requested."

    def panel(self):
        """Live lines of the planner of the current revision (empty when it has none or is not running): active
        roles, time since it started, since the last new record, and the watcher heartbeat. Read-only."""
        current = self.authority.current
        data = current.get("live")
        if data is None or current["run_id"] is None or current["status"] not in OBSERVING:
            return ()
        return tuple(live.panel_lines(data, data["started"], runs.now(), live.PLANNER_ROLES))

    def steps(self, now=None):
        """The planner graph steps of the current round as plain data (P2a): one `(role word, state, seconds,
        round)` per graph node, in graph order (the planner, then its verifier), nothing drawn.

        `now` is the stamp a running step is measured against (the current one when it is None). `seconds` is
        `now - first` of a running step, `end - first` of a done one, and None of a waiting one. `round` is the
        number of `planner` executions the timeline holds (1 when it holds none), and every node is read from that
        round only: a node the round has not reached yet is `waiting`. A revision with no `steps` (a store written
        before P2a) or without the field at all reads as two waiting nodes of round 1. The nodes are identified by
        their role word (`live.role`, `live.PLANNER_ROLES`), so the verifier of either planner graph generation
        answers for the same step."""
        current = self.plan()
        data = (current or {}).get("live") or {}
        entries = data.get("steps") or []
        now = runs.now() if now is None else now
        planner, verifier = (live.role(name, live.PLANNER_ROLES) for name in ("planner", "plan_verifier"))
        words = [live.role(node, live.PLANNER_ROLES) for node, _, _, _ in entries]
        rounds, seen = [], 0
        for word in words:
            seen += 1 if word == planner else 0
            rounds.append(max(1, seen))
        number = max(1, seen)
        reached = {words[i]: entry for i, entry in enumerate(entries) if rounds[i] == number}
        steps = []
        for word in (planner, verifier):
            step = reached.get(word)
            if step is None:
                steps.append((word, "waiting", None, number))
            elif step[3] is None:
                steps.append((word, "running", live.seconds_between(step[2], now), number))
            else:
                steps.append((word, "done", live.seconds_between(step[2], step[3]), number))
        return tuple(steps)

    def journal(self):
        current = self.authority.state and self.authority.state["revisions"] and self.authority.current
        return tuple((current or {}).get("live", {}).get("journal", ()))

    def log_tail(self, **options):
        """Last lines of the planner run's `zeroshot logs`, with the executable and state root it was submitted
        with. On demand only (the caller runs it on a worker); never parsed."""
        current = self.authority.current
        if not current["run_id"]:
            raise Blocked("The planner has no started run yet.", family="action.refused")
        engine = self.engine_factory(current["engine"], self.terminal)
        return engine.log_tail(current.get("native_binding"), current["run_id"], self.authority.project, **options)

    def failure_cause(self, current):
        if current["version"] not in self.causes:
            try:
                cause = self.engine_factory(current["engine"], self.terminal).failure_cause(self.authority)
            except Blocked:
                cause = None  # tools unavailable: the cause stays unknown
            self.causes[current["version"]] = PLANNER_CAUSE.get(cause, cause)
        return self.causes[current["version"]]

    # Screens -----------------------------------------------------------------

    def view(self):
        """The plan screen of the current revision, whatever its status. Viewing never submits."""
        a, current = self.authority, self.authority.current
        status, version = current["status"], current["version"]
        goal = goal_line(current["goal"], 200, "plan.details")
        if status == "planning" and current["run_id"] is None:
            if not a.fresh():
                return PlanView("stale", version, status, ("", STALE + catalog.tag("plan.stale"), goal),
                                ("start", "renew", "details"), family="plan.stale")
            if self.binding_changed():
                return PlanView("stale", version, status, ("", STALE_BINDING + catalog.tag("plan.stale"), goal),
                                ("start", "renew", "details"), family="plan.stale")
            return PlanView("unsent", version, status, ("", "Plan r%s has not been sent yet." % version, goal),
                            ("start", "details"))
        if status == "submission_unknown":
            return PlanView("unknown", version, status, (
                "", "Plan r%s: the planner submission is unconfirmed — it is unknown whether Zeroshot took it.%s"
                % (version, catalog.tag("submission.unknown")),
                "[g] sends the same documents again with the same key: Zeroshot recognises it and will not start "
                "planning twice. The commands to check are under [i].",
                goal), ("start", "details"), family="submission.unknown")
        if status in OBSERVING or status == "planning":
            lines = ["", "Plan r%s · the planner is working." % version, goal]
            if status == "observation_blocked":
                lines.append("Watching stopped: " + summary(current["diagnostic"]))
            return PlanView("observing", version, status, tuple(lines),
                            ("stop", "watch", "details") + (("tail",) if current["run_id"] else ()))
        if status == "stopped":
            return self.stopped(current, goal)
        if status in FAILED:
            return self.failure(current, goal)
        return self.proposal(current)

    def stopped(self, current, goal):
        """The plan screen of a revision the owner stopped: the cause line names the stop time (HH:MM in the local
        zone, like the chat rows; the stored stamp stays UTC), and the planner is restarted like after a failure,
        never by resubmitting the stopped run."""
        at = local_clock(current["stop"]["at"])
        return PlanView("stopped", current["version"], current["status"],
                        ("", "Plan r%s was stopped by you at %s." % (current["version"], at), goal),
                        ("restart", "details"))

    def failure(self, current, goal):
        cause = self.failure_cause(current)
        version, status = current["version"], current["status"]
        lines = ["", "Plan r%s · planning did not finish." % version, goal]
        actions = ["retry", "revise"]
        if status == "proposal_invalid":
            family = "plan.invalid_proposal"
            lines.append("The planner returned a plan that zplan did not accept: " + summary(current["diagnostic"])
                         + catalog.tag(family))
            lines.append("Next: [r] revise the goal or [g] start again.")
        elif cause == "auth":
            family = PLANNER_FAMILY[cause]
            lines.append("Planning stopped: the service rejected the authorization." + catalog.tag(family))
            lines.append("Next: [l] refresh login, then [g] check readiness.")
            actions.insert(0, "login")
        elif cause == "quota":
            family = PLANNER_FAMILY[cause]
            lines.append("Planning stopped: the service rejected the request because of a limit or quota." + catalog.tag(family))
            lines.append("Next: wait or check the account limits, then [g] start again.")
        elif cause == "network":
            family = PLANNER_FAMILY[cause]
            lines.append("Planning stopped: no connection to the model service." + catalog.tag(family))
            lines.append("Next: check the network, then [g] start again.")
        else:
            family = PLANNER_FAMILY[None]
            stage = {"planner_failed": " at the plan drafting step",
                     "plan_verifier_failed": " at the plan check step",
                     "critic_failed": " at the plan check step"}.get(current["diagnostic"], "")
            lines.append("Planning stopped%s; the cause is unknown — the available logs do not show it.%s"
                         % (stage, catalog.tag(family)))
            lines.append("Next: [i] Zeroshot diagnostic commands, then [g] start again.")
        actions.append("details")
        if current["run_id"]:
            actions.append("tail")
        return PlanView("failed", version, status, tuple(lines), tuple(actions), cause=cause, family=family,
                        home=self.recorded_home(current) if cause == "auth" else None)

    @staticmethod
    def recorded_home(current):
        """The Codex home a revision's native binding recorded, in its own spelling; None for a fixture or invalid one."""
        try:
            return recorded_home(current.get("native_binding"))
        except (ValueError, TypeError, AttributeError):
            return None

    def proposal(self, current):
        """Summary first, then milestones with their tasks and how many checks each has; the rest is [i]."""
        status, version = current["status"], current["version"]
        milestones = current["proposal"]["milestones"]
        tasks = sum(len(s["tasks"]) for m in milestones for s in m["slices"])
        override = current.get("override")
        verdict = {"approved": OVERRIDDEN if override else "approved", "proposed": "checked",
                   "review_exhausted": "the check did not accept it"}[status]
        lines = ["", "Plan r%s · %s · %s · %s" % (version, plural(len(milestones), "milestone", "milestones", "milestones"),
                                                 plural(tasks, "task", "tasks", "tasks"), verdict),
                 goal_line(current["goal"], 200, "plan.requirements")]
        if current["feedback"]:
            lines.append("Revision: " + one_line(current["feedback"], 200))
        for m in milestones:
            lines.append("  %s %s  (after: %s)" % (m["id"], one_line(m["title"], 80), ", ".join(m["depends_on"]) or "—"))
            for s in m["slices"]:
                for t in s["tasks"]:
                    lines.append("    %s %s · %s" % (t["id"], one_line(t["title"], 80),
                                                     plural(len(t["checks"]), "check", "checks", "checks")))
        if status == "review_exhausted" or override:
            lines.append('The plan check did not accept it: "%s"' % one_line(current["evidence"]["findings"], 300))
        if override:
            lines.append('Approved despite the check: "%s"' % override["reason"])
        family = None
        if status == "proposed" and not self.authority.fresh():
            lines.append("The project changed after planning: cannot approve, [r] revise rebuilds the plan."
                         + catalog.tag("plan.stale"))
            family = "plan.stale"
        # a stale proposal cannot be approved: revise (which re-plans) is the way on
        proposed = ("revise", "reject", "requirements") if family else ("approve", "revise", "reject", "requirements")
        actions = {"proposed": proposed,
                   "review_exhausted": ("revise", "restart", "requirements"),
                   "approved": ("revise", "requirements")}[status]
        if status == "review_exhausted" and "execution" in current:  # a version 1 plan has no gate to override
            actions = ("revise", "restart", "override", "requirements")
        findings = one_line(current["evidence"]["findings"], 300) if status == "review_exhausted" else ""
        return PlanView("proposal", version, status, tuple(lines), actions, family=family, findings=findings)

    @staticmethod
    def requirements_lines(current):
        """[i] requirements and checks: the full plan."""
        plan = current["proposal"]
        lines = ["Requirements:"]
        for req in plan["requirements"]:
            lines.append("  %s  %s" % (req["id"], req["text"]))
        for m in plan["milestones"]:
            lines.append("%s %s  (after: %s)" % (m["id"], m["title"], ", ".join(m["depends_on"]) or "—"))
            for s in m["slices"]:
                lines.append("  %s %s  [%s]" % (s["id"], s["title"], ", ".join(s["requirements"])))
                for t in s["tasks"]:
                    lines.append("    %s %s" % (t["id"], t["title"]))
                    for check in t["checks"]:
                        lines.append("      — " + check)
        return lines + Planning.gate_lines(current.get("evidence"), current.get("override"))

    @staticmethod
    def gate_lines(evidence, override=None):
        """The plan gate as the owner reads it, one text in the TUI and the plain UI: the verdict, the rounds used of
        the limit, each round's findings and the planner's reply, and the short configuration digest it was argued
        under. A plan of the first execution version has one verdict and its findings. `override` is the owner's
        record (never part of the evidence): it is shown next to the verdict, which stays."""
        if not evidence:
            return []
        verdict = {"accepted": "accepted", "rejected": "rejected"}
        if evidence.get("gate") != "plan":
            return ["Plan check: %s · %s" % (verdict.get(evidence["verdict"], evidence["verdict"]), evidence["findings"])]
        lines = ["Plan check: %s · rounds %s of %s · configuration %s" % (
            verdict.get(evidence["critic_verdict"], evidence["critic_verdict"]), evidence["rounds_used"],
            evidence["rounds_limit"], evidence["resolved_config_digest"][:12])]
        if override:
            lines.append('  Approved despite the check: "%s"' % override["reason"])
        elif evidence["critic_verdict"] != "accepted" and evidence["rounds_used"] >= evidence["rounds_limit"]:
            lines.append("  Rounds exhausted without agreement: [r] revise or approve anyway with a reason.")
        for item in evidence["discussion"]["rounds"]:
            lines.append("  Round %s · %s: %s" % (item["round"], verdict.get(item["verdict"], item["verdict"]),
                                                  item["findings"]))
            lines.append("    Planner reply: " + item["response"])
        return lines

    @staticmethod
    def planner_commands(current):
        """Ready-to-copy native status/logs of the planner run (the isolated state of its binding); none until the
        run exists. The same lines serve a failed or still running planner in both UIs."""
        binding = current.get("native_binding") or {}
        if current["engine"] != "native" or not current["run_id"] or "state_root" not in binding:
            return []
        root = Path(binding["state_root"])
        prefix = "ZEROSHOT_STATE_DIR=%s ZEROSHOT_CONFIG_DIR=%s %s" % (
            shlex.quote(str(root / "runs")), shlex.quote(str(root / "config")), shlex.quote(binding["executable"]))
        return ["  Zeroshot diagnostics (planner):"] + [
            "    %s %s %s" % (prefix, verb, shlex.quote(current["run_id"])) for verb in ("status", "logs")]

    @staticmethod
    def unknown_lines(current):
        """How to see whether Zeroshot took an unconfirmed submission (the run is never resent)."""
        binding = current.get("native_binding") or {}
        if "state_root" not in binding:
            return []
        root = Path(binding["state_root"])
        return ['Check by hand whether Zeroshot has a run "Terminal roadmap revision %s":' % current["version"],
                "  ZEROSHOT_STATE_DIR=%s ZEROSHOT_CONFIG_DIR=%s %s list" % (
                    shlex.quote(str(root / "runs")), shlex.quote(str(root / "config")), shlex.quote(binding["executable"]))]
