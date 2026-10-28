P1 — first start and /setup: take the preset or set it up

Owner 2026-10-27: the first start offers the preset or own settings; /setup changes them later. Today
modals.py `BootstrapScreen` has only «принять»/«позже»; process.py `propose` -> `Profile.accept` writes
zplan.process.json verbatim; /setup (screens.py `SettingsScreen`) only shows roles.

Write-set: terminal_planner/process.py, terminal_planner/tui/modals.py, terminal_planner/tui/screens.py,
terminal_planner/tui/controller.py, terminal_planner/tui/app.py, terminal_planner/tui/strings.py,
terminal_planner/catalog.py, docs/REFERENCE.md, tests/test_process.py, tests/test_tui_split.py,
tests/test_tui_profile_choice.py (new)

Acceptance criteria:
- P1 The bootstrap adds «настроить» between «принять» and «позже» (focus stays on «принять»). It opens one
  editor: Самостоятельность «сам» / «спрашивать план» / «спрашивать всё» (autonomy.level auto / supervised /
  manual); Параллельно 1 / 2 / 3 (autonomy.max_runs; a value outside 1-3 from the file shows as its own button);
  Слияние «само при зелёных проверках» / «спрашивать» (gates.merge required / off; without checks only
  «спрашивать», with the reason); per role: model (input, prefilled) and effort (buttons, authority.py
  NATIVE_EFFORTS). Buttons: «сохранить», «отмена». Example: «настроить», «спрашивать всё», 1, «сохранить»
  -> zplan.process.json has level manual, max_runs 1, all else as proposed, committed «zplan profile».
- P2 Save validates through `validate_profile`; an invalid model keeps the editor open with the reason, writes
  nothing. Example: model «a b» -> reason shown, no file.
- P3 /setup gets «профиль» for an accepted profile: the same editor on the file's values; save replaces the file
  atomically, commits it alone like `_commit_file`, records the new digest; unknown keys and other sections
  stay as they were. Example: level auto -> supervised in /setup -> the file differs only in that value.
- P4 Cancel or esc writes nothing; a «позже» profile shows «профиль» too and saving accepts it. Example: «отмена»
  -> file and record unchanged.

Non-goals (reviewers must not require): other profile keys (limits, risk, checks, rules); `zplan roles`;
roles.json; the line UI; en/zh texts; docs other than REFERENCE.

Tests: tests/test_tui_profile_choice.py covers P1-P4; process tests in tests/test_process.py.

Risk: high (persisted profile, git commit). DoD: `python3.13 devtools/fasttest.py tests.test_tui_profile_choice
tests.test_process tests.test_tui_split tests.test_reference tests.test_toolchain`: exit 0 (full suite: the gate).
