"""The `/` command palette of the chat input (release 0.5.2, run w2): the rows a typed command lists, and the
decision over the line the owner submitted.

Nothing wires it into the app yet: the integration run i2 composes the widget above the prompt box and runs what
`submit` returns. `Palette(Static)` is the list itself — `show_for(value, state)` hides it unless the typed value is
a command (`/...`) and otherwise draws the commands the frozen registry (`slash`) lists for it:
`slash.matches(value, state)` filtered by `slash.available(command, state)`, at most `MAX_ROWS` of them, in that
order. One row per command: the name in bold, then the description `strings.text` gives its id, dimmed; a row never
wraps (one too long ends in an ellipsis). An empty list is the one dim `note.palette_empty` row, never an empty box.
`DEFAULT_CSS` carries the approved lab's palette (`devtools/ui-lab/work.tcss`, `#palette`): the box sits above the
input, as tall as its rows (`height: auto`, its `max-height` leaves room for `MAX_ROWS` rows and the two border
rows), with the lab's rounded yellow border, one cell of horizontal padding and no wrapping.

`submit(line, state)` decides one typed line without a widget, an app or a store: `Submitted(command_name,
argument)` — the command's own name and its argument — when `slash.problem` is None, `Refused(note)` carrying the
catalog text of that problem id (with the `{name}` the ids ask for, the command word as typed) otherwise, and None
for a line that is not a command at all (an owner message belongs to the chat). Both are plain frozen values, so the
screen acts on them without asking this module anything else.

The palette draws and decides only: it never executes a command, never reads a project or a store and never reaches
the network or the engine — those stay with the actions the integration run wires to it.
"""

from dataclasses import dataclass

from rich.text import Text
from textual.widgets import Static

from . import slash, strings

# The rows the palette lists at most (the lab's `found[:7]`) and the column its descriptions start in (the lab pads
# the name with `f"{cmd:<11}"`, the longest command name being nine characters).
MAX_ROWS = 7
NAME_WIDTH = 11


@dataclass(frozen=True)
class Submitted:
    """One command line the screen may run: the command's own name (`/open`, not the word as typed) and its
    argument, exactly as `slash.parse` read it ("" when the line had none)."""
    command_name: str
    argument: str


@dataclass(frozen=True)
class Refused:
    """One command line the screen must not run: why, in the current language and reading as the owner's own input
    (the catalog text of the `slash.problem` id, its `{name}` filled with the command word as typed)."""
    note: str


def submit(line, state):
    """What the screen does with one typed `line` in `state`: `Submitted`, `Refused`, or None when it is not a
    command at all. Pure — no widget, no app, no store; the state is one of `slash.STATES`.

    The guard is the raw line, not `slash.parse`: a command starts at the first character, so a line whose leading
    whitespace `parse` would strip (" /open", "\t/status") is not a command and is left to the chat (A3 hides the
    palette for the same reason, on the same raw prefix)."""
    if not line.startswith("/"):
        return None
    parsed = slash.parse(line)
    if parsed is None:
        return None
    problem = slash.problem(parsed, state)
    if problem is None:
        return Submitted(parsed.command.name, parsed.argument)
    return Refused(strings.text(problem, name=parsed.name))


class Palette(Static):
    """The `/` command list drawn above the chat input: `show_for(value, state)` shows or hides it (A1-A3).

    It holds no state of its own and executes nothing: the value typed in the input and the screen state decide the
    rows, and the screen calls `submit` on Enter. `show_for` draws into the widget, so the widget must be mounted
    (Textual builds a Rich renderable's visual on the console of the widget's app); the screen calls it from the
    input's change event, which only fires on a mounted screen.
    """

    DEFAULT_CSS = """
    Palette {
        height: auto;
        max-height: 9;
        border: round ansi_yellow;
        padding: 0 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    highlight = 0  # the row Tab completes and Enter runs (O3); the first one until the owner moves it
    found = ()  # the commands the rows draw, in order (what `show_for` last listed)
    shown_value = ""  # the value `show_for` last drew for: a new value starts the highlight over

    def rows(self, value, state):
        """The commands the palette lists for `value` in `state`: `slash.matches` filtered by `slash.available`. The
        screen's palette narrows this further (`RunAwarePalette`); `show_for` keeps the first `MAX_ROWS` after that.
        `/language` is not listed while `strings.OFFERED` holds one language: there is nothing to choose."""
        return [command for command in slash.matches(value, state) if slash.available(command, state)
                and (command.name != "/language" or len(strings.OFFERED) > 1)]

    def show_for(self, value, state):
        """Draw the commands `value` lists in `state`, or hide the palette when it is not a command.

        Hidden when `value` does not start with "/"; otherwise the rows of `rows(value, state)`, one row each, or the
        single dim `note.palette_empty` row when none is left. The highlighted row is drawn reversed: the first
        one for a new value, the same one (kept inside the list) when only the state changed."""
        if not value.startswith("/"):
            self.display = False
            self.found = ()
            self.highlight, self.shown_value = 0, ""  # a palette opened again starts on the first row
            return
        self.found = self.rows(value, state)[:MAX_ROWS]
        if value != self.shown_value:
            self.highlight = 0
        self.shown_value = value
        self.highlight = min(self.highlight, max(len(self.found) - 1, 0))
        text = Text()
        if self.found:
            for index, command in enumerate(self.found):
                if index:
                    text.append("\n")
                picked = index == self.highlight
                text.append("%-*s" % (NAME_WIDTH, command.name), style="bold reverse" if picked else "bold")
                text.append(strings.text(command.description_id), style="reverse" if picked else "dim")
        else:
            text.append(strings.text("note.palette_empty"), style="dim")
        text.no_wrap, text.overflow = True, "ellipsis"
        self.update(text)
        self.display = True

    def move(self, delta, value, state):
        """O3: move the highlight `delta` rows, wrapping at both ends, and redraw."""
        if self.found:
            self.highlight = (self.highlight + delta) % len(self.found)
            self.show_for(value, state)

    def picked(self):
        """The highlighted command, or None when the palette lists nothing."""
        return self.found[self.highlight] if self.found else None
