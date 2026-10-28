C3b — the live panel says how long the run has been silent and the last command it ran (display half of slice C3, docs/CHAT_RELEASE_JTBD.md, job J3).

Goal: the owner can tell a healthy long step (a test suite) from a dead run without reading logs. Today the panel says "последнее событие N мин назад" from `live["last_event"]`, which only moves on a new watch record (a stage change), so a worker running tests for 20 minutes looks dead. C3a stores the last Codex command an active execution started (`live["command"]` = None or {"at": stamp, "text": str}).

Data reach: `live.panel_lines(live, started, now, roles, nodes, rounds)` (terminal_planner/live.py, after C3a) builds the line; `live["last_event"]`, `live["command"]` and `seconds_between`, `duration` are all in live.py. Callers: delivery.py:797 (milestone panel) and planning.py:396 (planner panel; its live records never get `command`, so it keeps today's output). Measured silence (docs/CHAT_RELEASE_JTBD.md "Measured silence"): p99 gap 45 s, long silences are normal, never say "завис".

Write-set: terminal_planner/live.py (`panel_lines` only), tests/test_live.py, tests/test_tui_live.py only if one of its assertions quotes the changed line.

Acceptance criteria:
- A1 Activity = the later of `live["last_event"]` and `live["command"]["at"]` (when present). The time part reads "последняя активность N назад" from it while N < 2 min, and "молчит N мин" when N ≥ 2 min; the other parts of that line (идёт, проверено / наблюдение прервано) are unchanged.
- A2 When `live["command"]` is present, one more line follows: "  последнее: <text>" (text as stored; already scrubbed and ≤ 160 chars).
- A3 A record without `command` (older records, the planner) shows exactly today's line ("последнее событие N назад"), byte for byte.
- A4 The panel's own wording (the strings live.py composes) never says "завис" / "stuck"; the echoed command text is shown as stored (amended 2026-10-22 after run 01a16096 looped 7 rounds on the literal reading).
- A5 Tests: a 10-minute-old command with an older event shows "молчит 10 мин" and "последнее: <text>"; a 30 s old command shows "последняя активность 30 с назад"; no command → today's text; existing tests unchanged except where they quote the line for a record with a command.

Non-goals (reviewers must not require): reading logs, any store change, colours, a stall verdict, TUI layout changes, the planner panel.

Testing: while editing run only the test you change; run the DoD command once at the end.

DoD: `python3.13 -m unittest tests.test_live tests.test_tui_live tests.test_runs tests.test_toolchain tests.test_reference` with TMPDIR short (see preamble), all green.
