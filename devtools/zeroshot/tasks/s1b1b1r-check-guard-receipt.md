# s1b1b1r-check-guard — receipt

- Base commit: `7f7503b9d1791d14a33de5c4c1c05002f80fd23f` (the checkout HEAD, branch `zs-s1b1b1r-check-guard`).
  `main` `84a17f9175b0d03b1efafa45ed153825db65b9fe` is one doc-only commit ahead (`84a17f9`, the critic session
  rotation of `devtools/zeroshot/ORCHESTRATOR.md`), outside the write-set; nothing was restored to match a revision.
  Every line the brief cites was re-checked on the base.
- Brief sha256: `c460dac905601bb96543cd7ddacb0ba30c562b3dc96962f52af3ce4c6c438e05`.
- Write-set (`git status --porcelain`): `terminal_planner/checks.py` (modified), `terminal_planner/check_guard.py`
  (new), `tests/test_checks.py` (modified), this receipt. `git diff --stat 7f7503b` lists no other file; no `sweep`
  symbol in `checks.py`; `git diff --stat main` adds only `devtools/zeroshot/ORCHESTRATOR.md` (main's own doc commit).
- Measured size (base `7f7503b`, receipt excluded; `+/-` are added/removed lines; measured after the repair of the
  third review round):
  - product: `checks.py` +444/−97, `check_guard.py` +348/−0 → 792 added, 97 removed, +695 net.
  - tests: `tests/test_checks.py` +1205/−4 → 1201 net (33 new tests, 16 existing ones kept).
  - Brief estimate product ~300, tests ~550 → over by ~492 (added; ~395 net) and ~655. Rationale: the reduced design
    still needs the whole two-session guard surface of parent M-1..M-5 (options, lifeline `S`/`F`/`X`/`D`, deadline,
    R-2/R-K release) in a stdlib-only file, plus the lease lifecycle with the `O_EXCL` collision retry, the
    lifeline-driven `_read`, the confirmed/unconfirmed stop (`_reap`, `ORPHANS`, `ABANDONED`), the owning lock handle
    (R-D) and the framed environment handoff (`_frame`/`_handover`, the explicit resolution of the A-G/R-1 conflict,
    repair round 2), with the D-before-EOF-before-frame precedence (repair round 3) — and the repository's convention
    of docstrings that carry the rule citations. The tests are 33
    methods, several multi-scenario (the collision test = 3 entry types + exhausted; the unconfirmed stop = 2 holds +
    control; the removal order = 4 cases; the worst-case filesystem case = 3 holders). This is above the estimate, so
    it carries an explicit critic disposition (ORCHESTRATOR step 1) before merge.
- Tests reused/adapted from `a9107fc` (the reference for the guarantees kept here only): the `Fixture` child/spy/wait
  helpers (`spawn`, `controller`, `until`, `alive`, `group_gone`, `pids`, `lines_from`) and the `QUALIFY`/`DIRECT`/
  `LEASED` controller bodies; `HardKillTests` H-1/H-2/H-3/H-3b/control (structure and checks) from its
  `HardKillTests` (this round's queued-frame regression reuses the H-3b manual-lease fixture shape);
  `LeaseTests.test_a_killed_zplan_never_removes_the_project_a_check_runs_in`,
  `test_a_killed_zplan_removes_a_leased_checkout` and the collision test
  `test_a_name_collision_never_touches_an_entry_the_lease_does_not_own` (kept verbatim in oracle) from its
  `LeaseTests`; `DeadlineTests.test_the_deadline_kills_group_c_and_reports_timeout` from its `DeadlineTests`;
  `ExceptionTests.test_a_cleanup_oserror_never_replaces_the_original_exception` from its
  `test_a_removal_oserror_never_replaces_the_original_exception`; `UnconfirmedTests` from its `UnconfirmedTests`;
  `test_a_popen_that_raises_leaves_the_process_untouched` from its `test_a_popen_that_raises_releases_every_acquired_
  descriptor`. The `ORPHANS`/`ABANDONED`/`REAP`/`GUARD`/`LEASES` names, `forget_after_remove`, `release_after_remove`
  and `after_report` follow its shapes; its identity/retry descriptor architecture (`a9107fc` checks.py:112-165,
  check_guard.py:314-357, `_Fd`/`_descriptor`/`_release`/`_owned`) is not carried.
- Edited existing tests (`tests/test_checks.py`): only the module docstring and the import line (`importlib.util`
  added), plus the one env oracle amendment at base line 124 (`shown - set(environment)` widened to
  `{__CF_USER_TEXT_ENCODING, LC_CTYPE}`); its other assertions (every sanitized key visible; the planted
  `HOME`/`GIT_DIR`/`SECRET_TOKEN` absent) are unchanged, as are all other base oracles and the `popen`/argv spy
  assertions. The fixture helpers this slice *adds* (`spawn`, `controller`, `until`, `alive`, `group_gone`, `entries`,
  `checkouts`, `pids`, `holds`, `forget`, `hook`, `lines_from`, `exited`) have no base oracle; `group_gone`'s oracle
  was corrected in the repair round (`ESRCH` alone, as the review demanded) and `holds` moved from
  `UnconfirmedTests` to the fixture so `LeaseTests` can use it too. Repair round 2 touched only assertions this slice
  itself added: the A-K close spies spy `checks._Lock.close`/`guard._Lock.close` (the owning handle, R-D) instead of
  `os.close`, the collision and guard-child fixtures register an owning handle, and
  `test_a_leased_checkout_hands_its_lease_and_lock_fd_to_the_guard` now also asserts the registered lease is a
  `checks._Lock` whose `fileno` is what travels. Repair round 3 added the module-level helpers `load_guard` (the guard
  loaded in-process by absolute path, stdlib only) and `frame` (one `E` lifeline line from a mapping), moved
  `RuleTests.test_only_esrch_proves_the_group_is_gone` onto `load_guard`, and strengthened the NUL test with the
  `socketpair`/`popen` spies above; no base oracle was touched.
- A-7 (H-1 on the base `s1b1` code, in a scratch copy of the checkout: base `checks.py`, no `check_guard.py`, this
  module, Python 3.13.3; re-measured after repair round 3 — the counts follow this module, so they move with it):
  `Ran 49 tests … FAILED (failures=15, errors=13, skipped=2)`, 19 passed. H-1
  (`HardKillTests.test_a_hard_kill_of_zplan_reaps_group_c_and_removes_the_checkout`) fails by the named assertion
  `False is not true : group C <pid> still runs` (the base has no guard, so the killed zplan leaves group C and the
  checkout). Named failures (15): the six `HardKillTests`
  (H-1/H-2/H-3/H-3b/control, plus this round's queued-frame regression, which finds no guard to run),
  `LeaseTests.test_a_killed_zplan_never_removes_the_project_a_check_runs_in`/
  `test_a_killed_zplan_removes_a_leased_checkout`/`test_a_name_collision_never_touches_an_entry_the_lease_does_not_
  own`/`test_group_c_holds_the_lease_lock_the_guard_handed_over`,
  `DeadlineTests.test_the_deadline_kills_group_c_and_reports_timeout`, `RemovalOrderTests.test_a_failed_exclusive_
  create_unlinks_nothing`/`test_the_guard_releases_a_lease_in_the_same_order`/`test_a_failed_removal_keeps_the_sidecar_
  in_the_guard`, and `SpawnTests.test_a_nul_argv_element_is_refused_before_anything_is_created` (its early-refusal
  spies show the base made a pair and a spawn before the NUL was refused — it failed as an error until repair
  round 3 raised it ahead of the `ORPHANS` access). Named errors (13, the base has no
  `ORPHANS`/`LEASES`/`REAP`/`GUARD`/`_remove`, so `patch.object` raises): the three `ExceptionTests`,
  `LeaseTests.test_a_leased_checkout_hands_its_lease_and_lock_fd_to_the_guard`,
  `LeaseTests.test_a_name_collision_never_touches_an_entry_the_lease_does_not_own` (its symlink subtest only),
  the four `RemovalOrderTests` that patch `_remove` (the abandoned pair, the two failed-removal cases and the
  checkout-exit order), the three `UnconfirmedTests` and
  `SpawnTests.test_a_missing_executable_reports_spawn_failed_and_leaves_no_guard`. Skips (2):
  `RuleTests.test_only_esrch_proves_the_group_is_gone` and `RuleTests.test_a_queued_frame_never_beats_an_observed_eof`
  skip because the base has no `check_guard.py` to load (`skipUnless`, so the module still imports on the base).
- Mutation table (each killed by a scratch-copy run of the named test; the ones with a check mark were reproduced
  here, the rest are killed by the same named test by construction):
  - (a) guard ignores lifeline EOF → `test_a_hard_kill_of_zplan_reaps_group_c_and_removes_the_checkout` ✔ (checkout survived);
  - (b) guard exits after `X` → `test_a_hard_kill_during_the_grace_reaps_a_surviving_descendant` ✔ (group C survived);
  - (c) check spawned in the guard's own group → `test_the_deadline_kills_group_c_and_reports_timeout` (no `X timeout`, guard dead);
  - (d) a lost lifeline at `S` answered `done` → `test_a_death_before_the_send_still_reaps_group_c_and_removes_the_lease` ✔ (pair survived);
  - (e) guard removes cwd without a lease → `test_a_killed_zplan_never_removes_the_project_a_check_runs_in` ✔ (project deleted);
  - (f) lease looked up by name prefix → the same direct-call test (the `checkout-direct` project would be leased);
  - (g) lock fd not passed with the lease, in the *guard's* own `Popen` (`pass_fds=()`) → `LeaseTests.test_group_c_holds_the_lease_lock_the_guard_handed_over` ✔ (with the guard dead only group C can hold the lock; the test-side `flock` succeeded, so the mutation is killed. Reproduced; the earlier claim that the two unconfirmed-stop tests covered this was wrong: their `flock` observes the *guard's* copy, so they cannot see group C's inheritance);
  - (i) `F` reported as an exit status → `test_a_missing_executable_reports_spawn_failed_and_leaves_no_guard`;
  - (j) EOF after `D` read as a death → `test_checks_run_in_profile_order_and_qualify_returns_the_identities` (the checkout vanishes between two checks of one `qualify`);
  - (n) `_reap` timeout treated as confirmed → `test_an_unconfirmed_stop_after_an_x_zero_returns_timeout` ✔ (status 0 instead of `timeout`);
  - (q) a cleanup `OSError` replaces the original → `test_a_cleanup_oserror_never_replaces_the_original_exception` ✔ (`OSError` escaped, `ValueError` gone);
  - (y) an unconfirmed stop returns the `X` status → `test_an_unconfirmed_stop_after_an_x_zero_returns_timeout` ✔;
  - (z) the orphaned guard never polled (`_drain` replaced by `ORPHANS.clear()` under the lock) → `test_an_unconfirmed_stop_after_the_spawn_returns_timeout` and `test_an_unconfirmed_stop_after_an_x_zero_returns_timeout` ✔ (both fail on `guard_process.returncode is None`: the guard is still an unreaped zombie after the next entry. Reproduced; the earlier pair of tests polled the guard themselves, which reaped it and hid this mutation);
  - (z3) the lock fd closed before the unlink → `test_the_checkout_exit_removes_the_directory_then_the_lock_then_the_fd` ✔ (order `close, remove, close, unlink`).
  - (rx) the parent's own lifeline copy closed without swallowing a cleanup `OSError` → `ExceptionTests.test_a_cleanup_
    oserror_on_the_lifeline_copy_never_replaces_the_original` ✔ (the injected `OSError(EIO)` escaped instead of the
    original `ValueError`);
  - (rk) a failed directory removal answered as done (both `_remove`s report success, so every holder unlinks the
    sidecar) → `RemovalOrderTests.test_a_failed_removal_keeps_the_sidecar_of_the_checkout_exit`/`..._in_the_guard`/
    `..._of_an_abandoned_pair` ✔ (each recorded `remove, unlink, close`: the lock pathname was unlinked although the
    directory survived; reproduced once per holder);
  - (r2) the guard's group-gone probe reads every `OSError` as gone → `RuleTests.test_only_esrch_proves_the_group_is_
    gone` ✔ (one `killpg` probe instead of the bounded wait; reproduced in-process);
  - (r3) the framed environment handoff removed (the guard keeps only what its interpreter received) → `Environment_
    Tests.test_every_name_of_the_handed_over_environment_reaches_the_check` ✔ (both modes lose
    `__PYVENV_LAUNCHER__`; reproduced, and reproduced independently before the fix);
  - (r4) a raw descriptor kept instead of the owning handle: `LEASES[key] = lock.fileno()` → `LeaseTests.test_a_
    leased_checkout_hands_its_lease_and_lock_fd_to_the_guard` and `RemovalOrderTests.test_the_checkout_exit_removes_
    the_directory_then_the_lock_then_the_fd` ✔ (the first fails the representation assertion, the second never sees
    the handle close; reproduced); the same in the guard (`pass_fds=(lock,)`, `os.close(lock)`) → `RemovalOrderTests.
    test_the_guard_releases_a_lease_in_the_same_order`/`..._a_failed_removal_keeps_the_sidecar_in_the_guard` ✔;
  - (r5) the owning handle closed before the sidecar unlink → `RemovalOrderTests.test_the_checkout_exit_removes_the_
    directory_then_the_lock_then_the_fd` ✔ (order `remove, close, unlink, close`; reproduced: the (z3) shape, now
    through the handle).
  - (r6) the pre-spawn handoff read the environment frame before the observed EOF (the queued frame wins over the
    peer's end) → `RuleTests.test_a_queued_frame_never_beats_an_observed_eof` and `HardKillTests.test_a_queued_frame_
    after_zplan_is_gone_spawns_nothing_and_removes_the_lease` ✔ (the in-process pair answers `({'A': '1'}, 'run')`
    instead of `(None, 'gone')`, and the guard child's injected `Popen` runs, so the `attempts` file appears although
    zplan is already gone; reproduced, and reproduced independently before the fix);
  - (r7) the early `_refuse_nul` call removed (the NUL reaches `subprocess` late) → `SpawnTests.test_a_nul_argv_
    element_is_refused_before_anything_is_created` ✔ (the socketpair and `popen` spies both fire: `([1], [1])` instead
    of `([], [])`; reproduced, and reproduced independently before the fix).
- R-6 (containment limit, stated, not tested): a check that leaves group C itself (`setsid`, daemonizing) is not
  contained, exactly as in s1b1 — the guard's SIGKILL reaches group C only.
- Parent R-3 guard-kill limit (stated, not tested): the guard can be killed directly (or zplan can die between
  checks), leaving a leftover entry; no immediate cleanup happens then, the directory and lock stay until the later
  recovery (`sweep`, s1b1b2), and a surviving process that still holds the inherited lock fd makes that recovery
  report busy.
- R-D non-goal (stated): a `KeyboardInterrupt` or another asynchronous exception arriving during acquisition or
  cleanup may leak the descriptors of that interrupted call (bounded per call, freed at process exit); it must never
  close a descriptor the process does not own. No identity/retry machinery is carried.
- Interpretations (also recorded in the docstrings of the tests that cover them): the group-gone oracle is
  `ProcessLookupError` (`ESRCH`) alone, in `checks._present`, in `Fixture.group_gone` and in the guard's
  `_await_gone`; a *reaped* leader with no members answers `ESRCH`, while an unreaped zombie member answers `EPERM`
  on macOS (measured here: `killpg(pgid, 0)` → `ESRCH` for a reaped leader with an empty group, `EPERM` for a zombie
  member), so `EPERM` is no proof and the bounded wait continues (an earlier reading that macOS answers `EPERM` for a
  reaped leader was wrong and is corrected here); `_lease` registers its key *inside* the protected block, so a
  failure after the `mkdir` releases the created pair (the A-K "abandoned `_lease` pair"); a removal is confirmed
  only when the directory is really gone, so a failed `rmtree` keeps the lock pathname (R-K) and `_forget`/`_discard`/
  `_release` only unlink after that confirmation. The environment conflict (repair round 2): A-G's "the check sees
  every name of the `env` given to `run_check` with its value" and R-1's plain `env=` cannot both hold, because the
  guard's *interpreter* unsets `__PYVENV_LAUNCHER__` in every child on macOS before `check_guard.py` runs (measured
  here: `env __PYVENV_LAUNCHER__=… python3.13 -c 'import os; print("__PYVENV_LAUNCHER__" in os.environ)'` → False,
  with and without `-I`); the conflict is resolved by framing the mapping on the lifeline (`_frame`, `--await-env`)
  and laying it over the guard's environment (`_handover`, `_inherited`), so additions stay, removals cannot happen
  and `env=` is still what `subprocess` validates. R-D (repair round 2): the lease lock is held by an owning handle
  (`_Lock`, a file object over the descriptor) in `LEASES`, in `checkout` and in the guard; only `fileno()` values
  travel to the spawns, and the handle is what closes last. The env amendment is the one at base line 124.
  The handoff precedence (repair round 3): a queued `D` is a normal end first (M-3), then an *observed* lifeline EOF
  is zplan gone (M-2/H-3b, so no check may be spawned), and only then an environment frame is read (A-G) — a frame
  that arrived behind the peer's EOF was written while the run was alive but says nothing about a run that is over, so
  it cannot revive the spawn. The NUL refusal (repair round 3): the early `_refuse_nul` oracle is "no `socketpair`
  call and no spawn call", spied directly, because a late `subprocess` `ValueError` also creates and closes a pair
  and leaves the descriptor count unchanged — the weaker oracle could not tell the two apart.
- DoD evidence (macOS, Python 3.13.3, a private `TMPDIR` scratch): the worker target
  `PYTHONPATH=.:tests python3 -m unittest tests.test_checks tests.test_live tests.test_process tests.test_toolchain
  tests.test_reference` → `Ran 252 tests … OK` (0 failures, 0 skips); `tests.test_checks` alone → 49 tests, OK.
  `python3 devtools/export_check.py` reports one `state-path` finding on `STATE.md` (pre-existing; `STATE.md` is
  unchanged by this slice) and **no** home-path finding. `tests.test_install` is not run (no packaging or packaged
  resource change).
- Repair of the third review round (phase `after: rejected`): (1) the pre-spawn handoff let a queued environment
  frame win over an observed lifeline EOF, so a check was spawned after zplan was gone (H-3b/M-2); `_handover` now
  reads the queued `D` first, then the observed EOF, and only then the frame, with two regressions
  (`RuleTests.test_a_queued_frame_never_beats_an_observed_eof`, in-process, and `HardKillTests.test_a_queued_frame_
  after_zplan_is_gone_spawns_nothing_and_removes_the_lease`, a guard child whose injected `Popen` must never run);
  (2) `SpawnTests.test_a_nul_argv_element_is_refused_before_anything_is_created` did not fail when the early
  `_refuse_nul` was removed, violating the "each new test fails when its guarded behavior is removed" rule; it now
  spies on `socket.socketpair` and the injected `popen` and asserts neither fired. Mutations (r6) and (r7) are the
  reproductions for these two findings.
- Repair of the second review round (phase `after: rejected`): (1) A-G's lost environment name is resolved by the
  explicit framing above, with `EnvironmentTests.test_every_name_of_the_handed_over_environment_reaches_the_check`
  covering both modes (`env=<mapping>` and `env=None`), and the same-name-plus-value regression proving the removal
  is gone; (2) R-D's representation is fixed by the owning `_Lock` handles in `checks.py` and `check_guard.py`, whose
  `fileno` values are all that travels, with the A-K order preserved (directory → sidecar unlink → handle close) and
  the A-K spies moved onto the handle close. Mutations (r3)-(r5) are the reproductions for these two findings.
- Repair of the first review round (phase `after: rejected`): the four demonstrated violations are fixed at the
  cause — the parent's lifeline copy is closed through `_shut_socket` (R-X); both `_remove`s answer whether the
  directory is really gone and every holder keeps the lock pathname when it is not (R-K); the two unconfirmed-stop
  tests observe the guard's exit with `waitid(WNOWAIT)` and assert the next entry reaps it (A-C/mutation z); the
  group-gone oracle is `ESRCH` in the guard and in the fixture, with `RuleTests.test_only_esrch_proves_the_group_is_
  gone` pinning it (A-H/A-D). New regression tests: `ExceptionTests.test_a_cleanup_oserror_on_the_lifeline_copy_never_
  replaces_the_original`, the three `RemovalOrderTests.test_a_failed_removal_keeps_the_sidecar_*`,
  `LeaseTests.test_group_c_holds_the_lease_lock_the_guard_handed_over` and
  `RuleTests.test_only_esrch_proves_the_group_is_gone`.
- Left to the orchestrator (not claimed here): `devtools/linux-test.sh tests.test_checks` on the Linux test host and
  then the full suite.
