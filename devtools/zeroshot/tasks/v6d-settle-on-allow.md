# v6d — an owner-turn action settles a matching awaiting request on the allow path too

This worktree holds v6b + v6c (owner-turn consent; briefs devtools/zeroshot/tasks/v6b-owner-turn-consent.md and
v6c-owner-turn-fixes.md). Astra's second review (one remaining finding): the matching awaiting ConsentRequest is
settled only in `_as_owner` (tui/controller.py:1131). Scenario: at manual an events turn asks to start M1
(awaiting); the owner changes the level to supervised in /setup, then says "start M1" in the chat; the policy now
allows the start, so the allow branch calls `delivery.start` directly: M1 starts, but the old request stays
awaiting, the card and status still say "waiting for the owner", and back at manual it blocks the next different
request in `_request`.

Change: after any successful owner-turn start, resume, rebrief, approve or merge, on the ask path and the allow path
alike, an awaiting ConsentRequest for the same action, milestone and arguments is settled as done with the action's
receipt lines; a different awaiting request is left as it is; an events-turn action settles nothing it did not run.

Write-set: terminal_planner/tui/controller.py, tests/test_consent.py

Acceptance criteria:
- A1 Allow path. Example: manual, an events turn asks to start M1 (awaiting); the level becomes supervised; an owner
  turn starts M1 -> M1 starts once and the request is done; a later events request at manual is not blocked by it.
- A2 Different request kept. Example: awaiting start of M2, owner turn starts M1 -> the M2 request stays awaiting.

Non-goals (reviewers must not require): anything else in v6b/v6c, wording.

Conflict rule: a test outside the write-set pinning this path: change nothing, end with `conflict: <file:line>`.

Risk: high (consent policy). DoD: `python3.13 devtools/fasttest.py tests.test_consent tests.test_bridge
tests.test_tui_consent_card`: exit 0.
