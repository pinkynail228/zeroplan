# zplan 0.6.0 UX audit (2026-10-26)

Owner request 2026-10-26: a deep UX audit (data first, state table, heuristics, start-screen port, English as the
source language, measured before/after). This file is the summary; evidence lives next to it.

| Evidence | Path (under `~/zs-pause/ux-audit/`) |
|---|---|
| New-user journey, clean HOME, empty non-Git folder, 43 steps (.ans/.txt/.svg) | `sb8/caps/` (`steps.tsv`, `index.html`) |
| Heuristic evaluation: 32 states, 34 findings, walkthroughs, Claude Code / opencode comparison | `heur/HEURISTICS.md` |
| Claude Code first run on a clean HOME | `ref/cc-01-first.ans`, `ref/cc-02-login.ans` |
| Main-screen states (fixture gallery) | `gallery-main/` |
| Start-screen mockups, 11 states x 120x40 + 80x24 | `mockups/index.html` (source `devtools/ui-lab/onboarding.py`) |
| All user-facing literals of 0.6.0 (2022 Cyrillic) | `strings-0.6.0.tsv` |

opencode was not recorded (its port was held by the owner's running opencode; not touched).

## 1. Baseline (0.6.0, scripted newcomer)

| Metric | Value |
|---|---|
| Time from first `zplan` to the first architect reply | 365 s (step 33) |
| Keystrokes to the first reply | 283 |
| Dead ends (input with no progress) | 9: steps 03, 04, 05 (path loop), 19, 20 (palette ↑↓/Tab), 22, 23 (`/log`), 26 (login cancel), 28 (goal while signed out) |
| Steps showing Russian after English was chosen | 29 of 43 |
| Outside knowledge needed | `git init` + commit in a shell; `zplan login` in a shell |

The scripted newcomer knew git; a real newcomer stops at step 03.

## 2. Findings by severity

| Sev | # | Finding | Slice |
|---|---|---|---|
| 4 | F01 | `/new` clears nothing; zplan's handoff prompt, STATE and JSON snapshot appear as chat rows | O4 |
| 4 | F02 | Nothing answers "what is happening": bar says "nothing runs" while the architect thinks | U1 (new) |
| 4 | F03 | Non-Git folder: line-mode path loop, no `git init`, only Ctrl+C out | O2 |
| 3 | F04 | No onboarding: language modal over a red error, then an empty chat | O2 |
| 3 | F05 | No sign-in in the TUI (`/setup` → Settings → Tab → «войти»; Ctrl+C kills zplan) | O2 |
| 3 | F06 | A goal sent while signed out does nothing | O2 |
| 3 | F07 | English not honored: 29/43 steps Russian; architect replies Russian (architect.py:294) | O1a-d, L1 |
| 3 | F08 | Raw markdown, internal labels ("ответ 1 · арх · черновик цели:"), engine jargon in replies | U2 (new) |
| 3 | F09 | Palette only displays: no cursor, ↑↓ dead, Tab leaves the input | O3 |
| 3 | F10 | First decision is a jargon "Process profile" with model ids | O2 (autonomy step) |
| 3 | F11 | "Next: write the goal" while the chat cannot answer | O2 (notices) |
| 3 | F12 | Palette shows 7 of 20 commands; no `/help`, `/new`, `/stop` on a bare `/` | U3 (new) |
| 2 | F13-F27 | Header noise, UTC times, Esc cancels a paid turn silently (F17), 80x24 run only in the bar (F18), doctor BLOCKED on non-blockers (F20, F21), Russian `--help` (F22), wrong close line (F23), Settings wall (F24), two interaction models (F25) | U4-U7 (new), O2 |
| 1 | F28-F34 | Error codes in copy, "План r1", naming drift, silent Ctrl+Q, silent installer | later |

Full rows with heuristic, evidence `file:line`/capture and fix status: `heur/HEURISTICS.md` §2.

"All on sol": every role defaults to `gpt-6.1-sol` (setup.py:43, ROLE_DEFAULTS setup.py:25), shown raw in the
profile modal. The autonomy step names the models in one line and moves the choice to `/settings`.

## 3. Against Claude Code and opencode

Claude Code's first run: one question per full screen with a cursor list (theme, login method, folder trust), each
choice says where to change it later, sign-in in plain words (subscription vs API billing), live status under the
input with "esc to interrupt", `/clear` empties the view, rendered markdown. zplan 0.6.0 has none of these
(HEURISTICS.md §4, P1-P9). The approved lab `devtools/ui-lab/welcome.py` already fixes F05, F09, F11, F13, F19, F28
and helps F02, F03, F04, F12; none of it was ported.

## 4. Start screen (mockups for owner approval)

One full screen: mascot + "zeroshot" word mark centered (welcome.py), a five-step line
(Language · Project · Tools · Sign in · Autonomy), one card with a cursor list, a key line. English first.

| # | State | What the user does |
|---|---|---|
| 00 | language | English / Русский / 中文; "change later with /language" |
| 01 | project-no-git | Create a repository here (git init + first commit) / Open another folder / Quit |
| 02 | project-identity | Name and email for commits when Git has none |
| 03 | project-created | Branch, first commit shown; Continue |
| 04 | tools-installing | Zeroshot, Codex, project check with progress |
| 05 | tools-failed | Plain cause, log path, Try again / Skip |
| 06 | signin | Sign in with ChatGPT / API key / Later |
| 07 | signin-waiting | Device URL + code, Esc cancels back to the card |
| 08 | autonomy | Auto (recommended) / Supervised / Manual; models + checks in one line |
| 09 | ready | Prompt "Describe what you want to build or change", context line |
| 10 | returning-notices | `! not signed in /login`, `◐ M1 running /status`, `↑ update /update` |

The main screen opens after the first goal. Line prompts remain only without a TTY.

## 5. English as the source language (plan L1)

| Step | Content |
|---|---|
| Inventory | 2022 Cyrillic literals: catalog.py 393, strings.py 221, delivery.py 197, process.py 159, runs.py 127, app.py 122, engine.py 85, cli.py 84, setup.py 83, others |
| One catalog | English source strings with ru/zh translations; `catalog.py` RU-only texts move into it |
| Lint test | fails on Cyrillic in `terminal_planner/` outside the catalog; allow-list file that may only shrink |
| Pseudo-locale | `ZPLAN_LANG=xx` renders `⟦Ŝéñđ⟧`; gallery under it shows every untranslated string |
| Architect | replies in the UI language (architect.py:294) |
| Default | English regardless of locale until the user picks |

## 6. Task plan

| Lane | Order | Slices |
|---|---|---|
| T (app.py) | P1b (attempt 2 running) → O3 → O2a → O2b → O1a → O1b | O2a start screen: language, project, git init, identity; O2b tools, sign-in, autonomy, notices; replaces the language and profile modals |
| E (chat/store) | C1b (gating) → O4 → D1 → O1c → O1d | |
| New | after O2 | U1 one status line near the input (F02, F14, F17); U2 markdown and labels in replies (F08, F15); U3 palette lists every command (F12, F27); U4 narrow run line (F18); U5 doctor blockers only (F20, F21); U6 CLI help and close lines (F22, F23, F32); L1 Cyrillic lint + pseudo-locale |

Done when: a newcomer on a clean HOME in an empty folder reaches the first architect reply with no shell detours;
time and keys re-measured with the same script (`sb8/tools`); 0 Russian steps in EN mode; the gallery covers every
state in both sizes.

## 7. Owner decisions needed

| # | Question |
|---|---|
| D-a | Approve the start-screen mockups (layout, step order, copy) |
| D-b | Default autonomy on the start screen: Auto (recommended) or Supervised |
| D-c | Mascot and word mark come from upstream brand assets (MIT, The Open Engine Company): fine privately; decide before any public release |
