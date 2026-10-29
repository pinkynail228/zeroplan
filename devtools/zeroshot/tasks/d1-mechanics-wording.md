D1 — DRIVER_MECHANICS says the final check retries and repairs, not "once per milestone"

Release critic rel081b, item 2: "a final milestone check once per milestone" (terminal_planner/engine.py:330)
understates the final phase: an incomplete final check runs once more (milestone.py:416-423, FINAL_ATTEMPTS = 2,
milestone.py:23), and a rejection gets bounded repairs and a re-check (FINAL_REPAIRS, milestone.py:22, 427-430). The planner and verifier read this sentence (engine.py:674, 691).

Reuse: DRIVER_MECHANICS as it is; the graph goldens and the comments above them, the way H5 updated them:
tests/test_task_gate.py:58-61 (BASE_GOLDEN), tests/test_plan_gate.py:28-33 (V1_GOLDEN); the wording test
tests/test_plan_gate.py:102-107; tests/test_ux.py:431.

Write-set: terminal_planner/engine.py, tests/test_task_gate.py, tests/test_plan_gate.py, tests/test_ux.py.

Acceptance criteria:
- W1 DRIVER_MECHANICS ends "..., and a final milestone check with bounded repairs and re-checks." in place of "a
  final milestone check once per milestone"; the wording test asserts the new tail. Example: the planner and
  verifier texts of a newly built graph contain "bounded repairs and re-checks" and not "once per milestone".
- W2 Only the new graph goldens change: the graph digests in BASE_GOLDEN and V1_GOLDEN are recomputed and each
  comment gains "and D1 (the final check's repairs and re-checks)"; runtime, input and config digests keep their bytes, and stored
  documents of prepared, submitted or approved revisions keep theirs. Example: the existing stored-revision tests
  pass unchanged.

Non-goals (reviewers must not require): milestone.py, FINAL_ATTEMPTS, any other prompt sentence, the critic texts,
docs.

Conflict rule: if a test outside the write-set pins the old sentence or a graph digest, change nothing and end with
`conflict: <file:line>`.

Risk: medium (model-bound text). DoD: once at the end, `python3.13 devtools/fasttest.py tests.test_task_gate
tests.test_ux tests.test_plan_gate tests.test_toolchain`: exit 0; `python3 devtools/budget.py`: OK. The changed
digest test fails on the old engine.py.
