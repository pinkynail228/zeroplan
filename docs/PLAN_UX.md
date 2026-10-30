# Plan: UX after 0.9.0 (0.9.1, 0.9.2)

Status 2026-10-30, after critic planux (AGREE WITH CHANGES, all taken). Follows docs/PLAN_0.9.md (0.9.0 = P1-P4,
P6). Goal in user terms: from `zplan` in a fresh repo to a merged change with no relay step, no false line on
screen, nothing written into the user's repository they did not ask for, and no decision the system could take
within the autonomy level.

Evidence (private archive, records): soak-083rc1 N1-N8; walk-0.8.2 steps 2-12; walk-rc1 N1-N7, W4/W8/W13/W14;
0.8.1 testers F6, F7, F10; the relay survey B10 and the surface inventory in the pause dir (static scenarios, not
incidents); carried from 0.9.0: P5 (F4), P7, Q4, the end screen's merge confirm.

## 0.9.1 (in this order; tasks sharing tui/app.py, tui/controller.py or card_kinds.py run one after another)

| Milestone | Tasks (one behaviour each) | Evidence |
|---|---|---|
| U1 Work continues after a fix | T one resume path: "try again" after the missing prerequisite is fixed (origin added, check passing) restarts the request the owner made (N2, B10 11); T the demo and the start screen say how to set a Git identity before /run fails (N4) | soak N2, N4 |
| U2 One true merge result | T one merge record in order, history "merged" after the architect's merge (S5 half, W8); T the end card shows when the main screen returns (B10 8); T the end screen's «merge» acts at once (F3 rest) | walk step 12, soak S5 |
| U3 Nothing written that the owner did not ask for | T a project without a GitHub origin gets a local identity; the user's remote is never touched and no origin card is shown (Q5; removes W13 and S2's 46k-token draft before the refusal); T profile persistence: an accepted profile lives in zplan's store, `zplan profile init` writes the file, and a file the owner writes later wins (Q4) | walk-0.8.2:41, walk-rc1:52, soak S2 |
| U4 Small truths | T the origin notice clears once an origin exists (N1); T the demo's "starts the first stage" only when it does (N6); T the merge row at manual names the owner's /merge (N5); T the disk-root refusal suggests a writable folder (N3); T merge and attempt commits carry the milestone title (W14, `runs.title`) | soak N1, N3, N5, N6; W14 |
| U5 The UI acts on events (P7) | T plan ready -> Plan tab through `move_tab`/`owner_tab`; T a stale goal draft re-asks the architect; T a stale proposal wakes the architect to revise (the freshness rule unchanged); T re-observe with backoff, a line only after repeated failures; T reconcile an unconfirmed submit on open (no automatic resend) | B10 4-10 |
| U6 Scheme that moves | T finished nodes turn done; T the running node is named by its node, not the shell (N7, rc1 N2) | soak N7 |

## 0.9.2

| Milestone | Tasks | Evidence |
|---|---|---|
| U7 First start in the chat | design -> critic -> tasks: profile and project choices as cards the architect proposes, the deterministic actions kept for the demo and before login; the first-start modal goes | F6, F7 |
| U8 One interface | T routing: no TTY prints "run zplan in your terminal", `--plain` says the mode is gone; T delete menu-only code, its tests and docs; `App` and subcommands stay | replan C2, Q2 |

Later: the project picker's typed path (F10); F4 stale-plan rule (its own design); M3 facts and rule order; a commit
summary beyond the title; narrow panes (W10). Not a task: N8 (rc and final carry one version by design).
Not doing: new gates, a total test metric, a second UI.
