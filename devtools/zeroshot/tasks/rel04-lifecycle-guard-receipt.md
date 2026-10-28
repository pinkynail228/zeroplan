# rel04-lifecycle-guard — receipt

Release 0.4.0 class repair 1 of 2 (step 11 BLOCK F-1; class audit critic rel04-classes, session
01a15375-895d-7402-aae0-bfba5d11deec, /tmp/zs-zplan/critic/rel04-classes.out). Replaces the stopped point
repair rel04-fixes (run 01a15382, no changes). DeepSeek worker, sol reviewers. Part of release candidate C2.

- **Two bases.** Regression baseline `56a8b57b0a5f7f6540c34e306ab8ebd4cc2d8f05` (main; the run's own
  `git status --porcelain` was empty at start) and repair base `684c4b64ae057cfa47dab6f7954ff091cbb90336` (the
  stopped candidate, committed unchanged; `Runs.revise_plan`'s caller guard already removed, runs.py:1300-1306).
- **Final tested tree.** `684c4b6` plus this repair's two files only — `tests/test_lifecycle_guard.py` (+201/−77)
  and this receipt (documentation; its own line count moves with each edit). `git diff 684c4b6` touches no other
  path; `terminal_planner/**` and every other test stay byte-identical to `684c4b6`. Stable anchor for the code
  under test: `sha256(tests/test_lifecycle_guard.py)` =
  `a9f7d8999a87af3856bccd51475b33ddb0966763c253a0fc0d31db1a551530d2`. (A whole-tree SHA cannot be embedded in the
  receipt it covers; delivery's `git add --all` commit is the orchestrator's.)
- Audit snapshot: `c242370`. The audit's line numbers were re-checked. On the regression baseline `56a8b57` they
  all hold (authority.py save :646, begin :665, approve :741, override :767; planning.py begin :296, `a.begin` :303,
  renew :311; runs.py ACTIVE :45, `Runs.active` :577, start's active check :604, resume's :986, revise_plan :1292,
  check_followup's active check :1311, revise :1355, both `self.authority.begin` :1299/:1359; delivery.py guard
  :528, start :569, merge :805; process.py freeze_plan :660, live_digest :669; cli.py plan flow :413-414). On the
  repair base `684c4b6` (= this tree) the product moved by the R-1/R-2 change: authority.py save :646,
  live_profile_digest :665, begin :671, approve :753, override :781; planning.py begin :296, `a.begin` :303, renew
  :305, revise :358; runs.py ACTIVE :45, `active_run` :50, `Runs.active` :585, start :594, resume :988, revise_plan
  :1300, `self.authority.begin` :1305, check_followup :1310, revise :1360, `self.authority.begin` :1364; delivery.py
  guard :528, start :569, merge :805; process.py guard :640, freeze_plan :660, live_digest :669; cli.py plan_flow
  :412. The two A-1/A-3 amendments of the re-specified task do not depend on a product line number.
- This file is the repair receipt (visit 5; run 01a1539a was force-stopped after round 4 under the ORCHESTRATOR
  step-2 stop rule and committed unchanged as `684c4b6`). Visits 1–4 of the stopped run and their fixes stand
  (visit 1: A-1 matrix completeness + scanner evasion and A-3's fixture session; visit 2: invalid direct-owner
  stores, `Runs.revise` covering only one ACTIVE writer state, no valid approval context, and an A-3 pilot with an
  internal all-green readiness stub whose base failure was misreported as a timeout; visit 3: the positive approval
  control hardcoded a single `stopped` history). Visit 5 applied the task's re-specified A-1 and A-3: (1) A-1
  became a **closed syntactic inventory** of `begin` calls — every `ast.Call` whose `func` is an `ast.Attribute`
  with `attr == "begin"` — compared as an exact `collections.Counter` (the fixed-predicate, two-set scan the
  round-4 reviewers evaded is gone); (2) A-3's plain half became a regression guard whose evidence is a
  **candidate-only mutation** that disables only the owner guard in `Authority.begin`. Visit 5 was rejected on two
  findings, both repaired here (visit 6, still test/receipt only): **(i)** the ordinals were assigned in AST
  *traversal* order, which is not source order for a dict literal (`{a.begin(): b.begin(), c.begin(): d.begin()}`
  numbered a=0, c=1, b=2, d=3) — the scanner now collects per scope and orders by source position before
  numbering, with `test_the_ordinals_are_source_order_not_ast_traversal_order` as the independent synthetic oracle;
  **(ii)** the receipt omitted A-4's named baseline failures — the four `DigestProviderTests` refusals that fail on
  `56a8b57` are now recorded by name in "Acceptance / A-5".

## Change (product)

- `terminal_planner/runs.py`
  - `active_run(records)` — one shared "active writer" predicate (`status in ACTIVE`), the single notion:
    `MilestoneRuns.active` and the `Authority.begin` guard both read it, no copy of the status set.
  - `MilestoneRuns.revise_plan` and `MilestoneRuns.check_followup`: the duplicate active-writer checks removed
    (see "removed caller checks").
- `terminal_planner/authority.py`
  - `Authority.begin`: refuses, before anything is read or written, while any run is in an `ACTIVE` state —
    family `action.refused`, message pattern `Milestone M… ещё выполняется; новая revision плана после его
    завершения или остановки.` Placed right after `check_project()`, before the profile freeze (so a refusal
    reads no profile sidecar and writes nothing).
  - `Authority.live_profile_digest()`: the session-bound provider (`self.profile.live_digest()`, or None when the
    session is explicitly unprofiled).
  - `Authority.approve(version)` / `Authority.override(version, reason)`: the `live_digest` parameter is gone;
    the digest is read from `live_profile_digest()`. No caller can disable (`None`) or replace (a supplied
    digest) the bound provider.
- `terminal_planner/planning.py`: `approve`/`override` no longer pass a digest; they call the owner API.

## Callers now covered

A-1's **closed inventory** of production `begin` calls (asserted by `BeginInventoryTests` against the real scanner
over the package source): every `ast.Call` whose `func` is an `ast.Attribute` with `attr == "begin"`, keyed by
(file, qualified scope, canonical receiver `ast.unparse`, ordinal in source order in the scope) and compared as an
exact `collections.Counter` — **10 occurrences today**. The ordinal is the *source* order: occurrences are collected
per scope and ordered by source position before numbering (never the AST visit order — a dict literal visits its keys
before its values), and the position never enters the identity. The four Authority callers, each explicitly bound to
its state x action matrix row (`AUTHORITY_BEGIN_ROWS`):

1. `Planning.begin` (planning.py:303, as `a.begin`) — matrix row `Planning.begin`; TUI goal form `[p]`/chat draft
   `c` → Ctrl+G, plain `[p]`.
2. `Planning.renew` (planning.py:305, `self.authority.begin`) — matrix row `Planning.renew`; `send`/`restart`/
   `renew` renewal and the plain `[n]`.
3. `MilestoneRuns.revise_plan` (runs.py:1305, `self.authority.begin`) — matrix row `Runs.revise_plan`; owner plan
   revision (`Planning.revise`, `[r]`, TUI revise).
4. `MilestoneRuns.revise` (runs.py:1364, `self.authority.begin`) — matrix row `Runs.revise`; steward follow-up /
   accepted proposal → plan revision.

The six others (known non-Authority candidates, listed by identity): `Architect.send` (`self`), `App.plan_flow`
(`self.planning`), `FixtureDriver.resume` (`self`), `FixtureDriver.submit` (`self`), `ArchitectChat._turn`
(`architect`), `Controller.start_planning.work` (`planning`).

All four Authority callers inherit the guard from the mutation that owns the state; the reachable instance (goal
form while M1 active) no longer creates revision r2, so r1's run is not dropped from the overview.

## Removed caller checks (now strictly redundant)

- `MilestoneRuns.revise_plan`: its `busy = self.active(); require(...)` block.
- `MilestoneRuns.check_followup`: its `require(self.active() is None, "Другой milestone run активен; …")`. Every
  caller of `check_followup` (`retry`, `answer`, `accept_proposal` → `start`, `revise` → `begin`) reaches a
  mutation that enforces the same predicate, so the condition is redundant; the other conditions of
  `check_followup` are kept unchanged.
- Kept on purpose (not redundant with `begin`): `MilestoneRuns.start`'s own active check (runs.py:604) and
  `MilestoneRuns.resume`'s (runs.py:986) — both guard paths that do not create a plan revision.

## A-1 coverage and state x action matrix (repair)

`tests/test_lifecycle_guard.py` (new at `684c4b6`; 634 lines after this visit's A-1 rewrite):

- **Direct owner guard** (`test_a1_direct_authority_begin_refuses_in_every_active_state`, repair 3): each of the
  six `runs.ACTIVE` states is a *validated* store (`self.build(state)`; the undispatched statuses drop the run id,
  as `validate_run` requires), not a status-only mutation of a submitted record — that variant only produced a
  `store.invalid` family mismatch at `save()` on the base instead of the missing guard. `Authority.begin` refuses
  with the Authority bytes, Git refs and the side-effect counters unchanged and no revision appended.
- **Closed syntactic inventory + oracle** (`BeginInventoryTests`): the real scanner returns every `begin` call of
  the package source as (file, qualified scope, canonical receiver, ordinal in the scope), compared as an exact
  `Counter` against the expected 10 (`test_the_ten_production_begin_calls_are_the_exact_multiset`); the four
  Authority rows are each present once and bound to a matrix row
  (`test_the_four_authority_callers_are_each_bound_to_a_matrix_row`), and the six others are listed by identity
  (`test_the_six_other_begin_calls_are_listed_by_identity`). The oracle behind the check runs the **same scanner
  over hand-written source** (never a mock): `test_the_comparison_accepts_the_reviewed_source` is the positive
  control, `test_the_ordinals_are_source_order_not_ast_traversal_order` is the round-5 oracle (a dict literal
  `{a.begin(): b.begin(), c.begin(): d.begin()}` must number a=0, b=1, c=2, d=3, and the AST traversal order
  a=0, c=1, b=2, d=3 must fail the comparison), and `test_the_comparison_flags_every_change` shows an added call
  inside an already listed function (the round-4 `authority = self.authority; authority.begin(...)` alias in
  `App.plan_flow`), a duplicated call, a removed call and a changed receiver each fail, with a message that names
  the occurrence and asks for a review.
  The whole-package round-4 alias (added to `cli.App.plan_flow` in a scratch copy) fails the inventory the same way
  (see "Mutation checks").
- **Matrix** (`test_a1_plan_creating_actions_refuse_in_every_active_state_and_are_allowed_for_every_terminal_outcome`):
  actions {`Planning.begin`, `renew`, `send`, `restart`, `revise` (plan), `Runs.revise_plan`} x run states {none,
  each of the six `ACTIVE` states, each terminal outcome}. The terminal outcomes are the production constants
  `runs.OUTCOMES` (done, needs_owner, blocked, invalid) as a finished run, plus the terminal statuses without a
  done outcome (`failed_recoverable`, `failed`, `stopped`). Plan-creating actions refuse in every ACTIVE state with
  the "Milestone M… ещё выполняется" message and unchanged bytes/refs/worktrees/driver counters, and append exactly
  one revision with no active run (positive control). `Planning.send` on the approved revision is the no-op "sent".
- **Steward follow-up matrix** (`test_a1_steward_revise_refuses_in_every_active_writer_state_and_proceeds_for_every_terminal_attempt`,
  repair 3): `Runs.revise` over a *valid* target (M1's latest failed attempt, accepted by `check_followup`) x the
  independent M2 writer in each of the six `ACTIVE` states — refused by the owner guard, not `check_followup`'s
  "not the latest attempt" — and, with no writer, allowed for every unsuccessful terminal attempt
  (`needs_owner`, `blocked`, `invalid`, `failed_recoverable`, `failed`, `stopped`) and refused for a successful
  (`done`) one. Every writer state is a validated record (undispatched states drop the run id, each variant is
  saved and re-read), with the bytes/refs/records/counters asserted unchanged on the refusal.
- **Approve/override** (`test_a1_approve_and_override_are_refused_for_the_revision_status_in_every_state`): the
  revision-status refusal in every state, bytes unchanged. **Positive control over the whole state domain (repair
  4)**: `test_a1_approve_and_override_are_allowed_on_a_new_revision_beside_every_terminal_outcome` runs
  {none} ∪ `TERMINAL_KEYS` (no run, or one terminal attempt per outcome/status: `done`, `needs_owner`, `blocked`,
  `invalid`, `failed_recoverable`, `failed`, `stopped`) x {`approve`, `override`}: `revise_plan` creates revision 2
  (no active writer), its gate leaves it `proposed` (accepted) or `review_exhausted` (rejected), and the action
  succeeds with revision 1's record and every run record asserted byte-identical afterwards. The reviewer's
  mutation — an incorrect refusal of `override` beside `finished` history — left the previous single-`stopped`
  control, the refusal matrix and all of `test_plan_override` green; it now fails this test for `done`,
  `needs_owner`, `blocked` and `invalid` (4 subtests), and the same mutation on `approve` fails the 4 `approve`
  subtests.
- **Side-effect counters**: `CountingDriver` counts every submit/force-stop/resume/watch; `counters()` also folds
  in the Authority bytes, Git refs, revision/run counts and worktree directories.

## A-3 TUI production entry point (repair)

`tests/test_tui_chat.py` `LifecycleGuardChatTests` (non-fixture, ~250 lines): a real production controller
(`fixture_id=None`, `profile=True` over a real accepted `zplan.process.json`, the real `Planning`/controller
wiring). Fakes only for the external dependencies: the scripted codex (provider), native engine/driver doubles for
the pinned `zeroshot` CLI, and readiness' own external boundary — the pinned toolchain's installation receipt and
binaries (`patch.object(setup, "tool_paths"/"check_installation")`, as `test_tui_polish` does) with a fixture
`CODEX_HOME` login. Readiness itself is **production** (repair 3): `setup.readiness(self.project, self.native_root)`,
the same callable `cli` hands the TUI, asserted to carry every `planning.NEEDS["plan"]` id and to be all-`ok`; the
earlier `Readiness(check("git"))` stub — an internal all-green list that left the plan gate and the profile
unexercised — is gone. `native_root` is `short_root()`, so the socket check does not depend on the process TMPDIR.
M1 is a native run held active by explicit Event barriers (its `watch` is gated, so the run cannot finish until the
test releases it; the controller follows it, so the slice is genuinely parked on the fake run while Ctrl+G hands
the goal draft over). The lifecycle identity is read **before** Ctrl+G and the hand-over is awaited on the
controller worker itself (a marker job queued behind it), so no assertion depends on elapsed time. Asserted: the
accepted profile is bound (`App.snapshot.profile is not None`), the store is the production one (`"fixtures"` not
in its path) and the revision engine is `native`; revision/approval and run identity are unchanged; the hand-over is
refused with the R-1 message (not `chat.OUTDATED`); M1 is still on home; releasing the run lets its result export
and merge through the existing actions.

## A-3 plain path (regression + candidate-only mutation)

`PlainFlowTests.test_a3_plain_revise_is_refused_while_active_and_the_run_still_delivers` drives the real line UI
(`cli.session`) with a fixture driver: the plain `r` is refused with the R-1 message, revision/run identity are
unchanged, and the later observe/export/merge still delivers.

This is **not** a base failure on either base, and the amended A-3 says so explicitly: `684c4b6`'s `begin` refuses
through the owner guard, and `56a8b57` refuses through the `Runs.revise_plan` caller copy R-1 removes (same family,
same `Milestone M… ещё выполняется` pattern). Both bases were checked passing with the final test file. The evidence
that the test guards the *owner* guard is therefore a **candidate-only mutation** in a scratch copy that disables
*only* `Authority.begin`'s guard (the caller guard is already gone on `684c4b6`, so nothing else is touched): the
plain `r` then reaches the planner, creates revision 2, and the test fails at its named behavioral assertion
`self.assertIn("ещё выполняется", output)`. The run ends normally — the extra trailing `[q]`s in the scripted input
exist only so the mutated run can end, so the failure is the assertion, never an EOF/input exhaustion. The TUI chat
hand-over (`test_tui_chat.LifecycleGuardChatTests`) remains the class-level A-3 base failure.

## Deferred

- **Start/merge process admission (class audit F-2's start/merge half).** The class audit marks it latent: the
  normal paths are guarded by `Delivery` (`Delivery.guard("milestone"|"merge")`, `Delivery.start`, `Delivery.merge`),
  and frozen recovery is a separate allowed path. Direct `Runs.start`/`Runs.merge` still bypass the process policy.
  Not touched here (R-3); deferred to the 0.5 S1a/S1c gate work, where the process admission moves into the
  mutations. R-3 keeps every allowed path (observe, stop, export, merge, resume/adopt, integration refresh,
  pending-dispatch recovery) on its own preconditions.

## Acceptance / A-5

A-5 requires the named failures and the skips separately; import/missing-symbol/setup failures do not count. Both
bases are reported, each run with the **final** test files; the non-candidate base restores the three product files
from git in a scratch copy (`/tmp/zs-b-*`, `TMPDIR=/tmp/zs-agent-*`), the candidate (this tree) leaves the product
untouched.

### Against the regression baseline `56a8b57` (main; product restored)

`python3.13 -m unittest test_lifecycle_guard test_tui_chat.LifecycleGuardChatTests
test_plan_override.DigestProviderTests` → **20 tests, 35 named subtest/assertion failures, 0 errors, 0 skips**:

- `test_a1_direct_authority_begin_refuses_in_every_active_state` — 6 subtests (one per ACTIVE state), each
  `AssertionError: Blocked not raised` at the `assertRaises` line. Valid stores, so the failure is the missing
  guard, not the invalid-fixture `store.invalid` mismatch an earlier receipt wrongly reported.
- `test_a1_plan_creating_actions_refuse_in_every_active_state_and_are_allowed_for_every_terminal_outcome` — 18
  subtests (`Blocked not raised`): `Planning.begin|renew|restart` × the six ACTIVE states (the actions
  `Planning.begin`/`renew` reach, per the acceptance clause). `Planning.revise`/`Runs.revise_plan` refuse through
  the base's own caller copies and `Planning.send` is the no-op "sent", so those combinations pass on the base.
- `test_a1_steward_revise_refuses_in_every_active_writer_state_and_proceeds_for_every_terminal_attempt` — 6
  subtests: `AssertionError: 'M2 ещё выполняется' not found in 'Другой milestone run активен; один writer на
  проект.'` — the base refuses through `check_followup`'s own copy with a *different* message, so ownership (and
  the message) is what changed. The terminal-attempt half passes on the base.
- `test_tui_chat.LifecycleGuardChatTests.test_a3_…` — `AssertionError: Lists differ …` at
  `self.assertEqual(after["revisions"], before["revisions"])`: the base's `begin` has no owner guard, so Ctrl+G
  appends revision 2 (identity captured before Ctrl+G, the hand-over awaited on the controller worker).
- `test_plan_override.DigestProviderTests` (R-2 baseline) — **4** failures, each `AssertionError: Blocked not
  raised`: `test_r2_approve_refuses_a_drifted_configuration_with_no_caller_digest`,
  `test_r2_override_refuses_a_drifted_configuration_with_no_caller_digest`,
  `test_r2_an_unusable_profile_is_refused_with_no_caller_digest` and
  `test_r2_a_postponed_profile_is_a_bound_provider`. The base's `approve`/`override` read the digest only when the
  caller supplies one (`None` disables the comparison), so no refusal is raised — this is the R-2 defect and the
  copy R-2 removes. `test_r2_execution_one_needs_no_digest` passes on the base (a v1 revision has no gate to
  compare against) — a regression guard, recorded, not hidden.
- Skips: none in these modules.

Passing on the base (regression/structural guards, recorded, not hidden): `BeginInventoryTests` (the inventory is
source-derived, so identical on both bases — 10 occurrences), `PlainFlowTests` (A-3 plain: the base refuses through
the caller copy), `AllowedPathsTests` (A-2: observe/stop/export/merge/resume/refresh never go through `begin`), the
approve/override refusal matrix and the parameterized positive control (16 subtests — the base allows approval
beside terminal history too), and the `runs.py` message-ownership subtests that already pass. The stopped receipt's
claim that the plain A-3 test was "not a base failure" is correct and is now stated as the amended A-3 requires:
a regression guard, not a base failure.

### Against the repair base `684c4b6` and the final tested tree (this repair)

`TMPDIR=… PYTHONPATH=.:tests python3.13 -m unittest test_lifecycle_guard` → **14 tests OK** (the 10-occurrence
inventory, its oracle, the direct guard, the matrix, the steward matrix, approve/override, A-2 and the plain path);
`test_plan_gate test_plan_override test_terminal_planner test_runs test_process test_live test_architect
test_milestone` → **421 tests OK** (`test_plan_override` carries the five `DigestProviderTests` R-2 cases — all
green here, against the four named baseline failures above); `test_tui_chat` → **117 tests OK**. No failures.

### Mutation checks (scratch copies, final test files)

- **A-3 plain / owner-guard mutation (candidate-only).** `Authority.begin`'s `busy = active_run(...)` set to `None`
  — nothing else touched, so only the owner guard is disabled → `test_lifecycle_guard test_tui_chat.
  LifecycleGuardChatTests` → **15 tests, 44 failures**: the direct test 6, the plan-creating matrix 30
  (`Planning.begin|renew|restart|revise|Runs.revise_plan` × six states), the steward matrix 6, the TUI class 1, and
  `PlainFlowTests` 1 — which fails at its named behavioral assertion `self.assertIn("ещё выполняется", output)`
  (the plain `r` created revision 2 instead of being refused). This is the A-3 plain evidence.
- **A-1 inventory at the package level.** `authority = self.authority; authority.begin(goal, self.roles, "native")`
  added inside the real `cli.App.plan_flow` (the round-4 evasion) → `BeginInventoryTests` fails: *"begin call
  inventory changed: 1 occurrence(s) differ from the reviewed set; review the change: cli.py:App.plan_flow
  receiver=authority ordinal=1 (expected x0, found x1)"*.
- **A-1 inventory oracle (in-test, real scanner).** `test_the_comparison_flags_every_change` runs the real scanner
  over hand-written source: the added round-4 alias, a duplicate, a removal and a changed receiver each raise the
  comparison error naming the occurrence; `test_the_ordinals_are_source_order_not_ast_traversal_order` shows the
  dict-literal AST traversal order (`a=0, c=1, b=2, d=3`) fails while the source order (`a=0, b=1, c=2, d=3`) passes.
- **Owner guard knows only `submitted`** (the "running writer" mutation the round-3/4 reviewers ran): the guard
  reads only runs with `status == "submitted"` → `BeginGuardTests` fails **36** subtests — the direct test, the
  plan-creating matrix and the steward matrix for every non-`submitted` state (`preparing`, `resume_pending`,
  `running`, `stopping`, `submission_unknown`).
- Retained from the stopped run's receipts and still valid because the product is byte-identical at `684c4b6`
  (not re-derived here): a state-dependent approval refusal fails the parameterized positive control for
  `done`/`needs_owner`/`blocked`/`invalid`; removing `accept_profile()` fails the TUI class; restoring only the base
  `approve`/`override` fails `DigestProviderTests` 4/5 — those four are the named R-2 refusals recorded in the
  baseline section above.

## Product / test split

- **This visit is test/receipt only.** `git diff 684c4b6`: `tests/test_lifecycle_guard.py` +201/−77 (the only code
  change; 124 net new lines) plus this receipt (documentation) — the code change is well under the 300 changed-line
  size target — and no product line: `terminal_planner/**` is byte-identical to `684c4b6`.
- Product (unchanged since the stopped candidate `684c4b6`): `terminal_planner/authority.py`,
  `terminal_planner/planning.py`, `terminal_planner/runs.py` (~56 lines changed, ~30 added), from the original
  task.
- Tests (the stopped candidate `684c4b6`, unchanged here except `test_lifecycle_guard.py`):
  `tests/test_lifecycle_guard.py` (now 634 lines: the closed 10-occurrence `begin` inventory + its oracle, the
  direct guard, the state×outcome matrix, the steward-follow-up matrix, the approve/override refusal matrix + the
  positive control over every state, A-2 allowed paths, A-3 plain); `tests/test_plan_override.py` (+A-4 R-2 cases);
  `tests/test_tui_chat.py` (+A-3 non-fixture TUI class); `tests/test_plan_gate.py`.

## Checks run (targeted, this worktree)

`TMPDIR=/tmp/zs-agent-* PYTHONPATH=.:tests /opt/homebrew/bin/python3.13 -m unittest …` on the final tree:

- `test_lifecycle_guard` → 14 OK.
- `test_plan_override test_plan_gate test_runs test_terminal_planner test_process test_live test_architect
  test_milestone` → 421 OK.
- `test_tui_chat` → 117 OK.
- `test_install test_plan_qual` → 27 tests OK, **5 skips**. The five skips are `test_install.InstalledGateTests`
  and their reason is the missing wheelhouse — `ZPLAN_TEST_WHEELHOUSE не задан: installed-app gate требует offline
  wheelhouse (setuptools 75.8.0, wheel 0.45.1, textual 8.2.8 с зависимостями)` — **not** a Linux-only
  qualification (corrected from the stopped receipt).
- `git diff --check` clean; no `.pre-commit-config.yaml` and no `.git/hooks/pre-commit` (nothing to run).

Full suites and the platform qualification remain the orchestrator's merge gate (ORCHESTRATOR.md, change loop 2).

## Interpretations

- A-1's coverage is the *closed syntactic inventory*: a *direct* `Authority.begin` test (the owner guard protects
  the class) plus the exact `Counter` of every production `begin` call, keyed by (file, qualified scope, canonical
  receiver, ordinal). There is no fixed receiver predicate to evade — an added, duplicated, removed or
  re-received call changes the multiset — and the oracle is the real scanner over hand-written source (never a
  mock). The matrix's ACTIVE records are real fixture runs moved to a named state by a validated `save()`;
  `preparing`/`submission_unknown`/`resume_pending` drop the run id, as an undispatched record requires. The
  `invalid` outcome is not a scripted fixture outcome, so it is the finished record reset exactly as the native
  "invalid" evaluation leaves it (no output, no manifest, no result).
- "Valid unsuccessful follow-up beside an independent active writer": `Runs.revise` needs an unsuccessful, latest
  attempt, so the independent writer is another milestone (M2, startable once M1 is integrated); otherwise the
  refusal would be `check_followup`'s "not the latest attempt", not the guard's. The reviewer's "running writer"
  mutation (a guard that only knew `submitted`) is caught by the `running` subtest of this matrix, of the direct
  test and of the plan-creating matrix.
- `approve`/`override` beside an ACTIVE writer are not a reachable combination (a proposed revision beside an
  active writer cannot exist: `begin` is what would create it and it refuses); the matrix therefore asserts their
  refusal for the revision-status reason in every state, and the valid approval context — a proposed
  (`review_exhausted` for override) revision *beside terminal history*, which the refusal matrix cannot build — is
  asserted allowed in `test_a1_approve_and_override_are_allowed_on_a_new_revision_beside_every_terminal_outcome`,
  plus the R-2 digest cases in `test_plan_override` / `test_plan_gate`.
- A-3's readiness is the production callable; only the toolchain boundary is doubled. `CODEX_HOME` is a fixture
  login directory (readiness judges auth by presence), and `tool_paths`/`check_installation` are patched for the
  pinned binaries — the same external-boundary doubling the existing Settings-screen tests use.
- A-3's *plain* half cannot be a behavior difference on either base (the base's caller copy refuses too, and the
  candidate's owner guard refuses), exactly as the amended A-3 states; its evidence is the candidate-only
  owner-guard mutation recorded above, not a base failure. The non-fixture TUI class uses a `zplan.process.json`
  kept out of the checkout (`.git/info/exclude`) so the clean-tree precondition and the accepted profile both hold.
- The guard reads `runs.active_run` through a call-time import of `runs` (which imports `authority` at load): one
  predicate, no import cycle.
- **Spec gap (non-rejecting, for the orchestrator):** the reviewers observed that with a *pending* bound profile
  (the sidecar removed, state `never`) and a *drifted* live config, `Profile.guard("plan")` refuses with
  `process.pending` while direct `approve`/`override` still compare and (on an unchanged config) approve. The
  requirement (A-4 / R-2) names "unusable profile" without defining the pending state: `live_digest()` answers the
  resolved digest there, so a *drifted* config is still refused; only an *unchanged* config approves, which R-2 does
  not forbid. Left as a spec gap, not a violation; no requirement was waived.
