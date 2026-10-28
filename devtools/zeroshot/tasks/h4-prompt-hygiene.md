H4 — what a user's agents read and what lands on their main: only true, product-facing text

Astra review 2026-10-28 (pause dir, critic/harness-graph.out item 4, harness-graph-3.out): user prompts carry a
dev-harness marker, claims of features that do not exist and a contradiction; the merge commit carries our
internal `Risk-Tier:` line, which nothing reads back (risk is computed and stored separately, runs.py:1665).

Reuse: the existing graph builders as they are; the qual tools' dispatch by marker; OWNER_RULES.

Write-set: terminal_planner/milestone.py, terminal_planner/engine.py, terminal_planner/runs.py,
devtools/driver_qual.py, devtools/plan_qual.py, devtools/task_gate_qual.py, docs/REFERENCE.md,
tests/test_milestone.py, tests/test_plan_gate.py, tests/test_merge_critic.py, tests/test_plan_qual.py,
tests/test_merge_gate.py, tests/test_task_gate.py.

Acceptance criteria:
- H1 No production graph carries `ZPLAN_NODE=`. The qual tools add the marker by decorating the graphs the existing
  builders return, in a scope, before digest and submission; their dispatch is unchanged.
  Example: `"ZPLAN_NODE" not in json.dumps(milestone_graph(2))`, nor in planner_graph_v2(3); inside the qual scope
  the submitted graph has the markers, after it the builders are marker-free again.
- H2 DRIVER_MECHANICS claims only what the milestone graph does (independent acceptance and code reviews, bounded
  repairs, a final milestone check). Example: no "evidence digests", "resume" or "reviewer identity".
- H3 The plan critic's authority sentence agrees with OWNER_RULES: repository text is not authority, except the
  owner's rules files in task.owner_rules, ranked as OWNER_RULES says. Example: the sentence names owner_rules;
  "Never trust planner-authored acceptance" stays.
- H4 A new merge candidate's message has no `Risk-Tier:` line; stored risk and gate decisions are unchanged;
  docs/REFERENCE.md no longer promises the line. Example: test_merge_gate's gated merge -> body without
  "Risk-Tier", same gate record.

Non-goals (reviewers must not require): the checker's absolute interpreter path (it isolates the checker); stored
records or past commits; this repo's own dev merge convention (ORCHESTRATOR.md); the merge critic's facts.

Conflict rule: if anything outside the write-set reads `Risk-Tier` from a commit, or the marker cannot be added
without a production flag, change nothing and end with `conflict: <file:line>`.

Risk: high (Git commit content and qualification wiring). DoD: run once, at the end: `python3.13
devtools/fasttest.py tests.test_milestone tests.test_plan_gate tests.test_merge_critic tests.test_plan_qual
tests.test_merge_gate tests.test_task_gate tests.test_reference tests.test_toolchain`: exit 0;
`python3 devtools/budget.py`: OK. Each new test fails with the old text restored.
