# s1a1b1-gate-record — receipt

0.5 item S1a, slice 2a of `devtools/zeroshot/tasks/s1a1-task-gate.md` ("the parent"; its Audit, R-* and A-* apply
verbatim where cited). Lane L2. DeepSeek worker, sol reviewers. Scope: the durable gate record + the dispatch
protocol + the service action + the native loopback qualification, with `process.unbuilt` kept (s1a1b2 removes it).
Slicing per critic swarm05 c as split by gate7 B; critic gate8 GO WITH CHANGES (applied in the brief).

- **Base.** Recorded base per the brief's admission note: `fa5ec74` (s2a2 + s2a2b; `s2a2-engine-wiring` merged at
  `03a2917`/`bc64c19`, s2a2b at `40a2189`). The candidates of the first five visits were written and tested in
  worktrees checked out at `bd6370f` ("s1a1b1 brief: admission note on the s2a2b base"), i.e. `fa5ec74` + the
  orchestrator's own STATE.md/CALIBRATION.md/brief commits; `git status --porcelain` was empty at the start of each.
  The numbers below name which commit they diff against.
- **Rerun provenance** (R-2's rerun seed paragraph; recorded separately, as the amendment requires):
  - **Seed** (preserved candidate, unreviewed round-5 changes included): `0830262` ("WIP s1a1b1 tail after
    force-stop"); its product/test bytes are exactly `23f3530`'s (the tail commit only wrote the receipt), and both
    are ancestors of the launch HEAD, so the accumulated implementation is what this run reviews -- the seed is not
    the review baseline.
  - **Baseline** (the current main incorporated into the branch before launch; the review and compatibility
    baseline): `600122e` ("s1a1b1/s1a1b2 briefs: critic s1a1b1-regate GO WITH CHANGES applied"). It contains no
    s1a1b1 implementation. The candidate's own numbers diff against it (`git diff --numstat 600122e`), the earlier
    visits' against `fa5ec74`/`bd6370f` as their text says.
  - **Launch HEAD**: `5a76c61` ("Merge branch 'main' into zs-s1a1b1-gate-record"), the seed branch with `600122e`
    merged in. The published brief and the code below are checked out here; the deliverable enters through
    `git add --all` on top of it.
  - **Submitted brief**: `devtools/zeroshot/tasks/s1a1b1-gate-record.md` at the launch HEAD, sha256
    `21c2e11af0161f3f56c6f8f17d8cf5c0352edce41120657d9e1b33cddfeece63` (the re-gate amendment of 2026-10-20
    included). The first five visits were written against the pre-amendment brief, sha256
    `2c0b211d0bd50ba8adf21cd8b5c99ad4a60229cbe0300ed485410ddeb269777e`; this visit re-read the amended brief and
    added what it requires (the nesting depths, the schema-directed generator, both retry paths -- "the fifth visit"
    below).
- **Brief.** `devtools/zeroshot/tasks/s1a1b1-gate-record.md`, submitted sha256
  `21c2e11af0161f3f56c6f8f17d8cf5c0352edce41120657d9e1b33cddfeece63` (pre-amendment
  `2c0b211d0bd50ba8adf21cd8b5c99ad4a60229cbe0300ed485410ddeb269777e`, the first five visits).
- **Audit re-check.** Every line cited in the parent's Audit was re-checked on this base; the premises still hold
  (`prepare`/`proposal` are the plan protocol mirrored here; s2a2's `recorded_engine`, `engine_for`, `codex_home`
  and the `prepare` binding writer are present and unedited; `phase(status, run_id)` and `OBSERVED_RUNS` exist and
  are reused). Every cited line had moved (the brief cites `6a537b5`; the candidate's own numbers are given, the
  lines the gate itself adds included): engine.py `task_gate_graph` 787→835, `task_gate_runtime` 856→904,
  `task_gate_input` 863→911, `prepare` 1034→1159, `proposal` 1109→1235, `observe` 1231→1423 (`gate_observe`; the
  plan `observe` at 1516), `invoke` 964→1089, `FixtureEngine` 208→208; authority.py `validate_state`
  427–437→419–441, `validate_receipt` 841→845, `override_matches` 828→832, `atomic_state` 98→98; runs.py
  `bootstrap_manifest` 142→142, `build_documents` 355→355, start's effective artifact 653–654→661–662,
  fixture binding 418→418 and 1494–1495→1506–1507. **No premise moved** (s2a2 touched `prepare` and `proposal`:
  the binding compare now runs in the record's own home, `with_home`; the gate path copies the *current* writers,
  never a stale one).
- **Size** (whole diff except this receipt; `git diff --numstat 600122e`, new files counted whole; the first five
  candidates are included -- four rejected outright and the fifth force-stopped and preserved as the rerun seed;
  the orchestrator's `0830262` preserves that seed's bytes; the sixth candidate's product bytes equal them, and
  the seventh, eighth and ninth visits add the changes the bullets below name):
  - product **746 insertions + 16 deletions = 762** — `terminal_planner/task_gate.py` +342/−7, `engine.py`
    +243/−4, `delivery.py` +147/−3, `runs.py` +8, `authority.py` +6/−2. The brief estimated ~220.
  - tests **1730** (`tests/test_task_gate_record.py`, new, 62 methods). The brief estimated ~300–350.
  - **core+tests = 2492 against the 600 ceiling (overrun 1892).** `devtools/task_gate_qual.py` **279** against the
    200 ceiling (overrun 79); **total 2771 against 800 (overrun 1971).** Measured overruns, for the orchestrator's
    step-1 disposition (exceeding a limit needs an explicit critic decision); the rationale is below.
  - The ninth visit (this one, the ninth candidate) added product **+28** (`task_gate.py`: the store's own read in
    `persistable`, the explicit `OUTPUT_NESTING_LIMIT` and the iterative `too_deep`, plus the rewritten refusal
    diagnostic and docstrings) and tests **+62** (the past-limit depths, the reader-permissive and reader-refusing
    stubs and the updated class docstrings), against the acceptance reviewer's finding -- no requested behaviour
    weakened, nothing reverted.
  - The eighth visit (the eighth candidate) added product **+2** (`task_gate.py`: the type-preserving
    comparison of the persisted discussion with the parsed one) and tests **+19** (the nested wrong-type shapes of
    `RecordSchemaTests`), against the acceptance reviewer's finding -- no requested behaviour weakened.
  - The seventh visit (the seventh candidate) added product **+31** (`engine.py`: the gate's own run-id
    identity check in `gate_observe` and the `gate_confirmed` normalisation, no deletion) and tests **+45** (the
    six-case `ReceiptTests`, the run-id cases of `TerminalIdentityTests` and the portable 5000-depth case), against
    the reviewers' three findings -- no requested behaviour weakened, nothing reverted.
  - The sixth visit (the sixth candidate) added tests **+143** and no product line (54 → 59 methods,
    three classes; `RecordSchemaTests`, three `PersistenceTests` methods and the run-id case of
    `TerminalIdentityTests`): the re-gate amendment of 2026-10-20 asks for the nesting depths 1/400 and a bounded
    schema-directed generator, and its fault model asks for both retry paths, a fault-free control and the
    unchanged earlier records -- all of them test-side only, which is why this deliverable's product bytes equal the
    seed's.
  - The first repair visit added product **+110** and tests **+312** (25 → 35 methods); the second added
    product **+46** (`task_gate.py` +24: the loop guard, the context-kind type check, `contextual_digest`;
    `engine.py` +14: the recorded-engine selection in `gate_bound`, the observed-source check in `gate_observe`,
    `gate_prepared`; `delivery.py` +8: `task_gate_recovery`) and tests **+162** (35 → 39 methods, six new
    class-level checks). The third added product **+65** and tests **+227** (39 → 48 methods, eight more class-level
    checks; `task_gate.py` +80: `persistable`/`escaped`/`submitted_title`/`concluded`, the UUID4 regex,
    `validate_candidate`; `engine.py` +18: the title/size intent check, the `task_gate.SIZE` constant and the two
    `concluded` delegations). The fourth repair visit (the fifth candidate) added product **+25** and
    tests **+163** (48 → 54 methods, three more classes; `task_gate.py` +4: `RecursionError` joined
    `persistable`/`validate_candidate`/`contextual_digest`/`parse_evidence`/the `validate_gates` guard and the
    envelope-depth check in `concluded`; `engine.py` +5: the malformed-receipt normalisation in `gate_run`;
    `delivery.py` +16: `task_gate_published`, the conditional rollback in `task_gate_new` and the serialization
    round trip in `task_gates`). The totals include the 16 deleted product lines the earlier figures omitted.
  - Rationale: the estimate predates the record slice's own breadth — one strict schema (24 record keys, 4 binding
    shapes, 8 statuses, an override shape), the engine's prepare/submit/observe/conclude path *plus* its fixture
    counterpart, the delivery admission + freeze + create + observe + rerun API, the pure `gate_manifest`, and a
    qualification script that must first approve the plan revision the gate needs over the same provider. The tests
    are 54 and each acceptance group names its own entry point, oracle and control (10 acceptance groups, 40 named
    mutations over the five visits, one class-level regression check per demonstrated violation), so the
    per-criterion size is ~25 lines, not the ~10 the estimate implies. Nothing of s1a1b2 (validity, barrier, admission field, LINEAGE, override writing,
    `unbuilt` removal) or s1a1c (keys, commands, display, docs) is absorbed; the product code follows this repo's
    commented style (every function has a docstring). s1a1a landed at 767 changed lines against a 600 ceiling with
    the same class of note.

## Repair (second candidate: the first was rejected by both reviewers)

Nine demonstrated violations were repaired in place; each names the finding, the fix and the regression test that
fails when the fix is removed (mutations k–v below). No requested behaviour was weakened and nothing was reverted.

1. **Strict store validation (R-2/R-5, A-4s).** `validate_gate` now checks the record against the store and against
   its own output: the revision exists and is approved with that approval identity, the milestone is one of its
   proposal's, the context has the `runs` owner-context shape, `rounds_limit` is the config's own int, and for a
   `concluded` record the persisted verdict, discussion and round count equal `read_review` of its own
   `terminal["output"]` under its own limit (an `output_invalid` record must be one the parser refuses).
   `parse_evidence`/`validate_binding` turn every malformed shape into `store.invalid`, never a `TypeError`.
   `StrictStoreTests.test_concluded_evidence_and_references_are_validated_against_the_record`.
2. **Frozen native binding on every path (R-3/A-3h).** `NativeEngine.gate_bound` compares the record's four identity
   fields with the dispatching engine before any dispatch or watch and then routes through `engine_for`, so a
   `preparing` restart dispatches in the *recorded* home, and a moved state root or changed executable bytes refuse
   with `engine.identity_changed` instead of watching elsewhere.
   `BindingTests.test_a_preparing_record_dispatches_in_its_recorded_home`,
   `BindingTests.test_an_observation_refuses_a_moved_state_root_or_changed_binary`.
3. **A completed preparation is recovered (A-4l).** `gate_prepare` reuses the on-disk checkout while its three
   frozen files still hash to the record's own digests and its HEAD is the recorded one, instead of refusing every
   existing checkout with `engine.checkout`; the crash-interrupted preparation continues under the same record.
   `NativeRecoveryTests.test_a_preparation_that_completed_before_a_crash_is_recovered`.
4. **The authoritative profile (R-4).** Admission reads `Authority.profile` (via `status(write=False)`), never the
   `Planning` service's own profile, so an unbound authority refuses with `action.refused` even when the service
   holds a usable profile.
   `NativeRecoveryTests.test_an_unbound_authority_profile_refuses_despite_a_bound_service`.
5. **Process families before the plan conditions (R-4).** never/missing/malformed are raised before the approved
   revision and milestone checks, so a missing profile is never reported as `action.refused`.
   `RecordTests.test_the_bound_profile_state_precedes_the_plan_conditions`.
6. **Recovery before admission (A-4l).** `task_gate_go` selects the newest nonterminal record before any admission,
   so a live config that would refuse a new gate (`gates.task: off`) neither blocks the recovery nor changes the
   record, and `submission_unknown` still refuses with its own family; an empty store still refuses.
   `LifecycleTests.test_recovery_is_selected_before_any_live_admission`.
7. **One frozen configuration identity (R-4).** `task_gate_new` takes the config *and* the rule pairs from the one
   `status.resolved` and freezes the documents with them (`gate_owner_rules` → `process.freeze_rules`), so a rule
   rewritten between the resolution and the document construction refuses (`process.changed`) instead of freezing
   digest A over documents built from B. A rebuild of a never-dispatched record reads its own rule files and
   requires them to resolve to the record's `resolved_config_digest`
   (`FrozenConfigTests.test_a_rule_changed_between_resolution_and_documents_refuses`,
   `FrozenConfigTests.test_a_rule_changed_before_a_rebuild_refuses_with_intent_changed`).
8. **The qualification resumes slices (R-6).** `run_scenario` drives `run_task_gate` in a loop until the record is
   terminal or the scenario deadline passes, exactly as `plan_qual.run_scenario` drives `proposal`; a `SliceEnded`
   is an observation step, not a scenario failure
   (`QualificationTests.test_a_watch_slice_that_ends_is_resumed_until_the_record_is_terminal`,
   control `QualificationTests.test_a_terminal_record_takes_one_call`).
9. **Baseline compatibility counts** are recorded below (command, counts, and failures/skips named separately).

## Repair (third candidate: the second was rejected by both reviewers)

Six demonstrated violations were repaired in place; each names the finding, the fix and the regression test that
fails when the fix is removed (mutations a′, b′, e′, f′, g′, h′ in the table below). No requested behaviour was
weakened and nothing was reverted.

1. **Malformed contexts and escaped surrogates refuse the store (R-2/R-5, A-4s).** `validate_context` now requires a
   string `context["kind"]` before the closed-set lookup, and `validate_gates` wraps each record's check so a shape
   that makes a check itself raise (an unhashable kind, a JSON-escaped lone surrogate in an output digest) becomes
   `store.invalid` instead of a `TypeError`/`UnicodeEncodeError`. A context is additionally checked against the
   record it belongs to: `task_gate.contextual_digest` reproduces the record's own artifact from its revision,
   milestone and context, so a proposal candidate that is `{}` or carries an unknown key is malformed.
   `MalformedStoreTests.test_malformed_contexts_and_escaped_surrogates_refuse_the_store` (mutations g′, h′; the
   context-kind type check and the loop guard are two layers of the same refusal, so a mutation of one alone
   survives -- see the mutation table).
2. **The recorded engine is selected before its identity is compared (R-3).** `gate_bound` now resolves
   `self.engine_for(record["binding"])` first and compares the record's four identity fields with *that* engine, so a
   restart whose current binary lives at another path still observes through the recorded one while a rewritten
   recorded binary or a moved state root keeps refusing `engine.identity_changed`.
   `BindingTests.test_a_restart_on_another_toolchain_observes_through_the_recorded_engine` (mutation b′).
3. **Durable crash-boundary state (R-4/A-5, A-7a).** `ProtocolTests` closes and reopens the store at both crash
   boundaries and asserts the persisted status/run id/receipt, so a status only the crashed process kept in memory
   (or a save deferred past `--detach`) is no longer mistaken for durability (mutation a′, the same mutation as
   `a`, re-checked against the reopened-store tests).
4. **The observed source is the frozen HEAD (parent R-2 terminal identity).** `gate_observe` requires
   `value["source"]["revision"] == record["identity"]["head"]` for every projection it receives, exactly as
   `NativeEngine.observe` compares its own (`engine.intent_changed`), so a terminal envelope of another revision
   never concludes the record.
   `TerminalIdentityTests.test_a_terminal_envelope_of_another_revision_is_refused` (mutation e′).
5. **A completed preparation is recovered under its frozen configuration (R-4/A-4l).** `task_gate_recovery` passes
   no documents while the record already has its checkout and its three frozen files on disk (`gate_prepared`), so
   `gate_prepare` reuses them and a rule file rewritten after the preparation no longer refuses the recovery; a
   never-prepared record still rebuilds from its frozen configuration and refuses (`engine.intent_changed`) when the
   rules moved. `NativeRecoveryTests.test_a_rule_changed_after_a_completed_preparation_still_recovers` (mutation f′),
   control `FrozenConfigTests.test_a_rule_changed_before_a_rebuild_refuses_with_intent_changed`.
6. **Size reporting.** The totals now count the deleted product lines (product 611, core+tests 1681, total 1961 at
   that visit; superseded by the fifth candidate's figures, 701/2162/2441, its own being 676/1974/2253, and by the
   sixth candidate's reported at the head of this receipt, 701/2305/2584).

## Repair (fourth candidate: the third was rejected by both reviewers)

Four demonstrated violations were repaired in place; each names the finding, the fix and the regression test that
fails when the fix is removed (mutations w–bb below). No requested behaviour was weakened and nothing was reverted.

1. **An output the store cannot hold never crashes the writer (R-2/R-5, R-4/A-6b).** The single `task_gate.concluded`
   writer now checks `persistable` *before* hashing or decoding: an envelope that holds a raw unpaired surrogate
   becomes `output_invalid` with no terminal and no digest, and an output whose *decoded discussion* holds one is
   refused by `read_review`'s own persistence check (its escape keeps the outer JSON valid UTF-8, so only the parser
   can refuse it). Both fixture (`FixtureEngine.gate_run`) and scripted-native (`NativeEngine.gate_conclude`) paths
   delegate to it. `EvidenceTests.test_a_decoded_lone_surrogate_is_output_invalid_without_evidence`,
   `EvidenceTests.test_an_output_the_store_cannot_hold_leaves_no_terminal`,
   `NativeEvidenceTests.test_a_decoded_discussion_surrogate_is_refused_by_the_parser`,
   `NativeEvidenceTests.test_a_raw_surrogate_in_the_envelope_leaves_no_terminal`, control
   `NativeEvidenceTests.test_an_ordinary_unicode_output_still_concludes` (mutations w, x).
2. **Store validation refuses anything it cannot persist (R-5).** `validate_gate` requires `persistable(entry)` from
   the very bytes `canonical` writes, so a lone surrogate in a decoded discussion or in any plain field
   (`diagnostic`) refuses the whole store instead of loading and crashing the next writer.
   `PersistedEvidenceTests.test_a_persisted_discussion_with_a_lone_surrogate_refuses_the_store` and
   `PersistedEvidenceTests.test_a_lone_surrogate_outside_the_output_refuses_the_store` (mutation y). (The
   `terminal.output`-side escapes were already covered by `MalformedStoreTests`.)
3. **The frozen intent includes the submitted title and the runtime size (parent R-2 terminal identity).**
   `gate_observe` now requires the observed projection's `title` to be `task_gate.submitted_title(milestone)` and its
   `size` the frozen `task_gate.SIZE` (`"medium"`, the one `task_gate_runtime` freezes), next to the frozen HEAD, and
   refuses `engine.intent_changed` otherwise. `TerminalIdentityTests.test_a_projection_of_another_title_or_size_is_refused`
   (mutation z).
4. **The closed candidate shape and UUID4 identifiers (R-2/R-5).** `validate_context` hands a proposal's candidate to
   `validate_candidate`, which requires `runs.structured(canonical(candidate))` (exactly `{"tasks", "amendments"}`),
   so an unknown candidate key refuses even though it cannot change the artifact; `ID`/`KEY` now pin UUID version 4
   and the RFC 4122 variant for both `id` and `submission_key`.
   `CandidateShapeTests.test_an_unknown_candidate_key_refuses_the_store` (mutation aa) and the four new cases of
   `StrictStoreTests.test_concluded_evidence_and_references_are_validated_against_the_record` (mutation bb).

## Repair (fifth candidate: the fourth was rejected by both reviewers)

Four demonstrated violations were repaired in place; each names the finding, the fix and the regression test that
fails when the fix is removed (mutations cc–gg below). No requested behaviour was weakened and nothing was reverted.

1. **A malformed detach receipt is an unconfirmed submission (R-4/A-5).** `NativeEngine.gate_run` wraps
   `validate_receipt(receipt[0])` so every way a `--detach` receipt can be malformed -- `{}`, an empty `runId`, an
   extra key -- normalises to the existing `submission.unknown` family (the run may be live, so the record must stay
   `submission_unknown`) instead of letting the shape raise `store.invalid`. The record itself is written before the
   dispatch, so a restart observes the recorded run id and dispatches nothing.
   `ReceiptTests.test_a_malformed_receipt_is_an_unconfirmed_submission` (three cases: `{}`, `{"runId": ""}`, an extra
   key; each reopens the store and asserts `submission_unknown`, `--detach` exactly once and no second dispatch),
   control `ReceiptTests.test_a_well_formed_receipt_concludes`.
2. **A nested output crashes neither the write nor the listing (R-4/A-6b, R-5, frozen `task_gates` API).**
   `persistable`, `validate_candidate`, `contextual_digest`, `parse_evidence` and the `validate_gates` per-record
   guard all catch `RecursionError`; `concluded` checks the record at the depth the store writes it
   (`persistable({"gates": [record]})`, envelope included) before `digest`; and `task_gates` returns a serialization
   round trip (`decode(canonical(record))`) instead of `copy.deepcopy`, which cannot walk a refused 500-deep output.
   So an `output_invalid` record holding 500 (or 5000) nested lists is writable **and** listable, and a store the
   serializer cannot walk raises `store.invalid` instead of `RecursionError`.
   `NestedOutputTests.test_a_deep_refused_output_is_still_writable_and_listable` (the holdable depths 1, 400 and
   500, listed and on-disk ids; the sixth visit extended it to the amendment's full depth domain),
   `NestedOutputTests.test_an_output_deeper_than_the_store_can_write_leaves_no_terminal` (5000, whose
   holdability is the interpreter's -- the sixth visit made the case assert the invariant instead of one tuple) and
   `NestedOutputTests.test_the_record_is_checked_at_the_depth_the_store_writes_it` (a `canonical` stub that refuses
   only the `{"gates": [record]}` envelope pins the record-depth check; mutations dd–ff).
3. **A published record survives a failed save (R-2/A-4l).** `task_gate_new` rolls the append back only when the
   record never reached the store file: the new `Delivery.task_gate_published` re-reads `authority.path`, and if the
   failing `save` already published the `preparing` record (an `os.fsync` error on the directory descriptor after the
   atomic rename), the record stays in memory and on disk, so a retry recovers the same id instead of appending a
   second record over a durable first. `PersistenceTests.test_a_published_preparing_record_is_not_erased_by_a_failed_save`
   (mutation gg).
4. **The measured size is corrected.** The new test file was 1461 lines at this visit (not 1298/1301); product is
   685 insertions + 16 deletions = 701; core+tests 2162 against the 600 ceiling (overrun 1562); qualification 279
   against 200 (overrun 79); total 2441 against 800 (overrun 1641). The 16 deleted product lines the earlier figures
   omitted are now included. The sixth visit's test additions move this to the figures at the head of this receipt
   (tests 1604, core+tests 2305, total 2584).

## Frozen contract as implemented (this slice defines it; s1a1b2 consumes it unchanged)

- **Store.** `state["gates"]` is written only beside `runs` (`authority.py:430` becomes
  `set(state) - {"runs", "gates"}`), validated on every load (`authority.py:439-441`). It is absent until the first
  gate is created (`state["gates"].setdefault`, `delivery.py:684`); `[]` is never written and is `store.invalid`
  (`task_gate.py:185-187`). A store without a gate keeps its bytes (A-4r control, A-1).
- **Record** (`task_gate.record`, `task_gate.py:128-139`; keys `task_gate.py:104-107`; `task_gate.freezes` :123-125): exactly `gate` = `"task"`,
  `id` = `"task-gate-"+uuid4` (regex `task_gate.py:113-114`), `plan_revision`, `approval`, `milestone`, `context` (the
  effective owner context, deep-copied), `identity` = `task_gate.identity(...)` (the three keys),
  `config` (the frozen resolved config), `rounds_limit` = `config["limits"]["task_rounds"]`, `documents` (graph,
  runtime, input digests), `binding` (below), `submission_key` = `"zplan-gate-"+uuid4`, `status`, `run_id`,
  `receipt`, `terminal`, `output_digest`, `rounds_used`, `discussion`, `critic_verdict`, `override`, `diagnostic`,
  `created`, `updated`. Never rewritten in place: `save` only bumps `updated` (`runs.py:601-603`); a rerun and a
  lost session append (`delivery.py:711-737`).
- **`task_gate.evidence(record)`** (`task_gate.py:142-144`): the 11 evidence keys, in the order the parent names
  them.
- **`validate_gates`** (`task_gate.py:179-199`: the per-record loop that turns a raising check into
  `store.invalid`; `validate_gate` :201-243, `validate_context` :244-258, `validate_candidate` :260-270,
  `contextual_digest` :272-283, `validate_status` :285-328, `parse_evidence` :330-337, `validate_override` :339-350,
  `validate_binding` :352-367): strict.
  Unknown/missing key, bad enum, duplicate id, inconsistent terminal fields, a binding that does not match the
  store's namespace, an ill-shaped override, a context that does not reproduce the record's own artifact and
  `gates: []` all raise `store.invalid`. Native binding =
  `binary_identity()`'s four keys **plus** `codex_home` (`toolchain.BINDING_FIELDS | {"codex_home"}`, checked by
  `toolchain.valid_binding`); fixture binding = exactly `{"fixture_id": authority.fixture_id}`.
- **Statuses** (`task_gate.py:99-101`): nonterminal `preparing | submission_unknown | observing | detached |
  observation_blocked`; terminal `concluded | native_failed | output_invalid`. `concluded` alone carries
  `critic_verdict ∈ {accepted, rejected}`, a discussion, `rounds_used = len(discussion["rounds"])` (≥1); every other
  status has those three `None`. `terminal` (native `terminalResult`, `output` included) and `output_digest`
  (= `digest(output)` only for a succeeded terminal) are cross-checked.
- **Override.** This slice writes only `None`; `validate_gates` already accepts exactly `{reason, verdict,
  evidence_digest}` through `override_matches(evidence(record), override, verdict_field="critic_verdict", ...)` on
  a `concluded` record whose `critic_verdict` is `"rejected"`, and refuses it anywhere else (A-4o).
- **`MilestoneRuns.gate_manifest(milestone_id, plan_revision, context)`** (`runs.py:605-611`): pure; exactly
  `bootstrap_manifest(milestone.build_manifest(revision["proposal"], ...)[0], context)` — the same value
  `start` digests at `runs.py:661-662` — with no git read, refresh or persistence.
- **Start/observe/rerun API** (`delivery.py:607-737`): `run_task_gate(milestone_id, context=None, progress=...,
  slice=None)` → the newest record for (revision, milestone): nonterminal → recovered/observed with the same id,
  no new dispatch, `submission_unknown` still refuses with `submission.unknown`; none/terminal → a new record is
  created and dispatched. `rerun_task_gate` refuses while the newest record is nonterminal, else appends and never
  touches an earlier record. `task_gates(milestone_id)` is a read-only serialization round trip, newest last. A live config,
  rules or HEAD change never turns an observation into a new dispatch (frozen documents/config): a record whose
  preparation already finished on disk is recovered by reusing those files (`task_gate_recovery`, `gate_prepared`),
  so a rule rewritten after the preparation cannot refuse it.
- **Admission** (`delivery.py:617-639`: the bound profile's own state first): the live config comes from the bound `Authority.profile` via
  `status(write=False)` only; never/missing/malformed → the process family; an unbound profile → `action.refused`;
  otherwise `action.refused` unless `gates.task == "required"` on an approved current revision that contains the
  milestone. No caller Status is read (the method takes none).

## Acceptance → evidence (targeted runs; each test names its entry point, oracle and control)

- **A-4r records — `RecordTests`** (`tests/test_task_gate_record.py:200`): the exact record keys/values against a
  fixture `run_task_gate` (`:203`), every scenario's outcome (`:232`), native failures are not rejections (`:241`),
  a native-shaped binding in a fixture store is `store.invalid` (`:251`), and the refusals `/1`, `gates.task: off`,
  unapproved, unknown milestone (`:262`), the deferred-profile case (`:276`) and never/missing/malformed (`:285`)
  leave the store bytes, the sidecar bytes and the absence of `gates` unchanged; a profile state with *no* approved
  revision keeps its own family (`:300`).
- **A-4l lifecycle — `LifecycleTests`** (`:321`): a nonterminal newest record keeps its id and dispatches nothing
  (`:324`); an unconfirmed submission refuses (`:339`); a config/HEAD change during observation never dispatches
  (`:352`); the recovery precedes any live admission (`:365`); the rerun refuses nonterminal and appends after
  terminal, the earlier record byte-identical (`:392`).
- **A-4s/A-4o store — `StoreTests`** (`:418`): a valid two-record store loads (`:421`); each malformation refuses
  (`:426`); a valid override loads and accepted/nonterminal/native_failed/extra-key shapes refuse (`:463`). The
  evidence/reference class is `StrictStoreTests` (`:916`, its test at `:928`).
- **A-6b evidence — `EvidenceTests`** (`:479`): the malformed, inconsistent and over-cap outputs delivered through
  the fixture dispatch path become `output_invalid` with `critic_verdict` None and no discussion (`:482`); a
  well-formed output concludes (`:497`); a decoded lone surrogate (both ranges) is the same refusal with the
  well-formed Unicode control (`:502`), and an unholdable envelope keeps no terminal (`:527`).
- **A-5 protocol — `ProtocolTests`** (`:648`; the store is closed and reopened at each boundary): a crash after the
  detach receipt → the reopened record is `detached` with its run id and receipt, the restart observes the same run
  id, `--detach` exactly once and only `watch` on the restart (`:661`); a crash inside `--detach` → the reopened
  record is `submission_unknown` and the restart refuses with no dispatch (`:680`); a native `succeeded` without a
  parsable `taskVerdict` sets nothing (`:699`).
- **A-3h binding — `BindingTests`** (`:714`): the stored binding is the 5-key native shape with `codex_home` equal
  to the dispatching engine's env home; with a different home in the env the observation runs with the recorded
  home (`watch` env `CODEX_HOME`) (`:718`); a preparing record dispatches in the recorded home (`:739`); a moved
  state root or changed executable bytes refuse (`:760`); a restart whose *current* binary is another path observes
  through the recorded one while a rewritten recorded binary still refuses (`:796`); the 4-key control is the
  key-set assertion (mutation d).
- **A-1 off — `OffTests`** (`:841`, the test at `:844`): a required task gate still refuses a start with
  `process.unbuilt`.
- **Parent R-2 terminal identity — `TerminalIdentityTests`** (`:1400`): each identity field is checked on its own
  against a matching-projection control. A `finished` projection naming another revision is refused
  (`engine.intent_changed`) with the record left `observation_blocked` and no terminal, while the recorded HEAD
  concludes (`:1412`); a projection of another *nonempty* `runId` refuses `engine.intent_changed` like the other
  three identity fields, while an empty or absent run id stays the shared structural envelope validation's own
  `store.invalid` -- either way the record stays nonterminal and its own run concludes (`:1436`); a projection that
  renames the title or shrinks the size is refused `engine.intent_changed` and the unchanged projection concludes
  (`:1483`).
- **Repair classes** (the five rejections' findings): `RecordSchemaTests` (`:854`, the closed schema's own domain
  at `:900`: every `RECORD_KEYS` key missing, every key with a wrong JSON type, every nested discussion field with a
  wrong JSON type, one unknown key -- each generated shape a `store.invalid`, against a valid control),
  `StrictStoreTests` (`:916`, four UUID cases),
  `MalformedStoreTests` (`:957`), `PersistedEvidenceTests` (`:993`), `PersistenceTests` (`:1048`, the amendment's
  fault model: a fault-free control at `:1074`, an earlier record kept byte-identical and nothing dispatched at
  `:1082`, the reopened-`Authority` retry at `:1099` and the same-service retry at `:1118`), `NestedOutputTests`
  (`:1138`, depths 1/400/500 at `:1175`, 5000 at `:1185`, 5001/9990 at `:1207`, the reader-permissive stub at
  `:1227`, the reader-refusing stub at `:1244` and the envelope-depth stub at `:1263`),
  `CandidateShapeTests` (`:1279`), `FrozenConfigTests` (`:1315`), `NativeRecoveryTests` (`:1367`),
  `TerminalIdentityTests` (`:1462`), `NativeEvidenceTests` (`:1586`), `ReceiptTests` (`:1629`, the six unconfirmed
  cases at `:1651` and the control at `:1691`) and `QualificationTests` (`:1699`).
- **A-7 compatibility/mutations:** no base-failing entry exists until the barrier — the record is unreachable from
  a start while `process.unbuilt` is kept (`process.py:713-708` unedited), and this slice changes no start,
  preview, retry, answer, accept, digest or screen behaviour. So the parent A-7 "no base-failing entry" clause is
  vacuous here and is held by **s1a1b2** (which removes `unbuilt` in the same change as the barrier). Targeted
  modules pass on the base and on the candidate (below).

## Check results (candidate)

- Worker DoD: `TMPDIR=<scratch> PYTHONPATH=.:tests python3 -m unittest tests.test_task_gate_record
  tests.test_task_gate tests.test_plan_gate tests.test_plan_override tests.test_tui_plan_gate tests.test_process
  tests.test_runs tests.test_toolchain tests.test_reference` → **Ran 364 tests in 425s … OK** (0 failures, 0 errors,
  **0 skips**; macOS skips nothing here — the native protocol runs on the scripted `NativeEngine` harness, not the
  pinned binary). The new module alone: **59 tests OK**. Direct importers of the changed modules
  (`test_terminal_planner`, `test_live`, `test_run_cause`, `test_tui_chat`, `test_tui_live`, `test_tui_milestones`,
  `test_tui_polish`, `test_milestone`, `test_plan_qual`) → **Ran 506 tests in 849s … OK** (first repair).
  The fifth visit re-ran the direct importers it could touch: `test_home_wiring`, `test_lifecycle_guard`,
  `test_run_cause`, `test_plan_qual`, `test_fixture_scope`, `test_record_home`, `test_live`,
  `test_terminal_planner` → **Ran 316 tests in 515s … OK** (0 failures, 0 errors, 0 skips). The sixth visit changed
  only `tests/test_task_gate_record.py`, so the DoD command above (which imports `test_process`,
  `test_terminal_planner` and the plan-gate suites) re-covers every importer of the changed module.
- Worker DoD (seventh visit, the reviewers' three findings repaired): `python3` and `python3.13` each run
  `tests.test_task_gate_record` → **59 tests OK**; the full nine-module DoD command under `python3.13` → **Ran 364
  tests in 487s … OK** (0 failures, 0 errors, 0 skips). The reviewer's failing case
  (`NestedOutputTests.test_an_output_deeper_than_the_store_can_write_leaves_no_terminal`) and the two
  refusal-family cases (`TerminalIdentityTests.test_a_projection_of_another_run_id_is_refused`,
  `ReceiptTests.test_an_unconfirmed_receipt_is_an_unconfirmed_submission`) now pass on both interpreters. This
  visit changed only `tests/test_task_gate_record.py` and `terminal_planner/engine.py` (the gate's own run-id
  check in `gate_observe` and the `gate_confirmed` normalisation), so the DoD command re-covers every importer of
  the changed product module.
- Worker DoD (eighth visit, the acceptance reviewer's finding repaired): `python3` (3.9) and `python3.13` each run
  `tests.test_task_gate_record` → **59 tests OK**; the full nine-module DoD command under `python3.13` → **Ran 364
  tests in 456s … OK** (0 failures, 0 errors, 0 skips). `RecordSchemaTests` alone failed four of its generated
  nested shapes before the repair (`discussion.version` `true`/`1.0`, `discussion.rounds[0].round` `true`/`1.0`)
  and passes after it, on both interpreters. This visit changed only `terminal_planner/task_gate.py` (the
  comparison) and `tests/test_task_gate_record.py`, so the DoD command re-covers every importer of the changed
  product module.
- Worker DoD (ninth visit, the acceptance reviewer's finding repaired): `python3` (3.9.6) and `python3.13`
  (3.13.3) each run `tests.test_task_gate_record` → **62 tests OK**; the full nine-module DoD command under
  `python3.13` → **Ran 367 tests in 490s … OK** (0 failures, 0 errors, 0 skips). The reviewer's own reproducer
  (`/tmp/.../reproduce-unreloadable-gate.py`, `python3.13`, depths 5000 and 9990) exits 0: 5000 keeps its terminal
  (this interpreter holds it) and 9990 is refused with no terminal **and the store reloads and lists** -- the
  reported `store.invalid` is gone. `NestedOutputTests` alone → 6 tests OK on both interpreters. This visit changed
  only `terminal_planner/task_gate.py` and `tests/test_task_gate_record.py`, so the DoD command re-covers every
  importer of the changed product module.
- **Baseline compatibility** (`git archive fa5ec74` into a private copy, `git init` + one commit so the
  single-source test can read Git metadata, then the targeted command without `tests.test_task_gate_record` — that
  module is new in this slice): **Ran 305 tests in 337s … OK**: `failures=0`, `errors=0`, `skipped=0`. Named
  failure: none. Named skip: none. (The count is an earlier visit's; the fourth and fifth visits changed no
  base-visible surface, so it is recorded there and not re-run here; the sixth visit changed only the new test
  module, so the 305 base-visible tests of this command are the ones it re-covers -- 364 minus the module's 59.) A
  copy *without* Git metadata makes exactly one pre-existing check error
  (`test_toolchain.SingleSourceTests.test_no_version_or_archive_literal_outside_the_toolchain_module`, a
  `CalledProcessError` from `git ls-files`); it passes in the metadata-bearing copy above, so the artifact is
  harness-only. On the candidate the same command is 364/364 with no skips: no base-failing entry exists until the
  barrier (s1a1b2).
- `PYTHONPATH=. python3 devtools/task_gate_qual.py --help` runs (exit 0); the provider/harness import and a
  scripted answer were smoke-checked locally. The scenarios themselves are the orchestrator's Linux-host check
  (the worker does not run model/native qualification; a pinned binary is present locally but the qualification
  host is Linux).
- `python3 devtools/export_check.py` reads one commit, never the working tree, so the result depends on which commit
  it is pointed at. On the pre-commit checkout (`bd6370f`, which does not contain this slice's new files) it reports
  `summary: 0 findings` with the private-term rule skipped (exit 3). On the committed candidate it reports **no
  `home-path` finding** -- the DoD's requirement -- and exactly five content findings, every one a false positive in
  this slice's own new files and none a secret: three `openai` matches on the `task-gate-<uuid>` literals at
  `tests/test_task_gate_record.py:941-943` (the `sk-` sits inside `ta[sk-]gate-` and the 39-char lowercase-hex tail
  reaches the rule's 20-char floor), one `credential` match on the `token = "%s-%s-%s"` format string at
  `devtools/task_gate_qual.py:89` and one `credential` match on this receipt's own quotation of that format string
  (line 421, the same shape quoted as prose -- the earlier candidate's receipt carried it too, so this visit adds no
  finding). The measurement is a `git commit-tree` of the staged candidate taken before the last three words of this
  sentence were written (so no tree sha is quoted: the receipt is inside the measured tree, and quoting its own tree
  changes it); the orchestrator's preserve commit is the durable reference, and the three `openai` lines and this
  finding's line can shift by a line or two with the receipt's final wording. The repository's own silencer for exactly this fixture shape is the exemptions
  file `devtools/export-exemptions.txt` (one `path<TAB>rule<TAB>sha256` line per finding, as it already carries for
  `tests/test_tui_planning.py`'s `openai` and `devtools/plan_qual.py`'s `credential`); that file is outside this
  slice's write-set, so supplying those five exemptions is left with the committed-candidate export/private-term gate
  (below).
- `git diff --stat 600122e` (the launch baseline; the earlier visits measured against the checkouts they started
  from, `bd6370f`/`fa5ec74`) lists **only the write-set**: the five product files plus the three new files this slice
  adds (`tests/test_task_gate_record.py`, `devtools/task_gate_qual.py`, this receipt -- `git diff --stat` shows
  tracked changes only, and the new files enter the delivery through `git add --all`). Against the recorded base
  `fa5ec74` the same diff additionally lists the three orchestrator-authored files committed before this slice
  (STATE.md, CALIBRATION.md, this brief); their bytes are unchanged by the worker. The orchestrator preserved the
  first five candidates in its own commits (`23f3530` "WIP s1a1b1 round 5 at re-gate stop" and `0830262`, its tail);
  `0830262` carries exactly the product/test bytes the fifth visit started from, and this receipt diffs the same
  files against `600122e`.
- `python3 -m pyflakes` on every touched/new file is clean (no unused imports, no shadowing introduced).

## Mutations (scratch copy of the candidate, never in the shared worktree)

Each mutation was applied alone to a copy of the candidate (`shutil.copytree` without `.git`/`.tools`) and the
named test run; every mutation is killed:

| # | mutation | killed by |
|---|----------|-----------|
| a | the `submission_unknown` save is moved below `--detach` (the status is still set in memory) | `ProtocolTests.test_an_unconfirmed_submission_refuses_and_never_dispatches_again` |
| b | a native `succeeded` sets `critic_verdict` accepted (bad output) | `ProtocolTests.test_a_native_success_without_a_task_verdict_sets_nothing` |
| c | a rerun overwrites / does not refuse a nonterminal record | `LifecycleTests.test_rerun_refuses_a_nonterminal_record_and_appends_after_a_terminal_one` |
| d | the native binding without `codex_home` | `BindingTests.test_the_binding_carries_the_dispatching_home_and_observes_in_it` |
| e | a lenient `validate_gates` (unknown keys dropped) | `StoreTests.test_strict_store_refuses_each_malformation` |
| f | `gate_manifest` omits `context` | `ManifestTests.test_the_manifest_is_pure_and_carries_the_owner_context` |
| g | `run_task_gate` no longer requires `gates.task == "required"` | `CallerStatusTests.test_the_bound_profile_decides_and_no_caller_value_does` |
| h | `status()` read with `write=True` | `RecordTests.test_a_deferred_profile_adopting_a_late_file_writes_nothing` |
| i | `FixtureEngine` writes a native-shaped binding | `RecordTests.test_a_fixture_gate_stores_the_exact_frozen_values` |
| j | a live change (or any state) always creates and dispatches a new record | `LifecycleTests.test_a_live_config_or_head_change_never_dispatches_again` |

Result: **KILLED 10/10, SURVIVED none.**

The same procedure over the repair's own guards (mutations k–v: `k, l, m, n, o, p, r, t, u, v` live in
`/tmp/mutate2.py`, the guard of `s` in `/tmp/mutate3.py`; each was applied alone to a fresh copy of the repaired
candidate and the named test run):

| # | mutation | killed by |
|---|----------|-----------|
| k | a `concluded` record's verdict/discussion/round count are no longer compared with its own output | `StrictStoreTests.test_concluded_evidence_and_references_are_validated_against_the_record` |
| l | the revision/approval/milestone references are not checked against the store | `StrictStoreTests.test_concluded_evidence_and_references_are_validated_against_the_record` |
| m | a lenient native-binding shape (any dict passes) | `NativeRecoveryTests.test_the_store_refuses_a_native_binding_that_is_not_the_full_shape` |
| n | the effective owner context is unchecked | `StrictStoreTests.test_concluded_evidence_and_references_are_validated_against_the_record` |
| o | admission reads the `Planning` service's profile instead of `Authority.profile` | `NativeRecoveryTests.test_an_unbound_authority_profile_refuses_despite_a_bound_service` |
| p | the plan/milestone conditions are tested before the profile's own state | `RecordTests.test_the_bound_profile_state_precedes_the_plan_conditions` |
| q | the newest nonterminal record is not selected before admission (the same line as mutation j) | `LifecycleTests.test_recovery_is_selected_before_any_live_admission` (mutation j's test also dies) |
| r | `gate_owner_rules` re-reads the live rule hashes instead of the resolved ones | `FrozenConfigTests.test_a_rule_changed_between_resolution_and_documents_refuses` |
| s | a rebuild no longer requires the live rules to resolve to the record's `resolved_config_digest` | `FrozenConfigTests.test_a_rule_changed_before_a_rebuild_refuses_with_intent_changed` |
| t | `gate_prepare` treats a finished preparation as unfinished (`engine.checkout`) | `NativeRecoveryTests.test_a_preparation_that_completed_before_a_crash_is_recovered` |
| u | `gate_bound` skips the four-field identity comparison | `BindingTests.test_an_observation_refuses_a_moved_state_root_or_changed_binary` |
| v | the qualification treats an ended watch slice as a scenario failure | `QualificationTests.test_a_watch_slice_that_ends_is_resumed_until_the_record_is_terminal` |

Measured: **KILLED 11/11, SURVIVED none.** Mutation `s` is the one guard whose removal is *not* caught by anything
else on a fixture record: `FixtureEngine` writes no checkout and no documents, so the rebuild's own digest check is
the only oracle there (on a native record `gate_prepare` independently refuses the same change through its
document-digest comparison, so the two guards corroborate each other).

The second repair repeats the procedure over its own guards (each applied alone to a fresh copy of the candidate,
`/tmp/zz_mut.py`, and the named test run):

| # | mutation | killed by |
|---|----------|-----------|
| a' | the `submission_unknown` save moved below `--detach` (mutation a again, on the reopened-store tests) | `ProtocolTests.test_an_unconfirmed_submission_refuses_and_never_dispatches_again` |
| b' | `gate_bound` compares the *current* engine (`self`) instead of the recorded one | `BindingTests.test_a_restart_on_another_toolchain_observes_through_the_recorded_engine` |
| e' | `gate_observe` no longer checks the observed `source.revision` | `TerminalIdentityTests.test_a_terminal_envelope_of_another_revision_is_refused` |
| f' | the recovery always rebuilds the documents from the live rules | `NativeRecoveryTests.test_a_rule_changed_after_a_completed_preparation_still_recovers` |
| g' | `validate_gate` no longer reproduces the record's own artifact (`contextual_digest`) | `MalformedStoreTests.test_malformed_contexts_and_escaped_surrogates_refuse_the_store` (candidates `{}` and unknown key) |
| h' | `validate_gates` no longer converts a raising check into `store.invalid` | `MalformedStoreTests.test_malformed_contexts_and_escaped_surrogates_refuse_the_store` (both surrogate cases) |
| i' | `validate_context` drops the `isinstance(kind, str)` check *while the loop guard stays* | **SURVIVED** -- by design, not a behaviour change |

Measured: **KILLED 6/6 behaviour-changing mutations; 1 corroborating pair.** `i'` is not a behavioural mutation:
the two layers of finding 1 are redundant on purpose (the type check gives the clean refusal, the loop guard is the
"never a crash" guarantee for every other raising shape), so removing either one alone leaves the store refused;
removing both turns the `[]`/`{}` kind back into a `TypeError`, which the same test then reports as an error.

The fourth repair repeats the procedure over its own guards (each applied alone to a fresh copy of the candidate and
the named test run):

| # | mutation | killed by |
|---|----------|-----------|
| w | `read_review` drops its persistence check on the decoded discussion | `EvidenceTests.test_a_decoded_lone_surrogate_is_output_invalid_without_evidence`, `NativeEvidenceTests.test_a_decoded_discussion_surrogate_is_refused_by_the_parser` |
| x | `concluded` never refuses an envelope it cannot hold (`persistable(output)` removed) | `EvidenceTests.test_an_output_the_store_cannot_hold_leaves_no_terminal`, `NativeEvidenceTests.test_a_raw_surrogate_in_the_envelope_leaves_no_terminal` |
| y | `validate_gate` drops `persistable(entry)` | `PersistedEvidenceTests.test_a_lone_surrogate_outside_the_output_refuses_the_store` |
| z | `gate_observe` drops the submitted-title / frozen-size check | `TerminalIdentityTests.test_a_projection_of_another_title_or_size_is_refused` (both fields) |
| aa | `validate_context` no longer checks a proposal candidate's closed shape | `CandidateShapeTests.test_an_unknown_candidate_key_refuses_the_store` |
| bb | `ID`/`KEY` accept any UUID-shaped suffix again | `StrictStoreTests.test_concluded_evidence_and_references_are_validated_against_the_record` (four new cases) |

Measured: **KILLED 6/6.** Mutations `w` and `x` are two layers of the same refusal (the envelope check catches a raw
surrogate, the parser check the escaped one), and `y` is killed only by the plain-field surrogate, because a decoded
surrogate inside the output is already refused by `w`; each is exercised by its own test above.

The fifth repair repeats the procedure over its own guards (each applied alone to a fresh copy of the candidate and
the named test run):

| # | mutation | killed by |
|---|----------|-----------|
| cc | `gate_run` no longer normalises a raising `validate_receipt` (a malformed receipt escapes as `store.invalid`) | `ReceiptTests.test_a_malformed_receipt_is_an_unconfirmed_submission` (all three cases) |
| dd | `persistable` no longer catches `RecursionError` | `NestedOutputTests.test_an_output_deeper_than_the_store_can_write_leaves_no_terminal` (and `..._is_still_writable_and_listable`) |
| ee | `concluded` checks the bare output instead of its store envelope (`persistable({"gates": [record]})`) | `NestedOutputTests.test_the_record_is_checked_at_the_depth_the_store_writes_it` |
| ff | `task_gates` deep-copies instead of serializing (`decode(canonical(record))`) | `NestedOutputTests.test_a_deep_refused_output_is_still_writable_and_listable` |
| gg | `task_gate_new` pops the append on every failed `save` | `PersistenceTests.test_a_published_preparing_record_is_not_erased_by_a_failed_save` |

Measured: **KILLED 5/5** (six cases: `cc` has three). Every mutation was applied alone to a fresh
`shutil.copytree` of the candidate and the named test run.

The fifth visit repeats the procedure over the checks it adds (each applied alone to a fresh copy of the candidate
and the named test run):

| # | mutation | killed by |
|---|----------|-----------|
| hh | the record's key set becomes superset-tolerant (`set(entry) >= RECORD_KEYS`, unknown keys dropped) | `RecordSchemaTests.test_every_generated_schema_violation_refuses_the_store` (the unknown-key shape) |
| ii | `gate_observe` validates the projection against its own `runId` instead of the recorded one | `TerminalIdentityTests.test_a_projection_of_another_run_id_is_refused` |
| jj | the failed initial save erases the published record from the file too (`pop()` + a second `save()`) | `PersistenceTests.test_a_reopened_authority_recovers_the_published_record`, `..._is_not_erased_by_a_failed_save`, `..._dispatches_nothing_and_keeps_earlier_records` |
| kk | (control) mutation `gg` again -- the memory rollback alone | `PersistenceTests.test_a_published_preparing_record_is_not_erased_by_a_failed_save`; the reopened-`Authority` retry survives it by design, because the record is recovered from the file, not from memory |

Measured: **KILLED 3/3 behaviour-changing mutations**, plus `kk`, which shows the two retry paths guard different
layers (`gg` the in-memory rollback, `jj` the file publication). The new `NestedOutputTests` depths 1 and 400 and the
`RecordSchemaTests` missing/wrong-type domain ride on the same guards (`dd`/`ee`/`hh`) as the depths and shapes they
extend; they are domain coverage, not a separate guard, which is why the table names no mutation for them.

The seventh visit repeats the procedure over the guards its three repairs add (each applied alone to a fresh copy of
the candidate and the named test run):

| # | mutation | killed by |
|---|----------|-----------|
| ll | `gate_observe` drops the gate's own run-id identity check (a foreign run id reaches `validate_projection`) | `TerminalIdentityTests.test_a_projection_of_another_run_id_is_refused` (the foreign-run-id case) |
| mm | `gate_confirmed` drops the receipt-persistability check (a receipt with an unpaired surrogate reaches the store's writer) | `ReceiptTests.test_an_unconfirmed_receipt_is_an_unconfirmed_submission` (both surrogate cases) |
| nn | `gate_confirmed` no longer normalises an unparsable answer (`engine.bad_output` escapes) | `ReceiptTests.test_an_unconfirmed_receipt_is_an_unconfirmed_submission` (the unparsable-answer case) |

Measured: **KILLED 3/3.** Each names the requirement it guards (the closed identity list of R-2, R-4/A-5's
unconfirmed submission). The portable 5000-depth case adds no guard of its own -- it rides the depth checks the
fourth repair already named (`dd`/`ee`) -- so the table names no mutation for it.

The eighth visit repeats the procedure over the guard its repair adds (applied alone to a fresh copy of the candidate
and the named test run):

| # | mutation | killed by |
|---|----------|-----------|
| oo | the persisted discussion is compared with the parsed one by `==` again (the serialization check removed) | `RecordSchemaTests.test_every_generated_schema_violation_refuses_the_store` (the four `true`/`1.0` shapes) |

Measured: **KILLED 1/1.** `oo` is the only mutation this visit needs: the four nested wrong-type shapes (`version`
`true`/`1.0`, `round` `true`/`1.0`) load as `concluded` under plain `==` and refuse as `store.invalid` under the
comparison, so the named test dies on `oo`; the class's remaining nested shapes (the text and list wrong types) are
domain coverage that `==` already refused.

The ninth visit repeats the procedure over the guards its repair adds (applied alone to a fresh copy of the candidate
and the named test run):

| # | mutation | killed by |
|---|----------|-----------|
| pp | the explicit retention limit is dropped (`or too_deep(output)` removed from `concluded`) | `NestedOutputTests.test_an_output_past_the_retention_limit_leaves_no_terminal` (depth 5001) and `..._test_a_payload_past_the_nesting_limit_is_refused_even_when_the_reader_would_take_it` |
| qq | the round-trip read is dropped (`persistable` encodes but never decodes) | `NestedOutputTests.test_the_record_is_dropped_when_the_store_cannot_read_its_own_write_back` |

Measured: **KILLED 2/2.** `pp` is the new guard: with the limit gone, depth 5001 keeps its terminal (2 failures on
3.13.3). `qq` is the repaired `persistable`: the reader-refusing stub then no longer drops the payload. The depth
9990 case rides both guards (`pp` when the interpreter's own probe holds it, `qq` when it does not), so the table
names no mutation for it alone.

## Interpretations (not fixed by the parent/slice text; reviewers inspect these)

- Admission order: the parent lists the profile states and the plan/milestone conditions but not their order; the
  profile's own state is decided first, so an unapproved revision never masks a pending/missing/malformed profile
  (and an unbound profile is still `action.refused` before either).
- Recovery precedes admission: A-4l ("a restart with a nonterminal newest record keeps its id and dispatches
  nothing") is read as strictly prior to R-4's admission, so a live profile that would refuse a *new* gate cannot
  block the recovery or change a record; a live rules change refuses only the rebuild of a never-prepared record
  (`engine.intent_changed`), because a record whose preparation is on disk froze its documents already.
- `gate_bound` selects the record's own engine first (`engine_for(record["binding"])`) and only then compares the
  record's four identity fields with that engine's, so a restart in another toolchain still observes through the
  recorded one while the recorded binary's bytes, its version or a moved state root still refuse
  (`engine.identity_changed`) -- the plan protocol's `prepare` compares the same four fields of the *current*
  engine, and R-3's "recovery goes through `engine_for`" is read as taking precedence for an existing record.
- A `preparing` record whose checkout and three frozen files are already on disk is recovered under its frozen
  configuration (`gate_prepared`): the rebuild from the live rules happens only while nothing is on disk, so the
  only records a post-preparation rule change can refuse are those with no preparation to reuse.
- `FixtureEngine` writes no checkout and no frozen files: the fixture recovery path's only oracle for a live rule
  change is the rebuilt documents' digests against the record's own (`task_gate_documents` + `validate`, mutation
  s); the native path additionally re-checks them in `gate_prepare`.

- The gate graph's node bindings come from the resolved configuration: the `worker` presents the frozen briefs
  (`proposer`) and the profile's `critic` reviews them (`delivery.task_gate_roles`, `delivery.py:24-27`). The parent
  fixes the two read-only nodes and their scopes (`sessionScope: node_instance`), not which profile role fills
  which node.
- The record's `terminal` is the native `terminalResult` (`output` included) and `output_digest` the digest of that
  output, so `validate_gates` can check the two against each other: `concluded`/`output_invalid` carry a succeeded
  terminal plus the digest, `native_failed` a failed terminal and no digest. An `output_invalid` record may carry no
  terminal at all: an output the store cannot hold is never written, so only its refusal is kept and the record stays
  loadable.
- `rounds_used`, `discussion`, `critic_verdict` are filled by `concluded` alone; every other status has `None`,
  including `output_invalid` (A-5's "no discussion stored").
- The persisted discussion is compared with the one the record's own output parses to *type-preservingly* -- its own
  `canonical` serialization, not `==` -- because Python treats `true == 1 == 1.0` and a nested field whose JSON type
  moved (`discussion.version`, `discussion.rounds[i].round`) would otherwise load a store no writer produces
  (R-5's "every malformed shape is `store.invalid`").
- The frozen intent a projection must match is the record's HEAD *plus* the submitted title
  (`task_gate.submitted_title(milestone)`, the whole-string form `gate_run` passes to `run --title`) and the frozen
  runtime `size` (`task_gate.SIZE`), so a projection that renames the run or resizes it is `engine.intent_changed`
  exactly like another revision (parent R-2 terminal identity). The closed list's first field, the run id, is the
  gate's own identity check too: a nonempty run id that is not the recorded one refuses `engine.intent_changed` in
  `gate_observe` (`engine.py:1455-1457`), while the *existing* structural envelope validation still applies to
  everything else -- a missing, empty or non-string run id stays `validate_projection`'s own refusal, exactly as the
  plan path splits the pair (`engine.py:1564-1566`). No other projection field is identity.
- Every string the record persists must survive `canonical`: an unpaired surrogate in an output is refused as
  `output_invalid` with no terminal and no digest, one in a *decoded discussion* by `read_review`, and one anywhere in
  a stored record by `validate_gate` (`persistable`, `task_gate.py:62-71`). `escaped` (the native failure reason)
  keeps that reason holdable instead of losing it.
- `concluded` measures the record at exactly the depth the store writes it (`persistable({"gates": [record]})`, the
  `state["gates"]` envelope included), because a nesting the serializer cannot walk must be refused before `digest`
  walks it too, and `persistable` now runs the store's own *round trip* at that depth -- `canonical`, then UTF-8,
  then the store's `decode` -- because a payload the writer holds can still be one the reader refuses, and a retained
  payload must stay writable, reloadable and listable (R-5's "otherwise set terminal and output_digest to None").
  A `RecursionError` from the *reader* depends on the interpreter and on how deep the call already is, so no probe
  of it can be trusted; `concluded` therefore also refuses any output nested deeper than `OUTPUT_NESTING_LIMIT`
  (5000, the deepest depth the amendment's input domain names -- reading "the complete store-envelope depth" as the
  domain the amendment checks, i.e. retention is promised inside it and refused past it). `task_gates` returns
  `decode(canonical(record))` rather than `copy.deepcopy`, since a record that holds a refused deep output is
  writable but not deep-copyable (R-4/R-5). `validate_gates` wraps each record's check so any `RecursionError` a
  hostile shape raises is `store.invalid`, never a crash. The amendment's input domain is the checked one: nesting
  depths 1/400/500 stay holdable on every supported interpreter (the terminal is kept, the record listable), 5000 is
  kept only where the interpreter's own write *and* read hold it, and 5001/9990 never are -- measured on this host a
  depth-5000 payload is refused (no terminal, no digest) by `python3` 3.9.6 (recursion limit 1000) and holdable by
  3.13.3, and both outcomes are the invariant the test asserts, while 5001 and 9990 are deterministic. The
  deterministic unpersistable coverage is the raw-surrogate case and the two stubs, which depend on no depth. Both surrogate ranges are checked raw and decoded,
  and the refusal domain is generated from the record schema itself (every `RECORD_KEYS` key missing, every key with
  a wrong JSON type, one unknown key -- 49 shapes, all `store.invalid`) with valid controls; these examples do not
  close the input corpus, but the limits they exercise are the existing discussion limits, unchanged.
- The initial save's fault model (the amendment's A-4l/A-5/A-6b boundary): one synchronous `OSError` from the
  *first directory fsync* after `atomic_state` replaced the store with the `preparing` record. `task_gate_new`
  reports the `PersistenceError`, keeps the append in memory only when the record is published in the file
  (`task_gate_published`), dispatches nothing, and the retry recovers the same id -- through the same service (whose
  `save` tracks the visible bytes) or through a reopened `Authority` (which reads the record back from the file).
  The earlier records stay byte-identical. Non-goals as the amendment states: no arbitrary asynchronous exceptions,
  no repeated or combined I/O failures, no crash durability after a failed directory fsync, no exactly-once beyond
  the existing submission protocol.
- A proposal context's candidate is the closed `{"tasks", "amendments"}` shape `runs.structured` accepts
  (`validate_candidate`), checked because the artifact reproduction alone would ignore an unknown extra key; and the
  `id`/`submission_key` must be UUID version 4 with the RFC 4122 variant, not merely UUID-shaped.
- The `gate` record's documents are persisted as digests beside the record and the frozen files live under
  `authority.directory/gates/<id>/` (`graph.json`/`runtime.json`/`input.json` + a read-only `checkout`), mirroring
  the plan gate's `revision-<n>/`; a recovery re-checks those bytes and refuses (`engine.intent_changed`) if they
  moved. A live rules change between a `preparing` save and its recovery re-derives the documents and refuses the
  same way; a dispatched record is observed under the frozen files on disk.
- `Delivery.task_gates` filters to the current revision's milestone (newest last); the frozen contract names the
  order, not the filter. `run_task_gate`'s "newest record for (revision, milestone)" is the same predicate.
- `term`/"`critic_verdict` set only by the parsed `taskVerdict`": a native failure reason (`critic_failed`,
  `proposer_failed`, `session_lost`) sets `diagnostic` to the reason and `critic_verdict` stays `None` (the
  scenario name is the native terminal reason, not a plan-gate purpose string).
- Boundary/scope decisions: the three named delivery methods are implemented with small private helpers in the same
  file (`task_gate_admission`/`_engine`/`_documents`/`_recovery`/`_new`/`_published`/`_latest`/`_go`, `delivery.py:617-737`) plus
  the module-level `task_gate_roles`; the frozen contract's "delivery.py: `run_task_gate`, `rerun_task_gate` and
  `task_gates` only" is read as the public surface, not as a ban on private plumbing in the same class. The engine
  path is
  `NativeEngine.gate_binding/gate_bound/gate_run/gate_confirmed/gate_prepare/gate_documents_ok/gate_observe/gate_conclude`
  plus the pure `task_gate_documents`/`gate_owner_rules`/`gate_prepared` and the `FixtureEngine` counterpart
  (`engine.py:252-292, 918-951, 1304-1473`); the plan path (`prepare`/`proposal` and s2a2's symbols `recorded_engine`, `engine_for`,
  `codex_home` and `prepare`'s binding compare/writer) is unedited and no helper was extracted (the plan-gate
  suites' goldens pass unchanged). `authority.py` changes exactly `validate_state` :430 (the extra allowed key) and
  the `gates` hook :439-441. `runs.py` adds only `gate_manifest` (`runs.py:605-611`); `start` is untouched. None of `process.py`, `catalog.py`,
  `cli.py`, `tui/*`, `setup.py`, `planning.py`, docs was touched.
- Deviation from the parent: the qualification script approves the plan revision natively (over the same loopback
  provider, plan graph) before it can run the gate, because `begin` requires the native engine in a production
  authority and `run_task_gate` requires an approved revision. That is the production flow, not a shortcut.

## Left to the orchestrator (not claimed here)

- The full suite (~15 min) and `devtools/linux-test.sh --py devtools/task_gate_qual.py` on the Linux test host,
  with the results appended to this receipt (the worker ran `--help` and the import only, per the DoD; the 364-test
  targeted run and the 316-test importer run above are the worker's own).
- The committed-candidate `devtools/export_check.py` / private-term gate: the content run of the candidate's tree
  (the staged candidate's `git commit-tree` above) has no `home-path` finding and the five false-positive findings
  recorded above (three `openai`, two `credential`, one of them this receipt's own quotation) need five
  `devtools/export-exemptions.txt` lines, a file outside this slice's write-set; the private-term rule needs its
  supplied term list. Both are the orchestrator's merge gate, not this slice's.
- The size disposition above (step 1): the overrun grew with each repair (2492/600 core+tests, 279/200
  qualification, 2771/800 total, deleted lines included) because one class-level regression check per demonstrated
  violation -- and the amendment's own input domain -- were required in the same change.
- s1a1b2 consumes this frozen contract unchanged: validity predicate, start barrier, required-attempt
  admission/LINEAGE, override writing, and the removal of the `process.unbuilt` branch.

## Sixth visit (2026-10-20, on the merged branch)

This visit re-read the *amended* brief on the launch HEAD `5a76c61` (current main `600122e` merged into the seed
branch; the seed's product/test bytes are `0830262`'s) and audited the accumulated implementation against the
re-gate amendment of 2026-10-20, which the first five visits had only partly covered. It found the amendment's
boundary contract implemented but its *test* requirements partly unimplemented, and closed them without touching a
product line (so the product bytes equal the seed's and the review diff is the accumulated implementation):

- Terminal identity: each of the four fields is now checked independently against a matching control -- the run id
  by the shared envelope validation (`store.invalid`, the plan path's split preserved), `source.revision`, the
  submitted title and the frozen size by the gate's own `engine.intent_changed` (`TerminalIdentityTests`).
- The fault model of the persistence guarantee: a fault-free control, an earlier record kept byte-identical, the
  failed save dispatching nothing, and **both** retry paths -- the same service and a reopened `Authority` -- are
  now covered (`PersistenceTests`).
- The amendment's input domain: the nesting depths 1, 400, 500 and 5000 (`NestedOutputTests`) and a bounded
  schema-directed generator over the record's closed keys -- every key missing, every key with a wrong JSON type,
  one unknown key, each a `store.invalid`, with a valid control (`RecordSchemaTests`).

No requested behaviour changed and nothing was reverted. Checks run in this visit: the DoD targeted command →
**Ran 364 tests in 425s … OK** (0 failures, 0 errors, 0 skips); `tests.test_task_gate_record` alone → **59 tests
OK**; `PYTHONPATH=. python3 devtools/task_gate_qual.py --help` → exit 0; `python3 devtools/export_check.py
--commit <the staged candidate's tree>` → `summary: 5 findings openai=3 credential=2`, no `home-path` (the DoD's
requirement; see the export bullet above for why no tree sha is pinned);
`git diff --stat 600122e` → only the write-set; `python3 -m pyflakes` on the touched test file → clean. The
mutation rows `hh`-`kk` above were each applied alone to a fresh `shutil.copytree` in the visit's scratch
directory, which was removed afterwards.

## Seventh visit (2026-10-20, on the merged branch: the reviewers' three findings repaired)

Both reviewers rejected the sixth candidate against the review baseline `600122e`. Each of the three demonstrated
violations is repaired in place, and each names the violated requirement, the fix and the regression test that fails
when the fix is removed (mutations `ll`-`nn` above). No requested behaviour was weakened, nothing was reverted, and
the plan path's bytes and behaviour are unchanged.

1. **A run-id mismatch is terminal identity, not a structural refusal (parent R-2's re-gate amendment: the closed
   list's four fields).** `NativeEngine.gate_observe` now compares the observed `runId` with the recorded one itself
   and refuses `engine.intent_changed` on a *nonempty* mismatch, exactly like the frozen HEAD, the submitted title and
   the frozen size; a missing, empty or non-string run id still reaches the shared `validate_projection`, so the plan
   path's own structural `store.invalid` is preserved. The class docstring, the test's oracle and the receipt's
   interpretation now say the same thing.
   `TerminalIdentityTests.test_a_projection_of_another_run_id_is_refused` (mutation `ll`).
2. **The 5000-depth case asserts the persistence invariant, not one interpreter's recursion limit (the re-gate
   amendment's input domain: the project's supported Python versions; the worker DoD).** On CPython 3.13 a 5000-deep
   payload is walkable, so the earlier fixed oracle (`terminal` False, `output_digest` None) both failed there and
   mis-stated the contract. The test now asserts what the amendment fixes -- `output_invalid`, `critic_verdict` None,
   `discussion` None, and then either a kept terminal with a digest or no terminal with the refusal in `diagnostic`
   (both keys retained) -- with the record writable, reloadable and listable either way; the interpreter-independent
   unpersistable coverage stays the raw-surrogate case and the serializer stub, neither of which depends on a depth.
   `NestedOutputTests.test_an_output_deeper_than_the_store_can_write_leaves_no_terminal`.
3. **Every way a detach confirmation can fail is an unconfirmed submission (R-4's recovery; A-5's protocol).**
   `NativeEngine.gate_confirmed` now holds the whole confirmation: an answer the client cannot parse
   (`engine.bad_output`), an ambiguous or malformed receipt (`store.invalid`), a receipt with an unpaired surrogate
   the store cannot hold, and the serializer's own `TypeError`/`ValueError`/`UnicodeError`/`RecursionError` all
   normalise to the existing `submission.unknown` -- never a family a later call could mistake for retryable -- while
   a `--detach` the CLI itself refused or could not run keeps its own family, exactly as the plan protocol reports
   it. The record stays `submission_unknown` in memory and on disk (the status saved before the dispatch), so a
   retry -- the same service or a reopened `Authority` -- observes the recorded run or refuses, and never resubmits.
   `ReceiptTests.test_an_unconfirmed_receipt_is_an_unconfirmed_submission` (six cases; mutations `mm`/`nn`), control
   `ReceiptTests.test_a_well_formed_receipt_concludes`.

Checks run in this visit: the worker DoD nine-module command under `python3.13` (3.13.3) → **Ran 364 tests in
487s … OK** (0 failures, 0 errors, 0 skips); `tests.test_task_gate_record` alone under `python3.13` and this host's
`python3` (3.9.6, an extra interpreter, not the project's floor) → **59 tests OK** each; `PYTHONPATH=. python3
devtools/task_gate_qual.py --help` → exit 0; the staged candidate's `git commit-tree` through `python3
devtools/export_check.py` → `summary: 5 findings openai=3 credential=2`, **no `home-path`**; `python3 -m pyflakes` on
every touched file → clean (pyflakes has no 3.13 build on this host, so the 3.9 run is the one recorded); `git diff
--stat 600122e` → only the write-set. Mutations `ll`-`nn` were each applied alone to a fresh `shutil.copytree` in the
visit's scratch directory, which was removed afterwards. Left with the orchestrator (below): the full suite, the
Linux `devtools/linux-test.sh --py devtools/task_gate_qual.py`, the committed-candidate export/private-term gate and
the size disposition.

## Eighth visit (2026-10-20, on the merged branch: the acceptance reviewer's finding repaired)

The acceptance reviewer rejected the seventh candidate against the review baseline `600122e` (the code reviewer
accepted it). The one demonstrated violation is repaired in place, and it names the violated requirement, the fix and
the regression test that fails when the fix is removed (mutation `oo` above). No requested behaviour was weakened and
nothing was reverted; the plan path's bytes and behaviour are unchanged.

1. **The persisted discussion is validated type-preservingly (R-5's strict store; the amended input domain's "the
   frozen record schema and existing owner-context validators are the single source of field types and closed
   shapes").** `task_gate.validate_status` compared the parsed discussion with the persisted one by Python `==`,
   which treats `true == 1 == 1.0`: a store whose `discussion.version` or `discussion.rounds[i].round` was written as
   a JSON `true` or `1.0` loaded as `concluded`/`accepted` even though `read_review` refuses the same discussion and
   the round count still matched. The comparison is now `canonical(parsed) == canonical(persisted)` -- the record's
   own serialization, so a nested field whose JSON type moved refuses the whole store as `store.invalid` without
   repair -- and the `validate_status` docstring and the receipt interpretation say so.
   `RecordSchemaTests.test_every_generated_schema_violation_refuses_the_store` generates the nested wrong-type shapes
   (`discussion.version` `true`/`1.0`/`"1"`, `discussion.rounds[0].round` `true`/`1.0`, `findings` `true`, `response`
   `[]`); the four `true`/`1.0` shapes failed before the repair and pass after it (mutation `oo`).

Checks run in this visit: the worker DoD nine-module command under `python3.13` (3.13.3) → **Ran 364 tests in
456s … OK** (0 failures, 0 errors, 0 skips); `tests.test_task_gate_record` alone under `python3.13` and this host's
`python3` (3.9.6) → **59 tests OK** each; `RecordSchemaTests` alone → 4 subtest failures before the repair and 1 test
OK after it, on both interpreters; `PYTHONPATH=. python3 devtools/task_gate_qual.py --help` → exit 0; the staged
candidate's `git commit-tree` through `python3 devtools/export_check.py` → `summary: 5 findings openai=3
credential=2`, **no `home-path`**; `python3 -m pyflakes` on every touched file → clean; `git diff --stat 600122e` →
only the write-set. Mutation `oo` was applied alone to a fresh `shutil.copytree` in the visit's scratch directory,
which was removed afterwards. Left with the orchestrator (below): the full suite, the Linux
`devtools/linux-test.sh --py devtools/task_gate_qual.py`, the committed-candidate export/private-term gate and the
size disposition.

## Ninth visit (2026-10-20, on the merged branch: the acceptance reviewer's finding repaired)

The acceptance reviewer rejected the eighth candidate against the review baseline `600122e` (the code reviewer
accepted it). The one demonstrated violation is repaired in place; it names the violated requirement, the fix, the
regression tests that fail when the fix is removed (mutations `pp`/`qq` above), the checked domain and the
interpretation the fix rests on. No requested behaviour was weakened and nothing was reverted; the plan path's bytes
and behaviour are unchanged.

1. **A retained terminal output stays reloadable and listable at the complete store-envelope depth (R-5; the amended
   input domain's "any retained payload must remain writable, reloadable, and listable ... otherwise set terminal and
   output_digest to None").** `task_gate.persistable` checked only that the record *encoded* to the store's own
   `canonical` bytes. A payload nested deep enough can be written and still be one the store's *reader* refuses: the
   reviewer's fixture dispatch of a 9990-deep output returned `output_invalid` while retaining `terminal` and
   `output_digest`, and every later reopen of the store through `Authority` raised `store.invalid` (a JSON decoder
   `RecursionError`), so the gate's own record became unlistable. `persistable` now runs the store's own round trip
   (`canonical`, then UTF-8, then the store's `decode`, R-5) and `concluded` additionally refuses (`UNPRINTABLE`, no
   terminal, no digest, both keys kept) any output nested deeper than `OUTPUT_NESTING_LIMIT` (5000). The explicit
   bound is required because a *reader* `RecursionError` depends on the interpreter and on the calling stack, so no
   read-back probe of it can be trusted at every depth; the round trip is kept because it is what catches the other
   unpersistable class (a JSON-escaped lone surrogate) at any depth. No whole-store decoder change was made.
   `NestedOutputTests.test_an_output_past_the_retention_limit_leaves_no_terminal` (depths 5001 and 9990: status,
   no terminal, no digest, the refusal in `diagnostic`, then `listed()` and `on_disk()` through the production
   loader), `..._test_a_payload_past_the_nesting_limit_is_refused_even_when_the_reader_would_take_it` (a
   reader-permissive stub leaves the nesting limit as the only guard: 5001 dropped, the shallow control kept) and
   `..._test_the_record_is_dropped_when_the_store_cannot_read_its_own_write_back` (a reader stub that refuses the
   `state["gates"]` envelope drops the output at depth 4) name the guard; mutation `pp` (limit removed) fails two of
   them and mutation `qq` (read-back removed) fails the third. The 5000 case keeps its invariant form, and its stub
   control is now shallow, because on `python3` 3.9.6 the store's writer itself already refuses 5000 -- the supported
   interpreter 3.13.3 holds it, which is why the boundary is asserted at 5001, past the limit on every interpreter.

Interpretation recorded with the fix (also in the regression class's docstring, which both reviewers inspect): the amendment's input
domain names depths 1, 400, 500 and 5000 and requires the retained payload to be writable, reloadable and listable
"at the complete store-envelope depth"; the fix reads that as retention promised *inside* the named domain and
refused *past* it, so `OUTPUT_NESTING_LIMIT` is 5000 -- the deepest depth the domain names -- rather than a probe of
the running interpreter's own reader budget.

Checks run in this visit: the worker DoD nine-module command under `python3.13` (3.13.3) → **Ran 367 tests in
490s … OK** (0 failures, 0 errors, 0 skips); `tests.test_task_gate_record` alone under `python3.13` and this host's
`python3` (3.9.6) → **62 tests OK** each; the reviewer's own reproducer under `python3.13` → exit 0 (5000 keeps its
terminal, 9990 is refused with no terminal and the store reloads and lists); `PYTHONPATH=. python3
devtools/task_gate_qual.py --help` → exit 0; `python3 -m pyflakes` on every touched file → clean; the staged
candidate's `git commit-tree` through `python3 devtools/export_check.py` → `summary: 5 findings openai=3
credential=2`, **no `home-path`**; `git diff --stat 600122e` → only the write-set. Mutations `pp` and `qq` were each
applied alone to a fresh `shutil.copytree` in the visit's scratch directory, which was removed afterwards. Left with
the orchestrator (below): the full suite, the Linux `devtools/linux-test.sh --py devtools/task_gate_qual.py`, the
committed-candidate export/private-term gate and the size disposition.

Orchestrator integration gate (2026-10-20, appended): Linux full suite on e020827 1420 tests OK; `devtools/linux-test.sh --py devtools/task_gate_qual.py` 8/8 scenarios OK; macOS full suite 1420 tests with one error, `test_real_pty_ctrl_c_detaches_status_shows_running_and_w_reattaches` TimeoutExpired, classified as a launch artifact, not this diff: the suite ran as a `&` job of a non-interactive shell, so SIGINT was ignored in the zplan child and Ctrl-C never detached; the same background launch fails main bdf708e identically, and the test passes 3/3 in the foreground on 043963d and on main (diagnostics ~/zs-pause/s1a1b1-realpty-diag, foreground logs ~/zs-pause/int-s1a1b1-043963d-realpty-fg.log). export_check on 043963d: 0 findings after five line-hash exemptions for the false positives above (devtools/export-exemptions.txt). Size: core+tests 2492 vs 600, qual helper 279 vs 200, total 2776 vs 800. Critic s1a1b1-merge (session 01a15ad5-adc7-7633-b5aa-a78c5afdd8f9): MERGE, size CONTINUE. Known stale wording: tests/test_task_gate_record.py:40 still says `runId -> store.invalid`; the implementation and assertions require `engine.intent_changed`.
