# v3c — a new attempt starts at once; instructions for it go through the chat

docs/PLAN_UX.md V3 (fewer decisions). The failure card's /retry already starts a new attempt with an empty note,
no form (card_host.py `retry_failed_card`). Two owner paths still open a form first: the panel key on a failed or
stopped row (`new_attempt_milestone`, tui/app.py) and the run screen's "new attempt" action (app.py, the `sent`
callback of the end view's actions), both through `attempt_screen` (a NoteScreen with bar "tui_attempt", "Note for
the new attempt (optional, may be left empty)"). The note is optional, so the form is one extra decision on every
retry. An owner who wants different instructions says so in the chat: the architect's `zplan_rebrief` carries a note
(its consent card at manual is the owner's yes).

Change:
- Both paths start the new attempt at once with an empty note, exactly as /retry does (the same controller call,
  the same `attempt_job` observation and run_note words); no form opens.
- The run screen's line about a new attempt says, once, that new instructions go through the chat ("To change the
  instructions, tell the architect in the chat.").
- `attempt_screen` and the `tui_attempt` screen with its catalog actions go; the plain CLI's own note prompt
  (cli.py:782) stays (not this screen).

Write-set: docs/REFERENCE.md (generated from the catalog), terminal_planner/tui/app.py, terminal_planner/catalog.py, tests/test_tui_live.py, tests/test_tui.py, tests/test_tui_milestones.py (:410-424, :776-782 press the form),
tests/test_reference.py

Acceptance criteria:
- A1 Panel. Example: M1 failed, the panel's new-attempt key -> attempt 2 starts, no NoteScreen is pushed, run_note
  "M1: new attempt started."
- A2 Run screen. Example: the end view of a stopped M1, action new attempt -> attempt 2 starts with no form.
- A3 Told where instructions go. Example: the end view of a failed M1 shows the chat line once.
- A4 Gone. Example: no "tui_attempt" screen in the catalog; the reference test still passes over every remaining
  NoteScreen bar.

Non-goals (reviewers must not require): the plan change ("plan") and answer notes, the architect's rebrief, the
plain CLI, resume.

Conflict rule: if a test outside the write-set pins the new-attempt form, change nothing in it and end with
`conflict: <file:line>`.

Risk: low (owner screen). DoD: `python3.13 devtools/fasttest.py tests.test_tui_live tests.test_tui tests.test_reference
tests.test_tui_failed_card tests.test_tui_milestones`: exit 0.
