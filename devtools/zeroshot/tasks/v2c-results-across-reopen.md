# v2c — the last result of each subject survives closing zplan

docs/PLAN_UX.md V2, third task; builds on v2a/v2b (`Controller._result`, `results`, tui/controller.py). The results
are memory only: after a quit and reopen, a merge the architect asked for and that was refused before any gate
record existed (another branch checked out, a missing Git identity, runs.py:1557) leaves no trace, while the
architect's own history resumes and asks again. Astra's consult: keep the last result per subject in the store,
never in planning.json (its key set is closed, authority.py:490, and a 0.9.0 zplan would refuse a store with a new
key).

Change: the results also live in one file beside the store, `results.json` in the session authority's directory,
written with `authority.atomic_state` in the job that wrote the result:
- it holds the last result of each subject (approval: the revision; merge: milestone + attempt), the most recent 20
  subjects at most, oldest first;
- the session open seeds the in-memory results from it (seq continues after the highest kept one);
- a file that is missing, unreadable or not this shape is ignored (no results, no refusal, nothing rewritten until
  the next result); a write that fails leaves the in-memory result and the operation's own outcome as they are (a
  landed merge is never reported failed because its receipt was not saved);
- planning.json and its validation are not touched; a fixture session writes under its own fixture directory.

Write-set: terminal_planner/tui/controller.py, tests/test_bridge.py

Acceptance criteria:
- A1 Across a reopen. Example: an approval of r1 and a refused merge of M1, close the controller, open a new one on
  the same project -> zplan_status `results` holds both, seq of the next result is higher than both.
- A2 Last per subject, bounded. Example: three merge results of M1 attempt 2 and 25 approvals of distinct revisions
  -> the file holds 20 subjects, M1's entry is its last result.
- A3 Never in the way. Example: a results.json of "[" -> the session opens, `results` is []; a directory that
  refuses the write -> the approval still answers done and is in `results`.
- A4 The store is unchanged. Example: planning.json bytes are identical before and after writing results.

Non-goals (reviewers must not require): other operations, the screen, a details reader, pruning by plan state.

Conflict rule: if a test outside the write-set pins the files in the authority directory, change nothing in it and
end with `conflict: <file:line>`.

Risk: medium (a new file in the state directory). DoD: `python3.13 devtools/fasttest.py tests.test_bridge
tests.test_consent tests.test_tui_hints`: exit 0.
