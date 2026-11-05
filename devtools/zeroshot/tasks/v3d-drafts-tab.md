# v3d — one permanent Drafts tab replaces the per-draft «Goal draft» tabs

docs/PLAN_UX.md V3, owner decision Q3, first of the Drafts tasks (Astra's consult: design dir
drafts-astra-consult.md). Today every goal draft the architect writes opens its own «Goal draft» view tab
(`on_draft_card_requested`, tui/card_host.py:361, through `add_view_tab`, tui/app.py:2275, which is the file-tab
lifecycle: a tab limit, forced activation, esc closes it), and a sent draft's tab closes once its revision exists
(card_host.py:130, `sent_drafts`). The right column's fixed tabs are Scheme
(TAB_LIVE) and Plan (TAB_PLAN), built in compose (app.py:977-982).

Change:
- A third fixed tab, Drafts, built like the other two, beside Scheme and Plan; it stays for the session (not a view
  tab: no limit, never closed by esc) and is part of the tab cycle.
- It lists the goal drafts of the retained chat history, newest first: each with its time and its text verbatim
  (`draft_tab_text`'s body); none -> one line saying drafts from the architect appear here.
- A new draft brings Drafts forward once, through `move_tab` (which already keeps the owner's own tab choice); no
  per-draft view tab opens any more, and the D6 rule that closed a sent draft's tab goes with it.
- The draft card stays as it is (a later task replaces it); its text names the Drafts tab instead of «Goal draft».

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/card_host.py, terminal_planner/tui/card_kinds.py,
terminal_planner/tui/strings.py, tests/test_tui_draft_card.py, tests/test_tui_draft_tab_ends.py,
tests/test_tui_card_keys.py, tests/test_tui_chat_dedupe.py, tests/test_tui_chat_steps.py, tests/test_tui_low_batch.py,
tests/test_tui_narrow.py, tests/test_tui_planning.py, tests/test_tui_split.py, tests/test_tui_look.py,
tests/test_tui_activity_pane.py, tests/test_tui_canvas_files.py, tests/test_tui_milestones.py

Acceptance criteria:
- A1 One tab. Example: two goal-draft replies -> one Drafts tab holding both, the newer first; no «Goal draft» tab.
- A2 It stays. Example: esc on the Drafts tab and sending the newest draft -> the tab and both drafts remain.
- A3 Forward once. Example: a new draft while the owner reads Scheme by their own choice -> move_tab's existing rule
  decides; with no owner choice Drafts comes forward once.
- A4 Narrow layout. Example: the narrow canvas pages Drafts like Plan and Scheme.

Non-goals (reviewers must not require): the draft card and /plan (next task), the proposed plan in Drafts (later
task), drafts beyond the retained history, persistence.

Conflict rule: if a test outside the write-set pins the «Goal draft» tab, change nothing in it and end with
`conflict: <file:line>`.

Risk: low (owner screen). DoD: `python3.13 devtools/fasttest.py tests.test_tui_draft_card tests.test_tui_draft_tab_ends
tests.test_tui_card_keys tests.test_tui_chat_steps tests.test_tui_narrow tests.test_tui_planning tests.test_tui_split`:
exit 0.
