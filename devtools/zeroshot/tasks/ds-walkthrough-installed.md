ds-walkthrough-installed — installed mode for the PTY walkthrough (docs/RELEASE_0.4.md, release gate step 5). DeepSeek calibration, grade medium. Devtools only: change devtools/ux_walkthrough.py and add a test; no change to terminal_planner/, tests/ outside the new test file, install.py, docs.

Today devtools/ux_walkthrough.py always runs `python -m terminal_planner.cli` with `PYTHONPATH=ROOT` (ux_walkthrough.py:104-106), so it proves the checkout, never an installed candidate.

Add `--installed`: the zplan process runs the package installed in the `--python` interpreter, not the checkout.
- The child gets no PYTHONPATH (remove it from the inherited environment), runs with `-I` (isolated: no cwd/script dir on sys.path, no PYTHON* env, no user site) and cwd = the throwaway project (already so).
- Before the first frame, the script runs the same interpreter the same way (`-I`, same env) with a one-liner that prints `terminal_planner.__file__` and `terminal_planner.__version__`, writes both to `FRAMES_DIR/installed.txt` and prints them; it also prints `terminal_planner.cli.__file__` and the interpreter's `sysconfig.get_paths()['purelib']`/`platlib`. It refuses (exit nonzero, clear message, no frames) unless both resolved (realpath) files lie inside that interpreter's purelib/platlib: this rejects the checkout, symlinks into it, and editable/.pth installs of another tree; it also refuses when the import fails.
- One function builds the child (interpreter, flags, env, cwd) and both the probe and every PTY launch use it; the probe cannot differ from the launched zplan.
- Without `--installed` the behaviour and output stay exactly as today.
- The walkthrough's own expectations still import `terminal_planner.catalog` from ROOT; in installed mode, additionally print a warning line when the installed `__version__` differs from ROOT's `terminal_planner.__version__` (the release candidate and the checkout must be the same commit), without failing.
- Update the module docstring usage with the `--installed` line.

Tests (`devtools/test_ux_walkthrough_installed.py`, stdlib only, no pyte/Textual needed, run with `python3 -m unittest discover -s devtools -p 'test_ux*'`): test the pieces that do not need a PTY by factoring the child environment/argv building and the installed-package probe into small functions. Cover: the PTY launch argv/env/cwd equals the probe's (same builder; assert on what `open()` would exec, e.g. by patching `os.execvpe`/`pty.fork` or exposing the built tuple); installed mode env has no PYTHONPATH even when the parent has one, argv has `-I`; default mode env/argv unchanged (PYTHONPATH=ROOT, no `-I`); the probe against a real temporary venv (`venv.create(dir, with_pip=False)`) with a minimal fake `terminal_planner` package (`__init__.py` with `__version__`, `cli.py`) copied into its site-packages: accepted; the same venv with site-packages/terminal_planner as a symlink to ROOT/terminal_planner: refused; a `.pth` file pointing at a temp tree outside site-packages: refused (all with real `-I`, nonzero exit, message, no frames dir content); version mismatch (fake package `__version__` differs from ROOT) prints the warning and does not fail. Importing ux_walkthrough must not require pyte for these tests (move the pyte import inside the code that needs it, or guard it).

Acceptance criteria:
- W-1 New tests pass (name the interpreter); in a scratch copy, removing the PYTHONPATH drop and removing the inside-ROOT refusal each make a test fail.
- W-2 Default mode unchanged: `/tmp/zs-zplan/ux/venv/bin/python devtools/ux_walkthrough.py $TMPDIR/frames --python ~/.local/share/planning-kit/app/0.3.1/bin/python` still ends with `walkthrough OK` if that interpreter is available to you; if the sandbox refuses it, say so and the orchestrator runs it.
- W-3 Installed mode refusal and acceptance are covered by the venv tests above; also show one manual command: `--installed --python <temp venv with the symlink into ROOT>` exits nonzero with the message and no frames.
- W-4 Diff touches only devtools/ux_walkthrough.py and devtools/test_ux_walkthrough_installed.py.
- After the run the orchestrator smoke-runs `--installed` against the installed 0.3.1 app (same `__version__` as the checkout, so no warning; equal versions do not prove the same commit: release step 5 binds the candidate's identity from the receipt).

critic ds-walkthrough-task (session 01a14200): GO WITH CHANGES (4, applied).
critic ds-walk-merge (session 01a14200): MERGE (P3 open: a refusal on a reused FRAMES_DIR leaves the old INDEX.md, ux_walkthrough.py:296).
