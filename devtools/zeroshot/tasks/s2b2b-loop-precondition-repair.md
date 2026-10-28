s2b2b-loop-precondition-repair — repair of the s2b2-profile-activation candidate (critic s2b2-exhausted chain, session 01a15946-07d3-7800-baa6-a514d25094bb). Task gate: critic s2b2-gate-fail GO WITH CHANGES (applied, same session). DeepSeek worker, sol reviewers.

Base: this run starts on the s2b2 candidate (worktree branch from zs-s2b2-profile-activation at 20dc77f, rebased on main 36cf419); the result merges as s2b2. Record the base and this brief's sha256 in the receipt.

Failure (integration gate on 20dc77f, 2026-10-20; ~/zs-pause/int-s2b2-20dc77f-linux.log and -mac.log, both Python 3.13): `tests.test_agent_activation.OwnerHomeAliasTests.test_r1_a_looping_owner_codex_home_does_not_break_a_launch` fails at tests/test_agent_activation.py:505: `assertRaises(RuntimeError)` around `(home/.codex).resolve()` on a self-loop symlink. The precondition depends on the interpreter: `Path.resolve()` (non-strict) raises `RuntimeError` on a loop up to Python 3.12 and returns a path on 3.13 (measured: 3.9.6 RuntimeError, 3.13.3 returns). The project supports Python >= 3.11 (pyproject.toml), the test hosts run 3.13. The product guard (`os.path.realpath`) is not in question.

Write-set (exclusive): tests/test_agent_activation.py, only the test above; the receipt devtools/zeroshot/tasks/s2b2b-loop-precondition-repair-receipt.md. No product file changes.

Rule:
- R-1 The test's R-1 claim stays: with `~/.codex` a self-loop symlink and no CODEX_HOME override, the launch returns the private home and does not raise. The precondition must hold on every supported interpreter (`>=3.11`, pyproject.toml:9; a worker 3.9 run is an extra diagnostic only). Replace the interpreter-dependent `assertRaises(RuntimeError)` precondition with a mandatory deterministic injection: keep the real self-loop symlink; patch `pathlib.Path.resolve` so it raises `RuntimeError` only for the owner's `~/.codex` path and delegates every other call to the saved original; hold the patch during all three acts of the test (`native_environment`, `engine_env`, `prepare`). Keep every existing assertion of the test and update its docstring.

Acceptance:
- A-1 The test passes under the worker's interpreter and the oracle is version-independent (the receipt names the interpreter used and the reason the precondition no longer depends on it).
- A-2 Mutation: in a scratch copy, the alias guard computes `own = (Path.home() / ".codex").resolve()` instead of `os.path.realpath`. The test must fail by a named assertion or by an ERROR whose traceback shows the injected `RuntimeError` raised from the alias guard (a direct violation of "does not raise"); an unrelated non-zero exit does not count. Report the result.

DoD:
- Worker (targeted): `PYTHONPATH=.:tests python3 -m unittest tests.test_agent_activation tests.test_toolchain tests.test_reference` passes.
- `git diff --stat <base>` lists only the write-set.
- Receipt: base, brief sha256, interpreter, the A-2 mutation result.
- Orchestrator, after acceptance: rerun the s2b2 integration gate (Linux and macOS full suites, export_check on the committed HEAD), then the fresh s2b2 merge verdict.

Size: ~15 changed test lines.
