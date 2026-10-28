# s2a3-architect-home — receipt

Worker receipt for `devtools/zeroshot/tasks/s2a3-architect-home.md` (slice 3 of 3 of `s2a-home-binding.md`).
Repair visit: fixes the two demonstrated violations of the first delivery (unreadable-config refusal; the A-5
integration fixture's logged-out current home).

## Provenance

- Base (the brief's base, `main`): `ac220ece5e077adfd7dea39e1534c727ec999432` (s2a1 merged).
  The checkout HEAD is `08fe3e3` ("Add s2a3-architect-home brief"); the only file between the two is the brief
  itself, so every line cited in the brief was re-read at `ac220ec` and still holds.
- Brief: `devtools/zeroshot/tasks/s2a3-architect-home.md`,
  sha256 `99dc2271a53e1a1fbd7c304f485257e182d158b62bf20b03d67b48d31e807a7d`.
- s2a1's frozen interface used as stated (`s2a1-home-core.md:14-16`): `record_home.effective_home(recorded)`,
  `toolchain.valid_codex_home(value)`, `setup.legacy_codex_home()`. Nothing from s2a2 is used.

## Files (candidate blobs)

| file | blob |
| --- | --- |
| `terminal_planner/architect.py` | `2cb6068dfa02d14a25c6099cd5594df7f90920af` |
| `terminal_planner/tui/chat.py` | `9a33479bb332d4cb01c5ef60b26ee4ebf124d85e` |
| `terminal_planner/catalog.py` | `b806c0e1a1a4c477d6dc979b36ace0cdad5f7f9f` |
| `docs/REFERENCE.md` (generated) | `0b7f5716ac81f27ae9a9e0102e167cdae6da624d` |
| `tests/test_architect_home.py` (new) | `0ab33b66c265c9c772ea7eb50d3f2e7b0c425821` |
| `tests/test_architect.py` (fixture setup only) | `b701cac59c8b3105fb99482e56cff0ba70971d6b` |
| `tests/test_tui_chat.py` (fixture setup only) | `adb02ef10a4198d3874c9b7507e65a8a294f8198` |
| `devtools/zeroshot/tasks/s2a3-architect-home-receipt.md` | this file |

`git diff --stat ac220ec` lists the write-set plus the brief file (170 lines) that `08fe3e3` added on top of the
base. `python -m terminal_planner.catalog --check docs/REFERENCE.md` -> `docs current`.
`devtools/export_check.py` on a private committed candidate copy (never the shared worktree):
`summary: 0 findings`, exit 3 (`private-term rule skipped`) — no home-path finding.

## Repair of the two rejections (both reproduced on the candidate first)

1. R-6 / frozen `check_home` contract — config read failures were answered with the built-in defaults. The old
   `except OSError: provider, auth = "openai", "file"` (and `Path.exists()` swallowing a permission error inside
   `codex_provider`) let a config.toml that exists but cannot be stat'ed or read reach a save and a launch.
   Reproductions on the candidate: a config.toml symlinked into a `chmod 000` directory and a home `chmod 000`
   both answered `None` / `readiness.auth` / `architect.home_lost` and the header `openai`.
   Now the config read decides (`_config_text` / `home_provider`, module level): an existing config that a read
   cannot yield is `readiness.codex_home` for a new thread and for a continuation alike, before any save or
   launch, and the header shows `"?"` for it. Regression:
   `tests/test_architect_home.py:UnreadableConfigTests.test_a_config_that_cannot_be_read_is_refused_for_both_turn_kinds`
   (both turn kinds, 0 Popen, byte-identical files) and the two unreadable shapes added to
   `HeaderHomeTests.test_a5_the_header_falls_back_to_a_question_mark`.
2. A-5 integration fixture — `test_a5_preparation_keeps_a_logged_in_recorded_home` claimed a current home without
   a login while the fixture's `current` home carried `auth.json`, so a mutation making `default_prepare` check
   the current home survived. The test now builds its own genuinely logged-out `logged-out-current` home and
   asserts the precondition (B has no `auth.json`, A has one). The separate logged-in-B control test is kept.
   Mutation `l` below is the reviewer's mutation and is now killed by that test.

## Frozen interface (confirmation)

- `architect.check_home(home, environment, resumed)` — module-level, returns `None` or raises `Blocked`:
  `architect.home_lost` (resumed) / `readiness.auth` (new thread) / `readiness.codex_home` (unreadable config,
  `from codex_provider`) / `architect.invalid_config` (selected profile, R-6). Fixed order: directory (resumed
  only) -> config.toml via `setup.read_toml`, non-empty top-level `profile` -> `architect.invalid_config` ->
  `codex_provider(home)` -> `_auth_present`. It never raises `OSError`: an `is_dir`/`is_file` failure and a
  config that a read cannot yield are both one of the families above.
- `architect._auth_present(home, auth, environment)` — the single private hook (module-level; s2b2 replaces the
  call with `setup.auth_served`). Presence only; no credential file is read, copied or printed.
- `Architect.next_home()` -> `(home: Path, resumed: bool)`, read-only.
- `Architect.reset()` drops `thread_id` and `codex_home`; `ArchitectStore.load` accepts a session without
  `codex_home`, validates a present one (`toolchain.valid_codex_home`, and a home requires a thread; an explicit
  JSON `null` is a present value, so it is corrupt); `persist` writes `thread_id` and
  `codex_home = str(setup.codex_home(self.environment))` in one save; a resumed turn's env is
  `dict(self.environment, CODEX_HOME=str(home))`, a new thread's env is unchanged. `build_argv` is unchanged.
- `tui/chat.py`: `default_prepare` builds the `Architect` first, takes `next_home()`, runs `check_home` for a new
  thread only, and builds the header from that home with the `header_provider` fallback `"?"`;
  `live_header` uses `next_home()` with the same fallback; `ArchitectChat._reset` refreshes the header through
  `_show_header`, so the header shows the current home after Ctrl+R.
- One added module-level seam outside the frozen three: `architect.home_provider(home, text=None)` — the single
  place a config that a read cannot yield becomes `readiness.codex_home`; `check_home` and
  `tui.chat.header_provider` both resolve the provider through it, so the pane and the turn cannot disagree.
  s2b2's `_auth_present` -> `auth_served` swap is unaffected by it.

## A-7 allowed fixture edits (each one listed)

1. `tests/test_architect.py:setUp` — creates the fixture CODEX_HOME directory and puts `auth.json` in it (it
   pointed at a directory that did not exist); the turn home check (R-5) judges presence, so a turn needs one.
2. `tests/test_tui_chat.py:Fixture.__init__` — the same home directory + `auth.json` for every chat fixture.
3. `tests/test_tui_chat.py:max_home()` — an `auth.json` for the 400-character home, whose provider
   (`requires_openai_auth = true`) needs file auth.
4. `tests/test_tui_chat.py:LifecycleGuardChatTests.setUp` — `home.mkdir(exist_ok=True)`: the fixture already
   created that directory; the test only adds its login.

No assertion was changed and there is no test-only bypass in product code.

## Base replay (behavioral)

Private copy of the working tree with the three product files replaced by their `ac220ec` versions
(`$TMPDIR` under `/tmp/zs-agent-…`, the shared worktree untouched):

```
python3 -c 'import shutil,sys; shutil.copytree(".", sys.argv[1], ignore=shutil.ignore_patterns(".git",".tools","__pycache__"))' /tmp/zs-agent-…/base/repo
git show ac220ec:terminal_planner/architect.py > /tmp/zs-agent-…/base/repo/terminal_planner/architect.py      # same for catalog.py and tui/chat.py
TMPDIR=/tmp/zs-agent-… PYTHONPATH=.:tests python3 -m unittest tests.test_architect_home -v
```

Result: `Ran 19 tests … FAILED (failures=30, errors=6)`, every behavioural case failing at its own assertion:

| case | base failure |
| --- | --- |
| A-5 "a continuation in A" spawn (`test_a5_a_continuation_acts_in_the_recorded_home_not_the_current_one`) | `'/…/current-home' != '/…/recorded-home'` (the turn spawned in the current B) |
| A-5 continuation readiness (`…checked_in_its_recorded_home_not_in_the_current_one`) | `'/…/logged-out-current' != '/…/recorded-home'` |
| A-5 integration, recorded A logged in / current B logged out (`…test_a5_preparation_keeps_a_logged_in_recorded_home`) | `'blocked' != 'ready'` (`default_prepare` refuses B's missing login; the prepare/send path never runs) |
| A-5 integration, recorded A lost (`…test_a5_a_lost_recorded_home_never_blocks_preparation_and_ctrl_r_recovers`) | `'blocked' != 'ready'` (Ctrl+R unreachable) |
| A-5 recovery (`…test_a5_recovery_from_a_broken_recorded_home`, both sub-cases) | `'/…/current-home' != '/…/broken-home'` resp. `'/…/gone-home'` |
| A-5 legacy home | `'/…/other-home' != '/…/legacy-home'` |
| A-5 lost-home refusals (4 sub-cases), malformed sessions (6 shapes + the null thread), A-6 profile, A-6 unreadable config | `AssertionError: Blocked not raised` (the turn spawned) |
| new A-6/r-6 regression (`…cannot_be_read_is_refused_for_both_turn_kinds`, 4 sub-cases) | `AssertionError: Blocked not raised` (defaults were substituted, the turn spawned) |
| A-5 new-thread recording, reset | `None != '/…/current-home'`, `'codex_home' unexpectedly found in …` |
| A-5 header / header fallback | `'/…/current-home' != '/…/recorded-home'`, `'openai' != '?'` (missing dir and symlink loop), `AttributeError: 'NoneType' object has no attribute 'home'` (malformed/unknown-profile/dir shapes: `live_header` returned `None`) |

Excluded from the replay (helper unit tests, covered by mutations): `PredicateTests` and the
`config.toml is a directory` header sub-case whose only base symptom is `AttributeError`
(`architect.check_home` absent, `Architect.next_home` absent, `live_header` returning `None`).

## Mutations (candidate copy per row; each killed by a named test)

| # | mutation | named test | result |
| --- | --- | --- | --- |
| a | skip the `home_lost` check (both raises removed) | `ThreadHomeTests.test_a5_a_lost_home_is_refused_before_anything_is_written` | KILLED (`Blocked not raised`) |
| b | check auth before resolving the recorded home (auth of B) | `ThreadHomeTests.test_a5_a_continuation_is_checked_in_its_recorded_home_not_in_the_current_one` | KILLED (refused continuation) |
| c | `persist` without `codex_home` | `ThreadHomeTests.test_a5_a_new_thread_records_the_home_it_started_in` | KILLED (`None != …/current-home`) |
| d | `reset` keeps `codex_home` | `ThreadHomeTests.test_a5_a_reset_forgets_the_home_and_the_next_turn_uses_the_current_one` | KILLED (`'codex_home' unexpectedly found`) |
| e | the check after the session save | `ThreadHomeTests.test_a5_a_lost_home_is_refused_before_anything_is_written` | KILLED (session bytes changed) |
| f | `default_prepare` refuses a lost continuation | `ChatHomeIntegrationTests.test_a5_a_lost_recorded_home_never_blocks_preparation_and_ctrl_r_recovers` | KILLED (`'blocked' != 'ready'`) |
| g | the header shows the current home for a continuation | `HeaderHomeTests.test_a5_the_header_shows_the_home_of_the_next_turn` | KILLED (`current-home != recorded-home`) |
| h | the profile check only on new threads | `ReadOnlyHomeTests.test_a6_a_selected_profile_is_refused_before_any_process` | KILLED (`'readiness.codex_home' != 'architect.invalid_config'`) |
| i | `codex_provider` before the profile check | `ReadOnlyHomeTests.test_a6_a_selected_profile_is_refused_before_any_process` | KILLED (`'readiness.codex_home' != 'architect.invalid_config'`) |
| j | `default_prepare` reads the recorded home's config | `ChatHomeIntegrationTests.test_a5_recovery_from_a_broken_recorded_home` | KILLED (`'blocked' != 'ready'`) |
| k | the header raises instead of falling back | `HeaderHomeTests.test_a5_the_header_falls_back_to_a_question_mark` | KILLED (`'openai' != '?'`, plus errors) |
| l | `default_prepare` checks the current home (the repair finding) | `ChatHomeIntegrationTests.test_a5_preparation_keeps_a_logged_in_recorded_home` | KILLED (`'blocked' != 'ready'`) |
| m | an unreadable config falls back to the built-in defaults (the repair finding) | `UnreadableConfigTests.test_a_config_that_cannot_be_read_is_refused_for_both_turn_kinds` | KILLED (`Blocked not raised`, a launch happened) |
| n | the header bypasses the shared config-read rule (the repair finding) | `HeaderHomeTests.test_a5_the_header_falls_back_to_a_question_mark` | KILLED (`'openai' != '?'` for the symlink loop) |

All fourteen were run under Python 3.13 in one private copy (`copy-repo`, patch, run `tests.test_architect_home`,
restore); `survivors: []`.

## Targeted runs (worker DoD)

```
TMPDIR=/tmp/zs-agent-… PYTHONPATH=.:tests python3 -m unittest \
  tests.test_architect_home tests.test_architect tests.test_tui_chat tests.test_tui \
  tests.test_record_home tests.test_setup tests.test_toolchain tests.test_reference
```

`Ran 301 tests … OK` (19 of them `tests/test_architect_home.py`) on the system Python 3.9, and `Ran 301 tests …
OK` again with `/opt/homebrew/bin/python3.13` (the interpreter `devtools/mac-test.sh` uses). `tests.test_architect`,
`tests.test_tui_chat`, `tests.test_tui`, `tests.test_record_home`, `tests.test_setup`, `tests.test_toolchain`,
`tests.test_reference` stay green (the argv equality tests included). `tests/test_architect_home.py` alone: 19
tests on both interpreters. A first 3.9 run was red only because the scratch TMPDIR was nested one level too
deep for `test_toolchain`'s socket-path limit (the same note `devtools/mac-test.sh` carries); re-run with the
short scratch dir it is green.
- Environment: the pinned dependency (`pyproject.toml`: `textual==8.2.8`) is already installed for both
  interpreters, so the suites run from the checkout with `PYTHONPATH=.:tests`. `install.py` (the private-venv
  installed qualification, A-8) was deliberately not run: it relocates the shared `zplan` launcher, and this
  slice runs beside active parallel nodes; A-8 belongs to the orchestrator on the Linux host.

## Interpretation, size, deferrals

- Interpretations (also recorded in the new module's docstring, which the reviewers inspect): the Popen spy wraps
  and delegates to the real launcher; the header's `"?"` also covers a config a read cannot yield, so the pane
  and the turn agree; `check_home` is the module-level callable; the `home_lost` text names the kind of login,
  never a variable; the required preparation scenario's "current B without one" is a genuinely logged-out home
  built by that test.
- Size: the whole diff except this receipt and the generated `docs/REFERENCE.md` is 812 added and 33 deleted
  lines = 845 changed, above the brief's 600-line stop line (its estimate was ~430). Product ~256
  (`architect.py` 181, `tui/chat.py` 72, `catalog.py` 3), tests ~589 (`tests/test_architect_home.py` 576 with
  19 regression tests, plus 13 fixture-setup lines in `tests/test_architect.py` and `tests/test_tui_chat.py`).
  Reported here for the orchestrator's re-gate rather than absorbed silently: the overage is documentation and
  coverage, the write-set is unchanged, and no file outside it is touched.
- Left to the orchestrator (not marked passed): the full suite at the merge gate, A-8 on the Linux test host, and
  `devtools/export_check.py` on the committed candidate.
- Product input (Zeroshot itself): none this visit.
