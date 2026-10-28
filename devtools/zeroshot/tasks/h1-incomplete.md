H1 — a final check that could not finish says `incomplete`, runs once more, then blocks

Trace audit 2026-10-28 (pause dir, harness/step1/rejections-new.txt #21 #30 #31 #32): every false alarm was a
final_verify rejection "the DoD could not be confirmed", no defect; each started a repair round. Task reviews had
none, so they stay as they are.

Reuse: verifier signal sets; loop `until`/`maxIterations` with converged/exhausted (upstream full_v1_reducer/
evaluation.rs:161); the guard/choice/success helpers and FINAL_STATE in milestone_graph; the REVIEW_BAR constant
style. Node `attempts` retries crashes only and a hard timeout is an error (evaluation.rs:315), so neither fits.

Write-set: terminal_planner/milestone.py, terminal_planner/tui/scheme.py, terminal_planner/tui/strings.py,
devtools/driver_qual.py, tests/test_milestone.py, tests/test_tui_scheme.py.

Acceptance criteria:
- I1 finalVerdict's enum and the signal sets of final_verify and final_reverify (both prefixes) gain `incomplete`,
  defined in one constant: a required check could not run to the end; a seen defect stays `rejected`.
  Example: `empty_final_verify` signals = accepted, rejected, incomplete; scope_verify unchanged.
- I2 final_verify and final_reverify each sit in a loop of at most 2 executions that ends on any other verdict or
  an error; the retry receives the previous finalFindings. No repair runs between them.
  Example: final_verify incomplete, then accepted -> done; repair never ran.
- I3 Incomplete twice ends the run `blocked` with the findings, before any later repair. Example: final_verify
  incomplete x2 -> blocked "final_verify message #2"; inside the repair loop, final_reverify incomplete x2 -> blocked.
- I4 Other paths unchanged; driver_qual gains p_final_incomplete_then_accepted, q_final_incomplete_blocked and
  r_reverify_incomplete_blocked (scripted, not run). Example: scenarios a..o keep node order and output.
- I5 The scheme shows the retry as a count on the final check box (`↻2/2`), no new frame; drawing at 120 columns
  with a retry observation is tested. Example: test_tui_scheme draws final check with ↻2/2.

Non-goals (reviewers must not require): task reviews, scope_verify, preflight, select*; the merge critic; docs;
running driver_qual (owner 2026-10-28: no Linux qualification for 0.8.2).

Conflict rule: if the new label or loops break the pinned 65536 assignment ceiling (comment above final_stage)
without restructuring other stages, change nothing and end with `conflict: <stage> <evidence>`.

Risk: high (the driver graph every user runs). DoD: run once, at the end: `python3.13 devtools/fasttest.py
tests.test_milestone tests.test_tui_scheme tests.test_tui_scheme_tab tests.test_toolchain`: exit 0;
`python3 devtools/budget.py`: OK. Each new test fails with the I1-I3 code reverted.
