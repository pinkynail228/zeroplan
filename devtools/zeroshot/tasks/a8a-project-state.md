A8a — the project STATE file and its tools (RELEASE_0.6.0_PLAN step 7 A8, first part; ARCHITECT_DESIGN.md
section 4 decision 6 "Project state file"). A8b (`/new` with warm-up, rot signal) comes after A6b2b.

Why: the architect forgets the plan and decisions on every session reset; the design keeps them in
`.zplan/STATE.md` in the project, written only through a tool. Found 2026-10-25: an untracked file there makes
the project dirty (engine.py:1326 refuses the planner) and changes the freshness hash (authority.py:226).

Reuse: architect_tools.py `TOOLS`, `_call`, `_tool_result`, `Blocked` -> tool error; authority.py
`atomic_state` pattern (temp, fsync, replace, directory fsync) and `PersistenceError`; live.py `scrub`;
runs.py `CONTROL`; project_read.py (`.zplan` is already unreadable through the read tools).

Write-set: terminal_planner/project_state.py (new), terminal_planner/architect_tools.py,
tests/test_project_state.py (new), tests/test_architect_tools.py.

Acceptance criteria:
- C1 Format: `project_state.SECTIONS = ("Now", "Next", "Open", "Decisions")`. `validate(text)` accepts UTF-8
  text of at most 6144 bytes whose `## ` headings are exactly these four in this order (other lines free);
  otherwise `Blocked` naming the rule. Example: four headings, 5 KB -> ok; "## Later" added -> refused; 6145
  bytes -> refused.
- C2 Write: `write(project, text)` validates, scrubs each line with `live.scrub`, and replaces
  `<project>/.zplan/STATE.md` atomically (dir 0o700, file 0o600). `read(project)` returns the text or "" when
  absent. Example: a line `api_key=abc` is stored masked.
- C3 Never dirty: before its first write, `write` ensures the line `/.zplan/` in the repository's
  `<git common dir>/info/exclude` (created if missing; existing lines kept; added once). Example: a clean
  project, `write` -> `git status --porcelain=v1 --untracked-files=all` stays empty and the `authority.py:226`
  hash is unchanged; a second `write` leaves exclude byte-identical.
- C4 Tools: `zplan_state` (no arguments) returns the text; `zplan_state_update {text}` writes it; a refusal
  is a tool error, not a crash. They work without `--controller` and are not `ACTION_TOOLS`. The module
  docstring names this file as the one write. Example: `tools/call zplan_state_update` with a fifth heading
  -> `isError` true and the file unchanged.

Non-goals (reviewers must not require): `/new`, warm-up, rot signal, showing STATE in the TUI (A8b); the
Controller; autonomy rules for STATE; history or merging of concurrent writes (last write wins).

Conflict rule: if a gate or check other than engine.py:1326 / authority.py:226 still sees the file, answer
`conflict:` with the path:line.

Risk: medium (one bounded write outside the sandbox). DoD: `python3.13 devtools/fasttest.py
tests.test_project_state tests.test_architect_tools tests.test_project_read tests.test_toolchain` exit 0;
quote the `fasttest:` lines.
