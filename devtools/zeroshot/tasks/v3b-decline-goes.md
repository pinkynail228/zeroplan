# v3b — the plan's "decline" action goes: it changes nothing and still asks a question

docs/PLAN_UX.md V3 (Astra's design review: remove the action itself, not only its confirmation). `Planning.reject`
(planning.py:439) only checks the revision is the current proposed one: "Declining changes nothing: the proposal
stays as it is, nothing is started." Yet it is offered everywhere a proposal is: the plan actions
(planning.py:663), the catalog entries `plan`/`tui_plan` "reject" (catalog.py:547, 682), the plain CLI
(cli.py:517-528, 613), the plan screen's button with its own "Reject proposal rN?" confirmation (tui/screens.py:80,
215-219), `ZplanApp.decide("reject")` (tui/app.py) and `Controller.reject_plan` with its v2a result. An owner who
does not want a proposal revises it, asks the architect, or simply does nothing.

Change: the action is removed end to end: no "reject" in the offered plan actions, no catalog entry, no CLI key, no
button or confirmation, no `decide` branch, no `reject_plan`, no "reject" operation in results; `Planning.reject`
goes too. An old typed key or command for it gets what any unknown key or command gets today. The architect's
TOOL_RULES line that lists what stays the owner's keeps "a rejection" only if it means something else; check and
leave it if so.

Write-set: docs/REFERENCE.md (generated from the catalog), terminal_planner/planning.py, terminal_planner/catalog.py, terminal_planner/cli.py,
terminal_planner/tui/screens.py, terminal_planner/tui/app.py, terminal_planner/tui/controller.py,
tests/test_reference.py, tests/test_tui_approve_card.py, tests/test_tui_planning.py, tests/test_tui_live.py,
tests/test_tui_auto_plan_card.py, tests/test_terminal_planner.py

Acceptance criteria:
- A1 Not offered. Example: a proposed plan r1 -> its actions are approve, revise, requirements (and info on the
  screen); a stale one -> revise, requirements.
- A2 Nowhere to call. Example: `Controller` has no reject_plan, `Planning` no reject; the plan screen has no decline
  button.
- A3 Nothing else moves. Example: approve, override and revise behave and report results as before.

Non-goals (reviewers must not require): the consent card's and the question card's own "decline" (different
actions), the plan critic's "reject" verdict, documentation pages.

Conflict rule: if a test outside the write-set pins the reject action, change nothing in it and end with
`conflict: <file:line>`.

Risk: low (removal). DoD: `python3.13 devtools/fasttest.py tests.test_reference tests.test_tui_approve_card
tests.test_tui_planning tests.test_tui_live tests.test_tui_auto_plan_card tests.test_terminal_planner`: exit 0.
