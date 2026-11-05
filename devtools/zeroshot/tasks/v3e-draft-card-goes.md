# v3e — the blocking draft card goes: a draft is saved in Drafts with one line, /plan sends it

docs/PLAN_UX.md V3, Q3, second Drafts task (Astra's consult, point 4). After
v3d every goal draft is listed in the permanent Drafts tab (TAB_DRAFTS, `render_drafts`, tui/card_host.py), yet
`refresh_draft_card` still mounts a card "Draft a plan from this?" after 11 of 11 plain first goals, and the slash state "draft" (tui/app.py, `screen_slash_state`) comes from that open
card, so an old draft can stand in the way of /approve.

Change:
- No draft card. A new goal draft (once per key, never again on a refresh or reopen)
  gets one zplan line in the chat: "Draft saved in Drafts." plus, when sending is possible now, "Use /plan to send
  the latest draft to planning."; Drafts comes forward through `move_tab` as in v3d.
- A bare `/plan` sends the newest draft that was not sent and whose identity is still fresh (the existing
  `chat.stale_reason` check right before sending, the draft identity travelling with the goal, as the card's /plan
  did); with none it keeps today's `send_unsent_plan`. `/plan <text>` is unchanged (a new goal).
- The slash state "draft" holds only while such a sendable draft exists; a sent or stale draft never holds it, so
  it never blocks /approve.
- The draft card's builder, strings and routes go with the card; /decline no longer applies to a draft.
- tests/test_tui_draft_tab_ends.py imports without Textual or Rich, as test_toolchain requires (v3d broke it).

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/card_host.py, terminal_planner/tui/card_kinds.py,
terminal_planner/tui/cards.py, terminal_planner/tui/strings.py, tests/test_tui_approve_card.py,
tests/test_tui_card_hooks.py, tests/test_tui_card_keys.py, tests/test_tui_cards.py, tests/test_tui_chat.py,
tests/test_tui_chat_scroll.py, tests/test_tui_chat_steps.py, tests/test_tui_draft_card.py,
tests/test_tui_draft_tab_ends.py, tests/test_tui_failed_card.py, tests/test_tui_merge_card.py,
tests/test_tui_reopen_fixes.py, tests/test_tui_split.py, tests/test_tui_slash.py, tests/test_tui_rb_fixes.py

Acceptance criteria:
- A1 No card. Example: a plain first goal at auto, the architect replies with a goal draft -> no card is mounted;
  the chat shows "Draft saved in Drafts." once, also after a reopen.
- A2 /plan sends the newest. Example: two drafts, bare /plan -> the newer is sent with its identity; a stale one
  (the plan moved) is refused on the status line and nothing starts.
- A3 Never in the way. Example: a draft sent as r1, r1 proposed -> /approve acts; the state is not "draft".

Non-goals (reviewers must not require): the proposed plan in Drafts, the approved-plan projection, V6, wording.

Conflict rule: a test outside the write-set pinning the draft card: change nothing, end with `conflict: <file:line>`.

Risk: low. DoD: `python3.13 devtools/fasttest.py tests.test_tui_draft_card tests.test_tui_draft_tab_ends
tests.test_tui_cards tests.test_tui_chat tests.test_tui_approve_card tests.test_tui_reopen_fixes tests.test_toolchain`: exit 0.
