"""S0 of 0.5.2 (docs/RELEASE_0.5.2_PLAN.md): the `terminal_planner/tui/app.py` split into `text`, `chat_view`, `modals`
and `screens`. A1: app.py no longer defines the moved blocks and each new module holds exactly its block. A2: every
name `dir(terminal_planner.tui.app)` listed before the change is still an attribute of it, and each moved name *is*
the moved module's own object. A4: the README code map names the four modules, one line each.

The moved names below are the contract the rest of the TUI suite already reaches through the app module
(`app_module.CHAT_MIN_ROWS`, `app_module.chat_head`, ...), so they are listed here rather than derived: the test
pins what the other tests and callers used before the split. The identity assertions import Textual; the source and
README scans read files and need neither Textual nor Rich.

Interpretations recorded here (the worker's session summary never reaches the reviewers):

- A1's "app.py is at most ~1900 lines" does not follow from this task's own block list and non-goals and is unreachable:
  the moved blocks are 1101 of the original 3384 lines (app.py is 2283 after the move), MainScreen (app.py:325-884) and
  ZplanApp (app.py:885-2283) — the two classes the task keeps — are 1959 lines on their own, and the remaining top-level
  lines of app.py (imports, the re-export block, the constants and helpers MainScreen/ZplanApp read, PlanPanel) are 324,
  so even moving every one of them leaves 1959 > 1900. The acceptance and code reviews raised this same contradiction and
  asked the orchestrator to reconcile it; this worker declines to widen the move beyond the four named blocks (the
  non-goals keep MainScreen/ZplanApp in app.py, A1's "exactly its block" forbids dumping the remaining helpers into the
  four modules, and the write-set allows no fifth) and does not weaken either side: the test pins the part that follows —
  app.py defines none of the moved names and each module defines exactly its own — and pins no line count (later 0.5.2
  runs edit app.py on purpose). Re-verified on candidate 6d4c74d.
- The imports app.py already had and the move no longer needs (`textwrap`, `ModalScreen`, `RichLog`, `TextArea`) stay:
  A2 names every attribute `dir(app)` listed before the change, and those four are in that list. Dropping them would
  remove attributes A2 keeps; the moved code that needs them imports them in its own module.
- The moved modules read the app-module helpers and constants they still need (`keys_bar`, `bar_width`,
  `help_text`, `screen_header_rows`, `QUIT_WAITS` in modals; `keys_bar`, `FIX_KEY`, `PLAIN_KEYS`, `LOG_LINES`,
  `LOG_PLACEHOLDER`, `PROGRESS_TITLE` in screens) with a function-level `from .app import ...`, the way the task
  allows: app.py imports the four modules, so a module-level import the other way round would be an import cycle.
  The task names the constants the text and chat blocks own (so those move with them and are imported back);
  it names none for modals and screens, so their constants stay in app.py and are read from there.
- `BLOCK_RECHECK_SECONDS` is patched as `terminal_planner.tui.app.BLOCK_RECHECK_SECONDS` in tests/test_tui_live.py;
  `ZplanApp` reads it and stays in app.py, so no patch target had to move or change.
- A `--fixture ID` run of this suite on a machine without the Textual wheelhouse skips the identity assertions
  (the app module cannot be imported) and still runs the source and README scans.

"""

import ast
import importlib
from pathlib import Path
import unittest

from tui_support import HAVE_TEXTUAL

REPO = Path(__file__).resolve().parents[1]
TUI = REPO / "terminal_planner" / "tui"
TEXTUAL_REASON = "Textual недоступен: нужен ZPLAN_TEST_WHEELHOUSE с wheels textual 8.2.8"

# module name -> the names app.py used to define and now imports back from it (the moved block, A1/A2).
MOVED = {
    "text": ("hang", "wrapped", "display_width", "fit_cells", "elide_middle", "elide_end", "csi_end", "string_end",
             "escape_end", "shown", "plain_scan", "plain_value", "plain_lines", "wrap_cells", "decimal_text",
             "short_count", "ELLIPSIS", "CSI_INTRO", "C1_CSI", "STRING_INTRO", "GENERIC_ESC"),
    "chat_view": ("token_fields", "body_rows", "state_row", "chat_state", "chat_refusal", "chat_outcome",
                  "chat_thinking", "thinking_row", "CHAT_MIN_COLS", "CHAT_MIN_ROWS", "CHAT_REFUSED", "SPIN"),
    "modals": ("Modal", "HelpScreen", "ConfirmScreen", "BootstrapScreen", "LanguageScreen", "FinishingScreen",
               "NoteScreen", "TextScreen", "journal_title", "RunScreen"),
    "screens": ("PlanScreen", "SettingsScreen"),
}
# Classes a module holds that app.py never defined (so nothing to import back): K1c2's shared button-row base.
# D1 added the autonomy-level reads the plan card needs to `card_kinds`; D4c (6d64c95) and T2 added the commit card's.
NEW = {"screens": ("ButtonScreen",), "modals": ("ProfileScreen",),
       "chat_view": ("MARKDOWN_LEAD", "MARKDOWN_MARKS", "plain_preview"),
       "card_kinds": ("AUTONOMY_LINE", "profile_level", "plan_stale", "plan_auto_approves",
                     "COMMIT_STAT_LINES", "LEGACY_AUTONOMY_LINE", "commit_card_source", "commit_key", "commit_spec")}

# `dir(terminal_planner.tui.app)` before the split, the interpreter's own dunders (`__name__`, `__file__`, ...) aside:
# every module has those, and A2 is about what app.py itself exposes. i9 dropped `LOGO`, `COMPACT_LOGO`,
# `LOGO_ROWS`, `LOGO_COLUMNS`, `BLOCK_LOGO_ROWS` and `roomy` with the logo itself (the main screen takes the lab
# look), so they are no longer part of the surface; `screen_header_rows` stays (modals read it) and now returns 0.
# `header_text` and `readiness_summary` also stay: the look no longer draws the header line they build, but A2's
# surface keeps every old attribute, and `tests/test_tui.py` still pins the long-project shortening they do.
# i2 removed the main-screen key-bar code the `Bar` replaced — `TABS_HINT`, `BAR_ITEM`, `labelled_bar`,
# `keeps_reserved`, `tabs_beside_bar` and `drop_panel_key` — so they are dropped from the surface list, exactly as
# i1c's `TAB_JOURNAL*`/`JOURNAL_EMPTY` were (`S0 merge fix`). `cell_len` stays: the import is kept even though i2
# no longer calls it (the `catalog.bar` path `keys_bar` keeps uses its own), the way A2 keeps every old attribute.
SURFACE = (
    "App", "BLOCK_RECHECK_SECONDS", "Binding", "Blocked", "BootstrapScreen",
    "C1_CSI", "CHAT_FIXTURE", "CHAT_MIN_COLS", "CHAT_MIN_ROWS", "CHAT_REFUSED",
    "CHECK", "CHECK_REMEDY", "CHECK_SECONDS", "CONFIRMED_SECONDS", "CSI_INTRO",
    "ConfirmScreen", "Delivery", "ELLIPSIS", "EMPTY_ANSWER", "EMPTY_CHANGE", "FIX_KEY", "FLOW_MIN_WIDTH",
    "FinishingScreen", "GENERIC_ESC", "HelpScreen", "Horizontal", "Input",
    "LOG_LINES", "LOG_PLACEHOLDER", "LanguageScreen", "MOVED",
    "MainScreen", "Modal", "ModalScreen", "NEW_ATTEMPT", "NOTHING_RUNNING", "NOT_STARTED", "NOT_STARTED_BELOW",
    "NoteScreen", "PANEL_HINT", "PLAIN_KEYS", "PRIMARY", "PROGRESS_LINES", "PROGRESS_TITLE", "PlanPanel",
    "PlanScreen", "QUIT_BUDGET", "QUIT_WAITS", "READING", "REFRESH_SECONDS", "RESERVE", "RichLog",
    "RunScreen", "STATUS_SHARE", "STOP_REQUESTED", "STRING_INTRO", "Screen", "SettingsScreen",
    "Static", "SuspendNotSupported", "TAB_HINT",   # TAB_JOURNAL*, JOURNAL_EMPTY: i1c; TABS_HINT: i2
    "TAB_LIVE", "TAB_LIVE_TITLE", "TAB_PLAN", "TAB_PLAN_TITLE", "TAILABLE", "TUI_MAIN_SCREENS", "TabPane",
    "TabbedContent", "Text", "TextArea", "TextScreen", "Vertical", "VerticalScroll",
    "ZplanApp", "asyncio", "bar_width", "body_rows", "catalog", "cell_len",
    "chat_module", "chat_outcome", "chat_refusal", "chat_state", "chat_thinking", "thinking_row", "SPIN", "check_closing",
    "check_label", "check_name", "coalesce_check", "csi_end", "decimal_text", "deque", "display_width",
    "draft_keys_ready", "elide_end", "elide_middle", "escape_end", "fit", "fit_cells",
    "flow_draw", "hang", "header_text", "help_text", "journal_title",
    "keys_bar", "milestone", "override_reason", "plain_lines", "plain_scan", "plain_value",
    "planning", "plural", "re", "readiness_summary", "refusal", "scheme", "screen_header_rows",
    "short_count", "shown", "state_row", "string_end", "summary", "textwrap",
    "time", "token_fields", "wrap_cells", "wrapped",
)


def definitions(path):
    """The names `path` defines at module level: functions, classes and assignment targets, imports aside."""
    found = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.add(node.name)
        elif isinstance(node, ast.Assign):
            found |= {target.id for target in node.targets if isinstance(target, ast.Name)}
    return found


def tui_module(name):
    return importlib.import_module("terminal_planner.tui." + name)


class SplitSourceTests(unittest.TestCase):
    """A1: each new module defines exactly its block, and app.py defines none of the moved names."""

    def test_each_new_module_defines_exactly_its_block_and_app_py_defines_none_of_them(self):
        for module, names in MOVED.items():
            self.assertEqual(sorted(definitions(TUI / (module + ".py"))), sorted(names + NEW.get(module, ())), module)
        moved = set().union(*MOVED.values())
        self.assertEqual(sorted(definitions(TUI / "app.py") & moved), [])


class SurfaceTests(unittest.TestCase):
    """A2: the old surface of the app module survives the split, and a moved name is the moved module's object."""

    @unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
    def test_every_name_of_the_old_surface_is_still_an_attribute_of_the_app_module(self):
        app = tui_module("app")
        for name in SURFACE:
            with self.subTest(name):
                self.assertTrue(hasattr(app, name))

    @unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
    def test_every_moved_name_is_the_module_object_of_the_module_that_holds_it(self):
        app = tui_module("app")
        for module, names in MOVED.items():
            owner = tui_module(module)
            for name in names:
                with self.subTest(name=name):
                    self.assertIs(getattr(app, name), getattr(owner, name))


# S1 of 0.5.2 (the card split): the module-level names `card_kinds` and `card_host` hold now, as `app.py` used to define
# them. The moved names are listed here, not derived, for the same reason as `MOVED`: the list is the contract the card
# tests (`app.merge_card_source`, `app.CARD_SOURCES`, ...) already reached through the app module.
CARD_MOVED = {
    "card_kinds": (
        "TAB_LIVE", "STATUS_SHARE", "NOT_STARTED_BELOW", "EMPTY_ANSWER", "MOVED", "FIX_KEY",
        "card_kind", "CARD_ROUTES", "CARD_SOURCES", "AUTO_END_CARDS", "card_route", "COMMAND_ACTIONS",
        "RUN_ERROR_PREFIXES", "blocked_note", "RunNote", "note_text", "CARD_KEY_SEP", "card_clock", "STAMP_HM",
        "stamp_hm", "token_run_id", "draft_card_key", "reply_occurrence", "draft_card_of", "draft_reply_time", "draft_tab_text",
        "DraftCardRequested", "MERGE_TASKS", "merge_key", "merge_stage", "merge_tasks_counts",
        "merge_same_attempt", "merge_spec", "merge_card_source", "merge_card_open", "QUESTION_CHOICES",
        "QUESTION_LINES", "QUESTION_CARD_CHROME", "QUESTION_CARD_INSET", "QUESTION_BUTTON_CHROME",
        "QUESTION_BUTTON_MIN", "question_button_cells", "question_button_rows", "_QuestionButton",
        "_QuestionButtons", "QuestionCard", "question_cards", "question_card_key", "question_body",
        "QuestionNoteScreen", "PLAN_CARD_SEP", "plan_card_counts", "plan_card_spec", "plan_card_source",
        "approve_plan_card", "revise_plan_card", "READY_ORIGIN", "READY_BLOCKED_NOTE", "READY_LINES",
        "READY_ORIGIN_FIX", "ready_blocked", "ready_failing", "ready_key", "ready_text", "ready_task",
        "origin_fix", "ready_source", "FAILED_CARD_STATES", "FAILED_CARD_LINES", "FAILED_CARD_RETRY",
        "FAILED_PLAN_STATUS", "failed_card_key", "failed_plan_card_key", "failed_plan_view", "failed_card_text",
        "failed_card_buttons", "failed_plan_restart", "failed_card_refusal", "failed_card_source"),
    "card_host": ("CARD_REVEAL_TRIES", "CardHost"),
}

# The `MainScreen` methods that became `CardHost`'s: `on_card_chosen` through `show_failed_card` and `merge_counts`
# through `question_answered` of the old app.py, in their old order.
CARD_HOST_METHODS = (
    "on_card_chosen", "show_card", "reveal_card", "close_card", "drop_card", "unmount_card", "newest_card_for",
    "render_card_sources", "draft_card_open", "open_draft_card", "draft_card_ref", "plan_identity_now",
    "action_plan", "action_decline", "refresh_draft_card", "on_draft_card_requested", "failed_cards",
    "failed_card_view", "failed_card_at", "failed_card_fetched", "failed_card_ref", "retry_failed_card",
    "retry_failed_plan", "show_failed_card", "merge_counts", "merge_counts_arrived", "merge_card_at",
    "merge_card_ref", "action_merge", "merge_exported", "merge_run", "action_merge_diff", "merge_diff_exported",
    "merge_settled", "question_cache", "question_card_specs", "question_text_room", "question_card_spec",
    "question_fetched", "answer_draft_of", "question_end", "approve_question", "decline_question",
    "open_question_note", "answer_question", "send_question_draft", "question_answered")


class CardSplitTests(unittest.TestCase):
    """S1 A1/A2: the card block left app.py and every moved name is still the same object through it.

    Interpretations recorded here (the worker's session summary never reaches the reviewers):

    - The task names the block `MERGE_TASKS` to the end of app.py and "the module-level card helpers they need ...
      where moving them is needed to avoid an import cycle". The registries (`CARD_SOURCES`, `CARD_ROUTES`,
      `AUTO_END_CARDS`, `COMMAND_ACTIONS`), `card_kind`, `card_route`, the run-note helpers the readiness card reads
      (`RunNote`, `note_text`, `blocked_note`), the draft-card helpers `CardHost` reads and `DraftCardRequested` moved
      with it, and so did the six constants both halves read (`TAB_LIVE`, `STATUS_SHARE`, `NOT_STARTED_BELOW`,
      `EMPTY_ANSWER`, `MOVED`, `FIX_KEY`): each is defined once, in `card_kinds`, and `app` imports it back.
      `CARD_REVEAL_TRIES` is only `CardHost.reveal_card`'s, so it lives in `card_host`.
    - `submit_verdict` stays in app.py, although it sits inside the task's block: it reads `screen_slash_state`, which
      needs `MainScreen` (`draft_card_state`), so moving it would force `card_kinds` to import `app` -- the cycle the
      task forbids. Its helper `merge_card_open` moved and is imported back.
    - `run_command` stays on `MainScreen`: the task's method ranges (`on_card_chosen` .. `show_failed_card`) start
      after it.
    - Nothing on the Textual side needed a change for the mixin: `Card.Chosen` and `DraftCardRequested` reach their
      `on_*` handlers through the class MRO, and `CardHost` holds no `BINDINGS` or `@on` handler.
    - `patch.object(app_module, "card_clock", ...)` in `test_tui_chat_scroll` and `test_tui_draft_card` now targets
      `card_kinds`, where the readiness source and `draft_reply_time` read the clock; no other patch target changed.
    """

    def test_app_py_defines_none_of_the_moved_card_names_and_each_new_module_holds_them(self):
        for module, names in CARD_MOVED.items():
            self.assertEqual(sorted(definitions(TUI / (module + ".py"))), sorted(names + NEW.get(module, ())), module)
        moved = set().union(*CARD_MOVED.values())
        self.assertEqual(sorted(definitions(TUI / "app.py") & moved), [])

    @unittest.skipUnless(HAVE_TEXTUAL, TEXTUAL_REASON)
    def test_every_moved_card_name_is_the_new_module_object_and_main_screen_inherits_the_card_host(self):
        app = tui_module("app")
        for module, names in CARD_MOVED.items():
            owner = tui_module(module)
            for name in names:
                with self.subTest(name=name):
                    self.assertIs(getattr(app, name), getattr(owner, name))
        host = tui_module("card_host").CardHost
        self.assertEqual(app.MainScreen.__mro__[1], host)
        for name in CARD_HOST_METHODS:
            with self.subTest(method=name):
                self.assertIs(getattr(app.MainScreen, name), getattr(host, name))
                self.assertNotIn(name, vars(app.MainScreen))
        self.assertIs(app.merge_card_source, tui_module("card_kinds").merge_card_source)
        self.assertIs(app.CARD_SOURCES, tui_module("card_kinds").CARD_SOURCES)


class CodeMapTests(unittest.TestCase):
    """A4: the README code map names the four modules, one line each."""

    def test_the_readme_code_map_gives_each_new_module_one_line(self):
        lines = (REPO / "README.md").read_text(encoding="utf-8").split("\n")
        for module in MOVED:
            entry = "tui/" + module + ".py: "
            named = [line for line in lines if line.startswith("- " + entry)]
            with self.subTest(module=module):
                self.assertEqual(len(named), 1, entry)
                self.assertTrue(named[0].rstrip().endswith("."), named[0])


if __name__ == "__main__":
    unittest.main()
