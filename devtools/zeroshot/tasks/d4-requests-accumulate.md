D4 — every revision request of a goal reaches the next plan, and outranks the goal text (soak S3)

Soak of rc1 2026-10-29 (real Codex, project textkit2): goal "at least 10× faster on 1 GB"; the architect revised
"drop the 10x target" (r3, 10× gone), then the owner declined twice: "Use 100 MB instead of 1 GB" (r4: 10× back),
"median of five calls" (r5: 10× kept, 1 GB back). Cause, traced in the run store: `Authority.amended_feedback`
(authority.py:833-840) joins requests only while the current revision has no proposal, so r4 and r5 each got only
the last request; `revise_plan` (runs.py:1887-1893) and `revise` (runs.py:1949-1954) resend the unchanged goal;
the planner prompt (engine.py:703) says only "Task contains goal, role bindings and revision feedback", so the goal
wins over a request it contradicts. The plan screen shows one `Revision:` line (planning.py:642-643).

Reuse: `amended_feedback`, the revision records (`goal`, `feedback`, `proposal`), the planner context
(engine.py:1360-1367), `one_line`. No new store field.

Write-set: terminal_planner/authority.py, terminal_planner/engine.py, terminal_planner/planning.py,
tests/test_revision_requests.py (new), tests/test_terminal_planner.py (only its `Revision:` pin at :1513)

Acceptance criteria:
- R1 The feedback of a new revision holds every request made for the current goal, in order, each once, whether or
  not the revision before had a proposal; an edit revision (empty feedback, a draft) in between loses none. Example:
  goal G; revise "drop 10x" -> proposal; revise "100 MB" -> proposal; revise "five calls" -> the third revision's
  feedback contains the three texts in that order, once each.
- R2 A new goal starts with no requests. Example: after R1's chain, a plan for goal H -> its feedback is "".
- R3 The planner's instructions say the revision feedback lists the owner's requests in order, each amends the
  goal, and a later request wins over an earlier one and over the goal text. Example: the planner prompt contains
  that rule; a fixture asserts the sentence, not the whole prompt.
- R4 The plan screen shows the requests, not only one cut line. Example: three requests -> three `Revision:` lines
  (latest last), each cut to one line; more than five -> the last five and "(N earlier)".

Non-goals (reviewers must not require): changing the goal text, the architect's tools, the plan check, the TUI
cards, a store migration.

Conflict rule: if a test outside the write-set pins the "a proposal absorbs them" behaviour, change nothing in it
and end with `conflict: <file:line>`.

Risk: medium (planner input). DoD: once at the end, in the foreground: `python3.13 devtools/fasttest.py
tests.test_revision_requests tests.test_terminal_planner tests.test_runs tests.test_plan_edit tests.test_plan_gate
tests.test_tui_milestones tests.test_docs tests.test_toolchain`: exit 0; budget.py: OK. New R1, R3, R4 tests fail on
today's code.
