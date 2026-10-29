C3 — every canvas hint names a step that works in that state (walk W3, W9, W12, W15)

Orchestrator walk and probe 2026-10-29: `plan_tab_line` (tui/app.py:204-214) turns `[w] watch M1` into
`/attempt watch M1`, `[d] diff` into `/diff diff` (`command_hints` keeps the label word; KEY_LABELS, app.py:173,
has only u, l, r); all merged -> `…; /view → revise — a new goal or a revision` (a new goal goes in the chat); at
`auto` the card says the architect approves (card_kinds.py:627) but `canvas_title` says "Plan ready · waiting for
your yes" (app.py:645, strings.py:427) and the Plan tab `Next: /approve`; the profile modal bar reads `[tab] later
[right] configure` for buttons accept, configure, later (catalog.py:700-701, modals.py:110-114).

Reuse: `plan_auto_approves`, `KEY_COMMANDS`, `PLAN_TAB_HINTS`, `catalog.bar`.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/strings.py, terminal_planner/catalog.py,
tests/test_tui_hints.py (new), tests/test_tui_look.py, tests/test_tui_cards.py, tests/test_tui_plan_gate.py,
tests/test_tui_live.py, tests/test_tui_milestones.py, tests/test_tui.py, docs/REFERENCE.md (old tests: only their
pins of the old hint texts and modal key order)

Acceptance criteria:
- H1 A letter key becomes `/command — rest`, dropping the label word when it is that command's own action. Example:
  `Next: [w] watch M1` -> `Next: /attempt — watch M1`; `[d] diff` -> `/diff`; `[g] start M2` stays `/run — start M2`.
- H2 All stages merged: Next says to write a new goal to the architect in the chat, no `/view`. Example: Plan tab ->
  "Next: all stages are merged — write a new goal to the architect in the chat".
- H3 When `plan_auto_approves(app.snapshot)`, the canvas title and Plan tab Next say the architect approves and the
  owner can tell it what to change, never "/approve". Example: auto, r1 proposed -> no "waiting for your yes".
- H4 The profile modal bar lists keys in button order, each key reaching its button. Example: accept, configure,
  later -> bar accept, configure, later, quit.
- H5 One invariant test runs every `Next:` text delivery.py builds through `plan_tab_line`: each command word is in
  `slash.COMMANDS`, none followed by its own label word; ru/zh mean the same. Example: no "/attempt watch".

Non-goals (reviewers must not require): letter keys returning, new commands, the line UI's texts.

Conflict rule: if a test outside the write-set pins an old hint text, change nothing in it and end with
`conflict: <file:line>`.

Risk: medium (visible text). DoD: once at the end, `python3.13 devtools/fasttest.py tests.test_tui_hints
tests.test_tui_look tests.test_tui_cards tests.test_tui_plan_gate tests.test_tui_live tests.test_tui_milestones
tests.test_tui tests.test_tui_auto_plan_card tests.test_tui_profile_choice tests.test_reference tests.test_docs
tests.test_toolchain`: exit 0; budget.py: OK. New H1-H5 tests fail on today's code.
