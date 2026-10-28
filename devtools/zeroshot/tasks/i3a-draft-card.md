I3a — decision cards on the main screen: the shared card contract, and the first card «Составить план из этого?»
for the architect's goal draft (0.5.2, docs/RELEASE_0.5.2_PLAN.md, run i3a).

Why: in 0.5.1 turning the architect's goal draft into a plan takes the owner through a hidden key (`c`, only with the
plan pane focused) and a form. The approved screen (docs/ui-redesign/WORK_SCREEN.md, lab `devtools/ui-lab/work.py`,
state "draft") ends the chat with a card: «Составить план из этого черновика? Полный текст — во вкладке «Черновик
цели»» with buttons yes/no; the full draft opens as a canvas tab. The widget exists and is tested:
`terminal_planner/tui/cards.py` — `CardSpec(key, title, text, buttons, hint, at, done, alarm)`, builders
`draft_card(key, at)` (buttons `/plan`, `/decline`), `closed(spec, done_text)`, `Card(spec)` posting
`Card.Chosen(command, card)` (read `card.spec.key`). Strings: `card.draft_sent`, `canvas.draft_tab`,
`canvas.draft_intro` in strings.py.

Today (main after runs i2 and i5, terminal_planner/tui/app.py): a `/` palette over `#input`; the state is the pure
`slash_state(snapshot, blocked, watching, draft)` called through `screen_slash_state(app)` (its `draft` flag is how
the `draft` state is reached); the module-level dispatcher dict `COMMAND_ACTIONS` maps a command name to
`callable(screen)` and `MainScreen.on_input_submitted` calls `action(self)` for a `palette.Submitted`; `/plan`,
`/decline`, `/open` are absent and answer `note.not_now`; `/diff` is mapped to `action_open_milestone` for now. `MainScreen.open_file_tab(name)`, `open_diff_tab()` and `add_view_tab(title, renderable, ...)` (run i5)
show canvas tabs. The goal draft: `chat.newest_goal_draft(entries)` (chat.py) returns the newest actionable
`Draft`; `ZplanApp.goal_draft_to_open()` and `action_open_goal_draft` (key `c`) -> `open_draft_form` -> GoalScreen;
submitting it calls `ZplanApp.start_goal(goal)`, which calls `controller.start_planning(goal, ..., draft=
self.goal_identity)` and clears `goal_draft`/`goal_identity` on success; `chat.stale_reason(identity, current)` says
when a draft is stale.

Change:
- Card contract (later runs i3b, i3c, i3d use only this, in parallel): a container `Vertical#cards` in `#chat-pane`
  between `#chat` and the input (height auto, max 40% of the pane, empty = zero height), and on MainScreen
  `show_card(spec)` (mount, or replace the card with the same key), `close_card(key, done_text)` (replace with
  `cards.closed(spec, done_text)`; a closed card stays until a newer card or a new chat turn), `drop_card(key)`.
  `on_card_chosen(event)` runs `event.command` through the same dispatcher as a typed `/` line, passing the card key;
  change the entry convention to `callable(screen, argument, key)` for every entry (update i2's entries; the typed
  path passes `verdict.argument` and key None = the newest open card of that kind). One function, e.g.
  `MainScreen.run_command(name, argument, key)`, is the only caller of `COMMAND_ACTIONS` for both paths.
  Run i3-chat-inline later moves the container into the chat history; nothing else may depend on its place.
- Draft card: when `newest_goal_draft` returns a draft whose card key was never shown, `show_card(draft_card(key,
  at=<reply time HH:MM>))`. Key = a stable string from the draft's chat entry and text (not `draft.identity` alone:
  two drafts under one plan share it). While that card is open, `screen_slash_state` passes `draft=True`.
- `/plan` (button or typed): the draft of that key; if `stale_reason` says it is stale, refuse on the status line and
  keep the card; else set `goal_identity` from the draft and call `start_goal(draft.text)` (no GoalScreen); on success
  `close_card(key, strings.text("card.draft_sent", time=HH:MM))`; on failure the existing error path, card stays.
- `/decline`: drop the draft card; that key is not shown again.
- The «Черновик цели» canvas tab: with a draft card open, `add_view_tab(strings.text("canvas.draft_tab"),
  <canvas.draft_intro + the full draft text>)` opens beside План (once per key; esc closes it like a file tab).
- Wire `/open PATH` -> `open_file_tab(PATH)` and `/diff` -> `open_diff_tab()` in `COMMAND_ACTIONS` (replacing the
  `/diff` -> `action_open_milestone` entry).
- Keep key `c`, GoalScreen and `action_open_goal_draft` working (run i8 removes them).

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/zplan.tcss, docs/USER_FLOW.md (draft card section),
tests/test_tui_draft_card.py (new), tests/test_tui_commands.py (entry convention only), tests/test_tui_chat.py (only GoalDraftTests u3_* per
devtools/zeroshot/test-retire-0.5.2.md row i3a, and assertions that the screen has no card). Do not edit cards.py,
strings.py, slash.py, palette.py, chat.py, controller, engine.

Acceptance criteria:
- A1 With a fixture chat whose last architect reply carries an actionable goal draft, at 120x40 and 80x24 the card
  shows under the chat with the two buttons, and the «Черновик цели» tab holds the full draft text.
- A2 Clicking «да» (or typing `/plan`) calls `start_planning` once with the draft text and its identity; the card
  becomes «✓ отправлен планировщику HH:MM» without buttons; a second `/plan` is refused (state no longer draft).
- A3 A stale draft: `/plan` refuses on the status line, `start_planning` is not called, the card stays.
- A4 `/decline` removes the card and the same draft does not bring it back on the next refresh.
- A5 `/open README.md` opens the file tab; `/diff` reaches `open_diff_tab`.
- A6 Tests per preamble: at most two whole-app tests (A1+A2, A3+A4); A5 and the card contract
  (`show_card`/`close_card`/`drop_card`, same key replaces) at unit level in tests/test_tui_draft_card.py.

Non-goals (reviewers must not require): cards inside the chat history (run i3-chat-inline), plan/merge/question/error
cards, removing key `c` or GoalScreen, translations of the legacy form, a draft editor.

DoD: `python3.13 devtools/fasttest.py $(ls tests/test_tui*.py | sed 's#tests/#tests.#;s#\.py$##') tests.test_live
tests.test_layout tests.test_toolchain tests.test_reference` with exit 0; quote its `fasttest:` lines.
