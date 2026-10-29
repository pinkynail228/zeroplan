S3a — zplan learns whether the terminal is light, inside Textual's own input, and sets the theme

Tester F4 2026-10-28: a white terminal shows white text; both apps force `ansi-dark` (tui/app.py:2343,
tui/start.py:267); Textual 8.2.8 never asks the background. A query outside Textual leaks late replies as keys:
filter before `parser.feed()` in `LinuxDriver.run_input_thread()`, via `App(driver_class=...)`.

Reuse: `ansi-light`; ui.json, `_stored`, `canonical` (tui/strings.py:75, 621); the apps' constructors
(tui/app.py:2268, tui/start.py:238).

Write-set: terminal_planner/tui/theme.py (new), terminal_planner/tui/strings.py, terminal_planner/tui/app.py,
terminal_planner/tui/start.py, tests/test_tui_theme.py (new), tests/test_tui_strings.py, tests/tui_support.py
(only: pop ZPLAN_THEME and COLORFGBG at import, beside XDG_CONFIG_HOME).

Acceptance criteria:
- R1 The choice: `ZPLAN_THEME` (dark, light, auto; other values = auto) -> ui.json "theme" -> auto; both apps set
  `ansi-light` or `ansi-dark` from it at mount. Example: ZPLAN_THEME=light, ui.json dark -> both apps `ansi-light`.
- R2 auto: until a reply, `COLORFGBG` (last field 7 or 15 -> light) else dark. A LinuxDriver subclass, both apps,
  writes `ESC ]11;? ESC \` once per process after application mode starts (not when SSH_CONNECTION is set); a
  pure filter `(state, chunk, now) -> (state, output, theme)` before `parser.feed()`, state process-wide, removes an
  OSC 11 reply (`ESC ]11;` ... BEL or `ESC \`) at any split whose gaps stay under `constants.ESCAPE_DELAY`.
  Light when rgb luminance > 0.5; applied on the UI loop only under
  auto. Example: "a", "\x1b]11;rgb:ffff/", "ffff/ffff\x07b" -> "a", "", "b", light.
- R3 A strict prefix of `ESC ]11;` is held at most ESCAPE_DELAY, then goes to the parser unchanged; after the full
  `ESC ]11;` the bytes are the reply's, and a reply idle past ESCAPE_DELAY (tail lost to tcflush,
  linux_driver.py:368) is dropped and the state reset, so it never eats later input. Nothing else is held, dropped
  or reordered. Example: "x" -> "x"; "\x1b" then ESCAPE_DELAY -> Escape; "\x1b[A" -> up; "\x1b]11;rgb:ff", then
  a pause, "q" -> "q". Tests: the read loop with a fake source and clock, and an app switch with a fake lifecycle.
- R4 `set_theme(code)` stores "theme" keeping "language"; `set_language` keeps "theme" (strings.py:630 writes only
  "language"). Example: set_theme("light") then set_language("en") -> ui.json holds both.

Non-goals (reviewers must not require): styles beyond the two theme names, `/theme`, the code theme,
docs, Windows, other sequences.

Conflict rule: if a test outside the write-set pins ui.json's exact bytes or the driver class, change nothing and end with `conflict: <file:line>`.

Risk: high (terminal input). DoD: once at the end, `python3.13 devtools/fasttest.py tests.test_tui_theme
tests.test_tui_strings tests.test_tui_language tests.test_tui_start tests.test_tui_look tests.test_toolchain`: exit
0; `python3 devtools/budget.py`: OK. New tests fail on the old code; never the runner's terminal.
