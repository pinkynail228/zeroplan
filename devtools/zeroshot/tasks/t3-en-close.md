T3 — close the English 0.8.0: guard, tests, docs, version

Design: 0.8-english-ui.md in the pause dir (design folder). T1 and T2 translated the product; main is red only on
tests and docs that still quote the old Russian text. Iterate on the failing modules only; run the DoD once at the end.

Write-set: tests/*, docs/USER_FLOW.md, docs/INSTALLATION.md, docs/UPGRADE.md, docs/TERMINAL_UX_BRIEF.md,
docs/REFERENCE.md, README.md, devtools/ux_walkthrough.py, terminal_planner/tui/zplan.tcss,
terminal_planner/__init__.py, install.py, pyproject.toml

Acceptance criteria:
- C1 New tests/test_english.py: an AST walk over every str constant (docstrings included) in terminal_planner/**/*.py
  and install.py fails, naming file:line, on Cyrillic outside the ru/zh values of strings.CATALOG, strings.DISPLAY_NAMES,
  LEGACY_* names and setup.YES_ANSWERS; install.sh is checked by line. Example: a literal "привет" injected in cli.py fails it.
- C2 Tests failing on main because they assert the old Russian text assert the shipped English text; Russian input
  fixtures (0.7.x rows, «да» answers) stay. Example: test_run_cause expects "  Reason: «review_failed»".
- C3 Live docs quote the English UI: USER_FLOW, INSTALLATION, TERMINAL_UX_BRIEF, README (quotes only); REFERENCE
  only via `python3.13 -m terminal_planner.catalog --write docs/REFERENCE.md`. UPGRADE gets a 0.8.0 note: English
  only, a stored "ru" falls back to English, old history stays Russian. Example: USER_FLOW shows `Reason:`.
- C4 devtools/ux_walkthrough.py expects the shipped English screen texts (the orchestrator runs it with pyte after
  merge); its and zplan.tcss's comments are English. Example: its `Дальше:` expectation becomes the English phrase.
- C5 Version 0.8.0 in __init__.py, install.py, pyproject.toml. Example: `zplan --version` prints 0.8.0.

Non-goals (reviewers must not require): product behaviour or text changes; docs outside the write-set (closed
records); the six test_agent_activation tests (run prune-tests); a full suite.

Conflict rule: a test that fails for a reason other than old text: change nothing for it and end with
`conflict: <test> <evidence>`.

Risk: medium (tests and docs). DoD: run once, at the end: `python3.13 devtools/fasttest.py tests.test_english
tests.test_docs tests.test_reference $(git diff --name-only --diff-filter=d $(git merge-base main HEAD) --
'tests/test_*.py' | sed 's|/|.|;s|\.py$||')`: exit 0; `python3 devtools/budget.py`: OK.
