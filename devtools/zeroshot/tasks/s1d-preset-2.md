s1d-preset-2 — 0.5 item S1d (docs/RELEASE_0.5_SCOPE.md S1d row): ship preset `zplan.default/2`, with task and merge gates required, and a migration the owner accepts explicitly. `/1` is unchanged. Design: docs/PROCESS_PROFILE.md "Profile" (preset frozen) and "Bootstrap and profile states". DeepSeek worker, sol reviewers. Existing projects move to /2 only through explicit migration acceptance. Fresh projects follow the existing bootstrap contract: later stores and uses the displayed /2 snapshot without writing the project file.

Base: main with s1a1, s1b, s1c1 and s1c2 merged. Record the base commit in the receipt. The audit is on main 74f1a3b: re-check every line number on the base, and re-gate if a premise moved.

Audit (74f1a3b):
- `PRESET="zplan.default/1"` process.py:29; `PRESETS` :58-66 (plan required, task/merge off; the comment at :56-57 forbids editing `/1`).
- Validation :148-151 (preset must be in PRESETS; the hint names only PRESET). `resolve` :304. `SOURCE_NAMES["preset"]` :52 hard-codes PRESET.
- Acceptance state: `read_record` :415, `make_record` :435, `Profile.status` :532, `accept` :585 (accepting→accepted), `defer` :629. There is no migration flow.
- No test pins `/1` bytes. Indirect coverage: tests/test_process.py:155-157, :373, :1032.

Read: process.py; tui/app.py and cli.py bootstrap/profile screens; catalog.py; docs/PROCESS_PROFILE.md; tests/test_process.py (ResolverTests :225, StateTests :338, BootstrapPlainTests :921, GateTuiTests :1218).

Rules:
- R-1 Freeze `/1`. Add a golden test that pins the normalized `/1` preset and the resolved-config digest for a fixed profile. It must pass on the base and after this task.
- R-2 /2 differs from /1 only in preset identity and gates.task/gates.merge. Keep the legacy resolver fallback at /1, including existing files without preset and saved snapshots. Use /2 explicitly only for new proposals. Keep literal, independent PRESETS entries. Existing implicit-/1 files may migrate only by explicit acceptance.
- R-3 Migration. Migration is offered for accepted files resolving to /1, including files without preset. Their resolution and digest remain unchanged until explicit acceptance. Profile screens (TUI and plain) show a one-time offer: "доступен пресет /2: проверки задач и слияния", listing the exact differences, with keys accept / later.
  - Migration acceptance rechecks the exact file/config shown; intervening changes refuse without mutation and require a fresh offer. Existing explicit gates remain authoritative, including values written by the old bootstrap. Test label-only migration when explicit gates mask both changes.
  - Accept replaces the existing preset value with "zplan.default/2", or inserts that key when absent, preserving all other keys and formatting where possible; write atomically and say to commit it. Then the existing accepted-file flow applies: a changed config invalidates open gates.
  - Later is remembered per config digest, outside the checkout. No re-offer until the resolved config digest changes; formatting-only edits do not trigger it.
- R-4 Explicit gate keys win. A project file with explicit `gates` values keeps them under either preset (existing precedence). The migration screen shows when `/2` would change nothing effective; then it offers only the label change.
- R-5 Unknown presets still refuse, with a hint that names both known presets.

Acceptance (unit tests):
- A-1 `/1` golden (R-1), on base and candidate.
- A-2 /2 differs from /1 only in preset identity and gates.task/gates.merge. Test unchanged legacy resolution/digest with omitted preset, preserved later snapshots, and /2 proposals through both accept and later bootstrap paths.
- A-3 An accepted `/1` project: resolution and digest are unchanged with no action. Accept → file preset is `/2` and other bytes are preserved for a canonical file. Later → no re-offer until the resolved config digest changes; formatting-only edits do not trigger it. Test migration with omitted preset, stale acceptance refusal without mutation, and formatting-only edits after later.
- A-4 Explicit gates win (R-4) under both presets.
- A-5 The migration offer appears in TUI and plain with the same text. No network.
- A-6 Base failure: a new-project proposal expecting `/2` fails on base. Report named failures and skips separately. Compatibility assertions pass on base. Behavioral regressions must reach a named assertion through an existing production entry point using base-supported fixtures; import/missing-symbol/setup failures and skips do not count. Map candidate-only invariants to killed mutations. Recheck the selected regression on the actual prerequisite base.

Size: about 300-500 changed lines including tests; above 500, a mandatory re-gate point, never a reason to cut acceptance.

DoD:
- Unit tests pass.
- PROCESS_PROFILE.md and USER_FLOW.md updated (`/2` shipped); REFERENCE.md regenerated.
- Receipt.
