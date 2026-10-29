C4 — the screen never shows finished steps as waiting or the journal as empty while a plan is drafted or after a run (walk W5-W7)

Orchestrator walk 2026-10-29 (real Codex): during planning and right after M1 merged, "What's happening" said
"nothing has happened yet" (tui/activity.py:191); on the Scheme tab `◌ preflight · waiting` and `◌ pick check ·
waiting` stayed while the worker ran. Causes: `Delivery.home` gives no `journal=` in its pending-plan branch
(terminal_planner/delivery.py:541-546) although the planner journal exists (`self.journal(None)`, :935-938); with
every stage merged `found` is None so `journal=()` (:566-567); `observation_from_flow` (tui/scheme.py:599-627) never
marks preflight, select_init or select_verify, so they fall back to waiting (scheme.py:224-228).

Reuse: `Delivery.journal`, `live.flow`'s `task` (live.py:361-437), scheme's `succeeded` state.

Write-set: terminal_planner/delivery.py, terminal_planner/tui/scheme.py, tests/test_live.py, tests/test_tui_scheme.py

Acceptance criteria:
- J1 While a plan is not approved (pending branch), `home().journal` is the current revision's planner journal.
  Example: a planning run whose live metadata holds two journal entries -> home.journal has those two lines.
- J2 With an approved plan and every stage merged, `home().journal` is the journal of the last stage in plan order
  that has an attempt record. Example: M1 merged with a three-entry journal, nothing else -> home.journal is those
  three lines. An approved plan with no attempt still has none (test_live.py:785-792 unchanged).
- J3 When the flow names a picked task (`flow["task"]` set) and no pick node is active, `observation_from_flow`
  marks preflight, select_init and select_verify succeeded. Example: {"task": "T1", "worker": {"state":
  "running"}, "select": False, ...} -> obs["preflight"] == obs["select_verify"] == {"state": "succeeded"}; a flow
  without `task` gives today's result (test_a4_observation_from_flow unchanged).

Non-goals (reviewers must not require): new journal entries, a planning clock, other scheme steps, wording.

Conflict rule: if a test outside the write-set pins an empty journal or a waiting preflight in these states, change
nothing in it and end with `conflict: <file:line>`.

Risk: low (read side). DoD: once at the end, `python3.13 devtools/fasttest.py tests.test_live tests.test_tui_scheme
tests.test_tui_scheme_tab tests.test_tui_activity tests.test_tui_activity_pane tests.test_tui_milestones
tests.test_toolchain`: exit 0; budget.py: OK. New J1-J3 tests fail on today's code.
