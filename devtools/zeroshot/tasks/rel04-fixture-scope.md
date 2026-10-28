rel04-fixture-scope — release 0.4.0 class repair 2 of 2 (step 11 BLOCK F-2 and F-3; class audit: critic rel04-classes, session 01a15375-895d-7402-aae0-bfba5d11deec, /tmp/zs-zplan/critic/rel04-classes.out). DeepSeek worker, sol reviewers. Part of the new release candidate C2. Runs in parallel with rel04-lifecycle-guard from a fixed main SHA (critic fixture-parallel GO: lifecycle-guard touches authority.py, planning.py, runs.py and tests only; the overlap is tests/test_tui_chat.py).

Base: main at the run start (record the commit in the receipt). Compatibility with rel04-lifecycle-guard (Authority.approve/override read Profile.live_digest themselves) is checked by the orchestrator on the merged candidate. The audit is at c242370; re-check every line number on the base.

Problem (class): fixture isolation is a convention per service, not one boundary. Reachable at c242370 from a `--fixture` TUI session:
- the architect chat: `tui/app.py:1621` builds a real `ArchitectChat`; on mount `_prepare -> _store -> ArchitectStore(project)` (`tui/chat.py:501,523`) reads production chat history and runs tool version probes (Zeroshot/Codex/restic); Enter runs a Codex turn (`architect.py:685`), Enter/reset write the production session/transcript; the chat binding reads the production process state.
- `install/login=None` and `tools=False` are set by local CLI wiring; low-level setup/login APIs do not know the mode (latent).
- Profile accept in a fixture session writes the real `<target>/zplan.process.json` (both UIs).
Not defects (intended local effects): fixture planning/run/process stores, local Git refs/worktrees/merge, checker runs; no fetch/push/network transport in the fixture workflow.

Read: cli.py (session composition, `--fixture`, `install/login/tools` wiring), tui/app.py (chat construction, keys), tui/chat.py, architect.py, chat.py, process.py (accept, project file), engine.py/driver fixture classes, setup.py/login entry points, README.md code map (:151), docs/REFERENCE.md (:147 hand-written prose), docs/USER_FLOW.md fixture section, the existing tests (test_tui_chat.py, fixture/plain tests).

Scope decision (critic rel04-pushback, AGREE WITH CHANGES): 0.4.0 gets the minimal fixture repair below. The mandatory session scope object, the all-keys effect spy and the source-derived sink inventory move to 0.5 (STATE Open); they are not acceptance here.

Rules:
- R-1 Classify fixture mode by `fixture_id is not None`, not truthiness, everywhere the CLI/session composition decides fixture behavior (e.g. cli.py:921, 930, 975, 986, 994, 999 at c242370; re-check on base). Validate the fixture id right after argument parsing, before setup/attach_tools or any other external I/O: `--fixture '' setup` and an invalid id are refused (today the empty id slips past cli.py:921 and installs tools).
- R-2 Fixture sessions construct no `ArchitectChat`, `ArchitectStore`, provider or tool probe (a disabled chat view is allowed). The chat key shows "Чат архитектора недоступен в демо (--fixture)."; Enter/retry/reset do nothing else (no Codex, no production transcript/session/process-state read or write, no version probes). Family `action.refused`.
- R-3 Profile in a fixture session (both bootstrap UIs and `profile init`): accept/defer persist the effective profile snapshot only in fixture state; a missing `<target>/zplan.process.json` is not created and an existing one stays byte-identical. Reopen stays usable without the project file (accept -> plan -> reopen must not become accepted -> missing).
- R-4 Production (native) sessions behave as today: chat works, probes run, profile accept writes the project file.
- R-5 Docs (F-3): edit docs/REFERENCE.md:147 prose so the `architect` role sets the model/effort of each architect chat turn; the README code map lists the process-profile and chat modules with one line each; USER_FLOW.md fixture section says the demo has no architect chat and makes no provider calls or target-profile writes (local Git/checker effects and fixture stores remain). The REFERENCE generator check must still pass.

Acceptance (unit tests, deterministic, no network; base reproductions enter through the existing `cli.main`/session composition, not a newly introduced factory):
- A-1 Startup and refusal: for `demo` and another valid fixture id, TUI (pilot) startup, chat key, Enter, retry and reset show the R-2 line with zero `ArchitectChat`/`ArchitectStore` construction, provider calls, tool probes and production transcript access (spies); tools/login treated as available. Plain fixture session: unchanged (no chat). Named failures on the base.
- A-2 Invalid ids: `--fixture ''` and an invalid id with `setup` (and the TUI/plain entry) are refused before any setup/attach_tools call or process spawn. Named failure on the base for the empty id.
- A-3 Profile: `cli.main ... --fixture demo profile init` and the TUI/plain bootstrap accept: a missing project file is not created; an existing one is byte-identical; accept -> plan -> reopen without the file still works. Named failures on the base.
- A-4 Production session: one chat turn completes with a fake provider; tool probes run; profile accept writes the project file (no regression).
- A-5 Docs tests and the REFERENCE generator check pass.
- A-6 Base failure report: named failures and skips separately; import/missing-symbol/setup failures do not count.

Size: about 60-120 product lines and 150-300 test lines; above 500 total, a mandatory re-gate point, never a reason to cut acceptance. After both merge: merge-tree gate with both regression sets (fixture accept -> plan -> approve -> reopen, production chat); a conflict or incompatibility gets a short repair run on top of the updated main, never hand product edits.

DoD:
- Targeted tests pass (tui chat, app, cli/plain, process, setup, docs/catalog).
- REFERENCE.md, README.md, USER_FLOW.md updated.
- Receipt: devtools/zeroshot/tasks/rel04-fixture-scope-receipt.md (base commit, which constructions/sinks are now skipped in fixture mode, R-3 decision, A-6 results, product/test split, items deferred to 0.5).
critic rel04-class-tasks: GO WITH CHANGES (mandatory scope, fixture_id is not None, R-3 contract fixed, R-5 wording, A-1/A-3 inventory and allowlist — applied), session 01a15375-895d-7402-aae0-bfba5d11deec
critic rel04-pushback: AGREE WITH CHANGES (minimal 0.4.0 scope; empty-id setup edge and profile init path added; session scope/spy/inventory deferred to 0.5), same session
critic fixture-parallel: GO (parallel start; merge-tree gate after lifecycle-guard), same session
