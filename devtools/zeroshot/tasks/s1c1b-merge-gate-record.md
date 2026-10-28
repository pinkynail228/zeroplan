s1c1b-merge-gate-record — 0.5 item S1c, slice 2 of 5 for 0.5 of devtools/zeroshot/tasks/s1c1-merge-gate.md (the parent; its R-* and A-* texts apply verbatim where cited; parent ID map in s1c1a-merge-gate-core.md). The durable merge-gate record and its dispatch/observe/rerun protocol, mirroring s1a1b1-gate-record.md. Merge stays closed: `process.unbuilt` for merge is kept (removed only by s1c1c). DeepSeek worker, sol reviewers.

Base: main after the merges of s1c1a-merge-gate-core, s1a1b2-gate-barrier (override and validity patterns on main) and s1b2a-qualification-records (records, `valid`). Critic gate22: no dependency on s1b3a (deferred to 0.5.x); this slice defines `qualification.current` itself. Lines below are cited at main 8f1f62c and will move. Record the actual base and this brief's sha256 in the receipt, re-check every cited line, and re-gate if a premise moved.
- Consumes, unchanged: s1c1a's `merge_gate` API and engine `merge_gate_graph/runtime/input`; s1a1b1's "Frozen contract" (the submission protocol, binding rules, status enum, `run_task_gate` newest-record rule) as the pattern; s1b2a's qualification records, `valid` and `Delivery.qualification`. No diagnosis records (the gate summary carries `diagnoses: []`, s1c1a R-3). If any differs, stop and re-gate.

Order: s1c1a → s1c1b (this) → s1c1c → s1c1d1/s1c1d2 (pair). s1c1e1/s1c1e2 and s1b3a deferred to 0.5.x (critic gate22); s1b3a will consume `qualification.current` from here.

Frozen contract (this slice defines it; s1c1c, s1c1d1/s1c1d2, s1c2-status-truth and, in 0.5.x, s1b3a/s1c1e1 consume it):
- `qualification.current(record, live)` (pure, moved here from s1b3a by critic gate22) → True iff `record["status"] in ("concluded", "refused")` and `commit`, `tree`, `checks_digest`, `destination.head` equal `live` (keys as in s1b2a `valid`). Outcome is not compared. s1b2a's `valid(record, live)` keeps its behaviour; it may be rewritten as `current(...) and outcome == "passed"` only if tests.test_qualification passes unchanged.
- Store: `state["merge_gates"]`, optional, absent until the first record, `[]` never written; not `state["gates"]` (frozen for task gates by s1a1b1) — same decision as s1b2a for qualifications.
- Record (exact keys): `gate` "merge"; `id` "merge-gate-" + uuid4 (full-match grammar as s1b2a's id); `run` = {plan_revision, milestone, attempt}; `identity` (s1c1a R-4, six keys); `config` (frozen resolved config) and `rounds_limit` (its `limits.merge_rounds`); `documents` (graph/runtime/input digests); `diff_digest`; `binding` (as s1a1b1: native four keys + `codex_home`, or exactly `{"fixture_id": …}`); `submission_key` "zplan-gate-" + uuid4; `status` ∈ the s1a1b1 enum; `run_id`, `receipt`, `terminal`, `output_digest`; `rounds_used`, `discussion`, `critic_verdict` (accepted | rejected | None); `override` (None here; s1c1c writes it, `validate_merge_gates` already accepts a well-formed `{reason, verdict, evidence_digest}` on a concluded rejected record, as s1a1b1 did); `diagnostic`, `created`, `updated`.
- Functions: `merge_gate.validate_merge_gates(state)` (strict → `store.invalid`), `merge_gate.evidence(record)` (the dict an override digest binds: gate, id, run, identity, rounds_used, rounds_limit, discussion, critic_verdict, output_digest); `Delivery.run_merge_gate(r, progress=...)`, `Delivery.rerun_merge_gate(r, progress=...)`, `Delivery.merge_gates(r)` (read-only, newest last). The newest record for the attempt decides: nonterminal → recover/observe that record (no new dispatch; `submission_unknown` refuses with `submission.unknown`); none or terminal → `run_merge_gate` creates and dispatches; `rerun_merge_gate` refuses while nonterminal and otherwise appends.

Write-set (exclusive for this slice):
- qualification.py: the one pure `current(record, live)` above (and, optionally, `valid` expressed through it);
- merge_gate.py: record construction, `validate_merge_gates`, `evidence`;
- engine.py: a merge-gate prepare/submit/observe path next to s1a1b1's task-gate path, plus the `FixtureEngine` counterpart; plan- and task-gate paths byte- and behaviour-identical;
- authority.py: `validate_state` :419-437 only ("merge_gates" allowed, one hook);
- delivery.py: `run_merge_gate`, `rerun_merge_gate`, `merge_gates` only;
- catalog.py: a new ERRORS group "Merge gate" with `merge.qual_missing` and `merge.gate_input` (raised here, R-3); remedies generic, no key named; docs/REFERENCE.md regenerated;
- new `tests/test_merge_gate_record.py`;
- new `devtools/merge_gate_qual.py` (mirror of s1a1b1's devtools/task_gate_qual.py: loopback synthetic provider, no model run);
- the receipt `devtools/zeroshot/tasks/s1c1b-merge-gate-record-receipt.md`.
Not touched: `Delivery.merge` :842-852, `Runs.merge` runs.py:1135-1177, process.py (the merge `process.unbuilt` :709-710 stays), task_gate.py, qualification.py outside `current`, checks.py, cli.py, tui/*, existing tests and goldens, docs except REFERENCE.

Rules:
- R-1 Unreached by merge: `Delivery.merge` under required still refuses with `process.unbuilt`; off is byte-identical everywhere (no `merge_gates` key). No key, end-screen action or `Дальше:` label; the gate is reachable only from code and tests until s1c1d.
- R-2 Profile: read with `status(write=False)`; dispatch only when the bound profile resolves `gates.merge == "required"` (else `action.refused`); never/missing/malformed → `process.pending`/`process.missing`/`process.invalid` as `Profile.guard` :693-704, without calling `guard("merge")`.
- R-3 Dispatch admission (parent R-2 dispatch part), before any side effect, in this order:
  1. `r` is the latest attempt and `extended(r)["delivery"]` ∈ {awaiting_merge, conflict}; else `action.refused`;
  2. qualification: checks=[] → none needed (qualification_id None); else the newest qualification of `r` must be `concluded` (passed or failed) and `qualification.current` → otherwise (none, running, interrupted, refused, stale) `merge.qual_missing`;
  3. live identity: destination HEAD (`git rev-parse refs/heads/<branch>`, argv only), `config_digest` of the live resolved config;
  4. `merge_gate.diff(project, head, commit)`; a refusal → `merge.gate_input` ("diff больше 256 КиБ" / "git не выдал diff"), no record. An oversized diff is an input refusal, never a skipped or passed gate (critic gate22): under required the merge stays closed; the remedy text names the two owner choices — shrink the change (a new attempt) or explicitly switch the profile to one with `gates.merge: off`. Nothing disables the gate automatically.
  A refused qualification (no check ran) counts as missing; it has no failed checks to override (parent R-6).
- R-4 Protocol: s1a1b1's sequence for this record — frozen documents and digests, the record saved `submission_unknown` before `--detach`, receipt, `observing`, detached/blocked handling. Native failure (`*_failed`, `session_lost`) is `native_failed`, a malformed output `output_invalid`, distinct from `critic_verdict == rejected`; exhausted rounds = rejected (parent R-3 terminals).
- R-5 Frozen observation: a live HEAD, config or qualification change never turns an observation into a new dispatch; staleness is s1c1c's.
- R-6 Fixtures: scratch paths and an isolated HOME/XDG only; no literal home paths.

Acceptance (tests/test_merge_gate_record.py; temp git repos; FixtureEngine merge-gate scenarios: accepted, rejected, exhausted, critic error, session_lost, malformed output; qualifications made through `Delivery.qualify`; no network). Each test names entry point, oracle and control.
- A-R Records: each scenario through `run_merge_gate` → exact record keys and values, `critic_verdict` and status per terminal; two calls on a nonterminal record → one dispatch (FixtureEngine submit count 1); `rerun_merge_gate` after a terminal → two records, the first byte-identical; while nonterminal → refused.
- A-Q Admission: checks=[] dispatches with qualification_id None; a passed and a failed current qualification dispatch; none, running, interrupted, refused, stale (each identity key) → `merge.qual_missing`, store and refs unchanged; a 256 KiB + 1 diff → `merge.gate_input`, no record. Control: the same attempt with a small diff dispatches. The refusal text names both owner choices; the profile is unchanged (no automatic `gates.merge: off`).
- A-C `qualification.current`: table over status (concluded passed/failed, refused → True when identity equal; running, interrupted → False) × each of commit, tree, checks_digest, destination.head changed alone (→ False); outcome never compared; tests.test_qualification passes unchanged.
- A-6 (parent, dispatch part) Restart: fault injection after `submission_unknown` is saved and before the receipt (the s1a1b1 hook) → new session → `run_merge_gate` recovers that record; no duplicate dispatch.
- A-S Store: each malformed record shape (unknown key, bad enum, duplicate id, binding namespace mismatch, an override on a non-rejected record) → `store.invalid`, file unchanged.
- A-Q2 Native qualification script: `devtools/merge_gate_qual.py --help` runs; the orchestrator runs it on the Linux test host before merge (parent DoD).
- A-7 Base failure: through `Delivery.merge`, required, after a passed qualification: still `process.unbuilt` (compatibility, passes on base and candidate). The counted regression: `Delivery.run_merge_gate` is candidate-only, so map it to killed mutations: (a) record saved after dispatch; (b) dispatch with a stale qualification; (c) dispatch with a refused qualification; (d) a second dispatch for a nonterminal record; (e) native `succeeded` read as accepted; (f) `guard("merge")` called (dispatch refused under required); (g) a diff over the limit truncated; (h) `current` comparing outcome; (i) `current` ignoring `destination.head`. Report named failures and skips separately.

Size: estimated 590-640 changed lines in total including the devtools script (product + tests 510-560), receipt and REFERENCE excluded: product ~240 (qualification ~10, merge_gate ~90, engine ~70, delivery ~50, authority ~5, catalog ~15), devtools script ~80, tests ~270-320. Above 600: report the measured overrun and rationale in the receipt; merge requires explicit critic disposition (ORCHESTRATOR step 1).

Parallelism: engine.py and catalog.py serial with any slice editing them. qualification.py: its prerequisite owner is s1b2a (s1b2b:16 does not touch it); no further serialization. delivery.py: new methods only.

Out of scope: merge rule, validity, overrides, removal of `process.unbuilt` (s1c1c); keys and screens (s1c1d1/s1c1d2); release (s1c1e1/s1c1e2, deferred to 0.5.x).

DoD:
- Worker (targeted): `PYTHONPATH=.:tests python3 -m unittest tests.test_merge_gate_record tests.test_merge_gate tests.test_task_gate_record tests.test_task_gate tests.test_plan_gate tests.test_qualification tests.test_runs tests.test_toolchain tests.test_reference` passes (verify every module path on the base). No full suite.
- `git diff --stat <base>` lists only the write-set; `python3 -m terminal_planner.catalog --check docs/REFERENCE.md` prints "docs current".
- `python3 devtools/export_check.py` reports no home-path finding on the committed candidate.
- Receipt: base, this brief's sha256, file list, A-7 counts, the mutation table.
- Orchestrator, before merge: the full suite and `devtools/merge_gate_qual.py` on the Linux test host.
