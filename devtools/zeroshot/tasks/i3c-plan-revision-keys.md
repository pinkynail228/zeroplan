I3c corrective — milestone card keys carry the plan revision (0.5.2; reviewer conflict on i3c-merge-card round 5).

Card contract: devtools/zeroshot/tasks/card-contract.md (read first). The checkout already holds the merge card
(i3c) integrated with main; keep its behaviour, its tests and the `/merge` `/diff` wiring at the end of app.py.

Defect: attempts restart at 1 for every plan revision (terminal_planner/runs.py ~1444), but three card keys name
only `<milestone>:<attempt>`: `merge_key` (app.py ~3832, `merge:M1:1`), `question_card_key` (~4056) and
`failed_card_key` (~4274). After an approved revision r2 the stage M1 attempt 1 reuses r1's key, so a card the
owner closed under r1 suppresses r2's card, and the merge counts cache (`merge_view`, ~1938) answers r2 with r1's
numbers.

Change: these keys become `<kind>:r<version>:<milestone>:<attempt>`, the version taken from the current plan
snapshot (`screen.app.snapshot.version`); every reader of a key's fields (`merge_stage`, the question and failed
helpers, any `split(":")` on these kinds) reads the new layout; caches keyed by these keys stay keyed by them (so
they are per revision). `failed_plan_card_key` (`failed:plan:<version>`) is unchanged. Update docstrings and the
card-contract key list; update tests that spell old keys.

Write-set: terminal_planner/tui/app.py, devtools/zeroshot/tasks/card-contract.md, tests/test_tui_merge_card.py,
tests/test_tui_question_card.py, tests/test_tui_failed_card.py, plus any other test module that spells a
`merge:`/`question:`/`failed:<milestone>` key (key strings only).

Acceptance criteria (example: plan r1, stage M1 attempt 1 awaiting merge; then plan r2 approved, M1 attempt 1
awaiting merge again):
- A1 r1 shows one card `merge:r1:M1:1`; after the owner closes it and r2 arrives, an open `merge:r2:M1:1` shows.
- A2 r2's card reads its own counts (a second `open_run` read for the r2 key), never r1's cached numbers.
- A3 Same for the question card (`question:r2:M1:1` shows after `question:r1:M1:1` was answered) and the failed
  card (`failed:r2:M1:1` after `failed:r1:M1:1` was retried).
- A4 `/merge` and `/diff` on `merge:r2:M1:1` act on stage M1; a typed `/diff` still opens the canvas diff tab.
- A5 Each regression fails on the old key layout (state that you checked this by reverting the key line once).

Non-goals (reviewers must not require): new card kinds, the chat layout, persisting closed keys.

Risk: medium. DoD: `python3.13 devtools/fasttest.py tests.test_tui_merge_card tests.test_tui_question_card
tests.test_tui_failed_card tests.test_tui_draft_card tests.test_tui_milestones tests.test_tui_card_hooks` exit 0;
quote its `fasttest:` lines.
