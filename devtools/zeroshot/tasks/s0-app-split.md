S0 — split terminal_planner/tui/app.py into modules, no behaviour change (0.5.2, docs/RELEASE_0.5.2_PLAN.md).

Why: app.py is 3357 lines and every 0.5.2 integration run edits it, so the runs cannot go in parallel and each worker
re-reads the whole file. After this run the chat, the canvas and the modal screens live in their own modules, so
later runs on different parts touch different files.

Change: a pure move. Cut each block below out of app.py into the named new module, unchanged except for the imports it
needs; app.py imports the moved names back so every name that `terminal_planner.tui.app` exposes today is still
importable from it and is the same object (`app.X is module.X`). No renames, no edits to logic, strings, CSS or keys.
- `terminal_planner/tui/text.py`: the pure text helpers from `hang` through `short_count` (app.py ~200-417:
  hang, wrapped, display_width, fit_cells, elide_middle, elide_end, csi_end, string_end, escape_end, shown, plain_scan,
  plain_value, plain_lines, wrap_cells, decimal_text, short_count) and the constants only they use.
- `terminal_planner/tui/chat_view.py`: the chat layout functions from `usage_row` through `chat_outcome` (~418-606) and
  the constants they own (CHAT_HEADER_ROWS, CHAT_MIN_COLS, CHAT_MIN_ROWS, CHAT_REFUSED, SCROLL_MARKER, ...).
- `terminal_planner/tui/modals.py`: Modal, HelpScreen, ConfirmScreen, BootstrapScreen, FinishingScreen, NoteScreen,
  TextScreen, journal_title, RunScreen (~727-1069).
- `terminal_planner/tui/screens.py`: GoalActions, GoalScreen, PlanScreen, SettingsScreen (~1630-1985).
MainScreen and ZplanApp stay in app.py. Module-level constants that a test patches by module path
(`patch("terminal_planner.tui.app.NAME", ...)`, e.g. BLOCK_RECHECK_SECONDS in tests/test_tui_live.py) must keep taking
effect: leave such a constant in app.py and have the moved code read it from there at call time, or move it and update
only that patch target in the test. No import cycles at import time (a moved module that needs app.py names imports
them inside the function or receives them; check `python3.13 -c "import terminal_planner.tui.app"`).

Write-set: terminal_planner/tui/app.py, the four new modules above, README.md (code map lines for terminal_planner/tui
only), tests/test_tui_live.py (patch targets only, if needed), tests/test_toolchain.py (only if it lists the TUI modules), tests/test_tui_split.py (new, A2).
Do not edit any other test, zplan.tcss, strings.py, catalog.py or any behaviour.

Acceptance criteria:
- A1 app.py no longer defines the moved blocks; each new module holds exactly its block; app.py is at most ~1900 lines.
- A2 Every name that `dir(terminal_planner.tui.app)` listed before the change (public and underscore) is still an
  attribute of the module and, for moved names, `is` the new module's object; one new test enumerates the moved names
  and asserts this.
- A3 The whole TUI test set is green unchanged (except allowed patch-target edits) — this is the behaviour proof.
- A4 README code map names the four modules in one line each.

Non-goals (reviewers must not require): moving MainScreen or ZplanApp methods, renaming, deduplicating, fixing bugs
seen while moving, new abstractions, tests for the moved functions beyond A2.

DoD: `python3.13 devtools/fasttest.py $(ls tests/test_tui*.py | sed 's#tests/#tests.#;s#\.py$##') tests.test_live
tests.test_layout tests.test_fixture_scope tests.test_toolchain tests.test_reference` with exit 0.
