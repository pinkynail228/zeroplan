# v6e — `zplan_plan {goal}`: in a turn the owner started, the architect sends the goal to the planner

docs/PLAN_UX.md V6 (owner decision Q6; design dir v6-chat-consent.md D3 and its "After Astra's review" part).
The architect has no tool to start planning: `zplan_edit_plan`/`zplan_revise_plan` need an existing revision
(architect_tools.py:89-102), so after "Add a changelog" the architect writes a goal draft and the owner still types
/plan (v3e: "Draft saved in Drafts. Use /plan ..."). The owner's path is `Controller.start_planning(goal, done,
draft=None, card=False)` (tui/controller.py), a `_plan_job` whose verdict the screen hands to the planner watch;
the two plan tools are posted as plan jobs from the socket thread (`PLAN_TOOLS`) and a "ready" verdict goes to
`on_plan_submission` (controller.py:1481-1500) so the app's planner watch dispatches it. v6a/v6b bind each request
to the owner turn that made it.

Change:
- A new action tool `zplan_plan {goal}` (string, the goal as the owner's words or the architect's restatement of
  them). Admitted only with an owner binding; an events binding is refused (family autonomy.ask, "only on the
  owner's word"). It runs the owner's own start-planning work in one `_plan_job` (goal validation, profile guard,
  readiness gate, the unsent revision when readiness fails, the submission), plan operation "plan" with origin owner
  via chat (v2g/v6b result shape); a "ready" verdict goes to `on_plan_submission` exactly as the plan tools do.
- It grants nothing else: approving the plan stays the approval rules of the level.
- TOOL_RULES (architect.py): when the owner asks for a plan, call zplan_plan with their goal instead of asking them
  to type /plan; never call it in a turn the owner did not start.

Write-set: terminal_planner/architect_tools.py, terminal_planner/architect.py, terminal_planner/tui/controller.py,
tests/test_bridge.py, tests/test_architect_tools.py, tests/test_architect.py

Acceptance criteria:
- A1 Owner turn plans. Example: no plan, an owner turn calls zplan_plan {"goal": "Add a changelog"} -> revision 1 is
  sent to the planner; results[-1] {operation plan, outcome sent, origin owner, via chat}.
- A2 Events refused. Example: an event turn's zplan_plan -> refused, no revision created.
- A3 Readiness. Example: the origin item fails -> outcome unsent with the origin line, the goal kept as the unsent
  revision, as the owner's own path does.
- A4 The architect is told. Example: the first prompt holds the zplan_plan line; the method file within 4600 bytes.

Non-goals (reviewers must not require): sending a specific Drafts entry by id, the settings tool, the screen.

Conflict rule: a test outside the write-set pinning the tool list: change nothing, end with `conflict: <file:line>`.

Risk: high (consent policy). DoD: `python3.13 devtools/fasttest.py tests.test_bridge tests.test_architect_tools
tests.test_architect tests.test_consent tests.test_tui_planning`: exit 0.
