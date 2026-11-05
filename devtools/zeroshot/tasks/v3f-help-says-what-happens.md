# v3f — the help texts stop promising a confirmation the screen no longer asks

docs/PLAN_UX.md V3, last task. Confirmations went: /run and resume (p094), the end screen's merge (u3), a named
stop (v3a), the new-attempt form (v3c). The catalog still says otherwise, and `zplan help`, the help screens and
docs/REFERENCE.md (generated from it) repeat it: catalog.py:123 ("a preview ... asks for confirmation"), :513,
:554 ("stop the attempt (after a confirmation)"), :561 ("merge ... after a confirmation"), :608, :610, :616, :633;
tui/modals.py:407 still names "the new-attempt form".

Change: for every catalog action or screen text that names a confirmation, read the code path it describes and
- where nothing is asked any more, say what happens ("Stop the running attempt.", "Merge the result branch into
  main."), keeping the rest of the text;
- where a confirmation is still asked (the planner's stop, the plain CLI's own prompts, the consent card), keep it.
Regenerate docs/REFERENCE.md with the project's generator; fix the modals.py docstring. No behaviour changes.

Write-set: terminal_planner/catalog.py, docs/REFERENCE.md, terminal_planner/tui/modals.py, tests/test_reference.py

Acceptance criteria:
- A1 True help. Example: the help of the TUI stop and merge actions holds no "confirmation"; the planner stop's
  text still says it asks.
- A2 Generated. Example: test_reference's generated-blocks check passes against the regenerated REFERENCE.md.
- A3 No behaviour. Example: no file outside the write-set changes; every TUI test module the DoD names passes.

Non-goals (reviewers must not require): new wording elsewhere, README, USER_FLOW (owner docs, a later pass),
translations.

Conflict rule: if a test outside the write-set pins one of these texts, change nothing in it and end with
`conflict: <file:line>`.

Risk: low (text). DoD: `python3.13 devtools/fasttest.py tests.test_reference tests.test_tui tests.test_tui_commands
tests.test_tui_palette`: exit 0.
