# u4w — zplan's commits in the user's history name the milestone, not only "Milestone M1 attempt 1"

Walk 2026-10-29 end and rc1 W14: `git log` after a merge reads "Merge zplan/m1-…-a1: Milestone M1 attempt 1 (plan
revision 1)" and "zplan: Milestone M1 attempt 1 (plan revision 1)": nothing in the project's history says what
changed. Both messages use `runs.title(r)` (runs.py:166): `commit_candidate` (runs.py:647) and the export
(runs.py:1510). `title(r)` is also the native run's title and is compared with the stored run record
(runs.py:1140, 1966, 2086), so it must stay as it is. The milestone's title is in the approved plan
(`m["title"]`, as runs.py:1810 reads it).

Change: the two commit messages lead with the milestone id and title, then the attempt:
"Merge M1: <milestone title>" (the branch name moves to the second paragraph with the existing trailer) and
"zplan: M1 <milestone title> (attempt 1, plan revision 1)". A title over 72 characters is cut with "…". `title(r)`
and every native run title stay unchanged.

Write-set: terminal_planner/runs.py, tests/test_runs.py, tests/test_install.py, tests/test_terminal_planner.py

Acceptance criteria:
- A1 History says what changed. Example: fixture plan with M1 "Add --lines to the word count CLI", one attempt,
  merged -> `git log --format=%s -2` is "Merge M1: Add --lines to the word count CLI" and "zplan: M1 Add --lines to
  the word count CLI (attempt 1, plan revision 1)".
- A2 The native run keeps its title. Example: the `zeroshot run --title` argument is still "Milestone M1 attempt 1
  (plan revision 1)" and a stored run record reloads.

Non-goals (reviewers must not require): a change summary in the message, the engine's own commits, branch names,
the merge receipt line in the UI.

Conflict rule: if a test outside the write-set pins the old commit subject, change nothing in it and end with
`conflict: <file:line>`.

Risk: medium (git history text). DoD: `python3.13 devtools/fasttest.py tests.test_runs tests.test_install
tests.test_terminal_planner tests.test_merge_gate tests.test_export`: exit 0.
