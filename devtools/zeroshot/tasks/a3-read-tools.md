A3 — read tools for the architect (RELEASE_0.6.0_PLAN lane T step 1; ARCHITECT_DESIGN.md 4.5).

Why: the architect will read the project to plan and brief (A5t wires these as tools). It must see only the
selected project and its worktrees, never credentials, and only scrubbed text.

Reuse: `scrub` (terminal_planner/live.py:623) for every returned line, unchanged; `Blocked` (authority.py:18) for
refusals; `git ls-files` as the file universe (git already knows what is ignored). New module, no edits elsewhere.

Write-set: terminal_planner/project_read.py, tests/test_project_read.py.

API (plain functions, JSON-ready dicts):
`list_files(project, root, prefix="")` -> `{"paths": [...], "truncated": bool}`;
`read_file(project, root, path, start=1, count=400)` -> `{"path", "start", "lines": [...], "truncated"}`;
`search(project, root, text)` -> `{"hits": [{"path", "line", "text"}], "truncated"}` (plain case-sensitive substring).
`root` = the project or one of its `git worktree list` paths. Files = `git -C root ls-files --cached --others
--exclude-standard`; nothing else is listed, searched or read.

Acceptance criteria:
- C1 Boundary: a root that is not the project or one of its worktrees, a path with `..` or absolute, or a symlink
  resolving outside the root -> `Blocked` family `read.outside_project`. Example: `read_file(p, p, "../x")` and a
  tracked symlink `link -> /etc/hosts` are both refused.
- C2 Credentials: basename `.env` or `.env.*`, `.netrc`, `id_rsa*`, `id_ed25519*`, `*.pem`, `*.key`, `*.p12`,
  `credentials*`, and any path under `.git/` or `.zplan/` -> read refused with family `read.credential`; list and
  search skip them. Example: `.env` (force-added) and `a.py` both contain `PASSWORD`; `search(p, p, "PASSWORD")`
  -> one hit, in `a.py`.
- C3 Scrub: every returned line (read lines, search hit text) equals `live.scrub` of the raw line. Example: a line
  with a credential field (built in the test, not written in this brief) comes back equal to `scrub` of it.
- C4 Limits: `count` capped at 400 lines and 64 KB per call; list at most 2000 paths; search at most 200 hits; a cut
  sets `truncated: true`. A file with a NUL byte in its first 8 KB -> family `read.binary`. Example: a 1000-line file
  read with start=1 count=1000 -> 400 lines, `truncated: true`.

Non-goals (reviewers must not require): MCP or tool wiring (A5t); writing files; the `.zplan/STATE.md` tool (A8);
regex search; reading untracked ignored files; Windows paths.

Risk: high (secrets). DoD: `python3.13 devtools/fasttest.py tests.test_project_read tests.test_live` exit 0;
quote the `fasttest:` lines.
