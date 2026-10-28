s9b-run-guards — 0.5 item S9 (docs/RELEASE_0.5_SCOPE.md:28), part 2 of 2:
- a budget rule that blocks the next starts and never kills a live run;
- a time limit on waiting for a mutating job at Ctrl+Q;
- UI handler exceptions logged instead of swallowed.
Incidents: cost watched by hand (DEV_RUNTIME_ECON.md:35); "Ctrl+Q waits for a mutating job without a time limit" and "UI handler exceptions are swallowed without a log" (STATE Open). The run view is in s9a-run-view. DeepSeek worker, sol reviewers.

Base: main with s2c-agent-usage (the `usage` field) and s9a-run-view merged. Record the base commit in the receipt. The audit is on 0186e38: re-check every line number on the base, and re-gate if a premise moved.

Audit (0186e38):
- Budget. No budget exists. Profile limits: `LIMITS` process.py:32, validation :172-180. Normalization requires the full LIMITS set (:305-334). The preset is at :64; the config digest is built from the normalized config.
  - `Delivery.guard("milestone")` delivery.py:527-531 is the shared refusal before any side effect for preview :533, start :568, new_attempt/answer/accept :827-835 (through `live_roles`).
  - `Delivery.resume` delivery.py:837 -> `runs.resume` runs.py:980 bypasses it.
  - Per-attempt usage comes from S2c (`usage`, null when unknown or incomplete).
- Ctrl+Q.
  - `action_quit` app.py:1431-1453: when `begin_closing` reports a mutation, it pushes FinishingScreen (app.py:642-647, text QUIT_WAITS app.py:60) and returns.
  - `quit_when_idle` app.py:1454-1458 exits only when no mutation is counted.
  - `Controller.stop` joins without bound while a mutation runs (controller.py:357-376, documented at :361).
  - A second Ctrl+Q while quitting does nothing new.
  - Mutating jobs are every `_job`/`post` label outside CUTTABLE (controller.py:37-38): answer_draft, approve, check_run, leave, merge, override, preview, profile, reject, renew, restart, revise, start, start_run, stop_run, submit, to_plan, setup, plus the dispatching observe slice and the `_end` export (controller.py:29-36).
  - The worker thread is a daemon (controller.py:307).
- Exceptions.
  - `App._handled` app.py:1505-1518 swallows (`except Exception: pass`).
  - The worker turns a non-Blocked exception into an error string with no traceback (controller.py:398-401) and swallows a failing `done` (controller.py:407-410).
  - terminal_planner has no logging and no traceback use at all.
  - The data root is setup.py:29 (durable after S5a).
  - `Modal.on_unmount` app.py:552-557 swallows the expected "app going away" case.

Read: those locations; tui/app.py :1340-1460, :1495-1530; tui/controller.py :270-440; process.py :25-70, :160-200, :295-400, :640-660; delivery.py :425-460, :520-580, :815-840; setup.py :20-40; catalog.py; docs/USER_FLOW.md (Ctrl+Q row :30, Live run); docs/PROCESS_PROFILE.md (limits); tests/test_tui.py quit tests, test_process*.py.

Rules:
- R-1 Budget setting. `limits.plan_tokens` is optional in zplan.process.json: an int 1..10**12 (bools rejected). When it is absent there is no budget.
  - Its absence leaves the normalized config, the config digest, the `/1` preset and every existing profile byte-identical to the base. An invalid value is `process.invalid`, like the other limits.
  - The profile display stops calling it "для следующих версий" once it acts.
  - docs/PROCESS_PROFILE.md documents it.
  - Keep the existing required LIMITS set unchanged. Validate plan_tokens as a separate optional limit; resolve and snapshot it only when present. complete() accepts the existing required limits plus this optional key. A present value participates in the config digest and normal profile-change handling; absence synthesizes no default and changes no existing digest.
- R-2 Spent. Only the current approved plan revision's milestone attempts in `runs.TERMINAL` count; integers only.
  - S is the sum of inputTokens + outputTokens over attempts whose `usage` is a dict with `complete` true.
  - K is the number of the others: usage absent, null or incomplete. They are counted, never as 0 and never estimated.
  - A resumed successor counts with its own usage.
  - Active attempts and planner revisions are not counted.
- R-3 Gate. With B set and S >= B, `Delivery.guard("milestone")` and `Delivery.resume` refuse before any side effect, with family `run.budget`: "Бюджет плана исчерпан: потрачено S из B токенов[; без данных: K попыток]. Новые запуски заблокированы; идущий прогон не останавливается. Поднимите limits.plan_tokens в zplan.process.json."
  - K > 0 with S < B does not block. S is the confirmed spend, not an estimate of the full spend.
  - Never stop, force-stop, kill or detach an active attempt because of the budget, and never skip its observation. A run that crosses B finishes and is delivered normally.
  - Planner revisions and merges are not gated.
- R-4 Budget display. With B set, the home overview shows "Бюджет: S из B токенов" plus ", без данных: K" when K > 0, on the line after the plan line. When S >= B, "Дальше:" names the budget remedy instead of a start, resume or new attempt. Other actions, [w], [e] and merge, stay as they are. Plain UI and TUI show the same line.
- R-5 Ctrl+Q limit. QUIT_MUTATION_LIMIT = 60 s on a monotonic clock that tests can inject; it starts at the first Ctrl+Q that found a mutation.
  - Before the limit, FinishingScreen shows QUIT_WAITS plus the job's catalog name and the elapsed seconds, and another Ctrl+Q changes nothing.
  - Exit eligibility is computed under the controller guard across every admitted mutation, including queued work, nested exports and pending delivery releases. A job is detachable only after a durable reconciliation checkpoint and while no unsafe mutation remains. Start and answer preparation are not detachable merely because their eventual submission is reconcilable. Define an exhaustive label/phase table before implementation; every omitted label or phase waits. stop_run is detachable only after stopping is durably saved.
  - The table (every label of the audit × its phases: before preparation, before durable persistence, during dispatch, after receipt, during delivery) is part of the deliverable, in the code next to CUTTABLE and in the receipt. Merge, export, setup and unclassified operations continue waiting (scope S9).
  - At the limit, when the guard computes eligibility: "[ctrl+q] ещё раз — выйти сейчас; операция будет сверена при следующем запуске"; a Ctrl+Q then exits within QUIT_BUDGET without joining the worker, and child processes started in their own session keep running. Otherwise: "<job> нельзя прервать без риска для Git/записей; жду завершения", and the wait stays unbounded. Eligibility is re-evaluated as phases advance.
  - The job finishing at any time exits as today.
- R-6 Exception log. Every exception caught by `App._handled`, by the worker's generic `except Exception` and by the `done` guard is appended to `<data root>/logs/tui-errors.log` (directory 0700, file 0600). The expected unmount/"app going away" catches are not logged.
  - Record: one block of a UTC stamp, a site (`handler`, `job:<label>` or `done:<label>`), the exception type, the message, and traceback frames as "file:line in function" (no locals, no source text). The message passes the s9a R-3 steps before writing.
  - Bound: before a write that would make the file exceed 256 KiB, rename it to `.1`, replacing any existing `.1`.
  - Any logging failure is swallowed after one attempt and never raises into the UI or the worker.
  - Serialize rotation and append across UI and worker threads. Bounds use encoded UTF-8 bytes. Bound each block to 16 KiB, retaining newest traceback frames and an omitted-frame count. Existing files must also have restrictive permissions. Show the once-per-session "записана" note only after a successful append.
  - Behavior after the exception is unchanged. The note text is "Внутренняя ошибка интерфейса записана: <path>".
- R-7 Text through the catalog, REFERENCE regenerated, and docs/USER_FLOW.md (Ctrl+Q row, budget line, error log path) updated.

Acceptance criteria (deterministic fixtures, no provider or network, temporary data roots; Textual pilot at 80x24 and 120x40; synchronization with Events and an injected monotonic clock, never fixed sleeps; production entry points):
- A-1 Setting: 1 and 10**12 are accepted. 0, -1, 10**12+1, true, 1.5 and "10" give process.invalid. With the setting absent, the base profile fixtures keep their normalized config and digest byte-identical, and `/1` is unchanged.
- A-2 Gate:
  - S = B-1 starts; S = B and S = B+1 refuse with the exact text. K > 0 with S < B starts, and the home line shows K.
  - Refusals come from preview, start, new_attempt, answer, accept and resume, in both UIs. A spy shows no worktree, branch, record or submission was created.
  - Attempts of an older revision and active attempts are excluded. A resumed pair counts both usages.
  - A running attempt that crosses B makes no stop/force_stop call, keeps being observed, and still reaches its end view.
- A-3 Ctrl+Q: Exercise production entry points with fake external backends and barriers before preparation, before durable persistence, during dispatch, after receipt and during delivery. Reopen the same store and prove reconciliation without duplicate submission or inconsistent Git/worktree state. Cover queued unsafe work and nested export. At least one production operation must qualify for bounded exit.
  - Before the limit (clock at 59.9 s) a second Ctrl+Q does not exit; at 60 s the line matching the guard's eligibility appears.
  - Merge, setup and an unclassified label keep waiting and exit when released.
  - The FinishingScreen text fits at both sizes.
- A-4 Exceptions:
  - A raising UI handler, a raising non-Blocked job and a raising `done` each append exactly one record, and the app keeps working (the next key acts).
  - A message carrying `api_key=…`, ESC sequences and a bidi character is written scrubbed.
  - Rotation at 256 KiB-1, exactly 256 KiB and +1 byte, measured in UTF-8 bytes with multi-byte messages; a block over 16 KiB keeps the newest frames and the omitted count.
  - Concurrent UI and worker exceptions (Event-synchronized) produce two whole blocks and a consistent rotation.
  - A pre-existing log file with loose permissions ends with 0600; the directory 0700.
  - A read-only log directory raises nothing and shows no "записана" note.
  - The unmount path writes nothing.
  - The note is shown once per session, after the first successful append.
- A-5 Regressions: production-entry regression tests must reach the intended behavioral assertion on the named base. New-helper unit tests are excluded from base replay and covered by targeted mutations. The receipt maps each acceptance criterion to base replay or candidate-only mutation coverage. Base replay must use inputs supported by the base and reach the intended behavioral assertion; import, missing-symbol, unsupported-config and setup failures are not behavioral evidence. Candidate-only coverage names the killed mutation and assertion. A base `process.invalid` for `plan_tokens` is not evidence of a working budget refusal. Mutations:
  - count unknown usage as 0;
  - let K alone block;
  - stop the live run on a budget hit;
  - gate resume through a path other than Delivery;
  - make merge detachable;
  - make start detachable during preparation;
  - ignore queued unsafe work in eligibility;
  - exit before the limit;
  - log without scrubbing;
  - drop the rotation or the append lock;
  - show the note after a failed append.
  Record the commands and base failures. Existing quit, shutdown and readiness tests stay green.

Size/Order: This file is an umbrella specification, not an executable task. Create and independently gate s9a1-run-reader (~380 lines), s9a2-run-view (~520 lines), and s9b1-run-budget (~280 lines). S9a1 owns parsing, scrub, execution attribution and cancellable reader mechanics; s9a2 owns presentation, attempt selection and refresh scheduling; s9b1 owns budget setting, accounting, guards and display. Assign every acceptance criterion to a child task. S9a2 additionally verifies the complete reader-to-screen path, including refresh, close, Ctrl+Q, reload and terminal transition. No child starts before its own gate passes.
Deferral: R-5/R-6 and their acceptance criteria are deferred beyond 0.5. They are not implementation deliverables or release gates for s9b1. Their future task requires a concrete eligibility table before task approval.
Assignment: s9b1-run-budget owns R-1..R-4, the budget parts of R-7, A-1, A-2 and the budget mutations of A-5. R-5, R-6, A-3, A-4 and the Ctrl+Q/logging mutations of A-5 are deferred (S9b2, scope Deferred).
Out of scope: per-attempt time or token caps, alarms, automatic stop or resume (S4b); planner budgets; a per-user budget setting; changing which jobs count as mutating; a bound for merge, export, setup or unclassified operations; log shipping or a log viewer; the run view (s9a); upstream changes.
critic s9-task: round 2 BLOCK -> umbrella; child s9b1 gated separately, S9b2 deferred (session 01a150fd-4cce-72d2-9d50-595b08e1a2b8)
