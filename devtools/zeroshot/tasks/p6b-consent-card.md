# p6b — the owner answers the architect's request on a card; the architect says the card is there

After p6a the Controller holds one `ConsentRequest` (start, resume, rebrief) and the asks for approve and merge.
Walk 2026-10-29 step 10: the architect asked "Merge M1 into main?" in the chat and the owner's typed yes was refused.

Change:
- a card "The architect asks" (tui/card_kinds.py, like `commit_card_source` :468-479) for an awaiting request:
  one line ("Start M1 (plan r3)?", "Continue M1 (attempt 2)?", "New attempt of M1: <note>?"), buttons «yes»
  (/approve) and «no» (/decline) routed to `consent`/`decline` by the card's key; the card closes when the request
  is no longer awaiting;
- the plan card and the merge card carry one line "The architect asks you to approve this plan." / "... to merge
  M1." while an ask names them;
- the app redraws on a new request like the commit proposal (tui/app.py:2411 `on_commit_proposal`);
- the architect's TOOL_RULES (architect.py:104-105) and the shipped method's Plan lines (architect_method.md:18)
  say: call the tool; when the level leaves it to the owner the call becomes a card, say in one line that it is
  there; never ask for a yes in the chat.

Write-set: terminal_planner/tui/card_kinds.py, terminal_planner/tui/card_host.py, terminal_planner/tui/app.py,
terminal_planner/tui/strings.py, terminal_planner/architect.py, terminal_planner/resources/architect_method.md,
tests/test_tui_consent_card.py, tests/test_architect.py

Acceptance criteria:
- A1 The request is answered on its card. Example: manual, the architect asks to start M1 -> a card "Start M1 (plan
  r1)?"; «yes» -> M1 starts and the card closes; «no» -> declined, nothing starts.
- A2 Approve and merge use their own cards. Example: supervised, the architect asks to merge M1 -> the M1 merge
  card shows "The architect asks you to merge M1."; its «merge» merges; no second card appears.
- A3 The architect is told to use the card. Example: the first prompt contains "becomes a card" and no longer "never
  ask for a yes in the chat (a chat reply cannot do it)" as the only rule; the method file stays within 4600 bytes.

Non-goals (reviewers must not require): the Controller contract (p6a), several requests, other languages beyond
copying the English text, the line UI.

Conflict rule: if a test outside the write-set pins a changed TOOL_RULES line or card text, change nothing in it and
end with `conflict: <file:line>`.

Risk: medium (UI, architect prompt). DoD: `python3.13 devtools/fasttest.py tests.test_tui_consent_card
tests.test_architect tests.test_tui_merge_card tests.test_tui_auto_plan_card tests.test_tui_approve_card`: exit 0.
