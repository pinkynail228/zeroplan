s5a1-warn-contract — 0.5 item S5a, slice 1 of 3 of devtools/zeroshot/tasks/disk-guard.md (the parent; its R-4 and A-2/A-6 apply verbatim where cited). Lane: Readiness. Slicing: critic overnight05 point 3, swarm05 c (~/zs-pause/critic/). DeepSeek worker, sol reviewers. Critic split3: GO (applied: doctor WARN→0 is tested with a ready or not-applicable profile context; the existing `profile_ready` condition stays; setup.py ownership is `item`/`severity`/`doctor` only, shared imports, `codex_home`, `native_environment`, `data_root` unchanged).

Base: 6e23523 (C2, intended v0.4.0 tag target); record the base commit in the receipt; re-check every line number on the base and re-gate if a premise moved. The stopped zs-disk-guard candidate is not a base.

Slices: s5a1 (this) = WARN contract, no producer of warnings; s5a2-disk-probe = R-1, R-2, R-5, A-3, A-4, the 15 GiB/override half of A-2; s5a3-disk-guard = R-3, disk in plan/start checks (not resume), the path/free-space text, A-1, A-5.

Write-set (exclusive): new `tests/test_warn_contract.py`; the receipt named in the DoD; setup.py `item` (:250-253), a new `severity(check)` next to it, `doctor` (:565-583); commands.py the `doctor` Command's Russian long help (:39-41); cli.py `App.run` start check (:235-241) and `App.readiness_screen` (:379-394); tui/controller.py `Check` (:77-85), `checks_of` (:150-151); tui/app.py `SettingsScreen.render_state` check rows (:1505-1520); docs/USER_FLOW.md :193-194 and docs/INSTALLATION.md :73, one sentence each. catalog.py stays with this lane tonight but needs no edit; if one seems needed, stop and re-gate. tui/app.py is L3's (V1): do not run concurrently with V1.

Read: setup.py :453-537; planning.py :100-108, :277; tui/app.py :612-622; tests/test_setup.py :339-360, :447; tests/test_ux.py :140, :159; tests/test_tui.py :35; tests/test_tui_polish.py :638.

Rules:
- R-1 Severity: parent R-4 first line. `item(..., severity=None)`: None gives "ok" when ok else "block"; "warn" and "ok" need ok=True, "block" needs ok=False; anything else raises ValueError. `severity(check)` returns `check.get("severity")` or that default, so dicts without the key stay valid. Existing items keep ok/block and byte-identical doctor lines.
- R-2 Doctor: parent R-4. A warn item prints `WARN: ` + its doctor text; OK/BLOCKED unchanged; exit 0 iff no block and the profile is ready; no model request.
- R-3 Plain UI: at start (cli.py:236-241), when nothing is missing, each distinct warn `line` is shown once as `! <line>` and the run continues without the readiness menu. `readiness_screen` lists warn lines too. Warnings add no key or action.
- R-4 TUI Settings: a warn row gets a yellow `! ` marker (not the red block style) and the full escaped doctor text, as ok rows do. `Check` gains `severity: str = "ok"` as its last field. The header (`readiness_summary`) is unchanged.
- R-5 Gating: warn keeps ok=True, so the planning gate and every `all(i["ok"])` check (cli.py:238, planning.py:277) are unchanged; warnings never block start, plan or resume.
- R-6 Text: the Russian doctor help names WARN and "exit 0 when nothing is BLOCKED"; the English short help is unchanged, so docs/REFERENCE.md stays as is (`python -m terminal_planner.catalog --check docs/REFERENCE.md` passes).

Acceptance (injected readiness items, no disk probe, no network, no provider):
- A-2w (parent A-2, display half): a literal item with `"severity": "warn"`: doctor prints `WARN: <doctor>` and returns 0; plus a block item: BLOCKED and 1. Settings (Textual pilot, tests/tui_support.py) shows the warn row's full text with the warn marker. Plain start shows `! <line>` and proceeds with no menu; `readiness_screen` shows it with no extra key.
- A-S Severity: `item()` defaults and each inconsistent pair raising ValueError; `severity()` on a dict without the key.
- A-C Compatibility: the DoD suites pass unchanged; a warn item leaves `Planning` start ready.
- A-6 Base replay (parent A-6, base 6e23523): the A-2w regressions use literal dicts and existing entry points only, so on the base they reach and fail their behavioral assertion (OK printed, nothing shown, ✓ row), not an import error. `item()`/`severity()` tests are candidate-only.
- Mutations (each killed by a named test): doctor prints OK for warn; warn makes doctor exit 1; plain start hides warnings when ready; Settings renders warn as ✓; `item()` accepts warn with ok=False.

Size: ~200-350 lines with tests (target 200-450); above 600, stop and re-gate.

Out of scope: s5a2, s5a3 as above; header summary; the GATEWAY_* warning (s3a3).

DoD: `PYTHONPATH=.:tests python3 -m unittest tests.test_warn_contract tests.test_setup tests.test_ux tests.test_tui tests.test_tui_polish tests.test_reference` pass; receipt devtools/zeroshot/tasks/s5a1-warn-contract-receipt.md with base commit, file list, base-replay failures and mutation table (mutation, killing test, result).
