RC6 — a refused `/plan` from the goal-draft card leaves the draft usable (0.6.0 smoke 2026-10-25, defect 3, high)

Incident: ~/zs-pause/dogfood/findings-2026-10-25.md #3 (repeat of 2026-10-24 #2). Fresh repository: the owner accepts
the profile (zplan.process.json is now untracked) and types `/plan` on the goal-draft card; readiness refuses
(uncommitted changes). The owner commits; `/plan` again: «черновик устарел: появился план», forever. Cause: `Controller.start_planning` (tui/controller.py:969-992) calls `planning.begin` before it
looks at the readiness gate, so the refusal itself saves an unsent revision; the plan identity moves from "no plan"
and the card's own draft is now stale against it (`chat.stale_reason`).

Reuse: `start_planning.work` as it is; `planning.gate`, `planning.begin`; `chat_module.stale_reason`. The card path
is the `submit_goal` call with `card_key` set (tui/app.py:2481); the goal form opened from a card with [c] passes the
same `draft=self.goal_identity` but no `card_key`.

Write-set: terminal_planner/tui/controller.py, terminal_planner/tui/app.py, tests/test_tui_draft_card.py,
tests/test_tui_ready_card.py (only its fake `start` at :119 takes the new argument), tests/test_lifecycle_guard.py (only if
its raise-site inventory for `Controller.start_planning.work` moves).

Acceptance criteria:
- C1 No revision on refusal from a card: when the card's own `/plan` (app.py tells the controller it is the card
  submission) meets a readiness gate that is not ok, `start_planning` it answers `unsent` with the gate's checks and writes nothing: no revision, no run.
  Example: draft card at "no plan", dirty tree -> `/plan` -> the card stays open, the status line names the checks,
  the plan identity is still "no plan".
- C2 Retry works: after the owner fixes readiness, `/plan` on the same card starts the planner. Example: the
  refusal of C1, then a clean tree -> `/plan` -> planner starts (one revision, sent), no «черновик устарел».
- C3 Form unchanged: any goal form submission, including a form opened from a card with [c], keeps today's
  behavior: saved as an unsent revision even when readiness refuses. Example: tests/test_tui_chat.py:2810 still
  passes unchanged (dirty tree, form from a draft -> revisions == [(DRAFT, 'planning')]).
Joint example: card + dirty tree -> no revision (C1) -> commit -> card `/plan` sends r1 (C2); the form path (also from [c])
still saves an unsent r1 on refusal (C3).

Non-goals (reviewers must not require): readiness checks or wording; closing stale
draft cards (other runs); the refusal between check and submission (`result.kind == "blocked"`).

Conflict rule: a test outside the write-set that pins an unsent revision after a refused card `/plan` -> `conflict:`
with path:line before any edit.

Risk: medium (planning lifecycle). DoD: `python3.13 devtools/fasttest.py
tests.test_tui_draft_card tests.test_tui_chat tests.test_tui_ready_card tests.test_lifecycle_guard tests.test_toolchain` exit 0; quote the `fasttest:` lines.
