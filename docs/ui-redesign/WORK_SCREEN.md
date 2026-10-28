# Work screen (the one screen after the welcome screen)

Owner direction 2026-10-22, reference: lazygit (panes + bottom command log). Status: draft for owner
approval; built first as a lab mockup on fixtures (`devtools/ui-lab/`). Rules: [PRINCIPLES.md](PRINCIPLES.md).

## Idea
One screen, no modes. Talking to the architect, watching the plan and the runs, and making decisions
all happen here. Closing the terminal stops nothing; the next `zplan` opens the same screen.

## Layout
Owner correction 2026-10-22 (reference: Claude Code "opusplan" flow diagram): the conversation is the
left column, full height (lazygit-like, ~38% width). The right column is Flow/Plan on top (80-85% of
the height, `←→` switches) and the activity log under it (15-20%, min 5 rows). One status/key line at
the very bottom. Live mockup: `devtools/ui-lab/work.py` (fixture timeline, replays every ~40 s).

Flow view: vertical boxes worker -> (acceptance review ∥ code review) -> final check -> merge; the
running box has a heavy border in its role colour, a spinner and its own timer; moving dots on the
active edges; a red `↺` edge back to the worker on rejection; review round as a `▰▱` bar. Header line:
current task and `задачи N/M`. Only honest progress: tasks N/M and rounds, never a fake percentage.

Log: `time  who  what`, newest at the bottom, never wraps; border subtitle `последнее: {what} · {m:ss}
назад`. No silence thresholds (owner decision, GLOSSARY.md Liveness).

80x24 (narrow): not built yet; plan is to stack: conversation full width, a one-line run summary,
`tab` swaps to Flow/Plan.

## Owner decisions 2026-10-22 (scenarios and controls)
Scenarios (the owner's own; used for the baseline and the done check):
| # | Scenario | Right top pane shows | Release |
|---|---|---|---|
| A | Talk with the architect about the goal; it splits it into tasks and shows the plan for approval; approve; watch | plan draft, then the worker scheme and the stage plan | 0.5.2 |
| B | Ask the architect to create a worker pipeline; it builds and visualizes it | the pipeline scheme as it is drafted | 0.6.0 (architect skill = feature) |
| C | Plan stopped or nothing running: ask the architect "show AGENTS.md" / "what changed" | file / diff, read-only | 0.5.2 via commands; architect-opens-it in 0.6.0 |

- The right top pane is a viewer ("canvas"): Scheme, Plan, File, Diff as tabs. The owner never edits by
  hand: changes are asked from the architect in the chat. Files open only when no run is working.
- Commands are English only (`/approve`, `/open`, `/diff`, `/language`, ...); descriptions translated.
  Never invent localized command names.
- Keys: enter, `/`, esc (close what the canvas shows), `←→` (switch canvas tabs), ctrl+q. No tab, no
  F-keys. A one-time hint on first open says `←→` switches the tabs.
- Mouse: click a canvas tab to switch; click the buttons on a decision card (approve / no); wheel
  scrolls a pane. The keyboard path always exists.
- 0.6.0 (planned, not now): architect -> screen channel ("show X"), architect skill to create a
  pipeline, interactive tabs.

## Panes
| Pane | Shows | Keys | Never shows |
|---|---|---|---|
| Conversation (left) | owner and architect messages as distinct blocks with time; architect steps folded into one "работает…" line; decision cards inline (approve plan, answer a question, merge) | type + enter; ↑↓ scroll; enter on a card button | ids, tokens, provider, CODEX_HOME |
| Flow (right, view 1) | block diagram of the current Zeroshot process, read-only, inherited from the engine: planner ⇄ plan check for planning; worker → reviewers (in parallel) → final check → merge for a milestone; each box has a state mark and the current task | ←→ switch view; enter on a box = its last lines in the log | editing |
| Plan (right, view 2) | goal → milestones → slices → tasks with marks; per milestone `N/M задач`, current step, steps left up to review and merge; the planning run as its own row while it works | ↑↓ move; enter expand/collapse | raw manifest JSON |
| Activity log (bottom) | one line per event: time, mark, who (in plain words), what, elapsed, "last sign of life N s ago"; newest on top; `! молчит N мин — /status, /stop` when silent too long | enter = full log (readable, not JSON) | JSON records, file bodies |
| Key line | 4-5 keys for the focused pane | | F-keys |

## Data (exists today; UI-only, no backend change)
| Need | Source |
|---|---|
| Milestone flow, states | `live.flow()` live.py:322 (worker, reviewers[], final, active, round/rounds, elapsed, silence, detached); topology `milestone.milestone_graph()` milestone.py:303 |
| Planning flow | `engine.planner_graph_v2()` engine.py:740 (planner ⇄ critic, bounded by plan_rounds); active nodes from `live["nodes"]` |
| Who is who (words) | `live.ROLES` live.py:44, `PLANNER_ROLES` :48; models per role `Snapshot.roles` |
| Activity lines | `r["live"]["journal"]`, `verdicts`, `command` (live.py:52); planner `Planning.journal()` |
| Liveness | `flow.silence` (s since last event/command), `flow.detached`, `live["heartbeat"]` (watcher) |
| Plan tree | `authority.current["proposal"]` (milestones → slices → tasks); states `MilestoneRuns.overview()` runs.py:1385; task status from `.zplan/milestone.json` via `runs.read_manifest` runs.py:263 |
| Merge step | `Row.state` awaiting_merge / conflict / integrated, `merge_state` runs.py:1469 |
| Conversation | `architect.ArchitectStore.transcript()` architect.py:397 (rows carry `ts`; `chat.entries_of` drops it today — keep it) |
| Refresh | snapshot poll 3 s (tui/app.py:37), milestone watch slices 5 s (controller.py:27) |

## Gaps and how the screen handles them (no backend work now)
| Gap | Screen behaviour now | Later (backend) |
|---|---|---|
| No per-agent heartbeat; `silence` is per run | "last sign of life" is per run, shown on the active agent's line; `! молчит` at 120 s (same threshold as today's panel) | per-node last-event time |
| Planner has no round counter | count planner/critic phases in the journal: `план · проверка 2 из ≤N` | explicit round field |
| No done/remaining per slice | compute from the manifest + proposal slices | — |
| Task status only while the worktree exists | finished milestones show their final state; future ones "не начат" | — |
| Final-stage / steward verdicts not kept | flow shows final check state only | keep verdicts |

## Open questions for the owner
1. Is the architect's own work (thinking a reply, drafting a plan) a box in the Flow, or only a line in the log?
2. Plan view depth by default: milestones only, or milestones + slices, tasks on enter?
3. ~~Activity log height~~ answered: 15-20% of the right column.
