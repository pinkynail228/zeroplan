A7a — the merge gate: a pinned integrated candidate, the project checks on it, fast-forward (RELEASE_0.6.0_PLAN
lane T step 5; ARCHITECT_DESIGN.md section 10 items 1, 2 and the landing of 4; rows :243, :246). Design reviewed:
~/zs-pause/critic/a7a-design.out.

Why: `MilestoneRuns.merge` (runs.py:1269) merges the result with nothing tested; `gates.merge: required` is refused
as unbuilt (process.py:67, :890). The checks must run on the exact commit that lands.

Reuse: `checks.qualify` (checks.py:163), `process.risk_of` (process.py:500), `Delivery.guard("merge")`
(delivery.py:571, its `Status.resolved`), `configured_identity`, `git_call`/`run_git`.

Write-set: terminal_planner/runs.py, terminal_planner/delivery.py, terminal_planner/process.py,
terminal_planner/catalog.py, docs/REFERENCE.md (regenerate: `python -m terminal_planner.catalog --write
docs/REFERENCE.md`), docs/PROCESS_PROFILE.md, tests/test_merge_gate.py (new), tests/test_process.py, tests/test_runs.py.

Acceptance criteria:
- C1 Refuse: every merge refuses (`milestone.merge_refused`, nothing written) while `MERGE_HEAD` exists. Example:
  `.git/MERGE_HEAD` present -> refusal naming `git merge --abort` (test_runs.py:1333 expects that text now).
- C2 Candidate: with `gates.merge: required`, take once the destination ref, head SHA, result SHA and
  `resolved.digest`; use literal SHAs only. `git merge-tree --write-tree --name-only -z <head> <result>`: exit 0 ->
  `commit-tree -p <head> -p <result>` with the owner's identity and today's message plus `Risk-Tier: <tier>` and
  `Checks: <checks_digest> passed`; exit 1 with paths -> `delivery="conflict"`, those files, `aborted=True` (tree
  untouched); exit 1 without paths or another exit -> `milestone.merge_refused`. Example: a disjoint change on main
  -> a candidate with parents [head, result].
- C3 Checks: `qualify(project, candidate, tree, config["checks"], <data_root>/checkouts)`. Saved before landing,
  as an optional validated field (old stores load unchanged): `r["gate"] = {"destination", "head", "result",
  "candidate", "tree", "config_digest", "checks" (the frozen list), "evidence", "risk"}`; risk = `risk_of` over the
  NUL-separated `git diff --name-only -z <head> <candidate>` when the config has `risk`, else tier `high`. Empty
  checks -> `merge.no_checks`; a failed check -> `merge.checks_failed` naming it; a checkout refusal -> the same
  family naming the refusal. None moves HEAD. Example: check `["false"]` -> refused, HEAD unchanged, gate kept.
- C4 Land: recheck symbolic HEAD, head SHA, clean status, no `MERGE_HEAD`, live config digest; any change ->
  refused (a later merge builds a new candidate). Then `git merge --ff-only --no-squash --no-autostash
  <candidate>`; exit 0 and HEAD == candidate and clean -> `integrated` with commit = candidate. Example: HEAD moved
  during the checks -> refused, nothing merged.
- C5 Off: with `gates.merge: off` or no profile the merge is today's apart from C1. Example: existing merge tests
  pass; `process.unbuilt` for merge is gone from code and docs.

Non-goals (reviewers must not require): critic agent and triggers, cleanup of worktree/branch/lock, zplan.process.json
to /2 (A7b); integration stays result ancestry (`refresh`), the gate record says what was tested; automatic merges
(A5t); merge queue (A9); progress while checks run.

Risk: high. DoD: `python3.13 devtools/fasttest.py tests.test_merge_gate tests.test_process tests.test_runs
tests.test_reference tests.test_toolchain` exit 0; quote the `fasttest:` lines.
