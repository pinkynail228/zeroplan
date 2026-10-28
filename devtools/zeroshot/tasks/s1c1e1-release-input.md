Deferred to 0.5.x (critic gate22): not launched for 0.5. Pre-launch note: the release flag is read from the approved revision the run is bound to, `authority.state["revisions"][r["plan_revision"] - 1]["proposal"]` (version = index + 1, authority.py:704-716 at 8f1f62c), never from `Delivery.plan()` (delivery.py:321, the current revision); re-check that accessor on the launch base.

s1c1e1-release-input — 0.5 item S1c, slice 5a of devtools/zeroshot/tasks/s1c1-merge-gate.md (the parent; its R-4, A-1, A-3b, A-4 and A-5 texts apply verbatim where cited; parent ID map in s1c1a-merge-gate-core.md, where "s1c1e" means this pair). Release mode in the schema, the store and the merge rule; the owner entry screens are s1c1e2-release-ui.md. DeepSeek worker, sol reviewers.

Base: main after the s1c1d1/s1c1d2 pair integration. Lines below are cited at main 8f1f62c and will move. Record the actual base and this brief's sha256 in the receipt, re-check every cited line, and re-gate if a premise moved.
- Consumes, unchanged: s1c1b's frozen contract (gate record, `run_merge_gate`, `validate_merge_gates`, `evidence`); s1c1c's R-3 rule and `merge_gate_state`; s1c1a's `identity`/`identity_matches` and its R-4 clause that a seventh key `release_digest` may be added only when present. If any differs, stop and re-gate.

Order: s1c1d1/s1c1d2 → s1c1e1 (this) → s1c1e2. Between the two merges a release milestone under `gates.merge: required` refuses merge with `merge.release_missing` and no key names the entry (s1a1b2 precedent); non-release milestones and off presets are unaffected.

Frozen contract (this slice defines it; s1c1e2 and s1c2-status-truth consume it):
- Plan: a milestone may carry `release`, a strict boolean; absent = non-release.
- Store: `state["release_inputs"]`, optional, absent until the first record, `[]` never written, append-only. Record exact keys `{id ("release-input-" + uuid4), run: {plan_revision, milestone, attempt}, version, decision, proposed_verdict, checklist: [{check, status, note}], digest, created}`; `note` is a string ("" when not given); `digest` = authority `digest` of the record without `id`, `digest`, `created`.
- Functions: `merge_gate.release_input(version, decision, proposed_verdict, checklist, checks)` → the record body or `Blocked` (family `merge.release_input`); `merge_gate.validate_release_inputs(state)`; `Delivery.set_release_input(r, version, decision, proposed_verdict, checklist)` (appends; the newest record of the attempt is live); `Delivery.release_input(r)` (read-only, newest or None); `Delivery.is_release(r)`.

Write-set (exclusive for this slice):
- authority.py: `validate_proposal` milestone records :264 — keys equal `["id","title","depends_on","slices"]` or that set plus `release`; `release` must be `True` or `False` (`type(x) is bool`; 0/1/"true"/None refused, "поля записи"); `validate_state` :419-437 ("release_inputs" allowed, one hook);
- engine.py: the planner prompt milestone schema line :610 adds "optional release (boolean, only for a release milestone)"; nothing else in any prompt or graph;
- merge_gate.py: `release_input`, `validate_release_inputs`, the optional seventh identity key `release_digest`, the release part of the gate context (`artifact` adds `release` only when present);
- delivery.py: the three functions above; `run_merge_gate` binds the live release input (stores the full record under the gate record key `release`, present only for release milestones, before dispatch) and `release_digest`; s1c1c's rule gains step 0 "release milestone without a live release input → `merge.release_missing`" at dispatch and at merge, and the live identity includes `release_digest` for release milestones;
- merge_gate.py `validate_merge_gates`: accepts the optional `release` record key (exact keys of a release input) and `identity.release_digest` only together;
- catalog.py: `merge.release_input`, `merge.release_missing` in the "Merge gate" group, generic remedies, no key named; docs/REFERENCE.md regenerated;
- new `tests/test_release_input.py`;
- the receipt `devtools/zeroshot/tasks/s1c1e1-release-input-receipt.md`.
Not touched: milestone.py (baseline keys :100-101 stay exact; `release` is read from the approved plan revision the run is bound to, through `authority.state["revisions"][r["plan_revision"] - 1]["proposal"]` (authority.py:704-716 at 8f1f62c), not `Delivery.plan()` delivery.py:321), runs.py, process.py, task_gate.py, qualification.py, flake.py, checks.py, cli.py, tui/*, existing tests and goldens, docs except REFERENCE.

Rules:
- R-1 Absence (parent R-4, A-1): a plan without `release` (and with `release: false`) yields the same proposal digest, plan record, baseline, gate records, identity (six keys), context and screens as base; no `release_inputs` key. `release: false` is a non-release milestone, digest-different from absent only because the plan text differs.
- R-2 Domain (parent R-4): `version` 1..128 characters, all `str.isprintable()`; `decision` 10..500 printable; `proposed_verdict` ∈ accepted | rejected; `checklist` has exactly one entry per frozen `baseline.checks` item, same order, `check` equal to that text (the last is `milestone.ALL_REQUIREMENTS`), `status` strict bool, `note` 0..500 printable. Boundaries: version 0/1/128/129, decision 9/10/500/501, note 500/501, a newline in any field refused (not printable), a reordered, missing or extra checklist entry refused.
- R-3 Size: the canonical JSON of the record body above 32768 UTF-8 bytes → `merge.release_input` before any write or dispatch, never truncated; 32768 accepted.
- R-4 Binding (parent R-4, R-5): `release_digest` = the live record's `digest`; a new `set_release_input` (any field, including one checklist status) makes an earlier gate stale (`merge.gate_stale`). The gate record stores the exact release record it was dispatched with.
- R-5 Requirement (parent A-5): for a release milestone under required, `run_merge_gate` and `Delivery.merge` without a live release input → `merge.release_missing`, no side effect; for a non-release milestone `set_release_input` → `action.refused` and nothing in the gate changes. Under off the release key is ignored everywhere (parent R-1).
- R-6 Override: the gate override of s1c1c R-5 is unchanged; `evidence(record)` adds `release` only when present, so a release decision is part of what an override digest binds.
- R-7 Fixtures: scratch paths and an isolated HOME/XDG only; no literal home paths.

Acceptance (tests/test_release_input.py; temp git repos; FixtureEngine merge-gate scenarios; plans from fixtures with and without `release`; no network). Each test names entry point, oracle and control.
- A-1 (parent) Off and absence: a plan without `release` → proposal digest, baseline bytes, gate record and identity equal to base goldens; `release: false` → non-release behaviour. Control: `release: true` adds the seventh key.
- A-3b (parent, release part): each R-2/R-3 boundary through `Delivery.set_release_input` (accepted/refused pairs, store unchanged on refusal); malformed plan values (0, 1, "true", None) → `validate_proposal` refused.
- A-4 (parent, release part): gate accepted, then one checklist status changed through `set_release_input` → `Delivery.merge` refuses `merge.gate_stale`; rerun → accepted → merges.
- A-5 (parent): release milestone, no input → `run_merge_gate` and `Delivery.merge` refuse `merge.release_missing` with no side effect; with input → dispatch, the gate record's `release` equals the stored record; non-release milestone → `set_release_input` refused, gate identity has six keys.
- A-S Store: malformed release records (unknown key, bad digest, checklist mismatch, `[]` written) → `store.invalid`, file unchanged; a gate record with `release` but no `release_digest` (or the reverse) → `store.invalid`.
- A-7 Base failure: through `validate_proposal`, a plan whose milestone has `release: true`: assert it is accepted. On base it fails by that named assertion (base: "поля записи"). Report named failures and skips separately.
- Mutations: (a) `release: 1` accepted; (b) truncation instead of refusal at 32769 bytes; (c) `release_digest` omitted from identity; (d) seventh key added for non-release milestones (A-1 golden); (e) checklist order not enforced; (f) the gate record storing a digest only, not the input; (g) `evidence` without `release`.

Size: estimated 470-540 changed lines, receipt and REFERENCE excluded: product ~210 (merge_gate ~100, delivery ~70, authority ~15, engine ~2, catalog ~15), tests ~260-330. Above 600: report the measured overrun and rationale in the receipt; merge requires explicit critic disposition (ORCHESTRATOR step 1).

Parallelism: authority `validate_proposal` and the planner prompt are shared with any plan-schema slice (S2/S3): serial. delivery/catalog serial with s1c2.

Out of scope: owner entry screens, merge question release line (s1c1e2); release-specific checks beyond the frozen baseline checklist.

DoD:
- Worker (targeted): `PYTHONPATH=.:tests python3 -m unittest tests.test_release_input tests.test_merge_rule tests.test_merge_gate_record tests.test_merge_gate tests.test_plan_gate tests.test_milestone tests.test_runs tests.test_toolchain tests.test_reference` passes, plus every test module importing authority.validate_proposal found by `rg -l validate_proposal tests/` (verify every module path on the base). No full suite.
- `git diff --stat <base>` lists only the write-set; `python3 -m terminal_planner.catalog --check docs/REFERENCE.md` prints "docs current".
- `python3 devtools/export_check.py` reports no home-path finding on the committed candidate.
- Receipt: base, this brief's sha256, file list, A-7 counts, the mutation table, the plan accessor cited.
- Orchestrator, before merge: the full suite on the Linux test host.
