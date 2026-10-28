u3b-chat-dedupe — show each draft body once in the chat pane (U-1 of the u3b-chat-view draft). Today an architect reply that carries a draft shows the draft body twice: inside the reply text (the fenced ```zplan-goal / ```zplan-answer block as written) and again as the labelled draft line (`entry_lines`, terminal_planner/tui/chat.py:658). Base: main after u3b-drafts-answer merges. DeepSeek worker, sol reviewers. Runs in parallel with u3b-chat-scroll (ownership below).

Read: terminal_planner/architect.py (`parse_drafts`, `_draft_opener`, `_skip_fence`, `_draft_record`, DRAFT_RULES, MAX_DRAFTS, MAX_DRAFT_TEXT), terminal_planner/tui/chat.py (`entries_of`, `drafts_of`, `entry_lines`, `draft_line`, `reply_names`, ENTRY_TEXT), terminal_planner/tui/app.py (`body_rows`, `chat_layout`, `plain_lines`, the L-1..L-4 comments), docs/TUI_PLAN.md (U3b), tests/test_tui_chat.py, tests/test_architect.py.

Ownership (parallel run): this task owns the architect scanner and the chat display transformation (`entries_of`, `entry_lines` and helpers in chat.py). It does not touch `chat_layout`, scroll state or keys (u3b-chat-scroll owns them). Preserve the signatures `entry_lines(entry, source) -> list[str]` and `body_rows(history) -> list[str]`. New tests go in a new file tests/test_tui_chat_dedupe.py.

Rules:
- R-1 Extract a shared span iterator used by `parse_drafts` and by the display; preserve `parse_drafts`' public records and acceptance behavior (no second parser). It runs over the full stored `row.text`, before the ENTRY_TEXT clip and before L-2. Match eligible spans to the row's stored draft records once, in stored order, by `(kind, milestone-or-empty, trimmed body)`. Display matching ignores identity/actionable and never consults the current snapshot.
- R-2 Matched records render once, as their labelled draft line at their source span (opener line, body and closing fence collapse into it), in reply order, and are excluded from the trailing draft rendering. Unmatched spans stay raw text exactly as today (malformed, unknown milestone, over-limit, sixth-and-later, a zplan fence inside another fenced block, no matching record). Unmatched stored records keep today's trailing rendering. Preserve the surrounding newlines.
- R-3 Display only: the store, the transcript, the draft records, `Draft.text` and the [c]/[t] actions are unchanged. A row without draft metadata (old format, failed or cancelled turn) is shown exactly as today.
- R-4 Clip: keep ordered narrative/draft segments structured. Count the transformed payload's Python characters: unchanged narrative plus trimmed draft bodies; generated labels and the leading ellipsis are excluded. Keep its last ENTRY_TEXT characters, retaining a cut segment's suffix and its label; wholly clipped matched segments are not appended again. Full Draft records remain available to [c]/[t]. Rows without matches keep today's rendering. Say this in a docstring.

Acceptance criteria (unit, deterministic fixtures):
- A-1 1 and 5 drafts in one reply: each body appears once, as its labelled draft line at the block's position (check the segments of each occurrence, not a global substring count). 0 drafts is a compatibility control.
- A-2 A sixth block, an unknown milestone, an empty body, an over-limit body, a zplan fence inside another fence, and an unclosed fence (placed at the end): these stay raw, and valid blocks beside them still collapse. Add missing, mismatched and duplicate metadata fixtures.
- A-3 Two identical bodies, and a body text that also occurs outside any fence: only the fenced, matched occurrences collapse.
- A-4 Whitespace around the body (the stored `Draft.text` is trimmed and the raw block is not): it still matches and collapses.
- A-5 Clip: 3999/4000/4001 payload characters, maximum-size bodies, clipping within and across segments, goal/answer mixtures and the L-2 controls; [c]/[t] still act on a draft whose body was clipped out of view.
- A-6 Restart: rows from the store give the same display; an old-format row is unchanged.
- A-7 A bounded generator (fixed seed, <= 200 cases): the oracle derives source spans from the fixture construction and applies the stored-record and clipping rules independently of the production replacement helper.
- A-8 Each new-behavior test (A-1 1/5, A-3, A-4, A-5, A-6 restart) fails on the base at the intended assertion; compatibility tests may pass. Record the exact test id, wrapper command and failing assertion. test_architect and the existing chat, drafts and layout tests stay green.

Size: ~200-350 lines with tests.
Out of scope: history scroll (u3b-chat-scroll), any key, any store or protocol change, wording outside the pane.
After both chat tasks merge (orchestrator): verify PageUp/PageDown and resize over deduplicated goal/answer replies, with unchanged draft actions.
critic u3b-chat-dedupe-task: GO WITH CHANGES, applied (session 01a1508c-a9c6-7163-9bf9-ce2e624118d4)
