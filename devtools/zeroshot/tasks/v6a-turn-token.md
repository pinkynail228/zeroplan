# v6a — every architect request carries the turn that made it, bound at admission

docs/PLAN_UX.md V6 (owner decision Q6), first slice; design and Astra's review in the pause dir
(design/v6-chat-consent.md, design/v6-astra-review.md). Nothing changes consent yet: this task only makes "which
turn asked" a fact the Controller can trust. Today a turn runs Codex with zplan's MCP server built per turn
(`mcp_servers_config`, architect.py:157: argv `--project`, `--controller`); each action tool call sends
`{id, tool, args}` over the socket (`_action`, architect_tools.py:179); the Controller admits it in
`_bridge_request`/`_bridge_action` (tui/controller.py). Turns are serial (`ArchitectChat._turn`, tui/chat.py:879,
owner or event), but a timed-out request's job can still run after its turn ended, so a global "current turn" read
at execution would misattribute it.

Change:
- The Controller mints an unguessable token for each owner turn (`begin_turn(message)` before Codex starts, from
  `_turn` with owner=True only; warm-up, hand-over and event turns get none) and closes it when the turn ends; a chat
  without a Controller (the demo, test fakes) mints nothing and its calls are events.
- The turn's MCP server gets the token in its argv (`--turn TOKEN`, built where `--controller` is); `_action` adds
  `"turn": TOKEN` to the envelope. The model never sees or supplies it.
- At admission the Controller fixes the request's binding once: "owner" when the token is one it minted and still
  open, else "events" (no token, unknown or closed). The binding and, for owner, a reference to the owner's message
  (the turn's own record: its first line, scrubbed, at most 200 characters, and its store occurrence) stay with the
  request; a late job keeps it. zplan_status `requests` show each request's binding.

Write-set: terminal_planner/architect.py, terminal_planner/architect_tools.py, terminal_planner/tui/chat.py,
terminal_planner/tui/controller.py, terminal_planner/bridge.py, tests/test_bridge.py, tests/test_architect_tools.py,
tests/test_architect.py

Acceptance criteria:
- A1 Owner turn. Example: an owner message turn calls zplan_status then zplan_start -> the start's registry entry
  has binding owner and the message reference.
- A2 Not owner. Example: an event turn's call, a call with no token and a call with a forged token -> binding events.
- A3 Late job. Example: a request admitted in owner turn T1 whose job runs after T1 ended and T2 began -> binding
  owner of T1, never T2.
- A4 No consent change. Example: at manual the owner-turn zplan_start still becomes a ConsentRequest.

Non-goals (reviewers must not require): acting on the binding (next task), receipts, new tools, the screen.

Conflict rule: if a test outside the write-set pins the MCP argv or the bridge envelope, change nothing in it and
end with `conflict: <file:line>`.

Risk: medium (architect contract). DoD: `python3.13 devtools/fasttest.py tests.test_bridge tests.test_architect_tools
tests.test_architect tests.test_consent tests.test_tui_chat`: exit 0.
