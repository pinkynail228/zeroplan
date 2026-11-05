# v3j — two leftovers of removed actions: the "proposed" hint and /decline in the draft state

docs/PLAN_UX.md V3. v3b removed the plan's decline action, but the catalog's state text for "proposed"
(terminal_planner/catalog.py:111) still says "[a] approve, [r] revise, [x] decline." and docs/REFERENCE.md (generated
from the catalog) repeats it. v3e removed the draft card, but the slash command table (terminal_planner/tui/slash.py,
the /decline entry) still offers /decline in the "draft" state, where it now only answers "not now".

Change: the "proposed" text names only the actions that exist ("[a] approve, [r] revise."); /decline is no longer
offered in the "draft" state (it stays for plan_ready and question); REFERENCE.md regenerated with the project's
generator. No other behaviour changes.

Write-set: terminal_planner/catalog.py, docs/REFERENCE.md, terminal_planner/tui/slash.py, tests/test_tui_slash.py,
tests/test_reference.py

Acceptance criteria:
- A1 Hint. Example: the "proposed" state text holds no "decline".
- A2 Slash. Example: in the draft state the palette does not list /decline; in plan_ready it does.
- A3 Generated. Example: test_reference's generated-blocks check passes.

Non-goals (reviewers must not require): other texts, the question card's /decline, the plain CLI.

Conflict rule: a test outside the write-set pinning these: change nothing, end with `conflict: <file:line>`.

Risk: low (text). DoD: `python3.13 devtools/fasttest.py tests.test_tui_slash tests.test_reference tests.test_tui_palette
tests.test_terminal_planner`: exit 0.
