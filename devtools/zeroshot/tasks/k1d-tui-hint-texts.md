K1d — no TUI text names a letter key

The TUI has no letter keys (K1a-K1c3), but line-UI service texts still reach it with `[g]`, `[l]`, `[r]`... The TUI rewrites at its display boundary: tui/app.py `command_hints`
(:160, KEY_COMMANDS :156) covers p g o w e i only; `plan_tab_line` (:166), PLAIN_KEYS (:303), FIX_KEY strip a few.

Inputs (texts that reach the TUI raw): planning.py:83/515, 529, 560-581, 612, 656; delivery.py:111, 1014, 1058,
1087, 1418; tui/app.py:120, 2116-2118, 3282; setup.py:441, 616, 621, 648-649; runs.py:725, 1355;
authority.py:376, 799; engine.py:1097; live.py:345. Surfaces: PlanScreen body (screens.py:113-116), failure cards
(card_kinds.py:791, 801), Settings rows, detail and log (screens.py:236, 269-271), run and chat notes
(app.py:2628, 2841, 3166), readiness notes (FIX_KEY users app.py:2117-2716), RunScreen body (modals.py `render_state` :406).

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/screens.py, terminal_planner/tui/card_kinds.py,
terminal_planner/tui/modals.py, tests/test_tui_look.py, tests/test_tui_planning.py, tests/test_tui.py,
tests/test_tui_ready_card.py, tests/test_tui_live.py, tests/test_tui_milestones.py, tests/test_tui_polish.py,
tests/test_tui_plan_gate.py, tests/test_tui_commands.py.

Acceptance criteria:
- C1 One table maps every letter to its TUI step: g /run, o w n /attempt, p /view, e /log, i /details, d /diff,
  t /answer, u «/setup → установить», l «/setup → войти», r «/view → доработать»; every surface above passes its
  text through it. Example: a failed plan shows «Дальше: /setup → войти, затем /run — проверить готовность».
- C2 On Settings (rows, detail, log) `[l]` and `[u]` name the buttons instead. Example: no login -> the row ends
  «— кнопка «войти»»; the empty log reads «…: кнопка «установить», кнопка «войти».»
- C3 The same service text keeps its letters in the plain CLI. Example: `zplan` line UI after a failed plan
  still prints «[l] обновить вход».
- C4 Invariant test: each input above, rendered through its surface, shows no `[a-z]` bracket. Example: a new
  `[k]` hint on the PlanScreen -> the test fails.
- C5 Load flakes (3 on 2026-10-25, each a 5 s wait beside a run): `until`, `chat_ready` (test_tui.py) and
  `until_pane` (test_tui_live.py) wait 20 s by default; a passing test is not slower. Example: `until` on a condition true at 6 s -> passes.

Tests: replace asserts of the old letter texts (test_tui_planning :362-383, test_tui :652, :796,
test_tui_ready_card :165, test_tui_look :274-290, test_tui_plan_gate :73); keep behavior checks.

Non-goals (reviewers must not require): editing service texts or the line UI; catalog bars, buttons; docs;
the F1 help footer.

A test outside the write-set asserting a letter on a TUI surface -> `conflict:`.

Risk: medium. DoD: `python3.13 devtools/fasttest.py` changed test modules, tests.test_toolchain: exit 0.
