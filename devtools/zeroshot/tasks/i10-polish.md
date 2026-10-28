I10-polish — three visible defects of the 0.5.2 main screen (orchestrator look pass 2026-10-24 on the gallery
build/gallery/i9-look, regenerate it with devtools/ui-lab/gallery.py; see its docstring for the command).

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/chat.py, terminal_planner/tui/zplan.tcss,
terminal_planner/tui/strings.py, tests/test_tui_look.py.
Do not edit delivery.py or catalog.py: their «Дальше: [p] план …» lines are the `--plain` line UI, which stays.

Acceptance criteria:
- P1 The prompt hint is never clipped while the pane is wide enough for it. Today at 120x40 (idle, running) the
  box shows «Напиши архитектору… или / для коман»: the prompt box is narrower than the chat pane. Example: at
  120x40 and 80x24 the prompt row contains the whole «Напиши архитектору… или / для команд», and `#prompt-box`
  spans the chat pane's content width (same left and right inset as the chat entries).
- P2 One message shows once. Today with a failed setup the chat holds the entry «Инструменты zplan не установлены:
  выполните zplan setup. [код: setup.tools_invalid]» and, below it, the `#status` line repeats the same text
  clipped («…выполн…»). Example (that state, 120x40): the text appears in exactly one place in the chat pane.
  Keep `#status` for planner progress and run watch lines that are not already a chat entry.
- P3 The «План» tab of the TUI shows no letter-key hints of the line UI. Today, with no plan, it reads «Плана нет.»
  / «Дальше: [p] план — описать цель» / «[p] — план: цель, ход планирования, предложение, утверждение.». Example:
  the same state reads «Плана нет.» and «Дальше: /plan — описать цель» (the `/` command that does the same), no
  `[p]`; with a proposed plan «Дальше: /plan — утвердить или доработать». Map only the hints that have a `/`
  command; drop a hint line that has none.

Non-goals (reviewers must not require): the `--plain` UI, other states or wording, EN/ZH strings beyond the
same-key entries you touch, scheme layout, colours, the bottom bar.

Risk: low (TUI display). DoD: `python3.13 devtools/fasttest.py tests.test_tui_look tests.test_tui tests.test_tui_chat
tests.test_tui_milestones tests.test_tui_live` exit 0; quote the `fasttest:` lines.
