A6b2b — wire the event feed into the app: the chat's feed port over the Authority on the Controller worker
(RELEASE_0.6.0_PLAN "Scope cut"; ARCHITECT_DESIGN.md section 4 decision 2; A6b2a's chat side merged 2026-10-25).

Why: A6b2a made `ArchitectChat(..., feed=PORT)` event-driven, but app.py builds the chat without a port, so a run
that finishes or a verdict still reaches the architect only when the owner types.

Reuse: tui/chat.py `ArchitectChat(feed=)`, `notify()`, the port contract `pending()`/`handle(seq)`/`snapshot()`
(module docstring); feed.py `bootstrap`, `pending(authority, limit=None)`, `handle`; tui/controller.py `post`,
the bounded wait of `_bridge_action` (`bridge.TIMEOUT`), `OBSERVATIONS`; tui/app.py `chat_snapshot()`.

Write-set: terminal_planner/tui/controller.py, terminal_planner/tui/app.py, tests/test_feed_wiring.py (new).

Acceptance criteria:
- C1 Port: `Controller.feed_port()` returns an object whose `pending()` and `handle(seq)` post one job each to the
  worker (`feed.pending(app.authority, limit=None)`, `feed.handle(app.authority, seq)`) and wait for it bounded by
  `bridge.TIMEOUT`; a timeout or a closing controller raises `Blocked` (a chat note, not a crash). `snapshot()`
  returns the app's `chat_snapshot()`. Example: two stored wake events -> `pending()` returns both in seq order
  from a thread that is not the worker; the worker thread never waits on the chat.
- C2 Bootstrap: the Controller runs `feed.bootstrap(authority)` once on the worker after the session opens,
  before the first observation job. Example: a store with two runs and no feed -> after open, `state["feed"]`
  exists with both runs' last states and no pending events.
- C3 Wiring and wake-up: app.py passes `feed=controller.feed_port()` to `ArchitectChat` when the session has an
  architect, and the Controller calls an `on_observed` hook (set by the app to `chat.notify`) on the worker after
  each completed `OBSERVATIONS` job. Example: a fixture run moves running -> awaiting_merge -> the chat runs one
  event turn whose message holds the awaiting_merge line; a second notify with nothing pending starts no turn.
- C4 No regression without an architect: a `--fixture` demo or a session without an architect builds no port,
  never calls bootstrap's save, and every screen and text stays byte-identical. Example: the existing
  tests.test_tui fixture flows pass unchanged.

Non-goals (reviewers must not require): backoff, stuck rules, «архитектор недоступен», hung-turn cancel (A6b3,
0.6.1); `/new` and the warm-up (A8b); changes to chat.py or feed.py (use them as they are); UI for the feed.

Conflict rule: if the port cannot be built without editing chat.py or feed.py, or bootstrap needs a save the
store refuses at open, answer `conflict:` with the path:line before any edit.

Risk: medium (worker threading, no new persisted shape). DoD: `python3.13 devtools/fasttest.py
tests.test_feed_wiring tests.test_tui_chat tests.test_feed tests.test_toolchain` exit 0; quote the `fasttest:`
lines.
