# Terminal UX

The 0.6 terminal UX: an English, PTY-testable interface in two forms. The full-screen shell is what `zplan` opens
on a terminal; the line UI (`zplan --plain`, also used for `TERM=dumb`, pipes and every subcommand) is its
line-oriented sibling. This is the normative design; [USER_FLOW.md](USER_FLOW.md) describes the screens, commands
and buttons as implemented.

## Full-screen shell

Owner 2026-10-25: no single-letter keys. The keys are Tab, ←→, ↑↓, Enter, Esc, PgUp/PgDn and Ctrl+Q; every action
is a `/` command typed in the chat input, and every screen, modal and decision card answers with buttons. A card's
button runs the same `/` command a typed line does.

- Input: a line that is not a `/` command goes to the architect chat; a `/` opens a palette of the commands the
  current state allows.
- Palette keys: ↑↓ pick a row (wrapping), Tab completes the picked command's name plus a space, Enter on a bare
  prefix (`/ap`) runs the picked command. With no palette, Tab still switches input and plan pane, and ↑↓ in an
  empty input recall the previous lines of this run. The bar names these keys while the palette is shown, (`bar.key_complete`, `bar.key_pick` in `strings.py`).
- Each screen ends with a "Next:" hint, and the hint names a command or a button (`/run`, «merge»), never a letter.
- Enter only sends or presses the focused button. Approve, start, merge and stop always need their own command or
  button (a start, a stop and the plan screen's approve also ask «yes» / «no»).
- Milestone states: waiting, ready, running, needs an answer, blocked, failed (can continue / cannot continue),
  waiting for merge, conflict, merged, submission status unknown.

Flows:

- No plan: tell the architect the goal in the chat -> card «Goal draft» -> «yes, draft the plan» (`/plan`; or type
  `/plan <goal>`) -> planner progress -> card «Plan» -> «yes, approve» (`/approve`) or «no, revise»
  (`/decline`, then a revision note). `/view` opens the plan screen with its buttons.
- Ready: `/run` shows worktree, branches, models and bounds in a confirmation -> «yes» -> observe: one line per
  progress record ("T3 · implementation", "T3 · review: rejected, repair 1/3", "plan: +T8 split T3"). Ctrl+Q = detach
  (the run continues; `/attempt` watches it again); `/stop` stops with a confirmation.
- Done: card «M1 ready» with the tasks line -> «merge» (`/merge`) or «see the changes» (`/diff`).
- Needs answer: card with the steward's question -> «simplify», «split», «skip» (`/approve`), your own words
  in the answer note (`/decline`) or the architect's draft (`/answer`).
- Blocked: the run-end screen (`/attempt`) -> «answer» or «to plan». Recoverable failure: the red card -> «try
  again» (`/retry`) or «details» (`/details`).
- Conflict: files list, hint to resolve manually and rerun `zplan` (ancestry detection finishes it).

## Line UI (`zplan --plain`)

The line UI keeps its letters: type a key, optionally followed by a milestone id, and press Enter. Home (`zplan
--plain`; `zplan status` prints it without prompts):

```
zplan · <project> (<branch>, clean)
Goal: <goal, 1 line>
Plan r3 · approved · 1/4 stages merged
  ✓ M1 <title>        merged a1b2c3d
  ▶ M2 <title>        running · task 3/5 (T7) · review
  · M3 <title>        waiting for M2
Next: [w] watch M2
[w] watch  [p] plan  [r] reconsider  [s] settings  [q] quit
```

Each screen ends with a "Next:" hint and single-letter keys; Enter only navigates (approve, start, merge, stop
always need their key). Flows:

- No plan: goal (multi-line, empty line ends) -> roles summary -> planner progress -> proposal view ->
  [a] approve [r] revise [x] decline.
- Ready: [g] start M<n> -> observe; Ctrl-C = detach (run continues); [k] stop = force-stop with
  confirmation.
- Done: [m] merge into <branch> [d] diff [l] later. Needs answer: [a] accept [t] answer [x] stop. Blocked: [t]
  answer and restart [p] plan. Recoverable failure: [g] continue.

No internal JSON, digests or receipts in the normal flow. The earlier 0.2 design brief stays in the private archive.
