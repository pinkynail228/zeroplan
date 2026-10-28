C1b — the architect wakes only when it has something to do

Re-smoke 2026-10-26 (pause dir, dogfood, findings-2026-10-26-resmoke.md) #2, #3: 7 architect turns for one
slice; turns 3-5 (51k, 85k, 62k input) woke on its own plan approval and on accepted review verdicts and answered
«действий нет»; turn 7 reported a merge the architect had just requested. The event line read
«M1 попытка 1: unknown -> awaiting_merge». Plan docs/RELEASE_0.6.1_PLAN.md, C1.

Write-set: terminal_planner/feed.py, terminal_planner/tui/controller.py, tests/test_feed.py,
tests/test_feed_wiring.py, tests/test_tui_chat.py.

Acceptance criteria:
- C1 Events captured while one of the architect's own actions runs (controller.py:679 `_bridge_action`, its job,
  both the bridge job and the plan job) carry wake false: the architect learns that result from the tool's answer.
  The events still ride along with the next wake batch. Example: auto, the architect's zplan_approve_plan -> the
  plan event «proposed -> approved» has wake false; the owner's /approve of the same plan -> wake true (RS5).
- C2 A verdict event (feed.py:176 `verdict`) wakes only when its verdict is not "accepted". Example: code_review
  accepted -> wake false; acceptance_review rejected -> wake true.
- C3 The transient `unknown` state (runs.py:298, finished with no outcome yet) is not captured as an event and is
  not stored as the last state, so the next event names the real previous state. Example: running -> (unknown) ->
  awaiting_merge gives one event «running -> awaiting_merge».
- C4 Every other event keeps its wake rule (WAKE, PLAN_WAKE) and text; a run that ends in a WAKE state after the
  action's job returned (a later observation) still wakes. Example: M1 reaches awaiting_merge in an observation
  job after the architect's zplan_start -> wake true.
- C5 `validate_feed` (feed.py:335 state branch, now `wake == (state in WAKE)`) accepts a state event with wake
  false for any state; wake true still needs a WAKE state. Schema, other checks, batching and ack are unchanged; a
  stored feed with `unknown` last states or wake-true verdicts loads. Example: a saved «awaiting_merge» event
  with wake false validates; «running» with wake true is refused.

Non-goals (reviewers must not require): the method text; status or event-line wording beyond C3; the merge card
in `auto` (P2); chat.py; token measurement (release smoke).

A test outside the write-set asserting a changed wake flag, event list or turn count -> `conflict:`.

Risk: high (wake rules decide whether `auto` progresses). DoD: `python3.13 devtools/fasttest.py`
tests.test_feed, tests.test_feed_wiring, tests.test_tui_chat, tests.test_process, tests.test_tui_draft_card,
tests.test_tui_failed_card, tests.test_tui_question_card, tests.test_bridge: exit 0.

Attempt 2: preflight conflict C1 vs C5 (validate_feed pinned wake to WAKE for state events); C5 now relaxes it.
