A6a — the project journal: engine history reader and duration-stamped steps (RELEASE_0.6.0_PLAN lane T step 4;
ARCHITECT_DESIGN.md section 9; docs/spikes/A0_ARCHITECT_TOOLS.md:15, :22).

Why: the owner asks "what was, what is, how long" (Q5); the engine already serves run history over `zeroshot ui`.
Measured 2026-10-25: `zeroshot ui --listen 127.0.0.1:0` prints `Zeroshot UI: http://127.0.0.1:PORT/ui/`
to stderr; `GET /ui/api/runs` -> `{"runs": [{"runId", "phase", "terminal", "cursor", "createdAt"(ms)}], "nextCursor"}`;
`GET /ui/api/runs/<id>/history?after=v2%3A0` -> `{"events": [{"cursor", "event"}], "nextCursor", "complete", ...}`;
unknown id -> 404. Event kinds: `node_started` (`reference.execution`, `reference.node`), `node_completed`
(`completion.reference`, `completion.outcome.status`, `.diagnostic.message`), `token_usage_observed` (`execution`,
`usage`), `safe_log` (`timestamp` ms, `execution`), `terminal` (`result.status`). Only `safe_log`
carries time.

Reuse: `NativeEngine.executable`, `NativeEngine.native_environment` (engine.py:1051, :1102); `live.scrub`; `Blocked`.

Write-set: terminal_planner/journal.py (new), tests/test_journal.py (new), terminal_planner/catalog.py,
docs/REFERENCE.md (regenerate: `python -m terminal_planner.catalog --write docs/REFERENCE.md`).

Acceptance criteria:
- C1 Reader: `Reader(engine)` (context manager) starts `[executable, "ui", "--listen", "127.0.0.1:0"]` in the
  engine's env (stdin/stdout devnull, new session), takes the origin from that stderr line within 10 s;
  `runs()` and `history(run_id, after="v2:0")` follow `nextCursor` until `complete` (at most 50 pages); exit
  terminates the child (kill after 5 s). No line, HTTP error, bad JSON -> `Blocked` `journal.history_unavailable`.
  Example: a fake `zeroshot` script in the test serving two pages -> `history` returns all their events in order.
- C2 Steps: `steps(events)` (pure) -> one step per execution `{"execution", "node", "start", "end", "duration",
  "status", "verdict", "tokens"}`; start/end = the latest `safe_log` timestamp at or before the started/completed
  event (None if none); duration = end - start in seconds; verdict = first line of the diagnostic, scrubbed, ≤200
  chars; tokens = summed input+output of that execution. Example: the A3c shape (worker 1, acceptance 2, code 3) ->
  three steps, worker `status` "verified".
- C3 Store: `append(path, entry)` adds one JSON line stamped `at` (ISO UTC on receipt); `load(path)` reads them
  back, skipping a torn last line. Kinds: `step`, `action`, `learning` (`cause`, `defect`, `fix`). Example: append
  a learning record, a torn line -> `load` returns the one record.

Non-goals (reviewers must not require): calling the journal from the Controller, the TUI or runs (A5t/A6b/A10);
SSE events endpoint; reading the private run store; a real `zeroshot` in unit tests.

Risk: medium (a child process; Linux + driver_qual at merge). DoD: `python3.13 devtools/fasttest.py
tests.test_journal tests.test_reference tests.test_toolchain` exit 0; quote the `fasttest:` lines.
