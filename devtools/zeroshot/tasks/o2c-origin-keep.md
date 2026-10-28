O2c — the start screen's origin step never replaces an existing origin by default

O2b (merged 7953773) added the origin step to terminal_planner/tui/start.py: a project whose `origin` is not a GitHub
URL (`needs_origin`) gets «Нет GitHub origin» with «Добавить origin» first; `add_origin` runs `git remote set-url
origin` when an origin exists. So an owner with a GitLab or self-hosted origin who presses Enter loses that URL
silently. A missing origin keeps today's behaviour.

Write-set: terminal_planner/tui/start.py, tests/test_tui_start.py.

Acceptance criteria:
- C1 With an existing non-GitHub origin the card names the current URL («Сейчас origin: <url>») and says the
  replacement drops it; the rows are «Пропустить» first, then «Заменить origin»; Enter on the first row leaves the
  remote untouched and opens the project. Example: origin https://gitlab.com/a/b.git -> step -> Enter -> `git remote
  get-url origin` = https://gitlab.com/a/b.git, `choose` returns the root.
- C2 «Заменить origin» with a valid OWNER/REPO runs `set-url` as today, and the card line before it shows the command
  that restores the old URL (`git remote set-url origin <old url>`; a URL with userinfo is shown as C4 says). Example: Down, Enter with `a/b` -> origin =
  https://github.com/a/b.git.
- C3 Without an origin nothing changes: «Добавить origin» first, prefilled `local/<folder>`. Example: empty folder ->
  Create -> step -> Enter -> origin = https://github.com/local/<folder>.git.
- C4 A URL with userinfo (user:token@) is never printed on the card: it shows the host and path only. Example: origin
  `"https://u" + ":t@gitlab.com/a/b.git"` -> the card text has no `u:t`.
- C5 No changed line matches export_check's `credential` or `url-userinfo` pattern (devtools/export_check.py:41-44;
  the gate runs the script on the merged commit): tests build userinfo fixtures at run time (as in C4's example) and do
  not name the variable token/password/secret. Example: those two regexes over `git diff` added lines -> no match.

Non-goals (reviewers must not require): a second remote, readiness changes (setup.py), pushing, English.

Risk: high (git writes in the owner's folder). DoD: `python3.13 devtools/fasttest.py` tests.test_tui_start,
tests.test_tui, tests.test_tui_strings, tests.test_toolchain: exit 0.
