# v4a — accepting or changing the process profile keeps a snapshot; the project's file is never written

docs/PLAN_UX.md V4 (design dir v4-astra-design.md, point 3, tasks 1-2). Today `ProcessProfile.accept`
(process.py:1026) writes zplan.process.json into the project and commits it (production), while a fixture session
already records "accepted" with the effective snapshot and writes nothing; `revise` (process.py:1087) replaces the
file and commits it alone. Rule (PLAN_UX V4): a snapshot; the owner's file is the source and is never rewritten.

Change:
- `accept` without a project file records "accepted" with the effective snapshot (as the fixture path does today)
  in production too: no file is written, nothing is committed. With a valid file present it records the file as the
  source, unchanged, as today; a malformed file is refused as today.
- `revise(changes)` on a snapshot-sourced profile sets the changes on the snapshot (the same `apply_changes`
  validation), records the new digest, writes and commits nothing. On a file-sourced profile it is refused
  (family action.refused) with the proposed change in its message ("zplan.process.json is the source: set <key> to
  <value> there"); the file stays byte-identical.
- `zplan profile init` (cli.py, today `accept`) exports: it writes the effective snapshot to zplan.process.json
  (never over an existing file) and commits it as today, with today's words; from then on the file is the source.
- Frozen profiles of plan revisions and attempts are untouched (they are read at freeze time, as today).

Write-set: terminal_planner/process.py, terminal_planner/tui/controller.py, terminal_planner/cli.py,
tests/test_first_run_fixes.py, tests/test_process.py,
tests/test_tui_profile_choice.py, tests/test_setup.py, tests/test_fixture_scope.py, tests/test_dirty_head.py,
tests/test_plan_override.py, tests/test_task_gate_record.py, tests/test_tui_chat.py, tests/test_user_commit.py

Acceptance criteria:
- A1 No file. Example: a fresh repo, accept -> status accepted, no zplan.process.json in the tree, no new commit;
  a reopen resolves the same digest.
- A2 Change the snapshot. Example: accepted snapshot, revise {"level": "manual"} -> level manual, new digest, the tree
  and HEAD unchanged.
- A3 File is the source. Example: the owner's own valid file, revise {"max_runs": 2} -> refused naming the file and
  the proposed value; the file's bytes unchanged.
- A4 Frozen kept. Example: an attempt frozen at digest D; revise -> it still reports D.

Non-goals (reviewers must not require): undo, the first-start card, the settings tool,
wording.

Conflict rule: a test outside the write-set that pins a written or committed profile file: change nothing, end
with `conflict: <file:line>`.

Risk: medium (profile storage). DoD: `python3.13 devtools/fasttest.py tests.test_process tests.test_tui_profile_choice
tests.test_setup tests.test_fixture_scope tests.test_plan_gate tests.test_bridge`: exit 0.
