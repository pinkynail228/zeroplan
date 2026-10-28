L1 — the TUI offers Russian only until the English and Chinese texts are complete

Owner Mac test of 0.6.0 (~/zs-pause/dogfood/findings-2026-10-26-owner-mac.md, O1): after choosing English the screen
stays mostly Russian (~1,300 literals outside terminal_planner/tui/strings.py). The 0.6.2 owner test must not offer
that choice. Today the first-run chooser (terminal_planner/tui/app.py, `first_run_language`; modals.py
`LanguageScreen`) lists English · Русский · 中文, marks the locale default (`en` on an `en_US.UTF-8` Mac), and a
`ui.json` stored by 0.6.0 may hold `en`.

Write-set: terminal_planner/tui/strings.py, terminal_planner/tui/app.py, terminal_planner/tui/modals.py,
terminal_planner/tui/slash.py, terminal_planner/tui/palette.py, tests/test_tui_language.py, tests/test_tui_strings.py,
tests/test_tui_commands.py, tests/test_tui_palette.py, tests/test_tui_slash.py, tests/test_tui_cards.py,
tests/tui_support.py

Acceptance criteria:
- C1 strings.py names the offered languages in one constant (`OFFERED = ("ru",)`); the language in effect is
  always an offered one: a stored or locale language outside it reads as `ru`. The catalog keeps en and zh. Example:
  `LANG=en_US.UTF-8` and `ui.json` `{"language": "en"}` -> `strings.language()` is `ru`, the main screen is Russian.
- C2 With one offered language no chooser opens on the first start; the profile modal (when the profile needs it)
  comes first. Example: a fresh config root, profile `never` -> the top screen is the profile modal, no
  `LanguageScreen` is ever pushed.
- C3 `/language` is not listed in the `/` palette while one language is offered; typed anyway, it changes nothing and
  one note says only Russian is available for now (a new strings id with en, ru and zh). Example: `/language en` ->
  the note, `strings.language()` stays `ru`, `ui.json` unchanged.
- C4 With `OFFERED` patched to all three languages the existing chooser, `/language` and English texts behave as
  today: the tests pinning them patch `OFFERED` instead of being deleted. Example: tests.test_tui_language a1-a4
  pass under the patch.

Non-goals (reviewers must not require): translating any text; the CLI, setup and doctor texts; the architect's reply
language; the start screen (terminal_planner/tui/start.py); removing en or zh from the catalog; an English release.

Risk: medium (zplan UI logic). DoD: `python3.13 devtools/fasttest.py` tests.test_tui_language, tests.test_tui_strings,
tests.test_tui_commands, tests.test_tui_palette, tests.test_tui_slash,
tests.test_tui_cards, tests.test_toolchain: exit 0.
