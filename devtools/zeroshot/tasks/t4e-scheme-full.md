T4e — `/scheme`: the block scheme on the whole screen

Owner 2026-10-28: the block scheme (scheme.py box mode, `_full`) is the key view, but it needs ~76 columns and the
right column is 40% of the window, so users only see the one-line fallback. Give it the whole screen on demand.

Reuse: `scheme.render` as it is (its three fitting modes decide what is drawn); `render_live` in tui/app.py; the
Esc chain in `action_cancel_turn`; Textual's own `Screen.maximize` if it fits; the slash command table in
tui/slash.py and card_kinds.py; strings.py for every visible word; `python -m terminal_planner.catalog --write
docs/REFERENCE.md` for the reference tables.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/slash.py, terminal_planner/tui/card_kinds.py,
terminal_planner/tui/strings.py, terminal_planner/tui/zplan.tcss, docs/REFERENCE.md, tests/test_tui_scheme_tab.py,
tests/test_tui_slash.py.

Acceptance criteria:
- F1 `/scheme` (any state) shows the Scheme tab on the whole window: the chat, the activity pane and the input are
  not drawn and the canvas content is at least the window width minus 6 cells.
  Example: 120x40 window, running milestone with a flow (worker done, both reviews running) -> the live text holds
  box frames for `acceptance review` and `code review` side by side.
- F2 On the whole screen the scheme is not cut to the pane height: `render` gets a height large enough for box mode
  (the pane scrolls), and after each repaint the running box's row is inside the visible region.
  Example: the F1 flow at 120x30 -> boxes, not the one-line list; the `acceptance review` box row is visible.
- F3 Esc (or `/scheme` again) restores the normal layout, the tab and the focus it had. Esc order: the `/` palette
  first, then the full screen, then today's chain unchanged.
  Example: `/scheme`, Esc -> chat and input visible, input focused; a second Esc cancels an architect turn as today.
- F4 With no flow, the full screen shows what the Scheme tab shows today. Example: idle project, `/scheme` -> the
  canvas's "nothing runs" text, no error.
- F5 The normal layout is unchanged (40% column, list fallback). `/scheme` is in the palette with en, ru and zh
  text, and docs/REFERENCE.md is regenerated. Example: typing `/sch` offers `/scheme`; test_reference passes.

Non-goals (reviewers must not require): scheme.py or its drawing; smaller boxes; the normal column width; README,
USER_FLOW or other docs; a key binding besides the command.

Conflict rule: if a test outside the write-set pins the command list or the Esc chain, change nothing and end with
`conflict: <file:line>`.

Risk: medium (UI, Esc chain). DoD: run once, at the end: `python3.13 devtools/fasttest.py tests.test_tui_scheme_tab
tests.test_tui_slash tests.test_tui_scheme tests.test_tui_live tests.test_reference tests.test_tui_palette`: exit
0; `python3 devtools/budget.py`: OK; each new test fails with the F1-F3 code reverted. Commit the diff on the branch.
