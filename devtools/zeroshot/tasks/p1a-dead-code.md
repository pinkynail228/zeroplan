# p1a — delete the unused journal module and correct five module docstrings that deny existing callers

terminal_planner/journal.py (240 lines) has no production importer (grep: only catalog.py names its error family
`journal.history_unavailable`); its own test is tests/test_journal.py. Five module docstrings state that nothing
calls the module, which is false today and misleads readers:
- record_home.py: "This slice adds the resolver only; no caller uses it yet (R-4)." (callers: architect, setup, engine)
- merge_critic.py: "... is never called from `gate_merge` or Delivery (that wiring is A7b2)." (callers: delivery, runs)
- tui/strings.py: "Nothing renders from this module yet: integration runs i1-i6 switch the main screen to it."
- tui/palette.py: "Nothing wires it into the app yet: ..." (caller: tui/app.py)
- tui/slash.py: "... nothing imports this module yet (the integration run i2 wires it to the app's actions)."

Why: dead code and false docs cost every later reader and brief (replan ledger C3).

Reuse: `python3.13 -m terminal_planner.catalog --write` regenerates docs/REFERENCE.md from catalog.py.

Write-set: terminal_planner/journal.py, tests/test_journal.py, terminal_planner/catalog.py, docs/REFERENCE.md,
terminal_planner/record_home.py, terminal_planner/merge_critic.py, terminal_planner/tui/strings.py,
terminal_planner/tui/palette.py, terminal_planner/tui/slash.py

Acceptance criteria:
- A1 The journal module and its family are gone. Example: `git ls-files terminal_planner/journal.py
  tests/test_journal.py` prints nothing; `grep -rn "history_unavailable" terminal_planner docs/REFERENCE.md` finds
  nothing; tests.test_reference passes.
- A2 Each of the five docstrings states what the module is and who uses it now, with no "yet"/"never called"
  sentence. Example: merge_critic.py's docstring says the merge gate (runs.py, delivery.py) raises the critic.

Non-goals (reviewers must not require): new tests (this is a deletion and prose); other docstrings; the live
journal in live.py, planning.py or runs.py; ARCHITECTURE.md; the "journal" word in UI strings.

Conflict rule: if a production module outside the write-set imports journal.py, change nothing and end with
`conflict: <file:line>`.

Risk: low (dead code, prose). DoD: `python3.13 devtools/fasttest.py tests.test_reference
tests.test_merge_critic tests.test_docs`: exit 0.
