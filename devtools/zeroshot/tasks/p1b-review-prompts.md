# p1b — reviewers judge evidence instead of rerunning checks; a test only for uncovered behaviour; method lines

Owner 2026-10-30 test policy: the final check runs the required checks once; reviewers run none. Today the shipped
acceptance review says "Gather fresh evidence yourself (run the checks); do not trust workerReport."
(terminal_planner/milestone.py, `acceptance` verifier), and VERIFY_RULE (milestone.py:35) makes every behaviour
change get a test even when existing tests cover it. The shipped method still says "Tests over 1.5x product lines:
over-testing." and describes the merge critic as something the architect calls ("only for its triggers ... and to
overrule a rejection citing a violated criterion"), while the merge gate raises it and only the owner overrules it.

Change:
- acceptance prompt: judge the diff, the tests and the worker's reported results; run no checks (the final check
  runs them); do not accept a worker claim without evidence in the diff or tests.
- VERIFY_RULE: a behaviour change that existing tests do not cover gets a relevant test (extend an existing test
  first); a test the task asks for is written; docs, copy or config alone get no new test.
- architect_method.md: delete the 1.5x sentence; the critic line says the merge gate raises the critic on its
  triggers, a critic block stops the merge and only the owner can override it.

Write-set: terminal_planner/milestone.py, terminal_planner/resources/architect_method.md, tests/test_milestone.py,
tests/test_architect.py

Acceptance criteria:
- A1 Acceptance runs no checks. Example: `milestone_graph(2)` node `acceptance_review` instructions contain "run no
  checks" and not "run the checks"; `code_review` is unchanged.
- A2 VERIFY_RULE asks for coverage of a gap. Example: it contains "existing tests do not cover" and "extend an
  existing test first", and still "docs, copy or config files alone gets no new test"; worker and both repair nodes
  carry it.
- A3 The method has no line budget and a true critic line. Example: architect_method.md has no "1.5x"; its Merge
  section names the merge gate raising the critic and the owner's override; the file stays within 4600 bytes and
  tests.test_architect passes.

Non-goals (reviewers must not require): reviewer timeouts, final_verify texts, the incomplete rerun, the planner and
plan critic prompts, the preset or graph structure, docs.

Conflict rule: if a test outside the write-set pins a changed sentence, change nothing in it and end with
`conflict: <file:line>`.

Risk: medium (shipped prompts). DoD: `python3.13 devtools/fasttest.py tests.test_milestone tests.test_architect
tests.test_install tests.test_runs`: exit 0.
