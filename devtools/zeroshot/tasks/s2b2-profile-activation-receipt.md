# s2b2-profile-activation — receipt (repair visit 10)

Base commit: `bd6370f0af4d48a7ff9e872e872c6c5ae28e71b4` — `main` after `s2a2-engine-wiring`, `s2a3-architect-home`
and `s2b1-profile-manager` were merged (the candidate's parent; `git diff --stat` is against it). The brief's
citations are pinned at `08fe3e3` (an ancestor); every cited line was re-checked on the actual base. All four
stop-and-report prerequisites are present: `agent_profile.ensure`/`written_version`, the `setup.agent_home`
family, `architect.check_home` with `_auth_present`, and `item(..., severity=)`. This brief's sha256:
`e7580719acb8aeeaf8257992b3b0541b872932a525d582453068e767842cf9df`
(`devtools/zeroshot/tasks/s2b2-profile-activation.md`).

## Repair notes

**Visit 10 (the eighth review: both reviewers now route the conflict to the orchestrator; the R-8-correct state is held).**

- **No product or test change this visit.** Both reviewers reject on the same single item — the two fixture files
  outside the exclusive write-set — and both now say the worker cannot close it. Acceptance: "The orchestrator must
  authorize or reassign these changes while preserving R-8 isolation; reverting them reopens verified fixture
  regressions." Code: "Simply reverting them would reopen the documented R-8 problem; another worker repair cannot
  resolve the ownership conflict alone." The worker therefore **holds** the visit-9 state (isolation present) rather
  than alternating again — the reverted state was already shipped in visit 8 and rejected for the R-8 regression.
- **Evidence refreshed this visit** (no edits since visit 9): the 14-module DoD command plus `tests.test_tui_polish`
  — **430 tests, 5 skipped, OK** (Checks); both reviewer reproductions still pass.
- **Acceptance review's non-rejecting spec gap, recorded (not silently accepted):** `readiness`'s *served* file-auth
  item (`setup.py:630`) reads "auth: login-файл есть в CODEX_HOME (наличие, не валидность)" when the login is
  actually served by `CODEX_API_KEY`/`OPENAI_API_KEY` and `auth.json` is absent. R-4 governs the *verdict* (and the
  *unserved* `[l]` branch) only, never this ok-line's wording, so no stated requirement is violated; the worker
  leaves it to the orchestrator because `setup.py`'s `readiness` is reworked by `s2b3` next (an in-write-set
  one-branch fix is available if the orchestrator wants it now).
- **Code review's single aggregate-run error is not candidate-specific.**
  `AnswerDraftTests.test_d4_open_refuses_a_milestone_that_finished_while_parked` raised "Authority physical bytes
  changed; reload under lock." once under the parallel reviewer run; the reviewer reproduced it neither on the
  candidate nor on the base in isolation, and this visit's run of the same 15 modules had no error. That is the
  known cross-process store race under concurrent agents, not this slice's code (it is also outside the write-set).

**Visit 9 (the seventh review: the isolation is restored; the write-set conflict is escalated, not traded).**

- **The two importer fixtures are edited again, R-8-correct.** The sixth review rejected the visit-8 revert exactly
  as the fourth/fifth reviews had rejected the edits: *one* of the two requirements must give, and this visit takes
  the reviewers' instruction literally — "resolve the exclusive-write-set conflict through the orchestrator, then
  isolate `HOME`/`XDG_DATA_HOME` and the provider variables in these fixtures without weakening assertions". So the
  isolation is back (identical to visit 7; `+12/-2` in `tests/test_tui_polish.py`, `+16/-1` in
  `tests/test_warn_contract.py`, no assertion touched) and the write-set conflict is handed to the orchestrator
  (scope section) rather than resolved by dropping the isolation.
- Both reviewer reproductions now pass on this candidate:
  - `XDG_DATA_HOME=<root with planning-kit/codex-home/auth.json> CODEX_HOME='' CODEX_API_KEY='' OPENAI_API_KEY=''
    TMPDIR=<scratch> … tests.test_tui_polish.ClosingLineTests.test_a4_a_failing_remedy_…` → OK (`[False, 'l']`).
  - A `written_version` spy over `tests.test_warn_contract.DoctorWarnTests` shows both reads are inside the
    fixtures' own `TemporaryDirectory` roots, never the inherited `XDG_DATA_HOME`.
- **Why this is not "self-authorizing".** The worker has now shipped both states and each was rejected by the other
  requirement; there is no third state (the isolation cannot live in a write-set file — visit 8 verified that).
  The diff therefore carries one extra fixture default per file, explicitly flagged here, and the orchestrator must
  either amend the write-set or reassign them to `s2b3`.

**Visit 8 (the sixth review: the isolation was reverted and handed off — SUPERSEDED by visit 9, which restores it).**

- **Exclusive write-set resolved.** The two importer fixtures this slice had edited (`tests/test_tui_polish.py`,
  `tests/test_warn_contract.py`) are restored to their **base** content, so the diff lists the write-set exactly:
  `git diff --name-only HEAD -- tests/test_tui_polish.py tests/test_warn_contract.py` is empty. Neither file's
  assertions changed, and both modules still pass in a normal run (see Checks).
- **The R-8 fixture need is not waived — it is reported for an authoritative disposition.** Those two fixtures are
  ambient-sensitive only because of this slice's new behaviour:
  - `setup.readiness` now judges `agent_home(os.environ)` (R-1), so with an *empty or unset* `CODEX_HOME` the home is
    `private_codex_home()` and the fixture's `codex_home` patch is bypassed — the runner's real data root (and an
    inherited `CODEX_API_KEY`/`OPENAI_API_KEY`) then decide the auth item.
  - `doctor`'s new profile line (R-5) reads `private_codex_home()/config.toml`.
  Reproduction on this candidate (the reviewer's): with `CODEX_HOME=''` and an inherited `XDG_DATA_HOME` whose
  `planning-kit/codex-home/auth.json` is seeded, `test_a4_a_failing_remedy_is_only_named_when_its_key_is_enabled`
  returns `([True, None])` where it expects `([False, 'l'])`; the same run on the base passes, because base
  `readiness` used the patched `codex_home`. The remedy is a fixture default in those two files (pin
  `XDG_DATA_HOME`/`HOME` into the fixture root; clear the provider variables), which the exclusive write-set does
  not authorize. Reverting loses that isolation again — so the two requirements conflict and one needs the
  orchestrator (below).
- **Why no in-scope alternative exists.** The isolation cannot live in a write-set file: neither module imports any
  test helper this slice may edit (`tests/test_tui_polish.py` imports `test_tui`/`test_tui_live`/
  `test_tui_milestones`/`test_tui_planning`/`tui_support`; `tests/test_warn_contract.py` imports none of them), and a
  module-level `os.environ` mutation would be a test-only bypass. Making the product deterministic under a *patched*
  `codex_home` (e.g. comparing the resolved home to Codex's own default) would be exactly that bypass, so it was
  rejected rather than shipped.
- **Proposed disposition (orchestrator).** Either (a) amend this slice's write-set with the two fixture defaults, or
  (b) hand them to `s2b3`, whose write-set already covers the same `setup.py` `readiness`/`doctor` area and docs.
  Either way the change is small (≈12 + ≈16 lines, no assertion touched) and is fully specified above.

**Visit 7 (the fifth review: the doctor abort on an unreadable profile, and the R-4/A-6 vs R-4b conflict).**

- **P2 — the doctor profile line no longer aborts doctor (R-5).** `agent_profile.written_version` reads
  `<home>/config.toml` and lets an `OSError` escape (a directory named `config.toml`, a permission error). `doctor`
  now catches it and answers "no profile yet", so the report continues to the process-profile lines and still exits
  1. `agent_profile.py` is unchanged (it is outside this slice's write-set; s2b1 owns it). Regression:
  `DoctorTests.test_the_default_home_doctor_survives_an_unreadable_profile_entry` — a `config.toml` *directory* in
  the fixture's private home; asserts the exit code, the "not written yet" line and that the process-profile line
  still printed. Mutation `m1` (drop the guard) is killed. Repro before the fix (doctor raised `IsADirectoryError`
  at `setup.py:716`, before the `Профиль процесса` line): unset `CODEX_HOME`, create
  `private_codex_home()/config.toml` as a directory, call `setup.doctor(print)`.
- **The R-4/A-6 verdict-parity conflict with R-4b is resolved: the auth verdict is judged on the owner's own env;
  the child mapping only shapes the child (R-4b).** For a custom provider whose `env_key` is `CODEX_API_KEY`, with
  `CODEX_API_KEY` absent and only `OPENAI_API_KEY` set, `readiness` reported `(False, 'i')` and `default_prepare`
  refused, but `Architect._turn` mapped the env with `setup.child_auth_env` *before* `check_home`, so the same
  resumed turn completed. `_turn` now calls `check_home` first and `setup.child_auth_env` after (architect.py:
  :803/:806); the child still receives the mapping. R-4's env-key rule is unconditional and A-6 requires one
  verdict in all three judges, while R-4b is scoped to the OPENAI_API_KEY *file*-auth route, so it must not flip
  the verdict to "served". Regression:
  `AuthTests.test_a6_a_codex_key_env_provider_is_refused_before_a_resumed_child` — a real resumed turn (a seeded
  session, the scripted codex) refuses with `architect.home_lost` and spawns nothing, matching
  `readiness`/`default_prepare`; with `CODEX_API_KEY` set the turn completes and the spawned child receives exactly
  that value. Mutation `m2` (map before the check) is killed.
- **Measurement fixed.** The earlier size paragraph mixed measures (it reported 1124 where the reviewer measured a
  331-line tracked diff plus an 809-line new module = 1140); the measured figures are in the Size section below.

**Visit 6 (the third review: the profile-lock escape, the broken-owner-home crash, and the last readiness fixture).**

- **P1 — the profile lock can no longer take the write outside zplan's own home (R-1/A-4).**
  `agent_profile.ensure` opens `<home>/.zplan-profile.lock` with `O_CREAT` (only to hold its `flock`), so a symlink
  at that name made zplan create the file it pointed at — the reviewer's absent `~/.codex/unexpected-lock-target`.
  `setup.py` gains `_refuse_escaped_profile_lock(home)`, called by `native_environment` on the implicit home just
  before `ensure`: any non-regular entry at `agent_profile.LOCK_NAME` is refused with the `setup.agent_home`
  family, so nothing is created or changed in either tree. Regression:
  `OwnerHomeAliasTests.test_r1_a_symlinked_profile_lock_does_not_write_outside_the_private_home` asserts the refusal
  from `native_environment`, `cli.main([])`, `zplan login` and `default_prepare`, zero spawned processes, zero
  `ensure` calls, the owner's target absent and both byte trees unchanged. Mutation `n4` (drop the guard) is killed.
- **P1 — a broken owner home no longer crashes a launch (code review finding 1).** `_refuse_owner_home` compared
  with `codex_home({})`/`Path.resolve()`, so a `~/.codex` symlink that loops raised `RuntimeError` out of every
  launch. Both sides now go through `os.path.realpath` (never raising; a broken path simply is not a usable Codex
  home, so the check does not fire). Regression:
  `OwnerHomeAliasTests.test_r1_a_looping_owner_codex_home_does_not_break_a_launch` keeps a looping `~/.codex`,
  asserts `Path.resolve()` really raises, and then launches through `native_environment`, `cli.main([])` and
  `default_prepare` into the fixture's own private home. Mutation `n5` (the unguarded `Path.resolve`) is killed.
- **P2 — the second real-readiness fixture is isolated too (R-8).** `ClosingLineTests` now shares one
  `fixture_home()` context manager (pins `XDG_DATA_HOME` into the fixture root, clears `CODEX_API_KEY` and
  `OPENAI_API_KEY`) around **both** `setup.readiness` calls —
  `test_a4_a_failing_remedy_…` and `test_a4_an_environment_key_auth_item_…`. Instrumented run (a `Path.exists`
  spy, an inherited `XDG_DATA_HOME` whose `planning-kit/codex-home/config.toml` exists): no access under the
  inherited root; the only `codex-home/config.toml` probe is the fixture's own. Assertions unchanged.
- **Residual, escalated, not silently waived.** The lock escape's *root cause* is `agent_profile._open_lock`
  following a symlink (`path.open("a")`); with `O_NOFOLLOW` there the guard would not be needed. `agent_profile.py`
  belongs to s2b1 and is outside this slice's write-set, so the worker fixed the one production caller it owns
  (`native_environment`) and reports the root cause here instead of editing that file — see the scope section.

**Visit 5 (the second review's P1 alias, the re-raised XDG isolation, and the scope escalation).**

- **P1 — an implicit private home that resolves into the owner's `~/.codex` is refused (R-1/A-4).**
  `terminal_planner/setup.py` gains `launch_home(env=None)`: `agent_home(env)` as before, but for the *implicit* home
  it first calls the new `_refuse_owner_home`, which raises `Blocked(family="setup.agent_home")` when the home's
  resolved path *is* `~/.codex` or lies inside it (a symlink at the `codex-home` entry or at a parent such as
  `planning-kit`). `native_environment` and the `--native-binary` branch of `cli.attach_tools` both go through it, so
  no launch anywhere hands Codex the owner's home and no profile is written there. Before the fix a symlinked
  private home made `agent_profile.ensure` replace the owner's `config.toml` with the packaged profile and leave a
  `config.toml.bak` (reproduced; `IsADirectoryError`-free but destructive). An explicit `CODEX_HOME` — `~/.codex`
  included — is untouched: that is the documented opt-in (A-4), guarded by
  `FreshInstallTests.test_a4_an_explicit_owner_home_is_used_and_gets_no_profile`.
  Regressions: `OwnerHomeAliasTests` (directory alias and parent alias; each asserts the refusal from
  `native_environment`, `cli.main([])`, `cli.main(["--native-binary", …])`, `zplan login` and `default_prepare`, zero
  spawned processes, zero `ensure` calls, and a byte-identical tree of `$HOME/.codex`). Mutations killed here:
  dropping the refusal (2 failures), an exact-equality-only test (1), and applying the check to an explicit
  `CODEX_HOME` (1).
- **P2/the re-raised R-8 finding — `test_tui_polish.ClosingLineTests` isolates the selected home.**
  An empty or unset `CODEX_HOME` makes `agent_home` return `private_codex_home()` directly, bypassing the fixture's
  `codex_home` patch, so the fixture also pins `XDG_DATA_HOME` into its temporary root. With inherited
  `XDG_DATA_HOME` (the reviewer seeded `$S/data/planning-kit/codex-home/auth.json`) the item came back
  `([True, None])`; now the home is the fixture's own (absent) and the item is `([False, 'l'])`. Assertions
  unchanged. Repro passes: `TMPDIR=$S XDG_DATA_HOME=$S/data CODEX_HOME='' PYTHONPATH=.:tests python3 -B -m unittest
  tests.test_tui_polish.ClosingLineTests.test_a4_a_failing_remedy_is_only_named_when_its_key_is_enabled`.

**Visit 4 (the code review's R-8 importer regression; two files added to the write set — visit 8 reverted them, visit 9 restored them; see the scope section).**

- **`tests/test_tui_polish.py` (code finding 1).** `ClosingLineTests.test_a4_a_failing_remedy_is_only_named_when_its_key_is_enabled`
  builds a real file-auth item from `setup.readiness`, and `setup.auth_served` reads the process env: an inherited
  `CODEX_API_KEY` (a developer shell's, or `run.sh`'s) served the login, so the auth item came back `([True, None])`
  instead of `([False, 'l'])` at `test_tui_polish.py:867`. The fixture now pins `CODEX_API_KEY`/`OPENAI_API_KEY`
  empty around the readiness call, so the item is deterministically unserved; the assertions are unchanged. `HOME`
  is already the fixture root (`ProjectTest`) and `agent_home` resolves through the test's patched
  `setup.codex_home`, so the item's home is the fixture's — no real data root is read.
  Repro (killed before the fix, passes now):
  `TMPDIR=$S CODEX_API_KEY=codex-sentinel-value-0001 PYTHONPATH=.:tests python3 -m unittest tests.test_tui_polish.ClosingLineTests.test_a4_a_failing_remedy_is_only_named_when_its_key_is_enabled`.
- **`tests/test_warn_contract.py` (code finding 2).** `DoctorWarnTests` stubbed `setup.readiness`, but `doctor` still
  read the process's own `private_codex_home()` for its profile line when `CODEX_HOME` was empty or unset: with no
  `HOME`/`XDG` isolation that was the host's real data root (R-8), and a seeded `config.toml` *directory* under it
  made `agent_profile.written_version` raise `IsADirectoryError` at `setup.py:661`. `DoctorWarnTests.setUp` now pins
  `HOME`, `XDG_DATA_HOME`, `XDG_CONFIG_HOME` and an empty `CODEX_HOME` inside a temporary root, so the profile line
  reads a fixture home (absent → "not written yet"). Assertions unchanged.
  Repro (error before the fix, passes now):
  `mkdir -p $S/data/planning-kit/codex-home/config.toml; TMPDIR=$S XDG_DATA_HOME=$S/data CODEX_HOME='' PYTHONPATH=.:tests python3 -m unittest tests.test_warn_contract.DoctorWarnTests`.
  (Visit 8 reverted this `setUp`; the same run then reads the runner's real private home — the R-8 hand-off.)
- **Write-set.** These two importer test files are added to the slice's write set (reported to the orchestrator);
  both edits are the "fixture default" kind the brief allows, with no assertion weakened and no test-only bypass.

**Visit 3 (the rejection's two code findings).**

- **R-1 through `--native-binary` (code finding 1).** `cli.attach_tools` (cli.py:960) no longer returns early for a
  development binary: `fixture` returns (no Codex at all), and `explicit` now builds the env itself —
  `environment = dict(os.environ, CODEX_HOME=str(agent_home(os.environ)))` (cli.py:971-972) — so the planner factory
  and the milestone driver are handed the same `CODEX_HOME` as a pinned-tools launch (R-1). Before, `environment`
  stayed `None`, `NativeEngine.codex_home()` fell back to the process env and a fresh install resolved `~/.codex`.
  Covered by `ExplicitBinaryTests` (both factories; unset, empty and explicit override); mutation **m** dies there.
- **A-7 observed a real attempt (code finding 2).** `EndToEndTests.test_a7_a_fresh_install_records_the_private_home`
  no longer hand-builds a binding: it runs a real fresh attempt — an approved native plan and one
  `MilestoneRuns.start` — through the `test_runs` harness (import-only, a function-local subclass so unittest never
  collects its tests) and reads the persisted `record["binding"]["codex_home"]`, compared against the private path
  computed from the fixture layout (`<XDG_DATA_HOME>/planning-kit/codex-home`), not from a production helper. It still
  asserts the attempt really ran (two `run` invocations) and keeps the architect-thread half (session `codex_home`,
  resumed child env). Mutations **a3** (the attempt writer's `codex_home`), **a2** (thread persistence) and
  **b2/b3** (the resumed recorded-home env) die here.

**Visit 2 (the earlier rejection's five acceptance + six code findings), kept.**

- **R-4b documentation:** `docs/INSTALLATION.md` states that the `OPENAI_API_KEY` route reaches the architect's
  Codex child but is unverified for the architect until the qualification gate.
- **A-4 base replay:** `FreshInstallTests.test_a4_…` asserts only through production entry points; the direct
  `agent_home` unit check moved to `HomeResolutionTests`.
- **A-7 record/spawn coverage:** real turns with stored sessions and spawned `CODEX_HOME`.
- **Guarded doctor mutation:** `DoctorTests.test_the_default_home_doctor_writes_no_profile` (mutation **i2**).
- **Deterministic fixtures:** `PROVIDER_VARS` (`CODEX_API_KEY`, `OPENAI_API_KEY`, `CORP_KEY`) dropped in `setUp`
  and filtered in `AuthTests.verdicts`.
- **R-8:** the private-home override is seeded before the act; the sentinel comparison moved to `tearDownModule`.
- **Export gate:** the sentinels match no `CONTENT_RULES` entry.

**Visit 3 extra (raised as a verification note, fixed).** Mutation **g** used to die with a `Screen`-missing-method
error; `Screen.ask` now raises `EOFError` like a real terminal at end of input, so **g** fails the refusal assertion
(`0 != 1`) in 0.2 s instead of erroring or spinning the menu.

## Files (write-set only)

`git diff --stat HEAD` lists exactly the write-set (plus the two new untracked files). Insertions/deletions:

- `terminal_planner/setup.py` (+141/-18): new `agent_home` :228, `launch_home` :235 and `_refuse_owner_home` :252
  (visit 5, R-1/A-4 alias refusal; visit 6, `os.path.realpath`), `_regular_file` :268, `auth_served` :277,
  `child_auth_env` :296, `_refuse_escaped_profile_lock` :313 (visit 6); `codex_home` docstring (wording);
  `native_environment(profile=True)` :338; `login` docstring; `readiness`'s `codex_home`/`auth` part :608-641; the
  `doctor` profile line :714-721 (visit 7: the read is failure-tolerant).
- `terminal_planner/architect.py` (+13/-19): `_auth_present` :550 delegates to `setup.auth_served`; `_turn` :803
  calls `check_home` before :806 applies `setup.child_auth_env` (visit 7: the verdict precedes the child mapping). `check_home`/`next_home`/the refusal order stay s2a3's.
- `terminal_planner/cli.py` (+18/-5): `attach_tools` :960 — the home is chosen independently of the executable
  (R-1, :972, now through `setup.launch_home`) and a `setup.agent_home` Blocked is re-raised (:979); the `status`
  env :1024.
- `terminal_planner/commands.py` (+3/-3): the `login` Command text.
- `README.md` (+7/-6), `docs/INSTALLATION.md` (+18/-11), `docs/USER_FLOW.md` (+8/-8): default-home wording and the
  R-4b qualification.
- `tests/test_agent_activation.py` (new, 873 lines): harness + `OverrideTests`, `StatusTests`, `ExplicitBinaryTests`,
  `HomeResolutionTests`, `OwnerHomeAliasTests` (visits 5-6), `ChildAuthEnvTests`, `DoctorTests`, `FreshInstallTests`,
  `SurfacingTests`, `AuthTests`, `EndToEndTests`, `IsolationTests`, `tearDownModule` (27 tests; visit 7 adds the
  unreadable-profile doctor test and the `CODEX_API_KEY`-env provider parity turn).
- `tests/test_agent_profile.py` (+5/-3), `tests/test_setup.py` (+17/-5), `tests/test_tui_polish.py` (+12/-2),
  `tests/test_warn_contract.py` (+16/-1): fixture/wording edits (below). The last two are the scope-amendment files
  (see the scope section).

Not touched: `agent_profile.py`, `catalog.py`, `engine.py`, `runs.py`, `authority.py`, `delivery.py`, `process.py`,
`task_gate.py`, `planning.py`, `record_home.py`, `toolchain.py`, `tui/*`, `docs/REFERENCE.md`, the other listed test
files, `devtools/zeroshot/run.sh`. `tui/chat.py` verified: `default_prepare` :414 judges a new thread through
`check_home` :437 and has no direct auth check, so no edit.

## Scope amendment required (orchestrator disposition) — the last open item

**`tests/test_tui_polish.py`** and **`tests/test_warn_contract.py`** are changed and are **not** in the brief's
exclusive write-set. Both are direct importers of the code this slice changes (`setup.readiness`, `setup.doctor`,
`setup.auth_served` through `agent_home`), and both need a fixture default for R-8:

- `test_tui_polish.ClosingLineTests`: `readiness` now judges `agent_home(os.environ)` (R-1); with an empty or unset
  `CODEX_HOME` that is `private_codex_home()`, which the fixture's `codex_home` patch cannot intercept, so the
  runner's real data root (and an inherited `CODEX_API_KEY`/`OPENAI_API_KEY`) can decide the auth item. The fixture
  pins `XDG_DATA_HOME` into its root and clears the provider variables (`fixture_home()`, shared by the two
  real-readiness tests).
- `test_warn_contract.DoctorWarnTests`: `doctor`'s new profile line (R-5) reads `private_codex_home()/config.toml`
  when `CODEX_HOME` is empty. `setUp` pins `HOME`/`XDG_DATA_HOME`/`XDG_CONFIG_HOME`/`CODEX_HOME=''` in a temporary
  root; the readiness list itself is stubbed.

No assertion was weakened and no production behavior changed for either; both reproductions pass (Checks).

**The eighth review put this explicitly in the orchestrator's hands** — acceptance: "The orchestrator must
authorize or reassign these changes while preserving R-8 isolation; reverting them reopens verified fixture
regressions"; code: "The orchestrator must authorize the two fixture files or arrange separately owned integration
that preserves their isolation" and "another worker repair cannot resolve the ownership conflict alone."

**This is the one item the worker cannot close.** The requirement pair is contradictory on its face: the write-set
must be exclusive (`git diff --stat <base>` lists only it) *and* those two fixtures must isolate the home they now
depend on. Visit 8 shipped the reverted state (write-set clean) and the review rejected it for the R-8 regression;
visits 4-7 shipped the isolated state and the review rejected it for the write-set. No third state exists — the
isolation cannot move into a write-set file (neither module imports an editable test helper; a module-level
`os.environ` mutation would be a test-only bypass, as would shaping the product to a patched `codex_home`).
**Disposition needed:** amend this slice's write-set with these two fixture defaults (≈12 + ≈16 lines, no assertion
changes), or reassign them to `s2b3`, whose write-set already covers the same `setup.py` `readiness`/`doctor` area
and the same docs.

**A third file is a recommended, separately-owned follow-up, not changed here: `terminal_planner/agent_profile.py`.**
The visit-6 lock escape is fixed at the only production caller this slice owns (`setup.native_environment` refuses a
non-regular lock entry), but the root cause is `agent_profile._open_lock`, which opens the lock with `path.open("a")`
and so follows a symlink (`O_NOFOLLOW` would end it). `agent_profile.py` belongs to s2b1 and is explicitly outside
this slice's write-set, so it is escalated rather than edited; if the orchestrator prefers the root-cause fix, it
should be authorized as an amendment to s2b1 (three lines plus its own lifecycle test), and the `setup.py` guard
can then be dropped.

## Edited existing assertions

No assertion weakened, no test-only bypass:

- `tests/test_agent_profile.py` — `ScopeTests.test_only_the_module_itself_mentions_agent_profile` renamed to
  `test_only_setup_and_the_module_itself_mention_agent_profile`; expects `["agent_profile.py", "setup.py"]`. Lifecycle
  assertions unchanged.
- `tests/test_setup.py` — `DoctorTests.setUp` pops `CODEX_API_KEY`/`OPENAI_API_KEY`; the override doctor ok-line now
  expects `(your $CODEX_HOME, not zplan's profile)` and `assertNotIn("профиль zplan", …)`; the no-`CODEX_HOME` section
  expects `CODEX_HOME <private> (zplan)`, `нет login … <private>`, `профиль zplan: not written yet …` and, after
  `agent_profile.ensure(private)`, `профиль zplan: profile N …`.
- `tests/test_tui_polish.py` — only `ClosingLineTests.test_a4_a_failing_remedy_is_only_named_when_its_key_is_enabled`
  and `test_a4_an_environment_key_auth_item_is_not_told_to_run_the_login` wrap their real readiness call in the
  class's shared `fixture_home()` (`XDG_DATA_HOME` into the fixture root, `CODEX_API_KEY`/`OPENAI_API_KEY` cleared) —
  R-8 determinism, since an empty `CODEX_HOME` makes `agent_home` bypass the `codex_home` patch. Assertions unchanged.
- `tests/test_warn_contract.py` — only `DoctorWarnTests` gained a `setUp` pinning `HOME`/`XDG_DATA_HOME`/
  `XDG_CONFIG_HOME`/`CODEX_HOME=''` inside a temporary root (R-8). Neither `doctor` nor the assertions changed.

## Base replay (A-8)

Method: a scratch copy (`.git`/`.tools`/`__pycache__` excluded), each tracked file restored to its base content with
`git show HEAD:<file>`, the new module kept; then
`TMPDIR=… PYTHONPATH=.:tests python3 -m unittest tests.test_agent_activation.OverrideTests
tests.test_agent_activation.FreshInstallTests tests.test_agent_activation.AuthTests
tests.test_agent_activation.ExplicitBinaryTests tests.test_agent_activation.EndToEndTests` → **11 failures, 0 errors**
(`Ran 15 tests`). Every one fails at a behavioural assertion (no `AttributeError`/`Blocked` error):

- A-3 ×2 — `'your $CODEX_HOME' not found` (the base doctor item names the override differently); an empty
  `CODEX_HOME` resolves to `~/.codex`, not private.
- A-4 ×1 — `native_environment()["CODEX_HOME"]` is `~/.codex`, not private.
- A-6 ×5 — three file-auth verdict rows `((False,'l'),False,False) != ((True,None),True,True)`; the spawned child's
  `CODEX_API_KEY` is `None`, not the OPENAI sentinel; the device argv ran with `~/.codex`.
- Explicit binary ×2 — the driver env is `None` (R-1 finding 1).
- A-7 ×1 — the attempt/`engine_env` home is `~/.codex`, not private.

A-3s is excluded (status on the base calls no `ensure`), guarded by mutation (j) alone.

`OwnerHomeAliasTests` is excluded too but for a different reason: it exercises the visit-5 candidate-only
`setup.launch_home`, so on the base the guard does not exist and the destructive write really happens. It is guarded
by mutations `n1`-`n3` instead.

## Mutation table

Each mutation applied to a scratch copy (pristine files restored between rows); the named test must fail. All
twenty-three rows were **KILLED** (exit 1); the reason is an assertion (or, for `m/m2`, `unexpectedly None`)
throughout. Rows `n1`-`n3` are the visit-5 owner-home alias guard; `n4`-`n5` the visit-6 lock guard and the
`os.path.realpath` owner resolution; `m1`-`m2` the visit-7 doctor guard and the child-mapping order.

| M | Mutation | Named test |
| --- | --- | --- |
| a | `ensure` under an override (`if profile:`) | `OverrideTests.test_a3_an_override_home_is_never_written_…` |
| b | `ensure` only when the override differs from the private home | same A-3 test |
| e | fall back to `~/.codex` when the override is empty | `…test_a3_the_empty_override_…` |
| f | drop both key branches from `auth_served` | `AuthTests.test_a6_file_auth_verdicts_…` |
| f2 | treat `CODEX_API_KEY=""` as absent | same A-6 verdicts test |
| f3 | no `child_auth_env` in the architect turn | `…test_a6_the_architect_child_env_mirrors_…` |
| g | swallow `setup.agent_home` in `attach_tools` | `SurfacingTests.test_a4b_a_profile_refusal_reaches_…` |
| i | `doctor` calls `ensure` (unguarded) | `…test_a3_an_override_home_is_never_written_…` |
| j | `status` with `profile=True` | `StatusTests.test_a3s_status_writes_nothing_…` |
| k | `login` calls `ensure` directly as well | `…test_a3_the_empty_override_…` |
| a2 | drop the thread-home persistence (`current["codex_home"]`) | `EndToEndTests.test_a7_a_fresh_install_records_…` |
| b2 | drop the resumed recorded-home env in `_turn` | same A-7 test |
| b3 | drop the resumed recorded-home env in `_turn` | `EndToEndTests.test_a7_a_record_still_spawns_…` |
| i2 | `doctor` calls `ensure` guarded by `not os.environ.get("CODEX_HOME")` | `DoctorTests.test_the_default_home_doctor_writes_no_profile` |
| m | `attach_tools` returns early for `--native-binary` (`if fixture or explicit`) | `ExplicitBinaryTests.test_r1_a_native_binary_launch_still_uses_…` |
| m2 | same, explicit override | `ExplicitBinaryTests` |
| a3 | drop `codex_home` from the attempt writer (runs.py start) | `EndToEndTests.test_a7_a_fresh_install_records_…` |
| n1 | drop the alias refusal in `launch_home` | `OwnerHomeAliasTests` (both alias tests) |
| n2 | refuse only an exact match, not a home inside `~/.codex` | `…test_r1_a_parent_symlink_into_the_owner_codex_home_is_refused` |
| n3 | apply the refusal to an explicit `CODEX_HOME` too | `FreshInstallTests.test_a4_an_explicit_owner_home_is_used_and_gets_no_profile` |
| n4 | drop `_refuse_escaped_profile_lock` from `native_environment` | `OwnerHomeAliasTests.test_r1_a_symlinked_profile_lock_does_not_write_outside_the_private_home` |
| n5 | `Path.resolve()` for the owner home with no failure handling | `OwnerHomeAliasTests.test_r1_a_looping_owner_codex_home_does_not_break_a_launch` |
| m1 | drop the `OSError` guard around `written_version` in `doctor` | `DoctorTests.test_the_default_home_doctor_survives_an_unreadable_profile_entry` |
| m2 | `child_auth_env` before `check_home` in `_turn` (the visit-7 conflict) | `AuthTests.test_a6_a_codex_key_env_provider_is_refused_before_a_resumed_child` |

## gate7 A binding note — confirmed

`native_environment` calls `agent_profile.ensure(private_codex_home())` exactly when
`os.environ.get("CODEX_HOME")` is empty or unset (setup.py:290), after `check_installation` and before the env is
returned; it is skipped for any non-empty value, `<private_codex_home()>` included.

## Checks run

- DoD targeted command (14 modules) plus `tests.test_tui_polish`: **OK (430 tests, 5 skipped)** in 422 s,
  Python 3.9.6 — re-run in visit 10 on the unchanged visit-9 state (visits 7/8/9: 411 s / 452 s / 431 s, all OK).
  Includes the two visit-7 regressions; no error in any run.
- Visit 9 (isolation restored): the reviewer's two reproductions pass — the seeded-`auth.json`, `CODEX_HOME=''` case
  returns `([False, 'l'])`, and a `written_version` spy over `DoctorWarnTests` shows both reads inside the fixture
  `TemporaryDirectory` roots, never the inherited `XDG_DATA_HOME`.
- Visit 9: `git diff --stat HEAD` lists the write-set plus the two scope-amendment fixtures (see the scope section);
  `git diff --check` clean, catalog `docs current`, `devtools/export_check.py` exit 3 with 0 findings on HEAD.
- Visit 6: the lock-symlink repro (`~/.codex/unexpected-lock-target`) is refused end to end and neither tree
  changes; a looping `~/.codex` keeps every launch working into the private home; the instrumented `Path.exists`
  run of `test_a4_an_environment_key_auth_item_…` under an inherited `XDG_DATA_HOME` touches no path outside its
  fixture.
- Both importer regressions were re-derived while the fixtures were edited (visits 4-7); visit 8 reverted both files
  to base, so those fixture-level results are historical. At base content they still pass under the run's own
  environment (see the visit-8 Checks bullets); only the explicitly empty-`CODEX_HOME` case re-opens the R-8 gap.
- The P1 alias is refused and the owner's tree is byte-identical, reproduced end to end for a `codex-home` symlink
  and for a `planning-kit` symlink (both with `CODEX_HOME` unset and empty); the explicit `CODEX_HOME=~/.codex`
  opt-in still launches and gets no profile (A-4, `FreshInstallTests`).
- `python3 -m terminal_planner.catalog --check docs/REFERENCE.md` → `docs current` (exit 0); `git diff --check`
  clean.
- `python3 devtools/export_check.py` → exit 3, `0 findings`, `private-term rule skipped` (it reads a commit and so
  omits the untracked module). Applying the module's `CONTENT_RULES` directly to `tests/test_agent_activation.py`,
  `docs/INSTALLATION.md` and `terminal_planner/cli.py` reports **0 findings** each.
- Mutations: 23 rows killed (table above); the reviewer's `CORP_KEY` reproduction passes. Visit 5 added three of
  the alias guard (dropping the refusal in `launch_home` → 2 failures, narrowing it to exact equality → the
  parent-alias test fails, dropping its implicit-only condition → the A-4 explicit-owner-home test fails); visit 6
  added `n4`/`n5`; visit 7 adds `m1` (the doctor `OSError` guard) and `m2` (`child_auth_env` before `check_home`).
- Visit 7: the two new regressions were re-derived in a scratch copy — each fails on the pre-fix candidate (the
  doctor test at its `not written yet` assertion, the auth test at `Blocked not raised`) and passes on this
  candidate. The doctor repro (`config.toml` as a directory) now returns 1 and prints the `Профиль процесса` line
  that the base also printed.

## Size (over 600 — reported per the brief)

Measured with `git diff --numstat HEAD` (tracked) plus the new untracked module, receipt excluded:

- tracked: 258 insertions + 81 deletions across 11 files = **339** changed lines;
- new `tests/test_agent_activation.py`: **873** lines (one file, untracked at review time);
- **total 1212 changed lines** (258 + 873 = 1131 insertions only).

Against the brief's ~510 estimate this is above 600 by either measure, so the merge needs explicit critic
disposition (ORCHESTRATOR step 1). The test module is the overrun: A-6 and A-7 are behavioural (real
scripted-codex processes behind a spy; A-7 also runs a real approved plan and attempt), so the module carries a
full harness before its first assertion, and A-6 needs seven file-auth verdicts, the env-key branch, the
`CODEX_API_KEY`-env provider parity turn, the child-env mapping at the spawn, the pre-child refusal, the leak check
and the `[l]`/`[i]` branch. Product (+155) and docs (+58) stay near their estimates. Trimming would drop boundary
cases the parent names, so the suite is kept whole.

## Interpretations

Recorded in the module docstring of `tests/test_agent_activation.py`:

- `agent_home(env)` resolves an override exactly as `codex_home` does; the A-4 regression asserts only through
  production entry points (so it replays on the base), while `setup.agent_home` and `setup.child_auth_env` are
  checked in separate unit classes.
- The `--native-binary` route is read as still a launch of the *product*: it carries `agent_home(os.environ)` even
  though no pinned tool is resolved, so R-1 holds on that route too.
- A-6's "same verdict in doctor, `default_prepare` and a resumed turn" is the doctor auth item, the
  `Blocked`/success of `default_prepare` for a new thread, and a resumed `check_home` outcome (a `Blocked` counts as
  "unserved"); all three share `setup.auth_served`.
- A-4's "a CLI planning prepare and an attempt start" is the captured engine/driver closures of a real `cli.main([])`.
- A-7 records and spawns real turns; the stored session, the persisted attempt binding and the spawned
  `CODEX_HOME` are observed, and the expected private path is computed from the fixture layout, not from a helper.
- The doctor profile line is asserted on its `profile … (packaged …)` / `not written yet …` text only.
- `cli.Terminal` binds `sys.stdout` at import, so entry points are captured by replacing the class; `Screen.ask`
  raises `EOFError` (a real terminal at end of input) so a wrongly-continuing path fails the assertion; the R-8
  sentinel comparison lives in `tearDownModule`.
- Two *importer* fixtures carry the R-8 fixture default the new home/auth behaviour needs (`test_tui_polish.
  ClosingLineTests`: clear the provider variables and pin `XDG_DATA_HOME`; `test_warn_contract.DoctorWarnTests`: pin
  `HOME`/`XDG`/`CODEX_HOME`). Both files are outside the exclusive write-set; this is the flagged scope amendment
  (scope section) — not a test-only bypass and not a weakened assertion. Visit 7 also
  guards `doctor`'s read of an unreadable entry (a *directory* named `config.toml`): the fix lives in `doctor`, not
  in `agent_profile.written_version` (which stays s2b1's), and the failed read is answered as R-5's "not written
  yet" branch — R-5 derives the informational line from `written_version`'s return alone (a version, or "not
  written yet") and does not name an unreadable entry, so no new wording is invented.
- The visit-7 R-4/A-6 vs R-4b resolution is recorded in
  `AuthTests.test_a6_a_codex_key_env_provider_is_refused_before_a_resumed_child`'s docstring: a turn's auth verdict
  is judged on the owner's own env (R-4's unconditional env-key rule), before the child mapping; R-4b is scoped to
  the OPENAI_API_KEY *file*-auth route, so `child_auth_env` shapes the child's env only and never turns an
  "unserved" verdict into a completed turn.
- The owner-home alias refusal (visit 5, the P1 finding) is recorded in `OwnerHomeAliasTests`' docstring: only the
  implicit home is judged (an explicit `CODEX_HOME=~/.codex` stays A-4's opt-in); the refusal reuses the existing
  `setup.agent_home` family (R-3c already routes it to `attach_tools`, `zplan login` and `default_prepare`) rather
  than adding a catalog id; `doctor`/`readiness` stay read-only and do not refuse; and the `--native-binary`
  development route is refused too, because `setup.launch_home` is shared with `native_environment`.
- The visit-6 decisions live with their regressions: the profile-lock confinement is a refusal (not a silent
  workaround) scoped to the implicit home, because only there does `native_environment` write a profile, and the
  lock entry's name stays `agent_profile.LOCK_NAME`; and the owner-home comparison uses `os.path.realpath` so a
  broken `~/.codex` cannot crash a launch — such a path is not a usable Codex home, so the alias check simply does
  not fire and zplan keeps its own private home.
