"""Decision cards of the chat: the main-path decisions (draft -> plan, approve plan, merge, owner question, error)
as the card widget the approved lab draws (`devtools/ui-lab/work.py`, `_card`, and the `.card*` rules of
`devtools/ui-lab/work.tcss`).

A `CardSpec` is the data of one decision: the opaque `key` the caller set (a draft id, an end token — never shown),
the maybe-translated `title`/`text`, the `buttons` as `(label, command line)` pairs (`command line` is a slash
command such as "/approve"), the optional `hint` (None means the shared `card.hint` line built from the commands),
the `at` time shown as the border subtitle, the `done` receipt line of a closed card, and the `alarm` flag. The
builders (`draft_card`, `plan_card`, `merge_card`, `question_card`, `error_card`) take that data and resolve every
id through `terminal_planner/tui/strings.py` (the frozen catalog); `closed(spec, done_text)` turns a spec into a
done card. A builder never touches the project, the controller or the network.

`Card(Vertical)` is the widget built from a spec: border title = title, subtitle = at; an open card shows the text,
one row of compact buttons and the dim hint, a done card is one dim row (`done_row`) with no border and no
buttons, and `alarm` adds the red style. Its `DEFAULT_CSS` carries the card rules, so the app needs no `zplan.tcss` edit. Pressing a
button posts one `Card.Chosen(command, card)` carrying the command line and the `Card` itself (the receiver reads
`card.spec.key`); the widget posts nothing else.

Nothing wires this module into the app yet (that is the i3 integration runs); it is new module only.

Worker interpretations (reviewers do not see the worker summary):
- `error_card(fix=...)`: `CardSpec` has no `fix` field (its fields are fixed by the task), so the exact shell
  command is appended to the caller's `text` on its own line ("{text}\\n{fix}"), shown verbatim: it is never passed
  through `strings.text`, so no placeholder is substituted into it.
- Every caller-provided string is rendered literally: the card's `Static`s use `markup=False` and the border
  title/subtitle get a `rich.text.Text`, because Textual parses console markup in a plain `str` by default and would
  drop square-bracketed text (`git remote add origin '../[archive]/repo.git'` -> `'..//repo.git'`,
  `Missing config[default]. Retry?` -> `Missing config. Retry?`). Button labels are literal in Textual already
  (`Button` builds its label with `Content.from_text`).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Optional, Tuple

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, Static

from . import strings

# One button: the visible label and the slash command line it stands for.
ButtonSpec = Tuple[str, str]


@dataclass(frozen=True)
class CardSpec:
    """The data of one decision card (see the module docstring). `key` is the opaque identity the caller set and the
    receiver of `Card.Chosen` reads back; `hint` is None for the default `card.hint` line; `done` is the closed-card
    receipt line (a done card shows it and no buttons); `alarm` is the red style (the error card)."""

    key: str
    title: str
    text: str
    buttons: Tuple[ButtonSpec, ...]
    hint: Optional[str]
    at: str
    done: Optional[str]
    alarm: bool


def _default_hint(buttons: Iterable[ButtonSpec]) -> str:
    """The shared hint line: `card.hint` with the button commands joined by " · ", as the lab draws it."""
    return strings.text("card.hint", commands=" · ".join(command for _, command in buttons))


def draft_card(key: str, at: str) -> CardSpec:
    """The goal-draft card: draft the plan from this goal? yes -> "/plan", no -> "/decline"."""
    return CardSpec(key=key, title=strings.text("card.draft_title"), text=strings.text("card.draft_text"),
                    buttons=((strings.text("card.plan_yes"), "/plan"), (strings.text("card.no"), "/decline")),
                    hint=None, at=at, done=None, alarm=False)


def plan_card(key: str, at: str, stages: str, tasks: str) -> CardSpec:
    """The plan-approval card: the caller passes ready words such as "3 stages"; approve -> "/approve"."""
    return CardSpec(key=key, title=strings.text("card.plan_title", stages=stages, tasks=tasks),
                    text=strings.text("card.plan_text"),
                    buttons=((strings.text("card.approve_yes"), "/approve"), (strings.text("card.revise"), "/decline")),
                    hint=None, at=at, done=None, alarm=False)


def merge_card(key: str, at: str, stage: str, done: str, total: str) -> CardSpec:
    """The stage-done card: merge -> "/merge", see the changes -> "/diff"."""
    return CardSpec(key=key, title=strings.text("card.merge_title", stage=stage),
                    text=strings.text("card.merge_text", done=done, total=total),
                    buttons=((strings.text("card.merge_yes"), "/merge"),
                             (strings.text("card.merge_changes"), "/diff")),
                    hint=None, at=at, done=None, alarm=False)


def question_card(key: str, at: str, task: str, text: str, buttons: Iterable[ButtonSpec]) -> CardSpec:
    """The owner-question card: the title names the task, the text and buttons come from the caller, the hint is
    `card.question_hint` (the owner may answer in words)."""
    return CardSpec(key=key, title=strings.text("card.question_title", task=task), text=text,
                    buttons=tuple(buttons), hint=strings.text("card.question_hint"), at=at, done=None, alarm=False)


def error_card(key: str, at: str, task: str, text: str, buttons: Iterable[ButtonSpec],
               fix: Optional[str] = None) -> CardSpec:
    """The error card (red): the title names the task, the text and buttons come from the caller. `fix` is an exact
    shell command (the no-origin case) shown verbatim on its own line, appended to the caller's text."""
    if fix is not None:
        text = text + "\n" + fix
    return CardSpec(key=key, title=strings.text("card.error_title", task=task), text=text,
                    buttons=tuple(buttons), hint=None, at=at, done=None, alarm=True)


def closed(spec: CardSpec, done_text: str) -> CardSpec:
    """`spec` as the closed card that shows only `done_text` (callers pass `strings.text("card.draft_sent", time=...)`
    or `strings.text("card.plan_done", time=...)`): a frozen-spec copy with the done line set."""
    return replace(spec, done=done_text)


DONE_MARKS = "✓↻"  # the marks a receipt text (`card.*_sent`, `card.*_done`, `card.error_retried`) starts with


def done_row(done_text: str) -> str:
    """S1: the one dim row a closed card is: its receipt, which starts with its own mark; a text without one gets
    the `✓`."""
    return done_text if done_text[:1] in DONE_MARKS else "✓ " + done_text


class _CardButton(Button):
    """A compact button that carries the slash command line it stands for."""

    def __init__(self, label: str, command: str, first: bool) -> None:
        super().__init__(label, compact=True, classes="first" if first else "")
        self.command = command


class Card(Vertical):
    """One decision card, built from a `CardSpec` (see the module docstring)."""

    DEFAULT_CSS = """
    Card {
        border: round ansi_magenta;
        border-title-color: ansi_white;
        border-title-style: bold;
        padding: 0 1;
        margin: 0 0 1 2;
        height: auto;
    }
    Card.alarm { border: round ansi_red; }
    Card.done { border: none; padding: 0; margin: 0; }
    Card.done .card-text { height: 1; text-wrap: nowrap; text-overflow: ellipsis; text-style: dim; }
    Card .buttons { height: 1; margin-top: 1; }
    Card Button { margin-right: 2; min-width: 6; }
    Card Button.selected { text-style: bold reverse; }
    Card .card-hint { height: 1; text-wrap: nowrap; text-overflow: ellipsis; text-style: dim; }
    """

    class Chosen(Message):
        """A card button was pressed: `command` is the button's slash command line, `card` is the `Card` itself
        (the receiver reads `card.spec.key`)."""

        def __init__(self, command: str, card: "Card") -> None:
            self.command = command
            self.card = card
            super().__init__()

    def __init__(self, spec: CardSpec, **kwargs) -> None:
        super().__init__(**kwargs)
        self.spec = spec
        self.choice = 0     # D2: the button the keys would press (index into `spec.buttons`)
        self.keyed = False  # D2: whether the keys are this card's (the screen marks the newest open card)
        # `rich` Text: a border title set from a str is rendered as console markup, so a bracketed task name
        # ("[archive]") would be dropped; the title and the `at` subtitle are caller-provided, show them verbatim.
        self.border_title = Text(spec.title)
        self.border_subtitle = Text(spec.at)
        self.add_class("done" if spec.done is not None else "open")
        if spec.alarm:
            self.add_class("alarm")

    def compose(self) -> ComposeResult:
        if self.spec.done is not None:
            yield Static(done_row(self.spec.done), classes="card-text", markup=False)
            return
        # `markup=False`: the text (and the appended `fix` command) is shown exactly as the caller passed it, so
        # bracketed paths such as `git remote add origin '../[archive]/repo.git'` survive.
        yield Static(self.spec.text, classes="card-text", markup=False)
        yield Horizontal(*[_CardButton(label, command, first=index == 0)
                           for index, (label, command) in enumerate(self.spec.buttons)], classes="buttons")
        hint = self.spec.hint if self.spec.hint is not None else _default_hint(self.spec.buttons)
        yield Static(hint, classes="card-hint", markup=False)

    def set_keyed(self, keyed: bool) -> None:
        """D2: whether the keys (↑↓ and Enter in the chat input) are this card's; only then is a choice drawn selected."""
        self.keyed = keyed
        self.paint_choice()

    def paint_choice(self) -> None:
        """D2: the selected choice is the button drawn in reverse (the lab's `card(...)`); an unkeyed card draws none.
        Idempotent, so it is asked again whenever the buttons may have been rebuilt (mount, resize)."""
        for index, button in enumerate(self.query(Button)):
            button.set_class(self.keyed and index == self.choice, "selected")

    def move_choice(self, delta: int) -> None:
        """D2: the next/previous choice, wrapping."""
        if self.spec.buttons:
            self.choice = (self.choice + delta) % len(self.spec.buttons)
            self.paint_choice()

    def press_choice(self) -> None:
        """D2: press the selected choice exactly as a click does — one `Chosen` with its command line."""
        if self.spec.done is None and self.spec.buttons:
            self.post_message(self.Chosen(self.spec.buttons[self.choice][1], self))

    def on_mount(self) -> None:
        self.paint_choice()

    def on_resize(self) -> None:
        self.paint_choice()  # a re-flowed button area (the question card) has new buttons

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.post_message(self.Chosen(event.button.command, self))
