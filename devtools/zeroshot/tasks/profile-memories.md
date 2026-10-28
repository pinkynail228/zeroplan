profile-memories — the packaged agent profile turns off Codex memories, so agents never carry context from earlier sessions or other projects (one zplan home serves every project; reviewers must judge only the diff and the criteria).

Data reach: terminal_planner/resources/agent_profile.toml (marker `# zplan-agent-profile: 1`, `[features]`), terminal_planner/agent_profile.py `EXPECTED` (~26) and `ensure` (a home holding another marker N is "replaced", previous file kept as .bak), tests/test_agent_profile.py (pins EXPECTED both ways), docs/AGENT_ENV_PLAN.md decision table (~65-79). The devtools home already runs with `memories = false` (dogfood evidence).

Write-set: the four files above, plus any other test that pins the marker number or the profile bytes.

Acceptance criteria:
- A1 `[features] memories = false` in the packaged profile and `"features.memories": False` in `EXPECTED`.
- A2 The marker becomes `# zplan-agent-profile: 2`, so `ensure` replaces an existing version-1 config (keeping it as .bak) on the next launch; a version-2 config is "current".
- A3 Tests: a version-1 config is replaced and the result contains `memories = false`; the existing both-direction EXPECTED test covers the new key. Each fails if the change is reverted.
- A4 docs/AGENT_ENV_PLAN.md table gains the memories row (why: one home across projects, reviewer independence).

Non-goals: other Codex keys, changing how CODEX_HOME is chosen, migration beyond the existing replace rule.

DoD: `python3.13 -m unittest tests.test_agent_profile tests.test_toolchain tests.test_terminal_planner` with TMPDIR short (see preamble), all green.
