A2b — plan and brief edits as new revisions through the planning API, checked by the plan gate
(RELEASE_0.6.0_PLAN lane E step 2; ARCHITECT_DESIGN.md section 5). Design reviewed: ~/zs-pause/critic/a2b-design.out.

Why: today a plan changes only through feedback to the planner (`Runs.revise_plan`, runs.py:1480). The architect
(A5t) must change a task's brief exactly; the existing plan run is the independent check: the proposer presents
the draft, the critic judges it against the goal and the prior proposal.

Reuse: `Authority.begin`, `validate_revision`, `intent_identity`, `commit_terminal`, `validate_proposal`,
`check_bounds`, `canonical` (authority.py); `Planning.renew` (planning.py:313); the plan context (engine.py:1233).

Write-set: terminal_planner/planning.py, terminal_planner/authority.py, terminal_planner/engine.py,
tests/test_plan_edit.py (new), tests/test_plan_gate.py, tests/test_task_gate.py (golden hashes only).

Acceptance criteria:
- C1 Edit: `Planning.edit(version, plan)` with a full edited proposal: refused (`action.refused`, nothing written)
  unless `version` is the current revision with a proposal, `plan` passes `validate_proposal` + `check_bounds` and
  differs from it; else `begin(..., draft=plan)` (deepcopy) then the planner run as `revise`. Old revisions without
  `draft` load and keep `intent_identity` byte for byte; with a draft it joins the identity. Example: an edit that
  changes one task's `write_set` -> revision N+1 with that `draft`, status as after `revise`.
- C2 Prompt: with a draft, `context["draft"]` is set and the proposer text says to return it unchanged in every
  round, explaining any problem in `planResponse` instead of fixing it. Example: the plan input of an edit revision
  contains the draft; without a draft the input is unchanged.
- C3 Bound: in `commit_terminal`, with a draft, a proposal not `canonical`-equal to it (either verdict) ->
  `proposal_invalid` "the planner changed the edit", no proposal or evidence; the equality is checked again when the
  evidence is validated on load and approve. Example: the fake planner returns the draft with one title changed ->
  `proposal_invalid`; returning it as is -> `proposed`, `approve` works.
- C4 Carried: `renew`/`restart` of an edit revision keep its draft. Example: renew after `plan.stale` -> the new
  revision has the same draft.

Non-goals (reviewers must not require): edits while a milestone runs (A5e; `begin` keeps refusing); the architect
tool and TUI (A5t); partial or patch-form edits; a new native graph.

Risk: high (persisted plan schema, gate evidence). DoD: `python3.13 devtools/fasttest.py tests.test_plan_edit
tests.test_plan_gate tests.test_task_gate tests.test_terminal_planner tests.test_lifecycle_guard tests.test_toolchain`
exit 0; quote the `fasttest:` lines.
