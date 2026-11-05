# u5a — when the planner finishes, the Plan tab comes forward instead of a line telling the owner to /view

Relay survey B10 #4: the planner's end only says "The planner finished: /view opens the plan." or "Planning
stopped: /view opens the plan." (`watched`, tui/app.py:4100-4118), so the owner must type /view to see what was
planned. `move_tab` (app.py:2833-2842) is the app's own tab move: it already leaves the tab alone once the owner chose
one since their last send or command (`owner_tab`) and while the whole-window /scheme is open; approval and start use
it (F9).

Change: on the planner's "done" and "failed" ends, `watched` moves to the Plan tab with `move_tab` and the note no
longer names /view ("The planner finished; the plan is on the Plan tab." / "Planning stopped; the Plan tab shows
why."). "stale" and other ends keep their note.

Write-set: terminal_planner/tui/app.py, tests/test_tui_follow.py, tests/test_tui_planning.py (PaneTabTests a1b and
RevisionStateTests a3 expect the live tab after the planner ends: the tab stays live while it runs, Plan once it ends)

Acceptance criteria:
- A1 The plan comes forward. Example: a goal sent, the Conversation tab active, no tab chosen since; the planner
  finishes -> the Plan tab is active and the note reads "The planner finished; the plan is on the Plan tab."
- A2 The owner's choice wins. Example: the owner opened the Changes tab after sending -> the planner finishes -> the
  tab stays Changes; the note still shows.

Non-goals (reviewers must not require): the plan card, the narrow layout's pane, approval and start moves (already
done), the plan screen.

Conflict rule: if a test outside the write-set pins the "/view opens the plan" note, change nothing in it and end
with `conflict: <file:line>`.

Risk: low (tab move, note). DoD: `python3.13 devtools/fasttest.py tests.test_tui_follow tests.test_tui_planning
tests.test_tui_chat tests.test_tui_live`: exit 0.
