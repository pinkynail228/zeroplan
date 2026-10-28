U2 — UI string catalog and language choice (release 0.5.2, docs/RELEASE_0.5.2_PLAN.md, run u2-strings).

Goal: `terminal_planner/tui/strings.py` gives every string of the new main screen in Russian, English and Chinese by a
stable id, and remembers the chosen language. Nothing uses it yet; integration runs i1-i6 switch the screen to it.

Sources of the texts: `docs/ui-redesign/GLOSSARY.md` (all tables with RU/EN/ZH columns: pane.*, plan.*, role.*,
state.*, flow.*, live.*, key.*) and every user-visible Russian literal in the approved lab `devtools/ui-lab/work.py`
(chat greeting and placeholder, card titles/texts/buttons/hints, canvas titles and empty texts, bar texts, `COMMANDS`
descriptions, notes such as "нет команды …"). Lab literals get ids in the areas `chat.`, `card.`, `canvas.`, `bar.`,
`cmd.` (`cmd.<name>` = the description; command names themselves stay English and are not in the catalog), `note.`.
Fixed ids other runs already use: `cmd.plan`, `cmd.approve`, `cmd.decline`, `cmd.merge`, `cmd.diff`, `cmd.open`,
`cmd.status`, `cmd.stop`, `cmd.language`, `cmd.setup`, `cmd.help`, `cmd.quit`, `note.unknown_command` (`{name}`),
`note.not_now` (`{name}`), `note.needs_arg` (`{name}`), `note.bad_language`, `note.view_empty`,
`note.view_outside` (`{name}`), `note.view_missing` (`{name}`), `note.view_directory` (`{name}`), `note.view_binary`
(`{name}`), `canvas.view_cut` (`{shown}`, `{total}`), `canvas.diff_empty`.
Fixture content (the CSV story, diff, file names, times) is not UI text and gets no id. Placeholders use
`str.format` names (`{stage}`, `{m}`), identical across the three languages of an id.

Write-set: terminal_planner/tui/strings.py (new), tests/test_tui_strings.py (new). Nothing else.

Acceptance criteria:
- A1 `text(id, **values) -> str` returns the current language's string; a missing translation falls back to EN; an
  unknown id raises KeyError (a programming error, never shown).
- A2 `LANGUAGES = ("en", "ru", "zh")` with display names "English", "Русский", "中文"; `language()` returns the current
  one; `set_language(code)` switches at once and persists it.
- A3 Default when nothing is stored: from `LC_ALL`, then `LC_MESSAGES`, then `LANG`: `ru*` -> ru, `zh*` -> zh, else en.
- A4 Stored in `terminal_planner.setup.config_root() / "ui.json"` as `{"language": code}`; an unreadable file or an
  unknown code is ignored (default applies); writing creates the directory.
- A5 Every id has all three languages, and each translation uses exactly the placeholder names of its EN text (test
  walks the whole table).
- A6 The catalog covers every GLOSSARY row listed above (test lists the GLOSSARY ids it expects).
- A7 One test per criterion with an isolated `XDG_CONFIG_HOME` and locale env.

Non-goals: translating legacy screens (settings, help, note editor, catalog.py), using the catalog anywhere,
plural rules beyond what GLOSSARY spells out, CJK width handling.

DoD: `python3.13 -m unittest tests.test_tui_strings tests.test_toolchain tests.test_reference` with TMPDIR short, green.
