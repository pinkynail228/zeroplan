# v6c — three defects in v6b's owner-turn consent (Astra's merge review: BLOCK)

This worktree already holds v6b (brief devtools/zeroshot/tasks/v6b-owner-turn-consent.md, its last commit): in a
turn the owner started, an action the level would ask about runs as the owner's own. Astra's merge review found three
defects (static review, file:line in this worktree):
1. tui/controller.py:1404 — the needs_owner exception sits inside the `decide(...) == "ask"` branch, so at supervised
   (rebrief allowed) an owner-turn rebrief answers a needs_owner question with the architect's note, no card.
2. tui/controller.py:1620 (and `_grant` exceptions, :1074) — a refused owner-turn call (a failing merge check, a
   moved token) answers origin owner but writes its result as origin architect without `via`/`turn`; results.json
   keeps the wrong attribution.
3. tui/controller.py:1132 — an events-turn start of M1 left a ConsentRequest awaiting; a later owner-turn "start M1"
   runs it through `_grant` but the request stays awaiting, so the card and status say "waiting for the owner" and
   the next events request is blocked by it.

Change:
- In an owner turn, a rebrief that answers a needs_owner question is a ConsentRequest at supervised and manual
  whatever `decide` says; auto and events turns keep today's behaviour.
- Every result of an owner-bound request, whatever its outcome (done, refused, failed, asked), is origin owner with
  via chat and the turn reference.
- An owner-turn action that does what an awaiting ConsentRequest asked for (same action, milestone and arguments)
  settles that request as done with the same receipt lines; a different awaiting request is left as it is.

Write-set: terminal_planner/tui/controller.py, tests/test_bridge.py, tests/test_consent.py

Acceptance criteria:
- A1 needs_owner. Example: supervised, owner turn, zplan_rebrief answering M1's question -> a ConsentRequest; at auto
  it runs as before.
- A2 Attribution. Example: manual, owner turn, zplan_merge of a low-risk candidate whose check fails -> results[-1]
  {outcome refused, origin owner, via chat, turn}; the same after a reopen.
- A3 Settled. Example: an events turn asks to start M1 (awaiting), then an owner turn starts M1 -> the request is
  done, M1 started once, a later events request is not blocked by it.

Non-goals (reviewers must not require): new tools, TOOL_RULES wording, the screen.

Conflict rule: a test outside the write-set pinning these paths: change nothing, end with `conflict: <file:line>`.

Risk: high (consent policy). DoD: `python3.13 devtools/fasttest.py tests.test_bridge tests.test_consent
tests.test_architect tests.test_tui_consent_card tests.test_feed_wiring`: exit 0.
