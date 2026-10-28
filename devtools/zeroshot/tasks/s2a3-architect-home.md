s2a3-architect-home — 0.5 item S2, slice 3 of 3 of devtools/zeroshot/tasks/s2a-home-binding.md (the parent). Its R-5, R-6, R-8, A-5, A-6, the architect mutations of A-7 and A-8 apply verbatim where cited. R-7 holds here as in every slice. Slicing: s2a1-home-core.md:5 and s2a2-engine-wiring.md:15 (swarm05 c, "engine binding separately from architect continuation"). Lane: Environment (L1). DeepSeek worker, sol reviewers. Critic gate9 A: GO WITH CHANGES (applied).

Base: main ac220ec (s2a1 merged). This slice starts now, in parallel with the running s2a2 and s2b1 (gate9 A); it has no dependency on s2a2. Lines below are cited at ac220ec. Re-check every line on the actual base, and re-gate if a premise moved. Record the base and this brief's sha256 in the receipt.
- s2a1's frozen interface is used exactly as stated in s2a1-home-core.md:14-16: `record_home.effective_home(recorded)` (record_home.py:15-22), `toolchain.valid_codex_home(value)` (toolchain.py:67-71) and `setup.legacy_codex_home()` (setup.py:218-221). Nothing from s2a2 is used.

Coverage (each parent item exactly once):
- s2a1: R-1 and R-2 (the core).
- s2a2: R-3 and R-4; A-1 store half, A-2, A-3, A-4, A-7 engine mutations (s2a2-engine-wiring.md:15).
- s2a3 (this):
  - R-5, R-6 and R-8;
  - A-5, A-6 and the A-7 architect mutations (skip the home_lost check; check auth before resolving the recorded home);
  - A-8 (orchestrator).
  The architect, chat header and `architect.home_lost` are out of s2a2's scope (s2a2-engine-wiring.md:141-142). Parent A-1's architect half ("a new thread records the home") is A-5 here.

Frozen interface for s2b2 (s2b2-profile-activation.md relies on it):
- `architect.check_home(home, environment, resumed)` is the one predicate for "can a turn start in this home".
  - It returns None, or raises Blocked:
    - `architect.home_lost` when resumed;
    - `readiness.auth` for a new thread;
    - `readiness.codex_home` when the config is unreadable (from `codex_provider`);
    - `architect.invalid_config` for a selected profile (R-6).
  - Order (fixed): home is a directory (resumed only) → config.toml parsed with `setup.read_toml`, a non-empty top-level `profile` → `architect.invalid_config` → `codex_provider(home)` → `_auth_present`. The profile check runs before `codex_provider`, which would otherwise answer `readiness.codex_home` for an unknown profile first (setup.py:449-453).
  - Its auth-presence step is one private helper, `_auth_present(home, auth, environment)`, the hook s2b2 replaces with `setup.auth_served`. It reads presence only.
- `Architect.next_home()` returns `(home: Path, resumed: bool)` for the next turn, without side effects.

Write-set (exclusive for this slice):
- architect.py:
  - `ArchitectStore.load` :345-359 (optional `codex_home`);
  - `Architect.reset` :555-571 (drop `codex_home`);
  - `Architect._turn` :644-697: resolve the turn home, `check_home` before the session save, the turn env, `persist` writing `codex_home`;
  - new `next_home`, `check_home`, `_auth_present`, next to them.
  - `build_argv` :86-101 is unchanged.
- tui/chat.py:
  - `default_prepare` :394-422, the auth checks :413-420 and the header :421;
  - `live_header` :377-391;
  - the header refresh after a reset in `ArchitectChat._reset`, (:660), only if it does not already re-read `live_header`.
- catalog.py: `architect.home_lost` in the architect group :336-352. docs/REFERENCE.md is regenerated only.
- new `tests/test_architect_home.py`;
- existing architect/chat test fixtures: the setup lines only (A-7 allowed edits).
- the receipt `devtools/zeroshot/tasks/s2a3-architect-home-receipt.md`.

Not touched: engine.py, runs.py, planning.py, authority.py, delivery.py, process.py, task_gate.py, setup.py, record_home.py, toolchain.py, cli.py, tui/app.py, tui/controller.py, docs other than REFERENCE.

Parallelism:
- s1a1b1 (task_gate, engine, authority :429-437, runs `gate_manifest`, delivery; catalog untouched, s1a1b1-gate-record.md Write-set): disjoint files → can run in parallel.
- s1a1b2: shares only catalog.py (different group) and the generated REFERENCE.md. Parallel is fine; the second merge regenerates.
- s2a2 (running; engine/runs/planning/tests/test_home_wiring.py): disjoint files and no shared API → parallel.
- s2b1 (running; agent_profile.py, resources, pyproject, catalog `setup.agent_home` in the Setup group :322-334, generated REFERENCE): this slice owns only the architect group :336-352 of catalog.py; REFERENCE is generated. Integration is sequential: completed candidates only, active workspaces are not rebased, and the second integration SHA regenerates REFERENCE and runs the full gates.
- s2b2: overlaps on architect.py (`_auth_present` → `auth_served`) and tui/chat.py (`default_prepare`). Strictly sequential: s2b2's Base requires s2a3.

Audit (ac220ec):
- Session record:
  - `_fresh_session` :552-553 = {version, thread_id, model, created, turns, usage};
  - `load` :345-359 checks thread_id/turns/usage only, else `architect.session_corrupt` :358;
  - `save` :361-364 is atomic.
- `_turn` :644-697:
  - it loads the session and builds the argv;
  - it saves `turns += 1` and appends the owner message (:659-660) before the Popen;
  - `persist(new_thread)` :662-665 stores the thread id on `thread.started` (:456-461);
  - Popen with `env=dict(self.environment)` :685-687.
- `reset` :555-571 sets `thread_id = None` under the project lock.
- `Architect.environment` is the `setup.native_environment()` copy from `default_prepare` (tui/chat.py:404, :422).
- `default_prepare` :394-422:
  - it judges the current home `setup.codex_home(environment)` :413;
  - `readiness.auth` for missing file auth :415-417, and for an unset env key :418-420 (read from `os.environ`);
  - the header comes from that home :421.
- The chat's reset (tui/chat.py:566-580) runs only in phase "ready", so a refusal in `default_prepare` would make Ctrl+R (tui/app.py:971, :1195-1198) unreachable.
- `live_header` :377-391 re-reads `codex_home(architect.environment)` after a turn (:628).
- argv: new thread `-s read-only` :95; resume `-c sandbox_mode="read-only"` :100. `codex_provider` setup.py:435-463 raises `readiness.codex_home`.
- Catalog architect families: catalog.py:336-352. Ctrl+R text: :403, :523.

Rules:
- R-5 Thread home: parent R-5 verbatim, made concrete:
  - Record: `persist(new_thread)` writes `thread_id` and `codex_home = str(setup.codex_home(self.environment))` in the same save.
    - `load` accepts a session without `codex_home`.
    - A present `codex_home` that fails `valid_codex_home` → `architect.session_corrupt`.
    - A session with `codex_home` and `thread_id: None` is also `architect.session_corrupt`.
  - `next_home()`:
    - with a thread id: `(record_home.effective_home(session.get("codex_home")), True)`. A session without the field gives `legacy_codex_home()`;
    - otherwise: `(setup.codex_home(self.environment), False)`.
    - It reads only.
  - `_turn`:
    - resolve `next_home()` first;
    - then `check_home(home, env, resumed)`;
    - then the existing session save, the transcript append and the Popen.
    - A refusal leaves `session.json` and `transcript.jsonl` byte-identical, and no process starts.
    - A resumed turn's env is `dict(self.environment, CODEX_HOME=str(home))`. A new thread's env is unchanged.
  - `check_home`:
    - for a resumed turn: a home that is not a directory → `architect.home_lost`;
    - then the config: unreadable → `readiness.codex_home`; a non-empty top-level `profile` → `architect.invalid_config` (before `codex_provider`, R-6);
    - then `codex_provider(home)`;
    - then `_auth_present`: file auth → `home/auth.json` is a file; env-key auth → the variable is non-empty in `environment`. If absent, `architect.home_lost` when resumed, `readiness.auth` for a new thread.
    - The `architect.home_lost` text names the home (tilde) and the rollover: Ctrl+R "новый диалог" starts a new thread in the current home. It never prints a credential or a variable value.
  - `reset()` also removes `codex_home`, so the previous thread's home is ignored.
  - `default_prepare`:
    - it builds the Architect, then takes `next_home()`;
    - only for a new thread, it runs `check_home` (the existing `readiness.auth` refusals, unchanged in text);
    - for a continuation, it runs no check of the recorded home at all (directory, config, profile, auth): every one of them is deferred to the turn, so a broken recorded home never blocks preparation and Ctrl+R stays reachable (gate9 A; tui/chat.py:574).
    - The header shows `next_home()` and that home's provider. If the provider cannot be read (missing dir, unreadable config, unknown profile), the header shows the home with the provider "?" (fallback); it never raises.
  - `live_header` uses `next_home()`, with the same fallback. After a reset, the header shows the current home.
- R-6 Read-only: parent R-6 verbatim.
  - `build_argv` and its equality tests are unchanged.
  - `check_home` reads the turn home's config.toml (both turn kinds). A non-empty top-level `profile` → `architect.invalid_config`, before `codex_provider`, any save or Popen. The test seeds an unknown profile name (no `[profiles.x]`) and expects `architect.invalid_config`, not `readiness.codex_home`.
  - Top-level `danger-full-access` is not refused (A-8 decides).
- R-7: no default-home, login, doctor or profile change (s2b). No credential file is read, copied or printed.
- R-8 Catalog: `architect.home_lost` (what/why/remedy, with the remedy naming Ctrl+R). REFERENCE regenerated.
- R-9 Fixtures:
  - Literal home paths in tests are under `/home/user/`.
  - Real files live in `tempfile` dirs, with HOME, XDG_DATA_HOME and CODEX_HOME pointed into them.
  - Spies replace Popen; there is no real Codex.

Acceptance (tests/test_architect_home.py; deterministic; a Popen spy records argv and env):
- A-5 (parent A-5, every bullet):
  - A new thread records the home.
  - A continuation spawns with the recorded home A while the current env has B.
  - A legacy session (no field) uses `legacy_codex_home()` (process CODEX_HOME=L, architect env Z → L).
  - Missing dir, missing auth.json (file auth) and unset or empty key → `architect.home_lost`, with 0 Popen calls and session and transcript bytes unchanged.
  - After reset the next turn spawns in B and records B.
  - A malformed `codex_home` (relative, empty, NUL, 4097 characters, non-str) and `codex_home` with a null thread → `architect.session_corrupt`.
  - The header shows A for a continuation and B after a reset.
  - Integration through `default_prepare` + `ArchitectChat`:
    - recorded A with a login and current B without one → prepares, and the send continues in A;
    - recorded A lost → prepares, and the send is refused `architect.home_lost`;
    - then Ctrl+R (`chat.reset()`) succeeds, and the next send is refused `readiness.auth` for B with 0 Popen calls;
    - recovery (gate9 A): recorded A with an unreadable config.toml (and, separately, a missing A directory), current B with a login → `default_prepare` succeeds with the fallback header; the send is refused (`readiness.codex_home`, resp. `architect.home_lost`) with 0 Popen calls; Ctrl+R succeeds; the next send spawns in B and records B.
  - The control: B with a login → the new thread spawns in B.
- A-6 (parent A-6):
  - The argv equality tests stay green.
  - A home with top-level `sandbox_mode = "danger-full-access"` still yields `-s read-only` and `-c sandbox_mode="read-only"`.
  - A non-empty `profile`, in either turn kind → `architect.invalid_config` with 0 Popen calls and the session unchanged.
- A-7 Base replay and mutations (parent A-7, architect part):
  - The A-5 integration cases and the "continuation in A" spawn fail on the base at their behavioural assertion. Record the commands and the failures. Helper unit tests are excluded and covered by mutations.
  - Mutations, each killed by a named test:
    - (a) skip the home_lost check;
    - (b) check auth before resolving the recorded home (auth of B);
    - (c) `persist` without `codex_home`;
    - (d) `reset` keeps `codex_home`;
    - (e) the check after the session save (bytes change);
    - (f) `default_prepare` refuses a lost continuation (Ctrl+R unreachable);
    - (g) the header shows the current home for a continuation;
    - (h) the profile check only on new threads;
    - (i) `codex_provider` before the profile check (unknown profile → `readiness.codex_home`);
    - (j) `default_prepare` reads the recorded home's config (the recovery case blocks preparation);
    - (k) the header raises instead of falling back.
  - The existing architect, chat and tui suites stay green. Allowed edits (gate9 A), each listed in the receipt:
    - fixture setup that prepares a valid temporary home for the new turn check: an existing home directory, `auth.json` or a provider key in the fixture env (e.g. tests/test_architect.py:108 sets CODEX_HOME to a directory that does not exist);
    - catalog-count assertions, if any.
    Assertions are unchanged, and there is no test-only bypass in product code.
- A-8 Installed check: parent A-8, by the orchestrator on the Linux test host after merge, not the worker.

Size: the whole diff except the receipt and the generated REFERENCE counts.
- Estimate ~430: product ~100 (architect ~70, chat ~27, catalog ~3), tests ~310, existing fixture setup ~20.
- Above 600, stop and report for a re-gate.

Out of scope:
- engine/runs/planning wiring (s2a2);
- the default home, `ensure`, login, doctor and the shared auth rule across doctor/chat (s2b2; this slice keeps today's presence rule, moved behind `_auth_present`);
- telemetry (s2c);
- migrating a home; upstream; devtools/zeroshot/run.sh.

DoD:
- Worker (targeted): `PYTHONPATH=.:tests python3 -m unittest tests.test_architect_home tests.test_architect tests.test_tui_chat tests.test_tui tests.test_record_home tests.test_setup tests.test_toolchain tests.test_reference` passes. The worker does not run the full suite.
- Orchestrator: the full suite at the merge gate; A-8 on the Linux test host.
- `git diff --stat <base>` lists only the write-set.
- `python3 devtools/export_check.py` on the committed candidate reports no home-path finding (exit 3 "incomplete" for a missing private list is reported, not a failure).
- Receipt:
  - base commit, this brief's sha256 and the file list;
  - base-replay failures;
  - the mutation table;
  - a confirmation that `check_home`/`_auth_present`/`next_home` match the frozen interface above.
