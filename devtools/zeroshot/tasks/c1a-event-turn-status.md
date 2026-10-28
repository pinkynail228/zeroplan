C1a — an event turn carries the status, so the architect reacts without extra round trips

Spike docs/spikes/C0_ARCHITECT_COST.md: 55% of the architect's input is requests that only follow a
`zplan_status` (31%) or `zplan_state_update` (24%) call, and 8% are `ALL_TOOLS` listings by the Codex code tool to
find a tool's name. Every request re-sends the whole thread (30-45k tokens).

Write-set: terminal_planner/tui/chat.py, terminal_planner/tui/controller.py, terminal_planner/feed.py,
terminal_planner/architect.py, terminal_planner/resources/architect_method.md, tests/test_tui_chat.py,
tests/test_feed.py, tests/test_feed_wiring.py, tests/test_architect.py, tests/test_bridge.py.

Acceptance criteria:
- C1 An event turn (chat.py:871, `feed.summary`) carries the status `zplan_status` would answer at that moment
  (controller.py:638 `_bridge_status`: requests, plan revision, milestone rows with tokens), compact, after the
  events. Example: an event batch "M1 done" -> the turn's stdin holds M1's row with its state and token.
- C2 When the status cannot be read in time (worker busy, `stale`), the turn says so in one line and still goes
  out; never blocks or fails the turn. Example: status unavailable -> «статус недоступен: вызови zplan_status».
- C3 The method (architect_method.md:11, :50; the file is at its 4096 B cap,
  test_architect.py:658: rewrite those lines, keep every other rule) says: on an event turn, act on the attached status; call
  `zplan_status` only to confirm an action you just asked for; update STATE only when a decision, the plan or the
  next step changed, at most once per turn. Example: the shipped method text contains these rules.
- C4 TOOL_RULES (architect.py:73) names the call form of the pinned Codex code tool, so the model does not list
  `ALL_TOOLS`: `await tools.mcp__zplan__zplan_status({})`, the same prefix for every zplan tool. Example: preamble
  contains `tools.mcp__zplan__zplan_status`.
- C5 Owner turns and the `/new` handoff and warm-up are unchanged. Example: an owner message's stdin has no status
  block added by this change.

Non-goals (reviewers must not require): repeating TOOL_RULES/DRAFT_RULES in `build_update` (kept, design D-0);
the rot metric; A6b3 (hung turns); the MCP server and Controller policy; real token measurement (release smoke).

A test outside the write-set asserting a changed prompt or method text -> `conflict:`.

Risk: medium. DoD: `python3.13 devtools/fasttest.py` tests.test_tui_chat, tests.test_feed, tests.test_feed_wiring,
tests.test_architect, tests.test_bridge, tests.test_install, tests.test_tui_question_card: exit 0.

Attempt 3: fresh on main after RS5 (plan events, feed.py) and RS6 (awaiting_merge rows carry `merge`, method
rewritten); attempt 2 passed but conflicts with both. The attached status keeps RS6's `merge` field; plan events
batch like run events. tests.test_tui_question_card A1/A2 stay unchanged and green (attempt 1 broke them).
