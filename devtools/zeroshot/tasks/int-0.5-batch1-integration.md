# 0.5 batch 1 — integration addendum (orchestrator, 2026-10-20)

Supplements the receipts of s2a1-home-core, s5a2-disk-probe, s5a1-warn-contract and s1a1a-gate-core (left as recorded).

- Candidates: zs-s2a1-home-core 1386982 (run 01a15580, base 6e23523), zs-s5a2-disk-probe 1c4023e (run 01a155aa, base e29f986), zs-s5a1-warn-contract 6a17daa (run 01a15585, base 6e23523), zs-s1a1a-gate-core a2d6c81 (run 01a15573, base 6e23523); each reviewer pair accepted.
- Integration chain: 7a7fb59 = c9f5164 + s2a1 + s5a2; 99cd700 = 7a7fb59 + s5a1; 8b245ff = 99cd700 + s1a1a + main c345b92 (s1b1 brief only). main fast-forwarded to 8b245ff.
- Gates (logs in ~/zs-pause/):
  - 7a7fb59: Linux full Ran 1164 OK; macOS test_disk/test_record_home/test_toolchain/test_reference 115 OK.
  - 99cd700: Linux full Ran 1176 OK; macOS warn_contract/setup/runs/tui/tui_polish/tui_chat/disk/record_home/toolchain/reference 381 OK.
  - 8b245ff: Linux full Ran 1200 OK, no skips; macOS plan_gate/plan_override/process/task_gate/toolchain/reference 246 OK, plus test_tui_plan_gate 7 OK.
- s2a1 intermittent failure: Linux full on 1386982 failed test_tui_chat LifecycleGuardChatTests.test_a3_a_chat_goal_handed_over_while_m1_is_active_is_refused_and_the_run_still_delivers ('ещё выполняется' not found in ''); three module reruns at 1386982 OK 117 each, all integrated full runs green. Recorded as intermittent (cause unproven; timing is a hypothesis), STATE Open.
- s1a1a size deviation: 767 changed lines against the brief's 600 stop threshold, without the required stop/re-gate. Accepted retroactively by critic int-s1a1a (245 product lines, 522 test lines, no s1a1b/c scope absorbed). Behavioral native qualification of the task gate is deferred to the s1a1b integration (receipt :162-164).
- s5a1 follow-up (not required by critic): commands.py English help still reads "exit status 0 only when everything is ready"; WARN keeps ok=True, so behavior is unaffected.
- Critics: int-s2a1-s5a2-s5a1 (MERGE 7a7fb59; 99cd700 after green gates), int-s1a1a (MERGE after green gates, add test_tui_plan_gate on macOS).
