fault-cause-words — an ended milestone says in words which step failed, not only the engine reason code.

Goal: fault case "the run ended with an engine failure" shows a cause the owner understands plus the next key (docs/CHAT_RELEASE_JTBD.md, fault cases). Measured 2026-10-22 on a dogfood run: the reviewer hit the engine timeout and the screen said only `Причина: «acceptance_review_failed»` (then "[g] продолжит ту же попытку"). The engine's terminal reason for a failed node is `<node>_failed`, stored as the record's diagnostic.

Data reach: `Delivery.reason(r)` (terminal_planner/delivery.py:878) builds the line from `r["diagnostic"]`; callers at delivery.py:945-956. Role words: `live.ROLES` (terminal_planner/live.py: node name -> Russian word, e.g. acceptance_review -> "приёмка", code_review -> "ревью кода"); `live.base(node)` strips a node prefix.

Write-set: terminal_planner/delivery.py (`reason` only), tests/test_run_cause.py.

Acceptance criteria:
- A1 When the diagnostic text is exactly `<node>_failed` and `live.base(<node>)` is a key of `live.ROLES`, the line reads `  Причина: этап «<role word>» не дал ответа (таймаут, сбой или неверный ответ) — <diagnostic>` (the code kept at the end, unquoted).
- A2 Any other diagnostic (including `review_failed`, free text, empty) is shown exactly as today, byte for byte; existing assertions on «review_failed» stay unchanged.
- A3 Tests: acceptance_review_failed and code_review_failed give the new line; an unknown `foo_failed` and free text are unchanged; the new test fails if `reason` is reverted.

Non-goals (reviewers must not require): reading engine logs, distinguishing timeout from crash, changing the next-key lines, the planner, any store change.

Testing: while editing run only the test you change; run the DoD command once at the end.

DoD: `python3.13 -m unittest tests.test_run_cause tests.test_live tests.test_toolchain tests.test_reference` with TMPDIR short (see preamble), all green.
