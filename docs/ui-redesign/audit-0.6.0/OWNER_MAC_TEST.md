# Owner Mac test of installed 0.6.0 (2026-10-26)

Install: owner ran `git archive v0.6.0` + `python3 install.py` + `zplan setup` on macOS arm64; zplan 0.6.0, store copy v3.backup-0.5.1-20261026T053915Z.

Owner verdict: not usable; no convenience.

| # | finding | owner words (translated) |
|---|---|---|
| O1 | After switching the interface to English, wording stays Russian. | "after switching to English the wording still stays Russian" |
| O2 | A clean project (folder without a Git repo with a commit) does not work: `zplan` prints «<path> — не Git-проект с commit.» and loops on «Git-проект (путь):». No onboarding (git init, first commit, explanation). | "in a clean project zplan does not work; this is not normal, onboarding etc. is needed" |
| O3 | Tab and other conveniences do not work while typing commands. | "Tab etc. don't work when I type commands" |
| O4 | The architect chat is a mess: unclear what is happening; opening zplan in this repo showed old content; `/new` does not clear it; unreadable. | "complete mess in the chat with the architect, I don't understand what happens; /new doesn't clear it; unreadable" |

Owner follow-up on O2: do all setup on the full-screen start screen with the Zeroshot logo; do not treat the user dumbly. Direction: one TUI onboarding screen (language -> project: use this folder, offer git init + first commit, or pick another -> login -> tools/setup check -> autonomy/profile -> chat); line prompts only without a TTY. Note: the TUI logo was dropped in i9 (app.py:225, :660); onboarding brings a start screen back.

Code mapping (read-only, 2026-10-26): O1 only new widgets use strings.text(); architect.py:294 hard-codes Russian replies; ~1,300 Cyrillic literals. O2 cli.py:82 choose_project loops, empty input re-checks cwd, Ctrl+D prints «план сохранён» (cli.py:1077), no-commit repo passes discover. O3 palette.py is a display-only Static; Tab is priority toggle_focus (app.py:628); no Up/Down. O4 entries_of shows the last 40 rows of all sessions (chat.py:34,150); /new appends handoff/warm-up prompts as «соб» rows (chat.py:408,901). Slices: docs/RELEASE_0.6.1_PLAN.md "Owner Mac test".
