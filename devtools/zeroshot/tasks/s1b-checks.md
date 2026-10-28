s1b-checks — 0.5 item S1b with S6 inside (docs/RELEASE_0.5_SCOPE.md S1b and S6 rows): G3 qualification. zplan runs the profile `checks` on an exported result commit, records the evidence per attempt (surviving restart), and attaches a bounded flake diagnosis to a failed check. Design: docs/PROCESS_PROFILE.md "Profile" (`checks`) and "Stages on native graphs" (Merge gate). DeepSeek worker, sol reviewers.

Base: main with s1a1-task-gate merged; S1b reuses its gate-record store pattern. Record the base commit in the receipt. The audit is on main 74f1a3b: re-check every line number on the base, and re-gate if a premise moved.

Audit (74f1a3b):
- Profile checks:
  - `validate_check` process.py:119-135 gives `{name, argv, timeout_s}`; the list is ≤8 (`MAX_CHECKS` :39), with a default timeout of 1800 (:41).
  - `resolve` defaults to `[]` (:305).
  - Display at :725-728 / :744-748: "проверки (для следующих этапов)" / "без квалификации" (`NO_QUALIFICATION` :46).
  - Nothing executes checks today.
- Export:
  - `Runs.evaluate` runs.py:958 freezes `result = {branch, tree, commit: None}`.
  - `Runs.finish` :1043-1079 creates the branch (export.py:74), sets `result.commit` and delivery="awaiting_merge".
  - The record schema check is at :468-485 (`result` keys exact).
  - `Runs.merge` :1081-1128.
  - `Delivery.merge` delivery.py:804-814 calls `guard("merge")`, which raises `process.unbuilt` (process.py:656-657).
- Helpers to reuse:
  - clean checkout: `git worktree add` runs.py:710-724; disposable clone engine.py:701;
  - runners with timeout: export.py:35 (sanitized env :20-33), runs.py:496, engine.py:129 (group kill);
  - capture: live.py:231 `tail`, live.py:362 `scrub`. Reuse live.py's streaming capture/scrub algorithm, not tail() as the check runner. Capture stdout and stderr, preserve exit status, and kill/reap the process group on timeout.

Read: those locations; terminal_planner/process.py, runs.py, delivery.py, export.py, live.py, authority.py (the s1a1 gate record type); cli.py and tui/controller.py, tui/app.py merge paths; catalog.py; docs/PROCESS_PROFILE.md; tests/test_process.py, test_runs.py (DeliveryTests :818, CrashWindowTests :519), test_live.py (TailTests :437), and the s1a1 tests.

Rules:
- R-1 Scope. Active only when the resolved config has `gates.merge == "required"`. With "off" (preset `/1`), every record, digest, screen, refusal and the merge path stay byte-identical to the base. With "required", merge still refuses until S1c's critic exists: keep `process.unbuilt` for the critic part, using a catalog message that says checks are recorded but the merge critic is not built.
- R-2 Run. After `finish` (awaiting_merge), an explicit owner action runs the qualification. It is a TUI key and a plain/CLI command, named in the catalog.
  - zplan creates a clean checkout of exactly `result.commit` outside the project checkout, under zplan's data dir, and verifies that its tree equals `result.tree`.
  - Each check's argv runs there in profile order, sequentially, with `timeout_s`, the sanitized environment and process-group kill on timeout. Execution never goes through a shell. Fail-fast: after the first failing check (nonzero, timeout, spawn failure) the rest are recorded as `not_run` (gate6).
  - The checkout is removed afterwards, also on failure and timeout.
- R-3 Evidence. Each qualification is its own Authority record and is never overwritten. It holds:
  - attempt id, result commit and tree;
  - destination HEAD at start;
  - checks digest (the digest of the resolved `checks` list);
  - per check: name, argv digest, exit status / `timeout` / `spawn_failed` / `not_run`, duration, and a bounded scrubbed output tail (reuse live.py; at most 200 lines / 32 KiB per check);
  - the overall outcome `passed` iff every check exited 0.
  It follows the plan submission discipline: an `uncertain` marker is recorded before any process starts. A restart finding `uncertain` reports "квалификация прервана" and offers a rerun; it never reports a pass.
- R-4 Validity. A qualification counts for merge only if the attempt's result commit and tree, the checks digest and the destination HEAD equal the live values. Otherwise it is "квалификация устарела" with the rerun key.
- R-5 Flake diagnosis (S6), offered only on a failed check. The owner action reruns that one check N times on the candidate commit and N times on the destination HEAD (base), alternating, in fresh clean checkouts with the same env and timeout.
  - N comes from `limits.flake_reruns`: an optional profile limit 1..10, default 4 when absent. Absent must not change existing digests, the same pattern as S9b1's `plan_tokens`. If S9b1 is not merged yet, follow the same optional-limit rule directly.
  - Freeze the candidate and base commit/tree identities before diagnosis; base is the qualification's recorded destination HEAD. Refuse stale qualification. Record both identities and reuse R-2's execution, timeout, cleanup and capture rules for every rerun.
  - Every run's result is kept in a diagnosis record attached to the qualification record.
  - Let b/c be failed-exit counts on base/candidate. Any timeout, spawn failure or incomparable environment => unclear. Otherwise: candidate_regression iff b=0 and c=N; candidate_flake iff b=0 and 0<c<N; preexisting_flake iff 0<b<N and c>0; unclear otherwise. Always show counts; these labels describe observations, not proof of causation.
  - A diagnosis never changes the qualification outcome. A failed qualification stays failed, and nothing in S1b lets a failed qualification count as passed.
- R-6 Display. Show the qualification state per done attempt (не запускалась / идёт / прошла / не прошла (check name) / прервана / устарела). `[i]` shows per-check status and tail, and the diagnosis table. Same text in TUI and plain. With `checks: []`, show "без квалификации"; the action is not offered and nothing is recorded. REFERENCE.md is regenerated.

Acceptance (unit tests, deterministic fixtures; checks are tiny local scripts in a temp git repo):
- A-1 Off is identical: golden comparison with `gates.merge` off, preset `/1`.
- A-2 Run: pass/fail/timeout/spawn-failure checks yield exact records.
  - The checkout tree equals `result.tree`; a tampered tree is refused.
  - The checkout is removed in every outcome.
  - No shell: an argv with `;` is passed literally.
- A-3 Restart: fault injection after the `uncertain` marker -> restart -> "прервана", never passed; the record is not overwritten.
- A-4 Validity: each of commit/tree/checks digest/destination HEAD changes -> stale.
- A-5 Diagnosis: a seeded check that fails deterministically or by a counter file produces each verdict. All 2N results are stored; the qualification outcome is unchanged. Timeout -> `unclear`.
- A-6 Scrub and bounds: a secret-shaped line is scrubbed in the stored tail; the tail is capped.
- A-6b Exhaustively test verdicts for all b/c counts at N=1,4,10; absent flake_reruns means 4 without changing stored config/digests; reject bool, 0 and 11. Test stderr capture, a descendant holding a pipe after parent exit, streaming bounds, and UTF-8 tails at 199/200/201 lines and 32767/32768/32769 bytes. Assert both final caps.
- A-7 Base failure: compatibility tests pass on base. A regression through an existing Delivery entry point (qualify after finish with `gates.merge: required`) fails on base. Report named failures and skips separately. Compatibility assertions pass on base. Behavioral regressions must reach a named assertion through an existing production entry point using base-supported fixtures; import/missing-symbol/setup failures and skips do not count. Map candidate-only invariants to killed mutations. Recheck the selected regression on the actual prerequisite base. The base regression may use the existing `Delivery.end` path: assert the qualification action is offered.

Not in this task: the merge critic, release mode and override of a failed qualification (S1c); `zplan status` truth (S1c2); preset `/2` (S1d).

Size: about 700-1000 changed lines including tests, above the ~500-line review trigger; kept together because executor, evidence store and diagnosis share one record and one runner. 1500 is a mandatory re-gate point, never a reason to cut acceptance.

DoD:
- Unit tests pass.
- REFERENCE.md and USER_FLOW.md updated; PROCESS_PROFILE.md marks G3 checks as built.
- Receipt: base commit and the A-7 counts.
