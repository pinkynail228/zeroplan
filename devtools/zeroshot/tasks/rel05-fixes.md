rel05-fixes — release 0.5 blockers from the release critic (~/zs-pause/critic/release-05.out): a credential shown in «последнее:» / a verdict line, and the version still 0.4.0.

Goal: 0.5 can be installed next to 0.4.0 and shows no credential value on screen.

Data reach:
- Secret: terminal_planner/live.py `scrub` (~591) and `_text` (~706); the remembered command (~777: `scrub(COMMAND_STATUS.sub(...))[:COMMAND_LIMIT]`) and the remembered verdict reason (~832: `scrub(text)[:VERDICT_TEXT]`). Measured on a9f810c: `live.scrub('curl -d "{\"api_key\":\"SENTINEL\"}" x')` returns the input unchanged, SENTINEL included, while `live.scrub('api_key=SENTINEL')` masks it. The command text is a shell command line, so a JSON body with escaped quotes inside it is a realistic path (a worker running curl against an API).
- Version: install.py:20 `VERSION`, install.py `OWNED`, pyproject.toml:7, terminal_planner/__init__.py:3; tests asserting "0.4.0" (tests/test_install.py ~41, ~226; tests/test_terminal_planner.py ~1658); README.md (~31, ~116); docs/INSTALLATION.md (title, ~28, ~31, the "Upgrade from" paragraph ~40, uninstall ~110); docs/UPGRADE.md (Rollback).

Write-set: terminal_planner/live.py, install.py, pyproject.toml, terminal_planner/__init__.py, README.md, docs/INSTALLATION.md, docs/UPGRADE.md, tests (test_live or the module that tests `scrub`, test_install, test_terminal_planner).

Acceptance criteria:
- A1 A credential value carried in a command line or a verdict reason is never kept: for `curl -d "{\"api_key\":\"SENTINEL\"}" https://x`, `curl -H "Authorization: Bearer SENTINEL" x` and `export OPENAI_API_KEY=SENTINEL`, the remembered command and the remembered verdict text contain no `SENTINEL`. Masking or hiding the whole line are both fine. Lines without a credential stay as today.
- A2 Version 0.5.0 everywhere the version is declared (install.py VERSION, pyproject, `__version__`); `OWNED` keeps 0.4.0 so the 0.5.0 installer recognises the 0.4.0 launcher; installing puts the venv under `app/0.5.0` and leaves `app/0.4.0` on disk; `zplan --version` prints `zplan 0.5.0`.
- A3 docs/INSTALLATION.md "Upgrade from 0.4.0": 0.5.0 keeps using `production/v3` and writes live records 0.4.0 cannot read, so copy the store directory before the first 0.5.0 start; going back = restore that copy and point the launcher at `app/0.4.0` (same shape as the existing 0.3.1 paragraph). docs/UPGRADE.md Rollback says the same.
- A4 Tests: the three A1 inputs through the command and verdict paths (they fail if the fix is reverted); version tests assert 0.5.0 and that 0.4.0 is in OWNED.

Non-goals (reviewers must not require): a new secret scanner, other scrub inputs not named here, migration code, store versioning, changing the store path.

Testing: while editing run only the test you change; run the DoD command once at the end.

DoD: `python3.13 -m unittest tests.test_live tests.test_install tests.test_terminal_planner tests.test_tui_flow tests.test_toolchain tests.test_reference` with TMPDIR short (see preamble), all green.
