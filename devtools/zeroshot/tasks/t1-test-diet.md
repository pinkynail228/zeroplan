T1 — test diet: cut the slow combinatorial matrices to one case per code branch (owner 2026-10-25: no
over-testing; per-test timing 2026-10-25: 13 tests take ~300 s of the suite, most of it "every state x every
outcome" loops from 2026-10-19).

Tests only. No product code changes; no test is added.

Write-set: tests/test_lifecycle_guard.py, tests/test_terminal_planner.py, tests/test_run_cause.py.

Targets (measured seconds):
- test_lifecycle_guard BeginGuardTests :385-540: plan_creating_actions...every_terminal_outcome 39 s,
  approve_and_override...every_terminal_outcome 38 s, approve_and_override_are_refused 26 s, steward_revise 17 s,
  direct_authority_begin 9 s.
- test_terminal_planner NativeTests: invalid_watch_suffix :733 31 s, first_terminal_survives :809 25 s,
  malformed_observations :1118 18 s, nonterminal_deadline :676 17 s.
- test_run_cause: the A-4 generators :1227 and :1392 (200 seeded cases each, 29 s), excerpts 20 s,
  unusable_reset :991 18 s, the valid reset 10 s.

Acceptance criteria:
- C1 One case per branch: each target loop keeps one case per distinct branch of the code under test (read the
  guard/projection code to find the branches) and drops the rest. Example: a guard that refuses every active state
  through one `status in ACTIVE` check keeps one active state plus one terminal outcome, not all of them; a guard
  with a separate branch per state keeps each such state. Each trimmed test gets a one-line comment naming the
  branches it keeps.
- C2 Generators: the A-4 generators run 20 cases (same seed), and their `seen` assertion (every cause class
  occurs) still holds; if 20 cases miss a class, take the smallest count that covers every class. Example:
  `range(200)` -> `range(20)`, `seen == set(CLASSES)` still passes.
- C3 Still guarding: for every trimmed test, break the code branch it guards (revert it locally, do not commit)
  and show that the trimmed test fails. Quote one line per test in the report: test name, the broken line, FAIL.
  Example: `lifecycle_guard.py:120 status in ACTIVE -> False`: approve_and_override_are_refused FAIL.
- C4 Time: report the per-test time before and after for each target (python3.13 -m unittest -v with
  timings, or fasttest output); the total for the targets is at most 60 s. Example: "plan_creating_actions 39 s -> 3 s".

Non-goals (reviewers must not require): new tests, refactoring the fixtures, other slow tests, tests in other
files.

Risk: low (tests only; C3 shows each kept case still fails on the bug it guards). DoD: `python3.13
devtools/fasttest.py tests.test_lifecycle_guard tests.test_terminal_planner tests.test_run_cause
tests.test_toolchain` exit 0; quote the `fasttest:` lines.
