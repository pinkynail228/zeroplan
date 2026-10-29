C2 — when the autonomy level leaves an action to the owner, the architect never asks for a yes in the chat; the refusal names the owner's command (walk W1)

Orchestrator walk 2026-10-29 (real Codex, level auto, no merge check): the architect asked "Merge M1 into main?";
the owner typed "yes, merge it"; the merge was refused ("zplan's autonomy policy requires you to merge M1 in the
interface") and the owner had to find the merge card. The five `autonomy.ask` refusals (tui/controller.py:861,
894, 912, 934, 1048) say only "in the zplan interface"; the method says "else ask" (Plan) and "Decision ask: tell the
owner in one line what to decide" (Merge) (terminal_planner/resources/architect_method.md:18, :37). Critic
walk082 Q3: a rule only in the method is lost under a project's zplan.architect.md and on resumed turns;
`TOOL_RULES` (architect.py:95-104) go into both the first turn and every update (architect.py:303-335).

Reuse: the slash commands `/approve`, `/run`, `/attempt`, `/merge` (tui/slash.py:70-93); the merge card;
`zplan_status`'s per-row `decision` (controller.py:270-288).

Write-set: terminal_planner/tui/controller.py, terminal_planner/architect.py, tests/test_bridge.py,
tests/test_architect.py

Acceptance criteria:
- K1 Each `autonomy.ask` refusal names the owner's step for that action and that a chat reply does not do it: plan
  approval -> `/approve` or the plan card; start, resume and a new attempt -> `/run` or `/attempt`; merge -> the merge
  card or `/merge`, and when the profile has no merge check it says that is why the merge is the owner's. Family
  stays `autonomy.ask`. Example: level auto, no merge check, zplan_merge M1 -> the message contains "/merge" and
  "no merge check".
- K2 `TOOL_RULES` gain one rule: when the level leaves an action to the owner, never ask for a yes in the chat (a
  chat reply cannot do it); say in one line which card or command does it. Example: build_preamble with a project
  zplan.architect.md and build_update both contain "never ask for a yes in the chat".
- K3 The shipped method file is unchanged. Example: tests.test_architect passes with its 4600-byte pins.

Non-goals (reviewers must not require): a chat yes performing the action, new cards, opening a card on a refusal,
the catalog entry's text, other refusals, the method file.

Conflict rule: if a test outside the write-set pins a refusal text this changes, change nothing in it and end
with `conflict: <file:line>`.

Risk: low (texts). DoD: once at the end, `python3.13 devtools/fasttest.py tests.test_bridge tests.test_architect
tests.test_architect_tools tests.test_reference tests.test_docs tests.test_toolchain`: exit 0; budget.py: OK.
New K1 and K2 tests fail on today's code.
