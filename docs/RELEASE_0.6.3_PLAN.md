# Release 0.6.3 plan: the architect chat reads like a conversation

Owner 2026-10-27, after a look at 0.6.2: the chat with the architect is hard to read (screenshot: four internal
header rows, «напишите /plan <цель>» stuck above the chat, an author line on every message, a pink bar on the
reply, plain text with raw markdown, a large empty area). The owner approved the chat-v2 look in the lab:
devtools/ui-lab/chat.py (commit d02f46c; `--gallery DIR` writes the states empty, dialog, thinking, goal-card,
working, merge, long-reply, note, error at 80x24, 100x45, 140x40). Inputs: newcomer findings 2026-10-26 defects
2-4 (pause dir: dogfood findings-2026-10-26-062-newcomer.md).

## Goal
At 80x24 and wider, the chat pane holds only the conversation, the decision cards, one line about what runs now
and the input. Engine, Controller, cards' actions and commands are unchanged; keys too, except V4's example pick.
Scope critic r063-scope 2026-10-27: GO WITH CHANGES, 7 findings folded in.

## Slices (sequential: they share terminal_planner/tui/app.py, except V5)
| # | Slice | Risk | Owner-visible result |
| --- | --- | --- | --- |
| V1 | chat chrome | low | no header rows; a short conversation sits at the bottom; model and tokens dim at the bar's right; one indicator line above the input (thinking clock, run line, notes); a note clears on the next owner action |
| V5 | architect reply style (method, parallel to V1) | low | short markdown replies that end with one next step; no «принят… пока не подтверждено» |
| V2 | messages | low | no author line; a time line at the start and after a 10 min gap; owner text with a yellow bar; architect reply with a «●» gutter rendered as markdown (L-2 sanitising runs on the raw lines first); draft lines without «ответ N · арх ·» |
| V2b | literal HTML-like text in replies (found by M1 review) | low | `Vec<String>`, `<!-- -->`, HTML blocks in an architect reply show literally instead of vanishing |
| V3 | steps and closed cards | low | event rows as one-line steps (✓/▶/!) in plain words; a decided card shrinks to one dim line |
| V6 | the chat is the wide column (sandbox sb13: 36 columns at 100x30) | low | the chat `1fr`, the canvas column 40%, as the lab's chat-first split; narrow mode unchanged |
| V4 | empty chat | medium (the arrows' pick changes beside the palette and history recall) | an empty chat shows the lab's centered intro and three generic example goals; ↑↓ picks one into the input |

Not in scope, a named deviation from the lab: its always-visible side plan (the right column shows the plan at ≥100
columns, but its tab may be «Сейчас»); the
narrow layout's pane switching; translations (Russian only, L1); feed.py event texts (they are also the
architect's input; V3 restyles them in the pane only).

## Method for every slice
- The lab file is the reference look; each brief names the lab state it matches.
- Replacing a UI element deletes the tests pinning its old text or keys; one invariant test per slice covers the
  new surface at 80x24 and 140x40.
- The L-2 sanitising of model text (terminal sequences, line breaks) keeps its tests: moved, never deleted.

## Release
After V1-V5: version 0.6.3, newcomer re-check in a fresh sandbox (installed candidate, real provider, the lab's
flows: goal -> plan -> run -> merge), Linux full suite on host 2, release critic, tag v0.6.3, gated push, install
on the owner's Mac.

## Later
- Newcomer defect 5 (profile modal jargon), defect 6 (`/la` palette), defect 7 (`/merge` in `auto`: owner).
- A side plan panel inside the chat pane for wide terminals, if the owner asks after testing 0.6.3.
