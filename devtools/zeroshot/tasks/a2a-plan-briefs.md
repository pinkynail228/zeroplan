A2a — plan tasks carry a brief (RELEASE_0.6.0_PLAN lane E step 1; ARCHITECT_DESIGN.md section 5).

Why: a milestone task is `{id, title, checks}` (authority.py:283, milestone.py:86, :126); the worker gets no
write-set, criteria or non-goals, so preflight (A4a) and the architect (A5t) have nothing to check or edit.

Reuse: `records`/`require`/`text` in validate_proposal (authority.py:244-288); `check`/`text` in milestone.py; one
brief validator shared by the proposal and the baseline/manifest task (no second copy).

Write-set: terminal_planner/authority.py, terminal_planner/milestone.py, terminal_planner/engine.py,
tests/test_milestone.py, tests/test_terminal_planner.py, docs/UPGRADE.md.

Brief = optional key `brief` on a task: `{goal, why, reuse, write_set, criteria, non_goals, risk, dod}`; strings
`goal` `why` `dod` nonempty, `reuse` may be empty; `write_set` 1-32 repo-relative file paths (no absolute, no `..`,
no duplicates); `criteria` 1-5 `{id, text, example}` all nonempty, ids unique; `non_goals` 0-16 nonempty strings;
`risk` one of low|medium|high; no other keys; every string at most 8192 chars.

Acceptance criteria:
- C1 A proposal task with a valid brief is accepted and the brief reaches the baseline, the manifest task and
  `next_task(...)["task"]["brief"]` unchanged. Example: task `{"id":"T1","title":"x","checks":["c"],"brief":{"goal":
  "g","why":"w","reuse":"","write_set":["a.py"],"criteria":[{"id":"C1","text":"t","example":"e"}],"non_goals":[],
  "risk":"low","dod":"python3 -m unittest tests.test_a"}}` -> next_task carries the same `brief` dict.
- C2 An invalid brief blocks with family `plan.invalid_proposal` (proposal) or the existing baseline/task check
  (stored). Example: 6 criteria, or `write_set: ["/etc/x"]`, or `risk: "huge"`, or an extra key -> blocked.
- C3 Records without `brief` (stored plans, baselines, manifests from 0.5.x) validate and run unchanged; no rewrite
  of stored files; `schemaVersion` stays "1". Example: `fixture_proposal()` (no briefs) validates and builds a manifest exactly as before.
- C4 planner_instructions (engine.py:648) asks for a brief on every task with the field list above;
  verifier_instructions (engine.py:633) rejects a task without a brief or with a criterion lacking an example.
  The fixture planner (engine.py:162) stays unchanged (11 test modules use it). docs/UPGRADE.md: one line that 0.5.x cannot read plans whose
  tasks carry `brief` (roll back only without them).

Non-goals (reviewers must not require): showing briefs in the TUI or plain output (A10); editing briefs or
amendments (A2b, A5e); foreman checks on the brief (A4a); the preflight graph node (A4b); a schemaVersion bump.

Risk: high (persisted schema, planner contract). DoD: `python3.13 devtools/fasttest.py tests.test_milestone
tests.test_terminal_planner tests.test_task_gate tests.test_plan_qual` exit 0; quote the `fasttest:` lines.
