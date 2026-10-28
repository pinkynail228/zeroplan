P3a — plan task tree model: milestone -> slice -> task with each task's status (0.6.0,
docs/RELEASE_0.6.0_PLAN.md, run p3a). A later run (p3b) draws it in the plan tab; this run adds the model and its
plain text lines only.

Today: the approved plan is `current["proposal"]` (shape checked by `authority.validate_proposal`:
`milestones[{id,title,depends_on,slices[{id,title,requirements,tasks[{id,title,checks}]}]}]`, ids unique). A
milestone attempt's manifest (`runs.read_manifest(r)`, None when missing or invalid) has `tasks[{id,title,status,
origin,...}]`, status open | done | dropped; plan tasks keep their plan ids (`milestone.build_baseline`,
`initial_manifest`); tasks added during work have `origin` other than "plan". `runs.current_task(manifest)` gives the
first open task.

Change: new module terminal_planner/plan_tree.py, pure (no I/O, no imports from tui/):
- `build(proposal, manifests)`: `manifests` = {milestone id: manifest or None} (the caller passes the latest
  attempt's manifest). Returns a list of milestone nodes, each with its slices, each with its tasks; every task has a
  status: `done`, `dropped`, `current` (the first open task of a milestone with a manifest), `open`. Tasks in a
  manifest that are not in the proposal go to the end of their milestone as `added` nodes with their own status;
  their line is «+ », then the status mark, at slice indent.
  Plan order is kept.
- `lines(tree)`: plain text lines, two spaces of indent per level, a status mark per task: `✓` done, `▸` current,
  `·` open, `✗` dropped, and a milestone counter «2/5».

Write-set: terminal_planner/plan_tree.py (new), tests/test_plan_tree.py (new), README.md (code map row).

Acceptance criteria (one joint example covers all five): proposal M1{S1{T1,T2,T3}}, M2{S2{T4}}; manifests
{M1: T1 done, T2 open, T3 dropped, added T9 open; M2: None} ->
```
M1 Title1 1/3
  S1 Title
    ✓ T1 Title
    ▸ T2 Title
    ✗ T3 Title
  + · T9 Title
M2 Title2 0/1
  S2 Title
    · T4 Title
```
- A1 Plan order and nesting as in the example.
- A2 Statuses from the manifest; the first open task of M1 is `current` (▸); added T9 shows as «+ · T9».
- A3 A milestone without a manifest shows every task open (M2).
- A4 The counter is done / tasks not dropped, added tasks counted («1/3» for M1).
- A5 A manifest task id equal to a plan id is never shown twice.

Non-goals (reviewers must not require): wiring into the TUI or CLI, colours, width cutting, reading files, invalid
proposals (the input is already validated).

DoD: `python3.13 devtools/fasttest.py tests.test_plan_tree tests.test_toolchain tests.test_reference` exit 0;
quote its `fasttest:` lines.
