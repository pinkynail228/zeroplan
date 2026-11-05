# v4b — a goal typed before the chat is ready is kept and sent once, to the project it was typed for

docs/PLAN_UX.md V4 (design dir v4-astra-design.md, point 2, task 6). Baseline: a goal typed before login or tools
is lost with no reply. `ZplanApp.send_chat` (tui/app.py) queues nothing: `ArchitectChat.send` (tui/chat.py:738)
refuses while the chat is not ready (tools missing, no login, preparing) and the line is gone. `refused_goal`
(app.py) is a different path (a planning request refused by readiness): do not add a second retry there. The
architect's per-project store (`ArchitectStore`, architect.py:509) lives outside the checkout under the data root,
keyed by the project's canonical path, and works before Git exists.

Change:
- When the chat cannot take a turn yet, Enter keeps the line as the project's one pending goal, stored beside that
  project's ArchitectStore ({id, text, project path, state}); the input clears and one line says "Goal saved for
  <project name>. It is sent once setup is done." A second Enter with the same text keeps one pending goal; a
  different text replaces it (the line says so).
- When the chat becomes ready, one handler sends the pending goal as an ordinary owner turn, once; it is marked
  sent only when the turn was accepted; a refused send keeps it pending. A reopen of the same project finds it.
- The goal belongs to its project: another project's chat never sends it; a folder change leaves it with the
  folder it was typed for.

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/chat.py, terminal_planner/architect.py,
tests/test_tui_chat.py, tests/test_architect.py, tests/test_tui_activity.py, tests/test_dead_ends.py,
tests/test_tui_chat_input.py, tests/test_agent_activation.py, tests/test_tui_origin_early.py, tests/test_tui.py (:539-547)

Acceptance criteria:
- A1 Kept. Example: no Codex login, the owner types "Add a changelog" + Enter twice -> one pending goal, the input
  empty, the saved line shown once.
- A2 Sent once. Example: login completes, the chat becomes ready -> exactly one owner turn "Add a changelog"; a
  further readiness refresh sends nothing.
- A3 Its own project. Example: a pending goal for project A; the app opens project B -> B's chat sends nothing; A's
  reopened chat sends it.
- A4 Survives reopen. Example: quit with a pending goal, reopen the same project after login -> it is sent once.

Non-goals (reviewers must not require): the onboarding cards, origin, /plan, the draft flow, wording.

Conflict rule: a test outside the write-set pinning that a refused send keeps nothing: change nothing, end with
`conflict: <file:line>`.

Risk: medium (owner input). DoD: `python3.13 devtools/fasttest.py tests.test_tui_chat tests.test_architect
tests.test_tui_activity tests.test_new_session tests.test_toolchain`: exit 0.
