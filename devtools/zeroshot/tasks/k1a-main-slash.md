K1a — the main screen has no letter keys; its actions are `/` commands (plan section K1)

Owner: no letter keys; arrows, Enter, Esc, Tab, PgUp/PgDn, Ctrl+C/Ctrl+Q stay. This run: the main screen only
(PlanPanel BINDINGS tui/app.py:551-558, MainScreen :572-589). `n`, `c`, the goal form: K1b; screens, modals: K1c.

State: attempt 2 timed out; its edits stay in the tree, 8 tests fail (test_reference, test_tui_live,
test_tui_milestones, test_tui_ready_card). Finish them; no restart.

Reuse: the keys' own actions; slash.py `COMMANDS`; `COMMAND_ACTIONS`, `card_route`; catalog.py `_a`,
`--write docs/REFERENCE.md`.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/slash.py, terminal_planner/tui/card_kinds.py, terminal_planner/tui/strings.py, terminal_planner/catalog.py, docs/REFERENCE.md, tests/test_tui_slash.py, tests/test_tui_polish.py, tests/test_reference.py, tests/test_tui_milestones.py, tests/test_tui_live.py, tests/test_tui_chat.py, tests/test_tui_planning.py, tests/test_tui.py, tests/test_tui_narrow.py, tests/test_tui_plan_gate.py, tests/test_tui_commands.py, tests/test_tui_look.py, tests/test_tui_run_command.py, tests/test_process.py, tests/test_tui_ready_card.py, tests/test_tui_approve_card.py, tests/test_tui_merge_card.py, tests/test_tui_chat_scroll.py, tests/test_tui_reopen_fixes.py, tests/test_warn_contract.py, tests/test_tui_activity_pane.py, tests/test_fixture_scope.py.

Acceptance criteria:
- C1 No letters: the main screen binds no single letter, `?`, Ctrl+S, Ctrl+R or F1 (except `n`, `c`). Example:
  plan panel focused, M1 ready, press `g` -> nothing starts; type `/run` -> M1 starts.
- C2 New commands do what the keys did: `/view` = `p` (opens the plan screen; `/approve` stays a decision),
  `/attempt` = `o` then `w` (opens the selected milestone's attempt in any state and resumes an interrupted
  observation), `/log` = `e`, `/answer` = `t`, typed `/details` = `i` when no error card owns it (card routing as
  today). Example: M1 running -> `/attempt` -> its
  attempt opens; `/log` -> the log tail.
- C3 Hints name commands: every main-screen hint, note and «Дальше:» text that named a removed key names the
  command. Example: `[w] наблюдать, [g] на нём` (app.py:2729) -> `/attempt`, `/run`.
- C4 Key bars: catalog tui_panel/tui_input entries name commands; REFERENCE.md regenerated; the catalog/bindings
  cross-check (test_tui_polish.py:635 area) follows. Example: the panel bar shows `/run`, not `g`.

Tests: a removed key's press becomes the typed command; tests of a dropped key (`r`, Ctrl+S/R, F1) go.

Non-goals (reviewers must not require): `n`, `c`, `/plan`, the goal form; letters inside screens and modals; the plain CLI's letter menus (cli.py, test_reference.py:246);
setup.py/delivery.py/planning.py texts.

Conflict rule: a test outside the write-set pressing a removed main-screen key -> `conflict:` path:line.

Risk: medium. DoD: `python3.13 devtools/fasttest.py` with the changed test modules plus
tests.test_reference tests.test_toolchain, exit 0; quote `fasttest:` lines.
