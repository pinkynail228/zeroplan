RS2 — re-smoke repairs: stale approve, /retry, /status, empty stage, run confirm

Re-smoke 2026-10-25b (~/zs-pause/dogfood/findings-2026-10-25b.md) med defects 2, 3, 4, 6 and old #5.

Write-set: terminal_planner/planning.py, terminal_planner/authority.py, terminal_planner/tui/slash.py,
terminal_planner/tui/card_kinds.py, terminal_planner/tui/app.py, terminal_planner/tui/activity.py,
terminal_planner/tui/strings.py, terminal_planner/catalog.py, docs/REFERENCE.md, tests/test_tui_slash.py,
tests/test_tui_commands.py, tests/test_tui_palette.py, tests/test_tui_approve_card.py, tests/test_tui_planning.py,
tests/test_plan_override.py, tests/test_reference.py, tests/test_tui_activity.py, tests/test_tui_strings.py,
tests/test_tui_failed_card.py, tests/test_tui_run_command.py, tests/test_ux.py, tests/test_terminal_planner.py.

Acceptance criteria:
- C1 A stale proposal (planning.py:611, `authority.fresh()` False) offers no approve: not in the view's actions,
  not on the plan screen, not on the chat plan card (card_kinds.py:602 offers «доработать» instead). The refusal
  (authority.py:866, :899) reads in Russian with a «Дальше:» step. Example: plan ready, commit to main -> plan
  screen shows «доработать», no «утвердить»; `/approve` -> «Проект изменился после планирования… Дальше: /view
  → доработать».
- C2 Typed `/retry` does what the card's «новая попытка» button does (card_kinds.py:95, :692, :813) in every state
  a card offers it, and the palette lists it there. Example: a failed plan card -> typing `/retry` restarts it,
  as pressing the button does.
- C3 `/status` (card_kinds.py:84) also writes one chat note: plan revision and status, each milestone and its state,
  the running job. Example: idle after a merge -> «План r1 · утверждён · M1 влит».
- C4 The bar and canvas title (activity.py:52, app.py:537) never show an empty stage. Example: slash state `error`
  with no matching milestone row -> no « · остановлен: ошибка» with a blank name before it.
- C5 The `/run` confirm (app.py:1719, focus on «да») names what Enter does; the others keep «нет». Example: `/run`
  -> its key line reads that Enter starts; `/merge` -> Enter is «нет».

Non-goals (reviewers must not require): export (RS1); palette listing of `/run`; «Что происходит» during planning;
cost; the low defects.

A test outside the write-set asserting a changed text, action or command list -> `conflict:`.

Risk: medium. DoD: `python3.13 devtools/fasttest.py` changed test modules, tests.test_reference: exit 0.
