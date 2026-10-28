s1a1-task-gate — 0.5 item S1a (docs/RELEASE_0.5_SCOPE.md S1a row), the G2 task gate before new attempts. The in-run amendment barrier (s1a2) is deferred beyond 0.5. Design: docs/PROCESS_PROFILE.md ("Gate discussion", "Gate record", "Stages on native graphs", "Acceptance scenarios"). DeepSeek worker, sol reviewers.

Base: main after the S2 and S3 children are merged (order in RELEASE_0.5_SCOPE.md). Record the base commit in the receipt. The audit is on main 74f1a3b: re-check every line number on the base, and re-gate if a premise moved.

Audit (74f1a3b):
- Plan gate (G1b), to mirror:
  - graph `engine.py:422` `planner_graph_v2(rounds)`: proposer `planner` :450 and verifier `critic` :441, signals accepted/rejected, `review_loop` :462 with `maxIterations` :467, terminals accepted_review / exhausted_review / critic_failed :477-479;
  - runtime `planner_runtime_v2` :484, with `sessionScope: node_instance` for both nodes;
  - input `planner_input_v2` :491; dispatch :717-723.
- Gate evidence `authority.py:586` `review_evidence`.
  - Fields at :598-601: gate, artifact_digest, resolved_config_digest, head, rounds_used, rounds_limit, discussion, critic_verdict.
  - Discussion: `bad_discussion` :897, `read_discussion` :901, `read_review` :935.
  - Stale: `GATE_STALE` :333 / `plan.gate_stale` :757, :786; live digest `process.py:669`.
  - Override: `override` :767, `validate_override` :566, `override_reason` :802.
  - Accepted-or-overridden: :546-549 and :754.
  - All of this is stored inside the plan revision record, with `gate == "plan"` hard-coded.
- `process.unbuilt`: `ProcessProfile.guard` process.py:640, task branch :655, messages `UNBUILT` :49-50. The preset `/1` is at :58-66 (task "off"); `limits.task_rounds` defaults to 2.
- Attempt entry points the gate must cover:
  - service: `Delivery.guard` delivery.py:527, called by preview :534, start :571, `live_roles` :824 and new_attempt :829;
  - runs: `Runs.start` runs.py:586, retry :1284, steward-proposal accept :1342, answer (runs.py:214 actions);
  - CLI: cli.py:621-630, :307, :715, :747;
  - TUI: tui/controller.py:637-649, :805; tui/app.py:2272, :2515.
- The milestone's frozen briefs are the deterministic `milestone.py:57` `build_baseline(proposal, milestone_id, plan_revision)`, already computed in preview (runs.py:1257). There is no briefs digest yet; `digest()` is authority.py:159.

Read: those locations; terminal_planner/engine.py, authority.py, process.py, delivery.py, runs.py, milestone.py :40-130, planning.py :340-370 and :470-545, cli.py, catalog.py, tui/controller.py, tui/app.py; docs/PROCESS_PROFILE.md, docs/USER_FLOW.md, docs/REFERENCE.md (generated from the catalog); tests/test_plan_gate.py, test_plan_override.py, test_tui_plan_gate.py, test_process.py (GuardTests, GateTuiTests), test_runs.py.

Rules:
- R-1 Scope. The task gate acts only when the resolved config has `gates.task == "required"`; then it replaces the `process.unbuilt` refusal for milestone actions. With `gates.task == "off"` (preset `/1`, the default), every graph, record, digest, screen and refusal is byte-identical to the base. The merge gate stays `process.unbuilt`. Do not add preset `/2` (that is S1d).
- R-2 Artifact. Compute the artifact from the exact validated bootstrap_manifest(baseline, context) used by the pending start (`Runs.bootstrap_manifest` runs.py:128), including accepted candidate changes and owner notes. Exclude only plan_revision, baseline.plan_revision, baseline.limits, progress and outcome. Gate submission and every start path must use the same pure projection before any mutation. Its `artifact_digest` uses the existing `digest()`. Each gate run has a unique identity, indexed by (plan revision, milestone id); reruns and session_lost create new records without overwriting earlier evidence. A record holds, in addition to the plan submission protocol fields (frozen graph/runtime/input, native binding, submission key, uncertainty recorded before dispatch, terminal identity, output digest):
  - gate="task";
  - artifact_digest;
  - resolved_config_digest;
  - head = the destination HEAD at gate start;
  - rounds_used and rounds_limit (`limits.task_rounds`);
  - discussion;
  - critic_verdict;
  - override.
  The frozen resolved config (including `gates.task`) is part of the gate identity and of the restored state of a required attempt. Store it in its own Authority record type, not inside the plan revision. Reuse the existing helpers (discussion parsing, override validation and reason rules, stale message) by generalising them; keep the plan gate's behaviour and stored bytes unchanged.
- R-3 Graph. Add a task-gate graph: two read-only nodes, a proposer and a `critic`, both with `sessionScope: node_instance`, and `maxIterations = limits.task_rounds`.
  - Inputs: the projected briefs, the repository at HEAD (read-only) and the rules files.
  - The proposer presents the briefs with a proposed verdict. From round 2 it answers each finding as fixed-impossible / disputed + why; it can never change the artifact.
  - The critic accepts, accepts a reasoned dispute, or repeats concrete unresolved findings.
  - Terminals: accepted / exhausted (= rejected) / critic_failed. Output: the versioned bounded `discussion` with the plan gate's shape and caps.
  - Native failure (`*_failed`, `session_lost`) is a distinct outcome from rejection. Native `succeeded` is not acceptance; only `critic_verdict == accepted` is.
- R-4 Barrier at start. With R-1 active, the following require a valid gate for the (approved revision, milestone):
  - start;
  - retry / new_attempt;
  - accepting a steward proposal into a new attempt;
  - answering into a new attempt.
  A gate is valid when its critic_verdict is accepted or it is overridden, and its artifact digest, resolved config digest (rules are already inside it, process.py:9) and destination HEAD all equal the live values. Enforce the shared start check on the exact effective artifact before Runs.start performs refresh or persistence.
  - Otherwise the action is refused before any side effect: no run, no worktree, no record. The refusal family is `task.gate_missing`, `task.gate_rejected` or `task.gate_stale`, with a catalog message naming the fix key.
  - Preview stays read-only and shows the gate status.
  - Unbypassable from TUI, plain and CLI. The single shared check lives in the service (Delivery or Runs), not in the UIs.
- R-5 Lifecycle. Running the gate is an explicit owner action (TUI key, plain and CLI command, named in the catalog and styled like the existing plan-gate actions).
  - Dispatch follows the plan submission protocol: a crash after dispatch never duplicates the run, and a restart mid-gate resumes observing or reports the uncertainty.
  - A rejected or exhausted gate shows its findings. Recovery is either "revise the plan" (new revision -> plan gate -> new task gate) or an override with a typed reason, using the plan gate's reason rules. The critic verdict stays as it was; the override is shown on the gate, preview and status.
  - A stale gate shows "проверка устарела" and the rerun key.
  - `[i]` on the gate shows the discussion, like the plan gate.
- R-6 Display. Profile display: task gate no longer "для следующих этапов" when required. Home/preview: the gate state per milestone (не проверено / идёт / принято / отклонено / переопределено / устарело). Same text in TUI and plain; REFERENCE.md regenerated.

Acceptance (unit tests with deterministic fixtures; no network, no real provider):
- A-1 Off is identical. With preset `/1` and with an explicit `gates.task: "off"`, golden checks show the graphs, the normalized config, the config digest, the stored plan revision and the preview/home text unchanged from the base. Existing suites pass unchanged.
- A-2 Graph. The task-gate graph validates with the same interpreter tests as the plan gate (test_plan_gate.py Interpreter / InterpretedGraphTests style):
  - reject -> accept in round 2;
  - a reasoned dispute accepted;
  - exhaustion at `task_rounds` -> rejected;
  - critic error -> critic_failed;
  - the proposer has no write path to the artifact.
- A-3 Barrier. With `gates.task: "required"`, each entry point in R-4, through service, CLI, plain and TUI pilot, is refused before any side effect in each of these states:
  - no gate;
  - a gate that is running;
  - rejected;
  - exhausted;
  - critic_failed;
  - session_lost;
  - stale by artifact, by config, by rules and by HEAD.
  "No side effect" is asserted by snapshotting the Authority store and the workspace directory. Each action is allowed after an accepted gate and after an override.
- A-3b Owner paths. Using existing needs_owner records, test accepted-candidate and owner-answer starts: the original gate refuses the changed effective artifact without mutation; a gate on that exact artifact permits the new attempt; changing the candidate or answer again invalidates permission.
- A-4 Invalidation. Changing the milestone's tasks or checks, an accepted candidate change or owner note, the profile (including resolved profile limits), a rules file or the destination HEAD makes the gate stale. The projection exclusions are exactly those listed in R-2; resolved profile limits remain part of the configuration identity. Another milestone does not change this artifact digest, but a new revision always requires its own gate. Reruns and session_lost create new records without overwriting earlier evidence.
- A-5 Protocol. With fault injection at the submission boundary (not FixtureScenarioTests alone, which do not cover the crash protocol): crash after dispatch -> restart -> the same native run is observed, with no second submission. An uncertain submission is reported, never resubmitted silently.
- A-6 Override. A reason outside the plan gate's rules is refused. Overriding keeps critic_verdict and is visible in preview, home and plain status. The override digest binds the evidence. Override is allowed only for valid, current, completed rejection evidence. Missing, running, malformed, stale, native-failed and session_lost gates cannot be overridden; assert refusal without mutation for each case.
- A-6b Caps. Test task_rounds=1,2,10; empty/malformed/inconsistent discussion; 4000/4001 characters per text and 32768/32769 UTF-8 bytes overall. Invalid output creates no usable evidence.
- A-7 Base failure. Compatibility tests (A-1) must pass on base. Include a regression through an existing Delivery entry point that expects task.gate_missing for required/no-gate; base must fail because it returns process.unbuilt. Exercise all new safety invariants on the candidate. Symbol-dependent skips do not establish base failure. Run the new tests on base with a scratch commit; report named assertion failures and skips separately in the receipt and test docstrings.

Not in this task: the in-run amendment barrier is deferred beyond 0.5; this task gates new attempt starts only; preset `/2` (S1d); the merge gate (S1b/S1c); spend limits (S9b1).

Size: about 700-1000 changed lines including tests. Keep the gate lifecycle and start enforcement together as one invariant. Above 1500 changed lines, report it in the receipt for a scope re-gate against the implemented artifact contract; do not omit acceptance or split at an unusable intermediate state.

DoD:
- Unit tests pass locally.
- `docs/REFERENCE.md` regenerated; docs/USER_FLOW.md updated for the gate step; docs/PROCESS_PROFILE.md marks G2-start as built.
- Receipt: base commit, the A-7 counts, and the file list.
- The orchestrator runs native qualification of the new graph on the Linux test host before merge (not the worker).
