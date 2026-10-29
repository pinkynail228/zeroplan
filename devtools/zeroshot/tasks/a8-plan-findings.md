A8 — a rejected plan's findings reach the architect and the next revision; the architect revises, not edits

Tester 2026-10-28: a plan reached r5. After review_exhausted the architect saw only the verdict
(plan_fields, tui/controller.py:245), could only edit (returned byte for byte, engine.py:793-797), and the next
planner got no findings (engine.py:1358-1363; findings in evidence, authority.py:687-698).

Reuse: `Planning.revise` (planning.py:402), `_edit_tool`'s `_plan_job` path (controller.py:931), the tool list
(architect_tools.py:89-115), PLAN_CRITIC_BAR.

Write-set: terminal_planner/engine.py, terminal_planner/tui/controller.py, terminal_planner/architect_tools.py,
terminal_planner/architect.py, tests/test_plan_gate.py, tests/test_bridge.py, tests/test_architect_tools.py,
tests/test_architect.py, tests/test_plan_edit.py.

Acceptance criteria:
- F1 zplan_status's plan carries `findings`: the current revision's evidence findings (text, ≤ 4000 characters,
  cut with "…"), "" when it has no evidence. Example: r2 review_exhausted, findings "T3 has no example"
  -> plan.findings "T3 has no example".
- F2 A planner revision after a checked one gets `prior_review` in its task: {revision, verdict, findings} of the
  same revision `prior_proposal` comes from, frozen in the input; the planner text
  says to address it; planFindings and discussion still start "Not reviewed" and empty, and prior_review is never
  part of the new evidence. Example: r2 rejected "T3 has no example", owner revises -> r3's input task has
  prior_review {revision 2, verdict rejected, findings "T3 has no example"}; r3's discussion has no round from r2.
- F3 A tool `zplan_revise_plan {revision, feedback}`: refused unless `revision` is current and feedback is non-empty
  text; otherwise `Planning.revise(feedback)` in the same single `_plan_job` as zplan_edit_plan, allowed at every
  autonomy level like edit; result {revision, status}. Example: revision 2 current, feedback "add examples" ->
  revision 3, status ready; revision 1 -> refused, nothing written.
- F4 The architect instructions: after a rejected check, read the findings in zplan_status and call
  zplan_revise_plan naming them; zplan_edit_plan only for an edit whose exact text the owner gave. Example: the
  text holds both rules.
- F5 EDIT_CRITIC no longer says "report any problem as a finding": an edit is judged under PLAN_CRITIC_BAR.
  Example: the critic text of an edit revision contains the bar and not "report any problem".

Non-goals: a brake or cap on revisions, cards, TUI strings, override, translation, upstream, old revisions' graphs.

Conflict: a test outside the write-set pins the planner or critic text or the tool list -> change nothing, end
with `conflict: <file:line>`.

Risk: high (engine contract, plan input). DoD: once at the end, `python3.13 devtools/fasttest.py
tests.test_plan_gate tests.test_plan_edit tests.test_bridge tests.test_architect_tools tests.test_architect
tests.test_toolchain`: exit 0; `python3 devtools/budget.py`: OK. Each new test fails on the old code.
