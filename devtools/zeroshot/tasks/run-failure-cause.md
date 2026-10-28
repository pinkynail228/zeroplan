run-failure-cause — 0.5 item S4 (docs/RELEASE_0.5_SCOPE.md): a failed milestone run says why the provider failed. The branch is held until the 0.4.0 tag and merges after it. DeepSeek worker, sol reviewers.

Observed in the engine records (~/.local/state/zeroshot/runs/*/runs.sqlite3, table v2_run_events): a provider limit, a 403 and a review defect end the same way. The node outcome is `crash`/`declared_failure`, and the run terminal reason is `review_failed`. The cause survives only as text in native error records. Excerpts (fragments of longer messages, not full fixtures):
- "Claude provider failure: You've hit your session limit · resets 3:10am (Europe/Moscow)" (run 01a1377a seq 204, terminal seq 220);
- "Codex provider failure: unexpected status 403 Forbidden" plus an HTML body over several lines (run 01a13849 seq 813, terminal seq 922);
- "workspace routing discovery unauthorized (401)" (01a14ba5 seq 76);
- "Your workspace is out of credits" (01a14c3c seq 1084).
zplan already classifies error text for planner runs:
- terminal_planner/engine.py:266-302 (`CAUSES`/`error_lines`/`classify`) and `failure_cause` engine.py:819-833;
- planning.py:396-470, which branches on the raw cause at :446;
- the planner.* catalog at catalog.py:177-182.
The planner recognises 401/403 today, but not session-limit or out-of-credits. `error_lines` ignores the native envelope `record.level/message` that the CLI emits (upstream/zeroshot/src/native_v2_cli/execution.rs:628): a flat error line classifies as auth, the same text in a native envelope as unknown. Milestone runs store only `diagnostic=terminal["reason"]` (runs.py:916-922), so the owner sees a bare "failed".

Read:
- terminal_planner/engine.py: `CAUSES`, `error_lines`, `classify`, `failure_cause`;
- planning.py:396-470;
- runs.py: `validate_run` and its exact field set near :53/:372, `run_state` :221-235, `conclude` :916-922, the stored `binding`;
- live.py: `scrub` near :362;
- catalog.py: :39, :177-182;
- delivery.py:303, :353, :768 (the failed-attempt line and end view);
- docs/REFERENCE.md and the tests for each;
- upstream/zeroshot/src/native_v2_cli/execution.rs near :628 (the envelope);
- upstream/zeroshot/src/native_v2_capsule/provider_process.rs near :424 (retry).

Rules:
- R-1 Extraction. Extend the shared `error_lines` extractor to accept native `record.level/message` and classify only error records. Keep the existing flat formats, and ignore info/system/model output. Production tests use native envelopes.
- R-2 Classes. On a milestone run that concludes `failed` or `failed_recoverable`, store an optional `cause`: one of auth, quota, limit, forbidden, network, unknown.
  - Match: `session limit` -> limit (never a standalone `resets`); `out of credits` -> quota; `403 Forbidden` -> forbidden.
  - Remove 403 from auth (auth keeps 401/login/unauthorized), and match forbidden before auth.
  - Planner: normalize limit->quota and forbidden->auth before planner rendering, everywhere the planner branches on the cause; existing planner wording is unchanged.
- R-3 Which failure. Source: the public `zeroshot logs <run>` JSON lines `{cursor, execution?, record:{level, message}}` (upstream protocol native_v2_observation.rs:302-313, projection.rs:70-120). The engine writes, for every failed execution, an error record with that execution id and the message `Node <node> failed: <code>[...][: <cause>]` (native_v2_supervisor/logging.rs:12-56, 89-101). A successful execution writes none. The single provider retry writes an error record plus a debug "provider failed; continuing once" with the same execution id (provider_process.rs:420-438), so an error record alone does not mean the execution failed.
  - This identifies the latest observed execution failure, not the proven terminal cause (a later success or a reviewer rejection writes no `Node … failed:` record). The latest observed execution failure is the `Node <node> failed:` record with the latest cursor whose cause is not the run-wide `run <reason>` (logging.rs:58-87). Its evidence is that message plus the earlier error records with the same execution id. Diagnostics of any other execution (recovered retries, earlier graph visits) are ignored. An explicitly non-provider completion failure (for example `result did not match the node contract`, policy denied, interactive input required) yields unknown regardless of earlier provider diagnostics in the same execution; earlier diagnostics may augment only a completion summary that itself identifies a provider failure.
  - Classify the evidence with R-2. If several classes match, the precedence is limit > quota > forbidden > auth > network (write it in a docstring). Within the winning class, take the message with the latest cursor and derive reset from that same message.
  - No such record, a truncated message (MAX_SAFE_LOG_BYTES/2) with no match, missing cursors, or a non-provider failure (for example a reviewer's declared failure) give unknown. No watch replay is needed; the execution id is used only for grouping.
- R-4 Reset text. Store an optional `reset` next to `cause`, for limit only. It is the text after `resets ` up to `;`, CR, LF or `<`, at most 96 characters. An empty, overlong or control-bearing value is dropped. Both fields pass `scrub` before persistence. A record without them (old format) loads and means unknown with no reset; `validate_run` accepts both fields as optional: if present, cause must be an allowed enum string; reset must be a nonempty string of at most 96 characters and requires cause=limit; invalid combinations are rejected.
- R-5 Display. The failed attempt's line and its end view show one catalog line with a remedy:
  - every known class is prefixed "В одном из выполнений зафиксировано: " (observational, R-3);
  - limit: "лимит провайдера; сброс: <reset>" when a reset is known, else "Лимит провайдера; проверьте лимиты аккаунта и повторите позже.";
  - quota: top up the account;
  - auth: [l]/`zplan login`;
  - forbidden: check the account or region;
  - network: retry later;
  - unknown: exactly today's text.
  New catalog families are `run.limit`, `run.quota`, `run.auth`, `run.forbidden` and `run.network`, with REFERENCE regenerated. Only catalog text and the safe reset are rendered, never the raw matched diagnostics (the 403 carries an HTML body).
- R-6 Read contract.
  - The read goes through the run's frozen binding/run_id/worktree, once, during a failed conclude. There are no reads for stopped, successful, pre-dispatch or legacy records, and none in a poll loop.
  - Timeout 30 s. Retention is bounded while reading, in bytes (256 KiB). After an overflow the leading partial JSONL record is discarded and never classified through the flat-format fallback; only complete retained records are classified.
  - A nonzero exit, a timeout or a read failure gives unknown. CLI stderr is not provider evidence.
- R-7 Diagnosis only. Nothing is retried, resumed or restarted because of the cause. The engine may retry once by itself when retryable and unused (provider_process.rs:424); zplan adds nothing.

Acceptance criteria (deterministic fixtures, no real provider):
- A-1 Native-envelope fixtures built from the four excerpts give limit (reset "3:10am (Europe/Moscow)"), forbidden, auth and quota. A synthetic unknown provider error, a plain review rejection, and a retry-recovered provider error (other execution id) followed by a reviewer's `Node ... failed` record give unknown. A provider retry diagnostic in the same execution as the latest observed execution failure is used. An auth failure in E1, a successful re-execution, then a reviewer rejection: the stored cause is auth, rendered with the observational prefix (not a terminal-cause claim). A provider limit, a retry, then `Node … failed: … result did not match the node contract` in the same execution gives unknown. Two classes in the evidence follow the precedence; a run-wide `run <reason>` record is never decisive. Existing flat extraction formats remain supported; causes follow R-2. Planner rendering preserves its existing families and wording.
- A-2 Both UI surfaces (the attempt line and the end view) show the cause and its remedy for `failed` and `failed_recoverable`, and the cause survives a reload. Unknown shows today's text unchanged.
- A-3 Edge cases: malformed or truncated envelopes, empty and oversized output at 262143/262144/262145 bytes including a multi-byte character at the cut, an HTML body, a credential-like token in the message, and reset boundaries (95/96/97 characters, control characters). The stored and rendered text holds no HTML, no token and no raw diagnostic.
- A-4 A bounded generator (fixed seed, <= 200 cases) over envelope sequences checks the stored cause against an independent oracle of R-2/R-3.
- A-5 Reads (spy): exactly one read on a failed conclude; none for stopped, successful, pre-dispatch or legacy records; no retry, resume or restart call. A timeout or nonzero exit gives unknown.
- A-6 Regressions: new-behavior tests fail on the base for the intended assertion. Compatibility and no-retry checks pass on both. Record the exact commands and base failures. The planner failure tests stay green.

Size: ~300-450 lines with tests.
Out of scope: auto-resume (S4b), parsing reset times, Claude rate-limit system lines, upstream changes.
critic run-failure-cause-task: GO after 4 rounds (session 01a1508f-ff31-7780-9b41-31ceb7d3a788)
