P1 — saving the profile works on an exFAT drive and still never shows a half-written or overwrites a file

Tester report 2026-10-28 (0.8.1, macOS, project on `/Volumes/SSD SAMSUNG/...`, exFAT): accepting the profile fails
with "[Errno 45] Operation not supported: '.zplan-process-…' -> 'zplan.process.json' [code: unknown_error]".
Cause: `_create` (terminal_planner/process.py:1107) publishes the fsynced temp with `os.link`; exFAT has no hard
links. Probe 2026-10-28 on a local `hdiutil` ExFAT image: `os.link` and macOS `renamex_np(..., RENAME_EXCL)` both
fail with ENOTSUP; `os.rename` and `os.replace` work. The file is written only under the Authority session lock
(process.py:14).

Reuse: `_create` and `_replace` as they are; `ctypes` from the standard library for `renamex_np` (libc, flag
RENAME_EXCL = 0x4); tests/test_process.py's scratch projects.

Write-set: terminal_planner/process.py, tests/test_process.py.

Acceptance criteria:
- E1 When `os.link` raises OSError with errno ENOTSUP or EOPNOTSUPP (only those), `_create` publishes the same
  fsynced temp with `renamex_np(RENAME_EXCL)`; when that is unavailable or fails with ENOTSUP/EOPNOTSUPP too, it
  checks the name is absent and then `os.rename`s the temp onto it. Example: link patched to raise ENOTSUP and
  renamex_np patched unsupported -> accept succeeds, the file holds the full text, no `.zplan-process-*` left.
- E2 Never over an existing file on any path: link EEXIST, renamex_np EEXIST, or the name present before the
  rename -> the same "already exists; it is not overwritten" refusal as today, the existing bytes unchanged.
  Example: link ENOTSUP, file already present -> refusal, original content intact.
- E3 Other OS errors are plain: permission denied, disk full (ENOSPC) and any other OSError from writing or
  publishing raise `Blocked` with an existing family (no new catalog family) whose message names the file and the
  error's strerror, never `unknown_error`; the temp is removed. Example: link raises ENOSPC -> Blocked, message
  contains "zplan.process.json" and "No space left on device", family is not None.
- E4 No regression where link works: on a normal filesystem the path is exactly today's (`os.link`), proven by a
  test with link spied. Example: a scratch
  project on the normal disk -> accept calls `os.link` once, never `os.rename` or `renamex_np`.

Non-goals (reviewers must not require): general FAT/FAT32 support, Linux `renameat2`, a probe at startup,
`_replace` or project_state writes (they already rename), the profile's Git commit, UI wording outside the raised
message, a real exFAT image in tests.

Conflict rule: if a test outside the write-set pins `_create`'s use of `os.link` or the unknown_error text, change
nothing and end with `conflict: <file:line>`.

Risk: high (persisted state in the user's project). DoD: run once, at the end: `python3.13 devtools/fasttest.py
tests.test_process tests.test_toolchain`: exit 0; `python3 devtools/budget.py`: OK. Each new test fails with the
old process.py restored.
