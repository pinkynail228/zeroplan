C0c4b — the right pane gets a third tab, Журнал: what happened during the observed run, newest at the bottom (slice C1 of docs/CHAT_RELEASE_JTBD.md; job J4/J3).

Goal: the owner sees the session log of the running (or last) attempt one key away, without leaving the main screen. C0c2 made the right pane a `TabbedContent` (id `right`) with «Сейчас» (`tab-live`) and «План» (`tab-plan`), `show_tab`, `TABS_HINT` in terminal_planner/tui/app.py; C0c4a stored the journal and exposes it as `Home.journal` (terminal_planner/delivery.py:196: `HH:MM:SS  text` lines of the observed attempt, oldest first, bounded by live.JOURNAL_LIMIT), filled at delivery.py:497-500. Nothing renders it yet.

Data reach: the main screen's snapshot (terminal_planner/tui/app.py, `render_state` and the C0c2 tab code) carries the same `Home` value as `snapshot.panel`; `journal` sits next to it. Entries are already scrubbed and formatted (delivery.py:806-808).

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/zplan.tcss, docs/USER_FLOW.md (full-screen shell section, one paragraph), TUI tests. No controller, delivery, runs or live changes.

Acceptance criteria:
- A1 The right pane has a third tab «Журнал» after «Сейчас» and «План». It shows `snapshot.journal`, one entry per line, oldest first, scrolled to the newest entry whenever new entries arrive while the tab is shown (unless the owner has scrolled up in it). With no entries it shows one line: «Журнал пуст: записи появятся, когда этап или планировщик начнёт работу.»
- A2 alt+3 and F4 switch to Журнал from anywhere (including while the chat input has focus) and never insert text; the key bar names them next to the C0c2 tab keys. The app never switches tabs on its own.
- A3 Сейчас and План, their keys, the chat focus at start-up and Tab focus to the pane and back keep working exactly as after C0c2.
- A4 Tests through tests/tui_support.py at 160x45 and 120x40: entries shown oldest first; a new entry appears on refresh; empty text; alt+3/F4 switch with the chat focused and insert nothing; the existing C0c2 tab tests still pass.

Non-goals (reviewers must not require): reading engine logs, filtering or searching the journal, colours per role, the --plain UI, any change to what is stored.

Testing: while editing run only the test you change; run the DoD command once at the end.

DoD: `python3.13 -m unittest tests.test_tui tests.test_tui_chat tests.test_tui_live tests.test_tui_planning tests.test_tui_polish tests.test_tui_milestones tests.test_toolchain tests.test_reference` with TMPDIR short (see preamble), all green.
