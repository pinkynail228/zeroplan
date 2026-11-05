# Project instructions

`zplan` is a terminal cockpit for turning a software goal into reviewed, verified Git branches with AI agents.

Read first: `STATE.md`, `docs/PRODUCT_CONTRACT.md`, and `docs/DEVELOPMENT.md`. Those documents are the active contract. Files under `docs/history/` (private archive) and the old harness under `devtools/zeroshot/` are historical evidence, not current instructions.

## Non-negotiable product rules

- Running `zplan` opens a useful terminal UI. A headless runner is an additional frontend for automation, never a replacement for the UI.
- The architect owns the conversation, plan, briefs, and run decisions. There is no separate LLM planner role.
- An independent critic reviews non-trivial plans and requested high-risk decisions. It does not co-author the plan or loop by default.
- Models explain and judge; deterministic code decides whether a check passed. A model can never turn a red, missing, or unrun check into a pass.
- Automatic merge requires at least one successful project check. No checks means no automatic merge. A baseline failure blocks automatic merge unless the owner explicitly accepts a reproduced, named-base exception.
- Only the exact reviewed and verified candidate tree may be merged. Manual fixups outside the change-and-review loop are forbidden.
- Zeroshot owns execution of its arbitrary graphs. zplan owns the conversation, plan, application state, projections, verification, and merge policy. Reuse the engine; do not build a second execution engine.
- The UI renders the actual Zeroshot graph, including parallel branches, choices, loops, retries, and repair paths. A linear animation is not an acceptable substitute.
- Conversation and operation history is durable per project. Closing the UI, changing views, or starting a new architect session must not lose it.
- TUI and headless automation call the same Application Service and read the same projections. Neither may maintain a competing business-state implementation.

## Engineering boundaries

- Target-agnostic: production code contains no paths or behavior specific to this repository or another target project.
- Keep Textual at the edge. Commands, transitions, invariants, operation results, and durable history belong to the application core; rendering and input belong to the TUI.
- Divide code by responsibility and stable contracts, not by file-size targets. Do not split a coherent behavior merely to satisfy a line cap.
- Choose the smallest solution that preserves validation, error handling, security, accessibility, and existing behavior: no new code, reuse, standard library, platform capability, installed dependency, then minimal new code.
- `prototype/`, `upstream/`, `docs/history/` (private archive), and recorded receipts are preserved. Do not rewrite historical evidence.
- Never push, tag, publish, release, alter credentials, or access real provider auth unless the owner explicitly asks for that exact action.

## Development and tests

- Do not use `devtools/zeroshot/run.sh` for product development or release qualification. It is a legacy graph diagnostic only.
- Test behavior and external contracts, not private function names, source inventories, exact layout, or incidental wording.
- Mock only nondeterministic external boundaries such as provider, network, clock, and engine transport. Use real Git, filesystem, state transitions, and application services in integration tests.
- Every check runs in a documented, hermetic environment. A failure is never reclassified as pre-existing by assertion alone.
- A successful engine run is not synonymous with accepted, verified, or merged work. Report those states separately.
- Read `docs/DEVELOPMENT.md` for the active harness, test layers, tool policy, and Definition of Done.

## Tools

- Use `ast-grep`/`sg` for syntax-shaped searches and codemods; use text search for text-shaped questions. Always inspect a dry-run before applying a codemod.
- Ponytail is adopted as a minimal-solution rule, not as a mandatory plugin or another runtime layer.
- context-mode is allowed only in the outer interactive development session. It is forbidden inside zplan worker, reviewer, critic, verification, and release-evidence runtimes unless a later measured decision explicitly changes this boundary.
