# Release 0.5.2 plan: the one-screen UI

Owner brief: docs/UI_REDESIGN.md (accepted 2026-10-22). Screens, controls and scenarios:
docs/ui-redesign/WORK_SCREEN.md, GLOSSARY.md, PRINCIPLES.md; the approved look is the lab
(`devtools/ui-lab/work.py`, commit e51751c, all states walkable with ctrl+t). Baseline to beat:
docs/ui-redesign/baseline-0.5.1/README.md. Owner 2026-10-22: "составь нормальный план релиза ... и начни реализацию".

## Scope
In: `terminal_planner/tui/` (+ `zplan.tcss`), the UI rows of `catalog.py`, docs (USER_FLOW, README code map, REFERENCE),
TUI tests. Out: engine, controller semantics, runs, planner, architect prompts, installer. A UI change that needs data
the controller does not expose stops and goes to 0.6.0, not into the run.

Done when (from the brief, measured, not claimed):
| # | Check | How |
|---|---|---|
| D1 | Scenario A and C without hints, fewer actions than the baseline (A: 15 keys + 3 texts + 1 shell, 3 dead ends) | owner walk, counted against the baseline table |
| D2 | A fresh agent says what is happening from one screenshot | 6 screenshots (one per state), haiku without context, answers recorded |
| D3 | Screen tests clean at 80x24, 120x40 and after resize | `tests.test_tui_screen` (new) |
| D4 | Every key works with the Russian layout | no letter hotkeys remain on the main screen; test sends enter, /, esc, arrows, ctrl+q |
| D5 | Works in Ghostty, Terminal.app, tmux, 16 colours, `NO_COLOR` | manual pass, captures in the gallery |
| D6 | Each main-screen state looks like the same lab state (layout, colours, titles) | gallery 120x40 beside `devtools/ui-lab/work.py` (ctrl+t), orchestrator after every UI merge |

## Decisions taken for the owner (2026-10-22, reversible)
- Languages: the catalog carries RU, EN, ZH for every string of the new main screen and cards; `/language` switches
  at once. Legacy modals that stay (settings, help, note editor) remain Russian in 0.5.2; translated in 0.6.0.
- The goal form, plan screen and run end modal stop being the main path: their decisions become chat cards
  (draft -> plan, approve plan, merge, owner question, error). The modals stay reachable until the cleanup run
  removes what nothing opens any more.
- "No GitHub origin" (baseline dead end 2) is a backend rule; 0.5.2 shows it as an error card with the exact fix
  command instead of a blocked screen. Removing the rule is 0.6.0.
- Scheme for the planner and the stage comes from the real engine graphs (`engine.planner_graph_v2`,
  `milestone.milestone_graph`) plus an observation built from facts the app already has (`Snapshot.flow`,
  live nodes); no new controller calls.

## Work order
Wave 1 runs in parallel (new modules only, exclusive write-sets, no `app.py`); wave 2 is sequential in `app.py`
(one owner at a time, one user-visible change per run, ORCHESTRATOR.md). All runs: `ZS_RUNTIME=deepseek`.
Speed-up (owner 2026-10-23 "количество воркеров поднять"): every new widget is first built in its own module in
parallel (w1-w3, no `app.py`), so each `app.py` run only wires a tested widget; i4 merges into i1c. Widgets start in the
order w3, w2, w1; each integration run starts as soon as its dependencies merge. strings.py and slash.py ids/API are
frozen after u1b; integration runs list chat.py, catalog.py, REFERENCE explicitly in their write-sets.
Critic rel052-speedup: BLOCK (9 findings) -> all 9 accepted: i3a-d kept separate, exact test owners, palette filter
and empty row, bar stage/clock values, journal lines as-is, i1b loop bounds via `limits`, card key in `Chosen`,
toolchain/reference in every DoD, start order w3-w2-w1.
| Run | Write-set | Change | Depends |
|---|---|---|---|
| u1-scheme | tui/scheme.py, tests/test_tui_scheme.py | port `devtools/ui-lab/flowdraw.py`: graph + observation -> Rich Text, boxes/tree/window fitting; `observation_from_flow(flow)` | — |
| u2-strings | tui/strings.py, tests/test_tui_strings.py | string catalog RU/EN/ZH (GLOSSARY ids), language from setting or locale, EN fallback, stored in the UI settings file | — |
| u3-viewer | tui/viewer.py, tests/test_tui_viewer.py | read-only file/diff renderable: line numbers, syntax by suffix, size cap, path stays inside the project | — |
| u4-slash | tui/slash.py, tests/test_tui_slash.py | `/` command registry: names, description ids, which states allow each, prefix match for the palette, parse of args | u2 ids (frozen list in the brief) |
| u1b-scheme-names | tui/scheme.py, strings.py, tests | loop and optional names through GLOSSARY ids (u1 port defect) | u1 |
| w1-cards | tui/cards.py, tests/test_tui_cards.py | card widget + builders (draft, plan, merge, question, error with fix command), `Card.Chosen(command)` | u2, u4 |
| w2-palette | tui/palette.py, tests/test_tui_palette.py | `/` palette widget + `submit(line, state)` over slash.py | u2, u4 |
| w3-activity | tui/activity.py, tests/test_tui_activity.py | «Что происходит» pane (rows, `последнее: … назад`) + bottom bar text | u2 |
| i1a-tab-keys | tui/app.py, zplan.tcss, USER_FLOW, tests | ←→ and click switch tabs; F-keys and alt+N removed | — |
| i1b-scheme-tab | same | Сейчас tab drawn by tui/scheme.py from `Snapshot.flow` | u1b, i1a |
| i1c-activity | same | Журнал tab -> «Что происходит» pane under the canvas (w3 `Activity`) from `Snapshot.journal` lines, silence from `flow.silence`, unknown -> no subtitle (was i4) | w3, i1b |
| i2-commands | same | palette (w2) in the chat input, commands call the existing actions (2026-10-23: letter hotkeys stay until i8, their actions have no replacement before the cards; i2 runs in parallel with i5, i3a wires /open and /diff); the key bar becomes the w3 `Bar` (job + timer from `flow.elapsed`, unknown -> —) | w2, i1c |
| i3a-draft-card | same | chat becomes a widget list that can hold cards (scroll kept); «Составить план из этого?» card (w1) + «Черновик цели» tab, yes = existing goal-draft handoff; one dispatcher for card buttons and slash lines (`Card.Chosen.card.spec.key` carries the draft identity) | w1, i2 |
| i3-chat-inline | same | (added 2026-10-23) the chat becomes a widget list (VerticalScroll) and the card container moves into the history as in the lab; the manual chat scroll arithmetic and its tests go; runs in parallel with i3b-d, which use only the i3a card contract (`show_card`/`close_card`/`drop_card`, dispatcher) | i3a |
| i3b-approve-card | same | plan approval card (approve / revise); parallel with i3c, i3d, i3-chat-inline (2026-10-23) | i3a |
| i3c-merge-card | same | stage done card (merge / changes), key = the end token | i3a |
| i3d-decision-cards | same | owner question and error cards (incl. the no-origin fix command) | i3a |
| i5-canvas-files | same | `/open FILE`, `/diff` as closable canvas tabs, esc closes, files only while no work runs | u3, i2 |
| i6-language | same | `/language` and first-run choice; main screen reads strings.py (2026-10-23: started beside i3a, owner asked for parallel work; `/language CODE` argument wired at merge) | i2 |
| i7-narrow | same | below 100 columns one pane at a time, «Разговор» first; `show_chat()` for cards, wired at merge (2026-10-23: started beside i3a) | i5 |
| i9-look | same + strings, chat_view, chat, catalog, REFERENCE | (added 2026-10-24, owner go: no slice ported the lab look) no logo/header, input inside the chat pane, terminal ANSI palette and lab CSS, lab pane/tab titles, author · time line per message; devtools/zeroshot/tasks/i9-look.md | i3-chat-inline |
| i8-cleanup | same + docs | remove unreachable modals, USER_FLOW/README | all (after i9) |

Each integration run updates the catalog.py rows, help and REFERENCE for the keys and actions it changes (no
contract drift between runs). Chat message times come from the transcript `ts` (chat.py is in the write-set).

Data limits found by the critic (rel052-plan, 2026-10-22), accepted as scope cuts, not backend work:
- Plan tab: no structured task statuses in `Snapshot` -> today's plan text and stage rows; the task tree is 0.6.0.
- Planning has no flow/nodes in the snapshot -> the canvas shows today's planner panel lines; the planner scheme
  and per-step timers are 0.6.0. Running stages: scheme from `Snapshot.flow`, timers = attempt elapsed + silence.
- `/stop` acts on running stages only; stopping planning needs an engine action (0.6.0).

Orchestrator (me) between runs: verify each run in the lab tmux session against the lab state, SVG before/after
gallery per merged run (`devtools/ui-lab/gallery.py`, new), keep STATE.md current.

Critic rel052-plan: BLOCK (8 findings) -> all 8 accepted: findings 1, 2, 3 as scope cuts above, 4 frozen in
u3/u2 (error ids), 5 chat.py in the write-set, 6 i3/i4 split, 7 catalog per run, 8 macOS full suite.

## Release gate
Linux full suite + macOS full suite on the candidate; D1-D5 recorded in docs/ui-redesign/acceptance-0.5.2.md;
critic release review of the accumulated diff (fresh session, xhigh); gated push; private tag v0.5.2; `zplan update`.

## Later (0.6.0)
Architect -> screen channel ("покажи X"), pipeline-creation skill (scenario B), interactive tabs, translated legacy
modals, removing the no-origin rule, plan task tree, planner scheme and per-step timers, `/stop` for planning, the architect listing its assumptions separately.
