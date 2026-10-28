K1e — the TUI docs describe slash commands and buttons, not letter keys

K1a-K1d removed every letter key from the full-screen shell: actions are `/` commands in the chat input, screens and
modals answer with buttons (Tab, ←→, Enter, Esc; arrows, PgUp/PgDn scroll), no goal form and no `Ctrl+G`. The docs
still describe 0.3: docs/USER_FLOW.md full-screen part (lines 1-364: the keys table :91-118, «Decision cards»,
«Live run», drafts :188-255) and docs/TERMINAL_UX_BRIEF.md.

Source of truth (read, do not change): terminal_planner/catalog.py (screens, actions, `tui_*` bars; docs/REFERENCE.md
is generated from it), tui/app.py (KEY_COMMANDS, BINDINGS), tui/screens.py, tui/modals.py, tui/card_kinds.py,
`/help` in a fixture shell (`zplan --fixture ID`).

Write-set: docs/USER_FLOW.md, docs/TERMINAL_UX_BRIEF.md, tests/test_docs.py.

Acceptance criteria:
- C1 USER_FLOW's full-screen part matches the shipped TUI: the keys table lists only keys bound in tui/ `BINDINGS`
  (today Tab, Esc, ←→, ↑↓, PgUp/PgDn, Enter, Ctrl+Q; no F1, Ctrl+S, Ctrl+R: help is `/help`, settings `/setup`) and
  a `/` command table lists each command (card_kinds.py:79 table) with what it does; plan, settings and run-end screens are described by their buttons (catalog labels).
  Example: the run end of a finished attempt reads «buttons «влить», «изменения», «подробнее»», not `m` / `d`.
- C2 No goal form or `Ctrl+G` in the full-screen part; drafts and answers are described as they work now (cards,
  `/answer`, note screens). Example: grep of lines before «# Line UI» finds no `Ctrl+G` and no «goal form».
- C3 TERMINAL_UX_BRIEF states the current normative design: slash-only input, buttons, «Дальше:» names a command
  or button; the line UI keeps its letters (`zplan --plain`). Example: the flows list says «/run», not «[g]».
- C4 The line UI part of USER_FLOW (from «# Line UI») is unchanged except links. Title says 0.6.
  Example: `git diff` shows no hunk after the «# Line UI» heading except a link fix.
- C5 test_docs: a test fails when the full-screen part names a bracketed letter (`[g]`), a backticked single letter
  as a key, `Ctrl+G`, `F1`, `Ctrl+S` or «goal form». Example: adding the row «| main | `p` | plan |» -> the test fails.

Keep (pinned by tests outside the write-set): «Что происходит», no «Журнал» tab; «Чат архитектора недоступен в
демо», «zplan.process.json»; «←→ вкладки», «click on a tab label», no «F2/F3/F4»; the `WARN:` sentence; no list,
table or fence glued to a paragraph (test_docs `glued`).

Non-goals (reviewers must not require): product code; REFERENCE.md, README, INSTALLATION; the line UI texts.

Risk: low. DoD: `python3.13 devtools/fasttest.py` tests.test_docs, tests.test_warn_contract,
tests.test_fixture_scope, tests.test_tui_activity_pane, tests.test_tui_milestones, tests.test_tui_chat: exit 0.
