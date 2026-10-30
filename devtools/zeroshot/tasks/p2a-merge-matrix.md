# p2a — the merge follows the autonomy level: auto merges, supervised asks only on high risk, manual asks

Owner decisions O4 and F6 (docs/PLAN_0.9.md, P2). Today `autonomy.decide(level, "merge", gate)` allows only at
`auto` with `gates.merge == "required"` (autonomy.py:29); the architect's `zplan_merge` (tui/controller.py:1060-1077)
and the status row's `decision` (controller.py:289) read it. New matrix for the architect's own merge:

| level | merge, normal risk | merge, high risk |
|---|---|---|
| auto | allow (gate off: no checks, no critic; gate required: as today) | allow (the gate's critic decides) |
| supervised | allow | ask |
| manual | ask | ask |

The risk is the candidate's at merge time: `process.risk_of(config, paths)` over the attempt's changed paths
(destination base .. result commit, as controller.py:278-283 lists them); a profile without a `risk` section, or
paths that cannot be listed, count as high (fail closed). A gate `required` without checks keeps refusing
(merge.no_checks). A typed /merge stays the owner's consent and is unchanged.

Write-set: terminal_planner/autonomy.py, terminal_planner/tui/controller.py, tests/test_autonomy.py,
tests/test_bridge.py, tests/test_tui_live.py (MergeEvidenceTests pins the old decision)

Acceptance criteria:
- A1 The matrix holds. Example: `decide("auto","merge","off","low")` -> allow; `decide("supervised","merge","off",
  "low")` -> allow; `decide("supervised","merge","required","high")` -> ask; `decide("manual","merge","required",
  "low")` -> ask; an unknown tier at supervised -> ask.
- A2 The architect's merge at auto with the gate off lands and says what did not run. Example: fixture project,
  level auto, `gates.merge: off`, M1 awaiting merge: `zplan_merge` -> kind integrated; the tool's line ends with
  "No merge check or critic ran: the profile's merge gate is off."
- A3 Supervised asks on high risk only. Example: level supervised, a change touching a path the profile's risk
  rules mark high -> refused with family autonomy.ask naming the merge card or /merge; a low-risk change -> merged.
- A4 The status row's `decision` uses the same rule. Example: zplan_status at supervised for a low-risk attempt ->
  `merge.decision` "allow".

Non-goals (reviewers must not require): the merge critic's triggers (p2c), UI and docs wording (p2b), the typed
/merge path, start/approve/resume policy, project rules forbidding merges (known 0.9.0 limitation).

Conflict rule: if a test outside the write-set pins the old merge decision, change nothing in it and end with
`conflict: <file:line>`.

Risk: high (autonomy policy). DoD: `python3.13 devtools/fasttest.py tests.test_autonomy tests.test_bridge
tests.test_merge_gate tests.test_tui_merge_card tests.test_process tests.test_tui_live`: exit 0.
