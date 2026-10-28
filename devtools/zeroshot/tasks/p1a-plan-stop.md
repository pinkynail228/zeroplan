P1a — stop a running planner from the `zplan` plan screen, with the cause kept (0.6.0, docs/RELEASE_0.6.0_PLAN.md,
run p1a). Incident U12/U17: run 01a164b0 had to be force-stopped by hand; the stop showed no cause.

Today: `Planning.view()` (planning.py) offers ("watch", "details", "tail") while the revision is observing; statuses
are `authority.PLAN_STATUSES` (no `stopped`; `save()` validates); the CLI plan screen maps view actions to catalog
ids in `cli.PLAN_ACTIONS`. Stages already stop through native force-stop (`runs.py` `force_stop`: `engine.call([...,
"force-stop", run_id], ...)`, only the exit code counts; the stop is confirmed by observing the finished run;
`MilestoneRuns.stop` persists `stopping` before the call). The planner run id is `current["run_id"]`.
`Planning.restart()` creates a new revision for a failed plan.

Change:
- Observing view offers `stop` (catalog id `plan.stop`, «[s] остановить планирование»). `Planning.stop()` saves a
  stop request with its time before calling native force-stop for `current["run_id"]` (same call as stages); a
  refused or timed-out call keeps the revision as it was and raises a Blocked with the reason.
- When the observation then ends the run, a revision with a stop request becomes `stopped` (new status in
  `PLAN_STATUSES` and the catalog), not `run_failed`. Its view: «План rN остановлен вами в HH:MM.» with `restart`
  and `details`. `restart` from `stopped` works like from a failure: a new revision and submission key; the stopped
  run is never resubmitted.

Write-set: terminal_planner/planning.py, terminal_planner/authority.py, terminal_planner/engine.py,
terminal_planner/catalog.py, terminal_planner/cli.py, docs/USER_FLOW.md, tests/test_plan_stop.py (new).

Acceptance criteria (joint example: fixture planner observing r1, run R1):
- A1 Plan screen shows «[s] остановить планирование»; pressing s calls force-stop once with R1 and shows
  «Остановка запрошена»; the stored revision already holds the request when force-stop is called.
- A2 After the fixture run finishes, the screen shows «План r1 остановлен вами в 01:40.» and offers restart, not
  «run failed».
- A3 Reopening zplan on the same store shows the same line (the cause survives).
- A4 Restart -> r2 is submitted with a new submission key; R1 is not submitted again.
- A5 Force-stop exits 1 -> «Не выполнено: …» on screen, the revision stays observing and s is offered again.

Non-goals (reviewers must not require): the TUI `/stop` (run p1b), recovering a partial proposal, stopping a
revision that is not observing, Linux runs.

DoD: `python3.13 devtools/fasttest.py tests.test_plan_stop tests.test_lifecycle_guard tests.test_plan_gate
tests.test_run_cause tests.test_live tests.test_ux tests.test_terminal_planner tests.test_runs tests.test_toolchain
tests.test_reference` exit 0; quote its `fasttest:` lines.
