"""The decision cards' kinds (S1 of 0.5.2, the card split of `app.py`): the shared card registries (`CARD_SOURCES`,
`CARD_ROUTES`, `AUTO_END_CARDS`, `COMMAND_ACTIONS`), the module-level helpers every card kind reads, and the sources,
routes and registrations of the merge, question, plan, ready and failed cards. A card run adds its rows here.

A pure move out of `app.py`: `app` imports this module and re-exports every name, so `app.X is card_kinds.X`. Imports
run one way (app -> card_host -> card_kinds); nothing here imports `app` at import time."""

import hashlib
from dataclasses import replace
import re
import time

from rich.text import Text
from textual.binding import Binding
from textual.containers import HorizontalGroup, VerticalGroup
from textual.message import Message
from textual.widgets import Button, Static

from .. import autonomy
from ..cli import summary
from ..project_read import shown_paths
from ..user_commit import STAMP as COMMIT_STAMP
from . import cards, chat as chat_module, strings
from .modals import NoteScreen
from .text import ELLIPSIS, display_width, elide_end, plain_lines, wrapped

TAB_LIVE = "tab-live"  # never `#plan`/`#live`: the pane bodies keep those ids (`app` pairs it with `TAB_PLAN`)
STATUS_SHARE = 0.4  # #status is capped at 40% of the left pane (zplan.tcss): more lines would be cut from the bottom
NOT_STARTED_BELOW = "Not started: fix the items marked below first."  # the marked items follow the message
EMPTY_ANSWER = "Empty answer: no new attempt was started."
MOVED = "The state changed while the screen was open: the current one is shown."
FIX_KEY = re.compile(r"\s+—\s+\[i\].*$")  # [i] of the plain readiness screen does not exist in the form


# i2: the `/` commands this run wires to the existing actions (command name -> callable(screen, argument, key)). The
# entry convention is the same for both paths (i3a): a `/` line typed in the chat and a card button both come through
# `MainScreen.run_command`, which is the only caller — `argument` is the parsed argument ("" when there is none) and
# `key` the card the command came from (None: a typed line, which acts on the newest card of that kind). A `Submitted`
# command absent from here shows `note.not_now` like a refusal; later runs add one entry each. i3a
# wires /plan and /decline to the draft card and /open and /diff to the canvas tabs (/diff used to reach
# `action_open_milestone`; i5's `open_diff_tab` is what it names now).
# `/language CODE` passes the typed code to i6's `choose_language(code)`; a bare `/language` opens the chooser.
def card_kind(key):
    """The kind of a card key: its prefix before `:` (`draft:<hash>` -> `draft`)."""
    return key.split(":", 1)[0]


def token_run_id(outcome):
    """The run identity of the attempt an outcome carries (`None` when it carries no Token): the observation of a
    just-started or re-attached attempt begins with it, so its first slice is attributed to this attempt and never
    to a finished one (C4)."""
    data = getattr(outcome, "data", None)
    return getattr(data, "run_id", None)


# Shared card hooks, frozen at the i3a merge (one owner: the orchestrator; card runs only add their own rows).
# CARD_ROUTES: commands several card kinds share (/approve, /decline) -> {(command, kind): callable(screen, argument,
# key)}. CARD_SOURCES: {kind: callable(screen) -> iterable of CardSpec}; `render_state` shows what a source returns and
# takes off that kind's open cards it no longer returns, so a stale card never acts. AUTO_END_CARDS: the end states
# (`EndView.state`) whose automatic RunScreen at the end of a watch is replaced by their card; [o] still opens it.
CARD_ROUTES = {("/decline", "draft"): lambda screen, argument, key: screen.action_decline(argument, key)}
CARD_SOURCES = {}
AUTO_END_CARDS = set()  # a card run adds its states: AUTO_END_CARDS.add("awaiting_merge")


def card_route(command, fallback=None):
    """A shared command's entry: the card `key` names its kind's route; a typed line (key None) acts on the newest
    open card whose kind routes `command`. With no such card the `fallback` runs, or `note.not_now`."""
    def act(screen, argument, key):
        if key is None:
            key = screen.newest_card_for(command)
        route = CARD_ROUTES.get((command, card_kind(key))) if key is not None else None
        if route is not None:
            return route(screen, argument, key)
        if fallback is not None:
            return fallback(screen, argument, key)
        screen.status_note(strings.text("note.not_now", name=command))
    return act


COMMAND_ACTIONS = {
    "/help": lambda screen, argument, key: screen.app.action_help(),
    "/quit": lambda screen, argument, key: screen.app.run_worker(screen.app.action_quit()),
    "/stop": lambda screen, argument, key: screen.stop_running_row(),
    "/new": lambda screen, argument, key: screen.action_reset_session(),
    "/setup": lambda screen, argument, key: screen.app.action_settings(),
    "/status": lambda screen, argument, key: screen.show_status(),
    "/approve": card_route("/approve", lambda screen, argument, key: screen.app.action_open_plan()),
    # K1a: the plan pane's former letter keys, typed in the chat (`/run` is registered in app.py beside its action)
    "/view": lambda screen, argument, key: screen.app.action_open_plan(),
    "/attempt": lambda screen, argument, key: screen.app.action_open_milestone(),
    "/answer": lambda screen, argument, key: screen.app.action_open_answer_draft(),
    "/log": lambda screen, argument, key: screen.app.action_tail_activity(),
    "/merge": lambda screen, argument, key: screen.app.action_open_milestone(),
    "/plan": lambda screen, argument, key: screen.action_plan(argument, key),
    "/decline": card_route("/decline"),
    # the error cards' retry button, routed by kind; typed `/retry` acts on the newest card that routes it
    "/retry": card_route("/retry"),
    # typed `/details` is the pane's former [i] unless an error card owns it (the card's route runs as before)
    "/details": card_route("/details", lambda screen, argument, key: screen.app.action_milestone_details()),
    "/scheme": lambda screen, argument, key: screen.toggle_scheme_full(),
    "/open": lambda screen, argument, key: screen.open_file_tab(argument),
    "/diff": lambda screen, argument, key: screen.open_diff_tab(),
    "/language": lambda screen, argument, key: screen.choose_language(argument or None),
    "/theme": lambda screen, argument, key: screen.choose_theme(argument or None),
}


# i2 (code-review repair): the run pane's own notes that are a displayed operation error or blocked result — the
# failed or blocked start/stop verdicts and a lost observation. The note is the only fact the screen holds for them
# (there is no separate status flag), so they are recognised by the prefix every one of those paths writes; an
# ordinary informational note (a pending stop, a watch summary, «… in progress», «… changed») matches none of
# them and stays out of the error state.
RUN_ERROR_PREFIXES = ("Not started:", "Not done:", "Not stopped:", "Watch interrupted:")


def blocked_note(note):
    """The run pane's displayed note when it is an operation error or blocked result, else "" (i2). `slash_state`
    reads it as the screen's `blocked` line, so a failed/blocked operation the pane shows flips the slash state —
    and with it the bar's job — to `error` even while every row is still ready/waiting."""
    text = (note or "").strip()
    return text if text.startswith(RUN_ERROR_PREFIXES) else ""


class RunNote:
    """i6: a pending main-screen status line held as its catalog id and values, never as rendered text. Every paint
    renders it with `strings.text` in the language chosen now, so a language switch relabels the line; the id is
    the line's identity, so the clearing paths recognise it whatever language is in effect (`note_is`).

    `ZplanApp.run_note` holds one of these for the two lines i6 names (a requested stop, a journal being read) and
    a plain string for every other note (the readiness-blocked and failed verdicts, a watch summary): those are not
    catalog lines yet, so they stay literal and are shown as they are."""
    __slots__ = ("id", "values")

    def __init__(self, id, **values):
        self.id, self.values = id, values

    def text(self):
        return strings.text(self.id, **self.values)


def note_text(note):
    """The text a pending `run_note` shows in the language chosen now: a `RunNote` renders its catalog line, every
    other note is already its own text (so the plain-string notes pass through unchanged). K1d: a letter key the
    text names is the TUI step that does it (`command_hints`)."""
    from .app import command_hints  # function-level: app imports this module
    text = note.text() if isinstance(note, RunNote) else note
    return command_hints(text) if isinstance(text, str) else text


CARD_KEY_SEP = "\x1f"  # joins the fields of a card key; a draft's text may hold any printable character


def card_clock():
    """The `HH:MM` the sent receipt carries (i3a): the wall clock when the owner acts.

    The receipt is the moment the planner was started, so it is the clock read then — not the reply's time, which
    is what the open card's own `at` carries (`draft_reply_time`)."""
    return time.strftime("%H:%M")


# i3a: the `HH:MM` inside one stored reply's `ts` (the ISO stamp `architect._stamp` writes, e.g.
# "2026-10-23T08:17:00Z"). P2a: a UTC stamp is shown in the local zone (`chat.stamp_at`), as the sent receipt is.
STAMP_HM = re.compile(r"[T ](\d\d:\d\d)")


def stamp_hm(stamp):
    """The `HH:MM` of one stored `ts`, or "" when it does not name a time (i3a); local time, as the chat rows."""
    return chat_module.stamp_at(stamp)


def draft_card_key(entry, draft, occurrence=None):
    """The stable key of one goal-draft card (i3a): built from the reply the draft came from, the draft's own text
    and the *occurrence* of that reply in the store's transcript — never from `draft.identity` alone, because two
    drafts under one plan (and two drafts of one reply) share the plan identity.

    `occurrence` is the reply's own place (`reply_occurrence`), so two *identical* replies — the same role, text and
    draft, and so the same content — are still two cards: that is the fix for the acceptance finding that the same
    reply repeated under one plan identity was suppressed as already seen. The same stored reply keeps its place
    across refreshes and restarts, so a card is still shown once per reply and a declined reply stays declined.
    Without a place (`occurrence is None`: the store cannot be read, the reply is not stored) the content alone
    decides the key, as before."""
    fields = (entry.role, entry.text, draft.kind, draft.text, repr(draft.identity),
              "" if occurrence is None else str(occurrence))
    return "draft:" + hashlib.sha1(CARD_KEY_SEP.join(fields).encode("utf-8", "replace")).hexdigest()


def reply_occurrence(chat, entry):
    """The place of the stored reply `entry` names in `chat`'s append-only transcript (i3a repair): how many
    role-filtered rows precede the *last* stored row whose role and whole draft record are the entry's own, or None
    when the store cannot be read or carries no such row.

    The count runs from the start of the file, never from the end of the window the pane happens to keep: the window
    slides (a newer row drops an older one out of `HISTORY`), and a distance from its end would move with it, which
    would re-key a declined card and bring it back. The newest card is always the newest actionable draft's reply,
    so the *last* stored row matching the entry is that reply's own — an identical reply stored *after* it is the
    next occurrence and gets the next key."""
    store = getattr(chat, "store", None)
    if store is None:
        return None
    try:
        rows = store.transcript()
    except (OSError, ValueError):
        return None
    found, seen = None, 0
    for row in rows:
        if not isinstance(row, dict) or row.get("role") not in chat_module.ROLES:
            continue
        if row.get("role") == entry.role and chat_module.drafts_of(row) == entry.drafts:
            found = seen
        seen += 1
    return found


def draft_card_of(chat):
    """`(key, draft)` of the newest actionable goal draft of the retained history, or None (i3a).

    The choice itself is `chat.newest_goal_draft` — the one source the `[c]` key reads too — and the key is the
    stable card key of the reply that carries it (`draft_card_key`), with that reply's own place in the store's
    transcript as its occurrence (`reply_occurrence`); a draft whose own reply is not in the retained history cannot
    be keyed and is no card."""
    entries = chat.state.entries
    draft = chat_module.newest_goal_draft(entries)
    if draft is None:
        return None
    position = next((index for index in range(len(entries) - 1, -1, -1) if draft in entries[index].drafts), None)
    if position is None:
        return None
    entry = entries[position]
    return draft_card_key(entry, draft, reply_occurrence(chat, entry)), draft


def draft_reply_time(chat, draft):
    """The `HH:MM` the goal-draft card's `at` carries (i3a/A2): the reply's own time, never the clock the card is
    drawn at.

    The pane's own data names no time (`chat.ChatEntry` has no timestamp), so the reply is found in the store's
    transcript — the same rows `chat.entries_of` built the entry from — by the draft it carries (kind, text,
    milestone and identity all equal), and that row's `ts` gives the time (`stamp_hm`). A store that cannot be
    read, and a draft no stored row carries, fall back to `card_clock()`; the time is read once per key, right
    before the card is shown, so no refresh of a history already carrying a card pays for it."""
    store = getattr(chat, "store", None)
    if store is not None:
        try:
            rows = store.transcript()
        except (OSError, ValueError):
            rows = ()
        for row in reversed(rows):
            if isinstance(row, dict) and row.get("role") == "architect" and draft in chat_module.drafts_of(row):
                time_of = stamp_hm(row.get("ts"))
                if time_of:
                    return time_of
    return card_clock()


def draft_tab_text(draft):
    """The «Goal draft» canvas tab's body: the catalog's intro line and then the draft's whole text, verbatim —
    the exact text the planner gets, so the tab is what the owner is agreeing to. Every line is escaped by
    `plain_lines` (L-2), so a terminal sequence in the draft can never reach the screen; the text itself is not
    changed."""
    return Text("\n".join([strings.text("canvas.draft_intro"), ""] + list(plain_lines(draft.text))))


class DraftCardRequested(Message):
    """i3a: a goal-draft card is to be shown (with its canvas tab) — posted by `MainScreen.refresh_draft_card`.

    The card slot and the canvas live in the pane's layout, so mounting them from inside `render_state` (a
    post-refresh callback) leaves that layout unresolved for a frame: the slot keeps its old rows and the chat body
    keeps the rows the card took. The request is a message instead, handled on the screen's own pump right after
    the refresh it was posted from, so Textual lays the slot, the chat body and the canvas out once and the next
    render reads the settled regions. `key` is the card's stable key, `draft` the goal draft it decides on and `at`
    the reply's own `HH:MM` (`draft_reply_time`), read then so the card's subtitle is the reply's time."""

    def __init__(self, key, draft, at):
        self.key = key
        self.draft = draft
        self.at = at
        super().__init__()


# i3c — the merge card (kind `merge`): the stage-done card of an attempt that is waiting for its merge. Its own rows
# of the shared registries, the command rows `/merge` and `/diff` its two buttons carry, and the helpers the source
# reads; `main` for i3b-i3e keep their own rows for themselves.
MERGE_TASKS = re.compile(r"Tasks:\s*(\d+)\s*/\s*(\d+)")


def merge_key(row, version):
    """The key of the merge card of one row: `merge:r<version>:<milestone>:<attempt>` (i3c). The plan revision and
    the attempt's own number are in the key, so a later revision of the plan — or a later attempt of the same
    stage — is a card of its own."""
    return "merge:r%s:%s:%s" % (version, row.id, row.token.attempt)


def merge_stage(key):
    """The milestone a `merge:` key names (its third field, after the kind and the plan revision)."""
    return key.split(":", 3)[2]


def merge_tasks_counts(end):
    """The `(done, total)` an attempt's EndView carries: the numbers of its own tasks line («Tasks: 2/3
    done», the line `Delivery.tasks_lines` writes into `EndView.body`). None when the view is missing or
    carries no such line — the merge card is then the bare one."""
    for line in getattr(end, "body", ()) or ():
        found = MERGE_TASKS.search(line)
        if found:
            return int(found.group(1)), int(found.group(2))
    return None


def merge_same_attempt(clicked, exported):
    """Whether the token an export answered with names the very attempt the card's click was made on (i3c): the
    milestone, plan revision, attempt and run are the click's own; only the status, outcome and delivery may have
    moved, because the export is exactly that delivery move. An export of another attempt — a revision or a run that
    changed under the click — is not this card's attempt and is never merged."""
    fields = ("milestone", "plan_revision", "attempt", "run_id")
    return (clicked is not None and exported is not None
            and all(getattr(clicked, name) == getattr(exported, name) for name in fields))


def merge_spec(key, at, stage, counts, overlap=()):
    """One merge card: with the counts the w1 builder `cards.merge_card` (its `card.merge_text`), without them the
    same card reading `card.merge_text_bare` — the decision (the title, the two buttons) is the same either way.
    After a landing refused for files of the owner's tree in the way (`overlap`) it is the red card that names them,
    with «merge later» (`/merge later`) and «show the differences»."""
    if overlap:
        return cards.CardSpec(key=key, title=strings.text("card.merge_overlap_title", stage=stage),
                              text=strings.text("card.merge_overlap_text", paths=shown_paths(overlap)),
                              buttons=((strings.text("card.merge_later"), "/merge later"),
                                       (strings.text("card.merge_diff"), "/diff")),
                              hint=None, at=at, done=None, alarm=True)
    if counts is None:
        return cards.CardSpec(key=key, title=strings.text("card.merge_title", stage=stage),
                              text=strings.text("card.merge_text_bare"),
                              buttons=((strings.text("card.merge_yes"), "/merge"),
                                       (strings.text("card.merge_changes"), "/diff")),
                              hint=None, at=at, done=None, alarm=False)
    return cards.merge_card(key, at, stage, str(counts[0]), str(counts[1]))


def merge_card_source(screen):
    """`CARD_SOURCES["merge"]` (i3c): one card per `awaiting_merge` row — the stage is done and the only decision
    left is «merge». A row with no attempt is no attempt of ours: state and token both have to name one.

    The key carries the current plan revision (`snapshot.version`), so a card the owner closed under one revision
    never suppresses the same stage's card under the next one, and every per-key cache (the counts, the `at`) is per
    revision.

    The counts come from that attempt's own EndView (`screen.merge_counts`, one read per key), and that read is
    asked for *only once the attempt is exported* (`token.delivery`): reading the view is what finishes (exports) an
    accepted attempt, and a refresh must never do that — the export stays the owner's own arrival, `[o]`. An
    attempt whose export has not run yet shows the same card without counts, exactly like one whose view carries no
    tasks line."""
    snapshot = getattr(screen.app, "snapshot", None)
    version = None if snapshot is None else snapshot.version
    shown = []
    for row in screen.app.rows():
        if row.state != "awaiting_merge" or row.token is None:
            continue
        key = merge_key(row, version)
        counts = screen.merge_counts(key, row.id) if row.token.delivery == "awaiting_merge" else None
        shown.append(merge_spec(key, screen.merge_card_at(key), row.id, counts, screen.merge_overlap.get(key, ())))
    return shown


def merge_card_open(screen):
    """i3c repair: whether `screen`'s slot holds an open merge card — an undecided card of kind `merge`. A closed
    receipt, or a card of another kind, is no open merge decision."""
    return any(spec.done is None and card_kind(key) == "merge" for key, spec in screen.card_specs.items())


CARD_SOURCES["merge"] = merge_card_source
AUTO_END_CARDS.add("awaiting_merge")  # that end's card replaces the automatic run screen ([o] still opens it)
COMMAND_ACTIONS["/merge"] = lambda screen, argument, key: screen.action_merge(argument, key)
# A typed `/diff` (no key) and a card of another kind keep the canvas diff tab; only the merge card's button
# selects its own stage first.
COMMAND_ACTIONS["/diff"] = lambda screen, argument, key: (
    screen.action_merge_diff(argument, key) if key is not None and card_kind(key) == "merge"
    else screen.open_diff_tab())

# i3d: the owner-question card, registered here (the card contract's parallel rule): the key is
# `question:r<version>:<milestone>:<attempt>`, so a new revision or attempt of a milestone is a new card; the source is
# `MainScreen.question_card_specs`, the shared `/approve` and `/decline` commands are routed to the card's own rows,
# and a `needs_owner` end replaces its automatic end-of-run modal with the card ([o] still opens the modal). The
# three quick answers are the `/approve` arguments the card buttons send; the card text is the end view's own
# question body (the source sizes the shown rows to the card slot and caps them at `QUESTION_LINES`, the task's ≤6
# lines; the draft button keeps its full `card.answer_draft` label and the card wraps its buttons when the row is
# too narrow).
QUESTION_CHOICES = ("simplify", "split", "skip")
QUESTION_LINES = 6
# i3d/A1: the source sizes the question text to the chat pane's own 40% (`STATUS_SHARE`) row budget; the card wraps
# its own buttons (`question_button_rows`), and the source gives back to the text the one row of chrome each wrapped
# button row costs (A3).
QUESTION_CARD_CHROME = 5     # the card's own non-text rows: 2 border + 1 gap + 1 button row + 1 hint
QUESTION_CARD_INSET = 6      # the card's margin(2) + border(2) + padding(2) inside the slot's width


# i3d/A3: the owner-question card's own button row. The shared `cards.Card` (and its one-row `.buttons`) is the
# other kinds' layout and is left untouched, so the question spec is shown through `QuestionCard`, a `cards.Card`
# that re-flows *its own* buttons alone. The full `card.answer_draft` label («send the answer draft») beside
# the three quick answers needs more cells than the 120x40 half-width card's inner 50 holds, so the draft leads
# one row and the quick answers follow on the next — a label is never shortened, dropped or clipped. The
# measurements are the shared card rules of `cards.Card.DEFAULT_CSS` (`Card Button { margin-right: 2; min-width: 6 }`
# plus the two cells `Button.get_content_width` keeps around a label).
QUESTION_BUTTON_CHROME = 4   # what one button adds around its label in a row: its 2-cell margin and its padding
QUESTION_BUTTON_MIN = 6      # `Card Button { min-width: 6 }`


def question_button_cells(label):
    """The cells one question-card button of `label` takes in its row, margin included (`QUESTION_BUTTON_CHROME`)."""
    return max(display_width(label) + 2, QUESTION_BUTTON_MIN) + (QUESTION_BUTTON_CHROME - 2)


def question_button_rows(buttons, width):
    """The buttons grouped into one-row tuples that each fit `width` cells.

    The card lays its buttons left to right and wraps a label onto the next row only when it would not fit, so the
    first row keeps as many labels as the card holds and no label is shortened or dropped. `width <= 0` (no
    laid-out card) keeps every button in one row; the caller sizes the text against the number of rows it gets."""
    buttons = tuple(buttons)
    if width <= 0:
        return (buttons,) if buttons else ()
    rows, row, used = [], [], 0
    for button in buttons:
        cells = question_button_cells(button[0])
        if row and used + cells > width:
            rows.append(tuple(row))
            row, used = [], 0
        row.append(button)
        used += cells
    if row:
        rows.append(tuple(row))
    return tuple(rows)


class _QuestionButton(Button):
    """One compact button of the question card, carrying the slash command line it stands for (the inherited
    `Card.on_button_pressed` posts `Card.Chosen` with `event.button.command`)."""

    def __init__(self, label, command, first):
        super().__init__(label, compact=True, classes="first" if first else "")
        self.command = command


# D4c — the commit card (kind `commit`): the architect's proposal to commit the owner's own files. It is shown from the
# controller's proposal (not from a plan row), carries the message, the diff stat and the plan-staleness warning, and
# its two buttons are the shared `/approve` («yes», commits) and `/decline` («no», runs nothing), routed by kind.
COMMIT_STAT_LINES = 12  # rows of the stat the card shows; the rest is counted


def commit_key(proposal):
    return "commit:%s" % proposal.id


def commit_spec(key, at, proposal):
    stat = proposal.stat.splitlines()
    if len(stat) > COMMIT_STAT_LINES:
        stat = stat[:COMMIT_STAT_LINES] + [strings.text("card.commit_more", count=len(stat) - COMMIT_STAT_LINES)]
    text = strings.text("card.commit_text", message=proposal.message, stat="\n".join(stat), stamp=COMMIT_STAMP)
    if proposal.selection.refused:
        text = strings.text("card.commit_left_out", paths="; ".join(
            "%s (%s)" % item for item in proposal.selection.refused)) + "\n\n" + text
    return cards.CardSpec(key=key, title=strings.text("card.commit_title"), text=text,
                          buttons=((strings.text("card.commit_yes"), "/approve"),
                                   (strings.text("card.commit_no"), "/decline")),
                          hint=None, at=at, done=None, alarm=False)


def commit_card_source(screen):
    """`CARD_SOURCES["commit"]`: one card while the controller holds a proposal that awaits the owner."""
    proposal = getattr(screen.app.controller, "commit_proposal", None)
    if proposal is None or proposal.state != "awaiting":
        return ()
    key = commit_key(proposal)
    return (commit_spec(key, screen.merge_card_at(key), proposal),)


CARD_SOURCES["commit"] = commit_card_source
CARD_ROUTES[("/approve", "commit")] = lambda screen, argument, key: screen.confirm_commit(key)
CARD_ROUTES[("/decline", "commit")] = lambda screen, argument, key: screen.decline_commit(key)


class _QuestionButtons(VerticalGroup):
    """The question card's action area: its buttons in one row while the card is wide enough, else wrapped onto
    further rows (`question_button_rows`). Textual has no wrapping container and a single row clips the tail, so the
    draft button and the three quick answers share two rows rather than a label being hidden. The grouping is
    rebuilt only when the card's own width changes it (a resize re-flows it), never on every pass."""

    def __init__(self, buttons, **kwargs):
        super().__init__(**kwargs)
        self.styles.height = "auto"  # the shared `Card .buttons` row is one line tall; this area may grow
        self._buttons = tuple(buttons)
        self._rows = None

    def on_mount(self):
        self._reflow()

    def on_resize(self, event):
        self._reflow()

    def _reflow(self):
        width = self.content_size.width
        if width <= 0:
            return
        rows = question_button_rows(self._buttons, width)
        if rows == self._rows:
            return
        self._rows = rows
        self.remove_children()
        self.mount_all([HorizontalGroup(*[_QuestionButton(label, command, first=(index == 0 and row_index == 0))
                                          for index, (label, command) in enumerate(row)])
                        for row_index, row in enumerate(rows)])


class QuestionCard(cards.Card):
    """The owner-question card widget (i3d): the shared `cards.Card` with the wrapping `_QuestionButtons` as its
    action area, so only the question kind wraps its buttons and every other kind keeps the shared one-row layout."""

    def compose(self):
        if self.spec.done is not None:
            yield Static(self.spec.done, classes="card-text", markup=False)
            return
        yield Static(self.spec.text, classes="card-text", markup=False)
        yield _QuestionButtons(self.spec.buttons, classes="buttons")
        # a question spec carries `card.question_hint`; the shared `card.hint` default keeps a spec without one whole
        hint = self.spec.hint if self.spec.hint is not None else strings.text(
            "card.hint", commands=" · ".join(command for _, command in self.spec.buttons))
        yield Static(hint, classes="card-hint", markup=False)


def question_cards(screen):
    """`CARD_SOURCES["question"]` (i3d): the question cards of the screen's current state.

    The screen's own `question_card_specs` does the work — read the `needs_owner` rows, fetch and cache each
    attempt's end view, build one `question_card` per key. A stand-in screen that does not carry the question kind
    (the shared card-hook doubles of `CARD_SOURCES`) shows no question card, exactly as a state with no
    `needs_owner` row does."""
    builder = getattr(screen, "question_card_specs", None)
    return () if builder is None else builder()


def question_card_key(milestone, attempt, version):
    """The key of one owner-question card (i3d): `question:r<version>:<milestone>:<attempt>` — the plan revision is
    part of the key, so an attempt of a new revision is a card of its own."""
    return "question:r%s:%s:%s" % (version, milestone, attempt)


def question_body(end, rows=QUESTION_LINES, width=0):
    """The card's question text: the end view's own body — its `Question:` line and the task lines — each stripped,
    wrapped to `width` cells when the card slot has one, and at most `min(rows, QUESTION_LINES)` displayed rows. It
    is the body the plain end screen prints, so the card says what that screen says; the card widget renders it
    literally (no markup).

    `rows`/`width` come from `MainScreen.question_text_room`, so the text never grows past the chat pane's own row
    budget and the card's buttons below it stay on screen (A1); the shown rows are also capped at `QUESTION_LINES` (6), because the
    body's logical-line cap does not bound the wrapped output — one long `Question:` line wraps past six rows — and
    the task makes the question text ≤6 lines. The last kept row is elided when the body has more rows than fit. The
    `(QUESTION_LINES, 0)` default — a caller with no laid-out slot — keeps the plain body with no wrapping."""
    keep = min(max(rows, 1), QUESTION_LINES)
    lines = [line.strip() for line in end.body[:QUESTION_LINES]]
    if width <= 0:
        return "\n".join(lines[:keep])
    shown_rows = wrapped(lines, width)
    if len(shown_rows) <= keep:
        return "\n".join(shown_rows)
    # the last kept row carries the ellipsis (`elide_end` keeps text that already ends with it), so a body cut to
    # the slot (or to the six-line cap) reads as cut, not as complete
    return "\n".join(shown_rows[:keep - 1] + [elide_end(shown_rows[keep - 1] + ELLIPSIS, width)])


CARD_SOURCES["question"] = question_cards
CARD_ROUTES[("/approve", "question")] = lambda screen, argument, key: screen.approve_question(argument, key)
CARD_ROUTES[("/decline", "question")] = lambda screen, argument, key: screen.decline_question(argument, key)
AUTO_END_CARDS.add("needs_owner")


class QuestionNoteScreen(NoteScreen):
    """The owner-question card's answer note: a `NoteScreen(..., answer=True, enter=True)` that submits on enter.

    The frozen hook's own `on_key` never sees the key while the form's `TextArea` holds the focus: Textual delivers
    a key to the focused widget first, and the `TextArea` consumes `enter` (it inserts a newline), so the screen's
    handler is not reached. The priority binding below is checked ahead of the focused widget on the card's own note
    (the plain answer forms keep their ctrl+g), so enter submits exactly the text the card-origin note intends."""
    BINDINGS = [Binding("enter", "send", "Send", priority=True)]

# i3b: the plan-approval card on the main screen (kind `plan`, key `plan:<version>`). While a plan is proposed the
# slot holds one card, «Plan · N stages · M tasks», whose two buttons decide the plan in one click: `/approve` goes
# straight to `decide` (no PlanScreen, no confirmation modal) and `/decline` opens the revision note. The counts are
# read verbatim from the plan summary line (`PlanView.lines[1]`, the one place they exist; a proposed plan whose view
# carries no such line shows the same card without counts). PlanScreen and its keys stay as they are.
PLAN_CARD_SEP = " · "  # the separator of the summary line's fields ("Plan r1 · 1 stage · 3 tasks · checked")


def plan_card_counts(plan):
    """The two rendered counts of a plan summary line (`PlanView.lines[1]`): the fields between "Plan rN" and the
    verdict, e.g. ("1 stage", "3 tasks") for the joint example. ("", "") when there is no summary line or it does
    not name both counts — the card then carries none."""
    lines = tuple(getattr(plan, "lines", None) or ())
    fields = lines[1].split(PLAN_CARD_SEP) if len(lines) > 1 else []
    counts = fields[1:-1]
    return (counts[0], counts[1]) if len(counts) == 2 else ("", "")


# The profile view (`process.describe`, the only form of the autonomy level the screen holds) names the level on the
# line «  autonomy: <level> · …»; the screen asks the policy (`autonomy.decide`) about that level, the one place the
# approval rule lives.
AUTONOMY_LINE = "  autonomy: "
# The Russian form of the same line (0.7.x wording of `process.describe`), still read as input.
LEGACY_AUTONOMY_LINE = "  автономия: "


def profile_level(snapshot):
    """The autonomy level named by `snapshot.profile`'s lines, "manual" when the profile or the line is missing or
    unreadable (the policy's own rule for a level it cannot read)."""
    profile = getattr(snapshot, "profile", None)
    for line in tuple(getattr(profile, "lines", None) or ()):
        for prefix in (AUTONOMY_LINE, LEGACY_AUTONOMY_LINE):
            if line.startswith(prefix):
                return line[len(prefix):].split(" · ", 1)[0].strip() or "manual"
    return "manual"


def plan_stale(snapshot):
    """Whether the proposed plan is the RS2 stale one (the project changed after planning)."""
    return getattr(snapshot.plan, "family", None) == "plan.stale"


def plan_auto_approves(snapshot):
    """Whether the architect approves the proposed plan itself: the plan is proposed and not stale and the policy
    allows `approve` at the profile's level (the same decision `feed._plan_wakes` takes). Any level that cannot be
    read is "manual", which asks."""
    return (snapshot is not None and snapshot.version is not None and snapshot.status == "proposed"
            and not plan_stale(snapshot) and autonomy.decide(profile_level(snapshot), "approve") == "allow")


def plan_card_spec(key, at, stages, tasks, stale=False, auto=False, narrow=False):
    """One plan card through the frozen builder (`cards.plan_card`); without counts the title is the plan word
    itself (`pane.plan`: «Plan», the word the plan pane carries), so the card is the same decision either way.
    RS2: a stale proposal (the project changed after planning) cannot be approved, so its card offers only
    «revise» and says why. D1: where the architect approves the plan itself (`auto`) the card does not ask: it
    says so and offers only «revise»; the pointer to the plan follows the layout (`narrow`: no right column)."""
    spec = cards.plan_card(key, at, stages, tasks)
    if stale:
        spec = replace(spec, text=strings.text("card.plan_stale_text"),
                       buttons=((strings.text("card.revise_only"), "/decline"),))
    elif auto:
        spec = replace(spec, text=strings.text("card.plan_auto_text"),
                       buttons=((strings.text("card.revise_only"), "/decline"),))
    elif narrow:
        spec = replace(spec, text=strings.text("card.plan_text_narrow"))
    if stages and tasks:
        return spec
    return replace(spec, title=strings.text("pane.plan"))


def plan_card_source(screen):
    """`CARD_SOURCES["plan"]`: one card while the plan is proposed (`snapshot.version` set and status `proposed`),
    keyed `plan:<version>` so one revision keeps one card. The source returns nothing as soon as the plan leaves
    `proposed` (an approval, or a revision started from `/decline`), so the card leaves on that render. The card
    text depends on the autonomy level and the layout (`screen.narrow`); a resize re-renders the sources, so an open
    card follows it."""
    # The app's current snapshot; a screen whose app has not painted one yet shows no card (production starts with
    # `app.snapshot = None`, and a card hook may be asked about a screen before its first slice).
    snapshot = getattr(screen.app, "snapshot", None)
    if snapshot is None or snapshot.version is None or snapshot.status != "proposed":
        return
    stages, tasks = plan_card_counts(snapshot.plan)
    yield plan_card_spec("plan:%s" % snapshot.version, card_clock(), stages, tasks, stale=plan_stale(snapshot),
                         auto=plan_auto_approves(snapshot), narrow=bool(getattr(screen, "narrow", False)))


def approve_plan_card(screen, argument, key):
    """`/approve` from the plan card (or a typed `/approve`): `decide("approve", version)` with no modal. `decide`
    only queues the approval — its verdict comes back later through the app's callback — so the card is closed only
    on a confirmed success, never right after the call. A refusal (`error` on that callback: the plan is no longer
    the current proposed one) keeps the open card and adds no line of its own: `decide` already reports it on the
    main screen (`say_note`), so a second line here would show it twice."""
    version = int(key.split(":", 1)[1])

    def settled(outcome, error):
        if error:
            return  # the open card stays: the decision was not made, and `decide` has said why
        screen.close_card(key, strings.text("card.plan_done", time=card_clock()))

    screen.app.decide("approve", version, after=settled)


def revise_plan_card(screen, argument, key):
    """`/decline` from the plan card (or a typed `/decline`): the plan screen's own revision note, with enter
    submitting (a card-origin note). The card stays while the note is open or cancelled; the revision the note
    starts ends the proposed state, so the source drops the card."""
    screen.app.push_screen(NoteScreen(enter=True), screen.app.revision_note)


CARD_SOURCES["plan"] = plan_card_source
CARD_ROUTES[("/approve", "plan")] = approve_plan_card
CARD_ROUTES[("/decline", "plan")] = revise_plan_card

# ------------------------------------------------------------------------------------------------------------------
# i3e1: the readiness error card (kind `ready`) — a red card with the reason and the exact fix command when work
# cannot start. Its own block at the end of the module: the card contract (devtools/zeroshot/tasks/card-contract.md)
# has every card run add its rows with module-level statements in a block of its own, never by editing the frozen
# `CARD_ROUTES`/`CARD_SOURCES` literals, and another card run's rows are never touched.
# ------------------------------------------------------------------------------------------------------------------

READY_ORIGIN = "origin"  # the id of the no-origin readiness item (setup.item / planning.NEEDS)
READY_BLOCKED_NOTE = "Not started:"  # the line every blocked start writes; a failed operation's note is not this
READY_LINES = 6  # the card's text carries at most this many failing lines
# The exact shell command the no-origin readiness item carries in its own `detail` (setup.readiness): «… Add it
# yourself: git remote add origin https://github.com/OWNER/REPO.git (or git remote set-url origin ...).»; the userinfo
# item carries `git remote set-url origin …` instead. The detail is prose around the command, so the command is read
# out of it — the readiness item itself is not changed (non-goal).
READY_ORIGIN_FIX = re.compile(r"git remote (?:add|set-url) origin \S+")


def ready_blocked(app):
    """Whether a start is blocked by the readiness right now: the goal form or the plan screen kept a refused
    submission (`goal_block`/`plan_block`), or the run pane shows the blocked-start note (`blocked_note`'s line,
    `Not started: …`). A failed or lost operation's note (`Not done: …`, `Watch interrupted: …`) is not a
    blocked start: it does not grow a readiness card. Reads the app's own state only — no controller or engine
    call on a render."""
    note = blocked_note(note_text(app.run_note))
    return bool(app.goal_block or app.plan_block or note.startswith(READY_BLOCKED_NOTE))


def ready_failing(app):
    """The failing readiness items of the last slice (`app.checks`), while a start is blocked by them — else (). A
    recheck that passes clears the block (`got_checks`) and the new slice has no failing item, so the card's source
    drops it; a recheck that still fails keeps the very same items, hence the same card key."""
    if not ready_blocked(app):
        return ()
    return tuple(c for c in (app.checks or ()) if not c.ok)


def ready_key(checks):
    """The card key: `ready:` and the failing checks' own ids joined by `+` — the same failures keep one card
    (never a duplicate), a changed failing set is a card of its own."""
    return "ready:" + "+".join(c.id for c in checks)


def ready_text(checks):
    """The card's text: the failing checks' own lines (`summary`'s bound; the plain screen's `— [i] …` key hint
    dropped, as `block_lines` does; any other letter key as its step), at most `READY_LINES` of them."""
    from .app import command_hints  # function-level: app imports this module
    lines = [command_hints(FIX_KEY.sub("", summary(c.line))) for c in checks if not c.ok]
    return "\n".join(lines[:READY_LINES])


def ready_task(app):
    """The `{task}` the card's title names: the project whose start is blocked, exactly as the header names it."""
    snapshot = app.snapshot
    return snapshot.project if snapshot is not None else app.controller.name


def origin_fix(check):
    """The exact shell command `check`'s own `detail` carries (`git remote add origin …`, or `git remote set-url
    origin …` for the userinfo item), or None when that detail carries no such command — the one helper the card's
    `fix` line comes from (the source hands it the failed `origin` item alone)."""
    found = READY_ORIGIN_FIX.search(check.detail or "")
    return found.group(0) if found else None


def ready_source(screen):
    """`CARD_SOURCES["ready"]` (i3e1): the one readiness card of the current state — while a start is blocked by
    failing checks, for both the goal and the plan start. Its text is the failing lines and its `fix` is the origin
    command when the origin check failed; with no failing check (the recheck passed) the source returns nothing and
    `render_card_sources` takes the card off. Read from the app's own state (`checks`, the blocked note and the
    refused-submission blocks) only.

    A key that has been shown is a seen key like any other (A4): the source is stateless — it never edits
    `cards_seen` — so a recheck that still fails keeps the very same key, hence the same card, while a key whose
    card `render_card_sources` has taken off (the failing set changed, or a passed recheck ended the block) is
    never shown again, exactly as for every other card kind. The key follows the failing set, so a *different* set
    is a card of its own."""
    failing = ready_failing(screen.app)
    if not failing:
        return ()
    origin = next((c for c in failing if c.id == READY_ORIGIN), None)
    return (cards.error_card(
        ready_key(failing), card_clock(), ready_task(screen.app), ready_text(failing),
        ((strings.text("card.error_retry"), "/retry"), (strings.text("card.error_details"), "/details")),
        fix=origin_fix(origin) if origin is not None else None),)


CARD_SOURCES["ready"] = ready_source
CARD_ROUTES[("/retry", "ready")] = lambda screen, argument, key: screen.app.request_check()
CARD_ROUTES[("/details", "ready")] = lambda screen, argument, key: screen.app.action_settings()

# i3e2: the failure card — a failed stage or a failed planning run as a red card with «try again» and
# «details» (release 0.5.2, docs/RELEASE_0.5.2_PLAN.md run i3e2; the card contract is
# devtools/zeroshot/tasks/card-contract.md). This block is this run's own rows of the shared hooks — `CARD_SOURCES`,
# `CARD_ROUTES` and `AUTO_END_CARDS` — and the helpers they use; nothing of them else is touched.
FAILED_CARD_STATES = ("failed", "failed_recoverable", "blocked", "stopped", "conflict")
FAILED_CARD_LINES = 6  # the bound of a failure card's text (the end view's body is longer than a card)
# The three actions a failure card can run modal-less, in the order the card prefers them: [g] continue,
# [n] new attempt, [g] check. A view offering none of them gets no retry button (only «details»).
FAILED_CARD_RETRY = ("resume", "new_attempt", "check")
# The planner statuses behind a failed planning run (`planning.FAILED`) or an owner-stopped one; `plan.kind ==
# "failed"` names the plan view of the failed run.
FAILED_PLAN_STATUS = ("run_failed", "proposal_invalid", "stopped")


def failed_card_key(row, version):
    """The stable key of one failed stage's card (i3e2): `failed:r<version>:<milestone>:<attempt>` of the attempt
    the row names. The plan revision and the attempt are part of the key, so a later revision or a later attempt of
    the same milestone is a card of its own."""
    return "failed:r%s:%s:%s" % (version, row.id, row.token.attempt)


def failed_plan_card_key(snapshot):
    """`failed:plan:<version>` for a snapshot whose current revision is a failed planning run, else None (i3e2).

    The version is part of the key, so the revision a restart prepares is a card of its own; a snapshot without a
    version carries no plan view to take the card's text from."""
    return None if snapshot is None or snapshot.version is None else "failed:plan:%s" % snapshot.version


def failed_plan_view(snapshot):
    """The failed planning run of `snapshot`, or None (i3e2): the plan screen's own failure facts — the `kind ==
    "failed"` view, or the `run_failed` / `proposal_invalid` status behind it (`planning.PlanView.failure`).

    A snapshot whose view is missing has nothing to take the card's text from, so it is no card: `take_snapshot`
    drops the view when the store cannot be read, and the overview lines it keeps are no plan screen."""
    if snapshot is None or snapshot.plan is None or snapshot.version is None:
        return None
    if snapshot.plan.kind == "failed" or snapshot.status in FAILED_PLAN_STATUS:
        return snapshot.plan
    return None


def failed_card_text(lines):
    """The text of a failure card (i3e2): the view's own lines, the leading blank line the screens drop dropped
    too, cut to the card's bound of `FAILED_CARD_LINES` lines. K1d: a letter key a line names is the TUI step that
    does it (`command_hints`)."""
    from .app import command_hints  # function-level: app imports this module
    body = [command_hints(line) for line in lines]
    while body and not body[0].strip():
        body.pop(0)
    return "\n".join(body[:FAILED_CARD_LINES])


def failed_card_buttons(retry):
    """The buttons of a failure card (i3e2): «try again» (`/retry`) only while the view behind the card
    offers a retry, then «details» (`/details`). Both are the card-only commands the contract names."""
    buttons = [(strings.text("card.error_retry"), "/retry")] if retry else []
    buttons.append((strings.text("card.error_details"), "/details"))
    return tuple(buttons)


def failed_plan_restart(view):
    """Whether a failed plan view offers the restart `/retry` runs (i3e2): `retry` on a failed revision, `restart`
    on an owner-stopped one — the two the plan screen's [g] runs through the same `controller.restart_plan`."""
    return "retry" in view.actions or "restart" in view.actions


def failed_card_refusal(outcome):
    """What a failure card's retry says on the status line when it started nothing (i3e2): the readiness refusal
    with its failing checks (the wording the other card refusals use), the service's own line for an attempt that
    moved, else its first line."""
    if outcome.kind == "blocked":
        return "\n".join([NOT_STARTED_BELOW] + ["! " + FIX_KEY.sub("", summary(c.line)) for c in outcome.checks])
    if outcome.kind == "stale":
        return MOVED
    return outcome.lines[0] if outcome.lines else strings.text("note.not_now", name="/retry")


def failed_card_source(screen):
    """The failure cards of the current state (i3e2): one red card per failed stage row and one for a failed
    planning run.

    A stage card's text is the body of that attempt's end view, fetched once per key off the event loop
    (`MainScreen.failed_card_view`) and cached, at most `FAILED_CARD_LINES` lines; until the fetch returns the
    source offers no card for that key, and the answer paints it on the next render. A row without an attempt
    (`token is None`: nothing ran, or the attempt belongs to another revision) has no end view to show. The
    planning card's text is the plan view itself, and it carries a retry button only while that view offers the
    restart. A key already shown and closed is never offered again — `render_card_sources` skips it, as for every
    other card kind."""
    app = screen.app
    snapshot = getattr(app, "snapshot", None)  # a stand-in screen's app (the shared hook test) carries none
    if snapshot is None:
        return []
    specs = []
    for row in snapshot.rows:
        if row.state not in FAILED_CARD_STATES or row.token is None:
            continue
        key = failed_card_key(row, snapshot.version)
        end = screen.failed_card_view(key, row)
        if end is None:
            continue
        spec = cards.error_card(key, at=screen.failed_card_at(key), task=row.id,
                                text=failed_card_text(end.body),
                                buttons=failed_card_buttons(any(name in end.names for name in FAILED_CARD_RETRY)))
        if row.state == "stopped":  # R-B: the owner's own stop is no error — neutral style, a stop title
            spec = replace(spec, title=strings.text("card.stopped_title", task=row.id), alarm=False)
        specs.append(spec)
    view = failed_plan_view(snapshot)
    if view is not None:
        key = failed_plan_card_key(snapshot)
        specs.append(cards.error_card(key, at=screen.failed_card_at(key),
                                      task=strings.text("canvas.plan_rev", v=snapshot.version),
                                      text=failed_card_text(view.lines),
                                      buttons=failed_card_buttons(failed_plan_restart(view))))
    return specs


CARD_SOURCES["failed"] = failed_card_source
CARD_ROUTES[("/retry", "failed")] = lambda screen, argument, key: screen.retry_failed_card(key)
CARD_ROUTES[("/details", "failed")] = lambda screen, argument, key: screen.show_failed_card(key)
AUTO_END_CARDS.update(FAILED_CARD_STATES)
