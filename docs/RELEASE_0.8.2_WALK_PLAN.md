# Plan: 0.8.2 after the real walk (Track C)

Status 2026-10-29. Critic walk082 (xhigh): AGREE WITH CHANGES, all five taken (W4 to K9, C1b, C2's rule in
every turn, U2's walks, P3's guard). This plan follows docs/RELEASE_0.8.2_PLAN.md (Track A: every item merged but A9, which is
running). It is deeper, not wider. Its input is one real walk, not memory. Each finding is placed in a failure
class, and each class gets one mechanism. Each mechanism has an acceptance check someone can rerun.

## Input: the walk

Walked on 2026-10-29, 00:53-01:04, with main at 07605e9.
- Who: an agent driving a real pty at 120x40 (key screens also at 80x24), with real Codex and the owner's HOME.
- Project: a fresh word-count Python project with no GitHub origin; its unittest file sits at the root.
- Path: start screen, a goal in the chat, a plan, auto-approval, the M1 run, the merge.
- Result: merged in about 11 minutes, with no hang. The 5 project tests pass after the merge.
- Where the evidence is: the log is walk-0.8.2.md and the snapshots are 01-25, both in the pause dir, folder walk.

| # | Seen | Severity | Class |
|---|---|---|---|
| W1 | The architect asks "Merge M1?" and the owner answers yes, but the merge is refused: the level leaves it to the owner (controller.py:1048) | major | K1 |
| W2 | `test_wc_cli.py` at the root is not found: "no qualification", merge gate off, merged with no test run (process.py:661) | major | K2 |
| W3 | At `auto` the plan card says the architect approves, while the canvas says "waiting for your yes · /approve" (app.py:645) | minor | K4 |
| W4 | At `auto` the milestone list is not shown before the approval | minor | K9 |
| W5 | Scheme shows `◌ preflight · waiting` and `◌ pick check · waiting` while the worker runs (scheme.py:599) | minor | K3 |
| W6/W7 | "nothing has happened yet" while a plan is being drafted and after a run merged (delivery.py:541, :566) | minor | K3 |
| W8 | The merge receipt appears above older chat lines, and there are three merge lines (card_host.py:673) | minor | K6 |
| W9 | `Next: /attempt watch M1` (app.py:173, no label for `w`) | minor | K4 |
| W10 | A diff in the 46-column pane is cut (`5 dele`) | minor | K5 |
| W11 | "↑↓ choose" on buttons laid out left to right; the selection could not be read in the pty capture | minor | K4 |
| W12 | The profile modal shows `[tab] later [right] configure`, but the buttons are accept, configure, later (catalog.py:700) | minor | K4 |
| W13 | A local project gets a fake `github.com/local/proj` origin card with an unlabelled field | minor | K7 |
| W14 | Commit texts are `zplan: Milestone M1 attempt 1 (plan revision 1)` | minor | K8 |
| W15 | After everything merged, Next says `/view → revise`; a new goal is typed in the chat instead (delivery.py:562) | minor | K4 |

## Failure classes and their mechanisms

| Class | Findings (also older) | Mechanism (one per class) | Where |
|---|---|---|---|
| K1 The owner as the system's hands: the system leaves an action to the owner, but tells them neither that nor how | W1, F11, F12 | Each refusal that leaves an action to the owner names the exact command or card. The architect never asks for a yes in the chat for such an action. | C2 (rc1); B10 (0.9) |
| K2 A safety gate that is missing without anyone saying so | W2 | The proposed profile finds the common test layouts. A profile with no check says, on its card, that merges then run no tests (already true: "no qualification") | C1 (rc1); more layouts in the ledger |
| K3 The screen shows work as idle while it runs or after it ends | F9, W5-W7 | Each pane reads the same fact as the engine: the observed attempt's or the planner's journal; earlier steps are done once a task is picked; the tab follows the confirmed event once | A9, C4 (rc1) |
| K4 A hint names a step that is wrong in that state | W3, W9, W11, W12, W15 | Hints come from the state and the real key map: the canvas reads the autonomy level, every rewritten key has a label, the key bar follows the button order | C3 (rc1) |
| K5 Content lost in a narrow pane | W10, the bar at 80x24 | Wrap or scroll; a cut is marked | soak, then 0.9 |
| K6 Chat order | W8 | A receipt is a new line at the bottom; one line per event | 0.9 |
| K7 Onboarding asks what zplan could find out | W13, F6, F10 | Facts first (B3), the chat-first design (B5) | 0.9 |
| K8 Engine-made commit texts | W14 | The commit says what changed (the task title) | 0.9, upstream first |
| K9 A decision made before the owner can see what it decides | W4 | At `auto` the plan card lists the stages before the architect approves | soak, then 0.9 |

## Cut line

| Bucket | Items |
|---|---|
| rc1 (5 + A9) | A9 the tab follows the work; C1 + C1b root unittest files, only where a file imports unittest (critic Q3: a pytest-style file would give a check that finds 0 tests, exit 5); C2 the ask refusals name the command; C3 the hints are true (W3, W9, W12, W15); C4 the journal and the scheme show finished work (W5-W7) |
| soak | W10, the bar at 80x24, W11 checked in Terminal.app, W4 |
| 0.9 | W8, W13 (B5), W14, K1's chat consent (B10) |

## UX acceptance for rc1 and how it is checked

| # | Criterion | Check |
|---|---|---|
| U1 | A fresh Python project with its tests at the root gets a check, and its merge runs it | Rerun the walk on the rc1 tree. The profile card names `python3 -m unittest`, and the merge record has a passing check |
| U2 | The architect never asks for a yes it cannot act on. A refusal names the command | Two extra walks, because after C1 the first walk's merge is allowed (critic Q4): `auto` on a project with no check, and `supervised`. In each, the architect's message before the merge or approval asks for no yes and names the card or command; a forced tool call's refusal contains `/merge` or `/approve` |
| U3 | No "nothing has happened yet" while a plan is being drafted or after a merge; no `◌` step above a running worker | grep over the walk snapshots |
| U4 | Every `Next:` line shown is a command that exists and works in that state | Collect the Next lines from the snapshots; each command word is in slash.COMMANDS and is accepted in that state |
| U5 | After an approval or a start, the tab moves once; after the owner's own switch it stays | The walk: approve, then start, then the owner switches tabs during the run |
| U6 | Light and dark, at 80x24 and 120x40: every text on the start screen, chat, card and scheme is readable | Terminal.app window shots (Novel, Pro) of four screens, looked at by eye |

## rc1 re-walk (2026-10-29, main 1552ea4, real Codex; three walks: auto with a check, auto with no check, supervised)

| U | Verdict | Evidence |
|---|---|---|
| U1 | PASS | the profile names `python3 -m unittest`, merge required; the merge check ran 8 tests OK; a pytest-style root file gave "no qualification" |
| U2 | PASS | auto, no check: "Use M1's merge card or `/merge`"; supervised: "Use the plan r1 card or `/approve`", then the merge card or `/merge`; no chat yes asked |
| U3 | partial | journal right while drafting and after the merge; `◌ task pick · waiting` above a running worker (N2) |
| U4 | PASS | every Next line a working command; outside Next, `/details details` on the Goal line (N3) |
| U5 | PASS | approve -> Plan once, start -> Scheme once; the owner's own tab choice kept |
| U6 | not run | no window shots overnight (display asleep) |

| # | New finding | Severity | Decision |
|---|---|---|---|
| N1 | Supervised `/merge` answered "Not done ... repeat the merge [merge.critic_pending]"; the owner pressed it three times over 11 minutes | major | rc1: c6 (the merge waits for the critic and says so) |
| N2 | `task pick` (the loop's next pick) shows waiting above the running worker; it is the next step, so the state is true but reads as idle | minor | 0.9 (K3) |
| N3 | `/details details` outside Next lines | minor | rc1: c7 |
| N4 | Skipping the origin card does not say planning then refuses; `/retry` does not re-offer it, `/plan` does | minor | soak (K7, B5) |
| N5 | "Implementation was not started; start it with /run" stays after zplan started and merged | minor | rc1: c7 |
| N6 | The merge critic record's diagnostic holds a planner sentence | minor | 0.9 |
| N7 | "nothing has happened yet" for about 2 s when M1 starts | minor | accept |

## Residual-risk ledger

| # | Risk | Decision |
|---|---|---|
| R1 | A terminal reply tail that arrives more than 100 ms after a stall is typed as text (A3) | accept for rc1; the soak looks for it |
| R2 | No single key empties a multi-line input | accept; 0.9 |
| R3 | The owner's message colour and the architect's code block in light were checked only by tests | close: a Terminal.app light shot with a real architect reply before rc1 |
| R4 | s2a's revert check only showed ModuleNotFoundError | accept: s2b's real-pty A/B covers the behaviour |
| R5 | W11: whether the selected card button is visible was not seen in a real terminal | close in the soak (a Terminal.app shot) |
| R6 | The start screen shows 0.8.1 on the 0.8.2 code | close: the release bump |
| R7 | Codex gives every role the root AGENTS.md with no rank; the ranked copy reaches only planning roles (B1 research) | accept for 0.8.2; Track B decision |
| R8 | Other test layouts (a `test/` folder, `*_test.py`, other languages) still get no check | accept; the card says "no qualification"; 0.9 with B3 |

## Pre-mortem: rc1 shipped and a tester still got stuck. Why?

| # | Story | Guard |
|---|---|---|
| P1 | The tab jumped while the tester was reading | A9 F2: the owner's own switch wins; U5 tests it |
| P2 | Root tests need packages that are not installed, the check fails, and the merge is blocked | The failure is shown and the profile can be edited; that is the project's own truth; accepted |
| P3 | Runs merged in parallel broke each other | Each merge gate runs every TUI module plus the touched modules on main plus the change, not the whole suite; the whole suite runs once on the candidate (mac-test.sh). Residual: a non-TUI module broken by a merge is found only at the candidate |
| P4 | The toy walk passed, but a real repository failed | The soak walk uses a clone of a small public Python repository from a clean HOME, plus the past cases |
| P5 | The version still said 0.8.1 | The candidate checklist bumps it and the walk checks it |
