# run-failure-cause — reproducible base replays and G-1 mutation (orchestrator, 2026-10-19)

Supplements run-failure-cause-receipt.md (section "Orchestrator correction"; that text is left as recorded). Critic rfc-close asked for exact commands. This file supersedes the base totals of that section; the G-1 mutation result there is confirmed unchanged.

Script: `~/zs-pause/run-failure-cause-fix/rfc-repro.sh` (private evidence dir), sha256 cf5f57bd48473cfff3b26839c2268651598b2bda52263484b2d83742642566f5. Command: `rfc-repro.sh <zplan checkout> <outdir>`; macOS, python3.13, `TMPDIR=/tmp PYTHONPATH=tests python3.13 -m unittest test_run_cause` in a fresh `git archive b2dd941` tree with only `terminal_planner/` replaced by `git archive <base> terminal_planner`.

| Run | Result | Assertion failures by class | Errors (not counted) |
|---|---|---|---|
| tests b2dd941 over 9871d2d | Ran 97, failures=269, errors=318 | StoreTests 235, PlannerCauseTests 16, DisplayTests 11, ExtractorTests 6, MilestoneTests 1 | missing symbols: engine.observed_cause 246, engine.reset_value 43, live.records 24 |
| tests b2dd941 over f3f4cf0 | Ran 97, failures=76, errors=265 | StoreTests 45, ResetTests 24, PlannerCauseTests 5, DisplayTests 1, ReaderTests 1 | `'list' object has no attribute 'split'` 265 (API shape) |
| b2dd941 StoreTests+MilestoneTests, unmutated | Ran 46, OK | — | — |
| same, conflict identity narrowed to `(execution, message)` at engine.py:511 | Ran 46, failures=5 | StoreTests `..._differ_in_their_target_are_unknown`, `..._differ_in_their_timestamp_are_unknown`; MilestoneTests `test_records_that_differ_beyond_their_message_are_not_identical` [record.target], [timestamp], [cursor spelling] | 0 |

Failure/error counts are unittest's summary (subtests counted individually). The earlier totals (25/366 and 31/315) are not reproduced by this script; the cause was not investigated. With the script, G-1 store regressions fail on both bases at assertions, not only on errors.

Logs: `~/zs-pause/run-failure-cause-fix/repro/` (base-9871d2d.log, base-f3f4cf0.log, mut-off.log, mut-on.log).
