S5 — «Create a project here» is never offered at a mount point either

Plan 0.8.2 A1b (critic plan082 3): s4 refused the home folder and a filesystem root (`cannot_be_project`,
terminal_planner/tui/start.py:126) and the card says "The home folder or a disk root cannot be a project"
(start.py:336), but on macOS an external disk is a mount point, `/Volumes/X`, whose parent is `/Volumes`, so
`path == path.parent` misses it and «Create a project here» is offered at the disk's top.

Reuse: `cannot_be_project` and its two callers (start.py:312, 335); `os.path.ismount`; the s4 test
tests/test_tui_start.py:318 and its fixtures.

Write-set: terminal_planner/tui/start.py, tests/test_tui_start.py.

Acceptance criteria:
- M1 `cannot_be_project` is also true when the resolved path is a mount point (`os.path.ismount`); an OSError there
  counts as false, as today. Example: `os.path.ismount` patched true for `/tmp/x/disk` -> true; a plain subfolder
  of it -> false.
- M2 The create row is absent and the card's line shown for such a folder, and `create()` refuses it too when
  reached without the row, writing nothing (no `git init`). Example: a scratch folder with ismount patched true ->
  the start card's choices are «Another folder» and «Quit»; calling create() leaves the folder without `.git`.
- M3 An existing repository whose root is the home folder or a mount point still opens (the s4 non-goal), and no
  code path deletes or rewrites a `.git`. Example: a repo at the isolated HOME -> «Open», its `.git` unchanged.
- M4 The card's line names the disk top as well: "The home folder or the top of a disk cannot be a project."
  Example: the card text for a mount point contains it.

Non-goals (reviewers must not require): Linux or Windows mount rules, network drives, the typed «Another folder»
path (0.9), wording of other start lines.

Conflict rule: if a test outside the write-set pins the old card line or the create row at a mount point, change
nothing and end with `conflict: <file:line>`.

Risk: medium (project creation). DoD: once at the end, `python3.13 devtools/fasttest.py tests.test_tui_start
tests.test_toolchain`: exit 0; `python3 devtools/budget.py`: OK. Each new test fails on the old start.py.
