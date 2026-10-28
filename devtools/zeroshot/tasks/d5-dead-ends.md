D5 — no dead ends on the normal path

Owner 2026-10-27 after D4: «где ещё такие косяки?» An audit of refusals that protect nothing found these (after
D4 merged; D4a-c handle uncommitted files and the baseline).

Write-set: terminal_planner/planning.py, terminal_planner/engine.py,
terminal_planner/runs.py, terminal_planner/delivery.py, terminal_planner/catalog.py, terminal_planner/tui/app.py,
terminal_planner/tui/chat.py, install.py, docs/REFERENCE.md, tests/*

Acceptance criteria:
- E2 The chat retries as soon as the checks it needs pass (planning.TOOL_CHECKS, planning.py:38), not
  only when every start check passes (tui/app.py:2515-2528). Example: no login + no Git identity -> `zplan login`
  done -> the chat answers without restarting zplan; identity still blocks only a milestone start.
- E3 Every refusal on the normal path carries a real family with a fix in catalog.py, never the default
  store.invalid: runs.py start (:886, :894) and merge (:1541). Example: merge while on another branch -> «[код:
  readiness.branch]» and «git switch <branch>», not «report it».
- E4 A plan left in submission_unknown (timeout or --detach refusal, engine.py:1404) offers [g] that resubmits the
  same frozen documents with the same submission key (the engine deduplicates: upstream
  zeroshot/src/native_v2_cli/local.rs:215-221, 309-353); catalog.py:242 then matches a real button. Example:
  fixture driver times out once -> [g] -> the same run id, the plan proceeds.
- E5 An interrupted clone (engine.py:1330, 1550, 1720) with native_prepared false and nothing submitted is
  removed and cloned again instead of «требуется ручная проверка». Example: leftover planner checkout dir from a
  kill -> next «составить план» plans.
- E6 install.py without Node.js/npm prints only the refusal (no «…затем zplan login.» hint from install.py:61 before it).
  Example: PATH without node -> last output is one refusal line naming Node.js/npm, exit 1.

Non-goals (reviewers must not require): merge critic polling; Git identity rules; en/zh texts; the line UI
beyond shared messages; engine changes.

Tests: new tests/test_dead_ends.py covers E2-E6 with fixtures; tests asserting the old behaviour are updated.

Risk: high (plan validity, resubmission). DoD: `python3.13 devtools/fasttest.py tests.test_dead_ends
tests.test_project_state tests.test_plan_gate tests.test_terminal_planner tests.test_runs tests.test_install tests.test_reference
tests.test_tui_chat`: exit 0 (full suite: the gate).
