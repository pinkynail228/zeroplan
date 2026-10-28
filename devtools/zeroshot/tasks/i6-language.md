I6 — the main screen speaks the chosen UI language: `/language`, a first-run language choice, and the main screen's
own texts read from strings.py (0.5.2, docs/RELEASE_0.5.2_PLAN.md, run i6).

Why: today the main screen is half-migrated: the bar, palette, cards and activity pane read `strings.text` (default
language `en`), the rest is hardcoded Russian, so one screen mixes two languages; nothing lets the owner pick one.

Today: `terminal_planner/tui/strings.py` already has the store and resolver: `LANGUAGES`, `DEFAULT="en"`,
`store_path()` (`setup.config_root()/"ui.json"`), `default_language()` (from LC_ALL/LC_MESSAGES/LANG),
`language()` (reads the file on every call, no cache), `set_language(code)` (atomic write; ValueError on unknown),
`display_name(code)`, `text(id, **values)` (missing translation -> en; unknown id -> KeyError). `slash.py` declares
`/language` with `Arg("language", choices=LANGUAGE_CHOICES)`; app.py lists it among the unwired commands that answer
`note.not_now`. Nothing calls `set_language`. The only first-run modal is `BootstrapScreen` (modals.py), pushed by
`ZplanApp.got_snapshot` when `profile.state == "never"`. `MainScreen.render_state` is the one repaint path; the
`TabPane` titles (`TAB_LIVE_TITLE`, `TAB_PLAN_TITLE`, app.py) and the `#input` placeholder are baked at compose time.

Change:
- Main-screen texts to strings.py (add ids with en, ru, zh; the ru text is exactly today's literal so Russian
  screens do not change): the header readiness words (`header_text`: checking, ready, not passed, detached HEAD),
  the chat pane title (wide; the narrow title is run i7's), «Прогон %s», `PROGRESS_TITLE`, the input placeholder
  (`chat.placeholder` exists), the chat-pane status lines (planner working, observing, `STOP_REQUESTED`, `READING`,
  `QUIT_WAITS`, `CHAT_FIXTURE`), `CHAT_REFUSED` and the usage row in chat_view.py, the canvas tab titles «Сейчас» and
  «План», the plan pane's border title, «Загрузка…», «Не открыто: », `NOTHING_RUNNING`, `PANEL_HINT`. Out of scope:
  other screens and modals (`catalog.py` key bars, PlanScreen, RunScreen, SettingsScreen; run i8 removes several),
  chat history already stored, engine-produced plan/journal lines.
- A method `MainScreen.relabel()` re-reads everything baked at compose (tab titles via
  `TabbedContent.get_tab(id).label`, the placeholder, the activity title) and then `render_state()`.
- `MainScreen.choose_language(code=None)`: with a code, `strings.set_language(code)`, `relabel()`, and a status note
  naming `display_name(code)`; with None, push the chooser. Wire `/language` in `COMMAND_ACTIONS` as
  `choose_language()` (opens the chooser): run i3a changes the entry convention to pass the typed argument at the
  same time; do not change the dispatcher signature here — the orchestrator passes the argument when merging.
- `LanguageScreen` (a `Modal` in modals.py): the three languages by `display_name`, ↑↓/enter or a mouse click picks
  one, esc keeps the current one. On first run (no `strings.store_path()` file) it is pushed before
  `BootstrapScreen`, its preselection is `default_language()`, and esc stores that default so it is asked once.
- Test isolation: today every in-process test reads the real user's `ui.json`. In tests/tui_support.py point
  `XDG_CONFIG_HOME` at a per-process temp dir holding `{"language": "ru"}` at import (before any test module
  imports the app), so existing Russian assertions stay green and no first-run chooser appears; tests that need
  another language or the first-run case use their own config dir.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/chat_view.py, terminal_planner/tui/modals.py
(LanguageScreen only), terminal_planner/tui/strings.py (new ids only), terminal_planner/tui/zplan.tcss (the chooser),
tests/tui_support.py (the ru pin), tests/test_tui_language.py (new), tests/test_tui_strings.py (new ids, if its
completeness check needs them), docs/USER_FLOW.md (language section). Do not edit slash.py, palette.py, cards.py,
activity.py, catalog.py, controller, engine. Other test files: only if a pin breaks because of the harness change;
say which and why.

Acceptance criteria:
- A1 With `ui.json` = en at 120x40 the main screen (header, chat title, tabs, plan pane, bar, input placeholder)
  shows no Cyrillic; with ru the same screen reads as today's Russian.
- A2 `choose_language("zh")` on a running screen relabels the tabs and the header at once and writes `ui.json`.
- A3 With no `ui.json` the first frame shows the chooser before the profile modal; enter on «Русский» stores ru and
  the main screen is Russian; a second start shows no chooser.
- A4 `/language` typed in the palette opens the chooser.
- A5 Tests per preamble: at most two whole-app tests (A1+A2, A3+A4) in tests/test_tui_language.py; every new
  strings id has en, ru and zh.

Non-goals (reviewers must not require): translating modals, other screens, catalog key bars, engine/plan text, the
chat history; `/language CODE` with an argument (merge wiring); a settings-screen row.

Parallel note: runs i3a (cards, the dispatcher convention) and i7 (narrow layout) edit app.py at the same time; do
not move or reformat code outside the strings you replace, the two new methods, the `/language` entry and the first-run
push; leave the chat-pane narrow title to i7.

DoD: `python3.13 devtools/fasttest.py $(ls tests/test_tui*.py | sed 's#tests/#tests.#;s#\.py$##') tests.test_live
tests.test_layout tests.test_toolchain tests.test_reference` with exit 0; quote its `fasttest:` lines.
