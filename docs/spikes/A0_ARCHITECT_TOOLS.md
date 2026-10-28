# A0 spike: architect tools through MCP (2026-10-24)

Verdict: **MCP works**; the fenced-block fallback (ARCHITECT_DESIGN.md 4.1) is not needed. Measured on the Mac
(codex-cli 0.162.1, model gpt-6.1-sol, effort low) with devtools/spikes/a0: `mcp_bridge.py` (stdio MCP server, two
tools) forwards each call to `controller_stub.py` (unix socket, a policy gate: `autonomy manual` refuses merge).

| Question | Result |
|---|---|
| Tool call under `exec --json -s read-only -c approval_policy="never"` | refused by Codex: `MCP tool call requires approval, but approval policy is never` |
| Same with `-c mcp_servers.<name>.default_tools_approval_mode="approve"` (values: auto, prompt, writes, approve) | call completes; the bridge reaches the socket outside the sandbox |
| `exec resume <thread> --json -c sandbox_mode="read-only" -c approval_policy="never"` + the same `mcp_servers` flags | same thread id, tool call completes |
| Policy gate refusal | returned as `isError: true` with the reason; the model reports it and stops |
| Sandbox unchanged | `touch x.txt` asked of the model in the same setup: no file created |
| `--json` shape | `item.started` / `item.completed` with `item.type == "mcp_tool_call"`, `server`, `tool`, `arguments`, `result.content[].text`, `error`, `status` (`completed` / `failed`) |
| Engine history reachable | `zeroshot ui --listen 127.0.0.1:PORT`: `GET /ui/api/runs` (runId, phase, terminal, cursor) and `GET /ui/api/runs/<id>/history?after=v2%3A0` -> events `node_started`, `node_completed` (`reference.node`, `outcome.status`, `outcome.diagnostic.message` = verdict text), `token_usage_observed`, `terminal`. Measured on 10.12.0 with a real run (r-b-mediums, 87 events); 10.16.0 serves the same endpoint (host 2, empty store) and `git diff v10.12.0 v10.16.0` changes only tests under profile_ui/ and history.rs |

Consequences for the slices:
- A3b: `architect.py:105`, `:110` replace `mcp_servers={}` with the zplan server and
  `default_tools_approval_mode="approve"` in `build_argv` (`architect.py:95-112`). The MCP
  server is zplan's own process outside the Codex sandbox, so every boundary is zplan code (A3 read rules, the
  Controller policy gate). Re-check once in the curated architect home (plugins off).
- A6a: history events carry no per-event time; the journal stamps start/end on receipt. Reader = the `zeroshot ui`
  HTTP projection (a child process on loopback), not the private run store.

Reproduce (any scratch git dir D, socket S):
`python3 devtools/spikes/a0/controller_stub.py S stub.log &` then
`echo 'Call zplan_status and report the token.' | codex exec --json -s read-only -C D -m MODEL -c 'approval_policy="never"' -c 'mcp_servers.zp.command="python3"' -c 'mcp_servers.zp.args=["devtools/spikes/a0/mcp_bridge.py","S"]' -c 'mcp_servers.zp.default_tools_approval_mode="approve"' -`
-> an `mcp_tool_call` item with `PING-7731`; drop the last `-c` -> the approval refusal.
