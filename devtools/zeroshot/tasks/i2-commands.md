I2 — `/` commands in the chat input and the new bottom bar on the main screen (0.5.2, docs/RELEASE_0.5.2_PLAN.md,
run i2).

Why: the approved screen (docs/ui-redesign/WORK_SCREEN.md, lab `devtools/ui-lab/work.py`) has one way to act besides
the cards: type `/` in the chat input, a palette of the commands allowed now opens above it, enter runs one. The bottom
row shows project, branch, what is running and its clock, and the four keys (←→, /, esc, ctrl+q). Both widgets exist
and are tested; this run only wires them:
- `terminal_planner/tui/palette.py`: `Palette(Static)` with `show_for(value, state)` (call on every input change;
  hides itself unless the value starts with "/"), and pure `submit(line, state)` -> `Submitted(command_name, argument)`
  | `Refused(note)` | None (None = not a command, the line goes to the chat as today).
- `terminal_planner/tui/slash.py`: `STATES` (idle, draft, planning, plan_ready, running, merge, question, error),
  `COMMANDS` and which states allow each.
- `terminal_planner/tui/activity.py`: `Bar(Static)` with `update_bar(project, branch, job, stage, elapsed, keys)`;
  `job` is planning, running, a key of activity.JOB_IDS, or None, `elapsed` None draws "—", `keys` = (key, strings id) pairs, ids
  `bar.key_tabs`, `bar.key_commands`, `bar.key_close`, `bar.key_quit` (strings.py).

Today (terminal_planner/tui/app.py; run s0 split helpers and modals into text.py, chat_view.py, modals.py, screens.py —
MainScreen and ZplanApp are still in app.py): `MainScreen.compose` yields `Input#input` then `Static#keys`;
`on_input_submitted` sends every line to `self.app.send_chat`; `show_keys`/`key_text`/`panel_keys` build the main key
bar from `catalog.bar` (screens `tui_input`, `tui_panel`) plus `TABS_HINT`. Nothing derives a slash state from the
snapshot yet.

Change:
- State: a running stage takes precedence over unrelated status/error lines. One method `MainScreen.slash_state()` (or a pure function beside it) maps what the screen already knows to one
  of `slash.STATES`: an error/blocked line shown -> error; an owner question pending -> question; a finished stage
  waiting for merge -> merge; a stage running -> running; the planner running -> planning; a plan proposed and not
  approved -> plan_ready; a goal draft open -> draft; else idle. Use only facts the screen/app already holds (snapshot,
  flow, drafts); no new controller or engine calls. Where a fact does not exist, pick the nearest state and say so in
  a one-line comment.
- Palette: mount a `Palette` (id `palette`) directly above `#input`; on `Input.Changed` of `#input` call
  `show_for(value, slash_state())`. On submit, `palette.submit(line, state)` first: None -> today's chat path,
  unchanged; `Refused` -> the note shows in the palette (or the status line), the input keeps the text; `Submitted` ->
  the input clears, the palette hides, and one dispatcher dict `COMMAND_ACTIONS` (command name -> callable) runs it.
  Escape precedence (both runs i2 and i5): hide the palette and clear its input; otherwise close the active file/diff canvas tab; otherwise run the existing cancel-turn action (`MainScreen.action_cancel_turn`).
- Wired now (existing actions only): `/help` -> action_help, `/quit` -> action_quit, `/stop` -> stop the running snapshot row even when another row is selected (reuse action_stop_milestone's confirmation for that row),
  `/setup` -> action_settings, `/status` -> switch the canvas to the Сейчас tab, `/approve` -> action_open_plan (the plan
  screen holds approve), `/merge` and `/diff` -> action_open_milestone (the run screen holds merge and diff).
  Not wired in this run (`/plan`, `/decline` -> run i3a/i3d cards; `/open` and the canvas `/diff` -> run i3a after i2 and i5 merge, i2 keeps `/diff` on action_open_milestone meanwhile; `/language` -> run i6): absent from
  `COMMAND_ACTIONS`, a `Submitted` for them shows `note.not_now` like a refusal. Later runs add one dict entry each.
- Bar: on the main screen `Static#keys` becomes an `activity.Bar` (id `keys` kept so layout CSS still applies), fed on
  every render with: project and branch from what `#header` shows; `job` from the slash state (planning -> planning,
  running -> running, plan_ready -> approve, merge/question/error -> same, else None); `stage` = the running stage name
  if known; `elapsed = snapshot.flow.get("elapsed")` when a flow exists, else None; keys = ←→ bar.key_tabs,
  / bar.key_commands, esc bar.key_close, ctrl+q bar.key_quit. Modal and other-screen bars (`modal_bar`, Modal.key_bar,
  RunScreen) stay exactly as they are; `keys_bar`/`catalog.bar` stay for them.
- Remove the main-screen-only bar code that nothing else uses after the swap (`panel_keys`, `key_text`, `TABS_HINT`
  segment, and helpers only they call). Keep `PlanPanel` letter bindings and the `tui_panel` catalog rows: their actions
  have no replacement until the cards land; run i8 removes them. Do not edit catalog.py.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/zplan.tcss, terminal_planner/tui/palette.py (only if a
wiring bug in it blocks you; say why), docs/USER_FLOW.md (main screen keys and commands), tests/test_tui_live.py,
tests/test_tui_polish.py, tests/test_tui_milestones.py, tests/test_tui.py, tests/test_tui_commands.py (new),
tests/test_tui_chat.py and tests/test_tui_activity_pane.py (only to retire old main-bar checks, e.g. test_tui_chat.py
~2428, 2448, 3331, 3362; test_tui_activity_pane.py ~197). Also old-bar checks at test_tui.py ~306-345,
test_tui_live.py ~404, test_tui_polish.py ~524.
Do not edit strings.py, slash.py, activity.py, catalog.py, cards.py, controller, engine.

Acceptance criteria:
- A1 Typing `/` in the chat input at 120x40 and 80x24 shows the palette above the input with only the commands allowed
  in the current state; typing `/st` narrows it; deleting the `/` hides it. A plain line still goes to the chat
  unchanged (existing chat tests stay green).
- A2 `/help` + enter opens the help screen; `/stop` while a stage runs reaches the existing stop confirmation;
  `/stop` while idle is refused with the not-now note and nothing else happens; `/plan` (not wired) shows the not-now
  note; esc with the palette open hides it and leaves the screen as it was.
- A3 The bottom row of the main screen is the `Bar`: project, branch, job phrase with clock for a running stage
  (fixture flow with elapsed 187 -> "0:03:07"), "—" when elapsed is unknown; all four key hints at 120 columns (at 80
  the Bar's existing clipping is allowed); modal bars unchanged.
- A4 `slash_state()` returns idle, plan_ready and running for the three existing fixture situations that show them, and
  `/stop` targets the running row while another row is selected (unit-level tests, not a whole-app walk).
- A5 Tests per preamble: at most two new whole-app tests (A1+A2 in one, A3 in the other), A4 at unit level, in
  tests/test_tui_commands.py. Delete, not rewrite, the tests listed for i2 in devtools/zeroshot/test-retire-0.5.2.md
  that pinned the old main key bar (KeyBarTests.u5_bar_shrinks_in_the_documented_order, PaneTabTests
  a4_regression_the_tab_hint_names_the_arrows, PaneTabTests a2_regression_the_tab_keys_stay_named_with_a_running_attempt,
  and any other assertion on the old main bar text); shrink KeyBarTests la5 and PilotBarTests a1 to the modal bars.
  Keep letter-driven workflows unchanged; remove obsolete main-bar assertions from mixed tests without deleting their
  behaviour checks.

Non-goals (reviewers must not require): cards, removing letter hotkeys or catalog rows, `/open`, `/language`,
translations of the main screen, narrow layout, new controller data, a better state model than A4 needs.

DoD: `python3.13 devtools/fasttest.py $(ls tests/test_tui*.py | sed 's#tests/#tests.#;s#\.py$##') tests.test_live
tests.test_layout tests.test_fixture_scope tests.test_toolchain tests.test_reference` with exit 0.
Parallel note: run i5-canvas-files edits the canvas tabs of MainScreen at the same time; do not move or reformat code
outside the input, the bar and the new dispatcher.
Shared areas: i2 owns the input, the bar, the dispatcher and PaneTabTests; i5 owns the file/diff canvas tabs and ArrowTabTests. CSS changes use separate selectors; docs/USER_FLOW.md changes go in separate sections.
