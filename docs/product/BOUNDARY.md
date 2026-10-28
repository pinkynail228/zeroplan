# zplan and Zeroshot: who does what

## Zeroshot (the engine)
An open-source engine that runs one task through a graph: a worker, then acceptance and code reviewers in parallel,
then a repair worker, in bounded rounds; the writer never approves its own work. Every event goes to a durable
ledger. Its CLI runs, lists, watches, stops (`force-stop`) and resumes runs. Its `plan` command is a hosted merge
plan of runs, not roadmap planning.

## The split
| Capability | Zeroshot | zplan |
|---|---|---|
| Implement, review, repair one task | yes | uses it unchanged, one run per milestone |
| Goal to requirements, milestones, tasks | no (one `task` per run) | planner + independent plan verifier |
| Human approval of a plan revision | no | approve, revise, reject; nothing runs before approval (0.6.0 `auto`: the independent plan verifier approves) |
| Order between milestones | hosted merge plan only | next milestone is ready after the previous one is merged |
| Isolation of agent edits | user keeps the worktree clean | a dedicated Git worktree and branch per attempt |
| Merge | optional delivery inside the graph | through the merge gate (pinned candidate, project checks, critic on high risk); owner-confirmed up to 0.5.2, by the autonomy level from 0.6.0; never pushes |
| Watching | `status`, `watch`, `logs`, a browser UI | one terminal screen: chat, plan, live scheme, activity, causes |
| Detach and reattach | runs are detached | reopening reconnects from stored records |
| Stop | `force-stop` | confirmed stop, request stored first, cause shown |
| Restart after failure | `resume`, checkpoints | a new attempt per restart; an old submission is never resent |
| Project rules | profiles, runtime configs | `zplan.process.json`: roles, gates, limits, rules from AGENTS.md / CLAUDE.md |
| Install | `npm install -g` | pinned, checksum-verified engine and agent CLI in a private home |
| Readiness | not in the CLI | `zplan doctor` and a readiness screen with the fix for each failure |
| Offline demo | no | `zplan --fixture demo`, no model tokens |

## Invariants
1. The engine owns run lifecycle state (phase, events, results); the terminal UI only calls it. zplan stores what the
   engine has no notion of: the plan, its revisions, and one record per attempt linking a milestone to its engine run.
2. The native lifecycle is authoritative: a run is stopped only after the engine reports it finished; a stored
   submission is never resubmitted.
3. Target-agnostic: the project comes from the working directory or an explicit choice; no project-specific code.
4. Reuse the engine's public contracts; inspect the engine before building anything next to it.
5. zplan acts only within the autonomy level the owner sets (0.6.0: `auto`, `supervised`, `manual`; up to 0.5.2 it never
   merges on its own); a red gate always stops; push, tags, publishing and deleting unmerged work are always the owner's.
6. One zplan release is qualified against exactly one engine and agent CLI version; a new engine is a new zplan release.
7. Unit tests run on deterministic fixtures; the installed product is qualified on Linux with Docker.

## When plain Zeroshot is enough
One self-contained change: write the input and runtime files, run it in a clean worktree, watch it, merge the branch.
zplan earns its extra layer when a goal needs several ordered steps, a plan you want to approve first, and a screen
you can leave and come back to. The cost: its own state store, a pinned engine version, and engine features
(profiles, targets, the browser UI, custom graphs) not exposed one to one.
