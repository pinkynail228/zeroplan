D5b — the origin notice is in place before the first architect turn is dispatched (critic rel083 finding 1)

Critic rel083 2026-10-29: `ZplanApp.send_chat` (tui/app.py:2556-2569) calls `self.chat.send` first, and
`ArchitectChat.send` (tui/chat.py:776) starts the turn's thread at once; only then does `send_chat` check the origin
and set `origin_note`. D5 O2 asked for the notice to precede the architect's turn.

Reuse: `Controller.origin_fix`, `origin_told`, `origin_note`, `note.origin_needed`, the existing tests in
tests/test_tui_origin_early.py.

Write-set: terminal_planner/tui/app.py, tests/test_tui_origin_early.py

Acceptance criteria:
- B1 The first send of a session whose project has no GitHub origin sets `origin_note` before `chat.send` is called.
  Example: a fake chat whose `send` records `app.origin_note` at call time -> the recorded note contains the origin
  fix command.
- B2 A send the chat refuses keeps nothing: no notice stays, and the next accepted send of the session still
  gets it once. Example: fake `send` returns (False, "busy") first, then (True, "") -> notice absent after the
  first, present after the second; a third send adds no notice.
- B3 With a GitHub origin, or on a host without the D5 fields, nothing changes. Example: tests.test_tui_origin_early
  O3 case and tests.test_tui_activity pass unchanged.

Non-goals (reviewers must not require): the notice text, the Skip row, `NEEDS`, readiness.

Conflict rule: if a test outside the write-set pins the order of `chat.send` and the origin check, change nothing in
it and end with `conflict: <file:line>`.

Risk: low. DoD: once at the end, in the foreground: `python3.13 devtools/fasttest.py tests.test_tui_origin_early
tests.test_tui_activity tests.test_tui_commands tests.test_tui_low_batch tests.test_tui_chat tests.test_tui
tests.test_docs tests.test_toolchain`: exit 0; budget.py: OK. New B1 and B2 tests fail on today's code.
