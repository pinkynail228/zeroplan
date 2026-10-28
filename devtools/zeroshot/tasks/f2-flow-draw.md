F2 — the Сейчас tab draws the active milestone attempt as a flow of boxes (drawing half of the flow slice, docs/CHAT_RELEASE_JTBD.md "Visual target of Сейчас"; owner reference: worker box → parallel reviewers → delivery box, legend, session log strip, status line; no percentages).

Goal: while a milestone runs, a glance at Сейчас shows which step is working, the round, how long it has been silent, the last command and each reviewer's verdict, drawn as linked boxes instead of text lines.

Data reach: `Home.flow` (terminal_planner/delivery.py, F1) = None or a plain dict from `live.flow` (terminal_planner/live.py): task, round, rounds, worker {state}, reviewers [2 × {role, name, state: running|accepted|rejected|waiting|other, text}], final {state}, select (bool), active (list of role words), elapsed, silence (seconds or None), command (text or None), detached (stamp or None). `Home.journal` = `HH:MM:SS  text` lines, oldest first. The Сейчас tab (C0c2, terminal_planner/tui/app.py: `live_view()` builds its lines into the `#live` Static inside `#live-pane`, wrapped to `scrollable_content_region.width`) renders `snapshot.panel` plus the status lines today; `live.duration(seconds)` formats durations.

Write-set: new terminal_planner/tui/flow.py (pure drawing), terminal_planner/tui/app.py (Сейчас uses it), terminal_planner/tui/zplan.tcss, new tests/test_tui_flow.py, existing TUI tests only where they quote Сейчас content for an active attempt.

Acceptance criteria:
- A1 `flow.draw(flow, journal, width)` (pure: no app, no I/O) returns a list of `rich.text.Text` lines, none wider than `width`, for width 40..120:
  1. a legend line: a coloured ■ and the word for исполнитель, приёмка, ревью кода, итоговая проверка (one fixed colour per role, the same colour as that role's box border);
  2. the worker box (full width, rounded box-drawing border): title «исполнитель»; «<task> · раунд N из M» (or «раунд N», or nothing without a task); when running: «идёт <elapsed> · молчит <silence>» when silence ≥ 120 s else «идёт <elapsed>», then «последнее: <command>» cut with «…» to fit;
  3. a connector that splits into two (│, ┬/┴ style), then the two reviewer boxes side by side, each half the width: the role word, and the state: running «● проверяет», accepted «✓ принято», rejected «✗ отклонено», waiting «· ждёт», other the raw string; for accepted/rejected the text wrapped to at most 2 lines and cut with «…»;
  4. a joining connector, then the delivery box: «итоговая проверка» running «● проверяет» / waiting «· после всех задач», and the line «результат → main: [m] после проверки»;
  5. a rule titled «журнал» followed by the last 4 journal lines (fewer when fewer exist), each cut to the width;
  6. one status line: «активны: <active words joined by ", ">» or «активны: —», and «наблюдение прервано — [w]» when detached.
- A2 The box of every running role has a bold border in its colour; finished boxes (✓/✗) a normal border; waiting boxes a dim border. When `select` is true and nothing else runs, the worker box title reads «выбор задачи».
- A3 Below width 40 (or when `flow` is None) `draw` is not used: Сейчас shows exactly what it shows after C0c2.
- A4 In the app, Сейчас shows `flow.draw(snapshot.flow, snapshot.journal, <tab content width>)` while `snapshot.flow` is not None, followed by the planner/run status lines C0c2 already shows there; it redraws on every refresh and on resize. План and the chat are unchanged.
- A5 Tests: pure `draw` at widths 40, 60, 80 and 120: no line wider than the width; the worker running with a 10 min silence shows «молчит 10 мин» and the command; reviewers rejected/accepted show ✗/✓ and their text; waiting shows «· ждёт»; journal strip shows at most 4 lines; status line. One TUI test through tests/tui_support.py at 160x45 and 120x40: an active attempt shows the legend and both reviewer words on Сейчас.

Non-goals (reviewers must not require): animation/spinners, percentages or progress bars, models or effort in boxes, the planner flow, the --plain UI, colour themes, any data change (F1 owns the data).

Testing: while editing run only the test you change; run the DoD command once at the end.

DoD: `python3.13 -m unittest tests.test_tui_flow tests.test_tui tests.test_tui_live tests.test_tui_milestones tests.test_tui_chat tests.test_toolchain tests.test_reference` with TMPDIR short (see preamble), all green.
