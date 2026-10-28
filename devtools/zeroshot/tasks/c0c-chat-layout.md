C0c — chat first: input focus and the right-pane tabs (dogfood blocker D4 and slice C1 of docs/CHAT_RELEASE_JTBD.md; jobs J1, J4).

Goal: the owner opens `zplan` and types into the chat at once, and the right pane has three tabs - Сейчас, План, Журнал - so the plan and the live run are one key apart. Today MainScreen sets AUTO_FOCUS to the plan pane (terminal_planner/tui/app.py:977), so typed letters fire panel keys ('?' opened help, ~/zs-pause/dogfood/findings.md item 3), and the chat takes 62 of 160 columns while the plan pane is empty (item 5).

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/zplan.tcss, terminal_planner/tui/controller.py only if a tab needs data the controller already has, docs/USER_FLOW.md (full-screen shell section), TUI tests. No engine, runs, live or delivery changes; tabs show data the TUI already holds.

Acceptance criteria:
- A1 (D4) On start the chat input has focus; typed letters go into the input; Tab still moves focus to the right pane and back; panel keys work on the first press once the pane is focused.
- A2 The right pane is a tabbed pane: Сейчас (the live run and planner lines now shown above the chat, app.py:1076-1086), План (the current plan lines, PlanPanel), Журнал (the stored run journal `live.journal` of the selected milestone, newest last). With no run, Сейчас says so in one line.
- A3 Tabs switch with alt+1 / alt+2 / alt+3 (and F2 / F3 / F4) from anywhere, including while the chat input has focus; these keys never insert text. The key bar names them.
- A4 Width: at 160 and 120 columns the chat gets about half of the width (between 45% and 55%); below the supported minimum the current fallback stays.
- A5 Everything the plan pane does today (keys p n c t g x o i w e, selection, refresh) still works on the План tab.
- A6 Each criterion has a test through the existing Textual test helpers (tests/tui_support.py), at 160x45 and 120x40.

Non-goals (reviewers must not require): a live log stream (slice C3), a cycle strip or round-of-max (C2), per-round verdicts (C4), mouse support beyond Textual defaults, theming, the --plain line UI.

DoD: `python3.13 -m unittest tests.test_tui tests.test_tui_chat tests.test_tui_live tests.test_tui_planning tests.test_tui_polish tests.test_toolchain tests.test_reference` with TMPDIR short (see preamble), all green.
