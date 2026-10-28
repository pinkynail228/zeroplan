U1 — the bar says what happens now: the architect's turn is visible, a cancelled turn is not silent

UX audit 0.6.0 (docs/ui-redesign/audit-0.6.0/AUDIT.md F02, F17), owner Mac test O4 "I don't understand what
happens". Plan docs/RELEASE_0.6.1_PLAN.md "MVP". Today the bar (`MainScreen.show_keys` / `bar_job`, tui/app.py;
`Bar`, tui/activity.py) says «работы нет» (`bar.idle`) while the architect thinks (`ArchitectChat.busy`,
tui/chat.py, read only); Esc that cancels a turn leaves no line.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/activity.py, terminal_planner/tui/strings.py,
tests/test_tui_activity.py, tests/test_tui_commands.py.

Acceptance criteria:
- C1 Nothing runs (bar job None) and an architect turn runs (an owner message, an event batch, the `/new`
  warm-up) -> the job phrase is «архитектор отвечает {clock}», the clock counting from when the screen first saw
  the turn busy. Example: idle, send «привет» -> «архитектор отвечает 0:03».
- C2 A job and an architect turn at once -> the job's phrase, then « · архитектор отвечает»; on a narrow bar
  this tail is dropped first. Example: M1 running at 120 columns + an event turn -> «… 4:10 · архитектор
  отвечает»; at 80 columns the job phrase alone.
- C3 When the turn ends, the phrase returns to the job's own (or «работы нет») at the next refresh, at most 1 s
  later. Example: the reply arrives -> «работы нет».
- C4 Esc that cancels the owner's running turn shows «Ответ архитектора отменён.» in the `#status` area until the
  next send. Example: send, Esc -> the line; send again -> the line is gone.

Non-goals (reviewers must not require): chat rows and their wording (O4); run, round or review wording; the
architect's turn kinds named apart; English or Chinese copy beyond what strings.py requires; tui/chat.py.

New tests go in tests/test_tui_activity.py; tests/test_tui_commands.py changes only where it pins `bar.idle`
during a turn.

A test outside the write-set asserting «работы нет» while a turn is busy -> `conflict:`.

Risk: medium (main-screen bar). DoD: `python3.13 devtools/fasttest.py` tests.test_tui_activity,
tests.test_tui_commands, tests.test_tui_chat, tests.test_tui_strings, tests.test_tui, tests.test_toolchain: exit 0.
