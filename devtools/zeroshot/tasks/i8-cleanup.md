I8 — remove the dead flow drawing and stale key docs (0.5.2 cleanup; docs/RELEASE_0.5.2_PLAN.md row i8-cleanup).

Audit 2026-10-24 (orchestrator, static read): every modal and screen still has a live path (RunScreen via the
automatic end view, `/merge` and panel `o`; PlanScreen via `/approve`), and the panel letter keys stay (n, g, w, e,
r have no command yet). The only unreachable code is the flow drawing: `flow.draw` and its private helpers and
constants (terminal_planner/tui/flow.py ~41-58, 92-195, 229-362: _legend, _worker, _split, _reviewers, _join,
_delivery, _journal, _status, _row, _box, ... LEGEND_ROLES, ROLE_COLORS, STATE_WORD, RESULT_LINE, the `live` import).
The scheme tab draws through scheme.py. Live: `wrap_status` (app.py), `clip` (activity.py), `ELLIPSIS`, `_wrap_cells`, `_cut_cells`.

Write-set: terminal_planner/tui/flow.py, tests/test_tui_flow.py, docs/USER_FLOW.md, README.md (code map line for flow.py only).

Acceptance criteria:
- A1 flow.py keeps only what a non-test caller uses. Example: `grep -n "^def draw\|LEGEND_ROLES" terminal_planner/tui/flow.py`
  prints nothing; `python3.13 -c "from terminal_planner.tui.flow import wrap_status, clip, ELLIPSIS"` exits 0.
- A2 tests/test_tui_flow.py loses DrawTests and every test of removed names, keeps the `wrap_status` tests; its
  docstring no longer says "run i8 removes it". tests/test_tui_scheme_tab.py is untouched and passes.
- A3 docs/USER_FLOW.md describes no UI that is gone: the reserved `[c]`/`[t]` key-bar labels (~184-196) and the old
  home-screen/key-bar examples (~445-447, ~479-483) become the current form (`/` commands, decision cards in the chat,
  bottom bar «notes · main · работы нет · ←→ вкладки · / команды · ctrl+q выйти»). Letter keys that still work stay
  documented. Example: the doc has no key-bar example containing `[c]` or `[t]`.
- A4 README code map line for flow.py states what it holds now (status wrapping and clipping helpers).

Non-goals (reviewers must not require): removing letter keys, modals, RunScreen, EndView or their tests; moving
helpers into text.py; rewriting USER_FLOW sections that are still accurate; EN/ZH docs.

Risk: low (dead code + docs). DoD: `python3.13 devtools/fasttest.py tests.test_tui_flow tests.test_tui_scheme_tab
tests.test_tui_activity tests.test_tui tests.test_reference` exit 0; quote the `fasttest:` lines.
