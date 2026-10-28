s1a1a-gate-core — 0.5 item S1a, slice 1 of 3 of devtools/zeroshot/tasks/s1a1-task-gate.md (the parent; its Audit, Read list, R-* and A-* texts apply verbatim where cited). Lane L2 (docs/RELEASE_0.5_SCOPE.md Order). Slicing: critic swarm05 c (~/zs-pause/critic/swarm05.out). DeepSeek worker, sol reviewers.

Base: 6e23523a8be138fcfb848c9cbf6869ec74283604 (C2, intended v0.4.0 tag target; critic early-start AGREE). If the tag moves, the branch is integrated as an integration candidate with gates on the final SHA (ORCHESTRATOR step 2); record the actual base and this brief's sha256 in the receipt. Record the base commit in the receipt. The parent audit is on 74f1a3b: re-check every line number on the base, and re-gate if a premise moved. S1a has no semantic dependency on S2/S3 (critic swarm05 a).

Slices: s1a1a (this) = pure core; s1a1b = durable gate record, dispatch protocol and the start barrier (parent R-2 record, R-4, R-5 dispatch, A-3, A-3b, A-5, A-6, A-7); s1a1c = UI/CLI adapters and docs (parent R-5 keys, R-6, REFERENCE/USER_FLOW/PROCESS_PROFILE). The parent's "keep lifecycle and enforcement together" is preserved: `gates.task == "required"` keeps returning `process.unbuilt` until s1a1b lands, so no intermediate state lets an unguarded required start through.

Write-set (exclusive for this slice): new `terminal_planner/task_gate.py`; new `tests/test_task_gate.py`; in `engine.py` only the new task-gate graph/runtime/input builders next to `planner_graph_v2` (no dispatch wiring); in `authority.py` only the generalisation of the discussion parsing, override-reason validation and stale-message helpers, with the plan gate's behaviour and stored bytes unchanged. No edits to delivery.py, runs.py, cli.py, catalog.py, tui/*, process.py guard, docs.

Rules:
- R-1 Scope: parent R-1. Nothing in this slice is reachable from a user action; `/1` and `gates.task: "off"` stay byte-identical (graphs, normalized config, config digest, stored plan revision, preview/home text).
- R-2 Projection: parent R-2 first paragraph only — a pure function from the exact validated `bootstrap_manifest(baseline, context)` to the artifact, with exactly the parent's exclusions, and `artifact_digest` via the existing `digest()`. Plus a pure `identity_matches(gate_identity, live)` comparing artifact, resolved-config and HEAD digests, reused by s1a1b and s1c2; the full validity predicate (terminal state, accepted verdict or checked override) belongs to s1a1b with the record contract; no storage.
- R-3 Graph: parent R-3 in full (proposer + `critic`, `sessionScope: node_instance`, `maxIterations = limits.task_rounds`, terminals, bounded discussion with the plan gate's shape and caps, native failure distinct from rejection).
- R-4 Helpers: the generalised discussion/override/stale helpers are called by the plan gate unchanged; plan-gate golden bytes and existing tests pass unchanged.

Acceptance (unit tests, deterministic fixtures, no network or provider):
- A-1 Off is identical: parent A-1.
- A-2 Graph: parent A-2 in full.
- A-4p Projection: the projection-level part of parent A-4 — changing tasks, checks, an accepted candidate change, an owner note or the resolved profile (including limits) changes the digest; another milestone and the excluded fields do not; `identity_matches` reports a mismatch for each of artifact, config, rules (inside the config digest, process.py:9) and HEAD. The rest of parent A-4 (a new revision always needs its own gate; reruns and session_lost create new records) is s1a1b.
- A-6b Caps: parent A-6b parsing and caps (task_rounds 1, 2, 10; empty/malformed/inconsistent discussion; 4000/4001 chars per text; 32768/32769 UTF-8 bytes overall) at the parser; "invalid output creates no usable persisted evidence" is s1a1b.
- A-7a Compatibility: plan-gate compatibility tests pass on the base and the candidate. New builders and helpers are covered by candidate-only mutations (below), not by base replay; parent A-7 (the Delivery-entry base failure) is s1a1b.
- Mutations: invert one exclusion, drop one field from `identity_matches`, and allow a proposer write path; each must be caught by a named test.

Size: about 300-450 changed lines including tests. Above 600, stop and report for a re-gate rather than absorbing s1a1b work.

DoD: unit tests pass locally; receipt with base commit, file list, compatibility results, mutation results. No docs edits (s1a1c).
