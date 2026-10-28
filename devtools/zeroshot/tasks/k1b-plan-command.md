K1b — the goal is `/plan <goal>` in the chat; the goal form goes (plan section K1)

Owner: no letter keys, every action a `/` command. After K1a a goal reaches the planner only from a draft card
(`action_plan`, tui/card_host.py:201) or the goal form (GoalScreen, screens.py:24, its Ctrl+G :27; opened by `/view`
with no plan, `action_open_plan` app.py:2261/:2279, by `c` `action_open_goal_draft` :2314 and `open_draft_form`
:2330); `/plan` acts only in `draft` (slash.py:64) and ignores its text; `n` (`action_new_plan` :2296) renews a stale
plan (`renew_plan` :2436; the send is `run_plan` :2570).

Reuse: `start_goal` (app.py:2449) with its readiness verdicts, `note_card_refusal`; RC6's `card=True` path of
`Controller.start_planning` (a refusal writes nothing); `renew_plan`, `run_plan`.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/card_host.py, terminal_planner/tui/slash.py, terminal_planner/tui/screens.py, terminal_planner/tui/strings.py, terminal_planner/tui/zplan.tcss, terminal_planner/catalog.py, docs/REFERENCE.md, tests/test_tui_chat.py, tests/test_tui_milestones.py, tests/test_tui_planning.py, tests/test_tui_polish.py, tests/test_tui_live.py, tests/test_tui_plan_gate.py, tests/test_tui_split.py, tests/test_tui_merge_card.py, tests/test_tui_question_card.py, tests/test_tui_draft_card.py, tests/test_tui_slash.py, tests/test_reference.py, tests/test_tui_commands.py, tests/test_tui_reopen_fixes.py, tests/test_tui_palette.py.

Acceptance criteria:
- C1 Typed goal: `/plan <text>` with no draft card starts planning on that text; a readiness refusal writes nothing
  and says the checks on the status line, as for the card. Example: idle, clean tree, `/plan add slugify` -> the
  planner runs r1; dirty tree -> «не запущено» + the checks, no revision.
- C2 No text: `/plan` with no card and no text sends the unsent revision (renewed first when stale); with none,
  the note «напишите /plan <цель>». Example: stale unsent r2 -> `/plan` -> r3 renewed and sent.
- C3 Card first: the card's button, and typed `/plan` without text while a draft card is open, act on the card
  (RC6 behavior); typed `/plan <text>` uses the text. Example: card open, `/plan` -> the card's goal is sent.
- C4 No form: GoalScreen, GoalActions, the form's Ctrl+G, the `n` and `c` keys (app.py:564) and their openers are gone; `/view` with no
  plan says «плана нет — /plan <цель>». Example: idle with no plan, `/view` -> that note, no screen opens.

Tests: form tests become `/plan <text>` tests or go; the palette lists `/plan` where it acts.

Non-goals (reviewers must not require): letters in screens and modals (K1c); readiness texts in
setup.py (K1d); the plain CLI; command history or completion.

Conflict rule: a test outside the write-set that opens the goal form or pins `/plan`'s states ->
`conflict:` path:line.

Risk: medium (planning entry). DoD: `python3.13 devtools/fasttest.py` with the changed test modules plus
tests.test_reference tests.test_toolchain, exit 0; quote `fasttest:` lines.
