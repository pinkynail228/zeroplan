s1a1b1-gate-record — 0.5 item S1a, slice 2a of devtools/zeroshot/tasks/s1a1-task-gate.md (the parent; its Audit, R-* and A-* texts apply verbatim where cited). Slicing: critic swarm05 c (~/zs-pause/critic/swarm05.out:49) as split by critic gate7 B (~/zs-pause/critic/gate7.out): s1a1b1 = durable record + dispatch + native qualification with `process.unbuilt` kept; s1a1b2 = validity + barrier + override with `unbuilt` removed in the same change. Lane L2. DeepSeek worker, sol reviewers. Critic gate8: GO WITH CHANGES (applied).

Original run admission (historical): main after the s2a2-engine-wiring merge (engine.py is shared; s2a2 also adds `NativeEngine.codex_home()`, s2a2-engine-wiring.md:38). s1a1b1 runs before s1a1b2. Lines below are cited at main 6a537b5 (s1a1a merged at 8b245ff). Record the actual base and this brief's sha256 in the receipt. Re-check every cited line on the base, in particular `prepare`/`proposal` engine.py:1034-1150, which s2a2 edits, and re-gate if a premise moved. Admission (critic launch-after-s2a2): actual base fa5ec74 (s2a2 + s2a2b); the audit also covers s2a2b's `phase(status, run_id)` and the run-scoped observation context `OBSERVED_RUNS` (engine.py), which a gate observation path reuses rather than duplicates; s2a2's symbols stay unedited.

Slices:
- s1a1a (merged) = pure core.
- s1a1b1 (this):
  - the task-gate record in `state["gates"]` with strict validation (parent R-2 record);
  - the dispatch protocol with crash safety (parent R-5 dispatch/recovery);
  - the service action `run_task_gate`;
  - the native loopback qualification script (parent DoD, deferred by s1a1a: s1a1a-gate-core-receipt.md:162-164; int-0.5-batch1-integration.md, "s1a1a size deviation" bullet);
  - A-4r, A-5, A-6b (persisted part).
  - `process.unbuilt` for a required task gate stays (process.py:707-708). No start, preview or retry behaviour changes.
- s1a1b2 = validity, start barrier, required-attempt admission/LINEAGE, override; removes `unbuilt` in the same change.
- s1a1c = TUI key, plain/CLI command, `[i]`, R-6 display, docs.

Frozen contract (this slice defines it; s1a1b2 consumes it unchanged, and any change is a re-gate of both):
- Store: `state["gates"]` is optional in schema 2, next to `runs` (authority.py:429 becomes `set(state) - {"runs", "gates"}`). It is absent until the first gate is created; `[]` is never written.
- Record (exact keys):
  - `gate`: "task";
  - `id`: "task-gate-" + uuid4;
  - `plan_revision` (int), `approval` (the revision's approval identity), `milestone`, `context` (the effective owner context or None);
  - `identity`: `task_gate.identity(...)`, the three keys;
  - `config`: the frozen resolved config; `rounds_limit` (`limits.task_rounds` of `config`);
  - `documents`: graph/runtime/input digests;
  - `binding`: depends on the authority.
    - Native authority: `binary_identity()` four keys plus `codex_home`, as s2a2 writes them (R-3).
    - Fixture authority: exactly `{"fixture_id": authority.fixture_id}`, as runs.py:418 and :1495 do, with the namespace check.
  - `submission_key`: "zplan-gate-" + uuid4;
  - `status` ∈ preparing | submission_unknown | observing | detached | observation_blocked | concluded | native_failed | output_invalid;
  - `run_id`, `receipt`, `terminal`, `output_digest`;
  - `rounds_used`, `discussion`, `critic_verdict` (accepted | rejected | None);
  - `override`: None, or exactly `{reason, verdict, evidence_digest}` with the `override_matches` shape (authority.py:828).
    - This slice writes only None, but `validate_gates` already accepts a well-formed override on a `concluded` record whose `critic_verdict` is "rejected", so s1a1b2 needs no validation change.
    - An override on any other record is `store.invalid`.
  - `diagnostic`, `created`, `updated`.
- Functions:
  - `task_gate.validate_gates(state)`: strict. Unknown or missing keys, bad enums, duplicate ids, inconsistent terminal fields, a binding that does not match the namespace (a fixture binding in a production store, or a native binding in a fixture store) and an ill-shaped override all raise `store.invalid`;
  - `task_gate.evidence(record)`: the dict an override digest binds — gate, id, plan_revision, approval, milestone, identity, rounds_used, rounds_limit, discussion, critic_verdict, output_digest;
  - `MilestoneRuns.gate_manifest(milestone_id, plan_revision, context)`: exactly `bootstrap_manifest(build_documents(...)["baseline"], context)` as `Runs.start` computes it at runs.py:653-654, pure, with no git, refresh or persistence;
  - Start/observe/rerun API (the one lifecycle s1a1b2 relies on):
    - `Delivery.run_task_gate(milestone_id, context=None, progress=..., slice=None)` → record. The newest record for (revision, milestone) decides:
      - nonterminal (preparing, submission_unknown, observing, detached, observation_blocked): recover or observe that same record, keeping its id. No new dispatch, and `submission_unknown` still refuses (`submission.unknown`).
      - none, or terminal: create and dispatch a new record.
    - `Delivery.rerun_task_gate(milestone_id, context=None, ...)`: the explicit rerun. It refuses while the newest record is nonterminal; otherwise it appends a new record and never touches earlier ones.
    - A live config, rules or HEAD change never turns an observation into a new dispatch. A nonterminal record is observed under its frozen documents and config; staleness is judged only by s1a1b2's validity.
  - `Delivery.task_gates(milestone_id)` → read-only list, newest last.

Write-set (exclusive for this slice):
- task_gate.py: the record schema, `validate_gates`, `evidence`, record construction;
- engine.py:
  - a task-gate prepare/submit/observe path for a gate record next to `prepare`/`proposal`, plus the `FixtureEngine` counterpart (:208);
  - no edit to s2a2's symbols (`recorded_engine`, `engine_for`, `codex_home`, the binding compare/writer in `prepare`);
  - the plan path's bytes and behaviour unchanged; extract a shared helper only if the plan-gate suites pass unchanged.
- authority.py: `validate_state` :429 and :435-437 (the `gates` hook) only;
- runs.py: the new pure `gate_manifest` only; `start` itself is not edited here;
- delivery.py: `run_task_gate`, `rerun_task_gate` and `task_gates` only;
- new `tests/test_task_gate_record.py`;
- new `devtools/task_gate_qual.py`;
- the receipt `devtools/zeroshot/tasks/s1a1b1-gate-record-receipt.md`.

Not touched: process.py, catalog.py (existing families only), cli.py, tui/*, setup.py, planning.py, docs.

Audit (6a537b5):
- Core:
  - task_gate.py:27-60 (`artifact`, `artifact_digest`, `identity`, `identity_matches`, `read_review`), `SUBJECT` :20;
  - engine.py `task_gate_graph` :787, `task_gate_runtime` :856, `task_gate_input` :863.
- Plan protocol to mirror:
  - `prepare` engine.py:1034-1107: frozen documents and digests, disposable clone :1074-1075, HEAD check :1082-1083;
  - `proposal` :1109-1150: `submission_unknown` saved before `--detach` at :1137-1139, receipt, `observing`, detach and blocked handling;
  - `observe` :1231, `invoke` :964, `FixtureEngine` :208, `validate_receipt` authority.py:841.
- Store: authority.py:427-437 (the `runs` extension precedent), `atomic_state` :98.
- Effective artifact at start: runs.py:653-654; `bootstrap_manifest` :142; `build_documents` :355.
- Profile: the bound `Authority.profile` (authority.py:372, bound at cli.py:138). `Profile.status(write=True)` process.py:546-593 may write the sidecar `process-state.json` (:10, :387); `status(write=False)` writes nothing. The refusals for never/missing/malformed are `process.pending`/`process.missing`/`process.invalid` (:697-702).
- Fixture binding: runs.py:418 (`{"fixture_id": ...}` checked) and :1494-1495; FixtureEngine engine.py:228, :236.
- Precedent qualification: devtools/plan_qual.py (325 lines; loopback synthetic provider, scenarios a-g, `devtools/linux-test.sh --py`). Model runs are not allowed on the Linux host (ORCHESTRATOR.md:17).

Rules:
- R-1 Unreached by start: with `process.unbuilt` kept, no start, retry, answer, accept, preview, record, digest or screen changes. Off/no-profile stores stay byte-identical: no `gates` key.
- R-2 Record: the frozen contract above; parent R-2 record paragraph. Never overwritten. Reruns and `session_lost` append a new record.
- R-3 Binding:
  - A native gate binding is `binary_identity()` plus `codex_home` = the home of the engine environment that actually dispatches (s2a2's `NativeEngine.codex_home()`), never the four keys alone.
  - A fixture gate binding is exactly `{"fixture_id": authority.fixture_id}`. FixtureEngine never constructs a synthetic native binding. Observation and recovery go through `engine_for(record["binding"])`.
- R-4 Dispatch: `run_task_gate`.
  - Admission:
    - It reads the authoritative live config from the bound `Authority.profile` via `status(write=False)`, never a caller-supplied Status.
    - States never/missing/malformed → `process.pending`/`process.missing`/`process.invalid`.
    - A native authority with no bound profile → `action.refused`.
    - Otherwise it refuses with `action.refused` unless the config has `gates.task == "required"`, the current revision is approved, and the milestone exists.
    - The `context` argument is the same effective owner context (answer or accepted candidate) that a later start will pass, so A-3b in s1a1b2 checks the same artifact.
  - Preparation and dispatch:
    - It computes the artifact via `gate_manifest` and `task_gate.artifact_digest`, the HEAD of the destination branch, and the config digest.
    - It saves the record (`preparing`), prepares a read-only disposable clone at that HEAD, and freezes the three documents.
    - It saves `submission_unknown` before `--detach`, then saves `observing` with the receipt.
  - Recovery:
    - A crash after dispatch never resubmits; a restart observes the recorded run id.
    - An unconfirmed submission raises the existing `submission.unknown`.
    - Native `*_failed`/`session_lost` → `native_failed`.
  - Output: a terminal output goes through `task_gate.read_review(output, rounds_limit)`. A refusal → `output_invalid`, with `critic_verdict` None and no discussion stored. Native `succeeded` alone sets nothing; only the parsed `taskVerdict` sets `critic_verdict`.
- R-5 Strict store: `validate_gates` runs on every load. A malformed entry refuses the whole store (`store.invalid`) and is never repaired.
- Re-gate amendment 2026-10-20 (run 01a157dd force-stopped in round 5 for an open contract; critic s1a1b1-r4-check RE-GATE EARLY, session 01a1596a-337e-7d91-b098-9d8de9ff59e1; candidate preserved at 0830262 on branch zs-s1a1b1-gate-record; critic s1a1b1-regate GO WITH CHANGES, applied). Boundary contract (R-2/R-4/R-5; A-4l/A-5/A-6b):
  - Terminal identity (parent R-2, closed list): run id equals the recorded run id, source.revision equals the frozen HEAD, and title and size equal the frozen gate intent. An equality mismatch raises engine.intent_changed. The mismatching projection supplies no terminal evidence; the same record remains nonterminal. Saving observation_blocked and its diagnostic is allowed. No other projection field is identity; existing structural envelope validation still applies. Test each identity field independently, with a matching projection as control.
  - Persistence product need: an owner retry after a reported save failure must not erase an already-published gate record.
  - Fault model: one synchronous OSError from the first directory fsync after atomic_state successfully replaces the store with the initial preparing record. Ordinary I/O resumes before retry. The existing A-5 submission-boundary crash checks remain unchanged.
  - Guarantee: report PersistenceError, preserve the published record, and recover its id on retry using either the same service or a reopened Authority. Existing records remain unchanged. Do not dispatch during the failed initial save. Check publication independently from the store file; inject only the named directory-fsync failure and include a fault-free control.
  - Non-goals: arbitrary asynchronous exceptions at every instruction, repeated or combined I/O failures, crash durability after a failed directory fsync, and exactly-once guarantees beyond the existing submission protocol.
  - Input domain: use the project's supported Python versions. Store validation covers the gates extension of stores decoded by the existing Authority loader. The frozen record schema and existing owner-context validators are the single source of field types and closed shapes. Violations refuse the whole store with store.invalid, without repair.
  - Terminal output is untrusted. Malformed, incomplete, or unpersistable output becomes output_invalid without discussion or critic_verdict. Rejected raw output need not be retained. Any retained payload must remain writable, reloadable, and listable at the complete store-envelope depth; otherwise set terminal and output_digest to None, retaining both keys.
  - Keep the existing discussion limits. Check both surrogate ranges, raw and decoded strings, and nesting depths 1, 400, 500, and 5000. Add a bounded schema-directed generator for missing/extra keys and wrong JSON types, with valid controls. These examples do not close the input corpus. Resource-limit refusals create no usable evidence.
  - Non-goals: unlimited raw-output retention, unlimited nesting or size, process survival under resource exhaustion, changes to the existing whole-store decoder, and Python versions below requires-python.
  - Rerun implementation seed: preserved candidate 0830262, including the unreviewed round-5 changes. Before launch, incorporate the current main into the rerun branch and pin that main SHA as the review and compatibility baseline; it must contain no s1a1b1 implementation. Record seed, baseline, launch HEAD and the submitted brief's sha256 separately in the receipt. Reviewers assess the entire accumulated implementation diff against that baseline, including all changes inherited from 0830262. The seed is not the review baseline.
- R-6 Qualification script: `devtools/task_gate_qual.py`, reusing plan_qual.py/driver_qual.py helpers by import rather than copy. It drives the production `Delivery.run_task_gate` against the pinned binary and a scripted loopback provider, with no model calls. Scenarios:
  - a_accept_r1;
  - b_reject_accept_r2;
  - c_dispute_accepted;
  - d_exhausted (task_rounds=2);
  - e_critic_error;
  - f_proposer_error;
  - g_malformed_discussion (output_invalid, no evidence);
  - h_continuity: the critic's round-2 request carries its round-1 answer (`sessionScope: node_instance`).
  The worker runs `--help` and an import locally; the orchestrator runs it on the Linux test host before merge.
- R-7 Fixtures: every literal home path in tests is under `/home/user/`.

Acceptance (unit tests; deterministic fixtures; no network or provider). Each test names its production entry point, its oracle and its control.
- A-4r Records:
  - Entry: `Delivery.run_task_gate` with FixtureEngine scenarios accept/reject/exhaust/critic_failed/session_lost. The fixture record's binding is exactly `{"fixture_id": ...}`; a native-shaped binding in a fixture store is `store.invalid`.
  - Oracle: the exact record keys and values, with a rerun appending (the earlier record byte-identical).
  - Control: `/1` and `gates.task: off` → `action.refused`; never/missing/malformed profiles → their process family. In each case the store bytes and the sidecar `process-state.json` bytes (or its absence) are unchanged, and there is no `gates` key.
- A-4l Lifecycle API:
  - A restart with a nonterminal newest record → `run_task_gate` keeps its id and dispatches nothing.
  - A config, rules or HEAD change during observation → still the same record, still no dispatch.
  - `rerun_task_gate` refuses on a nonterminal record and, on a terminal one, appends.
- A-4o Override shape: a valid override on a concluded rejected record loads. The same shape on an accepted, nonterminal or native_failed record, or with an extra key, → `store.invalid`.
- A-4s Strict store: for each of an unknown key, a missing key, a bad status, a duplicate id, `critic_verdict` set on a non-concluded record and `gates: []` → `store.invalid` on load. The control, a valid store with two records, loads.
- A-5 Protocol (parent A-5):
  - Faults injected after `submission_unknown` is saved and after the detach receipt.
  - Restart → the same run id is observed and `invoke(... "--detach")` is called exactly once (spy).
  - An unconfirmed submission → `submission.unknown`, with no second dispatch.
- A-6b Evidence: s1a1a's malformed, inconsistent and over-cap outputs, delivered through the fixture dispatch path → `output_invalid` with `critic_verdict` None. The control, a well-formed output, → `concluded`.
- A-3h Binding: the stored binding has `codex_home` equal to the dispatching engine's env home. With a different home in the env, a recorded gate is observed with its recorded home (`engine_for`). The control: a 4-key binding written by a mutated writer fails the test.
- A-1 Off: s1a1a's `OffIdenticalTests` and the plan-gate suites pass unchanged. `process.unbuilt` is still raised for a required start (asserted).
- A-7 Compatibility and mutations:
  - No base-failing entry exists until the barrier (s1a1b2 holds parent A-7); say so in the receipt.
  - Targeted modules pass on base and candidate.
  - Mutations, each killed by a named test:
    - (a) `submission_unknown` saved after dispatch;
    - (b) native `succeeded` sets `critic_verdict` accepted;
    - (c) a rerun overwrites;
    - (d) the binding without `codex_home`;
    - (e) a lenient `validate_gates` that drops unknown keys;
    - (f) `gate_manifest` that omits `context`;
    - (g) `run_task_gate` trusting a caller Status with `gates.task: off`;
    - (h) `status()` called with write=True (the sidecar snapshot changes);
    - (i) FixtureEngine writing a native-shaped binding;
    - (j) a live config change triggering a new dispatch during observation.

Size: the whole diff except the receipt counts, with these limits:
- core+tests ≤600 (estimated ~220 product, ~300-350 tests);
- `devtools/task_gate_qual.py` ≤200 (helper reuse);
- total ≤800.
Exceeding any one limit: report the measured overrun and rationale in the receipt; merge requires explicit critic disposition (ORCHESTRATOR step 1).

Out of scope: validity predicate, barrier, admission field, LINEAGE, resume, override, the `task.gate_*` families and the removal of `process.unbuilt` (s1a1b2); keys, commands, display, docs (s1a1c).

DoD:
- Worker (targeted): `python3 -m unittest tests.test_task_gate_record tests.test_task_gate tests.test_plan_gate tests.test_plan_override tests.test_tui_plan_gate tests.test_process tests.test_runs tests.test_toolchain tests.test_reference` passes, and `PYTHONPATH=. python3 devtools/task_gate_qual.py --help` runs. The worker does not run the full suite.
- `git diff --stat <base>` lists only the write-set.
- `python3 devtools/export_check.py` reports no home-path finding on the committed candidate.
- Receipt: base, this brief's sha256, file list, compatibility counts (named failures and skips separately), the mutation table, and the frozen contract as implemented (any deviation is a stop).
- Orchestrator, before merge: the full suite, then `devtools/linux-test.sh --py devtools/task_gate_qual.py` on the Linux test host, with the results appended to the receipt.
