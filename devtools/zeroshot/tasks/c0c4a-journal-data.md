C0c4a — the main-screen snapshot carries the run journal (data for the Журнал tab, slice C1 of docs/CHAT_RELEASE_JTBD.md; job J3/J4). No UI in this run.

Goal: the TUI can show the stored journal of a milestone attempt while it runs and after it ends. Today the journal reaches the TUI only in the end modal (`EndView.journal`, terminal_planner/delivery.py:250, :914); during a run the main screen gets only `Home.panel` (delivery.py:195, set at :497) copied into `Snapshot.panel` (terminal_planner/tui/controller.py:107, take_snapshot :240).

Data reach (checked by the orchestrator): `Delivery.journal(r)` (delivery.py:804-808) already formats an attempt's stored `live["journal"]` as "  HH:MM:SS  text" lines, oldest first; `active["record"]` is at hand where `Home` is built (delivery.py:492-497); the milestone under "Дальше" is `found` there.

Write-set: terminal_planner/delivery.py (Home and its construction in home()), terminal_planner/tui/controller.py (Snapshot and take_snapshot), their tests (the existing home tests in tests/test_live.py and tests/test_tui_milestones.py). Not tui/app.py, live.py, runs.py, engine.py.

Acceptance criteria:
- A1 `Home` gains `journal: Tuple[str, ...] = ()`: the active attempt's journal (`self.journal(active["record"])`); with no active attempt, the latest attempt of the milestone named under "Дальше" when it has one; else empty.
- A2 `Snapshot` gains the same field, copied in take_snapshot; nothing is rendered yet.
- A3 One test per criterion with a fixture record carrying journal entries (active, finished, none).

Non-goals (reviewers must not require): rendering, the planner's revision journal, live log following (C3), journal size or dedupe changes, refreshing a journal that nobody observes.

Testing: while editing run only the test you change; the DoD command once at the end (acceptance reviewer only).

DoD: `python3.13 -m unittest tests.test_live tests.test_tui_milestones tests.test_tui tests.test_tui_live tests.test_toolchain tests.test_reference` with TMPDIR short (see preamble), all green.
