R-B — medium defects from the 0.5.2 bug hunt (2026-10-24): status after reopen, user stop, raw commands, 80x24 chat.

Why: dogfood on 9afd63e (findings 4, 7-10); R-A merged ab76ece. `slash_state` (app.py:447) returns "draft" before running /
merge / error, so with a draft card or retained goal text the bar says «работы нет» and the `#right` title stays
«Черновик цели · ещё не отправлен» (`canvas_title` app.py:524). A user `/stop` lands in the error sets (app.py:452,
:497, card_kinds.py:680) and `Delivery.reason` prints «force_stopped» (delivery.py:895). The scheme node and the
activity subtitle show `/bin/zsh -lc 'PATH="/Users/…'` (scheme.py:561, activity.py:176). At 80x24 the chat opens
at the top (`chat_go_end` spent before layout, app.py:1262) and PgUp/PgDn act only with the pane focused (app.py:192).

Reuse: plan-stop wording «остановлен вами» (delivery.py:41); `scroll_chat` (app.py:1849); `scrub` in live.py.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/activity.py, terminal_planner/tui/scheme.py,
terminal_planner/tui/card_kinds.py, terminal_planner/tui/strings.py, terminal_planner/delivery.py,
tests/test_tui_rb_fixes.py (new), tests/test_tui_chat_scroll.py, tests/test_tui_chat.py, tests/test_tui_look.py,
tests/test_run_cause.py, tests/test_tui_milestones.py, tests/test_tui_planning.py, tests/test_tui_language.py,
tests/test_tui_scheme.py, tests/test_tui_activity.py, tests/test_tui_activity_pane.py, tests/test_tui_strings.py,
tests/test_tui_split.py.

Acceptance criteria:
- C1 Planning, a running row, a question, a merge wait and an error outrank "draft" in `slash_state`; draft wins only
  when nothing else is active. Example: draft card open + M1 running -> bar names the M1 job, title not «Черновик цели».
- C2 A milestone stopped by the owner reads as a stop, not an error: bar «M1 остановлен вами», the card reason
  «остановлен вами» (never «force_stopped»), neutral card style; the slash state stays error, so `/run` still offers a new attempt.
- C3 The TUI shows a command by its program name: `/bin/zsh -lc 'PATH="/Users/user/bin:$PATH" pytest -q'` -> `pytest`;
  no absolute local path in the scheme node or the activity subtitle. The stored `live.command.text` and the CLI
  `zplan` line (live.py:350) are unchanged.
- C4 At 80x24 the chat opens at its newest message; PgUp/PgDn with focus in the input scroll the chat.
- C5 One test per criterion in tests/test_tui_rb_fixes.py, each failing on the unfixed code.

Non-goals (reviewers must not require): a new slash state; plan-stop wording; persisting card decisions; second-terminal lock text;
Russian-layout keys; live.py; runs.py records.

Risk: medium (TUI state order + wording). DoD: `python3.13 devtools/fasttest.py tests.test_tui_rb_fixes
tests.test_tui_chat_scroll tests.test_tui_look tests.test_run_cause tests.test_tui_milestones tests.test_toolchain`
exit 0; quote the `fasttest:` lines.
