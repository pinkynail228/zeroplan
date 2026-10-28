A5e — an unchanged milestone keeps its done attempt across a plan revision (RELEASE_0.6.0_PLAN lane E step 4;
ARCHITECT_DESIGN.md section 5). Design: ~/zs-pause/critic/a5e-design.out .. a5e-design3.out (GO).

Why: after any new approved revision every older attempt is refused ("Revision N устарела", runs.py:1255), even
when its milestone did not change: a done attempt waiting for its merge is lost work.

Reuse: runs.py `carried` :211, `run_state` :249, `check_current` :1248, `refresh` :1433, `overview` :1495,
`check_followup` :1602, `node_label` :281; delivery.py `latest` :348, `row` :395, `resolve` :564, `plan_section` :1245.

Write-set: terminal_planner/runs.py, terminal_planner/delivery.py, tests/test_milestone_snapshot.py (new),
tests/test_runs.py, tests/test_terminal_planner.py.

Acceptance criteria:
- C1 Selection: one MilestoneRuns method gives a milestone's record under the current approved revision: its last
  current-revision attempt (today); else today's carried integrated result; else the last older-revision record in
  store order when `carried(<its proposal>, <current proposal>, <milestone>)` and its `run_state` is
  `awaiting_merge` or `conflict` (a carried attempt); else none (`ready`/`waiting`, as today). `overview`, Delivery
  `latest` (so `resolve`, `latest_only`, `journal_sections`) and `plan_section` use it; `refresh` reconciles a
  carried attempt's result (manual merge, branch reset) as today's. Example: r1 has M1, M2; M1's attempt is
  awaiting_merge; approved r2 changes only M2's brief -> M1's row `awaiting_merge` with " (r1)"; M2's row `ready`.
- C2 Actions: `check_current` also passes for the carried attempt C1 selects; its actions are today's for its
  state (finish/export, merge), reachable from its row (`row` gives a token, `resolve` accepts its older
  revision). Every other older record keeps today's refusal text and family; `check_followup` gets its own
  current-revision guard with that refusal. Example (C1's state): M1's r1 attempt merges, row integrated; merged
  by hand instead, the next refresh shows it integrated and M1's dependents stop waiting; M2's r1 attempt is
  refused "Revision 1 устарела ...".
- C3 Amendment: a changed milestone starts fresh: its older attempts never show in its row. Example (C1's state):
  starting M2 -> attempt 1 of r2, its frozen baseline holds the r2 brief.
- C4 Label: `node_label` names the A4b node `preflight` «предпроверка» (tui/strings.py). Example: a running attempt
  at `preflight` shows that word where `node_label` is used.

Non-goals (reviewers must not require): follow-ups, lineage or resume across revisions (failed, failed_recoverable,
stopped, needs_owner, blocked older attempts leave the row `ready`, as today); task gates (delivery.py:630, :724);
a new revision while a milestone runs (A9, authority.py:751); the architect tools (A5t); lane T work; TUI layout.

Risk: high (persisted lineage, lifecycle gates). DoD: `python3.13 devtools/fasttest.py tests.test_milestone_snapshot
tests.test_runs tests.test_terminal_planner tests.test_toolchain` exit 0; quote the `fasttest:` lines.
