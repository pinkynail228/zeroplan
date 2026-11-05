# v6b — in a turn the owner started, an action the level would ask about runs as the owner's own

docs/PLAN_UX.md V6, owner decision Q6; design and Astra's review in the pause dir (design/v6-chat-consent.md, its
"After Astra's review" part). v6a fixed each request's binding at admission (`Controller._binding`, the registry
entry's `binding` "owner"/"events" and the owner's message reference {text, occurrence}). Today a call the policy
answers "ask" becomes a ConsentRequest (`_request`: start, resume, rebrief) or an asked card (`_ask`: approve,
merge) whatever turn made it (relay R1-R4, R6).

Change:
- When the request's binding is owner, a start, resume, rebrief, approve or merge that the level would ask about
  runs at once through the same service call the owner's own yes runs (`_grant` for start/resume/rebrief, the
  approval and merge the owner's card makes), with every guard it has today (readiness, profile digest, moved
  token, the merge's vet).
- Still asked even in an owner turn: a merge whose candidate the profile rates high or unknown risk at supervised or
  manual; a rebrief that answers a needs_owner question (the owner writes that answer on the card); the commit card
  (unchanged). An events binding keeps today's matrix exactly.
- Its result: origin owner, plus "via": "chat", "turn" (the message reference) and the request id; it reaches the
  screen once through `on_result` like an architect result ("Started at your word: «<message text>»" as its first
  line); results.json keeps and reloads these fields.
- TOOL_RULES (architect.py): in a turn the owner started, call an action only when the owner's message asks for it;
  it then runs as the owner's own; never claim the owner asked when they did not.

Write-set: terminal_planner/tui/controller.py, terminal_planner/architect.py, tests/test_bridge.py,
tests/test_consent.py, tests/test_architect.py

Acceptance criteria:
- A1 Owner turn runs. Example: manual, an owner turn's zplan_start of M1 -> M1 starts, no ConsentRequest; results[-1]
  {operation start, outcome done, origin owner, via chat, turn.text the message}.
- A2 Events still ask. Example: manual, an event turn's zplan_start -> a ConsentRequest, as today.
- A3 Kept asks. Example: supervised, owner turn, zplan_merge of a high-risk candidate -> asked; a rebrief answering
  a needs_owner question -> a ConsentRequest.
- A4 Survives reopen. Example: the owner-turn result above is in `results` after a new controller opens the store.
- A5 The architect is told. Example: the first prompt holds the owner-turn line; the method file within 4600 bytes.

Non-goals (reviewers must not require): new tools, settings, the screen beyond the one line, wording.

Conflict rule: a test outside the write-set pinning the consent path for an owner turn: change nothing, end with
`conflict: <file:line>`.

Risk: high (consent policy). DoD: `python3.13 devtools/fasttest.py tests.test_bridge tests.test_consent
tests.test_architect tests.test_tui_consent_card tests.test_feed_wiring`: exit 0.
