A6b1 — the architect's event feed: a persisted queue of run events with its own handled mark (RELEASE_0.6.0_PLAN
step 6 A6b, first part; ARCHITECT_DESIGN.md section 4 decision 2 "Catch-up on open", critic architect-gaps B1;
design critic ~/zs-pause/critic/a6b1-design.out: a derived feed loses folded transitions and bounded verdicts).

Why: the engine cursor (`MilestoneRuns.observe`, runs.py:1035) only says what zplan observed; nothing records what
the architect has reacted to, so a run that finished while no architect turn ran is never brought to it. A6b2
(catch-up and wake-up turns, the explicit bootstrap on open) and A6b3 (unavailable architect, stuck rules) consume
this feed; this slice has no TUI caller.

Design: the queue lives in the planning store (`state["feed"]`, an optional schema-2 key exactly like `critics`,
authority.py:471/:483), so an event is written in the same atomic save as the record change that caused it: never
lost, never written without its cause. State events are captured in `Authority.save` (authority.py:720) by comparing
every run record's `run_state` with the feed's last captured state; verdict events are appended where a verdict is
recorded (runs.py:1122), identified by the reviewer's execution reference.

Reuse: runs.py `run_state` :292, `extended` :173, `resume` successor :1332 (same branch/attempt, `predecessor` set),
`read_verdict` :1096 (`reference`, `entry` task/round/role); authority.py `save` :720, `validate_state` :460,
merge_critic.py `validate_critics` (the optional-key precedent).

Write-set: terminal_planner/feed.py (new), terminal_planner/authority.py, terminal_planner/runs.py,
tests/test_feed.py (new).

Acceptance criteria:
- C1 Shape and bootstrap: `feed.bootstrap(authority)` creates `state["feed"] = {"seq": 0, "handled": 0,
  "last": {key: run_state(r) for every record}, "verdicts": {key: []}, "events": []}` and saves; it is a no-op when
  the feed exists. On a project with no store yet (`authority.state is None`, authority.py:416) it writes nothing and
  marks the Authority so that the save that first creates the store starts with an empty feed (`last` {}), so the
  first plan and run of that session are captured. Without a feed nothing is captured and the store stays
  byte-identical (today's stores). A record's key is `"%s/%s/%s/%s" % (plan_revision, milestone, attempt,
  predecessor or "-")`, unique across resume successors. `validate_feed` (called from `validate_state`) refuses a
  malformed feed like any malformed store. Example: bootstrap with M1 running -> last {M1 key: running}, no events;
  then M1 observed finished with outcome done -> two state events, running -> unknown (the save before
  `evaluate`, runs.py:1272) -> awaiting_merge (runs.py:1306), both pending; bootstrap on a new project, then plan + start M1 -> M1's
  events are captured.
- C2 State events: every `Authority.save` with a feed appends, before writing, one event per record whose
  `run_state` differs from `last[key]` (or has no `last`): `{"seq": n, "kind": "state", "key", "milestone",
  "plan_revision", "attempt", "run_id", "state", "previous", "wake", "at"}`, then updates `last`. `wake` is True for
  stopped, conflict, integrated, awaiting_merge, needs_owner, blocked, failed_recoverable, failed. Every save
  captures, so no transition between two saves is folded. Example: awaiting_merge -> integrated -> awaiting_merge
  (runs.py:1613) gives two events after the first; failed M1 resumed -> the successor key gets its own events and
  M1's stay. Rollback: when the write fails before the replace (any `PersistenceError` stage but
  `directory_fsync`, authority.py:728), the feed is restored to its state before this save's capture, so a record
  that the caller then removes (runs.py:839-842) leaves no event. Example: start whose save fails -> the next
  successful save has no event of the removed record.
- C3 Verdict events: a verdict recorded at runs.py:1122 also appends `{"seq", "kind": "verdict", "key",
  "milestone", "plan_revision", "attempt", "run_id", "execution", "task", "round", "role", "verdict", "text", "wake":
  True, "at"}` in the same save, unless that execution is already in `verdicts[key]` (bounded, last 32). The
  bounded display list (live.py VERDICT_LIMIT 8) does not bound the feed. Example: ten verdicts with no handled turn
  -> ten verdict events pending.
- C4 Read and acknowledge: `feed.pending(authority, limit=50)` returns `(the oldest `limit` events with seq >
  handled, the number of pending events after them)`; `([], 0)` without a feed. `feed.handle(authority, seq)` sets
  `handled = max(handled, min(seq, feed seq))`, removes handled events and saves; a stale ack is a no-op. Nothing is
  ever dropped before its ack: the queue is unbounded, only the batch is. Example: pending E1, E2; handle(E2.seq)
  then handle(E1.seq) -> nothing pending, handled = E2.seq; an event appended after the `pending()` read has a
  higher seq and stays pending; 501 events -> pending(limit=50) gives E1..E50 and 451, all 501 readable before
  their ack.

Non-goals (reviewers must not require): any TUI/Controller caller, catch-up and wake-up turns, the owner-first queue
(A6b2); hung-turn cancel, backoff, «архитектор недоступен», stuck rules, autonomy limits (A6b3); provider-error
events; journal.py changes; migrating stores without a feed (A6b2 bootstraps on open).

Risk: high (persisted store schema, every save). DoD: `python3.13 devtools/fasttest.py tests.test_feed tests.test_runs
tests.test_parallel_runs tests.test_terminal_planner tests.test_lifecycle_guard tests.test_toolchain` exit 0; quote
the `fasttest:` lines.
