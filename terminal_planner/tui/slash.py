"""The `/` command registry of the chat input: the main screen's commands, their states and their arguments.

Pure data and functions — no app, no I/O, no engine call, the palette and the app's actions
(`tui/palette.py`, `tui/app.py`, `tui/card_host.py`) use it. `COMMANDS` is the one ordered tuple of the twenty-one commands; each frozen `Command`
carries its English name, the id of its description in the string catalog (u2 owns the texts, this module keeps
only the ids), the screen states it acts in, and its argument rule (`arg`). `parse(line)` turns one typed line into
a `Parsed` — the resolved command or None for an unknown name, the raw name as typed, and the argument text — or
None when the line is not a command at all. `available(command, state)` says whether the command acts in that state
and raises `ValueError` for a state outside `STATES`. `matches(prefix, state=None)` is the palette's prefix filter,
ordered so that the commands acting in the given state come first. `problem(parsed, state)` returns the id of the
catalog note that says why a parsed line cannot act now, or None when it can.

Command names stay English (docs/ui-redesign/GLOSSARY.md); a typed name is matched case-insensitively, and a
Cyrillic look-alike typed on a Russian layout is never translated, so `parse` reports it as an unknown name and the
screen shows the palette. The states are the main screen's; `/stop` acts while a milestone runs and while the
planner runs (`planning`, 0.6.0)."""

from dataclasses import dataclass

from . import strings


# The screen states of the main screen (the lab's STATES, without its `empty`/`approve` aliases): a state outside
# this set is a programming error, never a user input.
STATES = frozenset(("idle", "draft", "planning", "plan_ready", "running", "merge", "question", "error"))

# The formal /language argument values; anything else after /language is a bad_language note.
LANGUAGE_CHOICES = ("en", "ru", "zh")
# S3b: the formal /theme argument values; anything else after /theme is a bad_theme note.
THEME_CHOICES = ("auto", "dark", "light")


@dataclass(frozen=True)
class Arg:
    """The argument a command expects after its name, when it expects one.

    `label` is what the argument is (for the palette and help text; the string catalog never sees it), `required`
    is True only when the command cannot act without it (/open needs a project-relative path), and `choices` is the
    closed set of allowed values when the argument is one (/language takes en|ru|zh); an empty `choices` accepts
    any text."""
    label: str
    required: bool = False
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class Command:
    """One `/` command: the English name, the id of its description, the states it acts in, and its argument rule.

    `states` is the frozenset of screen states the command acts in (the empty set would mean it acts nowhere, which
    no command does); `arg` is `None` for a command that takes no argument, otherwise an `Arg`."""
    name: str
    description_id: str
    states: frozenset
    arg: Arg | None = None


# The twenty-one commands, in the order the palette and the help list them: /plan, /approve, /decline, /run, /merge, /diff,
# /open, /status, /stop, /language, /setup, /help, /new, /quit, /view, /attempt, /answer, /log, /details, /retry, /scheme. K1a: the last
# five are the plan pane's former letter keys (p, o and w, t, e, i); they act in every state, as the keys did, and
# follow the original fourteen so the palette's seven rows (`palette.MAX_ROWS`) still open with the same commands.
# K1b: `/plan` acts where a goal can start or an open draft card is sent (idle, draft) and after a failure (error); its
# optional argument is the goal text. `/open` acts everywhere a file can be read while no work
# runs (idle, draft, plan_ready, merge, question, error — not planning or running); `/stop` acts
# while a milestone or the planner runs; `/run` acts in every state, as the pane's `g` did (K1a: a ready stage is
# started beside an open draft, a merge wait or an owner question; with nothing to run it says so); the rest act in
# every state. RS2: `/retry` is the failure and readiness cards' «try again» button typed; it acts in every state
# (a card outlives the state it was raised in) and, with no open card that offers it, says `note.not_now`. T4e: `/scheme`
# acts in every state and toggles the block scheme on the whole window.
COMMANDS = (
    Command("/plan", "cmd.plan", frozenset(("idle", "draft", "error")), Arg("goal")),
    Command("/approve", "cmd.approve", frozenset(("plan_ready", "question", "error"))),
    Command("/decline", "cmd.decline", frozenset(("draft", "plan_ready", "question"))),
    Command("/run", "cmd.run", STATES),
    Command("/merge", "cmd.merge", frozenset(("merge",))),
    Command("/diff", "cmd.diff", frozenset(("merge", "idle"))),
    Command("/open", "cmd.open", frozenset(("idle", "draft", "plan_ready", "merge", "question", "error")),
            Arg("path", required=True)),
    Command("/status", "cmd.status", STATES),
    Command("/stop", "cmd.stop", frozenset(("running", "planning"))),
    Command("/language", "cmd.language", STATES, Arg("language", choices=LANGUAGE_CHOICES)),
    Command("/setup", "cmd.setup", STATES),
    Command("/help", "cmd.help", STATES),
    Command("/new", "cmd.new", STATES),
    Command("/quit", "cmd.quit", STATES),
    Command("/view", "cmd.view", STATES),
    Command("/attempt", "cmd.attempt", STATES),
    Command("/answer", "cmd.answer", STATES),
    Command("/log", "cmd.log", STATES),
    Command("/details", "cmd.details", STATES),
    Command("/retry", "cmd.retry", STATES),
    Command("/scheme", "cmd.scheme", STATES),
    Command("/theme", "cmd.theme", STATES, Arg("theme", choices=THEME_CHOICES)),
)

_BY_NAME = {command.name: command for command in COMMANDS}


def hidden(command):
    """True for `/language` while the catalog offers one language: there is nothing to choose, so the command is not
    listed and a typed `/language` is an unknown name (read from `strings.OFFERED` on every call)."""
    return command.name == "/language" and len(strings.OFFERED) < 2


@dataclass(frozen=True)
class Parsed:
    """One parsed command line, ready for `problem`.

    `command` is the command the name resolved to, or None for a name outside `COMMANDS` (the screen then shows the
    palette). `name` is the command word exactly as typed, leading slash included and case kept, so a note can name
    what the user wrote; `argument` is the rest of the line after the name, stripped ("" when there was none)."""
    command: Command | None
    name: str
    argument: str


def parse(line):
    """`Parsed` for one typed line, or None when `line` (stripped) does not start with `/`.

    The command word is matched case-insensitively against `COMMANDS` (`/Plan` resolves to `/plan`); the argument
    is the rest of the line, stripped. No layout translation happens, so a Cyrillic look-alike stays unknown."""
    stripped = line.strip()
    if not stripped.startswith("/"):
        return None
    parts = stripped.split(None, 1)
    name = parts[0]
    argument = parts[1].strip() if len(parts) > 1 else ""
    command = _BY_NAME.get(name.lower())
    return Parsed(None if command is not None and hidden(command) else command, name, argument)


def available(command, state):
    """True when `command` acts in `state`; raises `ValueError` when `state` is not one of `STATES`."""
    if state not in STATES:
        raise ValueError("unknown screen state: %r" % (state,))
    return state in command.states


def matches(prefix, state=None):
    """The commands whose name starts with the first word of `prefix`, in registry order.

    With a `state`, the commands that act in it come first and the rest keep their registry order after them; a
    bare `/` (or any prefix every name shares) lists every offered command (`/language` only when several languages are offered). The name is matched as typed, not translated."""
    head = prefix.split()
    word = head[0] if head else prefix
    found = [command for command in COMMANDS if command.name.startswith(word) and not hidden(command)]
    if state is None:
        return found
    if state not in STATES:
        raise ValueError("unknown screen state: %r" % (state,))
    return ([command for command in found if state in command.states]
            + [command for command in found if state not in command.states])


def problem(parsed, state):
    """The id of the catalog note that says why `parsed` cannot act in `state`, or None when it can.

    The first reason wins: an unknown name (`note.unknown_command`) before a state the command does not act in
    (`note.not_now`) before a missing required argument (`note.needs_arg`) or a /language argument outside en|ru|zh
    (`note.bad_language`) or a /theme argument outside auto|dark|light (`note.bad_theme`)."""
    if parsed.command is None:
        return "note.unknown_command"
    if not available(parsed.command, state):
        return "note.not_now"
    arg = parsed.command.arg
    if arg is None:
        return None
    if arg.required and not parsed.argument:
        return "note.needs_arg"
    if arg.choices and parsed.argument and parsed.argument not in arg.choices:
        return "note.bad_theme" if parsed.command.name == "/theme" else "note.bad_language"
    return None
