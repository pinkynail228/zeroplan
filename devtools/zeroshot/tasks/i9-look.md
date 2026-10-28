I9-look — the main screen takes the approved lab look (layout, colours, titles)
(0.5.2 plan row i9-look; owner go 2026-10-24).

Reference: devtools/ui-lab/work.py (compose, on_mount, titles) + work.tcss; walk it with ctrl+t. Port the look, not its fixtures.

Today (app.py `compose` ~690): block `#logo` + `#header` rows on top; `#input` spans the full width under both
panes; own colours (blue borders); canvas tabs «Сейчас / План»; chat rows have
no author/time line.

Change: drop `#logo`, `#header` and the logo sizing helpers; project · branch · state stay only in the bottom bar.
The input moves into the chat pane bottom as the lab `#prompt-box` (chevron `›`, placeholder from strings); the `/`
palette opens above it inside the pane. The app runs with the terminal palette (`ansi_color=True`, theme
`ansi-dark`) and zplan.tcss takes the lab rules for panes, prompt, cards, messages, log pane and bar.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/zplan.tcss, terminal_planner/tui/strings.py,
terminal_planner/tui/chat_view.py, terminal_planner/tui/chat.py, terminal_planner/catalog.py, docs/USER_FLOW.md,
docs/REFERENCE.md, tests/test_tui_look.py (new), and any test module that asserts on the logo, header, `#input`
position, tab titles or chat row text.

Acceptance criteria (joint example, 120x40, idle project `notes`, then stage M2 running):
- A1 Row 0 is the top border of the panes; no logo, no header. The bottom bar reads
  «notes · main · работы нет · ←→ вкладки · / команды · ctrl+q выйти».
- A2 The input is inside the chat pane, at its bottom, as `› Напиши архитектору… или / для команд`; typing `/` opens
  the palette above it inside the same pane. Chat pane width 38%.
- A3 ANSI colours: pane borders bright black, the focused pane and the input border yellow, architect
  messages with a magenta left bar, cards magenta / grey when done / red on alarm.
- A4 Titles: chat «Разговор с архитектором»; canvas pane «notes · работы нет», while running
  «M2 <stage title> · идёт»; canvas tabs «Схема  План»; log pane «Что происходит».
- A5 Every chat message starts with an author line from the transcript `ts`: «архитектор · 21:01», «ты · 21:02».

Non-goals (reviewers must not require): new behaviour, bindings or cards; EN/ZH wording review beyond adding the
new ids; legacy modals; narrow-mode changes beyond the chat pane taking full width with its input; NO_COLOR/16-colour pass (D5, release gate); pixel-exact spacing.

Risk: medium (layout + CSS; the input move touches focus).
DoD: `python3.13 devtools/fasttest.py tests.test_tui_look tests.test_tui_split tests.test_tui_chat
tests.test_tui_narrow tests.test_tui_commands tests.test_tui_language tests.test_tui_scheme_tab tests.test_tui
tests.test_tui_polish tests.test_toolchain tests.test_reference` exit 0; quote its `fasttest:` lines.
