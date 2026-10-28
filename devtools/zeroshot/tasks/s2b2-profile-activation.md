s2b2-profile-activation — 0.5 item S2, slice 2 of 3 of devtools/zeroshot/tasks/s2b-agent-profile.md (the parent). Where cited, these apply verbatim:
- the parent's R-1, the R-3 call sites and R-4;
- the parts of R-5 and R-7 named below;
- A-3, A-4, A-6, A-7 and A-8 with the mutations not owned by s2b1 or s2b3.

Coverage map (authoritative for the parent's slices; it supersedes the two-part line s2b1-profile-manager.md:13-16, and s2b1 itself is unchanged):
- s2b1: R-2, R-3 lifecycle, A-1, A-2, the A-8 profile mutations, `setup.agent_home`.
- s2b2:
  - R-1, the R-3 call sites, R-4;
  - R-5 home/profile (the `codex_home` source text and the profile info line);
  - R-7 default-home text;
  - A-3, A-4, A-6, A-7;
  - A-8 mutations a, b, e, f, f2, f3, g, i, j, k.
- s2b3:
  - R-5 drift/sources, R-6;
  - R-7 `readiness.agent_drift`/`agent_sources` and warning text;
  - A-5;
  - A-8 mutations c, d, h, l, m.
- Orchestrator, one gate after s2b3: parent A-9 plus the OPENAI-only architect check (s2b2 R-4b).

Lane: Environment (L1). DeepSeek worker, sol reviewers. Critic gate9 B and gate10: GO WITH CHANGES (applied).

Base: main with s2a2-engine-wiring, s2a3-architect-home and s2b1-profile-manager merged ("activation stays after the whole of s2a", s2b1-profile-manager.md:3). This slice uses s2a3's frozen interface `architect.check_home`/`_auth_present`/`next_home` (s2a3-architect-home.md:15-24). Lines below are cited at main 08fe3e3; its product code equals ac220ec's. That tree has none of `agent_profile.py`, the s2a2 binding wiring or s2a3's `check_home`, so re-check every cited line on the actual base. Record the base and this brief's sha256 in the receipt.
- Stop and report, rather than build them, if the base lacks any of:
  - `agent_profile.ensure`/`written_version`;
  - the `setup.agent_home` family;
  - `architect.check_home` with `_auth_present`;
  - `item(..., severity=)` (s5a1).

Binding note from gate7 A (s2b1-profile-manager.md:49-51):
- `ensure` is called only when `CODEX_HOME` in the process env is unset or empty.
- It is skipped for any non-empty value, including `CODEX_HOME=<private_codex_home()>`.

Write-set (exclusive for this slice):
- setup.py:
  - new `agent_home(env)`, `auth_served(home, auth, env)` and `child_auth_env(env)`;
  - `native_environment` :234-239, which gains a keyword `profile=True`;
  - `login` :242-247;
  - the `codex_home`/`auth` part of `readiness` :503-536;
  - the doctor profile info line, in `doctor` :590-607;
  - the `codex_home` docstring :210-213 (wording only).
- architect.py, two points:
  - `_auth_present` delegates to `setup.auth_served`;
  - the turn env passes through `setup.child_auth_env` (R-4b).
  - `check_home`, `next_home` and the refusal order stay s2a3's.
- tui/chat.py: none expected. After s2a3, `default_prepare` judges auth through `check_home`. Verify on the base, and edit only if a direct auth check remains.
- cli.py: `attach_tools` :960-970 and the status env :1008-1014 (R-3c).
- commands.py: the `login` Command :47-53 text.
- Docs (default-home text only; the warning and precedence text is s2b3's):
  - README.md :66-69, :75, :118;
  - docs/INSTALLATION.md :65-71, :88;
  - docs/USER_FLOW.md :186, :235, :251-252, :437-439.
- Tests:
  - new `tests/test_agent_activation.py`;
  - existing tests in tests/test_setup.py, test_tui_chat.py, test_architect.py, test_ux.py, test_layout.py, test_reference.py, test_install.py, and (amendment 2026-10-20, critic s2b2-exhausted, session 01a15946-07d3-7800-baa6-a514d25094bb: the run exhausted change attempts on this write-set vs R-8 conflict) test_tui_polish.py and test_warn_contract.py for R-8 fixture defaults only:
    - the edits are wording assertions and fixture defaults (an explicit `CODEX_HOME`, a seeded private home, or `auth.json` where the default home moved);
    - assertions are not weakened, there is no test-only bypass, and each edit is listed in the receipt.
  - tests/test_agent_profile.py (s2b1's): only the stale `UnreachedTests` (:339-345 on the s2b1 candidate). Its "agent_profile is referenced only by itself" no longer holds after activation; replace it with "only setup.py and agent_profile.py reference it". Every lifecycle assertion is unchanged.
- The receipt `devtools/zeroshot/tasks/s2b2-profile-activation-receipt.md`.

Not touched:
- catalog.py: no new family here. `setup.agent_home` is s2b1's; the `readiness.agent_*` families are s2b3's.
- docs/REFERENCE.md;
- agent_profile.py;
- engine.py, runs.py, authority.py, delivery.py, process.py, task_gate.py, planning.py, record_home.py, toolchain.py;
- tui/app.py, tui/controller.py;
- tests/test_runs.py, test_lifecycle_guard.py, test_live.py, test_fixture_scope.py, tests/tui_support.py;
- devtools/zeroshot/run.sh.

Parallelism (for the critic):
- s1a1b1: disjoint product and test files → parallel.
- s1a1b2:
  - Its product files (runs/delivery/process/task_gate/catalog/REFERENCE) are disjoint from this slice's.
  - Shared test helpers and assertions, named:
    - s1a1b2 edits profile-binding lines in test_runs, test_lifecycle_guard, test_live, test_fixture_scope and the tui suites. This slice edits none of those files.
    - The only possibly shared files are tests/test_tui_chat.py and test_ux.py, if s1a1b2 binds profiles there. This slice edits only home/auth fixture defaults and home-wording assertions in them. It never edits a `.zeroshot` profile fixture or `tests/tui_support.py`.
    - If this slice needs any other file from s1a1b2's list, it stops and reports.
  - On that basis, parallel.
- s2b3: strictly after this slice (setup.py `readiness`, the same docs).
- Integration: completed candidates only; active workspaces are not rebased. The second integration SHA re-runs the full gates.
- Semantic coupling with s1a1b: none. The gate's `config_digest` is the process profile (`.zeroshot`), not the Codex home profile. The engine env comes from cli.py (s2a2-engine-wiring.md:31).

Audit (08fe3e3):
- Homes:
  - `codex_home(env)` setup.py:209-215;
  - `legacy_codex_home()` :218-221;
  - `private_codex_home()` :224-225;
  - `data_root()` :28-29.
- `native_environment` :234-239 sets CODEX_HOME = `codex_home(env)`. `login` :242-247 calls it, then `mkdir` :245, then device auth.
- `native_environment` callers:
  - cli.py:967 (`attach_tools`, which swallows Blocked/OSError/ValueError :968-970);
  - cli.py:1011 (`status`, which swallows :1013-1014 and builds no agent, only `NativeDriver` reads);
  - tui/chat.py:404 (`default_prepare`);
  - setup.py:243 (`login`).
- Login entry points: cli.py:1003, :1030 and tui/app.py:2955, all through `setup.login`.
- Readiness: the home :503, the source :504, the provider :506. File auth is judged by `auth.json` only (:518-527); env-key auth by `os.environ` (:528).
- Upstream (local checkout v10.11.0; the critic checked v10.12.0:84-98): `configure_openai_auth` native_v2_codex/command.rs:84-98.
  - An existing `CODEX_API_KEY`, even an empty one, short-circuits (:94).
  - Otherwise `OPENAI_API_KEY` is copied to `CODEX_API_KEY` (:97).
  - This holds for the native engine's Codex child only. The architect's direct Popen (architect.py:685-687) gets no such mapping.
- WARN contract: `item(..., severity=)` :256-272; the doctor prefix :599; exit :604-607. Plain start dedups warn lines (cli.py:245-246).

Rules:
- R-1 Default home: parent R-1 verbatim.
  - `agent_home(env)` = `Path(env["CODEX_HOME"]).expanduser().resolve()` when it is non-empty, else `private_codex_home()`.
  - `native_environment` sets CODEX_HOME = `agent_home(os.environ)`.
  - `codex_home(env)` and `legacy_codex_home()` are unchanged; records keep their homes through `record_home`.
  - `readiness` judges `agent_home(os.environ)`.
- R-3c Call sites (parent R-3, gate7 A, gate9 B):
  - Only `native_environment(profile=True)` calls `agent_profile.ensure(private_codex_home())`. It does so exactly when `os.environ.get("CODEX_HOME")` is empty or unset, after `check_installation` and before the env is returned.
  - `login` gets it through its one `native_environment()` call: one `ensure` per login in total, with no direct second call. Under an override, `login` keeps the existing `mkdir` :245.
  - `status` builds its env with `native_environment(profile=False)`: the same env, zero `ensure` and zero profile writes, because status reads records and spawns no agent turn.
  - `doctor`, `readiness`, `live_header`, `next_home` and `record_home` never call `ensure`.
  - The `setup.agent_home` Blocked (busy or OSError) reaches the owner:
    - `attach_tools` re-raises it instead of degrading to "tools not installed";
    - `zplan login` shows it and exits non-zero;
    - `default_prepare` refuses the chat with it.
- R-4 Auth: parent R-4, made exact against upstream. `auth_served(home, auth, env)` → bool, never reading, printing or logging a value:
  - env-key auth `("env", NAME)`: `env.get(NAME)` is non-empty;
  - file auth: `home/auth.json` is a file, or `env.get("CODEX_API_KEY")` is non-empty, or `CODEX_API_KEY` is absent from `env` and `env.get("OPENAI_API_KEY")` is non-empty;
  - so `CODEX_API_KEY=""` with `OPENAI_API_KEY` set is unserved without auth.json, as upstream :94 skips the copy. This is the one exception to "an empty variable counts as unset": an existing empty `CODEX_API_KEY` blocks the OPENAI fallback (parent R-4 note, gate10);
  - `None` auth: served.
  - Callers:
    - `readiness` (env = `os.environ`);
    - `architect._auth_present` (env = the turn env), which covers `default_prepare` for a new thread and both turn kinds.
  - The `[l]` key and the `l` remedy stay exactly on "file auth unserved"; the env-key branch keeps `i`.
- R-4b Architect child env: `child_auth_env(env)` returns a copy in which, when `CODEX_API_KEY` is absent and `OPENAI_API_KEY` is non-empty, `CODEX_API_KEY` is set to that value, mirroring upstream :94-97. The architect's turn env is built with it. Values are never logged.
  - Codex `exec` honouring `CODEX_API_KEY` with no auth.json is proven by the orchestrator in A-9, not by the worker. Until then INSTALLATION says the OPENAI_API_KEY route is unverified for the architect.
- R-5 Doctor (part; no writes, no model process, no lock):
  - The `codex_home` item's source text becomes "zplan" for the private home, or "your $CODEX_HOME, not zplan's profile" for an override. There is no new readiness item.
  - An informational line after the items, for the zplan home only: "profile N (packaged N)" from `written_version`, or "not written yet (written at login or first launch)".
- R-7 Text (part): README/INSTALLATION/USER_FLOW/commands.py say default = zplan's own home, override = `CODEX_HOME=... zplan login`. "Two logins" (owner ~/.codex vs the zplan home) is said once, in INSTALLATION. There is no isolation claim.
- R-8 Fixtures:
  - Literal home paths are under `/home/user/`.
  - Real files live in `tempfile` dirs, with HOME and XDG_DATA_HOME pointed into them.
  - An override home in a fixture is created (seeded) before the act, so `login`'s `mkdir` does not change the listing.
  - No test touches the runner's real data root. A sentinel check compares the original `private_codex_home()` before and after the module.

Acceptance (tests/test_agent_activation.py; temporary HOME and XDG_DATA_HOME; spies replace Codex and zeroshot; no network):
- A-3 Override (parent A-3):
  - Setup: CODEX_HOME=X (seeded, existing), with a spy on `agent_profile.ensure`.
  - Entry points: `cli.main(["login"])` (`subprocess.call` spied), `cli.main(["doctor"])`, `attach_tools` and `default_prepare`.
  - Each gives zero `ensure` calls, unchanged listings of X and of the private home, a spawned env with CODEX_HOME=X, and a doctor line saying "your $CODEX_HOME".
  - `CODEX_HOME=<private_codex_home()>` → zero `ensure` calls.
  - The control: CODEX_HOME="" → `cli.main(["login"])` calls `ensure` exactly once, and the profile is written.
- A-3s Status (gate9 B):
  - `cli.main(["status"])` with tools installed (fake installation) and no override → zero `ensure` calls, and the private home listing is unchanged (absent stays absent).
  - The control: the same status after the R-3c edit is reverted calls `ensure` (mutation j).
- A-4 No ~/.codex (parent A-4):
  - Setup: a seeded `$HOME/.codex` (config with apps on, auth.json) and no override.
  - Env setup, login, doctor, `default_prepare`, plus a CLI planning prepare and an attempt start (through `cli.main` with s2a2's env-capturing spies), spawn nothing with CODEX_HOME=~/.codex, and the tree hash of ~/.codex is unchanged.
  - With CODEX_HOME=~/.codex set explicitly, launches use it and no profile file appears there.
- A-4b Surfacing: `ensure` raises `setup.agent_home` → `attach_tools`, `zplan login` and `default_prepare` show that family (not `readiness.tools`) and spawn nothing.
- A-6 Auth (parent A-6):
  - Device-auth argv runs with CODEX_HOME = the private home.
  - File-auth cases, each with the same verdict in doctor, `default_prepare` (new thread) and a resumed turn's `check_home`:
    - (1) auth.json present;
    - (2) CODEX_API_KEY non-empty;
    - (3) OPENAI_API_KEY non-empty with CODEX_API_KEY absent;
    - (4) CODEX_API_KEY="" with OPENAI_API_KEY non-empty → unserved;
    - (4b) both non-empty with different sentinels → served;
    - (5) both empty;
    - (6) neither, and no auth.json.
  - Env-key providers: set, empty, unset.
  - Child env:
    - (3): the architect Popen env (spy) carries `CODEX_API_KEY` equal to the OPENAI sentinel.
    - (2) and (4b): `child_auth_env` returns the parent's env unchanged, and in (4b) the spawned `CODEX_API_KEY` is the CODEX sentinel, not the OPENAI one.
    - (4): `child_auth_env` returns the env unchanged (`CODEX_API_KEY` stays ""), and the turn is refused before any child, with zero Popen calls.
  - `[l]` appears only when file auth is unserved. No sentinel value appears in any output line or transcript.
- A-7 End-to-end with s2a (parent A-7):
  - A fresh install (no override) records codex_home = the private home on a new attempt and on a new architect thread.
  - A pre-0.5 record still spawns with `legacy_codex_home()`, and an s2a record with its recorded home.
- A-8 Regressions and mutations (parent A-8, this slice's part):
  - Base replay: A-3, A-4 and A-6 reach their behavioural assertion and fail there on the base. Record the commands and the failures. A-3s is excluded: status on the base does not call `ensure`, so it is guarded by mutation (j) only.
  - Mutations, each killed by a named test:
    - (a) `ensure` under an override;
    - (b) `ensure` only when the override differs from the private home;
    - (e) fall back to ~/.codex when the override is empty;
    - (f) ignore CODEX_API_KEY/OPENAI_API_KEY for file auth in `readiness` or `_auth_present`;
    - (f2) treat CODEX_API_KEY="" as absent (case 4 served);
    - (f3) no `child_auth_env` in the architect turn;
    - (g) swallow `setup.agent_home` in `attach_tools`;
    - (i) doctor calls `ensure`;
    - (j) status with `profile=True`;
    - (k) login calls `ensure` directly as well (two calls).
  - The drift and skills mutations (c), (d) and (h) are s2b3's.
- A-9 Qualification: one orchestrator gate after s2b3 (s2b3-agent-warnings.md, A-9): parent A-9 plus R-4b, a real architect turn with only OPENAI_API_KEY set and no auth.json. The worker does not run it.

Size: the whole diff counts except the receipt.
- Estimate:
  - product ~125: agent_home/native_environment/login ~30, auth_served/child_auth_env and callers ~50, cli status/attach ~15, doctor lines/commands ~30;
  - docs ~45;
  - tests ~300;
  - existing fixture/wording edits ~40.
- Total ~510. Above 600: report the measured overrun and rationale in the receipt; merge requires explicit critic disposition (ORCHESTRATOR step 1).
- The pre-split estimate with drift/sources was ~670 after the gate9 B additions, hence s2b3.

Out of scope:
- drift/sources warnings, `readiness.agent_drift`/`agent_sources`, the R-6 precedence table, parent A-5 (s2b3);
- s2b1's lifecycle;
- A-9 (orchestrator);
- s2c;
- the Claude lane home; declared project skills/hooks paths; migrating a login;
- devtools/zeroshot/run.sh; s1a1b*.

DoD:
- Worker (targeted): `PYTHONPATH=.:tests python3 -m unittest tests.test_agent_activation tests.test_agent_profile tests.test_architect_home tests.test_setup tests.test_warn_contract tests.test_tui_chat tests.test_architect tests.test_record_home tests.test_home_wiring tests.test_install tests.test_ux tests.test_layout tests.test_toolchain tests.test_reference` passes. The worker does not run the full suite.
- Orchestrator: the full suite at the merge gate.
- `git diff --stat <base>` lists only the write-set.
- `python3 devtools/export_check.py` on the committed candidate reports no home-path finding (exit 3 "incomplete" for a missing private list is reported, not a failure).
- Receipt:
  - base commit and this brief's sha256;
  - file list with line counts;
  - the existing-test edits;
  - base-replay failures;
  - the mutation table;
  - the gate7 A binding note confirmed.
