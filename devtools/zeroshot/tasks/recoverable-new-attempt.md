recoverable-new-attempt — a resumable failed attempt also offers a new attempt.

Goal: the owner is never stuck on a resume that repeats the same failure. Measured 2026-10-22 in dogfood: attempt 1 of M1 failed with `Node acceptance_review failed: timeout after 1200.0s`; review-timeout (823a1fa) raised that budget for new graphs, but [g] "продолжить" resumes the same native submission (runs.py `resume`: "the successor keeps the original submission"), so the successor ran the frozen 20-min graph and failed the same way (run 01a161b3). The state `failed_recoverable` offers only resume and plan (delivery.py END_ACTIONS line ~100, catalog.py:520-522), while `failed` and `stopped` offer `new_attempt` ([t], `Runs.retry`, runs.py:1474: a fresh attempt from destination HEAD with the current graph).

Data reach: END_ACTIONS (terminal_planner/delivery.py ~95-104), catalog actions `_a("failed_recoverable", ...)` and `_a("failed", "new_attempt", "t", ...)` (terminal_planner/catalog.py ~520-526), `Delivery.new_attempt` (delivery.py ~1038), `next_step` (delivery.py ~440-460), the end-screen key handling in the TUI and --plain UIs that already serve `failed.new_attempt`, `Runs.retry` / `check_followup` (runs.py).

Write-set: terminal_planner/catalog.py, terminal_planner/delivery.py, terminal_planner/runs.py only if `check_followup` refuses a recoverable failed record, the TUI/plain end-screen dispatch only if it needs the new action id wired, docs/USER_FLOW.md (one line in the failed-attempt section), tests (test_run_cause, test_tui_milestones or the module that tests failed.new_attempt).

Acceptance criteria:
- A1 The `failed_recoverable` end screen offers, in this order: [g] продолжить (unchanged), [t] новая попытка («начать попытку с текущего HEAD», same wording as `failed.new_attempt`), [p] план, [q] назад. [t] starts a new attempt exactly like `failed.new_attempt` (same `Delivery.new_attempt` path, same confirmation if that one has one).
- A2 Home «Дальше:» for a failed_recoverable milestone reads «[g] продолжить <M> — та же попытка в её рабочем дереве; [o] открыть — новая попытка»; [g] on home still resumes.
- A3 After a new attempt from failed_recoverable, the old attempt is no longer resumable from home (the new attempt is the latest), and nothing about resume changes for records that never get [t].
- A4 Tests: [t] on a failed_recoverable record starts a new attempt (a new run submitted with the current graph, the driver's submit called once, resume not called); the end screen lists the four keys; the home line; existing resume tests unchanged. The new test fails if the catalog entry is removed.

Non-goals (reviewers must not require): changing resume semantics, automatic retry, detecting timeouts, the planner.

Testing: while editing run only the test you change; run the DoD command once at the end.

DoD: `python3.13 -m unittest tests.test_run_cause tests.test_runs tests.test_tui_milestones tests.test_ux tests.test_toolchain tests.test_reference` with TMPDIR short (see preamble), all green.
