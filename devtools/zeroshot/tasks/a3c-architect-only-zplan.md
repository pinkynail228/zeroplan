A3c — the architect sees no MCP server but zplan's (RELEASE_0.6.0_PLAN lane T, security fix before A6a).

Why: measured 2026-10-25 with Codex 0.162.1: `-c mcp_servers={...}` merges into the owner's config, it does not
replace it, so an architect turn starts every server of the owner's CODEX_HOME and its plugins. A live turn called
`node_repl.js` (code execution outside the read-only sandbox) and it completed. Measured fix:
`-c features.plugins=false` drops plugin servers, and `name={enabled=false}` for each configured server inside the
same inline table turns it off; `codex mcp list --json` (0.1 s; JSON list of `{name, enabled, ...}`) reports the
result under the same `-c` overrides and env.

Reuse: `mcp_servers_config`, `_toml_string`, `build_argv`, `verify_cli`/`REQUIRED_HELP` in
terminal_planner/architect.py; `Blocked`.

Write-set: terminal_planner/architect.py, terminal_planner/catalog.py, docs/REFERENCE.md (regenerate:
`python -m terminal_planner.catalog --write docs/REFERENCE.md`), tests/test_architect.py, tests/test_tui_chat.py,
tests/test_tui_chat_scroll.py, tests/test_architect_home.py, tests/test_agent_activation.py.

Acceptance criteria:
- C1 Disable: before each turn (new and resumed), in the turn's env, `codex mcp list --json -c features.plugins=false`
  gives the enabled names; the turn's argv carries `-c features.plugins=false` and one inline table with `zplan` plus
  `<name>={enabled=false}` for each of them other than `zplan` (keys TOML-quoted). Example: a listing of
  `node_repl` and `context-mode` enabled -> both appear with `enabled=false` in the turn's `-c` value.
- C2 Fail closed: then `codex mcp list --json` with the turn's final overrides must show exactly `zplan` enabled;
  anything else, a non-zero exit, a timeout (10 s) or unparsable JSON -> `Blocked` family
  `architect.foreign_tools` naming the servers, and no turn process starts. Example: the second listing still shows
  `node_repl` enabled -> refusal naming `node_repl`; the store and transcript stay byte-identical.
- C3 Fixtures: every fake codex answers `mcp list --json` without counting it as a turn call (default: `zplan`
  enabled only; a scenario key overrides it), so existing turn tests keep their call indexes. `REQUIRED_HELP` gains
  `("mcp", "list"): ("--json", "--config")`. Example: the existing test_architect turn tests pass unchanged apart
  from the expected argv.

Joint example (C1+C2): first listing `node_repl` enabled; second listing (with `node_repl={enabled=false}`) only
`zplan` -> the turn runs with that argv.

Non-goals (reviewers must not require): a separate CODEX_HOME for the architect; `--ignore-user-config` (it drops
the owner's provider settings); servers of other agents (planner, workers); running a real Codex (the orchestrator
checks it live after the run).

Risk: high (the architect's sandbox boundary). DoD: `python3.13 devtools/fasttest.py tests.test_architect
tests.test_architect_home tests.test_agent_activation tests.test_tui_chat tests.test_tui_chat_scroll
tests.test_reference tests.test_toolchain` exit 0; quote the `fasttest:` lines.
