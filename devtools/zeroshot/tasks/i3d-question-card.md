I3d — the owner-question card: «Нужно твоё решение · M1» with quick answers (0.5.2, docs/RELEASE_0.5.2_PLAN.md, run i3d).

Card contract: devtools/zeroshot/tasks/card-contract.md (read first; builder `cards.question_card(key, at, task, text,
buttons)`).

Today: a question is a `Row` with `state == "needs_owner"`; its text is only in the EndView body
(`controller.open_run(milestone, done)` -> `Outcome("end", data=EndView)`). RunScreen answers through
`NoteScreen(..., answer=True)` -> `controller.answer(token, text, deliver(settled))`, then `watch_run`; drafts through
`controller.answer_draft(identity, milestone, text, done)`.

Change: kind `question`, key `question:<milestone>:<attempt>`. Source: one card per `needs_owner` row; the question
text = the EndView body fetched once per key off the event loop and cached, ≤6 lines. Buttons «упростить»,
«разбить», «пропустить» send `/approve simplify|split|skip`; when an answer draft for that milestone can be sent, a
first button «отправить черновик ответа» (new id `card.answer_draft`) sends `/approve draft`.
`/approve` row for `question`: `draft` -> `answer_draft` (refusal: status line, card stays); a choice ->
`controller.answer(token, card.question_<choice> text)`, then `watch_run`; no argument -> the draft if any, else the
written note; other text -> refused. `/decline` row: `NoteScreen(..., answer=True, enter=True)` -> `controller.answer`. Success closes the card with `card.answer_sent` (new id «✓ ответ
отправлен HH:MM»). `needs_owner` joins `AUTO_END_CARDS`.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/strings.py, docs/USER_FLOW.md (question card paragraph),
tests/test_tui_question_card.py (new), tests/test_tui_milestones.py (only assertions that RunScreen pops at a
needs_owner end: open it with [o] instead).

Acceptance criteria (joint example: fixture M1 attempt 1 stops on «Тест T3 падает 3 раза: что
делать?», 120x40):
- A1 No RunScreen pops; the card shows the question and «упростить», «разбить», «пропустить»; visible at 80x24.
- A2 «упростить» calls `controller.answer` once with the simplify text; the card reads «✓ ответ отправлен HH:MM».
- A3 With an answer draft for M1 the draft button is first and sends through `answer_draft`; a `draft.stale` refusal
  shows on the status line and the card stays.
- A4 `/decline` opens the note; enter with «сделай без теста» sends exactly that; esc keeps the card.
- A5 Typed `/approve maybe` is refused on the status line; nothing is sent.

Non-goals (reviewers must not require): removing RunScreen or key [t], error cards (i3e), inline history cards,
other card kinds, retiring old tests (run i8).

DoD: `python3.13 devtools/fasttest.py tests.test_tui_question_card tests.test_tui_card_hooks tests.test_tui_milestones
tests.test_tui_chat tests.test_toolchain tests.test_reference` exit 0; quote its `fasttest:` lines.
