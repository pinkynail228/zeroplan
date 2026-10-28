# Comprehension test

Give a fresh agent only the files of docs/product/ (not this one) and ask the ten questions. A pass is 9 of 10
answers matching the key in substance. A miss means the folder is unclear on that point: fix the doc, not the key.

| # | Question | Key |
|---|---|---|
| 1 | What is zplan, in one sentence? | A terminal client over the Zeroshot engine: goal in a chat, approved plan of milestones, each run by independent agents in the background, the human merges |
| 2 | What problem does it solve that Zeroshot alone does not? | Everything around a single run: splitting a goal into ordered tasks, plan approval, isolation, watching, merging |
| 3 | Name the two decisions that always stay with the human. | Approving the plan; merging a result |
| 4 | Where do agents make their edits? | In a separate Git worktree and branch per attempt, never in the user's checkout |
| 5 | Does zplan push or merge on its own? | No, never |
| 6 | Who owns the run state: zplan or Zeroshot? | Zeroshot; zplan only calls it and keeps the plan and its own run records |
| 7 | What happens to running work when the terminal is closed? | It continues; reopening zplan reconnects |
| 8 | When is plain Zeroshot the better choice? | A single self-contained change |
| 9 | Which claim does zplan explicitly not make yet? | That multi-agent results beat a single agent (not measured) |
| 10 | What are today's limits? | Codex only; macOS arm64 and Linux x86_64; not public yet; planner stop from the screen, planner timers and the plan tree come in 0.6.0 |

## Record
| Date | Agent | Score | Misses |
|---|---|---|---|
| 2026-10-24 | haiku, fresh | 9.5/10 | Q10 missed the 0.6.0 items; fixed: VISION limits line, run start vs "decides twice", state split in BOUNDARY, 0.5.2 marked current |
