F1 — a structured "flow" view of the active milestone attempt, for the Сейчас tab drawing (data half of the flow slice, docs/CHAT_RELEASE_JTBD.md "Visual target of Сейчас").

Goal: the next slice (F2) draws Сейчас as boxes: worker box → the two task reviewers side by side → delivery box, plus a log strip and a status line. Today the TUI only gets ready-made text lines (`Home.panel`, delivery.py:789-800 via `live.panel_lines`). F2 needs the same facts as plain data. This run adds that data and nothing visible.

Data reach: `Delivery.panel(r)` (terminal_planner/delivery.py:789) has the active record `r` (`r["live"]`, `r["created"]`, `r["status"]`) and the review bound `review_rounds(revision)`; `Home` (delivery.py:185-196) is built at delivery.py:497-500 with `panel=` and `journal=`. Live record keys and helpers: terminal_planner/live.py (`nodes` [node, execution] pairs, `task`, `workers`, `command` {at,text} or absent, `verdicts` list or absent, `last_event`, `heartbeat`, `detached`, `base`, `role`, `ROLES`, `seconds_between`, `parse`).

Write-set: terminal_planner/live.py (new pure function `flow` only), terminal_planner/delivery.py (`Home.flow` field and filling it next to `panel`), tests/test_live.py (it already builds Home panels through Delivery).

Acceptance criteria:
- A1 `live.flow(live, started, now, rounds=None)` returns a plain dict (JSON-serialisable, no Rich/Textual objects):
  - "task": live["task"] or None; "round": live["workers"] when task is set and workers ≥ 1 else None; "rounds": rounds.
  - "worker": {"state": "running" if a node with base `worker` is active, "done" if the task is set and a reviewer is active or has a verdict for this task and round, else "waiting"}.
  - "reviewers": exactly two entries in order acceptance_review, code_review: {"role": node, "name": ROLES word, "state": "running" when active, else "accepted"/"rejected"/other verdict string from the newest `verdicts` entry with this task, round and role, else "waiting"; "text": that entry's text or ""}.
  - "final": {"state": "running" if any active node's base is final_verify/final_reverify/scope_verify/repair, else "waiting"}; "select": True when any active node's base is select_init/select/select_verify/steward_apply/steward_decide.
  - "active": list of ROLES words of the active nodes, in order, without duplicates.
  - "elapsed": seconds since `started` (None when unknown); "silence": seconds since the later of last_event and command.at (None when unknown); "command": command text or None; "detached": live["detached"] stamp or None.
- A2 `Home.flow` holds `live.flow(...)` of the active attempt (same record and same `now()` reading as `panel`) and None when no attempt is active; the planner panel is untouched. Existing fields and lines are unchanged byte for byte.
- A3 Tests: a worker running in round 1; both reviewers running; acceptance rejected + code accepted for round 2 (from `verdicts`); verdicts of an older round or another task are ignored; a record without `command`/`verdicts` keys; final_verify active; Home.flow None when nothing is active and set when an attempt is active.

Non-goals (reviewers must not require): any drawing, TUI, colours, models/effort, percentages, the planner, reading logs, store changes.

Testing: while editing run only the test you change; run the DoD command once at the end.

DoD: `python3.13 -m unittest tests.test_live tests.test_runs tests.test_tui_live tests.test_tui_milestones tests.test_toolchain tests.test_reference` with TMPDIR short (see preamble), all green.
