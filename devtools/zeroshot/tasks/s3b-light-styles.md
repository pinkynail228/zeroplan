S3b — every zplan text reads on a light terminal, dark unchanged, and `/theme` fixes the choice (A3 step 2, F4)

Orchestrator check 2026-10-28 (Terminal "Novel"): the app mounts `ansi-light`, but some styles assume dark:
owner message body `ansi_bright_white` (tui/zplan.tcss:135, invisible), pane titles `ansi_white`
(zplan.tcss:17, 42, cards.py:140, activity.py:160), start wordmark `ansi_bright_yellow` and field background
`ansi_bright_black` (start.py:65, 69); code is `ansi_dark` (app.py:770, viewer.py:32).

Reuse: Textual's `:light` pseudo-class (textual/widget.py:400); `theme.choice/theme_name/apply`,
`strings.set_theme`; `/language`'s path (slash.py:79, card_kinds.py:104, app.py:1164 `choose_language`).

Write-set: terminal_planner/tui/zplan.tcss, terminal_planner/tui/start.py, terminal_planner/tui/cards.py,
terminal_planner/tui/activity.py, terminal_planner/tui/app.py, terminal_planner/tui/viewer.py,
terminal_planner/tui/theme.py, terminal_planner/tui/slash.py, terminal_planner/tui/card_kinds.py,
terminal_planner/tui/strings.py, tests/test_tui_theme.py, tests/test_tui_slash.py, docs/USER_FLOW.md,
docs/REFERENCE.md (test_tui_slash.py: its command list pins only)

Acceptance criteria:
- L1 Light-only rules (`:light`) for the styles above: default foreground or a darker ANSI colour; dark rules and
  their values unchanged. Example: under ansi-light the owner body's colour is not ansi_bright_white; under
  ansi-dark it still is; test_tui_look passes unedited.
- L2 The architect reply's code and the viewer use `ansi_light` under a light theme, `ansi_dark` otherwise, read
  from the app's theme when drawn; chat bodies redraw on a theme change. Example: a reply with a code block, theme
  switched to ansi-light -> its Markdown code theme is ansi_light.
- L3 `/theme auto|dark|light`, appended last in `COMMANDS`: stores the choice and applies it now (auto: the
  terminal's answer, else COLORFGBG, else dark); a bare `/theme` names the current choice; another value is a note,
  nothing stored. `ZPLAN_THEME` still wins at start; a late terminal answer changes nothing after `/theme dark` or
  `light`. Example: `/theme light` -> app.theme "ansi-light", ui.json theme "light", language kept.
- L4 USER_FLOW: the theme rule and `/theme` in two sentences; REFERENCE regenerated if its check needs it.
  Example: tests.test_docs and tests.test_fixture_scope pass.

Non-goals (reviewers must not require): new colours for dark, a theme chooser screen, other commands' order.

Conflict rule: if a test outside the write-set pins a value this changes, change nothing in it and end with
`conflict: <file:line>`.

Risk: medium (colours). DoD: once at the end, `python3.13 devtools/fasttest.py tests.test_tui_theme
tests.test_tui_slash tests.test_tui_commands tests.test_tui_palette tests.test_tui_look tests.test_tui_chat_messages
tests.test_tui_reply_safety tests.test_tui_start tests.test_docs tests.test_fixture_scope tests.test_tui_language
tests.test_toolchain`: exit 0; `python3 devtools/budget.py`: OK. New L1-L3 tests fail on today's code.
