# Upgrading zplan and its toolchain

One zplan release pins exactly one qualified toolchain: Zeroshot, Codex and restic versions, the archive SHA256 of
each supported platform and the bundled Codex lockfile. They live in one place,
[`terminal_planner/toolchain.py`](../terminal_planner/toolchain.py) (`DEFAULT`); the tool directory name
(`tools/zeroshot-<zeroshot>-codex-<codex>-<runtime>/`) is derived from it. There is no registry of several versions,
no capability flags and no auto-discovery: a new Zeroshot is a new zplan release.

`zplan doctor` prints the active toolchain (versions and tool directory) in the `Toolchain:` line right after its header.

## For users: update zplan

`zplan update` fetches the newest release tag of https://github.com/pinkynail228/zeroplan (or of
`ZPLAN_REPOSITORY` when set) and installs it through that release's own `install.py`, then runs `zplan setup`:

```sh
zplan update            # newest release; the old app and a store copy stay on disk
zplan update --check    # only prints the installed and the newest version
```

An install older than 0.7.0 looks for releases in its earlier repository; move it once with
`ZPLAN_REPOSITORY=https://github.com/pinkynail228/zeroplan.git zplan update`.

Close zplan before updating; nothing checks for a running process. `zplan update` runs `zplan setup` for the new
release, so Node.js ≥ 16 with npm must be on PATH (docs/INSTALLATION.md, Prerequisites). The new version gets
its own `app/<version>/` venv next to the old one. Older app directories are never touched, and the `zplan`
launcher moves only after the new venv reported its version. When the launcher moved from another owned version,
the installer first copies the
store (`production/v3`) to a sibling `v3.backup-<old version>-<UTC timestamp>` and prints that path together with
the previous app directory — the two rollback targets; a failed copy stops before the launcher moves. A re-run for
the version already installed is a no-op. The one-command install (`install.sh`) runs the same `install.py`, so it
updates in place too.

Without the network, or to pin a checkout by hand:

1. Get the newer tag in your clone: `git -C zeroplan fetch --tags && git -C zeroplan checkout <tag>`, then
   `cd zeroplan`.
2. `python3 install.py` (or `python3 install.py --wheelhouse DIR` offline). The same venv, backup and launcher
   steps as `zplan update`.
3. `zplan setup`. When the release changed the toolchain, the new tools are installed into **their own** directory
   next to the old one (checksum verified, atomic); an installed tool directory is never modified or replaced.
4. `zplan doctor` shows the new toolchain.

State (plans, run records, worktrees, native Zeroshot state, credentials) is not migrated or rewritten.

**0.6.x / 0.7.0 users who copied `auth.json`.** Earlier docs let you copy `~/.codex/auth.json` into zplan's Codex home
(`~/.local/share/planning-kit/codex-home/`). Delete the copy: `rm ~/.local/share/planning-kit/codex-home/auth.json`
(with `$XDG_DATA_HOME` set, use that directory), then run `zplan login`. A refresh token is single-use, so two copies
break each other on the first refresh, and a login or logout in the copy revokes your own `~/.codex` session.
`zplan doctor` blocks, and `zplan login` / `zplan logout` refuse, while a copy (or a symlink) is there.

**Work in flight.** Finish or integrate running milestones and approved plans before updating when you can. When you
did not, records bound to the older toolchain still load, show and are observed through *their own* executable and
state root, as long as that executable still exists with the recorded sha256 (the older tool directory is kept).
New plan revisions and new attempts always bind the current toolchain. When the recorded executable is gone or
changed, the action stops with `toolchain.mismatch` and nothing in the record is rewritten; choose one:

- finish it on the older zplan (see Rollback), or
- start over from a new plan revision on the current toolchain.

**Rollback.** Restore the store copy the installer printed over `production/v3` and point the launcher at the older
app, which keeps its own tool directory:

```sh
# macOS: ~/Library/Application Support/PlanningKit/production; Linux: ~/.local/state/PlanningKit/production
rm -rf "<production>/v3" && mv "<production>/v3.backup-<old version>-<UTC timestamp>" "<production>/v3"
ln -sfn ~/.local/share/planning-kit/app/<older>/bin/zplan ~/.local/bin/zplan
```

With `$XDG_DATA_HOME` or `$ZEROSHOT_TOOLS` set, use those directories instead of `~/.local/share` and `~/.local`.

Older tool directories and app directories are never deleted by a newer install; remove them by hand when you no
longer need them.
A store written by a newer zplan is not readable by an older one (0.4.0 adds planner output schema "2" and process/gate records that 0.3.1 rejects), so rollback across 0.3.1 -> 0.4.0 is only to a copy of the store saved before the upgrade, never to the store 0.4.0 has used.
0.5.0 keeps using that store (`production/v3`) and writes live records 0.4.0 cannot read, so rollback across
0.4.0 -> 0.5.0 works the same way: restore a copy of the store saved before the first 0.5.0 start and point the
launcher at `app/0.4.0`.
0.5.1 changes no store or record format: 0.5.0 and 0.5.1 read and write the same store (`production/v3`), so an
upgrade or a rollback between them needs no store copy, even though the installer still copies it to
`v3.backup-0.5.0-<UTC timestamp>` before the launcher swap.
0.5.2 writes records 0.5.1 cannot read (a planner revision's `live.steps`, the stop request `stop` and the plan
status `stopped`), so rollback across 0.5.1 -> 0.5.2 is only to the `v3.backup-0.5.1-<UTC timestamp>` copy the
installer made before the launcher swap, never to the store 0.5.2 has used; then point the launcher at `app/0.5.1`.
0.6.0 adds store records 0.5.2 was not built for (the event feed, parallel attempts): roll back across 0.5.2 -> 0.6.0
only to the `v3.backup-0.5.2-<UTC timestamp>` copy, then point the launcher at `app/0.5.2`.
0.5.x runs on Zeroshot 10.12.0 and cannot read a run record that carries the 10.16.0 failed-terminal `context`, so a
rollback from 0.6.0 to 0.5.x that keeps the current store works only while no run record has written one; otherwise
restore the store copy the installer made before the 0.6.0 launcher swap.
0.5.x cannot read plans whose tasks carry a `brief` (0.6.0 planners write one on every task); roll back only without them.
0.8.0 changes no store or record format; it makes the interface English only. A language stored in `ui.json` as `"ru"` (or `"zh"`) is not an error: it falls back to English, and the file is left as it is. History written by earlier versions stays as it was written: Russian chat turns, event rows and cards in an existing store are still read and shown in Russian, only new text is English.
0.8.1 changes no store or record format; a new project's proposed profile is the preset `zplan.default/3` (the worker on `gpt-6.1-terra` at effort max). Profiles that name `zplan.default/1` or `/2` resolve as before.

## For the maintainer: qualify and ship a new toolchain

Nothing activates a candidate automatically; the default changes only by an edited `toolchain.py` in a release.

1. **Compare the contracts.** Check out the candidate's upstream tag (`v<zeroshot>`) and read what changed since the
   current default's tag: CLI (`run`, `watch`, `status`, `resume`, `force-stop`, `logs`, `list`), the graph schema,
   built-in worker templates (`builtin.agent.*@N`), the policy (`policy.native-v2@1`), the graph profile and runtime
   config. The script below diffs the same things mechanically; reading the release notes is still yours.
2. **Run the candidate script on the Linux host** (native qualification runs there, not on macOS; the macOS run below
   is an optional install/contracts check). It installs the candidate into a scratch data root
   and a short isolated native state root, never into the production directories:

   ```sh
   # macOS (archive SHA256 of this platform's release asset; --upstream is the candidate's tag checkout)
   python3 devtools/toolchain-candidate.py --zeroshot <V> --sha256 <HEX> --upstream <checkout>
   # Linux host (`--py` runs a script from a fresh copy of the checkout; paths are host paths;
   # ZPLAN_TEST_TIMEOUT lifts linux-test.sh's default 30-minute cap; a full qualification takes longer)
   ZPLAN_TEST_TIMEOUT=10800 devtools/linux-test.sh --py devtools/toolchain-candidate.py --zeroshot <V> --sha256 <HEX> --upstream <host checkout>
   ```

   When the candidate also moves Codex (or restic), add `--codex <V> --codex-package <DIR>` (a directory with the
   candidate's `package.json` and `package-lock.json`) and `--restic <V>`; `--archive FILE` installs from a local
   archive (the checksum is still verified); `--url-template` overrides the release URL.

   Steps, each `PASS`/`FAIL`/`WARN`: **quiescence** (the production store is read, read-only: unknown or active
   intents, recoverable failures, unmerged results and unfinished approved plans stop the run unless
   `--keep-old-app`, which qualifies anyway because the older app and tools stay in use), **install**, **contracts**
   (flags zplan passes still exist in the candidate's `--help`; every profile/policy/built-in worker identifier the
   graphs send occurs in the upstream checkout; the checkout is on `v<V>`), **installed** (`tests.test_install`,
   `tests.test_milestone` against the candidate binary) and **driver** (`devtools/driver_qual.py` scenarios).
   The overall line is `RESULT: PASS` only without any `FAIL`. A failed qualification leaves the default intact; the
   scratch directory is removed (`--keep` keeps it for inspection).
3. **Mac real-provider smoke.** After bumping `DEFAULT` on a branch and installing it (`zplan setup`): one real plan and one real milestone
   on a disposable project (a clone with isolated stores), run by the orchestrator. Tests use deterministic fixtures; this is the first real-provider check.
4. **Bump** `DEFAULT` in `toolchain.py`: versions, all three platform archive SHA256 (`Linux x86_64`,
   `Linux aarch64`, `Darwin arm64`), and `terminal_planner/resources/package.json` + `package-lock.json` for a new
   Codex (a test fails when the lockfile and `codex` disagree). Any change to the bundle's content that keeps the
   versions (restic, lockfile, layout) needs a new `runtime` tag: a bundle is never replaced in place.
5. **Release.** Bump `__version__`, `pyproject.toml` and `VERSION` in `install.py` (append the previous version to
   `OWNED` there so its launcher stays ours), run the full suite (`devtools/linux-test.sh`), then tag a patch release.
   Update README/INSTALLATION paths that show the tool directory name.
