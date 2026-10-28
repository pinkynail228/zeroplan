I3b — the plan-approval card on the main screen: «План · N этапов · M задач», approve / revise in one click
(0.5.2, docs/RELEASE_0.5.2_PLAN.md, run i3b). Today approving takes PlanScreen, [a] and a confirmation modal.

Card contract: devtools/zeroshot/tasks/card-contract.md (read it first; builder `cards.plan_card(key, at, stages,
tasks)`, buttons `/approve`, `/decline`).

Today: a proposed plan is `snapshot.version is not None and snapshot.status == "proposed"`. Approve:
`ZplanApp.decide("approve", version)`; revise: `NoteScreen()` -> `ZplanApp.revision_note(text)`. The counts exist
only in the plan summary line `PlanView.lines[1]` ("План r1 · 1 этап · 3 задачи · проверен", fields split on " · ").

Change: kind `plan`, key `plan:<version>`. Source: one card while the plan is proposed, counts taken verbatim from
that line (no counts in the line -> the card without them). `/approve` row: `decide("approve", version)` with no modal,
then `close_card(key, card.plan_done)`; a refusal keeps the card and shows the existing error. `/decline` row: the
revise note with `enter=True`; the card stays while the note is open or cancelled; the revision start ends the
proposed state, so the source drops it. PlanScreen and its keys stay.

Write-set: terminal_planner/tui/app.py, docs/USER_FLOW.md (plan card paragraph), tests/test_tui_approve_card.py (new).

Acceptance criteria (joint example: fixture plan r1 proposed, line "План r1 · 1 этап · 3 задачи · проверен", 120x40):
- A1 The card reads «План · 1 этап · 3 задачи» with «да, утвердить» and «нет, доработать»; at 80x24 it is visible
  under the chat.
- A2 «да, утвердить» (or typed `/approve`) calls `decide("approve", 1)` once, no modal; the card reads
  «✓ утверждён HH:MM».
- A3 «нет, доработать» opens the note; enter with «короче» calls `revision_note("короче")`; esc keeps the card.
- A4 Approving r1 through PlanScreen takes the card off on the next render.
- A5 A refused approve (decide raises Blocked «план устарел») keeps the card open and shows the reason.

Non-goals (reviewers must not require): removing PlanScreen, reject/override on the card, inline history cards
(run i3-chat-inline), translations, other card kinds.

DoD: `python3.13 devtools/fasttest.py tests.test_tui_approve_card tests.test_tui_card_hooks tests.test_tui_draft_card
tests.test_tui_commands tests.test_toolchain tests.test_reference` exit 0; quote its `fasttest:` lines.
