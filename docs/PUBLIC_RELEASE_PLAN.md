# Public release plan: zeroplan

Owner 2026-10-27: go public after 0.6.3; repository name `zeroplan`; product agents keep full access by default
(Codex `danger-full-access` + approval `never`), stated plainly to the user. The transfer follows
docs/PUBLIC_REPO_PLAN.md steps 3-4 and 8 (fresh export, never this repository's history); its steps 5-7 (dev home
cutover, Actions) follow after the flip. Critic pub-scope 2026-10-27 (xhigh): GO WITH CHANGES, 9 BLOCK + 2 NOTE,
all applied (~/zs-pause/critic/pub-scope.*).

## Measured start (2026-10-27, main bb6be3d)
- `python3 devtools/export_check.py --private-terms <terms>` on HEAD: exit 0, 0 findings. The tree is clean; the
  history is not (private terms, measured 2026-10-24): only a fresh export goes out.
- The private repository URL is not a private term, so export_check passes it: install.sh:4,17,
  terminal_planner/update.py:18, tests/test_update.py, tests/test_tui_activity.py, README, INSTALLATION, UPGRADE,
  CHAT_RELEASE_JTBD, PUBLIC_REPO_PLAN, devtools/ui-lab/work.py, devtools/zeroshot/tasks/one-command.md:14.
- Claims audit (~/zs-pause/public/claims.md): 70 install and first-use claims, 17 STALE (mostly letter keys in
  README, USER_FLOW's line-UI checklist, Zeroshot 10.12.0 in USER_FLOW), 13 CHECK, 6 GAP.
- No stranger install ever ran: every newcomer check used the owner's Mac with Node, Codex and a login present.
- Host 2 (Ubuntu 24.04 x86_64) has Docker for the zplan user.

## Names and version
Repository `pinkynail228/zeroplan`, default branch `main`, title zeroplan in README. The command stays `zplan`;
the distribution name `zeroshot-planning-kit` and store paths stay (installed update path); renaming them is Later.
The first public release is v0.7.0: newer than the private 0.6.3, so install.py (refuses an installed version,
install.py:117) and `zplan update` move a private install onto it. No old tag goes out.

## Readiness matrix
Every row records in ~/zs-pause/public/: source SHA, export SHA, tag, environment (OS image, tool versions), command,
exit code. A change to the candidate reruns the rows it touches and always R1, R2; before the owner's go the
candidate is frozen and the remote refs are compared with it.

| # | Row | Check | Done when |
| --- | --- | --- | --- |
| R1 | History | export of one named commit, new `.git`, commit signing off, one initial commit, tag v0.7.0 on it; `git cat-file -p` of every commit and tag | refs = `main` + `v0.7.0` only, both on the export commit; author/committer/tagger pinkynail228 noreply; no signature or other header; tag = `zplan --version` |
| R2 | Content | export_check with the private terms; grep of the export tree and of an installed app for `zeroshot-planning-kit` repository URLs; gitleaks (container on host 2) | all exit 0 / no match; historical task files naming the old URL stay out of the export (manifest), originals unchanged |
| R3 | Docs truth | every install, first-use and stop claim of README, INSTALLATION, UPGRADE and USER_FLOW (claims table) has a check; stale ones fixed | each claim checked or removed |
| R4 | Linux clean room | one ubuntu:24.04 container on host 2 (owner 2026-10-27: debian, fedora dropped), tool baseline recorded; without Node, then with Node ≥ 16; install from the export through `ZPLAN_REPOSITORY` | no Node: one-line refusal, exit ≠ 0. With Node: install + setup exit 0; `zplan doctor` before login and Git identity: BLOCKED naming both, exit 1; after the documented identity: only the login blocks; fixture demo exit 0 |
| R5 | macOS | owner's Mac, `env -i`, fresh HOME, PATH without Node, then with Node, tool baseline recorded, same stages as R4 | as R4. No clean macOS VM (owner 2026-10-27): getting Python, Git, Node on a bare Mac is the documented Homebrew lines, not checked here |
| R6 | First run, one route | a fresh agent with only README and the URL on the R5a environment: prerequisites -> install -> login -> goal -> plan -> run -> stop -> merge, isolated stores, a fresh sample repo with a GitHub origin, none of the owner's settings | each stage done; every stall or guess is a finding, none left open. Device login reaches its code prompt; completion uses the documented `CODEX_HOME` route with a separate home (named deviation: the device approval needs a human) |
| R7 | Disclosure | README and INSTALLATION, before the login step, say: the Codex login and model access needed (default gpt-6.1-sol); runs cost model tokens and keep running (and spending) after the terminal closes; agents run as the user with full access: files and credentials outside the project, the whole HOME, network; how to stop a run; unsupported platforms (Windows, Intel macOS); uninstall incl. ~/.zp and the Codex home; where to report bugs | text present; R6 stopped a run with the documented command and saw it stopped |
| R8 | Update | isolated install of private v0.6.3, then `zplan update` with `ZPLAN_REPOSITORY` = the export | version 0.7.0, default URL = zeroplan in the installed update.py, launcher points at app/0.7.0, store backup present, setup ran, rollback by docs/UPGRADE.md works |
| R9 | Flip | owner go; R1 and R2 rerun on the final refs; then `curl \| sh` from the public URL in a fresh container within 1 h | install as R4 |

## Order
1. This plan + critic (done); claims table (done).
2. 0.6.3 finishes (E1, release gate, tag v0.6.3, install on the owner's Mac).
3. Commit `rel070` (orchestrator, release metadata like a version commit): the repository URL in install.sh,
   update.py, tests/test_update.py (3 sites + 1 test), version 0.7.0; the old URL joins the private terms so
   export_check guards it; the manifest excludes historical files naming it. Docs fixes (R3, R7): orchestrator.
4. Export (R1, R2) -> new private GitHub repository `zeroplan` (outward: owner confirms the creation).
5. R4-R8 on the export; fixes as batched repair runs here, re-exported under the rerun rule above.
   Then stop for the owner's test (owner 2026-10-27): remove the installed zplan from the owner's Mac (launcher,
   app/, tools/ deleted; store, codex-home, architect, worktrees, ~/.zp moved to ~/zs-pause/mac-uninstall-<date>/;
   the Homebrew `zeroshot` of the harness stays); the owner installs from the private repository by `git clone` +
   `python3 install.py` + `zplan setup` + `zplan login` and tests; findings become repair runs.
6. Release critic on the matrix evidence; owner go; flip (R9). Irreversible.

## Later
Dev home cutover and Actions (PUBLIC_REPO_PLAN steps 5-7); GitHub Pages; distribution and command rename; a
guarded agent mode (`--approve-for-me`) as an option; the owner's installed copy moves to v0.7.0 by `zplan update`
with `ZPLAN_REPOSITORY` or a fresh install.
