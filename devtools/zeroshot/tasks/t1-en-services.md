T1 — English interface: services, CLI and installer

Owner 2026-10-27: English-only. Design ~/zs-pause/design/0.8-english-ui.md (critic-reviewed).
Translate in place, no catalog extraction. T2 (TUI) runs in parallel; T3 closes.
Attempt 2: attempt 1 timed out after translating; finish it, and make tests/test_dead_ends.py and
test_merge_dirty.py import without textual/rich (test_toolchain; broken on main).
Glossary (T1 writes, T2's app.py:162-171 parses; both use exactly): «Дальше:»->«Next:»; [g] start|new attempt|check|continue; [u] install (tools); [l] log in|refresh login; [r] revise|reconsider.

Write-set: terminal_planner/agent_profile.py, terminal_planner/authority.py, terminal_planner/bridge.py,
terminal_planner/catalog.py, terminal_planner/cli.py, terminal_planner/commands.py, terminal_planner/engine.py,
terminal_planner/export.py, terminal_planner/foreman.py, terminal_planner/journal.py, terminal_planner/live.py,
terminal_planner/merge_critic.py, terminal_planner/planning.py, terminal_planner/process.py,
terminal_planner/project_read.py, terminal_planner/record_home.py, terminal_planner/runs.py,
terminal_planner/setup.py, terminal_planner/task_gate.py, terminal_planner/update.py, terminal_planner/user_commit.py,
install.py, install.sh, docs/REFERENCE.md, tests/*

Acceptance criteria:
- S1 Every string literal, docstring and comment in the write-set's production .py files is English; cli.py:303
  (bootstrap accept commits the file itself) says it was committed. Example: `zplan doctor` without a login prints
  no Cyrillic; an AST scan of those files finds Cyrillic only in S2's constant.
- S2 [y/N] answers keep accepting «д»/«да» besides y/yes (cli.py:83, cli.py:209, setup.py:459) via one named
  constant. Example: answering «да» to the setup prompt still confirms.
- S3 catalog.py texts are English, code tag ` [code: <family>]` (catalog.py:907); docs/REFERENCE.md changes only
  via `python3.13 -m terminal_planner.catalog --write docs/REFERENCE.md`. Example: catalog.tag("plan.stale") ->
  " [code: plan.stale]".
- S4 install.py and install.sh print English. Example: install.sh with no node on PATH -> one English refusal
  naming Node.js/npm.
- S5 Tests: only tests other than T2's (test_tui*, test_agent_activation, test_feed*, test_architect*) are edited;
  they assert the English text; a Cyrillic negative assertion is translated or deleted (reason in commit
  message); Russian input fixtures stay. Lines exempted by export_check stay byte-identical: setup.py:504,
  test_setup.py:253/587, test_live.py:885/1028/1157, test_task_gate_record.py:941-943.
  Example: test_setup asserts the English doctor line.

Non-goals (reviewers must not require): T2's files; docs other than REFERENCE and the guard test (T3); tests
failing only because of T2's texts; behaviour changes; ru/zh catalog columns.

Risk: medium (text only). DoD: `python3.13 devtools/fasttest.py $(git diff --name-only $(git merge-base main HEAD)
-- 'tests/test_*.py' | sed 's|/|.|;s|\.py$||')`: exit 0 (full suite in T3).
