RC2 — a new project is offered preset /2, so the default autonomy `auto` applies (0.6.0 smoke 2026-10-25, defect 10)

Incident: ~/zs-pause/dogfood/findings-2026-10-25.md #10. In a fresh repository the owner accepted the offered
profile and then had to type /run three times: the Controller asked at every step. Cause: `process.propose`
(process.py:645-652) offers `"preset": PRESET` = `zplan.default/1`, which has no `autonomy` section, so
`autonomy.level` reads `manual` (autonomy.py:56-61). `PRESET_V2` (process.py:34, :88) carries `level: auto`; the
owner set `auto` as the 0.6.0 default (STATE.md Direction, 2026-10-24).

Reuse: `PRESET_V2` and its preset data (process.py:88-95); `resolve`; `autonomy.level`.

Write-set: terminal_planner/process.py, tests/test_process.py.

Acceptance criteria:
- C1 Proposal: `propose` offers `zplan.default/2` with its `autonomy` section (level `auto` and the preset's
  limits); roles, gates, limits, rules and checks are offered as today. Example: a fresh project -> the proposal
  JSON has `"preset": "zplan.default/2"` and `"autonomy": {"level": "auto", ...}`.
- C2 Accepted: after accept, the written zplan.process.json resolves, and `autonomy.level` of that profile is
  `auto`. Example: accept the proposal of a fresh project -> `autonomy.level(profile)` == "auto"; merge still
  asks (`gates.merge` stays "off").
- C3 Unchanged: a project whose accepted profile says `/1` keeps `/1` and reads `manual`; the fallback with no
  profile stays `/1` (`process.PRESET`). Example: an existing `{"preset": "zplan.default/1"}` file -> level
  "manual", file untouched.
Joint example: fresh project -> proposal /2 + auto (C1) -> accepted file reads auto (C2); old /1 file -> manual (C3).

Non-goals (reviewers must not require): a migration offer for existing /1 projects; turning `gates.merge` on;
changes to autonomy.py, to the /1 or /2 preset data, or to the bootstrap screen wording beyond what the preset name
change forces.

Conflict rule: a test outside the write-set that pins `zplan.default/1` in a fresh proposal or in the accept flow
(grep `default/1` in tests/: test_task_gate*.py and test_parallel_home.py pin explicit /1 profiles and stay) ->
`conflict:` with path:line before any edit.

Risk: medium (default behavior of a new project). DoD: `python3.13 devtools/fasttest.py tests.test_process
tests.test_autonomy tests.test_toolchain` exit 0; quote the `fasttest:` lines.
