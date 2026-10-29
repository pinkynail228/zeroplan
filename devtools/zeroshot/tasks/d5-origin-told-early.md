D5 — a project without a GitHub origin hears it before any model work, not after the goal draft (soak S2, rc1 walk N4)

Soak of rc1 2026-10-29 and rc1 walk N4: at start the origin card (tui/start.py:322-326, `settle_origin` :426-436)
offers «Skip», which goes on with no word that planning needs an origin. The architect then drafts the goal (about
46k tokens in the soak) and only the plan is refused: readiness `origin` (setup.py:620-624) is in `NEEDS["plan"]`,
`["start"]` and `["resume"]` (planning.py:39-46) and in no need of the architect chat.

Reuse: `needs_origin`, `setup.readiness` item "origin" and its fix text, `planning.NEEDS`, the chat's note lines,
`status_note`.

Write-set: terminal_planner/tui/start.py, terminal_planner/tui/app.py, terminal_planner/tui/controller.py,
terminal_planner/tui/strings.py, tests/test_tui_origin_early.py (new), tests/test_tui_start.py

Acceptance criteria:
- O1 The origin card's skip row says what skipping costs. Example: no origin -> rows ["Add origin", "Skip — zplan
  cannot plan until the project has a GitHub origin"]; an existing non-GitHub origin -> the same skip text.
- O2 The first message the owner sends to the architect in a session whose project has no GitHub origin is preceded
  in the chat by one notice: planning needs an origin, with the command from the readiness item. The architect still
  answers; the notice is not repeated in that session. Example: fixture project without origin, send "add a flag" ->
  the chat holds the notice once, then the architect's turn; a second message adds no second notice; a project with
  a GitHub origin -> no notice.
- O3 Nothing changes for a project with a GitHub origin. Example: tests.test_tui_start passes with only the skip row
  pins updated.

Non-goals (reviewers must not require): adding the origin from inside the chat, readiness itself, the plan block
card, the plain CLI, `NEEDS`.

Conflict rule: if a test outside the write-set pins the bare «Skip» label, change nothing in it and end with
`conflict: <file:line>`.

Risk: low (text and one notice). DoD: once at the end, in the foreground: `python3.13 devtools/fasttest.py
tests.test_tui_origin_early tests.test_tui_start tests.test_tui_chat tests.test_tui_ready_card tests.test_tui
tests.test_docs tests.test_toolchain`: exit 0; budget.py: OK. New O1 and O2 tests fail on today's code.
