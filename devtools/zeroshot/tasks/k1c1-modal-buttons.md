K1c1 — the modals answer with buttons, not letters (plan section K1)

Owner: no letter keys; Tab, Left/Right, Enter, Esc, arrows, PgUp/PgDn, Ctrl+C/Ctrl+Q stay. Here: tui/modals.py
(HelpScreen :36, ConfirmScreen :51, BootstrapScreen :69, NoteScreen :191, TextScreen :245),
EnterConfirmScreen (app.py:1691), plus the app-level F1 (app.py:1702). Their bars come from catalog.py
(tui_confirm, tui_bootstrap, tui_help, tui_note, tui_answer, tui_attempt, tui_diff, tui_details :633-678).

Reuse: Textual `Button`; `keys_bar`, `bar_width`; the `present` guard (modals.py:110); `Modal.key_bar`.

Write-set: terminal_planner/tui/modals.py, terminal_planner/tui/app.py, terminal_planner/tui/zplan.tcss, terminal_planner/catalog.py, docs/REFERENCE.md, tests/test_tui_milestones.py, tests/test_tui_chat.py, tests/test_tui_polish.py, tests/test_process.py, tests/test_tui_live.py, tests/test_tui_planning.py, tests/test_tui_split.py, tests/test_tui_commands.py, tests/test_tui_question_card.py, tests/test_tui_stop_planning.py, tests/test_tui_plan_gate.py, tests/test_tui_language.py, tests/test_tui.py, tests/test_tui_chat_scroll.py, tests/test_tui_card_hooks.py, tests/test_tui_approve_card.py, tests/test_reference.py, tests/test_tui_run_command.py, tests/test_tui_activity_pane.py.

Acceptance criteria:
- C1 Confirm: buttons «да», «нет»; no letter answers; focus starts on «нет»; Tab/Left/Right move, Enter presses,
  Esc = нет. Example: merge confirm open, press `y` -> nothing; Right, Enter -> merged; reopened, Esc -> nothing.
- C2 Run start: EnterConfirmScreen's focus starts on «да», so Enter at once confirms as today; «н» goes. Example:
  `/run` -> confirm -> Enter -> M1 starts.
- C3 Bootstrap: buttons «принять», «позже» (no «позже» when `present`); no letters; the guard stays. Example: first
  start, Enter -> profile accepted; a present profile shows only «принять», Esc does nothing.
- C4 Note forms (note, answer, attempt): a send button after the text field replaces Ctrl+G; Tab reaches it, Enter
  sends; `enter=True` card notes unchanged; Esc closes. Example: `/answer`, type «да», Tab, Enter -> sent.
- C5 Help, Text: Esc only (q, ?, F1 go, the app's F1 too). Example: `/help`, `q` -> stays; Esc -> closed.

Bars: catalog entries name buttons and Esc, no letter; REFERENCE.md regenerated (`--write`); the bar below a
modal shows Tab, Enter, Esc.

Tests: a letter press becomes focus + Enter/Esc; an assert of an old bar text is deleted, not rewritten; one
invariant test: no modal binds a letter and each modal's buttons match its catalog entries.

Non-goals (reviewers must not require): PlanScreen, SettingsScreen, RunScreen (K1c2, K1c3); LanguageScreen;
QuestionNoteScreen's enter; setup/delivery/planning texts; the plain CLI.

Conflict rule: a test outside the write-set pressing a removed modal key -> `conflict:`.

Risk: medium. DoD: `python3.13 devtools/fasttest.py` with the changed test modules plus tests.test_reference
tests.test_toolchain, exit 0; quote `fasttest:` lines.
