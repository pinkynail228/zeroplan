O2a-mini — a full-screen start screen with the Zeroshot logo; an empty folder becomes a project in one step

Owner Mac test O2: without Git `zplan` loops on «Git-проект (путь):» (cli.py:82); Ctrl+D prints «Сессия закрыта»
(cli.py:1077). Look: devtools/ui-lab/onboarding.py.

Write-set: terminal_planner/tui/start.py (new), terminal_planner/cli.py, terminal_planner/tui/strings.py,
tests/test_tui_start.py (new), tests/test_terminal_planner.py.

Acceptance criteria:
- C1 When `tui_wanted(args)`, `zplan` opens a full-screen start screen before the main one: the mascot (the
  output of `python3 devtools/ui-lab/ascii_logo.py upstream/docs/brand/assets/oec-mascot.png braille 24 128`,
  kept as a constant in start.py), the «zeroshot» word mark, the version, a card with a cursor list. Below 60x24
  no mascot. Example: 120x40 in a repo with a commit -> card «<name> · <branch> · <last commit>»,
  rows «Открыть этот проект / Другая папка / Выйти»; Enter -> the main screen opens for that project.
- C2 A folder without Git, or a repo without a commit -> card «Здесь нет Git-проекта», rows «Создать проект здесь
  (git init + первый commit) / Другая папка / Выйти». Create: `git init` if needed, then one empty commit
  («Initial commit»; no file is added); without user.name/user.email the card asks both and writes them to the
  repo's local config. The next card shows branch, commit and, if files exist, «N файлов не в commit». Example:
  empty folder, Enter, Enter -> card «main · Initial commit», Enter -> the main screen.
- C3 «Другая папка»: a path input; a ready project opens; a not-ready folder shows the C2 card for it; a missing
  path shows an error on the card. Esc goes back. Example: `~/nope` -> «Папки нет».
- C4 «Выйти», Esc on the first card, Ctrl+C, Ctrl+Q -> exit 0, no «Сессия закрыта» line; before Create, nothing written to git.
  Example: empty folder, Esc -> the shell; the folder has no .git.
- C5 Without a TTY `choose_project` stays line-based; empty input re-checks the start folder; Ctrl+D or Ctrl+C
  before a project exits 0 with the line «Выход: проект не выбран.» only. Example: `zplan --plain < /dev/null` in
  an empty folder -> the not-a-project line, «Выход: проект не выбран.», exit 0.

Non-goals (reviewers must not require): language, tools, sign-in, autonomy steps; copy beyond what strings.py
requires; recent projects; adding files to the commit; tui/app.py (U1 edits it in
parallel). `choose_project(terminal, start)` keeps its signature.

A test outside the write-set pinning «Git-проект (путь)» or the C5 exit text -> `conflict:`.

Risk: high (git writes in the owner's folder). DoD: `python3.13 devtools/fasttest.py` tests.test_tui_start,
tests.test_terminal_planner, tests.test_setup, tests.test_agent_activation, tests.test_tui_strings,
tests.test_toolchain: exit 0.
