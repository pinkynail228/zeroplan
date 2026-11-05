# v1c — a merge row carries the check results and the critic's verdict of its candidate

docs/PLAN_UX.md V1, third task. When a merge is refused ("The check 'tests' failed (1); the merge was not done.",
runs.py:1653, family merge.checks_failed), the attempt stays awaiting_merge and the candidate's gate record keeps the
evidence: `r["gate"]["evidence"]` = {outcome, checks: [{name, argv_digest, status, duration_s, tail}]} (built in
checks.py:711, `tail` already bounded and passed through `live._shown`), and `r["gate"]["critic"]` names the
merge-critic record in `authority.state["critics"]` (verdict, findings). The architect's `merge` fields
(`merge_fields`, tui/controller.py) carry only the check names, so it cannot tell a failing test from a missing one
and asks the owner.

Change: `merge_fields` gains
- `"tasks"`: `{"done", "total"}` from the attempt's manifest as `Delivery.tasks_lines` counts it (dropped tasks
  excluded); None when the manifest is unavailable;
- `"gate_result"`: when `r["gate"]` exists and its `result` is the row's current result commit:
  `{"outcome", "checks": [{"name", "status", "tail"}], "critic": {"verdict", "findings"} or None}`, each `tail` and
  finding cut to 12 lines of at most 300 characters (reuse the line cut v1a added for `reason_fields`, extracted to
  one helper if needed); otherwise None (never built, or built for an older result).
Nothing runs a check or the critic for this: only stored records are read. TOOL_RULES (architect.py) extends the
merge line: after a refused merge read rows[].merge.gate_result; never ask the owner which check failed.

Write-set: terminal_planner/tui/controller.py, terminal_planner/architect.py, tests/test_bridge.py,
tests/test_architect.py

Acceptance criteria:
- A1 A failed check reaches the architect. Example: an awaiting_merge row whose stored gate for its result has check
  "tests" status 1 and tail "FAILED test_x" -> `merge.gate_result.outcome` "failed", the check's status 1 and its
  tail contains "FAILED test_x".
- A2 Only this candidate. Example: a gate record for an older result commit -> `gate_result` None; no gate -> None.
- A3 Nothing runs. Example: building the status runs no check and starts no critic (no new record in the store).
- A4 Tasks counted. Example: manifest with 3 tasks, 2 done, 1 dropped -> `tasks` {"done": 2, "total": 2}.
- A5 The architect is told. Example: the first prompt holds the gate_result line; the method file stays within
  4600 bytes.

Non-goals (reviewers must not require): the owner's merge card, running checks early, the critic's own output file,
wording.

Conflict rule: if a test outside the write-set pins the exact keys of `merge`, change nothing in it and end with
`conflict: <file:line>`.

Risk: medium (architect contract). DoD: `python3.13 devtools/fasttest.py tests.test_bridge tests.test_architect
tests.test_consent tests.test_architect_tools`: exit 0.
