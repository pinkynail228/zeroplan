C5 — a stale proposal's Next line never offers /approve (release critic rel082 finding 1)

Orchestrator check 2026-10-29 on 1552ea4: `Delivery.home` writes `Next: [p] plan — approve or revise` for every
proposed plan (terminal_planner/delivery.py:542), and `plan_tab_line` (tui/app.py:214-226, PLAN_TAB_HINTS at :160)
shows it as `Next: /approve — approve, or tell the architect what to revise`. A stale proposal (the project changed
after planning, `not self.authority.fresh()`) cannot be approved (planning.py:655-660, family `plan.stale`), so
the hint is false there; the release critic reproduced it with a helper probe.

Reuse: `self.authority.fresh()` (authority.py:930), `PLAN_TAB_HINTS`, the c3 H5 invariant test in
tests/test_tui_hints.py (`home_next_lines`).

Write-set: terminal_planner/delivery.py, terminal_planner/tui/app.py, tests/test_tui_hints.py, tests/test_live.py,
tests/test_tui_cards.py (test_tui_cards: only its Delivery.home stand-in gains what the new freshness read needs)

Acceptance criteria:
- S1 A proposed plan whose project is not fresh gets a home Next line that names revision, not approval. Example:
  proposed, `authority.fresh()` False -> `Next: [r] revise — the project changed after planning`; fresh -> the line
  stays `Next: [p] plan — approve or revise`.
- S2 The Plan tab shows the stale line as a step that works: no `/approve`. Example: `plan_tab_line` of the S1 line,
  with auto False or True -> `Next: the project changed after planning — tell the architect to revise the plan`.
- S3 The H5 invariant covers the stale line: `home_next_lines` includes a stale proposal, and every command word is
  still in `slash.COMMANDS`. Example: the stand-in's authority has `fresh=lambda: False` for one case.

Non-goals (reviewers must not require): the plan screen's own stale text (planning.py:656), the plan card, cards
for other states, wording elsewhere.

Conflict rule: if a test outside the write-set pins the approve hint for a stale proposal, change nothing in it and
end with `conflict: <file:line>`.

Risk: low (hint text). DoD: once at the end, `python3.13 devtools/fasttest.py tests.test_tui_hints tests.test_live
tests.test_tui_cards tests.test_tui_planning tests.test_tui_plan_gate tests.test_tui_auto_plan_card tests.test_tui tests.test_docs
tests.test_toolchain`: exit 0; budget.py: OK. New S1-S3 tests fail on today's code.
