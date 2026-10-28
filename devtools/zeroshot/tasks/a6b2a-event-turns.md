A6b2a — the architect's event turns in the chat: catch-up on ready, wake-up after a turn or a notify, the owner
first (RELEASE_0.6.0_PLAN step 6 A6b, second part; ARCHITECT_DESIGN.md section 4 decision 2 "Event-driven
architect" and "Catch-up on open"; consumes A6b1's feed, merged 2026-10-25 33c26ed).

Why: A6b1 stores every run event until an architect turn handles it (`feed.pending`/`feed.handle`), but nothing
sends those events to the architect: a run that finished, a verdict, a conflict reach it only when the owner
types. The chat (tui/chat.py `ArchitectChat`) runs one owner turn at a time and refuses a message while a turn
runs (`send` :605, "Архитектор уже отвечает").

Split: this slice is the chat side behind an injected feed port; the app/Controller wiring (the port over the
Authority on the Controller worker, `feed.bootstrap` on open, `notify()` after each observation) is A6b2b, after
A9t frees tui/app.py and tui/controller.py.

Reuse: tui/chat.py `ArchitectChat` (`send`, `_turn` :706, `cancel` :652, `_send`/`_drain`/`_apply`, `owner_entry`,
`entries_of`, `ROLES`/`LABELS`/`AUTHORS` :36-40); architect.py `Architect.begin`/`run`/`finish` :853-886, `_turn`
(`store.append("owner", ...)` :931), `TurnResult.status` :523; feed.py `pending`, `handle`, `WAKE`; tui/strings.py
catalog (`chat.you` :201).

Write-set: terminal_planner/tui/chat.py, terminal_planner/architect.py, terminal_planner/feed.py,
terminal_planner/tui/strings.py, tests/test_tui_chat.py, tests/test_architect.py, tests/test_feed.py.
Not tui/app.py, tui/controller.py, delivery.py (A9t owns them now), runs.py, authority.py.

Acceptance criteria:
- C1 The batch and the message: the chat reads every pending event (`port.pending()` -> the full list in seq
  order; `feed.pending(authority, limit=None)` returns all of them with rest 0, `limit=50` stays the default). The
  batch is the prefix of that list up to and including its 50th `wake` event (the whole list when it has fewer);
  `rest` is the number of events after the batch. `feed.summary(batch, rest)` is a pure function giving the event
  turn's text: a head line «События с прошлого хода:»; one line per wake event in seq order (state: milestone,
  attempt, previous -> state; verdict: milestone, task, round, role, verdict and the verdict text clipped to 300
  characters); «Промежуточных состояний без действия: N.» when the batch holds N > 0 non-wake events; «… и ещё N
  событий.» when `rest` > 0; a last line «Оцени их по снимку и действуй по своим правилам; если решать нечего,
  ответь коротко.». Example: batch [M1 attempt 1 preparing -> running (non-wake), M1 running -> awaiting_merge,
  M1 T2 round 2 code reviewer accepted "ok"], rest 3 -> five lines: the head, the awaiting_merge line, the verdict
  line, «Промежуточных состояний без действия: 1.», «… и ещё 3 событий.», then the last line (six in all); 60
  non-wake events then one wake event -> the batch is all 61, one wake line, «…без действия: 60.».
- C2 The row: `Architect.send`/`run` take `role="owner"` (default, today's behaviour byte-identical); an event
  turn stores its message as a `role "events"` transcript row. The chat shows it as its own author (catalog key
  `chat.author_events`: ru «события», en "events", zh "事件"), never as the owner's line; `ROLES`, `LABELS`
  («соб»), `AUTHORS` gain "events". Example: after an event turn the transcript reads events row, architect row.
- C3 Wake rule: `ArchitectChat(..., feed=None)`; `feed` is a port with `pending()` -> list, `handle(seq)` and
  `snapshot()`, called off the UI thread. With a port, the chat checks for events when it becomes ready (catch-up
  on open), after every turn ends, and on `notify()` (thread-safe; a no-op without a port or while closing). A
  `notify()` that arrives while a check or a turn runs is remembered and one more check runs right after it, so a
  wake event written during a check is never missed. A check starts an event turn only when the batch holds at
  least one wake event; otherwise no turn and no ack. An event turn sends `feed.summary(batch, rest)` with the
  port's snapshot; when its `TurnResult.status` is "completed" it calls `handle(the batch's last seq)` (the
  non-wake events of the batch are acknowledged with it); otherwise nothing is acknowledged. Errors: `pending` or
  `snapshot` raising `Blocked`/`OSError` -> a note, no turn; `handle` raising -> a note, and the ack's persisted
  state follows the existing persistence contract (still pending after a failure before the replace; applied after
  `directory_fsync`). After a port error, a turn that did not complete or an ack that failed, event checks are held until an owner turn completes,
  `reset` runs or the chat is rebuilt (no retry loop; A6b3 adds backoff). Without a port every behaviour and text
  stays byte-identical. Example: ready with pending [running -> awaiting_merge] -> one event turn, then
  handle(seq); pending only [preparing -> running] -> no turn; an event turn fails, or its `handle` raises -> a
  note, `notify()` starts nothing until the owner's next completed turn; `pending` raises `OSError` -> a note,
  later `notify()` calls start no check until then; a notify during a check that found
  nothing -> a second check runs and finds the new wake event.
- C4 The owner first: while an event turn or a check runs, the owner's `send` is accepted (returns (True, "")),
  the owner line shows at once with the note «Отправлю после текущего хода.», and that message runs as the very
  next turn, before any further event check. Only one owner message waits; a second one is refused with today's
  busy refusal. While an owner turn runs `send` refuses as today. `cancel` (esc) cancels the running turn only; a
  waiting owner message still runs after it. Example: event turn running, owner sends "стоп" -> accepted; the
  event turn ends -> "стоп" runs next; then a check runs for what is still pending.

Non-goals (reviewers must not require): any tui/app.py or tui/controller.py change, the real feed port,
`feed.bootstrap` on open, calling `notify()` from observation (A6b2b); hung-turn cancel, backoff, «архитектор
недоступен», stuck rules, wake-ups per hour limits (A6b3); a multi-message owner queue; feed schema changes.

Risk: medium (chat turn flow; no store schema change). DoD: `python3.13 devtools/fasttest.py tests.test_tui_chat
tests.test_tui_chat_dedupe tests.test_tui_chat_scroll tests.test_architect tests.test_feed tests.test_tui_strings
tests.test_architect_home tests.test_lifecycle_guard tests.test_toolchain` exit 0; quote the `fasttest:` lines.
