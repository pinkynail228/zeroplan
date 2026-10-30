# p3a — an undecided profile works as proposed, and parallel runs come from the profile

Owner decisions F2, F5, F7 (docs/PLAN_0.9.md, P3). Today an undecided profile (state "never") refuses plan, start,
merge and the task gate with `process.pending` (process.py:1196 `Profile.guard`, delivery.py:758) although the
proposal resolves; "later" exists already (`Profile.defer`, process.py:1181: the proposal's snapshot stored outside
the project and used). Parallel runs read `max_runs` only for an accepted profile, so "later" gets 1
(delivery.py:687-689); a saved 4 or 5 is clamped to 3 silently.

Change: where a guard meets "never", it records "later" for the proposal it would show (the same as `defer()`:
zplan's own store only, the project is not written) and goes on with it; "missing" and "malformed" keep refusing.
`max_runs` is read from the resolved configuration in any usable state, capped at 3; the profile view shows a saved
4 or 5 as 3. The first-start modal stays as it is (its card is later work).

Write-set: terminal_planner/process.py, terminal_planner/delivery.py, tests/test_process.py,
tests/test_task_gate_record.py, tests/test_parallel_home.py (it pins "never" -> one slot)

Acceptance criteria:
- A1 New work starts without a choice. Example: a fresh project, state never: `guard("plan")` returns the proposal's
  status; the store's record is now "later" with the proposal's digest; `git status` of the project is unchanged.
- A2 A damaged profile still refuses. Example: accepted, then zplan.process.json is "{broken" -> `guard("milestone")`
  raises process.invalid; the file deleted -> process.missing.
- A3 Parallel runs follow the profile. Example: "later" with `autonomy.max_runs` 3 -> admission allows 3 runs; a file
  with 5 -> 3, and the profile lines say 3.

Non-goals (reviewers must not require): the first-start modal, /setup, profile persistence (p3b), check detection
(p3c), presets /1 and /2.

Conflict rule: if a test outside the write-set needs `process.pending` for an undecided profile, change nothing in
it and end with `conflict: <file:line>`.

Risk: high (persisted profile state). DoD: `python3.13 devtools/fasttest.py tests.test_process
tests.test_task_gate_record tests.test_runs tests.test_tui_profile_choice tests.test_parallel_home`: exit 0.
