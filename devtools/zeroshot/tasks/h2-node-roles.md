H2 — read-only nodes are verifiers, so the engine stops telling them to install dependencies

Astra review 2026-10-28 (pause dir, critic/harness-graph.out, item E): upstream appends setup guidance to every
`step` ("install manifest/lockfile dependencies", upstream/zeroshot/src/native_v2_runner/response/guidance.rs:13)
and read-only guidance to every `verifier` (:5, which allows artifacts). The planner (engine.py planner_graph_v2)
and milestone `select` are steps that only read and report, so users pay for the install text.

Reuse: the verifier node shape (output and `out` write bindings, as the plan critic uses); `signals: {}` is
admitted (upstream protocol/openengine-cluster/v1/graph.schema.json:449); the `verifier` helper in milestone_graph.

Write-set: terminal_planner/engine.py, terminal_planner/milestone.py, devtools/driver_qual.py,
devtools/plan_qual.py, tests/test_milestone.py, tests/test_plan_gate.py, tests/test_plan_qual.py,
tests/test_task_gate.py.

Acceptance criteria:
- R1 planner_graph_v2's `planner` is a `verifier` with `signals: {}`, an explicit diagnostic schema, and the same
  input, output, write bindings and instructions. Example: `planner_graph_v2(3)` planner kind "verifier", output
  proposal + planResponse, writeBindings unchanged.
- R2 milestone `select` is a `verifier` with `signals: {}`, the same output `task`, write binding, text and snapshot
  file. Example: `milestone_graph(1)` select kind "verifier"; select_verify unchanged; worker, repair and
  steward_apply stay steps.
- R3 Model bindings, session scopes and worker refs of both nodes are unchanged (the native role moving from worker
  to verifier is the point). plan_qual and driver_qual answer a verifier with empty signals and a non-null output.
  Example: driver_qual a_two_tasks_done keeps node order and output; test_plan_qual's planner fixture passes.
- R4 Stored documents stay readable: planner_graph() (v1) and its golden digests are byte-identical; the v2 goldens
  in test_task_gate change only for the node kind. Example: V1_GOLDEN assertions pass untouched.

Non-goals (reviewers must not require): merging select with select_init or select_verify; any prompt wording; the
steward; docs.

Conflict rule: if the pinned engine rejects a verifier with empty signals or a non-null output, change nothing
and end with `conflict: <file:line> <evidence>`.

Risk: high (planner and driver graphs). DoD: run once, at the end: `python3.13 devtools/fasttest.py
tests.test_milestone tests.test_plan_gate tests.test_plan_edit tests.test_plan_qual tests.test_task_gate
tests.test_toolchain`: exit 0; `python3 devtools/budget.py`: OK. Each new test fails with the node kinds
reverted. plan_qual and driver_qual are not run (owner 2026-10-28: no Linux qualification).
