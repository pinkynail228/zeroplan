# s5a1-warn-contract — receipt

0.5 item S5a, slice 1 of 3 of `devtools/zeroshot/tasks/disk-guard.md` (the parent; its R-4 first line and
A-2/A-6 apply where cited). Lane: Readiness. Critic split3: GO. DeepSeek worker, sol reviewers.

- **Base commit:** `6e23523a8be138fcfb848c9cbf6869ec74283604` (C2, the intended v0.4.0 tag target). The run's own
  `git status --porcelain` was empty at start; the stopped zs-disk-guard candidate is not a base.
- **Line numbers re-checked on the base (no premise moved, no re-gate):** `setup.py` `item` :250-253, `doctor`
  :565; `commands.py` doctor help :39-41; `cli.py` `App.run` :235-241, `readiness_screen` :379-394;
  `tui/controller.py` `Check` :77-85, `checks_of` :150-151; `tui/app.py` `SettingsScreen.render_state` check rows
  :1505-1520; `docs/USER_FLOW.md` :193-194; `docs/INSTALLATION.md` :73. All hold unchanged on `6e23523`.

**Repair (visit 2, phase.after=rejected).** The acceptance review found the R-6 sentence in `docs/USER_FLOW.md`
was wrapped so a line began with `0.` — a glued ordered-list start that `tests/test_docs.py` (and
`tests/test_fixture_scope.DocsTests`) flags. The sentence was re-wrapped unchanged (`code 0.` moved up, so no
line starts with `0.`), and `tests/test_warn_contract.py` gained `R6DocSentenceTests`: it asserts the sentence's
wording is present and that `test_docs.glued` reports nothing for `docs/USER_FLOW.md` (the class-level guard, its
oracle the repository's own regex, independent of production). Re-wrapping the line back to `0.` fails it
(scratch copy, `FAILED (failures=1)`). Only `docs/USER_FLOW.md` and `tests/test_warn_contract.py` changed since
the rejection; the product and the other test evidence stand.

This slice writes the **contract** only: it teaches every readiness display a third severity (`warn`) and adds no
producer of warnings (the disk probe and thresholds are s5a2/s5a3). A warning keeps `ok=True`, so nothing that
reads `ok` or `all(i["ok"])` moves.

## Files (product `terminal_planner` 43+/11-, docs 5+/4-; tests +193)

- `terminal_planner/setup.py`: `item(..., severity=None)` resolves/validates severity ("ok"/"warn"/"block"; None
  keeps the old ok/block meaning; an inconsistent pair or an unknown word raises `ValueError`) and stores it in the
  item dict; new `severity(check)` returns `check.get("severity")` or the ok/block default; `doctor` prints
  `OK:`/`WARN:`/`BLOCKED:` and exits 0 iff no item is a block and the profile is ready.
- `terminal_planner/cli.py`: imports `severity`; `App.run` says each distinct warn `line` once (`! <line>`) when
  nothing is missing and continues with no readiness menu; `App.readiness_screen` lists warn lines beside the
  missing ones (deduped) and adds no key/action.
- `terminal_planner/tui/controller.py`: `Check` gains `severity: str = "ok"` as its last field; `checks_of`
  populates it from the item dict (`i.get("severity")` else the `ok`/`block` default — the same expression as
  `setup.severity`; the controller deliberately does not import `setup`, per its module docstring).
- `terminal_planner/tui/app.py`: `SettingsScreen.render_state` gives a warn row a yellow `! ` marker and the whole
  escaped `doctor` line, as an ok row shows (not the red block style, not the short `line`, no fix key). The header
  (`readiness_summary`) is untouched and still reads `✓ готов` when warnings are the only issue.
- `terminal_planner/commands.py`: the Russian `zplan doctor` long help names `WARN` and "Код выхода 0, когда
  ничего не BLOCKED"; the English short help is unchanged, so `docs/REFERENCE.md` stays as generated.
- `docs/USER_FLOW.md` :193-195 and `docs/INSTALLATION.md` :73-74: one sentence each on the `WARN:` line and its
  exit 0 (re-wrapped in the repair so no line begins with `0.`).
- `tests/test_warn_contract.py` (new): the A-S/A-2w/A-C regressions and the R-6 doc-sentence guard.
- This receipt. `catalog.py` needed no edit; `cat` stays.

Stable anchor for the code under test: `sha256(tests/test_warn_contract.py)` =
`e89576d575cc00948b1080f7524017d8d3a88d2979ad4bfd86e7c4fa01655084`.

## Acceptance → test

- **A-2w doctor:** `DoctorWarnTests.test_a2w_a_warn_item_prints_warn_and_exits_zero` (a literal warn dict:
  `WARN: <doctor>`, exit 0, `Plan: готов.`) and `..._a_block_item_still_blocks_next_to_a_warning` (WARN + BLOCKED,
  exit 1).
- **A-2w plain + readiness screen:** `PlainStartWarnTests.test_a2w_plain_start_shows_the_warning_and_proceeds_
  without_a_menu` (`! <line>` shown, no `[g] проверить снова` menu, home reached) and
  `..._readiness_screen_lists_the_warning_without_adding_a_key` (listed beside a missing check; the readiness menu
  line is byte-identical with and without the warn).
- **A-2w full-screen Settings:** `SettingsWarnTests.test_a2w_settings_marks_a_warning_yellow_and_keeps_its_doctor_
  line` (a Textual pilot from `tests/tui_support.py`; the `! <doctor>` row is present, the `✓` form and the short
  `line` are not, and the marker's rich span style is exactly `yellow`).
- **A-S:** `SeverityContractTests` (defaults, each consistent pair, each inconsistent pair, each unknown word,
  `severity()` on a dict without the key).
- **A-C:** `PlanningWarnTests.test_ac_a_warn_item_leaves_planning_start_ready` (a warn item through
  `Planning.gate("start")` is `ok=True`).
- **R-6:** `R6DocSentenceTests.test_the_warn_sentence_is_present_and_user_flow_has_no_glued_block` (the sentence
  is present and `docs/USER_FLOW.md` has no glued Markdown block start).

Interpretations (also in `tests/test_warn_contract.py`'s module docstring): (1) the public start path filters
readiness by id (`Planning.items("start")`, `NEEDS["start"]` minus `FIXTURE_SKIPS`), and this slice adds no
producer and no `NEEDS` entry, so the injected warn item reuses an id that is already a start check (`clean`) —
the id is only the filter key; `disk` joins `NEEDS` in s5a3. (2) `readiness_screen` lists a warn line with the same
`! ` prefix as a missing line (R-3 says "lists warn lines too", no distinct marker). (3) `Check.severity` is
resolved inside `checks_of` from the item dict, keeping the controller free of the `setup` import its docstring
forbids.

## A-6 base replay (`6e23523`, tests kept, `terminal_planner/` reset to the base)

Copy of the candidate with `terminal_planner/` replaced by `git archive 6e23523`, `docs/` and the new tests kept;
`TMPDIR` a private scratch dir, `PYTHONPATH=.:tests python3 -m unittest tests.test_warn_contract`. The A-2w
regressions reach and **fail their behavioral assertion** (no import or mock error):

| Test | Base result |
| --- | --- |
| `DoctorWarnTests.test_a2w_a_warn_item_prints_warn_and_exits_zero` | FAIL — base prints `OK: Диск: 13 GiB …`, not `WARN:` |
| `DoctorWarnTests.test_a2w_a_block_item_still_blocks_next_to_a_warning` | FAIL — the WARN line is an `OK:` on the base |
| `PlainStartWarnTests.test_a2w_plain_start_shows_the_warning_and_proceeds_without_a_menu` | FAIL — nothing is shown |
| `PlainStartWarnTests.test_a2w_readiness_screen_lists_the_warning_without_adding_a_key` | FAIL — only `! HEAD отсоединён`, no warn line |
| `SettingsWarnTests.test_a2w_settings_marks_a_warning_yellow_and_keeps_its_doctor_line` | FAIL — the base row is `✓ Диск: …` |

The candidate-only tests error on the base as designed (they exercise `item(severity=…)`/`severity()`):
`SeverityContractTests` (13 errors, subtests counted) and `PlanningWarnTests` (1 error) — no `ImportError`.

## Mutations (each applied to a scratch copy of the candidate, then the named test)

| Mutation | Killing test | Result |
| --- | --- | --- |
| `doctor` prints `OK:` for a warn item | `DoctorWarnTests.test_a2w_a_warn_item_prints_warn_and_exits_zero` | killed (`FAILED (failures=1)`) |
| warn makes `doctor` exit 1 (`ready` = all `ok`) | `DoctorWarnTests.test_a2w_a_warn_item_prints_warn_and_exits_zero` | killed (`FAILED (failures=1)`) |
| plain start hides warnings when ready | `PlainStartWarnTests.test_a2w_plain_start_shows_the_warning_and_proceeds_without_a_menu` | killed (`FAILED (failures=1)`) |
| Settings renders the warn row as `✓` | `SettingsWarnTests.test_a2w_settings_marks_a_warning_yellow_and_keeps_its_doctor_line` | killed (`FAILED (failures=1)`) |
| `item()` accepts warn with `ok=False` | `SeverityContractTests.test_item_rejects_each_inconsistent_pair` | killed (`FAILED (failures=2)`) |

## Checks

DoD, one run (after the repair): `PYTHONPATH=.:tests python3 -m unittest tests.test_warn_contract tests.test_setup
tests.test_ux tests.test_tui tests.test_tui_polish tests.test_reference` → **147 tests OK** (macOS python3.9;
Textual present). The rejecting guard: `tests.test_docs tests.test_fixture_scope.DocsTests` → **5 tests OK**.
Direct importers of the changed modules, separately: `tests.test_tui_chat tests.test_tui_planning` → 148 OK,
`tests.test_terminal_planner` → 80 OK. `python -m terminal_planner.catalog --check docs/REFERENCE.md` →
`docs current` (exit 0). Each run used a private `TMPDIR=$(mktemp -d /tmp/zs-agent-XXXXXX)`; revert/mutation
checks ran on scratch copies only; no commit, no push, no network.

Out of scope (unchanged): s5a2/s5a3, the header summary, and the `GATEWAY_*` warning (s3a3). `item()` is only
consumed through the reads above; no new readiness item is produced.
