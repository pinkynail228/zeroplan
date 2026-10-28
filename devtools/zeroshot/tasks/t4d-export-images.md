T4d — export_check accepts README images

Owner 2026-10-28: the public README's hero is `docs/img/demo.gif` (made by devtools/ui-lab/readme_gif.py from the
test fixtures). devtools/export_check.py reports every blob that is not UTF-8 as `unreadable`, so the 0.8.1 export
fails on it. Allow images in one narrow place; everything else stays as strict as now.

Reuse: `check()` in devtools/export_check.py (the blob loop that adds `unreadable`, the `private-term` scan) and the
fixture repos of tests/test_export.py.

Write-set: devtools/export_check.py, tests/test_export.py.

Acceptance criteria:
- E1 A blob that is not UTF-8 gives no finding only when all hold: its path is under `docs/img/`, ends in `.gif` or
  `.png`, starts with the format's signature (`GIF87a`/`GIF89a`, or the 8-byte PNG signature) and is at most 2 MiB.
  Anything else not UTF-8 is still `unreadable`.
  Example: `docs/img/demo.gif` starting `GIF89a`, 630 KB -> 0 findings; the same bytes at `tests/demo.gif` ->
  `unreadable`; `docs/img/x.gif` with random bytes -> `unreadable`; a 3 MiB GIF in `docs/img/` -> `unreadable`.
- E2 An accepted image is still scanned for private terms on its raw bytes (latin-1, case-insensitive), so text in
  a GIF comment or a PNG text chunk cannot leak.
  Example: a `docs/img/a.png` whose tEXt chunk holds a configured private term -> a `private-term` finding.
- E3 `--dir` mode compares an accepted image byte for byte like any other file.
  Example: the export tree's `docs/img/demo.gif` with one changed byte -> `dir-changed`.

Non-goals (reviewers must not require): other binary types or folders; the manifest; README or docs; image
content checks beyond the signature and size.

Conflict rule: if a test outside the write-set pins that every non-UTF-8 blob is `unreadable`, change nothing and
end with `conflict: <file:line>`.

Risk: medium (a release gate). DoD: run once, at the end: `python3.13 devtools/fasttest.py tests.test_export`:
exit 0; `python3 devtools/budget.py`: OK; each new test fails with the E1-E3 code reverted.
