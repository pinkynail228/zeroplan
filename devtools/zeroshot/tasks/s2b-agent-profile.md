s2b-agent-profile — 0.5 item S2, part 2 of 3 (docs/RELEASE_0.5_SCOPE.md S2; docs/AGENT_ENV_PLAN.md design 1, 3, 4, 6). Fresh implicit launches and `zplan login` use zplan's own Codex home, data_root()/codex-home, with a versioned packaged profile. zplan never writes its profile under an explicit `$CODEX_HOME` (an expert override). Undeclared skills, tools and config layers are never passed silently: the profile sets candidate suppression keys, and doctor reports every existing source as a warning until Linux qualification proves suppression. DeepSeek worker, sol reviewers.

Base: main with s2a-home-binding merged, which itself sits after the 0.4.0 tag with S4 and S5a merged. Record the base commit in the receipt. This part reuses S5a's warn severity (disk-guard R-4: a warning keeps ok=True, doctor prints WARN and exits 0 when warnings are the only issue). If that severity is not on the base, stop and report: it is a base requirement, not part of this task.

Observed (verified on the tree at 19d1b8e; re-check the line numbers on the base):
- The default home is `$CODEX_HOME` or ~/.codex (setup.py:209-215). The account apps of the owner's ~/.codex added ~73K input per DeepSeek turn (AGENT_ENV_PLAN Measured; turn 1: 94.8K vs 9.5K in a curated home). `private_codex_home()` exists (setup.py:218-219) but is only an opt-in (README.md:65-68, docs/INSTALLATION.md:65-67, :86, docs/USER_FLOW.md:239-240, :418-420).
- `zplan login` logs into the effective home (setup.py:236-241). Help text: commands.py:48-53. Doctor home/auth items: setup.py:476-510. Doctor output: setup.py:565-582. Chat preparation checks auth on its own (tui/chat.py:280-287). Catalog: catalog.py:120-138.
- The devtools precedent is the curated home that devtools/zeroshot/run.sh:30-34 exports. Its config sets cli_auth_credentials_store="file", approval_policy="never", sandbox_mode="danger-full-access", and features apps=false, hooks=false. It also trusts this repository under [projects], which the product profile must not copy. The product must not reference that path or this repository.
- Unverified for Codex 0.162.1: the pinned binary's config-schema strings name `[skills]` with `include_instructions`, `bundled` (BundledSkillsConfig) and `config` (per-skill entries), plus the paths `.agents/skills`, /etc/codex/config.toml, /etc/codex/managed_config.toml and /etc/codex/requirements.toml. Strings do not prove behavior. Whether these keys suppress skills, and whether a project `.codex/config.toml` applies under `danger-full-access` with a home that trusts no project, are open until the A-9 qualification. Upstream sets HOME for the Codex child to the owner's home, and HOME is reserved (upstream native_v2_codex/command.rs:19-37), so `~/.agents` stays reachable.
- Package data ships only resources/*.json (pyproject.toml:19-20).

Read:
- docs/AGENT_ENV_PLAN.md :52-99 and :115-137 (design, decision table, risks, acceptance);
- setup.py :25-40, :209-241, :400-440 (`read_toml`, `codex_provider`), :455-582 (readiness, doctor);
- cli.py :920-975; commands.py :40-60; catalog.py :115-140; tui/chat.py :244-289; planning.py:34 (TOOL_CHECKS);
- the s2a changes (`legacy_codex_home`, the binding `codex_home`, `architect.home_lost`);
- README.md, docs/INSTALLATION.md, docs/USER_FLOW.md (the CODEX_HOME passages above), docs/REFERENCE.md, and the tests of each.

Rules:
- R-1 Default home. `setup.agent_home(env)` = the nonempty `CODEX_HOME` of `env` (an override), else `private_codex_home()`.
  - `setup.native_environment()` sets CODEX_HOME to `agent_home(os.environ)`. Login, doctor, every new native run and planning revision, and every new architect thread therefore use it.
  - Records from s2a keep their recorded home. Pre-0.5 records keep `legacy_codex_home()`.
  - `codex_home(env)` (the home of an env) is unchanged.
  - Production code names no other home path. Explicit overrides and legacy continuations may use ~/.codex; no fresh implicit launch uses it. zplan never writes into ~/.codex itself and never reads credentials from it.
- R-2 Profile resource. `terminal_planner/resources/agent_profile.toml`, added to package data. Its first line is exactly `# zplan-agent-profile: <N>`, where N is a positive ASCII integer starting at 1. Its keys are the AGENT_ENV_PLAN decision table (:65-79), and nothing for the "inherit" rows:
  - top-level `approval_policy = "never"`, `sandbox_mode = "danger-full-access"`, `cli_auth_credentials_store = "file"`;
  - `[features]` `apps = false`, `hooks = false`, `plugins = false`, `multi_agent = false`, `goals = false`;
  - candidate suppression keys, whose effect is unproven until A-9: `[skills]` `include_instructions = false`, and `[skills.bundled]` `enabled = false`;
  - no `mcp_servers`, `projects`, `profile`, `profiles`, `apps`, `hooks` or `plugins` tables.
  One module constant holds the expected key set. A test pins it to the file, so adding, removing or changing a key fails a test.
- R-3 Profile write (lifecycle). zplan creates or replaces profile and backup files only under `private_codex_home()`, and never under an explicit override. Codex's own login and execution may write their auth and session state into whichever home they run in. The write runs inside `native_environment()` and login, when no override is set. Doctor never writes. Classification, backup and replacement are serialized by a per-home lock file. Lifecycle states of config.toml:
  - absent: create the home (mode 0700 when new) and write the profile;
  - present with a first line naming the current N: untouched, even if edited (that is drift, R-5);
  - present with another N, no marker, or undecodable bytes: copy it to `config.toml.bak`, replacing an older .bak, then write the profile. The per-home lock is non-blocking: a second writer gets `setup.agent_home` (busy, remedy: retry); after the first writer releases, a retry finds the current N and does nothing, so .bak keeps the original pre-upgrade config (critic gate7 A);
  - the write is atomic (a temp file in the same directory, then os.replace). For a symlinked config.toml, the link itself is backed up without following it (.bak becomes a symlink with the same target), and then the link is replaced. The link target is never written;
  - an OSError refuses the launch or login with a new family `setup.agent_home` naming the path. No temp file or partial file is left.
- R-4 Auth presence (one rule). One provider-aware auth-presence function is used by doctor, chat preparation (`default_prepare`), and the s2a architect-continuation check (`architect.home_lost`). It is evaluated against the selected home and the child environment:
  - file auth is served by `<home>/auth.json` being a file, or by a nonempty `CODEX_API_KEY` or `OPENAI_API_KEY` (the engine copies OPENAI_API_KEY to CODEX_API_KEY for a local user, upstream native_v2_codex/command.rs:84-100);
  - env-key auth is served by its nonempty variable;
  - an empty variable counts as unset, with one exception: an existing empty `CODEX_API_KEY` blocks the OPENAI_API_KEY fallback, because upstream copies OPENAI only when CODEX_API_KEY is absent (command.rs:94; critic gate10; s2b2 R-4);
  - values are never printed.
  `[l]` is offered only when file auth is unserved. `zplan login` runs in `agent_home(os.environ)` after R-3. zplan never copies, reads or prints credential files. Help and docs say: the zplan home by default; `CODEX_HOME=... zplan login` for an override.
- R-5 Doctor (no model request, no writes). Items:
  - `agent_home`: the path, and either "zplan" or "your $CODEX_HOME, not zplan's profile".
  - `agent_profile`, zplan home only: the written N vs the packaged N, or "not written yet (written at login or first launch)".
  - `agent_drift`: one WARN per finding, checked against the effective home's config.toml for both zplan and override homes. A finding is one of:
    - an expected key (R-2 set) that is missing or has another value;
    - a forbidden table present: `mcp_servers` (nonempty), `apps`, `hooks`, `plugins`, `projects`, `profile`, `profiles`;
    - a global `AGENTS.md` or `AGENTS.override.md` in the home.
  - `agent_sources`: one WARN for each existing source, whatever the profile says, until A-9 proves suppression for the pinned version:
    - each existing /etc/codex/{config.toml, managed_config.toml, requirements.toml};
    - nonempty `$HOME/.agents/skills`, `<home>/skills`, `/etc/codex/skills`, or the target's `.agents/skills`;
    - a target project `.codex/` directory, as "may apply to agents (not verified for this launch mode)". For an override home, a `[projects]` trust entry is never treated as absent.
    The /etc root and HOME are module-level values that tests replace.
  Drift and sources are warnings, never blocks; they never gate plan/start checks. The existing auth/codex_home items keep their meaning for the effective home. zplan never edits project config. Doctor never says "hidden" or "not loaded".
- R-6 Precedence table (in the module docstring and docs/INSTALLATION.md). It describes Codex 0.162.1 as qualified by A-9, with every unverified row marked "unknown", and it separates two mechanisms:
  - constraints: /etc/codex/requirements.toml (enforced requirements) and managed config;
  - value layers: CLI flags zplan or the engine pass > trusted project `.codex/config.toml` > the home's config.toml (the profile) > /etc/codex/config.toml (system defaults). This follows the documented Codex order; the trusted-project row stays "unknown for this launch mode" until A-9.
  - skills sources (HOME, the home, /etc, project): "unknown" until A-9.
  This general documentation is not a substitute for qualifying the pinned binary. The project AGENTS.md stays. A project's declared skills or hooks path is not part of this task.
- R-7 Text: catalog families `setup.agent_home`, `readiness.agent_drift` and `readiness.agent_sources`, with REFERENCE regenerated. Update README.md, docs/INSTALLATION.md, docs/USER_FLOW.md and commands.py so the opt-in wording becomes the default. Two logins are accepted (owner ~/.codex vs the zplan home): say so once in INSTALLATION.

Acceptance criteria (temporary HOME, XDG_DATA_HOME and /etc root; no network, no real Codex or provider):
- A-1 Profile: the packaged file parses, its marker is line 1, and its key set equals the constant. A missing or changed key in the file or the constant fails the pinned test.
- A-2 Write lifecycle:
  - absent -> written (home 0700);
  - same N edited -> untouched;
  - N-1, no marker, or binary garbage -> .bak equals the old bytes and config is the profile; an existing .bak is replaced;
  - reinstall (a second ensure with the same N) changes nothing, and .bak is kept;
  - symlink: .bak is a link to the same target, the target stays byte-identical, and config.toml is a regular file;
  - a forced OSError leaves no temp file and gives setup.agent_home;
  - concurrency (deterministic, two writers upgrading N-1): Synchronize both writers before lock acquisition. Pause writer 1 inside the critical section with an Event; writer 2 gets `setup.agent_home` (busy) without writing. Release writer 1; writer 2 retries and finds the current N. .bak contains the original N-1 bytes, config contains the current profile, and no temp file remains (critic gate7 A).
- A-3 Override: with CODEX_HOME=X, zplan creates or replaces no profile/backup file under X or the private home on login (spy), doctor or a launch. New launches spawn with CODEX_HOME=X. Doctor says "your $CODEX_HOME". CODEX_HOME="" counts as unset.
- A-4 Fresh implicit launches never use ~/.codex. With a seeded ~/.codex tree (config with apps on, auth.json) and no override: env setup, login (spy), doctor, a planning prepare and an attempt start spawn nothing with CODEX_HOME=~/.codex, and zplan's own code writes nothing there (byte-identical hash; the spies replace Codex). With CODEX_HOME=~/.codex set explicitly, launches use it, and zplan writes no profile there.
- A-5 Doctor: a seeded `[mcp_servers.x]` gives a WARN with exit 0; a missing `features.apps` gives a WARN; `[projects."/p"]` gives a WARN; the clean profile gives no agent_drift WARN. Sources: a seeded /etc/codex/managed_config.toml gives a WARN. A seeded ~/.agents/skills/s/SKILL.md gives a WARN under the profile too. A target `.codex/config.toml` gives the "may apply" WARN. No doctor line contains "hidden" or "not loaded". Doctor spawns no model process (spy).
- A-6 Auth: device-auth argv runs with CODEX_HOME = the private home. For each of four cases (file auth with auth.json; env-key auth with the variable set; an empty variable; no variable and no auth.json), doctor, `default_prepare` and the architect continuation give the same verdict. `[l]` appears only when file auth is unserved. Values are never printed.
- A-7 End-to-end with s2a: a fresh install records codex_home = the private home on a new attempt and a new architect thread. A pre-0.5 record still spawns with legacy_codex_home(), and an s2a record with its recorded home.
- A-8 Regressions: production-entry regression tests must reach the intended behavioral assertion on the named base (s2a merged). New-helper unit tests are excluded from base replay and covered by targeted mutations. Imports and fixtures must stay compatible with the replay base. Mutations: drop a profile key; write under an override; skip .bak; drop the lock; drop the mcp_servers rule; skip the skills WARN under the profile. Record the commands and the base failures. The existing readiness/doctor tests stay green, updated only where the default-home wording changed.
- A-9 Qualification (orchestrator, Linux test host, not the worker). Every suppression check has a positive control: without the restriction, the seeded item really appears; with it, it does not.
  - Skills: a seeded ~/.agents skill, a home skill and a project `.agents/skills` skill. Read the turn-1 instructions of a native worker and of an architect turn, with and without the R-2 skills keys.
  - Project config: a target `.codex/config.toml` that adds a test MCP server. Launch a native worker and an architect, in the zplan home (no trust) and in a home that trusts the project.
  - Native permissions under the profile: the worker can write files, run git, start a subprocess and reach a controlled local network endpoint.
  - Record the commands and results. Where suppression is not shown, the doctor WARN stays and the docs say "unknown"; no isolation claim is made. Update the R-6 table only from these results. The turn-1 performance comparison is in s2c A-5.

Size: ~500-700 added lines with tests and docs. Above the 500-line soft trigger; kept together because the default home, the profile lifecycle, the shared auth rule and doctor form one contract that is qualified once (critic s2-task).
Out of scope: run usage display and the devtools probe (s2c); the Claude lane home; declared project skills/hooks paths; migrating or copying an existing login; devtools/zeroshot/run.sh; S3 lanes.
critic s2-task: round 2 GO WITH CHANGES, applied; round 3 confirmed (session 01a150e9-43d9-7da2-ac3a-3948c0e033ef)
