# T1 design: stop the growth, keep the oracles, make the gates fast

Status: revision 4 (2026-11-03), after one Goldfish pass on revision 3 (`.local/goldfish/2026-11-03-test-system-r3/`:
2 Blockers and 12-15 Majors per reviewer; section 8 resolves them). Revision 3 planned to delete test areas wholesale;
that part is withdrawn. Roadmap: `docs/plans/2026-11-03-roadmap.md` T1.

Evidence (private, untracked), in `.local/test-review/`:

- `summary.txt`: the numbers below;
- `oracles.py` and `oracles.json`: the assertion inventory;
- `audit-2026-10-28/`: `REPORT.md`, `bugs.jsonl` and `mut.jsonl`, copied from the 2026-10-28 audit.

## 1. Facts

**Size and time.**
- 2540 tests and 65.4 k test lines, against 35.7 k product lines.
- 2649 test-seconds; 17 minutes wall at `-j 3`. On 2026-10-28 the audit measured 412 s for 2303 tests at `-j 8`.
- In-process TUI tests take 46% of the test-seconds.
- 70 tests over 5 s take 641 s (24%); 48 of them are TUI tests.

**Growth and churn.**
- Test lines grow about 1.6 times faster than product lines (audit: 1.59x over 190 merges; R1a: tests +674/-112,
  product +429/-116).
- Every slice adds an acceptance module. R1a added five `test_goldfish_*` modules.
- 1094 of 2498 test names carry a brief-criterion id (`test_c1_...`).
- 127 of the last 400 commits that touch `tests/` change no product file.

**What the assertions pin.** Inventory by syntax only: it does not follow helper methods, so it undercounts.
- 31% of tests hold at least one sentence assertion.
- 12% of assertions pin a state word, an error family or a command.
- 91 of 128 test modules import other test modules.

**What the suite catches.** Audit of 2026-10-28:
- 19 of 20 re-inserted historical fixes caught; 7 of them by exactly one test.
- 7 of the 20 bugs were caught only by in-process TUI tests.
- 44 of 224 seeded mutants survived. Weakest modules: `user_commit` 7 of 14, `check_guard` 6 of 14.

**What it missed.**
- In M0-H1, reviewers found 19 substantive defects after focused suites were green. Only their categories survive:
  merge bypass, data loss, scrubbing, stale verdicts, concurrency, false completed outcomes.
- In R1a, slice S4 removed a still-required behaviour together with its assertion. All gates stayed green; the
  architect caught it while reading the diff.

**Deletion trials of 2026-10-28.**
- v3 cut 741 tests and saved 17% CPU; v4 cut 192 tests and saved 3%.
- Both were unsafe on cold review: they lost distinct checks.
- Prose rules did not change behaviour: after "do not pin wording", 60% of new tests still pinned text.

## 2. Diagnosis

- **The flow is the problem, not the stock.** Each slice adds a module named after its criteria. Neutral changes
  re-pin text instead of unpinning it. An edit may silently drop an assertion.
- **Deleting by area repeats the failed 2026-10-28 trials.** The inventory cannot yet see helper assertions, and the
  TUI tests catch real bugs.
- **Gate time is dominated by a few slow, mostly TUI, tests and a low `-j`.** The many fast tests cost almost nothing.

## 3. Goals and non-goals

**Goals.**
- G1. The stock of sentence assertions, criterion-named tests and test modules can only shrink, unless a contract
  declares a growth with a reason. This is checked mechanically on every slice.
- G2. An assertion removed from an existing test must be declared with the behaviour it no longer protects;
  otherwise the slice is refused.
- G3. Slice gates and the integration run take at most 8 minutes of wall time on this Mac. The slow tests still run
  at release candidates and on store or engine changes.
- G4. The cost is measured in the current runner: test lines per product line, test seconds and sentence-assertion
  delta per slice.

**Non-goals.**
- Wholesale deletion of test areas.
- Black-box TUI scenarios. The revision-2 Blocker stands: the full-screen app has no fixture chat.
- Changing what zplan's workers are told about tests in target projects (a product trade-off for the owner,
  together with R2).
- New dependencies.

## 4. Design

### 4.1 The test ratchet (`devtools/test_ratchet.py BASE HEAD`)

An AST comparison of `tests/` between the slice's base and its result. The slice runner runs it as a gate after
green and before review, and the architect runs it at integration.

It refuses:
- a net increase of sentence assertions (the `oracles.py` classifier, moved into devtools);
- a new test whose name starts with a criterion id;
- a new `tests/test_*.py` module;
- an assertion removed from an existing test.

A contract opts out of a refusal only by naming it:
- `ratchet.new_module = "<reason>"`;
- `ratchet.text_pins = <n>` with a reason;
- `ratchet.removes = ["<test id>: <behaviour removed>"]`.

The reviewer sees those lines. A re-pin keeps the count, so the worker's flow is unchanged; unpinning lowers it.
Superseded on 2026-11-05 (F0, `docs/designs/2026-11-04-w0-worker-contract.md` 3.3): acceptance checks are never
committed; a durable test is part of a change only when its brief asks for one.

### 4.2 Lanes and parallelism

- `tests/lanes.py` marks the slow tests `full` (today the 70 tests over 5 s). `fasttest.py` and `mac-test.sh` read
  `ZPLAN_TEST_LANE` (default `default`).
- The default `-j` comes from a measurement on this Mac (3, 6 and 8 timed once).
- `docs/DEVELOPMENT.md` section 2: slice gates and integration run the default lane; release candidates and store
  or engine changes also run `full`.

### 4.3 Measurement

The slice ledger records three numbers per passed slice: test and product lines added and removed, the
sentence-assertion delta from the ratchet, and the gate seconds. Worker test time is counted from the worker log's
test commands, as calls.

### 4.4 Deletion, narrowed

Tests go together with the code they test when a behaviour is removed: R1b removes the planner path and its tests.
Any other deletion needs an inventory that follows helpers and records the asserted values, plus one cold review of
the batch. That is later work, outside T1.

## 5. Slices

| Slice | Result | Acceptance |
|---|---|---|
| T1a | The ratchet and its gate in the slice runner; `docs/DEVELOPMENT.md` rules: the ratchet replaces the per-test mapping rule (section 4, line 120); deletion goes with the code | Planted contracts: one adds a sentence assertion, one a criterion-named test, one removes an assertion. Each is refused without its declaration and passes with it; an unpinning slice passes. |
| T1b | Lanes and `-j` from the measurement | The default lane takes at most 8 minutes wall on this Mac; the full lane still runs every test. |
| T1c | Ledger numbers (4.3) shown by `slice_run status` | One real slice reports all three numbers. |

T1a and T1b run before the first D slice, so D adds no pins and its gates are fast.

## 6. Alternatives

- **Area deletion with planted defects (revision 3).** Withdrawn: the gate cannot see helper assertions, and caught
  defects do not prove that a check survives a deletion (audit).
- **A test-line budget (audit, `budget.py`).** It passed every merge while tests grew 2.3 times faster than the
  product, then was removed; it counts lines, not pins.
- **Prose rules.** Measured not to work.
- **Lanes only.** Faster, but the flow keeps growing; the ratchet is the cheap part that stops it.

## 7. Risks

| Risk | Mitigation |
|---|---|
| The sentence classifier misreads a contract text as a pin | a contract declares `text_pins`; the classifier lists each counted literal in the gate output |
| A slow test marked `full` hides a regression until integration | store and engine changes run `full`; release candidates run everything |
| The ratchet makes the architect's contract work heavier | its refusal names the exact opt-out line; the pre-start grep for pins remains only for removed assertions |

## 8. Resolution of the Goldfish findings (revision 3)

| Finding | Resolution |
|---|---|
| B: the deletion gate cannot see the checks it protects (all three) | accepted: area deletion withdrawn (4.4) |
| B: the revision-2 Blocker still applies to the TUI (all three) | accepted: black-box TUI is a non-goal of T1 |
| G1 (ephemeral acceptance) conflicts with the runner and drops regression protection | accepted: acceptance stays committed; the ratchet places it in behaviour modules |
| G2 (protected oracles) is refused by `start` and misses S4 | accepted: replaced by the removed-assertion check |
| G3: rule ids do not exist; the SHA goldens protect stored-revision replay | accepted: G3 dropped; goldens stay |
| G4: product trade-off, false premise ("examples are checks") | accepted: out of T1, to the owner with R2 |
| The cost figure measures a retired harness | accepted: a current measurement (4.3); 54% is not used as the motivation |
| Missing goals, non-goals and exit; incomplete alternatives | accepted: sections 3 and 6 |
| The pilot did not test the riskiest bet; area deletion ignores the helper graph | resolved by withdrawing area deletion |
| A harness (`ux_walkthrough.py`) and a seam (`zplan exec --fixture`) already exist | noted for the later black-box work; not used in T1 |
| Factual errors (mutant counts, "exactly one test", v3 savings, "most of the time", blast radius) | accepted: corrected in section 1 |
| The escaped defects have no surviving source | accepted: only their categories are cited |
