A10b — a refusal from the rejected-plan card shows where the owner is

Verifier 2026-10-28 on the real ZplanApp after a10: «approve anyway» with the reason "too short" is refused, but
the refusal goes only to `plan_lines` (terminal_planner/tui/app.py:3147-3149), which the main screen never draws;
the owner sees nothing. The same holds for «revise» with an empty note (app.py:3099-3101) a failed revise
(`plan_action_done`, app.py:3085-3092) and a decision's error or outcome (`decide`, app.py:3157-3171). `say_note` (app.py:2765) already puts a line under the plan view
on the plan screen and with the run lines on the home.

Reuse: `say_note`; the a10 card routes (`rejected_card_source`, `override_plan_card`, `revise_plan_card`); the
real-app fixtures of tests/test_tui_failed_card.py and tests/test_plan_override.py.

Write-set: terminal_planner/tui/app.py, tests/test_tui_failed_card.py, tests/test_plan_override.py,
tests/test_tui_planning.py, tests/test_tui.py (there only to read a moved line where `say_note` puts it).

Acceptance criteria:
- C1 `override_note`'s refused reason, `revision_note`'s empty-note line, `plan_action_done`'s error and `decide`'s
  error and outcome lines go through `say_note`, so on the plan screen they read as today and on the main screen they show with the run lines.
  Example: the real app at the rejected card, «approve anyway», reason "too short" -> the main screen text holds
  "Not done: A reason is required" and the card stays.
- C2 On the plan screen nothing changes. Example: the same short reason from the plan screen's override -> the line
  under the plan view, as today.
- C3 A valid reason still approves and the card leaves; the main screen shows the outcome line. Example: "the
  owner accepts the broad scope" -> approved, no card, "Plan r1 approved despite the check." on the main screen.

Non-goals (reviewers must not require): the wording of any line, other screens' notes, the card's layout, the
reason rule.

Conflict rule: if a test outside the write-set pins `plan_lines` after one of these calls on the main screen,
change nothing and end with `conflict: <file:line>`.

Risk: low (where a line shows). DoD: once at the end, `python3.13 devtools/fasttest.py tests.test_tui_failed_card
tests.test_plan_override tests.test_tui_planning tests.test_tui tests.test_toolchain`: exit 0; `python3
devtools/budget.py`: OK. The new test fails on the old app.py; the main-screen test runs on the real app
(`run_test`), not a stand-in screen.
