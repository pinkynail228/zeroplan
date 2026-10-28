# zplan features (0.5.2)

Grouped by the job they serve. Derived from code and tests on 2026-10-24; *planned* rows name their release.
Commands are typed in the chat input (`/` opens the list); the same steps exist in the line UI (`zplan --plain`).

## Get ready
| Feature | How |
|---|---|
| One-command install into a private environment | installer script, then `zplan setup` |
| Pinned, checksum-verified engine and agent CLI | `zplan setup` |
| Readiness check with the fix for each failure (tools, login, clean tree) | `zplan doctor`, the readiness card |
| Agent login in zplan's own private home | `zplan login` |
| Update to the newest release | `zplan update [--check]` |
| Per-project rules, roles, gates and limits | `zplan.process.json`, proposed on first run; `zplan profile` |
| Offline demo without model cost | `zplan --fixture demo` |
| Interface in English, Russian or Chinese | first-run choice, settings |

## Plan
| Feature | How |
|---|---|
| Chat with an architect agent about the project | type in the chat |
| The architect's goal draft becomes a plan request | the draft card, `/plan` |
| Planner and independent plan verifier | runs in the background after `/plan` |
| Planner progress above the chat | automatic |
| The plan: requirements, milestones, slices, tasks | «План» tab |
| Approve, ask for changes, reject a plan revision | `/approve`, chat, plan screen |
| Approve despite a failed check, with a stated reason | plan screen |
| Revise an approved plan | plan screen |
| Stop a running planner | line UI today; from the screen in 0.6.0 (*planned*) |
| Planner steps with timers | 0.6.0 (*planned*) |
| Plan as a task tree with statuses | 0.6.0 (*planned*) |

## Run
| Feature | How |
|---|---|
| Start the next ready milestone after a preview of what will run | plan pane, confirmation |
| One Git worktree and branch per attempt | automatic |
| Worker per task, two reviewers, repair loop, plan steward | the milestone graph |
| Local checks on the candidate in a clean environment | process file `checks` |
| Model and effort per role | settings, stored outside the project |
| Stop a running milestone, with confirmation | `/stop` |
| Retry after a recoverable failure, or a new attempt | the failed-run card |

## Watch
| Feature | How |
|---|---|
| Live scheme of the active run: who works, round, elapsed | «Схема» tab, `/status` |
| Activity rows with the time since the last event | under the canvas |
| Cause of a failure or a stop in plain words | the chat card |
| Close the terminal, runs continue; reopen reconnects | `ctrl+q`, then `zplan` |
| Log tail and full details on request | the card's details, `zplan status` |
| Status bar: project, branch, current job, clock | always visible |

## Deliver
| Feature | How |
|---|---|
| Merge card for a finished milestone: diff, merge, later | the chat card, `/merge`, `/diff` |
| Merge with `--no-ff` after confirmation; conflicts shown, abort possible | `/merge` |
| A question from the run answered in the chat | the question card |
| The next milestone becomes ready after a merge | automatic |
| Open a project file read-only | `/open PATH` |

## Not features
No push, no automatic merge, no run without an approved plan, no editing of your checkout by agents.
