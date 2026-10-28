I11 — `/run` starts the next milestone from the chat (0.5.2 release gate, D1/D4).

Why: in the TUI a milestone starts only with the plan pane's letter key `g` (`action_run_milestone`, app.py ~2593):
it needs Tab to the pane, does nothing with a Russian layout (D4), and since i10 the План tab no longer shows the
«Дальше: [g] запустить M1» hint (`plan_tab_line` drops letter-key lines).

Reuse, do not rewrite: `action_run_milestone` and its `g_action(row)` branches (check / preview+confirm / resume /
new attempt / busy note); `slash.COMMANDS` and `COMMAND_ACTIONS`; `plan_tab_line` and `PLAN_TAB_HINTS` (app.py).

Write-set: terminal_planner/tui/slash.py, terminal_planner/tui/app.py, terminal_planner/tui/strings.py,
terminal_planner/catalog.py (a `/run` row only, if needed), tests/test_tui_run_command.py
(new), tests/test_tui_slash.py, tests/test_tui_look.py (P3 hint expectations only), tests/test_tui_palette.py and
tests/test_tui_commands.py (the idle command lists, `IDLE_ROWS` :74 and :111, only), tests/test_tui_live.py,
tests/test_tui_milestones.py and tests/test_tui_planning.py (План tab hints only; attempt 2: attempt 1 stopped
on a write-set conflict, test_tui_live.py:426). Non-TUI tests and `--plain` keep «[g]». New tests import the app inside
the tests, not at module top (the tests.test_toolchain import scan runs without Textual or Rich).

Acceptance criteria:
- R1 `/run` is offered in `idle` and `error` and acts on the row the pane's `g` acts on (the selected row, else the
  first row whose `g_action` is not None), through the same branches. Example (fixture plan r1 approved, M1 ready,
  input focused, no Tab): type `/run`, Enter -> the same start confirmation `g` opens; «да» -> the driver gets one
  submission for M1.
- R2 Nothing to start gives one chat line «Не выполнено: <reason>», e.g. «Не выполнено: нет этапа, готового к
  запуску.»; a busy slot gives the existing busy note. No submission in either case.
- R3 The План tab names the command: «Дальше: [g] запустить M1» -> «Дальше: /run — запустить M1», «[g] новая попытка
  M1» -> «/run — новая попытка M1» (PLAN_TAB_HINTS or the same mapping); other letter-key lines still drop.
- R4 D4 smoke (one test, Russian layout): with the input focused the keys enter, `/`, esc, ←/→, ctrl+q work, and the
  approve -> run path is reachable with `/approve`, `/run` and Enter only (no letter key pressed).

Non-goals (reviewers must not require): removing or renaming pane letter keys, a run card, `/run M2` arguments,
the `--plain` UI, EN/ZH beyond same-key entries.

Risk: medium (starts native work from a new entry point; the start path itself is unchanged). DoD:
`python3.13 devtools/fasttest.py tests.test_tui_run_command tests.test_tui_slash tests.test_tui_look tests.test_tui
tests.test_tui_live tests.test_tui_milestones tests.test_tui_palette tests.test_tui_commands
tests.test_toolchain` exit 0; quote the `fasttest:` lines.
