A1b — preset risk rules and critic triggers (RELEASE_0.6.0_PLAN lane T step 2; ARCHITECT_DESIGN.md 10.3).

Why: the gatekeeper (A7) classifies a candidate's risk tier from its changed paths and calls a critic on named
triggers. A1b adds that as data plus one pure classifier; nothing calls it yet. Generic defaults live in the preset;
a project's own paths come from its `zplan.process.json`.

Reuse: the `autonomy` pattern in terminal_planner/process.py (a /2-only top key: `validate_profile`, `resolve`,
`complete`, the show line with `NEXT_STAGES`); `PurePosixPath.full_match` for patterns. Edit `zplan.default/2` in
place (no /3): nothing consumes /2 yet and no project file names it. `/1` stays byte-identical.

Write-set: terminal_planner/process.py, tests/test_process.py.

Data (`risk`, only in /2): `{"rules": [{"paths": [...], "tier": "low|medium|high"}], "triggers": [{"name", "paths":
[...]}]}`. Rules 1-32, triggers 1-16, 0-32 patterns each (rules need >= 1); a pattern is a relative POSIX glob, no
`..`, not absolute, <= 256 chars; trigger names match `NAME` and are unique. Preset defaults: low = `**/*.md`,
`docs/**`; high = installer/toolchain/packaging/CI manifests (`**/install*`, `pyproject.toml`, `setup.py`,
`package.json`, `Cargo.toml`, `**/*.lock`, `Dockerfile`, `.github/**`) and secrets (`**/.env*`, `**/*secret*`,
`**/*credential*`, `**/*.pem`, `**/*.key`). Triggers: `secrets`, `installer`, `toolchain`, `packaging` with matching
patterns; `data_loss`, `process_kill`, `disagreement` with no patterns (raised by name later, in A7).

Acceptance criteria:
- C1 Resolve: `risk.rules` and `risk.triggers` each come from the file when present (whole list replaced), else the
  preset; sources `risk.rules`, `risk.triggers`. Example: a /2 file with only `risk.rules` -> preset triggers,
  `sources["risk.triggers"] == "preset"`.
- C2 Validate: a bad tier, an absolute or `..` pattern, a duplicate trigger name, an unknown key, or `risk` under /1
  -> `Blocked` family `process.invalid` naming the key (e.g. `risk.rules[0].tier`); `risk` under /1 names the /2
  preset as the fix, as `autonomy` does.
- C3 Classify: `risk_of(config, paths)` -> `{"tier", "triggers": [names, sorted], "unmatched": [paths]}`. Per path the
  highest matching tier; an unmatched path counts `medium`; the result is the highest; an empty list -> `high`.
  Example: `["README.md"]` -> low; `["README.md", "src/a.py"]` -> medium, unmatched `["src/a.py"]`;
  `["app/.env.local"]` -> high, triggers `["secrets"]`.
- C4 Compatibility: the /1 config and digest are unchanged (the existing 7b40c07 capture test still passes); a /2
  snapshot must carry `risk` in full (`complete`); `describe` (`zplan profile`) shows one line `риск: правил N · триггеров M`
  with the `risk.rules` source marker and `NEXT_STAGES`.

Non-goals (reviewers must not require): calling `risk_of` from merge or the gatekeeper (A7); moving
zplan.process.json to /2 (A7); a migration for /2 snapshots written before this change; regex patterns.

Risk: medium. DoD: `python3.13 devtools/fasttest.py tests.test_process tests.test_terminal_planner` exit 0; quote
the `fasttest:` lines.
