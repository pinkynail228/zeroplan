D1 — our dev runs go through zplan's own milestone graph, preflight (foreman) node first (owner 2026-10-25:
the foreman stage in the worker bundle = the zplan preset, and dogfood). Today run.sh starts the upstream
`--template software-change`, which has no preflight; the product builds a graph with one
(milestone.py:430 `preflight`, :553) through runs.py `build_documents` (:431).

Reuse: runs.py `build_documents`, `checker_command`; milestone.py `build_baseline` (:76, the proposal shape),
`milestone_runtime`, `validate_baseline`; the brief fields of A2a (write_set, criteria with examples,
non_goals, risk, dod); run.sh (lock, worktree, homes, adapter checks: unchanged).

Write-set: devtools/zeroshot/milestone_run.py (new), devtools/zeroshot/run.sh,
tests/test_dev_milestone_run.py (new).

Acceptance criteria:
- C1 Brief -> proposal: `milestone_run.py documents TASK_FILE OUT_DIR --runtime RUNTIME_JSON` parses our
  task file format (the first line = title; `Write-set:` files; `Acceptance criteria:` items `- Cn text ...
  Example: ...`; `Non-goals`; `Risk:`; `DoD:`) into a one-milestone, one-task proposal, and writes
  graph.json, runtime.json, input.json, baseline.json from `build_documents`. Roles come from RUNTIME_JSON's
  nodes (worker, acceptance, code), so the Claude lane keeps Sonnet + Opus. Example: tasks/a8a-project-state.md
  -> one task with 4 criteria, write_set of 4 files, risk "medium", dod the fasttest command.
- C2 A file that misses a field -> exit 2 naming it, nothing written. Example: no `Write-set:` -> "write-set".
- C3 run.sh: `ZS_GRAPH=zplan` builds the documents into `$work.docs/` and starts `zeroshot run --graph
  ... --input ... --runtime-config ...` with the same title, submission key and `--validate-only` handling;
  without it run.sh is byte-identical in behaviour. Example: `ZS_GRAPH=zplan run.sh x tasks/a8a-project-state.md
  --validate-only` prints `{"valid":true}` with the pinned engine (toolchain.py:48, 10.16.0; if only an older
  engine is on PATH, say so in the report instead of failing).
- C4 Whatever the native run needs in the worktree before the graph starts (the files runs.py prepares
  before dispatch, e.g. `.zplan/` documents) is written by milestone_run.py; name each in the report with the
  runs.py line it mirrors.

Non-goals (reviewers must not require): making ZS_GRAPH=zplan the default (the orchestrator does it after one
real run); the authority/plan store; several tasks per milestone; the DeepSeek runtime.

Conflict rule: if `build_documents` cannot run without an authority or a plan store, answer `conflict:` with
the path:line before any edit.

Risk: medium (dev tooling only). DoD: `python3.13 devtools/fasttest.py tests.test_dev_milestone_run
tests.test_toolchain` exit 0; quote the `fasttest:` lines.
