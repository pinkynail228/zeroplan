# s2b2b-loop-precondition-repair — receipt

Repair of the `s2b2-profile-activation` candidate (critic `s2b2-exhausted` chain, session
`01a15946-07d3-7800-baa6-a514d25094bb`; task gate `s2b2-gate-fail` GO WITH CHANGES, applied, same session).
DeepSeek worker, sol reviewers. The result merges as `s2b2`.

## Base and brief

- **Base.** `20dc77f51cb852a9c9ddf4e5c83f14d179fb0eb5` (`WIP s2b2 at change_attempts_exhausted (round 10)`), the
  worktree branch `zs-s2b2b-loop-precondition-repair` from `zs-s2b2-profile-activation` at `20dc77f`, rebased on
  main `36cf419`. The run's own `git status --porcelain` was empty at start.
- **Brief sha256.** `eabf8b9d181e2c64d4fa87152577a2261362b4f68a1b21de9f9f83b82ea6cd8c` — sha256 over the UTF-8 bytes
  of this run's brief text (the `task` value of
  `/private/tmp/zs-zplan/s2b2b-loop-precondition-repair.input.json`, 8819 bytes; this node delivers the brief as
  graph input, not as a `devtools/zeroshot/tasks/*.md` file, so the text itself is what is hashed).

## Cause

The integration gate on `20dc77f` (2026-10-20; `~/zs-pause/int-s2b2-20dc77f-linux.log` and `-mac.log`, both Python
3.13) fails `tests.test_agent_activation.OwnerHomeAliasTests.test_r1_a_looping_owner_codex_home_does_not_break_a_launch`
at the line-505 precondition `assertRaises(RuntimeError)` around `(home/.codex).resolve()` on a self-loop symlink.
`Path.resolve()` (non-strict) raises `RuntimeError` on a loop up to Python 3.12 and returns a path on 3.13
(measured: 3.9.6 `RuntimeError`, 3.13.3 returns), so the test's precondition depended on the interpreter while
`pyproject.toml:9` supports `>=3.11`. The product guard (`os.path.realpath`, `setup._refuse_owner_home`) is not in
question.

## Change (test only)

`tests/test_agent_activation.py` (+35/−15; `test_r1_a_looping_owner_codex_home_does_not_break_a_launch` only).
No product file is touched.

- The real self-loop symlink stays: `os.symlink(".codex", self.root / "home" / ".codex")`.
- The interpreter-dependent precondition is replaced with a mandatory deterministic injection: `pathlib.Path.resolve`
  is patched to raise `RuntimeError` for the owner's `~/.codex` path alone and to delegate every other call to the
  saved original (`original_resolve = Path.resolve` captured before the patch), and the patch is held across all
  three acts (`setup.native_environment()`, `self.engine_env(project)`, `self.prepare(project)`).
- Every existing assertion of the test is kept, including the now-injected `with self.assertRaises(RuntimeError):
  owner.resolve()` block; only the docstring was updated (version independence, and the exact-path interpretation).

Stable anchor: `sha256(tests/test_agent_activation.py)` = `c5606631428b2203e944a61e1c01aaf3826c045130fe8c39d987247100011344`.

Size: measured +35/−15 changed test lines (task estimate ~15; the overrun is the required docstring — the
version-independence note and the interpretation record — not extra code).

## Checks

Interpreter used by the worker: **Python 3.9.6** (macOS arm64). `Path.resolve` raises `RuntimeError` on the
self-loop here too, so the 3.9 run is an extra diagnostic; it is not what makes the oracle version-independent.
The precondition no longer depends on the interpreter because the injected `Path.resolve` manufactures the
`RuntimeError` on every supported version, rather than reading the standard library's loop behaviour.

- DoD (worker, targeted): `PYTHONPATH=.:tests python3 -m unittest tests.test_agent_activation tests.test_toolchain
  tests.test_reference` → `Ran 86 tests in 88.244s`, `OK` (each run under a fresh `TMPDIR=/tmp/zs-agent-XXXXXX`).
- `git diff --stat 20dc77f` lists only `tests/test_agent_activation.py`; the receipt is the second write-set path.

## A-2 mutation result (scratch copy)

In a scratch copy (`mktemp -d /tmp/zs-agent-XXXXXX`, `copytree` of the tree ignoring `.git`, `.tools`,
`__pycache__`; never the shared worktree), `setup._refuse_owner_home` was mutated from
`own = Path(os.path.realpath(str(Path.home() / ".codex")))` to `own = (Path.home() / ".codex").resolve()`.

`TMPDIR=<scratch> PYTHONPATH=.:tests python3 -m unittest
tests.test_agent_activation.OwnerHomeAliasTests.test_r1_a_looping_owner_codex_home_does_not_break_a_launch` →
`FAILED (errors=1)`, an **ERROR whose traceback shows the injected `RuntimeError` raised from the alias guard**:

```
  File ".../repo/tests/test_agent_activation.py", line 527, in test_r1_a_looping_owner_codex_home_does_not_break_a_launch
    env = setup.native_environment()
  File ".../repo/terminal_planner/setup.py", line 340, in native_environment
    home = launch_home()
  File ".../repo/terminal_planner/setup.py", line 243, in launch_home
    _refuse_owner_home(home)
  File ".../repo/terminal_planner/setup.py", line 297, in _refuse_owner_home
    own = (Path.home() / ".codex").resolve()
  File ".../repo/tests/test_agent_activation.py", line 521, in resolve
    raise RuntimeError("symlink loop: %s" % path)
RuntimeError: symlink loop: $HOME/.codex (test temp home)
```

The traceback shows the injected `RuntimeError` raised at the alias guard's own resolution — a direct violation of
the test's "does not raise" claim — not an unrelated non-zero exit. The scratch copy was deleted afterwards.

## Interpretations (silence, ambiguity or contradiction)

1. **The injected raise is recognised by the exact `Path.home() / ".codex"` spelling** (recorded in the test
   docstring). That is the path an implicit resolution passes and the path the mutation resolves;
a resolved or prefix comparison would itself be the call under test.
2. **The injected `RuntimeError` carries a short message and `strict` is delegated positionally.** The task names
   no wording; only the exception type matters to the assertion under test.

## Scope, deferred and product input

- Write-set only: `tests/test_agent_activation.py` (that test) and this receipt. No `terminal_planner/**` change.
- Left to the orchestrator's merge gate: the s2b2 integration gate (Linux and macOS full suites, `export_check` on
  the committed HEAD), then the fresh s2b2 merge verdict (task DoD). Never run here.
- Product input for zplan (Zeroshot friction): none this visit — the shared workspace and the scratch-`TMPDIR`
  rule worked as described; no unclear contract or odd failure was hit.
