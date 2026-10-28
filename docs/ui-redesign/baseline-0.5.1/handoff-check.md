# Check: do decisions made in the chat reach the plan? (zplan 0.5.1, 2026-10-22)

Question (owner): the planner never sees the chat; can it plan well from a prompt alone?
Setup: scratch repo `notes` (after the baseline merge). Three chat turns with the architect about an
`import` command, decisions given only in the chat, the last two of them correcting the architect's
own draft. Then `c` (open the newest goal draft) -> `ctrl+g` (planner + plan check, 110 s) -> read
the stored proposal (requirements and task checks).

| Decision, said only in the chat | In the goal draft | In plan requirements | In task checks |
|---|---|---|---|
| import replaces the whole store | yes | R2 | T1, T2 |
| duplicate texts skipped, first kept | yes | R2 | T1, T2 |
| any file error: store untouched, exit 2 | yes | R4 | T1, T2 |
| success prints exactly "Импортировано N" | yes | R4 | T1, T2 |
| correction: ignore the id column | yes (replaced "id must be 1..N") | R1 | T1, T2 |
| correction: empty texts dropped silently | yes (replaced "empty text allowed") | R2 | T1, T2 |

Result: 6 of 6 chat decisions reached the plan, corrections included; the planner also read the
code itself (task checks name `list`, `export` and existing tests).

Risk seen: the architect added its own assumptions (header-only CSV clears the store, a fully empty
file is an error, atomic write). It flagged them for the owner in the first draft, but the corrected
draft kept them without the flag, and they went into the plan as requirements (R3, R4). The owner
only sees them by reading the draft. UI consequence for 0.5.2: the "make a plan from this?" card
shows the whole draft, the exact text the planner gets.

Plan r2 was left unapproved after the check; nothing ran.
