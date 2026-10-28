C0a — review bar of zplan's shipped graphs (dogfood blockers D1, D2, D3, D6; docs/RELEASE_0.5_SCOPE.md "Dogfood blockers", plan docs/CHAT_RELEASE_JTBD.md slice C0).

Goal: plans and milestone tasks that zplan runs converge instead of looping on new nits. Today the shipped code reviewer rejects on any finding and the worker must "repair every finding" (terminal_planner/milestone.py:417-432), the task loop is fixed at 4 iterations (milestone.py:21) and ignores the profile's `limits.task_rounds`, the plan critic rejects "when incomplete" with no bar (terminal_planner/engine.py:666-676, V2_VERIFIER_TAIL), and this repository's profile runs the plan critic at xhigh (zplan.process.json).

Write-set: terminal_planner/milestone.py, terminal_planner/engine.py (prompt constants and the milestone loop bound only), zplan.process.json, docs/REFERENCE.md (limits row), docs/USER_FLOW.md if it quotes a changed prompt, their tests. Nothing in tui/, authority.py, runs.py, process.py validation.

Acceptance criteria:
- A1 (D1) acceptance_review and code_review instructions: reject only when a check or the title of input.task fails, or the change breaks existing behaviour, on a realistic path; anything else goes into diagnostic.message as a non-blocking note marked `note:`. The worker instruction repairs the findings of a rejected review and may leave `note:` items.
- A2 (D2) the milestone review loop's maxIterations = 1 + the frozen `limits.task_rounds` of the plan revision's process profile (default 2 -> 3 iterations); if the milestone has no frozen profile (older revisions), the current 4 stays. docs/REFERENCE.md says task_rounds bounds the milestone repair rounds.
- A3 (D3) plan critic (v2 tail and v1 verifier text): every rejecting finding names what it protects - the task goal, a stated requirement, an owner rule or a repository invariant; a finding with none of these is a non-blocking `note:`; the critic adds no scope that the task does not ask for.
- A4 (D6) zplan.process.json: role critic effort high. The profile still loads (`zplan profile` / process.py load) without asking to re-accept anything new beyond what a changed profile already shows.
- A5 Revisions already prepared, submitted or approved keep their stored graph and runtime bytes; only newly built graphs carry the new text.
- A6 Each criterion has a test; the prompt tests assert the new rule sentences, not whole prompt snapshots.

Non-goals (reviewers must not require): new reviewer roles, a severity taxonomy, a findings parser, changes to the devtools preamble, changes to the native template, migration of stored revisions, any UI change.

DoD: `python3.13 -m unittest tests.test_milestone tests.test_plan_gate tests.test_terminal_planner tests.test_process tests.test_task_gate tests.test_toolchain tests.test_reference` with TMPDIR short (see preamble), all green.
