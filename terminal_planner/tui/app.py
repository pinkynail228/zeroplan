"""Full-screen zplan shell: header, planner progress, plan panel, input line, key bar, goal form, plan screen,
Settings.

The app renders immutable snapshots delivered by the controller worker and never touches Authority, Git or the
tools itself; the one thing it runs on the UI thread is the interactive login, under App.suspend(). Planning
decisions are the shared service's (terminal_planner.planning), reached only through controller jobs."""

import asyncio
from collections import deque, namedtuple
from dataclasses import replace
import hashlib
import re
import textwrap
import time

from rich.cells import cell_len
from rich.console import Group
from rich.markdown import CodeBlock, Heading, Markdown, MarkdownElement
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from textual.app import App, SuspendNotSupported
from textual.binding import Binding
from textual.containers import Center, Horizontal, HorizontalGroup, Vertical, VerticalGroup, VerticalScroll
from textual.geometry import Region
from textual.message import Message
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Input, RichLog, Static, Tab, TabbedContent, TabPane, TextArea

from .. import catalog, milestone, planning
from ..authority import Blocked, override_reason
from ..cli import plural, refusal, summary
from ..delivery import CHECK, Delivery, NEW_ATTEMPT, PLAN_STATUS, STATE_TEXT, full_line
from ..setup import INTERRUPTED
from . import cards, chat as chat_module, flow as flow_draw, palette, scheme, slash, strings, viewer
from .activity import Activity, Bar, _job_text

# A2 of the S0 split: the moved names stay attributes of this module too, so every caller and test that reaches them
# through `terminal_planner.tui.app` keeps working. Each one is the moved module's own object (`app.X is module.X`).
from .chat_view import (CHAT_MIN_COLS, CHAT_MIN_ROWS, CHAT_REFUSED, SPIN, body_rows, chat_outcome, chat_refusal,
                        chat_state, chat_thinking, state_row, thinking_row, token_fields)
# A2 of the S1 split: the decision cards' module-level names (and the few shared constants and helpers they read) moved
# to `card_kinds`, MainScreen's card methods to `card_host.CardHost`; they stay attributes of this module too, each one
# the moved module's own object (`app.X is card_kinds.X`). `submit_verdict` stays below: it reads `screen_slash_state`,
# which needs MainScreen, so a module import the other way round would be a cycle.
from .card_host import CARD_REVEAL_TRIES, CardHost
from .card_kinds import (AUTO_END_CARDS, CARD_KEY_SEP, CARD_ROUTES, CARD_SOURCES, COMMAND_ACTIONS, EMPTY_ANSWER,
                         FAILED_CARD_LINES, FAILED_CARD_RETRY, FAILED_CARD_STATES, FAILED_PLAN_STATUS, FIX_KEY,
                         MERGE_TASKS, MOVED, NOT_STARTED_BELOW, PLAN_CARD_SEP, QUESTION_BUTTON_CHROME,
                         QUESTION_BUTTON_MIN, QUESTION_CARD_CHROME, QUESTION_CARD_INSET, QUESTION_CHOICES,
                         QUESTION_LINES, READY_BLOCKED_NOTE, READY_LINES, READY_ORIGIN, READY_ORIGIN_FIX,
                         RUN_ERROR_PREFIXES, STAMP_HM, STATUS_SHARE, TAB_LIVE, DraftCardRequested, QuestionCard,
                         QuestionNoteScreen, RunNote, _QuestionButton, _QuestionButtons, approve_plan_card,
                         blocked_note, card_clock, card_kind, card_route, draft_card_key, draft_card_of,
                         draft_reply_time, draft_tab_text, failed_card_buttons, failed_card_key,
                         failed_card_refusal, failed_card_source, failed_card_text, failed_plan_card_key,
                         failed_plan_restart, failed_plan_view, merge_card_open, merge_card_source, merge_key,
                         merge_same_attempt, merge_spec, merge_stage, merge_tasks_counts, note_text, origin_fix, plan_auto_approves, plan_card_counts, plan_card_source, plan_card_spec,
                         question_body, question_button_cells, question_button_rows, question_card_key,
                         question_cards, ready_blocked, ready_failing, ready_key, ready_source, ready_task,
                         ready_text, reply_occurrence, revise_plan_card, stamp_hm, token_run_id)
from .modals import (BootstrapScreen, ConfirmScreen, FinishingScreen, HelpScreen, LanguageScreen, Modal,
                     NoteScreen, RunScreen, TextScreen, journal_title)
from .screens import PlanScreen, SettingsScreen
from .text import (C1_CSI, CSI_INTRO, ELLIPSIS, GENERIC_ESC, STRING_INTRO, csi_end, decimal_text, display_width,
                   elide_end, elide_middle, escape_end, fit_cells, hang, plain_lines, plain_scan, plain_value,
                   short_count, shown, string_end, wrap_cells, wrapped)

REFRESH_SECONDS = 3.0
BLOCK_RECHECK_SECONDS = 10.0  # a blocked-start message on the plan screen is re-checked this often
# i6: these names keep the catalog id of their line, never the line itself, so every render reads the language
# chosen now (`strings.text`); they stay module attributes for the callers and tests that reach them here.
STOP_REQUESTED = "chat.stop_requested"
CONFIRMED_SECONDS = 5.0  # a confirmed action's pending line waits this long for the snapshot that shows it
TAILABLE = ("running", "stopping", "failed_recoverable", "failed")
READING = "chat.reading"
CHECK_SECONDS = 60.0
LOG_LINES = 500
# The finishing modal's one line (FinishingScreen reads it): i6 lists `QUIT_WAITS` among the status lines whose text
# moves into the catalog, so the constant holds the id and the modal renders `strings.text` of it (its `ru` is this
# literal, so a Russian screen keeps the line). The rest of that modal — its key bar and the other modals — stays
# out of i6's scope (`docs/RELEASE_0.5.2_PLAN.md`).
QUIT_WAITS = "chat.quit_waits"
# R-2: a `--fixture ID` demo has no architect chat at all; the pane says so (with the standard catalog code of a
# refusal to act in this state) and Enter/retry/reset have nothing to reach.
CHAT_FIXTURE = "chat.fixture"
PANEL_HINT = "canvas.plan_footer"  # the line UI's footer; the Plan tab no longer shows it (`plan_tab_line`)
# C0c2/I1c: the canvas pane is a TabbedContent. The ids are the `TabPane` ids (`TabbedContent.active` takes them);
# the titles are what the tab strip shows. `Plan` holds the unchanged PlanPanel (the same id `plan-pane`); `Now`
# holds the live lines of the active attempt and the planner's or the run's lines. The old third tab, `Log`, is
# gone (I1c): the observed attempt's stored journal (`snapshot.journal`) now shows in the always-visible `Activity`
# pane below the canvas, so the canvas is once more two tabs.
TAB_PLAN = "tab-plan"  # `TAB_LIVE` ("tab-live") is `card_kinds`'; never `#plan`/`#live`: the pane bodies keep those ids
# i6: the tab titles are catalog ids too (the strip labels are re-read by `MainScreen.relabel` when the language
# changes, `TabPane`s being built once).
# i9/A4: the canvas tabs read "Scheme" and "Plan" like the lab (`pane.flow` / `pane.plan`), not "Now".
TAB_LIVE_TITLE, TAB_PLAN_TITLE = "pane.flow", "pane.plan"
# I7: in narrow mode "Conversation" joins the front of the tab cycle. It is not a TabPane (the chat pane is outside
# `#right`), so the selected page lives in `MainScreen.chat_shown` and the strip gets a plain `Tab` label of this
# id (`sync_narrow_label`) rather than a switchable pane.
TAB_CHAT = "tab-chat"
# I5: the file/diff canvas tabs. A file or a finished stage's diff opens as one more read-only tab after "Plan"
# (the write side is `terminal_planner/tui/viewer.py`; the tabs only show what it resolves and renders). At most
# `FILE_TABS_MAX` file tabs stay open — opening a fourth closes the oldest — and there is one diff tab, replaced in
# place when another diff is asked for. `TAB_DIFF` is its fixed id; file tabs get ids of their own (`tab-view-N`).
# A file tab's title is the file name elided to `FILE_TITLE_CELLS` so a long name cannot push the strip wider than
# the labels it shows.
FILE_TABS_MAX = 3
FILE_TITLE_CELLS = 24
TAB_DIFF = "tab-diff"
# A1: what a `Now` tab with nothing live says; the snapshot's own "Next:" line follows it when it has one.
NOTHING_RUNNING = "canvas.nothing_running"
# F2/A3: the width below which the Now tab keeps C0c2's plain lines rather than the scheme drawing (I1b).
FLOW_MIN_WIDTH = 40
# T4e: the height `/scheme` hands `scheme.render` on the whole screen — far more than the boxes of the longest graph
# need, so box mode (`_full`) is chosen by the width alone and the pane scrolls.
SCHEME_FULL_ROWS = 200
# I7: below this many columns the main screen shows one pane at a time — the chat or the canvas — full width,
# because at 80x24 the two side by side are both too narrow to read. At or above it both panes show, as today.
NARROW_COLUMNS = 100
# The plan *screen*'s progress border title: `screens.py` assigns this constant straight to `#plan-progress`, so it
# stays the Russian literal that screen has always shown (PlanScreen is outside i6). The main screen's own chat
# pane border resolves the catalog id `chat.title_planning` (same literal in `ru`) separately in `render_state`.
PROGRESS_TITLE = "Planner"
PROGRESS_LINES = 200
NOT_STARTED = "Not started: fix what is marked above first."  # the failing checks are listed with it
QUIT_BUDGET = 4.0  # seconds from Ctrl+Q for the whole exit: the cancelled turn and a cut watch slice share it
LOG_PLACEHOLDER = "The install log is empty so far: use the \"install\" or \"log in\" button."
EMPTY_CHANGE = "Empty text: the plan is unchanged."
# P1a: the note a revision of a stale proposal carries when the owner sends none — the cause is all the planner needs.
RENEW_NOTE = "The project changed after planning: rebuild the plan"
# The line a start refused as stale shows: the unsent revision no longer matches the project (or the Zeroshot
# binding) it was prepared on. One wording for both places it is said — the plan screen's own watch (`watched`) and
# a draft card's `/plan` whose submission came back `stale` (i3a/A2 repair; nothing was sent, so the card stays).
PLAN_OUTDATED = "The plan went stale before it was sent (the project or Zeroshot changed): /view opens the plan."
# Key bars: catalog order is the display order; the primary names keep their labels longest (catalog.bar).
PRIMARY = {"tui_input": ("send", "cancel", "settings", "panel", "quit"),
           "tui_panel": ("plan", "answer_draft", "run", "resume", "attempt", "check", "stop", "open", "quit"),
           "tui_plan": ("move", "press", "back"),
           "tui_settings": ("move", "press", "back"),
           "tui_run": ("merge", "diff", "accept", "answer", "attempt", "new_attempt", "plan", "resume", "check",
                       "leave", "tail", "details", "back"),
           "tui_bootstrap": ("accept", "configure", "later"), "tui_profile": ("move", "pick", "save", "cancel"),
           "tui_confirm": ("yes", "press", "no"),
           "tui_confirm_run": ("yes", "start", "no"),
           "tui_answer": ("button", "send", "back"), "tui_note": ("button", "send", "back"),
           "tui_attempt": ("button", "send", "back"), "tui_diff": ("scroll", "close"), "tui_details": ("scroll", "close"),
           "tui_help": ("close",)}
# U-3: a draft key's full label outlives every optional action's label (and the exit hint, the one action a crowded
# bar must never leave unlabelled), so `[t] answer draft` still fits at the supported 80x24.
RESERVE = {"tui_panel": ("answer_draft", "quit")}


LETTER_HINT = re.compile(r"\[[a-z]\]")


# i10/P3: the line UI's `[p] plan` hints as the TUI does the same step (`/plan` acts only on a goal draft, so
# neither of these is `/plan`: a goal is written to the architect, a proposed plan is approved with `/approve`).
PLAN_TAB_HINTS = {"Next: [p] plan — describe the goal": "Next: write the goal to the architect in the chat",
                  "Next: [p] plan — approve or revise":
                      "Next: /approve — approve, or tell the architect what to revise"}


# i11: the "Next:" hints whose letter key `/run` replaces (a ready milestone, a new attempt of a stopped or failed
# one, a re-check); K1d: wherever in the line they stand ("..., then [g] check readiness.").
RUN_TAB_HINT = re.compile(r"\[g\] (start|new attempt|check|continue) (?=\S)")
# K1d: the one table of the line UI's letter keys as the TUI step that does the same (K1a-K1c3 removed the keys; the
# texts the services write for the line UI still name them). A step with a button names the label the service text
# may repeat after the letter (`[l] refresh login` is `/setup → log in`, not `/setup → log in refresh login`).
KEY_COMMANDS = {"g": "/run", "o": "/attempt", "w": "/attempt", "n": "/attempt", "p": "/view", "e": "/log",
                "i": "/details", "d": "/diff", "t": "/answer", "u": "/setup → install", "l": "/setup → log in",
                "r": "/view → revise"}
KEY_LABELS = {"u": r"install(?: tools)?", "l": r"log in|refresh login",
              "r": r"revise|reconsider"}
KEY_HINT = re.compile(r"\[([%s])\]( (?:%s)(?!\w))?" % ("".join(KEY_COMMANDS), "|".join(KEY_LABELS.values())))
# K1d: Settings has the buttons "install" and "log in" instead of those two steps (labels: the catalog's).
SETTINGS_BUTTONS = {"u": "tui_settings.setup", "l": "tui_settings.login"}
SETTINGS_TAIL = re.compile(r"\s+—\s+\[([ul])\]\s.*$")  # `— [l] log in (…)` ends in the button
SETTINGS_KEY = re.compile(r"\[([ul])\]")


def command_hints(text):
    """K1a + K1d: `text` with each letter key it names (`[g]`, `[l]`, …) replaced by the TUI step that does it now
    (`KEY_COMMANDS`, the one table); a bracketed letter outside the table stays as it is."""
    def step(found):
        letter, label = found.groups()
        if label is not None and not re.fullmatch(KEY_LABELS.get(letter, r"(?!)"), label.strip()):
            return KEY_COMMANDS[letter] + label
        return KEY_COMMANDS[letter]
    return KEY_HINT.sub(step, text)


def button_hints(text):
    """K1d: `text` as Settings shows it — `[u]` and `[l]` name the buttons ("the \"log in\" button"), every other letter key
    its step (`command_hints`)."""
    def button(found):
        name = "«%s»" % catalog.label(SETTINGS_BUTTONS[found.group(1)])
        return ("Button " if found.start() == 0 else "button ") + name
    text = SETTINGS_TAIL.sub(lambda found: " — button «%s»" % catalog.label(SETTINGS_BUTTONS[found.group(1)]), text)
    return command_hints(SETTINGS_KEY.sub(button, text))


def plan_tab_line(line):
    """i10/P3 + K1a + K1d: a line of the line UI as the Plan tab shows it. The tab has no letter keys, so a "Next:"
    hint in PLAN_TAB_HINTS becomes the TUI step that does the same and every letter key a line names becomes its
    step (`command_hints`); a "Next:" line that still names a letter outside the table has no TUI step to name and
    is dropped (`None`). Other lines pass unchanged."""
    if not line.startswith("Next:"):
        return command_hints(line)
    line = PLAN_TAB_HINTS.get(line, line)
    line = RUN_TAB_HINT.sub(lambda found: "/run — %s " % found.group(1), line)
    line = command_hints(line)
    return None if LETTER_HINT.search(line) else line


def keys_bar(screen, width, include=None):
    """The key bar of a TUI screen for `width` (the widget's usable width in cells): whole actions, the primary
    ones labelled, never cut mid-word (R-1: every action shown keeps a nonempty label while the bar can afford
    it)."""
    return catalog.bar(screen, include, max(width, 10), primary=PRIMARY.get(screen, ()),
                       reserve=RESERVE.get(screen, ()))


def bar_width(widget, fallback):
    """R-1: the usable width in cells of one key-bar widget — the widget's own content region, so the bar is cut
    to the width it really has (its width in the terminal, minus its padding and border). A fixed constant or a
    screen-derived estimate is wrong as soon as the bar sits in an inset modal. Before the first layout the region
    is empty and `fallback` keeps the previous estimate; the resize that follows re-renders the bar."""
    width = widget.content_region.width
    return width if width > 0 else fallback


def screen_header_rows(width, height):
    """The rows MainScreen spends above its body: none since i9 — the approved lab look drops the logo and the
    header, so the panes begin at row 0. The result modal is constrained below exactly these rows (R-3), from the
    same rule that lays the main screen out."""
    return 0


def chat_keys_ready(app):
    """R-B: the guard of the conversation's PageUp/PageDown: the main screen with no modal on top and the focus in the
    plan pane (`draft_keys_ready`) or in the chat input — the keys are no text there, and the owner reads the history
    from where they type."""
    return draft_keys_ready(app) or (isinstance(app.screen, MainScreen) and getattr(app.focused, "id", None) == "input")


def draft_keys_ready(app):
    """The main screen with no modal on top and the focus in the plan pane (`#plan-pane`, the non-editor focus Tab
    reaches from the chat input): the guard of the pane's PageUp/PageDown (`chat_keys_ready`). No letter key acts
    there since K1a/K1b; every action is a `/` command."""
    return isinstance(app.screen, MainScreen) and getattr(app.focused, "id", None) == "plan-pane"


def set_message_role(widget, role):
    """Put `role` on one entry widget (`ChatMessage`): the role rides the widget's classes (`msg <role>`, the lab's
    `.msg` rows), so the old role class is taken off and the new one added; the role also shapes the body's gutter,
    so the body is painted again. `add_class`/`remove_class` take *names*, never one space-joined name —
    `"msg architect"` is not an identifier and raises `textual.dom.BadIdentifier` — so `msg` and the role are
    passed separately."""
    if widget.role == role:
        return
    widget.remove_class("msg", widget.role)
    widget.add_class("msg", role)
    widget.role = role
    widget.paint()


Shown = namedtuple("Shown", "time blocks")  # one entry as the pane keys and draws it: its time line, its L-2 blocks


def entry_rows(entries):
    """The retained history as one row per entry, in order: `(entry, role, shown)`, where `shown` is the entry's
    time line (`chat.time_labels`, "" for none) and its blocks (`chat.entry_blocks`), each block's lines escaped
    per L-2 and joined again.

    The `ChatEntry` itself rides along: the reconciliation follows the entries, not the display text."""
    return [(entry, entry.role, Shown(label, tuple((kind, "\n".join(plain_lines(text)))
                                                   for kind, text in chat_module.entry_blocks(entry))))
            for entry, label in zip(entries, chat_module.time_labels(entries))]


def chat_window_shift(old, new):
    """How the retained history moved between two renders: `(dropped, appended)` when `new` is `old` with
    `dropped` leading entries gone and `appended` (the rest of `new`) mounted at the end, the common part
    unchanged; None when no shift fits, because a reload rewrote the window's own keys. The keys are the entries
    (`ChatEntry`) wherever the screen tracks them; the display texts are the fallback key on a screen that carries
    only those. The smallest shift wins, so a plain append reports no drop."""
    for dropped in range(len(old) + 1):
        if old[dropped:] == new[:len(old) - dropped]:
            return dropped, new[len(old) - dropped:]
    return None


def chat_window_run(old, new):
    """The longest run of keys the two rendered windows share at some offset: `(old_start, new_start, length)`, the
    block of entries that stayed, in both orders `old_start == new_start == 0` for a plain append and a different
    pair of offsets for a window that slid while an optimistic tail left. Both windows are views of one append-only
    transcript — plus, at the tail, the owner's own line while a send is in flight — so what the reload kept is one
    contiguous block: the entries before it left (the front of a capped window), the ones after it arrived, and the
    owner's line that never persisted is simply gone. A run of length 0 means the windows overlap in nothing at all:
    a reload that pushed the whole window out at once. The keys are the entries wherever the screen tracks them and
    the display texts otherwise, exactly as `chat_window_shift` measures its slide."""
    best = (0, 0, 0)
    for old_start in range(len(old)):
        for new_start in range(len(new)):
            if old[old_start] != new[new_start]:
                continue
            length = 1
            while (old_start + length < len(old) and new_start + length < len(new)
                   and old[old_start + length] == new[new_start + length]):
                length += 1
            if length > best[2]:
                best = (old_start, new_start, length)
    return best




# I1a/A4: the main screen's key help names the tab controls, which are screen bindings rather than catalog actions
# (the catalog has no tab-key action): the arrows that switch the right pane's tabs and the mouse click on a tab
# label — so [F1] names the same controls the main key bar does. They ride the help's first line in the catalog's
# own `Keys · …` shape (`help_lines`), so [F1] shows them at once and the catalog's keys keep their room at 40
# rows (the help list otherwise already fills a 40-row terminal and would push its tail out of view).
TUI_MAIN_SCREENS = ("tui_input", "tui_panel")
TAB_HINT = " · [← / →] tabs — cycle through them; click a tab label — show it"


def help_text(*screens):
    """The key help overlay: for each screen its title and keys, straight from the catalog actions. When the help
    covers the main screen its own tab guidance (`TAB_HINT`) rides the first line, because those controls are screen
    bindings, not catalog actions, so the catalog cannot name them (I1a/A4)."""
    main = any(screen in TUI_MAIN_SCREENS for screen in screens)
    lines = ["Keys" + (TAB_HINT if main else "")]
    for screen in screens:
        lines += ["", catalog.SCREENS[screen].title + ":"] + catalog.key_lines(screen)
        if catalog.SCREENS[screen].footer:
            lines.append("  " + catalog.SCREENS[screen].footer)
    return "\n".join(lines)


PLAIN_KEYS = re.compile(r"\s+—\s+\[[id]\].*$")  # plain-screen keys ([i] details, [d] view) do not exist here


def fit(variants, width):
    return next((v for v in variants if len(v) <= width), variants[-1])


def check_name(check):
    """What a failed readiness item is called in a line or the header: the plain text without its plain-only key."""
    return PLAIN_KEYS.sub("", summary(check.line))


# R-4: the Settings actions that fix a readiness item, keyed by the structured Check.key (setup.item): only a
# key the Settings screen actually binds is used; any other item falls back to the catalog's key-free remedy
# for its structured Check.id and key (`catalog.remedy_free`), never to its `detail`, which may carry a
# disabled key, nor to its `line`/`doctor` text, which would be parsing free text for a fix.
CHECK_REMEDY = {"u": "tui_settings.setup", "l": "tui_settings.login"}


def check_label(check):
    """The failing item's owner-facing name for a closing line: `check_name`'s bounded line without the trailing
    `— [key] ...` hint the item itself carries. The hint is located with the structured `Check.key`, never parsed
    out of the text, and the closing line names that key once, from the same field."""
    text = check_name(check)
    marker = "— [%s]" % check.key
    found = text.rfind(marker) if check.key else -1
    return text[:found].rstrip(" —") if found > 0 else text


def tools_pass(checks):
    """True when the slice answered for the checks the architect chat needs (planning.TOOL_CHECKS) and every one
    of them passes; the start-only checks (Git identity, branch) are none of the chat's business."""
    tools = [c for c in checks if c.id in planning.TOOL_CHECKS]
    return bool(tools) and all(c.ok for c in tools)


def check_closing(checks, error, next_ids=()):
    """The one closing line of a completed interactive readiness batch, from its own result (R-4): the all-OK
    line with the enabled next keys, the failing Check names with a remedy the Settings screen really offers now
    (else the Check's own key-free remedy), the empty-result line, or the error. The names and the remedy come
    from the structured Check fields, never from parsing the line text for a key."""
    if error:
        return catalog.CHECK_ERROR + error
    if not checks:
        return catalog.CHECK_EMPTY
    failed = [c for c in checks if not c.ok]
    if not failed:
        tail = ", ".join(catalog.text(i) for i in next_ids)
        return catalog.CHECK_DONE + (" %s %s" % (catalog.NEXT, tail) if tail else "")
    names = "; ".join(check_label(c) for c in failed)
    # K1c2: the buttons share the key Enter, so an offered action is told apart by its id, not its key
    remedy = next((CHECK_REMEDY[c.key] for c in failed
                   if c.key in CHECK_REMEDY and CHECK_REMEDY[c.key] in next_ids), None)
    if remedy is not None:
        return "! %s — %s" % (names, catalog.text(remedy))
    # No offered key fixes these items: every failing item names the catalog's key-free remedy for its own
    # structured id and key, in the order the items failed. The item's `detail` is not used: real readiness items
    # put a key into it (`Installation: [u] ...`, `[l] starts the login ...`), and this session's Settings screen may
    # not bind that key (R-4). The key discriminates the one id whose causes differ: the auth item is a missing
    # login file or an unset environment key, and only the first is repaired by [l] (R-4).
    free = ", ".join(dict.fromkeys(catalog.remedy_free(c.id, c.key) for c in failed
                                   if catalog.remedy_free(c.id, c.key)))
    return "! %s%s" % (names, " — " + free if free else "")


def coalesce_check(pending, request):
    """The one follow-up readiness batch waiting for the running check (R-4): a later request coalesces into it,
    an interactive request makes the batch interactive (its one closing line is then owed), a background one never
    turns an interactive batch back into a silent one, and the batch keeps the origin of the request that asked
    last for the kind it is."""
    if pending is None:
        return request
    generation, origin, interactive = pending
    return (generation, request[1] if request[2] else origin, interactive or request[2])


def readiness_summary(checks, room=None):
    """`header.ready`, or `! <failed check>` (more than one: `! <first> · <n> more`); a count when `room` is too
    small. The words are the `header.*` catalog ids, so the line follows the chosen language; the `!` mark and
    the ` · ` separators are punctuation, not text, and stay in code (`check_name` is the check's own line)."""
    if checks is None:
        return strings.text("header.checking")
    failed = [c for c in checks if not c.ok]
    if not failed:
        return strings.text("header.ready")
    text = "! " + check_name(failed[0]) + (" · %s" % strings.text("header.failed_more", n=len(failed) - 1)
                                           if len(failed) > 1 else "")
    if room is not None and len(text) > room:
        # `plural` glues the count to the chosen word, exactly as it did over the literals, so the three catalog
        # forms keep the count the line always had (the words themselves are `strings.text`).
        text = "! " + plural(len(failed), strings.text("header.not_passed_one"),
                             strings.text("header.not_passed_few"), strings.text("header.not_passed_many"))
    return text


def header_text(project, branch, checks, width, note=""):
    """`<project> · <branch> · <readiness>[ · <profile note>]`, the project name shortened first when the line
    does not fit."""
    room = max(width - 2, 20)
    extra = " · " + note if note else ""
    ready = readiness_summary(checks, max((room - len(extra)) // 2, room - len(extra) - len(project) - len(branch) - 6))
    tail = " · %s · %s%s" % (branch, ready, extra)
    left = max(room - len(tail), 4)
    name = project if len(project) <= left else project[:left - 1] + "…"
    return name + tail


# i2: the bottom `Bar`'s four key hints, as `(key, catalog id)` pairs (`activity.bar_text`'s `keys`): the arrows,
# `/`, esc and ctrl+q, named by the frozen `bar.key_*` strings of `strings.py`.
BAR_KEYS = (("←→", "bar.key_tabs"), ("/", "bar.key_commands"), ("esc", "bar.key_close"), ("ctrl+q", "bar.key_quit"))
# i9/A1: the idle bar names only the tabs, the commands and the exit key (the lab's `_render_bar` adds `esc` only
# for a running job or an open file/diff tab); the `esc` hint joins `BAR_KEYS` then.
BAR_KEYS_IDLE = (("←→", "bar.key_tabs"), ("/", "bar.key_commands"), ("ctrl+q", "bar.key_quit"))
# O3: while the `/` palette is shown the bar names the keys that work it instead of the tabs and the `/`.
BAR_KEYS_PALETTE = (("Tab", "bar.key_complete"), ("↑↓", "bar.key_pick"), ("esc", "bar.key_close"),
                    ("ctrl+q", "bar.key_quit"))
# i2: the `Bar`'s job word per slash state (`activity.JOB_IDS`' keys plus the two timed jobs); a state without a job
# (idle, draft) shows `bar.idle`.
JOBS = {"planning": "planning", "running": "running", "plan_ready": "approve",
        "merge": "merge", "question": "question", "error": "error"}


def running_row(rows):
    """The `Row` of the one running stage, or None: `/stop` targets it whatever row the owner has selected."""
    return next((row for row in rows if row.state == "running"), None)


def note_is(note, id):
    """Whether `note` is the catalog line `id`, by identity, never by its rendered (language-dependent) text."""
    return isinstance(note, RunNote) and note.id == id


def progress_error(progress):
    """The planner pane's displayed note when its last line is an operation error or blocked result, else "" (i2,
    code-review repair). The pane shows `app.progress`; an observation failure (`ZplanApp.watched` with an error)
    appends "Not done: …" as that run's final line and stops watching, so the newest line is the screen's own
    fact for a lost/blocked observation whose revision still reads `observing` — `slash_state` can then report
    `error` instead of a phantom `planning`. Only the last non-blank line counts: a later, successful re-observation
    appends its own phases over the failure, so a stale failure never pins the state (scanning every line would)."""
    for line in reversed(list(progress)):
        text = (line or "").strip()
        if text:
            return blocked_note(text)
    return ""


def slash_state(snapshot, blocked="", watching=False, draft=False):
    """The one `slash.STATES` value the main screen is in (i2/A4), from the facts the screen already holds: the
    `snapshot` (its rows and the planning service's plan), a shown error/blocked line (`blocked`), the planner
    `watching` and an open goal `draft`. Pure: no widget, no controller, no engine call.

    Precedence (R-B): a running stage first, which beats an unrelated error/status line; then a shown error/blocked
    line or a blocked/failed/stopped stage (`error`), an owner question (`question`), a stage waiting for merge
    (`merge`), the planner (`planning`), an open goal draft (`draft`), a plan proposed but not approved
    (`plan_ready`), else `idle`; a failed planning run (`error`) ranks with a shown error when no draft is open.
    Where a fact does not exist the nearest state is taken: `planning` also covers a plan the screen only observes, and `plan_ready` is the `proposed` revision status the
    snapshot names (there is no separate approved-not-sent flag). An open goal draft wins only when nothing else
    is active: a draft card open beside a running stage must not hide the stage (the bar and the canvas title name
    the job, not "no work" / "Goal draft"). The i3a rule stays for the plan screen's own failure — its
    `kind == "failed"` view, whose body is the "planning stopped" line, or the `run_failed` /
    `proposal_invalid` status behind it: that run is what the draft card asks to redo, so the typed `/plan` must
    reach the card exactly as the card's button does; with no draft the bar reports the failure and the palette
    stops offering idle commands.
    """
    rows = snapshot.rows if snapshot is not None else ()
    if any(row.state in ("running", "stopping") for row in rows):
        return "running"
    planning_failed = (snapshot is not None
                       and ((snapshot.plan is not None and snapshot.plan.kind == "failed")
                            or snapshot.status in ("run_failed", "proposal_invalid")))
    if (blocked or (planning_failed and not draft)
            or any(row.state in ("blocked", "failed", "failed_recoverable", "stopped") for row in rows)):
        return "error"
    if any(row.state == "needs_owner" for row in rows):
        return "question"
    if any(row.state in ("awaiting_merge", "conflict") for row in rows):
        return "merge"
    if watching or (snapshot is not None and snapshot.plan is not None and snapshot.plan.kind == "observing"):
        return "planning"
    if draft:
        return "draft"
    if snapshot is not None and snapshot.version is not None and snapshot.status == "proposed":
        return "plan_ready"
    return "idle"


def draft_card_state(app):
    """i3a: whether the main screen of `app` holds an *open* goal-draft card — the fact `screen_slash_state` reads as
    the `draft` state.

    The card belongs to that screen's own pane, and a modal above it (the help) never takes the card away: the state
    stays `draft` until the card is closed or dropped."""
    screen = next((item for item in app.screen_stack if isinstance(item, MainScreen)), None)
    return screen is not None and screen.draft_card_open()


def screen_slash_state(app):
    """`slash_state` for the main screen's app: the error/blocked lines it shows are the plan-open error
    (`app.plan_error`, the plan pane's `Not opened: …`) and the run pane's own operation error or blocked note
    (`blocked_note(app.run_note)`, e.g. a readiness-blocked start), and the planner pane's own displayed failure
    (`progress_error(app.progress)`, a lost/blocked observation whose revision still reads `observing`). The
    `draft` state is an open goal-draft card on the main screen (`draft_card_state`, i3a). The displayed planner failure only counts while the planner is *not* watching: an active observation is «the
    planner running -> planning» even if a stale failure line still sits in the pane. The chat's own refusal is the
    chat area's line, not a stage error, so it does not flip the whole screen into `error` (which would leave every
    uninstalled session there). No controller or engine call."""
    planner_error = "" if app.watching else progress_error(app.progress)
    return slash_state(app.snapshot,
                       blocked=app.plan_error or blocked_note(note_text(app.run_note)) or planner_error,
                       watching=app.watching,
                       draft=draft_card_state(app))


# i9/A4: the milestone row the bar's job phrase and the canvas frame's title name — the row whose state matches the
# screen state; None when nothing runs (idle, draft, planning, plan_ready).
ROW_STATES = {"running": ("running", "stopping"), "question": ("needs_owner",),
              "merge": ("awaiting_merge", "conflict"),
              "error": ("blocked", "failed", "failed_recoverable", "stopped")}
# i9/A4: the canvas frame's own state title, per screen state (the lab's `_render_view` words).
SCHEME_TITLES = {"running": "canvas.scheme_running", "question": "canvas.scheme_question",
                 "merge": "canvas.scheme_merge", "error": "canvas.scheme_error"}


def active_row(app):
    """i9/A4: the milestone row the canvas frame's title names — the one whose state matches `screen_slash_state`."""
    wanted = ROW_STATES.get(screen_slash_state(app), ())
    return next((row for row in app.rows() if row.state in wanted), None)


def owner_stopped(row):
    """R-B: whether `row` is a milestone the owner stopped (`/stop`): a stop reads as a stop, not as an error, in the
    bar, the canvas title and the card — the slash state stays `error`, so `/run` still offers a new attempt."""
    return row is not None and row.state == "stopped"


def stage_label(row):
    """i9/A4: `M2 Export CSV` — a milestone row's id and title, the way the lab names the stage in a pane title."""
    return (row.id + " " + row.title).strip() if row is not None else ""


def canvas_title(app):
    """i9/A4: the canvas frame's border title, the lab's words per state — the project and `bar.idle` when nothing
    runs (`notes · no work`), the planner's or the running stage's phrase otherwise (`M2 <title> · running`). The
    frame is the `#right` box whose border wraps the tab strip, so the title names the canvas whichever tab shows."""
    state = screen_slash_state(app)
    if state in SCHEME_TITLES:
        row = active_row(app)
        if state == "error" and owner_stopped(row):
            return strings.text("canvas.scheme_stopped", stage=stage_label(row))
        if state == "error" and not stage_label(row):  # an error no milestone row owns: no blank name before it
            return strings.text("canvas.scheme_error_plain")
        return strings.text(SCHEME_TITLES[state], stage=stage_label(row))
    if state == "planning":
        return strings.text("canvas.scheme_planning")
    if state == "plan_ready":
        return strings.text("canvas.scheme_approve")
    if state == "draft":
        return strings.text("canvas.scheme_draft")
    snapshot = app.snapshot
    project = snapshot.project if snapshot else app.controller.name
    return "%s · %s" % (project, strings.text("bar.idle"))


class PlanPanel(VerticalScroll):
    """The right pane. No letter key acts on the main screen (K1a, K1b): every action is a `/` command typed in the
    chat (`COMMAND_ACTIONS`). The arrows select the milestone row."""
    BINDINGS = [Binding("up", "app.select(-1)", "Up", show=False), Binding("down", "app.select(1)", "Down", show=False)]


class RunAwarePalette(palette.Palette):
    """P1a: the palette lists `/run` only when it would act. `palette.py` lists every command its state allows and knows
    no milestone rows, so this one draws the same rows minus the commands the app says would refuse right now
    (`ZplanApp.palette_hidden`); a typed `/run` still reaches `palette.submit` and `action_run_next`'s refusal."""

    def rows(self, value, state):
        hidden = self.app.palette_hidden()
        return [command for command in super().rows(value, state) if command.name not in hidden]


class LeftHeading(Heading):
    """A heading in a chat reply: bold, left, no box (rich centres, frames and underlines them by default)."""

    @classmethod
    def create(cls, markdown, token):
        heading = super().create(markdown, token)
        heading.style_name = "bold"
        return heading

    def __rich_console__(self, console, options):
        self.text.justify = "left"
        self.text.style = "bold"
        yield self.text


class TightCode(CodeBlock):
    """A code block in a chat reply: no padding rows and no background, indented two cells."""

    def __rich_console__(self, console, options):
        yield Syntax(str(self.text).rstrip(), self.lexer_name, theme=self.theme, word_wrap=True,
                     padding=(0, 2), background_color="default")


class HtmlBlock(MarkdownElement):
    """HTML-looking lines in a chat reply: shown as typed, line for line, never rendered."""

    @classmethod
    def create(cls, markdown, token):
        return cls(token.content)

    def __init__(self, content):
        self.content = content

    def __rich_console__(self, console, options):
        yield Text(self.content.rstrip("\n"))


DRAWN_CONTENT = ("text", "text_special", "code_inline", "fence", "code_block", "html_block")  # token types whose content is drawn


class Reply(Markdown):
    """Rich Markdown for an architect's text. Rich drops `html_inline` / `html_block` tokens, so `Vec<String>` or
    `<!-- hi -->` would vanish; an inline one is made plain text here and a block one is an `HtmlBlock`."""

    elements = {**Markdown.elements, "heading_open": LeftHeading, "fence": TightCode, "code_block": TightCode,
                "html_block": HtmlBlock}

    def __init__(self, markup, **kwargs):
        super().__init__(markup, **kwargs)
        self.parsed = self.scrub(self.parsed)

    @classmethod
    def scrub(cls, tokens):
        """Every text the parse leaves to draw gets L-2 again, since Markdown decodes entities after the first
        escape: an inline `html_inline` becomes text, an image becomes its label as text (Rich draws an image ahead
        of the paragraph's words and drops its place in it), and each drawn content goes through `plain_lines`."""
        for token in tokens:
            if token.type == "image":
                token.content = "".join(child.content for child in token.children or ()
                                        if child.type in ("text", "text_special", "code_inline"))
                token.children = None
                token.type, token.tag, token.nesting, token.attrs = "text", "", 0, {}
            elif token.type == "html_inline":
                token.type = "text"
            if token.type in DRAWN_CONTENT:
                token.content = "\n".join(plain_lines(token.content))
            if token.children:
                cls.scrub(token.children)
        return tokens


GUTTERS = {"architect": ("●", "bold magenta"), "error": ("!", "bold red")}  # the 2-cell mark ahead of a body
# S1: an events entry's step rows (`chat.step_blocks`): the glyph and its colour in the 2-cell gutter ahead of the words.
STEP_MARKS = {"step_ok": ("✓", "green"), "step_run": ("▶", "cyan"), "step_bad": ("!", "red"), "step_idle": ("·", "dim")}


def step_row(kind, text):
    """S1: one step as a single row clipped to the pane's width: the glyph gutter, the words, then the dim detail
    after `chat.STEP_GAP`; a `step_more` row is the dim count, indented under the words."""
    if kind == "step_more":
        return Text("  " + text, style="dim", no_wrap=True, overflow="ellipsis")
    mark, style = STEP_MARKS[kind]
    words, _, detail = text.partition(chat_module.STEP_GAP)
    row = Text.assemble((mark + " ", style), words, no_wrap=True, overflow="ellipsis")
    if detail:
        row.append(chat_module.STEP_GAP + detail, style="dim")
    return row


def message_body(role, blocks):
    """V2: the renderable of one entry's blocks (`chat.entry_blocks`, already escaped per L-2). An architect's text
    is rich Markdown without links — model markup is never interpreted, Markdown only styles what it parses from the
    escaped text — a draft line is dim, a step is one `step_row`, every other text is plain; the architect and the error entries carry their
    mark in a 2-cell gutter."""
    parts = []
    for kind, text in blocks:
        if kind == "draft":
            parts.append(Text(text, style="dim"))
        elif kind.startswith("step_"):
            parts.append(step_row(kind, text))
        elif kind == "text" and role == "architect":
            parts.append(Reply(text, code_theme="ansi_dark", inline_code_theme="ansi_dark", hyperlinks=False))
        else:
            parts.append(Text(text))
    body = Group(*parts)
    if role not in GUTTERS:
        return body
    mark, style = GUTTERS[role]
    grid = Table.grid(expand=True)
    grid.add_column(width=2)
    grid.add_column(ratio=1)
    grid.add_row(Text(mark, style=style), body)
    return grid


class ChatMessage(Vertical):
    """One retained history entry (owner, architect, error, reset or events) as its own widget in the chat's scroll
    (`#chat`): an optional time line (`.time`, dim and centred) above the entry's body (`.body`, drawn by
    `message_body`). The role rides the widget's classes (`msg <role>`), the lab's `.msg` rows; the widget's height
    is its content, so the scroll pages through the entries the way the lab draws them and a card mounted beside
    one never clips a neighbour."""

    def __init__(self, shown, role):
        super().__init__(classes="msg " + role)
        self.role = role
        self.shown = shown

    def compose(self):
        time_line = Static(self.shown.time, classes="time", markup=False)
        time_line.display = bool(self.shown.time)
        yield time_line
        yield Static(message_body(self.role, self.shown.blocks), classes="body", markup=False)

    def on_mount(self):
        self.paint()  # an update that came while the children were still mounting

    def update(self, shown):
        self.shown = shown
        self.paint()

    def paint(self):
        """Draw `shown` into the children once they are mounted (before that, `compose` reads it)."""
        if not self.is_attached:
            return
        time_line, body = next(iter(self.query(".time")), None), next(iter(self.query(".body")), None)
        if time_line is None or body is None or not (time_line.is_attached and body.is_attached):
            return
        time_line.update(self.shown.time)
        time_line.display = bool(self.shown.time)
        body.update(message_body(self.role, self.shown.blocks))


EXAMPLE_IDS = ("chat.example_1", "chat.example_2", "chat.example_3")  # E1: generic goals, for any repository


class CardSlots(dict):
    """E1: the card each key's slot holds; a slot filled or emptied asks `changed` (the screen's `sync_intro`), so the
    intro follows the cards however they come and go."""

    def __init__(self, changed):
        super().__init__()
        self.changed = changed

    def __setitem__(self, key, card):
        super().__setitem__(key, card)
        self.changed()

    def pop(self, key, *default):
        card = super().pop(key, *default)
        self.changed()
        return card


class Intro(Vertical):
    """E1: what an empty chat shows in its scroll — the lead sentence, the dim "For example", the three examples with the
    selected one marked, and the dim hint — centred in the scroll. Not a `ChatMessage`; `MainScreen.sync_intro` owns it."""

    def __init__(self):
        self.lead = Static(markup=False, classes="lead")
        self.caption = Static(markup=False, classes="caption")
        self.examples = Static(markup=False, classes="examples")
        self.hint = Static(markup=False, classes="hint")
        super().__init__(self.lead, Center(Vertical(self.caption, self.examples, classes="pick")), self.hint,
                         classes="intro")

    def paint(self, selected):
        texts = [strings.text(example) for example in EXAMPLE_IDS]
        rows = Text()
        for index, example in enumerate(texts):
            rows.append(("\n" if index else "") + ("❯ " if index == selected else "› "), style="bold yellow")
            rows.append(example, style="bold" if index == selected else "")
        self.lead.update(strings.text("chat.intro"))
        self.caption.update(strings.text("chat.intro_caption"))
        self.examples.update(rows)
        self.hint.update(strings.text("chat.intro_hint"))


class LivePane(VerticalScroll):
    """T4e: the Scheme tab's scroll. The layout change `/scheme` makes (in either direction) lands after the refresh
    callbacks `toggle_scheme_full` can queue, so the pane itself reports its own resize and, for the few resizes
    that screen allows (`MainScreen.scheme_repaints`), the drawing is redone against the width it really has."""

    def on_resize(self, event):
        screen = self.screen
        if isinstance(screen, MainScreen) and screen.scheme_repaints > 0 and not screen.closing \
                and max(self.scrollable_content_region.width, 20) != screen.live_width:
            screen.scheme_repaints -= 1
            screen.render_settled()


class MainScreen(CardHost, Screen):
    BINDINGS = [Binding("tab", "toggle_focus", "Pane", priority=True),
                Binding("escape", "cancel_turn", "Cancel turn", priority=True),
                # I1a/A1-A3: the arrows switch the right pane's tab from anywhere on this screen. They are priority
                # so the chat input's own cursor keys (an `Input` binds left/right) hand them over; the action holds
                # the guard, so it still moves the cursor while the input holds text (A2) and does nothing on
                # another screen or under a modal (A3, where this screen is not the active one anyway).
                Binding("left", "view(-1)", "Tab left", priority=True),
                Binding("right", "view(1)", "Tab right", priority=True),
                # R-2: the scroll keys are priority so the plan pane (a VerticalScroll, which would otherwise eat
                # pageup/pagedown for its own paging) hands them to the chat; the action itself holds the guard, so
                # they still do nothing in the input, on another screen or under a modal.
                Binding("pageup", "scroll_up", "History up", priority=True),
                Binding("pagedown", "scroll_down", "History down", priority=True),
                # O3: the arrows in the chat input — pick a palette row, or recall the owner's previous line. Not
                # priority: the plan pane's own up/down (select a milestone) win when it holds the focus.
                Binding("up", "pick(-1)", "Up", show=False),
                Binding("down", "pick(1)", "Down", show=False)]
    # D4: the chat input starts focused, so the first keystroke is the owner's text. The plan pane binds only the
    # arrows; every action is a `/` command typed here.
    AUTO_FOCUS = "#input"
    ready = False
    status_text = None  # what `#status` shows now (None: not drawn yet)
    plan_lines = ()  # what the plan pane shows, line by line (before wrapping)
    live_lines = ()  # C0c2: what the Now tab shows, line by line (before wrapping)
    live_width = 0  # F2/A4: the pane width the tab was last drawn against (a settled re-render compares it)
    scheme_roots = None  # I1b: the stage graph per review-loop bound, built once in the screen's own dict
    journal_lines = ()  # I1c: what the activity pane shows, line by line (before wrapping); `snapshot.journal`
    tab_chosen = False  # C0c2/A1b: the start tab was picked from the first snapshot; the app never picks again
    history = ()  # O3: the lines the owner sent or ran in this run, oldest first (never saved)
    history_pos = None  # O3: the index of the recalled line the input still holds (None: not recalling)
    intro = None  # E1: the `Intro` mounted in `#chat` while the chat shows no entry and no card (None: not shown)
    example_pos = 0  # E1: the example the intro marks (0 whenever the intro comes back)
    tab_owner = "input"  # C0c2/A3: where the Plan tab returns the focus (`input` or `pane`); the start focus is the chat input
    focus_on_resume = None  # R-A C1: the widget that held the focus when the plan screen or Settings opened
    tab_focus_deferred = False  # C0c2/A3: a switch under a modal left the focus to it; take it back on resume
    closing = False  # L-5: the unmount has begun; no render runs and a late update is dropped
    narrow = False  # I7: below `NARROW_COLUMNS` the screen shows one pane at a time (one of these two)
    chat_shown = True  # I7: in narrow mode the chat pane is the shown one (`True`) or the canvas column (`False`)
    scheme_full = False  # T4e: `/scheme` shows the Scheme tab on the whole window (chat and activity not drawn)
    scheme_cmd = False  # T4e: on the whole-screen scheme the prompt is open at the bottom (a `/` was typed)
    scheme_repaints = 0  # T4e: the pane resizes after a `/scheme` toggle that may still redraw the tab (`LivePane`)
    full_return = None  # T4e: (tab, focused widget, chat_shown) to restore when the whole-screen scheme closes
    strip_shown = False  # I7: the "Conversation" label rides the canvas strip (narrow) or has been removed (wide)

    def compose(self):
        # i9: the approved lab look has no logo and no header — the panes begin at row 0, and the project, branch
        # and job state live only in the bottom `Bar`. The project · branch · state the old `#header` carried are
        # read by `show_keys`/`bar_job` at every render.
        with Horizontal(id="panes"):
            with Vertical(id="chat-pane"):
                # The conversation as a scroll of one widget per history entry (`ChatMessage`) with the decision
                # cards mounted inline in it (below), then the one status area on the input: the thinking clock or
                # the newest planner/run line, and the chat's own lines (the lab's indicator).
                yield VerticalScroll(id="chat")
                yield Static("", id="status", markup=False)
                # i9/A2: the `/` palette opens above the prompt box inside the chat pane (hidden until a `/` is
                # typed) and the prompt box (the lab's `#prompt-box`: a yellow chevron and the input) sits at the
                # pane's bottom, so the input line lives with the conversation it belongs to.
                yield RunAwarePalette(id="palette")
                with Horizontal(id="prompt-box"):
                    yield Static("›", id="chevron", markup=False)
                    yield Input(placeholder=strings.text("chat.placeholder"), id="input")
            # C0c2/A1: the canvas is a TabbedContent of "Scheme" and "Plan"; the plan tab holds the unchanged
            # PlanPanel (the same id `plan-pane`), the live tab the live lines and the planner's or the run's lines.
            # i9/A1+A4: the canvas frame is the `TabbedContent` itself (`zplan.tcss`): its border starts on row 0 and
            # wraps the strip, and its border title names the canvas state (`canvas_title`), so the title and the box
            # ride every tab rather than one pane.
            # I1c: the canvas sits in a Vertical above the always-visible "What's happening" pane (`Activity`), which
            # shows the observed attempt's stored journal; the canvas keeps the rest of the column's height (A1).
            with Vertical(id="right-column"):
                with TabbedContent(id="right", initial=TAB_PLAN):
                    with TabPane(strings.text(TAB_LIVE_TITLE), id=TAB_LIVE):
                        with LivePane(id="live-pane"):
                            yield Static("", id="live", markup=False)
                    with TabPane(strings.text(TAB_PLAN_TITLE), id=TAB_PLAN):
                        with PlanPanel(id="plan-pane"):
                            yield Static(strings.text("canvas.plan_loading"), id="plan", markup=False)
                yield Activity(id="activity")
        # i2/A3: the bottom row is the `Bar` (id `keys` kept, so its layout CSS still applies): project, branch,
        # the job phrase with its clock and the key hints. The other screens' and modals' bars are unchanged.
        yield Bar(id="keys")

    def on_mount(self):
        # i9/A4: the chat pane keeps the lab's one title (`Conversation with the architect`); the narrow pane pages it with
        # `chat.title_narrow` from `render_state`.
        self.query_one("#chat-pane").border_title = strings.text("chat.title")
        # D3: the conversation is anchored to its end: a view at the bottom stays there when the pane shrinks (the
        # status area above the input grows a row while a turn runs, a resize) or an entry or a card changes size;
        # an owner who scrolled away releases the anchor and keeps the position until the view returns to the end.
        self.query_one("#chat", VerticalScroll).anchor()
        self.query_one("#palette").display = False  # A1: hidden until a `/` is typed (no change event at the start)
        # I5: the file/diff canvas tabs this screen owns (per instance, never shared): their ids oldest first, the
        # resolved path each was opened from (so a second open activates the tab), the tab shown just before each
        # one became active (so esc returns to the real previous tab, base or view), the last base tab shown (the
        # fallback when that previous tab has already closed), and the counter naming the file-tab ids.
        self.view_tabs = []
        self.view_paths = {}
        self.view_prev = {}
        self.view_base = TAB_PLAN
        self.file_seq = 0
        # U1: a 1 s timer keeps the bar's turn clock, the thinking row's clock and spinner, and the turn's end current
        # between renders.
        self.set_interval(1.0, self.tick_clock)
        # i3a: the card slot's own bookkeeping, per screen instance. `card_widgets` is the card each key's slot
        # holds (mounted inline in `#chat`, open or closed), `card_specs` the spec it was built from (what
        # `close_card` closes), `draft_cards` the goal draft of every *open* draft card (the `draft` state,
        # `screen_slash_state`), and `cards_seen` every key ever shown or dropped — a key is never shown again.
        self.card_widgets = CardSlots(self.sync_cards)
        self.card_specs = {}
        self.draft_cards = {}
        self.cards_seen = set()
        # i3-chat-inline: the entry widgets of `#chat` in order, the display text and the `ChatEntry` each was
        # built from, so a render reuses them and only a real change (an appended entry, a reload) touches the
        # conversation — and the slide follows the entries, whose numbering the display text moves with — keeping
        # the scroll where the owner left it while a live line streams (R-4). `chat_go_end` is set when the view
        # owes a jump to the bottom (a new entry, an accepted send) and cleared once it happens.
        self.chat_entry_widgets = []
        self.chat_entry_texts = []
        self.chat_entry_entries = []
        self.chat_go_end = False
        # i3c: the merge card's own per-key caches. `merge_view` holds the (done, total) of the attempt a
        # card names — None until the one read of its view returns, and None when that view carries no tasks
        # line — and `merge_times` the HH:MM its `at` carries, read once when the card first appears.
        self.merge_view = {}
        self.merge_times = {}
        self.merge_overlap = {}  # D4b: card key -> the files of the owner's tree that stopped its landing
        self.ready = True
        self.layout_for(self.size)
        self.render_state()

    def on_unmount(self):
        """L-5: MainScreen has begun to unmount. From here on no render runs and a late chat update is dropped,
        never raising: by now its widgets are gone, and the app's own teardown below waits for the turn it cancels
        and for the controller — a wait a 0.2s timer can fire inside."""
        self.closing = True

    def on_resize(self, event):
        if self.ready and not self.closing:  # L-5: a resize landing inside the unmount paints nothing
            self.layout_for(event.size)
            self.render_state()
            # F2/A4: this render runs before the resize's layout pass, so the Now pane still reports its old —
            # often zero — geometry: the flow would be drawn to the previous pane width (boxes narrower than the
            # pane) or, once the stale width drops below `FLOW_MIN_WIDTH`, the plain fallback would stay on screen
            # although `snapshot.flow` is still set. Redraw the tab once the layout has settled, so it matches the
            # pane's final width (and the auto-height widget is re-measured).
            self.call_after_refresh(self.render_settled)
            # i2/A3: `render_state` above feeds the bottom row before this resize's layout pass, but the `Bar`
            # redraws its own cached fields when it is resized (`Bar.on_resize`), so that cached main bar lands
            # after a modal's own keys were set and paints over them (`app.py`'s old plain `Static` never repainted
            # itself, so swapping it for the `Bar` exposed this). Re-feed the row once the layout has settled: with
            # a modal on top this restores the modal's key bar, and without one it is the same main bar again.
            self.call_after_refresh(self.show_keys)

    def render_settled(self, attempt=0):
        """F2/A4: redraw the Now tab against the pane's settled width after a resize, so the drawing matches the
        pane's final geometry rather than the stale one `on_resize` read before the layout pass. A redraw can itself
        move that width — a taller drawing shows the pane's scrollbar, which narrows the content the next drawing is
        measured against — so `verify_live` checks once more. Bounded by `attempt`, and skipped once the screen is
        unmounting (the after-refresh callback can outlive the widgets it would touch)."""
        if self.closing:
            return
        self.render_live()
        self.render_status()  # S1b: leaving `/scheme`, the chat pane's width is only known now
        self.call_after_refresh(self.verify_live, attempt)

    def verify_live(self, attempt=0):
        """F2/A4: the drawing just made may have shown or hidden the pane's scrollbar, changing the width the next
        drawing would be measured against; redraw once more (bounded) so the drawn boxes always match the width the
        pane really has."""
        if self.closing:
            return
        settled = max(self.query_one("#live-pane").scrollable_content_region.width, 20)
        if attempt < 2 and settled != self.live_width:
            self.render_settled(attempt + 1)

    def layout_for(self, size):
        """I7: choose the pane layout from the terminal size. `size.width < NARROW_COLUMNS` sets `narrow` (and the
        screen class `narrow`): one pane at a time, full width. Entering narrow shows the chat; leaving it shows the
        canvas again (the tab `#right` holds, or `Plan` when it holds none), so a resize back to a wide terminal
        never leaves a hidden pane.

        i9: the old block/compact logo sizing is gone with the logo itself; this call now only paints the pane
        choice."""
        narrow = size.width < NARROW_COLUMNS
        if narrow != self.narrow:
            self.narrow = narrow
            self.chat_shown = narrow  # entering narrow shows the chat; leaving it shows the canvas
            if not narrow:
                right = self.query_one("#right", TabbedContent)
                if right.active not in self.view_tab_ids():
                    right.active = TAB_PLAN
        self.apply_narrow()

    def apply_narrow(self):
        """I7: paint the narrow/wide choice. Narrow shows exactly one of the two panes full width — the chat while
        `chat_shown`, else the canvas column — and the strip carries the "Conversation" label; wide shows both, as
        today, and drops the label. Called from `layout_for` and whenever `chat_shown` changes.

        Code review P2: hiding the canvas blurs whatever held the focus there — the plan pane, whose keys then die —
        and the chat input the owner goes on to type into stays empty. So the hand-off `show_tab` makes when it
        leaves "Plan" is made here too, the one place that hides the canvas (a switch or a resize): the canvas
        about to disappear reports that it owned the focus (`tab_owner = "pane"`, so a later return to "Plan" puts
        it back) and the focus moves to the chat input, exactly where the arrows leave it. A modal on top owns the
        focus itself and is left alone.

        i9 repair (the input moved inside the chat pane): the same hide now blurs the *chat input* when the chat is
        the pane going away — Textual drops the focus of a widget whose ancestor stops displaying, so the input the
        owner was typing into is left unfocused and the next keystroke dies. Revealing the chat again therefore
        gives the focus back where the reader types: when the chat is the pane just shown and nothing holds the
        focus (the state the hide leaves), the input takes it. A modal on top owns the focus and is left alone."""
        self.set_class(self.narrow, "narrow")
        chat = self.query_one("#chat-pane")
        canvas = self.query_one("#right-column")
        shown_chat = self.chat_shown if self.narrow else True
        shown_canvas = not self.chat_shown if self.narrow else True
        if self.scheme_full:  # T4e: the canvas alone, whatever the width; a typed `/` brings the prompt up at the bottom
            shown_chat, shown_canvas = self.scheme_cmd, True
        self.set_class(self.scheme_full, "scheme-full")
        self.set_class(self.scheme_full and self.scheme_cmd, "scheme-cmd")
        self.query_one("#activity").display = not self.scheme_full
        focused = self.focused
        hands_off = (not shown_canvas and canvas.display and focused is not None
                     and canvas in focused.ancestors_with_self)
        if hands_off:
            self.tab_owner = "pane"
        chat.display = shown_chat
        canvas.display = shown_canvas
        self.sync_narrow_label()
        if shown_chat and self.chat_go_end:
            self.call_after_refresh(self.scroll_chat_end)  # R-B: the jump that found no layout is made now
        if self.app.screen is not self:
            return
        if hands_off or (shown_chat and self.focused is None):
            self.query_one("#input").focus()

    def sync_narrow_label(self):
        """I7: the canvas strip's "Conversation" label. In narrow mode a disabled `Tab` is prepended to the built-in
        strip (before "Now"), so the cycle's first page is named there although the chat is not a TabPane; wide
        mode removes it. `strip_shown` remembers the choice, so the tab — mounted asynchronously — is added or
        removed exactly once per mode change and never twice."""
        tabs = self.query_one("#right ContentTabs")
        if self.narrow and not self.strip_shown:
            tabs.add_tab(Tab(strings.text("pane.chat"), id=TAB_CHAT, disabled=True),
                         before=tabs.get_content_tab(TAB_LIVE))
            self.strip_shown = True
        elif not self.narrow and self.strip_shown:
            tabs.remove_tab(TAB_CHAT)
            self.strip_shown = False

    def show_chat(self):
        """I7/A3: in narrow mode show the chat pane ("Conversation"), full width. In wide mode both panes are already
        shown, so this does nothing. The card runs call it when a card appears (the wiring is the orchestrator's at
        merge; no card is added here).

        I7 repair (code review P2): the focus hand-off when the hidden canvas was the focused one — and the
        remembering that "Plan" owned it — is `apply_narrow`'s, so showing the chat never leaves the input
        unfocused (see it there)."""
        if self.narrow:
            self.chat_shown = True
            self.apply_narrow()

    def show_canvas(self):
        """I7/A3: in narrow mode show the canvas column instead of the chat — the owner opened or activated a
        canvas tab. A no-op in wide mode (both panes show) and while the canvas is already the shown pane."""
        if self.narrow and self.chat_shown:
            self.chat_shown = False
            self.apply_narrow()

    def relabel(self):
        """i6: re-read every text this screen baked when it was composed, then repaint. The `TabPane`s and the
        chat input are built once, so a language switch would otherwise leave their labels in the old language:
        the tab strip's labels are set through `TabbedContent.get_tab(id).label`, the placeholder through the
        `Input` itself, and `render_state()` re-reads everything else it already paints (the header, the pane
        titles — the chat pane's own and the `Activity` border —, the plan lines and the status area). Called by
        `choose_language`; a call while the screen is not ready or is unmounting changes nothing (its widgets are
        gone or not built yet)."""
        if not self.ready or self.closing:
            return
        right = self.query_one("#right", TabbedContent)
        right.get_tab(TAB_LIVE).label = strings.text(TAB_LIVE_TITLE)
        right.get_tab(TAB_PLAN).label = strings.text(TAB_PLAN_TITLE)
        self.sync_card_keys()  # the input's placeholder, in the new language
        self.render_state()

    def choose_language(self, code=None):
        """i6: `/language` and the first-run chooser. With a `code` the catalog stores it at once, `relabel()`
        re-reads every baked label, and the status area above the chat names the code's own `display_name`
        (`note.language`) — so the whole screen reads the new language without a restart. With no code the chooser
        opens (`LanguageScreen`); a pick comes back here with its code, and an esc keeps the language in effect
        (the chooser stores it when nothing was stored yet, so it is asked once). With one offered language
        (`strings.OFFERED`) nothing opens and nothing changes: one note says so."""
        if len(strings.OFFERED) < 2:
            self.status_note(strings.text("note.only_russian"))
            return
        if code is None:
            self.app.push_screen(LanguageScreen(), lambda picked: picked and self.choose_language(picked))
            return
        strings.set_language(code)
        self.relabel()
        self.status_note(strings.text("note.language", name=strings.display_name(code)))

    def render_state(self):
        if not self.ready:
            return
        app = self.app
        snapshot = app.snapshot
        if app.plan_error:
            body = [strings.text("canvas.plan_error", error=app.plan_error)]
        elif snapshot is None:
            body = [strings.text("canvas.plan_loading")]
        else:
            pending = app.pending_text()
            body = [line for line in snapshot.lines if line.strip() and not (pending and line.startswith("Next:"))]
            if snapshot.panel:
                body += [""] + list(snapshot.panel)
            if pending:
                body += ["", "… " + pending]
            body = [line for line in map(plan_tab_line, body) if line is not None]
        self.plan_lines = body
        if CARD_SOURCES:  # mounted on the screen's own pump, never from inside a render (see DraftCardRequested)
            self.call_later(self.render_card_sources)
        selected = app.selection()
        marked = None
        if selected is not None and snapshot is not None and not app.plan_error:
            marked = snapshot.first_row + [r.id for r in snapshot.rows].index(selected.id)
        pane = self.query_one("#plan-pane")
        shown = Text()
        # The selection is style only: the lines stay exactly what the plain overview prints.
        for index, (first, rest) in enumerate(hang(body, max(pane.scrollable_content_region.width, 20))):
            shown.append("\n".join((first,) + rest) + "\n", style="reverse" if index == marked else "")
        shown.rstrip()
        self.query_one("#plan", Static).update(shown)
        self.render_live()
        # I1c/A2: the "What's happening" pane, from the observed attempt's stored journal the snapshot carries.
        self.render_activity()
        self.choose_tab()
        # i9/A4: the chat pane keeps the lab's one title (`Conversation with the architect`); in narrow mode it pages the
        # pane and names the keys instead (`chat.title_narrow`, i7).
        self.query_one("#chat-pane").border_title = strings.text("chat.title_narrow" if self.narrow else "chat.title")
        self.render_status()
        # The chat keeps its own area above the status: planner progress and the run watch stay readable while it is used.
        self.render_chat()
        # The status box on the input still has to take the rows this update added to it (its height is auto), so the
        # conversation's region is only settled after the next refresh: it is reconciled once more against the region
        # the scroll really has then, or a grown status line would leave the newest reply in a crop (L-1/L-4).
        self.call_after_refresh(self.render_chat)
        # i3a: the decision card of the newest actionable goal draft (the chat's own turn ends with it). The card
        # is shown once per key; the chat body it takes rows from is re-measured by the `render_chat` scheduled
        # above, which runs after this refresh's layout — the card is mounted by then.
        self.refresh_draft_card()
        self.show_keys()
        self.refresh_palette()

    def render_status(self):
        """The one status area on the input (`#status`, directly above the palette and the prompt box). Top to
        bottom: at most one activity row — the running turn (`<spinner> The architect is thinking… M:SS · <live>`), else
        the newest planner or run line — then a run note on its own row, then the chat's own lines (`chat_state`,
        `chat_note`, `chat_outcome`, `chat_refusal`) wrapped in full, so a remedy and a catalog code stay readable
        at any width. The area is capped at 40% of the pane and loses its top rows first (the activity row), so
        the lines nearest the input are the last to go."""
        if getattr(self, "scheme_full", False):  # S1b: the chat pane is hidden (width 0): nothing is measured or stored
            return
        app = self.app
        pane = self.query_one("#chat-pane")
        room = max(pane.content_region.width, 20)
        rows = max(int(pane.size.height * STATUS_SHARE), 1)
        thinking = chat_thinking(app)
        note = ""
        newest = ""
        if app.planner_pane():
            lines = [command_hints(line) for line in app.progress] \
                or ([strings.text("chat.planning")] if app.watching else [])
            lines += [app.finish_note] if app.finish_note else []
            newest = lines[-1] if lines else ""
        elif app.run_watch or app.run_note:
            rows = max(rows, 2)  # the note line keeps a row of its own
            lines = list(app.run_lines) or ([strings.text("chat.observing", stage=app.run_watch)]
                                            if app.run_watch else [])
            newest = lines[-1] if lines else ""
            note = note_text(app.run_note) if app.run_note else ""
        # The running turn is one escaped row (L-2/L-4); with none, the newest planner or run line is wrapped in full,
        # so an `/attempt` remedy stays readable. The note and the chat's own lines below are wrapped the same way.
        activity = [elide_end(thinking, room)] if thinking else wrapped([newest] if newest else [], room)
        # One status line while a turn runs: the note waits (it is not cleared) and shows again after the turn.
        own = [piece for text in (chat_state(app), "" if thinking else app.chat_note, chat_outcome(app),
                                  chat_refusal(app))
               if text for piece in plain_lines(command_hints(text))]
        tail = activity + wrapped([note] if note else [], room) + wrapped(own, room)
        text = "\n".join(tail[-rows:])
        if text != self.status_text:  # the 1 s clock repaints the area only when its text moved
            self.status_text = text
            self.query_one("#status", Static).update(Text(text))

    def render_live(self):
        """C0c2/A1 + I1b/A1: paint the Now tab from the same sources the area above the chat reads. While the
        snapshot carries an active attempt's flow (`snapshot.flow`) the tab is the stage scheme of
        `milestone.milestone_graph` with `scheme.observation_from_flow(snapshot.flow)` — the drawing, one legend
        line, then the planner's or the run's lines — and falls back to C0c2's plain lines below `FLOW_MIN_WIDTH`
        or without a flow (F2/A3). The width is the tab content's own region, recorded in `self.live_width` so a
        settled re-render (`verify_live`) can tell whether the drawing moved the pane's own width."""
        snapshot = self.app.snapshot
        pane = self.query_one("#live-pane")
        # i9/A4: the canvas frame's border title (`notes · no work`, `M2 <title> · running`, …), painted with the
        # tab. The frame is the `#right` TabbedContent around the tab strip (`zplan.tcss`), so the title names the
        # pane whichever of its tabs is shown.
        self.query_one("#right").border_title = canvas_title(self.app)
        live = self.query_one("#live", Static)
        width = self.live_width = max(pane.scrollable_content_region.width, 20)
        data = snapshot.flow if snapshot is not None else None
        showing = data is not None and width >= FLOW_MIN_WIDTH
        # F2/I1b: the `nowrap` rule that keeps a drawn line on one row (`zplan.tcss`) tags the widget only while the
        # drawing is shown, so C0c2's plain fallback below `FLOW_MIN_WIDTH` keeps Textual's own wrapping and a line
        # too wide in terminal cells is split onto a further row rather than clipped on the right.
        live.set_class(showing, "flow")
        if showing:
            # I1b/A7: the graph's own loop bounds are not facts of this attempt — the task loop's bound depends on
            # the task count, which the flow does not carry — so the bound is passed as `limits` and only when the
            # flow carries it (`runs.review_rounds`); the graph is then built with that bound (default 4 when
            # unknown) and no loop bound is drawn for the loops `limits` omits.
            rounds = data.get("rounds")
            known = rounds if isinstance(rounds, int) else None
            limits = {"review_loop": known} if known is not None else {}
            # F2/A4: the `nowrap` rule that keeps a drawn line on one row (`zplan.tcss`) clips any line wider than
            # the pane, so the appended planner/run lines are wrapped by terminal cells here
            # (`flow_draw.wrap_status`), not by characters (`wrapped`): a status line short in characters but wide
            # in cells keeps its tail on screen.
            tail = flow_draw.wrap_status(self.live_status(True), width)
            # I1b/A1: the scheme gets the pane's content height minus the legend line and the status lines (never
            # below 6), so the drawing, the legend and the tail fit the pane together.
            height = SCHEME_FULL_ROWS if self.scheme_full else max(6, pane.scrollable_content_region.height - len(tail) - 1)
            drawn = scheme.render(self.scheme_root(known if known is not None else milestone.TASK_ITERATIONS),
                                  scheme.observation_from_flow(data), width, height, limits=limits)
            legend = scheme.legend()
            self.live_lines = drawn.plain.split("\n") + [legend.plain] + tail
            body = Text()
            for index, line in enumerate([drawn, legend, *(Text(piece) for piece in tail)]):
                if index:
                    body.append("\n")
                body.append_text(line)
            live.update(body)
            if self.scheme_full:
                self.call_after_refresh(self.reveal_running, drawn.plain.split("\n"))
        else:
            self.live_lines = self.live_view()
            live.update(Text("\n".join(wrapped(self.live_lines, width))))

    def reveal_running(self, drawn):
        """T4e/F2: on the whole screen the drawing is taller than the pane, so after each repaint the pane scrolls just
        far enough for the running step to be visible: the heavy frame of a running box (box mode), else the row with
        the running mark (the one-line modes). The owner's own scroll is left alone while that row is in view."""
        if self.closing or not self.scheme_full:
            return
        row = next((i for i, line in enumerate(drawn) if "┏" in line), None)
        if row is None:
            row = next((i for i, line in enumerate(drawn) if scheme.SPIN[0] in line), None)
        if row is not None:
            pane = self.query_one("#live-pane")
            pane.scroll_to_region(Region(0, row, max(1, pane.scrollable_content_region.width), 3), animate=False)

    def toggle_scheme_full(self):
        """T4e `/scheme`: the Scheme tab on the whole window — the chat, the activity pane and the input are not drawn —
        and, shown again, back to the layout, tab and focus it had. The engine is not asked anything: only this
        screen's layout moves."""
        right = self.query_one("#right", TabbedContent)
        if self.scheme_full:
            tab, target, chat_shown = self.full_return
            self.scheme_full, self.scheme_cmd, self.full_return, self.chat_shown = False, False, None, chat_shown
            self.apply_narrow()
            if tab in self.view_tab_ids():
                right.active = tab
            if target is None or not target.is_attached or not target.focusable:
                target = self.query_one("#input")
            target.focus()
            self.render_state()
            self.settle_scheme()
            return
        self.full_return = (right.active, self.focused, self.chat_shown)
        self.show_tab(TAB_LIVE)
        self.scheme_full = True
        self.apply_narrow()
        self.render_state()
        self.settle_scheme()

    def close_scheme_cmd(self):
        """T4e: put the prompt away again on the whole-screen scheme: the input is emptied, the palette hidden and the
        focus goes back to the scheme's scroll."""
        self.scheme_cmd = False
        self.query_one("#input", Input).value = ""
        self.query_one("#palette").display = False
        self.apply_narrow()
        self.query_one("#live-pane").focus()

    def settle_scheme(self):
        """T4e: redraw the Scheme tab after the layout change of `toggle_scheme_full` — the panes that came or went
        change the tab's width; `LivePane.on_resize` repaints again once the width is really known."""
        self.scheme_repaints = 3
        self.call_after_refresh(self.render_settled)
        if self.scheme_full:  # the hidden input must not keep the keys: the focus goes to the tab once it is shown
            self.call_after_refresh(self.focus_scheme)

    def focus_scheme(self):
        if self.scheme_full and not self.closing and self.app.screen is self:
            self.query_one("#live-pane").focus()

    def scheme_root(self, rounds):
        """I1b: the stage graph of one attempt, built once per review-loop bound (`milestone.milestone_graph` is a
        pure builder but an expensive one). The graph's own `maxIterations` are not drawn as facts (`limits`,
        `render_live`): the bound here only shapes the graph `scheme.render` walks."""
        if self.scheme_roots is None:
            self.scheme_roots = {}
        root = self.scheme_roots.get(rounds)
        if root is None:
            root = self.scheme_roots[rounds] = milestone.milestone_graph(1, rounds)["root"]
        return root

    def live_status(self, leading):
        """C0c2/A1: exactly the planner's or the run's lines the area above the chat shows — `app.progress` with
        `app.finish_note`, or `app.run_lines` with `app.run_note`, the same sources in the same order. `leading` is
        whether a live line of the attempt precedes them, so a run's verdict note keeps its blank separator whether
        the attempt is shown as `snapshot.panel` (C0c2) or as the stage scheme (I1b). The chat's own lines
        (`chat_note`, `chat_outcome`, `chat_refusal`) belong to the area above the chat and are not repeated."""
        app = self.app
        lines = []
        if app.planner_pane():
            lines += [command_hints(line) for line in app.progress] \
                or ([strings.text("chat.planning")] if app.watching else [])
            lines += [app.finish_note] if app.finish_note else []
        elif app.run_watch or app.run_note:
            lines += list(app.run_lines) or ([strings.text("chat.observing", stage=app.run_watch)]
                                             if app.run_watch else [])
            if app.run_note:
                lines += ([""] if lines or leading else []) + [note_text(app.run_note)]
        return lines

    def live_view(self):
        """C0c2/A1: the Now tab's logical lines (before wrapping), the plain fallback F2/A3 keeps below the flow
        width: the live lines of the active attempt (`snapshot.panel`) first, then `live_status`'s planner or run
        lines (the blank separator before a run's note is kept because the attempt's lines lead). With none of them
        the tab says nothing is running, followed by the snapshot's own "Next:" line when it has one, so the key
        that starts the next step is named there too."""
        snapshot = self.app.snapshot
        lines = [command_hints(line) for line in (snapshot.panel if snapshot is not None else ()) if line.strip()]
        lines += self.live_status(bool(lines))
        if not lines:
            step = plan_tab_line(next((line for line in (snapshot.lines if snapshot is not None else ())
                                       if line.startswith("Next:")), "")) or ""
            lines = [strings.text(NOTHING_RUNNING) + (" " + step if step else "")]
        return lines

    def journal_view(self):
        """I1c/A2: the activity pane's logical lines (before wrapping): the observed attempt's stored journal
        entries, oldest first (`snapshot.journal`, already scrubbed and formatted by the delivery service). Nothing
        is filtered, searched or reordered here, and an empty journal stays empty: the `Activity` widget draws its
        own `canvas.log_empty` line then, so `JOURNAL_EMPTY` is gone."""
        snapshot = self.app.snapshot
        entries = snapshot.journal if snapshot is not None else ()
        return list(entries)

    def render_activity(self):
        """I1c/A2/A3: paint the "What's happening" pane whenever the Log tab used to (every `render_state`, i.e.
        every snapshot refresh), whichever canvas tab is shown. The pane shows the newest journal lines that fit,
        oldest first (`Activity.show`); the border subtitle carries the measured quiet of a live flow
        (`snapshot.flow["silence"]`) and no subtitle at all without one. The old follow/scroll-back state of the
        Log tab is gone: the pane always shows the newest lines that fit."""
        snapshot = self.app.snapshot
        self.journal_lines = self.journal_view()
        flow = snapshot.flow if snapshot is not None else None
        silence = flow["silence"] if flow else None
        self.query_one("#activity", Activity).show(self.journal_lines, silence)

    def live_active(self):
        """C0c2/A1b: whether the first snapshot says something is live now — a planner or a milestone attempt that
        the app may not be following (`snapshot.panel` is exactly the live lines of the active attempt or planner
        the store records, so a running attempt is seen even with `follow` off). Read from the held snapshot, not
        from the observer alone."""
        snapshot = self.app.snapshot
        return bool(snapshot is not None and snapshot.panel)

    def choose_tab(self):
        """C0c2/A1b: the tab shown at start is Now while a planner or a milestone attempt is active, else Plan.
        The choice is made once, from the first snapshot the app holds, and it reads the snapshot as well as the
        observer: `planner_pane()` or `run_watch` for what the app follows, `live_active()` for a live attempt the
        store holds but this session did not follow; the app never switches the tab on its own afterwards — only
        the owner's keys do (the arrows `←`/`→`, a click on a tab label, or `Tab` into the plan pane)."""
        if self.tab_chosen or self.app.snapshot is None:
            return
        self.tab_chosen = True
        active = self.app.planner_pane() or self.app.run_watch is not None or self.live_active()
        # I7: this start choice only sets the tab `#right` holds; it must not reveal the canvas, so A1's first frame
        # in narrow mode stays the chat alone.
        self.show_tab(TAB_LIVE if active else TAB_PLAN, reveal=False)

    def status_summary(self):
        """RS2 C3: the one-line chat note `/status` writes: the plan revision and its status, each milestone with its
        state word and the running job's clock (the bar's own phrase), all from the snapshot the screen holds."""
        snapshot = self.app.snapshot
        if snapshot is None or snapshot.version is None:
            return strings.text("note.no_plan")
        parts = ["Plan r%s" % snapshot.version, PLAN_STATUS.get(snapshot.status, snapshot.status or "—")]
        parts += ["%s %s" % (row.id, STATE_TEXT.get(row.state, row.state)) for row in snapshot.rows]
        job, stage, elapsed = self.bar_job()
        if job in ("planning", "running"):
            parts.append(_job_text(job, stage, elapsed))
        return " · ".join(parts)

    def show_status(self):
        """`/status`: the "Now" tab, and the summary as a note on the status line above the chat."""
        self.show_tab(TAB_LIVE)
        self.status_note(self.status_summary())

    def show_tab(self, tab, reveal=True):
        """C0c2/A2: show Now or Plan. Both panes are painted against the width they have once shown — the hidden
        one has none, so the wrap of its lines is settled after this switch's refresh.
        C0c2/A3: the hidden tab's pane cannot hold the focus, so a switch away from "Plan" moves it to the chat
        input and remembers that the pane owned it; the return to "Plan" puts it back, and the pane's keys keep
        working. A switch under a modal leaves the focus with the modal, which owns it — the pane's claim is only
        *deferred*: `on_screen_resume` takes it back when the modal closes, so the pane's keys act on the first
        press after the dismissal instead of dying with the help screen.
        I7: an explicit switch to a canvas tab reveals the canvas in narrow mode before focusing it (`show_canvas`),
        so `Tab` into the plan pane and `/status` show what they target; the start choice of `choose_tab` passes
        `reveal=False`, so the first frame stays the chat alone."""
        right = self.query_one("#right", TabbedContent)
        pane = self.query_one("#plan-pane")
        holding = self.focused is pane  # read before the switch: hiding the pane blurs it
        if holding:
            self.tab_owner = "pane"
        if reveal:
            self.show_canvas()  # I7: an explicit switch reveals its destination pane before taking the focus
        right.active = tab
        if self.app.screen is self:
            self.restore_tab_focus(tab, holding)
        else:
            self.tab_focus_deferred = True  # the modal owns the focus; take it back on resume
        self.render_state()
        self.call_after_refresh(self.render_state)

    def restore_tab_focus(self, tab, holding):
        """C0c2/A3: put the focus where the shown tab and the remembered owner say — back on the pane (`Plan` and
        the pane owned it) or on the chat input (the pane is hidden and held the focus). Anything else is left
        alone, so a switch that found the input focused changes nothing."""
        if tab == TAB_PLAN and self.tab_owner == "pane":
            self.query_one("#plan-pane").focus()
        elif tab != TAB_PLAN and holding:
            self.query_one("#input").focus()

    def on_screen_resume(self, _):
        """C0c2/A3: a modal closed and this screen is active again. A tab switch made while the modal was up only
        deferred the focus move (the modal owned the focus); take the pane's claim back now, never before, so the
        modal's own key handling is untouched. R-A C1: coming back from the plan screen or Settings
        (`focus_on_resume`) the widget that held the focus when it opened gets it back — the input stays the input,
        so text typed next is not read as the pane's letter keys, and the pane stays the pane."""
        target, self.focus_on_resume = self.focus_on_resume, None
        if target is not None and self.scheme_full and not self.scheme_cmd and target.id == "input":
            target = self.query_one("#live-pane")  # T4e: the input is not drawn on the whole-screen scheme
        if target is not None and target.is_attached and target.focusable:
            self.tab_focus_deferred = False  # the focus it held at opening wins over a move deferred under the screen
            target.focus()
            return
        if not self.tab_focus_deferred:
            return
        self.tab_focus_deferred = False
        if self.app.screen is self:
            self.restore_tab_focus(self.query_one("#right", TabbedContent).active, self.tab_owner == "pane")

    # The conversation (i3-chat-inline) -------------------------------------------------------------------
    def chat_entry_lines(self):
        """The retained history as one display block per entry, in order: `(role, text)`, where `text` is the
        entry's time line and blocks (`entry_rows`, each block escaped per L-2) — the display half of `entry_rows`,
        which the reconciliation reads the whole of."""
        chat = self.app.chat
        return [] if chat is None else [(role, text) for _entry, role, text in entry_rows(chat.state.entries)]

    def render_chat(self):
        """Paint the conversation (i3-chat-inline): sync the scroll's own entry widgets. A render that only streams a
        live line (the status area below the scroll) leaves the conversation and its scroll position untouched (R-4)."""
        if not self.ready or self.closing:
            return
        chat = self.app.chat
        self.app.note_chat_transcript(chat.state.transcript if chat is not None else None)
        self.sync_chat_history()
        self.sync_intro()

    def sync_cards(self):
        """A card came or went: the intro (E1) and the keyed card with the input's placeholder (D2) follow."""
        self.sync_intro()
        self.sync_card_keys()

    def sync_intro(self):
        """E1: show the `Intro` at the end of `#chat` while the shown history holds no entry and no card, and take it
        off the moment one appears (the selection returns to the first example for the next time). A `reset` entry
        (`/new` starts the new conversation with one) is the divider of an empty conversation, not an entry of it."""
        if not self.ready or self.closing:
            return
        scroll = self.query_one("#chat", VerticalScroll)
        wanted = not self.card_widgets and all(widget.role == "reset" for widget in self.chat_entry_widgets)
        if not wanted:
            if self.intro is not None:
                self.intro.remove()
            self.intro, self.example_pos = None, 0
            return
        if self.intro is None or scroll.children[-1] is not self.intro:
            if self.intro is not None:
                self.intro.remove()
            self.intro = Intro()
            scroll.mount(self.intro)
        self.intro.paint(self.example_pos)

    def sync_chat_history(self):
        """Reconcile `#chat`'s entry widgets with the retained history: drop the entries that slid out of the
        window's front, mount the appended ones at its end (so a card already inline stays where it is, and a new
        entry lands below it), and leave an unchanged window alone — a scroll the owner moved is not reset by a
        render that changed nothing (R-4). A changed window, and an unchanged one that still owes a jump to the
        bottom (`chat_go_end`: an accepted send, or a grown transcript whose append the capped window hides), asks
        for the scroll's end after the refresh.

        The slide follows the *entries*, not their display text: an entry that stayed can change its own text (its
        time line moves when the entry before it left the window) while keeping its place. A window that is the old
        one with its front dropped and entries appended therefore still matches key by key — the appended entries
        mount below an inline card, never before it. The key also carries the entry's own
        *occurrence* in the append-only transcript (`ChatEntry.occurrence`), so a window of *repeated* entries still
        slides: value-equal entries of different occurrences are different keys, and the front of a full repeated
        window is dropped while the appended pair mounts below an inline card, exactly as a distinct window does.
        A window that keeps one contiguous block of entries but is not that slide — the owner's optimistic line
        leaving again without ever persisting (a send cancelled before launch, or refused before the store took it,
        so `chat._sync` reloads the unchanged transcript), with or without the capped window's front moving on —
        keeps the block's own widgets in place (`chat_window_run`) and touches only the entries around it: the ones
        that left are taken off, an entry older than the block mounts ahead of it and a newer one at the end. The
        inline cards beside the block therefore never move. Two windows that overlap in nothing at all (a reload
        that pushed the whole window out in one jump) are the one case no slide fits: every old entry widget is
        taken off and the new entries mount at the end, after every inline card — a card was mounted before these
        entries, so rewriting the old rows in place would put the newest entry above an existing receipt. A screen
        that carries only the display texts (a stand-in, no tracked entries) reconciles on the texts alone, exactly
        as before."""
        scroll = self.query_one("#chat", VerticalScroll)
        chat = self.app.chat
        rows = entry_rows(chat.state.entries) if chat is not None else []
        texts = [text for _entry, _role, text in rows]
        entries = [entry for entry, _role, _text in rows]
        old_texts = self.chat_entry_texts
        old_widgets = self.chat_entry_widgets
        # The keys the slide is measured on: the entries when this screen tracks them alongside its widgets (a
        # stand-in screen carrying only the display texts reconciles on those).
        old_entries = getattr(self, "chat_entry_entries", ())
        tracked = len(old_entries) == len(old_widgets)
        old_keys = old_entries if tracked else old_texts
        new_keys = entries if tracked else texts
        grew = len(texts) > len(old_texts)
        shift = chat_window_shift(old_keys, new_keys)
        if old_keys == new_keys:
            # The retained window (and with it every widget) is exactly what it was. i9/A5 repair: an entry's own
            # `at` (the stored `ts`) is compared out of the key the slide measures, so a running turn's line that a
            # reload stamped from the store arrives as an equal entry with new display text — repaint the widgets
            # whose text moved, in place, so the owner's own line shows its clock without being remounted (its
            # place in the scroll, and any inline card beside it, stay put).
            if old_texts != texts:
                for widget, text in zip(old_widgets, texts):
                    widget.update(text)
        elif shift is not None and shift[0] < len(old_keys):
            dropped, _appended = shift
            kept = old_widgets[dropped:]
            for widget in old_widgets[:dropped]:
                widget.remove()
            # The kept entries may have changed their time line with the slide: refresh the role class and the
            # display text in place, so a card mounted beside one of them keeps its own slot.
            for index, widget in enumerate(kept):
                _entry, role, text = rows[index]
                set_message_role(widget, role)
                if old_texts[dropped + index] != text:
                    widget.update(text)
            for _entry, role, text in rows[len(kept):]:
                widget = ChatMessage(text, role)
                kept.append(widget)
                scroll.mount(widget)
            self.chat_entry_widgets = kept
        elif tracked and (run := chat_window_run(old_keys, new_keys))[2]:
            # The windows share one contiguous block of entries, but the new window is not the old one's own tail
            # extended (the slide branch above): the owner's optimistic line left again without ever persisting, a
            # send cancelled before launch or refused before the store took it (`chat._sync` reloads the unchanged
            # transcript) — with or without the capped window's front moving on in the same reload. The block that
            # stayed keeps its own widgets — and with them the inline cards mounted beside them, which an
            # optimistic line disappearing must never move. Only the entries around it are touched: the ones that
            # left are taken off, the ones that arrived mount where they belong (an entry older than the block goes
            # in ahead of it, a newer one at the end, after every inline card).
            old_start, new_start, length = run
            kept = old_widgets[old_start:old_start + length]
            for widget in old_widgets[:old_start] + old_widgets[old_start + length:]:
                widget.remove()
            for index, widget in enumerate(kept):
                _entry, role, text = rows[new_start + index]
                set_message_role(widget, role)
                if old_texts[old_start + index] != text:
                    widget.update(text)
            for _entry, role, text in rows[new_start + length:]:
                widget = ChatMessage(text, role)
                kept.append(widget)
                scroll.mount(widget)
            arrived = [ChatMessage(text, role) for _entry, role, text in rows[:new_start]]
            if arrived:
                scroll.mount(*arrived, before=kept[0])
            self.chat_entry_widgets = arrived + kept
        elif tracked:
            # The retained windows do not overlap: a reload pushed the whole window out at once, so every entry
            # kept now is new. Chronology is kept by taking the old entry widgets off and mounting the new ones at
            # the end — after every inline card, which was mounted before these entries — never by rewriting the
            # old rows in place, which would put the newest entries above an existing receipt.
            for widget in old_widgets:
                widget.remove()
            mounted = []
            for _entry, role, text in rows:
                widget = ChatMessage(text, role)
                mounted.append(widget)
                scroll.mount(widget)
            self.chat_entry_widgets = mounted
        else:
            # A rewritten window (no slide fits): update the widgets in place by position and adjust the count, so
            # the order and the cards beside them stay.
            common = min(len(old_widgets), len(texts))
            for index in range(common):
                set_message_role(old_widgets[index], rows[index][1])
                if old_texts[index] != texts[index]:
                    old_widgets[index].update(texts[index])
            if len(texts) > len(old_widgets):
                for _entry, role, text in rows[common:]:
                    widget = ChatMessage(text, role)
                    old_widgets.append(widget)
                    scroll.mount(widget)
            elif len(texts) < len(old_widgets):
                for widget in old_widgets[:len(old_widgets) - len(texts)]:
                    widget.remove()
                del old_widgets[:len(old_widgets) - len(texts)]
            self.chat_entry_widgets = old_widgets
        self.chat_entry_texts = texts
        self.chat_entry_entries = entries
        # R-4: a grown transcript sends the view back to the bottom even when the capped window left the widgets
        # exactly as they were — the widget list cannot show that append, only the store's own entry count can.
        if grew or getattr(self, "chat_go_end", False):
            self.chat_go_end = True
            self.call_after_refresh(self.scroll_chat_end)

    def scroll_chat_end(self):
        """R-4: put the conversation's view back at the bottom (a new entry or an accepted send)."""
        if self.closing:
            return
        scroll = self.query_one("#chat", VerticalScroll)
        scroll.scroll_end(animate=False)
        # R-B: a jump made before the pane has its layout (hidden by the narrow layout, not yet sized, the newest
        # entry not yet measured) lands nowhere, so the wish stays until a layout can honour it: `apply_narrow`
        # asks again whenever the chat is shown or the screen is resized.
        # A newest entry that is off screen has no region either: with the view already at a scrollable end (a tall card
        # below the entry) that is no missing layout, and the wish is done — else it would pull a scrolled owner down.
        last = self.chat_entry_widgets[-1] if self.chat_entry_widgets else None
        at_end = scroll.max_scroll_y > 0 and scroll.scroll_y >= scroll.max_scroll_y
        self.chat_go_end = scroll.size.height <= 0 or (last is not None and last.size.height <= 0 and not at_end)

    def refresh_palette(self):
        """i2/A1: an open palette follows the lifecycle — re-lists the commands the *current* state allows, so a
        stage that starts or finishes changes the list without the owner retyping (render_state calls it whenever
        the snapshot changes; the widget stays hidden while the input does not start with "/")."""
        box = self.query_one("#palette", palette.Palette)
        if box.display:
            box.show_for(self.query_one("#input", Input).value, screen_slash_state(self.app))

    def bar_job(self):
        """The `Bar`'s job, stage and clock: the slash state's job word (`JOBS`), the milestone `Row` that state
        names, and the active attempt's elapsed seconds (`snapshot.flow["elapsed"]`, None → the bar draws `—`)."""
        app = self.app
        snapshot = app.snapshot
        flow = snapshot.flow if snapshot is not None else None
        state = screen_slash_state(app)
        row = active_row(app)
        job = "stopped" if state == "error" and owner_stopped(row) else JOBS.get(state)
        if job == "approve" and plan_auto_approves(snapshot):
            job = "approve_auto"  # D1: the architect approves the plan itself, so the bar does not wait for the owner
        return job, (row.id if row is not None else ""), (flow.get("elapsed") if flow else None)

    def turn_clock(self):
        """U1: the seconds the architect's turn has run, None when no turn runs. The count starts when the turn
        does (`ArchitectChat.turn_started`, read only; a bare event check is not a turn)."""
        chat = self.app.chat
        if chat is None or not chat.turn_running:
            return None
        return max(time.monotonic() - chat.turn_started, 0.0)

    def tick_clock(self):
        """The 1 s timer: the bar's turn clock and the status area's thinking clock (and its spinner frame)."""
        self.show_keys()
        if self.ready and not self.closing:
            self.render_status()

    def bar_meta(self):
        """The dim tail of the bar: `model/effort · N tok`, then `chat.rot` when the session is long ("" without a
        chat). Each value is escaped (L-2) like every other text the pane draws."""
        chat = self.app.chat
        if chat is None:
            return ""
        state = chat.state
        header = state.header_fields
        model = plain_value(header.model or "") if header is not None else ""
        effort = plain_value(header.effort or "") if header is not None else ""
        parts = [("%s/%s" % (model, effort)).rstrip("/")]
        if state.usage:
            parts.append(strings.text("chat.tokens", count=short_count(state.usage[1])))
        if chat_module.session_long(state.usage):
            parts.append(strings.text("chat.rot"))
        return " · ".join(part for part in parts if part)

    def show_keys(self):
        """Feed the bottom row (i2). While a modal is on top the widget keeps showing the modal's own keys
        (`modal_bar`, unchanged — a plain `Static` under the translucent modal); otherwise it is the main `Bar`:
        the project, branch and job phrase with its clock that the old `#header` and status area used to carry, and
        the key hints (i9/A1: `esc` only while a job runs or a file/diff tab is open). Skipped once the screen is
        unmounting: `on_resize` schedules it after the refresh, a callback that can outlive the widgets it would
        touch (L-5, like `render_settled`)."""
        if self.closing:
            return
        turn = self.turn_clock()
        width = max(self.size.width - 2, 10)
        shown = self.app.modal_bar(width)
        bar = self.query_one("#keys", Bar)
        if shown is not None:
            bar.update(Text(shown))
            return
        snapshot = self.app.snapshot
        project = snapshot.project if snapshot else self.app.controller.name
        branch = (snapshot.branch or strings.text("header.detached")) if snapshot else "…"
        job, stage, elapsed = self.bar_job()
        keys = BAR_KEYS if (job is not None or self.view_tabs) else BAR_KEYS_IDLE
        if self.query_one("#palette").display:
            keys = BAR_KEYS_PALETTE
        bar.update_bar(project, branch, job, stage, elapsed, keys, turn, self.bar_meta())

    def on_descendant_focus(self, _):
        self.show_keys()

    def on_key(self, event):
        """P1a C2: a `/` that reaches this screen from a focused widget that is not the chat input — a card button the
        focus came back to when the screen it opened closed, or the plan pane — is not dropped: the chat input takes
        the focus and the `/`, so the palette opens. Nothing is forwarded while the chat pane is hidden (narrow canvas)."""
        if event.character != "/" or isinstance(self.focused, (Input, TextArea)):
            return
        field = self.query_one("#input", Input)
        if self.scheme_full and not self.scheme_cmd:  # T4e: on the whole-screen scheme the `/` brings the prompt up
            self.scheme_cmd = True
            self.apply_narrow()
        if not self.query_one("#chat-pane").display:
            return
        event.stop()
        event.prevent_default()
        self.tab_owner = "input"
        field.focus()
        self.app.type_in_chat(field, "/")

    def on_input_changed(self, event):
        """i2/A1: every change of the chat input re-decides the `/` palette — `show_for` hides it unless the value
        starts with `/` and lists the commands `slash` allows in the current state."""
        if event.input.id == "input":
            if self.scheme_cmd and not event.value.startswith("/"):  # the prompt is for commands only here
                self.close_scheme_cmd()
                return
            self.query_one("#palette", palette.Palette).show_for(event.value, screen_slash_state(self.app))
            self.show_keys()
            self.sync_card_keys()

    def on_input_submitted(self, event):
        """Enter in the chat input (i2/A1-A2, i3a): the palette decides first. `None` is not a command — one owner
        message = one turn, today's path unchanged (a refusal keeps the text; an accepted turn scrolls the
        conversation back to the bottom, R-4). `Refused` shows its note and keeps the text. `Submitted` clears the
        input, hides the palette and runs the command through the one dispatcher (`run_command`); an unwired command
        (`/language`) shows `note.not_now` like a refusal and, like a refusal, keeps the text in the input (the
        dispatcher reports that nothing ran, and that is read before the input is cleared)."""
        field = self.query_one("#input", Input)
        line = event.value
        card = self.keyed_card() if not line else None
        if card is not None and not self.query_one("#palette").display:
            card.press_choice()  # D2: Enter on the empty input answers the open card, as a click on its choice does
            return
        picked = self.palette_pick(line)
        if picked is not None:  # O3: a prefix with no argument runs the highlighted row, as if typed in full
            line = picked.name
        verdict = submit_verdict(self, line)
        if verdict is None:
            accepted, _ = self.app.send_chat(line)
            if accepted:
                self.remember(line)
                field.value = ""
                self.chat_go_end = True  # R-4: the accepted message is shown at the bottom, whatever was scrolled
            self.render_state()
            return
        if isinstance(verdict, palette.Refused):
            self.app.chat_note = verdict.note
            self.app.changed()
            return
        # i2/A2: an unwired command behaves exactly like a refusal — the note shows and the input keeps the text.
        # i3a: the availability check is `run_command`'s own False return, the one dispatcher both paths share.
        self.app.chat_note = ""  # a command that is allowed in this state ends the note, whatever set it
        if not self.run_command(verdict.command_name, verdict.argument):
            return
        self.remember(line)
        field.value = ""
        self.query_one("#palette").display = False
        if getattr(self, "scheme_cmd", False):  # T4e (a stub screen of the older tests has no such flag)
            self.close_scheme_cmd()

    def remember(self, line):
        """O3: keep one accepted line for Up to recall (a line equal to the newest is kept once)."""
        self.history_pos = None
        if not self.history or self.history[-1] != line:
            self.history = (*self.history, line)

    def palette_pick(self, line, complete=False):
        """O3: the highlighted palette row when `line` is only a prefix of a command — the palette is shown and the
        line parses to no command and no argument — otherwise None (a full command, with or without an argument, and
        a plain message keep their own path). `complete` (Tab) also takes a full command name typed without an
        argument, as that command: `/plan` + Tab is `/plan `; Enter on it stays on today's path."""
        box = self.query_one("#palette", palette.Palette)
        if not box.display or not line.startswith("/"):
            return None
        parsed = slash.parse(line)
        if parsed is None or parsed.argument:
            return None
        if parsed.command is not None:
            return parsed.command if complete and parsed.command in box.found else None
        return box.picked()

    # The decision cards of the chat (i3a) ---------------------------------------------------------
    def run_command(self, name, argument="", key=None):
        """Run one command name through the one dispatcher (`COMMAND_ACTIONS`): a `/` line typed in the chat
        (`on_input_submitted`) and a card button (`on_card_chosen`) both come through here, so a command behaves
        identically wherever it came from.

        `argument` is the parsed argument ("" when the line had none) and `key` the card the command came from (None:
        a typed line, which acts on the newest card of that kind). Returns True when an action ran and False when no
        action is wired for `name` — the typed path then keeps the input's text, exactly like a refusal (the caller
        clears the input only after a True)."""
        action = COMMAND_ACTIONS.get(name)
        if action is None:
            self.status_note(strings.text("note.not_now", name=name))
            return False
        action(self, argument, key)
        return True

    def stop_running_row(self):
        """`/stop`: the existing stop confirmation of the selected stage when it is running (with parallel slots the
        owner picks which), else of the first running stage. The action reads the screen's selection, so the row is
        selected for the call and the owner's own selection is put back at once (the confirmation and the stop
        capture the row itself)."""
        app = self.app
        rows = app.rows()
        row = next((r for r in rows if r.id == app.selected and r.state == "running"), None) or running_row(rows)
        if row is None:
            if screen_slash_state(app) == "planning":
                self.stop_planning()
            return
        previous, app.selected = app.selected, row.id
        app.action_stop_milestone()
        app.selected = previous

    def stop_planning(self):
        """`/stop` while the planner runs (p1b): one confirmation naming the revision; "yes" stops it through the
        controller job (`Planning.stop()` once, off the UI thread). A refusal is one "Not done: …" chat line and
        leaves the state as it was; success asks for a fresh snapshot, whose terminal observation shows the stopped
        plan's card."""
        app = self.app
        snapshot = app.snapshot
        if snapshot is None or snapshot.version is None:
            return

        def stopped(outcome, error):
            if error:
                self.status_note("Not done: " + error)
            else:
                app.request_refresh()
            app.changed()

        self.app.confirm(strings.text("confirm.stop_plan", v=snapshot.version),
                         lambda: app.controller.stop_planner(app.deliver(stopped)))

    def action_cancel_turn(self):
        """[esc] (i2 + i5): the open `/` palette first — hide it and clear its input; otherwise (T4e) close the
        whole-screen scheme (`/scheme`); otherwise close the file/diff
        canvas tab the canvas shows (returning to the tab that was active before it opened); otherwise cancel the
        running architect turn. Never a milestone's stop key."""
        if self.query_one("#palette").display:
            self.query_one("#palette").display = False
            self.query_one("#input", Input).value = ""
            if self.scheme_cmd:
                self.close_scheme_cmd()
            return
        if getattr(self, "scheme_full", False):
            self.toggle_scheme_full()
            return
        if self.close_active_view_tab():
            return
        chat = self.app.chat
        owner = chat is not None and chat._mode == "owner"  # U1: read only — the owner's own turn, not an event or a reset
        if chat is not None and chat.cancel():
            if owner:
                self.status_note(strings.text("note.turn_cancelled"))
            self.render_state()

    def action_reset_session(self):
        """[ctrl+r] and `/new`: a fresh architect session with a handoff and a warm-up turn (`chat.new_session`),
        carrying this moment's snapshot; refused while a turn runs (the chat shows the line)."""
        if self.app.chat is not None:
            self.app.chat.new_session(self.app.chat_snapshot())

    def action_toggle_focus(self):
        """[tab]: with the `/` palette shown and a prefix typed (no argument), the highlighted command's name and a
        space (O3); otherwise the chat input and the plan pane. C0c2/A3: the pane lives on the Plan tab, so the move to it shows
        that tab first and owns the focus (the return to the input leaves the shown tab where the owner left it and
        gives the focus back to the input)."""
        panel = self.query_one("#plan-pane")
        field = self.query_one("#input", Input)
        if self.focused is field:
            picked = self.palette_pick(field.value, complete=True)
            if picked is not None:
                field.value = picked.name + " "
                field.cursor_position = len(field.value)
                return
        if self.focused is panel:
            self.tab_owner = "input"
            self.query_one("#input").focus()
        else:
            self.tab_owner = "pane"
            self.show_tab(TAB_PLAN)
            panel.focus()

    def action_pick(self, delta):
        """[up]/[down] in the chat input (O3): with the intro of an empty chat shown and the input empty or holding one
        of its examples (E1), pick the next/previous example (wrapping) into the input; with the `/` palette shown,
        move its highlight (wrapping); with an open card, the palette hidden and the input empty (D2), move the card's
        selected choice (wrapping); with an empty input, recall the owner's previous lines of this run, newest
        first (Down walks back and ends on empty). Any other focus or text leaves the key alone."""
        field = self.query_one("#input", Input)
        if self.focused is not field:
            return
        box = self.query_one("#palette", palette.Palette)
        examples = [strings.text(example) for example in EXAMPLE_IDS]
        if self.intro is not None and not box.display and field.value in ("", *examples):
            # E1: the intro is shown — the arrows pick an example (wrapping) into the input, whatever recall holds.
            if field.value:
                self.example_pos = examples.index(field.value)
            self.example_pos = (self.example_pos + delta) % len(examples)
            self.history_pos = None
            field.value = examples[self.example_pos]
            field.cursor_position = len(field.value)
            self.intro.paint(self.example_pos)
            return
        card = self.keyed_card()
        if card is not None and not box.display and field.value == "":
            card.move_choice(delta)
            return
        recalling = self.history_pos is not None and field.value == self.history[self.history_pos]
        if box.display and not recalling:
            box.move(delta, field.value, screen_slash_state(self.app))
            return
        if recalling:
            pos = self.history_pos + delta
            if pos >= len(self.history):
                self.history_pos, field.value = None, ""
                return
            self.history_pos = max(pos, 0)
        elif field.value == "" and delta < 0 and self.history:
            self.history_pos = len(self.history) - 1
        else:
            return
        field.value = self.history[self.history_pos]
        field.cursor_position = len(field.value)

    def action_scroll_up(self):
        """[pageup] from the plan pane or the chat input: one page up the conversation through the `#chat` scroll's
        own paging (i3-chat-inline). Any other focus, screen or modal is left exactly as it was (R-2): the
        `chat_keys_ready` guard is the whole condition."""
        if chat_keys_ready(self.app):
            self.app.scroll_chat(1)

    def action_scroll_down(self):
        """[pagedown] from the plan pane or the chat input: one page down the conversation, back toward today's
        newest rows. Guarded exactly like `action_scroll_up` (R-2)."""
        if chat_keys_ready(self.app):
            self.app.scroll_chat(-1)

    def action_view(self, delta):
        """I1a/A1-A3: [←]/[→] show the previous (`-1`) / next (`+1`) tab of the canvas, cycling the base tabs
        Now -> Plan -> Now (I1c: the Log tab is gone) from anywhere on the main screen. I5/A4: every open
        file/diff tab joins the cycle after "Plan" (Now -> Plan -> <files...> -> Now), so the arrows reach
        them too; "Now" and "Plan" never close.

        A2: while the chat input holds text the arrow is the input's own key, never a tab switch — this is a
        priority binding, so it would otherwise take the key before the `Input` ever saw it. The condition reads the
        input's value on its own, whatever the focus: the owner can type "abc", `Tab` into the plan pane and press
        [→]; the text still keeps the tab where it was (and a focused, non-empty input gets its cursor moved here,
        exactly as before). Any other state — an empty input from any focus — switches the tab (A1). A3: this
        screen's binding only runs while this screen is the active one, so a modal on top or another screen keeps
        the arrow its own — the screen check below is the same guard the scroll keys use, spelled out where the key
        is."""
        field = self.query_one("#input", Input)
        if field.value:
            if self.app.focused is field:
                field.action_cursor_right() if delta > 0 else field.action_cursor_left()
            return
        if not isinstance(self.app.screen, MainScreen):
            return
        right = self.query_one("#right", TabbedContent)
        if self.narrow:
            # I7: the cycle gains "Conversation" in front (chat -> Now -> Plan -> view tabs -> chat). The chat is
            # not a TabPane, so `chat_shown` is the page the cycle sits on while the canvas is hidden.
            cycle = [TAB_CHAT] + self.view_tab_ids()
            current = TAB_CHAT if self.chat_shown else (right.active if right.active in cycle else TAB_LIVE)
            chosen = cycle[(cycle.index(current) + delta) % len(cycle)]
            if chosen == TAB_CHAT:
                self.show_chat()
            else:
                self.show_canvas()
                self.show_tab(chosen)
            return
        tabs = self.view_tab_ids()
        current = right.active if right.active in tabs else tabs[0]
        self.show_tab(tabs[(tabs.index(current) + delta) % len(tabs)])

    # I5: the file/diff canvas tabs ----------------------------------------------------------------
    def work_running(self):
        """I5/A3: whether any work runs now — the planner observation (`app.watching`) or a milestone attempt the
        held snapshot marks active. `app.planner_pane()` is deliberately not used: it keeps a finished planner's
        progress on screen, so it would keep saying work runs long after the planner stopped."""
        app = self.app
        if app.watching:
            return True
        snapshot = app.snapshot
        return bool(snapshot is not None and any(row.active for row in snapshot.rows))

    def status_note(self, line):
        """I5: one line for the status area above the chat — the place the app's own lines show (`chat_note`), so a
        refusal here reads exactly where the screen's other own notes do."""
        self.app.chat_note = line
        self.app.changed()

    def view_tab_ids(self):
        """I5/A4: every canvas tab in the order the strip shows them: "Now", "Plan", then the open file/diff
        tabs oldest first. The arrows cycle exactly this list."""
        return [TAB_LIVE, TAB_PLAN] + list(self.view_tabs)

    def open_file_tab(self, name):
        """I5/A1: show a project file as a read-only canvas tab after "Plan" and make it active.

        The path comes from `viewer.resolve` against the project root, so a name outside the project, a missing
        file and every other refusal open nothing and put their catalog text on the status line. Opening a file
        already open just activates its tab; a fourth file tab closes the oldest (A4). While any work runs nothing
        opens and the status line says so (A3); a tab already open stays."""
        if self.work_running():
            self.status_note(strings.text("note.not_now", name="/open"))
            return
        try:
            path = viewer.resolve(self.app.controller.project, name)
        except viewer.ViewError as error:
            self.status_note(strings.text(error.id, **error.values))
            return
        key = str(path)
        for tab_id, opened in self.view_paths.items():
            if opened == key and tab_id in self.view_tabs:
                self.activate_view_tab(tab_id)
                return
        # The refusal can also come from the render, not only from the resolution: a file that is not UTF-8 text
        # makes `file_view` raise `ViewError('note.view_binary')`. It goes through the same refusal path — no tab,
        # the catalog text on the status line — so a binary project file never leaks the exception.
        try:
            renderable = viewer.file_view(path, words=strings.text)
        except viewer.ViewError as error:
            self.status_note(strings.text(error.id, **error.values))
            return
        self.add_view_tab(name, renderable, key=key)

    def open_diff_tab(self):
        """I5/A2: show the selected finished attempt's diff as a read-only canvas tab titled "Changes <stage>".

        The attempt is the selected row's token (`app.selection().token`); without one — nothing finished selected —
        nothing opens and the status line says why. The diff is the existing `controller.diff`, run through
        `deliver`; only a `diff` outcome opens or replaces the single diff tab, so a stale verdict or an error keeps
        the canvas and shows its text on the status line instead. While any work runs nothing opens (A3)."""
        if self.work_running():
            self.status_note(strings.text("note.not_now", name="/diff"))
            return
        app = self.app
        row = app.selection()
        token = row.token if row is not None else None
        if token is None:
            self.status_note(strings.text("note.not_now", name="/diff"))
            return
        milestone = row.id
        app.controller.diff(token, app.deliver(
            lambda outcome, error: self.diff_opened(milestone, outcome, error)))

    def diff_opened(self, milestone, outcome, error):
        """I5/A2: the verdict of the diff the controller produced — the one diff tab for a `diff`, otherwise the
        status line (the error, or the outcome's own lines), with no tab.

        A3: the controller answers asynchronously, so work may have started since the request — the running check
        is repeated here, before anything is shown: while work runs nothing opens, an already open diff tab stays
        as it was, and the status line says the not-now text."""
        if self.work_running():
            self.status_note(strings.text("note.not_now", name="/diff"))
            return
        if error:
            self.status_note("Not done: " + error)
        elif outcome.kind == "diff":
            self.add_view_tab(strings.text("canvas.diff_tab", stage=milestone),
                              viewer.diff_view("\n".join(outcome.lines), words=strings.text), diff=True)
        else:
            self.status_note("\n".join(outcome.lines) or MOVED)

    def add_view_tab(self, title, renderable, key=None, diff=False):
        """I5: mount one file/diff canvas tab after the last open one (right after "Plan" when none is open) and
        show it. `key` is the resolved path a later open matches to reactivate the tab. There is one diff tab:
        asking for another diff updates the mounted pane's title and body in place instead of closing and
        re-adding it — `remove_pane` is asynchronous, so a fresh pane with the same id would collide with the one
        still mounted (`DuplicateIds`). The file tabs stay under `FILE_TABS_MAX` (the oldest closes for a fourth)."""
        right = self.query_one("#right", TabbedContent)
        if diff:
            tab_id = TAB_DIFF
            if tab_id in self.view_tabs:
                # Reuse the mounted diff pane: retitle its tab and swap the renderable inside its scroll. The
                # removal path is deliberately avoided here (see the docstring) so repeated requests never reuse
                # the id of a pane whose `remove_pane` has not completed yet.
                right.get_tab(tab_id).label = elide_end(title, FILE_TITLE_CELLS)
                right.get_pane(tab_id).query_one(Static).update(renderable)
                self.remember_previous(tab_id)
                right.active = tab_id
                self.show_canvas()  # I7: an opened/updated canvas tab brings the canvas into view in narrow mode
                return
        else:
            self.file_seq += 1
            tab_id = "tab-view-%d" % self.file_seq
        self.remember_previous(tab_id)
        pane = TabPane(elide_end(title, FILE_TITLE_CELLS),
                       VerticalScroll(Static(renderable), classes="view-scroll"), id=tab_id)
        right.add_pane(pane, after=self.view_tabs[-1] if self.view_tabs else TAB_PLAN)
        self.view_tabs.append(tab_id)
        if key is not None:
            self.view_paths[tab_id] = key
        files = [tab for tab in self.view_tabs if tab != TAB_DIFF]
        while len(files) > FILE_TABS_MAX:
            self.close_view_tab(files.pop(0))
        right.active = tab_id
        self.show_canvas()  # I7: opening a file/diff tab shows the canvas in narrow mode

    def remember_previous(self, tab_id):
        """I5/A4: record where esc returns from `tab_id`: the tab the canvas shows right now, or the last base tab
        shown for anything base-level (an open at start-up, a plain view tab shown before)."""
        current = self.query_one("#right", TabbedContent).active
        if current in (TAB_LIVE, TAB_PLAN):
            self.view_base = current
        if current and current != tab_id:
            self.view_prev[tab_id] = current

    def return_target(self, tab_id):
        """I5/A4: the tab to show once `tab_id` closes — the tab that was active when it opened (the real previous
        tab, view or base), walking further back past any remembered tab that has itself closed, and falling back
        to the last base tab shown. A base tab always exists, so the walk always ends on one."""
        target = self.view_prev.get(tab_id, self.view_base)
        seen = {tab_id}
        while target not in (TAB_LIVE, TAB_PLAN) and (target in seen or target not in self.view_tabs):
            if target in seen:  # a cycle in the remembered chain: fall back rather than loop forever
                return self.view_base
            seen.add(target)
            target = self.view_prev.get(target, self.view_base)
        return target

    def activate_view_tab(self, tab_id):
        """I5/A1: show an already open file tab (the same file opened again), remembering where esc returns."""
        self.remember_previous(tab_id)
        self.query_one("#right", TabbedContent).active = tab_id
        self.show_canvas()  # I7: activating an open file tab shows the canvas in narrow mode

    def close_view_tab(self, tab_id):
        """I5/A4: close one file/diff tab; when it was the shown one, return to the tab that was active before it
        opened. The return target is selected *before* the removal: `remove_pane` is asynchronous and would
        otherwise let the tabs' own neighbour-activation override the assignment once the removal completes."""
        right = self.query_one("#right", TabbedContent)
        if right.active == tab_id:
            right.active = self.return_target(tab_id)
        right.remove_pane(tab_id)
        if tab_id in self.view_tabs:
            self.view_tabs.remove(tab_id)
        self.view_paths.pop(tab_id, None)

    def close_active_view_tab(self):
        """I5/A4: [esc] first closes the file/diff tab the canvas shows; True when it closed one, so the caller
        leaves the architect turn running."""
        right = self.query_one("#right", TabbedContent)
        if right.active not in self.view_tabs:
            return False
        self.close_view_tab(right.active)
        return True


# i11: `/run` is the pane's [g] from the chat (the action lives on the app, beside `action_run_milestone`).
COMMAND_ACTIONS["/run"] = lambda screen, argument, key: screen.app.action_run_next()


class EnterConfirmScreen(ConfirmScreen):
    """The start confirmation `/run` reaches: the focus starts on "yes", so Enter at once confirms."""
    default_yes = True

    def key_bar(self, width):
        """The key line: Enter is named `start` (the "yes" button is already focused), not the neutral `press`."""
        return keys_bar("tui_confirm_run", width, ("tui_confirm.yes", "tui_confirm_run.start", "tui_confirm.no"))

    def compose(self):
        with Vertical(id="confirm"):
            yield Static(Text(self.question + "\n\n" + self.key_bar(56)), id="confirm-question", markup=False)
            with Horizontal(id="confirm-buttons"):
                yield Button(catalog.label("tui_confirm.yes"), id="confirm-yes", compact=True)
                yield Button(catalog.label("tui_confirm.no"), id="confirm-no", compact=True)


class ZplanApp(App):
    CSS_PATH = "zplan.tcss"
    TITLE = "zplan"
    # I1a/A4: the tab keys are no longer app-level bindings (the arrows live on `MainScreen`, where they need the
    # screen and the chat input to decide between the cursor and a switch); only the two keys that work on every
    # screen stay here.
    BINDINGS = [Binding("ctrl+q", "quit", "Exit", priority=True)]

    def __init__(self, controller, follow=True, chat_prepare=None, chat_binding=None, architect=True):
        """`follow`: an attempt still running when the snapshot arrives is observed again on its own (reopening
        zplan resumes it); False leaves observation to the owner's `/attempt`.

        `chat_prepare(project)` builds the ready architect off the event loop (default: the installed toolchain,
        the login and the effective architect role); tests inject a fixture. The chat is one conversation per
        project, built here and started on mount. `chat_binding(project)` re-reads the effective role before every
        turn (default: the accepted process profile's `architect` role), so a role edited between turns is used.

        `architect=False` (a `--fixture ID` session, R-2) builds no chat at all: no `ArchitectChat`/`ArchitectStore`,
        no provider turn and no tool probe; the pane shows `CHAT_FIXTURE` and the chat keys have nothing to reach.

        i9/A3: the app runs with the terminal palette (`ansi_color=True`, the `ansi-dark` theme set at mount), the
        way the lab does, so the names `zplan.tcss` and the card/palette widgets use are the terminal's own ANSI
        colours and follow the owner's terminal theme."""
        super().__init__(ansi_color=True)
        self.controller = controller
        # A5t2b: the architect's `zplan_edit_plan` saves the revision on the worker and hands its verdict here, so a
        # "ready" revision is shown by the very `after_submission` the owner's own submission uses (its planner watch
        # dispatches it). The hook is a worker-callable; `plan_submission` marshals it to the UI thread.
        controller.on_plan_submission = self.plan_submission
        # D4c: the architect's commit proposal (worker thread) is drawn as a card on the UI thread.
        controller.on_commit_proposal = lambda proposal: self.from_worker(self.changed)
        self.follow = follow
        self.chat_prepare = chat_prepare or chat_module.default_prepare
        self.chat_binding = chat_binding or chat_module.architect_binding
        self.worker_loop = None   # the UI thread's loop: worker results are handed over to it, never waited for
        self.snapshot = None      # last Snapshot (None until the first slice arrives)
        self.checks = None        # last tuple of readiness Check
        self.plan_error = ""
        self.chat_note = ""
        self.checking = False
        self.setup_origin = None  # the screen a running setup started from (R-4)
        self.check_seq = 0        # readiness requests are numbered (R-4): a running check never satisfies a later one
        self.check_batch = None   # (origin, interactive) of the running check, None when none runs
        self.pending_check = None  # at most one interactive follow-up batch waiting for the running check
        self.quitting = False     # [ctrl+q] pressed while a mutating job runs: exit when it ends
        self.quit_deadline = None  # monotonic deadline of the exit [ctrl+q] started (None: quit has not begun)
        self.setting_up = False
        self.log_lines = deque(maxlen=LOG_LINES)
        self.exit_code = 0
        self.goal_identity = None  # the plan identity of the goal draft being sent (None: a typed goal)
        self.goal_block = ()      # readiness items behind the last refused submission
        self.goal_message = ""
        self.starting = False     # a goal submission is in flight
        self.progress = deque(maxlen=PROGRESS_LINES)  # planner phase lines, as the observation delivers them
        self.watching = False     # a planner observation is running
        self.resumed = set()      # revisions whose observation already restarted on its own
        self.plan_lines = ()      # notes under the plan view: details, a refusal, a decision
        self.selected = None      # the milestone selected in the plan panel (None: the service's focus)
        self.run_lines = deque(maxlen=PROGRESS_LINES)  # milestone phase lines, as the observation delivers them
        self.run_buffers = {}     # milestone -> its attempt's own lines (C4): each running attempt keeps its own
        self.run_buffer_id = {}   # milestone -> the run id whose attempt `run_buffers` holds (None: not resolved)
        self.run_chain = set()    # milestones with a live chain of watch slices (C4)
        self.run_note = ""        # the last milestone action's verdict, under the progress lines
        self.run_watch = None     # the milestone whose attempt the run lines show
        self.run_last = None      # the milestone the run lines belong to
        self.run_seen = set()     # run ids whose observation restarted on its own
        self.pending = None       # (kind, milestone, token before, asked, confirmed at): an action in flight
        self.finish_note = ""     # how the planner observation ended (the chat pane; the plan screen says it itself)
        self.plan_block = ()      # readiness items behind the last refused submission (re-checked on show)
        self.details_lines = ()   # the lines [i] put under the plan view (a second [i] removes them)
        self._chat_transcript = None  # R-4: the transcript's entry count at the last render (append provenance)
        project = getattr(controller, "project", None)
        self.architect = architect  # R-2: whether this session has an architect chat at all (`chat_off` reads it)
        # A6b2b: an architect session gets the feed port over the Controller worker, and the worker wakes the chat
        # after each observation job; a session without one (a `--fixture ID` demo) builds no port and no hook.
        feed_port = getattr(controller, "feed_port", None) if project is not None and architect else None
        self.chat = None if project is None or not architect else chat_module.ArchitectChat(
            project, lambda: self.chat_prepare(project), binding=lambda: self.chat_binding(project),
            hand_over=self.hand_over, on_change=self.changed, feed=feed_port() if feed_port else None)
        if feed_port is not None:
            controller.snapshot_source = self.chat_snapshot
            controller.on_observed = self.chat.notify

    @property
    def chat_off(self):
        """R-2: the line the pane shows when there is no chat — an unknown project's refusal, or (no architect at
        all, a `--fixture ID` demo) the fixture's own with the standard catalog code of a refusal to act. i6: read
        from the catalog on every call, so a language switch relabels this line with the rest of the pane."""
        if self.architect:
            return strings.text("chat.refused")
        return strings.text(CHAT_FIXTURE) + catalog.tag("action.refused")

    def get_default_screen(self):
        return MainScreen()

    # Lifecycle -----------------------------------------------------------------

    def on_mount(self):
        self.theme = "ansi-dark"  # i9/A3: the terminal palette, like the lab
        self.worker_loop = asyncio.get_running_loop()
        self.controller.start()
        self.request_refresh()
        self.request_check()
        self.set_interval(REFRESH_SECONDS, self.request_refresh)
        self.set_interval(CHECK_SECONDS, self.request_check)
        self.set_interval(BLOCK_RECHECK_SECONDS, self.recheck_blocked)
        self.set_interval(0.2, self.quit_when_idle)
        if self.chat is not None:
            self.chat.start()  # "preparing the chat…" until the toolchain, the login and the role checks are done

    def on_unmount(self):
        left = self.quit_left()
        if self.chat is not None:
            # A cancelled turn takes its own process group down before the app leaves.
            self.chat.close() if left is None else self.chat.close(left)
        self.controller.stop() if left is None else self.controller.stop(timeout=left)

    def quit_left(self):
        """Seconds left of the budget [ctrl+q] started, or None when it has not begun (the callers' own default)."""
        deadline = self.quit_deadline
        return None if deadline is None else max(deadline - time.monotonic(), 0.0)

    async def action_quit(self):
        """Never ends a mutating job (submission, merge, setup, ...): the screen says it is finishing and the
        exit follows when the job ends. Only a watch slice or a plain read is cut. The architect turn is not a
        controller job: it is cancelled at once, whether or not a mutating job runs. The cancelled turn and a cut
        slice share one bounded budget (QUIT_BUDGET), so the exit keeps its deadline whatever the slice is doing."""
        self.pending_check = None  # R-4: the exit discards the waiting follow-up; no closing line is owed
        if self.chat is not None:
            self.chat.shutdown()  # from here no send or reset is accepted, whatever else quit still waits for
            self.chat.cancel()
        # Close the controller *before* the first await: no submission or export may be registered behind the
        # exit while the cancelled turn is waited for (it would then be waited for without bound). A mutation
        # already in flight still keeps its own quit behaviour: the app shows it is finishing and leaves when it ends.
        if self.controller.begin_closing():
            if not self.quitting:
                self.quitting = True
                self.push_screen(FinishingScreen())
            return
        if self.quit_deadline is None:
            self.quit_deadline = time.monotonic() + QUIT_BUDGET
        if self.chat is not None:
            await asyncio.to_thread(self.chat.wait, self.quit_left())  # bounded: cancel kills the group
        await asyncio.to_thread(self.controller.stop, self.quit_left())
        self.exit(0)

    def quit_when_idle(self):
        if self.quitting and not self.controller.mutating():
            if self.chat is not None:
                self.chat.wait(chat_module.QUIT_GRACE)
            self.exit(0)
        elif self.chat is not None and self.chat.busy:
            self.changed()  # the live "thinking…" line counts its seconds while the turn runs

    def chat_snapshot(self):
        """The frozen read-only snapshot one turn carries: the UI's current snapshot, never Authority.

        Taken once, at send time, and never recomputed for that turn: the draft identity of a reply is the identity
        of this projection (architect.plan_identity: `revision` and `plan_state` for a goal, the milestone's
        `token` for an answer), so a refresh that changes the screen later cannot change what a sent turn carries.

        Before the first refresh arrives there is no snapshot to project, so the projection omits `revision`
        altogether: the plan state of that turn is unknown, which a draft must not read as "no plan" (a plan-less
        screen says `revision: None`), and its drafts are not actionable."""
        snapshot = self.snapshot
        if snapshot is None:
            return {"project": self.controller.name, "branch": None, "milestones": []}
        lines = list(snapshot.lines)
        # The overview's first line is the goal ("Goal: ..."); the second, when present, is the plan status line.
        goal = lines[0] if lines else ""
        status = lines[1] if len(lines) > 1 and lines[1].startswith("Plan r") else ""
        return {"project": snapshot.project, "branch": snapshot.branch,
                "plan_summary": " · ".join(part for part in (goal, status) if part),
                "revision": snapshot.version, "plan_state": snapshot.plan_state,
                "uncommitted": list(snapshot.uncommitted),
                "milestones": [{"id": row.id, "title": row.title, "state": row.state,
                                "token": token_fields(row.token)} for row in snapshot.rows]}

    def send_chat(self, value):
        """One Enter in the chat input: one turn on the chat's own thread, or a refusal line. Nothing is queued."""
        if self.chat is None:
            return False, self.chat_off
        accepted, line = self.chat.send(value, snapshot=self.chat_snapshot())
        if accepted:
            self.chat_note = ""  # the owner's accepted turn ends the note, whatever set it
        return accepted, line

    def note_chat_transcript(self, size):
        """R-4: `size` is the number of transcript entries the chat's last store reload carried — provenance the
        retained window cannot give, because `HISTORY` caps it at 40 and `ENTRY_TEXT` clips every entry, so an
        appended entry can change the store while leaving the window (its text included) identical, and a long
        entry's clipped text can differ without an append. A reload that grew the transcript sends the view to the
        bottom whatever the capped window shows; an unchanged reload leaves the scroll where it is. Only a reload
        moves the count, so a poll or a live/stream update never resets a scrolled view. `None` (no chat) touches
        nothing. The jump is recorded on the *owning* MainScreen, never on `self.screen`: a reload can land while a
        modal covers the conversation, and the pending jump must survive until that screen is visible again (R-4)."""
        if size is None:
            return
        if self._chat_transcript is not None and size > self._chat_transcript:
            screen = self.main_screen()
            if screen is not None:
                screen.chat_go_end = True
        self._chat_transcript = size

    def scroll_chat(self, pages):
        """R-2: one PageUp/PageDown page of the conversation from the plan pane — the `#chat` scroll's own paging
        (`scroll_page_up`/`scroll_page_down`), never a hand-computed row count. Another screen is left alone; the
        scroll itself clamps at either end."""
        screen = self.screen
        if not isinstance(screen, MainScreen):
            return
        scroll = screen.query_one("#chat", VerticalScroll)
        scroll.scroll_page_up() if pages > 0 else scroll.scroll_page_down()

    # Worker results ------------------------------------------------------------

    def hand_over(self, call, release=None):
        """Run `call()` on the UI thread from the worker thread, without waiting for it: the worker never blocks on
        the UI. `closing` is re-checked on the UI side, so a delivery that loses the race with the unmount is
        dropped; `release`, when given, runs at once then -- the job's delivery is over either way."""
        loop = self.worker_loop
        if not self.controller.closing and loop is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(self._handled, call, release)
                return
            except RuntimeError:  # the loop went away between the check and the hand-over
                pass
        if release is not None:
            release()

    def _handled(self, call, release):
        """The UI-thread side of a hand-over: `closing` is re-checked here, so a delivery queued just before the UI
        began to unmount is dropped instead of running on a screen that is going away."""
        try:
            if not self.controller.closing:
                with self._context():  # the app's context, as call_from_thread would set it
                    call()
        except Exception:  # a bug in one handler must not kill the loop, the worker, or the job behind it
            pass
        finally:
            if release is not None:
                release()

    def from_worker(self, handler, *args):
        """Run `handler(*args)` on the UI thread from the worker thread. Once closing has begun the UI thread is
        unmounting and waits for the worker, so nothing is delivered then."""
        self.hand_over(lambda: handler(*args))

    def deliver(self, handler):
        """A controller callback (worker thread) that runs `handler(result, error)` on the UI thread. The hand-over
        takes the mutating job's release, so its count falls when the handler returned, raised or was dropped."""
        def done(result, error):
            self.hand_over(lambda: handler(result, error), self.controller.take_release())
        return done

    def screens(self):
        return [s for s in self.screen_stack if hasattr(s, "render_state")]

    def changed(self):
        for screen in self.screens():
            # A screen whose message pump has stopped is unloading: its widgets are already gone by then (the
            # teardown removes them inside that pump), so painting it raises NoMatches — the 0.2s idle timer of
            # the live turn can still fire inside the unmount. Only screens that are still running are painted.
            # L-5: a screen can also be attached and running while it is already going away (the unmount awaits the
            # turn it cancels), so a screen that has begun to unmount is never painted either: the update is dropped.
            if screen.is_attached and screen.is_running and not getattr(screen, "closing", False):
                screen.render_state()

    def request_refresh(self):
        self.controller.refresh(self.deliver(self.got_snapshot))

    def request_check(self, origin="background", interactive=False):
        """Ask the worker for one readiness slice. `interactive` requests are the owner's own (Settings [g], a
        finished login, setup) and their batch closes with one catalog line; background ones (the timer, a
        navigation, the blocked-start re-check) update the checks silently.

        Readiness requests are tracked by origin and generation (R-4): a request that lands while a check runs is
        never satisfied by that check, and at most one follow-up batch waits for it (`coalesce_check`); repeated
        requests before that batch starts coalesce into it, and a background one neither replaces the waiting
        batch nor produces a closing line.

        A slice that is only queued has not read anything yet, so it is started after every request that lands
        before the worker enters it: such a request joins that batch (`controller.check_queued`) instead of
        waiting for one more slice. Only a check already executing (or one whose result is on its way) is never
        enough for a later request."""
        if self.controller.quit_begun():
            return  # R-4/C-3b: the exit admits no new readiness work; a slice queued behind it runs for nobody
        self.check_seq += 1
        request = (self.check_seq, origin, interactive)
        if not self.checking:
            self.start_check(request)
            return
        if self.controller.check_queued():
            self.check_batch = coalesce_check(self.check_batch, request)
            return
        self.pending_check = coalesce_check(self.pending_check, request)

    def start_check(self, batch):
        """Post one readiness slice and remember whose batch it is (its generation, origin and interactivity). A
        refused post (the worker still has this slice, or the app is closing) puts the batch back as the one
        waiting follow-up, so the request that asked for it is never lost (R-4).

        A slice whose own callback has not been applied yet still owns `check_batch`: `checking` stays True until
        `got_checks` took it. Starting the waiting follow-up then — `setup_done` does, when setup completes while
        another batch's delivery is still queued — would overwrite that identity with the follow-up's, so the
        completed slice would close with the wrong batch and the follow-up would close with none. The follow-up
        waits instead; `got_checks` starts it once the identity it owes is settled."""
        if self.checking:
            self.pending_check = coalesce_check(self.pending_check, batch)
            return
        if not self.controller.check(self.deliver(self.got_checks)):
            self.pending_check = coalesce_check(self.pending_check, batch)
            return
        self.checking = True
        self.check_batch = batch
        self.changed()

    def start_pending(self):
        """The one follow-up batch starts as soon as a slice can be admitted (R-4); `start_check` puts it back
        when the worker still has one, and that slice's own completion calls this again. Once the exit began the
        waiting batch is dropped instead of started: it is UI work the quit discards (R-4/C-3b), and a delivery
        that still lands (the protected job's own) must not start it behind the exit."""
        if self.pending_check is None:
            return
        pending, self.pending_check = self.pending_check, None
        if self.controller.quit_begun():
            return
        self.start_check(pending)

    def settings_keys(self):
        """The Settings actions a closing line may name, in catalog order: the enabled next keys of R-4.

        Availability is what the live guards decide, not what the session merely has a callable for: while setup
        runs, `start_setup` refuses [u] ("installation is already running") and `start_login` refuses [l] ("log in after it
        finishes"), so neither may be named as an enabled next key or as the remedy key — the catalog's key-free
        remedy stands in for it (`check_closing`)."""
        busy = self.setting_up
        offered = [i for i, usable in (("tui_settings.setup", self.controller.install is not None and not busy),
                                       ("tui_settings.login", self.controller.login is not None and not busy))
                   if usable]
        return offered + ["tui_settings.recheck", "tui_settings.roles", "tui_settings.back"]

    def got_snapshot(self, snapshot, error):
        if error:
            self.plan_error = error
        else:
            self.snapshot, self.plan_error = snapshot, ""
            # i6: the one-time language chooser is triggered by the missing language store alone, never by the
            # profile's state — an existing project that upgraded from a version which stored no language still
            # gets it, whatever its profile says (`state` is `never`, `later` or `accepted`). A profile that still
            # needs its own first-start choice gets `BootstrapScreen` after the chooser has answered (a pick comes
            # back through `choose_language`; esc keeps the locale default and stores it). L1: with one offered
            # language there is nothing to choose, so no chooser opens and the profile modal comes first.
            if not any(isinstance(s, (LanguageScreen, BootstrapScreen)) for s in self.screen_stack):
                profile = snapshot.profile
                needs_profile = profile is not None and profile.state == "never"
                if len(strings.OFFERED) > 1 and not strings.store_path().exists():
                    def first_run_language(code, profile=profile, needs_profile=needs_profile):
                        # The chooser answers on the screen below it (`choose_language` relabels that screen and
                        # stores the code); the profile modal, when the profile still needs it, follows it.
                        main = next((s for s in self.screen_stack if isinstance(s, MainScreen)), None)
                        if code and main is not None:
                            main.choose_language(code)
                        if needs_profile:
                            self.push_screen(BootstrapScreen(profile))
                    self.push_screen(LanguageScreen(), first_run_language)
                elif needs_profile:
                    self.push_screen(BootstrapScreen(profile))  # the first-start choice, once per project
            self.settle_pending(snapshot)
            # A planner that kept running while zplan was closed is watched again, once per revision.
            if snapshot.observing and not self.watching and snapshot.version not in self.resumed:
                self.resumed.add(snapshot.version)
                self.watch_planner()
            self.follow_runs(snapshot)
        self.changed()

    def got_checks(self, checks, error):
        """One readiness slice came back: an interactive batch closes with exactly one catalog line, a background
        one (the startup, a navigation, the blocked-start re-check, the timer) stays silent whatever its result —
        R-4: background requests never produce a closing line. The one coalesced follow-up batch starts below."""
        batch, self.check_batch = self.check_batch, None
        self.checking = False
        if batch is not None and batch[2]:
            self.say(check_closing(checks, error, self.settings_keys()))  # one journal line for this batch
        if not error:
            self.checks = checks
            failing = tuple(c for c in checks if not c.ok)
            if self.goal_block:
                # i3e1 repair: a refused goal/plan-card start stays blocked (and keeps its readiness card) until
                # every check passes — a recheck that still fails must not clear the marker just because it
                # answered (the form's own block and the ready card's source both read it).
                self.goal_block = failing
            if self.plan_block and not failing:
                self.plan_block = ()  # whatever blocked the start is fixed
            if tools_pass(checks):
                self.retry_chat()  # E2: the chat needs only the tool checks; a missing Git identity never holds it
            if checks and all(c.ok for c in checks):
                # i3e1 repair: readiness passing ends the readiness block itself, not just the check slice. A
                # refused goal/plan start's marker is already cleared above; the run pane's blocked-start note
                # (`Not started: …`, a refused milestone start) is the other thing `ready_blocked` reads, so it
                # goes too — otherwise the screen stays in `error` and a later failing background check grows the
                # readiness card again without any blocked start. A failed operation's own note (`Not done:`,
                # `Watching interrupted:`) is not a readiness block and stays.
                if blocked_note(note_text(self.run_note)).startswith(READY_BLOCKED_NOTE):
                    self.run_note = ""
        self.changed()
        self.start_pending()  # the one coalesced follow-up batch starts now

    def retry_chat(self):
        """Let a chat that refused preparation try again once readiness is fixed; off the event loop, no turn."""
        if self.chat is not None:
            self.chat.retry()

    def recheck_blocked(self):
        """A refused start left a message on the plan screen: look at the project again so it never outlives the
        problem it names."""
        if self.plan_block and isinstance(self.screen, PlanScreen):
            self.request_check()

    def block_lines(self):
        """The refused-start block of the plan screen: the failing checks as they are now (the last readiness
        slice), or a note that they pass."""
        if not self.plan_block:
            return []
        failing = [c for c in (self.checks if self.checks is not None else self.plan_block) if not c.ok]
        if not failing:
            return ["Checks passed: the planner can be started — [g]."]
        return [NOT_STARTED_BELOW] + ["! " + FIX_KEY.sub("", summary(c.line)) for c in failing] + [
            "Fix this (/setup on the main screen — settings), then [g] again."]

    # Pending actions -------------------------------------------------------------------

    def pending_text(self):
        """The local `starting M2…` line of an action the owner confirmed and the engine has not answered yet."""
        if self.pending is None:
            return ""
        return Delivery.pending_text(self.pending[0], self.pending[1])

    def stop_pending(self, milestone):
        """True while a confirmed stop of `milestone` is in flight or waiting for the snapshot that shows it."""
        return self.pending is not None and self.pending[0] == "stop" and self.pending[1] == milestone

    def begin_pending(self, kind, milestone):
        row = self.snapshot.row(milestone) if self.snapshot is not None else None
        self.pending = [kind, milestone, row.token if row is not None else None, time.monotonic(), None]
        self.changed()

    def confirm_pending(self):
        """The engine answered: the line stays only until a snapshot shows the change (or a few seconds)."""
        if self.pending is not None:
            self.pending[4] = time.monotonic()

    def clear_pending(self):
        self.pending = None

    def settle_pending(self, snapshot):
        if self.pending is None or self.pending[4] is None:
            return
        row = snapshot.row(self.pending[1])
        if (row.token if row is not None else None) != self.pending[2] or \
                time.monotonic() - self.pending[4] > CONFIRMED_SECONDS:
            self.pending = None

    def guard_pending(self):
        """True (and a note) when the same kind of action is already in flight: it is not repeated."""
        if self.pending is None:
            return False
        self.say_note("Already in progress: %s Wait for Zeroshot to confirm." % self.pending_text())
        return True

    def say_note(self, line):
        """A short verdict line: under the plan view on the plan screen, else with the run lines of the home.

        i6: a catalog note (`RunNote`) keeps its identity only on the home, where every repaint renders it in the
        language chosen now. The plan screen shows plain text (`plan_lines` is always strings, `screens.py` measures
        each line), and it is out of i6's scope, so a note reaching it is rendered here rather than stored as the
        object — the same shape every other line that screen already paints has."""
        if isinstance(self.screen, PlanScreen):
            self.plan_lines = (note_text(line),)
        else:
            self.run_note = line
        self.changed()

    def modal_bar(self, width):
        """The key bar text of the modal on top (None: no modal; the screen shows its own keys)."""
        top = self.screen
        return top.key_bar(width) if isinstance(top, Modal) and top.bar else None

    # Owner actions ---------------------------------------------------------------

    def say(self, line):
        self.log_lines.append(line)
        for screen in self.screen_stack:
            if isinstance(screen, SettingsScreen) and screen.is_attached:
                screen.write(line)

    def notify(self, line, origin=None):
        """Log one line and, when the action that produced it started on the plan screen, keep the outcome on that
        screen (R-4): a login or setup that failed or was cancelled stays visible on its originating form whatever
        overlay covers it by then, and the readiness closing line that follows in the journal cannot overwrite it."""
        self.say(line)
        self.notify_origin(origin, line)

    def notify_origin(self, origin, line):
        """Put `line` on the screen the action started from — the currently displayed plan screen when the action
        did not start on one. Closing lines of a readiness batch never take this route: they belong to the
        journal, so they cannot erase an action's own outcome."""
        screen = origin if isinstance(origin, PlanScreen) else self.screen
        if isinstance(screen, PlanScreen):
            self.plan_lines = (line,)
        self.changed()

    def action_settings(self):
        if not isinstance(self.screen, MainScreen):
            return
        self.push_screen(SettingsScreen())
        self.request_check()

    def action_help(self):
        """[?] from the screens: the keys of the screen on top; a second press closes the overlay."""
        top = self.screen
        if isinstance(top, HelpScreen):
            top.dismiss(None)
        elif isinstance(top, MainScreen):
            self.push_screen(HelpScreen("tui_input", "tui_panel"))
        elif isinstance(top, RunScreen):
            self.push_screen(HelpScreen("tui_run"))  # R-5: the modal's own catalog screen, journal action included
        elif isinstance(top, (ConfirmScreen, NoteScreen, TextScreen)):
            self.push_screen(HelpScreen(top.bar if top.bar != "tui_attempt" else "tui_answer"))

    # Planning --------------------------------------------------------------------

    def planner_pane(self):
        """Whether the left pane shows planner text: while the planner observes, or its text is the latest
        thing said and no milestone run is watched or has a note."""
        if self.watching:
            return True
        return bool(self.progress or self.finish_note) and not (self.run_watch or self.run_note)

    def note(self, line):
        """A line for the planner-progress area (left pane / plan screen)."""
        self.progress.append(line)
        self.changed()

    def action_open_plan(self):
        """`/view`: the plan screen; with no plan, the note naming `/plan <goal>`. Opening dispatches nothing."""
        if not isinstance(self.screen, MainScreen) or self.snapshot is None:
            return
        if not self.controller.can_plan:
            self.chat_note = "The planner is unavailable in this session."
            self.changed()
            return
        self.plan_lines = ()
        if self.snapshot.version is None:
            self.chat_note = strings.text("note.no_plan")
            self.changed()
        else:
            screen = PlanScreen()
            screen.from_main = True
            self.push_screen(screen)
            self.request_refresh()

    def leave_to_input(self):
        """Esc from the plan screen or Settings: back to the main screen with the focus on the widget that had it when
        the screen opened (R-A C1). The main screen keeps its own `focused` while covered; it reads the choice in
        `on_screen_resume`."""
        main = next((item for item in reversed(self.screen_stack[:-1]) if isinstance(item, MainScreen)), None)
        if main is not None:
            main.focus_on_resume = main.focused
        self.pop_screen()

    def answer_draft_to_open(self):
        """The newest actionable answer draft of the milestone selected in the plan pane, or None: [t]'s source.

        The milestone is the plan pane's own pick (`app.selection`), never the milestone a chat line happens to
        name: [t] answers the milestone the owner is looking at, and a history whose newest answer draft belongs
        to another milestone offers no [t] at all. The row's own id travels with the draft's identity to the
        worker, so a retained draft whose identity names another milestone is refused there and never opens that
        other attempt. Read from the retained chat state, like the goal draft."""
        content, row = self.chat, self.selection()
        if content is None or row is None:
            return None
        return chat_module.newest_answer_draft(content.state.entries, row.id)

    def action_open_answer_draft(self):
        """`/answer`: open the newest actionable answer draft of the selected milestone in the existing answer form.

        The command acts only on the main screen with no modal on top (a typed line has the chat input's focus, so
        the plan-pane guard of the `c` key does not apply). With no such draft it says so. Opening is
        read-only and starts nothing: the controller rebuilds the draft's identity on the worker with the draft's
        `milestone`, checks the token against it, re-checks it with `resolve(exact=True)` and only then builds the
        read-only view, so a draft of a moved-on attempt, or one whose identity names another milestone, is
        refused before any view or attempt exists. A refusal (a stale identity, an active attempt, a malformed
        identity, an end view without an answer) is the pane's note and opens nothing; the end view it does open
        exports nothing."""
        if not isinstance(self.screen, MainScreen):
            return
        draft = self.answer_draft_to_open()
        if draft is None:
            self.chat_note = "There is no answer draft for the selected stage."
            self.changed()
            return

        def opened(outcome, error):
            if error:
                self.note_run("Answer draft not opened: " + error)
            elif outcome.kind == "end" and outcome.data is not None and "answer" in outcome.data.names:
                self.open_answer_draft_form(draft, outcome.data)
            else:
                self.note_run("Answer draft not opened: the attempt state changed.")
        self.controller.open_answer_draft(draft.identity, draft.milestone, self.deliver(opened))

    def open_answer_draft_form(self, draft, end, note="", text=None):
        """The existing answer form, prefilled from the draft, editable, and sent with the draft's own identity.

        The provenance is the draft, captured here for as long as the form is open: the send callback calls the
        controller with `draft.identity`, never with a token of the view the screen shows, so a refresh that moves
        the screen on can never swap a fresh attempt in behind the draft.

        The field's text is the owner's own, kept apart from that identity: `None` means a fresh open, prefilled
        from the draft, while a refusal reopens the stripped copy of what was just sent (`text`) and only adds its
        note — an edited answer is never silently replaced by the draft's original prefill, and the text that stays
        on screen is the one the owner wrote, still editable and copyable."""
        self.push_screen(NoteScreen("Answer to the question of %s" % end.milestone, answer=True,
                                    text=draft.text if text is None else text, note=note),
                         lambda sent: self.send_answer_draft(draft, end, sent))

    def send_answer_draft(self, draft, end, text):
        """The draft form's explicit send: an empty field keeps the form; otherwise the answer goes through the
        existing path behind the draft's own provenance re-check (the controller's `answer_draft`).

        Every refusal (`error`, readiness, an empty field) reopens the form with the text that was sent in this very
        call, so the refusal never restores the draft's prefill over the owner's edits; only the identity and the
        milestone stay the draft's own, so the send answers the milestone the draft names and no other."""
        if text is None:
            return
        if not text:
            self.open_answer_draft_form(draft, end, EMPTY_ANSWER, text="")
            return

        def answered(outcome, error):
            self.answer_draft_settled(draft, end, text, outcome, error)
        self.controller.answer_draft(draft.identity, draft.milestone, text, self.deliver(answered))

    def answer_draft_settled(self, draft, end, text, outcome, error):
        """The verdict of the draft's send: a stale draft reopens the form with the reason and sends nothing (the
        text just typed stays copyable, no end view is exported); a started attempt closes the form and is watched.
        Every reopen carries `text` — the send's own text — and never `draft.text`: an edited answer survives the
        refusal as the owner's text, with only the note (or the readiness checks) added."""
        if error:  # "draft is stale: …" here; nothing was sent and no attempt was exported
            self.open_answer_draft_form(draft, end, error, text=text)
            return
        milestone = end.milestone
        if outcome.kind == "attempt":
            self.fresh_attempt(milestone, token_run_id(outcome), "%s: new attempt started." % milestone)
        elif outcome.kind == "active":
            self.attach_attempt(milestone, token_run_id(outcome), "%s is running." % milestone)
        elif outcome.kind == "blocked":
            self.open_answer_draft_form(draft, end, "\n".join([NOT_STARTED_BELOW] + [
                "! " + FIX_KEY.sub("", summary(c.line)) for c in outcome.checks]), text=text)
            self.request_check()
        else:
            self.note_run("%s: screen refreshed." % milestone)

    def renew_plan(self):
        def renewed(outcome, error):
            if error:
                self.say("Not done: " + error)
                self.plan_lines = ("Not done: " + error,)
            else:
                self.plan_lines = ("A new plan was prepared on the current project; the goal and settings are the same. "
                                   "The model was not started.",)
                self.chat_note = self.plan_lines[0]
            self.request_refresh()
            self.changed()
        self.controller.renew_plan(self.deliver(renewed))

    def start_goal(self, goal, card_key=None):
        """The explicit submit of a goal: readiness, then a saved unsent revision and the planner.

        `card_key` is the draft card the submission came from (the `/plan` button or the command typed in the chat,
        both through the screen's one dispatcher); a goal typed as `/plan <text>` passes nothing. The submission
        never leaves the main screen: on success a card is closed with the sent receipt, so where the decision stood
        the owner reads that the plan started. Every failure — a readiness refusal (`unsent`, which the controller
        answers without saving a revision), a submission refused as `stale` and a controller error alike — is said
        on the main line (`note_card_refusal`) and a draft card stays an open decision."""
        if self.starting:
            return
        self.starting, self.goal_message = True, ""
        self.goal_block = ()
        self.changed()

        def started(outcome, error):
            self.starting = False
            if error:
                self.goal_message = "Not done: " + error
            elif outcome.kind == "unsent":
                self.goal_block, self.goal_message = outcome.checks, NOT_STARTED
                self.request_check()
            elif outcome.kind == "stale":
                # `start_planning` answers `stale` when the prepared revision is no longer the project's (the target
                # moved between preparation and submission) and starts no planner. Nothing was sent, so a card must
                # not read as a started plan.
                self.goal_message = PLAN_OUTDATED
                self.request_refresh()
            else:
                self.goal_identity = None
                self.close_started_card(card_key)
                self.after_submission(outcome)
            if error or outcome.kind in ("unsent", "stale"):
                self.note_card_refusal(error, outcome)
            self.changed()
        self.controller.start_planning(goal, self.deliver(started), draft=self.goal_identity, card=True)

    def send_unsent_plan(self):
        """`/plan` with no card and no text: the unsent revision goes to the planner (`run_plan`; the service renews a
        stale one first, in the same step). With none, the note naming `/plan <goal>`."""
        view = self.snapshot.plan if self.snapshot is not None else None
        if view is None or view.kind not in ("unsent", "stale", "unknown"):
            screen = self.main_screen()
            if screen is not None:
                screen.status_note(strings.text("note.plan_needs_goal"))
            return
        self.run_plan(view)

    def note_card_refusal(self, error, outcome):
        """A `/plan` that did not start the planner says so on the main screen's own status line, and a draft card
        stays an open decision.

        The submission never opens a form or leaves the main screen, so without a line of its own the refusal would
        be visible nowhere. A readiness refusal lists the failing checks exactly as a blocked start does in the run
        pane; a submission refused as stale names the staleness (`PLAN_OUTDATED`, the same line the plan screen's
        own watch shows); a controller error is its own text. Nothing is said on the success kinds: there a card is
        closed and its receipt is the outcome."""
        if error:
            note = "Not done: " + error
        elif outcome.kind == "stale":
            note = PLAN_OUTDATED
        else:
            note = "\n".join([NOT_STARTED_BELOW] + ["! " + FIX_KEY.sub("", summary(c.line))
                                                    for c in outcome.checks])
        screen = self.main_screen()
        if screen is not None:
            screen.status_note(note)

    def close_started_card(self, card_key):
        """i3a: the draft card a `/plan` came from becomes the sent receipt of the started plan. No card (a goal
        typed as `/plan <text>`) closes nothing."""
        if card_key is None:
            return
        screen = self.main_screen()
        if screen is not None:
            screen.close_card(card_key, strings.text("card.draft_sent", time=card_clock()))

    def main_screen(self):
        """The main screen of this app, whatever modal sits on top (None before one is mounted): the card slot and
        its methods live there, so a plan started from a card is closed through this."""
        return next((screen for screen in self.screen_stack if isinstance(screen, MainScreen)), None)

    def plan_submission(self, outcome):
        """The verdict of the architect's plan edit (A5t2b), on the worker thread: handed to `after_submission` on
        the UI thread, exactly as the owner's own submission is, so a "ready" revision starts the planner watch that
        dispatches it and the plan screen shows it observed."""
        self.from_worker(self.after_submission, outcome)

    def after_submission(self, outcome):
        """What a service verdict means after [g]: ready starts the observation, blocked says so, the rest is
        shown by the plan view itself."""
        notes = tuple(outcome.lines)  # e.g. the service's "rebuilt on the current project" line
        if outcome.kind in ("blocked", "unsent"):
            self.plan_lines = notes
            self.plan_block = tuple(outcome.checks)  # shown by block_lines(), re-checked while it is on screen
            self.request_check()
        elif outcome.kind == "ready":
            self.plan_lines = notes
            self.plan_block = ()
            self.progress.clear()
            self.finish_note = ""
            self.watch_planner(dispatch=True)  # this watch submits the revision to the planner
            self.request_check()  # the header's readiness follows what the start just proved
        self.request_refresh()

    def run_plan(self, view):
        """[g] on the plan screen: submit the unsent revision, or run a failed/exhausted one again."""
        callback = self.deliver(lambda outcome, error: self.plan_action_done("Not done: ", outcome, error))
        if "start" in view.actions:
            self.controller.submit_plan(callback)
        else:
            self.controller.restart_plan(callback)

    def plan_action_done(self, prefix, outcome, error):
        self.plan_lines = ()
        if error:
            self.plan_lines = (prefix + error,)
            self.request_refresh()
        else:
            self.after_submission(outcome)
        self.changed()

    def revision_note(self, text):
        if text is None:
            return
        if not text and self.plan_is_stale():
            text = RENEW_NOTE  # P1a: renewing a stale proposal needs no invented text
        if not text:
            self.plan_lines = (EMPTY_CHANGE,)
            self.changed()
            return
        self.controller.revise_plan(text, self.deliver(
            lambda outcome, error: self.plan_action_done("Not done: ", outcome, error)))

    def plan_is_stale(self):
        """The current proposal is one the project moved away from (`plan.stale`): approving it is refused and a
        revision re-plans it on the project as it is now."""
        view = self.snapshot.plan if self.snapshot is not None else None
        return view is not None and view.family == "plan.stale" and "revise" in view.actions

    def forward_to_chat(self, text, leave=False):
        """P1a: a key the full screen on top has no use for is not dropped: it is typed into the main screen's chat
        input. A `leave` screen (the plan screen or Settings, for a `/`) also closes and hands the focus to that input,
        so the palette opens in view; the run end screen stays open and its buttons keep the focus (the keys that act
        there are untouched), the text waiting in the input for when the owner closes it."""
        main = next((item for item in reversed(self.screen_stack[:-1]) if isinstance(item, MainScreen)), None)
        if main is None:
            return
        field = main.query_one("#input", Input)
        if leave:
            main.focus_on_resume = field
            self.pop_screen()
        self.type_in_chat(field, text)

    def type_in_chat(self, field, text):
        """Append `text` to the chat input once its focus has settled: taking the focus selects the whole value
        (`Input.select_on_focus`), and the first character would replace the text already typed."""
        def put():
            field.cursor_position = len(field.value)
            field.insert_text_at_cursor(text)
        self.call_after_refresh(put)

    def confirm(self, question, then, enter_yes=False):
        """`enter_yes`: the start / resume confirmations start with the focus on "yes", so `/run` + Enter finishes the
        start (i11/R4)."""
        self.push_screen((EnterConfirmScreen if enter_yes else ConfirmScreen)(question),
                         lambda yes: then() if yes else None)

    def override_note(self, version, text):
        """The reason form closed: Esc (None) writes nothing; a reason the rule refuses is refused here, before the
        service is called (the service refuses it again)."""
        if text is None:
            return
        try:
            reason = override_reason(text)
        except Blocked as error:
            self.plan_lines = ("Not done: " + refusal(error),)
            self.changed()
            return
        self.decide("override", version, reason)

    def decide(self, name, version, reason=None, after=None):
        """The owner's decision on a plan revision. The controller runs it on the worker and its verdict comes back
        through the callback below, never as a synchronous return: `after(outcome, error)`, when given, is the
        caller's own hook on that verdict — run once the plan screen's own lines have been set."""
        def decided(outcome, error):
            if error:
                self.plan_lines = ("Not done: " + error,)
            elif outcome.kind == "overridden":
                self.progress.clear()
                self.finish_note = ""
                self.plan_lines = ("Plan r%s approved despite the check. Implementation was not started; start it with /run on the "
                                   "main screen." % version,)
            elif outcome.kind == "approved":
                self.progress.clear()  # the planner's last words are history once the plan is approved
                self.finish_note = ""
                self.plan_lines = ("Plan r%s approved. Implementation was not started; start it with /run on the main screen."
                                   % version,)
            else:
                self.plan_lines = ("Proposal r%s was not approved; nothing was started." % version,)
            self.request_refresh()
            self.changed()
            if after is not None:
                after(outcome, error)
        if name == "approve":
            self.controller.approve_plan(version, self.deliver(decided))
        elif name == "override":
            self.controller.override_plan(version, reason, self.deliver(decided))
        else:
            self.controller.reject_plan(version, self.deliver(decided))

    def show_details(self):
        """[i] on the plan screen toggles the requirements/diagnostics block under the plan."""
        if self.plan_lines and self.plan_lines == self.details_lines:
            self.plan_lines = self.details_lines = ()
            self.changed()
            return

        def shown(outcome, error):
            self.plan_lines = tuple(outcome.lines) if not error else ("Not done: " + error,)
            self.details_lines = self.plan_lines if not error else ()
            self.changed()
        self.controller.details(self.deliver(shown))

    # Milestones --------------------------------------------------------------------

    def rows(self):
        return self.snapshot.rows if self.snapshot is not None else ()

    def selection(self):
        """The selected milestone row: the owner's pick, else the one the service names under "Next"."""
        rows = self.rows()
        if not rows:
            return None
        found = next((r for r in rows if r.id == self.selected), None)
        if found is None and self.snapshot.focus is not None:
            found = next((r for r in rows if r.id == self.snapshot.focus), None)
        return found or rows[0]

    def action_select(self, step):
        if not isinstance(self.screen, MainScreen):
            return
        rows = self.rows()
        if not rows:
            panel = self.screen.query_one("#plan-pane")
            (panel.scroll_down if step > 0 else panel.scroll_up)()
            return
        index = [r.id for r in rows].index(self.selection().id)
        self.selected = rows[max(0, min(len(rows) - 1, index + step))].id
        self.changed()

    def note_run(self, line):
        self.run_note = line
        self.changed()

    def g_action(self, row):
        """The catalog action [g] has on the selected row of the panel (the delivery service's decision as the
        snapshot carries it): check, start, resume, new attempt, or None (nothing; busy elsewhere)."""
        busy = self.snapshot.busy if self.snapshot is not None else None
        if row.state in CHECK:
            return "tui_panel.check"
        if busy is not None:
            return None
        if row.startable:
            return "tui_panel.run"
        if row.state == "failed_recoverable":
            return "tui_panel.resume"
        if row.state in ("failed", "stopped"):
            return "tui_panel.attempt"
        return None

    def action_run_milestone(self):
        """[g] on the plan panel: reconcile an interrupted attempt, start a ready milestone, resume a failed one
        in its worktree, or begin a new attempt of a stopped/failed one. Never starts while another milestone
        holds the single active slot."""
        row = self.selection() if isinstance(self.screen, MainScreen) else None
        if row is None or self.guard_pending():
            return
        g = self.g_action(row)
        busy = self.snapshot.busy if self.snapshot is not None else None
        if g == "tui_panel.check":
            self.check_milestone(row)
        elif g == "tui_panel.run":
            self.preview_milestone(row)
        elif g == "tui_panel.resume":
            self.resume_milestone(row)
        elif g == "tui_panel.attempt":
            self.new_attempt_milestone(row)
        elif busy is not None and busy != row.id and row.state in ("ready", "failed_recoverable", "failed", "stopped"):
            self.note_run(self.busy_note(busy))
        else:
            self.note_run("%s: %s." % (row.id, row.text))

    def busy_note(self, busy):
        """The refusal `/run` shows while every parallel slot is taken (C2): with one slot today's line, with more
        slots the slot count and the active milestones `Delivery.full_line` builds (its letter keys as commands)."""
        slots = self.snapshot.slots if self.snapshot is not None else 1
        ids = [r.id for r in self.snapshot.rows if r.state in ("running", "stopping", "unknown")] \
            if self.snapshot is not None else []
        full = full_line(ids, slots)
        return command_hints(full) if full else (
            "Busy with %s: a new start, a continuation and a new attempt wait. "
            "/attempt to watch, /run on it to check." % busy)

    def run_target(self):
        """The row `/run` acts on: the selected row when it has a [g] action, else the first row with one; with a busy
        slot, the first ready/failed/stopped row the busy slot is holding back (its [g] is the busy note). None when
        `/run` has nothing to do — the palette lists `/run` only when this is not None (`palette_hidden`)."""
        rows = self.rows()
        row = self.selection()
        if row is None or self.g_action(row) is None:
            row = next((r for r in rows if self.g_action(r) is not None), None)
        if row is None and self.snapshot is not None and self.snapshot.busy is not None:
            row = next((r for r in rows if r.id != self.snapshot.busy
                        and r.state in ("ready", "failed_recoverable", "failed", "stopped")), None)
        return row

    def palette_hidden(self):
        """The commands the palette leaves out although their state allows them: `/run` with no row to act on. A
        typed `/run` is not affected — it still answers with `action_run_next`'s refusal."""
        return () if self.run_target() is not None else ("/run",)

    def action_run_next(self):
        """i11 `/run`: what [g] does on the row the pane's [g] acts on (`run_target`) through
        `action_run_milestone`'s own branches. With no such row: one "Not done: …" chat line. The owner's
        selection is put back at once."""
        row = self.run_target()
        if row is None:
            self.chat_note = "Not done: no stage is ready to start."
            self.changed()
            return
        previous, self.selected = self.selected, row.id
        self.action_run_milestone()
        self.selected = previous

    def preview_milestone(self, row):
        def previewed(outcome, error):
            if error:
                self.run_note = "Not done: " + error
            elif outcome.kind == "blocked":
                self.run_note = "\n".join([NOT_STARTED_BELOW] + [
                    "! " + FIX_KEY.sub("", summary(c.line)) for c in outcome.checks])
                self.request_check()
            else:
                preview = outcome.data
                self.confirm(outcome.lines[0], lambda: self.begin_run(preview), enter_yes=True)
            self.changed()
        self.controller.preview_start(row.id, self.deliver(previewed))

    def begin_run(self, preview):
        if self.guard_pending():
            return

        def started(outcome, error):
            if error:
                self.clear_pending()
                self.run_note = "Not started: %s Screen refreshed." % error
            elif outcome.kind == "changed":
                # The profile changed after the preview: nothing started; the new preview is confirmed again.
                self.clear_pending()
                self.run_note = "Not started: " + outcome.lines[0]
                fresh = outcome.data
                self.confirm(outcome.lines[1], lambda: self.begin_run(fresh), enter_yes=True)
            else:
                self.confirm_pending()
                self.run_note = ""
                self.request_refresh()  # queued before the observation: the row shows the attempt at once
                self.fresh_attempt(preview.milestone, token_run_id(outcome), "%s started · plan r%s · attempt %s" % (
                    preview.milestone, preview.plan_revision, preview.attempt))
                self.request_check()
            self.request_refresh()
            self.changed()
        self.begin_pending("start", preview.milestone)
        self.controller.start_run(preview, self.deliver(started))

    def check_milestone(self, row):
        self.run_note = "Reconciling %s with Zeroshot (without sending again)…" % row.id
        self.changed()
        self.controller.check_run(row.token, self.deliver(
            lambda outcome, error: self.opened(row.id, outcome, error)))

    def attempt_job(self, kind, milestone, call):
        """A confirmed resume / new attempt from the panel: the pending line until the engine answers."""
        def done(outcome, error):
            if error or outcome.kind in ("stale", "blocked"):
                self.clear_pending()
                if error:
                    self.run_note = "Not done: " + error
                elif outcome.kind == "blocked":
                    self.run_note = "\n".join([NOT_STARTED_BELOW] + [
                        "! " + FIX_KEY.sub("", summary(c.line)) for c in outcome.checks])
                    self.request_check()
                else:
                    self.run_note = "%s Screen refreshed." % (outcome.lines[0] if outcome.lines else MOVED)
            else:
                self.confirm_pending()
                self.run_note = ""
                self.request_refresh()
                self.fresh_attempt(milestone, token_run_id(outcome),
                                   "%s: %s." % (milestone, "continuing the same attempt" if kind == "resume"
                                                else "new attempt started"))
            self.request_refresh()
            self.changed()
        self.begin_pending(kind, milestone)
        call(self.deliver(done))

    def resume_milestone(self, row):
        token = row.token
        self.confirm("Continue %s (attempt %s)?\nThe same attempt in its working tree; what is already done is not lost."
                     % (row.id, token.attempt),
                     lambda: self.attempt_job("resume", row.id,
                                              lambda done: self.controller.resume_run(token, done)), enter_yes=True)

    def new_attempt_milestone(self, row):
        """[g] on a stopped or failed milestone: the new-attempt form (what it does, the field, the confirm key)."""
        def opened(outcome, error):
            if error:
                self.run_note = "Not done: " + error
                self.changed()
            elif outcome.kind == "end" and "new_attempt" in outcome.data.names:
                end = outcome.data
                self.push_screen(self.attempt_screen(end), lambda text: None if text is None else self.attempt_job(
                    "attempt", end.milestone, lambda done: self.controller.new_attempt(end.token, text, done)))
            else:
                self.opened(row.id, outcome, error)  # the end view lists what is possible
        self.controller.open_run(row.id, self.deliver(opened))

    @staticmethod
    def attempt_screen(end):
        return NoteScreen(
            "New attempt %s · %s\n%s\nThis is a new run of the stage: the model will be started again. "
            "The earlier attempt stays in the history." % (end.milestone, end.title, NEW_ATTEMPT % end.branch),
            answer=True, bar="tui_attempt", label="Note for the new attempt (optional, may be left empty):")

    def action_stop_milestone(self):
        row = self.selection() if isinstance(self.screen, MainScreen) else None
        if row is None or row.state != "running" or row.token is None:
            if row is not None:
                self.note_run("%s: %s — nothing to stop." % (row.id, row.text))
            return
        if self.guard_pending():
            return

        def stopped(outcome, error):
            if error:
                self.clear_pending()
                self.run_note = "Not stopped: " + error
            elif outcome.kind == "stale":
                self.clear_pending()
                self.run_note = "Not stopped: %s Screen refreshed." % outcome.lines[0]
            else:
                self.confirm_pending()
                self.run_note = RunNote(STOP_REQUESTED, stage=row.id)
                self.watch_run(row.id)
            self.request_refresh()
            self.changed()

        def stop():
            self.begin_pending("stop", row.id)
            self.controller.stop_run(row.token, self.deliver(stopped))
        self.confirm(Delivery.stop_text(row.token), stop)

    # The activity tail ------------------------------------------------------------------

    def tail_target(self, row=None):
        """The milestone whose log [e] shows (the selected row first), "" for the planner, None for nothing."""
        snapshot = self.snapshot
        if snapshot is None:
            return None
        for r in ([row] if row is not None else []) + list(snapshot.rows):
            if r.state in TAILABLE and r.token is not None and r.token.run_id and not r.carried:
                return r.id
        if not snapshot.rows and snapshot.plan is not None and "tail" in snapshot.plan.actions:
            return ""
        return None

    def action_tail_activity(self):
        if isinstance(self.screen, MainScreen):
            self.show_tail()

    def show_tail(self):
        """[e]: the last lines of `zeroshot logs`, read once on the worker (never on refresh)."""
        target = self.tail_target(self.selection())
        if target is None:
            self.say_note("Log: there is no running or failed run right now.")
            return

        def shown(outcome, error):
            if note_is(self.run_note, READING):
                self.run_note = ""
            if error:
                self.say_note("Log unavailable: " + error)
                return
            self.push_screen(TextScreen(outcome.data, outcome.lines))
        self.say_note(RunNote(READING))
        if not self.controller.tail(self.deliver(shown), target or None):
            self.say_note("The log is already being read.")

    def tail_modal(self, modal):
        def shown(outcome, error):
            if error:
                modal.set_end(modal.end, "Log unavailable: " + error)
            elif outcome.kind == "stale":
                self.settled(modal, outcome, None)
            else:
                self.push_screen(TextScreen(outcome.data, outcome.lines))
        if not self.controller.tail_run(modal.end.token, self.deliver(shown)):
            modal.set_end(modal.end, "The log is already being read.")

    def action_open_milestone(self):
        """[o]: the end-of-run view of the selected attempt (an active one: observation attaches again)."""
        row = self.selection() if isinstance(self.screen, MainScreen) else None
        if row is None:
            return
        if row.token is None:
            self.note_run("%s: %s." % (row.id, row.text))
            return
        self.controller.open_run(row.id, self.deliver(lambda outcome, error: self.opened(row.id, outcome, error)))

    def opened(self, milestone, outcome, error):
        if error:
            self.run_note = "Not done: " + error
        elif outcome.kind == "none":
            self.run_note = outcome.lines[0]
        elif outcome.kind == "active":
            self.run_note = "%s is running; watching continues." % milestone
            self.request_refresh()
            # C4: the outcome names the attempt this open found (an architect rebrief may have started one the
            # screen has not refreshed yet), so its own run id is adopted -- never the predecessor's buffer or
            # identity, which `watch_run` alone would reuse.
            self.attach_attempt(milestone, token_run_id(outcome))
        else:
            self.run_note = ""
            self.show_end(outcome.data)
        self.request_refresh()
        self.changed()

    def action_milestone_details(self):
        """[i] on the plan panel: the outcome first, then the plan, diagnostics last (the plain [i] text)."""
        if not isinstance(self.screen, MainScreen):
            return

        def shown(outcome, error):
            lines = outcome.lines if not error else ("Not done: " + error,)
            self.push_screen(TextScreen("Details", lines))
        self.controller.plan_record(self.deliver(shown))

    # An attempt under observation ----------------------------------------------------

    def follow_runs(self, snapshot):
        """A running attempt that kept going while zplan was closed is observed again, once per run: every running
        row gets a chain of its own (C4), so an attempt that finishes while another is shown is still concluded and
        frees its slot, and the first one becomes the shown attempt when nothing is shown yet; an open end-of-run
        modal whose attempt moved underneath is re-rendered."""
        for row in snapshot.rows:
            if not self.follow or row.token is None or row.state not in ("running", "stopping"):
                continue
            if row.token.run_id in self.run_seen:
                continue
            self.run_seen.add(row.token.run_id)
            self.adopt_run(row.id, row.token.run_id)  # a new attempt's own lines, never the finished one's (C4)
            if self.run_watch is None:
                self.watch_run(row.id)  # the first one: shown, and its own chain starts
            else:
                self.observe_attempt(row.id)  # a chain of its own, without taking over the run lines
        modal = next((s for s in self.screen_stack if isinstance(s, RunScreen)), None)
        if modal is not None:
            now = snapshot.row(modal.end.milestone)
            if now is None or now.token != modal.end.token:
                self.controller.open_run(modal.end.milestone, self.deliver(
                    lambda outcome, error: self.refreshed(modal, outcome, error)))

    def refreshed(self, modal, outcome, error):
        """The answer to a re-render request: the modal now shows the attempt as it is."""
        if error or not modal.is_attached:
            return
        if outcome.kind == "end":
            if outcome.data.token != modal.end.token:
                modal.set_end(outcome.data, MOVED)
        else:
            modal.dismiss(None)
            self.run_note = outcome.lines[0] if outcome.lines else "%s: the run changed." % modal.end.milestone
        self.changed()

    def run_buffer(self, milestone):
        """The run lines of `milestone`'s attempt: the deque its own chain appends to (C4)."""
        return self.run_buffers.setdefault(milestone, deque(maxlen=PROGRESS_LINES))

    def adopt_run(self, milestone, run_id):
        """The observation state of `milestone`'s current attempt, discovered by `follow_runs` (an architect
        rebrief starts one the app did not): a run id that is not the one its lines belong to means a new attempt,
        which gets its own, empty lines and its own chain (C4) -- the finished attempt's buffered lines are never
        shown for it. When the milestone is the shown one, its new attempt's lines are shown from now on; another
        milestone's new attempt leaves the shown attempt's place untouched."""
        owner = self.run_buffer_id.get(milestone)
        if owner is not None and owner != run_id:
            if self.run_last == milestone:
                self.fresh_run_lines(milestone)  # the shown milestone: the new attempt's empty lines are shown
            else:
                self.run_buffers[milestone] = deque(maxlen=PROGRESS_LINES)
                self.run_chain.discard(milestone)  # a new attempt is a new chain
        self.run_buffer_id[milestone] = run_id

    def show_run(self, milestone):
        """The run lines show `milestone`'s attempt from now on, keeping what that attempt already emitted; the
        attempt left behind keeps its own lines (a direct append before the switch is flushed into its buffer)."""
        if self.run_last is not None:
            self.run_buffers[self.run_last] = self.run_lines
        self.run_watch = self.run_last = milestone
        self.run_lines = self.run_buffer(milestone)
        return self.run_lines

    def fresh_run_lines(self, milestone):
        """The run lines of a *new* attempt of `milestone`: a fresh, empty buffer, shown from now on."""
        if self.run_last is not None:
            self.run_buffers[self.run_last] = self.run_lines
        self.run_buffers[milestone] = deque(maxlen=PROGRESS_LINES)
        self.run_chain.discard(milestone)  # a new attempt is a new chain
        self.run_buffer_id[milestone] = None  # the new attempt's run id is not known yet (`follow_runs` adopts it)
        self.run_watch = self.run_last = milestone
        self.run_lines = self.run_buffers[milestone]
        return self.run_lines

    def fresh_attempt(self, milestone, run_id, line=None):
        """A *new* attempt of `milestone` (its Token's `run_id`, `line` the run lines' first note) is the shown and
        observed attempt: its own, empty buffer (C4), its own identity from the very first slice on -- so no later
        adoption drops its slices as another attempt's -- and its own chain. This is the one entry point the
        retry paths share, the owner's own [g] and the failure card's `/retry` alike."""
        self.fresh_run_lines(milestone)
        if run_id is not None:
            self.run_buffer_id[milestone] = run_id  # the attempt's own identity, never the finished one's
        if line is not None:
            self.run_lines.append(line)
        self.watch_run(milestone)

    def attach_attempt(self, milestone, run_id, line=None):
        """An attempt of `milestone` the screen observes again (`line` the note): a `run_id` that is not the one its
        lines belong to is a later attempt, which gets its own, empty buffer and chain (C4); the observation then
        carries this attempt's identity."""
        if run_id is not None:
            self.adopt_run(milestone, run_id)
        self.watch_run(milestone)
        if line is not None:
            self.run_lines.append(line)

    def watch_run(self, milestone):
        """Observe the attempt of `milestone` in slices (one worker job each); input and quit stay responsive
        between them. The run lines show this attempt from now on; every running attempt keeps a chain of its own."""
        self.run_lines = self.show_run(milestone)
        if not self.watching:
            self.progress.clear()  # a stale planner finish never stays over a run
            self.finish_note = ""
        self.changed()
        self.observe_attempt(milestone)

    def observe_attempt(self, milestone):
        """Start `milestone`'s own chain of watch slices when it has none; its lines land in its own buffer, so
        another attempt's lines are never attributed to it and a result carries this milestone and its attempt
        (C4). A chain is marked only with its first slice's submission; a submission the worker coalesces away
        (the same milestone *and* the same run id already has a slice pending, which then carries the chain on)
        leaves no chain stranded -- a different run id never coalesces with it (see `post_slice`)."""
        if milestone in self.run_chain:
            return
        self.run_chain.add(milestone)
        self.post_slice(milestone, self.run_buffer_id.get(milestone))

    def post_slice(self, milestone, run_id):
        """Post the next bounded slice of `milestone`'s chain; the callbacks carry the milestone and the attempt
        (`run_id`), so a result is never attributed to another attempt (C4). The slice's run id is part of the
        job's label, so a new attempt's slice is never coalesced away by a still pending slice of the finished
        attempt: a coalesced submission always means the same attempt already has one waiting, which continues the
        chain -- never a chain marked active with nothing scheduled."""
        self.controller.observe_run(
            milestone, lambda line, name=milestone, rid=run_id: self.emit_run(name, rid, line),
            self.deliver(
                lambda outcome, error, name=milestone, rid=run_id: self.run_slice(name, rid, outcome, error)),
            run_id)

    def emit_run(self, milestone, run_id, line):
        """A phase line of `milestone`'s attempt, on the worker thread."""
        self.from_worker(self.run_line, milestone, run_id, line)

    def run_line(self, milestone, run_id, line):
        if self.stale_run(milestone, run_id):
            return  # a finished attempt's line: never the current attempt's (C4)
        self.run_buffer(milestone).append(line)
        self.changed()

    def stale_run(self, milestone, run_id):
        """Whether a slice of a finished attempt reached the app after a new attempt of `milestone` took over: its
        lines, its end and its chain belong to the old attempt, never to the current one (C4)."""
        owner = self.run_buffer_id.get(milestone)
        return run_id is not None and owner is not None and owner != run_id

    def run_slice(self, milestone, run_id, outcome, error):
        """The verdict of one slice of `milestone`'s chain, carrying the attempt it belongs to (C4). The shown
        attempt's slice is the owner's own (`run_watched`: the lines and the end screen); a background attempt's
        slice never takes those over, but still concludes the attempt and frees its slot, or continues its chain."""
        if self.stale_run(milestone, run_id):
            return  # a finished attempt's slice: it must not conclude the new attempt's chain (C4)
        if milestone == self.run_watch:
            self.run_watched(run_id, outcome, error)
        else:
            self.request_refresh()
            self.changed()
            if not error and outcome.kind == "continue":
                self.post_slice(milestone, run_id)  # the background chain goes on beside the shown attempt
        if error or outcome.kind != "continue":
            self.run_chain.discard(milestone)  # the chain is over: nothing follows this attempt

    def run_watched(self, run_id, outcome, error):
        """The shown attempt's slice verdict: its lines, its end screen and its note are the owner's (the milestone
        is `run_watch`, which `run_slice` has already matched)."""
        milestone = self.run_watch
        if error:
            self.run_watch = None
            self.run_note = "Watching interrupted: %s /attempt — continue." % error
        elif outcome.kind == "continue":
            self.request_refresh()  # the plan pane rows follow: phase, task counts
            self.post_slice(milestone, run_id)
            return
        else:
            self.run_watch = None
            if note_is(self.run_note, STOP_REQUESTED):
                self.run_note = ""  # answered by the result below: never left after "finished"
            if outcome.data is not None:
                self.run_lines.append("%s finished." % milestone)
                if outcome.data.state not in AUTO_END_CARDS:  # that state's card replaces the automatic modal
                    self.show_end(outcome.data)
        self.request_refresh()
        self.changed()

    def show_end(self, end, note=""):
        """The end-of-run modal; an open one is replaced in place. Over a form or another screen it is not
        pushed: the row says the attempt ended and [o] opens it."""
        modal = next((s for s in self.screen_stack if isinstance(s, RunScreen)), None)
        if modal is not None:
            modal.set_end(end, note)
        elif isinstance(self.screen, MainScreen):
            self.push_screen(RunScreen(end, note))
        else:
            self.run_note = "%s finished: /attempt on the main screen opens the result." % end.milestone

    def modal_action(self, modal, name):
        """An owner action of the end-of-run modal; every one carries the attempt the modal was built from."""
        end = modal.end
        token = end.token
        kind = {"merge": "merge", "new_attempt": "attempt", "resume": "resume", "check": "check"}.get(name)
        if kind is not None and name != "new_attempt" and self.guard_pending():
            modal.set_end(modal.end, "Already in progress: %s" % self.pending_text())
            return

        def settled(outcome, error):
            self.settled(modal, outcome, error)

        def begin(kind=kind):
            if kind is not None:
                self.begin_pending(kind, end.milestone)
                modal.set_end(modal.end, self.pending_text())

        def sent(text):
            if text is None:
                return
            if name == "answer":
                if not text:
                    modal.set_end(modal.end, EMPTY_ANSWER)
                    return
                self.controller.answer(token, text, self.deliver(settled))
            elif name == "new_attempt":
                if self.guard_pending():
                    modal.set_end(modal.end, "Already in progress: %s" % self.pending_text())
                    return
                begin()
                self.controller.new_attempt(token, text, self.deliver(settled))
            else:
                if not text:
                    modal.set_end(modal.end, EMPTY_CHANGE)
                    return
                self.controller.to_plan(token, text, self.deliver(settled))
        if name == "diff":
            self.controller.diff(token, self.deliver(lambda outcome, error: self.diff_shown(modal, outcome, error)))
        elif name == "merge":
            def merge():
                begin()
                self.controller.merge(token, self.deliver(settled))
            self.confirm(end.question, merge)
        elif name == "check":
            begin()
            self.controller.check_run(token, self.deliver(settled))
        elif name == "resume":
            begin()
            self.controller.resume_run(token, self.deliver(settled))
        elif name == "accept":
            self.controller.accept(token, self.deliver(settled))
        elif name == "leave":
            self.controller.leave(token, self.deliver(settled))
        elif name == "answer":
            self.push_screen(NoteScreen("Answer to the question of %s" % end.milestone, answer=True), sent)
        elif name == "new_attempt":
            self.push_screen(self.attempt_screen(end), sent)
        elif name == "plan":
            self.push_screen(NoteScreen("What to change in the plan", answer=True), sent)

    def diff_shown(self, modal, outcome, error):
        if error:
            modal.set_end(modal.end, "Not done: " + error)
        elif outcome.kind == "stale":
            self.settled(modal, outcome, None)
        else:
            self.push_screen(TextScreen("Changes %s" % modal.end.milestone, outcome.lines, diff=True))

    def settled(self, modal, outcome, error):
        """The verdict of an owner action, on the modal that asked."""
        if error or outcome.kind in ("stale", "blocked"):
            self.clear_pending()
        else:
            self.confirm_pending()
        if not modal.is_attached:
            self.request_refresh()
            return
        milestone = modal.end.milestone
        if error:
            modal.set_end(modal.end, "Not done: " + error)
        elif outcome.kind == "stale":
            note = "%s %s" % (MOVED, outcome.lines[0] if outcome.lines else "")
            if outcome.data is not None:
                modal.set_end(outcome.data, note.strip())
            else:
                modal.dismiss(None)
                self.run_note = "%s: the run changed; screen refreshed." % milestone
        elif outcome.kind == "blocked":
            modal.set_end(modal.end, "\n".join([NOT_STARTED_BELOW] + [
                "! " + FIX_KEY.sub("", summary(c.line)) for c in outcome.checks]))
            self.request_check()
        elif outcome.kind in ("attempt", "active"):
            modal.dismiss(None)
            if outcome.kind == "attempt":
                self.fresh_attempt(milestone, token_run_id(outcome), "%s: new attempt started." % milestone)
            else:
                self.attach_attempt(milestone, token_run_id(outcome), "%s is running." % milestone)
        elif outcome.kind == "left":
            modal.dismiss(None)
            self.run_note = outcome.lines[0]
        elif outcome.kind == "plan":
            modal.dismiss(None)
            self.after_submission(outcome.data)
            self.plan_lines = tuple(outcome.lines)
            screen = PlanScreen()
            screen.from_main = True  # R-A C1: Esc returns the focus as from the [p] plan screen
            self.push_screen(screen)
        elif outcome.kind == "end":
            modal.set_end(outcome.data, "")
        else:  # integrated / conflict / refused / open: the merge verdict, with the attempt as it is now
            end = outcome.data if outcome.data is not None else modal.end
            modal.set_end(end, outcome.lines[0] if outcome.lines else "")
        self.request_refresh()
        self.changed()

    def watch_planner(self, dispatch=False):
        """Observe the planner in slices (one worker job each) so input and quit stay responsive between them.
        `dispatch` is the first slice of a submission the service just accepted: that one prepares the checkout,
        sends the revision to the planner and saves the receipt, so the controller counts it as a mutating job and a
        quit waits for it instead of cutting it. Every other watch observes a revision that is already dispatched
        and stays cuttable; only the submission verdict knows which one this is."""
        if self.watching or not self.controller.can_plan:
            return
        self.watching = True
        self.changed()
        self.controller.observe(self.emit_phase, self.deliver(self.watched), dispatch=dispatch)

    def emit_phase(self, line):
        """A planner phase line, on the worker thread."""
        self.from_worker(self.note, line)

    def watched(self, outcome, error):
        if error:
            self.watching = False
            self.note("Not done: " + error)
        elif outcome.kind == "continue":
            self.request_refresh()  # the plan screen follows the receipt: sent, observing
            self.controller.observe(self.emit_phase, self.deliver(self.watched))
            return
        else:
            self.watching = False
            if self.run_watch is None:
                self.run_note = ""  # the planner's finish is the latest word, not an older milestone note
            self.finish_note = {
                "done": "The planner finished: /view opens the plan.",
                "failed": "Planning stopped: /view opens the plan.",
                "stale": PLAN_OUTDATED}.get(
                    outcome.kind, "Watching finished.")
            self.changed()
        self.request_refresh()

    def recheck(self):
        self.say("Checking readiness…")
        self.request_check(origin="recheck", interactive=True)

    def start_setup(self):
        origin = self.screen  # the form the owner pressed [u] on; an overlay may cover it before the setup ends
        if self.controller.install is None:
            self.notify("Installing tools is unavailable here (test mode or an explicitly set executable).",
                        origin)
            return
        if self.setting_up:
            self.notify("Installation is already running.", origin)
            return
        self.setting_up = True
        self.setup_origin = origin
        self.say("Installing tools…")

        def emit(line):
            self.from_worker(self.say, line)
        self.controller.setup(emit, self.deliver(self.setup_done))

    def setup_done(self, checks, error):
        """Setup's own post-install check closes its interactive batch: no second, redundant check is asked for.
        Its failure stays on the form the setup started from, whatever is displayed by the time it returns; the
        closing line of its batch belongs to the journal (R-4)."""
        origin, self.setup_origin = self.setup_origin, None
        self.setting_up = False
        if error:
            self.notify("Not done: " + error, origin)
        else:
            self.checks = checks
            self.say("Installation finished." if all(c.ok for c in checks) else
                     "Installation finished; some issues remain — see the list above.")
            if tools_pass(checks):
                self.retry_chat()  # a chat that refused a missing toolchain prepares now that it is installed
        self.say(check_closing(checks, error, self.settings_keys()))
        self.start_pending()  # a request that landed while setup held the worker is not lost (R-4)
        self.changed()  # the readiness pane shows the post-install checks this batch carried

    def start_login(self, plan=None):
        """The interactive login: its readiness request is registered after the login returns, so the in-flight
        checks of the wait can never be mistaken for its result (R-4). `plan` is the failed plan screen's view
        ([l] refresh login): the login then targets the home that run recorded and refreshes it after a confirmation."""
        origin = self.screen  # the form the owner pressed [l] on; an overlay may cover it before the login returns
        if self.controller.login is None:
            self.notify("Login is unavailable here (test mode or an explicitly set executable).", origin)
            return
        if self.setting_up:
            self.notify("Installation is running; log in after it finishes.", origin)
            return
        self.say("Logging in to Codex in this terminal…")
        try:
            with self.suspend():
                code = self.controller.login(**({"home": plan.home, "refresh": True} if plan is not None else {}))
        except SuspendNotSupported:
            self.notify("This terminal does not support suspending: run zplan login separately.", origin)
            return
        except (Blocked, OSError, ValueError) as error:
            self.notify("Login failed: " + refusal(error), origin)
        except KeyboardInterrupt:
            self.notify("Login interrupted.", origin)
        else:
            self.notify("Login finished." if not code else
                        "Login interrupted." if code == INTERRUPTED else
                        "Login not completed (code %s); log in again: [l]. " % code + catalog.LOGIN_DEVICE_CODE_OFF
                        + catalog.tag("setup.login_failed"),
                        origin)
        self.request_check(origin="login", interactive=True)


def submit_verdict(screen, line):
    """The palette's verdict for one typed `line` in the chat (`MainScreen.on_input_submitted`), with the i3c
    repair: a line the palette refuses only because another decision card's state leads is accepted when an open
    merge card answers it.

    The failure this repairs (code-review finding P2): a goal-draft card and the stage-done merge card coexist, so
    `screen_slash_state` reads `draft` (the i3a precedence — an open draft beats every other fact) while the merge
    card is open; the palette then refused the typed `/merge` as out of state, although the card's own button ran
    the very same `action_merge` — exactly the button/typed-line divergence the i3a repair fixed for `/plan`. Here
    the open merge card is judged as its own state: a line the `merge` state allows and whose only other
    `slash.problem` is none (an unknown name, a missing argument or a bad `/language` code is not a state matter)
    becomes a `Submitted`, so `run_command` routes it to the newest open merge card, exactly as clicking the button
    does — draft commands and every other state stay the palette's own decision, because with no open merge card the
    verdict is `palette.submit`'s own. `action_merge`'s own `guard_pending` is untouched: a second `/merge` while
    the first is in flight is still refused there."""
    verdict = palette.submit(line, screen_slash_state(screen.app))
    if isinstance(verdict, palette.Refused) and merge_card_open(screen):
        parsed = slash.parse(line)
        if parsed is not None and parsed.command is not None and slash.problem(parsed, "merge") is None:
            return palette.Submitted(parsed.command.name, parsed.argument)
    return verdict
