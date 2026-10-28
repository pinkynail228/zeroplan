R1 — the architect's replies are short, readable markdown that end with the next step

docs/RELEASE_0.6.3_PLAN.md V5. Newcomer check 2026-10-26, defect 4: after a start the architect wrote «Запрос на
запуск M1 принят… Начало выполнения пока не подтверждено.» (stilted, says nothing the owner can act on). The chat
will render architect replies as markdown (V2, later slice). The shipped method is
terminal_planner/resources/architect_method.md (4340 bytes; tests/test_architect.py caps it at 4400 in three asserts).

Write-set: terminal_planner/resources/architect_method.md, tests/test_architect.py

Acceptance criteria:
- C1 The method's Role section holds one reply-style rule (one line, at most 300 bytes): replies are short
  markdown in the owner's language (a list or a heading only when it helps, code only in fences); each reply ends
  with what happens next (the action taken and when the owner hears back) or the one question only the owner can
  answer; an action is named by its real state (requested, started, done or refused) and a requested one says when
  the owner hears back, never a hedge like "accepted, start not yet confirmed". Example: after zplan_start returns
  queued the reply is «Запросил запуск M1; напишу, когда он начнётся.»; the rule line contains `markdown`,
  `ends with` and `requested`. Lab state: dialog (devtools/ui-lab/chat.py).
- C2 The method stays within 4600 bytes (the three 4400 asserts become 4600) and every needle the existing tests pin
  is kept. Example: `len(architect.method().encode())` <= 4600; tests a11, rs6, p3a, c1a pass unchanged otherwise.
- C3 A test pins C1 by its key phrases on the whitespace-normalized Role section, like p3a. Example: the test
  fails when the rule line is removed from the file.

Non-goals (reviewers must not require): TUI rendering of markdown; architect.py prompts or tool rules; other
method sections; a project's own zplan.architect.md; translations of the method.

Risk: low (product prose: the shipped method text). DoD: `python3.13 devtools/fasttest.py` tests.test_architect,
tests.test_toolchain: exit 0.
