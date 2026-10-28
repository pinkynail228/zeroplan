# Release 0.4.0 preparation

Status: accepted plan (2026-10-15; critic rel04: GO WITH CHANGES, 7 applied; rescoped by the plan reset 2026-10-16 (owner; critic plan-reset GO WITH CHANGES): G2/G3 and `/2` -> 0.5, no owner-run steps). Release = U4 in docs/TUI_PLAN.md. Until G3 exists the release gate below is run by the
orchestrator by hand and argued with the critic; from G3 on it is zplan's own merge gate in release mode.

## Scope

| Item | State | Needed for 0.4.0 |
|---|---|---|
| G1a process profile core | merged 06be0e1 | yes |
| G1b-core argued plan gate | merged 2026-10-16 (8d67fb5) | yes |
| G1b-override owner override with reason | merged 2026-10-16 | yes |
| Critic accumulated-diff review (replaces owner review #2): fresh sol xhigh session, `a09b1b9..<named candidate SHA>`, incl. packaging/pyproject.toml | done (critic accum, 2026-10-17) | yes |
| U3b chat on the process service | merged 2026-10-18 (496f046) | yes |
| G2 task gate + amendment barrier | moved to 0.5 | no |
| G3 checks + merge/release gate + derived truth | moved to 0.5 | no |
| Preset `zplan.default/2` + migration: an owner-accepted settings diff (`task`/`merge`: off -> required, other settings kept), accept / later / crash-safe | moved to 0.5 | no |
| dogfood-polish run by the orchestrator through zplan on a clone | merged 2026-10-19 (7bab467) | yes |
| Toolchain Zeroshot 10.12.0 / Codex 0.162.1 | done: default since tc1012 (40ebf9f, 2026-10-16) | decision below |
| P0 public disclosure scope | open | blocks any public show; not the private tag |

## Toolchain decision

10.12.0 (published 2026-10-15) adds local folders/generic Git transport (`--cwd`, folders without Git) and checkpoint
error detail. It touches the run source contract zplan submits, so it is not a drop-in.
Proposal: right after G1b merges, qualify it on the Linux host and activate it in its own small change before U3b, so
U3b is built and qualified on the toolchain 0.4.0 ships. If it fails, 0.4.0 ships on 10.11.0 and the finding goes
to STATE `Open`.
- Qualification before activation (Linux host; native qualification never on macOS, AGENTS.md): the candidate script
  (`devtools/toolchain-candidate.py`: installed tests + driver_qual) plus `plan_qual.py` (G1b planner graph) and the
  architect initial/resume/forced-write check for the new Codex (tc1012: the Linux real-provider part is replaced by a
  provider-free Linux sandbox check plus the Mac real-provider check, the provider refuses the Linux host; critic tc1012
  merge, devtools/zeroshot/tasks/tc1012-upgrade.md); then the Mac real-provider smoke, run by the
  orchestrator on a clone with isolated stores (commit, wheel hash, toolchain, commands, results, frames/log/spend
  saved outside /tmp).
- Activation: new tool directory (`tools/zeroshot-10.12.0-codex-0.162.1-*`), all three platform SHA256, Codex
  `package.json`/lockfile; the 0.3.1 app and its tool directory stay untouched.
- Freeze from activation: any later toolchain change re-qualifies every affected component.

## Release gate (checklist)

Each line has a command and a recorded result in the release receipt. The receipt pins one immutable candidate:
commit/tree, wheel SHA256 and toolchain. Fixes after any step (incl. review #3) produce a new candidate and repeat
the affected steps; the tag points at the qualified candidate.

1. Versions: `pyproject.toml`, `__version__`, `install.py` `VERSION` = 0.4.0; `OWNED` keeps 0.3.1.
2. Wheel contents: `zplan.tcss`, `resources/*.json` present (build the candidate wheel, list it, record its hash).
3. Suites: macOS (`python3.13`, wheelhouse) and Linux (`devtools/linux-test.sh`) full green.
4. Native qualification on Linux: `driver_qual.py` all scenarios, `plan_qual.py`.
5. PTY walkthrough against the installed candidate (installed mode of `devtools/ux_walkthrough.py` without
   `PYTHONPATH=ROOT`, ux_walkthrough.py:106; the receipt shows the import path of `terminal_planner`).
5b. Boundary qualification: the lifecycle tests (devtools/zeroshot/tasks/rel04-lifecycle-guard.md A-1-A-4: direct
   owner guard in every ACTIVE state, the four-caller set, approve/override digest cases) and the fixture tests
   (rel04-fixture-scope.md A-1-A-3: startup/chat refusal, empty/invalid fixture ids, profile init and reopen) pass
   against the installed candidate, without checkout imports. Record commit, wheel SHA256 and imported product paths.
   Added after the step-11 review of c242370 (BLOCK; class audit rel04-classes; scope trimmed by critic
   rel04-pushback). The full boundary gate (all entry points and effect sinks) is a 0.5 release step.
6. Upgrade 0.3.1 -> 0.4.0 on macOS with saved 0.3.1 state containing: an approved v1 plan, a finished milestone, an
   unmerged result and a detached/uncertain submission bound to the old toolchain, a project without
   `zplan.process.json` (bootstrap shown once), a project on `/1` (stays on `/1`, no migration offered; frozen
   records unchanged). Rollback is checked on a saved copy of the
   pre-upgrade state only: 0.4.0 writes records 0.3.1 cannot read (planner output schema "2"), so two versions never
   share one store; docs/UPGRADE.md says so.
7. Fresh install on Linux from the candidate commit (`install.py`, `zplan setup`, `zplan doctor` all OK).
8. Real-provider full journey with the installed candidate on a clone of the owner's project (never the original):
   run by the orchestrator: profile accept -> argued plan -> milestone -> orchestrator qualification + critic ->
   merge; frames; spend recorded.
9. Release verdict: the orchestrator's qualification of this checklist and a critic release verdict over the
   receipt (no zplan release-mode gate in 0.4). Any change of the checked artifact invalidates that verdict.
10. Docs current: README, docs/USER_FLOW.md (TUI screens, process journey), INSTALLATION, UPGRADE (0.3 -> 0.4, no
    shared store with 0.3.1), REFERENCE; this file moves to the private archive with the receipt.
11. Release review (replaces owner review #3): a fresh critic session over the full release diff; findings closed
    or accepted.
12. Order: qualification -> release review -> critic release verdict over the receipt -> merge (owner go given in advance for the private tag, ORCHESTRATOR.md section Owner),
    tag `v0.4.0` on the candidate, push.

## Can start now (no product code)

- P0 audit (read-only): secrets/history scan, mentions of private projects/hosts in tracked files and history,
  provenance of the private archive (prototype/, reference/, docs/history/); proposal for public scope (export vs. cleanup).
- Release receipt template and the saved 0.3.1 upgrade state for step 6.
- Installed mode for `devtools/ux_walkthrough.py` (step 5).
- Toolchain contract reading for 10.12.0 (release notes, CLI/graph diff) without touching `upstream/` during runs.
