# v6f — `zplan_settings`: on the owner's word in the chat, the architect changes the level, runs, merge gate or roles

docs/PLAN_UX.md V6 (owner decision Q6: "the owner can change the mode or settings through the architect"; design
dir v6-chat-consent.md D4 and its "After Astra's review" part). v4a made `ProcessProfile.revise(changes)`
(process.py) change the snapshot only: CHANGE_KEYS level, max_runs, merge (= gates.merge), roles
{name: {model, effort}}, validated by `apply_changes`; with the owner's own zplan.process.json as the source it is
refused with the proposed change and the file stays untouched. The /setup editor reaches it through
`Controller.edit_profile`. v6a/v6b bind each architect request to the owner turn that made it.

Change:
- A new action tool `zplan_settings {level?, max_runs?, merge?, roles?}` (at least one key). Admitted only with an
  owner binding; an events binding is refused (family autonomy.ask, "settings change only on the owner's word").
  It runs `revise(changes)` in one job; its result (operation settings, origin owner via chat, the turn reference)
  names each changed value as "old -> new"; a file-source or invalid value is a refused result with the profile's
  own message. The screen's profile header follows from the next snapshot.
- Running attempts keep their frozen profile; the change applies to what starts next (say so in the result line).
- TOOL_RULES (architect.py): when the owner asks to change the mode or settings, call zplan_settings with exactly
  what they asked; never change settings on your own initiative; zplan_status `profile` shows the result.

Write-set: terminal_planner/architect_tools.py, terminal_planner/architect.py, terminal_planner/tui/controller.py,
tests/test_bridge.py, tests/test_architect_tools.py, tests/test_architect.py

Acceptance criteria:
- A1 Owner word. Example: an owner turn's zplan_settings {"level": "manual"} -> the profile level is manual;
  results[-1] {operation settings, outcome done, origin owner, via chat}, a line "level: auto -> manual".
- A2 Events refused. Example: an event turn's zplan_settings {"max_runs": 1} -> refused; the profile unchanged.
- A3 Owner's file. Example: a valid zplan.process.json is the source -> refused with the proposed change; the file
  bytes unchanged.
- A4 The architect is told. Example: the first prompt holds the zplan_settings line; the method file within 4600
  bytes.

Non-goals (reviewers must not require): undo, the first-start card, the /setup editor, other profile keys.

Conflict rule: a test outside the write-set pinning the tool list: change nothing, end with `conflict: <file:line>`.

Risk: high (consent policy). DoD: `python3.13 devtools/fasttest.py tests.test_bridge tests.test_architect_tools
tests.test_architect tests.test_consent tests.test_process`: exit 0.
