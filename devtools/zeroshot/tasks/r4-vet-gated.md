# r4 — the gated merge path also asks the owner when the integrated candidate is high risk at supervised

Release critic rel090, turn 2 (BLOCK 1 left open): r23 added `vet(paths)` (the architect's last word on the
integrated candidate's own paths, tui/controller.py `_merge_tool`) only to the ungated path of
`MilestoneRuns.merge`; with `gates.merge: required` the call returns into `gate_merge` (runs.py:1560-1561) before
`vet`. Scenario: supervised, gate required, the attempt edits `ci/build.yml`, main renames it into a high-risk path;
the pre-merge estimate allows, checks pass, the critic says go, and `gate_merge` lands it (runs.py:1669) without the
owner, although the level asks on high risk. The critic's go is not the owner's consent.

Change: `MilestoneRuns.merge` passes `vet` to `gate_merge`, which calls it with the candidate's paths (the `paths`
it already computes for the risk and the critic, from `gate_candidate` or the reused gate record) before the critic
and before landing, for a new and a reused candidate alike; a refusal lands nothing and keeps the gate record.

Write-set: terminal_planner/runs.py, tests/test_merge_gate.py

Acceptance criteria:
- A1 Gate required, supervised, high-risk candidate: no landing. Example: the scenario above in a fixture ->
  `zplan_merge` refuses with autonomy.ask; HEAD unchanged; no critic run is started for it.
- A2 A low-risk gated merge at supervised lands as today. Example: gate required, a low-risk change -> checks,
  then merged.

Non-goals (reviewers must not require): the critic's triggers, the owner's own /merge, the ungated path (r23),
wording.

Conflict rule: if a test outside the write-set pins a gated landing of a high-risk candidate at supervised, change
nothing in it and end with `conflict: <file:line>`.

Risk: high (merge gate). DoD: `python3.13 devtools/fasttest.py tests.test_merge_gate tests.test_bridge
tests.test_merge_critic tests.test_tui_merge_wait`: exit 0.
