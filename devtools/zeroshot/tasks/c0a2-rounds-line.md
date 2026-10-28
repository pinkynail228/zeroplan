C0a2 — the profile summary stops calling task rounds "for later stages" (follow-up of c0a-review-bar, merged f6c1db0).

Goal: since f6c1db0 `limits.task_rounds` bounds the milestone review loop (docs/REFERENCE.md limits row), but the profile summary still prints "раунды: план N; задачи N, слияние N (для следующих этапов)" (terminal_planner/process.py:772-773), which tells the owner task rounds do nothing.

Write-set: terminal_planner/process.py (that summary line only), docs/USER_FLOW.md only if it quotes the line, their tests.

Acceptance criteria:
- A1 The summary shows the task rounds as in effect, with the source marker the plan rounds already use (`where("limits.task_rounds")`), e.g. "раунды: план 3 [..]; повторы задачи 2 [..]; слияние 2 (для следующих этапов)"; merge rounds keep "для следующих этапов".
- A2 One test asserts the new line for the repository profile and for the preset default.

Non-goals: any other summary line, the gates lines, REFERENCE.md.

Testing: while editing run only the test you change; run the DoD command once at the end.

DoD: `python3.13 -m unittest tests.test_process tests.test_toolchain tests.test_reference` with TMPDIR short (see preamble), all green.
