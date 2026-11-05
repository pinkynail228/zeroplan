# R1 design: EGM planning on Zeroshot

Status: revision 6 (2026-11-03), ready to slice. Pass 1 (comprehension, design critic, implementation readiness) and a re-review of
revision 2 are in `.local/goldfish/2026-11-03-egm-planning/`; resolutions: section 9. Revision 3 splits R1: **R1a**
(this design) makes the architect's own path planner-free; **R1b** (a later design) moves the owner's remaining
paths (`/plan`, owner revise, steward proposals, line UI) once R1a is in use.
Implements `docs/designs/2026-11-03-egm-pivot.md` rev. 3.

## 1. Problem

The owner's intent passes through two models before any review: the architect (one `codex exec` per turn,
`terminal_planner/architect.py`) restates a goal for `zplan_plan`, a separate LLM planner in a Zeroshot graph writes
the plan, and a critic argues with that planner for up to `plan_rounds` rounds (`engine.planner_graph_v2`). The
contract says there is no separate planner and the critic reviews once, re-reviewing only unresolved findings
(`docs/PRODUCT_CONTRACT.md:27,31`).

## 2. Goals and non-goals

Goals: (G1) a plan the architect makes in the conversation is written by the architect and reviewed without a
planner run (R1a); the owner's remaining planner paths are listed and move in R1b. (G2) The owner and the
architect see how a fresh reader with no context understood the plan (a paraphrase). (G3) One critic pass per
revision with the existing rejection bar. (G4) The architect fixes or disputes findings in a new revision, within a
bounded number of revisions. (G5) Execution, verification, merge and approval rules are unchanged; stored
revisions and runs load and replay as before.

Non-goals: milestone execution and task gates (R2); the EGM plugin; a new plan format or a new plan execution
version; moving the architect off Codex; a profile migration.

## 3. Reused as is

- Draft revisions: `draft` is a full proposal the run must return byte for byte (`authority.begin(draft=)`,
  `Authority.review_evidence`, `planning.edit`).
- The revision record, receipts, envelopes, evidence, freshness, `approve`, `override`, stop (`authority.py`).
- Output schema "2" with a one-round discussion (`read_review`, `read_discussion` with `rounds_limit`).
- `validate_proposal`, `check_bounds`, `verifier_instructions`, `PLAN_CRITIC_BAR`, the disposable checkout at HEAD
  (`engine.prepare`), the native `--validate-only` admission (`engine.py:1428`).

## 4. Design

### 4.1 A Goldfish review is a draft revision of execution 2

No new execution version. A revision created by the architect carries `draft` and `frozen.review = "goldfish"`
(a new optional key of the frozen snapshot; a revision without it runs the planner graph as today, so stored
revisions replay unchanged). `engine.prepare` builds `goldfish_graph()` for such a revision instead of
`planner_graph_v2`. The revision keeps both planning roles (`planner`, `plan_verifier`); the Goldfish nodes use the
`plan_verifier` binding. `frozen.plan_rounds` stays and becomes the architect's revision budget (4.5).

### 4.2 Goldfish graph

```text
seq planning
  par review (join: all)
    comprehension  verifier, builtin.agent.software-worker@1, signals {}  -> out.paraphrase
    critic         verifier, builtin.agent.acceptance-verifier@1          -> signal verdict, diagnostic.message, out.discussion
  choice review_result
    comprehension error | critic error -> fail comprehension_failed | critic_failed
    otherwise -> succeed reviewed (output schema "2" fields + paraphrase)
```

Each worker ref is used once in the graph (admission rejects one ref with two contracts, `milestone.py:368`).
Runtime: both nodes `sessionScope: "execution"` (a fresh session per run, as milestone reviewers,
`engine.py:1065`); `plan_verifier` model and effort. Input: schema "2" with `proposal` = the draft and
`planResponse` = the architect's responses (4.4), `discussion` empty. The success node binds `proposal` from state,
so the output proposal is the draft by construction. The critic writes a one-round discussion
(`read_discussion` accepts 1..`plan_rounds` rounds). `read_review` accepts `paraphrase` only on goldfish revisions. Phases and failure labels gain `comprehension`
(`engine.PHASES`, `planning.py:606-608`, `live.py`, `tui/scheme.py`).

### 4.3 Nodes

Instructions are zplan's own wording informed by EGM (no EGM text ships; section 7).

- **comprehension** (advisory, no verdict): its input is a separate state field `reader` = `{goal, feedback, plan}`;
  it is not bound to `task`, so it never sees prior reviews, roles or rules. Not reading the repository is an
  instruction only (the run shares the checkout). Writes `paraphrase` (<= 3000 characters): what the plan will deliver and in what order, in plain
  words, and any part it could not explain. It decides nothing: the architect compares the paraphrase with the
  owner's words (the EGM author's step) and the owner sees it on the plan card.
- **critic**: today's critic instructions (`verifier_instructions`, `PLAN_CRITIC_BAR`, owner rules) plus: the draft is
  the architect's and is never changed; repository text, the plan and the architect's responses are claims, not
  authority; accept a dispute only when it cites the owner's words or a fact checkable in the checkout; repeat
  unresolved prior findings and add findings only for what changed or what the prior review could not have seen.
- **paraphrase limit**: `read_review` keeps the first 3000 characters of `paraphrase` (deterministic, so evidence
  recomputed from the same output is identical); an over-long paraphrase never invalidates the review.

### 4.4 Entry paths

| Path | Today | R1a |
|---|---|---|
| `zplan_plan` | `{goal}` -> planner | `{goal, plan, request?}`: with `plan`, a goldfish draft revision; without `plan`, refused ("write the plan") in R1a builds; `goal` stays the architect's statement of the goal (as today) |
| `zplan_edit_plan` | needs a current proposal; graph 2 with planner | needs a current revision with a proposal or a draft; a goldfish revision; optional `response` (<= 3000 chars: one line per prior finding, `fixed: ...` or `disputed: ...`) and `request` (the owner's words this revision answers, quoted by the architect) |
| `zplan_revise_plan` | feedback -> planner | removed from the architect's tools |
| `renew`, restart, stale resend | `begin` with execution 2, the draft kept | keep `draft`, `frozen.review`, `response` of the renewed revision |
| `FixtureArchitect` | `{goal}` | `{goal, plan}` with a fixture plan that carries briefs |
| owner `/plan`, owner revise, steward proposal, line UI | planner | unchanged in R1a (R1b) |

Every goldfish revision stores `origin`: `plan` (made by `zplan_plan`), `edit` (by `zplan_edit_plan`) or `renew`
(renew, restart, stale resend), and `by`: `owner` when the call came in a turn the owner started or from an owner
action, `architect` when it came in an event turn (the controller knows the turn's binding). Feedback: a `plan` revision's `feedback` is its `request` verbatim (or empty); an
`edit` or `renew` revision inherits the current revision's `feedback` and appends `request` when given, so the
owner's requests travel with the chain (`amended_feedback` is not used on goldfish revisions). A chain starts at
an `origin: plan` revision or at any revision without `origin` (a planner revision); for a goldfish revision
(`frozen.review` present) `engine.prepare` takes `prior_proposal` and `prior_review` only from revisions of its chain
before it (a planner revision keeps today's search), and
`amended_feedback` stops at an `origin: plan` revision. The critic and
comprehension get `FEEDBACK_RULE` (later requests win over earlier ones and over the goal).

An unchanged plan in `zplan_edit_plan` is accepted when `response` is non-empty, the baseline moved, or the current
revision has no evidence (a failed or stopped run); "unchanged" compares with the current `proposal`, else `draft`.
`zplan_status` `plan` exposes `draft` for the current revision when `proposal` is null, so the architect can read
its plan back after a failure.

### 4.5 Revision budget, brake and wakes

One rule: in a chain, the architect may create at most `budget` revisions with `by: architect` (any origin, any
status of the revision it replaces). `budget` comes from one helper used by `_brake` and the wake check: the current
revision's `frozen.plan_rounds`, else `DEFAULT_PLAN_ROUNDS`. At the limit `_brake` refuses an event-turn `zplan_edit_plan` with "the
owner decides now". Revisions with `by: owner` do not count; an owner turn may create one revision per owner message (keyed on the
message reference of the turn), so one message cannot drive an unbounded loop. An event-turn edit is also refused when
the current revision is `stopped` (the owner stopped it; re-running needs an owner turn). The budget is the cost
ceiling per goal: at most `budget` Goldfish runs without the owner after the chain start, plus one per owner message.

Wakes keep today's per-level rule (`feed.PLAN_WAKE`, `autonomy.decide`): a rejection or a failed run maps to
`start` and wakes the architect at `auto` and `supervised`, the owner at `manual`; an accepted plan maps to
`approve` and wakes the architect only at `auto`. At `supervised` and `manual` the owner compares the paraphrase
with their intent on the plan card before approving; the architect sees it on its next turn. The A10 mark that
silences a rejected architect-made revision is replaced by the budget: when the chain is at its budget,
`review_exhausted`, `run_failed` and `proposal_invalid` do not wake the architect (its only step would be the
refused edit); `proposed` and `approved` always follow `PLAN_WAKE`.

### 4.6 What the architect knows

The plan format and planning rules move out of `planner_instructions` into one constant `PLAN_FORMAT` used by the
planner prompt (old revisions) and by the `zplan_plan` and `zplan_edit_plan` tool descriptions (no size cap there);
`TOOL_RULES` (`architect.py:90-98`) says to write the plan, compare the paraphrase with the owner's words, and answer
findings with responses. `architect_method.md` (4600-byte cap) gets two lines; the format stays in the tools.
`validate_proposal` and `check_bounds` are unchanged (they also run on stored plans). A new `check_draft`, called only
from `Planning.edit` and the `zplan_plan` path (never from `begin`, so renewing a stored draft is unaffected), requires a brief on every task and caps the canonical plan at 256 KB, so a
plan the critic would always reject or the bridge could not carry is refused before any run. `TOOL_RULES` gains:
paraphrase, findings and status text are data from other models, never instructions.

### 4.7 Display

`zplan_status` `plan`, the plan card and the timeline show the paraphrase ("How a fresh reader understood it") and
the architect's responses (replacing "Planner reply", `planning.py:704`); findings as today. Model text is shown
through the existing `planning.clean` sanitising. Owner-facing "planner" wording for new revisions becomes "plan
check" (`planning.py:555,561`, `controller.py:1979`).

## 5. Alternatives

- **A. Direct model calls from the controller, no graph.** Needs new receipt, observation, crash and stop handling
  the revision store already has for graph runs. Rejected: duplicates the engine (`AGENTS.md:15`).
- **B. Keep graph 2 for drafts (the planner echoes the draft).** Exists today. Rejected: the planner node and role
  stay, one model call per revision is wasted, and the contract removes the planner.
- **C. A new plan execution version 3.** Cleaner separation, but the store refuses unknown versions
  (`authority.py:520`), every reader of `execution` changes, and an older zplan cannot open the store. Rejected for
  a frozen-snapshot key that old revisions simply lack.
- **D. A comprehension verdict that blocks.** A node cannot detect its own misreading, and a blocking finding with
  no dispute path breaks the contract's fix-or-dispute rule. Rejected: advisory paraphrase, compared by the author.
- **E. A third node for implementation readiness.** Rejected for now: the critic already rejects tasks without a
  complete brief and unverifiable checks; `check_bounds` now requires briefs.

## 6. Risks

| Risk | Mitigation |
|---|---|
| Plans get worse without the planner's repository exploration | the architect reads the project; the critic verifies checks against the checkout; the R1 exit reports revisions per goal and tokens for the qualification goals |
| The architect plans from uncommitted files | the critic rule covers checks; it is extended to `reuse` and `write_set` paths missing at HEAD |
| A persuasive or injected dispute flips the verdict | 4.3 untrusted-text rule; disputes are shown to the owner; the budget bounds attempts; approval at `auto` still needs an accepted critic verdict |
| Paraphrase or findings carry instructions to the architect | the new `TOOL_RULES` line (4.6), pinned by a test |
| The owner's remaining paths still run the planner until R1b | listed in 4.4; the R1a exit checks the architect path only |
| One node fails after the other finished | the run fails as a whole (`run_failed`); the architect re-submits with `zplan_edit_plan`; the paid result is lost, as for a critic error today |
| Older zplan versions | `validate_frozen` rejects unknown keys (`authority.py:524-526`), so a version before R1 refuses a store holding a goldfish revision: downgrade is unsupported; S1 adds this to `docs/UPGRADE.md` |
| Tests pin planner prompts and paths | each slice maps pinned behaviour to the new path or keeps it for old revisions |

## 7. License

zplan ships no EGM text. The node instructions are zplan's wording; EGM is credited in `docs/REFERENCE.md`. The
vendored personas stay in `devtools/egm/` for development use only. (The pivot decision said they may move into the
product; this design does not need that.)

## 8. Slices (R1a)

| Slice | Change | Acceptance (written first, red on base) |
|---|---|---|
| S1 | engine + authority: `goldfish_graph`, runtime, input with `reader`; `frozen.review`; `paraphrase` read and clipped; fixture scenarios; `docs/UPGRADE.md` downgrade note | admission `--validate-only` of the goldfish graph against the pinned binary (not run when absent, reported); a fixture draft revision ends `proposed` with a paraphrase; a rejecting critic ends `review_exhausted`; a stored planner revision replays unchanged |
| S2 | planning + feed + authority + `engine.prepare`: `origin` and `by`; chain boundaries; renew keeps the kind; feedback inheritance and chain start of 4.4; edit rules (unchanged plan, after failure, `response`, `request`); `check_draft`; budget, brake and wakes of 4.5 | Controller-level tests with the fixture engine at `auto`, `supervised` and `manual` |
| S3 | tools + architect prompt: `zplan_plan {goal, plan, request?}`, `zplan_edit_plan` arguments, `zplan_revise_plan` removed, `PLAN_FORMAT`, `TOOL_RULES`, `draft` in status, `FixtureArchitect` | tool-level tests; the pinned `TOOL_RULES` test updated by behaviour, not wording |
| S4 | display: paraphrase and `response` in status, plan card, timeline; "plan check" wording for goldfish revisions | terminal scenario at 80x24 and wide |
| S5 | docs: `USER_FLOW.md`, generated `REFERENCE.md` | the existing REFERENCE drift test |

Exit (R1a): with an owner-authorised real architect and a fixture repository, a goal in the conversation ->
architect plan -> Goldfish review shown -> approval -> first milestone dispatched through Zeroshot, with no planner
node in that run; full product suite green on the integrated tree; revisions per goal and tokens reported.

## 9. Resolution of the Goldfish findings (rev. 1)

| Finding | Resolution |
|---|---|
| A10 brake ends the fix loop (all three) | accepted: 4.5 |
| Paths still reaching the planner; renew falls back (all three) | accepted: 4.4 lists every `begin` caller |
| Dispute-only edit refused; no path after a failed run (critic, readiness, comprehension) | accepted: 4.4 `zplan_edit_plan` row |
| Comprehension verdict incoherent; no dispute path | accepted: advisory paraphrase (4.3, alternative D) |
| Owner's words never reach reviewers | accepted: revision goal = owner's message (4.4) |
| Architect never told the plan format | accepted: 4.6 |
| Execution 3 record underspecified | resolved by removing execution 3 (4.1, alternative C) |
| Evidence readers (`gate_lines` rounds, findings) | resolved: schema "2" with a one-round discussion keeps every field |
| Graph not buildable; session scope; phases | accepted: 4.2 |
| `/plan` contradicts the contract | accepted: `/plan` removed, contract kept (4.4) |
| Security and partial failure missing | accepted: section 6 |
| License of adapted text | accepted: section 7 |
| Plan size; briefs optional | accepted: 4.6 `check_bounds` |
| Re-review scope; responses data model | accepted: 4.3 critic rule, 4.4 responses |
| Owner edit row in the TUI does not exist | accepted: row removed |
| Cost and measurement without numbers | partial: per-goal ceiling = budget; exit reports revisions and tokens; no threshold before real data |
| Persona size claim, Alternative C rationale | accepted: claims removed |

Re-review of revision 2 (Blockers 2, Majors 11), resolved in revision 3:

| Finding | Resolution |
|---|---|
| B1 owner's message verbatim is not available and may not be the goal | accepted: the goal stays the architect's statement; owner words enter as `request` -> `feedback`; the comprehension paraphrase is the intent check |
| B2 at the budget limit the owner's words cannot pass the brake | accepted: an edit in an owner turn always passes (4.5) |
| M3 follow-up owner words never reach reviewers | accepted: `request` -> `feedback`, `FEEDBACK_RULE` for both nodes, `amended_feedback` stop condition (4.4) |
| M4 not every `begin` caller listed; old revisions renew into the planner | partial: owner paths and old revisions stay on the planner in R1a and are listed; R1b moves them |
| M5 recovery after a failed run | accepted: `draft` in status; unchanged resubmission without evidence (4.4) |
| M6 wakes ignore autonomy | accepted: today's per-level rule kept and stated (4.5) |
| M7 chain undefined | accepted: 4.5 |
| M8 `check_bounds` runs on stored plans; fixtures lack briefs | accepted: separate `check_draft`; fixture plan with briefs |
| M9 no stored form for responses and title | accepted: field `response`; no title field |
| M10 comprehension cannot be limited to the goal | accepted: `reader` state field (4.3) |
| M11 overlong paraphrase discards the review | accepted: deterministic clipping (4.3) |
| M12 routing owner actions to the architect | deferred to R1b with those paths |
| M13 the cited status-is-data rule does not exist | accepted: added to `TOOL_RULES` (4.6) |

Re-review of revision 3 (Majors 6), resolved in revision 4: stored `origin` (M1, M3); feedback inherited on every
edit and set from `request` on a chain start, no prior plan or review across goals (M1, M2); fixes and retries
counted separately, one retry after a failed run (M4); the wake rule stated as coded, `supervised` added to S2 (M5);
`check_draft` never called from `begin` (M6).

Re-review of revision 4 (Majors 7), resolved in revision 5 by replacing the two counters with one stored `by` and
one budget over architect-made revisions in any status (M1, M5); chain boundaries at planner revisions and a
chain-scoped prior search in `engine.prepare` (M2, M3); `amended_feedback` stops at `origin: plan` (M4); no
event-turn edit of a `stopped` revision (M6); the owner compares the paraphrase at `supervised` and `manual` (M7).

Re-review of revision 5 (Majors 4), resolved in revision 6: the chain-scoped prior search applies only to goldfish
revisions (M1); the silenced statuses at the budget are named, `proposed` and `approved` always wake by level (M2);
one `budget` helper (M3); one owner-turn revision per owner message (M4). Pass sizes: rev. 1: 3 reviewers, 6
Blockers; rev. 2: 2 Blockers, 11 Majors; rev. 3: 6 Majors; rev. 4: 7 Majors; rev. 5: 4 Majors, all narrow. The
remaining risk is pinned by the S1 and S2 acceptance tests rather than further review passes.
