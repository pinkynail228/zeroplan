T2 — English interface: TUI, chat and the architect

Owner 2026-10-27: English-only. Design ~/zs-pause/design/0.8-english-ui.md
(critic-reviewed). T3 closes. T1 is merged into this branch.
Attempt 3 (1-2 timed out; translation done). Left: tests/test_tui_live.py:24 imports tui.card_kinds (rich) at
module level, breaking the bare import (test_toolchain) of it and 4 modules importing it; test_tui_chat_after_merge
settled-merge scroll test (50 != 0). Iterate on those modules; DoD once at the end.

Write-set: terminal_planner/tui/*.py, terminal_planner/feed.py, terminal_planner/delivery.py,
terminal_planner/architect.py, terminal_planner/architect_tools.py, tests/*

Acceptance criteria:
- U1 Every string literal, docstring and comment in the write-set's terminal_planner .py files is English except
  U3's LEGACY_* and strings.py ru/zh values; OFFERED = ("en",), every "en" value English (Cyrillic today: chat.intro*, chat.example_1-3,
  card.commit_*, note.commit_no_suspend, cmd.retry, cmd.language, note.bad_language); ru/zh values untouched;
  /language is hidden while one language is offered. Example: a fresh TUI shows no Cyrillic.
- U2 Producer and consumer change together, each pair tested by feeding the producer's real output to the consumer:
  delivery.py:542 -> tui/app.py:155-157; T1's hints -> app.py:162-171; delivery.py:1022 -> tui/card_kinds.py:282;
  feed.py:277-282 -> tui/chat.py:1225-1227; feed.py:255-268 -> chat.py:233/1235-1237. Example: the English
  «Tasks: 2/3» line from delivery parses in MERGE_TASKS.
- U3 Stored 0.7.x rows keep working: the Russian forms of feed.STATUS_PREFIX (feed.py:233), EVENT_HIDDEN, step_of
  (chat.py:1248), PROMPT_STARTS (chat.py:471-476) and the draft label (chat.py:51/297) stay accepted as input in
  named LEGACY_* constants. Example: a 0.7.x-shaped events row is hidden as before; a reply with «Черновик цели:»
  is cut as before.
- U4 The architect replies in the language of the owner's last message (architect.py:301); event turns and the
  warm-up have no owner message and are English; architect.py:89 names the English «yes» button. Example: owner
  writes in Russian -> the prompt says reply in that language; event-turn prompt has no Cyrillic.
- U5 Tests: only tests/test_tui*.py, test_agent_activation.py, test_feed*.py, test_architect*.py
  are edited; they assert the English text; tests pinning the ru column point at en, except tests of the language
  mechanism; Cyrillic negative assertions are translated or deleted (reason in the commit message); Russian input
  fixtures and test_tui_planning.py:29, test_ux.py:26 (export_check-exempted) stay byte-identical. Example:
  test_tui_cards asserts the English card text.

Non-goals (reviewers must not require): T1's files; docs, the guard test and non-TUI tests asserting
T2's texts (T3); behaviour changes.

Risk: medium (text). DoD: `python3.13 devtools/fasttest.py $(git diff --name-only
$(git merge-base main HEAD) -- 'tests/test_*.py' | sed 's|/|.|;s|\.py$||')`: exit 0 (full suite in T3).
