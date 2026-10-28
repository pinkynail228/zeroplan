# 0.5.2 acceptance (release gate, docs/RELEASE_0.5.2_PLAN.md D1-D5)

Candidate: 117e83c (2026-10-24); superseded by the i11-run-command merge 9afd63e (see D4). Gallery:
`devtools/ui-lab/gallery.py` -> /tmp/zs-zplan/gallery-rc052 (5 states x 80x24 / 120x40).

| Check | Evidence | Result |
|---|---|---|
| D1 owner walk, scenario A and C | owner, after the final candidate | pending |
| D2 a fresh agent reads one screenshot | haiku, no context, 5 screenshots at 120x40 (idle, palette, plan ready, running, file) | 5/5 states described correctly with the right next step; its "broken" notes checked below |
| D3 screen at 80x24, 120x40, resize | `tests.test_tui` LayoutTests.test_a2_layout_at_80x24_and_120x40_and_resize, `tests.test_tui_look` (P1/P2 at both sizes), `tests.test_tui_narrow`; the planned `tests.test_tui_screen` was not written, these cover it | pass on 117e83c (whole Mac suite) |
| D4 keys with a Russian layout | gap found: starting a milestone needed the pane key `g`; fix = run i11-run-command (`/run`, smoke test of enter, /, esc, arrows, ctrl+q) | i11 merged 9afd63e; whole Mac suite on cda5b62 OK (1735) |
| D5 Ghostty, Terminal.app, tmux, 16 colours, `NO_COLOR` | owner, manual pass | pending |

## D2 notes from the agent, checked by the orchestrator
| Note | Verdict |
|---|---|
| Prompt hint clipped («команд» cut) | false: the whole hint fits (idle PNG) |
| Plan-ready shows the «Схема» tab | false: «План» is active |
| «Инструменты zplan не установлены» on every screen | gallery fixture has no installed tools; not a product state; fix the gallery fixture later |
| Running timer 0:00:00, no node marked running | static capture of a just-started fixture run |
| Palette descriptions end in «…» | by design at 120x40 (middle/end clip rule) |
| File tab: no close key in the bar | open: `esc` closes it (USER_FLOW); the bar does not say so |
