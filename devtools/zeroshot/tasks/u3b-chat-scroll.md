u3b-chat-scroll — scroll the chat history (U-2 of the u3b-chat-view draft). Today the `#chat` pane shows only the newest rows that fit (`chat_layout`, terminal_planner/tui/app.py: "filled from the bottom with the history's newest rows"), and older replies can't be read in the TUI. Scrolling covers the retained display history (HISTORY entries, each clipped to ENTRY_TEXT, chat.py), not the whole transcript. Base: main after u3b-drafts-answer merges. DeepSeek worker, sol reviewers. Runs in parallel with u3b-chat-dedupe (ownership below).

Read: terminal_planner/tui/app.py (`chat_layout`, `body_rows`, `wrap_cells`, `chat_header`, `state_row`, `chat_state`, the key bindings, the Tab cycle and the focus guard used by `draft_keys_ready`, the L-1..L-4 comments), terminal_planner/tui/chat.py (`ChatState`, `entries_of`, HISTORY, reload and send paths), terminal_planner/catalog.py (screens/actions; docs/REFERENCE.md is generated from it), docs/TUI_PLAN.md (U3b), tests/test_tui_chat.py, tests/test_layout.py.

Ownership (parallel run): this task owns `chat_layout` and the UI scroll state and actions. It does not change parsing, `entries_of` or `entry_lines` (u3b-chat-dedupe owns them); any change in chat.py stays outside those functions. Preserve `body_rows(history) -> list[str]` as the shared pipeline. New tests go in a new file tests/test_tui_chat_scroll.py.

Rules:
- R-1 Let W be the wrapped rows from body_rows(history), N = len(W), B = rows - len(head) (head = the header rows plus the state row when there is one; idle has none), and o = clamp(offset, 0, max(0, N - B)). At o = 0 the output is exactly today's. At o > 0 render the marker, then W[s:s+B-1], where s = max(0, N - B - o). PageUp adds max(1, B - 1), PageDown subtracts it, then clamp.
- R-2 Keys: scrolling is enabled only on MainScreen with #plan-pane focused. The existing Tab cycle is preserved. All editors (including an empty and a nonempty #input), and all other screens and modals keep their current key behavior. Add the actions to the catalog and regenerate docs/REFERENCE.md and the help from it.
- R-3 The marker is `↑ история (PgDn ↓)` (18 cells). It is rendered iff the layout is supported and the effective o > 0.
- R-4 Reset to 0 on an accepted owner send or a newly appended transcript entry, including entries discovered by a reload. An unchanged reload keeps the offset. A rejected send and poll/live/stream updates do not reset it. Re-clamp on every supported render; keeping the offset does not promise visual anchoring across reflow. Do not detect an append by the retained history length alone (HISTORY caps it at 40).
- R-5 Below L-1, the scroll keys are ignored and today's fallback renders with no marker. The saved offset is kept and re-clamped when the layout becomes supported again.

Acceptance criteria (unit + Textual pilot, deterministic fixtures):
- A-1 Exact visible row identities and order match an independent slice oracle; the oldest retained row is reachable. Cover N = 0, B-1, B, B+1 and an overflow; negative and oversized offsets; PageUp at the top and PageDown at the bottom are no-ops.
- A-2 Idle, live and blocked states, a long state text, dimensions 19/20/21 cols × 7/8/9 rows, and a resize larger and smaller while scrolled: re-clamp, the marker rule and the o = 0 rule hold, never more than `rows` rows, each <= `cols` cells.
- A-3 #plan-pane focused scrolls; the goal/answer forms, #input empty and with text, other screens and a modal do not scroll, and the Tab cycle is unchanged.
- A-4 Append at HISTORY = 40, repeated text, reset entries, an unchanged reload, and a reload carrying another window's new entry; a live update and a poll keep the offset; an accepted send resets it, a rejected one does not. Pilot tests wait for explicit fixture delivery and a settled render.
- A-5 A seeded generator (<= 200 cases) over sizes around the L-1 minimum, offsets and history lengths checks the A-1/A-2 invariants against the oracle.
- A-6 Each new scrolling behavior has a named behavioral assertion that fails on the base; report the command and the assertion. Preservation controls may pass on the base; import or signature failures do not count. The existing L-1..L-4 (test_tui_chat, test_layout), U-3 key-bar and drafts tests stay green.

Size: ~250-400 lines with tests.
Out of scope: draft dedupe (u3b-chat-dedupe), mouse scroll, a scrollbar, any store change.
After both chat tasks merge (orchestrator): verify deduplicated rows across PageUp/PageDown and resize, with unchanged draft actions.
critic u3b-chat-scroll-task: GO WITH CHANGES, applied (session 01a1508c-a9c6-78f2-9701-d783182af964)
