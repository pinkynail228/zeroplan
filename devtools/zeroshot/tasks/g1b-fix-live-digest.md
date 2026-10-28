g1b-fix-live-digest — repair round on G1b-core (branch zs-g1b-plan-gate, task devtools/zeroshot/tasks/g1b-plan-gate.md). One defect found at the merge gate (critic g1b-merge: NO-MERGE, P2).

Defect: `Profile.live_digest()` (terminal_planner/process.py ~668) calls `self.status()`, which is not a pure read: when the session holds the lock it finishes an interrupted accept and adopts a file that appeared after "later" (`_write(make_record("accepted", ...))`). So a refused approve (`plan.gate_stale`) can write the profile sidecar before refusing. G1b requires "Nothing is written by a refusal". `Profile.roles()` has the same shape.

Change: compute the live digest (and roles) without any write: e.g. let `status()` take a keyword that disables the finishing/adoption writes, and use it from `live_digest()` and `roles()`; the digest must be the one that `status()` with writes would report for the same files (an adopted "later" file and a finished accept give the file's digest). Keep `status()` behaviour for every other caller unchanged. Smallest change; no other refactor.

Acceptance criteria:
- F-1 Regression test: profile in state "later", then a valid zplan.process.json appears with a config different from the plan's frozen digest; approve is refused with `plan.gate_stale`, and both planning.json bytes and the profile sidecar file bytes (and its absence/presence) are unchanged. Same for an interrupted "accepting" record with the file present, and for "accepting" without the file, both with and without `previous` (covers the `_write` restore and the `_drop` paths). A separate test: `roles()` in each of these states writes nothing (sidecar bytes and presence unchanged). The tests fail when `live_digest()` goes back to the writing `status()` (show once in a scratch copy).
- F-2 `live_digest()` equals the digest `status()` would accept for the same files (test for "later"+file and "accepting"+file).
- F-3 Existing tests pass: tests.test_process, tests.test_plan_gate, tests.test_tui_plan_gate, tests.test_terminal_planner (name the interpreter).
- F-4 Diff touches terminal_planner/process.py and tests only.

critic g1b-fix-task (session 01a141f9): GO WITH CHANGES (2, applied).
Merged with G1b-core (critic g1b-merge2: MERGE).
