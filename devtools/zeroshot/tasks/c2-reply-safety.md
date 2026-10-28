C2 — an architect reply cannot smuggle controls or lose prose; the chat's worker start cannot race its wait

Critic r063-release 2026-10-27 (pause dir: critic/r063-release.out) on v0.6.3. L-2 escapes each block's raw lines
(tui/text.py `plain_lines`) before app.py `Reply` (Rich Markdown, M1/M2) parses them, so Markdown decodes entities
after the escape; Rich drops an image token's paragraph text. Separately chat.py assigns `self._work` and starts it
a step later (`send` :744-747, `_advance` :1032-1034 and :1041-1042, reset :777-779); `wait` (:803) can join the
unstarted thread ("cannot join thread before it is started", seen once on Linux in test_tui_chat c3_a).

Write-set: terminal_planner/tui/app.py, terminal_planner/tui/text.py, terminal_planner/tui/chat.py,
tests/test_tui_chat_messages.py, tests/test_tui_chat.py, tests/test_tui_reply_safety.py (new)

Acceptance criteria:
- S1 Every text a `Reply` draws after parsing (text, inline code, code blocks, headings, list items, link and image
  labels) passes the same escape as L-2; an entity that decodes to a bidi, zero-width or C0/C1 control shows as
  L-2 shows that character typed raw. Example: reply «a &#x202e;b &lrm;c» -> no U+202E or U+200E in the rendered
  segments; the same visible form as a raw «a ‮b ‎c».
- S2 An image in a reply keeps its paragraph: «before ![alt](https://example.invalid/i.png) after» renders the words
  «before», «alt» and «after» in order; no link or image URL is opened or styled as a hyperlink.
  Example: rendered text contains «before» and «after».
- S3 Starting a chat worker and `wait`/`close` cannot interleave into a join of an unstarted thread: a thread is
  started before it becomes visible to `wait`, or `wait` and the start share a lock; `close` still waits the bounded
  time for a started turn. Example: a deterministic test that calls `wait` between creation and start (patched
  `Thread.start` or an injected hook) -> no RuntimeError, and a running turn is still joined.
- S4 Everything M1/M2 pinned stays: HTML-like text literal, raw CSI/OSC blocked, Rich markup literal, hyperlinks off.
  Example: reply «`Vec<String>` [b]x[/b]» -> shown literally.

Tests: tests/test_tui_reply_safety.py covers S1-S3 (entities for U+202E, U+200E, U+200B, U+001B, U+009B; the image
line; the start/wait interleave). Existing L-2 and M1/M2 tests are kept.

Non-goals (reviewers must not require): new markdown features; image display; other threads than the chat's worker;
quit timing budgets; texts and cards.

Risk: low-medium (rendering of model text; the chat worker's lifecycle). DoD: `python3.13 devtools/fasttest.py tests.test_tui_reply_safety tests.test_tui_chat_messages tests.test_tui_chat tests.test_toolchain`: exit 0 (the full
suite is the merge gate's).
