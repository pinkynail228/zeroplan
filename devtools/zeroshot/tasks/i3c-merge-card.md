I3c — the stage-done card: «M1 готов», merge or see the changes in one click (0.5.2, docs/RELEASE_0.5.2_PLAN.md,
run i3c).

Card contract: devtools/zeroshot/tasks/card-contract.md (read first; builder `cards.merge_card(key, at, stage,
done, total)`, buttons `/merge`, `/diff`).

Today: a stage waiting for merge is a snapshot `Row` with `state == "awaiting_merge"` (`row.token` = latest attempt).
Merge from RunScreen: `modal_action(modal, "merge")` -> `guard_pending()` -> `app.confirm`
-> `begin_pending("merge", milestone)` -> `controller.merge(token, deliver(settled))`; `settled` assumes a modal. Task
counts exist only as the EndView body line from `Delivery.tasks_lines` («Задачи: 2/3 выполнены»);
`controller.open_run` returns the EndView. `MainScreen.open_diff_tab()` shows the selected row's diff.

Change: kind `merge`, key `merge:<milestone>:<attempt>`. Source: one card per `awaiting_merge` row; done/total read
from that attempt's EndView tasks line, fetched once per key off the event loop and cached (until it arrives, or
without that line, the card text has no counts: new id `card.merge_text_bare`). `awaiting_merge` joins
`AUTO_END_CARDS`. `/merge` for a merge card: no modal; `guard_pending`, `begin_pending`, `controller.merge` with a
modal-less settle (status-line note, `clear_pending`, refresh); success -> `close_card(key, card.merge_done)`
(new id «✓ M1 влит в main HH:MM», en/ru/zh); failure -> the outcome on the status line, the card stays (a conflict
moves the row out of `awaiting_merge`, so the source drops it). `/diff` from the card: select its row, then
`open_diff_tab()`.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/strings.py, docs/USER_FLOW.md (merge card paragraph),
tests/test_tui_merge_card.py (new), tests/test_tui_milestones.py (only assertions that RunScreen pops at an awaiting-merge
end: open it with [o] instead).

Acceptance criteria (joint example: fixture stage M1 attempt 1 ends awaiting merge, tasks line «Задачи: 2/3
выполнены», 120x40):
- A1 No RunScreen pops; the card reads «M1 готов», «2 из 3 задач …», buttons «влить», «посмотреть изменения»; at 80x24
  it is visible under the chat.
- A2 «влить» (or typed `/merge`) calls `controller.merge` once, no modal; the card reads «✓ M1 влит в main HH:MM».
- A3 «посмотреть изменения» opens the M1 diff tab in the canvas.
- A4 A second `/merge` while the first is pending is refused by `guard_pending`; merge is still called once.
- A5 [o] on the M1 row still opens RunScreen with the merge action.

Non-goals (reviewers must not require): removing RunScreen, conflict handling (run i3e2), inline history cards,
other card kinds.

DoD: `python3.13 devtools/fasttest.py tests.test_tui_merge_card tests.test_tui_card_hooks tests.test_tui_milestones
tests.test_tui_commands tests.test_toolchain tests.test_reference` exit 0; quote its `fasttest:` lines.
