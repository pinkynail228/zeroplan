# Project instructions

`zplan`: terminal client over the native Zeroshot engine, built through Zeroshot itself.

- Orchestrator session: STATE.md, then devtools/zeroshot/ORCHESTRATOR.md before any step.
- Inside a Zeroshot run: devtools/zeroshot/preamble.md and the task; do the work directly; never start another Zeroshot run.

Invariants:
- Target-agnostic: the target project comes from the working directory or an explicit selection; production code has no paths or logic specific to one target project.
- The engine owns planning and lifecycle state; the terminal UI only calls it. Reuse the engine and its public contracts wherever they cover the requirement; read upstream source before choosing the native boundary.
- prototype/ (private archive) and upstream/ (unchanged checkout of https://github.com/the-open-engine/zeroshot) stay untouched; historical receipts and records are never edited or translated, only added.
- Unit tests run locally with deterministic fixtures; native and installed qualification runs on the Linux test host, not macOS.
- Rule files (AGENTS.md, devtools/zeroshot/ORCHESTRATOR.md, devtools/zeroshot/preamble.md) are locked; changes need the owner's unlock.

Live docs: README.md (the product page: only what a first-time reader needs), docs/ARCHITECTURE.md (code map, development), docs/USER_FLOW.md, docs/INSTALLATION.md, docs/TERMINAL_UX_BRIEF.md, the plan named in STATE.md.
