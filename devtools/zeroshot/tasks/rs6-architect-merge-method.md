RS6 — the architect merges on its own evidence and leaves an approved plan alone

Delivery smoke 2026-10-26 #2, #3 (pause dir, dogfood, findings-2026-10-26-delivery.md): at awaiting_merge the
architect asked the owner for the worktree path ("zplan_status does not show it"); it edited an approved plan
unasked and reported a refused approval as a blocker. Critic r060-tag #3-#5. RS5 adds plan events (feed).

Write-set: terminal_planner/tui/controller.py, terminal_planner/resources/architect_method.md,
tests/test_architect.py, tests/test_tui_chat.py, tests/test_tui_live.py.

Acceptance criteria:
- C1 A `zplan_status` row (controller.py:627 `_rows_job`) in `awaiting_merge` carries `merge`: result commit,
  milestone branch, destination branch, changed files against the destination (at most 20, then a count), the
  live profile's `gates.merge` and check names, and `decision` = `autonomy.decide(level, "merge", gate)`. Rows
  in other states are unchanged. Example: M1 awaiting_merge, gate required, auto -> `merge.decision` "allow",
  `merge.files` lists `textkit.py`.
- C2 Method, Merge: at awaiting_merge with decision allow and accepted review verdicts, request `zplan_merge`;
  that action builds the integrated candidate and runs the checks and the critic, so never wait for a green
  candidate first and never ask the owner for paths; with decision ask, tell the owner in one line what to
  decide. Example: method text holds "zplan_merge" in the Merge section.
- C3 Method, plan events: proposed with an accepted verdict -> approve when the level allows and it matches the
  owner's direction, else ask; approved -> start the first ready milestone when the level allows; a planning
  failure -> report it with the next step. Example: method text names `zplan_approve_plan` and `zplan_start`.
- C4 Method: an approved plan is changed only on the owner's request or a run's evidence that it is wrong (name
  it); a refused action is reported as refused with its reason, never as done. Example: method text holds both.
- C5 The method file stays at most 4096 bytes (test_architect.py:658) and generic: make room by tightening
  existing wording, dropping no rule. Example: `wc -c` <= 4096.

Non-goals (reviewers must not require): feed or event changes (RS5); Controller policy or enforcement;
verdicts in the status (verdict events carry them); TOOL_RULES; the C1a status-in-event work.

A test outside the write-set asserting a changed status payload or method text -> `conflict:`.

Risk: medium. DoD: `python3.13 devtools/fasttest.py` tests.test_architect, tests.test_tui_chat,
tests.test_tui_live, tests.test_tui_split, tests.test_tui_question_card, tests.test_bridge: exit 0.
