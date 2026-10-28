review-timeout — milestone nodes that gather fresh evidence by running the checks get the worker's time budget.

Goal: a milestone attempt must not fail only because a reviewer re-ran a slow check. Measured 2026-10-22 on a dogfood run of this repository (task: extend `zplan --version`): the worker finished in 26 min, then `acceptance_review` re-ran the task's checks (tests including test_install) as its body tells it to ("Gather fresh evidence yourself (run the checks)") and the engine stopped it: `Node acceptance_review failed: timeout after 1200.0s` -> `Run failed: acceptance_review_failed`, round 1 of 3, no verdict. Today every node except worker/repair/empty_repair gets CONTROL_TIMEOUT (20 min, terminal_planner/milestone.py:38), the three writers get WORKER_TIMEOUT (45 min).

Data reach: `milestone_graph` in terminal_planner/milestone.py: `executable(..., timeout=CONTROL_TIMEOUT)` (line ~337), `verifier(...)` (line ~346) calls `executable` without a timeout; the nodes are built at lines ~376 (final_verify), ~378 (final_reverify), ~437 (acceptance_review), ~442 (code_review). Test: tests/test_milestone.py `test_executable_contracts_and_runtime` (line ~555) asserts the per-node timeout.

Write-set: terminal_planner/milestone.py, tests/test_milestone.py.

Acceptance criteria:
- A1 acceptance_review, code_review, final_verify and final_reverify get timeoutMs = WORKER_TIMEOUT; `verifier` takes an optional `timeout` (default CONTROL_TIMEOUT) passed to `executable`. All other nodes keep their current timeout; attempts stay 1.
- A2 test_executable_contracts_and_runtime asserts the new set of long nodes (worker, repair, empty_repair, acceptance_review, code_review, final_verify, final_reverify -> 45 min; all others 20 min), so it fails if any of the four reviewers is back at 20 min.

Non-goals (reviewers must not require): retrying a timed-out node, changing reviewer instructions, failure-cause wording in the UI, the planner graph, any timeout value other than the two existing constants.

Testing: while editing run only the test you change; run the DoD command once at the end.

DoD: `python3.13 -m unittest tests.test_milestone tests.test_toolchain tests.test_reference` with TMPDIR short (see preamble), all green.
