# p3b — accepting the profile writes nothing into the project; saving it to the project is explicit

Owner decision Q4 (docs/PLAN_0.9.md, P3). Every walk shows a "zplan profile" commit on the user's main before any
work: `Profile.accept` writes zplan.process.json and commits it (process.py:1016-1069, `_commit_file` :1109). A
fixture session already accepts without writing the project: the accepted record carries the effective snapshot
(process.py:1046-1057, R-3). `zplan profile init` is the explicit way to write the file (cli.py:934-950).

Change: in a production session too, accept records "accepted" with the snapshot of the resolved proposal (with the
owner's changes) and writes and commits nothing in the project. An existing project file is only recorded, as
today. `zplan profile init` keeps writing the file and is named where the profile is shown as the way to share it.

Write-set: terminal_planner/process.py, tests/test_process.py, tests/test_tui_profile_choice.py,
tests/test_first_run_fixes.py

Acceptance criteria:
- A1 Accept leaves the project untouched. Example: fresh repo with one commit, the profile modal's «accept» ->
  `git log --oneline` still one commit, no zplan.process.json, `git status --porcelain` empty; reopening zplan reads
  the profile as accepted with the same digest.
- A2 Changes from «configure» are kept. Example: configure -> level supervised -> save -> reopened status has level
  supervised; still no project file.
- A3 The explicit path still writes. Example: `zplan profile init` in that project creates zplan.process.json from
  the accepted values.

Non-goals (reviewers must not require): a "save to project" button, the modal's layout, guards (p3a), checks (p3c),
crash-recovery records beyond what accept needs.

Conflict rule: if a test outside the write-set pins the profile commit, change nothing in it and end with
`conflict: <file:line>`.

Risk: high (persisted profile state, git). DoD: `python3.13 devtools/fasttest.py tests.test_process
tests.test_tui_profile_choice tests.test_first_run_fixes tests.test_user_commit tests.test_fixture_scope`: exit 0.
