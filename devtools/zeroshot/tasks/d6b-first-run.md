D6b — first-run fixes from the newcomer test (R6)

R6 2026-10-27 (~/zs-pause/public/r6/R6.md): a fresh agent walked README -> merge on macOS. Login itself is D6a.

Write-set: terminal_planner/setup.py, terminal_planner/cli.py, terminal_planner/process.py,
terminal_planner/tui/*.py, terminal_planner/user_commit.py,
terminal_planner/catalog.py, docs/REFERENCE.md, tests/*

Acceptance criteria:
- G1 Ctrl-C during `zplan login` prints «Вход прерван» and exits 130, not the plans/runs message with exit 0; the
  Codex child gets NO_COLOR=1 and TERM=dumb when stdout is not a TTY; Ctrl-C in the commit card (D4c,
  card_host.confirm_commit) is caught like login's; after D6a's «Это ваш Codex» line cli.main adds no «Вход не завершён». Example: SIGINT to the login child -> exit 130; login piped
  to a file -> child env has NO_COLOR=1; SIGINT during a commit hook -> «Коммит прерван», index unchanged.
- G2 ProfileScreen (modals.py) shows one hint line with its keys (move ←→/tab, pick enter/space, save ctrl+s or
  «сохранить», cancel esc) and the selected button of each group is visibly marked apart from focus («● »).
  Example: focus on «2» while «1» is selected -> «● 1» and focused «2» render differently.
- G3 The bootstrap profile card and `zplan profile` show autonomy level and max_runs as they are, without
  «(для следующих этапов)» on autonomy. Example: proposed auto/3 -> card shows «сам» and «3».
- G4 `zplan profile init` that commits the file itself says so («закоммичен: zplan profile») and never tells the
  user to commit it. Example: init in a clean repo -> output has no «git commit».
- G5 `zplan status` works while the shell is open: read-only, no store.locked. Example: TUI running in the project
  -> `zplan status` exit 0 with the same overview.

Non-goals (reviewers must not require): login/logout semantics (D6a); merge confirmation; docs other than
REFERENCE; en/zh texts; roles.json.

Tests: new tests/test_first_run_fixes.py covers G1-G5 with fixtures (fake Codex binary); existing tests updated.

Risk: medium (store access). DoD: `python3.13 devtools/fasttest.py tests.test_first_run_fixes tests.test_setup
tests.test_tui_profile_choice tests.test_process tests.test_terminal_planner tests.test_reference`: exit 0.
