C4b — the live panel shows the review verdicts of the last two rounds (display half of slice C4, docs/CHAT_RELEASE_JTBD.md, job J5).

Goal: when a review round ends the owner sees each reviewer's verdict and one-line reason, and the previous round's next to it, so a loop that keeps finding new things is visible early. C4a stores them: `live["verdicts"]` = list (≤ 8, newest last) of {"at", "task", "round", "role" ("acceptance_review" | "code_review"), "verdict", "text"}; older records lack the key.

Data reach: `live.panel_lines` (terminal_planner/live.py) gets the live record; `live.ROLES` names the roles ("приёмка", "ревью кода"). Callers: delivery.py (milestone panel) and planning.py (planner panel; never has `verdicts`).

Write-set: terminal_planner/live.py (`panel_lines` only), tests/test_live.py, tests/test_tui_live.py only if an assertion quotes a changed line.

Acceptance criteria:
- A1 With `verdicts` non-empty, after the round line, the panel shows the entries of the newest task among them (task of the newest entry), for its latest two rounds, newest round first: one header line per round "  <task>: раунд N" (or "  проверка" when round is None) then one line per reviewer "    <role name> ✓ <text>" for verdict accepted and "    <role name> ✗ <text>" for rejected; any other verdict string is shown as is instead of the mark. Text empty → the line ends after the mark.
- A2 Each reviewer line is cut to 120 characters with "…" when longer.
- A3 A record without `verdicts` or with an empty list shows exactly today's lines, byte for byte.
- A4 Tests: two rounds (rejected then accepted) show both, newest first; three rounds show only the last two; entries of another task are not shown; record without the key unchanged.

Non-goals (reviewers must not require): colours, detection of repeated findings, final_verify verdicts, TUI layout or tabs, any store change.

Testing: while editing run only the test you change; run the DoD command once at the end.

DoD: `python3.13 -m unittest tests.test_live tests.test_tui_live tests.test_runs tests.test_toolchain tests.test_reference` with TMPDIR short (see preamble), all green.
