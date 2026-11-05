# u9f — one zplan never reports "Another zplan is updating the profile" about itself

Soak of v0.9.0-rc1, F6 (minor, once in 2 starts): with a single zplan running, the start showed "Another zplan is
updating the profile in …; try again. [code: setup.agent_home]", which hid the real "No Codex login" message.
`agent_profile.ensure` (terminal_planner/agent_profile.py:95-108) takes `fcntl.flock(LOCK_EX | LOCK_NB)` on a fresh
open of the lock file; two threads of the same process (the chat's preparation and the readiness check both reach
`ensure`) hold two open file descriptions, so the second thread's non-blocking lock fails as if another zplan held it.

Change: `ensure` serializes callers of one process with a module-level `threading.Lock` around the flock section, so
the second thread waits for the first and then finds the profile current; another process holding the flock still
gets today's refusal.

Write-set: terminal_planner/agent_profile.py, tests/test_agent_profile.py

Acceptance criteria:
- A1 Two threads, no false refusal. Example: two threads call `ensure(home)` at once on a fresh home -> both return
  (one "written", the other "current"), neither raises setup.agent_home.
- A2 Another process still refuses. Example: a child process holds the flock -> `ensure` raises setup.agent_home as
  today.

Non-goals (reviewers must not require): the profile contents, the login check, the message text, other locks.

Conflict rule: if a test outside the write-set pins the in-process refusal, change nothing in it and end with
`conflict: <file:line>`.

Risk: medium (concurrency in setup). DoD: `python3.13 devtools/fasttest.py tests.test_agent_profile tests.test_setup`:
exit 0.
