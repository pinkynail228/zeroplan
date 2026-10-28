P2b — the planner-stop line in local time; the origin card's restore line keeps the scheme

Two display leftovers of P2a (merged a5b9c93) and O2c (merged 4b996da), both found at their gates 2026-10-26.

Causes read on main: `stopped` (terminal_planner/planning.py:543) builds «План rN остановлен вами в HH:MM.» from
`current["stop"]["at"][11:16]`, the UTC `runs.now()` stamp (...Z, set near :429), while the chat rows and cards now show
local time (P2a, `stamp_at` in tui/chat.py). `shown_url` (terminal_planner/tui/start.py:169) cuts the scheme together
with the userinfo, so for an origin with userinfo the card's restore line reads `git remote set-url origin
gitlab.com/a/b.git`, which is not the old remote.

Write-set: terminal_planner/planning.py, tests/test_plan_stop.py, terminal_planner/tui/start.py, tests/test_tui_start.py

Acceptance criteria:
- C1 The stop line shows the stop time in the local zone; the stored stamp stays UTC. planning.py must not import
  terminal_planner.tui (a small local helper is fine). Example: TZ=Europe/Moscow, stop at 2026-10-24T01:40:00Z ->
  «План r1 остановлен вами в 04:40.»; TZ=UTC -> «… в 01:40.».
- C2 `shown_url` keeps the scheme and cuts only the userinfo; a URL without userinfo is unchanged. Example: origin
  `"https://u" + ":t@gitlab.com/a/b.git"` -> card «Сейчас origin: https://gitlab.com/a/b.git» and the restore line
  `git remote set-url origin https://gitlab.com/a/b.git`, no `u:t` anywhere on the card; `git@gitlab.com:a/b.git` ->
  unchanged.
- C3 No changed line matches export_check's `credential` or `url-userinfo` pattern (devtools/export_check.py:41-44):
  userinfo fixtures are built at run time and the variable is not named token/password/secret. Example: those two
  regexes over `git diff` added lines -> no match.

Non-goals (reviewers must not require): stored formats, other screens, English, restoring the userinfo itself.

Risk: low (display only). DoD: `python3.13 devtools/fasttest.py` tests.test_plan_stop, tests.test_tui_stop_planning,
tests.test_tui_start, tests.test_tui, tests.test_tui_strings, tests.test_toolchain: exit 0.
