s4b-auto-resume — 0.5 item S4b (docs/RELEASE_0.5_SCOPE.md S4b row): optional auto-resume. It needs explicit per-run permission, has an attempt cap and a time cap, can be cancelled and survives restart. It is never used for auth, forbidden (403), quota or unknown. Acceptance: a permitted run resumes once after a seeded temporary limit, and a refused class does not. DeepSeek worker, sol reviewers.

Base: main with S4a (run-failure-cause: `cause`/`reset` on milestone runs), S2 and S3 (lanes checked before every start and resume) merged, and the S2/S3 recovery qualification recorded. Record the base commit in the receipt. The audit is on main 74f1a3b plus the S4a spec: re-check every line number on the base, and re-gate if a premise moved.

Audit (74f1a3b):
- Manual resume: `Runs.resume` runs.py:980-1004.
  - It is allowed only when the run is failed with a run_id, has never been resumed, no other run is active, and native `workspaceRecovery.recoverable` is true with no successor.
  - It saves a `resume_pending` successor before dispatch.
  - Crash recovery is `adopt_successor` :1006-1018.
  - `failed_recoverable` state: runs.py:216, :235.
- Callers: `Delivery.resume` delivery.py:837; tui/controller.py:808; cli.py:305, :327, :716. Catalog entries catalog.py:68, :222, :378, :437.
- S4a (devtools/zeroshot/tasks/run-failure-cause.md):
  - `cause` is one of auth, quota, limit, forbidden, network, unknown;
  - `reset` is free text, for limit only (e.g. "3:10am (Europe/Moscow)"); it is not machine-parseable;
  - its R-3 says the cause is observational ("latest observed execution failure"), not a proven terminal cause.
- TUI timers: app.py:1475-1478 (`REFRESH_SECONDS=3` :36), `follow_runs` :2408 re-attaches after restart. `controller.observe_run` :650-668. Plain CLI has no background loop.
- Records persist in the locked Authority store (runs.py:3, :580; authority.py:98).

Read: those locations; terminal_planner/runs.py, delivery.py, process.py (limits pattern; S9b1's optional-limit rule), catalog.py, cli.py, tui/controller.py, tui/app.py; the S4a and S3 changes; docs/USER_FLOW.md; tests/test_runs.py :444, :506; test_tui_milestones.py :281, :302, :455; test_tui_live.py :443; test_reference.py :321.

Rules:
- R-1 Eligible classes: `limit` and `network` only. `auth`, `forbidden`, `quota`, `unknown`, a missing cause, and any run that manual resume would refuse are never auto-resumed. Eligibility is re-evaluated at fire time against the current record, not only at scheduling.
- R-2 Permission. Per run, by an explicit owner action (TUI key; plain/CLI command), offered only on an eligible failed run. The owner chooses the delay. Default 60 minutes for limit and 5 for network; allowed range 1..360 minutes; the `reset` text is shown as a hint, never parsed.
  - A permission record is stored in Authority before anything else: {run id, cause at grant, fire_at (UTC), attempts_allowed=1, deadline = grant + 6 h, state scheduled}.
  - There is no project-wide or default-on permission.
- R-3 Cap. At most one auto-resume per permission. A resumed run that fails again needs a new owner permission. The cap holds across restarts.
- R-4 Fire. While zplan's TUI is open, the existing refresh loop fires a due permission. Plain mode has `zplan resume --wait RUN`, which waits in the foreground until fire_at and then fires; Ctrl+C cancels the wait without cancelling the permission.
  - Firing calls the same `Runs.resume` path, with the same checks: S3 lane checks and the task gate if required. It never calls a second implementation.
  - Under the Authority lock, persist scheduled -> firing before dispatch; finish as fired | refused(reason) | expired. Reuse MilestoneRuns.resume and its durable resume_pending record. On restart, adopt a confirmed native successor. If none is confirmed, mark the permission refused and expose the existing recovery state; never redispatch a firing permission. Grant, cancel and fire serialize on the same lock.
- R-5 Cancel. An owner action cancels a scheduled permission. A cancelled or expired permission never fires. Closing zplan does not cancel; on reopen a due, unexpired permission fires once.
- R-6 Display. Home, run view and status show "автопродолжение в HH:MM (через N мин)", "автопродолжение отменено/истекло/отклонено: reason" and the next key. Catalog families are `resume.auto_*`; REFERENCE.md is regenerated.

Acceptance (unit tests, deterministic fixtures, injected clock; no real waiting):
- A-1 Parameterize limit and network: permission -> fire_at -> exactly one resume through MilestoneRuns.resume. Verify defaults, accepted delays 1/360 minutes, refused delays 0/361, and deadline-1/deadline/deadline+1 seconds. A second failure requires new permission.
- A-2 Each refused class (auth, forbidden, quota, unknown, missing) cannot be granted. A class changed to refused after grant (record updated) -> refused at fire time, with no resume.
- A-3 Fault-inject after persisting firing, after persisting resume_pending, and after native acceptance before saving the receipt. Reopen: no redispatch; zero driver calls before dispatch, one after dispatch. Concurrent TUI/--wait firing, synchronized with barriers, makes at most one driver call. Grant -> close -> reopen after fire_at fires once.
- A-4 Cancel and expiry: cancelled or past-deadline permissions never fire.
- A-5 Plain --wait fires with an injected clock; interrupt preserves permission. With TUI closed and no --wait process, advancing the clock causes no dispatch. status and other observation-only commands never fire permissions.
- A-6 Manual resume preconditions are unchanged; S3 lane refusal at fire -> refused(reason), with no resume.
- A-7 Replay through the existing cli.main entry point: granting permission must fail on base at an observable behavioral assertion, not an import or missing-method error. Cover new-helper safety logic with targeted mutations; report named failures and skips separately.

Size: about 500-800 changed lines including tests, above the ~500-line review trigger. Kept together because grant, fire, cancel and restart reconciliation are one lock-serialized state machine over one record; splitting would leave a permission that can be granted but not safely fired or cancelled.

DoD:
- Unit tests pass.
- USER_FLOW.md and REFERENCE.md updated.
- Receipt.
