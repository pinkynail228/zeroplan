tab-hint — the key bar names the tab keys legibly.

Goal: the key bar's tab hint is readable and names keys that work everywhere. Today `TABS_HINT = "alt+1/2/3F2/F3/4 "` (terminal_planner/tui/app.py:83) is glued together and shows in docs/USER_FLOW.md:20. Measured in dogfood 2026-10-22: alt+1/2/3 do not reach the app under tmux or in macOS Terminal without Option-as-Meta; F2/F3/F4 work in both.

Data reach: `TABS_HINT` and its users (app.py ~80-83, ~160, ~1397-1411), the tab bindings (app.py ~1829), docs/USER_FLOW.md (lines ~20 and ~37), tests that assert the hint (tests/test_tui_milestones.py ~1568, ~1581, ~1687-1713, ~1928; tests/test_tui_chat.py ~3360; grep for "alt+1/2").

Write-set: terminal_planner/tui/app.py (the hint string and its comment only), docs/USER_FLOW.md, the tests above.

Acceptance criteria:
- A1 `TABS_HINT = "F2/F3/F4 вкладки  "`; the key bar at 160x45 and 120x40 shows it followed by the existing keys, separated by two spaces.
- A2 alt+1/2/3 stay bound and keep working exactly as now; only the hint text changes. The help screen ([f1]) still lists alt+1/2/3 as alternates if it lists them today.
- A3 docs/USER_FLOW.md shows the new bar line and says F2/F3/F4 switch tabs, with alt+1/2/3 as alternates where the terminal passes Alt.
- A4 Tests assert the new hint at both sizes and fail if the old glued string returns; the existing switching tests still pass.

Non-goals (reviewers must not require): new keys, rebinding, the --plain UI, help screen redesign.

Testing: while editing run only the test you change; run the DoD command once at the end.

DoD: `python3.13 -m unittest tests.test_tui tests.test_tui_chat tests.test_tui_live tests.test_tui_milestones tests.test_tui_polish tests.test_toolchain tests.test_reference` with TMPDIR short (see preamble), all green.
