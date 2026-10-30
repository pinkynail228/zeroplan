# zplan reference

Every command, flag, key, state and error code of zplan. The tables below are generated from the code
(`python -m terminal_planner.catalog --write docs/REFERENCE.md`) and a test fails when they drift; the
sections around them are written by hand. For the first run read README.md; for screen-by-screen behaviour
read USER_FLOW.md.

Contents: [How the pieces fit](#how-the-pieces-fit) · [Lifecycle](#lifecycle) · [Commands and flags](#commands-and-flags) ·
[Screens and keys](#screens-and-keys) · [Plan statuses](#plan-statuses) · [Milestone states](#milestone-states) ·
[Run statuses, outcomes and delivery](#run-statuses-outcomes-and-delivery) · [Error families](#error-families) ·
[Worked examples](#worked-examples)

Help is available offline and without a project: `zplan --help`, `zplan help <command>`, `zplan <command> --help`,
and `?` on any screen lists that screen's keys. None of them needs tools, a login, a Git project or a model.

## How the pieces fit

| Piece | What it is | Who owns the truth |
| --- | --- | --- |
| zplan | This terminal client: screens, keys, help. | Nothing durable except the planning record below. |
| Zeroshot | The native engine that runs the planner and the milestone graphs. | Run lifecycle: submitted, running, finished, failed, stopped. |
| Codex | The model CLI Zeroshot drives; its login lives in `CODEX_HOME`. | Provider access. |
| `planning.json` | zplan's locked record: goal, plan revisions, approval, milestone run records. | The plan status and run records below. |
| Git project | The repository you open zplan in (or `--project`). | Branches, worktrees, the merged result. |

zplan never decides run lifecycle itself. It submits, watches and reconciles; after an interruption it asks
Zeroshot what happened (`[g]`) instead of submitting again. At autonomy `manual` a model never runs unless you
approve it; at `auto` and `supervised` zplan starts runs itself. `--fixture` replaces the engine with a deterministic demo that spends no tokens.

### Pinned tools versus global installs

`zplan setup` installs its own Zeroshot and Codex into a versioned directory under the zplan data directory
(hash-checked). zplan only ever runs those pinned copies; a `zeroshot` or `codex` found on `PATH` is neither
used nor modified, and removing the pinned directory does not touch a global install. `readiness.tools` and
`readiness.codex` report the pinned copies as missing or damaged; `[u]` or `zplan setup` repairs them.

### CODEX_HOME resolution

The Codex login and config live in the effective home: `$CODEX_HOME` when set (your own Codex, an explicit
opt-in), otherwise zplan's own `codex-home/` under its data directory. zplan logs in and out only of the home it
owns, that is, its own `codex-home/` (the same real directory, however it is spelled). `zplan login` there keeps an
existing login (`codex login status` first) and otherwise runs the device login; `zplan logout` there runs
`codex logout`, and is refused while a run or the architect is live in that home. In any other home `zplan login`
and `zplan logout` run no Codex: they answer «This is your Codex (<home>): log in via codex login» and exit 0 when a
login is there, else 1. `zplan doctor` prints which home is in use (`readiness.codex_home`, `readiness.auth`).
zplan never prints, copies or logs credentials (it compares digests of `auth.json` files locally to detect a
copy, reading out no value), and never copy `auth.json` between homes: the refresh token is
single-use, so a copy breaks the other login on its first refresh. A private `auth.json` that is a symlink, not a
regular file or byte-equal to `~/.codex/auth.json` blocks login, logout and doctor with «remove the copy: rm <path>».

### Project readiness

Before anything is sent, the project must pass the readiness checks (`readiness.*` in
[Error families](#error-families)): a Git repository with a commit, a branch (not a detached HEAD), a GitHub
`origin` and a Git identity. Uncommitted changes never block: the planner, the checks and the runs work on the last
commit, and the `clean` item only says how many files it does not hold. Each failing item names its fix; `[g]` on the
settings screen re-checks.

Each model action needs only the checks it uses: sending a plan to the planner needs the pinned tools, login,
Git repository, branch and `origin` (no Git identity: the planner commits nothing); starting a
milestone attempt adds the Git identity; resuming an attempt needs the same (the work is in the attempt's own
worktree). The `--fixture` engine needs no tools, login or `origin`. Actions that
need the milestone driver stop with `readiness.tools` (`[u]` or `zplan setup`) while the pinned tools are missing
or damaged. Quitting the TUI (`Ctrl+Q`) never cuts a mutating job (a submission, start, merge or setup): the
screen says it is finishing and the shell exits when the job ends; only a watch slice is cut.

### Plan revisions

A goal produces a plan *revision*: `proposed` until you approve it with `[a]`. `[r]` asks for a new
revision instead of editing the old one, and a revision records the tree it was made from. If the project
(or the Zeroshot the plan was prepared for: another toolchain, a rebuilt binary, another state directory)
changed since, the plan fails with the `plan.stale` error (the revision stays planning or proposed): an unsent plan is rebuilt and sent by `[g]` once readiness passes (`[n]` only prepares it); a proposal is re-planned with `[r]`. Approval is bound to one revision;
milestones are attempted only from an approved one.

A plan is *argued* before it reaches you. One revision freezes, once, at creation: the roles, `plan_rounds`, the
rules files (bytes and hashes) and the digest of the resolved configuration; everything the run then uses is built
from that snapshot, and a frozen rule file that no longer matches is refused before dispatch (`engine.intent_changed`).
The planner and the `critic` run as one graph (planner graph 2): the critic keeps one provider conversation across
the rounds, rejects with findings, the planner repairs or disputes with a reasoned reply, and the loop ends at the
first acceptance or after `plan_rounds` rounds (exhausted = rejected, `review_exhausted`). The critic reports the
cumulative discussion `{"version": 1, "rounds": [{"round", "verdict", "findings", "response"}]}`; zplan accepts it only
when the rounds are contiguous from 1, at most `plan_rounds`, every non-final verdict is `rejected`, each text is at
most 4000 characters, the whole at most 32 KB, and the last round equals the signalled verdict, findings and reply
(otherwise `proposal_invalid`, no evidence). The terminal output schema is `"2"`: schema `"1"` plus `planResponse`
and `discussion`; revisions created before this version stay version 1 and keep reading schema `"1"`.
The discussion is as the critic reported it: zplan validates its shape and that the final round matches the signalled
result, not that earlier rounds are unchanged.

The revision's evidence carries the gate: `gate` (`plan`), `artifact_digest`, `resolved_config_digest`, `head`,
`rounds_used`, `rounds_limit`, `discussion` and `critic_verdict`. `[a]` needs `critic_verdict == accepted`, and is
refused (`plan.gate_stale`, «the check is out of date») when the live resolved configuration digest differs from the gate's:
the profile, roles or a rules file changed after the critic accepted. Nothing is written by the refusal; `[r]` plans
again under the current configuration. The rules reach the planner and the critic in the listed order, with lower
priority than the task and graph mechanics.

A `review_exhausted` revision of execution version 2 can be approved by the owner anyway (`[o]`,
`plan.override` / `tui_plan.override`; no CLI command) with a typed reason: the stripped text, one printable line,
10 to 500 characters. One locked transition makes the revision `approved` under the same conditions as `[a]`
(fresh baseline `plan.stale`, live configuration digest `plan.gate_stale`, bounds, native prepare) except that
`critic_verdict` must be `rejected`; anything else is refused (`action.refused`) and writes nothing. The revision
gets an optional field `override = {"reason", "verdict": "rejected", "evidence_digest"}`; the evidence stays
byte-identical, `approval` also binds the override, and validation accepts `approved` with verdict `rejected`
only with a matching override. A record without `override` keeps its approval digest and bytes. The plan is then
shown as `approved despite the check` next to the unchanged rejected verdict.

### Milestone attempts

Each milestone is run as one Zeroshot run, an *attempt*. A failed or blocked attempt is never edited: `[t]`
starts a new attempt (numbered `a1`, `a2`, ...), `[g]` continues a `failed_recoverable` run in its worktree.
Up to 3 attempts may run per project at a time, with disjoint write-sets.

### Worktrees and branches

Every attempt gets its own Git worktree under `<data dir>/worktrees/` and a working branch
`zplan-work/<plan>/<milestone>/a<N>` inside your repository. A finished attempt publishes a result branch
`zplan/<milestone>-r<revision>-<approval>-a<N>`. zplan's control files (`.zplan/`) stay in the worktree and
are never exported. Your checked-out branch and working tree are never written by an attempt.

### Merge

`[m]` on an `awaiting_merge` milestone shows the diff and, after confirmation (`[y]`), merges the result branch into
the destination branch. Both merge paths build the merge commit off your tree (`git merge-tree --write-tree` and
`commit-tree` under your Git identity; Git 2.38 or newer, `zplan doctor` checks it) and land it with `merge --ff-only`.
A conflict is recorded from `merge-tree` (`milestone.conflict` family, with its files) and your tree is never written, so
no abort runs; to resolve it, merge the result branch by hand, commit, and reopen zplan. Uncommitted changes do not block
a merge: right before landing zplan lists the paths the merge changes (`diff --no-renames --name-only HEAD <merge
commit>`) and refuses (`milestone.merge_overlap`, one card naming the paths, «merge later» keeps the branch, «show the
differences») when one of them, or a parent of one, exists in the project as untracked, ignored or modified -- your local
ignored `.env` is never overwritten. If your set of uncommitted changes differs right after the landing from right before
it, the merge stays landed and the run records it; zplan never resets or checks out. While a merge is unfinished in the
project (`MERGE_HEAD`) every `[m]` is refused (`milestone.merge_refused`): finish it or run `git merge --abort`.
With `gates.merge: required` the merge first builds a candidate commit (the message carries a `Checks:`
line), runs the profile `checks` on exactly that commit, and only if they pass and HEAD and the profile are unchanged
fast-forwards the destination to it (`merge.checks_failed` otherwise). The evidence is kept in the run's `gate` record.

### State and data directories

| Directory | Holds | Safe to delete? |
| --- | --- | --- |
| `~/.local/share/planning-kit/app/<version>/` | The zplan application venv. | Yes, after finishing runs; reinstall to restore. |
| `~/.local/share/planning-kit/tools/` | Pinned Zeroshot and Codex. | Yes; `zplan setup` restores it. |
| `~/.local/share/planning-kit/codex-home/` | zplan's own Codex home: its login and `config.toml` profile. | Only if you accept logging in again. |
| `~/.config/planning-kit/roles.json` | Role defaults (model, effort). | Yes; defaults return. |
| `.../PlanningKit/production/v3/<project>/planning.json` | Plans, approvals, run records (macOS `~/Library/Application Support`, Linux `~/.local/state`). | No: this is your plan history. |
| `.../PlanningKit/production/v3/<project>/process-state.json` | Whether the project's process profile was accepted or postponed ("later"), with the snapshot a postponed profile uses. Written under the same project lock as `planning.json`. | Yes; the profile is offered again. Plans and runs are untouched. |
| `~/.local/share/planning-kit/worktrees/` | Attempt worktrees. | Only when no milestone is running; unmerged results then vanish. |
| `~/.zp/` | Native Zeroshot state (`runs/`, `config/`), kept short for socket paths. | Not while a run is active; history is lost. |
| fixture state (`--fixture`) | Demo runs in an isolated namespace. | Yes. |

Paths follow `$XDG_DATA_HOME` / `$XDG_CONFIG_HOME`; docs/INSTALLATION.md has the full table.

### Process profile

`zplan.process.json` in the project root holds the process profile: which models work in which roles, which review
gates apply, the review limits and the test commands. It is tracked in Git, so a team shares one profile. Without
one, zplan proposes a profile on the first start in the project and asks to accept it (`[a]`, writes the file; commit
it) or postpone it (`[l]`, nothing is written into the project and the header says «profile not saved»).
`zplan profile` prints the resolved profile with the source of every key; `zplan profile init` writes the proposed
file without asking and refuses when one exists.

| Key | Type | Allowed values | Acts in this version |
| --- | --- | --- | --- |
| `preset` | string | `zplan.default/1`, `/2` or `/3` (each frozen once shipped; a change arrives as a new version). `/3`, the one a new profile gets, defaults the worker to `gpt-6.1-terra` at effort `max` and every other role to `gpt-6.1-sol` high; `/1` and `/2` keep `gpt-6.1-sol` for every role | Names the defaults for every key you omit. |
| `roles` | object | keys `planner`, `critic`, `worker`, `reviewer`, `steward`, `architect`; each `{"model": ..., "effort": ...}` with effort `low`, `medium`, `high`, `xhigh` or `max` | Yes: feeds the role preferences of every new plan revision and milestone attempt. `critic` is the former `plan_verifier`; `architect` sets the model and effort of each architect chat turn (the full-screen chat re-reads the role before every turn). Existing revisions and attempts keep the roles they were frozen with; restart, revise, a new attempt, an answer and an accepted proposal take the file's current roles. |
| `gates` | object | keys `plan`, `task`, `merge`; each `required` or `off` | `plan` must be `required`: the critic reviews every plan and approval needs its acceptance. `task` is accepted, but `required` blocks milestone start with a named refusal (`process.unbuilt`) until the gate exists. `merge: required` gates the merge (see `checks`); `off` is shown as «no check». |
| `limits` | object | keys `plan_rounds`, `task_rounds`, `merge_rounds`; integers 1–10, `plan_rounds` 1–5 | `plan_rounds` is the number of plan–critic rounds a new plan revision may use; it is frozen into the revision with the rules and roles (preset `zplan.default/1` keeps 3). `task_rounds` bounds the repair rounds of every task review loop of a milestone run from that revision: the loop runs one implementation pass plus `task_rounds` repairs (preset `zplan.default/1` keeps 2, so 3 iterations); it is frozen into the revision like `plan_rounds`, and a milestone built without a frozen profile keeps the fixed 4. `merge_rounds` is stored and shown only. |
| `rules` | list of strings | at most 8 relative paths of existing files inside the repository (no `..`, no absolute paths, at most 256 KB each) | Yes, for planning: the files' content reaches the planner and the critic in the listed order, below the task and graph mechanics, and is frozen into each plan revision; the total is limited to 64 KiB (`process.invalid` names the file to shorten). The digest covers the content of each file. |
| `checks` | list of objects | at most 8 of `{"name", "argv", "timeout_s"}`; `argv` is a non-empty list of strings (no shell), `timeout_s` an integer 1–86400 (default 1800) | Run only by the merge gate (`gates.merge: required`): in order, in a disposable checkout of the exact candidate commit that will land, stopping at the first failure; with `gates.merge: off` they are stored and shown «for later stages» and nothing is executed. An empty list is shown as «no qualification»; with the merge gate required it refuses the merge (`merge.no_checks`). |

All keys are optional. Precedence per key: the project file, then the bindings saved in
`~/.config/planning-kit/roles.json` (`roles` only), then the preset. Unknown keys, wrong types, unknown role or gate
names and an empty `argv` are refused with the key named (`process.invalid`). The digest shown by `zplan doctor` and
`zplan profile` covers the resolved values and the content of every rules file. With a project file `zplan roles`
only shows the roles (they live in the file).

```json
{
  "preset": "zplan.default/1",
  "rules": ["AGENTS.md"],
  "roles": {"worker": {"model": "gpt-6.1-terra", "effort": "max"}},
  "gates": {"plan": "required", "task": "off", "merge": "off"},
  "limits": {"plan_rounds": 3, "task_rounds": 2, "merge_rounds": 2},
  "checks": [{"name": "unit", "argv": ["npm", "test"], "timeout_s": 1800}]
}
```

Profile states of a project (shown by `zplan doctor`, `zplan profile` and Settings):

| State | Meaning | New plans and milestones | Watching, stopping, export |
| --- | --- | --- | --- |
| `never` | Neither accepted nor postponed; the proposal (or an existing valid file) is shown on the first start. | Allowed with the proposal's values, frozen like a chosen profile; nothing is written to the project until you accept. | Work. |
| `later` | Postponed: the snapshot of the shown proposal, stored outside the project, is used; header «profile not saved». If the file appears it is accepted. | Allowed with the snapshot values. | Work. |
| `accepted` | `zplan.process.json` is present and valid; the decision is recorded in `process-state.json`. | Allowed with the file's values. Edits are picked up before the next submission or start; a change between a preview and its confirmation is refused and shown again (`process.changed`). | Work. |
| `missing` | The accepted file was deleted or the branch lacks it. | Refused with the fix (`process.missing`). | Work. |
| `malformed` | The file is not valid JSON or fails validation. | Refused with the key named (`process.invalid`). | Work. |

A damaged `process-state.json` is refused with the file named (`process.state`); delete it and the profile is
offered again. A crash between writing `zplan.process.json` and recording it is finished on the next start.

## Lifecycle

```
goal ──[g]──▶ planning ──▶ observing ──▶ proposed ──[a]──▶ approved
                │               │            │ [r] revise      │
                │               ▼            ▼                 ▼
                │         run_failed /   (new revision)   milestone: waiting ─▶ ready
                │         proposal_invalid /                                      │ [g]
                ▼         review_exhausted                                        ▼
        submission_unknown / detached                   running ──▶ awaiting_merge ──[m]──▶ integrated
        / observation_blocked ──[g]/[w]──▶ observing        │              │ conflict
                                                            ├─▶ needs_owner / blocked ──[t]──▶ new attempt
                                                            ├─▶ failed_recoverable ──[g]──▶ same attempt
                                                            ├─▶ failed / stopped ──[t]──▶ new attempt
                                                            └─▶ unknown / stopping ──[g]──▶ reconciled
```

A plan revision moves through the plan statuses; once approved, each milestone has its own view state and
its runs have a native status, an outcome and a delivery state. All of them are listed below.

## Commands and flags

<!-- BEGIN GENERATED: commands -->
| Command | Usage | Purpose (as in `--help`) | Meaning |
| --- | --- | --- | --- |
| `zplan` | `zplan [--plain] [--project PATH]` | open the plan and milestones of the current Git project | Opens the plan and milestones of the Git project in the working directory (full-screen on a terminal, line-oriented otherwise). |
| `zplan status` | `zplan status [--project PATH]` | show the home screen once, without prompts | Prints the home screen once (no prompts, no escape codes, nothing dispatched). |
| `zplan setup` | `zplan setup` | install the pinned Zeroshot and Codex into zplan's data directory | Installs the pinned Zeroshot bundle and Codex into zplan's data directory (checksums verified, no model call). |
| `zplan doctor` | `zplan doctor [--project PATH]` | check readiness: tools, login, Git, project | Prints the Toolchain line (versions, tool directory), then one line per readiness check; exit status 0 only when everything is ready. |
| `zplan login` | `zplan login` | log in to Codex (device auth) in zplan's own directory | Runs the installed Codex device login in zplan's own Codex home (a login that is already there is kept); in a CODEX_HOME of yours it runs nothing; zplan never reads credentials. |
| `zplan logout` | `zplan logout` | log out of Codex in zplan's own directory | Runs codex logout in zplan's own Codex home only; refused in a CODEX_HOME of yours, for a copied auth.json and while a run or the architect is live there. |
| `zplan update` | `zplan update [--check]` | update zplan to the newest release | Fetches the newest release tag and installs it (the old app and a store backup stay for rollback); --check only reports the versions. |
| `zplan roles` | `zplan roles [--project PATH]` | choose the model and effort for each role | Edits the model/effort binding of each role (saved outside any project's state); with a project zplan.process.json it only shows the roles, which live in that file. |
| `zplan profile` | `zplan profile [init] [--project PATH]` | show the project's process profile or create zplan.process.json | Prints the resolved process profile with the source of each key; `init` writes the proposed zplan.process.json non-interactively and refuses when one exists. |

| Flag | Commands | Purpose (as in `--help`) | Meaning |
| --- | --- | --- | --- |
| `--plain` | (none) | line-oriented mode without the full-screen interface (also when the output is not a terminal) | Forces the line-oriented UI. |
| `--project PATH` | (none), status, doctor, roles, profile | Git project (default: the current directory) | Selects the Git project instead of the working directory. |
| `--state-dir DIR` | (none), status, profile | fixture only: root of the isolated state | Fixture state root; production overrides are rejected. |
| `--fixture ID` | (none), status, profile | isolated demo without a model; native runs are forbidden | Runs against the deterministic fixture engine in an isolated authority. |
| `--native-binary PATH` | (none), status | explicit isolated Zeroshot executable (development) | Explicit Zeroshot executable instead of the pinned private tools. |
| `--native-state-dir DIR` | (none), status, doctor | durable Zeroshot history; a short path for Unix sockets | Durable native state root (short path: Unix socket limit). |
| `--check` | update | only show the versions, change nothing (for update) | Reports the installed and the newest release without changing anything. |
| `--version` | all | show the version | Prints the version. |
| `-h, --help` | all | show help | Prints help for the command. |
<!-- END GENERATED: commands -->

## Screens and keys

Screens of the line UI and of the full-screen shell. `?` shows the keys of the screen you are on; the line
UI lists exactly the keys its menu offers at that moment.

<!-- BEGIN GENERATED: screens -->
| Screen | Title (as shown) | Meaning |
| --- | --- | --- |
| `home` | Home screen | Plan overview and milestone list. |
| `readiness` | Readiness | What is missing before a model run. |
| `bootstrap` | Process profile | First start in a project without an accepted process profile. |
| `goal` | Goal saved | After the goal text, before the planner starts. |
| `plan` | Plan | A plan revision at any status. |
| `observe` | Observation | Live view of a running attempt (type a key, then Enter). |
| `unknown` | Run: status unknown | Unconfirmed submission or an interrupted attempt. |
| `awaiting_merge` | Run: done, awaiting merge | An accepted, exported result. |
| `conflict` | Run: merge conflict | A conflicting merge. |
| `needs_owner` | Run: answer needed | The steward asks the owner. |
| `blocked` | Run: blocked | A blocked attempt. |
| `failed_recoverable` | Run: failed, can be resumed | A resumable failure. |
| `failed` | Run: failed | An unrecoverable failure. |
| `stopped` | Run: stopped | A stopped attempt. |
| `tui_input` | Full-screen mode: input line | TUI main screen, input line focused (letters are text). |
| `tui_panel` | Full-screen mode: plan panel | TUI main screen, plan panel focused. |
| `tui_plan` | Full-screen mode: plan | TUI plan screen (goal, planner progress, proposal). |
| `tui_note` | Full-screen mode: plan revision | TUI revision note editor. |
| `tui_run` | Full-screen mode: run result | TUI end-of-run modal of one milestone attempt. |
| `tui_diff` | Full-screen mode: changes | TUI scrollable diff of an exported result. |
| `tui_details` | Full-screen mode: details | TUI scrollable plan record and diagnostics. |
| `tui_attempt` | Full-screen mode: new attempt | TUI form of a new attempt of a stopped or failed milestone. |
| `tui_answer` | Full-screen mode: answer or note | TUI text editor for an answer, a new-attempt note or a plan change request. |
| `tui_confirm` | Full-screen mode: confirmation | TUI confirmation of a plan or milestone decision. |
| `tui_confirm_run` | Full-screen mode: run confirmation | TUI confirmation of a run start: “yes” is focused at once. |
| `tui_bootstrap` | Full-screen mode: process profile | TUI first-start screen of the process profile. |
| `tui_profile` | Full-screen mode: profile setup | TUI editor of the process profile: autonomy, parallel runs, the merge gate and the roles. |
| `tui_settings` | Full-screen mode: settings | TUI settings (readiness, setup log, roles). |
| `tui_help` | Full-screen mode: help | The key help overlay. |
<!-- END GENERATED: screens -->

<!-- BEGIN GENERATED: keys -->
| Screen | Key | Action ID | Label (as shown) | Hint (as in `?`) | Meaning |
| --- | --- | --- | --- | --- | --- |
| `home` | `p` | `home.plan` | plan | open the plan: describe the goal, approve or revise | Open the plan screen (goal when none). |
| `home` | `r` | `home.revise` | reconsider | revise the approved plan | Write a revision request for the plan. |
| `home` | `s` | `home.settings` | settings | model and effort of the roles | Role bindings (model/effort). |
| `home` | `i` | `home.details` | details | full record of the plan and runs, diagnostic commands | Full plan and run records, diagnostic commands. |
| `home` | `q` | `home.quit` | quit | close zplan; runs continue | Leave; runs continue. |
| `home` | `w` | `home.watch` | watch | follow the running milestone | Observe the running attempt. |
| `home` | `g` | `home.check` | check | reconcile an unconfirmed submission or stop with Zeroshot | Reconcile an unconfirmed submission/stop. |
| `home` | `g` | `home.start` | start | start a ready milestone (with a preview and a confirmation) | Start a ready milestone after a preview. |
| `home` | `g` | `home.resume` | continue | continue the same attempt after a failure (resume) | Resume the failed, recoverable attempt. |
| `home` | `g` | `home.attempt` | new attempt | start a new attempt of a stopped or failed milestone | Start a new attempt after a stop or an unrecoverable failure. |
| `home` | `o` | `home.open` | open | the end screen of a milestone that needs attention | Open the end screen of a milestone that needs attention. |
| `home` | `e` | `home.tail` | log | the last lines of the Zeroshot log (on request): a running or failed run | Show the tail of the run log. |
| `readiness` | `u` | `readiness.install` | install tools | install the pinned Zeroshot and Codex | Run setup. |
| `readiness` | `l` | `readiness.login` | log in | log in to Codex in this terminal | Run the Codex login. |
| `readiness` | `d` | `readiness.changes` | changes | show uncommitted changes (changes nothing) | List uncommitted changes; changes nothing. |
| `readiness` | `g` | `readiness.recheck` | check again | repeat the check after the fix | Re-run the readiness check. |
| `readiness` | `i` | `readiness.details` | details | instructions for each finding | Fix instructions for each item. |
| `readiness` | `q` | `readiness.back` | back | go back | Return to the previous screen. |
| `readiness` | `q` | `readiness.leave` | quit | quit zplan | Leave zplan (the first readiness screen). |
| `bootstrap` | `a` | `bootstrap.accept` | accept | write zplan.process.json and accept the profile | Accept the proposed profile (writes the file). |
| `bootstrap` | `l` | `bootstrap.later` | later | work from the proposal without writing to the project | Postpone; the snapshot is used and the header says so. |
| `bootstrap` | `q` | `bootstrap.leave` | quit | quit without deciding | Leave without deciding. |
| `goal` | `g` | `goal.start` | start the planner | check readiness and submit the goal to the planner | Check readiness, then submit the goal. |
| `goal` | `s` | `goal.settings` | settings | edit the roles before starting | Edit roles before submitting. |
| `goal` | `q` | `goal.back` | back | leave the goal unsaved and go back | Leave without saving the goal. |
| `plan` | `g` | `plan.start` | start the planner | check readiness and submit the goal; a stale unsent plan is first rebuilt on the current project; an unconfirmed submission is sent again unchanged | Check readiness, then submit the unsent revision; a stale unsent one is first rebuilt on the current project; an unconfirmed submission is sent again unchanged. |
| `plan` | `n` | `plan.renew` | prepare a new plan on the current project | the same goal on the current project state; no model is run | Prepare a new unsent revision, same goal, current project; nothing is sent. |
| `plan` | `i` | `plan.details` | details | full record and diagnostic commands | Full record and diagnostics. |
| `plan` | `e` | `plan.tail` | log | the last lines of the planner's Zeroshot log (on request) | Show the tail of the planner run log. |
| `plan` | `w` | `plan.watch` | watch | follow the planner | Watch the planner. |
| `plan` | `s` | `plan.stop` | stop planning | stop the running planner | Stop the running planner; the run is never resubmitted. |
| `plan` | `a` | `plan.approve` | approve | approve the plan; no implementation is started | Approve this revision (starts nothing). |
| `plan` | `r` | `plan.revise` | revise | write what to change and re-plan | Request a revision. |
| `plan` | `x` | `plan.reject` | decline | do not approve the proposal | Decline the proposal. |
| `plan` | `i` | `plan.requirements` | requirements and checks | the full plan: requirements, tasks, checks | Full plan with requirements and checks. |
| `plan` | `o` | `plan.override` | approve despite the check | approve a plan the check rejected; a reason is required | Approve a plan the critic rejected, with a typed reason (starts nothing). |
| `plan` | `g` | `plan.restart` | start the planner again | a new revision of the same goal | Run the planner again. |
| `plan` | `g` | `plan.retry` | check readiness and start again | check readiness and submit a new revision | Check readiness and resubmit. |
| `plan` | `l` | `plan.login` | refresh login | log in to Codex again | Refresh the Codex login. |
| `plan` | `q` | `plan.back` | back | return to the home screen | Back to home. |
| `observe` | `k` | `observe.stop` | stop | k and Enter: stop the attempt (after a confirmation) | Stop the attempt after a confirmation. |
| `observe` | `Ctrl-C` | `observe.detach` | detach | quit; the run continues | Detach; the run continues. |
| `observe` | `?` | `observe.help` | help | this help | This help. |
| `observe` | `e` | `observe.tail` | log | the last lines of the Zeroshot log (on request) | Show the tail of the run log. |
| `unknown` | `g` | `unknown.check` | check | reconcile with Zeroshot without resubmitting | Reconcile without resubmitting. |
| `unknown` | `q` | `unknown.back` | back | go back | Back. |
| `awaiting_merge` | `m` | `awaiting_merge.merge` | merge into <branch> | merge the result (merge --ff-only of the finished commit) after a confirmation | Merge the result branch after a confirmation. |
| `awaiting_merge` | `d` | `awaiting_merge.diff` | diff | show the result's changes | Show the result's diff. |
| `awaiting_merge` | `l` | `awaiting_merge.later` | later | go back, changing nothing | Leave unmerged. |
| `conflict` | `m` | `conflict.merge` | retry the merge | retry the merge (after a manual resolution) | Retry the merge. |
| `conflict` | `d` | `conflict.diff` | diff | show the result's changes | Show the result's diff. |
| `conflict` | `l` | `conflict.later` | later | go back, changing nothing | Leave as is. |
| `needs_owner` | `a` | `needs_owner.accept` | accept | accept the steward's proposal | Accept the steward's proposal. |
| `needs_owner` | `t` | `needs_owner.answer` | answer | answer and start a new attempt | Answer and start a new attempt. |
| `needs_owner` | `x` | `needs_owner.stop` | stop | leave unanswered | Leave unanswered. |
| `needs_owner` | `q` | `needs_owner.back` | back | go back | Back. |
| `blocked` | `t` | `blocked.answer` | answer and restart | answer and start a new attempt | Answer and start a new attempt. |
| `blocked` | `p` | `blocked.plan` | plan | revise the plan | Revise the plan. |
| `blocked` | `q` | `blocked.back` | back | go back | Back. |
| `failed_recoverable` | `g` | `failed_recoverable.resume` | continue | continue the same attempt in its worktree | Resume the same attempt. |
| `failed_recoverable` | `t` | `failed_recoverable.new_attempt` | new attempt | start an attempt from the current HEAD | New attempt from the current HEAD. |
| `failed_recoverable` | `p` | `failed_recoverable.plan` | plan | revise the plan | Revise the plan. |
| `failed_recoverable` | `q` | `failed_recoverable.back` | back | go back | Back. |
| `failed` | `t` | `failed.new_attempt` | new attempt | start an attempt from the current HEAD | New attempt from the current HEAD. |
| `failed` | `p` | `failed.plan` | plan | revise the plan | Revise the plan. |
| `failed` | `q` | `failed.back` | back | go back | Back. |
| `stopped` | `t` | `stopped.new_attempt` | new attempt | start an attempt from the current HEAD | New attempt from the current HEAD. |
| `stopped` | `p` | `stopped.plan` | plan | revise the plan | Revise the plan. |
| `stopped` | `q` | `stopped.back` | back | go back | Back. |
| `tui_input` | `tab` | `tui_input.panel` | panel | move to the plan panel | Focus the plan panel; with the `/` palette shown and a command prefix typed, complete the highlighted command instead. |
| `tui_input` | `up / down` | `tui_input.pick` | pick | a command in the palette or the previous line | Up/Down move the palette highlight; in an empty input they recall the owner's previous lines of this run. |
| `tui_input` | `enter` | `tui_input.send` | send | send the message to the architect as one turn | Send the typed message to the architect as one turn. |
| `tui_input` | `esc` | `tui_input.cancel` | cancel turn | interrupt the architect's turn (a milestone is not touched) | Cancel the running architect turn; a milestone keeps running. |
| `tui_input` | `/new` | `tui_input.reset` | new dialog | start a new dialog with the architect | Start a new architect session; the transcript keeps a reset entry. |
| `tui_input` | `/setup` | `tui_input.settings` | settings | open settings | Open settings. |
| `tui_input` | `/help` | `tui_input.help` | keys | help on this screen's commands | Key and command help. |
| `tui_input` | `ctrl+q` | `tui_input.quit` | quit | quit | Quit. |
| `tui_panel` | `tab` | `tui_panel.input` | input | return to the input line | Focus the input line. |
| `tui_panel` | `/view` | `tui_panel.plan` | plan | open the plan: goal, progress, proposal (with no plan — /plan <goal>) | Open the plan screen; with no plan, a note names `/plan <goal>`. |
| `tui_panel` | `/answer` | `tui_panel.answer_draft` | answer draft | open the newest answer draft of a milestone in the answer form | Open the newest actionable answer draft of the selected milestone in the answer form; nothing is submitted. A malformed identity, a still-running attempt and an end that offers no answer are refused as `draft.malformed`, `draft.active` and `draft.unavailable`, and a moved-on draft as `draft.stale`. |
| `tui_panel` | `/run` | `tui_panel.run` | start | start the selected ready milestone | Start the selected ready milestone after a confirmation. |
| `tui_panel` | `/run` | `tui_panel.resume` | continue | continue the same attempt in its worktree | Resume the failed attempt after a confirmation. |
| `tui_panel` | `/run` | `tui_panel.attempt` | new attempt | a new attempt of a stopped or failed milestone | Open the new-attempt form of a stopped or failed milestone. |
| `tui_panel` | `/run` | `tui_panel.check` | check | reconcile an unconfirmed submission or stop with Zeroshot | Reconcile an unconfirmed submission or stop; nothing is sent again. |
| `tui_panel` | `/stop` | `tui_panel.stop` | stop | stop the running run | Stop the running attempt after a confirmation. |
| `tui_panel` | `/attempt` | `tui_panel.open` | open | the end result of a milestone run; a running run is watched again | Open the end-of-run view of the selected milestone; a running attempt is observed again. |
| `tui_panel` | `/details` | `tui_panel.details` | details | result, plan, diagnostics | Outcome first, then the plan, diagnostics last. |
| `tui_panel` | `/log` | `tui_panel.tail` | log | the last lines of the Zeroshot log (on request) | Show the tail of the run log. |
| `tui_panel` | `↑↓` | `tui_panel.select` | select | select a milestone | Select a milestone row. |
| `tui_panel` | `pageup` | `tui_panel.scroll_up` | history up | scroll the chat history to the start (PgUp) | Scroll the chat history up: its oldest retained rows become reachable; nothing else changes. |
| `tui_panel` | `pagedown` | `tui_panel.scroll_down` | history down | scroll the chat history to the end (PgDn) | Scroll the chat history back down toward the newest rows. |
| `tui_panel` | `/setup` | `tui_panel.settings` | settings | open settings | Open settings. |
| `tui_panel` | `/help` | `tui_panel.help` | keys | this help | Key and command help. |
| `tui_panel` | `ctrl+q` | `tui_panel.quit` | quit | quit | Quit. |
| `tui_run` | `tab` | `tui_run.move` | to button | move to the next button (Tab, ←/→ switch buttons) | Move to the next button (Tab, Left/Right switch buttons). |
| `tui_run` | `enter` | `tui_run.press` | press | press the focused button; ↑↓ PgUp PgDn scroll the result | Press the focused button; arrows and PgUp/PgDn scroll the end screen. |
| `tui_run` | `enter` | `tui_run.merge` | merge | merge the result into the destination branch | Merge the exported result after a confirmation. |
| `tui_run` | `enter` | `tui_run.diff` | changes | show the result's changes | Show the result's diff. |
| `tui_run` | `enter` | `tui_run.accept` | accept | accept the steward's proposal | Accept the steward's proposal. |
| `tui_run` | `enter` | `tui_run.answer` | answer | answer in a note: a new attempt with it | Answer in a note; a new attempt starts with it. |
| `tui_run` | `enter` | `tui_run.attempt` | new attempt | note optional | A new attempt from the destination HEAD. |
| `tui_run` | `enter` | `tui_run.plan` | to plan | the request goes to plan revision | Route a scope change back to plan revision. |
| `tui_run` | `enter` | `tui_run.resume` | continue | continue the same attempt in its worktree | Resume the same attempt. |
| `tui_run` | `enter` | `tui_run.check` | check | reconcile with Zeroshot, no resubmit | Reconcile an unconfirmed submission or stop; never resubmits. |
| `tui_run` | `enter` | `tui_run.tail` | log | the last lines of the Zeroshot log (on request) | Show the tail of the run log. |
| `tui_run` | `enter` | `tui_run.details` | details | attempt journal: the saved observation entries | The retained journal entries of this attempt, from the store; no native log is read. |
| `tui_run` | `enter` | `tui_run.leave` | leave | leave unanswered | Leave unanswered. |
| `tui_run` | `esc` | `tui_run.back` | close | close; nothing changes | Close; nothing changes. |
| `tui_diff` | `↑↓` | `tui_diff.scroll` | scroll | scroll the changes | Scroll the diff. |
| `tui_diff` | `esc` | `tui_diff.close` | close | return to the run result | Close the diff. |
| `tui_details` | `↑↓` | `tui_details.scroll` | scroll | scroll the details | Scroll the details. |
| `tui_details` | `esc` | `tui_details.close` | close | return to the home screen | Close the details. |
| `tui_answer` | `tab` | `tui_answer.button` | to button | from the text field move to the “send” button | Move from the text field to the send button. |
| `tui_answer` | `enter` | `tui_answer.send` | send | Enter on the “send” button: send the text (an empty answer starts nothing) | Press the send button: send the text. |
| `tui_answer` | `esc` | `tui_answer.back` | back | close without changes | Close without changes. |
| `tui_attempt` | `tab` | `tui_attempt.button` | to button | from the text field move to the “start attempt” button | Move from the text field to the start button. |
| `tui_attempt` | `enter` | `tui_attempt.send` | start attempt | Enter on the “start attempt” button: start a new attempt (the note is optional) | Press the start button: start the new attempt with the note (may be empty). |
| `tui_attempt` | `esc` | `tui_attempt.back` | back | close without changes: the attempt does not start | Close; nothing starts. |
| `tui_plan` | `tab` | `tui_plan.move` | to button | move to the next button (Tab, ←/→ switch buttons) | Move to the next button (Tab, Left/Right switch buttons). |
| `tui_plan` | `enter` | `tui_plan.press` | press | press the focused button; ↑↓ PgUp PgDn scroll the plan | Press the focused button; arrows and PgUp/PgDn scroll the plan. |
| `tui_plan` | `enter` | `tui_plan.run` | start the planner | check readiness and submit the goal; a stale unsent plan is first rebuilt on the current project; an unconfirmed submission is sent again unchanged | Check readiness, then submit the unsent or failed revision; a stale unsent one is first rebuilt on the current project. |
| `tui_plan` | `enter` | `tui_plan.renew` | new revision | the same goal on the current project | New revision, same goal, current project. |
| `tui_plan` | `enter` | `tui_plan.login` | log in | log in to Codex again (the terminal is suspended) | Codex login under suspend. |
| `tui_plan` | `enter` | `tui_plan.watch` | watch | follow the planner | Resume watching the planner. |
| `tui_plan` | `enter` | `tui_plan.tail` | log | the last lines of the planner's Zeroshot log (on request) | Show the tail of the planner run log. |
| `tui_plan` | `enter` | `tui_plan.approve` | approve | approve the plan; no implementation is started | Approve (starts nothing). |
| `tui_plan` | `enter` | `tui_plan.override` | approve despite the check | approve a plan the check rejected; a reason is required | Approve a plan the critic rejected, with a typed reason (starts nothing). |
| `tui_plan` | `enter` | `tui_plan.revise` | revise | write what to change and re-plan | Request a revision. |
| `tui_plan` | `enter` | `tui_plan.reject` | decline | do not approve the proposal | Decline the proposal. |
| `tui_plan` | `enter` | `tui_plan.info` | details | requirements and checks; for a failure, diagnostics | Full requirements and checks, or the diagnostics of a failure. |
| `tui_plan` | `esc` | `tui_plan.back` | back | return to the home screen | Back to the main screen. |
| `tui_plan` | `ctrl+q` | `tui_plan.quit` | quit | quit | Quit. |
| `tui_note` | `tab` | `tui_note.button` | to button | from the text field move to the “send revision” button | Move from the text field to the send button. |
| `tui_note` | `enter` | `tui_note.send` | send revision | Enter on the “send revision” button: re-plan with this text | Press the send button: send the revision request. |
| `tui_note` | `esc` | `tui_note.back` | back | close without changes | Close without changes. |
| `tui_confirm` | `tab` | `tui_confirm.yes` | yes | move to the “yes” button (Tab, ←/→ switch buttons) | Move to the “yes” button (Tab, Left/Right switch buttons). |
| `tui_confirm` | `enter` | `tui_confirm.press` | press | press the focused button; focus starts on “no”, on “yes” for a run start | Press the focused button; it starts on “no”, on “yes” for a run start. |
| `tui_confirm_run` | `enter` | `tui_confirm_run.start` | start | “yes” is already focused: Enter starts at once | “yes” is already focused: Enter starts at once. |
| `tui_confirm` | `esc` | `tui_confirm.no` | no | cancel; nothing changes | Cancel; nothing changes. |
| `tui_bootstrap` | `enter` | `tui_bootstrap.accept` | accept | the “accept” button (focused at once): write zplan.process.json and accept the profile | The “accept” button, focused at once: accept the proposed profile (writes the file). |
| `tui_bootstrap` | `right` | `tui_bootstrap.configure` | configure | move to the “configure” button (→): set your own values before the file is written | Move to the “configure” button: set your own values before the file is written. |
| `tui_bootstrap` | `tab` | `tui_bootstrap.later` | later | move on to the “later” button (Tab or →, after “configure”): work from the proposal without writing to the project | Move to the “later” button: postpone; the snapshot is used and the header says so. |
| `tui_bootstrap` | `ctrl+q` | `tui_bootstrap.quit` | quit | quit without deciding | Quit without deciding. |
| `tui_profile` | `←→/tab` | `tui_profile.move` | move | move to another button or field (←/→ switch buttons within a row, Tab goes to the next field) | Move between buttons and fields (Left/Right switch buttons within a row; Tab goes to the next field). |
| `tui_profile` | `enter/space` | `tui_profile.pick` | pick | pick the focused button: it gets the mark “● ” | Pick the focused button; the picked one is marked «● ». |
| `tui_profile` | `ctrl+s` | `tui_profile.save` | save | validate the values and write the profile (the “save” button does the same) | Validate the values and write the profile (the “save” button does the same). |
| `tui_profile` | `esc` | `tui_profile.cancel` | cancel | close the form, writing nothing | Close the editor; nothing is written. |
| `tui_settings` | `tab` | `tui_settings.move` | to button | move to the next button (Tab, ←/→ switch buttons) | Move to the next button (Tab, Left/Right switch buttons). |
| `tui_settings` | `enter` | `tui_settings.press` | press | press the focused button | Press the focused button. |
| `tui_settings` | `enter` | `tui_settings.setup` | install | install tools | Run setup with a live log. |
| `tui_settings` | `enter` | `tui_settings.login` | log in | log in to Codex (the terminal is suspended) | Codex login under suspend. |
| `tui_settings` | `enter` | `tui_settings.recheck` | check | check readiness again | Re-check readiness. |
| `tui_settings` | `enter` | `tui_settings.roles` | roles | show the roles | Toggle the roles view. |
| `tui_settings` | `right` | `tui_settings.profile` | profile | open the process profile: autonomy, parallelism, merge, roles | Edit the accepted process profile. |
| `tui_settings` | `esc` | `tui_settings.back` | back | return to the home screen | Back to the main screen. |
| `tui_settings` | `ctrl+q` | `tui_settings.quit` | quit | quit | Quit. |
| `tui_help` | `esc` | `tui_help.close` | close | close the help | Close the help. |
<!-- END GENERATED: keys -->

## Plan statuses

Persisted on each plan revision in `planning.json`.

<!-- BEGIN GENERATED: plan_status -->
| ID | Meaning | Likely cause | Owner remedy |
| --- | --- | --- | --- |
| `planning` | Goal saved, not yet sent to the planner. | The goal was just written, or readiness failed before submission. | [g] on the plan screen (readiness is checked first). |
| `submission_unknown` | The planner submission was sent but Zeroshot's acceptance was not confirmed. | zplan or the engine was interrupted at the moment of submission. | [g] sends the same frozen submission again (Zeroshot recognises its key); [i] shows the Zeroshot list command. zplan never resubmits on its own. |
| `observing` | The planner run is being watched. | A session is attached to the running planner. | Wait; Ctrl-C detaches, the planner keeps running. |
| `detached` | The planner runs but no session watches it. | The owner detached or the session ended. | [w] on the plan screen to watch again. |
| `stopped` | The owner stopped the planner run; it will not be resubmitted. | The owner asked to stop a run under observation. | Open the plan screen; [g] runs the planner again in a new revision. |
| `observation_blocked` | Watching stopped with a diagnostic while the planner may still run. | A native watch call failed or returned unusable output. | [w] watch again; [i] for the diagnostic. |
| `run_failed` | The planner run ended without a plan. | A provider, network, quota or authorization failure. | The plan screen names the cause; [g] restarts after readiness, [r] revises the goal. |
| `proposal_invalid` | The planner returned a plan zplan did not accept. | The plan broke the roadmap contract. | [r] revise the goal, or [g] run the planner again. |
| `review_exhausted` | The critic did not accept the plan within the revision's plan rounds; it cannot be approved in the usual way. | The goal is too broad or ambiguous, or the critic and the planner could not agree. | [i] shows every round; [r] revise, [g] run the planner again, or [o] approve it over the rejection with a typed reason. |
| `proposed` | A reviewed plan waits for the owner. | The planner and verifier finished. | [a] approve, [r] revise, [x] decline. |
| `approved` | The owner approved this revision; milestones may run. A plan approved over a rejected plan check carries the owner's reason and is shown as approved despite the check. | [a] on the proposed plan, or [o] on a plan the critic rejected. | [g] start a milestone on the home screen; [r] to change the plan. |
<!-- END GENERATED: plan_status -->

## Milestone states

What the home screen shows for each milestone of the approved plan.

<!-- BEGIN GENERATED: milestone_state -->
| ID | Meaning | Likely cause | Owner remedy |
| --- | --- | --- | --- |
| `waiting` | The milestone waits for the milestones it depends on. | A dependency is not merged yet. | Run and merge the dependency first. |
| `ready` | Dependencies are merged; the milestone can start. | Nothing was started for it in this plan revision. | [g] start it (a preview with worktree, branches and limits asks for confirmation). |
| `running` | An attempt is executing. | Started by [g]. | [w] watch; k + Enter while watching stops it. |
| `unknown` | The attempt's submission or an interrupted run is not confirmed. | zplan or the engine stopped between submission and acknowledgement. | [g] reconciles with Zeroshot without resubmitting. |
| `needs_owner` | The steward needs an answer or an accepted proposal. | The task list could not proceed alone. | [o] then [t] answer or [a] accept. |
| `blocked` | The attempt reported it cannot proceed. | A missing fact, access or contradiction. | [o], then [t] answer and restart, or [p] revise the plan. |
| `failed_recoverable` | The attempt failed and can continue in its worktree. | A provider or tool error. | [g] resumes the same attempt (or [o], then [g]). |
| `failed` | The attempt failed and cannot continue. | An unrecoverable engine or check failure. | [g] starts a new attempt (or [o], then [t] / [p] revise the plan). |
| `awaiting_merge` | The accepted result is exported to its own branch and waits for the owner. | The attempt finished with outcome done. | [o], then [d] review the diff and [m] merge. |
| `conflict` | Merging the result conflicted. | The destination branch moved or touched the same files. | [o]; merge the result branch by hand, then reopen zplan. |
| `integrated` | The result is merged into the destination branch. | [m] succeeded or ancestry was detected. | Nothing; dependents become ready. |
| `stopped` | The owner stopped the attempt. | k + Enter while watching. | [g] starts a new attempt (or [o], then [t] / [p] plan). |
| `stopping` | A stop was requested and is not confirmed yet. | Native has not acknowledged the force-stop. | [g] re-sends and reconciles the stop. |
<!-- END GENERATED: milestone_state -->

## Run statuses, outcomes and delivery

A milestone attempt is a run record: its native status, then (when finished) its outcome and how the result
was delivered.

<!-- BEGIN GENERATED: run_status -->
| ID | Meaning | Likely cause | Owner remedy |
| --- | --- | --- | --- |
| `preparing` | The attempt's worktree and frozen documents are being prepared. | Right after [g]. | Wait; an interrupted preparation is reconciled by [g]. |
| `submission_unknown` | The submission to Zeroshot is unconfirmed. | Interruption at submission. | [g] reconciles. |
| `submitted` | Zeroshot admitted the run. | Submission was acknowledged. | [w] watch. |
| `running` | Zeroshot executes the run. | The graph is working. | [w] watch. |
| `stopping` | A stop was requested. | k + Enter. | [g] reconciles. |
| `resume_pending` | A resume was sent but its successor run is unconfirmed. | Interruption at resume. | [g] reconciles. |
| `finished` | The run ended normally; see outcome. | The graph completed. | Per outcome. |
| `failed` | The run ended with a failure. | A provider or tool error. | [o] for the failure screen. |
| `stopped` | The run was stopped. | Owner stop. | [o]. |
<!-- END GENERATED: run_status -->

<!-- BEGIN GENERATED: outcome -->
| ID | Meaning | Likely cause | Owner remedy |
| --- | --- | --- | --- |
| `done` | The milestone's final verification accepted the result. | All tasks and checks passed. | Delivery follows: export then [m] merge. |
| `needs_owner` | The steward asked the owner. | A decision outside the task list. | [t] answer or [a] accept. |
| `blocked` | The run declared itself blocked. | A fact or access is missing. | [t] answer or [p] plan. |
| `invalid` | The run's output did not satisfy the contract. | Malformed result from the graph. | [t] new attempt; [i] on home for diagnostics. |
<!-- END GENERATED: outcome -->

<!-- BEGIN GENERATED: delivery -->
| ID | Meaning | Likely cause | Owner remedy |
| --- | --- | --- | --- |
| `none` | Nothing exported yet. | The run has not finished with done. | Per run state. |
| `exporting` | The result branch is being created. | Right after done. | Reopen zplan to finish export. |
| `awaiting_merge` | The result branch exists and waits for [m]. | Export finished. | [m] merge. |
| `conflict` | The merge conflicted and was aborted (or left the tree dirty). | Overlapping changes. | Merge by hand, then reopen. |
| `integrated` | The result is in the destination branch. | [m] succeeded. | Nothing. |
<!-- END GENERATED: delivery -->

## Error families

Every refusal or failure zplan shows ends with ` [code: <family>]`. Arbitrary text from a model or provider is
shown only as a bounded detail next to the code; a failure without a family shows `unknown_error`.

<!-- BEGIN GENERATED: error -->
| ID | Meaning | Likely cause | Owner remedy |
| --- | --- | --- | --- |
| `readiness.socket` | The Zeroshot socket path is too long. | The native state directory path is long. | Use a shorter --native-state-dir or ZPLAN data path. |
| `readiness.tools` | Pinned Zeroshot is missing or damaged. | Setup was not run or files changed. | [u] or `zplan setup`. |
| `readiness.codex` | The pinned Codex binary is missing. | Setup was not run or files changed. | [u] or `zplan setup`. |
| `readiness.codex_home` | Codex settings (CODEX_HOME/config.toml) cannot be read. | A malformed or unknown config. | Fix or remove the file; [i] shows the detail. |
| `readiness.auth` | No usable Codex login for the selected provider. | No login file or API key variable. | [l] or `zplan login` in zplan's own home; in your own CODEX_HOME sign in with `codex login`; a copied auth.json: `rm` it, then `zplan login`; or set the provider key variable. |
| `readiness.git` | Git is not installed or older than 2.38. | git is not on PATH, or its version lacks `merge-tree --write-tree`. | Install or upgrade Git to 2.38 or newer ([i] shows the command). |
| `readiness.identity` | No Git author identity. | user.name/user.email are unset. | git config --global user.name / user.email. |
| `readiness.roles` | The saved role configuration is damaged or invalid. | A hand-edited or old roles.json. | `zplan roles` or delete roles.json. |
| `readiness.repo` | The directory is not a Git project with a commit. | Wrong directory or no commit yet. | cd into the project or pass --project. |
| `readiness.branch` | HEAD is detached. | A checkout of a commit or tag. | git switch <branch>. |
| `readiness.origin` | origin is not a GitHub repository. | No origin or another host. | git remote add origin https://github.com/OWNER/REPO.git. |
| `readiness.clean` | Some files are not in the last commit (informational: this item is always ok). | Edited or untracked files. | None needed: the plan, the checks and the runs read the last commit; your files stay as they are. |
| `plan.stale` | The project or the Zeroshot it was prepared for changed after the plan was created or reviewed; the plan cannot be sent or approved. | A commit or edit after the baseline was frozen, or a different Zeroshot toolchain, rebuilt binary or state directory. | [g] on an unsent plan rebuilds it on the current project and sends it; [n] only prepares the new plan; [r] revises a proposal. |
| `plan.gate_stale` | The plan was argued under another process configuration than the one that applies now; it cannot be approved. | The process profile (limits, roles, rules selection) or a rules file changed after the critic accepted the plan. | [r] revises: the plan is rebuilt under the current configuration and argued again. |
| `plan.invalid_proposal` | The returned plan broke the roadmap contract (shape, ownership, size). | The planner produced a malformed or oversized plan. | [r] revise the goal or [g] run again. |
| `plan.failed` | The planner run ended without an accepted plan. | See the plan status and the cause screen. | The plan screen names the next key. |
| `plan.stop_unconfirmed` | Zeroshot did not confirm the stop of the running planner. | The native force-stop call failed or timed out. | [s] on the plan screen tries again; the run keeps being observed meanwhile. |
| `draft.stale` | A draft was sent or opened for a state the project no longer has; it was not applied. | For a goal draft: a new revision was prepared, or the same revision's state moved on (submitted, plan ready, approved). For an answer draft: the plan, the attempt, the run or the delivery moved on, or the milestone finished, after the reply the draft came from. | Ask the architect again: [/plan] on the card of its new reply, or [/answer], applies normally. Nothing is exported and the stale draft's text stays copyable. |
| `draft.malformed` | An answer draft's identity cannot be rebuilt into the attempt it was written for, so its form was not opened. | A chat record written by another version, or a hand-edited or truncated draft identity. | Ask the architect again for a fresh draft: only a draft whose identity rebuilds is applied by [t], and this one never is. |
| `draft.active` | An answer draft belongs to an attempt that is still running; only a finished attempt offers an answer. | The reply that carried the draft was written while the attempt was still running, and that same attempt is still the current one - its plan, attempt, run, status, outcome and delivery have not moved on since. | The draft cannot be applied while it runs: [w] watches the attempt and [o] opens its end once it finishes, where [t] answers it directly. For the draft's own text, ask the architect again - its new reply carries a fresh draft. |
| `draft.unavailable` | An answer draft's attempt has an end that offers no answer, so there is nothing left to answer. | The reply's draft was written for an attempt whose end already offered no answer - it had finished and was exported or merged, or it never needed one - and its identity still matches the current one. | Nothing is left to answer: [o] shows that end with its own keys ([m] merge, [d] diff), and the next step goes to the plan with [p]. A fresh draft from the architect carries the same end, so it would not help. |
| `submission.unknown` | The engine did not confirm a submission; zplan will not resend it by itself. | Interrupted between send and acknowledgement. | [g]: on a plan, send the same frozen submission again (Zeroshot recognises its key); on a run, reconcile. [i] shows the Zeroshot list command. |
| `planner.auth` | The provider rejected the authorization. | An expired or revoked login or key. | [l] refresh login, then [g]. |
| `planner.quota` | The provider refused the request for a limit or quota. | Rate or usage limit. | Wait or check account limits, then [g]. |
| `planner.network` | The model service was unreachable. | Offline, DNS or proxy failure. | Check the network, then [g]. |
| `planner.unknown` | The planner stopped for a cause the public logs do not show. | Anything else. | [i] prints Zeroshot diagnostic commands; then [g]. |
| `planner.detached` | Watching the planner was interrupted; it continues. | Ctrl-C or a dropped watch. | [w] on the plan screen watches again. |
| `engine.unavailable` | Zeroshot did not start or answer. | Broken install or a stuck process. | `zplan doctor`, then `zplan setup`. |
| `engine.rejected` | Zeroshot deterministically rejected an operation. | A contract or admission refusal. | `zplan doctor`; diagnostics under [i]. |
| `engine.bad_output` | Zeroshot returned oversized or malformed output. | A tool/version mismatch. | `zplan doctor`; reinstall with `zplan setup` if it persists. |
| `engine.identity_changed` | The pinned executable or its state changed. | Binary replaced or version mismatch. | Use the original isolated paths or reinstall. |
| `toolchain.mismatch` | A plan or run is frozen on another Zeroshot toolchain whose executable is gone or changed. | A newer zplan release replaced the default toolchain and the recorded executable no longer matches its sha256. | Finish it on the older zplan (its tools directory is kept), or start over from a new plan revision on the current toolchain. |
| `engine.checkout` | The disposable planner checkout is missing or could not be prepared. | Disk, Git or an interrupted preparation. | Retry with a new revision ([n]); frozen history stays. |
| `engine.intent_changed` | The frozen submission no longer matches its record. | Hand-edited state. | Not resumable; prepare a new revision ([n]). |
| `engine.observation_lost` | No reconstructable first watch record exists for the run. | Missing native history. | [i] for the Zeroshot commands; resubmission stays forbidden. |
| `store.invalid` | A stored record or envelope failed validation. | Corruption, hand edits or a version mismatch. | Do not edit state; keep the directory and report it. Older versions' records stay readable. |
| `store.locked` | Another terminal controls this project's plan. | A second zplan session holds the lock. | Close the other session. |
| `store.write_failed` | Persisting zplan state failed. | Disk full or permissions. | Free space or fix permissions, reopen. |
| `project.unreadable` | The project could not be read as a Git tree. | Not a project with a commit, or a changing tree. | cd into the project; keep the tree still while zplan reads it. |
| `action.refused` | The requested action is not allowed in the current state. | The state moved on or the action's precondition is unmet. | Reopen the screen; it offers the valid keys. |
| `usage.invalid_option` | An option or explicit selection is not allowed in this mode. | Production/fixture mix-up. | `zplan help` for the options. |
| `git.failed` | A Git command failed or timed out. | Repository state or locks. | Run the same git command by hand. |
| `milestone.blocked` | The attempt reported it is blocked. | A fact, access or contradiction. | [t] answer and restart or [p] revise the plan. |
| `milestone.failed` | The attempt failed and cannot continue. | An unrecoverable failure. | [t] new attempt or [p] revise the plan. |
| `milestone.failed_recoverable` | The attempt failed but can resume. | A transient provider or tool failure. | [g] resumes in the same worktree. |
| `milestone.conflict` | Merging the result conflicted. | Overlapping changes in the destination. | Merge the result branch by hand, commit, reopen zplan. |
| `milestone.lost` | The attempt was interrupted and its state is unconfirmed. | A crash or closed session. | [g] reconciles with Zeroshot. |
| `milestone.stop_unconfirmed` | Zeroshot did not confirm the stop. | The force-stop call failed. | [g] re-sends; the run stays stopping meanwhile. |
| `milestone.preflight` | The checker preflight failed in the milestone worktree. | A broken tool or worktree. | [i] diagnostics; fix the environment and start again. |
| `milestone.branch_exists` | The attempt branch already exists at another commit. | A leftover branch. | Delete or rename that branch. |
| `milestone.too_many_tasks` | The milestone has more tasks than one run can execute. | An oversized plan. | [r] revise to split the milestone. |
| `milestone.manifest_invalid` | The task manifest or an amendment is malformed. | A worker wrote an invalid manifest. | [t] new attempt; [p] revise. |
| `milestone.merge_refused` | The merge was refused without conflicts. | Identity, hooks or tree state, an unfinished merge (MERGE_HEAD; `git merge --abort`), or HEAD, the tree or the profile changed during the merge checks. | [i] and `git status`; fix, then [m]. |
| `milestone.merge_overlap` | The merge was not landed: it would write over files of your tree. | A file the merge changes, or a parent directory of it, exists in the project as untracked, ignored or modified. | The result branch is kept: move or commit those files, then merge again; the card's “show differences” lists the changes. |
| `milestone.critic_blocked` | The merge critic blocked the candidate. | A high risk tier or a finding the critic judged a block. | Read the findings ([i], [d]); change the result or start a new attempt, then [m]. |
| `merge.no_checks` | The merge gate is required but the profile lists no checks. | gates.merge is `required` and `checks` is empty. | List the checks in zplan.process.json, or set gates.merge to `off`. |
| `merge.checks_failed` | The checks on the merge candidate did not pass, or could not run. | A check exited non-zero or timed out, or the candidate could not be checked out. | Read the evidence ([i]), fix the result, then [m]; the destination is unchanged. |
| `merge.critic_pending` | The merge critic did not finish in the observation slice. | The critic run is still working. | zplan keeps observing the same run and lands the candidate on the critic's `go`; after leaving zplan meanwhile, [m] again observes the same run. |
| `merge.critic_failed` | The merge critic ended without a verdict. | The critic run failed, or its output was invalid. | [m] again to start a new critic; [i] shows the diagnostic. |
| `run.limit` | One of the attempt's executions hit a provider session or usage limit. | The provider or account limit is exhausted; the log says when it resets when the provider tells it. | Wait for the reset (shown when it is known) or check the account limits, then retry. |
| `run.quota` | One of the attempt's executions was refused because the account is out of quota. | No credits are left on the account. | Top up the account, then retry. |
| `run.auth` | One of the attempt's executions was refused for missing or invalid authorization. | An expired, revoked or unreadable login. | [l] refresh the login (`zplan login`), then retry. |
| `run.forbidden` | One of the attempt's executions was refused with a forbidden (403) status. | The provider rejects the account, the region or the workspace access. | Check the account or the region, then retry. |
| `run.network` | One of the attempt's executions could not reach the model service. | A DNS, proxy or connection failure. | Retry later. |
| `export.source_missing` | The plan's source commit is not in the project. | History was rewritten or pruned. | Revise the plan on the current project. |
| `export.unsupported_layout` | The result contains layouts the export refuses. | Submodules, nested Git, filters (LFS/ident/encoding) or special files. | Remove them from the result or the project. |
| `export.reserved_path` | The project tracks zplan's control directory. | .zplan/ is committed. | Untrack .zplan/ in the project. |
| `export.snapshot_changed` | The result changed or does not match the verified candidate. | Edits after acceptance or Git conversion. | [t] new attempt. |
| `export.branch_exists` | The result branch already exists differently. | A leftover or concurrent export. | Delete or rename the branch. |
| `setup.command_failed` | A setup command could not run or exited non-zero. | Missing tool or network. | Fix the cause shown, rerun `zplan setup`; the previous install is kept. |
| `setup.busy` | Another setup is running. | A concurrent `zplan setup`. | Wait for it. |
| `setup.agent_home` | zplan could not write its agent profile (config.toml) into its own Codex home. | A concurrent zplan holding the profile lock, an unwritable home, or an entry that is not a regular file. | Retry; if it persists, fix the path named in the message. |
| `setup.prerequisite` | Node.js >= 16 and npm are required. | Not installed. | Install Node.js/npm, rerun setup. |
| `setup.unsupported_platform` | No pinned release for this platform. | Not macOS arm64 or Linux x86_64/aarch64. | Use a supported platform. |
| `setup.tools_invalid` | The installed tools failed verification. | Version or checksum mismatch. | Remove the tools directory and rerun `zplan setup`. |
| `setup.download_invalid` | The downloaded release failed verification. | Corrupt or tampered download. | Retry; nothing was installed. |
| `setup.login_failed` | The Codex login did not finish. | Cancelled or rejected device login, or device-code login is off for the account. | If device-code login is off for the account, turn it on in the ChatGPT account security settings; then [l] or `zplan login` again. |
| `architect.invalid_config` | The architect's executable, model or thread id is invalid. | Bad settings. | Fix the role binding with `zplan roles`. |
| `architect.session_corrupt` | The stored architect session is damaged. | A hand-edited or truncated file. | Delete the file named in the message to start a new conversation. |
| `architect.home_lost` | The recorded Codex home of the architect's thread is gone. | That CODEX_HOME was moved or deleted, or its login is gone. | Ctrl+R “new dialog” starts a new thread in the current home. |
| `architect.project_missing` | The project directory is gone. | Moved or deleted. | Reopen zplan in the project. |
| `architect.busy` | The architect is already answering. | A turn is in progress. | Cancel the turn or wait. |
| `architect.closing` | The interface is leaving: no new turn or reset is accepted. | The quit key was pressed. | Start zplan again to talk to the architect. |
| `architect.foreign_tools` | Codex would start an MCP server besides zplan's in the architect's turn, or the server list could not be checked. | A server or plugin of your Codex config that the turn could not turn off. | Remove the server named in the message from your Codex config, or fix `codex mcp list`; no turn was started. |
| `architect.empty_message` | The message is empty. | Nothing was typed. | Type a message. |
| `architect.locked` | Another zplan process talks to this project's architect. | A second session. | Close the other session. |
| `read.outside_project` | The path or root is outside the selected project and its worktrees. | A `..` or absolute path, a link leading out, an untracked file, or a foreign root. | Name a tracked file inside the project. |
| `read.credential` | The file looks like a credential file and is never read. | Its name matches a credential pattern, or it lies under `.git/` or `.zplan/`. | Nothing to fix: by design. |
| `read.binary` | The file is binary. | A NUL byte in its first 8 KB. | Read a text file. |
| `architect.cancelled` | The owner cancelled the turn. | Cancel key. | Send a new message. |
| `architect.lost_session` | Codex no longer has the stored conversation. | Its rollout was removed. | Reset to start a new conversation. |
| `architect.auth` | Codex rejected the authorization. | An expired login. | `zplan login`, repeat the message. |
| `architect.failed` | The turn ended without a result. | A provider error, a signal or a non-zero exit. | Repeat the message; the capped detail is in the transcript. |
| `architect.controller_unavailable` | The live Controller is not reachable from the architect's tools. | No zplan window is serving this project, or its socket directory is gone. | Open zplan in the project; the tools only reach a running Controller. |
| `architect.controller_timeout` | The Controller did not answer an action in time; the outcome is unknown. | The worker was busy past the wait (a run, a submission). | Call zplan_status: the request keeps its state and its result once the job ran. |
| `architect.request_invalid` | The architect's action tool call carried bad arguments. | A missing or wrongly typed milestone, revision or run id. | Call the tool with the arguments its schema names. |
| `commit.refused` | The commit of the owner's files was refused; nothing was run. | No commit yet, a detached HEAD, a merge or rebase in progress, a held index.lock, a merge being landed, or none of the proposed paths is a changed file git may commit (credential files are never committed). | Do what the message names (`git switch <branch>`, finish or abort the merge or rebase, wait for the other git) and ask the architect again. |
| `commit.failed` | `git commit` did not create the commit; HEAD and the index are as they were. | A hook refused, git failed, or the terminal could not be handed over. | Fix what the hook or git printed and confirm the commit again. |
| `autonomy.ask` | The autonomy policy asks the owner to do this action themselves. | Automatic actions are off (until A7), or the level is manual, or the action is a start at a level that asks. | Do it with your own key in the zplan interface. |
| `process.invalid` | The project's zplan.process.json (or its rules/checks) is not valid. | A hand edit with an unknown key, a wrong type, an empty command or a rules path outside the repository. | Fix the key named in the message, or delete the file and run `zplan profile init`. |
| `process.state` | The profile's acceptance record in zplan's state directory is damaged. | A hand edit or an interrupted write by another tool. | Delete the file named in the message; the profile is offered again. Plans and runs are untouched. |
| `process.missing` | The accepted zplan.process.json is gone from the project. | The file was deleted or the branch without it was checked out. | `git checkout -- zplan.process.json`, or `zplan profile init` to create it again. |
| `process.unbuilt` | A gate the profile requires is not implemented in this version. | gates.task is `required`. | Set the gate to `off` in zplan.process.json. |
| `process.changed` | The profile changed after the preview was shown. | zplan.process.json or the saved roles were edited meanwhile. | Look at the preview shown again and confirm it. |
| `tui.unavailable` | The full-screen interface cannot start. | Textual is missing or not importable. | `zplan --plain`, or reinstall zplan. |
| `unknown_error` | A failure that has no catalog family. | An unclassified message or exception. | The bounded text shown with it is the only detail: `zplan doctor`, [i] on home, then docs/REFERENCE.md. |
<!-- END GENERATED: error -->

## Worked examples

### 1. A new machine to a first plan (on a clean repo)

1. `zplan doctor` — lists what is missing (`readiness.tools`, `readiness.auth`, …), each with its fix.
2. `zplan setup` — installs the pinned Zeroshot and Codex (`readiness.tools`, `readiness.codex`).
3. `zplan login` — device login for Codex (`readiness.auth`).
4. `zplan doctor` again: every line is `ok`.
5. In the project: `zplan --plain` (or `zplan` on a terminal), `p`, type the goal, `g` — the planner starts.
   `?` on any screen lists the keys it accepts.

### 2. From an approved plan to a merged milestone

1. The plan status is `proposed`; read it (`i` for the requirements and checks), then `a` to approve. Nothing
   is started yet.
2. On the home screen the first milestone is `ready`: `g` shows a preview (worktree, branches, limits); `y`
   confirms. The state becomes `running`; `w` watches, Ctrl-C detaches and the run continues.
3. The outcome is `done` and the state `awaiting_merge`: `o`, `d` to read the diff, `m` then `y` to merge.
4. The milestone is `integrated`; dependents turn `ready` and step 2 repeats.

### 3. Uncommitted changes

1. The project has edits that are not in the last commit: planning and attempts are not refused. Settings shows
   «Not committed: N files — the plan sees the last commit» (an uncommitted `zplan.process.json` is named there: runs
   see the committed one).
2. The plan, the checks and the attempts read the last commit; your files stay as they are and a plan stays current
   while only the tree changes. The architect lists the uncommitted paths, and the foreman warns when a task's
   write_set holds one of them.
3. A new commit or a branch switch makes a plan made earlier `plan.stale`: `[g]` on an unsent stale plan rebuilds it
   on the current project and sends it in the same step (`[n]` prepares it without sending).

### 4. Blocked milestone: answer, accept or a new attempt

1. A milestone shows `blocked`, `needs_owner` or `failed`; `[o]` opens its attempt screen with the reason.
2. `blocked` or `needs_owner`: `[t]` answers and restarts as a new attempt (`blocked.answer`,
   `needs_owner.answer`).
3. `needs_owner`: `[a]` accepts the steward's proposal instead (`needs_owner.accept`).
4. `failed`: `[t]` starts a new attempt; `[p]` revises the plan when the task itself is wrong.

### 5. After an interruption

1. You closed the terminal during a run. Reopen zplan: the milestone shows `unknown` (submission not
   confirmed) or `running` (still going).
2. For `unknown`, press `g`. zplan asks Zeroshot what happened and never resubmits on its own.
3. If the run failed with `failed_recoverable`, `o` then `g` continues the same attempt in its worktree; for
   `failed` or `stopped`, `o` then `t` starts a new attempt, or `p` revises the plan.
4. A code you do not recognise, or `unknown_error`: look it up in [Error families](#error-families); the
   detail line next to it is the only extra information zplan has.
