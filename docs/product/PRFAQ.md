# PR/FAQ

## zplan: plan with AI agents, watch them build, merge what you approve

*A terminal client for the Zeroshot engine.*

Building a real feature with an AI agent still means one long session, a big prompt and a surprise at the end.
Zeroshot fixed the inner loop: a worker writes, independent reviewers check, a repair worker fixes, until the change
passes. zplan adds the outer loop. You talk the idea through with an architect agent, get a plan of milestones that
an independent verifier has checked, approve it, and let each milestone run in its own Git worktree. One terminal
screen shows the plan, who is working, which round, and how long since the last event. When a milestone is done, a
card in the chat shows the diff; you merge it or not. Close the terminal and the work goes on.

[Author quote: to be written by the owner.]

Run `zplan` in any Git repository. The installer pins the engine and agent versions zplan is tested against.

## FAQ

**Why not just use Zeroshot?**
For one self-contained task, do. Zeroshot runs one task per run; zplan plans the goal into ordered milestones,
isolates each run in a worktree, keeps the plan and the merge as your decisions, and gives you one screen to leave
and come back to.

**Why not one coding agent (Codex, Claude Code) in a long session?**
One agent approves its own work and drifts on large goals. zplan separates the roles: planner, plan verifier,
worker, reviewers. Whether that gives better results than a single agent has not been measured yet; it is the design
bet, not a proven claim.

**Is it a fork of Zeroshot?**
No. It installs the official engine and calls its public interface. The engine owns run state; zplan stores only the
plan, its revisions and its own run records.

**Will it change my code without asking?**
Agents work in a separate worktree. zplan never merges without your confirmation and never pushes.

**What does it cost?**
Model tokens of the planner, workers and reviewers, on your own agent account. Several agents per change cost more
tokens than one. `zplan --fixture demo` shows the flow with no model calls.

**What if a run hangs or I close the laptop?**
Runs are background jobs of the engine. The screen shows the time since the last event; you can stop a run with
`/stop`. Reopening zplan reconnects to whatever is still running.

**Which agents, which systems?**
Codex today. macOS arm64 and Linux x86_64. Any terminal, 80x24 and up.

**Does it work on my project?**
It is not tied to any project: it takes the repository it is started in and the rules in its `AGENTS.md` /
`CLAUDE.md` and `zplan.process.json`.

**How mature is it?**
Pre-1.0, used daily by its author on real repositories, including zplan itself. 0.5.2 is the first release with the
one-screen interface.
