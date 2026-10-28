H3 — agents verify in proportion to the change, the project's own way, instead of always "with tests"

Our own repo has 1.84x test code over product code. The worker text every user gets says "smallest coherent change
in the project's style, with tests" (milestone.py worker) and the architect's method says "Done = the task's new
and changed tests pass" (terminal_planner/resources/architect_method.md:24). Astra review 2026-10-28 (pause dir,
critic/harness-graph.out, item 1): a prompt-layer fix; requested tests, including a project's first, stay.

Reuse: the REVIEW_BAR / CONFLICT_BAR pattern in milestone.py (one shared constant; tests assert the sentence).

Write-set: terminal_planner/milestone.py, terminal_planner/engine.py, terminal_planner/resources/architect_method.md,
tests/test_milestone.py, tests/test_plan_gate.py, tests/test_architect.py, tests/test_task_gate.py.

Acceptance criteria:
- P1 One constant states the rule: verify each change the project's own way and in proportion to it. In a project
  with a test setup, a behaviour change (a new feature included) gets a relevant test; tests the task asks for (a
  first test included) are written; no test is added merely because docs, copy or config files changed.
  Example: a typo fix in README -> run the existing checks, no new test; a config value that changes
  behaviour -> a regression check for it; a task asking for the project's first test -> that test is written.
- P2 The milestone worker and repair texts use the constant; "with tests" appears in no model-bound text.
  Example: no node of `milestone_graph(2)` has "with tests" in its instructions.
- P3 The planner asks for a `dod` that proves the task the project's own way (its existing checks, or a command or
  file check for a non-code change); the architect's "Done" line says the task's DoD passes, not "new and changed
  tests". Example: `dod` stays a nonempty string; architect_method.md has no "new and changed tests".
- P4 The final check's `incomplete` text no longer lists "a failed command": a check that runs and fails is
  `rejected`. Example: milestone.py final instructions have no "a failed command"; a missing tool stays.

Non-goals (reviewers must not require): graph shape; the review bars; removing tests from this repository; test
counts.

Conflict rule: if a test outside the write-set pins the old worker, planner or architect wording, change nothing
and end with `conflict: <file:line>`.

Risk: medium (prompt text every user runs; no graph shape change). DoD: run once, at the end: `python3.13
devtools/fasttest.py tests.test_milestone tests.test_plan_gate tests.test_architect tests.test_task_gate
tests.test_toolchain`: exit 0; `python3 devtools/budget.py`: OK. Each new test fails with the old text it guards
restored.
