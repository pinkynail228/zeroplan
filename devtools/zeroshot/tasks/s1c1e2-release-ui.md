Deferred to 0.5.x (critic gate22): not launched for 0.5. Pre-launch note: launch only after s1c1e1 (whose accessor note applies); re-base on the then-current merge-gate screens.

s1c1e2-release-ui — 0.5 item S1c, slice 5b of devtools/zeroshot/tasks/s1c1-merge-gate.md (parent R-3 release-input action, R-8 release decision; parent ID map in s1c1a-merge-gate-core.md, where "s1c1e" means s1c1e1 + this). The owner entry for s1c1e1-release-input.md on plain, CLI and TUI; it renders and calls, it decides nothing. DeepSeek worker, sol reviewers.

Base: main after the s1c1e1-release-input merge. Lines below are cited at main 8f1f62c and will move. Record the actual base and this brief's sha256 in the receipt, re-check every cited line, and re-gate if a premise moved.
- Consumes, unchanged: s1c1e1's frozen contract (`set_release_input`, `release_input`, `is_release`, the R-2 domain, families `merge.release_input`/`merge.release_missing`); s1c1d1/s1c1d2's `merge_gate` and `tui_merge_gate` screens and `merge_gate_lines`. If any differs, stop and re-gate.

Order: s1c1e1 → s1c1e2 (this). Plain and TUI land together in this slice (no integration branch needed; the size allows it).

Write-set (exclusive for this slice):
- catalog.py: action `release` (key `r`, "решение о выпуске") on the `merge_gate` and `tui_merge_gate` screens, offered only when `Delivery.is_release(r)` under required; s1c1e1's remedies now name `[c]` → `[r]`; docs/REFERENCE.md regenerated;
- delivery.py: `merge_gate_lines` and `merge_question` add, for a release milestone, "Выпуск: <version> — <proposed_verdict>; решение: <decision>" and "Чек-лист: N из M отмечено" (or "Выпуск: решение не внесено"); a pure `release_form(r)` returning the prefill (the live input or empty fields plus the frozen checks);
- cli.py: a `release_screen(r)` prompting version, decision, proposed verdict, then each check in order (y/n plus optional note); an empty version cancels; a refusal prints the family text and keeps the store unchanged;
- tui/app.py and tui/controller.py: a `ReleaseScreen` with the same fields (one row per frozen check, checkbox plus note), submit through a short controller job calling `set_release_input`;
- docs/USER_FLOW.md (release milestone: `[c]` → `[r]` → `g` → `[m]`), docs/PROCESS_PROFILE.md (release mode built);
- new `tests/test_release_ui.py`;
- the receipt `devtools/zeroshot/tasks/s1c1e2-release-ui-receipt.md`.
Not touched: merge_gate.py, authority.py, engine.py, runs.py, process.py, existing tests and goldens, README.md.

Rules:
- R-1 Absence: for non-release milestones and under off, every screen, key list, merge question and REFERENCE row outside the new entries is identical to base; `r` not offered.
- R-2 Same texts: plain and TUI show the strings of `merge_gate_lines`/`merge_question`; validation is s1c1e1's (no UI-side length check beyond input widgets accepting the text).
- R-3 Prefill: the form opens with the live input when present, so a one-status edit is one change (and then makes the gate stale, s1c1e1 R-4).
- R-4 Fixtures: scratch paths and an isolated HOME/XDG only; no literal home paths.

Acceptance (tests/test_release_ui.py; plain fixture and tui_support pilots; FixtureEngine; no network). Each test names entry point, oracle and control.
- A-1 Absence: non-release milestone and `/1` goldens of the gate screen, merge question and TUI transcript equal base. Control: a release milestone offers `r`.
- A-5u (parent A-5 through UI): release milestone, plain `c` → `r` → fill → `g` → accepted → `[m]` merges; the same through the TUI pilot; `[m]` before `r` prints `merge.release_missing`.
- A-3bu Boundary refusal through each UI: a 129-character version and a 501-character note → the family text, store bytes unchanged.
- A-8 (parent R-8, release part): merge question and gate screen lines for a filled, an absent and a stale input.
- A-7 Base failure: plain gate screen of a release milestone under required: assert `"release" in [a.name for a in screen.actions]`. On base it fails by that named assertion. Report named failures and skips separately.
- Mutations: (a) `r` offered for a non-release milestone; (b) the form not prefilled (a status edit drops the decision); (c) the TUI validating locally and storing a truncated value.

Size: estimated 380-460 changed lines, receipt and REFERENCE excluded: product ~200 (cli ~60, tui ~90, delivery ~30, catalog ~20), docs ~15, tests ~170-240. Above 600: report the measured overrun and rationale in the receipt; merge requires explicit critic disposition (ORCHESTRATOR step 1).

Parallelism: tui/app.py and controller.py serial with every TUI slice; delivery/catalog serial with s1c2.

Out of scope: schema, store, rule (s1c1e1).

DoD:
- Worker (targeted): `PYTHONPATH=.:tests python3 -m unittest tests.test_release_ui tests.test_release_input tests.test_merge_gate_ui tests.test_tui_merge_gate tests.test_tui tests.test_ux tests.test_docs tests.test_toolchain tests.test_reference` passes (verify every module path on the base). No full suite.
- `git diff --stat <base>` lists only the write-set; `python3 -m terminal_planner.catalog --check docs/REFERENCE.md` prints "docs current".
- `python3 devtools/export_check.py` reports no home-path finding on the committed candidate.
- Receipt: base, this brief's sha256, file list, A-7 counts, the mutation table.
- Orchestrator, before merge: the full suite on the Linux test host.
