# zplan vision

## In one sentence
zplan is a terminal cockpit for building software with AI agents: you describe a goal in a chat, approve a plan of
milestones, and watch independent agents implement and review each milestone in the background, while every
decision that matters (the plan, the merge) stays yours.

## The problem
AI coding agents are good at one task and bad at a project.

- **One agent, one long session, a big goal.** The session drifts, loses context, and the agent approves its own
  work. You find out what went wrong at the end, after the tokens are spent.
- **A multi-agent engine helps, but only per task.** [Zeroshot](https://github.com/the-open-engine/zeroshot) runs a
  task through a worker and independent reviewers until it passes. Everything around that task is still manual: you
  split the goal into tasks, write each brief, decide the order, keep your checkout clean, watch logs, judge whether a
  silent run is alive, and merge the branches yourself.
- **The overhead lands on the person.** Setting up the agent environment, disabling tools that inflate every
  prompt, babysitting long runs, re-explaining the project to each new session: it often costs more time than the
  code itself.

## What zplan does
zplan takes the part before and after each engine run and puts it in one terminal screen.

1. **Talk, then plan.** You discuss the idea with an architect agent in a chat. When it is clear, the architect drafts
   a goal; one choice turns it into a plan request.
2. **A plan you approve.** A planner breaks the goal into requirements, milestones and tasks; an independent verifier
   checks the plan. Nothing runs until you approve a specific revision. You can ask for changes or reject it.
3. **Milestones run in isolation.** Each milestone is one Zeroshot run in its own Git worktree: a worker per task,
   two reviewers, a repair loop. Your checkout is never edited by an agent.
4. **You watch, without babysitting.** The screen shows the plan, the live scheme of who is working, the round, the
   elapsed time and the time since the last event. Close the terminal and nothing stops; reopen and zplan reconnects.
5. **You merge.** A finished milestone becomes a result branch and a card in the chat: see the diff, merge it
   (`--no-ff`), or leave it. zplan never pushes. The next milestone becomes ready after the previous one is merged.
6. **Ready out of the box.** One installer pins the engine and agent versions zplan is tested against, keeps them in
   a private home with no stray tools, and checks readiness (tools, login, clean tree) before anything is spent.

## Who it is for
- Developers who work in a terminal and want AI agents to deliver goals larger than one task on their own repository.
- Zeroshot users who want planning, ordering and merging around their runs instead of writing them by hand.
- Its first user is its author: zplan is built with Zeroshot, and the target is to build zplan with zplan.

## What zplan is not
- **Not a fork or a second engine.** Zeroshot owns the run lifecycle and state; zplan only calls it.
- **Not unbounded autonomy.** From 0.6.0 the owner picks the autonomy level (`auto`, `supervised`, `manual`); zplan
  never acts past it, never merges with a red gate and never pushes, tags or publishes.
- **Not tied to one project.** It works on whatever repository it is started in.
- **Not a dashboard of agent internals.** Raw logs and tool calls stay behind an explicit action; the screen shows
  decisions, progress and causes.
- **Not a proven quality win yet.** Separate reviewers and an approved plan are the design bet; there is no
  measurement yet that the result beats a single agent.

## Principles
1. **The human sets the bounds:** in `manual` the owner decides at the plan and at the merge; `supervised` and `auto`
   (0.6.0) hand those decisions to the gates and the critic; outward actions (push, tags, publishing) stay the owner's.
2. **Closing stops nothing.** Planning and runs are background jobs; the screen is a view.
3. **No warning without its fix.** Every blocked state names the command that unblocks it.
4. **The user's words, not ours.** No run ids, phases or environment variables on the main screen.
5. **One screen, fixed zones.** Chat on the left, plan and live scheme on the right, one status bar. No hidden modes.
6. **Any terminal.** ANSI colours only, works at 80x24, over SSH, with `NO_COLOR`; no function keys.
7. **Reuse the engine.** A feature that the engine already has is called, not rebuilt.
8. **Light process.** Test depth follows what a person will touch; no ceremony for unseen code.

## Where it is going
| Release | Adds |
|---|---|
| 0.5.2 (this release) | The one-screen terminal UI (chat, plan, scheme, cards, `/` commands) |
| 0.6.0 (planned) | The architect leads: plans, briefs, preflight, parallel runs, verdicts and gated merges within the owner's autonomy level (docs/ARCHITECT_DESIGN.md) |
| Next (planned) | Build zplan with zplan: several live runs, review rounds and their verdicts visible in one screen |

Limits today: the agent provider is Codex only; a running planner is stopped from the line UI (`zplan --plain`)
until 0.6.0; macOS arm64 and Linux x86_64; the repository is not public yet.
