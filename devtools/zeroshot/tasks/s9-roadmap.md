s9-roadmap — S9 run view as a card flow, delivered in small sequential steps (owner 2026-10-19: "не надо съедать слона за один заход"; UI first on real-shaped data, then the backend). Each step is its own task file, gated by the sol critic, merged and usable before the next starts. Steps shrink the earlier split (s9a2a/s9a2b/s9a3); their rules are reused step by step, not all at once.

| Step | What the owner gets | Content | Depends on |
|---|---|---|---|
| V1 | The card screen, seen in `--fixture` demo | Flow data type (cycles, executions: node, role, active/no longer active, last agent message) + fixture flows built from real captured runs, containing only fields the public contracts provide; cards render in TUI and plain; screenshots at 80x24 and 120x40. No native reads. | 0.4.0 tag |
| V2 | The same screen on real runs | Watch replay from the start, topology projection over the zplan milestone graph (s9a2a R-1, R-2), ungrouped fallback, incomplete history; fills the V1 type | V1, s9a1 |
| V3 | What reviewers answered | Response parse before scrub, provenance label, findings grammar, drill-in (s9a2a R-3, s9a2b R-7) | V2 |
| V4 | Summary and navigation | Time, stage, outcome, next, last progress/stall, attempt selector, refresh (s9a2-run-view R-1..R-4, carried over) | V3 |
| V5 | Home cards and event log | s9a3-home-cards | V4 |
| later | Optional | Tokens per step and the "last command/action" line: not in this sequence (tokens are internal-only today; actions are adapter text) | upstream/owner |

Rules for every step: the fixture data never contains a field the real contracts do not provide; unknowns are shown as unknown; each step's tests include its own mutations; one UI task at a time (shared tui/app.py).

Start: V1 after the v0.4.0 tag with its own gated brief (devtools/zeroshot/tasks/v1-flow-cards.md: Flow contract, explicit write-set; V1 owns tui/app.py and, for its duration, catalog.py). Each next V step starts when its prerequisites are merged (lanes in docs/RELEASE_0.5_SCOPE.md Order; owner 2026-10-19, critic swarm05); no wave barrier. Detailed specs only for the next V step.
critic s9a2-split-gate: BLOCK on the three drafts (items folded into V1..V5), session 01a150fd-4cce-72d2-9d50-595b08e1a2b8
