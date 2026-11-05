# v4c — the first start applies the proposed profile at once and says so on a card with "change"

docs/PLAN_UX.md V4, owner decision Q2 ("the level is applied as auto after a short explanation, with change on the
card"); design dir v4-astra-design.md, point 1 (the profile row) and task 5. Today a project whose profile is still
undecided ("never") opens the modal `BootstrapScreen` (tui/modals.py:90; pushed from tui/app.py where the snapshot
arrives, "the first-start choice, once per project"): accept / configure / later, nothing else dismisses it. Since
v4a, accepting keeps a snapshot and writes no file.

Change:
- An undecided profile is accepted as proposed (the existing `Controller.decide_profile(True, ...)`, a snapshot, no
  file), once per project, with no modal. An existing accepted profile, a later one and the owner's own file are kept
  as they are (manual included).
- One card in the chat says what was applied, from the profile's own values: the level and what it means ("Auto
  applied: zplan plans and runs the work; merges follow the merge rules; publishing stays yours."), the parallel runs,
  the check names (or "no checks found: nothing is verified before a merge"), and offers one button, change, which
  opens the existing profile editor; after a change the card shows the new values.
- `BootstrapScreen` and its catalog screen `tui_bootstrap` go (docs/REFERENCE.md regenerated); the editor stays.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/modals.py, terminal_planner/tui/card_host.py,
terminal_planner/tui/card_kinds.py, terminal_planner/tui/cards.py, terminal_planner/tui/strings.py,
terminal_planner/tui/zplan.tcss, terminal_planner/catalog.py, docs/REFERENCE.md, tests/test_tui_profile_choice.py,
tests/test_tui.py, tests/test_tui_hints.py, tests/test_tui_language.py, tests/test_tui_polish.py, tests/test_tui_split.py,
tests/test_process.py, tests/test_reference.py

Acceptance criteria:
- A1 No modal. Example: a fresh project -> no BootstrapScreen; the profile is accepted (snapshot, no file); one
  profile card in the chat with the level, runs and checks.
- A2 Change. Example: change on the card -> the editor opens; setting manual -> the card shows manual.
- A3 Kept. Example: an accepted manual profile or the owner's file -> nothing is applied, no card.
- A4 Once. Example: a reopen of the same project shows no new card.

Non-goals (reviewers must not require): undo, the other onboarding cards, the settings tool, wording beyond the
lines above.

Conflict rule: a test outside the write-set pinning the bootstrap modal: change nothing, end with
`conflict: <file:line>`.

Risk: medium (first start). DoD: `python3.13 devtools/fasttest.py tests.test_tui_profile_choice tests.test_tui
tests.test_tui_hints tests.test_tui_polish tests.test_reference tests.test_toolchain`: exit 0.
