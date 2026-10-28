"""L-2/L-4: the chat pane's text — the conversation's rows, the indicator row above the input and the chat's own
lines — as pure functions of the history and the chat's own state. `chat.py` holds
the chat itself and `app.py` renders it as the scroll of one widget per entry (i3-chat-inline); the old manual
scroll window and its clamped offset are gone with `chat_scroll`/`chat_layout`."""

import re

from . import chat as chat_module, strings
from .text import plain_lines

CHAT_MIN_COLS = 20     # L-1: the supported layout; below it the newest rows survive
CHAT_MIN_ROWS = 8
SPIN = "◐◓◑◒"         # the thinking row's spinner: one frame per second of the turn
# The one refusal of a chat that cannot start: its text is the literal `chat_state` used before the catalog;
# i6 reads `chat.refused` instead, so the line follows the chosen language (its EN is this same text).
CHAT_REFUSED = "The architect chat is unavailable: no project selected."


def token_fields(token):
    """The plain fields of a delivery `Token`, as a chat draft's identity carries them (None: no attempt).

    The architect adapter has no lifecycle imports, so the identity travels as plain data: the app flattens the
    token once, when the turn's snapshot is taken, and the stored draft keeps exactly these values. It is the
    `Token` of the milestone's attempt in that snapshot, so two answer drafts of one reply keep their own."""
    if token is None:
        return None
    return {"milestone": token.milestone, "plan_revision": token.plan_revision, "attempt": token.attempt,
            "run_id": token.run_id, "status": token.status, "outcome": token.outcome, "delivery": token.delivery}


def body_rows(history):
    """L-4: every display row of the history, oldest first — each entry's own blocks (the text and the marked
    partial of a cut turn, and the labelled drafts), each of them split and escaped per L-2. Unbudgeted and
    unwrapped."""
    rows = []
    for entry in history:
        for _kind, text in chat_module.entry_blocks(entry):
            rows += plain_lines(text)
    return rows


def state_row(value):
    """L-4: a line as one row. L-2 comes first and runs on each original line: the value is split on LF and
    every line is scanned on its own, so a terminal sequence never completes across a line break (the line the
    model streamed and the line it continued on are two separate values). The safe lines then join into the one row
    the pane draws — a streamed reply carries line breaks and they must not cost rows — and the whitespace that is
    left in them collapses: by then L-2 has turned every unprintable one into its escape, so the only whitespace
    still there is the ordinary space, and a run of it (or of the line breaks) becomes the one space L-4 asks for.
    Nothing L-2 escaped is affected: `\\t` and `\\x85` are text by now, not whitespace."""
    return " ".join(word for piece in plain_lines(value) for word in piece.split())


def chat_state(app):
    """The line of a chat that is not ready: it is still preparing, or there is no chat at all (an unknown project,
    a fixture demo). Everything else is `None`: a blocked start says it through `chat_refusal`, a running turn
    through `chat_thinking`, and a finished, cancelled or failed turn is in the history."""
    state = app.chat.state if app.chat is not None else None
    if state is None:
        return getattr(app, "chat_off", None) or strings.text("chat.refused")
    return chat_module.PREPARING if state.phase == "preparing" else None


def thinking_row(state):
    """L-4: the running turn as the indicator's one row: `<spinner> The architect is thinking… M:SS · <live>`. The spinner
    steps with each second of the turn. The model supplies `state.live`, so L-2 must see the original line breaks:
    `state_row` splits it on LF and escapes each line on its own before the row joins them."""
    seconds = int(state.elapsed)
    clock = "%d:%02d" % divmod(seconds, 60)
    live = plain_preview(state.live)
    return "%s %s%s" % (SPIN[(seconds - 1) % len(SPIN)], strings.text("chat.thinking", clock=clock),
                        " · " + live if live else "")


MARKDOWN_LEAD = re.compile(r"\s*(?:#+\s*|[-*]\s+)?")
MARKDOWN_MARKS = re.compile(r"\*\*|__|`")


def plain_preview(value):
    """The thinking row's live text without markdown markers: `state_row` after L-2, with each line's leading `#`s
    or `- `/`* ` and every `**`, `__` and backtick dropped. The markers go after L-2 has escaped the line, so
    dropping one can never complete a terminal sequence the model left open."""
    lines = (MARKDOWN_MARKS.sub("", MARKDOWN_LEAD.sub("", piece, count=1)) for piece in plain_lines(value))
    return " ".join(word for piece in lines for word in piece.split())


def chat_thinking(app):
    """The indicator row of the running turn, or "" when no turn runs."""
    state = app.chat.state if app.chat is not None else None
    return thinking_row(state) if state is not None and state.phase == "ready" and state.running else ""


def chat_refusal(app):
    """u3b-chat C-7: the catalog refusal (with its remedy) of a chat that cannot start, or "". L-4 gives the
    blocked start no exception: this is the one state row the pane has, and the supported terminal is wide enough
    for the whole refusal, remedy and catalog code included."""
    state = app.chat.state if app.chat is not None else None
    return state.refusal if state is not None and state.phase == "blocked" else ""


def chat_outcome(app):
    """u3b-chat C-4/C-6: the chat's own last line when the body has no row for it, else "".

    A send or a reset the chat itself refused leaves its refusal and catalog code in the chat's note: another
    window's lock (`architect.locked`, C-6), a chat that is closing, a rebind the profile refused. None of those
    is written to the store (C-6 keeps its bytes), so this line is the pane's own, in the status area above the
    input, beside the app's `chat_note` — also while a turn runs, since a refusal is read for the turn it was
    refused for.
    A result the history already carries (a completed turn, a reset entry, a failed turn's error entry, a turn
    the owner cancelled) is not repeated here: its history row is the one u3b-chat gives it (L-4)."""
    state = app.chat.state if app.chat is not None else None
    if state is None or state.phase != "ready" or not state.note:
        return ""
    line = " ".join(str(state.note).split())
    return "" if any(line in " ".join(str(entry.text).split()) for entry in state.entries) else line
