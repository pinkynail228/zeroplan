A3b — the architect gets the read tools through MCP (RELEASE_0.6.0_PLAN lane T step 3; A0 result:
docs/spikes/A0_ARCHITECT_TOOLS.md).

Why: A0 showed Codex calls a stdio MCP server under `-s read-only` when the server is approved by config. The server
is zplan's own process outside the sandbox, so its code is the boundary: it exposes only A3's read functions.

Reuse: terminal_planner/project_read.py (`list_files`, `read_file`, `search`, unchanged); the framing of
devtools/spikes/a0/mcp_bridge.py; the frozen-interpreter pattern of `checker_command` (runs.py:356); `Blocked`.

Write-set: terminal_planner/architect_tools.py (new), terminal_planner/architect.py, tests/test_architect_tools.py
(new), tests/test_architect.py; terminal_planner/catalog.py and docs/REFERENCE.md only if a new `Blocked` family is
raised (regenerate with `python -m terminal_planner.catalog --write docs/REFERENCE.md`).

Server (`architect_tools.main(argv)`, argv `--project ABS_DIR`): newline-delimited JSON-RPC 2.0 on stdin/stdout.
`initialize` -> `{"protocolVersion": <the client's>, "capabilities": {"tools": {}}, "serverInfo": {"name": "zplan"}}`;
notifications get no reply; `ping`; `tools/list`; `tools/call`. Tools `zplan_list_files {prefix?, root?}`,
`zplan_read_file {path, start?, count?, root?}`, `zplan_search {text, root?}`; `root` defaults to the project.
Result = `{"content": [{"type": "text", "text": <json of the A3 result>}]}`; a `Blocked` -> `isError: true`, text
`<family>: <message>`. Unknown method -> error -32601; bad JSON or a line over 1 MiB -> -32700; the loop goes on.

Acceptance criteria:
- C1 Protocol: driving `main` through a subprocess with initialize, tools/list, tools/call -> three tools listed, each
  with an object `inputSchema`; a read of a tracked file returns its lines. Example: `zplan_read_file {"path": "a.py"}`
  in a temp git repo -> text whose JSON `lines` equals `project_read.read_file` of it.
- C2 Boundary carried: a tool call that A3 refuses comes back `isError: true` with the family, the process keeps
  serving. Example: `zplan_read_file {"path": ".env"}` -> `read.credential: ...`, then `ping` still answers.
- C3 Argv: both `build_argv` forms replace `-c mcp_servers={}` with one inline table
  `mcp_servers={zplan={command=..., args=[...], default_tools_approval_mode="approve"}}` (one `-c`, so no other
  server comes from config); `command` = absolute `sys.executable`, args = `-I -c <code> --project <project>` where
  the code inserts this package's root and calls `architect_tools.main`. Sandbox and approval flags unchanged.
  Example: tests/test_architect.py:138 and :141 updated to the new exact argv; the TOML strings are escaped so a
  project path with a quote or backslash parses (a test with such a path).
- C4 Preamble: `build_preamble` names the three tools and says there are no write tools; the "read-only" and owner-key
  rules stay. Example: the preamble contains `zplan_read_file` and still contains "read-only".

Non-goals (reviewers must not require): mutation tools, the Controller socket, the autonomy gate (A5t); running a real
Codex (the orchestrator checks that live after the run); a `.zplan/STATE.md` tool (A8); MCP resources or prompts.

Risk: high (the architect's sandbox boundary). DoD: `python3.13 devtools/fasttest.py tests.test_architect
tests.test_architect_tools tests.test_project_read tests.test_architect_home tests.test_toolchain
tests.test_reference` exit 0; quote the `fasttest:` lines.
