RS4 — architect token counter counts each token once

Cost analysis 2026-10-26 (C0 input; re-smoke 2026-10-25b session, codex-cli 0.162.1): on `codex exec resume`,
`turn.completed.usage` is the thread's running total, not the turn's. zplan adds it every turn: architect.py:624-626
into the turn result, architect.py:1096-1097 into `session["usage"]`. The 11 turns' reports were 77,699 ... 1,052,821
input tokens (monotonic); the session file summed them to 5,842,903 (5.55x). The header shows the inflated number and
`session_long` (tui/chat.py:415, ROT_TOKENS 2,000,000) asked for `/new` at turn 7 on a real 603k.

Write-set: terminal_planner/architect.py, tests/test_architect.py.

Acceptance criteria:
- C1 After a completed turn, `session["usage"]` equals the thread total Codex last reported (each key), not a sum
  over turns. Example: turn 1 reports input 100, turn 2 (resumed) reports input 250 -> session input 250.
- C2 The transcript's architect row for a turn carries that turn's own usage: the reported total minus the session
  total before the turn, per key, never negative. Example: the turns above -> rows with input 100, then 150.
- C3 A new thread (no saved thread id: the first turn, or after `reset()` (architect.py:822, used by `/new`)
  forgot it) counts from zero; `session["turns"]` is untouched. Example: session input 250, `reset()`, then a turn
  reporting input 40 -> session input 40, row input 40.
- C4 Within one exec, several `turn.completed` events: the last report is the total (not their sum). The
  `usage` event emitted to the UI and `session["turns"]` keep their meaning. Example: reports {input 7, output 3}
  then {input 9, output 4} -> result total {input 9, output 4}.
- C5 A failed or cancelled turn changes nothing in the session usage (as today); the next completed turn's total
  covers it. Example: turn 2 fails, turn 3 reports input 400 -> session input 400.

Non-goals (reviewers must not require): ROT_TOKENS/ROT_TURNS and the rot metric (0.6.1 C1); tui/chat.py;
journal.py's run token counts; migration of existing session files (the next completed turn replaces their total).

A test outside the write-set asserting a summed usage -> `conflict:`.

Risk: medium. DoD: `python3.13 devtools/fasttest.py` tests.test_architect, tests.test_new_session,
tests.test_tui_chat: exit 0.
