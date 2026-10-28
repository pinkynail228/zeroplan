RC5 — the readiness card says to commit zplan.process.json when that is the only change (0.6.0 smoke 2026-10-25, defect 3)

Incident: ~/zs-pause/dogfood/findings-2026-10-25.md #3 (repeat of 2026-10-24 #2). Right after accepting the profile in
a fresh repository, the only uncommitted file is zplan's own zplan.process.json; `/plan` shows «Есть незакоммиченные
изменения — [d] посмотреть» and nothing says that the file zplan just wrote must be committed. Cause: the `clean`
readiness item (terminal_planner/setup.py:431-436) has one generic text for every dirty tree.

Reuse: the `clean` item and `item(...)` in setup.py; `process.PROFILE_FILE` for the file name;
`git status --porcelain=v1 --untracked-files=all` already read there.

Write-set: terminal_planner/setup.py, tests/test_setup.py.

Acceptance criteria:
- C1 Profile only: when the dirty paths are exactly zplan.process.json, the item's line and card text name it and
  the command. Example: a fresh repo with only `?? zplan.process.json` -> «Закоммитьте zplan.process.json: git add
  zplan.process.json && git commit -m "zplan profile"» (the card's short line: «Закоммитьте zplan.process.json»).
- C2 Anything else: any other dirty tree (other files, or the profile plus others) keeps today's texts byte for
  byte. Example: `?? notes.txt` -> «Есть незакоммиченные изменения — [d] посмотреть».
Joint example: only the profile -> C1 texts; profile + notes.txt -> today's generic texts (C2).

Non-goals (reviewers must not require): zplan committing anything itself (it never commits for the owner); an
exemption of the profile from the clean check (the planner works on a checkout of HEAD, where an untracked profile
does not exist); the engine's own dirty message (engine.py); the origin item; English strings.

Conflict rule: a test outside tests/test_setup.py that pins the clean item for a profile-only tree (grep
«незакоммиченные» in tests/: test_tui_ready_card.py, test_ux.py, test_tui.py) -> `conflict:` with path:line before
any edit.

Risk: low (wording on one branch). DoD: `python3.13 devtools/fasttest.py tests.test_setup tests.test_toolchain`
exit 0; quote the `fasttest:` lines.
