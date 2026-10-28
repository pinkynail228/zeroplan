"""The milestone delivery service shared by the line UI and the full-screen UI.

Every rule that decides what may happen to a milestone attempt lives here: what the home screen offers and which
milestone a key applies to, the preview before a start, bounded observation slices (the only caller of the mutating
poll), stop and its confirmation text, the end-of-run view of every outcome with exactly the owner actions it
allows, the diff, merge and the cleanup an integrated merge leaves behind (A7c), new attempt, answer, accept,
resume and the way back to the plan, and the outcome-first details text. A token (`Token`) names the attempt a
view or modal was built from; an action over a token that
no longer matches is refused with `Changed` and the UI re-renders. The UIs render the answers and call the named
actions; they decide nothing themselves.

No terminal, no Textual: it renders nothing but plain lines and frozen results."""

from dataclasses import dataclass
import copy
import hashlib
import os
from pathlib import Path
import re
from typing import Optional, Tuple

from . import catalog, live, merge_critic, process, task_gate
from .engine import (NativeEngine, ObservationDetached, SliceEnded, gate_owner_rules, gate_prepared,
                     merge_critic_documents, reset_value, task_gate_documents)
from .authority import Blocked, baseline, canonical, decode, git, require
from .planning import OVERRIDDEN, Planning, goal_line, one_line, summary
from .process import ProfileChanged
from .runs import (ACTIVE as RUN_ACTIVE, CONTROL, MAX_RUNS, amendment_text, critic_identity,
                   diagnostic_commands, extended, git_call, now, review_rounds, run_state, Overlap)

def task_gate_roles(config):
    """The gate graph's node bindings from the resolved configuration (R-3): the worker presents the frozen briefs
    and the profile's critic reviews them."""
    return {"proposer": config["roles"]["worker"], "critic": config["roles"]["critic"]}


def critic_roles(resolved):
    """The critic role binding of a resolved configuration (A7b2): the profile's `critic`, which `roles()` exposes
    under its legacy name `plan_verifier`."""
    return {"critic": resolved.roles()["plan_verifier"]}


merge_critic_identity = critic_identity


# C4: `refusal` bounds the whole rendered line at this many characters (`summary`); a block names the first three
# findings inside the room left after the family's prefix, so the outer bound never drops one of them.
REFUSAL_LIMIT = 256
CRITIC_BLOCK_PREFIX = "The merge check stopped the merge: "
CRITIC_FINDINGS = 3


def first_findings(findings, prefix=CRITIC_BLOCK_PREFIX, limit=CRITIC_FINDINGS):
    """The first `limit` findings of a critic's message, one bounded line each, together inside the room `refusal`
    leaves after `prefix` (C4): the outer `REFUSAL_LIMIT`-character bound must not drop a finding."""
    lines = [line for line in str(findings).splitlines() if line.strip()][:limit]
    if not lines:
        return "no findings"
    room = REFUSAL_LIMIT - len(prefix) - 2 * (len(lines) - 1)
    width = max(room // len(lines), 1)
    return "; ".join(one_line(line, width) for line in lines)


def critic_prepared(authority, record):
    """True while `record`'s read-only candidate checkout and its three frozen documents are already on disk and
    still hash to the record's own digests (the critics-directory mirror of `gate_prepared`)."""
    directory = authority.directory / "critics" / record["id"]
    return (directory / "checkout").is_dir() and NativeEngine.critic_documents_ok(directory, record)


DIFF_LIMIT = 4000
# A7b2: one bounded observation slice of a merge critic (seconds). The Controller's merge job passes none and so
# waits at most this long before the merge asks again; the plain CLI passes None to wait for the whole run.
CRITIC_SLICE = 5.0
# A7c: after an integrated merge the attempt's worktree goes, but only while it still holds exactly the merged
# product tree and no ignored path outside zplan's control files (`CONTROL`) or the disposable caches below (at any
# depth); any other ignored leftover keeps the worktree (and its branch) for the owner.
CLEANUP_CACHES = frozenset({"__pycache__", "node_modules", ".pytest_cache", ".mypy_cache", ".ruff_cache"})
# Immediate local feedback of a confirmed action, shown until the engine confirms (the UI owns the state).
PENDING = {"start": "starting %s…", "stop": "stopping %s…", "merge": "merging %s…",
           "attempt": "starting a new attempt of %s…", "resume": "continuing %s…", "check": "checking %s…"}
NEW_ATTEMPT = "The new attempt starts from HEAD %s; earlier unmerged results are not carried over."
EMPTY_ANSWER = "Empty answer: no new attempt was started."
PLAN_STATUS = {"approved": "approved", "proposed": "proposed, waiting for approval",
               "run_failed": "planning stopped", "proposal_invalid": "plan not accepted by zplan",
               "review_exhausted": "the review did not accept the plan", "planning": "not sent",
               "submission_unknown": "submission not confirmed", "observing": "the planner is working",
               "detached": "the planner is working", "observation_blocked": "observation interrupted",
               "stopped": "stopped by you"}
STATE_TEXT = {"waiting": "waiting", "ready": "ready", "running": "running", "needs_owner": "needs an answer",
              "blocked": "blocked", "failed_recoverable": "failed · can continue",
              "failed": "failed · cannot continue", "awaiting_merge": "waiting for merge", "conflict": "conflict",
              "integrated": "merged", "stopped": "stopped", "stopping": "stopping"}
# Active states [g] check reconciles: an unconfirmed submission, a stop not yet confirmed by native.
CHECK = ("unknown", "stopping")
ATTENTION = ("needs_owner", "blocked", "conflict", "awaiting_merge", "failed_recoverable", "failed", "stopped")
RUN_STATUS = {"preparing": "preparing", "submission_unknown": "submission not confirmed", "submitted": "submitted",
              "running": "running", "stopping": "stopping", "resume_pending": "resume not confirmed",
              "finished": "finished", "failed": "failed", "stopped": "stopped"}
OUTCOME = {None: "—", "done": "done", "needs_owner": "needs an answer", "blocked": "blocked",
           "invalid": "invalid result"}
DELIVERY = {"none": "not exported", "exporting": "exporting", "awaiting_merge": "waiting for merge",
            "conflict": "merge conflict", "integrated": "merged"}
# R-5: the cause of a failed attempt and the one catalog line both of its surfaces show. Only catalog text and the
# bounded reset are rendered -- never the raw matched diagnostics, which may carry an HTML body or a credential.
RUN_CAUSE = {"limit": "run.limit", "quota": "run.quota", "auth": "run.auth", "forbidden": "run.forbidden",
             "network": "run.network"}
CAUSE_PREFIX = "Recorded in one of the executions: "
CAUSE_TEXT = {"limit": "Provider limit; check the account limits and try again later.",
              "quota": "The account quota is exhausted; top up the account and try again later.",
              "auth": "The service rejected the authorization; [l] refresh login (`zplan login`) and retry the attempt.",
              "forbidden": "Access denied (403 Forbidden); check the account or region and try again.",
              "network": "No connection to the model service; try again later."}


def cause_line(r):
    """The one catalog line of a failed attempt (R-5), or "" when its cause is unknown.

    The observation names the latest observed execution failure (R-3), never the proven terminal cause; every known
    class carries the "one of the executions" prefix and its own remedy, and a known limit shows its reset when one
    was stored. The stored reset is rendered only while G-2's predicate accepts it (the store writes nothing else);
    a value the predicate refuses leaves the limit line without a reset."""
    cause = (r or {}).get("cause")
    family = RUN_CAUSE.get(cause)
    if family is None:
        return ""
    reset = reset_value((r or {}).get("reset")) if cause == "limit" else None
    text = "provider limit; resets: " + reset if reset else CAUSE_TEXT[cause]
    return CAUSE_PREFIX + text + catalog.tag(family)


# Run state -> catalog family shown on the attempt's end screen.
RUN_FAMILY = {"blocked": "milestone.blocked", "failed": "milestone.failed",
              "failed_recoverable": "milestone.failed_recoverable", "conflict": "milestone.conflict",
              "unknown": "milestone.lost"}
ACTIVE = ("running", "stopping")
# The "back" action of an end screen's menu; awaiting merge and conflict end with [l] later instead.
END_BACK = {"unknown": "unknown.back", "needs_owner": "needs_owner.back", "blocked": "blocked.back",
            "failed_recoverable": "failed_recoverable.back", "failed": "failed.back", "stopped": "stopped.back"}
# End-screen owner actions per run state: (service action, catalog action ID) in menu order; [q] back is the UI's.
END_ACTIONS = {
    "unknown": (("check", "unknown.check"),),
    "awaiting_merge": (("merge", "awaiting_merge.merge"), ("diff", "awaiting_merge.diff"),
                       ("later", "awaiting_merge.later")),
    "conflict": (("merge", "conflict.merge"), ("diff", "conflict.diff"), ("later", "conflict.later")),
    "needs_owner": (("accept", "needs_owner.accept"), ("answer", "needs_owner.answer"),
                    ("leave", "needs_owner.stop")),
    "blocked": (("answer", "blocked.answer"), ("plan", "blocked.plan")),
    "failed_recoverable": (("resume", "failed_recoverable.resume"),
                          ("new_attempt", "failed_recoverable.new_attempt"), ("plan", "failed_recoverable.plan")),
    "failed": (("new_attempt", "failed.new_attempt"), ("plan", "failed.plan")),
    "stopped": (("new_attempt", "stopped.new_attempt"), ("plan", "stopped.plan")),
}


INTERNAL = re.compile(r"\b[a-z]+(?:[A-Z][a-z]+)+=\S*|\b\d+ open\b|; manifest: .*$")


def full_line(ids, slots):
    """The refusal a start, resume or new attempt of a ready or failed milestone reads while every parallel slot is
    taken (C2): the slot count and the active milestones. None with the single slot, whose own line `pick` and the
    panel keep unchanged, byte for byte."""
    if slots <= 1:
        return None
    return "All %s slots are busy (%s): a new start, a continuation and a new attempt wait. [w] watch, " \
           "[g] check." % (slots, ", ".join(ids))


def plain(text):
    """Model text for the normal flow: quoted as is, minus internal tokens (acceptanceVerdict=…, "4 open", the
    manifest problem); the full diagnostic stays under [i]."""
    text = INTERNAL.sub("", summary(text))
    return re.sub(r"(?:\s*[;,]\s*)+(?=[;,]|$)", "", re.sub(r"^\s*[;,]\s*", "", text)).strip(" ;,")


def short(sha):
    return sha[:7] if sha else "—"


def of_milestones(count):
    """"stage" after "N/M" (a fraction of the whole): "1/1 stage", "0/2 stages"."""
    return "stage" if count == 1 else "stages"


def refusal(error):
    """One bounded line for a refusal or failure plus its stable catalog code ([code: ...]); an error without a
    family is shown as unknown_error."""
    return summary(error) + catalog.tag(error)


class Changed(Blocked):
    """The attempt, plan revision or delivery a view was built from is no longer the current one.

    `what` is the reason on its own (`plan revised` / `another attempt started` / `attempt progressed`), kept
    apart from the full owner-facing message: a chat draft's refusal names exactly that reason next to
    «draft outdated», and the screen that raised the error still shows the whole message."""
    family = "action.refused"

    def __init__(self, what="the attempt or plan changed"):
        self.what = what
        super().__init__("The state changed (%s): the screen was refreshed; check and repeat the action." % what)


# Results -------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Token:
    """The identity of an attempt as a view saw it: a modal acts only while this is still the latest attempt."""
    milestone: str
    plan_revision: int
    attempt: int
    run_id: Optional[str]
    status: str
    outcome: Optional[str]
    delivery: str

    @classmethod
    def of(cls, r):
        return cls(r["milestone"], r["plan_revision"], r["attempt"], r["run_id"], r["status"], r["outcome"],
                   extended(r)["delivery"])


@dataclass(frozen=True)
class Row:
    """One milestone of the approved plan: `text` is the state exactly as the overview line shows it."""
    id: str
    title: str
    state: str
    text: str
    token: Optional[Token] = None  # the latest attempt of the current revision (None: not started / carried)
    carried: bool = False
    waiting: Tuple[str, ...] = ()
    commit: Optional[str] = None  # the merge commit once integrated

    @property
    def startable(self):
        return self.state == "ready"

    @property
    def active(self):
        return self.state in ACTIVE


@dataclass(frozen=True)
class Home:
    """The plan part of the home screen: the lines as printed, the catalog action IDs of its menu, the rows."""
    kind: str  # none | pending | approved
    lines: Tuple[str, ...]
    ids: Tuple[str, ...]
    rows: Tuple[Row, ...] = ()
    focus: Optional[Row] = None
    g: Optional[str] = None  # the catalog action [g] has here (home.start / resume / attempt / check) or None
    g_milestone: Optional[str] = None  # the milestone [g] acts on
    busy: Optional[str] = None  # the first active milestone when every parallel slot is taken (else None)
    panel: Tuple[str, ...] = ()  # live lines of the attempt (or planner) under observation
    journal: Tuple[str, ...] = ()  # stored journal entries of the observed attempt, oldest first (nothing rendered yet)
    flow: Optional[dict] = None  # structured facts of the active attempt for the "Now" drawing (F1); None without one
    slots: int = 1  # how many attempts the live profile admits side by side (C1); 1 without an accepted autonomy


@dataclass(frozen=True)
class Pick:
    """Which milestone a plain key applies to and what to do: follow (an attempt to watch or open), check,
    start, or message (nothing to do; `text` says why)."""
    kind: str
    row: Optional[Row] = None
    text: str = ""


@dataclass(frozen=True)
class Preview:
    """What a start would create, shown before the owner confirms; carries the revision and attempt it was
    computed for so a confirmation of a changed situation is refused."""
    milestone: str
    title: str
    plan_revision: int
    attempt: int
    lines: Tuple[str, ...]
    profile: str = ""  # digest of the resolved process profile the preview was built on ("": none enforced)


@dataclass(frozen=True)
class Slice:
    """One observation slice: new display lines and the cursor to pass to the next slice."""
    events: Tuple[str, ...]
    mark: object
    active: bool


@dataclass(frozen=True)
class EndAction:
    name: str  # service action: merge diff later accept answer leave plan resume new_attempt check
    id: str  # catalog action ID of the line UI's menu
    args: Tuple[str, ...] = ()


@dataclass(frozen=True)
class EndView:
    """The end-of-run screen of one attempt, frozen: heading, status line and body exactly as the plain end
    screen prints them, and the only owner actions it allows."""
    state: str
    token: Token
    milestone: str
    title: str
    heading: str
    status: str
    body: Tuple[str, ...]
    actions: Tuple[EndAction, ...]
    family: Optional[str] = None
    attempt: int = 1
    branch: str = ""  # destination branch
    question: str = ""  # the merge confirmation of an awaiting/conflict attempt
    journal: Tuple[str, ...] = ()  # the attempt's stored journal entries, oldest first, at most JOURNAL_LIMIT

    @property
    def back(self):
        return END_BACK.get(self.state)

    @property
    def names(self):
        return tuple(a.name for a in self.actions)

    @property
    def lines(self):
        return (self.heading, self.status) + self.body


@dataclass(frozen=True)
class Merge:
    """The verdict of a merge: `stay` keeps the end view open (conflict or refusal that left the record)."""
    kind: str  # integrated | conflict | overlap | refused | open
    line: str
    stay: bool
    paths: tuple = ()  # overlap: the files of the owner's tree in the way of the landing


def plan_lines(authority, plan, runs):
    """The plan record in English, one language for every label. Claims that stopped being true after a merge
    (the repository changed since approval, nothing implemented) are dropped; `runs` are the attempts of this
    revision."""
    a = authority
    merged = any(extended(r)["delivery"] == "integrated" for r in runs)
    status = OVERRIDDEN if plan.get("override") else PLAN_STATUS.get(plan["status"], plan["status"])
    lines = ["Plan r%s · %s" % (plan["version"], status),
             "Goal: " + plan["goal"]]
    if plan["feedback"]:
        lines.append("Revision: " + plan["feedback"])
    if a.fresh():
        lines.append("Project: matches the plan baseline")
    elif plan["status"] == "approved":
        if not merged:
            lines.append("The repository changed after approval (plan baseline digest %s, now %s); a plan revision rebuilds it on the current state."
                         % (plan["baseline"][:12], baseline(a.project)[:12]))
    else:
        lines.append("Project: CHANGED — the plan needs revising")
    lines.append("Roles: " + "; ".join("%s=%s/%s" % (role, v["model"], v["effort"]) for role, v in plan["roles"].items()))
    evidence = plan.get("evidence")
    if evidence:
        lines += Planning.gate_lines(evidence, plan.get("override"))
        if evidence["kind"] == "fixture":
            lines.append("Training plan: demonstration only; a real run is not allowed.")
    proposal = plan["proposal"]
    if not proposal:
        lines.append("The intent is saved; the proposal is not accepted yet.")
        return lines
    lines.append("Requirements:")
    for req in proposal["requirements"]:
        lines.append("  %s — %s" % (req["id"], req["text"]))
    for m in proposal["milestones"]:
        lines.append("%s — %s · after: %s" % (m["id"], m["title"], ", ".join(m["depends_on"]) or "—"))
        for s in m["slices"]:
            lines.append("  %s — %s · covers %s" % (s["id"], s["title"], ", ".join(s["requirements"])))
            for task in s["tasks"]:
                lines.append("    %s — %s" % (task["id"], task["title"]))
                lines.append("      checks: " + "; ".join(task["checks"]))
    if not runs:
        lines.append("Nothing has been implemented; this is only a plan.")
    return lines


# Service ---------------------------------------------------------------------------------------------------------

class Delivery:
    """Milestone decisions over one locked Authority and its MilestoneRuns."""

    def __init__(self, authority, runs, planning):
        self.authority, self.runs, self.planning = authority, runs, planning

    # Reading -----------------------------------------------------------------

    def plan(self):
        a = self.authority
        return a.current if a.state and a.state["revisions"] else None

    def title(self, milestone_id):
        plan = self.plan()
        found = next((m for m in plan["proposal"]["milestones"] if m["id"] == milestone_id), None) if plan else None
        return found["title"] if found else milestone_id

    def latest(self, milestone_id):
        """The milestone's record under the current approved revision -- the one place the row, `resolve`,
        `latest_only`, `journal_sections` and `plan_section` read: its latest attempt of this revision, a carried
        integrated result, or the carried attempt whose result is still to deliver (`runs.current_record`)."""
        return self.runs.current_record(milestone_id)

    @staticmethod
    def state_text(item):
        state, r = item["state"], item["record"]
        line = cause_line(r) if state in ("failed", "failed_recoverable") else ""
        if state == "waiting":
            return "waiting for " + ", ".join(item["waiting"])
        if state == "running":
            parts = ["running"]
            if item["task"]:
                parts.append("task %s/%s (%s)" % item["task"])
            if item["phase"]:
                parts.append(item["phase"])
            return " · ".join(parts)
        if state == "unknown":
            return "submission status unknown" if r["status"] == "submission_unknown" else "interrupted · needs a check"
        if state == "integrated":
            x = extended(r)
            text = "merged %s" % short(x["integration"]["commit"] or x["result"]["commit"])
        else:
            text = STATE_TEXT[state] + (" · " + line if line else "")
        # A carried record names its revision: the milestone's work of an older, still-unchanged revision.
        return text + (" (r%s)" % r["plan_revision"] if item.get("carried") else "")

    @staticmethod
    def overview_lines(plan, items, text=None):
        """The approved plan as plain lines (summary, one per milestone): shared by the line UI and the TUI panel."""
        text = text or Delivery.state_text
        merged = sum(i["state"] == "integrated" for i in items)
        lines = ["Plan r%s · %s · %s/%s %s merged" % (plan["version"], OVERRIDDEN if plan.get("override") else "approved",
                                                    merged, len(items), of_milestones(len(items)))]
        width = min(40, max(len(i["title"]) for i in items))
        for i in items:
            glyph = {"integrated": "✓", "running": "▶", "stopping": "▶"}.get(i["state"], "·")
            lines.append("  %s %s %s  %s" % (glyph, i["id"], one_line(i["title"], width).ljust(width), text(i)))
        return lines

    @staticmethod
    def focus_item(items):
        for states in (("running",) + CHECK, ATTENTION, ("ready",)):
            found = next((i for i in items if i["state"] in states), None)
            if found is not None:
                return found
        return None

    def row(self, item):
        r = item["record"]
        # A carried attempt keeps its token: its finish/export and merge stay reachable from the row; a carried
        # integrated result has nothing to act on and no token (as before).
        record = r is not None and (not item["carried"] or item["state"] in ("awaiting_merge", "conflict"))
        commit = None
        if item["state"] == "integrated":
            x = extended(r)
            commit = x["integration"]["commit"] or x["result"]["commit"]
        return Row(item["id"], item["title"], item["state"], self.state_text(item), Token.of(r) if record else None,
                   item["carried"], tuple(item["waiting"]), commit)

    def rows(self, items=None):
        return tuple(self.row(i) for i in (self.runs.overview() if items is None else items))

    @staticmethod
    def busy(items, slots=1):
        """The first active milestone (running, stopping, unknown) while the active ones number `slots` or more, or
        None: it names the slot that is holding the next start, resume or new attempt back; below `slots` the free
        slots are simply used. With the single slot of today (`slots` 1) it is exactly the one busy milestone, so
        every single-slot message and behaviour stays."""
        active = [i for i in items if i["state"] in ACTIVE + ("unknown",)]
        return active[0] if len(active) >= slots else None

    @staticmethod
    def g_item(items):
        """The milestone [g] acts on: a state to reconcile first, then a failed/stopped attempt, then a ready one."""
        for states in (CHECK, ("failed_recoverable", "failed", "stopped"), ("ready",)):
            found = next((i for i in items if i["state"] in states), None)
            if found is not None:
                return found
        return None

    def g_id(self, items, slots=None):
        """The catalog action ID [g] has on home, or None when it has nothing to do. `slots` is the profile's own
        bound when the caller already read it (one read per refresh), else it is read here."""
        found = self.g_item(items)
        if found is None:
            return None
        state = found["state"]
        if state in CHECK:
            return "home.check"
        if state == "failed_recoverable":
            return "home.resume"
        if state in ("failed", "stopped"):
            return "home.attempt"
        slots = self.slots() if slots is None else slots
        return None if self.busy(items, slots) is not None else "home.start"

    @staticmethod
    def tail_item(items, target=None):
        """The milestone whose activity tail [e] shows: `target`, else the first running or failed attempt."""
        for i in items:
            ok = (i["record"] is not None and not i["carried"]
                  and i["state"] in ("running", "stopping", "failed_recoverable", "failed"))
            if ok and (target is None or i["id"] == target):
                return i
        return None

    @staticmethod
    def next_step(item):
        """"\"Next:\" for a milestone from the same table as its end screen (END_ACTIONS): the key that does it and
        what it does. [g] performs resume / new attempt / check / start directly; [o] opens the end screen whose
        keys are the listed actions."""
        state, name = item["state"], item["id"]
        if state == "running":
            return "[w] watch %s" % name
        if state in CHECK:
            return "[g] check %s — reconcile with Zeroshot without resubmitting" % name
        if state == "ready":
            return "[g] start %s" % name
        actions = END_ACTIONS.get(state)
        if actions is None:
            return "[o] open %s" % name
        if state == "failed_recoverable":
            return "[g] continue %s — the same attempt in its worktree; [o] open — a new attempt" % name
        if state in ("failed", "stopped"):
            return "[g] new attempt %s — from the current HEAD" % name
        branch = (item["record"] or {}).get("destination", {}).get("branch", "")
        labels = [catalog.label(action_id, branch) if "%s" in catalog.action(action_id).label
                  else catalog.label(action_id) for _, action_id in actions]
        return "[o] open %s — %s" % (name, ", ".join(labels))

    def home(self):
        """The plan part of home (the TUI panel shows exactly these lines). Refresh only detects integration."""
        plan = self.plan()
        if plan is None:
            return Home("none", ("No plan.", "Next: [p] plan — describe the goal"),
                        ("home.plan", "home.settings", "home.quit"))
        lines = [goal_line(plan["goal"], 100, "home.details")]
        if plan["status"] != "approved":
            lines.append("Plan r%s · %s" % (plan["version"], PLAN_STATUS[plan["status"]]))
            lines.append("Next: [p] plan — %s" % ("approve or revise" if plan["status"] == "proposed" else "open"))
            ids = ["home.plan", "home.revise", "home.settings", "home.details", "home.quit"]
            if plan["run_id"] and plan["status"] in ("observing", "detached", "observation_blocked", "run_failed"):
                ids.insert(1, "home.tail")
            return Home("pending", tuple(lines), tuple(ids), panel=self.planner_panel())
        items = self.runs.overview()
        lines += self.overview_lines(plan, items)
        found = self.focus_item(items)
        slots = self.slots()
        ids = []
        if any(i["state"] == "running" for i in items):
            ids.append("home.watch")
        g = self.g_id(items, slots)
        if g:
            ids.append(g)
        if any(i["state"] in ATTENTION for i in items):
            ids.append("home.open")
        if self.tail_item(items) is not None:
            ids.append("home.tail")
        if found is None:
            lines.append("Next: all stages are merged; [r] revise — a new goal or a revision")
        else:
            lines.append("Next: " + self.next_step(found))
        ids += ["home.plan", "home.revise", "home.settings", "home.details", "home.quit"]
        active = next((i for i in items if i["state"] in ACTIVE and i["record"] is not None), None)
        busy = self.busy(items, slots)
        g_item = self.g_item(items)
        observed = active["record"] if active else (found["record"] if found else None)
        journal = self.journal(observed) if observed is not None else ()
        panel, flow = self.panel_flow(active["record"]) if active else ((), None)
        return Home("approved", tuple(lines), tuple(ids), tuple(self.row(i) for i in items),
                    self.row(found) if found else None, g, g_item["id"] if g_item else None,
                    busy["id"] if busy else None, panel, flow=flow, journal=journal, slots=slots)

    @staticmethod
    def next_view(home):
        """The key Enter follows on home: only a view, never a start or a check."""
        if home.kind != "approved":
            return "p"
        if home.focus is None:
            return ""
        return {"running": "w", "unknown": "", "stopping": "", "ready": ""}.get(home.focus.state, "o")

    def pick(self, key, target, home):
        """The milestone a plain home key (w/g/o) applies to: `target` or the first one in a matching state, else
        the focus."""
        items = self.runs.overview()
        if key == "g":
            found = self.g_item(items)
            default = found["id"] if found else None
        else:
            wanted = {"w": ("running",), "o": ATTENTION}[key]
            default = next((i["id"] for i in items if i["state"] in wanted), None)
        focus = home.focus.id if home.focus else None
        milestone_id = target or default or focus
        item = next((i for i in items if i["id"] == milestone_id), None)
        if item is None:
            return Pick("message", None, "Stage %s is not in the plan." % milestone_id)
        row = self.row(item)
        if key == "w":
            if item["state"] != "running":
                return Pick("message", row, "%s is not running now." % milestone_id)
            return Pick("follow", row)
        if key == "g":
            state = item["state"]
            if state in CHECK:
                return Pick("check", row)
            slots = self.slots()  # the profile's own bound, read once for the busy hint and the refusal
            busy = self.busy(items, slots)
            if state in ("ready", "failed_recoverable", "failed", "stopped") and busy is not None:
                full = full_line([i["id"] for i in items if i["state"] in ACTIVE + ("unknown",)], slots)
                return Pick("message", row, full or (
                    "%s is busy now (%s): a new start, a continuation and a new attempt wait. [w] watch, "
                    "[g] check." % (busy["id"], self.state_text(busy))))
            if state == "ready":
                return Pick("start", row)
            if state == "failed_recoverable":
                return Pick("resume", row)
            if state in ("failed", "stopped"):
                return Pick("attempt", row)
            if state == "waiting":
                return Pick("start", row)
            return Pick("message", row, "%s: %s. Open: [o] %s" % (milestone_id, self.state_text(item), milestone_id))
        if row.token is None:
            return Pick("message", row, "%s: %s." % (milestone_id, self.state_text(item)))
        return Pick("follow", row)

    def resolve(self, token, exact=True):
        """The attempt of the token's milestone the current revision selects, or Changed when the plan revision,
        the attempt, the run or (exact) its status, outcome and delivery are no longer the ones the view was built
        from. A token of the carried attempt (an older revision) is accepted while that attempt is the selected
        one; every other older revision's token stays `plan revised`."""
        plan = self.plan()
        if plan is None:
            raise Changed("plan revised")
        r = self.latest(token.milestone)
        same = (r is not None and r["plan_revision"] == token.plan_revision and r["attempt"] == token.attempt
                and r["run_id"] == token.run_id)
        if plan["version"] != token.plan_revision and not same:
            raise Changed("plan revised")
        if r is None or r["attempt"] != token.attempt or r["run_id"] != token.run_id:
            raise Changed("another attempt started")
        if exact and Token.of(r) != token:
            raise Changed("attempt progressed")
        return r

    # Start -------------------------------------------------------------------

    def guard(self, kind):
        """The process profile's refusal for a new attempt ("milestone"), plan revision ("plan") or merge, before
        any side effect; its Status when a profile is enforced, else None."""
        profile = self.planning.profile
        return profile.guard(kind) if profile is not None else None

    def slots(self):
        """How many milestone attempts the live profile admits side by side (C1): `autonomy.max_runs` of the accepted
        profile, capped by the engine's own `runs.MAX_RUNS` (the hard cap `admit` enforces). 1 when the profile has
        no `autonomy` (preset /1), is not accepted or cannot be read -- today's single slot, so every single-slot
        behaviour and message stays. Reads the bound `Authority.profile` with `status(write=False)`, like
        `task_gate_admission`, so a refusal never writes the store."""
        profile = getattr(self.authority, "profile", None)
        try:
            status = profile.status(write=False) if profile is not None else None
        except (Blocked, OSError, ValueError):
            status = None  # a corrupt or deleted store reads as "no autonomy": today's single slot, never a crash
        resolved = getattr(status, "resolved", None)
        value = None
        if resolved is not None and getattr(status, "state", None) == "accepted":
            value = resolved.config.get("autonomy", {}).get("max_runs")
        return min(value, MAX_RUNS) if isinstance(value, int) and not isinstance(value, bool) else 1

    def admission(self, exclude=None):
        """The one service guard every path that creates an attempt runs on the worker, before any side effect
        (C3): refused with `action.refused` when the active attempt records -- `runs.ACTIVE`, `exclude` left out --
        already number the live profile's `slots()`. The screen's `busy` is only a hint; below the cap the action
        reaches the service and `runs.admit`'s own refusal (the same milestone, an overlapping write-set) is what
        the action shows."""
        slots = self.slots()
        active = [r for r in self.runs.runs if r["status"] in RUN_ACTIVE and r is not exclude]
        require(len(active) < slots,
                "The profile's limit of parallel milestone runs (%s) is reached: %s are already running." % (slots, len(active)),
                family="action.refused")

    def preview(self, milestone_id, roles):
        status = self.guard("milestone")
        if status is not None:
            roles = status.resolved.roles()  # the accepted profile as it is now, not the caller's older copy
        p = self.runs.preview(milestone_id, roles)
        limits = p["limits"]
        lines = ["Start %s · %s (attempt %s)" % (milestone_id, p["milestone"]["title"], p["attempt"]),
                 "  Worktree:        " + p["worktree"],
                 "  Work branch:     " + p["branch"],
                 "  Result branch:   " + p["result"],
                 "  Merge into:      %s (from HEAD %s)" % (p["destination"] or "detached HEAD", short(p["base"])),
                 "  Roles:           " + " · ".join("%s %s/%s" % (role, b["model"], b["effort"])
                                                    for role, b in p["roles"].items()),
                 "  Limits:          %s tasks (+ up to %s new), %s repairs per task, %s final repairs" % (
                     p["tasks"], limits["max_additions"], limits["task_iterations"] - 1, limits["final_repairs"])]
        return Preview(milestone_id, p["milestone"]["title"], self.authority.current["version"], p["attempt"],
                       tuple(lines), status.digest if status is not None else "")

    @staticmethod
    def start_question(preview):
        return "Start %s?" % preview.milestone

    @staticmethod
    def start_text(preview):
        """The TUI confirmation: the milestone, the plan revision and the attempt it would create."""
        return "Start %s · %s?\nPlan r%s · attempt %s. A worktree and a result branch will be created; " \
               "the run goes on in the background and survives leaving zplan." % (
                   preview.milestone, preview.title, preview.plan_revision, preview.attempt)

    @staticmethod
    def stop_text(token):
        """The TUI confirmation of a stop: it ends this attempt only, never the plan or anything merged."""
        return "Stop the run %s (attempt %s)?\nThe attempt's unfinished work will not be accepted; the plan and what is " \
               "already merged do not change. You can start a new attempt later." % (token.milestone, token.attempt)

    # Task gate (G2-start) ----------------------------------------------------

    def task_gates(self, milestone_id):
        """The task-gate records of the current revision's milestone, oldest first; a read-only list (R-2). The copy
        is a serialization round trip, so a record holding a refused output with a deep nesting -- one the store can
        write but `copy.deepcopy` cannot walk (R-4/R-5) -- is still listable."""
        plan = self.plan()
        if plan is None:
            return []
        return [decode(canonical(record)) for record in self.authority.state.get("gates", [])
                if record["plan_revision"] == plan["version"] and record["milestone"] == milestone_id]

    def task_gate_admission(self, milestone_id):
        """(status, plan) a task gate may run under, or a refusal (R-4). The live configuration comes from the bound
        `Authority.profile` via `status(write=False)` -- never from a caller and never from the planning service, so
        an unbound profile is `action.refused` whatever `Planning` holds. The profile's own refusal (never, missing,
        malformed) is raised before any plan or milestone condition, and nothing is written on a refusal."""
        profile = self.authority.profile
        require(profile is not None, "The process profile is not bound: the task check is not allowed.", family="action.refused")
        status = profile.status(write=False)
        if status.state == "never":
            raise Blocked("The project's process profile is not accepted yet: accept or postpone it.", family="process.pending")
        if status.state == "missing":
            raise Blocked(status.problem, family="process.missing")
        if status.state == "malformed":
            raise Blocked(status.problem, family="process.invalid")
        plan = self.plan()
        require(plan is not None and plan["status"] == "approved"
                and plan["approval"] == self.authority.approval_identity(plan),
                "Tasks can be checked only for an approved plan revision.", family="action.refused")
        require(any(m["id"] == milestone_id for m in plan["proposal"]["milestones"]),
                "Milestone %s is not in the approved plan." % milestone_id, family="action.refused")
        require(status.resolved is not None and status.resolved.config["gates"]["task"] == "required",
                "The task check is turned off in %s." % process.PROFILE_FILE, family="action.refused")
        return status, plan

    def task_gate_engine(self, plan):
        """The engine environment that dispatches the gate (R-3): the same factory the plan gate uses. A native
        record's own binding decides the executable, state root and home inside `gate_run`."""
        return self.planning.engine_factory(plan["engine"], getattr(self.planning, "terminal", None))

    def task_gate_documents(self, record, rules=None):
        """The three frozen documents of `record` (R-4), built from its own frozen configuration and stored owner
        context. `rules` are the `(path, sha256)` pairs of the one resolved configuration the record is frozen on
        (`gate_owner_rules` re-reads each file and checks it against its pair). A rebuild passes none: the rule files
        are then read now and must still resolve to the record's own `resolved_config_digest`, so a rule changed
        after the record was created refuses here rather than reaching the documents under another configuration."""
        config = record["config"]
        if rules is None:
            rules = process.read_rules(self.authority.project, config["rules"]) if config["rules"] else ()
            require(process.config_digest(config, rules) == record["identity"]["resolved_config_digest"],
                    "The task check rules changed; resubmission is not allowed.",
                    family="engine.intent_changed")
        manifest = self.runs.gate_manifest(record["milestone"], record["plan_revision"], record["context"])
        return task_gate_documents(record["rounds_limit"], task_gate_roles(config),
                                   {"artifact": task_gate.artifact(manifest), "head": record["identity"]["head"],
                                    "owner_rules": gate_owner_rules(self.authority.project, rules)})

    def task_gate_recovery(self, record):
        """The documents a recovery passes to `gate_run`: None while the record already has a preparation on disk
        (A-4l), so `gate_prepare` reuses its frozen files; the rebuild of a never-prepared record passes the three
        documents built from its own frozen configuration -- rules that no longer resolve to the record's
        `resolved_config_digest` refuse (`engine.intent_changed`) rather than freeze another configuration."""
        return None if record["run_id"] is not None or gate_prepared(self.authority, record) \
            else self.task_gate_documents(record)

    def task_gate_new(self, milestone_id, context, plan, status, engine):
        """The new gate record and the documents it froze (R-4), persisted in `preparing` before any side effect. The
        identity, the frozen configuration and the documents all come from the one resolved configuration of this
        dispatch, so a rule changed after the resolution refuses in `gate_owner_rules` instead of freezing a config
        digest that describes other documents. The record stores the documents' digests, never their values."""
        config, rules = status.resolved.config, status.resolved.rules
        manifest = self.runs.gate_manifest(milestone_id, plan["version"], context)
        head = git(self.authority.project, "rev-parse", "HEAD").decode().strip()
        record = task_gate.record(plan["version"], plan["approval"], milestone_id, context,
                                  task_gate.identity(task_gate.artifact_digest(manifest), status.digest, head),
                                  config, {}, engine.gate_binding(self.authority))
        documents = self.task_gate_documents(record, rules)
        record["documents"] = task_gate.freezes(documents)
        self.authority.state.setdefault("gates", []).append(record)
        try:
            self.authority.save()
        except BaseException:
            # R-2/A-4l: a save publishes the file before its directory fsync, so a failure there can leave the record
            # durable. Roll back only an append that never reached the file; a published record stays in memory, so a
            # retry recovers it instead of appending a second one over the first.
            if not self.task_gate_published(record["id"]):
                self.authority.state["gates"].pop()
            raise
        return record, documents

    def task_gate_published(self, record_id):
        """True while `record_id` is already visible in the store file, i.e. a failed `save` published it. A file the
        reader cannot parse is not this record's, so the append is treated as unpublished (R-2)."""
        try:
            state = decode(self.authority.path.read_bytes().decode("utf-8"))
        except (OSError, UnicodeError, Blocked, ValueError, TypeError):
            return False
        entries = state.get("gates") if isinstance(state, dict) else None
        return isinstance(entries, list) and any(
            isinstance(entry, dict) and entry.get("id") == record_id for entry in entries)

    def task_gate_latest(self, plan, milestone_id):
        return next((record for record in reversed(self.authority.state.get("gates", []))
                     if record["plan_revision"] == plan["version"] and record["milestone"] == milestone_id), None)

    def run_task_gate(self, milestone_id, context=None, progress=lambda _: None, slice=None):
        """Run (or resume) the task gate of `milestone_id` and return its record (R-4).

        The newest record for (revision, milestone) decides: a nonterminal one is recovered or observed as it is,
        keeping its id (an unconfirmed submission still refuses with `submission.unknown`); otherwise a new record is
        created and dispatched. A live config, rules or HEAD change never turns an observation into a new dispatch:
        an existing record is selected before any admission."""
        return self.task_gate_go(milestone_id, context, progress, slice, rerun=False)

    def rerun_task_gate(self, milestone_id, context=None, progress=lambda _: None, slice=None):
        """The explicit rerun (R-4): it refuses while the newest record is nonterminal; otherwise it appends a new
        record and never touches an earlier one."""
        return self.task_gate_go(milestone_id, context, progress, slice, rerun=True)

    def task_gate_go(self, milestone_id, context, progress, slice, rerun):
        """Recover or observe the newest nonterminal record, else create and dispatch a new one after admission."""
        plan = self.plan()
        newest = None if plan is None else self.task_gate_latest(plan, milestone_id)
        if newest is not None and not task_gate.terminal(newest["status"]):
            if rerun:
                raise Blocked("The task check %s is not finished yet (%s); wait for it to end."
                              % (milestone_id, newest["status"]), family="action.refused")
            if newest["status"] == "submission_unknown":
                raise Blocked("The task check submission is not confirmed; resubmission is not allowed.",
                              family="submission.unknown")
            documents = self.task_gate_recovery(newest)
            return self.task_gate_engine(plan).gate_run(self.authority, newest, documents, progress, slice)
        status, plan = self.task_gate_admission(milestone_id)
        engine = self.task_gate_engine(plan)
        record, documents = self.task_gate_new(milestone_id, context, plan, status, engine)
        return engine.gate_run(self.authority, record, documents, progress, slice)

    def start(self, preview, roles):
        """The confirmed start; refused when the plan revision or the attempt number moved since the preview, or
        the process profile changed (the owner then confirms the preview shown again)."""
        status = self.guard("milestone")
        if status is not None:
            if preview.profile and status.digest != preview.profile:
                raise ProfileChanged("The process profile changed after the preview: check the new values and "
                                     "confirm the start again.")
            roles = status.resolved.roles()
        plan = self.plan()
        if plan is None or plan["version"] != preview.plan_revision:
            raise Changed("plan revised")
        mine = [r for r in self.runs.runs if r["plan_revision"] == preview.plan_revision
                and r["milestone"] == preview.milestone and r["predecessor"] is None]
        if len(mine) + 1 != preview.attempt:
            raise Changed("attempt %s is already started" % (len(mine)))
        self.admission()  # the profile's cap of parallel attempts, before the attempt exists
        return self.runs.start(preview.milestone, preview.plan_revision, roles)

    # Observation and stop ------------------------------------------------------

    def now_line(self, r):
        """`now: …` of an active attempt, or None when nothing is known yet."""
        now = self.runs.activity_now(r)
        if not (now["task"] or now["phase"]):
            return None
        return "  now: %s" % " · ".join(
            ([("task %s/%s (%s)" % now["task"])] if now["task"] else []) + ([now["phase"]] if now["phase"] else []))

    def step(self, r, mark=None, seconds=None):
        """One bounded observation slice: the only caller of the mutating poll. `active` is False once the
        attempt is no longer submitted/running/stopping."""
        if seconds is None:
            events, mark = self.runs.poll(r, mark)
        else:
            events, mark = self.runs.poll(r, mark, seconds)
        return Slice(tuple(events), mark, r["status"] in {"submitted", "running", "stopping"})

    # Live run visibility --------------------------------------------------------

    @staticmethod
    def pending_text(kind, milestone):
        return PENDING[kind] % milestone

    def panel(self, r):
        """Live lines of an active attempt: active roles (parallel ones all shown), the round the task under review
        is in out of the review loop's bound, time since the attempt started, since the last new record, and the
        watcher heartbeat (or that observation was interrupted). Read-only: the times were stored by the observing
        services; the bound is the attempt's own revision (`runs.review_rounds`), the same value the submitted graph
        was built with, and no new store read is made."""
        return self.panel_flow(r)[0]

    def flow(self, r):
        """The active attempt's facts as plain data for the "Now" drawing (F1): `live.flow` of the same record and
        the same clock reading as `panel`, over the attempt's own revision's review bound."""
        return self.panel_flow(r)[1]

    def panel_flow(self, r):
        """The live panel lines and the structured flow of attempt `r`, both from one clock reading so the two never
        disagree; read-only, with no new store read."""
        data = r.get("live")
        revision = self.authority.state["revisions"][r["plan_revision"] - 1]
        at = now()
        rounds = review_rounds(revision)
        lines = live.panel_lines(data, r["created"], at, rounds=rounds)
        if r["status"] == "stopping":
            lines.insert(0, "  Stop requested; waiting for Zeroshot to confirm.")
        return tuple(lines), live.flow(data, r["created"], at, rounds=rounds)

    def planner_panel(self):
        return self.planning.panel()

    @staticmethod
    def journal_lines(data):
        """`HH:MM:SS  text` per journal entry, oldest first; empty for a record without live metadata."""
        return tuple("  %s  %s" % (live.clock(e["at"]), e["text"]) for e in (data or {}).get("journal", ()))

    def journal(self, r=None):
        """The journal of an attempt (the planner of the current revision when `r` is None), bounded."""
        if r is None:
            return self.journal_lines(self.authority.current.get("live"))
        return self.journal_lines(r.get("live"))

    def active_run(self):
        """The running or stopping attempt of the current plan, if any."""
        found = self.runs.active() if self.plan() else None
        return found

    @staticmethod
    def tailable(r):
        """An activity tail is offered for a run that is executing or has failed (it has a native run id)."""
        return r is not None and r["run_id"] is not None and r["status"] in ("running", "stopping", "submitted", "failed")

    def tail(self, r=None, **options):
        """`zeroshot logs` of an attempt (the planner when `r` is None): the last lines or a single explanatory
        line. Blocking up to the reader deadline: callers run it on a worker, never on refresh."""
        try:
            if r is None:
                lines = self.planning.log_tail(**options)
            else:
                lines = self.runs.driver().log_tail(r.get("binding"), r["run_id"], r["worktree"], **options)
        except Blocked as error:
            return ["The journal is unavailable: " + summary(error)]
        except OSError as error:
            return ["The journal is unavailable: " + summary(error)]
        return lines or ["The journal is empty so far: Zeroshot has not written anything yet."]

    def activity(self, target=None):
        """(title, lines) of the activity tail the owner asked for on home: the running or failed attempt of
        `target`/the first such milestone, else the planner of the current revision. Blocking: run on a worker."""
        plan = self.plan()
        if plan is not None and plan["status"] == "approved":
            item = self.tail_item(self.runs.overview(live=False), target)
            if item is None:
                raise Blocked("There is no running or failed run now: no journal.", family="action.refused")
            r = item["record"]
            return "Journal %s · attempt %s" % (item["id"], r["attempt"]), self.tail(r)
        if plan is None or not plan["run_id"]:
            raise Blocked("The planner has no run yet: no journal.", family="action.refused")
        return "Planner journal r%s" % plan["version"], self.tail(None)

    @staticmethod
    def stop_question(r):
        return "Stop %s? The attempt's unfinished work will not be accepted." % r["milestone"]

    def stop(self, r):
        """The confirmed stop; a second request while stopping is refused."""
        if r["status"] == "stopping":
            raise Blocked("%s is already stopping." % r["milestone"], family="action.refused")
        self.runs.stop(r)
        return r

    @staticmethod
    def check_line(r):
        return ("Checking the stop of %s…" if r["status"] == "stopping" else "Checking the unfinished submission of %s…") % r["milestone"]

    def reconcile(self):
        return self.runs.reconcile()

    # End of run ----------------------------------------------------------------

    def latest_only(self, r):
        later = self.latest(r["milestone"])
        return later if later is not None and later is not r else r

    def reason(self, r):
        """The one-line cause of an ended attempt. A terminal node reason (`<node>_failed`) whose node is a known
        role is spelled out with that role's word; every other diagnostic keeps today's text. Eligibility is
        decided on the raw diagnostic, so a manifest suffix (added to normal blocked outcomes) is not stripped."""
        raw = r["diagnostic"] or ""
        if r.get("status") == "stopped":  # only the owner's stop ends a run as stopped; the engine's word is not for them
            return "  Reason: " + PLAN_STATUS["stopped"]
        if raw.endswith("_failed"):
            role = live.ROLES.get(live.base(raw[:-len("_failed")]))
            if role is not None:
                return "  Reason: the %s step gave no answer (timeout, failure or invalid answer) — %s" % (role, raw)
        text = plain(raw)
        return "  Reason: " + ("«%s»" % text if text else "not given; details — [i] on the main screen")

    def tasks_lines(self, r):
        manifest = self.runs.manifest(r)
        if not manifest:
            return ["  The manifest is unavailable."]
        tasks = [t for t in manifest["tasks"] if t["status"] != "dropped"]
        lines = ["  Tasks: %s/%s done" % (sum(t["status"] == "done" for t in tasks), len(tasks))]
        for item in manifest["amendments"]:
            lines.append("  Plan changed: %s%s" % (amendment_text(item),
                                                   " — " + one_line(item["reason"]) if item["reason"] else ""))
        return lines

    def end(self, r):
        """The end view of the latest attempt after `r`. An accepted attempt that is not exported yet is exported
        first (an owner-visible arrival, never a refresh). Raises for an active attempt: it is observed, not ended."""
        r = self.latest_only(r)
        state = run_state(r)
        if state in ACTIVE:
            raise Blocked("%s is still running." % r["milestone"], family="action.refused")
        if state != "unknown" and r["outcome"] == "done" and extended(r)["delivery"] in {"none", "exporting"}:
            self.runs.finish(r)
            state = run_state(r)
        return self.view(r, state)

    def view(self, r, state=None):
        state = state or run_state(r)
        x = extended(r)
        milestone, title, branch = r["milestone"], self.title(r["milestone"]), r["destination"]["branch"]
        code = RUN_FAMILY.get(state)
        status = "  Run: %s · outcome: %s · delivery: %s" % (
            RUN_STATUS[r["status"]], OUTCOME.get(r["outcome"], r["outcome"]), DELIVERY[x["delivery"]])

        def build(text, body, actions=None):
            chosen = tuple(EndAction(name, action_id, (branch,) if name == "merge" and state == "awaiting_merge" else ())
                           for name, action_id in END_ACTIONS.get(state, ()) if actions is None or name in actions)
            return EndView(state, Token.of(r), milestone, title,
                           "%s · %s — %s%s" % (milestone, title, text, catalog.tag(code) if code else ""), status,
                           tuple(body), chosen, code, r["attempt"], branch,
                           self.merge_question(r) if state in ("awaiting_merge", "conflict") else "",
                           self.journal_lines(r.get("live"))[-live.JOURNAL_LIMIT:])

        if state == "unknown":
            return build("submission status unknown" if r["status"] == "submission_unknown" else "interrupted",
                         ["  The submission is not confirmed; [g] check reconciles it with Zeroshot (without a rerun)."])
        if state == "integrated":
            return build("merged", ["  Merged into %s (commit %s)." % (branch, short(x["integration"]["commit"]
                                                                          or x["result"]["commit"]))]
                         + (["  Note: " + x["integration"]["landing"]] if x["integration"].get("landing") else []))
        if state == "awaiting_merge":
            body = self.tasks_lines(r) + ["  Changes relative to the base %s:" % short(r["destination"]["base"])]
            body += ["    " + line for line in self.runs.diff(r).splitlines() or ["(no changes)"]]
            return build("done, waiting for merge", body)
        if state == "conflict":
            conflicts = x["integration"]["conflicts"]
            body = ["  Files: " + ", ".join(conflicts[:10]) + (" …" if len(conflicts) > 10 else "")]
            if x["integration"]["aborted"]:
                body.append("  Your tree is untouched: repeat git merge %s by hand, resolve the conflict, commit, then zplan"
                            % x["result"]["branch"])
            else:  # a record of an older version, whose merge was written into the tree and then aborted
                body.append("  Aborting the merge failed: the working tree is NOT clean. git status:")
                body += ["    " + line for line in self.runs.merge_state()]
            return build("merge conflict into " + branch, body)
        if state == "needs_owner":
            return self.owner_view(r, build)
        if state == "blocked":
            body = [self.reason(r)]
            for task in (self.runs.manifest(r) or {}).get("tasks", []):
                if task["status"] == "open" and task.get("notes"):
                    body.append("  %s: %s" % (task["id"], one_line(task["notes"])))
            return build("blocked", body)
        if state == "failed_recoverable":
            return build("failed, can continue",
                         [self.reason(r)] + self.cause_lines(r)
                         + ["  [g] continue resumes the same attempt in its worktree."])
        if state == "failed":
            return build("failed, cannot continue", [self.reason(r)] + self.cause_lines(r))
        return build("stopped", [self.reason(r)])

    def owner_view(self, r, build):
        output = r["output"] or {}
        body = []
        if output.get("question"):
            body.append("  Question: " + one_line(output["question"], 400))
        proposal = output.get("proposal")
        names = ["answer", "leave"] + (["accept"] if proposal else [])
        if proposal:
            candidate, problem = self.runs.candidate(r)
            if candidate is None:
                body.append("  Proposal: " + one_line(proposal, 400))
                if problem:
                    body.append("  Not usable as the stage's task list: " + summary(problem))
                body.append("  Difference from the plan: it changes the stage plan → accepting opens a plan revision.")
            else:
                body.append("  Proposal: change the stage's tasks")
                for item in candidate["amendments"]:
                    body.append("    %s — %s" % (amendment_text(item), one_line(item["reason"])))
        return build("needs the owner's answer", body + self.tasks_lines(r), names)

    def diff_text(self, r):
        """The result's `git diff --stat` followed by the bounded full diff (the plain [d])."""
        return self.runs.diff(r) + "\n" + self.runs.diff(r, limit=DIFF_LIMIT)

    @staticmethod
    def cause_lines(r):
        """The end view's cause line (R-5) as a body line, or [] when the cause is unknown."""
        line = cause_line(r)
        return ["  " + line] if line else []

    @staticmethod
    def merge_question(r):
        return "Merge the result of %s into %s?" % (r["milestone"], r["destination"]["branch"])

    def merge(self, r, slice=CRITIC_SLICE, expected=None):
        """The confirmed merge. A conflict keeps the attempt open (its end view names the files).

        A gated merge runs the merge critic (`critic_authorize`) between the checks and the landing: `slice` bounds
        its one observation (`None` waits for the whole run; the Controller's call keeps the default). `expected`
        is the profile digest a caller decided on (the architect's merge policy): the merge's own profile read must
        be that profile, else `ProfileChanged` and nothing is merged."""
        try:
            status = self.guard("merge")
            if expected is not None and (status is None or status.digest != expected):
                raise ProfileChanged("The process profile changed after the merge decision: check the new values and "
                                     "repeat the merge.")
            resolved = status.resolved if status is not None else None
            self.runs.merge(r, resolved,
                            critic=lambda rr, gate, paths: self.critic_authorize(rr, gate, paths, resolved, slice))
        except Overlap as error:
            return Merge("overlap", refusal(error), True, error.paths)
        except Blocked as error:
            return Merge("conflict" if extended(r)["delivery"] == "conflict" else "refused",
                         "Not done: " + refusal(error), extended(r)["delivery"] == "conflict")
        if extended(r)["delivery"] == "integrated":
            left = self.cleanup(r)
            tail = "; left in place: %s." % ", ".join(left) if left else "."
            landing = extended(r)["integration"].get("landing")
            return Merge("integrated", "Merged: %s → %s%s%s" % (r["milestone"], r["destination"]["branch"], tail,
                                                                " Note: " + landing if landing else ""), False)
        return Merge("open", "", True)

    # Merge critic (A7b2) ----------------------------------------------------------

    def critic_authorize(self, r, gate, paths, resolved, slice):
        """Run (or reuse) the merge critic of one gated candidate (A7b2) and return its record when it allows the
        merge, or None when the risk raises no reason (the candidate lands as before).

        The engine is the planning factory of the merge's own revision; a native record freezes the engine's
        `critic_binding`, a fixture one its `gate_binding`, and the critic role is the profile's own. The newest
        `state["critics"]` record with an equal identity is reused: a never-prepared one rebuilds its documents, a
        prepared or submitted one is observed with `documents=None` and is never resent, an unconfirmed submission
        refuses as `submission.unknown`; a terminal record without a verdict is replaced by a new one, appended and
        saved before its dispatch. A `block`, a missing verdict and a slice that ends become the refusals
        `milestone.critic_blocked`, `merge.critic_failed` and `merge.critic_pending`; every other error stays one."""
        names = merge_critic.reasons(gate["risk"], {})
        if not names:
            return None
        revision = self.authority.state["revisions"][r["plan_revision"] - 1]
        engine = self.task_gate_engine(revision)
        briefs = self.merge_critic_briefs(r)
        identity = merge_critic_identity(r, gate, paths, names, briefs)
        newest = next((record for record in reversed(self.authority.state.get("critics", []))
                       if record["identity"] == identity), None)
        if newest is not None and newest["status"] == "submission_unknown":
            raise Blocked("The merge check submission is not confirmed; resubmission is not allowed.",
                          family="submission.unknown")
        if newest is not None and merge_critic.terminal(newest["status"]) and newest["verdict"] is not None:
            record = newest
        elif newest is not None and not merge_critic.terminal(newest["status"]):
            documents = self.merge_critic_recovery(newest, resolved, paths, briefs)
            record = self.critic_run(engine, newest, documents, slice)
        else:
            record = self.critic_new(resolved, engine, identity, names, paths, briefs, slice)
        if record["verdict"] == "block":
            raise Blocked(CRITIC_BLOCK_PREFIX + first_findings(record["findings"]),
                          family="milestone.critic_blocked")
        require(merge_critic.allows(record, identity),
                "The merge check did not allow merging the candidate %s; the merge was not done." % gate["candidate"][:12],
                family="merge.critic_failed")
        return record

    def critic_new(self, resolved, engine, identity, names, paths, briefs, slice):
        """A new merge-critic record, appended and saved before its dispatch (the `task_gate_new` pattern): its
        documents are built from the merge's own revision roles and frozen briefs, and it freezes the engine's own
        binding (native `critic_binding`, fixture `gate_binding`)."""
        documents = merge_critic_documents(critic_roles(resolved), identity, names, paths, briefs)
        binding = getattr(engine, "critic_binding", engine.gate_binding)(self.authority)
        record = merge_critic.record(identity, names, binding, documents)
        self.authority.state.setdefault("critics", []).append(record)
        try:
            self.authority.save()
        except BaseException:
            # A save publishes the file before its directory fsync: roll back only an append that never reached it.
            if not self.critic_published(record["id"]):
                self.authority.state["critics"].pop()
            raise
        return self.critic_run(engine, record, documents, slice)

    def critic_run(self, engine, record, documents, slice):
        """One merge-critic run through its own engine (a recovery uses the record's own binding inside `critic_run`)
        with the child's refusals: a slice that ends leaves the record and lands nothing (`merge.critic_pending`);
        every other error stays as it is."""
        try:
            return engine.critic_run(self.authority, record, documents, lambda _: None, slice)
        except ObservationDetached as error:
            raise Blocked("The merge check did not finish within its slice; repeat the merge.",
                          family="merge.critic_pending") from error

    def merge_critic_recovery(self, record, resolved, paths, briefs):
        """The documents a merge-critic recovery passes to `critic_run`: None while the record already has a
        preparation on disk or was submitted (`critic_prepare` reuses its frozen files), else the rebuild of a
        never-prepared record -- a crash right after the append -- with the same digests."""
        if record["run_id"] is not None or critic_prepared(self.authority, record):
            return None
        return merge_critic_documents(critic_roles(resolved), record["identity"], record["reasons"], paths, briefs)

    def merge_critic_briefs(self, r):
        """The milestone's frozen briefs (A7b2): the task briefs of the merge's own plan revision, from the bootstrap
        manifest that revision validates (`gate_manifest`), never the live project."""
        return self.runs.critic_briefs(r)

    def critic_published(self, record_id):
        """True while `record_id` is already visible in the store file, i.e. a failed `save` published it. A file the
        reader cannot parse is not this record's, so the append is treated as unpublished (`task_gate_published`)."""
        try:
            state = decode(self.authority.path.read_bytes().decode("utf-8"))
        except (OSError, UnicodeError, Blocked, ValueError, TypeError):
            return False
        entries = state.get("critics") if isinstance(state, dict) else None
        return isinstance(entries, list) and any(
            isinstance(entry, dict) and entry.get("id") == record_id for entry in entries)

    # Cleanup after an integrated merge (A7c) -------------------------------------

    def cleanup(self, r):
        """Remove the integrated attempt's worktree and branches; return the items left behind, by name.

        An existing worktree goes only while nothing in it is missing from the merge (`clean_tree`); its working
        branch is deleted only after that removal succeeded. An already-gone worktree is pruned. A branch is
        deleted only when everything on it is merged (`merged`), checked against the integration commit, never
        against an upstream (`-d` would). Every step is best effort: a failure or a skip leaves the delivery, the
        store and the outcome as they were, and never touches anything but this worktree and its two branches --
        never `gc`, never another path. A worktree that cannot even be inspected counts as existing (nothing is
        removed or pruned on an unknown path) and is reported among the leftovers; an uncertain branch is kept the
        same way (`branch_exists`)."""
        x, project = extended(r), self.authority.project
        worktree, result = Path(r["worktree"]), x["result"] or {}
        if self.present(worktree):
            if self.clean_tree(r) and self.git_ok(project, "worktree", "remove", "--force", str(worktree)):
                self.drop(r, r["branch"])
        else:
            self.git_ok(project, "worktree", "prune")
            self.drop(r, r["branch"])
        if result.get("branch"):
            self.drop(r, result["branch"])
        left = [str(worktree)] if self.present(worktree) else []
        return left + [branch for branch in (r["branch"], result.get("branch")) if branch and self.branch_exists(project, branch)]

    @staticmethod
    def present(worktree):
        """True while the worktree must be treated as existing: a failed inspection (e.g. an unreadable parent
        directory) is uncertain, so nothing is removed or pruned and the worktree is reported among the leftovers."""
        try:
            return worktree.is_dir()
        except OSError:
            return True

    def drop(self, r, branch):
        """Delete a branch of the attempt only when its tip is merged (`merged`); otherwise it stays."""
        project = self.authority.project
        try:
            tip = git_call(project, "rev-parse", "--verify", "--quiet", "refs/heads/%s^{commit}" % branch)
        except Blocked:
            return
        if tip.returncode == 0 and self.merged(r, project, tip.stdout.decode().strip()):
            self.git_ok(project, "branch", "-D", branch)

    @staticmethod
    def merged(r, repo, commit):
        """True when everything reachable from `commit` is in the destination: it is an ancestor of the integration
        commit. Equal files are not enough (a commit in between could hold other work), so a checkpoint commit
        (a resumed attempt) keeps its worktree and branch for the owner. A refused Git call is False."""
        landed = (extended(r)["integration"] or {}).get("commit")
        try:
            return bool(landed) and git_call(repo, "merge-base", "--is-ancestor", commit, landed).returncode == 0
        except Blocked:
            return False

    def clean_tree(self, r):
        """True when nothing in the worktree is missing from the merge. Read-only; any refused or unreadable step
        fails closed (the worktree is kept). All must hold:
        - the product tree identity equals the exported result's (tracked and untracked product files);
        - every index entry that differs from HEAD equals the result's entry at that path (nothing staged that the
          merge lacks, e.g. a `git add -f`);
        - HEAD is merged (`merged`: no commit of the attempt beyond the destination);
        - every untracked file, ignored or not, listed without any ignore rule (so no worktree or global ignore
          configuration can hide one), is under `.zplan/` or a disposable cache, or is a regular file or symlink
          whose content the result commit carries at the same path."""
        result = r["result"] or {}
        if result.get("tree") is None or not result.get("commit"):
            return False
        worktree = r["worktree"]
        try:
            if self.runs.product_tree(r) != result["tree"]:
                return False
            if not self.staged_merged(worktree, result["commit"]):
                return False
            head = git_call(worktree, "rev-parse", "--verify", "--quiet", "HEAD^{commit}")
            if head.returncode != 0 or not self.merged(r, worktree, head.stdout.decode().strip()):
                return False
            others = git_call(worktree, "ls-files", "-z", "--others")
            if others.returncode != 0:
                return False
            left = [p for p in others.stdout.decode().split("\0") if p and not self.disposable(p)]
            return not left or self.carried(worktree, result["commit"], left)
        except (Blocked, OSError, UnicodeError):
            return False

    @staticmethod
    def staged_merged(worktree, commit):
        """True when each path staged differently from HEAD is staged exactly as the result commit holds it."""
        literal = {"GIT_LITERAL_PATHSPECS": "1"}
        staged = git_call(worktree, "diff", "--cached", "--name-only", "--no-renames", "-z", env=literal)
        if staged.returncode != 0:
            return False
        paths = [p for p in staged.stdout.decode().split("\0") if p]
        return not paths or git_call(worktree, "diff", "--cached", "--quiet", "--no-renames", commit, "--", *paths,
                                     env=literal).returncode == 0

    @staticmethod
    def carried(worktree, commit, paths):
        """True when the result commit holds each path with the same content (a file's bytes, a symlink's target),
        hashed in the repository's object format."""
        listing = git_call(worktree, "ls-tree", "-r", "-z", commit)
        form = git_call(worktree, "rev-parse", "--show-object-format")
        if listing.returncode != 0 or form.returncode != 0:
            return False
        digest = {"sha1": hashlib.sha1, "sha256": hashlib.sha256}.get(form.stdout.decode().strip())
        blobs = dict(reversed(entry.split("\t", 1)) for entry in listing.stdout.decode().split("\0") if entry)
        for path in paths:
            local = Path(worktree) / path
            if digest is None or path not in blobs or not (local.is_symlink() or local.is_file()):
                return False
            data = os.fsencode(os.readlink(local)) if local.is_symlink() else local.read_bytes()
            if digest(b"blob %d\0" % len(data) + data).hexdigest() != blobs[path].split()[2]:
                return False
        return True

    @staticmethod
    def disposable(path):
        """True for a leftover path under `.zplan/` or the disposable caches `__pycache__/`, `node_modules/`,
        `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/` (at any depth)."""
        parts = path.rstrip("/").split("/")
        return any(path == c or path.startswith(c + "/") for c in CONTROL) or not CLEANUP_CACHES.isdisjoint(parts)

    @staticmethod
    def git_ok(project, *args):
        """One best-effort git command of the cleanup: True on exit 0, False when git exits or cannot run."""
        try:
            return git_call(project, *args).returncode == 0
        except Blocked:
            return False

    @staticmethod
    def branch_exists(project, branch):
        """True when the branch may still exist: `show-ref` exit 1 is its only confirmed absence, so a Git refusal
        (a non-1 exit code or a spawn failure) is uncertain and reported as present, keeping the branch in the
        leftovers."""
        try:
            return git_call(project, "show-ref", "--verify", "--quiet", "refs/heads/" + branch).returncode != 1
        except Blocked:
            return True

    # Owner actions that create an attempt or a revision --------------------------

    @staticmethod
    def attempt_line(r):
        return NEW_ATTEMPT % r["destination"]["branch"]

    def live_roles(self, kind):
        """The accepted profile's roles as they are now (None without a profile: the attempt or revision then
        inherits the previous one's); frozen revisions and attempts are never rewritten."""
        status = self.guard(kind)
        return status.resolved.roles() if status is not None else None

    def new_attempt(self, r, note=""):
        self.admission(r)
        return self.runs.retry(r, note, self.live_roles("milestone"))

    def answer(self, r, text):
        self.admission(r)
        return self.runs.answer(r, text, self.live_roles("milestone"))

    def accept(self, r):
        """needs_owner: ("attempt", the new attempt) or ("plan", the new revision, to be sent to the planner). Only
        the attempt branch opens a run, so only it takes the cap guard; a plan revision is not an attempt."""
        if self.runs.candidate(r)[0] is not None:
            self.admission(r)
        return self.runs.accept_proposal(r, self.live_roles("milestone"))

    def resume(self, r):
        self.admission(r)
        return self.runs.resume(r)

    def to_plan(self, r, feedback):
        return self.runs.revise(r, feedback, self.live_roles("plan"))

    @staticmethod
    def leave_line(r):
        return "%s stays unanswered; the attempt is over, nothing is running. Come back: [o] %s" % (
            r["milestone"], r["milestone"])

    # Details -------------------------------------------------------------------

    def lead(self):
        """Outcome first: one line per milestone of an approved plan, what really happened to it."""
        plan = self.plan()
        if plan is None or plan["status"] != "approved":
            return []
        lines = []
        for item in self.runs.overview(live=False):
            if item["state"] == "running":
                task, phase = item["task"], item["phase"]
                what = " ".join(p for p in (task[2] if task else None, phase) if p)
                lines.append("%s is running%s" % (item["id"], ": " + what if what else ""))
            else:
                lines.append("%s %s" % (item["id"], self.state_text(item)))
        return lines

    def journal_sections(self, plan):
        """What happened during the live runs, per attempt (latest of each milestone, then the planner): the
        stored journal, survives closing a result screen and restarting zplan."""
        lines = []
        for m in (plan["proposal"] or {}).get("milestones", []):
            r = self.latest(m["id"]) if plan["status"] == "approved" else None
            entries = self.journal_lines((r or {}).get("live"))
            if entries:
                lines += ["Journal %s (attempt %s):" % (m["id"], r["attempt"])] + list(entries)
        entries = self.journal_lines(plan.get("live"))
        if entries:
            lines += ["Planner journal r%s:" % plan["version"]] + list(entries)
        return lines + [""] if lines else lines

    def plan_section(self, plan):
        """The plan record with the record each milestone's row shows (the current revision's selection), so the
        plan screen does not claim nothing was implemented while a carried attempt is in flight."""
        runs = []
        for m in (plan.get("proposal") or {}).get("milestones", []):
            r = self.latest(m["id"])
            if r is not None:
                runs.append(r)
        return plan_lines(self.authority, plan, runs)

    def diagnostics(self, plan):
        """The tail for diagnosing: receipts, worktrees, run ids and ready-to-copy Zeroshot commands."""
        lines = []
        if plan["run_id"]:
            lines.append("Planner r%s: run %s" % (plan["version"], plan["run_id"]))
            if plan.get("diagnostic"):
                lines.append("  " + summary(plan["diagnostic"]))
            lines += self.planning.planner_commands(plan)
        for r in self.runs.runs:
            x = extended(r)
            lines.append("%s r%s attempt %s · run %s · %s · outcome %s · delivery %s" % (
                r["milestone"], r["plan_revision"], r["attempt"], r["run_id"] or "—", RUN_STATUS[r["status"]],
                OUTCOME.get(r["outcome"], r["outcome"]), DELIVERY[x["delivery"]]))
            lines.append("  worktree %s · branch %s · result %s %s" % (
                r["worktree"], r["branch"], x["result"]["branch"] if x["result"] else "—",
                short(x["result"]["commit"]) if x["result"] else ""))
            if r["diagnostic"]:
                lines.append("  " + summary(r["diagnostic"]))
            commands = diagnostic_commands(r)
            if commands:
                lines.append("  Zeroshot diagnostics (%s):" % (
                    "continuation of %s" % r["predecessor"] if r["predecessor"] else "root run"))
                lines += ["    " + command for command in commands]
        return lines

    def details(self):
        """[i] on home, the same text in both UIs: the real outcome first, then the plan, then the diagnostic tail."""
        plan = self.plan()
        if plan is None:
            return ("No plan.",)
        lines = self.lead()
        if lines:
            lines.append("")
        lines += self.journal_sections(plan)
        lines += self.plan_section(plan)
        tail = self.diagnostics(plan)
        if tail:
            lines += ["", "For diagnosis (ids, paths, Zeroshot commands):"] + tail
        return tuple(lines)

    def plan_info(self):
        """[i] on the plan screen: the requirements and checks of a plan; for a failed or unconfirmed planner the
        details with its diagnostics and the way to see whether Zeroshot took the submission."""
        current = self.authority.current
        view = self.planning.view()
        if view.kind == "proposal":
            return ("Goal: " + current["goal"], "") + tuple(self.planning.requirements_lines(current))
        lines = list(self.details())
        if view.kind == "unknown":
            lines += self.planning.unknown_lines(current)
        return tuple(lines)
