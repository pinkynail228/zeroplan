Deferred to 0.5.x (critic gate22): not launched for 0.5. Pre-launch notes: (1) define one shared deadline/cancel contract for the whole diagnosis, covering checkout, every check run and worktree cleanup, before launch; the 2 x 10 x timeout_s bound below covers checks only; (2) the optional limit `flake_reruns` edits process.py next to s9b1's `plan_tokens`: serialize the two; (3) `qualification.current` now belongs to s1c1b (gate22), so this slice consumes it instead of defining it; the separate `state["diagnoses"]` list stays (gate22: correct).

s1b3a-flake-diagnosis — 0.5 item S1b (S6 inside), slice 3a of devtools/zeroshot/tasks/s1b-checks.md (the parent; its R-* and A-* texts apply verbatim where cited). Slicing: critic swarm05 c ("Bounded check executor -> qualification records/actions -> flake diagnosis"); this is the last link, split like s1b2 (critic gate12 point 4: the record/action core here, keys and `[i]` in s1b3b-flake-ui.md; no button that does nothing). DeepSeek worker, sol reviewers.

Base: main after the s1b2b-qualification-ui merge (so after s1b1 → s1b1b1 → s1b1b2 → s1b1c → s1b2a → s1b2b). Lines below are cited at main 8f1f62c and will move: s1b1b1/s1b1b2/s1b1c rewrite checks.py internals, s1b2a adds terminal_planner/qualification.py, `state["qualifications"]` and `Delivery.qualify`/`qualification`, s1b2b the `[v]` wiring and process.py `describe` edits. Record the actual base and this brief's sha256 in the receipt, re-check every cited line, and re-gate if a premise moved.
- Consumes, unchanged: `checks.qualify(project, commit, tree, checks, root)` and `checks.sweep(root)` as merged (s1b2a-qualification-records.md header lists their contracts); s1b2a's record (R-3), `valid` (R-4), the `running`/session rule (R-5), `Delivery.qualify` admission and root (R-2), families `qualification.refused`/`qualification.running`. If any differs, stop and re-gate.

Parent ID map (every S1b ID, one owner each; sub-parts named where the parent text spans slices):
| Parent ID | Owner |
|---|---|
| R-1 scope | s1b2a (the `UNBUILT["merge"]` text: s1b2b) |
| R-2 execution, checkout, cleanup | s1b1 (hard exit: s1b1b1 guard, s1b1b2 sweep, s1b1c git bound) |
| R-2 owner action | s1b2a (Delivery), s1b2b (key, handlers) |
| R-3 per-check evidence shape | s1b1 |
| R-3 Authority record, `uncertain` marker | s1b2a |
| R-4 validity | s1b2a |
| R-5 flake diagnosis | s1b3a (this) — deferred to 0.5.x (critic gate22) |
| R-6 state texts | s1b2a; `[i]` per-check lines s1b2b; the diagnosis table and its key s1b3b — deferred to 0.5.x (critic gate22) |
| A-1 | s1b2a (screens and keys: s1b2b) |
| A-2 | s1b1 (record path A-2r: s1b2a) |
| A-3, A-4 | s1b2a |
| A-5 | s1b3a — deferred to 0.5.x (critic gate22) |
| A-6 | s1b1 |
| A-6b capture, stderr, descendant pipe, tail caps | s1b1 |
| A-6b verdicts at N=1,4,10; `flake_reruns` absent/bool/0/11 | s1b3a — deferred to 0.5.x (critic gate22) |
| A-7 | executor mutations s1b1; Delivery base failure s1b2a; action-based s1b2b; diagnosis s1b3a (service) and s1b3b (action) — deferred to 0.5.x (critic gate22) |
| DoD docs | REFERENCE: each slice; USER_FLOW, PROCESS_PROFILE G3 checks: s1b2b; flake paragraph: s1b3b — deferred to 0.5.x (critic gate22) |

Order (0.5.x): … → s1b2b → s1c1b (defines `qualification.current`, critic gate22) → s1b3a (this) → s1b3b. Base moves to main after the s1c1b merge when launched.

Decision: diagnoses get their own store list `state["diagnoses"]`, each bound to one qualification id; the qualification record is never edited (parent R-3 "never overwritten"; s1b2a R-3 allowed edits stay exactly running → concluded | refused | interrupted). s1b2a's Order line called this "a new optional record key"; a separate list keeps that record immutable and follows s1b2a's own store decision.

Write-set (exclusive for this slice):
- process.py: the optional limit `flake_reruns` only — `_object` names for "limits" :172-173, the range check :174-180, `resolve` :315-320 (copy only when present), `complete` :328-337 (accept LIMITS or LIMITS + flake_reruns), and a pure `flake_reruns(config)` → int (4 when absent). `describe`/`bootstrap_lines` untouched (s1b3b);
- new `terminal_planner/flake.py`: `verdict(b, c, n, unclear)`, record construction, `validate_diagnoses(state)`, the rerun loop;
- authority.py: `validate_state` :419-437 — "diagnoses" in the allowed set and one hook (as s1b2a added for qualifications);
- delivery.py: new `diagnose(r)` and `diagnosis(r)` (read-only) only; `view`, `END_ACTIONS` :86-97, `next_step` :431, `state_text` :336 unchanged;
- catalog.py: none (families reused, R-7); docs/REFERENCE.md unchanged;
- new `tests/test_flake.py`;
- the receipt `devtools/zeroshot/tasks/s1b3a-flake-diagnosis-receipt.md`.
Not touched: checks.py, check_guard.py, runs.py, cli.py, tui/*, engine.py, task_gate.py, existing tests and goldens, docs.

Consumed interface (defined by s1c1b since critic gate22; this slice no longer writes qualification.py): `qualification.current(record, live)` → True iff `record["status"] in ("concluded", "refused")` and `commit`, `tree`, `checks_digest`, `destination.head` equal `live` (keys as in s1b2a `valid`). Outcome is not compared. `valid(record, live)` stays `current(...) and outcome == "passed"`.

Rules:
- R-1 Scope: parent R-1 via s1b2a R-1 (required and non-empty checks). Off, or `flake_reruns` absent: every record, digest, store byte, screen and golden is byte-identical to base; no `diagnoses` key is ever written unless a diagnosis ran.
- R-2 `limits.flake_reruns` (parent R-5): optional; domain int 1..10, bool rejected (`process.invalid`, same message shape as :179). Absent → no key in the resolved config, the snapshot or the config digest (`config_digest` :261 sees the same dict as base); `flake_reruns(config)` returns 4. Present → it is part of the config and its digest like any limit. Same rule as s9b1-run-budget.md R-1 (`plan_tokens`); if s9b1 merged first, reuse its optional-limit mechanism instead of a second one.
- R-3 Admission `Delivery.diagnose(r)`, all before any side effect, else `qualification.refused` with the reason in the text:
  - R-1 active; `r` is the latest attempt and `awaiting_merge`;
  - the newest qualification of `r` is `concluded`, `outcome == "failed"`, and `current` against the live values (else "квалификация устарела"); a refused or interrupted record is not diagnosable;
  - the failed check = the first evidence entry whose status is not 0 and not `not_run`; its name is in the live checks;
  - no `running` diagnosis or qualification of this session (else `qualification.refused` "диагностика уже идёт"); `checks.sweep(root)` reports `busy == 0` (else `qualification.running`); a dead session's `running` diagnosis is moved to `interrupted` first (s1b2a R-5 pattern).
- R-4 Frozen identities: candidate = the qualification's `commit`/`tree`; base = its `destination.head` and that commit's tree, read with the same read-only argv git read s1b2a uses for the destination HEAD, before the marker; `n = flake_reruns(live config)`; `check` = the live check of that name (same `checks_digest`, so same argv/timeout).
- R-5 Runs: save the record `running` first (atomic store write; no checkout or check exists before it). Then 2n runs alternating candidate, base, candidate, base …, each `checks.qualify(project, side_commit, side_tree, [check], root)` — a fresh checkout per run, the sanitized env, the check's `timeout_s`, cleanup and capture exactly as the executor. After each run append its entry and save (the only edit while `running`). Every run executes; none is skipped after a timeout.
- R-6 Record, exact keys: `id` = "diagnosis-" + uuid4 (same grammar as s1b2a's id); `qualification` (an existing qualification id); `check` (name); `n`; `candidate` = {commit, tree}; `base` = {commit, tree}; `status` ∈ running | concluded | interrupted; `runs`: list of entries, each exactly `{side, index, status, duration_s, tail, refusal}` where side ∈ candidate | base, index 0..n-1, status/duration_s/tail as s1b2a's evidence types, refusal ∈ checkout | tree_mismatch | None (a refused run has status "not_run", duration 0, tail ""); `counts` = {b, c} or None; `verdict` ∈ R-8 labels or None; `created`, `updated`. Consistency: running/interrupted → counts None, verdict None, 0..2n-1 runs in alternation order; concluded → exactly 2n runs in alternation order, counts and verdict set. `validate_diagnoses` strict on every load → `store.invalid`, never repaired (unknown/missing keys, bad types, duplicate ids, a dangling qualification id, tails over 200 lines or 32768 UTF-8 bytes, inconsistency).
- R-7 Families: reuse `qualification.refused` and `qualification.running` (raised from `diagnose`); no new family; REFERENCE unchanged.
- R-8 Verdict (parent R-5): b/c = runs with status ≠ 0 on base/candidate. `unclear` if any run is `timeout`, `spawn_failed` or refused (the "incomparable environment" of the parent: a side whose checkout cannot be made is not comparable; the env is identical by construction). Else: candidate_regression iff b=0 and c=n; candidate_flake iff b=0 and 0<c<n; preexisting_flake iff 0<b<n and c>0; unclear otherwise. `verdict` is a pure function over (b, c, n, unclear); counts are always stored.
- R-9 Independence: a diagnosis never edits a qualification record, never changes its outcome, `valid` or `state_of`; nothing in this slice lets a failed qualification count as passed.
- R-10 Restart: a dead session's `running` diagnosis reads "диагностика прервана" via `diagnosis(r)`, never a verdict; its stored runs stay. KeyboardInterrupt/exception from the executor → best-effort `interrupted`, then re-raise.
- R-11 Fixtures: scratch paths and an isolated HOME/XDG only; no literal home paths.

Acceptance (tests/test_flake.py; temp git repos; FixtureEngine runs finished through `Delivery.end` and qualified through `Delivery.qualify`; checks are `sys.executable -c ...` scripts that fail deterministically or by a counter file outside the checkout; no network; no sleep over 3 s). Each test names entry point, oracle and control.
- A-5 (parent): through `Delivery.diagnose`, one fixture per verdict: regression (fails on candidate only), candidate_flake (counter: fails on alternate candidate runs), preexisting_flake (fails on some base and candidate runs), unclear (timeout on one run; a base tree mismatch). Oracle: exactly 2n stored runs in alternation order, counts, verdict; the qualification record byte-identical before/after; `Delivery.qualification(r)` text unchanged; the qualify root empty afterwards. Control: a passed, stale, refused, interrupted or running qualification → `qualification.refused`, store unchanged.
- A-6b (parent, verdict part): `verdict` for every (b, c) in 0..n × 0..n at n = 1, 4, 10, against an independent table written in the test; `unclear=True` dominates.
- A-6b (parent, limit part): absent → 4, and `resolve`/`complete`/`config_digest` output byte-equal to base for /1 and for a file without the key; present 1 and 10 accepted and digested; True, 0, 11, "4", 4.0 → `process.invalid`.
- A-R Restart: a controlling `sys.executable` child runs `Delivery.diagnose`; SIGKILL after a handshake written by the third run; new session: "диагностика прервана", the stored runs intact, no verdict; the next `diagnose` sweeps, marks `interrupted`, appends a new record.
- A-S Store: each malformed R-6 shape → `store.invalid` on load, file unchanged.
- A-7 Base failure: the counted regression goes through the existing entry point `Profile.status` (process.py:546): a project file with `limits: {"flake_reruns": 4}` resolves with state "accepted"/present and `flake_reruns(config) == 4`; on base it fails by the named assertion on the state (base raises `process.invalid`). `Delivery.diagnose` is candidate-only: its behaviour is covered by A-5 and the mutations below, never counted as a base failure (a missing symbol is not behavioral evidence). Report named failures and skips separately.
- Mutations, each killed by a named test: (a) marker saved after the first checkout; (b) no alternation (all candidate first); (c) reuse of one checkout across runs (spy on `checks.qualify` calls); (d) verdict without the unclear rule; (e) b=0,c=0 labelled candidate_flake; (f) diagnosis editing the qualification record; (g) absent `flake_reruns` synthesised into the config (digest change); (h) bool accepted; (i) stale qualification diagnosable (drop destination HEAD from `current`); (j) base side using the live HEAD instead of the frozen one; (k) skipping remaining runs after a timeout.

Size: estimated 470-540 changed lines, receipt excluded: product ~200 (flake.py ~120, delivery ~45, process ~20, qualification ~8, authority ~5), tests ~270-340 (the hard-kill harness reuses s1b2a's). Above 600: report the measured overrun and rationale in the receipt; merge requires explicit critic disposition (ORCHESTRATOR step 1).

Parallelism: with s1c1a none (new files plus engine.py). With s9b1: both add an optional limit in process.py — serial (R-2). With s1a1c1/c2 and s1b3b: delivery — serial (s1b3b is next).

Out of scope: keys, `[i]` table, describe line, docs (s1b3b); the merge gate (S1c).

DoD:
- Worker (targeted): `PYTHONPATH=.:tests python3 -m unittest tests.test_flake tests.test_qualification tests.test_checks tests.test_process tests.test_runs tests.test_ux tests.test_toolchain tests.test_reference` passes (tests.test_qualification exists after s1b2a; verify every module path on the base). No full suite.
- `git diff --stat <base>` lists only the write-set; `python3 -m terminal_planner.catalog --check docs/REFERENCE.md` prints "docs current".
- `python3 devtools/export_check.py` reports no home-path finding on the committed candidate.
- Receipt: base, this brief's sha256, file list, A-7 counts (named failures and skips separately), the mutation table.
- Orchestrator, before merge: the full suite on the Linux test host.
