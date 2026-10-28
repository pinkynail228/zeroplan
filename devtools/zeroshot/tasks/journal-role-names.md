Journal role names — the run journal names the milestone selection nodes correctly (regression of live-role-names, found 2026-10-22).

Goal: `live.stages` (terminal_planner/live.py, the `elif node in ROLES: text = "итоговая проверка"` branch) journals every node that has a `live.ROLES` entry and no own branch as "итоговая проверка". live-role-names (merge 8145744) added select_init, select, select_verify and steward_decide to `live.ROLES`, so a milestone start now journals "итоговая проверка" three times instead of the selection. Reproduce: `live.stages(d, {"activeExecutions": [{"node": "select_init", "execution": "nv2-" + "a" * 64}]}, stamp, ("T1",))` writes "итоговая проверка".

Data reach: live.py `stages` and `ROLES` only; final verification node names: final_verify, final_reverify, scope_verify (and their `empty_` variants through `base`).

Write-set: terminal_planner/live.py (`stages` only), tests/test_live.py.

Acceptance criteria:
- A1 Only final_verify, final_reverify and scope_verify journal "итоговая проверка"; any other node with a `live.ROLES` entry and no own branch journals its role word (`ROLES[node]`, e.g. "выбор задачи", "стюард"); a node without an entry still journals "этап <node>".
- A2 Tests: select_init journals "выбор задачи", steward_decide "стюард", final_verify "итоговая проверка", an unknown node "этап <node>"; the existing journal tests stay green unchanged.

Non-goals (reviewers must not require): panel changes, task naming of selection lines, changes to ROLES.

Testing: run only the test you change while editing; run the DoD command once at the end.

DoD: `python3.13 -m unittest tests.test_live tests.test_tui_live tests.test_runs tests.test_toolchain tests.test_reference` with TMPDIR short (see preamble), all green.
