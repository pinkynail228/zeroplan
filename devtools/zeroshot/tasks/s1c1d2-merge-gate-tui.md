s1c1d2-merge-gate-tui — 0.5 item S1c, slice 4b of devtools/zeroshot/tasks/s1c1-merge-gate.md (parent R-3 actions, R-8; parent ID map in s1c1a-merge-gate-core.md). The TUI for what s1c1d1-merge-gate-plain.md wires in Delivery and plain; it renders and calls, it decides nothing. Mirrors s1a1c2-gate-tui.md. DeepSeek worker, sol reviewers.

Base: the s1c1d1 integration branch (s1c1d1 R-9), not main; the pair is integrated together. Lines below are cited at main 8f1f62c and will move. Record the actual base and this brief's sha256 in the receipt, re-check every cited line, and re-gate if a premise moved.
- Consumes, unchanged, from s1c1d1: the `merge_gate` screen's action set and offer table (R-2), `merge_gate_lines`, `findings_note`, the R-8 texts, and the s1c1b/s1c1c service calls. If they differ, stop and re-gate.

Order: s1c1d1 → s1c1d2 (this) → pair integration into main (end of S1c1 in 0.5; s1c1e1/s1c1e2 deferred to 0.5.x, critic gate22). GO by critic gate22: no own validity logic.

Write-set (exclusive for this slice):
- catalog.py: action `tui_run.gate` (key `c`, free at 8f1f62c :573-587); screen `tui_merge_gate` with `run`/`rerun` (`g`), `watch` (`w`), `override` (`o`), `override_checks` (`k`), `attempt` (`n`), `details` (`i`), `back` (`esc`), `help` (`?`); docs/REFERENCE.md regenerated;
- tui/app.py: `PRIMARY` :86 and the `tui_run` binding/`IDS` block :841-848; the end handler next to `merge` :2789-2793; a `MergeGateScreen` mirroring s1a1c2's `tui_gate` screen; the merge confirmation shows s1c1d1's merge-question lines;
- tui/controller.py: jobs `merge_gate` (dispatch/observe, mutating: a quit waits, controller.py:29-36 rule), `override_merge_gate`, `override_failed_checks` next to `merge` :801-807; `n` reuses the existing new-attempt job with the s1c1d1 note and keyword;
- new `tests/test_tui_merge_gate.py`;
- the receipt `devtools/zeroshot/tasks/s1c1d2-merge-gate-tui-receipt.md`.
Not touched: delivery.py, runs.py, cli.py, merge_gate.py, engine.py, authority.py, process.py, existing tests and goldens, docs except REFERENCE.

Rules:
- R-1 Off: with `/1` or `gates.merge: off` every TUI screen, binding list, footer and pilot transcript is identical to base; `c` not bound to a visible action.
- R-2 Same offers and texts as s1c1d1 R-2/R-8, read from the same Delivery functions; no TUI-side decision.
- R-3 Long job: the gate dispatch/observe is a mutating job; the screen says it continues after leaving and offers `w` to watch.
- R-4 Fixtures: scratch paths and an isolated HOME/XDG only; no literal home paths.

Acceptance (tests/test_tui_merge_gate.py; tui_support pilots; FixtureEngine merge-gate scenarios; no network):
- A-1 Off: pilot transcripts of `tui_run` under `/1` and off equal base; no `c`. Control: required binds `c`.
- A-3 (parent, TUI part): each s1c1c family reached from TUI `m` with no side effect; `c` → `g` → accepted → `m` merges; `o` and `k` with valid reasons then `m` merges; an empty reason cancels.
- A-8t Display: the same lines as s1c1d1 A-8 on `MergeGateScreen` and in the merge confirmation (string-equal to `merge_gate_lines`).
- A-L Long job: quit during a gate dispatch waits for the job.
- A-7 Base failure: pilot, required, awaiting_merge with a current passed qualification, press `c`: assert the active screen is `tui_merge_gate`. On base (the s1c1d1 branch) it fails by that named assertion. Report named failures and skips separately.
- Mutations: (a) `c` bound under off; (b) the TUI computing its own offers (an `o` on a stale gate); (c) the gate job not mutating.

Size: estimated 330-420 changed lines, receipt and REFERENCE excluded: product ~160 (app ~110, controller ~35, catalog ~15), tests ~170-240. Above 600: report the measured overrun and rationale in the receipt; merge requires explicit critic disposition (ORCHESTRATOR step 1).

Parallelism: tui/app.py and controller.py serial with every TUI slice (s1a1c2, s1b2b, V1..V5 flow slices).

Out of scope: plain, Delivery and service (s1c1d1, s1c1c); release input (s1c1e2, 0.5.x).

DoD:
- Worker (targeted): `PYTHONPATH=.:tests python3 -m unittest tests.test_tui_merge_gate tests.test_merge_gate_ui tests.test_tui_task_gate tests.test_tui_milestones tests.test_tui tests.test_toolchain tests.test_reference` passes (verify every module path on the base). No full suite.
- `git diff --stat <base>` lists only the write-set; `python3 -m terminal_planner.catalog --check docs/REFERENCE.md` prints "docs current".
- `python3 devtools/export_check.py` reports no home-path finding on the committed candidate.
- Receipt: base, this brief's sha256, file list, A-7 counts, the mutation table.
- Orchestrator: the full suite on the Linux test host and the touched modules plus importers on macOS, on the pair, before integrating it into main.
