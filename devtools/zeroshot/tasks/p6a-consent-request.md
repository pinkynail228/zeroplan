# p6a — an architect action the level leaves to the owner becomes a request the owner can grant, not a refusal

P6 (docs/PLAN_0.9.md; design and critic p6consent in the pause dir). Today `zplan_start`, `zplan_resume`,
`zplan_rebrief`, `zplan_approve_plan` and `zplan_merge` raise `autonomy.ask` with relay text when the level leaves
the action to the owner (tui/controller.py:881-883, 914-917, 933-935, 955-958, 1070-1077). `zplan_propose_commit`
already shows the pattern: one stored `CommitProposal` (controller.py:348-359), `{"status": "awaiting_owner"}` to the
architect, and only the owner's answer acts (`commit_files`).

Change (Controller only; p6b draws it):
- start, resume, rebrief at "ask": store one `ConsentRequest` (id, action, milestone, the tool's arguments, the
  profile digest the policy read, for start the `Preview` already built; state awaiting/done/declined/stale/failed;
  lines) and return `{"status": "awaiting_owner", "request": id}`. The same request again returns the same id; a
  different one while one awaits is refused naming the awaiting one.
- approve and merge at "ask": return `{"status": "awaiting_owner", "card": "plan"|"merge"}` and record the ask
  (`asked`: approve with its version, merge with its milestone) for the existing card; the owner's own card or
  command acts as today and clears it.
- `consent(id)` runs the stored action through the existing operations and checks: start with the stored Preview
  (`Delivery.start` refuses a moved attempt or revision, delivery.py:876), resume and rebrief with their exact token;
  a digest that moved -> stale, nothing runs. `decline(id)` -> declined. A finished request's consent does nothing.
  Both run as Controller jobs (the existing post/closing guard).
- zplan_status lists the request (action, milestone, state, lines) and the asks.

Write-set: terminal_planner/tui/controller.py, tests/test_bridge.py, tests/test_consent.py

Acceptance criteria:
- A1 A start becomes a request once. Example: manual, plan approved: zplan_start M1 twice -> the same request id,
  state awaiting; `consent(id)` -> M1 starts; `consent(id)` again -> nothing new starts.
- A2 A stale request runs nothing. Example: supervised, request to start M1, then the profile file changes ->
  consent -> state stale with the reason; no attempt.
- A3 Approve and merge point at their cards. Example: supervised, zplan_approve_plan r1 -> awaiting_owner, card
  "plan"; the status lists the ask; the owner's /approve approves and clears it.

Non-goals (reviewers must not require): the card's look (p6b), persisting requests across a restart, several
awaiting requests, conflict recovery, the line UI.

Conflict rule: if a test outside the write-set pins the old autonomy.ask relay text, change nothing in it and end
with `conflict: <file:line>`.

Risk: high (autonomy enforcement). DoD: `python3.13 devtools/fasttest.py tests.test_bridge tests.test_consent
tests.test_autonomy tests.test_architect_tools`: exit 0.
