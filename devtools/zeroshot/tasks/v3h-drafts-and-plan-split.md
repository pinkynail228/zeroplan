# v3h — a run start brings the Plan tab forward; the approved-plan view reuses home's read

docs/PLAN_UX.md V3, Q3 ("the Plan tab comes forward after launch"; Astra's consult, design dir
drafts-astra-consult.md, point 1). Today `run_started` (tui/app.py) brings Scheme forward once per run (F9);
approval already brings Plan forward (`plan_approved`). v3g added `Delivery.approved()` (delivery.py), which runs
`Runs.overview` a second time on every snapshot even when the current revision is the approved one (home has just
run it), so each refresh detects integration twice.

Change:
- `run_started` brings Plan forward instead of Scheme, once per run; `move_tab` keeps the owner's own tab choice as
  today; nothing else about tabs changes.
- `Delivery.approved()` reuses the overview home already read when the current revision is the approved one; it
  runs its own only for an older approved revision.

Write-set: terminal_planner/tui/app.py, terminal_planner/delivery.py, tests/test_tui_follow.py,
tests/test_tui_milestones.py, tests/test_tui_canvas_files.py, tests/test_tui_activity_pane.py,
tests/test_tui_reopen_fixes.py, tests/test_tui_narrow.py, tests/test_parallel_home.py

Acceptance criteria:
- A1 Plan on start. Example: M1's run starts with no owner tab choice -> Plan is the active tab, not Scheme.
- A2 The owner's choice wins. Example: the owner moved to Scheme by key, then a run starts -> Scheme stays.
- A3 One read. Example: r1 approved and current -> one snapshot refresh calls `Runs.overview` once.

Non-goals (reviewers must not require): what Plan and Drafts render (next task), pointers in card texts, Scheme.

Conflict rule: a test outside the write-set pinning the start's tab: change nothing, end with
`conflict: <file:line>`.

Risk: low (owner screen). DoD: `python3.13 devtools/fasttest.py tests.test_tui_follow tests.test_tui_milestones
tests.test_tui_canvas_files tests.test_tui_activity_pane tests.test_tui_reopen_fixes tests.test_parallel_home`: exit 0.
