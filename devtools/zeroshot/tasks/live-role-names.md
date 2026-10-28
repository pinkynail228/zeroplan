Live role names — the live panel names every node of the shipped milestone graph in words (dogfood 2026-10-22 finding 1, job J2).

Goal: at a milestone start the panel showed "Сейчас работают: select": the raw node name, because `live.ROLES` (terminal_planner/live.py:37-40) lacks the steward's selection nodes of the milestone graph (terminal_planner/milestone.py:274-276: select_init, select, select_verify, steward_decide).

Data reach: `live.role(node)` maps a node through `live.ROLES` (live.py, `role`/`base`); the node names come from milestone.py:274-276 `ROLES` keys.

Write-set: terminal_planner/live.py (`ROLES` only), tests/test_live.py.

Acceptance criteria:
- A1 `live.ROLES` maps select_init, select and select_verify to "выбор задачи" and steward_decide to "стюард"; every other entry is unchanged.
- A2 A test asserts that every node name in `milestone.ROLES` (and its `empty_` variants through `live.base`) has an entry in `live.ROLES`, so a future graph node without a name fails the test.

Non-goals (reviewers must not require): changing milestone.py, planner roles, colours, panel layout.

Testing: run only the test you change while editing; run the DoD command once at the end.

DoD: `python3.13 -m unittest tests.test_live tests.test_tui_live tests.test_milestone tests.test_toolchain tests.test_reference` with TMPDIR short (see preamble), all green.
