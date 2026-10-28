A5t1 — the architect reaches the live Controller: socket bridge, status, start and stop tools, autonomy policy
(RELEASE_0.6.0_PLAN step 5 lane T, split; ARCHITECT_DESIGN.md section 4 decisions 1 and 3). Plan edit, approve,
merge, resume and re-brief are A5t2 (after A5e, A7b2). Design: ~/zs-pause/critic/a5t-design.out.

Why: the architect has only read tools (architect_tools.py:21); it cannot act, and the store is locked to the live
process (authority.py:381), so its actions must go through that process's Controller and its gates.

Reuse: tui/controller.py `post` :429, `begin_closing` :358, `stop` :371, `_blocked` :654, `preview_start` :660,
`start_run` :670, `stop_run` :790; delivery.py `resolve` :556 (`Changed`); architect_tools.py `serve` :132, `_call`
:54; architect.py `mcp_servers_config` :109, prompt :245; process.py `autonomy.level` :94.

Write-set: terminal_planner/bridge.py (new), terminal_planner/autonomy.py (new), terminal_planner/architect_tools.py,
terminal_planner/architect.py, terminal_planner/tui/controller.py, terminal_planner/tui/chat.py,
terminal_planner/catalog.py, docs/REFERENCE.md, tests/test_bridge.py (new), tests/test_autonomy.py (new),
tests/test_architect_tools.py, tests/test_architect.py, tests/test_reference.py.

Acceptance criteria:
- C1 Socket: the Controller serves AF_UNIX in a fresh 0700 dir under /tmp (path < 100 bytes), removed on stop; one
  JSON line request {id, tool, args} -> one JSON line reply {id, ok} | {id, error: family, message}; bounded read
  and write. An action posts a `mutating=True` job; `post` refusing (closing) -> an immediate refusal; the
  worker's callback sets the Event; the wait is bounded (120 s) -> `architect.controller_timeout` "исход
  неизвестен"; shutdown never joins a request thread from the worker. Example (barriers before/after `post`):
  closing before admission -> refusal, no job; closing after admission -> the job completes, quit waits for it as
  for any admitted job, the bridge adds no wait of its own.
- C2 Tools: `zplan_status`, `zplan_start {milestone, revision}`, `zplan_stop {milestone, run_id}` added to TOOLS;
  the MCP server gets `--controller PATH`; no socket -> `architect.controller_unavailable`. Every tool result,
  error and timeout included, carries the request id. Status replies at once, never waiting for a job: this
  session's request registry (queued, running, done + result; kept after a timeout) plus the rows (approved
  revision, each milestone's state, attempt, run_id) of the last worker snapshot, or `rows unavailable`; a rows
  refresh is queued as a non-mutating job without waiting. Example (worker held by a barrier): a start with id X
  times out -> status returns X `queued` at once; released into the job -> `running`; finished -> `done` with its
  result.
- C3 Freshness: inside one job the Controller refuses with today's `Changed` text when `revision` is not current
  (start) or `run_id` is not the milestone's latest attempt (stop); start runs preview + start in that job and keeps
  the `ProfileChanged` refusal; the policy decision uses the same profile digest. Example: stop with the run_id of
  a finished attempt A while attempt B runs -> refused, B keeps running.
- C4 Policy: `autonomy.decide(level, action) -> "allow" | "ask"`; level from the accepted profile; /1 or unreadable
  -> manual. stop: allow at every level. start: ask at every level while `AUTOMATIC = False` (module constant; the
  release gate: automatic actions stay off until A7 is merged; A5t2 flips it); with it True: auto/supervised
  allow, manual ask. "ask" -> error `autonomy.ask`, message: ask the owner to do it with their key. Order:
  invalid arguments, then C3's stale refusals, then the policy. Example: auto profile, current start ->
  `autonomy.ask`, stale start -> `Changed`; patched True -> the run starts and the TUI row shows it after refresh.
- C5 Text: the prompt lists the tools and says the Controller decides; new families in catalog.py and
  docs/REFERENCE.md. Example: `autonomy.ask` does not render as `unknown_error`.

Non-goals (reviewers must not require): plan edit/approve, merge, resume, re-brief tools (A5t2); a TUI decision
card; journal records of architect actions (A6b); auth tokens; delivery.py, runs.py changes.

Risk: high (new process boundary, lifecycle). DoD: `python3.13 devtools/fasttest.py tests.test_bridge
tests.test_autonomy tests.test_architect_tools tests.test_architect tests.test_reference tests.test_lifecycle_guard tests.test_tui_chat
tests.test_tui_commands tests.test_toolchain` exit 0; quote the `fasttest:` lines. The orchestrator runs a live Codex -> MCP -> socket
smoke on the Mac and, where the pinned CLI is logged in, on Linux.
