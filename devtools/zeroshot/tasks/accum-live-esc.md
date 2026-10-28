accum-live-esc — repair of accum-live (critic accum merge: NO-MERGE, blocker 1). Runs on the existing worktree /tmp/zs-zplan/accum-live (branch zs-accum-live, HEAD 0cb2d1e). The task devtools/zeroshot/tasks/accum-live.md and its ACs L-1..L-5 still apply. DeepSeek worker, sol xhigh reviewers. Read AGENTS.md, terminal_planner/live.py (`tail`, `SECRET`, `QUOTED_KEY` ~305, `CREDENTIAL`, `scrub`), tests/test_live.py, and how Zeroshot 10.12 writes log records (upstream/ source: NDJSON log events whose `message` carries the original text, so its quotes arrive escaped).

Defect (invariant: no credential value is ever shown). `QUOTED_KEY` and `CREDENTIAL` do not handle a field that sits inside a JSON string of an NDJSON log record, where its quotes arrive escaped. The critic reproduced both cases through the real `live.tail()`:
- `json.dumps({"message": '{"api_key":"SYNTHETIC_CREDENTIAL_012345"}'})`: the value stays fully visible;
- `json.dumps({"message": 'api_key="a b SECRET_END"'})`: only the start of the value is masked (`api_key=[скрыто] b SECRET_END`).

Change: choose the smaller sound fix and say why. Either
- (a) scrub the decoded text: when a tail line is a JSON record, mask the credential fields inside its decoded string values and show the line built from the masked values, never the raw one; or
- (b) make the patterns handle escaped quotes, i.e. `\"key\":\"value\"` and `key=\"a b\"` at any nesting depth.

No credential value may remain visible at any nesting depth: a doubly escaped field (a JSON string inside a JSON string inside the record) is masked too. Keep scrub linear, keep the partial-first-line drop, keep everything that already passes.

Acceptance criteria:
- E-1 Tests through `scrub` and through the full `live.tail()` reader (popen fixture) cover both critic cases, a doubly escaped case, and the plain shapes of L-1. No part of a value appears in the output. Each new test fails on 0cb2d1e (say how you checked).
- E-1b A truncated last NDJSON line: take both critic cases and strip the closing characters of the outer JSON, so the credential stays inside. `tail()` shows such a partial last line; a JSON-decoding fix must not fall back to the old regex and expose the value. The output is safe, with no raw potentially secret payload.
- E-2b Depth limit and decode errors: processing is bounded, nothing raises out of scrub/tail, and nothing leaks. Past a set depth limit, hiding the whole record (or the rest of the line) is allowed and is the expected safe result; a deeply nested test case covers it. "Any nesting depth" above means this: masked or hidden, never shown, without an unbounded recursive decoder.
- E-2 A complexity test: a long line of escaped quotes and backslashes, and a long NDJSON record, both finish in bounded time (keep the style of the existing perf tests).
- E-3 All L-1..L-5 tests stay green, plus the targeted modules (tests.test_live, tests.test_tui_live, tests.test_tui_milestones, tests of runs observe). The full suites are the orchestrator's merge gate.
- E-4 The diff on top of 0cb2d1e touches only terminal_planner/live.py and tests/.

critic accum (session 01a14651-23d9-76b1-aaf7-200692ca4081): task CHANGE (truncated NDJSON, depth/decode limit) -> applied (E-1b, E-2b) -> GO.

Merge (candidate 7f6e898): Linux full 675 OK, macOS full 675 OK (skip 1); critic accum merge2: MERGE (nice-to-haves: empty head at live.py:464 masked, tests for \u0000/HOLD forgery, comment at live.py:333).
