s1b2a-qualification-records — 0.5 item S1b, slice 2a of devtools/zeroshot/tasks/s1b-checks.md (the parent; its R-* and A-* texts apply verbatim where cited). Split of s1b2-qualification-records.md by critic gate12 (~/zs-pause/critic/gate12.out:8-10, point 4): records, the action in Delivery and the display texts here; keys, handlers, R-8 and TUI in s1b2b-qualification-ui.md. DeepSeek worker, sol reviewers. Re-gate after s1b1b1r: critic regate-after-s1b1b1r GO WITH CHANGES (applied), session 01a1594a-a691-72a2-859a-8ac49e602d3f.

Base: main after the s1a1b1-gate-record merge (the generalised store hook, a hard prerequisite) and the S1b chain s1b1 → s1b1b1r → s1b1b2 → s1b1c (this slice comes next, then s1b2b). Lines below are cited at main 299c377 (product code identical to 28c2c29). They will move: s1a1b1 edits authority.py :429-437 and delivery.py; s1b1 adds terminal_planner/checks.py; s1b1b1r adds the guard, s1b1b2 `checks.sweep`, s1b1c the git deadline. Record the actual base and this brief's sha256 in the receipt, re-check every cited line, and re-gate if a premise moved.
- Consumes the s1b1 executor API (s1b1-check-executor.md R-2..R-5): `checks.qualify(project, commit, tree, checks, root)` → a refusal `{"refused": "checkout" | "tree_mismatch"}` or `{"checks_digest", "checks": [evidence...], "outcome", "commit", "tree"}`; evidence keys exactly `name, argv_digest, status, duration_s, tail`; status int | "timeout" | "spawn_failed" | "not_run".
- Consumes s1b1b1r-check-guard.md: inherited parent R-2/R-3, fail-closed R-C, interrupted-call limits R-D/R-X, and lease cleanup R-K; s1b1b2-check-sweep.md R-4/R-5; and s1b1c-git-bound.md R-1. Guard cleanup after zplan death has those contracts' bounds and limits, not an instantaneous or unconditional completion guarantee. Unconfirmed stops and removal errors may leave a lease pair for sweep. A rerun requires `busy == 0`; direct guard termination retains parent R-3's recovery limit.
- Mirrors, but does not change, the gate-record store frozen in s1a1b1-gate-record.md "Frozen contract".
- If the merged APIs differ from these texts, stop and re-gate.

Order: s1b1 → s1b1b1r → s1b1b2 → s1b1c → s1b2a (this: parent R-1, the R-2 action in Delivery, the R-3 record and marker, R-4 validity, R-6 texts; A-1, A-2r, A-3, A-4, A-5v, display-based A-7) → s1b2b (keys/handlers on plain and TUI, R-8, A-6u, action-based A-7, docs) → s1b3 (flake diagnosis; a new optional record key) → S1c (merge critic, override, removal of `process.unbuilt` for merge).

Decision: qualifications get their own list `state["qualifications"]`, not a field of the run record and not entries in `state["gates"]`.
- Why: a run record is strictly keyed (runs.py:60-69, `validate_run` :385) and is s1a1b2's write-set; `state["gates"]` is frozen for task gates. A separate list touches only the store-hook line s1a1b1 already generalised.
- Same pattern as gates: optional key, absent until the first record, `[]` never written; strict validation on every load; append-only (only the status transition below edits a record).

Write-set (exclusive for this slice):
- new `terminal_planner/qualification.py`: record construction, `validate_qualifications(state)`, `valid(record, live)`, `state_of(records, r, live, in_flight)` and the R-6 texts;
- authority.py: `validate_state` only — "qualifications" in the allowed set at :429 (as generalised by s1a1b1) and one hook next to :435-437;
- delivery.py: new `qualify(r)` and `qualification(r)` (read-only state); the `awaiting_merge` body line in `view` :779-782 and the `state_text` :336-355 suffix, only when R-1 is active; `next_step` :431-452 and `END_ACTIONS` :86-97 unchanged;
- catalog.py: one ERRORS group "Qualification (merge-gate checks)" after "Process profile" :353-368 (remedies name no key; s1b2b adds `[v]`); docs/REFERENCE.md regenerated;
- new `tests/test_qualification.py`;
- the receipt `devtools/zeroshot/tasks/s1b2a-qualification-records-receipt.md`.

Not touched: checks.py, check_guard.py, runs.py, process.py (s1b2b), cli.py and tui/* (s1b2b), task_gate.py, engine.py, setup.py (only `data_root` imported), commands.py, existing tests and goldens, all docs except REFERENCE.

Audit (299c377):
- Checks config: `validate_check` process.py:119-135, `MAX_CHECKS` :39, `DEFAULT_TIMEOUT` :41, `NO_QUALIFICATION` :46.
- Merge guard: `guard` process.py:693-711; `merge` → `process.unbuilt` :709-710. Called only from `Delivery.merge` delivery.py:842-855. `Delivery.end` :743-753 renders without the guard.
- Pure profile reads: `live_digest` :720-727, `roles` :729-737 use `status(write=False)`; bound profile `Authority.profile` authority.py:372.
- Run record: `result = {branch, tree, commit}` runs.py:486-492; `run_state` :235-246; `Runs.finish` :1093-1129; `Runs.merge` reads `refs/heads/<branch>` (:1143).
- End view: `END_ACTIONS` delivery.py:86-97; `build` :763-771; `next_step` :449-452 lists the labels of every `END_ACTIONS` entry.
- Store: `validate_state` authority.py:419-437; session lock :374-389 (one session per project: a `running` record seen by a new session belongs to a dead one).
- Data dir: `setup.data_root` setup.py:28; worktrees precedent runs.py:583.
- Reference invariants: tests/test_reference.py :339 (raise sites name a family), :372 (every family has a use site), :522 (generated blocks current).

Rules:
- R-1 Scope (parent R-1). Active only when the bound profile resolves `gates.merge == "required"` (read with `status(write=False)`) and `checks` is non-empty.
  - Otherwise every record, digest, store byte, screen, `Дальше:` line, key list and golden is byte-identical to base.
  - `required` with `checks: []`: the awaiting_merge body and the home row say "без квалификации"; nothing recorded.
  - No key, no end-screen action and no `Дальше:` label for qualification in this slice (gate12:8: no button that does nothing); `Delivery.qualify` is reachable only from code and tests until s1b2b.
  - `Delivery.merge` still refuses with `process.unbuilt`; its text is s1b2b's.
- R-2 Action (parent R-2 action part): `Delivery.qualify(r)`.
  - Admission, before any side effect: `r` is the latest attempt, `run_state(r) == "awaiting_merge"`, R-1 active; else `qualification.refused`. Never/missing/malformed profile → `process.pending`/`process.missing`/`process.invalid` (as `guard`). A `running` record of this run started by this session → `qualification.refused` ("квалификация уже идёт").
  - Inputs frozen at start: `commit`, `tree` from `r["result"]`; destination HEAD = `git rev-parse refs/heads/<destination branch>` (argv only); `checks` and `checks_digest` from the live resolved config.
  - Order:
    1. `checks.sweep(root)`, `root = setup.data_root() / "qualify"` (injectable like `worktrees`); `busy > 0` → `qualification.running` ("предыдущая квалификация ещё завершается"), no record;
    2. the read-only git read of the destination HEAD (it precedes the marker; no checkout, no check);
    3. save the record with `status: "running"` (the `uncertain` marker, atomic store write);
    4. `checks.qualify(project, commit, tree, checks, root)`;
    5. save the concluded or refused record.
    No checkout and no check or clone process exists before the marker is on disk.
  - Hard exit: executor cleanup follows the consumed contracts above. A SIGKILL leaves the persisted record `running`; R-5 applies. If `checks.qualify` raises an exception, including `KeyboardInterrupt`, attempt a best-effort save of `status: "interrupted"`, then re-raise the original exception; failure of that save may leave the persisted marker `running`. Do not assume executor cleanup completed. Product need: interrupted qualification must never become a passed record. The exception fixture injects one exception at the executor call boundary with no further interruption during the save; asynchronous completion or durable saving under another interrupt is a non-goal. Power-loss coverage is the files-only restart fixture, not fault injection inside store writes.
- R-3 Record (parent R-3), exact keys:
  - `id`: exactly `"qualification-" + str(uuid.uuid4())`, the full match of `qualification-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}`; `run` = {plan_revision (int), milestone (str), attempt (int)};
  - `commit`, `tree` (40-hex), `destination` = {branch, head} (head 40-hex), `checks_digest` (64-hex);
  - `status` ∈ running | concluded | refused | interrupted; `outcome` ∈ passed | failed | None; `refusal` ∈ checkout | tree_mismatch | None;
  - `checks`: the executor's evidence list verbatim ([] unless concluded); `created`, `updated` (the store's timestamp format).
  - Evidence entry types, exact keys: `name` str (a valid check name, process.py:119-135); `argv_digest` 64 lowercase hex; `status` an int (not bool) or "timeout" | "spawn_failed" | "not_run"; `duration_s` int or float (not bool), ≥ 0, 0 for `not_run`; `tail` str, "" for `spawn_failed` and `not_run`.
  - Consistency: running/interrupted → outcome None, refusal None, checks []; refused → outcome "failed", refusal set, checks []; concluded → refusal None, 1..`MAX_CHECKS` entries, `outcome == "passed"` iff every status == 0, every entry after the first non-zero/timeout/spawn_failed is `not_run`, no `not_run` before it.
  - `validate_qualifications(state)`: strict on every load. Unknown/missing keys, bad enums or types, an id outside the grammar, duplicate ids, a `run` naming no record in `state["runs"]`, a tail over 200 lines or 32768 UTF-8 bytes, or an inconsistent record → `store.invalid`. Never repaired.
  - Allowed edits: only running → concluded | refused | interrupted. Reruns append.
- R-4 Validity (parent R-4): `valid(record, live)` iff concluded, passed, and `commit`, `tree`, `checks_digest`, `destination.head` equal the live values. Any mismatch on a concluded or refused record → `stale`.
- R-5 Restart (parent R-3 marker): a `running` record not started by the current session shows "прервана", never passed. The next `qualify` first moves it to `interrupted`, then appends; only after `sweep` reports `busy == 0` (R-2 step 1).
- R-6 Display texts (parent R-6), one text through Delivery for plain, TUI and `zplan status`: не запускалась / идёт / прошла / не прошла (<check name>) / прервана / устарела; refusals "не прошла (рабочая копия не создана)" / "(дерево не совпало)". awaiting_merge body "Квалификация: <state>"; home `state_text` " · квалификация: <state>". No key names in these texts.
- R-7 Families `qualification.refused`, `qualification.running`: raised from `Delivery.qualify` (use sites for test_reference :339/:372); REFERENCE regenerated.
- R-8 Fixtures: every literal home path in tests is under `/home/user/`.

Acceptance (tests/test_qualification.py; temp git repos; FixtureEngine runs finished through `Delivery.end`; checks run `sys.executable -c ...`; no network; no sleep over 3 s). Each test names its entry point, oracle and control.
- A-1 Off: `Delivery.end`, `Delivery.home`, `cli.status`, `process.describe` with `/1` and with `gates.merge: "off"` plus checks: byte-equal to base goldens; no `qualifications` key. Control: required shows the body line. `required` + `checks: []` → "без квалификации", store unchanged. Under required the EndView actions equal base (no new action).
- A-2r Record path: `Delivery.qualify`: pass, fail (exit 3 on check 2 of 3), timeout, spawn failure, refused (tree mismatch, checkout refusal). Oracle: exact record keys and values; check 3 after a failure `not_run`; no `checkout-*` entry remains after confirmed cleanup without a filesystem removal error; unconfirmed-stop or removal-error leftovers follow the consumed R-C/R-K and sweep contracts. Control: running, needs_owner, integrated and a non-latest attempt → `qualification.refused`, store unchanged.
- A-3 Restart: a controlling `sys.executable` child runs `Delivery.qualify`; its check starts a descendant and writes a handshake file; the test SIGKILLs the child after the handshake (no SystemExit stub); then a new Authority session. Oracle: record `running`; group and leased checkout gone within the s1b1b1r A-H/H-1 test bound; "прервана", never "прошла"; a rerun runs `sweep`, moves the record to `interrupted`, appends a new one, the earlier one otherwise byte-identical; the delayed side-effect oracle from s1b1b1r A-H/H-1 passes.
  - Power-loss shape: a store with a `running` record plus a leftover checkout and lock with no holder (files only) → "прервана"; the next `qualify` sweeps (removed 1) and proceeds.
  - Busy: a leftover whose lock a live helper holds → `qualification.running`, store unchanged; after the helper exits it proceeds.
  - One `KeyboardInterrupt` object raised by the executor test double at the call boundary, with a functioning store and no second interruption → `interrupted` saved and the same object re-raised; no executor-cleanup completion oracle. Control: a concluded passed record in a new session shows "прошла".
- A-4 Validity: from a valid passed record, each alone → "устарела": commit, tree (fixture store), checks digest (edit zplan.process.json), destination HEAD (a commit on the destination branch). Control: an unrelated file outside the project does not; another milestone's work does not while the destination HEAD is unchanged (its merge into the destination does).
- A-5v Store: each malformed shape in R-3 → `store.invalid` on load, file unchanged.
- A-7 Base failure: through `Delivery.end` on an awaiting_merge attempt, `gates.merge: "required"`, one check, no record: assert the body contains "Квалификация: не запускалась". On base it fails by that named assertion. Run on base with a scratch commit; report named failures and skips separately.
- Mutations, each killed by a named test: (a) marker after the executor call; (b) a dead session's `running` shown as passed or идёт; (c) validity without destination HEAD; (d) without checks digest; (e) a qualify entry in static `END_ACTIONS` or a qualify label in `Дальше:` (A-1); (f) the body line with `checks: []`; (g) a rerun overwriting a record; (h) passed with a timeout entry accepted; (i) profile read with `status(write=True)`; (j) `Delivery.merge` no longer refusing under required; (k) qualify root inside the project; (l) `qualify` without `sweep` or ignoring `busy`; (m) the marker saved after `checks.qualify` created the checkout (spy).

Size: estimated 470-560 changed lines, receipt and REFERENCE excluded: product ~180 (qualification.py ~110, delivery ~45, catalog ~15, authority ~5), tests ~290-380 (the hard-kill harness reuses s1b1b1r's). Above 600: report the measured overrun and rationale in the receipt; merge requires explicit critic disposition (ORCHESTRATOR step 1).

Parallelism: with s1a1b2 (delivery different functions, catalog different group, REFERENCE regenerated by the second merge): parallel. With s2b2/s2b3: catalog only with s2b3 (different group), REFERENCE regenerated. With s1a1c1: both edit delivery `state_text`/`view` wiring; serial.

Out of scope: keys, handlers, `[i]`, TUI job, `UNBUILT["merge"]` text, docs (s1b2b); flake diagnosis (s1b3); merge critic (S1c); a subcommand (gate11 point 1).

DoD:
- Worker (targeted): `PYTHONPATH=.:tests python3 -m unittest tests.test_qualification tests.test_checks tests.test_runs tests.test_process tests.test_ux tests.test_task_gate_record tests.test_toolchain tests.test_reference` passes. No full suite.
- `git diff --stat <base>` lists only the write-set; `python3 -m terminal_planner.catalog --check docs/REFERENCE.md` prints "docs current".
- `python3 devtools/export_check.py` reports no home-path finding on the committed candidate.
- Receipt: base, this brief's sha256, file list, A-7 counts (named failures and skips separately), the mutation table.
- Orchestrator, before merge: the full suite on the Linux test host.
