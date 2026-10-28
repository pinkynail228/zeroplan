A9t — parallel runs reach the screen: N slots from the profile instead of the single busy slot (RELEASE_0.6.0_PLAN
step 8 lane T; ARCHITECT_DESIGN.md section 4 item 4; the engine side is A9, merged 2026-10-25 fbe719a).

Why: A9 lets `MilestoneRuns.admit` (runs.py:737) run disjoint attempts together, but the home and the panel still
hold one "busy" slot: `Delivery.busy` (delivery.py:453) is the first active milestone, and while it exists [g]
refuses every start, resume and new attempt (`pick` :591, `g_id` :479, app.py `g_action` :2671,
`action_run_milestone` :2703). The preset's `autonomy.max_runs` (process.py:94, range 1..5) is read by nothing.

Reuse: delivery.py `busy`, `g_id`, `pick`, `home` :516, `preview` :635, `start` :808, `new_attempt` :1344,
`resume` :1354, `task_gate_admission` :682 (the `status(write=False)` profile read); runs.py `MAX_RUNS` :56 (the hard
cap), `admit` (its overlap/cap refusals are the messages the owner sees); tui/controller.py `Snapshot.busy` :121;
tui/app.py `g_action`, `action_run_milestone`, `action_run_next` :2709.

Write-set: terminal_planner/delivery.py, terminal_planner/tui/controller.py, terminal_planner/tui/app.py,
tests/test_parallel_home.py (new), tests/test_architect_home.py, tests/test_tui_run_command.py,
tests/test_parallel_runs.py, tests/test_live.py, tests/test_tui_live.py, tests/test_bridge.py.
Not runs.py, authority.py (lane T A6b1 owns them now).

Acceptance criteria:
- C1 Slots: `Delivery.slots()` = `min(autonomy.max_runs, runs.MAX_RUNS)` of the live profile read with
  `status(write=False)`, and 1 when the profile has no `autonomy` (preset /1), is not accepted or cannot be read
  (today's single slot, so every existing single-slot behaviour and text stays). Example: zplan.default/2 -> 3;
  `"autonomy": {"max_runs": 2}` -> 2; preset /1 -> 1.
- C2 Full, not busy: `busy` (Home.busy, Snapshot.busy, same field and type) names the first active milestone only
  when the active milestones (running, stopping, unknown) number `slots()` or more; otherwise None. The static
  helper stays static: `Delivery.busy(items, slots=1)` (tests/test_live.py:1831 calls it on the class). With slots 1
  every message stays byte-identical. With more slots and the cap reached the refusal reads «Заняты все N слотов
  (M1, M2): новый запуск, продолжение и новая попытка ждут. [w] наблюдать, [g] проверить.» in `pick` and the
  panel's [g]; check/reconcile of an interrupted attempt stays available when full. Example: slots 3, M1 running
  -> [g] on ready M2 is "start"; M1, M2, M3 running -> [g] on M4 refuses with the line above.
- C3 One service guard: every path that creates an attempt checks the cap on the worker, before any side effect,
  through one Delivery guard (family `action.refused`, «Достигнут предел параллельных milestone runs (N) профиля:
  …»): `start`, `new_attempt`, `resume`, `answer`, the "attempt" branch of `accept` (delivery.py:1347 area), and the
  architect's `zplan_rebrief` (tui/controller.py:762 calls `runs.answer`/`retry` directly: route it through the
  guard). The screen's `busy` is only a hint. Below the cap the action goes to the service and `admit`'s own refusal
  (same milestone, overlapping write-set) is shown as that action's refusal. Example: slots 2, M1 {a.py} running,
  [g] on M2 {a.py} -> "Milestone M2 пересекается с M1 (a.py): ждёт его завершения."; slots 1, M1 running,
  `zplan_rebrief` of failed M2 -> the cap refusal, no new attempt.
- C4 Every active attempt is observed: each running attempt has its own chain of bounded observation slices
  (the job label and coalescing per milestone, its own mark; callbacks carry their milestone/run identity, so a
  result is never attributed to another attempt); `follow_runs` starts one for every running row not yet followed,
  so an attempt that finishes while another is shown is still concluded and frees its slot. `run_watch` stays the
  one attempt the run lines show; [w] on another running row switches the shown attempt (no «Наблюдение M1 уже
  идёт» for a different row; the same row keeps that note). The home `panel`/`flow`/`journal` keep following the
  first active attempt (A10 does the multi-run view). Example: M1 and M2 running, M2 finishes while M1 is shown ->
  M2's row becomes awaiting_merge without any key; [w] on M2 -> M2's lines are shown and M1 keeps being observed.

Non-goals (reviewers must not require): provider pause (A6b3, needs the event feed); a multi-run panel or bundle
view (A10); runs.py/authority.py changes; new architect tools.

Risk: high (admission, lifecycle). DoD: `python3.13 devtools/fasttest.py tests.test_parallel_home
tests.test_parallel_runs tests.test_live tests.test_tui_live tests.test_architect_home tests.test_tui_run_command
tests.test_tui_chat tests.test_bridge tests.test_lifecycle_guard tests.test_toolchain` exit 0; quote the `fasttest:` lines.
