# p4c — any one-line reason approves a rejected plan

Owner decision F8 (docs/PLAN_0.9.md, P4). Approving a plan the check rejected needs a typed reason of 10 to 500
characters (`OVERRIDE_REASON`, authority.py:79; `override_reason` :940-949, shared by the stored-record reader and
task_gate.py:369), so a short real reason ("ok, tested") is refused.

Change: a reason is any non-empty printable line of at most 500 characters, in submit and in the stored-record
reader; the refusal says "A reason is required: one line, at most 500 characters."

Write-set: terminal_planner/authority.py, tests/test_plan_override.py, tests/test_tui_plan_gate.py,
tests/test_tui_failed_card.py (a10b types 'too short' to get the refusal: an empty reason does it now)

Acceptance criteria:
- A1 A short reason works. Example: a review_exhausted plan, override with "ok" -> approved; the stored override
  carries "ok" and reloads.
- A2 Empty and multi-line reasons still refuse. Example: "  " -> refused with the new text; "a\nb" -> refused; 501
  characters -> refused.

Non-goals (reviewers must not require): the reason form's keys, the task gate's own flow, catalog texts.

Conflict rule: if a test outside the write-set pins the 10-character minimum, change nothing in it and end with
`conflict: <file:line>`.

Risk: medium (persisted override records). DoD: `python3.13 devtools/fasttest.py tests.test_plan_override
tests.test_tui_plan_gate tests.test_task_gate_record tests.test_tui_failed_card`: exit 0.
