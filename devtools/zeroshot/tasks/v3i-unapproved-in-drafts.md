# v3i — an unapproved revision shows in Drafts; the Plan tab shows only the approved plan

docs/PLAN_UX.md V3, Q3, last Drafts task (Astra's consult, design dir drafts-astra-consult.md, points 1-2). After
v3d/v3e/v3g/v3h: Drafts (TAB_DRAFTS) lists the goal drafts; the Snapshot carries `approved` (the last approved
plan's lines, `Delivery.approved()`); Plan comes forward on approval and on a run start. But the Plan tab still
renders `snapshot.lines`, i.e. the current revision whatever its status (planning, proposed, stale, failed,
review_exhausted ...), and the planner's finish moves to Plan (u5a, `move_tab(TAB_PLAN)` when the planner ends).

Change:
- The Plan tab renders `snapshot.approved`'s lines; before any approval one line: "No approved plan yet: the
  proposal is in Drafts." When the current revision is the approved one, Plan shows exactly what it shows today.
- Drafts renders, above the goal drafts, the current revision whenever it is not approved, with the text the Plan
  tab shows for it today.
- When the planner ends (u5a) Drafts comes forward instead of Plan (same once-only rule, `move_tab`).
- Pointers say Drafts: the plan card's text (strings card.plan_text "The “Plan” tab is on the right") and the
  planner finish/failure line that names the tab.
- Actions are untouched: approve, revise, override, the plan card and /view act on the current revision as today.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/card_host.py, terminal_planner/tui/strings.py,
tests/test_tui_planning.py, tests/test_tui_approve_card.py, tests/test_tui_auto_plan_card.py, tests/test_tui.py,
tests/test_tui_commands.py, tests/test_tui_failed_card.py, tests/test_tui_hints.py, tests/test_tui_look.py,
tests/test_tui_milestones.py, tests/test_tui_rb_fixes.py, tests/test_tui_draft_tab_ends.py, tests/test_tui_language.py,
tests/test_tui_follow.py

Acceptance criteria:
- A1 Split. Example: r1 approved with M1 running, then r2 proposed -> Plan shows r1 with M1 running; Drafts shows
  r2's plan text above the drafts.
- A2 Before approval. Example: only r1 proposed -> Plan shows "No approved plan yet: the proposal is in Drafts.";
  Drafts shows r1's plan text; the planner's end brought Drafts forward.
- A3 Actions unchanged. Example: /approve with Drafts showing r1 approves r1; Plan then shows r1 and comes forward.

Non-goals (reviewers must not require): the goal-draft list, actions on an old revision, Scheme, wording beyond the
lines above.

Conflict rule: a test outside the write-set pinning the Plan tab's content: change nothing, end with
`conflict: <file:line>`.

Risk: low (owner screen). DoD: `python3.13 devtools/fasttest.py tests.test_tui_planning tests.test_tui_approve_card
tests.test_tui_auto_plan_card tests.test_tui tests.test_tui_milestones tests.test_tui_hints tests.test_toolchain`:
exit 0.
