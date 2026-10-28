A4a — the foreman's mechanical checks of a brief before launch (RELEASE_0.6.0_PLAN lane E step 3;
ARCHITECT_DESIGN.md section 6).

Why: most failed runs since 0.5 came from brief defects (missing files, stale references, oversize briefs), not
worker bugs. The foreman checks a brief against the project before a run starts; a blocking finding goes back to the
architect and the run does not start (wiring is A4b/A5t; this slice is the pure check).

Reuse: `authority.brief_problem` and `BRIEF_KEYS` (the A2a brief format); terminal_planner/project_read.py
(`read_file`, `search`: tracked files only, credentials skipped) for every file access; `authority.canonical`.

Write-set: terminal_planner/foreman.py (new), tests/test_foreman.py (new).

API: `inspect(project, brief) -> [{"check": "F1"|"F3"|"F5", "blocking": bool, "text": str}]`, sorted by check
then text; empty = pass. An invalid brief (`brief_problem` not None) -> one blocking F5 finding with that problem,
nothing else checked. "Path token" = a backtick-quoted token containing `/` or ending in `.py`, `.md`, `.json`,
`.sh`, `.toml`, optionally with `:LINE`.

Acceptance criteria:
- C1 Write-set reach (F1, blocking): a write-set path that is not a tracked file and whose parent directory has no
  tracked file. Example: write_set `["tests/test_x.py", "nowhere/new.py"]` in a repo with tracked `tests/a.py` ->
  one finding naming `nowhere/new.py`.
- C2 Stale references (F1, blocking): a path token in `reuse` or a criterion's text or example that is neither
  tracked nor in the write-set; a `path:LINE` whose file has fewer lines; a backtick-quoted identifier in `reuse`
  (letters, digits, `_`, `.`) that `search` finds nowhere. Example: reuse "`a.py:9` and `missing_fn`" with a 3-line
  tracked `a.py` -> two findings (line 9 beyond 3 lines; `missing_fn` not found).
- C3 Platform (F3, not blocking): a write-set test file (tracked, under `tests/`) whose text contains `HOME`,
  `XDG_`, `/home`, `sys.version` or `sys.platform`, while the dod does not mention `linux` (any case) -> a finding
  naming the file and the token. Example: tracked `tests/test_h.py` with `os.environ["HOME"]` -> one F3 finding.
- C4 Size (F5, blocking): canonical JSON of the brief over 4096 UTF-8 bytes, or the write-set over 12 files. Example:
  a brief whose `why` is 5000 characters -> one F5 finding with the measured byte count.

Joint example (C1+C2 on one brief): write_set `["src/new.py"]` with tracked `src/old.py`, reuse "`src/old.py`",
criterion text "edits `src/new.py`" -> no findings.

Non-goals (reviewers must not require): agent checks F2 and F4, the agent part of F1, the preflight node and the
`conflict` route (A4b); calling `inspect` from runs, the Controller or the TUI (A5t); untracked or ignored files;
regex or fuzzy matching.

Risk: medium. DoD: `python3.13 devtools/fasttest.py tests.test_foreman tests.test_toolchain` exit 0; quote the
`fasttest:` lines.
