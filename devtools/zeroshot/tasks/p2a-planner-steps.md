P2a — planner steps with timers and round, as data (0.6.0, docs/RELEASE_0.6.0_PLAN.md, run p2a). A later run (p2b)
draws them in the planning canvas; this run records and returns them only.

Today: while a plan revision is observing, `Watch.record` (planning.py) stores `current["live"]["nodes"]` =
`[[node, execution], ...]` from `status.activeExecutions`, overwritten every record; nothing keeps when a node was
first seen or when it left. The planner graph (engine.py, planning graph) is a `review_loop` of `planner` then
`plan_verifier`; one loop iteration = one round. Role words: `live.role(node, live.PLANNER_ROLES)`. Live records are
checked by `live.valid` (`KEYS`, `ACCEPTED_KEYS`: older shapes keep loading).

Change:
- live.py: a new optional live key `steps` = `[[node_base, execution, first, end], ...]` (stamps as stored by
  `runs.now()`, `end` None while active), at most 16 kept, oldest dropped. A function updates it from one record:
  a new execution is added with `first` = now; an execution no longer active gets `end` = now. Records without
  `steps` stay valid.
- planning.py: `Watch.record` updates `steps` from the same active executions; when the revision's run ends, open
  steps are closed at that time. `Planning.steps(now=None)` returns, for the current round, one item per graph node
  in order `planner`, `plan_verifier`: `(role word, state, seconds, round)`; state `running` | `done` | `waiting`;
  seconds = now - first (running), end - first (done), None (waiting); round = number of `planner` executions seen
  (1 when none).

Write-set: terminal_planner/live.py, terminal_planner/planning.py, tests/test_planner_steps.py (new).

Acceptance criteria (joint example: fixture revision observing; records at 01:00:00 [planner e1], 01:03:00
[plan_verifier e2], 01:04:00 [planner e3]):
- A1 `steps(now=01:05:00)` -> (("планировщик", "running", 60, 2), ("проверка плана", "waiting", None, 2)).
- A2 Then a record at 01:06:00 [plan_verifier e4]: `steps(now=01:06:30)` -> planner ("done", 120, 2), verifier
  ("running", 30, 2).
- A3 A store written before this change (live without `steps`) loads; `steps()` -> both `waiting`, round 1.
- A4 Reopening the store between records gives the same `first`/`end` stamps (persisted, not recomputed).
- A5 The run ends at 01:07:00 (terminal observation, also `stopped` from p1a): open steps get `end` 01:07:00 and
  `steps()` still returns the last round, nothing `running`.

Non-goals (reviewers must not require): drawing in the TUI or CLI, changing `panel_lines`, milestone runs, per-task
rounds, a graph other than planner/plan_verifier.

DoD: `python3.13 devtools/fasttest.py tests.test_planner_steps tests.test_live tests.test_plan_stop
tests.test_plan_gate tests.test_terminal_planner tests.test_toolchain tests.test_reference` exit 0; quote its
`fasttest:` lines.
