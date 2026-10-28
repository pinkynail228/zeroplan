s1c1a-merge-gate-core — 0.5 item S1c, slice 1 of 5 for 0.5 (7 in total; s1c1e1/s1c1e2 deferred to 0.5.x by critic gate22) of devtools/zeroshot/tasks/s1c1-merge-gate.md (the parent; its R-* and A-* texts apply verbatim where cited). Slicing: critic swarm05 c ("ordinary merge gate with both overrides → release mode; enforcement invariant must not be broken"), refined at the stable contracts the S1a chain already proved (s1a1a core → s1a1b1 record → s1a1b2 barrier → s1a1c UI). This slice is the pure core, like s1a1a: nothing calls it. DeepSeek worker, sol reviewers.

Base: main after the s1a1b1-gate-record merge (engine.py ownership passes from s1a1b1 to this slice; s1a1b1's gate path is the pattern). Lines below are cited at main 8f1f62c and will move. Record the actual base and this brief's sha256 in the receipt, re-check every cited line, and re-gate if a premise moved.
- Consumes, as plain dicts only (no import of their modules): the qualification record of s1b2a-qualification-records.md R-3. Tests build those dicts by hand, so this slice does not wait for its merge. No flake-diagnosis input (s1b3a deferred to 0.5.x, critic gate22); if a merged shape differs, stop and re-gate.

Slices and the parent ID map (every S1c1 ID, one owner each; sub-parts named where the parent text spans slices):
| Parent ID | Owner |
|---|---|
| R-1 scope (removal of `process.unbuilt` for merge) | s1c1c; every earlier slice keeps off and required byte-identical |
| R-2 dispatch precondition | s1c1b |
| R-2 merge precondition, checks=[] binding | s1c1c |
| R-3 graph, input, full diff or refusal, terminals | s1c1a (this) |
| R-3 dispatch/observe/rerun protocol, native failure vs rejection in the record | s1c1b |
| R-3 catalog actions (submit, observe, rerun, overrides): plain, CLI, Delivery wiring | s1c1d1 |
| R-3 catalog actions: TUI | s1c1d2 |
| R-3 release-input action | s1c1e2 — deferred to 0.5.x (critic gate22) |
| R-3 input: diagnosis verdicts in the summary | s1c1a passes `diagnoses: []`; content deferred to 0.5.x (critic gate22) with s1b3a |
| R-4 release mode | s1c1e1 — deferred to 0.5.x (critic gate22) |
| R-5 merge rule, recheck before `git merge`, five families | s1c1c |
| R-6 both overrides (records, validity, invalidation) | s1c1c |
| R-6 override texts on gate, merge question, home, status | s1c1d1 (TUI rendering of the same strings: s1c1d2) |
| R-7 rejected → new attempt with findings | s1c1d1 (service + plain); TUI key: s1c1d2 |
| R-8 display, `[i]` discussion | s1c1d1 (strings, plain); s1c1d2 (TUI); release decision line: s1c1e2 — deferred to 0.5.x (critic gate22) |
| A-1 off identical | s1c1c (plan without `release` and its digests: s1c1e1 — deferred to 0.5.x (critic gate22); in 0.5 the plan schema is unchanged) |
| A-2 graph interpreter | s1c1a |
| A-3 merge rule through service | s1c1c; through CLI and plain: s1c1d1; through TUI: s1c1d2 |
| A-3b | s1c1c, except: malformed release values and release-input boundaries s1c1e1 (deferred to 0.5.x (critic gate22)); the decisive change beyond 4000 diff characters s1c1a |
| A-4 staleness | s1c1c (release checklist edit: s1c1e1 — deferred to 0.5.x (critic gate22)) |
| A-5 release | s1c1e1/s1c1e2 — deferred to 0.5.x (critic gate22) |
| A-6 crash after dispatch | s1c1b; crash between recheck and `git merge`: s1c1c |
| A-7 base failure (`merge.qual_missing` through Delivery.merge) | s1c1c (each slice adds its own A-7) |
| DoD native qualification of the new graph | s1c1b (devtools qualification script; orchestrator on the Linux test host) |
| DoD docs | REFERENCE: each slice that touches the catalog; USER_FLOW, PROCESS_PROFILE: s1c1d1 (release: s1c1e2 — deferred to 0.5.x (critic gate22)) |

Order: s1c1a (this) → s1c1b-merge-gate-record → s1c1c-merge-rule → s1c1d1-merge-gate-plain + s1c1d2-merge-gate-tui (integrated as a pair) (end of S1c1 in 0.5). Deferred to 0.5.x: s1c1e1-release-input → s1c1e2-release-ui. s1c1a may run in parallel with s1b2a/s1b2b (disjoint write-sets); s1c1b needs s1b2a and defines `qualification.current` itself (critic gate22). The window between the s1c1c merge and the d1/d2 pair is a development intermediate only, never released.
Enforcement invariant: `gates.merge == "required"` keeps refusing merge with `process.unbuilt` until s1c1c installs the whole merge rule (qualification condition, gate validity, both overrides) in one change. No release milestone exists in 0.5 (the plan schema has no `release` key; s1c1e1 is deferred), so no release merge is ever admitted on a non-release gate.

Write-set (exclusive for this slice):
- new `terminal_planner/merge_gate.py`: `diff`, `summary`, `artifact`, `identity`, `identity_matches`, `read_review`, constants;
- engine.py: new `merge_gate_graph(rounds)`, `merge_gate_runtime(roles)`, `merge_gate_input(context)` next to `task_gate_graph` :787-853, `task_gate_runtime` :856-860, `task_gate_input` :863-867. No edit to existing symbols; a shared builder with the task gate is allowed only if tests.test_task_gate and tests.test_plan_gate pass unchanged;
- new `tests/test_merge_gate.py`;
- the receipt `devtools/zeroshot/tasks/s1c1a-merge-gate-core-receipt.md`.
Not touched: authority.py, delivery.py, runs.py, process.py, catalog.py, cli.py, tui/*, task_gate.py, qualification.py, checks.py, existing tests, docs.

Audit (8f1f62c):
- Task-gate core to mirror: task_gate.py:27-62 (`artifact`, `artifact_digest`, `identity`, `identity_matches`, `read_review`, `SUBJECT` :20, `FIELDS` :21); `read_discussion` authority.py:931; `digest` :159; `canonical` (imported in tests/test_task_gate.py:38).
- Graph shape: engine.py `task_gate_graph` :787-853 (verifier nodes, `review_loop` with `maxIterations = rounds`, terminals accepted/exhausted/critic_failed), `record` :581, `state_binding` :587.
- Existing UI diff: `Runs.diff` runs.py:1316 against `destination.base`, truncated to `DIFF_LIMIT` 4000 delivery.py:24 by `diff_text` :828-830 — never critic evidence (parent R-3).
- Sanitized git: export.py `environment` :25, `OPTIONS` :21, `TIMEOUT` :18 (300 s).
- Tests to mirror: tests/test_task_gate.py `GraphTests` :150, `ProposerContractTests` :185, `AdmissionTests` :237, `InterpretedGraphTests` :352, `ParserTests` :400.

Rules:
- R-1 Unreached: nothing outside tests imports merge_gate.py or calls the new engine functions; every existing graph, document, digest and screen is byte-identical.
- R-2 Diff (parent R-3 input, full or refused): `diff(project, head, commit)` runs `git diff --no-color --no-ext-diff --full-index <head>...<commit>` (argv only, `export.environment()`, `export.OPTIONS`, `export.TIMEOUT`) and returns `{"bytes": raw, "digest": sha256 hex of raw, "text": raw decoded UTF-8 with errors="replace"}` or `{"refused": "diff_failed" | "too_large"}`. Domain: any repository state; nonzero exit, timeout or `OSError` → diff_failed; `len(raw) > MAX_DIFF_BYTES` → too_large, never truncated. `MAX_DIFF_BYTES = 262144`; boundaries 0 (empty diff accepted), 262144 accepted, 262145 refused. Binary files appear as git's "Binary files … differ" line.
- R-3 Summary (parent R-3 input): `summary(qualification)` → None for checks=[] (no record), else `{id, outcome, checks: [{name, status}], diagnoses: []}` from the s1b2a record; tails are excluded. `diagnoses` is always the empty list in 0.5 (flake diagnosis deferred to 0.5.x, critic gate22); the key exists so 0.5.x fills it without a shape change.
- R-4 Identity (parent R-5 artifact): `identity(commit, tree, destination_head, qualification_id, checks_digest, config_digest)` → exactly those six keys (qualification_id None and `checks_digest = digest([])` for checks=[], parent R-2). `identity_matches(gate, live)` compares all six; pure. s1c1e may add a seventh key `release_digest` only when present; absent it changes nothing.
- R-5 Input: `artifact(identity, diff, summary, owner_rules)` → the gate context `{identity, diff: text, diff_digest, qualification: summary, owner_rules}`; `merge_gate_input(context)` is the initial state: `{"schemaVersion": "1", "merge": canonical(context), "mergeResponse": "", "mergeVerdict": "rejected", "mergeFindings": "Not reviewed", "discussion": canonical({"version": 1, "rounds": []})}`.
- R-6 Graph (parent R-3): `merge_gate_graph(rounds)` = the task-gate shape with merge field names: a read-only `proposer` that argues (fixed / disputed + why) and never writes the artifact, a `critic` with `sessionScope: node_instance`, `maxIterations = rounds` (the frozen `limits.merge_rounds`), terminals `accepted_merge_gate`, `exhausted_merge_gate`, `critic_failed`; both nodes `verifier`. `merge_gate_runtime(roles)` uses the same role keys as `task_gate_runtime`.
- R-7 Output: `read_review(output, rounds_limit)` checks exact `FIELDS` ("schemaVersion", "mergeVerdict", "mergeFindings", "mergeResponse", "discussion"), verdict ∈ accepted | rejected, and parses the discussion with `read_discussion(..., SUBJECT="проверки слияния")`; malformed → `Blocked`.
- R-8 Fixtures: scratch paths and an isolated HOME/XDG only; no literal home paths.

Acceptance (tests/test_merge_gate.py; temp git repos; the tests/test_task_gate.py interpreter and pinned-binary admission harnesses; no network). Each test names entry point, oracle and control.
- A-2 (parent) Graph: interpreter runs reject→accept, reasoned dispute accepted, exhaustion after exactly `rounds`, critic error → `critic_failed`, proposer error; the proposer has no write path (document inspection as `test_the_proposer_has_no_write_path_to_the_artifact`); native admission of the documents with the pinned binary (skips without it, as AdmissionTests).
- A-D Diff: the full text equals `git diff <head>...<commit>` for a change placed beyond the first 4000 characters (parent A-3b) and differs in digest when only that change differs; boundaries 0 / MAX / MAX+1 bytes (generated files); a non-UTF-8 file → replacement characters in text, digest over raw bytes; a failing git (bad commit) → diff_failed.
- A-I Identity: each of the six keys changed alone → `identity_matches` false; checks=[] → qualification_id None and `digest([])`; key set exact.
- A-P Parser: well-formed accepted/rejected outputs parse; missing/extra field, bad verdict, wrong schemaVersion, a discussion over the rounds limit → refused.
- A-7 Base: compatibility — tests.test_task_gate and tests.test_plan_gate pass unchanged on the candidate; no production entry point exists yet, so candidate-only invariants map to killed mutations: (a) proposer with a write path; (b) critic without `node_instance`; (c) `maxIterations` not `rounds`; (d) truncating the diff at MAX instead of refusing; (e) dropping one identity key; (f) diff from `destination.base` instead of the given head. Report named failures and skips separately.

Size: estimated 370-450 changed lines, receipt excluded: product ~155 (merge_gate.py ~85, engine ~70), tests ~215-295. Above 600: report the measured overrun and rationale in the receipt; merge requires explicit critic disposition (ORCHESTRATOR step 1).

Parallelism: engine.py is shared with s1a1b1 (base) and any S2/S3 slice editing engine adapters: serial with those. With s1b2a..s1b3b: disjoint.

Out of scope: record, dispatch, store (s1c1b); merge rule, overrides (s1c1c); UI (s1c1d1/s1c1d2); release (s1c1e1/s1c1e2, 0.5.x); diagnosis content (s1b3a, 0.5.x).

DoD:
- Worker (targeted): `PYTHONPATH=.:tests python3 -m unittest tests.test_merge_gate tests.test_task_gate tests.test_plan_gate tests.test_toolchain tests.test_reference` passes. No full suite.
- `git diff --stat <base>` lists only the write-set.
- `python3 devtools/export_check.py` reports no home-path finding on the committed candidate.
- Receipt: base, this brief's sha256, file list, A-7 counts, the mutation table.
- Orchestrator, before merge: the full suite on the Linux test host.
