ds-walk-stale-index — a reused FRAMES_DIR must not keep a previous run's INDEX.md (critic ds-walk-merge P3, STATE DeepSeek line). DeepSeek, grade easy, runs in parallel with tui-quit-race. Devtools only: change devtools/ux_walkthrough.py and devtools/test_ux_walkthrough_installed.py; nothing else.

Today `Walk.__init__` (devtools/ux_walkthrough.py:165-172) removes the old numbered frames `[0-9][0-9]-*.txt`, and `probe_installed` (:136) removes `installed.txt`, but a previous `INDEX.md` stays. A refused installed run (`finish(ok, index=False)`, :293-296) writes no new index, so the directory still shows the old run's INDEX.md, possibly with a passing result, next to an empty frame set. The same stale index survives a run that dies before `finish` writes it.

Required:
- At the start of a run (before the probe and before the first frame) the frame directory holds none of the previous run's outputs: numbered frames, `installed.txt` and `INDEX.md` are removed. Do it in one place (the `Walk` constructor or one helper it calls), not scattered.
- Other files in FRAMES_DIR that the walkthrough does not write are left alone.
- Default and `--installed` behaviour and output are otherwise unchanged.

Tests (add to devtools/test_ux_walkthrough_installed.py, stdlib only, no pyte/Textual): a FRAMES_DIR prepared with an old `INDEX.md` (content "walkthrough OK"), an old `01-x.txt`, an old `installed.txt` and an unrelated `notes.txt`; a refused installed run (reuse the existing refusal fixture: symlinked or `.pth` venv) leaves no `INDEX.md`, no numbered frame, no `installed.txt`, and `notes.txt` intact. Plus a unit check that constructing the walk alone clears the three kinds and keeps `notes.txt`.

Acceptance criteria:
- S-1 `python3 -m unittest discover -s devtools -p 'test_ux*'` passes (name the interpreter, report counts); the existing tests are unchanged and pass.
- S-2 In a scratch copy, removing the new INDEX.md cleanup makes the new test fail on its assertion; show it.
- S-3 Diff touches only the two files above.

Note: the refusal test must call the real Walk.__init__ (the existing MainTest.run_main patches it out and would not check the cleanup); the existing .pth fixture with a minimal package without Textual fits.

critic ds-walk-stale-index (session 01a143f0-a296-72e1-8c86-476d2d717521): GO (1 note, applied).
