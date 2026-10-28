s9a3-home-cards — 0.5 item S9, child 3 of the umbrella devtools/zeroshot/tasks/s9a-run-view.md. Owner direction (2026-10-19): see the release/plan log and a flow of cards on home. Home shows each milestone of the current plan as a card and a bounded event log; it reuses existing stored state only. DeepSeek worker, sol reviewers.

Base: main with s9a2b-run-flow-view merged. Record the base commit; re-check line numbers.

Read: delivery.py home rows (`latest`, `next_step`, the "задача k/n (T) · phase" row), live.py journal (JOURNAL_LIMIT, `stages`), runs.py `overview`, tui/app.py home screen and key bars, cli.py plain home, catalog.py, docs/USER_FLOW.md home section, test_tui.py, plain home tests.

Rules:
- R-1 Milestone cards. Each milestone of the current revision is one card: id and title, state text (the existing `run_state`/home mapping), task k/n and phase exactly as today, «последнее событие» (existing label), "Дальше" from the same `next_step`. Selecting a card and the existing keys behave as today ([e] opens the s9a2b selector).
- R-2 Event log. A bounded panel with the latest journal lines of the current plan's attempts (existing `live.journal` entries, newest first, milestone id prefixed, HOME_LOG lines). No new journal kinds.
- R-3 No new native reads: no `watch`/`logs` calls from home; the home refresh cadence is unchanged. Plain UI prints the same cards and log lines.
- R-4 Layout at 80x24 and 120x40: cards wrap or scroll; selection stays visible; values bounded with "…".

Acceptance (Textual pilot at both sizes, plain home, deterministic):
- A-1 Plans with 1, 3 and 8 milestones in mixed states render every card with today's state/next texts (oracle: the existing home mapping).
- A-2 The event log shows newest-first lines across milestones, bounded at HOME_LOG.
- A-3 Spies: zero `zeroshot` calls from home rendering and refresh.
- A-4 Existing home key behavior and tests unchanged (list any updated test with the reason).
- A-5 Mutations: a second state/next table; reading logs from home.

Size: 200-350 lines total; above 500, a mandatory re-gate point.
Out of scope: run-flow cards (s9a2b); new journal data; cross-plan boards; web UI.

DoD: targeted tests pass; docs updated; receipt devtools/zeroshot/tasks/s9a3-home-cards-receipt.md.
critic s9a2-split-gate: BLOCK (identity check, prefix integrity, reader contract, findings grammar, stage coverage, card flow, home calls, event-log bounds); not run as is: material for the V steps of s9-roadmap.md, session 01a150fd-4cce-72d2-9d50-595b08e1a2b8
