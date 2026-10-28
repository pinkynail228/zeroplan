"""The architect chat of the full-screen shell: one conversation per project, one turn per owner message.

Preparation (toolchain, login and role checks) and every turn run on threads of this module, never on the UI event
loop and never on the controller worker: that worker alone owns Authority, and a turn may take minutes. The UI
thread reads a frozen `ChatState` and posts one message per Enter; events and results come back through the app's
hand-over path, so a flood of streamed events is coalesced into a single wake-up and the pending queue is a bounded
ring: neither the memory nor the UI queue can grow without limit. The transcript is the store's; the pane shows its
bounded tail, and an app restart rebuilds the same history from `ArchitectStore.transcript()`.

A6b2a: an injected feed port (`ArchitectChat(..., feed=PORT)`) makes the chat event-driven. The port's
`pending()`/`handle(seq)`/`snapshot()` are called off the UI thread; the chat catches up when it becomes ready,
after every turn ends and on `notify()`, and runs one event turn per catch-up batch that holds a wake event. The
owner's own messages have priority: one waits behind a running check or event turn and runs before any further
check. Without a port every behaviour and text is exactly the owner-only chat."""

from collections import deque
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import threading
import time
from typing import Tuple

from .. import architect as adapter
from .. import bridge, feed, process, project_state, setup
from ..architect import NO_PLAN, Architect, ArchitectStore, check_home, home_provider
from ..authority import Blocked
from ..cli import refusal
from . import strings

PENDING = 512            # coalesced UI events kept per turn: a stream of events cannot grow memory or the queue
HISTORY = 40             # transcript entries kept for display; older entries stay in the store
ENTRY_TEXT = 4000        # characters of one entry the pane keeps (the store keeps the whole text)
LIVE_CHARS = 400         # characters of the latest streamed text shown while the turn runs
NOTE_CHARS = 300         # characters of the last note line
QUIT_GRACE = 3.5         # seconds quit waits for a cancelled turn to take its process group down (cancel: 2 s)
# i9/A5: how long a running turn re-reads the store for its own owner row. The row is written before Codex starts
# (`architect._turn`), so the wait is a moment; the bound only keeps a store that cannot be read from spinning.
STAMP_SECONDS = 5.0
STAMP_EVERY = 0.02       # the re-read interval while the row is not there yet
# A6b2a: an event-driven architect turn is a transcript role of its own ("events"), never the owner's line: the row
# the adapter writes (`role "events"`) is shown as its own entry like every other role.
ROLES = ("owner", "architect", "error", "reset", "events")
# V2: a time line stands before the first shown entry and before any entry stored this long after the previous one.
TIME_GAP = timedelta(minutes=10)
DRAFT_MARK = "↳ "  # V2: a draft line starts with it; the draft kind (and the milestone of an answer) follows
STAMP_HM = re.compile(r"[T ](\d\d:\d\d)")  # the HH:MM inside a stored `ts` (`architect._stamp`)
DRAFT_KINDS = {"goal": "goal draft", "answer": "answer draft"}
# 0.7.x replies (and stored rows) label a draft block in Russian; `label_cut` still cuts those labels.
LEGACY_DRAFT_KINDS = {"goal": "черновик цели", "answer": "черновик ответа"}
PREPARING = "preparing chat…"
CHAT_UNAVAILABLE = "Chat unavailable."
# A6b2a C4: the note the owner's message shows while an event check or an event turn runs ahead of it.
WAITING = "Will send after the current turn."


@dataclass(frozen=True)
class Draft:
    """One draft block of a successfully completed architect reply: the data contract u3b-drafts-goal and
    u3b-drafts-answer build on.

    `kind` is "goal" or "answer"; `text` is the draft body exactly as the architect wrote it, and stays copyable.
    `milestone` is the milestone id of an answer ("" for a goal). `identity` is the plain provenance of the state
    the turn was sent with: for a goal the plan identity (the string "no plan", or `[revision, state]` where the
    state is the controller snapshot's `{"status": ..., "override": ...}`), for an answer the plain attempt token
    of that milestone in the turn's snapshot. It is None when that snapshot could name none. `actionable` is True
    only when `identity` is present and the turn's success mark was persisted with the reply: a draft without that
    metadata, and any reply stored before drafts existed, is copyable text only. This task adds no key: an
    actionable draft is not yet a UI action."""
    kind: str
    text: str
    milestone: str = ""
    identity: object = None
    actionable: bool = False


@dataclass(frozen=True)
class ChatEntry:
    """One transcript entry as the pane shows it; `partial` is the last text of a turn that did not complete.

    `sections` is the reply's transformed body as `(head, label, body)` triples (`entry_sections`); it stays
    structured so the pane can set each draft line apart from the narrative around it. `text` is the same body as
    one string, and is what an entry without sections (an owner line, an old row) is shown from."""
    role: str
    text: str
    partial: str = ""
    drafts: Tuple[Draft, ...] = ()  # the drafts of a successful architect reply; empty for every other entry
    matched: Tuple[int, ...] = ()   # indices into `drafts` whose source span was collapsed into `text`
    sections: Tuple = ()            # the transformed body as (head, label, body): the narrative, the draft labels
    occurrence: int = None          # the entry's place among the transcript's role rows; None when built by hand
    at: str = field(default="", compare=False)  # the stored `ts` of the row, "" when it names none (`moment` reads it)


@dataclass(frozen=True)
class ChatHeader:
    """The chat header's fields, each one whole.

    The effective CODEX_HOME and the provider are both free text: a directory name and a provider key may each
    hold the ` · ` the display line is spelled with. The chat therefore hands the UI the fields themselves — the
    line is only ever for a human to read — so a separator inside a value cannot move one field into another."""
    home: str = ""
    provider: str = ""
    model: str = ""
    effort: str = ""

    @property
    def line(self):
        """The display line the fields spell; empty when there is no field at all."""
        if not (self.home or self.provider or self.model or self.effort):
            return ""
        return header_line(header_home(self.home, self.provider), self.model, self.effort)


@dataclass(frozen=True)
class ChatState:
    """The frozen chat of the main screen: replaced on the UI thread, read by the renderer."""
    phase: str = "preparing"      # preparing | ready | blocked
    refusal: str = ""             # the catalog refusal (with its remedy) when the chat cannot start
    header: str = ""              # the header's display line, built from `header_fields` (never re-split)
    header_fields: ChatHeader = ChatHeader()  # effective CODEX_HOME, provider and model, one field each
    usage: Tuple[int, int] = None  # session usage counters (turns, tokens), integers or None; never a display string
    entries: Tuple[ChatEntry, ...] = ()
    transcript: int = 0           # R-4: displayable transcript entries the store held at the last `history` load
    running: bool = False         # a turn is in flight
    started: float = 0.0          # monotonic start of the running turn (elapsed is computed from it)
    elapsed: float = 0.0
    live: str = ""                # latest streamed text of the running turn
    note: str = ""                # the last refusal or the verdict of a turn


def stamp_at(stamp):
    """i9/A5: the `HH:MM` of one stored `ts` (`architect._stamp`), or "" when it names no time.

    P2a: a stored UTC stamp (ending in `Z`) is shown in the local zone, the clock the cards' receipts read; a stamp
    without a zone is shown as it is stored. The store keeps UTC."""
    if not isinstance(stamp, str):
        return ""
    if stamp.endswith("Z"):
        try:
            return datetime.fromisoformat(stamp).astimezone().strftime("%H:%M")
        except (ValueError, OverflowError, OSError):
            pass  # not a full ISO stamp: the stored HH:MM below
    match = STAMP_HM.search(stamp)
    return match.group(1) if match else ""


def moment(stamp):
    """V2: the local time of one stored `ts`, or None when it names none a time line can use.

    The same zone rule as `stamp_at` (P2a): a stored UTC stamp is read in the local zone, a stamp with another offset
    in that offset's own clock converted to the local one, and a stamp without a zone as it is stored. The result is
    naive, so two of them subtract and compare with a local date."""
    if not isinstance(stamp, str):
        return None
    try:
        when = datetime.fromisoformat(stamp)
        return when.astimezone().replace(tzinfo=None) if when.tzinfo is not None else when
    except (ValueError, OverflowError, OSError):
        return None


def time_labels(entries, today=None):
    """V2: the time line each entry stands behind, one string per entry ("" for none), in order.

    The first entry that carries a time and every entry stored `TIME_GAP` or more after the previous timed entry get
    one: `HH:MM`, or `DD.MM HH:MM` when the entry was stored on another day than `today` (a local date, the clock's
    own by default). An entry with no stored time (the owner's line while its turn has not stamped it yet) gets none
    and does not move the gap."""
    today = today or datetime.now().date()
    labels, previous = [], None
    for entry in entries:
        when = moment(entry.at)
        if when is None:
            labels.append("")
            continue
        if previous is None or when - previous >= TIME_GAP:
            labels.append(when.strftime("%H:%M" if when.date() == today else "%d.%m %H:%M"))
        else:
            labels.append("")
        previous = when
    return labels


def entries_of(rows, history=HISTORY):
    """The transcript tail the pane shows, from the store's rows; the whole transcript stays in the store.

    O4: the pane shows the current conversation only — the rows from the last `reset` row on (that row is the first
    line), or every row when there is none — and never a prompt zplan sent on `/new` itself: a row of the hidden
    `system` role is not a transcript role at all, and an `events` row of an older store that begins with the handoff
    or the warm-up prompt (`is_prompt_row`) is skipped. Skipped and cut rows still count in each shown entry's
    `occurrence`, so an entry keeps its place among the store's role rows.

    An architect reply is transformed before it is clipped. Every eligible source span `architect.draft_spans`
    finds in the full stored text is matched once, in stored order, to the draft records stored with the row (by
    kind, milestone and trimmed body) and collapses into that record's labelled line where it stood: the body is
    shown once, at the block's position, and the record's index is kept in `ChatEntry.matched` so the trailing
    rendering skips it. Eligibility is `architect.draft_body`'s own rule — the parser's body rule, shared, not a
    second one — so a span the parser would never have recorded (empty or oversized) can neither collapse nor
    take the record a later span owns. The payload the pane's `ENTRY_TEXT` bound counts is the transformed text as
    Python characters — the unchanged narrative and the trimmed draft bodies, never the labels the pane generates
    nor the leading `…`; its last `ENTRY_TEXT` characters are kept, a cut section keeping its suffix and its label,
    a wholly clipped one not appended again. A span with no record left, and a row without any match, keep today's
    rendering. The stored records themselves are untouched: `ChatEntry.drafts` keeps every `Draft`, so [c]/[t] still
    act on a draft whose body is out of view, and `ChatEntry.sections` keeps the body structured so the pane can
    set a collapsed draft line apart from the narrative around it."""
    found = []
    occurrence = 0
    for row in rows:
        if not isinstance(row, dict) or row.get("role") not in ROLES:
            continue
        text = str(row.get("text") or "")
        if row["role"] == "reset":  # O4: a new conversation starts here; what came before is not shown
            found = []
        elif is_prompt_row(row):  # O4: an old store kept the `/new` prompts as `events` rows
            occurrence += 1
            continue
        if row["role"] == "events":  # C1a/U1b: the status and the closing instruction are for the architect; the pane shows the events only
            text = "\n".join(line for line in text.split("\n") if line not in EVENT_HIDDEN
                              and line not in LEGACY_EVENT_HIDDEN
                              and not line.startswith((feed.STATUS_PREFIX, feed.LEGACY_STATUS_PREFIX)))
        drafts = drafts_of(row)
        sections, matched = entry_sections(text, drafts)
        sections = clip_sections(sections)
        stamp = row.get("ts")
        found.append(ChatEntry(row["role"], sections_text(sections), str(row.get("partial") or ""), drafts,
                               matched, sections, occurrence, stamp if isinstance(stamp, str) else ""))
        occurrence += 1
    return tuple(found[-history:])


# U1b: the event prompt's lines the pane never shows besides the `STATUS_PREFIX` one: the status the read could not
# give, and the closing instruction (the last line of an event text, taken from `feed.summary` itself).
EVENT_HIDDEN = (feed.STATUS_UNAVAILABLE, feed.summary([], 0).split("\n")[-1])
# The same two lines as 0.7.x stored them (Russian); rows of an old store keep them, so they stay hidden.
LEGACY_EVENT_HIDDEN = ("статус недоступен: вызови zplan_status",
                       "Оцени их по снимку и действуй по своим правилам; если решать нечего, ответь коротко.")


def is_prompt_row(row):
    """O4: True for an `events` row that holds one of the two prompts `/new` sends (the handoff, the warm-up). New
    stores keep them under the hidden `system` role; this recognises the rows 0.6.0 stored as `events`."""
    text = str(row.get("text") or "")
    return row.get("role") == "events" and text.startswith(PROMPT_STARTS + LEGACY_PROMPT_STARTS)


def owner_entry(text, occurrence=None):
    """The owner's own line as the pane shows it, built through the same `entries_of` pipeline a store reload uses.

    A plain `ChatEntry("owner", text)` carries no sections, so it never equals the persisted form the reload builds
    from the store row (`entry_sections` renders even the plain owner text as one narrative section) — and that
    unequal pair defeats the reconciliation's slide across the turn, rewriting the conversation around an inline
    card. One row is never clipped by the window, so `history` does not matter here.

    `occurrence` is the line's own place in the append-only transcript (the store's role-row count when the turn
    started), so the optimistic line reconciles with the persisted row the turn's reload brings back — the same
    place, not only the same text. Without it the line is built as `entries_of` builds a one-row window."""
    entry = entries_of([{"role": "owner", "text": str(text)}])[0]
    return entry if occurrence is None else replace(entry, occurrence=occurrence)


def transcript_size(rows):
    """R-4's append provenance: the number of transcript entries the stored `rows` hold, before the `HISTORY` cap
    and the `ENTRY_TEXT` clipping `entries_of` applies to the window the pane keeps.

    The transcript is append-only, so this count only grows and a reload that grew it appended at least one entry —
    an entry the cap or the per-entry text limit may hide from the retained window, so a window comparison cannot
    see it (and two reloads of a full window can hold the same 40 entries while one of them appended). Counts the
    rows `entries_of` reads, so a row the pane cannot show is not an entry: the store's own role filter, no more.
    """
    return sum(1 for row in rows if isinstance(row, dict) and row.get("role") in ROLES)


def draft_label(draft):
    """The label a draft line and a collapsed source span both write ahead of a draft's own text: its kind and,
    for an answer, its milestone."""
    return DRAFT_KINDS.get(draft.kind, draft.kind) + (" " + draft.milestone if draft.milestone else "") + ": "


def matching_draft(drafts, used, kind, milestone, body):
    """The index of the first record of `drafts` not in `used` that one eligible source span belongs to, or None.

    The display matches by content alone — `(kind, milestone or "", body)`, the body already trimmed by
    `architect.draft_body` — so identity, `actionable` and the current snapshot never take part: a row renders the
    same whatever the plan did since. The stored order is the reply's own order, so a reply with several drafts
    collapses each into the span it was parsed from."""
    wanted = (kind, milestone or "", body)
    for index, draft in enumerate(drafts):
        if index not in used and (draft.kind, draft.milestone or "", draft.text) == wanted:
            return index
    return None


def label_cut(lines, cursor, start, kind):
    """The end of the narrative run `lines[cursor:start]` before a draft block of `kind`: the app draws its own
    label for the block, so a last line that is only that label (`Goal draft:` or its 0.7.x Russian form, bold or
    not, colon or not) is left out with the blank lines after it. Any other line stays."""
    end = start
    while end > cursor and not lines[end - 1].strip():
        end -= 1
    labels = "|".join(re.escape(label) for label in (DRAFT_KINDS.get(kind, kind), LEGACY_DRAFT_KINDS.get(kind, kind)))
    if end > cursor and re.fullmatch(r"[*_]*\s*(?:%s)\s*:?\s*[*_]*\s*:?" % labels, lines[end - 1].strip(), re.I):
        end -= 1
        while end > cursor and not lines[end - 1].strip():
            end -= 1
        return end
    return start


def entry_sections(text, drafts):
    """One stored reply as ordered sections `[head, label, body]` plus the indices of the collapsed records.

    The sections spell the reply's transformed text: narrative runs exactly as they are stored (unmatched spans
    included) and, at each matched source span, the labelled draft line that replaces the opener, the body and the
    closing fence. A span whose body `architect.draft_body` rejects — empty or over `MAX_DRAFT_TEXT`, the rule the
    parser applies to itself — is never matched, so it can neither collapse nor take the record a later span owns.
    `head` is the one line break that separated a section from the one before (empty for the first), `label` the
    generated draft label (empty for narrative) and `body` the text that counts towards `ENTRY_TEXT` — the
    narrative as it stands or the trimmed draft body."""
    lines = str(text or "").split("\n")
    sections, matched, used, cursor = [], [], set(), 0
    for start, end, kind, milestone, raw in adapter.draft_spans(text):
        body = adapter.draft_body(raw)
        if body is None:  # the parser stores nothing for such a block, so no record may be spent on it
            continue
        index = matching_draft(drafts, used, kind, milestone, body)
        if index is None:  # no record left for this span: it stays the raw text it is stored as
            continue
        before = label_cut(lines, cursor, start, kind)
        if before > cursor:
            sections.append(["\n" if sections else "", "", "\n".join(lines[cursor:before])])
        used.add(index)
        matched.append(index)
        sections.append(["\n" if sections else "", DRAFT_MARK + draft_label(drafts[index]), body])
        cursor = end
    if cursor < len(lines):
        sections.append(["\n" if sections else "", "", "\n".join(lines[cursor:])])
    return sections, tuple(matched)


def clip_sections(sections, limit=ENTRY_TEXT):
    """R-4: `sections` with their payload cut down to its last `limit` characters.

    The payload is the heads, the narrative and the trimmed draft bodies; the generated labels are excluded from
    the count. A section the cut reaches keeps its suffix and, for a draft, its whole label; a section the cut
    passes whole is dropped, and a matched draft dropped that way is not appended again. The first surviving
    section's head takes the leading `…` that marks the clip — also excluded from the count, as R-4 says."""
    total = sum(len(head) + len(body) for head, _label, body in sections)
    if total <= limit:
        return tuple((head, label, body) for head, label, body in sections)
    drop = total - limit
    out = []
    for head, label, body in sections:
        if drop >= len(head) + len(body):
            drop -= len(head) + len(body)
            continue
        if drop:
            if drop < len(head):
                head = head[drop:]
            else:
                body, head = body[drop - len(head):], ""
            drop = 0
        out.append((head, label, body))
    if not out:  # only a zero limit can reach this; the marker still stands for everything the cut dropped
        return (("…", "", ""),)
    return (("…" + out[0][0], out[0][1], out[0][2]),) + tuple(out[1:])


def sections_text(sections):
    """The pane text of `sections`: for each of them its head, the generated label of a draft section and its body."""
    return "".join(head + label + body for head, label, body in sections)


def drafts_of(row):
    """The drafts a stored transcript row carries, as the pane shows them.

    Only the reply of a successful architect turn carries any: the adapter writes them with the reply, together
    with the turn's success mark (`status: "completed"`). Both are needed for a draft to be actionable, and the
    identity stored with the draft is the one of the turn's own snapshot — old text is never bound to the current
    snapshot. A row without that metadata (a reply stored before drafts existed, or without a success mark) comes
    back as the ordinary text it was stored with."""
    saved = row.get("drafts") if isinstance(row, dict) and row.get("role") == "architect" else None
    if not isinstance(saved, (list, tuple)):
        return ()
    success = row.get("status") == "completed"
    found = []
    for item in saved:
        if not isinstance(item, dict) or item.get("kind") not in DRAFT_KINDS:
            continue
        identity = item.get("identity")
        found.append(Draft(str(item["kind"]), str(item.get("text") or ""), str(item.get("milestone") or ""),
                           identity, success and identity is not None))
    return tuple(found)


def newest_goal_draft(entries):
    """The newest actionable goal draft of the retained history, or None: U-3's source of the [c] choice.

    The choice is made from `ChatState.entries` and from nothing else — never from what the chat pane happens to
    show — and it is the last actionable `goal` draft the history still holds; the entries keep the replies' own
    order, so the newest reply's own goal draft wins first. Anything else — an answer draft, a goal draft without
    a persisted identity, a non-actionable one — is not a choice, and a history without one yields None."""
    for entry in reversed(tuple(entries)):
        for draft in reversed(tuple(entry.drafts)):
            if draft.kind == "goal" and draft.actionable:
                return draft
    return None


def newest_answer_draft(entries, milestone):
    """The newest actionable answer draft of `milestone` in the retained history, or None: the [t] choice.

    Same source and same order as `newest_goal_draft` — the retained `ChatState.entries` alone — but scoped to one
    milestone: only an `answer` draft of that id is a choice, and the newest one wins, which also settles several
    answer drafts of one reply (they keep the reply's own order). A draft of another milestone, a non-actionable
    one and a history without one all yield None."""
    for entry in reversed(tuple(entries)):
        for draft in reversed(tuple(entry.drafts)):
            if draft.kind == "answer" and draft.actionable and draft.milestone == milestone:
                return draft
    return None


OUTDATED = "draft is outdated"                # the refusal a goal draft that no longer matches the plan gets
NEW_REVISION = "new revision"                 # its reasons: the plan moved to another revision (or appeared)
STATE_CHANGED = "plan state changed"          # or the same revision's state did


def stale_reason(identity, current):
    """The reason a goal draft's provenance `identity` no longer matches the plan identity `current`, "" when it
    still does: the goal-draft half of the provenance re-check.

    Both sides are the plain goal identity `architect.plan_identity` builds: the string "no plan", or the pair
    `[revision, state]`. The check is made on the controller worker right before `planning.begin`, so `current` is
    the session's plan identity *as it is then*: a plan that appeared under a "no plan" draft, a draft that
    outlived its own revision (a new revision), and a revision whose state moved on without a new revision
    (submitted, plan ready, approved) are each a stale draft. An identity the draft cannot carry (None) is stale
    too, and never reads as "no plan"."""
    if identity == current:
        return ""
    if identity == NO_PLAN:
        return "a plan appeared"
    if current == NO_PLAN:
        return "the plan is gone"
    if not isinstance(identity, (list, tuple)) or not isinstance(current, (list, tuple)):
        return STATE_CHANGED
    if identity[0] != current[0]:
        return NEW_REVISION
    return STATE_CHANGED


def usage_counts(session):
    """The session's `(turns, tokens)` counters as integers, or None when the record says nothing.

    Codex counts `cached_input_tokens` inside `input_tokens`, so the tokens are `input_tokens` plus
    `output_tokens`: every other key of the usage map is a breakdown, not another counter. The UI keeps these two
    integers and lays them out itself (L-3); it never spells them into a display line and reads them back out."""
    if not isinstance(session, dict):
        return None
    turns = session.get("turns")
    usage = session.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    if not isinstance(turns, int) or isinstance(turns, bool):
        return None
    tokens = sum(usage[key] for key in ("input_tokens", "output_tokens")
                 if isinstance(usage.get(key), int) and not isinstance(usage.get(key), bool))
    return (turns, tokens)


# A8b: the rot signal fires past either counter of `usage_counts`; the header then suggests `/new`.
ROT_TURNS = 40
ROT_TOKENS = 2_000_000

# A8b: the two fixed turns `/new` sends around the reset. Both are stored under `PROMPT_ROLE` (not typed by the owner).
HANDOFF_MESSAGE = ("Session closing. Save the handoff for the next session: call zplan_state_update with the full "
                   "STATE text (plan, next step, open questions, decisions). Answer in one line.")
HANDOFF_FAILED = "Handoff not saved (the turn failed or was cancelled): the new conversation starts without it."
WARMUP_MESSAGE = ("New session. You are continuing work on the project; the previous conversation is forgotten.\n\n"
                  "Project STATE:\n%s\n\nScreen snapshot:\n%s\n\n"
                  "Briefly say where we are and what to do next.")
NO_STATE = "(none)"
# 0.7.x stored the two prompts in Russian (as `events` rows in 0.6.0 stores); `is_prompt_row` still recognises them.
LEGACY_HANDOFF_MESSAGE = ("Сессия закрывается. Сохрани передачу дел следующей сессии: вызови zplan_state_update с полным "
                          "текстом STATE (план, следующий шаг, открытые вопросы, решения). Ответь одной строкой.")
LEGACY_WARMUP_MESSAGE = ("Новая сессия. Ты продолжаешь работу над проектом; прежний разговор забыт.\n\n"
                         "STATE проекта:\n%s\n\nСнимок экрана:\n%s\n\n"
                         "Коротко скажи, где мы и что делать дальше.")
PROMPT_STARTS = (HANDOFF_MESSAGE, WARMUP_MESSAGE.split("%s", 1)[0])
LEGACY_PROMPT_STARTS = (LEGACY_HANDOFF_MESSAGE, LEGACY_WARMUP_MESSAGE.split("%s", 1)[0])
PROMPT_ROLE = "system"  # O4: the transcript role of the two `/new` prompts; not in `ROLES`, so the pane never shows it


def session_long(usage):
    """True when the `(turns, tokens)` counters of `usage_counts` are past the rot threshold (None: no counters)."""
    return usage is not None and (usage[0] >= ROT_TURNS or usage[1] >= ROT_TOKENS)


def architect_binding(project, role="architect"):
    """The effective `architect` model/effort of the project's process profile, else the frozen preset's.

    A profile the chat cannot read is not a fallback: a broken (malformed) or deleted (missing) accepted profile
    raises `Blocked` with the catalog refusal and its remedy, instead of talking to Codex with a role nobody chose.
    The same holds for a roles.json the profile cannot read (its `Blocked` travels through unchanged)."""
    model, effort = process.PRESETS[process.PRESET]["roles"][role]
    try:
        status = process.Profile.peek(project).status(write=False)
    except (OSError, ValueError):
        return model, effort
    if status.state == "malformed":
        raise Blocked(status.problem or ("%s is damaged." % process.PROFILE_FILE), family="process.invalid")
    if status.state == "missing":
        raise Blocked(status.problem or ("The accepted %s was removed from the project." % process.PROFILE_FILE),
                      family="process.missing")
    resolved = getattr(status, "resolved", None)
    binding = resolved.config.get("roles", {}).get(role) if resolved is not None else None
    if not isinstance(binding, dict):
        return model, effort
    return str(binding.get("model") or model), str(binding.get("effort") or effort)


def header_line(prefix, model, effort):
    """The chat header of one binding: the effective CODEX_HOME and provider, then the role's `model/effort`."""
    return "%s · %s/%s" % (prefix, model, effort)


def header_home(home, provider):
    """The static part of a header — the effective CODEX_HOME and the provider — before the bound role."""
    return "CODEX_HOME %s · provider %s" % (setup.tilde(home), provider)


def header_provider(home):
    """The provider a turn in `home` selects, or "?" when it cannot be read (R-5).

    The header's fallback: a missing directory, an unreadable config.toml (a permission error, a symlink loop, an
    over-long component) and an unknown profile all answer "?", and a filesystem failure is one of them, never an
    exception. It resolves the provider through `architect.home_provider`, the same rule `check_home` uses, so the
    pane and the turn never disagree about a config that cannot be read; the refusal belongs to the turn, not the
    header."""
    try:
        if not Path(home).is_dir():
            return "?"
        provider, _auth = home_provider(home)
    except (Blocked, OSError, ValueError):
        return "?"
    return provider


def live_header(architect):
    """Re-read the header's own fields (the effective CODEX_HOME and provider) of the next turn, on the chat thread.

    The next turn acts in `architect.next_home()`: the recorded home of a continuation, the current home for a new
    thread (R-5), so a continuation keeps showing its recorded home while the current env holds another one. Codex
    selects its provider from that home's config.toml when the turn's own process starts, so the header follows the
    current config; a provider that cannot be read falls back to "?" (`header_provider`, never raising). A store
    that cannot be read at all leaves the prepared fields in place."""
    if not getattr(architect, "environment", None):
        return None
    try:
        home, _resumed = architect.next_home()
    except (Blocked, OSError, ValueError):
        return None
    return ChatHeader(home=setup.tilde(home), provider=header_provider(home))


def default_prepare(project):
    """Production preparation: the installed toolchain, the login and the profile's architect role. Returns
    (Architect, header); raises Blocked with a catalog family and a remedy when the chat cannot start. Runs off the
    UI event loop (the pinned binaries are executed here) and never on the controller worker."""
    try:  # pinned receipt + version checks; Blocked(setup.tools_invalid)
        root = setup.check_installation()
    except Blocked:
        raise
    except OSError as error:  # nothing installed under this data root at all
        raise Blocked("zplan tools are not installed: run zplan setup.", family="setup.tools_invalid") from error
    environment = setup.native_environment()
    executable = setup.tool_paths(root)[1]
    if not (executable.is_file() and os.access(executable, os.X_OK)):
        raise Blocked("Codex not found: %s; run zplan setup." % executable, family="setup.tools_invalid")
    missing = adapter.verify_cli(executable, environment)
    if missing:
        raise Blocked("The pinned Codex lacks required flags (%s); update the tools: zplan setup."
                      % ", ".join(missing), family="setup.tools_invalid")
    model, effort = architect_binding(project)
    # The action tools reach the live Controller of this process through its published socket (None: no window
    # serves this project, so they answer `architect.controller_unavailable`).
    architect = Architect(executable, environment, project, model, effort, controller=bridge.path_for(project))
    home, resumed = architect.next_home()
    if not resumed:
        # R-5: only a new thread is judged here -- the existing readiness.auth refusals, unchanged in text. A
        # continuation runs no check of its recorded home at all (directory, config, profile, auth): every one of
        # them is deferred to the turn, so a broken recorded home never blocks preparation and Ctrl+R (new dialog)
        # stays reachable (gate9 A).
        check_home(home, environment, resumed)
    header = ChatHeader(home=setup.tilde(home), provider=header_provider(home), model=model, effort=effort)
    return architect, header


class ArchitectChat:
    """One architect conversation of one window. `prepare()` builds the ready architect (or raises Blocked) on a
    thread of this object; `send`/`reset` run on their own thread too, so the UI never waits for Codex. All state
    changes happen on the UI thread (through the hand-over), so the renderer never sees a torn chat."""

    def __init__(self, project, prepare, *, binding=None, hand_over=None, on_change=None, history=HISTORY,
                 pending=PENDING, store=None, feed=None):
        self.project = Path(project).expanduser().resolve()
        self.prepare = prepare
        self.binding = binding or (lambda: architect_binding(self.project))
        self.hand_over = hand_over or (lambda call: call())
        self.on_change = on_change or (lambda: None)
        self.history = history
        self.pending = pending
        self.store = store
        # A6b2a: the injected feed port (`pending()`/`handle(seq)`/`snapshot()`, called off the UI thread) or None.
        # Without one every behaviour and text below is byte-identical to the owner-only chat.
        self.feed = feed
        self._header = ChatHeader()
        self._state = ChatState()
        self._guard = threading.Lock()
        self._inbox = deque()  # ordered pending items; only streamed events are bounded (a drop skips control ones)
        self._streamed = 0  # streamed `event` items queued right now (bounded by `pending`)
        self._wake = False
        self._architect = None
        self._work = None
        self._mode = None            # the activity `_work` runs: None | "owner" | "reset" | "check"
        self._in_turn = False        # a cancellable turn runs (owner, reset, an event turn) — not a bare feed check
        self._turn_at = 0.0          # U1b: `time.monotonic()` when that turn began (read only with `_in_turn`)
        self._waiting = None         # C4: the one owner message waiting behind an event check: (text, snapshot)
        self._check_requested = False  # a check is due (on open, after a turn, or from `notify`)
        self._held = False           # C3: event checks stopped after a failure until an owner turn completes or a reset
        self._cancelled = False
        self._closing = False

    # state --------------------------------------------------------------------

    @property
    def state(self):
        state = self._state
        if state.running and state.started:
            state = replace(state, elapsed=max(time.monotonic() - state.started, 0.0))
        return state

    @property
    def ready(self):
        return self._state.phase == "ready"

    @property
    def busy(self):
        """True while a send or a reset holds the conversation (the lock is taken by the architect call)."""
        return self._work is not None

    @property
    def turn_running(self):
        """U1b: True while an architect turn runs (an owner turn, an event turn after its check promoted the batch, a
        reset's turns); a bare event check waiting in `pending()` is `busy` but not a turn."""
        return self._in_turn

    @property
    def turn_started(self):
        """U1b: `time.monotonic()` at the start of the turn `turn_running` reports, so the bar's clock counts from
        the turn itself, not from the first look that happens to see it (a queued owner turn can start in the same
        UI step that ends an event turn)."""
        return self._turn_at

    @property
    def turn_thread(self):
        """The thread of the running send/reset, or None; the test asserts turns never run on the controller worker."""
        return self._work

    @property
    def queued(self):
        """Streamed events of a turn waiting for the UI thread (bounded by `pending`); the handful of control
        messages one turn sends (history, stamp, usage, header, note, done) are kept apart and never evicted by a
        flood."""
        with self._guard:
            return self._streamed

    # preparation --------------------------------------------------------------

    def start(self):
        """Begin the preparation on its own thread; the pane shows "preparing chat…" until it is done."""
        self._prepare_thread()

    def retry(self):
        """A blocked chat prepares again after readiness may have been fixed (setup, login, a recheck): on its own
        thread and without a turn, so a fixed toolchain, login or role is picked up without restarting the app. A
        ready chat, or one already preparing, is left alone."""
        with self._guard:
            if self._state.phase != "blocked":
                return
            self._state = replace(self._state, phase="preparing", refusal="")
        self._changed()
        self._prepare_thread()

    def _prepare_thread(self):
        threading.Thread(target=self._prepare, name="zplan-chat-prepare", daemon=True).start()

    def _prepare(self):
        try:
            store = self._store()
            self._send(("history", store.transcript()))
        except (Blocked, OSError, ValueError) as error:
            self._send(("blocked", refusal(error)))
            return
        try:
            prepared = self.prepare()
        except (Blocked, OSError, ValueError) as error:
            self._send(("blocked", refusal(error)))
            return
        architect, header = prepared
        self._header = header
        if architect.store is not None:
            self.store = architect.store  # one directory and one lock for the store reads of this chat
        self._send(("ready", architect, header))
        self._sync()

    def _store(self):
        store = self.store
        if store is None:
            store = ArchitectStore(self.project)
            self.store = store
        return store

    def _sync(self, pending=None):
        """Reload the transcript and the usage counters from the store (before a send/reset and after a turn).

        `pending` is the owner line of the turn about to start: the reload carries the other window's rows, so our
        own message is re-applied on top of it and never disappears while the turn runs."""
        store = self._store()
        self._send(("history", store.transcript()))
        if pending is not None:
            self._send(("entry", pending))
        self._send(("usage", usage_counts(store.load())))

    # owner operations ---------------------------------------------------------

    def send(self, message, snapshot=None):
        """One owner message = one turn on its own thread. Returns (accepted, refusal line); nothing is queued when
        the chat refuses and the refusal stays on screen. The owner's line appears at once; the transcript is
        reloaded from the store when the turn ends.

        A6b2a C4: while an event check or an event turn runs (mode `"check"`) the owner's message is accepted and
        waits its turn — one message only, shown at once with the waiting note — and runs before any further check;
        a second waiting message is refused as busy, and while the owner's own turn runs `send` refuses as before."""
        text = str(message or "").strip()
        if not text:
            return self._refuse(refusal(Blocked("The empty message to the architect was not sent.",
                                                family="architect.empty_message")))
        if self._state.phase == "preparing":
            return self._refuse("Chat is still preparing: " + PREPARING)
        if self._state.phase != "ready":
            return self._refuse(self._state.refusal or CHAT_UNAVAILABLE)
        if self._closing:
            return self._refuse(refusal(Blocked("Exiting: new messages are not sent.",
                                                family="architect.closing")))
        if self.busy:
            with self._guard:
                if self._mode == "check" and self._waiting is None:
                    self._waiting = (text, snapshot)
                    queued = True
                else:
                    queued = False
            if queued:
                self._write(replace(self._state, note=WAITING,
                                    entries=(self._state.entries + (owner_entry(text, self._state.transcript),))[-self.history:]))
                self._changed()
                return True, ""
            return self._refuse(refusal(Blocked("The architect is already answering: wait for the reply or cancel the turn [esc].",
                                                family="architect.busy")))
        self._cancelled = False
        self._mode = "owner"
        self._enter_turn()
        self._write(replace(self._state, running=True, started=time.monotonic(), live="", note="",
                            entries=(self._state.entries + (owner_entry(text, self._state.transcript),))[-self.history:]))
        self._launch(threading.Thread(target=self._turn, args=(text, snapshot), name="zplan-chat-turn", daemon=True))
        self._changed()
        return True, ""

    def _launch(self, thread):
        """Make `thread` the `_work` and start it under one guard; `wait` reads `_work` under the same guard, so it
        never sees a thread that was not started (joining one raises)."""
        with self._guard:
            self._work = thread
            thread.start()

    def _enter_turn(self):
        self._turn_at = time.monotonic()  # before the flag: a reader that sees the turn sees its start
        self._in_turn = True

    def reset(self):
        """Start a new architect session (the transcript keeps its reset entry). Refused while a turn runs."""
        return self._start_reset(self._reset, (), "Starting a new conversation…")

    def new_session(self, snapshot=None):
        """A8b, `/new` and Ctrl+R: a fresh architect session that does not start blind. One handoff turn asks the
        architect to save the project STATE, the thread is forgotten, and one warm-up turn in the new thread carries
        the STATE and `snapshot`. Refused exactly like `reset`."""
        return self._start_reset(self._new_session, (snapshot,), "Saving the handoff and starting a new conversation…")

    def _start_reset(self, target, args, note):
        if self._closing:
            return self._refuse(refusal(Blocked("Exiting: a new conversation is not started.",
                                                family="architect.closing")))
        if self.busy:
            return self._refuse(refusal(Blocked("The architect is answering: the new conversation starts after the turn.",
                                                family="architect.busy")))
        if self._state.phase != "ready":
            return self._refuse(self._state.refusal or ("Chat is still preparing: " + PREPARING))
        self._cancelled = False
        self._mode = "reset"
        self._enter_turn()
        self._write(replace(self._state, note=note))
        self._launch(threading.Thread(target=target, args=args, name="zplan-chat-reset", daemon=True))
        self._changed()
        return True, ""

    def shutdown(self):
        """Quit began: no further send or reset is accepted, whether or not a turn still runs."""
        with self._guard:
            self._closing = True

    def cancel(self, notify=True):
        """Cancel the running turn (never a milestone: this chat has no milestone handle). False when none runs."""
        with self._guard:
            # A6b2a: a bare feed check has no turn to cancel; an event turn, an owner turn and a reset all do.
            if self._work is None or not self._in_turn:
                return False
            self._cancelled = True
            architect = self._architect
        if architect is not None:
            architect.cancel()  # SIGTERM now, SIGKILL after the grace; the turn's own group only
        if notify:
            self._note("Cancelling the turn…")
            self._changed()
        return True

    def wait(self, timeout=QUIT_GRACE):
        """Wait (bounded) for the operation in flight; False when it outlived the wait."""
        with self._guard:
            work = self._work
        if work is not None:
            work.join(timeout)
        return work is None or not work.is_alive()

    def close(self, timeout=QUIT_GRACE):
        """Leave: cancel the turn if one runs and wait a bounded time, so no process outlives the app. `timeout` is
        what is left of the exit budget when [ctrl+q] started one, QUIT_GRACE otherwise."""
        if self.busy:
            self.cancel(notify=False)
            self.wait(timeout)

    # worker -------------------------------------------------------------------

    def _rebind(self, architect):
        """Re-read the effective architect role and the header prefix, and hand both to the adapter before the turn
        is reserved.

        The process profile and the Codex config may change between turns (a role edited, the file removed, another
        `model_provider` in CODEX_HOME): the conversation and the header follow the current binding and the provider
        the turn's own process reads, not the ones the chat was prepared with. A profile the chat cannot read ends
        the turn as a catalog refusal before any Codex process exists. Resolved on this chat thread, never on the UI
        event loop."""
        model, effort = self.binding()
        architect.model, architect.effort = str(model), str(effort)
        self._show_header(architect)

    def _show_header(self, architect):
        """Re-read the home/provider the next turn will use (`live_header`) and hand the header to the UI.

        Runs on the chat thread after a rebind and after a reset: the header always shows `next_home()`, so a
        continuation keeps its recorded home and a reset returns to the current one (R-5). A home whose provider
        cannot be read shows "?"; a store that cannot be read at all keeps the prepared fields."""
        live = live_header(architect)
        self._header = replace(live or self._header, model=architect.model, effort=architect.effort)
        if self._header.line:
            self._send(("header", self._header))

    def _turn(self, message, snapshot, role="owner", owner=True, ack=None, last=True):
        """One turn off the UI thread: an owner message (`owner` True, the default) or an event-driven turn
        (`owner` False, `role` "events", `ack` the batch's last seq to acknowledge when it completed).

        Returns True when the turn completed. An owner turn shows and stamps its own optimistic line first; an event
        turn has none (its "events" row is written by the store before Codex starts, and comes back on the reload).
        A completed event turn with `ack` acknowledges the feed batch (`handle`); a failed ack is a note and holds
        the checks like any other failure. `last` False (the turns inside `_new_session`) leaves the activity open: the
        caller sends the `done`."""
        architect = self._architect
        reserved = False
        completed = False
        try:
            self._rebind(architect)  # the effective role again: the profile may have changed since the last turn
            if owner:
                # the other window's turns, with our own line kept on top: the line's own occurrence is the place
                # the reload will carry it at (the store's role-row count when the turn started)
                occurrence = self._state.transcript
                self._sync(owner_entry(message, occurrence))
                # i9/A5 repair: the optimistic line above carries no `ts` — the store only gets one when the turn
                # writes the row. Stamp it from there while the turn runs (the row is written before Codex starts).
                threading.Thread(target=self._stamp_owner_line, args=(occurrence, message), name="zplan-chat-stamp",
                                 daemon=True).start()
            with self._guard:
                cancelled = self._cancelled
                if not cancelled:  # reserve under the chat lock: `cancel` takes it too, so it cannot slip in here
                    architect.begin()
                    reserved = True
            if cancelled:  # cancelled after Enter, before Codex existed: no process is started at all
                self._send(("note", "Turn cancelled before Codex started: the message was not sent."))
            else:
                result = architect.run(message, snapshot=snapshot, on_event=self._on_event, role=role)
                completed = result.status == "completed"
                if not completed:
                    self._send(("note", result.cause or "The architect's turn did not finish."))
                elif ack is not None:
                    try:  # A6b2a C3: the completed event turn acknowledges everything up to the batch's last seq
                        self.feed.handle(ack)
                    except (Blocked, OSError, ValueError) as error:
                        completed = False
                        self._send(("note", refusal(error)))
        except (Blocked, OSError, ValueError) as error:
            self._send(("note", refusal(error)))
        finally:
            if reserved:
                architect.finish()
            self._sync_later()
            if last:
                self._send(("done", "owner" if owner else "event", completed))
        return completed

    def _check(self):
        """A6b2a C3, off the UI thread: one event check. Read the whole pending list, keep its batch, and run one
        event turn only when the batch holds a wake event; otherwise no turn and no ack. A port error (`pending` or
        `snapshot` raising) is a note and no turn; an ack that raises is a note and no completion. Either one holds
        the checks (C3) until an owner turn completes or a reset. A shutdown that begins while the check waits in
        `pending`/`snapshot` wins over the promotion: the batch is not promoted and no turn is launched, so a check
        already in flight cannot start Codex after `close()` returned."""
        port = self.feed
        try:
            events = port.pending()
        except (Blocked, OSError, ValueError) as error:
            self._send(("note", refusal(error)))
            self._send(("done", "check", False))
            return
        events, rest = feed.batch(events)
        if not any(event.get("wake") for event in events):
            self._send(("done", "check", True))  # nothing to hand over, and nothing acknowledged
            return
        try:
            snapshot = port.snapshot()
        except (Blocked, OSError, ValueError) as error:
            self._send(("note", refusal(error)))
            self._send(("done", "check", False))
            return
        try:  # C1a: the status rides the turn; one that cannot be read never blocks or fails it
            status = port.status()
        except (Blocked, OSError, ValueError):
            status = {}
        with self._guard:
            # C4: a message the owner sent while this check ran waits in `_waiting` and must run before the check
            # promotes its batch into an event turn. Read the slots and claim the turn under one lock: a send that
            # still lands afterwards is a send during the event turn, which the same owner-first rule queues.
            waiting = self._waiting is not None
            closing = self._closing
            if not waiting and not closing:
                self._cancelled = False
                self._enter_turn()
        if closing:
            # C-5: quit began while this bare check waited in `pending()`/`snapshot()`. Shutdown is honoured under
            # the same lock as the promotion, so the check releases the activity without launching: `close()` must
            # never be followed by a Codex process (`cancel` cannot reach a bare check — it has no turn).
            self._send(("done", "check", True))
            return
        if waiting:
            # Nothing promoted and nothing acknowledged: the batch stays pending for the check the owner's turn
            # asks for (`_after` requests one when that turn ends).
            self._send(("done", "check", True))
            return
        self._send(("start",))
        self._turn(feed.summary(events, rest, status), snapshot, role="events", owner=False, ack=events[-1]["seq"])

    def _reset(self):
        try:
            self._forget(self._architect)
        finally:
            self._sync_later()
            self._send(("done", "reset", True))

    def _forget(self, architect, lead=""):
        """Forget the architect's thread and say so (after `lead`); False when the reset was refused (the note is the
        refusal)."""
        try:
            self._sync()
            architect.reset()
        except (Blocked, OSError, ValueError) as error:
            self._send(("note", refusal(error)))
            return False
        # O4: the pane drops everything before the reset row now, not after the warm-up turn: reload, and clear the
        # handoff turn's streamed text and the old note.
        self._sync_later()
        self._send(("fresh", lead + "New conversation: the previous thread id is forgotten."))
        # R-5: the next turn starts in the current home, so the header follows the reset (`next_home()` no
        # longer answers the previous thread's home).
        self._show_header(architect)
        return True

    def _new_session(self, snapshot):
        """A8b, off the UI thread: handoff turn, reset, warm-up turn. A handoff that failed or was cancelled does not
        block the reset (the note says so); a quit that began meanwhile (or a refused reset) skips the warm-up, so no
        Codex process starts after `close()`."""
        try:
            saved = self._turn(HANDOFF_MESSAGE, snapshot, role=PROMPT_ROLE, owner=False, last=False)
            with self._guard:
                self._cancelled = False  # an [esc] that cut the handoff must not cancel the warm-up too
                closing = self._closing
            if self._forget(self._architect, "" if saved else HANDOFF_FAILED + " ") and not closing:
                self._turn(self._warmup(snapshot), snapshot, role=PROMPT_ROLE, owner=False, last=False)
        finally:
            self._sync_later()
            self._send(("done", "reset", True))

    def _warmup(self, snapshot):
        """The warm-up message: the project STATE ("(none)" when empty or unreadable) and the snapshot."""
        try:
            state = project_state.read(self.project).strip() or NO_STATE
        except (OSError, ValueError):
            state = NO_STATE
        return WARMUP_MESSAGE % (state, json.dumps(snapshot, ensure_ascii=False, sort_keys=True, default=str))

    def _sync_later(self):
        """Best effort: a store read that fails after a turn or a reset must still release `busy` and let the next
        send in; the refusal takes the place of the reload it could not do."""
        try:
            self._sync()
        except (Blocked, OSError, ValueError) as error:
            self._send(("note", refusal(error)))

    def _on_event(self, event):
        self._send(("event", event))

    # events (A6b2a) -----------------------------------------------------------

    def notify(self):
        """Thread-safe: an observation was just made, so ask the chat to check the feed — a no-op without a port,
        before the chat is ready or while it is closing. A notify that lands while a check or a turn runs is
        remembered (`_check_requested`), so one more check runs right after, and a wake event written during a check
        is never missed. The decision runs on the UI thread through the hand-over, never here."""
        if self.feed is None or self._state.phase != "ready":
            return
        with self._guard:
            if self._closing:
                return
            self._check_requested = True
        self.hand_over(self._advance)

    def _advance(self):
        """UI thread: start the next activity — the one waiting owner message first (C4), else one requested event
        check. Never starts two at once; a check is skipped while the checks are held (C3)."""
        if self._closing:
            return
        if self._work is not None:
            return
        if self._waiting is not None:
            text, snapshot = self._waiting
            self._waiting = None
            self._cancelled = False
            self._mode = "owner"
            self._enter_turn()
            self._write(replace(self._state, running=True, started=time.monotonic(), live="", note=""))
            self._launch(threading.Thread(target=self._turn, args=(text, snapshot), name="zplan-chat-turn", daemon=True))
            self._changed()
            return
        if self.feed is None or self._held or not self._check_requested or self._state.phase != "ready":
            return
        self._check_requested = False
        self._mode = "check"
        self._launch(threading.Thread(target=self._check, name="zplan-chat-check", daemon=True))

    def _after(self, what, ok):
        """UI thread: an activity ended. C3 — a failed check, a turn that did not complete or a failed ack holds
        the checks until an owner turn completes or a reset; "after every turn ends" asks for the next check."""
        if what == "check":
            if not ok:
                self._held = True
        else:
            if what == "reset" or (what == "owner" and ok):
                self._held = False
            elif not ok:
                self._held = True
            self._check_requested = True
        self._advance()

    def _stamp_owner_line(self, occurrence, message):
        """i9/A5: put the store's own `ts` on the running turn's line, while the turn still runs.

        The line `send` posts is the optimistic one — the owner row it will reconcile with does not exist yet — so
        it carries no time. The turn writes that row before Codex starts (`architect._turn`), so
        the store holds the message with its time a moment later: re-read the transcript until the row at this
        turn's own place in it (`occurrence`) appears and hand the UI the `ts` of that row alone (`stamp`), which
        stamps the entry standing at that place — same place in the window, now with its time — and the entry
        can stand behind a time line for the rest of the turn. A targeted stamp, never a whole reload: a re-read can finish
        after the turn's own reload has already brought the reply back, and replacing the entries with such a
        captured window would drop that reply from the UI (it stays in the store, but the window would lie until the
        next reload). Bounded and quiet: a store that cannot be read, and a message the turn never persisted
        (cancelled before the write), leave the optimistic line for the turn's own reload to settle."""
        store = self._store()
        deadline = time.monotonic() + STAMP_SECONDS
        while time.monotonic() < deadline and not self._cancelled:
            try:
                rows = store.transcript()
            except (Blocked, OSError, ValueError):
                return
            roles = [row for row in rows if isinstance(row, dict) and row.get("role") in ROLES]
            for index in range(occurrence, len(roles)):
                row = roles[index]
                if row.get("role") == "owner" and row.get("text") == message:
                    self._send(("stamp", index, row.get("ts")))
                    return
            time.sleep(STAMP_EVERY)

    # UI thread ----------------------------------------------------------------

    def _send(self, item):
        """From a worker thread: queue one item, coalesced under the bounded inbox, and wake the UI at most once.

        A stream of `event` items is coalesced by dropping the oldest *event*, so memory and the UI queue stay
        bounded. A control message (history, stamp, usage, header, blocked, entry, note, done) is never evicted by
        that flood: the rebind header and the turn's end must always arrive, whatever the streamed text does."""
        with self._guard:
            self._inbox.append(item)
            if item[0] == "event":
                self._streamed += 1
                if self._streamed > self.pending:
                    self._drop_oldest_event()
            if self._wake:
                return
            self._wake = True
        self.hand_over(self._drain)

    def _drop_oldest_event(self):
        """Drop one streamed event (the oldest), keeping every control message where it is. Called with `_guard`."""
        for index, queued in enumerate(self._inbox):
            if queued[0] == "event":
                del self._inbox[index]
                self._streamed -= 1
                return

    def _drain(self):
        """UI thread: apply everything queued so far, in arrival order, and repaint once."""
        with self._guard:
            items, self._wake, self._streamed = list(self._inbox), False, 0
            self._inbox.clear()  # one place enforces the cap on streamed events
        for item in items:
            self._apply(item)
        self._changed()

    def _apply(self, item):
        kind = item[0]
        if kind == "history":
            rows = item[1]
            self._state = replace(self._state, entries=entries_of(rows, self.history),
                                  transcript=transcript_size(rows))
        elif kind == "stamp":
            # i9/A5 repair: the running turn's own line, stamped from the row the turn wrote. A targeted merge of
            # that one `ts` — `occurrence` names the entry — never a whole reload, so a re-read that finished
            # before the reply landed cannot replace a newer window and drop the reply from the UI.
            index, at = item[1], item[2]
            entries = tuple(replace(entry, at=at)
                            if isinstance(at, str) and at and entry.occurrence == index and entry.role == "owner" and not entry.at
                            else entry for entry in self._state.entries)
            self._state = replace(self._state, entries=entries)
        elif kind == "usage":
            self._state = replace(self._state, usage=item[1])
        elif kind == "ready":
            self._architect = item[1]
            self._state = replace(self._state, phase="ready", header=item[2].line, header_fields=item[2],
                                  refusal="")
            # A6b2a C3: catch-up on open — once ready, look for events that accumulated while no turn ran.
            self._check_requested = True
            self._advance()
        elif kind == "header":
            self._state = replace(self._state, header=item[1].line, header_fields=item[1])
        elif kind == "blocked":
            self._state = replace(self._state, phase="blocked", refusal=item[1])
        elif kind == "entry":
            self._state = replace(self._state, entries=(self._state.entries + (item[1],))[-self.history:])
        elif kind == "event":
            event = item[1]
            text = event.get("text") if isinstance(event, dict) else None
            # Every non-empty text is kept as it came: a streamed `\t` or a lone control character is text the
            # model sent, and L-2 shows it as its escape — `strip()` here would drop the event and leave the
            # previous line up, as if the model had said nothing at all.
            if isinstance(text, str) and text:
                self._state = replace(self._state, live=text[-LIVE_CHARS:])
        elif kind == "note":
            self._state = replace(self._state, note=item[1][:NOTE_CHARS])
        elif kind == "fresh":
            self._state = replace(self._state, note=item[1][:NOTE_CHARS], live="")
        elif kind == "start":
            # A6b2a C3: an event check decided to run an event turn; show it as a running turn like any other.
            self._state = replace(self._state, running=True, started=time.monotonic(), live="", note="")
        elif kind == "done":
            self._state = replace(self._state, running=False, started=0.0, elapsed=0.0, live="")
            with self._guard:
                self._in_turn = False
            self._mode = None
            self._work = None
            self._after(item[1], item[2])

    def _write(self, state):
        self._state = state

    def _note(self, text):
        self._state = replace(self._state, note=str(text)[:NOTE_CHARS])

    def _refuse(self, line):
        """Show a refusal on the chat line and report it; called on the UI thread from send/reset."""
        self._note(line)
        self._changed()
        return False, line

    def _changed(self):
        self.on_change()


# S1: an `events` entry is shown as steps. The tone of a plan status / run state picks the glyph and the colour the
# pane draws (ok ✓ green, run ▶ cyan, bad ! red, idle · dim); the words are the `step.plan.*` / `step.run.*` ids.
PLAN_TONES = {"planning": "run", "submission_unknown": "run", "observing": "run", "observation_blocked": "bad",
              "detached": "bad", "run_failed": "bad", "proposal_invalid": "bad", "review_exhausted": "bad",
              "proposed": "ok", "approved": "ok", "stopped": "bad"}
RUN_TONES = {"waiting": "idle", "ready": "idle", "unknown": "idle", "preparing": "run", "submission_unknown": "run",
             "submitted": "run", "running": "run", "stopping": "run", "resume_pending": "run", "finished": "ok",
             "integrated": "ok", "awaiting_merge": "ok", "stopped": "bad", "conflict": "bad", "needs_owner": "bad",
             "blocked": "bad", "failed_recoverable": "bad", "failed": "bad"}
VERDICT_PASS = ("approve", "approved", "accepted")  # a reviewer's verdict that passes; any other is a remark
STEP_GAP = "  "  # between a step's words and its dim detail
STEP_JOIN = " · "
# The wake-event line shapes `feed.summary` writes (`feed._event_line`), the head, the idle count and the rest count.
PLAN_LINE = re.compile(r"plan r(\d+): (\S+) -> (\S+)")
STATE_LINE = re.compile(r"(\S+) attempt (\S+): (\S+) -> (\S+)")
VERDICT_LINE = re.compile(r"(\S+) (\S+) round (\S+) (\S+): (\S+) —(?: (.*))?")
# The same shapes as 0.7.x wrote them into stored `events` rows (Russian): the head, the idle count and the rest count
# too. `step_of` accepts both forms.
LEGACY_PLAN_LINE = re.compile(r"план r(\d+): (\S+) -> (\S+)")
LEGACY_STATE_LINE = re.compile(r"(\S+) попытка (\S+): (\S+) -> (\S+)")
LEGACY_VERDICT_LINE = re.compile(r"(\S+) (\S+) раунд (\S+) (\S+): (\S+) —(?: (.*))?")
LEGACY_EVENT_HEAD = "События с прошлого хода:"
LEGACY_EVENT_IDLE = re.compile(r"Промежуточных состояний без действия: (\d+)\.")
LEGACY_EVENT_REST = re.compile(r"… и ещё (\d+) событий\.")


def _counted(line, count):
    """The pattern of a `feed.summary` line that holds `count` as its one number, taken from the line itself."""
    return re.compile(re.escape(line).replace(str(count), r"(\d+)"))


EVENT_HEAD = feed.summary([], 0).split("\n")[0]
EVENT_IDLE = _counted(feed.summary([{"wake": False}], 0).split("\n")[1], 1)
EVENT_REST = _counted(feed.summary([], 12345).split("\n")[1], 12345)


def step_of(line):
    """S1: one line of an `events` entry as a step `(tone, words, detail)`, or None for a line that is no step (the
    head line and the idle count). The line is the architect's text, `feed.summary`'s wake-event line: a plan event
    `plan r1: proposed -> approved` is `ok, "Plan r1 approved"`, a state event `M1 attempt 2: running -> failed` is
    `bad, "M1 failed", "attempt 2"` and a verdict `M1 T1 round 2 reviewer: approve — ok` is
    `ok, "M1 check passed", "round 2 · ok"` (the texts are the catalog's; 0.7.x's Russian line forms parse alike). A status or state the tables do not know, and any other line, is a
    dim `idle` step that keeps the transition (`M1: a -> b`) or the line itself."""
    line = line.strip()
    if not line or line in (EVENT_HEAD, LEGACY_EVENT_HEAD) or EVENT_IDLE.fullmatch(line) \
            or LEGACY_EVENT_IDLE.fullmatch(line):
        return None
    more = EVENT_REST.fullmatch(line) or LEGACY_EVENT_REST.fullmatch(line)
    if more:
        return "more", strings.text("step.more", count=more.group(1)), ""
    found = PLAN_LINE.fullmatch(line) or LEGACY_PLAN_LINE.fullmatch(line)
    if found:
        revision, _, status = found.groups()
        if status in PLAN_TONES:
            words = strings.text("step.plan", revision=revision, word=strings.text("step.plan." + status))
            return PLAN_TONES[status], words, ""
        return "idle", line, ""
    found = VERDICT_LINE.fullmatch(line) or LEGACY_VERDICT_LINE.fullmatch(line)
    if found:
        milestone, _, rounds, _, verdict, text = found.groups()
        passed = verdict in VERDICT_PASS
        words = strings.text("step.verdict_ok" if passed else "step.verdict_bad", milestone=milestone)
        parts = ([strings.text("step.round", round=rounds)] if rounds != "—" else []) + ([text] if text else [])
        return ("ok" if passed else "bad"), words, STEP_JOIN.join(parts)
    found = STATE_LINE.fullmatch(line) or LEGACY_STATE_LINE.fullmatch(line)
    if found:
        milestone, attempt, previous, state = found.groups()
        if state in RUN_TONES:
            return RUN_TONES[state], milestone + " " + strings.text("step.run." + state), \
                strings.text("step.attempt", attempt=attempt)
        return "idle", "%s: %s -> %s" % (milestone, previous, state), ""
    return "idle", line, ""


def step_blocks(text):
    """S1: the display blocks of an `events` entry's text, one `step_<tone>` block per step line (`step_of`); the
    block text is the words, then `STEP_GAP` and the detail when there is one. The entry's own text is untouched."""
    blocks = []
    for line in text.split("\n"):
        step = step_of(line)
        if step is not None:
            tone, words, detail = step
            blocks.append(("step_" + tone, words + STEP_GAP + detail if detail else words))
    return blocks


def entry_blocks(entry):
    """V2: one transcript entry as display blocks `(kind, text)`, in order. `text` is the narrative as the reply
    wrote it (`"text"`, rendered as Markdown for an architect), `draft` a labelled draft line — the collapsed lines
    at their block's own position, then one per draft that was not collapsed — and `partial` the marked last text of
    a turn that did not complete. Nothing in the text is escaped here: L-2 runs on each block's raw lines before
    the pane draws it. S1: an `events` entry is `step_blocks` instead."""
    if entry.role == "events":
        return step_blocks(entry.text)
    blocks = []
    if entry.sections:
        for head, label, body in entry.sections:
            if label:
                blocks.append(("draft", label + body))
            elif head.startswith("…") or body:  # the clip marker stands even when its section is all that is left
                blocks.append(("text", (head if head.startswith("…") else "") + body))
    elif entry.text:
        blocks.append(("text", entry.text))
    if entry.partial:
        blocks.append(("partial", "(" + strings.text("chat.partial") + "): " + entry.partial))
    for index, draft in enumerate(entry.drafts):
        if index not in entry.matched:  # already shown in the text, at the block's own position
            blocks.append(("draft", DRAFT_MARK + draft_line(draft)))
    return blocks


def draft_line(draft):
    """One draft as the pane labels it: its kind, the milestone of an answer, then the draft text itself."""
    return draft_label(draft) + draft.text
