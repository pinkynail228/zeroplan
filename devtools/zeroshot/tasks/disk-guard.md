disk-guard — 0.5 item S5a (docs/RELEASE_0.5_SCOPE.md): zplan refuses to start a new milestone attempt or planning submission when the disk under its effective work roots is nearly full, and doctor shows the free space. The branch is held until the 0.4.0 tag. DeepSeek worker, sol reviewers.

Observed: reviewer scratch filled the disk (~80 GB, ENOSPC) during dev runs (STATE Open). zplan has no free-space check anywhere: the only one is devtools/zeroshot/run.sh:16-20.

The default zplan-owned paths are durable; overrides may select other filesystems:
- data_root() honours XDG (setup.py:29);
- worktrees have their own overridable root (runs.py:562), and `git worktree add` also writes metadata into the target repository's Git common directory (runs.py:719);
- the planner checkout lives under Authority (engine.py:668-669);
- the native engine has its own state_root (engine.py:587);
- authority state is at authority.py:152-154;
- Codex uses CODEX_HOME or ~/.codex (setup.py:209-215); data_root()/codex-home is opt-in.

Read:
- terminal_planner/setup.py: data_root, the native root, readiness :253, doctor output :574, the items near :453-500;
- runs.py: start path, `refresh` :619/:1150, worktree :558-562/:719;
- planning.py: goal save :285-292, check filtering :251-254, submission;
- engine.py: state_root :587, the planner checkout :668;
- authority.py: :152-154, :353-371;
- catalog.py, the plain UI and the TUI Settings readiness display, docs/REFERENCE.md, and their tests.

Rules:
- R-1 Probe. One module function probes the effective roots:
  - the effective worktree storage;
  - engine.state_root;
  - authority.directory;
  - the target Git common directory.
  Each root resolves to its nearest existing ancestor; no directory is created. Successful probes are deduplicated by the ancestor's st_dev, and free bytes come from `shutil.disk_usage`. Doctor uses the configured roots.
- R-2 Thresholds. Units are GiB = 2**30 bytes.
  - The block threshold is 5 GiB, overridable by `ZPLAN_MIN_FREE_GB`. An unset override means 5; a positive ASCII integer of GiB is accepted.
  - An empty, zero, negative, fractional, NaN, infinite or malformed override refuses new starts with `disk.invalid_config`, and doctor reports BLOCKED.
  - Block is evaluated first (free < block threshold), then warn (free < 15 GiB). Equality to a threshold is allowed.
- R-3 Guard.
  - New planning submissions and new milestone attempts are guarded in the service/engine path, independent of the UI. The check runs before preparation, refresh, binding or attempt writes.
  - A retry or restart that creates a new run is guarded.
  - Observing, stopping and continuing an already submitted run stay available.
  - A blocked start is refused with `disk.low`, naming the path and the free GiB.
  - Existing saved goals and session locks are outside the no-write guarantee.
- R-4 Display. Disk items have a severity of ok, warn or block; a warning keeps ok=True.
  - Doctor prints WARN, and exits successfully when warnings are the only issue.
  - The plain UI and TUI Settings show warnings with the path and the free space.
  - Disk is added to the plan/start checks; it does not gate resume.
  - Doctor makes no model request.
- R-5 Errors. A nonexistent root uses its nearest existing ancestor. A probe OSError is a warning for that root, and it never hides another device's low-space block. Tests never depend on the machine's real free space.

Acceptance criteria (the probe is tested through mocks of `disk_usage`/`stat`; the guard tests fake the probe; no real disk filling):
- A-1 Milestone and planning entry points tested independently at the threshold minus 1 byte, the threshold, and the threshold plus 1 byte. On a block there is no native submission or validation, no checkout or branch creation, and no store change (spies).
- A-2 The 15 GiB warn boundaries; overrides below and above 15; doctor WARN with exit 0, BLOCKED for a block or an invalid config; Settings and plain UI show the warning.
- A-3 Missing ancestors; two roots on one device give one item, two devices give two; one probe error plus another low device still blocks.
- A-4 Each invalid override value gives `disk.invalid_config`.
- A-5 Observing, stopping and continuing an existing submitted run work while the disk is low.
- A-6 Feature regressions reach and fail their intended behavioral assertion on 304e575, not an import or mock error. Compatibility tests may pass on the base. Verify the new helper logic with targeted mutations, and record the exact targeted commands. The existing readiness tests stay green.

Size: ~250-400 lines with tests.
Out of scope: cleanup (S5b), agent-home migration, the devtools run.sh paths, engine storage changes.
critic disk-guard-task: GO WITH CHANGES, applied (session 01a1508f-ff31-7d30-9140-74ed97acdaf8)
