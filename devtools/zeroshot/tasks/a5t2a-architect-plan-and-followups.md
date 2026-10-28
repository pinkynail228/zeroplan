A5t2a — the architect's plan approve, resume and re-brief tools through the Controller bridge (RELEASE_0.6.0_PLAN
step 5 lane T; ARCHITECT_DESIGN.md section 4; second part of A5t). Plan edit (needs the planner dispatch the UI
watch drives today, tui/app.py:3147), the merge tool and the `autonomy.AUTOMATIC` flip are A5t2b (after A7b2).
Design: ~/zs-pause/critic/a5t-design*.out, a5t2a-design*.out.

Why: A5t1 gave the architect status, start and stop (tui/controller.py `_run_tool` :560); it still cannot approve a
checked plan or follow up on a failed attempt, so every follow-up needs the owner's keys.

Reuse: tui/controller.py `TOOL_ARGUMENTS` :42, `_bridge_status` :495, `_rows_job`, `_run_tool` :560, `_start_tool`
:582 (one profile read for policy and action), `_plan_job` :664, `approve_plan` :737, `_blocked` :654, `_creating`
:986, `resume_run` :1004, `new_attempt` :1000, `answer` :996; planning.py `approve` :395; delivery.py `resolve` :564,
`Token` :157, `resume` :1203, `new_attempt` :1193, `answer` :1196; runs.py `retry` :1584 (a note -> `answer`);
autonomy.py `decide` :20.

Write-set: terminal_planner/tui/controller.py, terminal_planner/autonomy.py, terminal_planner/architect_tools.py,
terminal_planner/architect.py, tests/test_bridge.py, tests/test_autonomy.py, tests/test_architect_tools.py,
tests/test_architect.py.

Acceptance criteria:
- C1 Status: each row also carries `token` (the row's `Token` fields as a JSON object, None without an attempt), and
  the payload carries `plan`: the current revision's version, status (proposed, approved, rejected, ...) and gate
  verdict, also when it is not approved. Example: a proposed revision 2 over approved 1 -> `plan` names 2 `proposed`.
- C2 Tools: `zplan_approve_plan {revision}`, `zplan_resume {milestone, token}`, `zplan_rebrief {milestone, token,
  note}` (non-empty note; `needs_owner` -> `Delivery.answer`, otherwise `Delivery.new_attempt(r, note)`: the note is
  added to the attempt's task notes, the brief itself is unchanged) in TOOLS, `TOOL_ARGUMENTS` and the bridge, each
  a `mutating=True` job like A5t1's actions, every result with the request id. Example: rebrief of a failed attempt
  with note "use the fixture path" -> a new attempt whose notes hold that text.
- C3 Freshness, in the job: approve refuses with today's `Changed` text unless `revision` is current; resume and
  rebrief resolve the given token exactly (`delivery.resolve(Token(**token), exact=True)`). Today's gates stay:
  `Authority.approve` (verifier pass, gate digest), `_blocked(app, "resume"|"start")` (an `Outcome("blocked")`
  becomes a `Blocked` naming the checks), `check_followup`, the profile guard. Example: the same run advanced
  (status changed) since the status read -> `Changed`; approve of revision 1 while 2 is current -> `Changed`.
- C4 Policy: `autonomy.ACTIONS` gains approve, resume, rebrief: ask at every level while `AUTOMATIC` is False; with
  it True: approve allow only at auto, resume and rebrief as start (auto, supervised allow; manual ask). The level
  comes from the one profile read the action is checked against (as `_start_tool`): approve refuses `ProfileChanged`
  when that digest differs from the revision's gate `resolved_config_digest`. Order: invalid arguments, stale, the
  policy, the action. Example: auto profile, current approve -> `autonomy.ask`; patched True -> approved, status
  `plan` shows it.
- C5 No override, text: no override, reject, edit or merge tool; `TOOL_RULES` lists the new tools in one line each
  and says an approval over a rejected critic and every merge are the owner's; no new error families. Example:
  TOOLS is exactly the 3 read tools plus status, start, stop and C2's three.

Non-goals (reviewers must not require): plan edit, merge tool, `AUTOMATIC = True` (A5t2b); a TUI decision card;
journal records (A6b); delivery.py, runs.py, planning.py, catalog.py changes.

Risk: high (process boundary, plan approval). DoD: `python3.13 devtools/fasttest.py tests.test_bridge
tests.test_autonomy tests.test_architect_tools tests.test_architect tests.test_tui_chat tests.test_lifecycle_guard
tests.test_toolchain` exit 0; quote the `fasttest:` lines.
