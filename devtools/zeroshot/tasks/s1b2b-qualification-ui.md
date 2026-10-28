s1b2b-qualification-ui — 0.5 item S1b, slice 2b of devtools/zeroshot/tasks/s1b-checks.md. Split of s1b2-qualification-records.md by critic gate12 (~/zs-pause/critic/gate12.out:8, point 4): the owner action on plain and TUI for what s1b2a-qualification-records.md built in Delivery. DeepSeek worker, sol reviewers.

Base: main after the s1b2a-qualification-records merge. Lines below are cited at main 299c377 (product code identical to 28c2c29) and will move. Record the actual base and this brief's sha256 in the receipt, re-check every cited line, and re-gate if a premise moved.
- Consumes, unchanged, s1b2a: `Delivery.qualify(r)`, `Delivery.qualification(r)`, the R-6 texts, families `qualification.refused`/`qualification.running`. If they differ, stop and re-gate.

Write-set (exclusive for this slice):
- delivery.py: the awaiting_merge `actions` of `view` :779-782 (qualify added dynamically, never to static `END_ACTIONS` :86-97); `next_step` :431-452 names the qualify label only when R-1 is active; the `[i]` lines;
- process.py: `describe` :778-779 and `bootstrap_lines` :798-799 drop "для следующих этапов" on the checks line only under `gates.merge == "required"`; `UNBUILT["merge"]` :50 reworded to the parent's message (s1b-checks.md:25), e.g. "checks записаны, merge critic ещё не реализован: выключите проверку слияния в zplan.process.json"; the family stays `process.unbuilt`;
- catalog.py: actions `awaiting_merge.qualify`, `awaiting_merge.details`, `tui_run.qualify` (key `v`, free: :495-497, :567-587); the s1b2a remedies now name `[v]`; docs/REFERENCE.md regenerated;
- cli.py: the end-screen handlers :730-733 and a `qualify` handler next to `merge` :747-760;
- tui/controller.py: a `qualify` job next to `merge` :801-807; tui/app.py: the `tui_run` handler next to :2789-2792 and `PRIMARY["tui_run"]` :87;
- docs/USER_FLOW.md ("End screens" :387-412: one qualification paragraph), docs/PROCESS_PROFILE.md (:120 G3 checks part built; merge critic still unbuilt);
- new `tests/test_qualification_ui.py`;
- the receipt `devtools/zeroshot/tasks/s1b2b-qualification-ui-receipt.md`.

Not touched: qualification.py, checks.py, check_guard.py, authority.py, runs.py, commands.py, existing tests and goldens.

Rules:
- R-1 Scope: as s1b2a R-1 (required and non-empty checks); off is byte-identical to base on every screen, key list, `Дальше:` line and REFERENCE row outside the new entries.
- R-2 Action: `[v]` "квалифицировать" / "квалифицировать заново" (stale, failed, interrupted) on `awaiting_merge` and `tui_run`, only when R-1 is active and `Delivery.qualification(r)` is not идёт; it calls `Delivery.qualify(r)`; refusals print the family text and stay on the screen.
- R-3 `[i]`: plain `awaiting_merge.details` (offered only when active) and the existing `tui_run.details` (appended only when active): per-check status, `duration_s`, the stored tail, under commit/tree/HEAD short ids.
- R-4 Long job (was s1b2 R-8): in the TUI the qualification is a controller job registered as mutating (controller.py:29-36), so a quit waits for it; the screen says it continues and its bound (sum of `timeout_s`). Plain runs it in the foreground; Ctrl-C reaches the executor's interrupt path (s1b2a R-2). Cancel UX stays parked (gate11 point 2).
- R-5 Text: every label in the catalog; REFERENCE regenerated; `UNBUILT["merge"]` text shown only under required.
- R-6 Fixtures: every literal home path in tests is under `/home/user/`.

Acceptance (tests/test_qualification_ui.py; plain-terminal fixture and tui_support pilots; checks run `sys.executable -c ...`; no network):
- A-1 Off: plain end screen, TUI `tui_run` pilot, `describe`, `bootstrap_lines` under `/1` and off equal base; no `v`. Control: required offers `v`.
- A-6u UI: plain end screen and TUI pilot offer `[v]` only when active; `?` lists it (test_reference :231 passes); `v` runs one qualification and the body line changes to "прошла"; `[i]` shows the per-check lines and the scrubbed tail; while идёт no `[v]`.
- A-8 Long job: TUI quit during a qualification waits for the job (the mutating rule); plain Ctrl-C saves `interrupted`.
- A-9 Merge text: under required, `Delivery.merge` refuses with `process.unbuilt` and the new text; off unchanged.
- A-7 Base failure (action-based): plain end screen of an awaiting_merge attempt, required, one check: assert `"qualify" in [a.name for a in view.actions]`. On base (s1b2a merged) it fails by that named assertion. Report named failures and skips separately.
- Mutations: (a) qualify in static `END_ACTIONS` (off `Дальше:` changes); (b) `[v]` with `checks: []`; (c) `[v]` while идёт; (d) the TUI job not mutating (quit does not wait); (e) `UNBUILT["merge"]` old text under required; (f) describe still says "для следующих этапов" under required.

Size: estimated 260-340 changed lines, receipt and REFERENCE excluded: product ~110 (delivery ~20, process ~8, catalog ~12, cli ~25, tui ~45), docs ~30, tests ~120-200. Above 600: report the measured overrun and rationale in the receipt; merge requires explicit critic disposition (ORCHESTRATOR step 1).

Parallelism: shares delivery `next_step`, cli/TUI end wiring and catalog action blocks with s1a1c1/c2: serial with them. With s2b3: catalog.py and USER_FLOW (different blocks; sequential integration). REFERENCE regenerated by the second merge.

Out of scope: records, validity, restart (s1b2a); flake diagnosis (s1b3); merge critic (S1c); a subcommand (gate11 point 1: TUI + `zplan --plain`).

DoD:
- Worker (targeted): `PYTHONPATH=.:tests python3 -m unittest tests.test_qualification_ui tests.test_qualification tests.test_process tests.test_ux tests.test_tui_milestones tests.test_docs tests.test_toolchain tests.test_reference` passes. No full suite.
- `git diff --stat <base>` lists only the write-set; `python3 -m terminal_planner.catalog --check docs/REFERENCE.md` prints "docs current".
- `python3 devtools/export_check.py` reports no home-path finding on the committed candidate.
- Receipt: base, this brief's sha256, file list, A-7 counts, the mutation table.
- Orchestrator, before merge: the full suite on the Linux test host.
