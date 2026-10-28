# Baseline: owner scenarios on zplan 0.5.1

Recorded 2026-10-22, 22:10-22:27, installed zplan 0.5.1, tmux 120x40, a fresh scratch git repo
(`notes`: one Python file, one test, README, AGENTS.md; no remote). Scenarios from
[../WORK_SCREEN.md](../WORK_SCREEN.md). Captures are tmux ANSI dumps (`cat FILE.ans` in a terminal).
The redesign is done when the owner passes the same scenarios without hints in fewer actions.

## Scenario A: goal in the chat -> plan -> approve -> watch -> merge
| # | Action (what the user does) | Count | Screen | Problem |
|---|---|---|---|---|
| 1 | start `zplan` | — | A01 | modal "process profile" first; jargon (`zplan.default/1`, planner, critic, steward, model ids) |
| 2 | `l` (later) | key 1 | A02 | chat header shows model, provider, `CODEX_HOME` |
| 3 | type the goal to the architect, enter | text 1 | A03 | good: the architect drafts a plan in the chat |
| 4 | type "yes, approved, go", enter | text 2 | A04 | **dead end**: architect is read-only, says "move the goal block through planner -> verifier -> approval" |
| 5 | `tab`, `p` | keys 2-3 | A05 | goal editor is empty: the chat draft is not carried over |
| 6 | retype the goal, `ctrl+g` | text 3, key 4 | A06 | **dead end**: blocked "no GitHub origin"; fix is a shell command outside zplan |
| 7 | `git remote add origin ...` in a shell | shell 1 | — | leaves the app |
| 8 | `g` | key 5 | — | planning ~1 min, shown as a text list (no scheme) |
| 9 | `a`, `y` | keys 6-7 | A07 | approve needs a second confirm |
| 10 | read "start is [g] on the main screen"; `esc`, `esc` | keys 8-9 | A08 | first `esc` has no visible effect |
| 11 | `g`, `y` | keys 10-11 | A09 | right pane shows plan text and "running: task pick", no scheme |
| 12 | `w` (watch) | key 12 | A10 | no visible change except the chat title |
| 13 | `F2` | key 13 | A11 | **dead end for the owner**: the scheme is only on F2; F-keys are off on the owner's MacBook |
| 14 | wait ~8 min (3 tasks) | — | A12 | end modal opens by itself; log shows "стюард" (jargon) |
| 15 | `m`, `y` | keys 14-15 | A13 | merged into main |

Correction (found after the recording): 0.5.1 already carries the architect's goal draft into the goal
form with `c` ("goal draft", `tui/app.py` `action_open_goal_draft`); neither the architect's reply nor
the screen pointed to it, so step 5 is a discoverability dead end, not a missing feature.

Total: 15 keys + 3 typed texts + 1 shell command; 3 dead ends (4, 6, 13) and 3 jargon screens.
Wall time 17 min, of it ~1 min planning and ~8 min the run.

## Scenario C: look at files and changes when nothing runs
| # | Action | Count | Screen | Problem |
|---|---|---|---|---|
| 1 | on the end modal: `d` (changes) | key 1 | C01 | diff exists only on the end-of-run modal, stacked on it, plain text |
| 2 | `esc`, `esc`, `tab`, type "show me AGENTS.md", enter | keys 2-4, text 1 | C02 | **dead end**: `tab` moved focus away from the input; the typed letters went to the pane as hotkeys, silently |
| 3 | `tab`, type again, enter | key 5, text 2 | C03 | works, but the file comes as raw markdown in the chat with an absolute path; a long file would flood the chat |

No file view and no diff view outside the end modal. Total: 5 keys + 2 texts, 1 dead end.

## Scenario B: the architect builds a worker pipeline
Not available in 0.5.1 (planned for 0.6.0); nothing to measure.

## What the redesign must beat
| Measure | 0.5.1 | Target |
|---|---|---|
| A: actions from goal to watching the run | 13 keys + 3 texts + 1 shell | chat + approve on the card (1 click or `/approve`), scheme visible without keys |
| A: dead ends | 3 | 0 |
| C: open a file / the diff | 1 dead end, file in the chat | `/open FILE` or ask the architect, shown in the canvas |
| Jargon on screen | profile id, model ids, provider, `CODEX_HOME`, steward, planner/verifier | none (GLOSSARY.md) |
