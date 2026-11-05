# v3g — the last approved plan and its progress, readable while a newer revision is only proposed

docs/PLAN_UX.md V3, Q3, third Drafts task (Astra's consult, design dir drafts-astra-consult.md, point 1). Q3: the
Plan tab shows the approved plan and its progress; an unapproved revision belongs in Drafts. Today everything reads
the current revision: `Delivery.home()` (delivery.py:546) shows only "Plan rN · status" for a non-approved current
revision, and `Runs.overview()` (runs.py:1815) returns [] unless the current revision is approved. So after r1
approved and running, a revise to r2 (proposed) hides r1 and its milestones' progress. Revisions keep their status
in the store: the newest revision whose status is "approved" is the last approved plan; `current_record(milestone,
revision, memo)` (runs.py:1765) already takes a revision.

Change (a read-only projection; no screen change in this task):
- `Runs.overview` takes an optional revision (default: today's current one, unchanged) and builds the same entries
  for it; nothing is dispatched or exported.
- `Delivery` gains the view of the last approved plan: its goal line, version and the overview lines of its
  milestones with their state, as home shows them for an approved current revision; None when no revision was ever
  approved. When the current revision is the approved one it equals home's plan part.
- The Snapshot carries it (`approved`, plain data, None when none), read in the same refresh as today's lines. The
  current revision's `plan`, `version`, `status`, `rows` and every action stay exactly as they are.

Write-set: terminal_planner/runs.py, terminal_planner/delivery.py, terminal_planner/tui/controller.py,
tests/test_parallel_home.py, tests/test_terminal_planner.py

Acceptance criteria:
- A1 Kept while revising. Example: r1 approved, M1 running; the owner revises and r2 is proposed -> the snapshot's
  `approved` shows r1 with M1 running; `rows` and `plan` are r2's, as today.
- A2 Across a reopen. Example: the same store opened by a new controller -> `approved` is r1 with M1's state.
- A3 None before the first approval. Example: only r1 proposed -> `approved` is None.
- A4 Same when current. Example: r1 approved and current -> `approved`'s lines equal home's plan lines.

Non-goals (reviewers must not require): the Plan and Drafts tabs' content (next task), the plan card, actions on the
old revision (none: it is a view), wording.

Conflict rule: if a test outside the write-set pins `Runs.overview`'s signature or the Snapshot's fields, change
nothing in it and end with `conflict: <file:line>`.

Risk: low (read-only projection). DoD: `python3.13 devtools/fasttest.py tests.test_parallel_home
tests.test_terminal_planner tests.test_bridge tests.test_tui_milestones tests.test_milestone_snapshot tests.test_live`: exit 0.
