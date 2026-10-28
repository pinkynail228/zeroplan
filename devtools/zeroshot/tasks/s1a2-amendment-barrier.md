s1a2-amendment-barrier — DEFERRED beyond 0.5 (critic session 01a15144, 2026-10-19: the pinned engine has no deterministic routing node, graph.rs:232 / runtime.rs:211, and no production record of each worker's received input exists, so neither prevention nor deterministic detection is possible without new native support). Do not run. Original draft: 0.5 item S1a (docs/RELEASE_0.5_SCOPE.md S1a row), child 2 of 2: the amendment barrier inside a milestone run. Design: docs/PROCESS_PROFILE.md "Stages on native graphs" (task gate, barrier during a run). DeepSeek worker, sol reviewers.

Base: main with s1a1-task-gate merged. Record the base commit in the receipt. The audit is on main 74f1a3b: re-check every line number on the base, and re-gate if a premise moved.

Audit (74f1a3b):
- Milestone graph:
  - `milestone.py:478` `task_iteration`: select -> worker -> reviews -> `steward_apply` -> `steward_decide`.
  - `task_loop` :479-483 stops only on done, needs_owner or blocked.
  - `steward_apply` may reword, split, add, reorder or drop tasks (:441-454). `steward_decide` (:455-465) signals needs_owner only for a rejected scope change or an owner-only decision.
  - Routing to `success("needs_owner", ...)` already exists (:487-488).
  - So today a contract-changing amendment reaches the next worker without a gate.
- Deterministic validator: `check_amendments` milestone.py:179 and `main`/`check` :526-545, which compares against `--before`.
- The owner side of needs_owner exists: runs.py:214 (accept_proposal / answer / revise), delivery.py:760, :834. After s1a1, accept and answer into a new attempt already require a valid task gate.

Read: terminal_planner/milestone.py, runs.py :200-260 and :1280-1360, delivery.py :750-840, engine.py (graph materialization and frozen config), the s1a1 changes; tests/test_milestone.py, test_runs.py, and the s1a1 tests.

Rules:
- R-1 Scope. Active only when the attempt's frozen resolved config has `gates.task == "required"`. With "off", the materialized milestone graph, its documents and its digests are byte-identical to the base.
- R-2 Contract change. Applied amendments of kind add, split or reword are a contract change, and so is any change to a task's checks. Reorder and drop are not; they reach the owner through the existing paths.
  - Detection is deterministic, in the validator (`check_amendments` / `check`), not in a prompt.
- R-3 Barrier. When R-1 is active and the iteration applied a contract change, the attempt ends in `needs_owner` before any further worker step.
  - The proposal carries the amended briefs and the list of changed task ids.
  - No worker sees the amended task.
- R-4 Owner path. The owner's accept (or revise) on that proposal leads to a new attempt only through s1a1's barrier: a gate on the amended briefs must be accepted or overridden first. The refusal names the gate key.
- R-5 Restart. A crash between `steward_apply` and the needs_owner terminal never lets the next worker run on restart.

Acceptance (unit tests with deterministic fixtures):
- A-1 Off is identical: golden comparison of the materialized graph and documents with `gates.task` off.
- A-2 Detection: one table test per amendment kind (add/split/reword/checks-change/reorder/drop) on the validator.
- A-3 Barrier, driven through the graph interpreter / fixture runner used by test_milestone.py: a reword in iteration 1 -> terminal needs_owner, the worker invocation count unchanged after the amendment, and the proposal contains the changed id.
- A-4 Owner path: accept -> refused `task.gate_missing` -> gate accepted on the amended briefs -> new attempt allowed. Revise -> new revision -> plan gate path.
- A-5 Restart, per R-5, with the fixture runner.
- A-6 Base failure: the new tests on the base fail on the intended assertions; symbol-dependent tests skip with a reason. Record the counts.

Size: about 300-500 changed lines including tests.

DoD:
- Unit tests pass.
- docs/PROCESS_PROFILE.md marks the barrier as built.
- Receipt: base commit and the A-6 counts.
- The orchestrator runs native qualification of the changed milestone graph on the Linux test host before merge.
