Rules for every agent in this run (worker, reviewers); repository guidance is AGENTS.md.

Environment:
- Every Python command uses `python3.13` (read `python3` in the DoD as `python3.13`); missing: stop and report, never fall back. Quote `python3.13 -V` in the evidence.
- Before any test, `mktemp -d /tmp/zs-agent-XXXXXX` and use it as TMPDIR. Reviewers share the worktree: for a revert check copy the repo into the scratch dir (`python3.13 -c 'import shutil,sys; shutil.copytree(".", sys.argv[1], ignore=shutil.ignore_patterns(".git",".tools","__pycache__"))' DIR/repo`), never revert files in the shared worktree; `rm -rf` the scratch dir before you finish.
- No commit, push or network. Leave STATE.md and AGENTS.md alone.

Tests:
- Several modules: `python3.13 devtools/fasttest.py MODULE...` (exit 0 = green); one class or test: `PYTHONPATH=.:tests python3.13 -m unittest ...`.
- A test only for new uncovered behaviour or a reproduced defect: extend an existing test first; one scenario may cover several criteria. Text and layout edits get no new test; assert an exact string only when it is a contract (a command, a protocol field, a required warning); a task that touches a surface replaces its wording pins with the behaviour. At most two tests per task drive the whole app. No mutation tables, base replays, receipt files or stress rounds unless the task asks. Linux-only tests skip on macOS. Fixtures use scratch paths or an isolated HOME/XDG, never the runner's home. A change to `pyproject.toml` or `terminal_planner/resources/` also runs `tests.test_install`.

Worker:
- Each visit starts with `git status --porcelain`.
- First visit, before any edit: read the task, open every entry point, file and example it names. If two criteria cannot both hold, or one needs a file outside the write-set or data the code lacks, change nothing and end with one line `conflict: <IDs> <input or file where it fails>`. Anything else unclear: take the reading closest to the task's example, record it as an interpretation, go on.
- Before new code, stop at the first step that holds: no code needed; existing repo code (used the way the surrounding code does); the standard library; an installed dependency; only then minimal new code. Never drop validation, error handling or safety to shorten code; no abstractions, options, fallbacks or refactors outside the task.
- Run only the tests of your change, while editing and once after the last edit; the full DoD runs once in the final check, not by you. Quote the test commands you ran and their result lines. A test that looks flaky: rerun only it once and say so.
- Repair: fix the cause of each demonstrated violation on all affected paths, within the task, without weakening behavior; keep earlier reproductions passing; extend the failing criterion's test, a new test only when none can express the defect.
- Final summary: each criterion -> test and file:line; what you left out; interpretations and why (or "none"), also in the docstring of the covering test (reviewers do not see the summary). Say if Zeroshot itself got in the way.

Reviewers:
- Acceptance: verify each criterion with evidence from the task's new or changed tests and the code; run no tests (the final check runs the DoD). Checks left to the merge gate (full suite, anything your sandbox refuses): list separately, never as passed, never a rejection.
- Code: read code and tests without the acceptance evidence; one focused reproduction may back a finding: one test id, ≤ 120 s, never a module, the DoD or the suite. Check the AGENTS.md invariants, that tests exercise what they claim, and scope creep.
- Both: check the worker's interpretations against the task and invariants; an interpretation or a missing example never waives a stated requirement.
- Reject only a demonstrated violation of an acceptance criterion, task requirement or invariant on a realistic path (normal use and the inputs, states and failures the task names). A rejecting finding cites the requirement (ID or quote), gives a reproduction or directly checkable evidence on the current candidate, and names the affected paths. An acceptance rejection blocks regardless of the code verdict.
- Non-rejecting notes: `spec gap: ...` for hostile inputs the task does not name (corrupted stores, injected signals, exotic text) and behavior no requirement governs, whatever an unconditional word says; `tests: ...` for test count, naming, form, extra cases (only a behaviour change with no test, or a test that cannot fail, rejects; test count never blocks).
- Contradictory requirements: start the verdict with `conflict: A2/A4 ...` (both IDs, one input where both cannot hold); never waive either.
- Re-raise a finding only with evidence on the current candidate. Report all demonstrated violations together, after one pass over the boundary values and lifecycle states the task states.
