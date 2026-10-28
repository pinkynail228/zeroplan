A12 — a project file replaces the shipped architect method

Owner: the method is never locked; a person customizes it by editing one plain file, with no commands or settings
(settings come in later releases). Today `method()` (architect.py :268) always reads the packaged
resources/architect_method.md, and `build_preamble` (:274) carries it in the first turn; the turn code (:942) has
`self.project`, the resolved project directory. The profile file `zplan.process.json` sits at the project root
and is tracked; the method file goes beside it so a team can commit and share it.

Write-set: terminal_planner/architect.py, tests/test_architect.py, README.md.

Acceptance criteria:
- C1 When `<project>/zplan.architect.md` exists and holds text, the first turn of a new conversation carries that
  text in place of the shipped method; a resumed turn carries neither.
  Example: the file holds "# Our method\n- Small slices." -> the first prompt contains "Small slices." and not
  "At most 5 acceptance criteria"; the second prompt of the thread contains neither.
- C2 Without the file, or when it is empty or whitespace only, the first turn carries the shipped method as today.
  Example: no file -> first prompt contains "At most 5 acceptance criteria"; a file holding "\n  \n" -> the same.
- C3 A file that is not valid UTF-8 never breaks the turn: invalid bytes are replaced and the rest is carried.
  Example: the bytes b"# M\n\xff ok" -> the first prompt contains "ok" and the turn starts.
- C4 README.md says in one or two sentences where the shipped method is and that `zplan.architect.md` at the
  project root replaces it (copy the shipped text to start). Example: README contains "zplan.architect.md".

Tests: the existing A11 tests stay; the shipped-method checks (size, no dates) apply to the packaged file only.

Non-goals (reviewers must not require): merging the project file with the shipped one; a size cap or Blocked
family for the file; settings or profile keys; an accept step for the file (the architect stays read-only and the
Controller enforces the autonomy level); docs/USER_FLOW.md (K1d); editing the shipped method.

Risk: medium. DoD: `python3.13 devtools/fasttest.py tests.test_architect tests.test_toolchain`, exit 0; quote
`fasttest:` lines.
