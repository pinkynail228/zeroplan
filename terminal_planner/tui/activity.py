"""«What's happening» — the journal pane under the canvas — and the one-line key/status bar (release 0.5.2, run w3).

Two widgets of the one-screen UI, built after the approved lab (`devtools/ui-lab/work.py` `_render_log` and
`_render_bar`; `#log-pane` and `#bar` in `devtools/ui-lab/work.tcss`). Nothing wires them into the app yet — the
integration run i4 does — so the module is a leaf: no project, no controller, no process, no network. Every visible
word comes from the frozen string catalog `terminal_planner.tui.strings` (ids `pane.activity`, `canvas.log_empty`,
`live.last_event`, `live.job_timer`, `bar.*`); this module holds no wording of its own.

`Activity.show(lines, silence)` takes the journal lines the app already has (`Snapshot.journal`: formatted strings,
oldest first) and the seconds since the last activity (`flow.silence`), and shows the newest lines that fit the
pane, oldest first, never wrapped: a line wider than the pane ends in `…` (A3), and no lines show the one dim
`canvas.log_empty` line (A1). The border title is `pane.activity`; the border subtitle is `live.last_event` with
the last line clipped to 40 cells and the silence as `m:ss`, and it stays empty when there are no lines or the
silence is not known — a run without a measured silence shows no clock, never an invented `0:00` (A2).

`bar_text(project, branch, job, stage, elapsed, keys, width)` is the pure text of `Bar`: the project in bold, the
branch, the job phrase of its state (`bar.idle`, `bar.job_planning`, `live.job_timer`, `bar.waiting_approve`,
`bar.approving_plan`, `bar.waiting_merge`, `bar.waiting_question`, `bar.stopped_error` — the error in red), then
the keys the app offers as `key label` pairs, and `bar.continue` only while a job is planning or running and at least 24 cells are still
free. An unknown `elapsed` shows `—` in either clock phrase, never `0:00:00` (A4). The result is never wider than
`width` cells: a longer bar is cut with a trailing `…` (A5). Only its arguments decide the result; the language of
the strings is the catalog's own choice, exactly as for every other screen the widget draws into.

The journal lines stay plain: role colours and alarm rows are 0.6.0, so nothing here parses a line. Both border
texts go in as a literal `rich.text.Text` rather than a markup string, because their text is data — the catalog's
caption, the last journal line — not markup: a line carrying brackets is drawn as typed, never parsed away or
rejected as a bad tag.

The widgets carry the lab's two rules as their `DEFAULT_CSS` (an app or a screen overrides them): `#log-pane`'s
height (20%, at least five rows), its round border with the title and subtitle colours and its `0 1` padding, and
`#bar`'s single row, both never wrapping. The subtitle's 40-cell clip is the repo's own `flow.clip`.
"""

from __future__ import annotations

from rich.cells import cell_len
from rich.text import Text
from textual.widgets import Static

from . import strings
from .flow import clip
from .scheme import without_local_path

ELLIPSIS = "…"
LAST_EVENT_CELLS = 40  # the subtitle names the last line clipped to this many cells (A2)
CONTINUE_CELLS = 24  # `bar.continue` needs this many free cells to be appended (A5)
GAP = " · "  # i9/A1: the one separator between the bar's groups, `bar.continue` included
DASH = "—"  # the clock of an unknown elapsed time (A4)
RUNNING = ("planning", "running")  # the jobs whose bar keeps `bar.continue` (A5)
# Job value -> the catalog id of its phrase. `planning` and `running` carry a clock, so they are handled apart.
JOB_IDS = {"approve": "bar.waiting_approve", "approve_auto": "bar.approving_plan",
           "merge": "bar.waiting_merge", "question": "bar.waiting_question", "error": "bar.stopped_error",
           "stopped": "bar.stopped_owner"}


def _clock(elapsed):
    """`elapsed` seconds as `h:mm:ss` (hours not padded), or `—` when the time is not known (A4)."""
    if elapsed is None:
        return DASH
    elapsed = int(elapsed)
    return "%d:%02d:%02d" % (elapsed // 3600, elapsed // 60 % 60, elapsed % 60)


def _ago(silence):
    """`silence` seconds as `m:ss`: the `{m:ss}` value of the `live.last_event` subtitle (A2)."""
    silence = int(silence)
    return "%d:%02d" % (silence // 60, silence % 60)


def _job_text(job, stage, elapsed):
    """The job phrase of the bar: the state's own catalog text, or `bar.idle` when nothing runs (A4)."""
    if job == "planning":
        # P2a: an unknown time shows no clock at all (not the dash): the phrase without its trailing slot
        return strings.text("bar.job_planning", clock="" if elapsed is None else _clock(elapsed)).rstrip()
    if job == "running":
        return strings.text("live.job_timer", stage=stage, h=_clock(elapsed))
    if job == "error" and not stage:  # an error no milestone row owns (a blocked start, a failed plan): no blank name
        return strings.text("bar.error_plain")
    if job in JOB_IDS:
        return strings.text(JOB_IDS[job], stage=stage)
    return strings.text("bar.idle")


def _head_cells(text, room):
    """How many whole characters of `text` fit into `room` cells (a wide glyph is never half shown)."""
    used, count = 0, 0
    for char in text:
        width = cell_len(char)
        if used + width > room:
            break
        used += width
        count += 1
    return count


def _fit(text, width):
    """`text` cut to `width` cells, a dropped tail marked with `…`; the kept styling is preserved (A5)."""
    if width <= 0:
        return Text()
    if text.cell_len <= width:
        return text
    if width == 1:
        return Text(ELLIPSIS)
    head = text.divide([_head_cells(text.plain, width - 1)])[0]
    head.append(ELLIPSIS)
    return head


def bar_text(project, branch, job, stage, elapsed, keys, width, turn=None, meta=""):
    """The whole bottom bar as one `rich.text.Text` no wider than `width` cells (never wider, A5).

    `job` is the state value (`None` for nothing running), `stage` the milestone a waiting job names, `elapsed` the
    seconds of the job's clock or `None` (shown `—`), `keys` the `(key, catalog id)` pairs the app offers. `turn` is
    the seconds an architect turn has run, `None` when none runs (U1): with no job the phrase is `bar.architect` and
    that clock; beside a job it is the ` · bar.architect` tail after the job's phrase, the first thing a narrow bar
    drops. `meta` is the dim `model/effort · N tok` text the bar ends with (and the long-session hint): it is
    appended whole, last, and only when every other field (the turn tail, `bar.continue`) is kept and fits beside it,
    so it goes before any other field is cut."""
    def build(tail):
        text = Text()
        text.append(str(project), style="bold")
        if branch:
            text.append(" · %s" % branch, style="dim")
        text.append(GAP)
        if job is None and turn is not None:
            text.append("%s %s" % (strings.text("bar.architect"), _ago(turn)))
        else:
            text.append(_job_text(job, stage, elapsed), style="red" if job == "error" else "")
        if tail:
            text.append(GAP + strings.text("bar.architect"))
        for key, key_id in keys:
            text.append(GAP + str(key), style="bold dim")
            text.append(" " + strings.text(key_id), style="dim")
        return text

    whole = True  # every optional field of the bar is kept: only then may the tail follow (C2)
    text = build(job is not None and turn is not None)
    if job is not None and turn is not None and text.cell_len > width:
        text, whole = build(False), False
    if job in RUNNING:
        if width - text.cell_len >= CONTINUE_CELLS:
            text.append(GAP + strings.text("bar.continue"), style="dim")
        else:
            whole = False
    if meta and whole and text.cell_len + len(GAP) + cell_len(meta) <= width:
        text.append(GAP + meta, style="dim")
    fitted = _fit(text, width)
    fitted.no_wrap, fitted.overflow = True, "ellipsis"
    return fitted


class Activity(Static):
    """The always-visible journal pane under the canvas: the newest lines that fit, oldest first (A1-A3)."""

    DEFAULT_CSS = """
    Activity {
        height: 20%;
        min-height: 5;
        border: round ansi_bright_black;
        border-title-color: ansi_white;
        border-subtitle-color: ansi_green;
        padding: 0 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._lines = ()
        self._silence = None

    def on_mount(self):
        self._draw()

    def show(self, lines, silence):
        """Show `lines` — the ready journal lines, oldest first — and `silence` seconds of quiet, or None."""
        self._lines = tuple(lines or ())
        self._silence = silence
        self._draw()

    def on_resize(self, event):
        self._draw()

    def _draw(self):
        """The pane's text: the newest lines that fit its content height, else the one dim empty line."""
        rows = max(1, self.size.height)
        text = Text()
        if not self._lines:
            text.append(strings.text("canvas.log_empty"), style="dim")
        else:
            for index, line in enumerate(self._lines[-rows:]):
                if index:
                    text.append("\n")
                text.append(str(line))
        text.no_wrap, text.overflow = True, "ellipsis"
        # Literal `Text`: the catalog and the journal lines are data, never console markup (a line may hold `[`).
        self.border_title = Text(strings.text("pane.activity"))
        self.border_subtitle = self._subtitle()
        self.update(text)

    def _subtitle(self):
        """`live.last_event` for the last line and the measured silence as literal `Text`, or empty (A2).

        The catalog text and the clipped journal line are data: a bracket in either is drawn as typed, never
        parsed as console markup. Empty means the empty `Text` (never `None`): no invented clock (A2).
        """
        if not self._lines or not isinstance(self._silence, int):
            return Text()
        return Text(strings.text("live.last_event", what=clip(without_local_path(self._lines[-1]), LAST_EVENT_CELLS),
                                 m=_ago(self._silence)))


class Bar(Static):
    """The one-line bar at the very bottom: `bar_text` for the widget's own width (A4-A5)."""

    DEFAULT_CSS = """
    Bar {
        height: 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._fields = None
        self._turn = None
        self._meta = ""

    def update_bar(self, project, branch, job, stage, elapsed, keys, turn=None, meta=""):
        """Show the bar for the current state: the same fields as `bar_text`, the width the widget's own."""
        self._fields = (project, branch, job, stage, elapsed, keys)
        self._turn = turn
        self._meta = meta
        self._draw()

    def on_resize(self, event):
        self._draw()

    def _draw(self):
        if self._fields is None:
            return
        self.update(bar_text(*self._fields, width=self.size.width, turn=self._turn, meta=self._meta))
