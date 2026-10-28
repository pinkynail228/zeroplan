# Release 0.6.1 plan: the architect runs unattended, cheaper, and the screen shows it

Owner 2026-10-26: do not wait for the owner's Mac test of 0.6.0; plan and start the next releases. 0.6.0 ships the
architect-led loop (docs/RELEASE_0.6.0_PLAN.md); the 0.6.0 scope cut moved A10 and A6b3 here. Inputs: the re-smoke
findings 2026-10-25 and 2026-10-25b (pause dir, dogfood), docs/ARCHITECT_DESIGN.md sections 4.2 and 9. Scope review:
critic r061-scope 2026-10-26, GO WITH CHANGES; its findings are folded in below.

## Goal
A trivial slice on a fresh repository with configured checks goes goal -> merged in `auto` with zero routine
confirmations (plan approve is the only ask; policy questions the architect raises count as separate outcomes, not
failures). The architect survives a hung or rate-limited turn, an event turn costs a fraction of today's, and the
screen tells what happens during planning and runs.

Measured baseline (re-smoke 2026-10-25b): 11 architect turns, 5.88M tokens; two slices attempted, one merged, plus a
replan and an export workaround; event turns 0.2-1M each; «сессия длинная: /new» at turn 7-8, mid-task. The baseline
is not a matched workload: C0 defines the matched one before any cost target binds.

## Slices (two lanes; at most two worker groups)
| # | Lane E (architect, Controller) | Lane T (TUI) |
| --- | --- | --- |
| 1 | C0 cost spike (low): where a turn's tokens go (method, snapshot, events, tool results, history) on the re-smoke transcripts; defines the matched workload (repo, goal, model and settings, token accounting, completion boundary) and the provisional target (-50%); docs/spikes/C0_ARCHITECT_COST.md | P1a interaction repairs (medium): the palette lists only commands that act now (`/run` with nothing to run); input loss (a dropped `/`, typing swallowed by the run screen); plan screen focus and Esc; stale renew with an empty note |
| 2 | A6b3 architect unavailable (high), see criteria below | P1b copy and layout (low): draft tab and «предпроверка · ждёт» retire; Settings «войти» phrase; `/details` text beside «подробнее»; `PRIMARY['tui_run']`; stale key comments (app.py F1, catalog.py Ctrl+R) |
| 3 | C1 cost cuts from C0 (medium): smaller snapshot and event batches; session rot by tokens, not turns, and the session counter resets on `/new` | P2 messages (medium): errors next to the card and input; the warm-up prompt not shown raw; one clock for chat and card stamps; stale status lines retire; no dangling «—» in the bar |
| 4 | Stuck signals (medium): 45 min round without review, 2 h run, after round 3 completes; advisory only, to the architect and the screen | A10a1 «Что происходит» during planning (planner timers, p2b) (medium) |
| 5 | Cleanup (high): see criteria below | A10a2 journal history pane with durations (medium) |
| 6 | — | A10b1 «Схема»: preset graph before start, each live run's node and round, a run list when several run (medium) |
| 7 | — | A10b2 plan tree (p3b) (medium) |

A6b3 criteria: hung-turn cancel; retry with backoff; pending events survive cancel and retries; catch-up runs before
any new admission; «архитектор недоступен» after the preset limit, and exhausted retries pause admission (running runs
continue); `/stop` stays usable throughout; `/new` without the model warms from snapshot, STATE and journal.

Cleanup criteria: only worktrees and branches of stopped or blocked attempts after their milestone merged; an attempt
with commits not reachable from main is kept and listed, never deleted; deleting a branch with unmerged work stays the
owner's at every level (ARCHITECT_DESIGN.md section 4, item 3 "Autonomy policy"): zplan lists it, the owner decides.

Shared files: `terminal_planner/catalog.py`, `docs/REFERENCE.md` and `terminal_planner/tui/app.py` have one owner at
a time: a slice that needs them runs after the previous owner merged (never two in flight). Controller and journal
interfaces freeze when A6b3 merges; lane T slices that read them start after that. Order: lane E C0 -> A6b3 -> C1 ->
stuck -> cleanup; lane T P1a -> P1b -> P2 -> A10a1 -> A10a2 -> A10b1 -> A10b2.

## Inputs from the 0.6.0 release (2026-10-26)
v0.6.0 = 4a6a22c tagged after the re-smoke (pause dir, dogfood, findings-2026-10-26-resmoke.md): in `auto` the
architect approved, started and merged M1 unattended once the owner confirmed its goal draft; 0.83M architect input
for one slice. Folded into the slices: C1 takes the wake turns that end «действий нет» (approved, review events) and
the `unknown` from-state in run events; P2 takes the merge card shown in `auto` while the architect merges and one
clock; held C1a and P1a are re-gated first. Owner decision 2026-10-26: `auto` submits the architect's own goal draft
(new slice D1: an autonomy action "submit"; supervised and manual keep the owner's `/plan`; after C1b). Test debt: Linux TUI races (tests.test_new_session c1, tests.test_tui_milestones a1b, both
failing before RS5/RS6), tests that read the installed tools, the architect method at its 4096 B cap.

## MVP for the owner's own test (owner 2026-10-26): before everything else
Owner: a short MVP now, so the owner checks the work himself; Russian is enough; a start screen with the logo.
Private tag `v0.6.1-mvp` when these four merge; every other slice of this plan waits for the owner's test.
| Lane | Slice | Owner sees |
| --- | --- | --- |
| E | O4 readable chat (brief o4-readable-chat) | start and `/new` show only the current session, no prompts |
| T | O3 command completion (brief o3-command-completion) | Tab completes a `/` command, arrows pick, Enter runs |
| E | O2a-mini start screen (after O4) | full-screen start: Zeroshot mascot + word mark, project step (this folder / another / quit; no Git or no commit -> `git init` + first commit; identity when Git has none); shown on every full-screen start; line prompts without a TTY; a quit before a project prints no «план сохранён» |
| T | U1 status line (after O3) | one line by the input says what happens now (the architect's turn beside the job phrase; a cancelled turn) |
Out of the MVP: English (O1a-d), the language, tools, sign-in and autonomy steps of the start screen (full O2),
P1b, D1, C/A6b3/A10, U2-U6. Gate per merge as the rules say; final check: the audit's scripted newcomer on a signed-in
HOME, the owner's case (empty folder -> start screen -> first architect reply -> goal -> merged in `auto`), run by the orchestrator.

## Owner Mac test of 0.6.0 (2026-10-26): first priority
Owner verdict on installed 0.6.0: not usable (pause dir, dogfood, findings-2026-10-26-owner-mac.md). These slices go
before every slice above except the running C1b and P1b and D1; C0 and the A10 screens move after them.
| # | Slice | Cause (read 2026-10-26) | Write-set core |
| --- | --- | --- | --- |
| O3 | Command completion (medium): Tab completes the `/` command while the palette is open; Up/Down pick a row; Enter runs the picked row; Tab still switches panes otherwise | palette is a display-only Static; Tab is a priority `toggle_focus` (app.py:628) | tui/palette.py, tui/app.py |
| O4 | Readable chat (medium): a start and `/new` show only the current session; handoff and warm-up prompts are never shown; one owner-readable line per event batch | `entries_of` shows the last 40 rows of every session; `/new` only appends; prompts stored as «соб» rows (chat.py:408, :901) | tui/chat.py, tui/chat_view.py, architect.py store |
| O2 | Start screen (high): one full-screen onboarding before the main screen: language, project (this folder; no Git or no commit -> offer `git init` + first commit, or another folder, or quit), login, tools check, autonomy; line prompts only without a TTY; a quit before a project prints no «план сохранён» | `choose_project` loops (cli.py:82); empty input and Ctrl+D misreport (cli.py:1077); language and profile come only after the project | cli.py, tui/app.py, tui/modals.py, tui/strings.py |
| O1a-d | English everywhere (medium each): a: main screen and chat (app.py, chat.py, chat_view.py, catalog labels the TUI uses) and the architect replies in the chosen language (architect.py:294); b: cards, scheme, screens, modals, controller; c: delivery, live, runs texts on screen; d: CLI, setup, doctor | only new widgets use `strings.text()`; ~1,300 Cyrillic literals outside the tables | per letter |

Order: lane T P1b -> O3 -> O2 -> O1a -> O1b; lane E C1b -> O4 -> D1 -> O1c -> O1d. app.py is shared: O3, O2, O1a
run one at a time; O4 does not touch app.py. The release gate adds: a fresh folder without Git, English chosen
first, reaches the chat through the start screen with no Russian on screen.

## Release gate
Smoke on a fresh repository with configured checks (also 80x24 and the Russian keyboard layout, not checked in 0.6.0):
goal -> merged in `auto` with zero routine confirmations; architect tokens per slice against C0's matched workload,
target -50% (provisional until C0). A forced architect failure (rate limit or killed turn) is measured separately:
recovery without owner action and no lost events. Full Mac + full Linux; fresh release critic; private tag.

## After 0.6.1
0.7.0 public release (owner-gated): the clean export of docs/PUBLIC_REPO_PLAN.md, the agent permission default
(STATE "Agent perms"), GitHub Pages, install route. Profile keys for the architect method (A11 "Later").
