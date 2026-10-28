A5t2b — the architect's plan edit and merge tools, and automatic actions on (RELEASE_0.6.0_PLAN step 5 lane T,
last part of A5t; ARCHITECT_DESIGN.md section 4 decisions 1 and 3; release gate "automatic actions stay off until
A4b and A7 are merged": both merged 2026-10-25).

Why: after A5t2a the architect can approve, start, stop, resume and re-brief, but every one of them asks
(`autonomy.AUTOMATIC = False`), it cannot change a plan, and every merge needs the owner's key.

Reuse: tui/controller.py `TOOL_ARGUMENTS`, `_run_tool`, `_approve_tool` (one profile read for policy and action),
`_resume_tool`, `_token_argument`, `_plan_job`, `revise_plan` :856, `merge` :1107, `_action_status`; planning.py
`edit` :377 (a Submission; the first planner watch slice dispatches it); tui/app.py `after_submission` :2513
(`watch_planner(dispatch=True)` on "ready"); delivery.py `merge` (gated: checks + merge critic), `resolve`, `Token`;
autonomy.py `decide`.

Write-set: terminal_planner/tui/controller.py, terminal_planner/tui/app.py, terminal_planner/autonomy.py,
terminal_planner/architect_tools.py, terminal_planner/architect.py, tests/test_bridge.py, tests/test_autonomy.py,
tests/test_architect_tools.py, tests/test_architect.py.

Acceptance criteria:
- C1 Edit: `zplan_status`'s `plan` gains `proposal` (the current revision's full proposal, None without one), the
  source the architect edits. `zplan_edit_plan {revision, plan}` (the full edited proposal) runs `Planning.edit(revision, plan)` in one
  `_plan_job`; its refusals stay (`action.refused`: not current, invalid, unchanged); a "ready" verdict reaches the
  app's `after_submission` exactly as the owner's own submission does, so the TUI's planner watch dispatches it.
  Policy "edit": allow at every level (it only proposes; approval stays gated). Example: edit of the current
  proposal with one milestone title changed -> revision n+1 planning, the plan screen shows it observed.
- C2 Merge: `zplan_merge {milestone, token}` resolves the token exactly (`_token_argument`, milestone checked) and
  runs `Delivery.merge(r, expected=<digest of the profile read the policy decided on>)` (main 4d4fa55: another
  profile at the merge's own read -> `process.changed`, nothing merged) in one `mutating=True` job; result
  `{milestone, kind, line}` exactly as `Delivery.merge` renders it. Policy "merge": ask unless that profile has
  `gates.merge: required`; then auto allow, supervised and manual ask. A `refused` line naming
  `merge.critic_pending` means: call merge again with the same token (TOOL_RULES says so).
- C3 Automatic on: `AUTOMATIC = True`. Joint example (C2, C3), auto profile with `gates.merge: required`: start ->
  running; merge of an awaiting_merge attempt -> checks, critic go, `integrated`; same with `gates.merge: optional`
  -> `autonomy.ask`; supervised -> start allowed, merge `autonomy.ask`; manual -> both ask.
- C4 Text: `TOOL_RULES` gains the two tools (one line each) and says override, reject, push, tags and deleting
  branches with unmerged work are always the owner's (the existing cleanup of merged branches stays); the prompt says automatic actions follow the autonomy level. Example: TOOLS is
  exactly A5t2a's set plus edit_plan and merge.

Non-goals (reviewers must not require): an override or reject tool; a TUI decision card; journal records of
architect actions (A6b); delivery.py, runs.py, planning.py, catalog.py changes; parallel admission (A9).

Risk: high (merge landing, automatic actions). DoD: `python3.13 devtools/fasttest.py tests.test_bridge
tests.test_autonomy tests.test_architect_tools tests.test_architect tests.test_tui_chat tests.test_lifecycle_guard
tests.test_toolchain` exit 0; quote the `fasttest:` lines.
