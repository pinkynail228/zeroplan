# Agent environment out of the box (0.5)

Status: 2026-10-18; critic agent-env-plan (session 01a1488f, xhigh) GO WITH CHANGES, applied below. Nothing moves into
0.4.0: no concrete product failure is shown, and the large DeepSeek apps tax is already removed in devtools.
Owner request: zplan sets up the agents it launches optimally out of the box (context, prompt caching, settings), so an
owner pays no hidden token tax and gets no stray tools.
Data: ~/zs-pause/agent-env-study (REPORT.md; cache/scan2.py + sessions2.csv; cache/first.py); STATE Open "Agent environment".

## Measured (Codex 0.162.1, Zeroshot 10.12.0)

Method (scan2.py):
- One request is a `token_count` event whose cumulative `total_token_usage` changed; repeats are dropped (the first
  scan.py double-counted 27.5M / 13.6M input).
- The cohort is sessions started on or after 2026-10-14 (session_meta timestamp) in ~/.codex and the curated home.
- Provider `gateway` means Zeroshot DeepSeek workers only (direct probes use other provider names).
- Percentiles use `statistics.quantiles(n=10, method="inclusive")`.

| Fact | Number |
|---|---|
| Cache-read share, DeepSeek workers (157 sessions, 19434 requests, 3159M input) | 95.11% |
| Cache-read share, gpt-6.1-sol (747 sessions) | 94.62% |
| Requests per DeepSeek worker session, p10/p50/p90 | 19 / 78 / 253 |
| Input per request, DeepSeek worker, median of session means (mostly apps on) | 154K |
| DeepSeek worker sessions with a compaction | 51 / 157 |
| Turn-1 input, DeepSeek: ~/.codex with apps / apps off / curated home | 94.8K / 21.9K / 9.5K |
| Turn-1 input, sol: apps on / apps off / curated home | 18.2K / 17.9K / 13.8K (apps -0.4K; whole curated profile -4.4K vs the owner home) |
| Turn-1 input, DeepSeek in the curated home, one feature off (base 9.5K) | multi_agent -2.3K, goals -0.7K; image_generation, browser_use, computer_use, plugins, tool_suggest, sleep_tool: ~0 |
| Smoke run 01a15063 (curated home) | worker turn 1 11.6K vs 97.9K in the ~/.codex run 01a15047 |

Conclusions (only what the data shows):
- Cache-read is high on both lanes. An unneeded prefix still raises billed input and context use on every request, even
  at a high cache-read share. Whether misses matter in money depends on the provider's prices; that is not measured.
- Not measured: the effect on caching of the adapter's request rewrites (model alias; `text.format` removed or `strict`
  set false, yandex_adapter.py:75-117), and what the cache is keyed on. Compaction is observed, but not shown to be caused
  by the prefix.
- The large tax came from the owner's account config (apps on the gateway lane), not from zplan or Zeroshot. It reached
  agents because zplan runs them in the owner's own `~/.codex` by default (setup.py:209-215). On the OpenAI lane apps
  cost 0.4K per turn.

## What a client can set (upstream bb84bf7)

- Native runs: the engine fixes the Codex argv (model, provider, effort, output schema, and the bypass flag when the
  policy is unset or the run is hosted, codex/permissions.rs:32-62). There is no args/config passthrough. Everything
  else comes from `CODEX_HOME/config.toml` (from the `zeroshot run` process env).
- Runtime plan per node: `model`, `effort`, `sessionScope`, `lane`, `connections` (env names; CODEX_HOME, HOME, PATH,
  TMPDIR, CLAUDE_CONFIG_DIR reserved).
- Architect: zplan launches Codex itself and already passes `-s read-only`, `sandbox_mode`, `approval_policy` as
  `-c` flags (architect.py:95-100). It stays read-only whatever the profile says.
- The engine adds no system prompt. Prompt order: header -> instructions -> static guidance -> input JSON (varies) ->
  static contract -> trailer (runner/response.rs:468-488).

## Design: zplan owns the agent home

1. **Default home.** New native runs, new architect threads and `zplan login` use `private_codex_home()`
   (data_root()/codex-home). An explicit `$CODEX_HOME` is an expert override, shown by doctor as "your home, not zplan's
   profile". zplan never rewrites profile or backup files under an explicit CODEX_HOME. Codex may write its own
   authentication and session state there.
2. **Recovery contract.** Session records do not store their home today (architect session architect.py:529; run
   binding engine.py:568). From 0.5:
   - each architect session and each native run/planning binding records the `CODEX_HOME` it started in;
   - resume, recovery and an architect continuation use the recorded home;
   - a record from before 0.5 (no home) keeps `codex_home()` as it resolves today (`$CODEX_HOME` or ~/.codex);
   - an architect thread whose home is gone or not logged in is a refusal with an explicit rollover ("new thread"),
     never a silent switch.
3. **Profile.** The package carries a versioned `agent_profile.toml`. zplan writes it as `config.toml` into its own home
   only, on a missing file or a version change, keeping `config.toml.bak`. Decision table:

   | Setting | Value | Why |
   |---|---|---|
   | features.apps, hooks, plugins | off | the 73K gateway tax; account/user tooling outside the run's review |
   | features.multi_agent | off | unreviewed subagent fan-out; 2.3K/turn |
   | features.goals | off | not used by zplan's prompts; 0.7K/turn |
   | approval_policy / sandbox_mode | "never" / "danger-full-access" | today's local behaviour, explicit (no bypass flag added); qualify writes, git, subprocess, network |
   | cli_auth_credentials_store | "file" | login in this home only |
   | mcp_servers, global AGENTS.md | none | no owner tools/instructions in agents |
   | features.memories | off | one zplan home serves every project: agents must not carry context from earlier sessions or other projects, and reviewers judge only the diff and the criteria |
   | history | inherit Codex default, re-check | not measured |
   | web_search, tool output limits, project_doc_max_bytes | inherit | do not cut docs/web without qualification |
   | reasoning summary / verbosity | inherit | cost effect not measured |
   | model_auto_compact_token_limit | inherit | no shared threshold without qualification |
   | shell_environment_policy | inherit | workers need toolchain and provider variables |

   Project AGENTS.md stays (Codex loads it from the worktree). Undeclared capabilities are not inherited (critic
   rel05-scope): the agent-home task fixes the precedence for skills from ~/.agents or /etc/codex and for trusted
   project config, and keeps those sources out of the agent's view where Codex allows it. Where Codex does not allow
   it, zplan refuses or warns: never a silent pass. zplan never edits project config. Project hooks/skills a project
   really needs get an explicit, declared path.
4. **Login.** `zplan login` logs into the zplan home (device auth, as today). If the zplan home has no login, doctor offers
   `[l]`, taking the active env/API-key auth into account (no `[l]` when a provider key variable already serves). With no
   override or legacy continuation, ~/.codex remains byte-identical. Explicit overrides and legacy continuations may use
   it; zplan itself never reads, copies or prints credential contents.
5. **Session scopes (unchanged, documented so nobody "optimises" them away):**

   | Node | Scope | Source |
   |---|---|---|
   | milestone worker | `node_instance` (one thread per worker node instance: the cache persists across repair visits) | milestone.py:505 |
   | milestone reviewers, steward | `execution` (independent fresh review) | milestone.py:505 |
   | planner, plan critic (v2) | `node_instance` | engine.py:484-488 |
   | legacy plan verifier | `execution` | engine.py:497-500 |
6. **Doctor (no model request).** Shows the written profile version and the effective configuration separately: drift is
   an expected key missing or a forbidden one present (`mcp_servers`, `[apps]`, hooks), and skills/project config add
   tools. Also shows the home, the login file present, and an override in use. Drift is a warning, never a block.
7. **Telemetry.**
   - Native runs: the run end and run log show the engine's aggregate `tokenUsage` (input, cache-read share, output;
     authority.py:881 validates it). Missing, incomplete or zero usage reads "нет данных", never 0%.
   - The architect: its own turn usage (Codex `--json` turn events).
   - No alarm thresholds until a per provider/model/effort baseline with enough samples exists.
8. **Probe on every Codex bump (devtools).** A fixed workload is run per provider/model/effort in a fresh, isolated home.
   Each toggle gets its own session id, recorded with the config hash and the result, and the rollout is read by that
   id (not by "newest matching cwd", as first.py did). The probe is a step of the tool-bump qualification. The gateway
   lane needs its adapter auth set up.

Out of scope / later:
- the Claude lane: a curated `CLAUDE_CONFIG_DIR` needs its own login and qualification (keychain on macOS);
- prompt order (the static contract after the variable input): an upstream issue, filed only with the owner's go;
- the adapter's rewrites: measure their cache effect before changing the shared adapter.

## Risks

- A feature turned off may be needed later: the profile is versioned and shown by doctor. Re-enabling is a profile
  change with a probe.
- Two logins (owner ~/.codex and the zplan home), accepted for isolation (critic agent-env-scope option (a)).
- Codex renames a feature key: an unknown key is ignored, and the bump probe catches the lost setting.

## Tasks and acceptance (0.5)

Split into three tasks, in this order (critic s2-task 01a150e9-43d9-7da2-ac3a-3948c0e033ef):
- **s2a-home-binding** (recorded home on every binding and architect thread; every recovery path uses it; architect
  read-only refusal): ~400-550 lines with tests.
- **s2b-agent-profile** (default zplan home + versioned profile + login + shared auth rule + doctor drift/sources;
  Linux suppression qualification with positive controls): ~500-700 lines.
- **s2c-agent-usage** (planner and milestone usage display + isolated single-worker devtools probe and baseline
  check): ~350-500 lines.
Task files: devtools/zeroshot/tasks/s2a-home-binding.md, s2b-agent-profile.md, s2c-agent-usage.md.

Acceptance:
- Fresh install: `zplan login` -> run -> worker turn 1 within 1.2x of the recorded baseline for that
  provider/model/effort/workload/config hash. Installed check, read from the run's own session ids.
- Every launch path (milestone run, planning, architect, resume, recovery, repair visit) uses the recorded home; a
  pre-0.5 record keeps its home; restart mid-run resumes in the same home.
- The architect stays read-only under the profile, and under a home that sets `danger-full-access`.
- zplan never rewrites profile or backup files under an explicit CODEX_HOME; Codex may write its own authentication and
  session state there. Reinstall and a profile version upgrade keep `.bak`. Seeded drift (`[mcp_servers.x]`)
  -> doctor warning.
- With no override or legacy continuation, ~/.codex remains byte-identical. Explicit overrides and legacy continuations
  may use it; zplan itself never reads, copies or prints credential contents.
- Tests fail when the profile key set, the scope table, the home recording or the doctor drift rule is broken.
