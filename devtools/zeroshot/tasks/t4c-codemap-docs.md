T4c — code-map tests read docs/ARCHITECTURE.md

Owner 2026-10-28: the README becomes a short product page; the code map and the development section moved to
docs/ARCHITECTURE.md (commit 2920379, AGENTS.md lists it as a live doc). The README still carries its old copy only
because three tests read the code map there. This task points those tests at the new file; it changes no product
code and no docs.

Reuse: the existing assertions as they are; only the file they read changes.

Write-set: tests/test_tui_split.py, tests/test_fixture_scope.py, tests/test_docs.py.

Acceptance criteria:
- C1 `CodeMapTests` in tests/test_tui_split.py checks the code map in docs/ARCHITECTURE.md (one `- tui/<module>.py: `
  line per moved module, ending with "."); its docstrings name docs/ARCHITECTURE.md, not the README.
  Example: deleting the `- tui/card_host.py: ` line from docs/ARCHITECTURE.md fails the test; deleting the whole
  "Development" section from README.md does not.
- C2 `DocsTests.test_a5_the_docs_state_the_fixture_chat_boundary` in tests/test_fixture_scope.py looks for
  "process.py:" and "tui/chat.py:" in docs/ARCHITECTURE.md instead of README.md; its REFERENCE and USER_FLOW
  assertions are unchanged.
  Example: README.md without "process.py:" passes; docs/ARCHITECTURE.md without "tui/chat.py:" fails.
- C3 docs/ARCHITECTURE.md is a live doc in tests/test_docs.py (`LIVE`), so its Markdown is checked like the others.
  Example: a list glued to the paragraph line above it in docs/ARCHITECTURE.md fails test_docs.

Non-goals (reviewers must not require): README.md, docs/ARCHITECTURE.md or any other doc text; other tests that
read the README (test_reference, test_dirty_head, test_login_home keep reading it); product code.

Conflict rule: if a test outside the write-set needs the README code map, change nothing and end with
`conflict: <file:line>`.

Risk: low (tests only). DoD: run once, at the end: `python3.13 devtools/fasttest.py tests.test_tui_split
tests.test_fixture_scope tests.test_docs tests.test_reference`: exit 0; show C1-C3 fail on a scratch edit of
docs/ARCHITECTURE.md and pass with the README code map removed (restore both files after).
