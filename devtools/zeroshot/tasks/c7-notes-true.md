C7 — no label word after its own command anywhere, and the approval note never says "not started" once zplan starts the work (rc1 walk N3, N5)

Orchestrator rc1 walk 2026-10-29 (real Codex): the Goal line shows `— /details details` (A13-A15): `command_hints`
(tui/app.py:189-197) keeps a label word equal to the command's own name, which c3's `next_key` (app.py:210-212)
drops only on Next lines. After approval at `auto` the note "Plan r1 approved. Implementation was not started;
start it with /run on the main screen." (app.py:3251-3257, also the overridden branch at :3246-3251) stayed the
last note after zplan started M1 and after the merge.

Reuse: `next_key`'s rule, `autonomy.decide(level, "start")` with `autonomy.level_of` or the profile level the
snapshot holds (`card_kinds.profile_level`), `run_note`.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/strings.py, tests/test_tui_hints.py,
tests/test_tui_plan_gate.py, tests/test_tui_milestones.py, tests/test_tui.py (old tests: only their pins of the
approved note text)

Acceptance criteria:
- N1 `command_hints` drops a label word that is the command's own name, in any line. Example: `Goal: x — [i]
  details` -> `Goal: x — /details`; `[l] refresh login` keeps today's result.
- N2 When the level lets zplan start the work itself (`decide(level, "start") == "allow"`), the approved and the
  overridden notes say zplan starts it, never "not started" or "/run". Example: auto -> "Plan r1 approved. zplan
  starts the first stage."; manual -> today's text with /run.
- N3 Once a run of the approved revision has started, an approval note of that revision is no longer the note
  shown. Example: approve at manual, then /run M1 -> the note is not "Implementation was not started".

Non-goals (reviewers must not require): other notes, the plan card, cards, the scheme, the line UI.

Conflict rule: if a test outside the write-set pins the old note text, change nothing in it and end with
`conflict: <file:line>`.

Risk: low (visible text). DoD: once at the end, `python3.13 devtools/fasttest.py tests.test_tui_hints
tests.test_tui_plan_gate tests.test_tui_milestones tests.test_tui tests.test_tui_look tests.test_tui_cards
tests.test_tui_planning tests.test_docs tests.test_toolchain`: exit 0; budget.py: OK. New N1-N3 tests fail on
today's code.
