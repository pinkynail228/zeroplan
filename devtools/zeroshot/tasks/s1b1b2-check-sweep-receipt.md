# s1b1b2-check-sweep — receipt

- Base commit: `21e239e9ac50bbc8c9314dcc9dbbb4c180f858b8` (branch `zs-s1b1b2-check-sweep`, = `main` after the
  s1b1b1r-check-guard merge with its s1b1b1r2 repair). Nothing was restored to match `sourceRevision`; the only
  starting material taken from `d2a1669` is the design of the restored `SweepTests` (repaired below), per the brief.
  Every line the brief cites was re-checked on the base: `sweep`/`_sweep_one`/`SweepTests` are absent from the base
  (the s1b1b1r merge deliberately left `sweep` to this slice), the lease pair, R-K order, R-C leftover and the
  `forget_after_remove`/`release_after_remove` seams are as merged.
- Brief sha256:
  `002cf2cb5f784cedb2bdbfdbc31576858126d06a4b494fc0d0c0f0e12da35fbc` (`devtools/zeroshot/tasks/s1b1b2-check-sweep.md`,
  re-hashed on this visit).
- Interpreter: `python3.13 -V` → `Python 3.13.3` (the run's rule; every command below uses it).
- Write-set (`git status --porcelain`): `terminal_planner/checks.py` (modified), `tests/test_checks.py` (modified),
  this receipt. `git diff --stat main` lists only those two files. Untouched: `check_guard.py`, `run_check`, `_read`,
  `_reap`, `_git`, `_prepare`, every other file.
- Measured size (base `21e239e`, receipt excluded; `+/-` = added/removed lines, `git diff --numstat main`):
  - product `terminal_planner/checks.py`: **+171 / −10** (`sweep` + `_sweep_one` + `_owned`/`_lstat`/`_is_regular`/
    `_is_directory` ~120, the two no-op hooks ~8, R-W publication + pre-flock failure ownership in `_lease` ~15,
    R-P ~3, docstrings ~25).
  - tests `tests/test_checks.py`: **+973 / −1** (the −1 is the module import line; no existing assertion line changed).
  - Brief estimate product ~110, tests ~300. Both are over (product by ~60, tests by ~609): the cumulative diff adds
    more than 500 lines, so the overrun is reported here with a rationale and needs an explicit critic disposition
    (ORCHESTRATOR step 1). Rationale: the Acceptance list is 13 named Boundary rows (each wanting its own counts and
    `lexists` checks), the 4-shape × 5-lock-shape matrix, A-S, A-P, A-X (the hard kill and every A-C hold), the A-W
    interleavings 1/2/3 with two separate old-owner processes, and the named states — 32 test methods, several
    multi-scenario — under the repository convention of docstrings that carry class/domain/oracle/interpretation.
    Three repair visits added ten regressions, one per demonstrated rejection class (stale lockless classification,
    classification `OSError`, `_lease`/`_discard` failure ownership, non-blocking acquisition, a busy `.lock`-named
    entry, a failed pre-flock acquisition unlinking another holder, an `O_EXCL` collision never being adopted, and a
    `.lock.lock` orphaned by its base's removal, plus a raw integer carried through `_sweep_one` instead of an owning
    handle). No coverage is padded: each method maps to a stated requirement or to a demonstrated rejection.
- Mutation table (each mutation applied alone to a scratch copy of the tree, `python3.13`, the named test re-run;
  `KILLED` = the test fails with the mutation). Rows (r3)–(r7) were added by the repair visits — see "Repair history".

  | # | mutation (edit to the candidate) | killed by (named test) | observed |
  |---|---|---|---|
  | h | `_sweep_one`: drop the `flock(LOCK_EX\|LOCK_NB)` | `test_sweep_removes_unheld_leftovers_and_reports_a_held_lock_busy` | FAIL |
  | r | `_sweep_one`: `if False` in place of the post-flock `_owned` re-verification | `test_a_publication_between_sweep_open_and_flock_is_never_removed` | FAIL |
  | r2 | `_lease`: `if False` in place of the publication `_owned` check | `test_a_sweep_between_lease_create_and_flock_leaves_a_locked_checkout` | FAIL |
  | s | `_sweep_one`: `os.chmod(entry, 0o700)` through a symlink entry before removal | `test_sweep_unlinks_a_symlink_entry_without_reaching_its_target` | FAIL |
  | t | `_sweep_one`: drop the post-removal `_lstat(entry)` re-check | `test_sweep_never_counts_a_failed_removal_as_removed` | FAIL |
  | u | `sweep`: classify any `*.lock` name as a lock (the suffix heuristic) | `test_sweep_removes_a_directory_named_like_a_sidecar_lock` | FAIL |
  | v | `_sweep_one`: leave a symlink entry and still report the unit gone | `test_sweep_never_keeps_a_dangling_lock_link_unaccounted` | FAIL |
  | w | `checkout`: accept a project under the root | `test_a_project_at_or_under_the_root_is_refused_and_creates_nothing` | FAIL |
  | x | `_sweep_one`: unlink the lock before removing the entry | `test_sweep_removes_the_entry_before_its_lock` (also `test_sweep_never_counts_a_failed_removal_as_removed`) | FAIL |
  | z3a | s1b1b1r dependency, `checks._forget`: close the lock handle before the directory removal/unlink (s1b1b1r mutation z3) | `test_an_old_owners_checkout_exit_pauses_for_sweep_and_a_new_acquisition` | FAIL |
  | z3b | s1b1b1r dependency, `check_guard._release`: close the transferred fd before the release (z3, guard half) | `test_the_guards_release_pauses_for_sweep_and_a_new_acquisition` | FAIL |
  | r3 | `_sweep_one` lockless branch: on `FileExistsError`, reopen the name the other actor created and adopt it | `test_a_lock_a_sweep_did_not_create_is_never_adopted` | FAIL |
  | r4 | `_lstat`: swallow every `OSError` as "absent" | `test_a_classification_error_on_a_live_lock_is_busy` | FAIL |
  | r5 | `_sweep_one`: `flock(LOCK_EX)` (blocking) for a sweep-created lock | `test_a_lockless_sweep_creates_its_own_lock_nonblocking` | FAIL |
  | r6 | `_lease`: `_discard` on the pre-flock failure path (unlink without ever holding the flock) | `test_a_failure_before_its_flock_never_unlinks_the_lock` | FAIL |
  | r7 | `sweep`: one pass instead of the repeat-while-progress loop | `test_a_held_lock_orphaned_by_its_bases_unit_is_busy` | FAIL |
  | d | `_sweep_one`: carry the raw `os.open` integer and close it with `os.close` (no owning `_Lock`) | `test_sweep_holds_every_opened_lock_in_an_owning_handle` | FAIL |

  (r)/(r2)/(z3a)/(z3b) are the interleaving oracles A-W calls out; (x) is proven twice (the order spy and the
  "failed removal leaves the lock" oracle); (r3)–(r7) pin the rejections the repair visits answer and (d) pins the
  R-D owning-handle repair. All seventeen
  were confirmed in a scratch copy after each single edit (private `TMPDIR`; the mutation target restored
  afterwards). An A-W(3) reviewer-side reproduction (`_lease` pre-flock failure while a sweep holds the lock) also
  passes on the candidate and fails on (r6).
- A-7 base evidence (candidate `tests/test_checks.py` run against base `main` `checks.py` in a scratch copy; base has
  no `sweep`): the new `sweep` tests are candidate-only (a missing `sweep` on base is not a behavioral failure).
  Existing behavior asserted on base: `test_a_project_at_or_under_the_root_is_refused_and_creates_nothing`
  **fails by its named assertions** on base — the `project = <root>/checkout-p` subTest raises its own
  `self.fail("a project at or under the root was accepted")` (base `checkout` accepts it) and the trailing assertion
  reports `AssertionError: True is not false : something was created under the root` (2 failures, 0 skips; base
  `checks.py` from `git show main:...`, candidate `tests/test_checks.py`). No skips: on this macOS host the
  mode-000-root skip does not trigger (a plain user cannot list a 000 root) and `os.mkfifo` exists.
- DoD checks run on the candidate (this visit):
  - `TMPDIR=<scratch> PYTHONPATH=.:tests python3.13 -m unittest tests.test_checks tests.test_live tests.test_process
    tests.test_toolchain tests.test_reference` → `Ran 284 tests in 203.183s`, `OK` (32/32 `SweepTests`; the five
    pre-existing modules otherwise unchanged; `skipped=0`).
  - `python3.13 devtools/export_check.py` → `summary: 0 findings` (exit 3: the private-term rule is skipped; it
    reads committed HEAD, so committed-candidate export verification stays the orchestrator's).
  - `git diff --stat main` lists only `terminal_planner/checks.py` and `tests/test_checks.py` (+ this receipt when
    added). `git diff --check` → clean; `git status --porcelain` → the two write-set files plus this receipt.

## Repair history

Two rejected review rounds; each demonstrated violation has a named regression test and a killing mutation.

**Repair visit 1** (`phase.after = rejected`, three violations plus the non-blocking and busy-sidecar findings):

1. **R-W/R-4 live-publication deletion** — `_sweep_one`'s lockless branch unlinked whatever name sat at the lock
   path (a stale "lockless" read taken before the act). Repaired by making the branch publish its own lock with
   `O_CREAT|O_EXCL|O_NOFOLLOW`, so an `O_EXCL` collision is one busy and no regular lock is ever cleared.
2. **R-V/R-W classification errors read as "not a lock"** — `_is_regular`/`_is_directory` swallowed every
   `OSError`. Repaired through `_lstat`, which answers `None` only for the two "no such name" errors and lets any
   other `OSError` reach the caller, where `sweep` counts the unit one busy and touches nothing.
3. **R-W failure ownership in `_lease`** — a pre-flock failure must not unlink a live lock. First addressed by
   gating the unlink on an `fstat`/`lstat` identity check.
4. **Non-blocking acquisition** — the lockless branch now takes `flock(LOCK_EX | LOCK_NB)`, never a blocking
   `LOCK_EX`.
5. **Busy `.lock`-named entry preserved** — a `.lock`-named entry whose own lock is held is busy and is not cleared
   by its base's unit.

**Repair visit 2** (`phase.after = rejected`, three further violations):

1. **Identity equality does not establish flock ownership** (`_lease`'s failure cleanup unlinked a lock the sweep
   held, because the inode identity still matched). `_lease` now carries an `owner` flag that only becomes true after
   its *own* `fcntl.flock(...)` succeeds; the `FileExistsError` and `BaseException` paths call `_discard` only when
   `owner`, and otherwise `_shut` (close only this attempt's own handle, unlink nothing). Killing mutation (r6);
   regression `test_a_failure_before_its_flock_never_unlinks_the_lock`.
2. **`O_EXCL` collision must not be adopted** (the interim `_publish` reopened the name another actor had created).
   R-W is explicit: "`O_EXCL` failure when sweep creates a lock → busy." The lockless branch now calls `os.open(lock,
   O_CREAT|O_EXCL|O_NOFOLLOW|O_RDWR, 0o600)` directly; a `FileExistsError` reaches `_sweep_one`'s `except OSError`
   and becomes one busy, leaving the foreign lock intact. Killing mutation (r3); regression
   `test_a_lock_a_sweep_did_not_create_is_never_adopted`.
3. **A held `.lock.lock` orphaned by its base's removal must be counted** — the classification snapshot skips
   `X.lock.lock` as the lock of the entry `X.lock`; clearing `X` with its lock `X.lock` strands it, and the old
   single pass left it uncounted. `sweep` now repeats while a pass removed something, so the newly orphaned name is
   examined and a held one is one busy. Killing mutation (r7); regression
   `test_a_held_lock_orphaned_by_its_bases_unit_is_busy`.
4. **Scope** — the interim `_discard` edit was reverted: `_discard` is byte-identical to `main`
   (`checks._discard`, `_forget`, `_read`, `run_check`, `_remove`, `_shut`, `_shut_fd` all verified identical), so
   the failure-ownership handling lives entirely in `_lease`, inside the permitted write-set.

**Repair visit 3** (`phase.after = rejected`, acceptance: inherited s1b1b1r R-D):

1. **`_sweep_one` carried a raw `os.open` integer** in both acquisition branches and closed it with `os.close`,
   with no transferring spawn — exactly the shape R-D's bare-integer exception does not cover (it allows "an `int`
   closed in exactly one place right after the spawn that transferred it"). Both branches now wrap the descriptor
   in the owning `_Lock` file object (the same handle `_lease` uses), borrow `owner.fileno()` for the `flock` and the
   `_owned` identity check, and close the owner in the `finally` after the unlink — on the success path and on the
   error path alike. Killing mutation (d); regression
   `test_sweep_holds_every_opened_lock_in_an_owning_handle`. (`_shut_fd` is left defined, as in `main`, where it is
   likewise unused; removing s1b1b1r's function would exceed the write-set.)

## Restored tests and what changed in them

`SweepTests` from `d2a1669 tests/test_checks.py:1437-1563` was restored and repaired against R-4/R-V/R-W:

- `test_sweep_removes_unheld_leftovers_and_reports_a_held_lock_busy` — kept; the held lock is now a
  `sys.executable` child holding `flock` on an inherited fd (the brief's helper), the orphan lock is added to the
  fixture, and every touched path is checked with `lexists`. Counts 3 removed / 1 busy then 1 / 0.
- `test_sweep_answers_zeros_for_a_missing_root_and_removes_a_lock_without_its_directory` — split: the missing-root
  part is `test_sweep_answers_zeros_for_a_missing_and_an_empty_root`, the orphan-lock part moved into the A-S core
  test above (an orphan lock is an R-4 unit like any other).
- `test_sweep_never_reports_a_recovery_it_did_not_perform` — repaired into
  `test_sweep_answers_busy_for_a_root_it_cannot_list`. R-4 says "any other type with `unlink`", so a **regular-file**
  entry is now *removed*, not busy as the old oracle asserted; the unlistable-root and not-a-directory oracles are
  kept, and the regular-file entry moved to the matrix (`file` row).
- `test_sweep_unlinks_a_symlink_entry_without_reaching_its_target` — kept verbatim in oracle (target outside the
  root, its modes and content), mutation (s).
- `test_sweep_removes_a_directory_named_like_a_sidecar_lock` — kept, counts adapted to the R-4 rows (2 / 1 then 1 / 0).
- `test_sweep_never_keeps_a_dangling_lock_link_unaccounted` — kept; the count is repaired from 2 to 3: under R-4 an
  R-4 row-2 `.lock` symlink is an entry of its own, so the fixture (a dangling lock link beside its entry + one alone)
  is three units. Mutation (v).

## New tests (candidate-only)

- Boundaries: missing + empty root; unlistable root (regular file, mode-000 root with a skip as root); failed removal
  (root 0500) → busy then removed after restore; symlink entry → target untouched; `*.lock` **directory** with/without
  its own `*.lock.lock` (absent, free, held); `checkout-x` and `checkout-x.lock` both directories → both in one sweep;
  fifo named `checkout-f.lock` (bounded worker thread, never blocks); non-prefixed names and `checkout` without the
  dash untouched; 200 leftovers in one call; the **matrix** (entry = directory/file/symlink/fifo × lock = absent/free/
  held/symlinked/directory).
- Counting/lock order: `test_sweep_never_counts_a_failed_removal_as_removed` (injected `_remove` refusal → busy, the
  lock stays); `test_sweep_removes_the_entry_before_its_lock` (order spy: `["remove","unlink"]`).
- States: a live `checkout` busy → gone after exit; a leftover held by a surviving **group C** after the guard exited
  → busy, then removed once group C is killed.
- A-P: `test_a_project_at_or_under_the_root_is_refused_and_creates_nothing` (mutation w).
- A-W: 1 `test_a_publication_between_sweep_open_and_flock_is_never_removed` (mutation r); 2
  `test_a_sweep_between_lease_create_and_flock_leaves_a_locked_checkout` (mutation r2); 3a
  `test_an_old_owners_checkout_exit_pauses_for_sweep_and_a_new_acquisition` and 3b
  `test_the_guards_release_pauses_for_sweep_and_a_new_acquisition` (both depend on s1b1b1r R-K / mutation z3).
- A-X: `test_a_hard_kill_of_zplan_leaves_nothing_for_a_sweep` (after H-1, no `checkout-*` entry and `sweep` zeros);
  `test_a_sweep_reports_each_unconfirmed_holds_lease_busy_then_removes_it` (both A-C holds: busy while the guard
  holds, then the leftover pair removed, then zeros).
- Repair visit 1 regressions: `test_a_lock_published_after_a_lockless_classification_is_busy`,
  `test_a_busy_lock_named_entry_survives_its_bases_sweep`,
  `test_a_classification_error_on_a_live_lock_is_busy` (r4),
  `test_a_lockless_sweep_creates_its_own_lock_nonblocking` (r5),
  `test_a_failed_acquisition_never_unlinks_another_publishers_lock` (inode replaced after the flock).
- Repair visit 2 regressions: `test_a_failure_before_its_flock_never_unlinks_the_lock` (r6),
  `test_a_lock_a_sweep_did_not_create_is_never_adopted` (r3),
  `test_a_held_lock_orphaned_by_its_bases_unit_is_busy` (r7).
- Repair visit 3 regression: `test_sweep_holds_every_opened_lock_in_an_owning_handle` (d) — every `sweep` descriptor
  is wrapped by an owning `_Lock`, never raw-closed, on the success and the error path.

## Interpretations (silence/ambiguity resolved)

1. **R-4 row 2 counts as its own entry.** A `.lock`-named symlink (live or dangling) or fifo is "a lockless entry"
   per R-4's table and the ordering note ("a directory `X.lock` is handled before `X`'s lock is examined"), so it is
   swept as its own unit, longest-first. Consequently a base entry + a symlinked or directory-shaped lock is **two**
   units (and the dangling-link fixture is three). Recorded in the docstrings of
   `test_sweep_never_keeps_a_dangling_lock_link_unaccounted` and
   `test_sweep_handles_each_entry_shape_with_each_lock_shape`. The unlink R-4's second sentence gives a non-regular,
   non-directory lock *name* is done by that name's **own** unit (which is why the sentence can say "never opened"),
   so the base entry never clears the name itself; a surviving `.lock`-named name is therefore one its own unit could
   not remove, and the base's `O_EXCL` collision makes it **busy**
   (`test_a_busy_lock_named_entry_survives_its_bases_sweep`).
2. **A-W (1): the old owner is a real `checkout` context exited inside the hook.** The hook calls the context's
   `__exit__` once, then enters B under `os.urandom` pinned to the same name; an `_exited` set makes the cleanup
   idempotent.
3. **A-C holds leave the pair on disk.** For both holds, zplan's `_reap` queues `D` before closing, so the guard
   reads a normal end and R-2 does not release; after the guard exits the pair is present with a free lock, so the
   sweep after it reports `removed: 1` (not `0`). Recorded in
   `test_a_sweep_reports_each_unconfirmed_holds_lease_busy_then_removes_it`'s docstring; this differs from the
   brief's line "after the guard exits, sweep removes the leftover pair" only in that *every* hold leaves the pair.
4. **R-D identity amendment.** `_owned` compares `fstat(fd)` with `lstat(path)` (`st_dev`/`st_ino`, regular,
   `st_nlink > 0`) — exactly the amendment the brief grants for establishing lock-path ownership; no
   descriptor-reuse recovery, identity-based close/retry or R-O machinery is added.
5. **R-P message.** The existing `ValueError("root must be outside the project")` now also covers project-under-root,
   so its message is `"root and project must be outside each other"`. No existing test asserts the old text
   (`assertRaises(ValueError)` only).
6. **An unreadable type counts its pair once.** R-V says "any `OSError` on an entry → busy for that entry", and R-4
   makes a `.lock` regular file the *lock* of the entry named without it. So when the `lstat` of a `.lock` name fails
   with anything but "no such name", `sweep` counts **one** busy for the pair and skips the base entry it belongs to —
   counting it twice would report two units where only one pair exists. Recorded in `sweep`'s docstring and in
   `test_a_classification_error_on_a_live_lock_is_busy` (the verifier's reproduction expects exactly `0 removed /
   1 busy` for one injected `EIO` on a live lock).
7. **A pre-flock failure closes only its own fd; the pathname is not its to unlink.** R-W makes a name a lock "only
   for the holder of `flock` on the inode at it"; `fstat`/`lstat` identity proves the path still names this attempt's
   inode, not that this attempt holds the lock. So `_lease` tracks an `owner` flag that turns true only after its own
   `flock` succeeds, and both failure branches `_shut` (close only) when `owner` is false. Recorded in `_lease`'s
   docstring and in `test_a_failure_before_its_flock_never_unlinks_the_lock`'s docstring. `_discard` itself is
   untouched (identical to `main`), so the write-set's "nothing else of s1b1b1r's code" holds.
8. **An `O_EXCL` collision when sweep creates a lock is busy — the name is never adopted.** A stale lockless
   classification is a read taken before the act; the `O_EXCL` create, not that read, decides. Reopening the name
   another actor created could take a lock its creator has not flocked yet, so the collision is one busy.
   Recorded in `_sweep_one`'s docstring and in `test_a_lock_a_sweep_did_not_create_is_never_adopted`'s docstring.
9. **A `.lock.lock` orphaned by its base's removal is revisited.** R-4's snapshot classifies `X.lock.lock` as the
   lock of the entry `X.lock`; once a unit removes `X` and `X.lock`, that name is an orphan lock. `sweep` repeats
   while any pass removed something, so the orphan is examined and a held one is one busy (a lease being acquired).
   Each name is still counted at most once (`counted`). Recorded in `sweep`'s docstring and in
   `test_a_held_lock_orphaned_by_its_bases_unit_is_busy`'s docstring.
10. **`_sweep_one` holds each descriptor in an owning `_Lock`.** R-D's bare-integer exception is scoped to an `int`
    "closed in exactly one place right after the spawn that transferred it"; `_sweep_one` transfers nothing, so both
    of its acquisition branches (`O_CREAT|O_EXCL` for a lockless entry or orphan, `O_RDWR` for an existing lock) wrap
    the `os.open` result in the same owning `_Lock` file object `_lease` uses, borrow `fileno()` for the `flock` and
    `_owned`, and close the owner in the `finally` after the unlink. Recorded in `_sweep_one`'s docstring and in
    `test_sweep_holds_every_opened_lock_in_an_owning_handle`'s docstring.

## Left out (by design)

- The dropped ownership state machine / descriptor-reuse recovery (s1b1b1r R-D/R-X scope, excluded here).
- R-5's rerun gate is a *caller* rule ("a new qualification starts only after `sweep(root)` returns `busy == 0`");
  the caller is s1b2a, so this slice only proves the `busy` semantics (out of scope: calling `sweep` from Delivery).
- R-6 (a check that leaves group C itself) is the parent's, stated not tested.
- The 5-lock-shape matrix uses the four R-4 row-4 entry shapes; the two `.lock`-named entry rows are covered by the
  dedicated directory / dangling-link / both-directories tests rather than repeated for all five lock shapes.
