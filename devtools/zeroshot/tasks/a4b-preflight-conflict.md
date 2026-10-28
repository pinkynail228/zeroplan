A4b — the milestone graph's preflight verifier and `conflict` route (RELEASE_0.6.0_PLAN lane E; ARCHITECT_DESIGN.md
section 6 F1, F2, F4; section 7). Design reviewed: ~/zs-pause/critic/a4b-design.out.

Why: a contradictory brief today burns every review round: reviewers can only reject, and `conflict:` is a text
convention of devtools/zeroshot only. A4a (foreman.py) covers the mechanical checks; the agent checks and the route
belong in the graph.

Reuse: `milestone_graph` helpers `verifier`, `choice`, `guard`, `fail`, `seq` (milestone.py:311); `ROLES`,
`milestone_runtime`; `live.ROLES`; tui/scheme.py node and reviewer-state maps (:85, :576); `driver_qual.SCENARIOS`.

Write-set: terminal_planner/milestone.py, terminal_planner/live.py, terminal_planner/tui/scheme.py,
terminal_planner/tui/strings.py, devtools/driver_qual.py, tests/test_milestone.py, tests/test_live.py,
tests/test_tui_scheme.py, tests/test_tui_scheme_tab.py, tests/test_tui_milestones.py, tests/test_tui_strings.py,
tests/test_install.py (tests only where they pin node names, labels, enums or graph digests).

Acceptance criteria:
- C1 Preflight: root = `seq(preflight, preflight_result)`; `preflight` is a read-only verifier (reviewer role, fresh
  session, `writes=[]`), input `milestone` + `baseline`, signal `preflight` in [`ready`, `conflict`];
  `preflight_result` checks the error first (`fail("preflight_failed")`), then `conflict`
  (`fail("preflight_conflict")`), otherwise the existing root subtree unchanged (no new promotions, final_stage not
  moved). It judges each open task's brief: F1 a criterion needs an edit outside the write-set or evidence that is
  unavailable (reading a file outside it is fine); F2 two criteria, or a criterion and a non-goal, contradict, or an
  example breaks its criterion; F4 a criterion over an open domain without a case list. Example: scenario
  `i_preflight_conflict` ends failed `preflight_conflict` with no worker call.
- C2 Review conflict: only `acceptanceVerdict`/`codeVerdict` gain `conflict` (final/scope verdicts, SIGNALS and
  `milestone_output` stay); prompt: conflict only for an evidenced brief defect that needs a brief change, naming
  task, criterion and the incompatible requirements; implementation defects stay `rejected`, remarks stay `note:`,
  missing tools or failed commands are never conflict. `review_loop.until` stops on it; `review_result` routes it to
  `fail("review_conflict")` after the error branches, before `steward_apply`; `reviews.join` stays `all`. Example:
  `j_review_conflict` (acceptance conflict, code accepted, round 1) ends failed `review_conflict` after one worker.
- C3 Display: `preflight` shows as «предпроверка» (strings.py) in the live view and the scheme; a reviewer
  `conflict` shows as failed in scheme observations. Example: active node `preflight` renders that word.
- C4 Admission: every driver_qual script (adapter scripts included, driver_qual.py:634) seeds `preflight: ready`;
  existing scenarios keep their outcome with `preflight` first in the order; AdmissionTests pass for 1 and
  MAX_INITIAL_TASKS tasks. Example: `a_two_tasks_done` order starts `["preflight", "select_init", ...]`, `done`.

Non-goals (reviewers must not require): runs.py (node_label for preflight, keeping a second departing reviewer
verdict: A5e owns runs.py after A7a); routing a conflict to the architect (A5t); foreman checks (A4a); catalog;
fixture driver; the plan graph.

Risk: high (native graph contract); the orchestrator runs driver_qual on Linux at merge. DoD: `python3.13
devtools/fasttest.py tests.test_milestone tests.test_live tests.test_tui_scheme tests.test_tui_scheme_tab
tests.test_tui_milestones tests.test_tui_strings tests.test_install tests.test_toolchain` exit 0; quote the
`fasttest:` lines. The pinned 10.16.0 binary is absent on this Mac, so AdmissionTests skip here; the orchestrator
runs them and driver_qual on the Linux host.
