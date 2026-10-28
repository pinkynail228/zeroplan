u3b-chat-fix — continue u3b-chat after its run ended `change_attempts_exhausted` (run 01a146e4, 10 rounds; the last round of both reviewers rejected only on the two points below). Runs on the existing worktree /tmp/zs-zplan/u3b-chat (branch zs-u3b-chat). The worktree HEAD is the WIP commit of that run's final state, its parent is main 64e76e8. The task devtools/zeroshot/tasks/u3b-chat.md, with all its rules and ACs C-1..C-n, still applies unchanged; read it first. Reviewers review the whole diff 64e76e8..HEAD. DeepSeek worker, sol xhigh reviewers.

Open findings of the last round:
1. tui/app.py ~524-526 (code review): on 80x24, a long but valid CODEX_HOME in the chat header fills the whole chat block and hides the reply. Bound the header height, e.g. by eliding the path in the middle and keeping it to one line; the full path stays reachable (help / details). The reply and the input must stay visible.
2. tests/test_tui_chat.py ~1119 (both reviewers): the usage assertion "ходов 1" fails reproducibly when a valid, longer TMPDIR makes the header wrap. Make the assertion wrap-independent while still checking that the counters are visible and have the right values. After fix 1 the header is bounded, so add a test at 80x24 with a long CODEX_HOME: the reply line and the input are visible.

Acceptance criteria:
- F-1 Both findings fixed; the new 80x24 long-path test fails on the WIP HEAD (say how you checked).
- F-2 The targeted TUI and architect modules are green with a long TMPDIR, e.g. `TMPDIR=/tmp/zs-long-$(python3 -c 'print("x"*80)')`, and with the default TMPDIR. Create the long TMPDIR before running tests. In the test process, assert that `Path(tempfile.gettempdir()).resolve() == Path(os.environ["TMPDIR"]).resolve()`; a silent fallback to another directory must fail qualification.
- F-3 No other behaviour change; all C-* tests of u3b-chat stay green.

critic u3b-chat (session 01a145cb-a563-7da0-a718-05a4e2bb9662): CHANGE -> applied (F-2 TMPDIR fallback check) -> GO (confirmed in session on 48c14be); classification: attempt exhaustion with converging findings, not a worker failure; stays on DeepSeek.
