S4 — the start screen never makes the home folder a project and never freezes on a large folder

Tester report 2026-10-28 (0.8.1, macOS): zplan started in `~`, «Create a project here» made `~` a Git repo; the next
card ran `git status --porcelain --untracked-files=all` over the whole home (start.py unstaged_files, called from
show() on every redraw, no timeout, on the UI thread), so the app ignored every key, Ctrl+Q included, and had to be
killed five times. After that `~` opened as a project (origin card `local/<user>`).

Reuse: start.py's Folder/inspect/rows/enter/show and run_git; tests/test_tui_start.py's scratch folders, isolated
HOME and run_app.

Write-set: terminal_planner/tui/start.py, tests/test_tui_start.py.

Acceptance criteria:
- H1 A folder that is the user's home folder (`Path.home()`, resolved) or a filesystem root never gets «Create a
  project here»: the card says the home folder or a disk root cannot be a project and suggests making a folder for
  it (`mkdir ~/my-project`); its rows are «Another folder» and «Quit». Other folders, home subfolders included, keep
  the row. Example: start in HOME without Git -> rows Another folder, Quit, the mkdir hint shown, no `.git` created;
  start in HOME/proj without Git -> «Create a project here» first.
- H2 The count of files not in the commit runs once per card entry (enter), not in show(); it uses
  `--untracked-files=normal` and a timeout of at most 2 s; a timeout or error drops the line and the card still
  opens. Example: 200 untracked files in one new subfolder -> «1 file not in the commit»; a stubbed timeout -> the
  card shows the branch and commit line, no count line; moving the cursor runs no git.
- H3 Keys stay live: no git call in show() or the cursor actions. Example: on a ready card, pressing down then up
  three times calls the count once (counter on the patched function).

Non-goals (reviewers must not require): opening an existing repo whose root is the home folder (only creation is
refused); the main screen, doctor or readiness checks; theming; docs.

Conflict rule: if a test outside the write-set pins the untracked count or the create row, change nothing and end
with `conflict: <file:line>`.

Risk: high (git writes in the user's folders). DoD: run once, at the end: `python3.13 devtools/fasttest.py
tests.test_tui_start tests.test_terminal_planner tests.test_toolchain`: exit 0; `python3 devtools/budget.py`: OK.
Each new test fails with the old start.py restored.
