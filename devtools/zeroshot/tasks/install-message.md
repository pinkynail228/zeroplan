install-message — after `install.sh` or `zplan update` already ran `zplan setup`, the installer still prints "...следующий шаг: zplan setup" / "...затем zplan setup", which is wrong and confusing.

Data reach: install.py `installed_message` (~50-53), install.sh (runs install.py then `<launcher> setup`), terminal_planner/update.py (runs the release's install.py then setup), tests/test_install.py, tests/test_update.py.

Write-set: install.py, install.sh, terminal_planner/update.py, tests/test_install.py, tests/test_update.py.

Acceptance criteria:
- A1 When install.py is run by install.sh or by `zplan update`, its final message does not tell the user to run `zplan setup` (they run it right after); it still names the PATH line when the bin dir is not on PATH. A plain `python3 install.py` (manual route) keeps today's message. One small, explicit signal is enough (e.g. an env variable or a flag the two callers pass); pick the simplest.
- A2 install.sh ends with one line naming the next step: `zplan login` (and the PATH export when the bin dir is not on PATH).
- A3 Tests for both message variants and that both callers pass the signal; each fails if reverted.

Non-goals: any other wording, install logic, setup behaviour.

DoD: `python3.13 -m unittest tests.test_install tests.test_update` with TMPDIR short (see preamble), all green.
