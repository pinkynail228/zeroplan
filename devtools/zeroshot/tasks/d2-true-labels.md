D2 — labels that say what they do: the merge choice, the theme reply, the disk-root hint (soak S1, S9, S10)

Soak of rc1 2026-10-29. S1: the profile editor offers the merge gate as `MERGES = (("required", "automatic on green
checks"), ("off", "ask"))` (tui/modals.py:189). "ask" writes `gates.merge: off`, and with "off" the owner's
`/merge` lands with no checks and no merge critic (runs.py:1548). Everywhere else "off" reads "no check"
(process.py:68 `OFF`, gate_text :1241; docs/REFERENCE.md:165). S9: `/theme` answers "Theme: auto" (app.py:1212-1217
uses `theme.choice()`), never the theme in effect (`theme.theme_name()`, theme.py:58). S10: the refusal of a home
folder or a disk root (tui/start.py:341-343) always says `mkdir ~/my-project`, also for the top of an external disk.

Reuse: `process.OFF` / `gate_text`, `theme.theme_name`, `cannot_be_project` (start.py:129-136), the strings catalog.

Write-set: terminal_planner/tui/modals.py, terminal_planner/tui/app.py, terminal_planner/tui/strings.py,
terminal_planner/tui/start.py, tests/test_tui_profile_choice.py, tests/test_tui_theme.py, tests/test_tui_start.py

Acceptance criteria:
- T1 The editor's "off" button names that the merge then runs no check. Example: labels of the merge row ->
  ["automatic on green checks", "you merge, no check"]; with no checks -> only "you merge, no check" and today's
  reason.
- T2 `/theme` names the choice and, for auto, the theme in effect. Example: auto on a light terminal ->
  "Theme: auto (light)"; `/theme dark` -> "Theme: dark".
- T3 The disk-root hint names a folder on that disk; the home hint keeps ~. Example: path /Volumes/X (a mount point)
  -> "mkdir /Volumes/X/my-project"; path ~ -> "mkdir ~/my-project".

Non-goals (reviewers must not require): the gate's behaviour, the plain CLI, docs, other strings, the theme logic.

Conflict rule: if a test outside the write-set pins the old label "ask" for the merge gate, change nothing in it and
end with `conflict: <file:line>`.

Risk: low (text). DoD: once at the end, in the foreground: `python3.13 devtools/fasttest.py
tests.test_tui_profile_choice tests.test_tui_theme tests.test_tui_start tests.test_tui tests.test_docs
tests.test_toolchain`: exit 0; budget.py: OK. New T1-T3 tests fail on today's code.
