# u4b — two notes that stay false: the origin notice after an origin exists, and "zplan starts" in the demo

Soak 2026-10-30:
- N1: "Planning needs a GitHub origin. …" (`origin_note`, `note.origin_needed`, tui/app.py:2580-2590) stays on
  screen after the owner adds an origin, through the run and the merge: it is cleared only at the next accepted
  chat message.
- N6: in the demo (`zplan --fixture demo`, the architect chat is off) `/approve` says "Plan r1 approved. zplan starts
  the first stage." (app.py:3367-3370) while nothing starts and the Plan tab says /run: the note reads only the
  autonomy level, and only the architect starts work at that level.

Change: the origin notice goes as soon as a readiness slice or refresh finds the origin fixed
(`controller.origin_fix()` empty); the approval note says zplan starts the work only when the level allows a start
and the architect chat can act (not the demo, not an architect that is unavailable); otherwise today's "start it with
/run" line.

Write-set: terminal_planner/tui/app.py, tests/test_tui_origin_early.py, tests/test_tui_hints.py

Acceptance criteria:
- A1 The notice follows the origin. Example: no origin, a goal sent -> the notice shows; `git remote add origin
  https://github.com/o/r.git`, the next readiness slice -> the notice is gone.
- A2 The demo does not promise a start. Example: `--fixture demo`, level auto, `/approve` -> the note reads
  "... start it with /run on the main screen."; a real session at auto keeps "zplan starts the first stage."

Non-goals (reviewers must not require): the origin card, the readiness check, other notes, wording beyond the two.

Conflict rule: if a test outside the write-set pins the notice after an origin is added or the demo's "starts"
line, change nothing in it and end with `conflict: <file:line>`.

Risk: low (notes). DoD: `python3.13 devtools/fasttest.py tests.test_tui_origin_early tests.test_tui_hints
tests.test_tui_card_hooks`: exit 0.
