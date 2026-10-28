# s1a1a-gate-core — receipt

0.5 item S1a, slice 1 of 3 of `devtools/zeroshot/tasks/s1a1-task-gate.md` ("the parent"; its Audit, Read list,
R-* and A-* apply verbatim where cited). Lane L2. DeepSeek worker, sol reviewers. Pure core only: nothing in this
slice is reachable from a user action.

- **Base.** `6e23523a8be138fcfb848c9cbf6869ec74283604` — the intended v0.4.0 tag target ("C2"); the stated base of
  this brief. The tag did not move: `git rev-parse HEAD` was that SHA at start and the run's own
  `git status --porcelain` was empty.
- **Brief.** `devtools/zeroshot/tasks/s1a1a-gate-core.md`, sha256
  `2c649d1191377b8e873bb3a6cf1cbb3a87f95ec974760739d70e8f1b46f995ec`; parent `s1a1-task-gate.md`, sha256
  `56d90de0bb07d5a199b26165bf614dfc06ff3b14db6abce137f835230225bc3d`.
- **Audit re-check.** The audit is on `74f1a3b`; every cited line was re-checked on the base. Offsets moved with the
  merges landed between `74f1a3b` and the base, but no premise moved (the same functions and contracts exist):
  engine.py `planner_graph_v2` 422→422, `critic` 441→441, `planner` 450→450, `review_loop` 462→462,
  `maxIterations` 467→467, terminals 477–479→477–479, `planner_runtime_v2` 484→484, `planner_input_v2` 491→491,
  dispatch 717–723→818–824; authority.py `review_evidence` 586→587, gate fields 598–601→599–602, `bad_discussion`
  897→913, `read_discussion` 901→917, `read_review` 935→951, `GATE_STALE` 333→333, `plan.gate_stale` 757/786→772/803,
  `override` 767→781, `validate_override` 566→573, `override_reason` 802→819, accepted-or-overridden 546–549→556–558
  and 754→769, `digest` 159→159; process.py `guard` 640→693, task branch 655→707, `UNBUILT` 49–50→49–50, preset `/1`
  58–66→58–66 (`limits.task_rounds` default 2 at :64), live digest 669→722; delivery.py guard 527→528, preview
  534→534, start 571→569, `live_roles` 824→823, `new_attempt` 829→829; runs.py `bootstrap_manifest` 128→136,
  `Runs.start` 586→594, retry 1284→1292, steward accept 1342→1341, preview 1257→1265; milestone.py:57→57.
- **Size.** 4 files against the base, **737 insertions / 30 deletions = 767 changed lines**:
  `terminal_planner/engine.py` +108, `terminal_planner/authority.py` 45+/30−, new `terminal_planner/task_gate.py`
  62, new `tests/test_task_gate.py` 522. **This is above the brief's 600-line ceiling.** The overshoot is the
  repair the two reviews demanded: the base goldens of the stored revision/preview/home for both configurations
  (they catch the persisted-field mutation the 18 original tests missed) plus the native-contract and
  instruction regressions. All of it is s1a1a core work; nothing of s1a1b
  (record, dispatch, start barrier, A-3/A-3b/A-5/A-6/A-7) or s1a1c (UI/CLI, docs) is absorbed. Flagged here for
  the orchestrator in case it wants a re-gate.

## Repair of the rejected candidate (visit 2)

- **Finding 1 (code + acceptance, R-3 — round-two classification).** `TASK_PROPOSER_RETURNS` said only "answer
  every finding ... in turn"; R-3 requires "answers each finding as fixed-impossible / disputed + why". The text
  now reads "marking each one fixed-impossible (and why the briefs cannot carry the change) or disputed (and why
  the finding does not hold)". As a verifier node the proposer also answers with the shape its contract requires
  (verdict, diagnostic.message and output.taskResponse), so the instruction no longer says "Return only
  taskResponse". Regression: `ProposerContractTests.test_the_authored_proposer_contract_requires_the_round_two_classification`
  asserts against the *generated* proposer instructions (`engine.task_gate_graph(2)["...proposer..."]["instructions"]`),
  not through the interpreter (which supplies the response itself and could not see the omission).
- **Finding 2 (code, R-3 — the effective native contract).** The proposer was a `step` node; the pinned runtime
  maps `step` to the Worker contract, whose guidance tells the node to "follow repository setup and install
  manifest/lockfile dependencies in the checkout" — the exact text this run's own `step` node carries. That
  contradicts the read-only proposer. The proposer is now a `verifier` node (the only read-only agent contract;
  it declares the `signals`/`diagnostic` a verifier node requires; the runtime role follows the node's own
  declaration, not the worker label - zplan's milestone graph labels the same two kinds with its own refs, and the
  built-in `software-change` template carries a `verifier` kind on a `builtin.git-delivery.*` label, so labels are
  names - validated by native admission). Regressions:
  `ProposerContractTests.test_the_proposer_is_not_the_installing_step_worker` and `PinnedGuidanceTests.test_only_the_worker_block_tells_the_node_to_install_dependencies`
  (reads the pinned binary itself). **Zeroshot product input:** a read-only agent node has no native contract
  that is free of the setup/install mandate except `verifier`, whose text ("Verify the prepared shared checkout …
  Run checks and create artifacts") is also not a proposer's job; a role that "only argues" has no native kind.
- **Finding 3 (acceptance, A-1 — missing base goldens).** `OffIdenticalTests` freezes the base bytes of the
  stored plan revision, the preview text and the home text for preset `/1` *and* for an explicit
  `gates.task: "off"`. Demonstrated: adding a persisted evidence field (`evidence["task_gate"]`, which passes the
  store's own validation) leaves 22 of the module's 24 tests passing and fails exactly these two
  (`/tmp/zs-agent-mut/evidencefield`).
- The two mutations required by the brief (invert an exclusion, drop an identity field) and the proposer-write-path
  mutation were re-run on this candidate: all three still fail their named tests (below).

## Change (product)

- `terminal_planner/task_gate.py` (new, 62 lines) — the pure core:
  - `artifact(manifest)` / `artifact_digest(manifest)` (via the shared `digest()`): the projection of the
    *validated* `Runs.bootstrap_manifest(baseline, context)` with exactly the parent's exclusions —
    manifest `plan_revision`, `progress`, `outcome` and baseline `plan_revision`, `limits`.
  - `identity(artifact_sha, resolved_config_digest, head)` and the pure `identity_matches(gate_identity, live)`
    comparing all three (artifact, resolved configuration incl. rules/limits, HEAD); no storage, no I/O.
  - `read_review(output, rounds_limit)`: validates the task-gate output shape and parses its bounded discussion
    through the generalised `authority.read_discussion` (own subject).
- `terminal_planner/engine.py` (+108) — only the new builders beside `planner_graph_v2`, no dispatch wiring:
  `task_gate_graph(rounds)` (read-only `proposer` + `critic`, both `verifier` nodes so the runtime applies the
  read-only contract to each, `sessionScope: node_instance` via the runtime, `maxIterations = rounds`, terminals
  `accepted_task_gate`/`exhausted_task_gate`, fails `proposer_failed`/`critic_failed`; the proposer has no write
  binding to the `task` state and the verdict it argues is only its own `verdict` signal), `task_gate_runtime(roles)`,
  `task_gate_input(context)`, and the proposer/critic instruction texts.
- `terminal_planner/authority.py` (45 +/30 −) — generalisation only, plan gate bytes unchanged:
  - `bad_discussion(reason, subject=...)` and `read_discussion(text, rounds_limit, final, subject=...)`: the parser
    now takes the final (verdict, findings, response) and the refusal subject; `read_review` calls it with the
    plan values, so `planVerdict/planFindings/planResponse` messages are byte-identical.
  - `gate_stale(subject="плана")` replaces the `GATE_STALE` constant; both plan raise sites call it (same text).
  - `override_matches(evidence, override, verdict_field="verdict", subject="плана")`: the pure owner-record
    validation extracted from `Authority.validate_override`, which now calls it (same checks, same messages).
- `tests/test_task_gate.py` (new, 522 lines) — the slice's acceptance tests (below).

## Acceptance → evidence

Deterministic fixtures only: real temporary Git repositories, the scripted interpreter, no provider, no network.
Every run used a private scratch `TMPDIR` (`mktemp -d /tmp/zs-agent-XXXXXX`) —
`TMPDIR=$S PYTHONPATH=.:tests python3 -m unittest -q <module>`.

- **A-1 Off is identical.** `BaseTests.test_the_plan_documents_and_the_normalized_configuration_are_the_base_bytes`
  freezes the base digests (v1 documents via `test_plan_gate.V1_GOLDEN`; new v2 goldens for graph 2/3, runtime,
  input; bare `process.resolve(None, {}, None).digest`). `OffIdenticalTests` adds the stored plan revision (the
  whole revision record), the preview text and the home text, captured on the base (a clean `git archive HEAD`
  checkout; the goldens were re-verified against that checkout with this module copied in), for preset `/1` and
  for an explicit `gates.task: "off"`; the fixture's volatile identifiers (the checkout root, run ids and every
  hexadecimal run of six characters or more: digests, Git SHAs, the project id) are masked before hashing.
  `OffTests` keeps the lifecycle guard: `gates.task: "required"` still refuses `preview` as `process.unbuilt`.
- **A-2 Graph.** `GraphTests` (loop bound = `task_rounds` for 1/2/3/10, terminal and fail names, the proposer and
  critic output/signal shape, the `verifier` kind of both nodes, `node_instance` scope) and
  `InterpretedGraphTests` (interpreter over the real graph): round-1 acceptance stops the loop; reject → reasoned
  dispute accepted → accepted with the output readable by `read_review`; exhaustion at `task_rounds` → rejected
  after exactly the frozen rounds (1/2/10); proposer/critic errors → `proposer_failed`/`critic_failed`. The
  interpreter asserts the proposer receives the previous round's findings, and `GraphTests.test_the_proposer_has_no_write_path_to_the_artifact`
  shows no write binding reaches the `task` state. `AdmissionTests` (skipped without the pinned binary) submits
  the frozen graph/runtime/input to `zeroshot run … --validate-only` and requires `{"valid": true}` — the documents,
  not the graph's behavior: behavioral native qualification stays with the orchestrator.
- **A-4p Projection.** `ProjectionTests.test_tasks_checks_a_candidate_and_an_owner_note_change_the_digest` (task,
  check, an accepted steward candidate with a reword amendment and an owner note each move the digest; another
  milestone's briefs do not), `test_the_excluded_fields_do_not_change_the_artifact_digest`,
  `test_identity_matches_accepts_only_equal_identities` (artifact/config/HEAD each detected), and
  `ConfigIdentityTests` (a rules edit and a `limits.task_rounds` change each move the resolved configuration digest
  and the identity mismatch) cover artifact, configuration (rules and limits inside it) and HEAD.
- **A-6b Caps at the parser.** `ParserTests`: `task_rounds` 1/2/10 bounds; empty, malformed (not JSON, version,
  extra field, gap, missing field), inconsistent (last round ≠ final result) discussions; 4000/4001 characters per
  text and exactly 32768/32769 UTF-8 bytes overall (the sized helper hits both boundaries exactly).
- **R-3 contract of the proposer.** `ProposerContractTests` asserts the proposer is a `verifier` node (never the
  installing `step`), that its generated instructions require the round-two fixed-impossible/disputed
  classification *and* name the verifier response shape (verdict, diagnostic.message, output.taskResponse), while
  the plan gate keeps its own words; `PinnedGuidanceTests` reads the pinned binary and shows
  the install mandate sits only in the Worker block, the block a `step` node gets.
- **A-7a Compatibility.** The plan-gate suites pass on the base and on the candidate: in a scratch `git archive`
  copy of the base `test_plan_gate test_plan_override` → **75 tests OK**; on the candidate the same two modules →
  **75 tests OK**. New builders/helpers are covered by candidate-only mutations (below), not by base replay.

## Check results (candidate)

- `test_task_gate` — 24 OK (was 18; +6 regressions for the rejected findings).
- `test_plan_gate` — 44 OK; `test_plan_override` — 31 OK (plan-gate golden bytes and override behaviour unchanged).
- `test_process` — 88 OK; `test_tui_plan_gate` — 7 OK; `test_reference` — 33 OK (the new module adds no catalog
  family; generated `docs/REFERENCE.md` unchanged).
- `test_runs` — 52 OK; `test_milestone` — 35 OK; `test_terminal_planner` — 80 OK; `test_tui` — 32 OK.
- Contract for both new/repaired tests: each was shown to fail when its guarded behavior is removed (below).
- `git diff --check` — clean; no pre-commit configuration or hook exists in the repository.

## Mutations (candidate-only, scratch copy; never in the shared worktree)

Each was applied alone to a fresh copy (`shutil.copytree`, `.git`/`.tools` excluded) and the named test run there:

- **Invert one exclusion** (`EXCLUDED` keeps `plan_revision`) → `ProjectionTests.test_the_excluded_fields_do_not_change_the_artifact_digest`
  FAILED (1 test, 1 failure).
- **Drop one identity field** (`IDENTITY_FIELDS` loses `head`) → `ProjectionTests.test_identity_matches_accepts_only_equal_identities`
  FAILED (1 test, 1 failure).
- **Allow a proposer write path** (a `write("task", …)` binding added to the proposer) →
  `GraphTests.test_the_proposer_has_no_write_path_to_the_artifact` FAILED (1 test, 1 failure).
- **Proposer back to a `step` node** (`kind` "verifier" → "step") → `ProposerContractTests` FAILED (1 test, 1 failure).
- **Revert the proposer contract** (`TASK_PROPOSER_RETURNS` back to its pre-repair text: no
  fixed-impossible/disputed classification and the worker-shaped "Return only taskResponse") →
  `ProposerContractTests.test_the_authored_proposer_contract_requires_the_round_two_classification` FAILED.
- **Add a persisted evidence field** (`review_evidence` also stores `task_gate: None`, which the store's own
  revision validation accepts) → `OffIdenticalTests` FAILED for **both** configurations (2 tests, 2 failures)
  while the other 22 tests of the module passed. This is the case the acceptance review reproduced; the new
  goldens are the only tests that catch it.

## Environment / scope

- Dependencies need no install step: `pyproject.toml` pins `textual==8.2.8`, present at that exact version; there is
  no lockfile. Local interpreter Python 3.9.6; tests run from the checkout with `PYTHONPATH=.:tests`.
- Left to the orchestrator's merge gate (not claimed here): the full suite (~15 min) and the **native Linux
  qualification of the new task-gate graph** (the orchestrator runs it before merge, not the worker).
  `AdmissionTests` here is the documents' admission check only.
- Deliberately left out (other slices): the durable gate record, dispatch protocol and start barrier (s1a1b:
  parent R-2 record fields, R-4, R-5 dispatch, A-3, A-3b, A-5, A-6, A-7); UI/CLI adapters and docs (s1a1c: R-5
  keys, R-6, REFERENCE/USER_FLOW/PROCESS_PROFILE). No docs edits here; `prototype/`, `reference/`, `upstream/`,
  `delivery.py`, `runs.py`, `cli.py`, `catalog.py`, `tui/*` and the `process.py` guard are untouched.

## Interpretations (not fixed by the parent text)

- The gate output is `schemaVersion "1"` with `taskResponse/taskVerdict/taskFindings/discussion`; the parent fixes
  only the discussion shape and the record's field names, not the node output's. `read_review` returns
  `(verdict, findings, response, discussion)`; the record's `critic_verdict` is that verdict (s1a1b).
- `task_gate_runtime(roles)` takes the graph's own node keys ("proposer", "critic"); mapping resolved profile
  bindings onto them is the dispatch slice's business.
- Terminals are named `accepted_task_gate`/`exhausted_task_gate`/`proposer_failed`/`critic_failed` (the parent names
  the outcomes only); the graph seq node is `task_gate` and keeps the plan gate's `review_loop` shape.
- The proposer is a `verifier` node with the small extra surface a verifier node requires: a `verdict` signal that
  carries the proposed verdict and that nothing binds (only the critic's verdict is acceptance), and a
  `message` diagnostic; its instruction therefore names all three parts of the verifier response envelope
  (verdict, diagnostic.message, output.taskResponse). R-3 fixes "two read-only nodes", not their kinds or worker labels, and the worker label is
  a name only — zplan's milestone graph labels the same two kinds with its own refs — so the node kind selects the
  native contract.
- `identity_matches` compares two mappings keyed by `artifact_digest`/`resolved_config_digest`/`head` (built by
  `task_gate.identity`); the full validity predicate (terminal state, accepted verdict or checked override) stays
  with s1a1b, as does any storage.
- The A-1 goldens mask the fixture's volatile identifiers (checkout root, uuids, every hexadecimal run of six or
  more characters) so that they freeze the persisted field set and the wording of the journey rather than the
  fixture's random ids; a change to any *persisted* field or to the preview/home text still fails them.
- The task gate's refusal subject is `"проверки задач"`/`"задач"`; the plan gate's messages and stored bytes are
  unchanged. The `gate="task"` record constant belongs to the record slice.
