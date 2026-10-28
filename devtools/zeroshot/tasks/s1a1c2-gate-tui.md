s1a1c2-gate-tui — 0.5 item S1a, slice 3b of devtools/zeroshot/tasks/s1a1-task-gate.md (the parent; R-5, R-6, A-1 apply). Split of s1a1c-gate-ui.md by critic gate11 B (~/zs-pause/critic/gate11.out:9-13): the TUI for what s1a1c1-gate-plain.md wires in the service and the plain screens. Lane L2. DeepSeek worker, sol reviewers.

Base: the s1a1c1 integration branch (s1a1c1-gate-plain.md R-9), not main; the pair is integrated together. Lines below are cited at main 28c2c29 and will move. Record the actual base and this brief's sha256 in the receipt, re-check every cited line, and re-gate if a premise moved.
- Consumes, unchanged, from s1a1c1: `Row.admitted`, `home.gate` / `Pick("gate")`, `owner_context`, `admitted`, `task_gate_lines`, the catalog `task_gate` texts and the s1a1c1 R-2..R-6 rules. The TUI renders and calls them; it decides nothing itself. If they differ, stop and re-gate.

Write-set (exclusive for this slice):
- catalog.py: action `tui_panel.gate` (key `v`, block :529-566); screen `tui_gate` with `run`/`rerun`/`continue` (`g`), `watch` (`w`), `override` (`o`), `details` (`i`), `back` (`esc`), `help` (`?`); docs/REFERENCE.md regenerated;
- tui/app.py:
  - `PRIMARY` :80-89 entries for `tui_panel.gate` and `tui_gate`;
  - `g_action` :2409-2423 and `action_run_milestone` :2425-2445: a ready/failed/stopped row with `admitted == False` → `tui_panel.gate` (opens the modal; never preview/new attempt); `v` binding next to the main bindings :1335-1339;
  - the `tui_gate` modal (styled like `tui_run`), bound to (milestone, context, continuation);
  - owner actions routed through s1a1c1 R-3: answer draft `answer_draft_to_open` :2133 / `answer_draft_settled` :2203, end-screen answer :2775, new attempt :2781 and `new_attempt_milestone` :2529-2539, accept :2801: compute the context through `Delivery.owner_context`, and if not `admitted`, open `tui_gate` with the original controller call as the continuation;
- tui/controller.py: `run_gate`, `override_gate`, `gate_state` jobs; the dispatching slice of `run_gate` is mutating, observation slices are cuttable (rules :26-38); `take_snapshot` :240-256 unchanged (rows carry `admitted`);
- docs/USER_FLOW.md: the TUI lines of the gate step (s1a1c1 wrote the plain part);
- new `tests/test_tui_task_gate.py`;
- the receipt `devtools/zeroshot/tasks/s1a1c2-gate-tui-receipt.md`.

Not touched: delivery.py, runs.py, cli.py, planning.py, process.py, task_gate.py, existing tests and goldens, other docs.

Rules:
- R-1 Off: with `/1`, `gates.task: off` or no profile, every TUI screen, binding list, footer and pilot transcript is identical to base; `v` is not bound to a visible action.
- R-2 Panel offer: `[g]` on a row follows s1a1c1 R-2 through `Row.admitted`: not admitted → the gate modal; admitted → today's run/attempt; failed_recoverable resume and CHECK unchanged. `v` opens the modal for the selected ready/failed/stopped row.
- R-3 Owner-context path: answer, accept (candidate) and new attempt with a note open the modal bound to their context when not admitted; after accepted/overridden, `g` "продолжить" runs the original controller job with the same text. `esc` keeps the record and drops the draft text only if the owner leaves the answer form too (the existing draft rules apply).
- R-4 Modal keys as s1a1c1 R-4; `[i]` shows `task_gate_lines`.
- R-5 Lifecycle (parent R-6): a gate run is a controller job; quit waits for the dispatching slice; a restart mid-gate shows "идёт" and `w` observes without a second dispatch.
- R-6 Fixtures: every literal home path in tests is under `/home/user/`.

Acceptance (tests/test_tui_task_gate.py; tui_support pilots; FixtureEngine gate scenarios; no network):
- A-1 Off: panel, run modal, answer/accept/new-attempt pilots under `/1` and off equal base transcripts; no `v` in the footer. Control: required shows `v`.
- A-2 Panel: required, ready M1 without a gate: `g` opens `tui_gate`, start count 0; `v` the same; after accepted, `g` previews the start as today. failed_recoverable → resume without a gate (control).
- A-3a Answer and A-3p accept: needs_owner pilot → answer → modal bound to the answer → `g` → accepted → `g` продолжить → the attempt's context equals the s1a1c1 builder's and its `admission.gate` is that gate. Non-candidate accept → plan revision, no modal.
- A-3n New attempt with a note → modal on the answer context; empty note → context None.
- A-4 Override and stale as s1a1c1 A-4u/A-5u, through the modal.
- A-5 Restart: an `observing` gate, new TUI session → "идёт"; `w` observes; one FixtureEngine submission.
- A-7 Base failure: pilot, required, ready M1 without a gate, press `g`: assert the active screen is `tui_gate`. On base (s1a1c1 merged) it fails by that named assertion (the run preview opens). Report named failures and skips separately.
- Mutations, each killed by a named test: (a) `g_action` ignores `admitted`; (b) answer job sent without the R-3 check; (c) every observation slice posted as a dispatch; (d) `o` on a stale or running gate; (e) the modal computes its state instead of `task_gate_state` (TUI and plain texts differ); (f) `v` bound under off.

Size: estimated 330-420 changed lines, receipt and REFERENCE excluded: product ~150 (app ~105, controller ~30, catalog ~15), docs ~10, tests ~200. Above 600: report the measured overrun and rationale in the receipt; merge requires explicit critic disposition (ORCHESTRATOR step 1).

Parallelism: on top of s1a1c1 on its integration branch (s1a1c1 R-9). With s1b2b: tui/app.py and catalog TUI blocks are shared; serial. With s2b3: catalog.py and docs/USER_FLOW.md are shared (different blocks: s2b3 the readiness group and one doctor example; here `tui_panel`/`tui_gate` and the gate step's TUI lines), so the two integrate sequentially and the second regenerates REFERENCE. With s1b1b1, s1b1b2, s1b1c, s2b2: no shared file except REFERENCE.

Out of scope: everything in s1a1c1; cancel UX (gate11:14).

DoD:
- Worker (targeted): `PYTHONPATH=.:tests python3 -m unittest tests.test_tui_task_gate tests.test_task_gate_ui tests.test_tui_plan_gate tests.test_tui_milestones tests.test_tui_planning tests.test_ux tests.test_docs tests.test_toolchain tests.test_reference` passes. No full suite.
- `git diff --stat <base>` lists only the write-set; `python3 -m terminal_planner.catalog --check docs/REFERENCE.md` prints "docs current".
- `python3 devtools/export_check.py` reports no home-path finding on the committed candidate.
- Receipt: base, this brief's sha256, file list, A-7 counts, the mutation table.
- Orchestrator, before integration: the full suite on the Linux test host on the pair (s1a1c1 + this), then integrate both together.
