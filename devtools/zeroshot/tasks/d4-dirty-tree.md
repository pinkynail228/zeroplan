D4a — uncommitted changes never block; one truth: HEAD

Owner 2026-10-27: a dirty project refused «составить план» and «новая попытка» repeated it. Design
(~/zs-pause/design/0.7.1-dirty-login.md, critic-reviewed): the tree is the user's; every zplan reader sees HEAD.
Planner/task/merge-critic/runs already clone HEAD; the clean checks protect nothing. Merge (D4b) and the commit
action (D4c) are not in this task.

Write-set: terminal_planner/setup.py, terminal_planner/engine.py, terminal_planner/runs.py,
terminal_planner/authority.py, terminal_planner/project_read.py, terminal_planner/foreman.py,
terminal_planner/architect_tools.py, terminal_planner/architect.py, terminal_planner/catalog.py,
terminal_planner/tui/*.py, README.md, docs/REFERENCE.md, docs/USER_FLOW.md, tests/*

Acceptance criteria:
- K1 No refusal for uncommitted changes at plan, task check, merge critic (engine.py:1333/1560/1734) or milestone
  start (runs.py:797). Readiness "clean" (setup.py:431-444) is informational, ok, never a blocker: «Не в коммите:
  N файлов — план видит последний коммит»; an uncommitted zplan.process.json is named there (runs see HEAD).
  Example: untracked file -> «да, составить план» plans; modified profile -> note names zplan.process.json.
- K2 baseline() (authority.py:222) for new records = "v2:" + digest of HEAD and branch only; check_index_flags is
  removed. Records without the prefix are checked with the old formula. Example: plan ready, unrelated edit -> plan
  still approvable; a stored 0.7.0 revision on a clean tree is not stale.
- K3 project_read list/read/search (used by foreman.py and architect_tools.py) read the HEAD tree (ls-tree, show,
  grep HEAD), not the disk. Example: line only in an uncommitted edit -> foreman flags the citation as missing.
- K4 The architect's state section (architect.py:250) lists the uncommitted paths (first 5 + «и ещё N»); the
  foreman warns when brief write_set ∩ uncommitted paths is non-empty. Example: write_set src/a.py, a.py modified
  -> warning names src/a.py.
- K5 No text tells the user to commit before planning (README, REFERENCE, USER_FLOW, catalog). Example:
  `grep -rn "нужен чистый\|Нужен чистый" terminal_planner` -> only runs.py:1451 (D4b).

Non-goals (reviewers must not require): merge paths runs.py:1451-1550 (D4b); a commit action (D4c); stash; en/zh.

Tests: new tests/test_dirty_head.py, each test failing on today's code; old-behaviour tests updated.

Risk: high (plan validity). DoD: `python3.13 devtools/fasttest.py tests.test_dirty_head tests.test_setup
tests.test_project_state tests.test_plan_gate tests.test_foreman tests.test_project_read tests.test_architect
tests.test_architect_tools tests.test_terminal_planner tests.test_runs tests.test_reference`: exit 0.
