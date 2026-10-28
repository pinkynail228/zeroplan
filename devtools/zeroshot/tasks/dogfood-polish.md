Polish from the first real-provider dogfood walkthrough (zplan 0.3.0 on a clone of this repo, real planner + milestone M1, merged). Frames: /tmp/zs-zplan/dogfood/frames (INDEX.md); frame numbers below refer to it. Read AGENTS.md, docs/USER_FLOW.md, docs/REFERENCE.md, terminal_planner/tui/app.py, tui/controller.py, tui/zplan.tcss, catalog.py, live.py, delivery.py and their tests. Do not touch prototype/, upstream/, reference/, docs/history/, STATE.md, AGENTS.md, LICENSE. No real provider; no network. Russian UI, English code.

Build:
1. Key bar while a milestone runs at 120x40 (frame 11): "[e]  [↑↓]  [s]  [r]" have no labels. At 120x40 every key shown in any home/plan/running/modal state has a label; drop or shorten lower-priority keys rather than show a bare key. 80x24 keeps the existing rule (primary actions labelled, no word cut).
2. Goal text: the plan panel cuts the goal after two lines with "…" (frames 03, 11) and nothing says where the rest is. The full goal is reachable from home and the plan screen (e.g. in [i] details), and the cut line says how to see it.
3. Result modal (frames 15-17): it opens over the logo/header, fills ~30 empty rows, and hides the attempt journal. It sits inside the main area below the header, its height fits its content (scrolls when long), and it shows the attempt journal summary (last entries: rounds of repair, reviewer verdicts as already recorded) and the same "Дальше:" line as home. [i] on the result modal opens the journal instead of doing nothing.
4. Settings journal after login/recheck (owner, real Mac run): the log ends with "Проверка готовности…" and nothing else; the owner cannot tell whether it finished or what to do next. `got_checks` updates the list silently. When a check started from Settings (login, setup, recheck) completes, the journal gets a closing line: all OK -> "Готово: всё в порядке. Дальше: [q] назад, [n] новый план" (wording via catalog, keys as bound); failing items -> their names plus the fix key; a check error keeps today's "Проверка не выполнена: ...". No closing line for the silent background checks (startup, refresh).
5. Chat stub: the chat pane looks like a working input, the owner typed a message and got "появится в следующей версии". Until U3b the pane must not look typeable: show "Чат с архитектором появится в 0.4. Новый план: [n]" and route focus/typing so no message can be composed there.

Acceptance criteria:
- P-A1 Pilot test: running milestone at 120x40, every key in the key bar has a label; existing 80x24 key bar tests stay green.
- P-A2 A long goal (5+ lines) is fully visible through the named way, plain and TUI.
- P-A3 Pilot test: result modal region starts below the header, its height is at most content + frame for a short result, it contains the journal entries and the "Дальше:" text from END_ACTIONS.
- P-A5 Pilot test: Settings login (fake login) and recheck each end with the closing line, OK and failing variants; a background refresh check adds no line.
- P-A6 Pilot test: the chat pane accepts no text input and shows the [n] hint; the existing chat placeholder tests updated.
- P-A4 Each new test fails when its fix is reverted (say how you checked). devtools/ux_walkthrough.py stays green (`/tmp/zs-zplan/ux/venv/bin/python devtools/ux_walkthrough.py <dir> --python <installed app python>`; name the interpreter you used). Catalog/help/REFERENCE current; full suite green with ZPLAN_TEST_WHEELHOUSE=/tmp/zs-zplan/wheelhouse.

Superseded (plan reset 2026-10-16 (owner; critic plan-reset GO WITH CHANGES)): run by the orchestrator through zplan after U3b and before U4, on a clone with isolated stores and the installed candidate; evidence (commit, wheel hash, toolchain, commands, results, frames/log/spend) outside /tmp.

Deferred (2026-10-15): run by the owner through zplan after U3b/G2/G3. Before that, apply critic polish (GO WITH CHANGES):
- The first plan opens with [p], not [n] ([n] only re-plans a stale revision, app.py:1052/1069); hints and AC press the named keys. Drop item 5 / P-A6 (U3b replaces the stub).
- Item 3: the result modal shows the END_ACTIONS choice with the keys bound on that modal (home's [o] does not exist there, delivery.py:392).
- Item 4: a check requested while one runs is dropped (controller.py:218); after login a fresh check must run and produce one correct closing line; setup reports through setup_done, not got_checks (app.py:1745) — cover OK/failing/exception, login cancel/nonzero. Never print a Check.key the current screen does not bind (e.g. [i] in Settings).
- New AC: login/setup failure or cancel started from the goal/plan screen is visible on that screen, not only in the Settings log.
- P-A1 covers home/plan/running/modal; P-A3 covers [i], a long scrollable journal and return.
