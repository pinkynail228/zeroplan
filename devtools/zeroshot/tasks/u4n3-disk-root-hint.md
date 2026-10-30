# u4n3 — the disk-root refusal suggests a folder the owner can create

Soak 2026-10-30 N3: started at `/`, the start screen refuses it and says "Make a folder for it: mkdir /my-project",
but `/` is read-only on macOS, so the suggested command fails. The text is built in tui/start.py:345-346 from the
refused path itself (`Path(self.info.path).resolve() / "my-project"`).

Change: for the home folder keep "mkdir ~/my-project"; for the top of a disk (`/`, `/Volumes/<name>`) suggest a
folder inside the home folder (`mkdir ~/my-project`) when the root is not writable, and the disk's own
`<root>/my-project` when it is (a mounted external drive).

Write-set: terminal_planner/tui/start.py, tests/test_tui_start.py

Acceptance criteria:
- A1 `/` gets a working hint. Example: the start screen at `/` (not writable) shows "mkdir ~/my-project".
- A2 A writable drive keeps its own folder. Example: `/Volumes/SSD` writable -> "mkdir /Volumes/SSD/my-project";
  the home folder -> "mkdir ~/my-project".

Non-goals (reviewers must not require): creating the folder, other refusals, the picker's typed path.

Conflict rule: if a test outside the write-set pins the old hint, change nothing in it and end with
`conflict: <file:line>`.

Risk: low (one hint). DoD: `python3.13 devtools/fasttest.py tests.test_tui_start`: exit 0.
