# zplan 0.6.0: heuristic evaluation (terminal UX)

Date: 2026-10-26. Evaluator: heuristic pass, read-only. Repo HEAD 9b6316b (code = tag v0.6.0 + briefs).
Scale: Nielsen severity 0-4 (4 = catastrophe, fix before release; 3 = major; 2 = minor; 1 = cosmetic).
Heuristics: N1 visibility of status, N2 match with the real world, N3 user control/freedom, N4 consistency,
N5 error prevention, N6 recognition over recall, N7 flexibility/efficiency, N8 minimalist design, N9 error
recovery, N10 help/documentation; clig.dev: C-help, C-output, C-errors, C-interact, C-naming, C-robust.

Evidence keys: `NN` = `~/zs-pause/ux-audit/sb8/caps/NN-*.txt` (real first run, 43 steps, 2026-10-26);
`g:<name>` = `~/zs-pause/ux-audit/gallery-main/<name>.svg` (fixture); `T` = owner's real transcript
(`~/.local/share/planning-kit/architect/zeroshot-planning-kit-6eb4fc279e3b/transcript.jsonl`); code paths are
relative to the repo, `tui/` = `terminal_planner/tui/`.

Verdict: the product works end to end, but a newcomer cannot get from install to a first answer without
outside knowledge (git, where sign-in lives), and once in, the screen does not answer "what is happening".
34 findings: 3 catastrophic (sev 4), 9 major (3), 15 minor (2), 7 cosmetic (1). Most of the sev 3-4 ones map to
the 0.6.1 slices O1-O4, but three have no planned fix: F02 (no coherent "what is happening", sev 4), F08
(raw markdown and engine jargon in replies) and F12 (palette capped at 7 of 20 commands).

## 1. State inventory

| # | Screen x state | Reached by | Evidence | Worst finding (sev) |
|---|---|---|---|---|
| S01 | install.py output | `python3 install.py` | 01 | F33 (1) |
| S02 | Line mode: folder is not a Git project, path prompt loop | `zplan` in a non-Git folder | 02-05, cli.py:82-94 | F03 (4) |
| S03 | Line-mode close line | Ctrl+C / Ctrl+D anywhere in line mode | 06, 07, 13, cli.py:1078 | F23 (2) |
| S04 | `zplan --help` | shell | 08 | F22 (2) |
| S05 | `zplan doctor` (before setup / after setup / after login) | shell | 09, 11, 30 | F21 (2) |
| S06 | `zplan setup` | shell | 10 | F33 (1) |
| S07 | `zplan login` device code | shell, or Settings «войти» | 12, 25 | F05 (3) |
| S08 | TUI first open: Interface language modal over main | first `zplan` in a Git project | 15 | F34 (1), F07 (3) |
| S09 | Process-profile modal (BootstrapScreen) 120x40 / 80x24 | after language | 16, 16b, modals.py:88 | F10 (3) |
| S10 | Main idle, not signed in | after profile | 17, 27, 28 | F06 (3), F11 (3) |
| S11 | Main idle, signed in, empty chat | `zplan` with login | 31, g:idle-120x40 | F04 (3), F13 (2) |
| S12 | `/` palette: bare, filtered, after Tab | type `/` | 18-23, 24a, g:palette-* | F09 (3), F12 (3) |
| S13 | Settings screen | `/setup` | 24, screens.py:229 | F24 (2) |
| S14 | Sign-in from Settings (TUI suspended), Ctrl+C | Settings «войти» | 25, 26 | F05 (3) |
| S15 | Goal sent, architect thinking | Enter on a goal | 32 | F02 (4), F14 (2) |
| S16 | First reply + goal-draft card + "Goal draft" tab | reply arrives | 33, 33b | F08 (3), F15 (2) |
| S17 | Planning running (scheme "Planning · running", "Usually 1-3 minutes") | card «yes, draft the plan» / `/plan` | strings.py:302-318 (not captured) | F02 (4) |
| S18 | Plan ready card + Plan tab | planner done | g:plan-ready-120x40 | F29 (1); card itself good |
| S19 | Milestone running (title, scheme, activity, bar) | `/run` / auto | g:running-120x40 | F02 (4) |
| S20 | Owner-question card (simplify / split / skip / own words) | steward asks | card_kinds.py:465, strings.py:239-249 | F07 (3, RU labels) |
| S21 | Awaiting-merge card + Changes tab | milestone done | strings.py:233-238 | no new issue |
| S22 | Failed / stopped card; RunScreen end-of-attempt modal | run fails | card_host.py:320, modals.py:315 | F29 (1) |
| S23 | `/new` in progress and done | `/new` | 34-37b | F01 (4), F16 (2) |
| S24 | File tab (`/open`) | `/open README.md` | g:file-120x40 | F30 (1) |
| S25 | Help modal | `/help` | modals.py:40, app.py:318 | F27 (2) |
| S26 | Confirm modal (stop plan, run, stop) | `/stop`, `/run` | strings.py:181, modals.py:54 | F29 (1) |
| S27 | Note / Text modals (revise note, answer) | «no, revise», `/answer` | modals.py:220-312 | F26 (2) |
| S28 | Finishing modal (quit during a mutating job) | Ctrl+Q mid-job | modals.py:210 | none found |
| S29 | Narrow 80x24: idle, reply, running, palette, after /new | resize | 31b, 33b, 37b, g:*-80x24 | F18 (2) |
| S30 | Quit | Ctrl+Q | 29, 38 | F32 (1) |
| S31 | Plan screen | `/view` | screens.py:66 (not captured) | F07 (3, RU) |
| S32 | Line UI home (`--plain`) | `zplan --plain` | TERMINAL_UX_BRIEF.md (not captured) | F25 (2) |

Not captured live: S17, S20-S22, S24-S28, S31, S32 were scored from compose code, the string catalog and fixture
SVGs; their severities are conservative.

## 2. Findings (sorted by severity)

Lab = fixed by the approved lab `devtools/ui-lab/welcome.py` (y / p = partly / n). Planned = 0.6.1 slice that
targets it (docs/RELEASE_0.6.1_PLAN.md "Owner Mac test"; O2 mockups in `~/zs-pause/ux-audit/mockups/`).

| ID | State | Finding (what the user sees) | Heuristic | Sev | Evidence | Lab | Planned |
|---|---|---|---|---|---|---|---|
| F01 | S23 | `/new` does not clear anything. The old conversation stays. zplan's own prompts then appear as chat entries: the handoff order, the full project STATE (`## Next/## Open/## Decisions`, dated) and the raw JSON "Снимок экрана: {"branch": …}". The architect repeats the same goal draft. The owner's "chat is a mess" in one step. | N1, N8, N2 | 4 | 35, 36, 37, 37b; tui/chat.py:172 (only the STATUS_PREFIX lines are filtered), :408-411, :916-922; T: 2 `events` rows of 179 and 2394 chars shown as entries | n | O4 |
| F02 | S15, S17, S19, S29 | Nothing answers "what is happening now". While the architect thinks, the bar says "nothing runs" and the activity pane "nothing has happened yet". During a run the title and bar say "M1 running", the scheme shows one line "running 1 s" and the activity pane still says "nothing has happened yet". The three zones disagree, and the architect's work is not in any of them. | N1 | 4 | 32; g:running-120x40 (+png); tui/activity.py:1-25 (journal lines only) | p (one notice line "◐ Planning · step · 4 min /status") | none |
| F03 | S02 | In a folder without Git, zplan drops to a line prompt "Git-проект (путь)". Enter, the folder name and "." all get the same refusal. There is no `git init` offer and no way out except Ctrl+C. The user has to leave the product and know git (45 keystrokes at step 14). | N9, N3, C-errors | 4 | 02-05, 14; cli.py:82-94 | n (browses folders, no git init) | O2 |
| F04 | S08-S11 | No onboarding. The first full screen is a language modal over a red error. Then an empty chat with a raw error. Nothing says what zplan does, shows an example goal or explains chat → draft → plan → run → merge. | N10, N6 | 3 | 15, 17, 31 | p (prompt "Опиши, что хочешь сделать", notices, key line) | O2 |
| F05 | S07, S12-S14 | No sign-in path inside the TUI. The palette has no `/login` (`/log` = run log). Sign-in hides behind `/setup` → Russian Settings → Tab → «войти». Ctrl+C on the device-code screen exits zplan with no message and never returns to Settings. | N6, N3, N9 | 3 | 18, 22-26 | y (`/login` + red notice with action) | O2 |
| F06 | S10 | A goal typed while signed out does nothing: the text stays, no new line appears. The refusal is the same text already on screen. | N1, N9 | 3 | 28; tui/chat.py:660-661; tui/app.py:1449-1455 | p (warning before typing) | O2 (partly) |
| F07 | all | Choosing English is not honored. The profile modal, chat errors, right pane, Settings, doctor, `--help`, close lines, key labels and the architect's replies are Russian. 29 of 43 steps show Russian after English was chosen. About 600 lines of hard-coded Cyrillic literals live outside the catalog (app.py 134, cli.py 87, authority.py 86, setup.py 83, controller.py 46, chat.py 38). | N4, N2 | 3 | 16, 17, 24, 33; steps.tsv `ru_in_en`; grep count | n (lab RU only) | O1a-d |
| F08 | S16, S23 | Replies are hard to read. Markdown comes through raw (`##`, `**`, backticks, fences). Each reply carries an internal label "ответ 1 · арх · черновик цели:". Engine words appear (planner → verifier → approval, Controller, run_failed, zplan_status, STATE). | N2, N8 | 3 | 33, 36, 37; T: architect max 1460 chars with code fences; tui/chat.py:1137-1139 | n | O4 partly (prompts only); markdown/jargon unplanned |
| F09 | S12 | The palette only displays. No row is highlighted and ↑↓ do nothing. Tab moves focus to the right pane silently (only a border colour changes) and drops the "/". Enter on a prefix is "no such command". | N3, N7, C-interact | 3 | 19-23; tui/palette.py:70-111; tui/app.py:628 | y (OptionList dropdown with highlight) | O3 |
| F10 | S09 | The first decision asked of a newcomer is in jargon: "Process profile (zplan.default/2)", roles planner/critic/worker/reviewer/steward with model ids, "qualification", "plan check: required". Accepting quietly writes a file. | N2, N8 | 3 | 16, 16b | n | O2 (autonomy step) partly |
| F11 | S10 | The right pane says "No plan. Next: write the goal to the architect" while the chat cannot answer (not signed in). The hint points into the dead end. | N1, N2 | 3 | 17, 28 | y (notices replace the hint) | O2 partly |
| F12 | S12 | The palette shows at most 7 of 20 commands. On a bare `/`, `/help`, `/new`, `/stop`, `/quit` and `/log` are never visible, and descriptions are cut ("set up the project and si…"). | N6, N10 | 3 | 18, 24a; tui/palette.py:31 `MAX_ROWS = 7`; tui/slash.py:65-86 | p (7-item list includes /help) | none |
| F13 | S11, S29 | The chat header shows model id, provider, the CODEX_HOME path, turns and tokens. PRINCIPLES 7 forbids this. At 80x24 the full path takes 3 of about 18 rows. | N8 | 2 | 31, 31b, 37b | y (silent when healthy) | none |
| F14 | S15 | "думает… 0:03" is drawn above the user's own message. No hint says Esc cancels. Times are UTC (06:02 shown, 09:02 local). | N1 | 2 | 32 | n | none |
| F15 | S16, S23 | The architect tells the user to "transfer the draft into the zplan interface for planner → verifier → approval", while a card with «yes, draft the plan» sits right below it. That is two conflicting instructions. | N2, N4 | 2 | 33, 36 | n | none |
| F16 | S23 | After `/new` the tab strip shows "Goal draft  Goal draft" and a second identical draft card appears. The progress line "Сохраняю передачу дел…" appears at the top of the chat, far from the input. The capture caught it about 5 minutes later. | N1, N4 | 2 | 35, 36 | n | O4 partly (dup tab not listed) |
| F17 | S15 | Esc is overloaded: it closes the palette, else closes a canvas tab, else cancels the running architect turn with no confirmation. One stray Esc throws away a paid turn. | N5, N3 | 2 | tui/app.py:1521-1532 | n | none |
| F18 | S29 | At 80x24 the right column is hidden. A running milestone is only the bar segment "M1 идёт 0:00:01", and the bar itself is cut ("esc з…"). The planned one-line run summary (WORK_SCREEN.md, narrow) is not built. | N1 | 2 | g:running-80x24, 31b | n | none |
| F19 | S11 | The chat never says which project the architect works in (only the dim bar does). The owner asked the architect "в какой директории ты работаешь?" | N1 | 2 | T (2026-10-22 owner row); 31 | y (context line project · branch · changes) | O2 partly |
| F20 | S09, S05 | Accepting the profile writes an uncommitted `zplan.process.json`, which then makes doctor report BLOCKED. Doctor also says BLOCKED for "no GitHub origin" and "no Git identity" while the chat works fine, so BLOCKED stops meaning anything. | N9, C-errors | 2 | 17, 30, 11 | n | none |
| F21 | S05 | Doctor shows 5 BLOCKED lines in mixed RU/EN with internal terms ("Native controller socket path", "Frozen state/intent", digest). It tells the user to "нажмите [l]" in a shell, and dumps a 20-line profile. | C-output, C-errors, N2 | 2 | 09, 11, 30 | n | O1c/d (text only) |
| F22 | S04 | `--help` is Russian only and has no examples. It says "? on any screen shows the keys", but the TUI has no `?` key (TERMINAL_UX_BRIEF: no letter keys). It points to docs/REFERENCE.md, which is not installed, and lists dev flags (--fixture, --native-binary, --state-dir) to users. | C-help, N10 | 2 | 08 | n | none |
| F23 | S03 | The close line "Сессия закрыта. План и запущенные milestones сохранены; прогон не отменён" is printed when no plan or run ever existed, including after a cancelled login. | N1, N2 | 2 | 06, 07, 13; cli.py:1078 | n | none |
| F24 | S13 | Settings is a wall of absolute paths and engine terms. The buttons «установить войти проверить роли» show no focus until Tab. Russian only. | N8, N2 | 2 | 24 | p (`/setup` as a command, no screen) | O1b, O2 |
| F25 | S02, S32 | Two interaction models. The line mode, which a newcomer meets first, uses single letters. The TUI uses `/` commands only. Help text mixes both. | N4 | 2 | 02, 08; docs/TERMINAL_UX_BRIEF.md | n | none |
| F26 | S27 | In the Note modal Enter does not send (Tab to the button, then Enter), while Enter sends in the chat input. | N4 | 2 | tui/modals.py:220-226 | n | none |
| F27 | S25 | `/help` is a Russian key list titled with catalog names ("Полноэкранный режим: поле ввода"). It has no command overview and no explanation of the flow. | N10 | 2 | tui/app.py:318-328; catalog.py:455-481 | p (/help listed) | none |
| F28 | S10 | User-facing errors carry internal tags ("[код: readiness.auth]") and full sandbox paths. | N8 | 1 | 15, 17 | y | none |
| F29 | S18, S22, S26 | Revision and stage ids in copy: "План r1", "Stop planning of plan r1?" (PRINCIPLES 7). | N2 | 1 | g:plan-ready-120x40; strings.py:181 | n | none |
| F30 | S24 | `/open` is refused while any run works ("files open when no work is running"), though the viewer is read-only. | N3 | 1 | strings.py:457 | n | none |
| F31 | all | Naming drifts: "Planning Kit 0.6.0" (doctor), "zplan", "planning kit" (lab), "milestone / stage / этап" mixed. | N4, C-naming | 1 | 09, 08, 24 | n | O1 partly |
| F32 | S30 | Ctrl+Q exits silently. The TUI never says that work continues and `zplan` returns to it (the line mode says a wrong version of it). | N1 | 1 | 29, 38 | n | none |
| F33 | S01, S06 | The installer re-executes under python3.13 silently and prints a Russian pip log; setup takes ~24 s with no progress line. | C-output | 1 | 01, 10 | n | none |
| F34 | S08 | The language modal does not say how to change it later (`/language`). | N6 | 1 | 15 | n | O2 |

Positives (keep): goal-draft tab "This is exactly what planning gets" (transparent hand-off); plan-ready card asks
one question with two buttons and the typed equivalent (`or /approve · /decline`); question card offers quick
answers plus "answer in words"; the bar keeps one line with project · branch · job · keys.

## 3. Cognitive walkthroughs

Q1 knows what to do · Q2 sees the control · Q3 links control to goal · Q4 understands the feedback.

(a) First goal → first architect reply (fresh install, empty folder; real run: 283 keys, 4 launches, 9 dead
ends, 365 s of zplan time, plus git and a browser outside the product)

| Step | Action | Q1 | Q2 | Q3 | Q4 | Failure / evidence |
|---|---|---|---|---|---|---|
| 1 | `zplan` in the new folder | y | y | y | n | line prompt "Git-проект (путь)", no git init (F03; 02) |
| 2 | Answer the prompt (Enter, name, ".") | n | n | n | n | same refusal 3 times (03-05) |
| 3 | Leave, `git init` + empty commit | n | n | n | - | product never says this (14) |
| 4 | `zplan` → pick English | y | y | y | n | next modal is Russian (F07; 16) |
| 5 | Process profile: accept | n | y | n | n | jargon; file written silently (F10, F20) |
| 6 | Type the goal, Enter | y | y | y | n | nothing happens, not signed in (F06; 28) |
| 7 | Find sign-in | n | n | n | n | no /login, "/log" ≠ login, Settings in Russian, Ctrl+C kills the app (F05; 18-26) |
| 8 | Relaunch, type the goal | y | y | y | p | "thinking" line above the message; header shows CODEX_HOME (F14, F13; 32) |
| 9 | Read the reply + card | p | y | p | p | Russian jargon reply vs a clear card (F08, F15; 33) |

(b) Understand "what is happening now" during a run (fixture `running`, code)

| Step | Where the user looks | Q1 | Q2 | Q3 | Q4 | Failure / evidence |
|---|---|---|---|---|---|---|
| 1 | Chat | n | y | n | n | nothing about the run unless a card is open |
| 2 | Right title / Scheme tab | p | y | p | n | "M1 … running", scheme "running 1 s": no task, step or role (g:running-120x40) |
| 3 | "What's happening" pane | y | y | y | n | "nothing has happened yet" while M1 runs (F02) |
| 4 | Bar | p | y | p | p | "M1 идёт 0:00:01", the only consistent signal |
| 5 | `/status` | n | n | p | ? | not shown on bare `/` in every state; output not captured (F12) |
| 6 | Same at 80x24 | n | n | n | n | only the bar; ←→ to reach the canvas is not taught (F18) |
| 7 | During an architect turn | p | y | n | n | chat "думает…", bar "nothing runs", pane "nothing has happened" (F02; 32) |

(c) Start a fresh conversation with `/new`

| Step | Action | Q1 | Q2 | Q3 | Q4 | Failure / evidence |
|---|---|---|---|---|---|---|
| 1 | Look for the command | n | n | n | - | `/new` is not in the 7 rows of a bare `/` (F12; 18) |
| 2 | Type `/new` | y | y | y | y | palette shows "/new a fresh architect session…" (34) |
| 3 | Enter | y | y | y | n | progress line at the top of the old chat; old chat stays (F16; 35) |
| 4 | Wait | n | n | n | n | no progress in the bar or pane; finished in ~1-2 min |
| 5 | Read the result | n | y | n | n | handoff STATE, raw JSON, repeated draft, duplicate tab (F01; 36, 37, 37b) |

## 4. First run vs Claude Code (captured) and opencode (not recorded)

Claude Code: `~/zs-pause/ux-audit/ref/cc-01-first.ans`, `cc-02-login.ans` (clean HOME). opencode: from its
public first run as known to the evaluator, not recorded here (`oc-01-first.ans` is empty).

| # | Pattern | Claude Code | opencode (not recorded) | zplan 0.6.0 |
|---|---|---|---|---|
| P1 | Guided first-run sequence, one question per full screen | welcome banner → "Let's get started." → theme → login method (cc-01, cc-02) → folder trust | home screen with logo and the command list; `auth login` provider list | line-mode git loop, then 2 modals, then main with an error (F03, F04) |
| P2 | Choice lists with a visible cursor and arrows | `❯ ✔ Dark mode` cursor row (cc-01) | highlighted list rows | palette with no cursor (F09) |
| P3 | Each setup choice says where to change it later | "To change this later, run /theme" (cc-01) | settings via commands | language modal says nothing (F34) |
| P4 | Sign-in is part of the first run, with plain-language options | "Claude account with subscription · Pro, Max…" / "Console account · API usage billing" (cc-02) | provider list with short labels | not in the TUI flow; Settings button; Ctrl+C kills the app (F05) |
| P5 | The working folder is stated and confirmed | "Do you trust the files in this folder?" with the path | project path in the header | path only in the dim bar; owner asks the architect (F19) |
| P6 | Live status next to the input: verb, elapsed, tokens, "esc to interrupt" | spinner line under the last message | busy indicator in the status line | "думает…" above the user's message, no cancel hint, other panes say idle (F14, F02) |
| P7 | A new or cleared session gives a clean view | `/clear` empties the view | `/new` opens an empty session; sessions list | `/new` appends internal prompts (F01) |
| P8 | Replies rendered as markdown, internal steps folded | rendered markdown; tool calls as short collapsible lines | rendered markdown; tool calls collapsed | raw markdown, internal labels (F08) |
| P9 | Empty-state tips | "Tips for getting started" (/init, ? for shortcuts) | command list on the home screen | empty chat with an error (F04) |

## 5. What the approved lab (welcome.py) already solves

| Lab element (welcome.py) | Findings fixed (y) or helped (p) |
|---|---|
| Notices: mark + one-line message + action on the same line (`! … /login`), silent when healthy | F05 y, F11 y, F13 y, F28 y, F06 p, F02 p (one "◐ job · step · time /status" line) |
| Context line `project · branch · changes` | F19 y |
| Prompt "Опиши, что хочешь сделать в проекте" as the visual centre, one key line | F04 p |
| One dropdown (OptionList) for commands, projects, folders, with a highlighted row | F09 y, F12 p |
| `/project`, ctrl+o folder browsing | F03 p (no git init; O2 mockup `01-project-no-git` adds it) |

Not touched by the lab: F01, F07, F08, F10, F14-F18, F20-F27, F29-F33. The lab is Russian-only and covers the
welcome screen, not the chat, the canvas or the CLI. Gaps not in any 0.6.1 slice: F02, F08 (markdown, jargon),
F12, F13, F14, F15, F17, F18, F20, F22, F23, F25-F27, F32.
