P3a — the architect does not name zplan's internals to the owner

Newcomer re-check 2026-10-26 (main 3de1a1f, ~/zs-pause/dogfood/findings-2026-10-26-mvp-recheck.md, item 2): after a
start the architect's reply read «Controller принял запрос запуска». "Controller" is internal: the method's first line
(terminal_planner/resources/architect_method.md:3) and every action tool description (terminal_planner/architect_tools.py
:66-90, "Ask the live Controller ...") use it, and nothing tells the architect which words the owner sees.

Write-set: terminal_planner/resources/architect_method.md, tests/test_architect.py

Acceptance criteria:
- C1 The method's Role section gains one rule: in replies to the owner, name what the owner sees (zplan, the plan, a
  milestone, a run, a check, a merge) and never internal names: Controller, socket, manifest, preset, tool names
  (zplan_*), status JSON fields. Example: the method text contains a Role line naming "Controller" and "zplan_" as words
  the owner never reads; a start reply reads like «Запустил M1» rather than «Controller принял запрос запуска».
- C2 A test pins the rule in the shipped method (the text as the architect receives it), and the method stays within
  its current size class (the file is ~4.1 KB; the new rule is one line, ≤ 300 bytes). Example: removing the line makes
  the new test fail.

Non-goals (reviewers must not require): tool descriptions or names (architect_tools.py), catalog texts, English UI,
other method sections, a model run.

Risk: low (prose). DoD: `python3.13 devtools/fasttest.py` tests.test_architect, tests.test_architect_tools,
tests.test_toolchain: exit 0.
