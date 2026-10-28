s1c2-status-truth — 0.5 item S1c (docs/RELEASE_0.5_SCOPE.md S1c row), child 2 of 2: derived truth. `zplan status` and a TUI panel show project truth from Authority, not from a chat. `--markdown` exports a STATE-like file. Design: docs/PROCESS_PROFILE.md R7 and "Stages on native graphs" (Truth). DeepSeek worker, sol reviewers.

Base: main with s1c1-merge-gate merged. Record the base commit in the receipt. The audit is on main 74f1a3b: re-check every line number on the base, and re-gate if a premise moved.

Audit (74f1a3b):
- `zplan status`: commands.py:22-29, cli.py:805-813. It prints the read-only home (`Delivery.home` delivery.py:423, `runs.overview` runs.py:1195) and has no gate truth.
- Status tests: tests/test_terminal_planner.py:1569 (read-only), :1645 (prints once), :565 (workspace recovery public contract).

Read: those locations; commands.py, cli.py, delivery.py, runs.py, planning.py, process.py (header_note :763), authority.py (gate records from s1a1/s1c1, qualification records from s1b), tui/app.py home panel; docs/USER_FLOW.md; the tests above.

Rules:
- R-1 Content. Derive status from read-only Authority/profile snapshots and local Git identities, without network or reconciliation writes. Reuse the enforcement validity predicates. Unavailable identity is shown as unknown, never accepted/current. Next action: preserve home's milestone focus order. Select only prerequisites enforced for the focused action: profile validity for new actions; plan-gate authorization before plan approval; task-gate authorization before a new attempt; qualification and merge-gate authorization before merge. Skip gates configured off and apply the enforcement predicates, including valid overrides. Do not require a fresh plan gate for an already-approved plan or a fresh task gate for an already-started attempt. Running/uncertain prerequisites select observation/reconciliation; rejection selects findings; native failure selects recovery; stale evidence selects rerun. Encode this table independently in fixtures. It shows:
  - the project and profile state (preset, gates on/off, "без проверки" for off gates);
  - the current plan revision and its plan-gate verdict or override;
  - per milestone: attempt state, task-gate state, qualification state, merge-gate state and overrides;
  - the next owner action, as exactly one catalog action with its key, derived by a single pure function shared with home;
  - owner notes (answers and override reasons, most recent 10).
- R-2 Compatibility. Existing `zplan status` output stays a prefix-compatible superset. The existing public contract tests (test_terminal_planner.py:565, :1569, :1645) pass unchanged.  With task/merge gates off and no task/qualification/merge records, preserve base output byte-for-byte; retain the existing required plan gate.
- R-3 `--markdown PATH` writes the same content as Markdown to PATH: atomic write, refusing to overwrite a path that is a directory or a symlink. It is a new flag in commands.py and documented. It never writes inside `.zplan/`. Resolve parent aliases before checking containment. Refuse destinations inside the project's .zplan directory or Authority directory, including through parent symlinks; refuse directory and symlink targets. Failed atomic replacement leaves an existing target unchanged.
- R-4 TUI. A panel or section on home shows the same derived lines, from the same function (not a second rendering of the data).
- R-5 Notes. Show the most recent 10 owner notes in Authority order; cap each displayed note at 500 characters with an explicit truncation marker, without changing stored text. Test empty, multiline, 500/501-character and legacy unbounded notes. Check tails are not included (only status words).

Acceptance (unit tests, deterministic fixtures):
- A-1 Golden: with task/merge gates off and no task/qualification/merge records, output equals base.
- A-2 Golden per state: one Authority fixture per state of each gate type → exact lines. The next action is correct for each state (table test). Cover off gates, valid overrides, and an approved plan with an exported attempt after HEAD changes: select the unmet merge prerequisite, not plan/task regating.
- A-3 Read-only: snapshot the Authority store and project dir before and after `status` and `status --markdown`; only the target file differs.
- A-4 Markdown: atomic write, refusals for a directory or symlink, content equal to the plain lines modulo Markdown markup.
- A-5 TUI and plain agree: the same function output appears in both (pilot test).
- A-6 Base failure: a regression on `zplan status` with a fixture holding a rejected merge gate, expecting the gate line, fails on base. Report named failures and skips separately. Compatibility assertions pass on base. Behavioral regressions must reach a named assertion through an existing production entry point using base-supported fixtures; import/missing-symbol/setup failures and skips do not count. Map candidate-only invariants to killed mutations. Recheck the selected regression on the actual prerequisite base. Recheck on the actual s1c1 base: the gate line may already exist there; then choose a regression on the next-action line.

Size: about 400-700 changed lines including tests; above 700, a mandatory re-gate point, never a reason to cut acceptance.

DoD:
- Unit tests pass.
- USER_FLOW.md and REFERENCE.md updated; PROCESS_PROFILE.md marks Truth as built.
- Receipt.
