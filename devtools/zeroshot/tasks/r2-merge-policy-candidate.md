# r2 — the architect's merge is decided on the integrated candidate and lands only under the profile it was decided on

Release critic rel090 (BLOCK, two findings) on the 0.9.0 candidate:
1. At `supervised` the risk tier comes from `changed_paths(app, r)` = destination base .. result commit
   (tui/controller.py:275, :1190), not from the candidate that lands. Scenario: the attempt edits `ci/build.yml`
   while main renames it to `.github/workflows/build.yml`; the policy sees a medium path and allows, `merge-tree`
   carries the edit into the workflow (high), and with the merge gate off it lands without the owner.
2. With the merge gate off, `MilestoneRuns.merge` lands through `land(...)` without `pinned` (runs.py:1564), so a
   profile the owner changes to `manual` while the candidate is built does not stop the landing; the gated path
   passes the digest (`pinned`), and `land` already re-reads it (runs.py:1586-1596).

Change:
- the tier for the architect's merge at supervised is classified on the paths of the integrated candidate's tree
  (`runs.gate_paths(project, head, tree)`, runs.py:641) right before landing; a high tier refuses with
  `autonomy.ask` and nothing lands (the existing merge-card ask of p6a follows); `merge_fields`' decision may keep
  the pre-merge estimate.
- the ungated landing passes the digest the merge was decided on (`Delivery.merge`'s `expected`, else the resolved
  profile's digest) as `pinned`, so a changed profile refuses with today's `process.changed` and lands nothing.

Write-set: terminal_planner/runs.py, terminal_planner/delivery.py, terminal_planner/tui/controller.py,
tests/test_merge_gate.py, tests/test_bridge.py

Acceptance criteria:
- A1 A high-risk integrated candidate is not merged at supervised. Example: fixture, supervised, gate off, the
  attempt edits `ci/build.yml`, main renames it into a high-risk path before the merge -> `zplan_merge` refuses
  with autonomy.ask; HEAD unchanged.
- A2 A profile changed during the merge stops it. Example: gate off, the profile file changes between the decision
  and the landing -> refused (process.changed); HEAD unchanged; with no change the merge lands as today.

Non-goals (reviewers must not require): the owner's own /merge wording, the "No merge check" line for owner merges
(Later), the gated path, the critic.

Conflict rule: if a test outside the write-set pins an ungated merge landing under a changed profile, change
nothing in it and end with `conflict: <file:line>`.

Risk: high (merge gate). DoD: `python3.13 devtools/fasttest.py tests.test_merge_gate tests.test_bridge
tests.test_merge_cleanup tests.test_consent tests.test_runs`: exit 0.
