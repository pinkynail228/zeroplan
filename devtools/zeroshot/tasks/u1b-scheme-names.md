U1b — the scheme names its loops and optional branches in the owner's words (0.5.2, docs/RELEASE_0.5.2_PLAN.md).

Bug: `terminal_planner/tui/scheme.py` shows engine names for the stage graph's loops and its optional branch: today a
running stage reads "↻ task loop · 3 из 20", "↻ review loop · 1 из 4", "? если нужно: final repair",
"↻ repair loop · до 3 раз", and every step inside the optional branch ends with "· если нужно: final repair".
The approved look (lab `devtools/ui-lab/flowdraw.py` NAMES and `_leaf`, run `python3.13` on
`flowdraw.render(milestone graph, obs, 110, 34, 0)` to see it) reads "↻ задачи по очереди · 3 из 20",
"↻ раунды ревью · 1 из 4", "? если нужно: доработка после итоговой проверки", "↻ раунды доработки · до 3 раз", and a
waiting step inside the branch ends with "· если нужно" only.

New ids (GLOSSARY.md already lists them; RU / EN / ZH):
`flow.task_loop` задачи по очереди / tasks one by one / 逐个任务; `flow.review_loop` раунды ревью / review rounds /
评审轮次; `flow.repair_loop` раунды доработки / fix-up rounds / 修复轮次; `flow.final_repair` доработка после итоговой
проверки / fix-up after the final check / 最终检查后的修复; `state.if_needed` если нужно / if needed / 如有需要.

Write-set: terminal_planner/tui/scheme.py, terminal_planner/tui/strings.py, tests/test_tui_scheme.py,
tests/test_tui_strings.py.

Acceptance criteria:
- A1 The node names `task_loop`, `review_loop`, `repair_loop`, `final_repair` map to the new ids in scheme.py's name
  table; with the built-in table the milestone graph (rounds 3) at 110x34 with the observation above renders the
  approved lines quoted above (test compares those lines).
- A2 A waiting step inside an optional branch shows `state.if_needed` as its word, without the branch name.
- A3 strings.py carries the five ids in all three languages (its whole-table test still passes).
- A4 With `words=strings.text` and language en, the same render shows "tasks one by one" and "if needed".

Non-goals: other wording changes, layout changes, wiring into app.py.

DoD: `python3.13 -m unittest tests.test_tui_scheme tests.test_tui_strings tests.test_toolchain tests.test_reference`
with TMPDIR short, green.
