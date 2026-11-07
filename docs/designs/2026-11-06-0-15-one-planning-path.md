# 0.15 design: one planning path, the line UI gone

Status: revision 3 (2026-11-07), built (59d11cd to 4ae0d32). One change while building: the scripted demo architect keeps its one plan (3.5 dropped: the demo has no model to revise with). Revision 1's Goldfish pass (`.local/goldfish/2026-11-06-0-15-r1/`) is resolved in
section 7, revision 2's (`.local/goldfish/2026-11-06-0-15-r2/`: design critic, implementation readiness; no design
Blocker) in section 8, which overrides the sections above it where they differ. Sources:
- the 0.14 design (`2026-11-06-0-14-lean-zplan.md`): its revision 2 (sections 1 to 7) and the requirements of its
  sections 8 and 9;
- the 0.14 qualification (`docs/plans/backlog.md`, "Seen in the 0.14 qualification");
- the measurements of section 1.

**What changed from revision 1.** The line UI goes in 0.15, before the routes change: while it stays, every
refusal in the shared services would have to be duplicated in the TUI and undone in 0.16. A changed goal starts a
new plan with `zplan_plan`, so it never bypasses the owner's yes. Everything else that revision 1 put in 0.16 gets
its own design after 0.15.

## 1. Problem, with measurements

**The owner has two planners.** The architect writes plans that the Goldfish plan check judges. The old planner
graph (`engine.py`, built by `Authority.begin` without `review="goldfish"`) still writes the plan for these entry
points:

| # | Entry point | Code path at 59d11cd |
|---|---|---|
| 1 | `/plan <goal>` | `card_host.action_plan` → `app.start_goal` → `controller.start_planning` → `Planning.begin` |
| 2 | bare `/plan` with a goal draft | `card_host.action_plan` → `start_goal(draft.text, card_key=…)` → the same |
| 3 | bare `/plan` without a draft | `app.send_unsent_plan` → `run_plan`: sends the unsent revision, whichever planner made it |
| 4 | the failed-plan card's `/retry`, `[g]` restart, `[n]` renew | `card_host.retry_failed_plan` → `controller.restart_plan`; `controller.renew_plan` → `Planning.restart`, `renew` |
| 5 | "back to plan" at a run's end | `app.modal_action("plan")` → `controller.to_plan` → `Delivery.to_plan` → `MilestoneRuns.revise` |
| 6 | a steward proposal that does not fit the milestone, accepted | `controller.accept` → `Delivery.accept` → `MilestoneRuns.accept_proposal`, its `"plan"` branch |
| 7 | revising a plan the old planner made | `app.revision_note` → `controller.revise_plan` → `Planning.revise` → `runs.revise_plan` |
| 8 | the line UI (`zplan --plain`, and `zplan` without a terminal or without Textual) | `cli.App.plan_flow` and the rest of its menu |

A plan written there skips every 0.11-0.14 rule: the critic's readiness rules, the base checks in its input, the
architect's method, the stored decline.

**The tests.** Two full-lane runs, each with one change at 59d11cd (logs in the private evidence, `rel014/`):
- **E2:** `cli.App.run`, `dispatch`, `choose`, `plan_flow`, `proposal_flow`, `plan_screen`, `screen`, `menu`,
  `observe` and `follow` raise. **175 tests fail.** 108 reach the menu through the shared helpers
  `tests/test_process.py` `run_session` (64) and `awaiting_merge` (51), `test_fixture_scope.py`, and
  `test_merge_gate.gated`; the line UI's own classes are `TerminalTests`, `PlainFallbackTests`, `PlainHelpTests`,
  `BootstrapPlainTests`, `PlainTests` and `NativeJourneys`.
- **E3:** `Authority.begin` raises unless `review="goldfish"`. **395 tests fail.** 142 through `Planning.begin`
  (107 of them from the line UI's `plan_flow`, the rest the TUI's `/plan`), 43 through `test_plan_override.make`,
  25 through `test_task_gate_record.approved_native_plan`, 17 through `test_parallel_runs.approve_parallel`, and the
  old planner's own tests.

Before E3, F1 (59d11cd) moved the shared fixtures to Goldfish revisions: `ProjectTest.begin` writes a Goldfish
revision of `fixture_draft()`, the native fakes return the Goldfish review, and `begin_old_planner` and
`NativeTests.old_terminal` keep the old planner for its own tests. That change alone failed 171 tests (E1); all were
moved without weakening an assertion, and the full lane is green.

**A defect seen in the 0.14 qualification.** When the owner's decline changed the goal (a CLI command became a chat
command), the architect edited the plan with `zplan_edit_plan`, which keeps the chain's goal, and the plan tab showed
r1's goal over r2's plan.

## 2. Goals and non-goals

**Goals:**
1. **No owner, steward or architect action writes an old-planner revision.** Each entry point of section 1 goes to
   the architect, or is refused or removed (section 3.2). A permanent test guards it (section 3.6).
2. **A message that code builds for the owner, or that `/plan` sends, approves nothing:** it binds no yes in words.
3. **A changed goal is a new plan,** written with `zplan_plan` at the owner's word and approved by the owner.
4. **The line UI's menu goes.** Every subcommand stays (`status`, `doctor`, `setup`, `login`, `logout`, `update`,
   `profile`, `roles`, `exec`, `help`). `zplan` without Textual, or without a terminal on both ends, refuses with its
   reason. The tests that use the menu as a harness move to `Delivery` and `Planning`.
5. **The test fixtures make Goldfish revisions** (F1, done; F2 for the TUI tests).
6. **The plan check's documents are pinned** byte-identical to 0.14 by a new test.

**Non-goals:** the removal of the old planner's and the task gate's writer code, the planner-era settings, goal-draft
UI, `devtools/zeroshot/`, the observer functions, `ARCHITECT_DESIGN.md` and `P0_AUDIT.md`: each needs the line UI gone
first, and gets its own design after 0.15 (section 6). Also: module splits by size; batch conversion of sentence
assertions; deleting the owner's local data.

## 3. Design

### 3.1 Messages that code builds

`ZplanApp.send_owner_note(message, declined=False)` (K's `send_revision_note`, renamed and widened) is the one way the
TUI sends a message for the owner:
- the turn's snapshot carries `plan_state.binds = False`, and `application.shown_plan` returns None when
  `binds is False` or `declined` is true; so the turn approves nothing (`_approve_decided` compares
  `turn["shown_plan"]`). With `declined=True`, K's stored decline also holds;
- a chat that cannot take the turn now gets the whole message added to the main screen's input, else it is shown on
  the status line (K);
- an unavailable architect (not logged in, a lost session) answers through the same refusal: `chat.send` returns
  `(False, reason)`, and the owner reads the reason with his text kept in the input.

The messages are English, like K's: the architect reads them, the owner sees them as his own line. The palette and
status lines are strings in `tui/strings.py` in en, ru and zh.

### 3.2 The routes

| # | 0.15 | Where |
|---|---|---|
| 1 | `/plan <goal>` sends `<goal>` (without the `/plan` prefix) through `send_owner_note`: binds no yes. Offered whenever the chat is: the `idle`, `draft`, `error` states and also while a plan waits (`slash.py` states). Palette label `cmd.plan`: "send a goal to the architect" | `card_host.action_plan`; `app.start_goal` and `controller.start_planning` go (no other caller) |
| 2 | bare `/plan` with a goal draft sends the draft's text the same way | `card_host.action_plan` |
| 3 | bare `/plan` without a draft sends an unsent **Goldfish** revision as today (the readiness checks held it back; it is the architect's plan). Otherwise the note `note.plan_needs_goal` ("write the goal after /plan, or in the chat") | `app.send_unsent_plan` |
| 4 | for a current revision the old planner made, `/retry` of the failed-plan card, `[g]` and `[n]` refuse with `note.plan_in_chat` ("plan again in the chat"); a Goldfish revision is unchanged. The ready card's `/retry` only re-checks and is unchanged | `Planning.restart` and `Planning.renew` refuse a non-Goldfish current revision with family `action.refused`, and so does the owner's send of an unsent one (`controller.submit_plan`); `Planning.submission` itself is unchanged, since the old planner's own tests still submit until the next design |
| 5 | "back to plan" sends "Back to plan after <M> attempt <N>: <reason>" through `send_owner_note`, after a controller job has checked the token and `MilestoneRuns.check_followup` (only the latest unsuccessful attempt of the current revision). That job records no plan result: no plan operation ran. The run-end screen closes as today | `controller.to_plan` checks and returns `(milestone, attempt)`; `Delivery.to_plan` and `MilestoneRuns.revise` go |
| 6 | a steward proposal that does not fit the milestone is not offered for acceptance. Its view says "This proposal goes beyond the milestone; the architect, woken by it, will discuss it with you in the chat." The `needs_owner` wake already reaches the architect (`feed.py`), which plans only on the owner's word (`_plan_tool`) | `MilestoneRuns.accept_proposal` refuses a non-fitting candidate; `owner_actions` and `Delivery.owner_view` offer `accept_proposal` only for a fitting one; `Delivery.accept` and `Controller.accept` lose their `"plan"` result; `catalog.py` and `delivery.py` texts change |
| 7 | revising any revision with a note is K's route: a proposed revision's decline is stored, then "Revise plan r<N>: <note>" is sent. The `goldfish` condition in `decline_to_architect` goes. The architect edits (`zplan_edit_plan` accepts an old-planner proposal as its base) or writes a new plan; either way a Goldfish revision | `app.decline_to_architect`; `controller.revise_plan`, `Planning.revise` and `runs.revise_plan` go |
| 8 | the line UI goes (3.4) | `cli.py` |
| — | `Planning.edit` (an owner edit through the old planner's renew) goes: no product caller | `planning.py` |
| — | a stored old-planner revision shows, and the owner's card can approve it | unchanged |

An empty note on a stale plan (`revision_note` turns it into `RENEW_NOTE`) renews only a Goldfish revision; for an
old-planner revision it is refused by row 4.

### 3.3 A changed goal

No new mechanism. The architect's tool rules (`architect.py`, the `zplan_edit_plan` line) gain one sentence: "When
the owner's change alters what the plan is for, write a new plan with zplan_plan instead of an edit." `zplan_plan`
already requires the owner's turn (`_plan_tool`), starts a new chain, and its first revision waits for the owner's
yes at every level, so a goal never changes without him. `architect_method.md` does not change.

### 3.4 The line UI

- **Goes:** `cli.App`'s menu and flows (`run`, `dispatch`, `choose`, `offer`, `explain`, `plan_flow`,
  `proposal_flow`, `plan_screen`, `screen`, `menu`, `observe`, `follow`, `panel`, the `[x]` actions), `session`,
  `choose_project`, `configure_roles`'s menu use, `render`, `Terminal.ask`'s menu use, `PLAIN_CHAT`, and `--plain`.
- **Stays:** `status` (it uses `App.home`, so `App` keeps `home`, `home_body`, `planning`, `delivery`, `roles`, and
  its constructor: renamed `Overview`), every subcommand, `help_request`, and `login`'s confirm.
- **Refusals:** `zplan` with `--plain` exits 2 with "zplan is full-screen only; run it in a terminal". Without a
  terminal on both ends, or with `TERM=dumb`, it exits 2 with "zplan needs an interactive terminal; for scripts use
  zplan status or zplan exec". An ImportError of Textual exits 1 with "zplan's full-screen UI cannot start (<error>):
  reinstall zplan". The catalog's `tui.unavailable` entry and the help text change with them.
- **The harness tests:** `run_session`, `awaiting_merge`, `test_fixture_scope`'s session and `test_merge_gate.gated`
  call `Planning`/`Delivery` directly (accept the profile, plan with `ProjectTest.begin`, approve, `Delivery.start`,
  observe, finish), so their assertions on the merge, the gates and the cleanup stay. The line UI's own classes go,
  each removal declared in the commit's ratchet trailer.

### 3.5 The fixture demo and the scripted architect

`FixtureArchitect.run`, when a plan exists, answers an owner message with `zplan_edit_plan` of the current plan
(unchanged, with the message as the response), so the demo's decline, "back to plan" and `/plan` produce a revision
the owner can see; without a plan it writes one, as today. The README demo line (`/plan Add a changelog`) keeps
working and is reworded only if its result changes.

### 3.6 Tests

- **The guard:** `tests/test_one_planning_path.py` runs the TUI route of each row of 3.2 (rows 1-7) under a patch
  of `Authority.begin` that records `review`, and asserts every recorded call is Goldfish. It replaces E3 as a
  permanent check; after the line UI is gone the only non-Goldfish callers left are `begin_old_planner` and the old
  planner's own tests, which the next design removes.
- **One behaviour test per row** of 3.2, in that module (rows 1, 2, 5 and 7 also assert the turn binds no yes).
- **The plan check's documents:** `tests/test_goldfish_review.py` gains a test that builds the Goldfish graph,
  runtime and input for a fixed context and compares their SHA-256 with literals captured at 0.14.0 (F3, before any
  0.15 product change).
- **F2:** the TUI tests that typed `/plan` to get a plan seed a proposed Goldfish revision with
  `ProjectTest.begin` before the shell opens; `ApproveCardShell.propose_joint` becomes such a seed (it writes an
  old-planner revision today).

### 3.7 Order of work (each step a commit, fast tests of the touched modules)

1. F2 and F3.
2. L: the harness tests move off the menu, then the menu goes (3.4).
3. P1: `send_owner_note`, `shown_plan`'s `binds`; rows 7 and 5.
4. P2: rows 1-4 and `Planning.edit`.
5. P3: row 6.
6. P4: the tool sentence (3.3); `FixtureArchitect` (3.5).
7. Docs: ARCHITECTURE, README, USER_FLOW, REFERENCE, `PRODUCT_CONTRACT.md` where it names the line UI, STATE.
8. Goldfish as built (`design_critic`, `codebase_details`) on the diff of L and P1-P4.

## 4. Alternatives

| Alternative | Verdict |
|---|---|
| Keep the line UI until 0.16, with TUI-only refusals (revision 1) | Rejected: the refusals would sit in the TUI while the shared services still write old-planner revisions for the line UI, and 0.16 would move them again (implementation readiness B3) |
| Everything, including the writers' removal, in 0.15 | Rejected: E3 shows 395 tests bound to the writers; after the line UI goes, the next design can measure what is left |
| Remove `/plan` | Rejected: the README's demo (`README.md`, "Try it") and the palette document it; keeping it costs one route |
| `/plan <goal>` sent like typed text (may bind a yes) | Rejected: `/plan` asks for new planning, not an answer to the shown plan (design critic 7) |
| A structured request (a revise record the architect reads with a tool) | Rejected for now: a new tool and method text for what the message carries; the stored decline gives the consent guarantee in code. Brought back if the architect misreads such messages in the qualification |
| A code-side `revise_draft` of the current plan with the owner's note, without the architect | Rejected: the note needs the architect to turn it into a plan; a code-side edit could only resubmit the same plan |
| `goal` on `zplan_edit_plan` (revision 1) | Rejected: it keeps the edited chain's owner approval, so at `supervised` the architect could approve a changed goal alone (design critic 1); it also needs a goal-only change rule, validation and a feedback reset. `zplan_plan` already has the owner's-word rule and a fresh chain |
| The line UI's menu kept as a test harness | Rejected: product code no owner may use; the tests move to the services the TUI calls |

## 5. Risks

- **Consent.** No route binds a yes (3.1); the stored decline refuses the architect's approve; a changed goal is a new
  chain the owner approves. Tests: 3.6.
- **The architect is the only planner.** A logged-out or lost architect blocks planning. The owner reads the reason
  with his text kept, and `zplan login` restores it. The qualification includes a run with the architect logged out.
- **A route loses the owner's words.** Each route keeps the text in the input when the chat cannot take it.
- **Lost coverage when the line UI goes.** The harness tests move first, with their assertions; only the line UI's
  own classes go, each declared.
- **Scripts that ran `zplan` without a terminal.** They now get exit 2 and the reason naming `zplan status` and
  `zplan exec`. UPGRADE.md says so.
- **The plan check changes by accident.** F3 pins it before any product change.
- **Rollback.** 0.15 writes no new record shape; 0.14 opens a 0.15 store.

## 6. After 0.15

One design, measured again after the line UI is gone, for: the old planner's writer (its readers stay, with a stored
0.10-era fixture); the task gate's writer (keeping `STATUSES`, `TERMINAL`, `persistable`, `escaped`, `too_deep`,
`validate_binding`, `terminal`, `submitted_title`, `SIZE`, and the engine's `SCHEMA`, `DOCUMENTS`, `concluded`); the
planner-era settings (note: `limits.plan_rounds` is also the Goldfish chain budget, and every revision freezes the
`planner` role); the goal-draft UI; `devtools/zeroshot/`; the observer functions; `plan_qual.py`,
`task_gate_qual.py` and their export exemptions; `ARCHITECT_DESIGN.md` and `P0_AUDIT.md`.

## 7. Resolution of revision 1's review

| Finding | Resolution |
|---|---|
| DC1 Blocker, IR M2, CD M4: `goal` on edit bypasses the owner's yes; files and rules missing | Dropped: a changed goal is a new `zplan_plan` plan (3.3) |
| DC2 Blocker, IR M1, CD M3: `binds: false` read by nothing | `shown_plan` reads it; P1 work item and tests (3.1, 3.6) |
| IR B1, CD M1, DC11: F1 already in the tree | Section 1 says F1 landed and re-measures at 59d11cd |
| IR B2, DC4, CD M9: the E3 check cannot pass and is not a test | A permanent route guard (3.6) |
| IR B3, CD M2: the line UI shares the services 0.15 changes | The line UI goes first in 0.15 (3.4); refusals live in the services (3.2) |
| CD B1, IR M4: `propose_joint` seeds an old-planner revision | F2 changes it (3.6) |
| DC3: a goal-only edit refused | Moot (3.3) |
| DC5, IR M5, CD N4: "back to plan" loses its guards | The token and `check_followup` run first; no plan result (3.2 row 5) |
| DC6: the architect is the only planner | Risk entry and a logged-out qualification run (5) |
| DC7: `/plan` may approve the shown plan | It binds no yes (3.2 row 1) |
| DC8, CD N5: the edit-chain alternative's rationale | Restated (4) |
| DC9, IR M3, CD M7: goal-draft removal incomplete | Goal-draft UI moves to the next design; row 2 routes its `/plan` |
| DC10, CD M2: the steward branch's other callers and texts | Listed (3.2 row 6) |
| IR M6, CD M5: which tool for an old-planner revision | Either; both write a Goldfish revision (3.2 row 7) |
| IR M7, CD M10: the demo and 0.14 section 8 items | 3.5; the rest listed in section 6 |
| IR M8, DC13, CD N2: the byte-identical test does not exist | F3 builds it with 0.14.0 digests (3.6) |
| IR M9: 0.16 is goals only | Section 6: its own design after 0.15 |
| IR M10, CD N3: strings | Keys named (3.2, 3.1); en, ru, zh |
| CD M6: `plan_rounds` and `planner` are not planner-only | Noted for the next design (6) |
| CD M8: bare `/plan` with a goal draft | Row 2 |
| CD M11: `revise_draft` alternative | Weighed (4) |
| DC12, IR nits: counts, `/retry` routes, `Planning.revise`, sources | Table renumbered; the ready card's `/retry` named; README cited |
| DC14, CD: measurements not checkable | Each experiment's one change is stated (1); the logs are private evidence |

## 8. Revision 3: the second pass's decisions

These override sections 1 to 7 where they differ. F1 (59d11cd), F3 (2a4693d, digests of the 0.14.0 candidate's
product code, 37847ee) and L1 (5e575b1: `awaiting_merge` through the services) are done.

**8.1 Binding.** `send_owner_note` sets `binds: False` at the top level of the turn's snapshot, not in `plan_state`, so
a goal draft's provenance (`[revision, plan_state]`) is unchanged; `application.shown_plan` returns None when
`snapshot.get("binds") is False`. Signature: `send_owner_note(message, declined=False, error=None)`; a non-empty
`error` (a refused decline) sends nothing, says the error and keeps the message in the input. Without a chat (no
project, or a session opened with `architect=False`) every route of 3.2 refuses with "The architect is not available
in this session; nothing was sent." and keeps the text; the old path is gone.

**8.2 The architect's tool rules** (`architect.py`, exact new wording of the two lines):
- `zplan_plan`: "... While a revision waits for the owner's yes, change it with zplan_edit_plan instead of starting
  another, unless the owner's change alters what the plan is for: then write a new plan with zplan_plan."
- `zplan_edit_plan`: "... It keeps the plan's goal; for a different goal use zplan_plan."

A changed goal through an edit is therefore prevented by instruction, not by code: an edit never changes the goal
text, and at `supervised` or `auto` the architect may approve its own later revision of an owner-approved chain alone,
which is the owner's own rule (one approval per plan chain, `PRODUCT_CONTRACT.md` section 5.6) and not new in 0.15.
Accepted as a measured risk: the qualification includes a decline that changes the goal, and its result is checked.

**8.3 Row 6 keeps the owner's click.** Accepting a steward proposal that does not fit the milestone sends it to the
architect as the owner's message ("The owner accepts the steward's proposal for <M> attempt <N>: <proposal>"),
binding no yes. `MilestoneRuns.accept_proposal` returns `("architect", message)` for it instead of writing a revision;
`Delivery.accept` passes that on; `Controller.accept` returns `Outcome("to_architect", lines=(message,))`. The view's
text for such a proposal becomes "Accepting sends it to the architect, who changes the plan with you." The
`needs_owner` hint in `catalog.py` ("[p] revise the plan") becomes "accept sends the proposal to the architect".
`owner_actions` (no product caller) is not touched.

**8.4 Row 5's contract.** `Controller.to_plan(token, feedback, done)` runs `_acting`, then
`app.delivery.runs.check_followup(r)`, and returns `Outcome("to_architect", lines=("Back to plan after <M> attempt
<N>: <reason>",))`; `_plan_ended("feedback")` and the `"plan"` outcome (which opened `PlanScreen`) go;
`ZplanApp.settled` handles `"to_architect"`: closes the run-end screen and calls `send_owner_note`. A message left in
the input while the chat was busy is not checked again; the architect reads the status before acting.

**8.5 Rows 1-4.** `start_goal`, `start_planning`, `_start_work`, the readiness retry branch that called `start_goal`
(`app.py`, the `refused_goal` callback), and the state only they use (`starting`, `goal_message`, `goal_block`,
`refused_goal`, `note_card_refusal`) go. A goal draft sent with bare `/plan` keeps its stale check and is marked sent
(`draft_sent`) once the chat takes the message. `/plan` is available in `idle`, `draft`, `error`, `planning` and
`plan_ready`. Row 4's refusal is the service's: `Planning.restart`, `renew` and `send` raise `Blocked("This plan was
made by the old planner: plan again in the chat.", family="action.refused")` for a non-Goldfish current revision, and
the TUI shows it as "Not done: ..." as it shows every refusal; `controller.submit_plan` adds nothing. The paragraph
on an empty note after the row table is void: an empty note on a stale plan is `RENEW_NOTE` through row 7 for any
revision. A failed old-planner revision has no proposal, so only `zplan_plan` helps there.

**8.6 The structural guard.** Besides the route tests, `tests/test_one_planning_path.py` parses every
`Authority.begin` call in `terminal_planner/` (AST) and requires `review="goldfish"`, except an allow-list of the old
planner's writers left for the next design (`Planning.begin`, `Planning.renew`'s non-Goldfish branch, and
`MilestoneRuns.revise`/`revise_plan` if still present), and requires that no function outside the allow-list calls
them. Route expectations: rows 1, 2, 5, 6 and 7 with `FixtureArchitect` wired (`tui/__init__.py`): at least one
`Authority.begin`, every one Goldfish; row 3 (a Goldfish send) and row 4 (refused): none.

**8.7 The line UI, exactly.** The TUI controller builds its session on `cli.App` (`open_session`), so `App` stays,
under its name, as the headless session core: its constructor, `roles` (property and setter), `plan`, `home`,
`home_body` (lines only), `show`. Every other method goes (`run`, `bootstrap`, `dispatch`, `tail`, `resume`,
`ready`, `readiness_screen`, `gate`, `fixer`, `fix`, `roles_summary`, `plan_flow`, `unsent`, `submit`, `outcome`,
`run_planner`, `proposal_flow`, `plan_screen`, `keys`, `unknown_details`, `attempt`, `relogin`, `renew`, `restart`,
`stop_planner`, `revise_current`, `approve`, `override`, `requirements`, `revise_plan`, `settings`, `details`,
`start`, `check`, `follow`, `observe`, `panel`, `screen`, `menu`, `show_diff`, `merge`, `new_attempt`, `to_plan`,
`answer`, `accept`, `leave`, `offer`, `explain`, `choose`, `confirm`, `text`, `title`), and so do `session`,
`choose_project`, `render`, and `PLAIN_CHAT`. `--plain` stays as a hidden flag that only refuses (exit 2, "zplan is
full-screen only; run it in a terminal"); `exec`'s message drops it. No terminal on both ends, or `TERM` empty, unset
or `dumb`: exit 2, "zplan needs an interactive terminal; for scripts use zplan status or zplan exec". The harness
helper is `ProfileTest.finished(milestone, outcome="done")` in `tests/test_process.py` (start, step until the
attempt ends, open the end view, which exports a done attempt); the `run_session` helpers of `test_process`,
`test_fixture_scope` and `test_terminal_planner` go with the tests that asserted the line UI's printed text.

**8.8 F2.** `ProjectTest.begin(authority, engine="fixture", goal=..., draft=None)` takes the draft;
`ApproveCardShell.propose_joint` writes the joint plan itself as the Goldfish draft (`draft=JOINT_PLAN`) and proposes
it with `FixtureEngine`, so the five tests that read its content keep it.

**8.9 Risks added.** An old-planner revision still running at the upgrade blocks both architect tools until it ends
(`Authority.begin` refuses while the current revision runs); the owner then approves it or asks the architect for a
new plan. The architect's event-turn edits inside an owner-approved chain are the owner's existing delegation rule
(8.2), unchanged by 0.15.

**8.10 Strings.** `cmd.plan` becomes "send a goal to the architect: /plan <goal>" in en, with ru "отправить цель
архитектору: /plan <цель>" and zh "把目标发给架构师：/plan <目标>"; `note.plan_needs_goal` keeps its key with "write the
goal after /plan, or in the chat" (ru, zh likewise). The architect-facing messages are English. Docs step 7 adds
`docs/UPGRADE.md` ("What changes in 0.15": `zplan --plain` and `zplan` without a terminal refuse) and the README demo
("The architect chat is off in the demo" is false: the demo runs the scripted architect).

**8.11 Not adopted.** A code-level refusal of edits in `needs_owner` wake turns (design critic 4): 8.3 keeps the
owner's click for the steward's proposal, and the architect's other event-turn edits are the existing delegation.

## 9. The as-built review (`.local/goldfish/2026-11-07-0-15-built/`)

| Finding | Resolution |
|---|---|
| DC B1: an old-planner revision whose submission was never confirmed could not be cleared | `Planning.send` resends an unconfirmed submission before the old-planner refusal (it writes no revision); test |
| DC M1, CD 1: "back to plan" or a steward proposal was dropped when the run-end screen closed first | `settled` handles `to_architect` before the detached-modal branch |
| DC M2: a refused "back to plan" lost the owner's reason | the reason goes back to the chat input |
| DC M3: a code-built message kept in the input bound a yes when sent later | the input sends binding no yes while it holds one (`unbound_input`) |
| DC M4: `/plan <goal>` with the chat preparing or logged out lives only in the input | Accepted: the owner reads the reason with his text kept; quitting loses unsent input, as for any typed text |
| DC N1, CD 2: accepting a proposal beyond the milestone still passes the start readiness gate | Accepted: unchanged from 0.14 (the plan branch passed it too) |
| DC N3, CD 4: dead code | The line UI's Delivery helpers (`next_view`, `pick`, `start_question`, `now_line`, `stop_question`, `check_line`, `attempt_line`), `App`'s `back` and `panel_clock`, and `cli.py`'s unused imports go; `goal_identity` stays (the goal-draft UI uses it) |
| DC N4: `zplan exec --plain` accepted; refusals after `load_roles` | `exec --plain` is a parser error again; the refusals come first |
| DC N6: bare `/plan` on an old-planner revision did not say why | It shows the old-planner refusal |
| DC M5, CD 3, 6-8: the packet's scope and form | Accepted: the design is the record; the packet was a diff with questions |
