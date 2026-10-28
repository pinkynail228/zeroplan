Deferred to 0.5.x (critic gate22): not launched for 0.5. Pre-launch notes: depends on the s1b3a pre-launch notes (shared deadline/cancel contract incl. checkout and cleanup; the 10 h bound covers checks only; optional-limit edits serialized with s9b1); re-base on the merge-gate UI (s1c1d1/s1c1d2) that will own the same end-screen blocks by then.

s1b3b-flake-ui — 0.5 item S1b (S6 inside), slice 3b of devtools/zeroshot/tasks/s1b-checks.md: the owner action and the diagnosis table on plain and TUI for what s1b3a-flake-diagnosis.md built in Delivery. Split like s1b2a/s1b2b (critic gate12 point 4). Parent ID map: s1b3a-flake-diagnosis.md. DeepSeek worker, sol reviewers.

Base: main after the s1b3a-flake-diagnosis merge. Lines below are cited at main 8f1f62c and will move (s1b2b adds `[v]`/`[i]` qualification wiring at the same places). Record the actual base and this brief's sha256 in the receipt, re-check every cited line, and re-gate if a premise moved.
- Consumes, unchanged, s1b3a: `Delivery.diagnose(r)`, `Delivery.diagnosis(r)`, the record (R-6), the verdict labels (R-8), `flake_reruns(config)`; and s1b2b's `[v]`/`[i]` wiring and long-job rule. If they differ, stop and re-gate.

Order: s1b3a → s1b3b (this). Then S1c (s1c1c consumes nothing from here).

Write-set (exclusive for this slice):
- delivery.py: the awaiting_merge `actions` of `view` :755 (diagnose added dynamically, never to static `END_ACTIONS` :86-97); the `[i]` lines s1b2b added (one diagnosis table after the per-check lines); the R-6 diagnosis texts;
- process.py: `describe` rounds line :770-772 appends "; перезапуски проверки N" only when `flake_reruns` is present in the resolved config (absent: byte-identical);
- catalog.py: actions `awaiting_merge.diagnose`, `tui_run.diagnose` (key `f`, free on both screens at 8f1f62c: :501-503, :573-587); docs/REFERENCE.md regenerated;
- cli.py: the end-screen handler next to `merge` :747-756;
- tui/controller.py: a `diagnose` job next to `merge` :801-807, registered as mutating (as s1b2b's qualify job); tui/app.py: the `tui_run` handler next to :2789-2793, the binding next to :841, `IDS` :848, `PRIMARY["tui_run"]` :86;
- docs/USER_FLOW.md (the qualification paragraph s1b2b added: one diagnosis paragraph), docs/PROCESS_PROFILE.md (S6 flake diagnosis built; `limits.flake_reruns` documented);
- new `tests/test_flake_ui.py`;
- the receipt `devtools/zeroshot/tasks/s1b3b-flake-ui-receipt.md`.
Not touched: flake.py, qualification.py, checks.py, check_guard.py, authority.py, runs.py, existing tests and goldens.

Rules:
- R-1 Scope: s1b3a R-1. Off, `checks: []`, or no failed current qualification: every screen, key list, `Дальше:` line and REFERENCE row outside the new entries is byte-identical to base.
- R-2 Offer: `[f]` "диагностика нестабильности" on `awaiting_merge` and `tui_run` only when the newest qualification is concluded, failed and current (s1b3a R-3) and no diagnosis or qualification is идёт; `next_step` unchanged (a diagnosis is never the next step). It calls `Delivery.diagnose(r)`; a refusal prints the family text and stays on the screen.
- R-3 Long job: TUI: a mutating controller job (quit waits); the screen states the bound `2 × n × timeout_s` of the check. Plain: foreground; Ctrl-C reaches s1b3a R-10.
- R-4 `[i]` table (parent R-6): under the per-check lines, per diagnosis of the shown qualification (newest first, at most 3 shown, "ещё K" otherwise): check name, n, "база: b из n, кандидат: c из n", the verdict text, and per run one line `side index status duration`. Verdict texts: candidate_regression "падает только на кандидате (регрессия кандидата)", candidate_flake "нестабильна только на кандидате", preexisting_flake "нестабильна и на базе", unclear "неясно". A note line: "Это наблюдение, а не доказательство причины." Running → "идёт: r из 2n"; interrupted → "диагностика прервана". The qualification state line stays "не прошла (<check>)" in every case (s1b3a R-9).
- R-5 Text: every label in the catalog; REFERENCE regenerated.
- R-6 Fixtures: scratch paths and an isolated HOME/XDG only; no literal home paths.

Acceptance (tests/test_flake_ui.py; plain-terminal fixture and tui_support pilots; checks `sys.executable -c ...`; no network):
- A-1 Off: plain end screen, TUI `tui_run` pilot, `describe` under `/1`, off, and required with a passed qualification: equal to base; no `f`. Control: a failed current qualification offers `f`.
- A-5u UI: `f` runs one diagnosis (n=1 via `limits.flake_reruns: 1`); `[i]` shows the counts line, the verdict text, 2 run lines and the note; the qualification line still says "не прошла (<check>)". While идёт: no `f`, no `v`.
- A-6u Bounds: 4 diagnoses → 3 shown plus "ещё 1"; n=10 → 20 run lines.
- A-8 Long job: TUI quit during a diagnosis waits; plain Ctrl-C saves `interrupted` and `[i]` says "диагностика прервана".
- A-7 Base failure (action-based): plain end screen of an awaiting_merge attempt with a failed current qualification, required: assert `"diagnose" in [a.name for a in view.actions]`. On base (s1b3a merged) it fails by that named assertion. Report named failures and skips separately.
- Mutations: (a) `f` in static `END_ACTIONS`; (b) `f` on a passed or stale qualification; (c) the diagnose job not mutating; (d) a verdict changing the qualification line; (e) describe line printed when `flake_reruns` is absent.

Size: estimated 240-320 changed lines, receipt and REFERENCE excluded: product ~100 (delivery ~35, process ~5, catalog ~10, cli ~15, tui ~35), docs ~20, tests ~120-180. Above 600: report the measured overrun and rationale in the receipt; merge requires explicit critic disposition (ORCHESTRATOR step 1).

Parallelism: shares delivery `view`/`[i]`, cli/TUI end wiring and catalog action blocks with s1c1d: serial (this first). With s1c1a/s1c1b: none.

Out of scope: records, verdict, restart (s1b3a); merge gate (S1c).

DoD:
- Worker (targeted): `PYTHONPATH=.:tests python3 -m unittest tests.test_flake_ui tests.test_flake tests.test_qualification_ui tests.test_qualification tests.test_process tests.test_ux tests.test_tui_milestones tests.test_docs tests.test_toolchain tests.test_reference` passes (the qualification and flake modules exist after s1b2a/s1b2b/s1b3a; verify every path on the base). No full suite.
- `git diff --stat <base>` lists only the write-set; `python3 -m terminal_planner.catalog --check docs/REFERENCE.md` prints "docs current".
- `python3 devtools/export_check.py` reports no home-path finding on the committed candidate.
- Receipt: base, this brief's sha256, file list, A-7 counts, the mutation table.
- Orchestrator, before merge: the full suite on the Linux test host.
