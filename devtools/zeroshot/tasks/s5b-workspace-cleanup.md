s5b-workspace-cleanup — 0.5 item S5b (docs/RELEASE_0.5_SCOPE.md S5b row): cleanup of zplan-owned workspaces only. A workspace is removed only when no live process uses it, no recovery, export or gate record references it, and its candidate is saved. Never by prefix or age alone; foreign or ambiguous dirs are kept. Acceptance: cleanup keeps the candidate and every referenced dir. DeepSeek worker, sol reviewers.

Base: main with S5a (disk-guard), S2 and S3 merged and the S2/S3 recovery qualification recorded. Record the base commit in the receipt. The audit is on main 74f1a3b: re-check every line number on the base, and re-gate if a premise moved.

Audit (74f1a3b):
- zplan-owned locations:
  - worktrees under `data_root()/worktrees` (runs.py:562; setup.py:29-30), or `authority.directory/worktrees` in fixture/test runs (cli.py:796, :810; tui/controller.py:295);
  - naming at runs.py:88-90: dir `<proj8>-<plan8>-<ms>-a<n>`, branch `zplan-work/<plan8>/<ms>/a<n>`; validated at :383-386; created at :714-725;
  - per-run dirs `authority.directory/runs/<worktree name>` (runs.py:665-666);
  - planner checkouts `authority.directory/revision-<v>/checkout` (engine.py:668-669).
- References: run records `worktree`/`branch`/`predecessor`/`delivery`/`result{branch,tree,commit}`/`integration` (runs.py:465-478, :59); native `workspaceRecovery.recoverable`/`successorRunId`; task/merge gate and qualification records (S1a1/S1b, if merged on the base).
- No cleanup code exists; only `git worktree prune` (runs.py:714-725). S5a lists the effective roots and the warn severity (devtools/zeroshot/tasks/disk-guard.md).
- The incident dirs `/tmp/zs-agent-*` come from the devtools reviewer preamble (devtools/zeroshot/preamble.md:2-3: `mktemp -d` as TMPDIR, repo copied in), not from zplan. run.sh:17-20 only warns.

Read: those locations; terminal_planner/runs.py, engine.py, setup.py, delivery.py, cli.py, catalog.py, the S5a disk module; devtools/zeroshot/preamble.md, run.sh; tests/test_runs.py :306, :336, :353, :542; test_export.py; the S5a tests.

Rules:
- R-1 Scope and ownership. Only milestone worktrees and their per-run dirs are in scope. Planner checkouts (`revision-<v>/checkout`) and every other path are out of scope and never touched.
  - A worktree is zplan-owned only if all of these hold:
    - it sits directly under the current Authority's worktrees root;
    - its name parses exactly by runs.py:88-90;
    - at least one run record in this Authority names exactly that path in `worktree`.
  - Its per-run dir is owned only if it is `authority.directory/runs/<that same worktree name>` (runs.py:665-666) and is not a symlink.
  - Anything else is foreign or ambiguous and is kept and listed with its reason. This includes unparseable names, valid names without a record, symlinks, paths outside the root or with `..`, an unknown record schema, and any read error.
- R-2 Lineage and references. Start from every run record naming the exact worktree and follow predecessor/successor links. Any recovery, export, task-gate, qualification or merge-gate record that still needs the worktree or its per-run dir blocks removal. Apply runs.TERMINAL and run-field predicates only to run records. Unknown schemas or unresolved references keep both dirs.
- R-3 Removable only when every one of these holds, evaluated under the Authority lock immediately before removal:
  - Every run record in the lineage is in runs.TERMINAL and no successor is pending. A recoverable failed leaf blocks removal. A failed predecessor's recoverable flag alone does not block removal when its confirmed successor is included in the lineage. Preserve predecessor records unchanged; unconfirmed native lineage keeps both dirs.
  - No live native run for any lineage run id, and no process with its cwd inside either the worktree or its per-run dir. Use the existing helpers or lsof +D with a timeout; on error, keep both dirs.
  - no delivery is in exporting/awaiting_merge/conflict;
  - candidate saved: the lineage's final record has `result.commit`, that commit is reachable from a ref in the target repo, and the worktree's current `product_tree` (runs.py:112) equals `result.tree`, so nothing tracked or untracked in the product was changed after export. Otherwise keep it, with reason "изменения после экспорта".
  There is no "abandoned" path in 0.5: a workspace without an exported result is kept.
- R-4 Command. `zplan cleanup` (plain/CLI) and a TUI action on the S5a disk warning work in two steps.
  - First a dry-run list: removable with size; kept with reason.
  - Then an owner confirm re-evaluates R-1..R-3 per item under the lock and removes only the items that still pass. Removal is `git worktree remove --force` against its repo, then `git worktree prune`; the per-run dir is removed with plain removal.
  - Each removal is recorded (path, run ids, bytes) before deletion and marked done after; a crash mid-way is reconciled on the next run.
  - There is no automatic or scheduled cleanup.
- R-5 After cleanup, home, status and the run views of the affected records still load. They show "рабочая копия удалена" instead of failing, and no action that needs the worktree (resume, export) is offered for those records.

The devtools reviewer scratch (`/tmp/zs-agent-*`, devtools/zeroshot/preamble.md:2-3) is out of scope. It is a separate devtools lifecycle task owned by the orchestrator.

Acceptance (unit tests, temp dirs and temp git repos, driven through the real CLI entry point):
- A-1 For each R-3 condition, a fixture where only that condition fails -> kept, with the named reason. All conditions pass -> removed, and the candidate commit is still reachable.
- A-2 Foreign and ambiguous dirs are kept: an unparseable name, a valid name without a record, a symlink to a referenced dir, a dir in another Authority's root, a path with `..`, a planner checkout, a record of unknown schema, and an unreadable record.
- A-3 Use a valid failed recoverable predecessor and its confirmed successor, without rewriting the predecessor's recoverable flag. A running, pending or recoverable leaf keeps both dirs. An integrated leaf with a reachable result.commit and matching current product_tree permits removal. An outstanding gate or qualification reference to either dir keeps both.
- A-4 Changed candidate: a tracked edit, an untracked new file and a deleted file after export -> kept for each.
- A-5 Dry-run is read-only (snapshot equal). If records change between dry-run and confirm (e.g. a resume starts), the changed item is kept.
- A-6 Crash mid-removal -> rerun reconciles. After cleanup, home/status/run view load and show R-5's text (reload test).
- A-7 Parameterize a child process whose cwd is in the worktree or its per-run dir: both dirs are kept.
- A-8 Base failure: `zplan cleanup` through cli.main on base fails at an observable assertion (an unknown command is refused); the safety tables run on the candidate. Report named failures and skips separately.

Size: about 500-800 changed lines including tests, above the ~500-line review trigger. Kept together because ownership, lineage and the removal protocol are one safety decision; a split would ship either an unsafe remover or a list-only command with no result.

DoD:
- Unit tests pass.
- USER_FLOW.md, REFERENCE.md and docs/INSTALLATION.md (disk section) updated.
- Receipt.
