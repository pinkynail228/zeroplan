H5 — the planner's mechanics sentence names the final check per milestone; the qual marker is added once

h4 (merged f990a82) final check, non-blocking notes: DRIVER_MECHANICS (engine.py) ends "bounded repairs and a final
milestone check for every task", but the final check runs once per milestone, so the planner still reads one untrue
claim. driver_qual's documents() calls mark() on a graph the marked() scope already decorated, so bare-CLI scenarios
a..j carry each marker twice (dispatch reads the last one, so behaviour is the same).

Reuse: the h4 tests that pin DRIVER_MECHANICS (test_plan_gate) and the marker scope (test_milestone); marked() and
mark() in devtools/driver_qual.py as they are.

Write-set: terminal_planner/engine.py, devtools/driver_qual.py, tests/test_plan_gate.py, tests/test_milestone.py,
tests/test_task_gate.py (its planner golden digests pin the sentence; refresh them for this text only).

Acceptance criteria:
- M1 DRIVER_MECHANICS says the reviews and bounded repairs are per task and the final check per milestone.
  Example: the text has "for every task" only before "a final milestone check", or "once per milestone" after it.
- M2 Inside the marked() scope every node of a bare-CLI scenario's graph starts with exactly one ZPLAN_NODE marker.
  Example: driver_qual documents() for scenario a -> each instructions string has "ZPLAN_NODE=" exactly once.

Non-goals (reviewers must not require): other prompt text; the qual dispatch; running driver_qual (owner
2026-10-28: no Linux qualification).

Conflict rule: if a test outside the write-set pins the old DRIVER_MECHANICS text, change nothing and end with
`conflict: <file:line>`.

Risk: low (one sentence and a dev tool). DoD: run once, at the end: `python3.13 devtools/fasttest.py
tests.test_plan_gate tests.test_milestone tests.test_task_gate tests.test_toolchain`: exit 0; `python3 devtools/budget.py`: OK. Each new
test fails with the old sentence or the second mark() restored.
