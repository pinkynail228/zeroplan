S1 — move the decision cards out of terminal_planner/tui/app.py, no behaviour change (0.5.2; precedent s0-app-split).

Why: app.py is 4639 lines; every card run edits it, so runs cannot go in parallel and each worker re-reads it all.
After this run card code lives in two card modules and later card runs touch those.

Change: a pure move, unchanged except for imports. No renames, no logic/string/CSS/key edits.
- `terminal_planner/tui/card_kinds.py`: app.py's module-level card block from `MERGE_TASKS` (~4087) to the end of the
  file (merge, question, plan, ready and failed card sources and their registrations), plus the module-level card
  helpers they need (`card_kind`, `card_route`, `CARD_KEY_SEP`, `card_clock`, `draft_card_*`, ...) where moving them
  is needed to avoid an import cycle.
- `terminal_planner/tui/card_host.py`: `class CardHost` holding MainScreen's card methods: `on_card_chosen` through
  `show_failed_card` (~1546-1924) and `merge_counts` through `question_answered` (~2194-2568). `class MainScreen(CardHost, Screen)`.
Imports run one way: app -> card_host -> card_kinds -> (cards, chat, modals, text, strings, ...); nothing imports
app.py at import time. The registries (CARD_SOURCES, CARD_ROUTES, AUTO_END_CARDS, COMMAND_ACTIONS) stay single
objects, reachable as `app.X`. A test that patches a moved name on the app module (`patch.object(app_module,
"card_clock")`) gets only its target changed to the new module.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/card_kinds.py (new), terminal_planner/tui/card_host.py
(new), README.md (TUI code map lines only), tests/test_tui_split.py, plus patch-target lines only in tests that
patch a moved name.

Acceptance criteria:
- A1 app.py no longer defines the moved names; app.py is at most ~3500 lines. Example: `grep -c "def merge_card_source\|def show_card" terminal_planner/tui/app.py` prints 0.
- A2 Every name in `dir(terminal_planner.tui.app)` before the change is still an attribute, and moved ones are the
  same object. Example: `app.merge_card_source is card_kinds.merge_card_source`, `app.CARD_SOURCES is card_kinds.CARD_SOURCES` (if moved);
  `MainScreen.show_card is CardHost.show_card`. tests/test_tui_split.py gets one test enumerating the moved names.
- A3 Behaviour proof: the DoD suite is green with no test edits beyond A2 and patch targets.
- A4 README code map names the two modules, one line each.

Non-goals (reviewers must not require): moving other MainScreen or ZplanApp methods, renaming, deduplicating, fixing
bugs seen while moving, new tests beyond A2.

Risk: medium (structure only). DoD: `python3.13 devtools/fasttest.py $(ls tests/test_tui*.py | sed 's#tests/#tests.#;s#\.py$##')
tests.test_live tests.test_layout tests.test_reference` exit 0, plus `python3.13 -c "import terminal_planner.tui.app"`;
quote the `fasttest:` lines.
