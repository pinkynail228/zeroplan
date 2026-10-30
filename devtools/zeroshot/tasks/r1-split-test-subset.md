# r1 — the card-split test checks that moved names live in their module, not the module's whole name list

`tests/test_tui_split.py` `CardSplitTests.test_app_py_defines_none_of_the_moved_card_names_and_each_new_module_holds_them`
(:209-211) asserts that each card module defines exactly `CARD_MOVED[module] + NEW[module]`, so every new card
helper (P6 added `CONSENT_NOTE` and four more to tui/card_kinds.py) fails it although the split it guards still
holds. Main fails it today.

Change: the test asserts that every name in `CARD_MOVED[module]` is defined in that module and none of them in
app.py (what the split guarantees); a module may define more names. `NEW` goes if nothing else reads it.

Write-set: tests/test_tui_split.py

Acceptance criteria:
- A1 The split stays guarded. Example: moving `merge_card_source` back into tui/app.py makes the test fail.
- A2 New helpers do not fail it. Example: on today's main (card_kinds.py with `CONSENT_NOTE`) the test passes.

Non-goals (reviewers must not require): product code, the other split tests, renaming anything.

Conflict rule: if another test reads `NEW`, keep it and end only with the assertion change.

Risk: low (test). DoD: `python3.13 devtools/fasttest.py tests.test_tui_split`: exit 0.
