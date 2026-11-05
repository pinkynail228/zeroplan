# v1b — the architect's status carries the failing readiness items and the effective profile

docs/PLAN_UX.md V1, second task. A start refused for readiness or a level the architect guesses are facts the owner's
screen shows (the plan block's readiness lines, the profile header) but `zplan_status` does not: its payload
(`Controller._bridge_status`, tui/controller.py) holds requests, revision, rows, plan, commit, consent and asked. The
rows job (`_rows_job`) already reads the profile once, through `autonomy.status_of(app.profile)`, but only when a row
awaits a merge; the gate's readiness is `app.planning.items("start")` (planning.py:281), items built by
`setup.item` (setup.py:560).

Change: the rows job reads both once per status and the payload gains two keys.
- `"readiness"`: the items of `app.planning.items("start")` whose severity is "block", each
  `{"id", "line", "fix"}` (`fix` is the item's `detail`), every text passed through `live.scrub`; `[]` when nothing
  blocks (also without a readiness check, as in the fixtures).
- `"profile"`: from the one `autonomy.status_of(app.profile)` read: `{"state", "digest", "level",
  "parallel_runs"}` (`digest` the resolved short digest, `level` from `autonomy.level_of`, `parallel_runs` from
  `process.parallel_runs` of `autonomy.max_runs`); None without a profile or when it cannot be read. `merge_fields`
  keeps using that same read, so the merge evidence and the profile never come from two reads.
Both are part of the job's snapshot, so a stale answer carries the last read like the rows. TOOL_RULES
(architect.py) extends the zplan_status line: it also reports the failing readiness items with their fix and the
profile (level, parallel runs); a start refused for readiness: name the item and its fix, never ask the owner.

Write-set: terminal_planner/tui/controller.py, terminal_planner/architect.py, tests/test_bridge.py,
tests/test_architect.py

Acceptance criteria:
- A1 Readiness reaches the architect. Example: a fixture controller with a readiness whose origin item blocks ->
  zplan_status `readiness` is one item with id "origin" and its fix; a passing or warning item is not listed.
- A2 The profile reaches the architect. Example: a profile at level auto with max_runs 3 -> `profile.level` "auto",
  `profile.parallel_runs` 3; no profile -> `profile` is None.
- A3 One read. Example: the rows job calls `autonomy.status_of` once per status, with or without a row awaiting merge.
- A4 The architect is told. Example: the first prompt holds the readiness/profile wording; the method file stays
  within 4600 bytes.

Non-goals (reviewers must not require): the screen, the operation results, caching readiness, warnings, wording.

Conflict rule: if a test outside the write-set pins the exact keys of the status payload, change nothing in it and
end with `conflict: <file:line>`.

Risk: medium (architect contract). DoD: `python3.13 devtools/fasttest.py tests.test_bridge tests.test_architect
tests.test_consent tests.test_architect_tools`: exit 0.
