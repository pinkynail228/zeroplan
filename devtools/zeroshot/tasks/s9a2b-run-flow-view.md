s9a2b-run-flow-view — 0.5 item S9, child 2b of the umbrella devtools/zeroshot/tasks/s9a-run-view.md. Replaces the view half of the superseded s9a2-run-view.md: the run view shows the seven summary fields and then the s9a2a flow as cards with a drill-in. In the terminal, never a web page. DeepSeek worker, sol reviewers.

Base: main with s9a2a-run-flow-data merged. Record the base commit. Re-check every line number; stop and re-gate if a premise no longer holds.

Carried over from s9a2-run-view.md (superseded; read it on the base), unchanged unless stated below: the audit, R-1 (seven summary fields) except Этап, R-2 attempt selection, R-3 refresh scheduling, R-4 layout, R-5 catalog/docs; acceptance A-1, A-3, A-6b, A-7, A-8, A-9 and the A-10 mutation list and base-replay rules.

Changes:
- R-1 Этап now comes from the s9a2a projection: "задача-цикл k, проверка-цикл j (наблюдаемые)" plus the currently active node(s) with their roles, or the ungrouped reason; never a native round number. The old "раунд: нет данных" line goes.
- R-6 Cards. After the summary, one card per s9a2a cycle (preparation, each task cycle with its review cycles, final stage with its repair cycles), newest cycle first and the active one expanded. A card row per execution: node (role), "активно"/"больше не активно", the reviewer/steward answer with its provenance label, findings count, the preview of the last agent message. Ungrouped runs show the same rows as a flat timeline under the reason line. Incomplete history shows "история неполная: <reason>" above the cards. All text through the catalog; literal Rich Text or markup=False.
- R-7 Drill-in. Enter on an execution row opens a read-only detail: every finding (scrubbed, full bounded text), the last agent message, the last observed command/action, the execution id suffix and cursors. esc/q return to the same scroll position. No mutation, no native read beyond the running tail job.
- R-8 Tail sections. The s9a1 worker/run-wide tails stay available below the cards (or as a toggle); their labels are unchanged.
- Plain UI: prints the summary, then the cards as indented lines, and offers the drill-in as a numbered choice; same lines as the TUI for one fixture.

Acceptance (in addition to the carried-over ones; Textual pilot at 80x24 and 120x40, Events not sleeps, production entry points, the real s9a1/s9a2a readers against the fakes):
- A-11 The A-1 real-capture fixture of s9a2a renders the expected cards; the active cycle is expanded; answers show «принятие движком неизвестно»; findings counts match.
- A-12 Drill-in shows all findings of a 4-finding diagnostic longer than 300 characters in full (bounded), scrubbed per item; returns to the same scroll position.
- A-13 Ungrouped and incomplete runs show their reason lines and still render every execution.
- A-14 A new execution appearing during refresh adds a row without reopening; an execution leaving active changes only its status text, never to success.
- A-15 Mutations: render the answer without the provenance label; show the raw response; label a cycle as a native round; open drill-in mutations (any action key reaching a mutation).

Size: about 200-300 production and 300-450 test lines; above 800 total, a mandatory re-gate point.
Order: s9a2a -> s9a2b -> s9a3 -> s9b1.
Out of scope: data/projection rules (s9a2a); home cards (s9a3); budget (s9b1); numeric native rounds; `zeroshot ui`; upstream changes.

DoD: targeted tests pass; REFERENCE regenerated; docs/USER_FLOW.md "Live run" describes selector, cards and drill-in; receipt devtools/zeroshot/tasks/s9a2b-run-flow-view-receipt.md.
critic s9a2-split-gate: BLOCK (identity check, prefix integrity, reader contract, findings grammar, stage coverage, card flow, home calls, event-log bounds); not run as is: material for the V steps of s9-roadmap.md, session 01a150fd-4cce-72d2-9d50-595b08e1a2b8
