s2c1-probe-cli — 0.5 item S2, the probe part of devtools/zeroshot/tasks/s2c-agent-usage.md (the parent; its Observed, R-4, R-5 and A-4 texts apply verbatim where cited). Lane L5 (docs/RELEASE_0.5_SCOPE.md Order). Slicing: critic swarm05 a/c (~/zs-pause/critic/swarm05.out): usage storage/display and the probe CLI are separable; the installed S2 journey (parent A-5) still needs s2a/s2b and stays with the parent's remaining part (s2c2 usage). Ownership: here R-4, R-5 (without its ORCHESTRATOR sentence), A-4 and the probe mutations of A-6; in s2c2: R-1..R-3, R-6, the R-5 ORCHESTRATOR sentence, A-1..A-3, A-5 and the usage mutations of A-6. DeepSeek worker, sol reviewers.

Base: the v0.4.0 tag. Record the base commit in the receipt. Re-check every line number on the base, and re-gate if a premise moved. The parent's single-task argument (critic s2-task: one installed run qualifies storage, formatter and probe) is kept: the probe is qualified in the parent A-5 run after s2c2; this slice ships the deterministic part only.

Write-set (exclusive): new `devtools/zeroshot/agent_probe.py`; new `devtools/zeroshot/probe/` (fixed native graph with one Codex agent node, runtime and input documents, workload `probe-v1`); new `devtools/test_agent_probe.py`. No edits to terminal_planner/*, catalog.py, docs, ORCHESTRATOR.md (its one-line rule from parent R-5 lands with s2c2 after the installed run), and no baseline file (parent A-5 records it).

Rules:
- R-4: parent R-4 in full.
- R-5: parent R-5 in full (`run`, `turn1`, `record`, `check`; exclusive home lock; snapshots before launch; exactly one new rollout validated by session_meta; manifest only after a successful native terminal result; rollout grammar; integer-only ratio; auth.json never opened), except the ORCHESTRATOR.md line.

Acceptance (deterministic fixtures, no real provider; tmp homes; a fake `zeroshot` that creates 0, 1 or 2 rollouts and can edit config.toml; synchronization with Events, never fixed sleeps):
- A-4: parent A-4 in full.
- A-6p Mutations (candidate-only; new module, excluded from base replay per parent A-6): let the probe pick the newest file; take config_sha256 after launch; publish the manifest before the terminal result; compare the ratio in floats; accept a bool total. Each killed by a named assertion.

Size: about 300-450 changed lines including tests. Above 600: report the measured overrun and rationale in the receipt; merge requires explicit critic disposition (ORCHESTRATOR step 1).

DoD: tests pass locally (`python3 -m unittest devtools.test_agent_probe` or the repo's devtools test runner); receipt with base commit, file list, mutation table. No real provider run; the installed qualification follows the S2 platform matrix (provider-free Linux + real-provider macOS, critic swarm05b, re-gated with s2a/s2b/s2c2).
