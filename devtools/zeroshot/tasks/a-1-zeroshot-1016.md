A-1 — Zeroshot 10.16.0 becomes the default engine (RELEASE_0.6.0_PLAN A-1).

Why: Linux qualification of 10.16.0 (2026-10-24): install, contracts PASS; driver 12/13, `m_adapter_resume`
blocks «Несовместимое planning state/envelope.»: 10.16 adds an optional `context` to a failed terminal result
(v10.16.0 `protocol/openengine-cluster/v1/native-v2-observation.schema.json`: `FailureContext`,
`FailureDiagnostic`, `ActiveExecution`); zplan accepts only `{status, reason}` (authority.py:947, runs.py:388).
Other 10.13-10.16 schema changes are additive (Pi providers), unused by zplan.

Reuse: `require`, `nonempty` and the `activeExecutions` item check (authority.py:926-929); one shared validator for
both sites. `git -C upstream show v10.16.0:PATH` for the schema.

Write-set: terminal_planner/authority.py, terminal_planner/runs.py, terminal_planner/toolchain.py,
tests/test_toolchain.py, tests/test_setup.py, tests/test_runs.py, tests/test_terminal_planner.py, docs/UPGRADE.md.
Version strings in other test fixtures stay.

Acceptance criteria:
- C1 A failed terminal result may carry `context`: absent, null, or exactly the schema shape (all optional: `incomplete`
  bool; `primary` diagnostic or null; `recorded` at most 5 diagnostics; a diagnostic = required `message` string of
  at most 16384 chars without control characters, optional `cursor` string or null, optional `execution` `{execution, node}` or null; no other
  keys at any level). Accepted in the planning envelope and in the stored run terminal. Example:
  `{"status":"failed","reason":"node_failed","context":{"incomplete":false,"primary":{"message":"timeout after
  1200s","cursor":null},"recorded":[]}}` -> the run ends `failed` with diagnostic «node_failed».
- C2 Any other `context` blocks as today. Example: `recorded` with 6 items, or a diagnostic with key `extra`, or
  without `message` -> «Несовместимое planning state/envelope.».
- C3 Stored records written under 10.12 (no `context`) validate and load unchanged; no migration, no rewrite.
- C4 Default toolchain = Zeroshot 10.16.0, Codex 0.162.1 unchanged, SHA256s:
  x86_64-unknown-linux-musl 2f1ad10956875eccb1aadf60b879fb4195db20fbffd9854a4537f0f1369c9a40,
  aarch64-unknown-linux-musl 6f58bc709bbf9e5d1959834e6f03357f0fe195e4463a7065301bb8b50f794ef3,
  aarch64-apple-darwin d8da042239ea252b41ab39f3eba82892e51a7b01c3c0a63460d4f24bfe74e2ef.
  Example: `toolchain.current().tool_dir_name` -> `zeroshot-10.16.0-codex-0.162.1-runtime2`. docs/UPGRADE.md: one
  line that 0.5.x on 10.12 cannot read run records that carry `context` (roll back only with no such records).

Non-goals (reviewers must not require): showing `context` messages in the UI or diagnostics; Pi providers; a
Codex upgrade; changes to driver_qual/plan_qual; the Linux qualification itself (the orchestrator runs it at merge).

Risk: high (native contract, persisted records, toolchain pin). DoD: `python3.13 devtools/fasttest.py
tests.test_toolchain tests.test_runs tests.test_terminal_planner` exit 0; quote the `fasttest:` lines.
