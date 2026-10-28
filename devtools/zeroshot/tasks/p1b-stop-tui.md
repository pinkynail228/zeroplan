P1b — `/stop` stops a running planner from the TUI (0.6.0, docs/RELEASE_0.6.0_PLAN.md row p1b; incident U12/U17:
a running planner could only be force-stopped by hand).

Already there (reuse, do not rewrite): `planning.Planning.stop()` (planning.py:395: saves the request, force-stops
the native run once, raises Blocked on refusal) and `stopped()` (the cause line «План rN остановлен вами в HH:MM.»);
the line UI's `stop_planner` (cli.py:562); the TUI's milestone stop `/stop` -> `stop_running_row` ->
`action_stop_milestone` with a ConfirmScreen and `controller.stop_run` (controller.py:782, a `_job`); the
failed/stopped plan card (card_kinds.py ~737) with its restart button.

Write-set: terminal_planner/tui/slash.py, terminal_planner/tui/controller.py, terminal_planner/tui/card_host.py, terminal_planner/tui/card_kinds.py (the stopped-plan card kind; attempt 2, 2026-10-24: attempt 1 stopped on a write-set conflict),
terminal_planner/tui/app.py, terminal_planner/tui/strings.py, terminal_planner/catalog.py (the `/stop` row only),
tests/test_tui_stop_planning.py (new), tests/test_tui_slash.py.

Acceptance criteria:
- S1 `/stop` is offered while the planner runs (slash state `planning`) as well as `running`. In `planning` it asks
  once: a ConfirmScreen naming the revision, e.g. «Остановить планирование плана r2?» (EN/ZH same key); «нет»/esc
  changes nothing.
- S2 «да» stops through a controller job (never on the UI thread), which calls `Planning.stop()` exactly once.
  Example (fixture planner run of r2, fake engine counting `force_stop`): `/stop`, «да» -> force_stop calls == 1;
  after the terminal observation the chat shows the stopped-plan card «План r2 остановлен вами в HH:MM.» with its
  restart button, and the bar no longer reads planning.
- S3 A refusal (Blocked from `stop()`) shows one chat line «Не выполнено: <reason>», the state stays `planning`,
  and a second `/stop` asks again.
- S4 While a milestone runs, `/stop` behaves exactly as today (the existing milestone stop tests pass unchanged).

Non-goals (reviewers must not require): restart flow changes, the planner scheme or timers (p2b), stopping from the
plan screen with a letter key, the `--plain` UI, new persistence.

Risk: medium (process lifecycle reached from the UI; the stop contract itself is p1a's, unchanged). DoD:
`python3.13 devtools/fasttest.py tests.test_tui_stop_planning tests.test_tui_slash tests.test_tui tests.test_tui_live
tests.test_plan_stop tests.test_tui_planning` exit 0; quote the `fasttest:` lines.
