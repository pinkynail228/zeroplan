# Public repository as the development home

Owner decision 2026-10-18: the clean public export (scope recorded in the private archive) becomes the main development repository;
this repository becomes a private archive (history, prototype/, reference/, docs/history/, upstream/ checkout).
Tests move to GitHub Actions in parallel with the local gate first. The moment of making it public is a separate
owner go; until then the new repository is private.
This changes the 2026-10-16 decision "the merge gate stays local; the export gets one workflow" (STATE P0 line).

## Measured starting point (2026-10-18, main e9bbf45)
`python3 -I devtools/export_check.py --private-terms <terms outside the repo>` -> exit 1, 24 findings:
11 private-term (AGENTS.md, linux-test.sh:10, PROCESS_PROFILE.md:21, TUI_PLAN.md:15, test_architect.py:371/375,
5 task files), 3 home-path (3 task files), 10 fixture credentials (test_live, test_setup, test_tui_planning,
test_ux, devtools/plan_qual.py, setup.py:244 parser). The private terms list stays outside every repository.

## Steps
1. Scope update (orchestrator, devtools/docs): as the dev home the export carries the orchestration files.
   Manifest: `+ STATE.md` (an explicit include; dropping the exclusion is not enough) and `+ .github/workflows/`;
   devtools/zeroshot/ is already under `+ devtools/`; the audit itself stays out (private archive); this plan is exported after the scrub (private details removed).
2. Scrub task `pub-scrub` (Zeroshot, DeepSeek worker): export_check exit 0 on its candidate with the private
   terms; fixture credentials only via line-level exemptions; `ZPLAN_TEST_HOST` required by linux-test.sh (no
   private fallback); AGENTS.md without private provider/project names and with a neutral pointer to the private
   archive for history; STATE.md/CALIBRATION/task files without home paths and private hosts. The working
   context survives: STATE `Plan/Next/branch/task` stay current, task inputs exist in the export, clone/update
   URLs name the new repository. Live docs that point into excluded files get the needed normative content moved
   in, not just the link removed (docs/TERMINAL_UX_BRIEF.md:3 sends the design to an excluded file; :4 names a
   missing old tag). Behaviour unchanged (Linux full suite).
3. Export (orchestrator), on one named commit with no Zeroshot run in flight (the transfer boundary): `git archive`
   filtered by the manifest into a staging dir without `.git`; `export_check --repo <archive> --commit <SHA>
   --dir <staging> --private-terms <file>`; new `.git` with repo-local identity pinkynail228 + GitHub noreply set
   before the first commit (the owner decision recorded in the private archive) and kept for all later work; one initial commit. Metadata
   gate (export_check does not cover it): author/committer/tagger and messages of every commit and tag to be
   pushed, checked by a recorded command. The exported tree qualified on its own: Linux full suite, Mac full
   suite, install.py.
4. GitHub repository: created private (name by the owner); push of the export. Outward: owner confirms first.
5. Cutover of the dev home, between runs: no running, paused or recoverable Zeroshot run still needs the archive
   (finish or record each); Frozen sources of old runs are not rewritten. In the new checkout: branch upstream and
   the actual Zeroshot `source.remote` point to the new repository (Zeroshot selects the remote by the branch
   upstream, not by the origin URL alone); clone/update URLs in README/INSTALLATION/AGENTS replaced and grep-checked; orchestration smoke from the new checkout (one easy task through
   run.sh). The archive is pushed once more and stays private and read-only.
6. Actions workflow (devtools task in the new repo): ubuntu full unit suite (Python + Textual from PyPI); macOS
   suite as a second job; native qualification (driver_qual/plan_qual) only if the Zeroshot toolchain installs on
   the runner (checked, not assumed). Real-provider, installed and release checks stay local (orchestrator, clone).
7. Gate transition: the next 3 merges run the local gate and Actions on the same candidate SHA. Evidence per
   pair: Actions run/job ids, local command + exit + tested HEAD, toolchain versions, executed test count and the
   skip list (equal verdicts with different skips are not equal coverage, e.g. tests/test_toolchain.py:169
   without the wheelhouse). Actions becomes the merge gate for the scopes it covers only when all 3 pairs agree
   on verdict, failures and skips; a disagreement or a missing required job keeps the local gate. The checks that
   stay local are listed in ORCHESTRATOR.md, changed then through the critic.
8. Making it public: owner go only; before it, rerun export_check and the metadata gate on the final refs.

## Order
Part of the public 0.5 release (RELEASE_0.5_SCOPE.md); does not block 0.4.0. Steps 1-3 need no outward action;
4 creates a private GitHub repository (owner confirms); 5 waits for a gap between runs; 8 is irreversible.

critic pubrepo (session 01a14df0-6929-7b91-840a-d3cf706eb441, xhigh): GO WITH CHANGES (STATE/workflows include,
metadata gate, cutover before the comparison merges, verifiable cutover, working context, transition evidence)
-> applied.
