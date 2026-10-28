# Installation: zplan 0.8.1

Supported: macOS on Apple silicon (arm64). Not supported: Linux (for now: this release is qualified on macOS
only), Windows and Intel macOS (no pinned toolchain for the last two; `zplan setup` stops). Runs execute natively as
your user; no container runtime is needed. The interface is in English only; there
is no language chooser, and a stored `"ru"` falls back to English.

## Prerequisites

- Python ≥ 3.11 with `venv`, Git, curl (the one-command install), Node.js ≥ 16 with npm (setup installs the pinned Codex through `npm ci`).
  If `python3` is older, `install.py` re-runs itself with `python3.13`, `python3.12` or `python3.11` from PATH
  and stops with a message naming the requirement when none exists.
- A Git identity (`git config --global user.name` / `user.email`): milestone commits and your merges use it.
- A Codex login with model access (next section).

```sh
# macOS (Homebrew; Git from Xcode Command Line Tools or Homebrew; the Command Line Tools' python3 is 3.9, too old)
brew install python node
```

## Before you log in

- **Account and model.** `zplan login` signs Codex in with your own account (device code), and that account needs
  access to the models the roles use: the worker defaults to `gpt-6.1-terra` (effort max), every other role to `gpt-6.1-sol` (Setup, login, doctor: Roles).
- **Cost.** Every planner revision, milestone run and architect turn spends model tokens on that account; zplan
  gives no estimate up front. A milestone run keeps running, and spending, after you quit zplan or close the
  terminal, until it finishes or you stop it.
- **Full access.** The planner and milestone agents run as your user through Codex with
  `sandbox_mode = "danger-full-access"` and `approval_policy = "never"` (zplan's profile in its Codex home):
  without asking, they can read and change every file your user can, outside the project too (the whole HOME,
  including credentials such as SSH keys, tokens and cloud configs), and use the network. This is the default, and
  there is no guarded mode; install zplan only under a user and on a machine where that is acceptable. The
  architect chat itself runs Codex read-only.
- **Autonomy.** The process profile zplan proposes on the first start in a project sets `autonomy.level` to `auto`:
  while the full-screen shell is open, the architect approves a checked plan and starts or resumes ready
  milestones by itself. `"autonomy": {"level": "manual"}` in `zplan.process.json` makes it ask for each of these;
  `supervised` asks for the plan approval and for every merge. On that first start «configure» sets the autonomy level,
  parallel runs (1-3), the merge rule and each role's model and effort before saving; `/setup` → «profile» changes them
  later. Merges stay yours unless the profile sets `gates.merge` to `required` at level `auto`; the proposed profile
  does that whenever zplan found a test command, and the architect then merges a milestone whose merge gate passed.
- **Stop a run.** In the full-screen shell type `/stop` and answer «yes»: it stops the milestone selected in the list,
  else the first running one (or the planner while it plans); repeat for each running milestone. In the line UI (`zplan --plain`) press `k` + Enter while watching the milestone, then
  `y`. Quitting zplan or closing the terminal only detaches.
- **Uninstall** removes the launcher, `~/.local/share/planning-kit` (with zplan's Codex home `codex-home/`),
  `~/.config/planning-kit`, `~/.zp` and the plan store: see [Uninstall](#uninstall).
- **Bugs.** Report them in the [GitHub issues](https://github.com/pinkynail228/zeroplan/issues).

## Install

One command fetches the newest release, installs it with its own `install.py` and runs `zplan setup`:

```sh
curl -fsSL https://raw.githubusercontent.com/pinkynail228/zeroplan/main/install.sh | sh && export PATH="$HOME/.local/bin:$PATH"
zplan login                # Codex device login (zplan setup runs inside the installer; needs Node.js)
```

`install.sh` itself fetches and installs with only `git` and `python3`: it picks the newest `vX.Y.Z` release tag,
shallow-clones it into a temporary directory, runs that release's `install.py` with any arguments you pass to the
script and then `zplan setup`. The install is complete only when that `zplan setup` succeeded; it installs the
pinned Codex through `npm ci`, so **Node.js ≥ 16 with npm** must be on PATH as well (Prerequisites), since
`zplan login` needs the Codex it installs. Without Node.js/npm the command stops with a non-zero exit, and its last lines
name the prerequisite — it never reports a half-ready install you cannot log in to; install Node.js and re-run
the same command (or `<launcher> setup`). A host with only `git` and `python3` cannot end up with a ready zplan.
`ZEROSHOT_TOOLS` may start with `~` (it is expanded like `install.py` does).
`ZPLAN_VERSION=0.8.1 sh install.sh` pins a release; `ZPLAN_REPOSITORY` points at another repository. A missing
`git`/`python3` or a repository without a `vX.Y.Z` tag stops with one message and a non-zero exit. Once installed,
`zplan update` moves to a newer release and runs the same `setup` step (docs/UPGRADE.md).

Manual/offline from a checkout (the same route `install.sh` performs):

```sh
git clone https://github.com/pinkynail228/zeroplan.git
cd zeroplan
python3 install.py
export PATH="${ZEROSHOT_TOOLS:-$HOME/.local}/bin:$PATH"
zplan --version            # zplan 0.8.1
zplan setup                # pinned Zeroshot 10.16.0 + Codex 0.162.1
zplan login                # Codex device login
```

`install.py` creates a private venv at `$XDG_DATA_HOME/planning-kit/app/0.8.1` (default `~/.local/share/...`),
installs the checkout and its one runtime dependency, Textual 8.2.8 (the full-screen shell), into it and then points the `zplan` launcher
(`~/.local/bin/zplan`, or `$ZEROSHOT_TOOLS/bin/zplan`) at it. An existing `zplan` that this installer does not
own is refused. The installed app never imports from the checkout; you can delete the clone afterwards.

**Offline:** `python3 install.py --wheelhouse DIR` builds with `pip --no-index` from `DIR`, which must hold
`setuptools-75.8.0-py3-none-any.whl`, `wheel-0.45.1-py3-none-any.whl` and `textual-8.2.8-py3-none-any.whl`
with the wheels it depends on (rich, markdown-it-py, mdurl, pygments, platformdirs, typing_extensions, …).

**Upgrade from 0.6.x:** 0.8.0 was the first public release. An install of 0.6.x looks for releases in its earlier
repository, so point it at this one: `ZPLAN_REPOSITORY=https://github.com/pinkynail228/zeroplan.git zplan update`
(or run the one-line install). The launcher moves to `app/0.8.1`, the older `app/` directory stays on disk, and the
installer copies the store to `v3.backup-<old version>-<UTC timestamp>` first.

**Older releases (0.2.x to 0.5.x)** were never public. What each step changed in the store, and how to roll back
across it, is in [UPGRADE.md](UPGRADE.md) (Rollback). Detach from running milestones before replacing the app;
replacing code never cancels a run.

A release that changes the Zeroshot/Codex toolchain installs it into its own tool directory next to the old one;
records bound to the older toolchain keep working while that directory exists. Details, rollback and the
maintainer's qualification checklist: [UPGRADE.md](UPGRADE.md).

## Setup, login, doctor

```sh
zplan setup     # pinned Zeroshot 10.16.0 + Codex 0.162.1; rerunnable, verifies hashes
zplan login     # Codex device login (enable device login for your account if asked)
cd /path/to/your-project
zplan doctor    # every line OK: → ready
```

- `zplan setup` downloads Zeroshot 10.16.0 and checks its pinned SHA256, installs Codex 0.162.1 from the bundled
  npm lockfile with `npm ci`, verifies both versions and only then publishes the tool directory
  (`tools/zeroshot-10.16.0-codex-0.162.1-runtime2`). A failed setup publishes nothing; corrupt tools fail closed.
  Global `zeroshot` / `codex` installations are never used or replaced.
- `zplan login` first runs the pinned Codex `login status` (file credential store) in zplan's own Codex home: a login
  that is there is kept («Login already present»); otherwise it runs `login --device-auth`. To sign in again run
  `zplan logout` (revokes zplan's own token only; refused while a run or the architect is live there), then
  `zplan login`. In a `CODEX_HOME` of yours neither command runs Codex. zplan never prints, copies or logs credentials; to
  detect a copied login it compares digests of `auth.json` files locally (see docs/REFERENCE.md).
- **Codex home.** Login, doctor and every run use zplan's own home,
  `~/.local/share/planning-kit/codex-home` (`$XDG_DATA_HOME`), and zplan writes its versioned `config.toml`
  profile there at login or on the first launch. An explicit `CODEX_HOME` overrides it for the runs
  (sign in there with `codex login`, then `CODEX_HOME=... zplan`); zplan writes no profile into an override home and
  never logs in or out of it.
  You then have two logins side by side: yours in `~/.codex`, untouched, and the zplan home's own. zplan has its
  own login in its own Codex home; it never copies or links `~/.codex` credentials, because a shared refresh
  token can log out the other copy. Never copy `auth.json` into it: a copy blocks doctor with «remove the copy: rm <path>». In the zplan home an absent `config.toml` means zplan's profile; in an
  override home it means Codex defaults (provider
  `openai`). A malformed one or an unknown `model_provider` blocks doctor. A login can also come from
  `CODEX_API_KEY`, or for a run from an `OPENAI_API_KEY` that the engine maps to `CODEX_API_KEY`; that
  `OPENAI_API_KEY` route is unverified for the architect until the qualification gate — the mapping reaches the
  architect's Codex child, but Codex itself accepting `CODEX_API_KEY` with no `auth.json` has not been proven yet.
- `zplan doctor` checks: pinned Zeroshot and Codex, the Codex home (zplan's own or `$CODEX_HOME`) and its
  provider, login presence (not validity), Git identity, the native socket path, roles, and — inside a project —
  repo with a commit, attached branch, GitHub `origin`, clean tree. It also prints one informational line for
  zplan's own profile. Each `BLOCKED:` line names its fix; exit 1 if any check is blocked. A `WARN:` line names a
  non-blocking issue and still exits 0. No model request is sent and no secret is printed.
- Roles: `zplan roles` edits `$XDG_CONFIG_HOME/planning-kit/roles.json` (default `~/.config/...`); Settings in
  the full-screen shell (`/setup`, button «roles») only shows the resolved roles, it never edits them. Defaults: model `gpt-6.1-sol`, `gpt-6.1-terra` for `worker`; effort high for `planner`, `plan_verifier`, `reviewer`
  and `steward`, max for `worker`. An approved plan keeps the roles it was planned with. In a project with a
  `zplan.process.json` the roles of the project file win key by key; roles.json fills only the keys the file does
  not set (`plan_verifier` is read as `critic`). See USER_FLOW.md, «First start in a project».

## Where things live

| What | Path |
| --- | --- |
| App venvs | `~/.local/share/planning-kit/app/<version>/` |
| Launcher | `~/.local/bin/zplan` or `$ZEROSHOT_TOOLS/bin/zplan` |
| Pinned tools | `~/.local/share/planning-kit/tools/zeroshot-10.16.0-codex-0.162.1-runtime2/` |
| Codex home | zplan's own `~/.local/share/planning-kit/codex-home/`; an explicit `$CODEX_HOME` overrides it |
| Roles | `~/.config/planning-kit/roles.json` |
| Plan and run records | `~/Library/Application Support/PlanningKit/production/v3/<project>/planning.json` |
| Milestone worktrees | `~/.local/share/planning-kit/worktrees/` |
| Native Zeroshot state | `~/.zp/` (`runs/`, `config/`) |

`~/.local/share` follows `$XDG_DATA_HOME`. Native state lives in the short `~/.zp` because each run's control
socket (`<state>/runs/runs/<run uuid>/controller.sock`) must stay under 104 bytes on macOS; an
existing `~/.local/share/planning-kit/native` from an older install keeps being used. `--native-state-dir PATH`
selects another private directory; `zplan doctor --native-state-dir PATH` checks its length.

## Uninstall

Stop or finish every running milestone first (`/stop` for each; a run you only detached from keeps running and spending).
Removing the launcher and `~/.local/share/planning-kit/app/` removes the program; the other paths hold state and
credentials — `codex-home/` is zplan's Codex home with its login — so delete them only when you no longer need
the plans, the history and that login. With the default paths (adjust for `$XDG_DATA_HOME`, `$XDG_CONFIG_HOME`,
`$ZEROSHOT_TOOLS` or `--native-state-dir` if you set them):

```sh
rm -f ~/.local/bin/zplan
rm -rf ~/.local/share/planning-kit       # app/, tools/, codex-home/, worktrees/, architect/, checkouts/
rm -rf ~/.config/planning-kit            # roles.json, ui.json
rm -rf ~/.zp                             # native Zeroshot state
rm -rf ~/Library/"Application Support"/PlanningKit   # plan store
```

A Codex home you chose with `CODEX_HOME` and your own `~/.codex` are yours; zplan never removes them. Your
projects keep their `zplan-work/*` and `zplan/*` branches, your merge commits, `.zplan/STATE.md` with its
`/.zplan/` line in `.git/info/exclude` and, if you accepted it, `zplan.process.json`.

## Removed in 0.3

0.3 replaced the 0.2 Task runtime: own containers, egress configuration, containment, the Docker boundary,
resource binding (`setup resources`) and diagnostic export are gone. Docker is no longer a prerequisite.

## Development

```sh
PYTHONPATH=.:tests python3 -m unittest discover -s tests
devtools/linux-test.sh                      # full suite on the Linux test host
```

`ZPLAN_TEST_WHEELHOUSE=DIR` enables the installed-app gate (`tests/test_install.py`): an offline install into a
temporary HOME next to a fake older install, then the installed fixture journey from an unrelated project.
`--native-binary PATH` is a development override for an explicit Zeroshot executable, not the normal path.
