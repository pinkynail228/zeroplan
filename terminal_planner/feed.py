"""The architect's event feed (A6b1): a persisted queue of run events with its own handled mark.

Why: the engine cursor (`MilestoneRuns.observe`) says only what zplan observed; nothing records what the architect
has reacted to, so a run that finished while no architect turn ran is never brought to it. This module is the
durable queue A6b2 (catch-up and wake-up turns) and A6b3 consume; it has no TUI caller.

Where: the queue lives in the planning store (`state["feed"]`, an optional schema-2 key exactly like `critics`),
so an event is written in the same atomic save as the record change that caused it: never lost, never written
without its cause. State events are captured in `Authority.save` by comparing every run record's `run_state` with
the feed's last captured state; verdict events are appended where a verdict is recorded (`MilestoneRuns.read_verdict`),
identified by the reviewer's execution reference. Nothing is ever dropped before its ack: the queue is unbounded,
only a `pending` batch is bounded; `verdicts` is the one bounded structure (last `VERDICT_BOUND` executions per key),
used solely to skip a verdict execution that was already captured.

Interpretations (recorded here as the task asks; each is the reading closest to the task's example):
- A record with no `last` entry (the first save after bootstrap, or the first save of a session bootstrapped on a
  store that did not exist yet) captures an event with `previous` None.
- `bootstrap` on a session whose store does not exist yet marks the authority (`feed_pending`) instead of writing;
  the save that first creates the store then starts from an empty feed (`last` {}), so that session's first plan and
  run are captured by the ordinary state capture.
- Rollback covers every `PersistenceError` stage but `directory_fsync` (the replace already happened there): the
  feed is restored to its state before this save's capture, so a record the caller then removes leaves no event.
"""

import copy
import json
from datetime import datetime, timezone

from . import autonomy
from .authority import PLAN_STATUSES, Blocked, PersistenceError, require

# The one optional schema-2 key this module owns.
SCHEMA_KEYS = frozenset({"seq", "handled", "last", "verdicts", "events"})
# RS5: `plan` is the one optional key: the plan revision and status last captured ({"revision", "status"}, or None
# before the store has a revision). A feed written before RS5 has none; its first save records the current revision
# without an event.
PLAN_KEY = "plan"
EVENT_KINDS = ("state", "verdict", "plan")
STATE_KEYS = frozenset({"seq", "kind", "key", "milestone", "plan_revision", "attempt", "run_id", "state",
                        "previous", "wake", "at"})
PLAN_EVENT_KEYS = frozenset({"seq", "kind", "key", "plan_revision", "status", "previous", "wake", "at"})
VERDICT_KEYS = frozenset({"seq", "kind", "key", "milestone", "plan_revision", "attempt", "run_id", "execution",
                          "task", "round", "role", "verdict", "text", "wake", "at"})
# A state the architect must react to (C2): an event carrying it wakes a catch-up turn.
WAKE = frozenset({"stopped", "conflict", "integrated", "awaiting_merge", "needs_owner", "blocked",
                  "failed_recoverable", "failed"})
# RS5: a plan status the architect can act on, with the autonomy action that acts on it: the event wakes a turn only
# when `autonomy.decide` allows that action at the session's level; every other event rides along with wake false.
PLAN_WAKE = {"proposed": "approve", "approved": "start", "run_failed": "start", "proposal_invalid": "start",
             "review_exhausted": "start"}
# Executions remembered per key so a re-observed verdict is not captured twice (the store-side only bounding).
VERDICT_BOUND = 32
# A6b2a: how many wake events one catch-up turn covers (the batch rule); events past it wait for the next turn.
BATCH = 50
# A6b2a C1: a verdict line names the verdict text clipped to this many characters (the line stays one line).
VERDICT_TEXT = 300
INVALID = "Invalid feed; store rejected."


def now():
    """The event's `at`: the same Zulu second stamp the run records use."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def key(r):
    """A record's feed key: unique across resume successors (the successor carries its predecessor's run id)."""
    return "%s/%s/%s/%s" % (r["plan_revision"], r["milestone"], r["attempt"], r["predecessor"] or "-")


def empty():
    return {"seq": 0, "handled": 0, "last": {}, "verdicts": {}, "events": []}


def records(authority):
    state = authority.state
    return state.get("runs", []) if isinstance(state, dict) else []


def _feed(authority):
    state = authority.state
    return state.get("feed") if isinstance(state, dict) else None


def _append(queue, event):
    queue["seq"] += 1
    event["seq"] = queue["seq"]
    queue["events"].append(event)


def _save(authority, undo):
    """Save; when the write fails before the replace, `undo` this module's own change first, so the memory matches
    the disk and a retried bootstrap or ack writes again instead of returning as a no-op."""
    try:
        authority.save()
    except PersistenceError as error:
        if error.stage != "directory_fsync":
            undo()
        raise


def bootstrap(authority):
    """Create `state["feed"]` seeded from the current records and save, once. A feed already present is left as it
    is (no-op, no save); on a session whose store does not exist yet it writes nothing and marks the authority so the
    save that first creates the store starts from an empty feed (C1)."""
    if authority.state is None:
        authority.feed_pending = True
        return
    if "feed" in authority.state:
        return
    from .runs import run_state  # function-level: runs imports this module at load
    queue = empty()
    for r in authority.state.get("runs", []):
        item = key(r)
        current = run_state(r)
        if current != "unknown":  # transient: the next capture names the real state
            queue["last"][item] = current
        queue["verdicts"][item] = []
    authority.state["feed"] = queue
    _save(authority, lambda: authority.state.pop("feed", None))


def _acting(authority):
    """True while the Controller runs one of the architect's own actions (it sets `architect_acting` on the
    authority for the job's duration); the events captured then carry wake false."""
    return getattr(authority, "architect_acting", False)


def capture(authority):
    """Append, before the store is written, one state event per record whose `run_state` differs from the feed's
    last captured state (or whose key has none yet), then update `last`. Returns a snapshot of the feed taken before
    this save's capture, for `restore` on a failed write, or None when there is no feed (C2). The transient `unknown`
    state is neither captured nor stored. While the architect's own action runs (`authority.architect_acting`) the
    events carry wake false."""
    queue = _feed(authority)
    if queue is None:
        return None
    from .runs import run_state
    snapshot = copy.deepcopy(queue)
    _capture_plan(authority, queue)
    for r in records(authority):
        item = key(r)
        current = run_state(r)
        if current == "unknown":
            continue
        previous = queue["last"].get(item)
        if item in queue["last"] and previous == current:
            continue
        _append(queue, {"kind": "state", "key": item, "milestone": r["milestone"],
                        "plan_revision": r["plan_revision"], "attempt": r["attempt"], "run_id": r["run_id"],
                        "state": current, "previous": previous,
                        "wake": current in WAKE and not _acting(authority), "at": now()})
        queue["last"][item] = current
    return snapshot


def _plan_wakes(authority, status):
    """RS5: whether a plan event with `status` wakes a turn: the autonomy level of the session's profile lets the
    architect do what the status asks (`PLAN_WAKE`)."""
    action = PLAN_WAKE.get(status)
    return action is not None and autonomy.decide(autonomy.level(authority.profile), action) == "allow"


def _capture_plan(authority, queue):
    """RS5: append one plan event when the current revision's status differs from the one last captured for that
    revision, or the revision is new; then record it. The event wakes by the autonomy level (`_plan_wakes`). A feed with no `plan` entry records the current revision
    silently (a store written before RS5 raises no event for an old approval)."""
    revisions = authority.state.get("revisions") or []
    current = revisions[-1] if revisions else None
    seen = queue.get(PLAN_KEY)
    latest = None if current is None else {"revision": current["version"], "status": current["status"]}
    if PLAN_KEY not in queue:
        queue[PLAN_KEY] = latest
        return
    if latest is None or latest == seen:
        return
    previous = seen["status"] if seen is not None and seen["revision"] == latest["revision"] else None
    _append(queue, {"kind": "plan", "key": "plan/%d" % latest["revision"], "plan_revision": latest["revision"],
                    "status": latest["status"], "previous": previous,
                    "wake": _plan_wakes(authority, latest["status"]) and not _acting(authority), "at": now()})
    queue[PLAN_KEY] = latest


def restore(authority, snapshot):
    """Undo this save's state capture after a write that failed before the replace (C2)."""
    if snapshot is not None:
        authority.state["feed"] = snapshot


def verdict(authority, r, execution, entry, found_verdict, text):
    """Append a verdict event for one recorded verdict, in the same save as the record change, unless that execution
    was already captured for the record's key (C3). It wakes only when the verdict is not "accepted". `entry` is the queued reviewer: its task, round and role."""
    queue = _feed(authority)
    if queue is None:
        return
    item = key(r)
    seen = queue["verdicts"].setdefault(item, [])
    if execution in seen:
        return
    seen.append(execution)
    del seen[:-VERDICT_BOUND]
    _append(queue, {"kind": "verdict", "key": item, "milestone": r["milestone"],
                    "plan_revision": r["plan_revision"], "attempt": r["attempt"], "run_id": r["run_id"],
                    "execution": execution, "task": entry["task"], "round": entry["round"], "role": entry["role"],
                    "verdict": found_verdict, "text": text,
                    "wake": found_verdict != "accepted" and not _acting(authority), "at": now()})


def pending(authority, limit=50):
    """(the oldest `limit` events with seq > handled, the number of pending events after them); ([], 0) without a
    feed (C4). A pure read."""
    queue = _feed(authority)
    if queue is None:
        return [], 0
    waiting = [event for event in queue["events"] if event["seq"] > queue["handled"]]
    if limit is None:  # A6b2a: the catch-up turn reads the whole queue, "rest" then means nothing is left after it
        return waiting, 0
    return waiting[:limit], len(waiting) - min(limit, len(waiting))


def batch(events):
    """A6b2a C1: (the prefix of `events` up to and including its `BATCH`-th wake event, the number of events after
    the batch). A list with fewer than `BATCH` wake events is one batch; the non-wake events behind a wake one ride
    along with it, so the batch always ends on a wake event when it can. A pure function over the `pending` list."""
    wakes = 0
    for index, event in enumerate(events):
        if event.get("wake"):
            wakes += 1
            if wakes == BATCH:
                return events[:index + 1], len(events) - index - 1
    return list(events), 0


STATUS_PREFIX = "Status: "
LEGACY_STATUS_PREFIX = "Статус: "  # 0.7.x stored event turns spell the prefix in Russian
STATUS_UNAVAILABLE = "status unavailable: call zplan_status"


def status_line(status):
    """C1a: the status an event turn carries after its events: the `zplan_status` payload as one compact line, or the
    one line saying it is unavailable when the read gave nothing (empty) or the payload is `stale` (the worker was
    busy; the last rows could name a state that has moved on). The plan is named by version, status and verdict, not
    by its proposal text. A pure function."""
    if not isinstance(status, dict) or not status or status.get("stale"):
        return STATUS_UNAVAILABLE
    plan = status.get("plan")
    if isinstance(plan, dict):  # the proposal is the whole plan text: the turn names the revision, not its body
        status = {**status, "plan": {name: value for name, value in plan.items() if name != "proposal"}}
    return STATUS_PREFIX + json.dumps(status, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def summary(batch, rest, status=None):
    """A6b2a C1: the event turn's text for one `batch` and the `rest` count left after it. A pure function: the head
    line, one line per wake event in seq order, the count of the batch's non-wake events, the count left, the status
    line (C1a, only when `status` is given: `None` leaves the text as it was) and the closing instruction. `rest` is
    dropped when it is 0, the idle count is dropped when the batch is all wake."""
    lines = ["Events since the last turn:"]
    idle = 0
    for event in batch:
        if event.get("wake"):
            lines.append(_event_line(event))
        else:
            idle += 1
    if idle:
        lines.append("Intermediate states without action: %d." % idle)
    if rest:
        lines.append("… and %d more events." % rest)
    if status is not None:
        lines.append(status_line(status))
    lines.append("Assess them against the snapshot and act by your rules; if there is nothing to decide, answer briefly.")
    return "\n".join(lines)


def _event_line(event):
    """One wake event as the event turn names it: a state event by its milestone, attempt and transition; a plan
    event by its revision and transition (RS5); a verdict event by its milestone, task, round, role, verdict and its
    text as one line (`_one_line`), clipped to `VERDICT_TEXT` characters."""
    if event.get("kind") == "plan":
        return "plan r%s: %s -> %s" % (event["plan_revision"], event.get("previous") or "—", event["status"])
    if event.get("kind") == "verdict":
        return "%s %s round %s %s: %s — %s" % (event["milestone"], event.get("task") or "—",
                                               event.get("round") or "—", event["role"], event["verdict"],
                                               _one_line(event.get("text")))
    return "%s attempt %s: %s -> %s" % (event["milestone"], event.get("attempt"),
                                        event.get("previous") or "—", event["state"])


def _one_line(text):
    """A6b2a C1: the verdict text as one summary line — every run of whitespace (a newline the ordinary text may
    carry included) collapses to a single space, so one verdict never breaks the one-line-per-wake-event rule —
    then clipped to `VERDICT_TEXT` characters so the bound still holds."""
    return " ".join((text or "").split())[:VERDICT_TEXT]


def handle(authority, seq):
    """Acknowledge every event up to `seq`: `handled = max(handled, min(seq, feed seq))`, the handled events removed,
    and saved. A stale ack (no advance) is a no-op (C4)."""
    queue = _feed(authority)
    if queue is None:
        return
    reached = max(queue["handled"], min(seq, queue["seq"]))
    if reached == queue["handled"]:
        return
    handled, events = queue["handled"], queue["events"]
    queue["handled"] = reached
    queue["events"] = [event for event in queue["events"] if event["seq"] > reached]

    # The save's own failed-write restore may have replaced the feed object: undo on the current one.
    _save(authority, lambda: authority.state["feed"].update(handled=handled, events=events))


def validate_feed(queue):
    """Refuse a malformed feed like any malformed store: a wrong key set, a negative or inverted counter, a bad
    state or verdict enum, or an event that does not fit its kind refuses the whole store (`store.invalid`)."""
    from .runs import MILESTONE_STATES
    require(isinstance(queue, dict) and set(queue) in (SCHEMA_KEYS, SCHEMA_KEYS | {PLAN_KEY}), INVALID)
    plan = queue.get(PLAN_KEY)
    require(plan is None or (isinstance(plan, dict) and set(plan) == {"revision", "status"}
                             and type(plan["revision"]) is int and plan["revision"] >= 1
                             and plan["status"] in PLAN_STATUSES), INVALID)
    require(type(queue["seq"]) is int and queue["seq"] >= 0, INVALID)
    require(type(queue["handled"]) is int and 0 <= queue["handled"] <= queue["seq"], INVALID)
    require(isinstance(queue["last"], dict)
            and all(isinstance(k, str) and k and v in MILESTONE_STATES for k, v in queue["last"].items()), INVALID)
    require(isinstance(queue["verdicts"], dict)
            and all(isinstance(k, str) and k and isinstance(v, list) and len(v) <= VERDICT_BOUND
                    and all(isinstance(ref, str) and ref for ref in v) for k, v in queue["verdicts"].items()), INVALID)
    require(isinstance(queue["events"], list), INVALID)
    previous = 0
    for event in queue["events"]:
        require(isinstance(event, dict) and event.get("kind") in EVENT_KINDS, INVALID)
        require(type(event.get("seq")) is int and previous < event["seq"] <= queue["seq"]
                and event["seq"] > queue["handled"], INVALID)
        previous = event["seq"]
        common = (isinstance(event.get("key"), str) and event["key"]
                  and type(event.get("plan_revision")) is int and event["plan_revision"] >= 1
                  and isinstance(event.get("wake"), bool) and isinstance(event.get("at"), str) and bool(event["at"]))
        require(common, INVALID)
        if event["kind"] == "plan":
            require(set(event) == PLAN_EVENT_KEYS and event.get("status") in PLAN_STATUSES
                    and (event.get("previous") is None or event["previous"] in PLAN_STATUSES)
                    and (not event["wake"] or event["status"] in PLAN_WAKE), INVALID)
            continue
        run = (isinstance(event.get("milestone"), str) and bool(event["milestone"])
               and type(event.get("attempt")) is int and event["attempt"] >= 1
               and (event.get("run_id") is None or isinstance(event["run_id"], str)))
        require(run, INVALID)
        if event["kind"] == "state":
            require(set(event) == STATE_KEYS and event.get("state") in MILESTONE_STATES
                    and (event.get("previous") is None or event["previous"] in MILESTONE_STATES)
                    and (not event["wake"] or event["state"] in WAKE), INVALID)
        else:
            require(set(event) == VERDICT_KEYS and isinstance(event.get("execution"), str) and event["execution"]
                    and (event.get("task") is None or isinstance(event["task"], str))
                    and (event.get("round") is None or (type(event["round"]) is int and event["round"] >= 1))
                    and isinstance(event.get("role"), str) and event["role"]
                    and isinstance(event.get("verdict"), str) and event["verdict"]
                    and isinstance(event.get("text"), str), INVALID)
