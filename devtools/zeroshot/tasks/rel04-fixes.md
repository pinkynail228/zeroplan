rel04-fixes — release 0.4.0 step 11 BLOCK repair (fresh release review, session 01a15375-895d-7402-aae0-bfba5d11deec; route: critic rel04-block-plan GO WITH CHANGES). DeepSeek worker, sol reviewers. The result becomes the new release candidate C2; keep the change minimal.

Base: main (candidate c242370 plus task documents only). Record the base commit in the receipt.

Findings (at c242370):
- F-1 blocker: terminal_planner/tui/controller.py:526 `start_planning` (chat `c` -> Ctrl+G, and the goal form) calls `planning.begin` while a milestone writer is active. It creates revision r2; r1's run leaves the overview, and its result can no longer be exported or merged through the UI. `revise` refuses this case through `runs.revise_plan` (runs.py:1292-1297, `self.active()`); `Planning.begin` (planning.py:296) has no such guard. The plain `[p]` path does not reach `begin` in this case: with an approved plan and an active milestone, cli.py:413-414 opens the existing plan.
- F-2 major: terminal_planner/tui/app.py:1621 builds a real `ArchitectChat` in `--fixture` sessions; Enter starts Codex and uses the project's production transcript. Fixture mode promises an isolated demo without tokens.
- F-3 minor (release checklist step 10): docs/REFERENCE.md:147 (hand-written prose, outside the generated sections) describes the `architect` role as unused, but it sets the model/effort of every chat turn; the README code map (introduced at README.md:151) misses the process-profile and chat services.

Read: those locations; terminal_planner/planning.py, runs.py (`active`, `ACTIVE`, `revise_plan`), tui/controller.py, tui/app.py (chat construction and chat keys), terminal_planner/tui/chat.py, terminal_planner/architect.py, cli.py (home keys and the `[p]` flow), catalog.py (role texts), README.md, docs/REFERENCE.md generation (devtools or catalog), tests for chat, controller, planning and plain home.

Rules:
- R-1 Active-writer refusal in `Planning.begin`, before any revision is created or persisted: if `runs.active()` reports a writer (every status in `runs.ACTIVE`), refuse with `action.refused` and the same wording pattern as `revise_plan` ("Milestone M… ещё выполняется; …"). One rule for every caller (TUI chat, TUI goal form, plain). Do not duplicate the check in the controller. `renew`/`restart`/`send` keep their current behavior unless they reach `begin` through the same path; say in the receipt which callers reach the guard.
- R-2 Fixture sessions have no architect chat: no `ArchitectChat` is constructed when the session is a fixture session; the chat key shows one line "Чат архитектора недоступен в демо (--fixture)." and nothing else happens (no Codex, no transcript read or write). Production chat is unchanged.
- R-3 Docs: edit the REFERENCE.md:147 prose directly so the `architect` role sets the model/effort of each architect chat turn; README code map lists the process-profile and chat modules with one line each. Change the catalog only if its own text is wrong; the REFERENCE generator check must still pass. No other doc rewrites.

Acceptance (unit tests, deterministic, no network):
- A-1 F-1 regression through a production entry point: a production-mode (non-fixture) TUI pilot with a valid accepted profile and passing readiness, the real `Planning.begin`/controller wiring, and fakes only for external dependencies (provider, native engine). M1 is held active with explicit Event barriers. A chat goal handed over with Ctrl+G is refused with the R-1 message; the revision, approval and run identity are unchanged; M1 stays visible on home. Then release the barrier: after the fake run finishes, its result can be exported and merged through the existing actions. Readiness failure, stale-draft rejection or timing must not be what refuses. It fails on the base at a named assertion.
- A-2 Plain: not reachable (cli.py:413-414 opens the existing plan); state this in the receipt; no plain regression test.
- A-3 `Planning.begin` unit test for each `runs.ACTIVE` status: refused, store bytes unchanged; each case is a named failure on the base (setup/invalid-record failures excluded). Positive controls: with no active writer, including terminal historical attempts, `begin` still creates the revision.
- A-4 F-2: using the actual fixture-session construction for `demo` and another valid fixture id, exercise startup, chat submission via Enter, retry and reset: each shows the R-2 line, with zero `ArchitectChat` construction, provider calls and production transcript access (spies). A production session completes one chat turn with a fake provider. The fixture assertions fail on the base.
- A-5 Docs: REFERENCE.md regenerated and the generator check test passes; existing doc tests pass.
- A-6 Base failure: report named failures and skips separately for A-1, A-3, A-4 on the base; import/missing-symbol/setup failures and skips do not count.

Size: about 150-300 changed lines including tests; above 300, a mandatory re-gate point, never a reason to cut acceptance.

DoD:
- Targeted tests pass (tests for chat, controller/TUI, planning, plain home, catalog/docs).
- REFERENCE.md regenerated; README updated.
- Receipt: devtools/zeroshot/tasks/rel04-fixes-receipt.md (base commit, findings -> tests, callers reaching the guard, A-6 results, product/test line split).
critic rel04-fixes-task: GO WITH CHANGES (F-1 plain path, F-3 location, A-1 barriers/readiness, A-3 controls, A-4 actions — applied), session 01a152da-ffb0-7500-9ad4-a3f0e4fa2edb
SUPERSEDED 2026-10-19: run 01a15382 stopped before any change; replaced by the class repairs rel04-lifecycle-guard.md and rel04-fixture-scope.md (critic rel04-classes).
