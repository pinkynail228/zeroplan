# p09a — the shipped method and the plan critic aim for the elegant decision; the critic is a dialogue, not a gate

Owner 2026-10-29: aim for the elegant decision (reuse over reinvention, the smallest design that serves the user; no
over-testing, over-engineering or whack-a-mole); the critic is a second pair of eyes, not a gate.

Change:
- terminal_planner/resources/architect_method.md: one line in `## Plan` with the elegance aim above; the critic line
  in `## Merge` ("The independent critic is a safety net, not authority: ...") becomes the dialogue stance: a second
  pair of eyes, not authority; its triggers and "never on routine merges" stay; form your own position first; take
  what makes the solution better, say why you reject the rest; agree when convinced, never to be agreeable. Shorten
  other lines to stay within 4600 bytes.
- terminal_planner/engine.py: one sentence after `PLAN_CRITIC_BAR` in `V2_VERIFIER_TAIL` only (v1 is frozen; the
  merge critic judges safety): prefer the smallest plan that serves the goal and reuses what exists; a missing check,
  test or robustness step without a concrete failure scenario, or something that could be deleted or simplified, is a
  `note:`, not a rejection.

Write-set: terminal_planner/resources/architect_method.md, terminal_planner/engine.py, tests/test_architect.py,
tests/test_plan_gate.py, tests/test_task_gate.py (only `v2_graph_2`/`v2_graph_3` and their comment)

Acceptance criteria:
- A1 The architect's first prompt carries the elegance aim. Example: `build_preamble(SNAPSHOT)` -> its `## Plan`
  section has a line with "reuse over reinvention", "smallest design" and "whack-a-mole".
- A2 The merge critic line is the dialogue stance. Example: `architect.method()` -> `## Merge` contains "not
  authority", "Form your own position first", "say why you reject the rest" and "never to be agreeable", and no
  longer "safety net".
- A3 The plan critic notes, not rejects, an unasked extra. Example: `engine.V2_VERIFIER_TAIL` and the v2 `critic`
  node's instructions in `planner_graph_v2(3)` contain the new sentence after `PLAN_CRITIC_BAR`;
  `engine.V1_VERIFIER_TAIL` and `engine.MERGE_CRITIC_TAIL` are unchanged; test_task_gate refreshes only the two v2
  graph goldens and adds the reason to their comment, as earlier refreshes did.
- A4 The method stays a short generic preset. Example: the file is at most 4600 bytes; tests.test_architect's
  existing method tests pass unchanged apart from new assertions.

Non-goals (reviewers must not require): the v1 verifier, the merge critic prompt, the edit critic text, docs,
the architect's tools or Role, the preset version.

Conflict rule: if a test outside the write-set pins a sentence this brief changes, change nothing in it and end with
`conflict: <file:line>`.

Risk: medium (plan critic prompt). DoD: once at the end, in the foreground: `python3.13 devtools/fasttest.py
tests.test_architect tests.test_plan_gate tests.test_milestone tests.test_docs tests.test_toolchain`: exit 0;
budget.py: OK. New A1-A3 assertions fail on today's code.
