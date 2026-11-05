# R2 design: a red base settled while planning; a project's first check

Status: R2a built (2a2144d, then the fixes of its review as built: `.local/goldfish/2026-11-05-r2a-built/`) and R2b
built (cb665ee). As built, the record keeps the first failing check's tail instead of an evidence digest (the
approval binds the whole record); a check that cannot start is no red base (the card says so, and starts stay
refused); an unsettled revision settles at approval and refuses if red; the start refuses a HEAD that moved while
its checks ran; every attempt started on the red base asks at merge, and the merge card names the base and its
failure. Revision 2 (2026-11-05), after one Goldfish pass on revision 1 (`.local/goldfish/2026-11-05-r2/`:
comprehension, design_critic, implementation_readiness; section 7 resolves every finding). Revision 2 drops
revision 1's "the base stays red" option and splits R2 into two steps:
- R2a: a red base that the plan's first milestone fixes;
- R2b: making a milestone's new tests the project check.

Both touch merge and start rules, so each is built as a slice with a contract review (`DEVELOPMENT.md` section 2).

Terms:
- *Project check*: a command in the profile's `checks`, run by code (`checks.qualify`). The profile is either the
  project's committed `zplan.process.json` (file source) or a snapshot that zplan keeps outside the project.
- *Merge gate*: the profile's `gates.merge`. Only `required` lets zplan merge by itself, and only after the project
  checks pass on the exact candidate (`gate_merge`, `runs.py:1638`). With the gate off, every merge is the owner's,
  labelled unverified.
- *Base*: the commit a milestone attempt starts from (`destination.base`).
- *Base checks* (D1): the project checks run on HEAD (`Runs.base_checks`). A passed result is cached by a digest of
  the tree and the checks (`base-checks.json`).
- *Red base*: a base on which a project check fails, or cannot run.
- *Plan card*: the card on which the owner approves a plan revision (`Planning.proposal`, `planning.py:704-748`).
- *Settings card*: the consent card for a `zplan_settings` request (P4c). Nothing applies until the owner says yes.

## 1. Problem, with evidence

- **The contract.**
  - `PRODUCT_CONTRACT.md` section 2: "Required checks run on the base before the first attempt. A check that cannot
    run or fails there is settled while planning, never mid-run."
  - Section 7, item 5: "A baseline failure blocks automatic merge. An exception requires reproduction on a named base
    SHA and an explicit owner decision."
- **A red base blocks every start, fixes included** (probe E9, 2026-11-04). The owner committed a failing test.
  - D1 then refused every start (`delivery.py:1009-1011`), including the milestone meant to fix it.
  - The owner had to fix the base himself.
  - Nothing showed the red base before the plan's approval.
- **A project's first tests never become its check** (probe E4).
  - Without checks the merge gate is off, and every merge is the owner's. That rule is right.
  - After a milestone adds tests, `zplan_settings` cannot add a check or turn the gate on: it takes only the level,
    parallel runs, the gate and roles (`architect.py:153`). And the gate refuses `required` without checks
    (`process.py:778-780`).

## 2. Goals and non-goals

Goals:
1. **R2a.** Before the owner approves a plan, the plan card shows the result of the base checks. When the base is red,
   the owner's yes on that card lets the plan's milestones start on exactly that base. Their merges wait for his yes,
   which is the contract's named-base exception. Once a merge has made the base green, the flow is automatic again.
2. **R2b.** After a milestone has added tests, one settings card puts a check and `gates.merge: required` into the
   profile together. From the next approved plan on, merges are automatic.

Non-goals:
- A base that stays red while the plan's milestones merge. The candidate gate refuses any failing check
  (`runs.py:1730-1734`), and a per-check exception is a contract change.
- Letting a check that a plan introduced gate its own milestone.
- Writing a file-source profile: zplan never edits the project's committed `zplan.process.json`. For that case the
  architect names the exact edit, as `Profile.preview`'s refusal already does (`process.py:1069-1072`).

## 3. Design

### R2a: a red base settled while planning

1. **When the base checks run.** At the end of the plan job, after the plan check reaches a verdict (the revision is
   `proposed`, or `review_exhausted` for an override), the job runs the base checks.
   - It uses `Runs.base_checks` with the profile read through `status()`, not `guard("milestone")`. So an undecided
     profile stays undecided, and a task-gate refusal does not break planning.
   - The card appears after the checks end. Their time is bounded by the profile's own timeouts, and the plan
     job's progress line says that the checks are running.
2. **Where the result is kept.** The revision gets a new optional top-level key, `base_checks`, as `live`, `override`
   and `draft` are kept (`authority.py:714-718`). It holds the base commit, the tree, the checks digest, the outcome,
   the names of the failed checks (empty for a refusal, with its reason), and the evidence digest. Older stores
   simply lack the key, and older zplan versions refuse a store that has it, as with every new key (UPGRADE notes
   it).
3. **The card and the status.** One line, in three exact forms:
   - "Checks on the base: all passed (<names>)."
   - "Checks on the base: <names> fail on <commit>. The first milestone must fix them; its merge waits for your yes."
   - "No project check: merges wait for your yes." This form is shown whenever the profile lists no checks or the
     merge gate is off.

   `zplan_status` carries the same under `plan.base_checks`. The architect's method gets one line: on a red base, the
   plan's first milestone fixes it.
4. **Approval.** `Planning.approve` and `Planning.override` approve the revision with its `base_checks` as they are
   on the record. They are not run again, so the owner approves exactly what the card showed. `approval_identity`
   binds the evidence digest.
   - The architect never approves a revision with a red `base_checks` by itself: `approves_alone` is false for it,
     so its card goes to the owner.
5. **D1 at start.** The base checks run as today.
   - When they fail, the start may proceed only on the recorded red base: HEAD's tree equals the approved revision's
     `base_checks.tree`, the checks digest is the same, and the same checks fail. The same failure is required
     because a flaky or new failure is not what the owner accepted.
   - Any other failure refuses, as today.
6. **Merge.** An attempt whose `destination.base` is the approved revision's red base commit is never merged
   automatically. `Delivery.merge` refuses it with the new family `merge.base_red` before the gate runs. The
   Controller turns that into the owner's merge card, as for `autonomy.ask` (`controller.py:2046`).
   - The card names the base commit and the failed checks.
   - The owner's merge still runs `gate_merge`: the candidate's checks must pass, so only a candidate that fixes the
     base lands.
   - The rule is derived from the two stored records, so it fails closed: no side file can be lost.
7. **After the fix.** HEAD moves. The next start's base checks pass on the new tree, and the next attempts' bases
   are not the red commit. The flow is automatic again.

### R2b: the first check

1. `zplan_settings` accepts `checks` (a list of `{name, argv, timeout_s}`). Together with `merge: required`, the
   change is validated by `process.apply_changes`:
   - `CHANGE_KEYS` gains `checks`;
   - the checks are applied before the `required` rule reads them;
   - `_setting_lines` shows each check's full argv and timeout (`check_text`).
2. It stays owner-turn only (P4c). The architect's plan-end report suggests the check in one sentence. The owner's
   word in the chat starts the turn that opens the settings card.
3. **The profile source.** A snapshot profile gets the change. For a file-source profile the request is refused with
   the exact edit to make.
4. **When the change applies.** Approval freezes the profile's digest (`PRODUCT_CONTRACT.md` section 5, item 7), so
   the new check takes effect from the next approved plan. The architect's next revision of the current plan is
   refused as `plan.gate_stale` and re-checked, as today for any profile change (`authority.py:1066-1068`).

## 4. Alternatives

| Alternative | Verdict |
|---|---|
| Revision 1's side file `base-accepted.json` | Rejected: it is lost on corruption, its loss fails open, and it misses the approval's identity. The revision key fails closed and is bound to approval |
| Let a base stay red under an owner exception per check | Rejected for R2: it is a contract change, and the candidate gate refuses any failing check. The backlog keeps it, triggered by a project whose red check the owner wants to keep |
| Key `merge.base_red` on the destination head at merge time | Rejected: it needs another base run at each merge. Attempts started on the red base asking the owner is bounded by the plan's first fixing milestone |
| Refuse to approve a plan on a red base | Rejected: nothing can fix the base without a start (E9) |
| Let an event turn open a `checks` settings card | Rejected: it breaks P4c's owner-turn rule for a once-per-project need; the owner's one word costs little |
| Apply the new check to the current plan | Rejected: approval freezes the configuration (contract) |

## 5. Risks

- **Plan card latency.** The checks run before the card shows, bounded by their timeouts. A project with slow checks
  waits longer for its first card on a new tree. Passed results are cached by tree.
- **Commands before approval.** The base checks are the profile's own commands. For an undecided profile they are the
  auto-detected ones (`process.py:639-671`), which the owner saw on the first-start screen. They run in a disposable
  checkout, as D1's do today.
- **A flaky check.** The same-failure rule refuses a start whose failure differs from the approved one. The architect
  then revises the plan, and the owner sees the new card.
- **A model-written check command** (R2b). It runs on every later candidate after the owner's yes. A command that
  always passes, such as `true`, would weaken the gate. The card shows the full argv, and the owner approves it.
- **Rollback.** A store with `base_checks` on a revision cannot be opened by older versions; UPGRADE says so. In-flight
  attempts on a red base are refused by `merge.base_red` only in this version.
- **The contract's "owner twice".** A red base adds a merge yes for every attempt started on it (usually one), and
  every architect revision while the base is red goes to the owner. A project's first check adds one word and one
  card, once per project.

## 6. Change, tests and live checks

**R2a code:**
- `authority.py`: the optional key, its validation, and approval identity;
- `planning.py`: the plan job's base run, the card line, `approve`/`override`;
- `autonomy.approves_alone` and its caller;
- `delivery.py`: D1's same-failure rule and `merge.base_red`;
- `catalog.py`: the new family;
- `tui/controller.py`: `plan_fields` and the merge-ask path;
- the method line; UPGRADE.

**R2a tests** (behaviour, through Planning, Delivery and the Controller with the fixture engine):
- a red base on the card and in status;
- approval keeps the shown result;
- the architect cannot approve a red-base revision alone;
- a start on the recorded red base proceeds;
- a start refuses on a moved base and on a different failure;
- an automatic merge is refused with `merge.base_red`, and the owner's merge of a fixing candidate lands;
- after the fix, the next milestone merges by itself;
- override covered.

**R2b code:** `process.py` (`CHANGE_KEYS`, `apply_changes`), `tui/controller.py` (`TOOL_ARGUMENTS`,
`_settings_changes`, `_setting_lines`), `architect_tools.py` (schema), `architect.py` (the tool text).

**R2b tests:**
- a settings card adds a check and the gate together;
- a file-source profile is refused with the edit;
- an events turn is refused.

**Live at the release:**
- a repository with a committed failing test: the card shows it, the first milestone fixes it, one merge yes, then
  the next milestone merges by itself;
- a new repository without tests: plan yes, merges with yes, one word and one settings yes, then the next plan
  merges by itself.

## 7. Resolution of the Goldfish findings (revision 1)

Reviewers: R implementation_readiness, D design_critic, C comprehension.

| Finding | Resolution |
|---|---|
| An owner's yes cannot land a candidate that still fails, so "stays red" is unreachable (R B1, D 1, C 2) | Accepted: the option is dropped. The first milestone fixes the base; the owner's merge still requires the candidate's checks to pass |
| The tree key cancels the acceptance after one merge (R B2, D 3, C 3) | Accepted: by design after the fix. Without "stays", only the attempts started on the red base ask, and the next starts see a green base |
| The shown result is not stored; flaky checks (R B3, D 4) | Accepted: `base_checks` on the revision; approval keeps it; the start requires the same failure |
| The architect can approve a later revision alone (D 2) | Accepted: `approves_alone` is false for a red-base revision |
| The architect cannot propose settings in an event turn (R B4, D 6) | Accepted: owner-turn kept; the report suggests the check and the owner's word starts the turn |
| Adding a check does not turn on the gate (R B5, D 5, C 1) | Accepted: `checks` and `merge: required` in one change |
| File-source profiles are refused (R M1, D 7, C 5) | Accepted: snapshot only; the architect names the edit for a file source |
| Missing touch points; open choices; override (R M2-M3, D nits) | Accepted: section 6 names them; override covered |
| The "No project check" line is wrong when the gate is off; refusals have no names (R M4, D nit) | Accepted: three exact forms; a refusal records its reason |
| Side effects of `guard`; cost; latency; security of commands before approval (R M5, D nits, C 7) | Accepted: read through `status()`; latency and command risks in section 5 |
| The side file fails open; rollback (D 8) | Accepted: the rule is derived from the stored records, so it fails closed; rollback stated |
| The rejected alternatives did not hold (D 9, R N2) | Accepted: the revision key chosen; the head-at-merge alternative weighed |
| The check change against the contract's freeze (C 6) | Accepted: R2b applies from the next approved plan |
| The key used at merge (C 4) | Accepted: the attempt's base commit against the revision's red commit |
| Untested cases (R M6) | Accepted: section 6 lists the cases |
| Nits: citations (section 7, not 5), card text, the bounds of `base-checks.json`, the contract's "owner twice" | Fixed in the text; the cache's bound is left as it is (a passed entry per tree) |
