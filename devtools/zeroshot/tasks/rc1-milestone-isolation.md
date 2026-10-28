RC1 — plans never ask a milestone to reach main (0.6.0 smoke 2026-10-25, defect 1, high)

Incident: ~/zs-pause/dogfood/findings-2026-10-25.md #1. The architect drafted a goal «…доведи до слияния в main»; the
planner wrote milestone checks on main (`git diff --exit-code main -- …`, `git show main:…`), the verifier accepted
them, every run failed its final check because main cannot hold the change before the merge; a plan without those
checks was rejected («слияние в main требуется в M1»). A milestone runs in its own worktree; the merge to main
happens after it, through the merge gate.

Reuse: engine.py `planner_instructions` (:672), `verifier_instructions` (:658), `DRIVER_MECHANICS` (:315) as the
pattern for a shared constant; architect.py `DRAFT_RULES` (:57).

Write-set: terminal_planner/engine.py, terminal_planner/architect.py, tests/test_ux.py, tests/test_architect.py,
tests/test_plan_gate.py, tests/test_task_gate.py (refresh only the graph goldens: V1_GOLDEN["graph"],
BASE_GOLDEN["v2_graph_2"], ["v2_graph_3"], with a comment line naming RC1, as A3 and A2a did; runtime, input and
config_digest goldens must stay byte-identical).

Acceptance criteria:
- C1 Planner: the planner prompt carries one shared sentence (a new engine.py constant) saying a milestone runs in
  its own worktree, delivery to main happens after it through the merge gate, and no task or check reads or
  requires main. Example: the planner node prompt of `planner_graph` and of `planner_graph_v2` both contain the
  constant's text.
- C2 Verifier: the verifier prompt carries the same constant plus: reject a check that reads main (`git diff main`,
  `git show main:`, `git log main`), and never reject a plan for lacking a merge to main. Example: the plan_verifier
  node prompt contains "never reject a plan for lacking a merge".
- C3 Architect: `DRAFT_RULES` gains one rule: a goal describes the product change only; merging into main is the
  owner's /merge step and never goal text. Example: the first-turn preamble contains that rule.
Joint example: goal «add slugify with a test, deliver to main» -> planner prompt (C1) and verifier prompt (C2) each
hold the isolation constant; the architect preamble (C3) tells it to leave «deliver to main» out of the goal.

Non-goals (reviewers must not require): a mechanical lint of check commands; changes to the plan schema, merge
gate or the edit prompts beyond inheriting the constant; any live model run.

Conflict rule (preflight 2026-10-25 found the two golden files above, now in the write-set): any other test outside
the write-set that pins a whole prompt or graph byte for byte -> `conflict:` with the path:line before any edit.

Risk: low (prompt text). DoD: `python3.13 devtools/fasttest.py tests.test_ux tests.test_architect tests.test_plan_gate tests.test_task_gate
tests.test_toolchain`
exit 0; quote the `fasttest:` lines.
