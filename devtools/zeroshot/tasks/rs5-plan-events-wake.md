RS5 — plan events wake the architect

Delivery smoke 2026-10-26 #1: event turns come only from run records (feed.py:109 `capture`, WAKE :38), so after a proposal is ready or approved nothing wakes the architect and
`auto` never starts M1. Critic r060-tag #2.

Write-set: terminal_planner/feed.py, terminal_planner/tui/controller.py, tests/test_feed.py,
tests/test_feed_wiring.py.

Acceptance criteria:
- C1 Every `Authority.save` (authority.py:730, `feed.capture` :742) also appends one plan event when the current
  plan revision's status (authority.py:80 PLAN_STATUSES; revisions in `state["revisions"]`) differs from the
  status the feed last captured for that revision, or the revision is new. It wakes only when the autonomy
  level (autonomy.py:21 `decide`, level from `autonomy.level(authority.profile)`) lets the architect act on it:
  `proposed` -> "approve", `approved`, `run_failed`, `proposal_invalid`, `review_exhausted` -> "start"; otherwise
  it rides along with wake false. Example: auto, r1 planning -> proposed -> one event, wake true; manual (no
  profile) -> the same event, wake false, no turn; a second save with no change -> no event.
- C2 The event turn names it in one line (feed.py `summary`/`_event_line`). Example: «план r1: planning ->
  proposed»; owner approval of r1 -> «план r1: proposed -> approved».
- C3 One mechanism for every approval path: owner approve/override (planning.py:395, :400), TUI or
  CLI, or the architect's `zplan_approve_plan`, all produce the C1 event through the same save. An idle chat
  learns of it: the Controller calls `on_observed` (controller.py:535) after a mutating job too, never after
  read-only ones or the feed ack. Example: supervised owner /approve, chat idle -> a turn starts, no manual notify.
- C4 State safety: a failed write undoes the capture (`restore`, as for run events); a store whose feed has no
  plan entry yet (written before this change) loads, and its first save records the current revision silently
  (no old-approval event); no event repeats after a restart; `validate_feed` refuses a malformed plan
  event. Example: store with feed and approved r3, no plan entry -> load, save -> no event; then r4 proposed ->
  one event.
- C5 Run and verdict events, batching, ack and their texts are unchanged. Example: the existing
  feed tests pass unchanged.

Non-goals (reviewers must not require): the architect's method or what it does on the event (RS6); the status
payload; chat.py changes; events for draft or non-current revisions; migration of other stores.

A test outside the write-set asserting a changed feed text or schema -> `conflict:`.

Risk: high (persisted state). DoD: `python3.13 devtools/fasttest.py` tests.test_feed, tests.test_feed_wiring,
tests.test_tui_chat, tests.test_bridge, tests.test_lifecycle_guard, tests.test_tui_draft_card: exit 0.

Attempt 4: merge critic: an owner approval saved wake=True but nothing notified the idle chat (only
observation jobs call `on_observed`); the test hid it with a manual `chat.notify()`. Keep the earlier code.
