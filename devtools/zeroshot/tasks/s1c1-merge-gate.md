s1c1-merge-gate — 0.5 item S1c (docs/RELEASE_0.5_SCOPE.md S1c row), child 1 of 2: the G3 merge critic and release mode. Merge happens only after passed checks and an accepted critic verdict, or an owner override. Child 2 (s1c2-status-truth) adds derived truth. Design: docs/PROCESS_PROFILE.md "Owner requirements" R4/R5, "Gate discussion", "Gate record", "Stages on native graphs" (Merge gate). DeepSeek worker, sol reviewers.

Base: main with s1a1-task-gate and s1b-checks merged. Record the base commit in the receipt. The audit is on main 74f1a3b: re-check every line number on the base, and re-gate if a premise moved.

Audit (74f1a3b, plus the merged s1a1/s1b):
- Merge path:
  - `Delivery.merge` delivery.py:804-814 calls `guard("merge")` (process.unbuilt, process.py:656-657);
  - `Runs.merge` runs.py:1081-1128 does `--no-ff`, with delivery awaiting_merge/conflict;
  - CLI cli.py:713-736; TUI tui/controller.py:783-786, tui/app.py:2526.
- Gate pieces to reuse:
  - s1a1's gate record type, discussion parsing, override and stale helpers;
  - the plan-gate graph shape engine.py:422-479;
  - s1b's qualification record and validity.
- Release flag: none. The plan schema authority.py:264 has fixed milestone keys `["id","title","depends_on","slices"]`; the engine planner prompt is engine.py:333.

Read: those locations; terminal_planner/authority.py, engine.py, process.py, delivery.py, runs.py, planning.py (gate_lines :525), catalog.py, cli.py, tui/controller.py, tui/app.py; docs/PROCESS_PROFILE.md; the s1a1 and s1b tests; tests/test_plan_gate.py, test_plan_override.py, test_runs.py DeliveryTests.

Rules:
- R-1 Scope. With `gates.merge == "off"`, everything stays byte-identical to the base. With "required", this task replaces s1b's remaining `process.unbuilt` for merge.
- R-2 Precondition. Gate dispatch requires either checks=[] or a current terminal qualification (passed or failed). Merge requires: (checks=[] OR current passed qualification OR current failed qualification with a valid failed-checks override) AND a current merge gate AND (accepted critic verdict OR valid gate override). For checks=[], bind qualification_id=null and the empty checks digest; display "без квалификации", never "passed".
- R-3 Graph. Add a merge-gate graph with the s1a1 shape: a read-only proposer that argues and cannot change the artifact, a `critic` with `node_instance`, and `maxIterations = limits.merge_rounds`.
  - Gate submission, observation, rerun, release-input entry and overrides are explicit catalog actions available in TUI, plain and CLI, following s1a1 lifecycle rules. Do not use Delivery.diff_text()'s truncated UI diff as critic evidence; provide the full frozen diff or explicitly refuse oversized input.
  - Input: the exact diff destination-HEAD...result.commit, the qualification record summary (per-check status and the diagnosis verdicts), the rules files and, for a release milestone, R-4's release input.
  - Terminals, discussion caps, and native failure vs rejection are as in s1a1.
- R-4 Release mode. A milestone may carry `release: true` in the plan schema; the planner prompt mentions the key only as optional. release is an optional strict boolean; absence adds no field and changes no existing digest. Release input contains a version label (1..128 printable characters), an owner-authored decision (10..500 printable characters), proposed_verdict=accepted|rejected, and the frozen milestone baseline.checks in their existing order. Each checklist entry has an explicit boolean status and an optional note of at most 500 printable characters. Bind the complete input to the gate; refuse input above 32768 UTF-8 bytes before dispatch, without truncation.
  - The release input is stored in the gate record before dispatch.
  - The critic verdict covers both.
- R-5 Merge rule. With R-1 active, `[m]`/merge requires all of the following, rechecked immediately before `git merge`:
  - the R-2 qualification condition (checks=[], passed, or failed with a valid failed-checks override);
  - a valid merge-gate record whose artifact (result commit + tree + destination HEAD + qualification record id + checks digest + config digest, plus release input when present) equals the live values;
  - `critic_verdict == accepted` or an override.
  Otherwise the refusal comes before any side effect, with families `merge.qual_missing`, `merge.qual_failed`, `merge.gate_missing`, `merge.gate_rejected` and `merge.gate_stale`.
- R-6 Override.
  - A failed-checks override is a separate owner record bound to the qualification id and artifact identity. Store the exact failed-check names as a structured list and a reason validated by s1a1 rules. New qualification or changed identity invalidates it. It changes neither qualification outcome nor critic verdict.
  - A rejected merge gate can be overridden with a typed reason (s1a1 rules); the critic verdict stays.
  - The failed-checks override is shown as "слияние несмотря на проваленные проверки" on the gate, merge question, home and status.
  - Missing/running/stale/native-failed gates and missing/stale/interrupted qualifications cannot be overridden.
- R-7 Rejected -> new attempt with the findings as owner feedback, using the existing new_attempt path (the findings text goes into the attempt context), or override.
- R-8 Display. The merge question shows qualification, gate verdict, override(s) and the release decision. `[i]` shows the discussion. Same text in TUI and plain; REFERENCE.md regenerated.

Acceptance (unit tests, deterministic fixtures):
- A-1 Off is identical, golden (including a plan without `release` and its digests).
- A-2 Graph: interpreter tests as in s1a1 (reject->accept, dispute, exhaustion, critic error, no write path).
- A-3 Merge rule: each refusal family through service, CLI, plain and TUI, with no side effect (Authority store and git refs/HEAD snapshot unchanged). Allowed after accepted, after gate override, and after gate override plus failed-checks override.
- A-3b Cover checks=[], accepted critic plus failed-checks override, rejected critic requiring both overrides, and stale override refusal. Exercise missing/running/exhausted/native-failed/session_lost gates without mutation. Test every bound identity independently, malformed release values, release-input boundaries, and a decisive change beyond the first 4000 diff characters.
- A-4 Staleness: destination HEAD moves after the gate -> stale; a new qualification -> stale; release checklist edit -> stale.
- A-5 Release: release input is required for a release milestone and refused when absent. A non-release milestone ignores it.
- A-6 Restart: crash after gate dispatch -> no duplicate run (fault injection as in s1a1 A-5). Crash between the recheck and `git merge` -> the existing merge crash-window handling still holds (CrashWindowTests).
- A-7 Base failure: compatibility on base; a regression through Delivery.merge with `gates.merge: required` that expects `merge.qual_missing` fails on base. Report named failures and skips separately. Compatibility assertions pass on base. Behavioral regressions must reach a named assertion through an existing production entry point using base-supported fixtures; import/missing-symbol/setup failures and skips do not count. Map candidate-only invariants to killed mutations. Recheck the selected regression on the actual prerequisite base. The base fixture has non-empty checks.

Size: about 800-1200 changed lines including tests, above the ~500-line review trigger; kept together because the merge rule, both overrides and the gate record are one enforcement invariant reusing s1a1/s1b stores. 1600 is a mandatory re-gate point, never a reason to cut acceptance.

DoD:
- Unit tests pass.
- Docs updated: REFERENCE, USER_FLOW, PROCESS_PROFILE (G3 merge gate built).
- Receipt.
- The orchestrator runs native qualification of the new graph on the Linux test host before merge.
