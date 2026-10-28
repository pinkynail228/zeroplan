M2 — architect replies never lose text that looks like HTML

docs/RELEASE_0.6.3_PLAN.md V2 follow-up. M1 renders an architect entry with rich Markdown (app.py `Reply`). Its
markdown-it parser runs with HTML on and Rich drops `html_inline` / `html_block` tokens, so model text vanishes:
`use Vec<String> here` shows `use Vec here`; `<!-- hi --> z` shows nothing (reproduced with rich 15.0.0 on 2026-10-27).

Write-set: terminal_planner/tui/app.py, tests/test_tui_chat_messages.py

Acceptance criteria:
- C1 Text that markdown-it would read as HTML (inline tags, comments, HTML blocks) shows literally, character for
  character, in an architect entry; Markdown styling of everything else is unchanged. Example: reply
  `use Vec<String> here` -> a row `● use Vec<String> here`; reply `<!-- hi --> z` -> a row `● <!-- hi --> z`.
- C2 Block HTML keeps its lines. Example: reply `x\n\n<div>\nblock\n</div>\n\ny` -> rows with `x`, `<div>`,
  `block`, `</div>`, `y` in that order.
- C3 Code and comparisons are unchanged. Example: `` `Vec<T>` ok `` -> `Vec<T> ok`; `1 < 2 and 3 > 2` -> the same
  text; `## План\n- M1` -> `● План`, `• M1` (M1 C2 still holds).
- C4 L-2 still runs first and markup is never interpreted. Example: `[bold]x[/] <b>y</b> \x1b[31mz` -> shows
  `[bold]x[/] <b>y</b> z` literally.

Tests: extend tests/test_tui_chat_messages.py (one test, 80x24) with C1-C4; it must fail on today's main.

Non-goals (reviewers must not require): rendering HTML; links; owner, error, reset or event entries; other
Markdown features; translations.

Risk: low (display). DoD: `python3.13 devtools/fasttest.py` (the full suite): exit 0.
