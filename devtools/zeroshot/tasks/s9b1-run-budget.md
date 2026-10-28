s9b1-run-budget — 0.5 item S9 (docs/RELEASE_0.5_SCOPE.md S9 row), child 3 of 3; umbrella devtools/zeroshot/tasks/s9b-run-guards.md (its R-1..R-4). An optional plan-token budget that blocks the next starts and resumes and never stops a live run. Incident: cost watched by hand (DEV_RUNTIME_ECON.md:35). The Ctrl+Q limit and the exception log (umbrella R-5/R-6) are deferred beyond 0.5 (S9b2). DeepSeek worker, sol reviewers.

Base: main with s2c-agent-usage (the `usage` field) and s9a2-run-view merged (order and shared catalog/delivery files; no semantic dependency on s9a). Record the base commit in the receipt. The audit is on 0186e38: re-check every line number on the base, and re-gate if a premise moved.

Audit (0186e38):
- No budget exists. Profile limits: `LIMITS` process.py:32, validation :172-180. Normalization requires the full LIMITS set (:305-334). The preset is at :64; the config digest is built from the normalized config.
- `Delivery.guard("milestone")` delivery.py:527-531 is the shared refusal before any side effect for preview :533, start :568, new_attempt/answer/accept :827-835 (through `live_roles`).
- `Delivery.resume` delivery.py:837 -> `runs.resume` runs.py:980 bypasses it.
- Per-attempt usage comes from S2c (`usage`, null when unknown or incomplete); `runs.TERMINAL` names the finished states.

Read: process.py :25-70, :160-200, :295-400, :640-660; delivery.py :300-320, :400-460, :520-580, :815-840; runs.py :960-1000 and TERMINAL; catalog.py; cli.py home rendering; docs/PROCESS_PROFILE.md (limits); docs/USER_FLOW.md (home); tests/test_process*.py, test_delivery*.py, test_tui.py home tests.

Rules:
- R-1 Budget setting. `limits.plan_tokens` is optional in zplan.process.json: an int 1..10**12 (bools rejected). When it is absent there is no budget.
  - Its absence leaves the normalized config, the config digest, the `/1` preset and every existing profile byte-identical to the base. An invalid value is `process.invalid`, like the other limits.
  - The profile display stops calling it "для следующих версий" once it acts.
  - Keep the existing required LIMITS set unchanged. Validate plan_tokens as a separate optional limit; resolve and snapshot it only when present. complete() accepts the existing required limits plus this optional key. A present value participates in the config digest and normal profile-change handling; absence synthesizes no default and changes no existing digest.
- R-2 Spent. Only the current approved plan revision's milestone attempts in `runs.TERMINAL` count; integers only.
  - S is the sum of inputTokens + outputTokens over attempts whose `usage` is a dict with `complete` true.
  - K is the number of the others: usage absent, null or incomplete. They are counted, never as 0 and never estimated.
  - A resumed successor counts with its own usage. Active attempts and planner revisions are not counted.
- R-3 Gate. With B set and S >= B, `Delivery.guard("milestone")` and `Delivery.resume` refuse before any side effect, with family `run.budget`: "Бюджет плана исчерпан: потрачено S из B токенов[; без данных: K попыток]. Новые запуски заблокированы; идущий прогон не останавливается. Поднимите limits.plan_tokens в zplan.process.json."
  - K > 0 with S < B does not block. S is the confirmed spend, not an estimate of the full spend.
  - Never stop, force-stop, kill or detach an active attempt because of the budget, and never skip its observation. A run that crosses B finishes and is delivered normally.
  - Planner revisions and merges are not gated.
- R-4 Display. With B set, the home overview shows "Бюджет: S из B токенов" plus ", без данных: K" when K > 0, on the line after the plan line. When S >= B, "Дальше:" names the budget remedy instead of a start, resume or new attempt. Other actions, [w], [e] and merge, stay as they are. Plain UI and TUI show the same line.
- R-5 Text through the catalog, REFERENCE regenerated, docs/PROCESS_PROFILE.md documents plan_tokens, docs/USER_FLOW.md shows the budget line.

Acceptance criteria (deterministic fixtures, no provider or network, temporary data roots; Textual pilot at 80x24 and 120x40; production entry points):
- A-1 Setting: 1 and 10**12 are accepted. 0, -1, 10**12+1, true, 1.5 and "10" give process.invalid. With the setting absent, the base profile fixtures keep their normalized config and digest byte-identical, and `/1` is unchanged. A present value changes the digest and goes through normal profile-change handling.
- A-2 Gate:
  - S = B-1 starts; S = B and S = B+1 refuse with the exact text. K > 0 with S < B starts, and the home line shows K.
  - Refusals come from preview, start, new_attempt, answer, accept and resume, in both UIs. A spy shows no worktree, branch, record or submission was created.
  - Attempts of an older revision and active attempts are excluded. A resumed pair counts both usages.
  - A running attempt that crosses B makes no stop/force_stop call, keeps being observed, and still reaches its end view.
  - The home budget line and the budget "Дальше:" fit at both sizes; merge stays offered at S >= B.
- A-3 Regressions: production-entry regression tests must reach the intended behavioral assertion on the named base. New-helper unit tests are excluded from base replay and covered by targeted mutations. The receipt maps each acceptance criterion to base replay or candidate-only mutation coverage. Base replay must use inputs supported by the base and reach the intended behavioral assertion; import, missing-symbol, unsupported-config and setup failures are not behavioral evidence. Candidate-only coverage names the killed mutation and assertion. A base `process.invalid` for `plan_tokens` is not evidence of a working budget refusal. Mutations:
  - count unknown usage as 0;
  - let K alone block;
  - stop the live run on a budget hit;
  - gate resume through a path other than Delivery;
  - synthesize a default plan_tokens (digest change when absent);
  - count active or older-revision attempts;
  - gate merge.
  Record the commands and base failures. Existing profile, digest and readiness tests stay green.

Size: ~280 lines (production ~110, tests ~170).
Order: Required release order: dogfood-polish-04 -> 0.4.0 tag -> S4/S5a -> S2a -> S2b -> S2c -> s9a1 -> s9a2 -> s9b1. S9b1 starts after s9a2 is merged and its own gate passes. S9b2 is deferred.
Out of scope: Ctrl+Q limit and exception log (deferred S9b2); per-attempt time or token caps, alarms, automatic stop or resume (S4b); planner budgets; a per-user budget setting; the run view (s9a2); upstream changes.
critic s9-task: round 3 GO (session 01a150fd-4cce-72d2-9d50-595b08e1a2b8)
