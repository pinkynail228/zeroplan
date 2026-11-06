# 0.13 design: the plan is right before the owner's yes

Status: built (revision 2 plus its second Goldfish pass, `.local/goldfish/2026-11-06-0-13-r2/`; section 8). Revision 2
(2026-11-06), after one Goldfish pass on revision 1 (`.local/goldfish/2026-11-06-0-13/`:
comprehension, design_critic, implementation_readiness; section 7 resolves every finding).

Revision 1 added a third node, `readiness`, and a background job for the base checks. Review showed what that would
touch:
- about 15 exact `review == "goldfish"` checks, the chain budget included;
- the stored evidence, where approval and override read the critic's verdict;
- byte-identical replay of old revisions;
- the Controller's single job queue, which a background job would block.

Revision 2 gets the same result with instruction text and one change of order. No node, review value or stored form
changes. The critic's instructions are part of the graph document, so new revisions get a new graph digest, while
frozen documents keep older revisions as they were.
It still completes the Elephant-Goldfish protocol of the plan check: comprehension, antagonistic review and
implementation readiness (https://opensource.googleblog.com/2026/10/introducing-elephant-goldfish-model-plugin.html).

Terms:
- *Plan check*: the Zeroshot run of `engine.goldfish_graph`. Its two nodes run side by side, once:
  - `comprehension` sees only the goal, the owner's requests and the plan, and retells it;
  - `critic` reads the frozen task context (`input.task`), the proposal and the checkout, then accepts or rejects.
    Its rejection goes to the architect, who may revise within the chain budget. The owner may approve a rejected
    plan with a reason (override).
- *Brief*: what a plan gives each task: goal, write set, criteria with examples, non-goals and done-when (the `dod`
  field).
- *Base checks*: the profile's checks run on HEAD (`Runs.base_checks`). R2a keeps their result on the revision as
  `base_checks`, the record that approval binds.
- *preflight*: the first node of every milestone run, after the owner's yes. It judges the open tasks' briefs by its
  rules F1, F2 and F4 (`milestone.py:487-496`).
  - F1: a criterion needs an edit outside the write set, or evidence that is unavailable.
  - F2: criteria contradict each other or a non-goal, or an example breaks its criterion.
  - F4: a criterion over an open domain has no case list.

  F3 is `foreman.py`'s platform-path check, not a preflight rule.
- *The readiness rules*: preflight's F1, F2 and F4, plus two new ones, W1 and W2 (section 3).
- *Role outcomes*: what each node of a Zeroshot run decided, counted from the run records.

## 1. Problem, with evidence

The live runs of 0.11 and 0.12 (private evidence under `.local/diag/`) cover about 14 plans and 20 milestone
attempts. The 0.12 qualification's role outcomes (14 runs, recorded in `docs/plans/backlog.md`):
- the plan critic accepted 6 of 6;
- preflight passed 8 of 8;
- the acceptance and code reviews each rejected 1 of 8: the suite failing on a red base, which the worker then
  fixed;
- the final check accepted 7 of 7.

The failures the owner paid for:
1. **A brief the worker could not satisfy** (0.11 run 1). The done-when said "the tree is clean, the files are in
   Git", but workers never commit. The final check rejected three repairs, and the attempt was lost: 16 minutes.
   - preflight passed it, because its rules do not cover it.
   - The plan check passed it, because neither node judges whether a worker can carry a brief out.
   - b11051d fixed this one sentence's effect on the verifiers, not the class of defect.
2. **A red base not planned for** (0.12 L2). R2a runs the base checks after the plan check, so the plan check never
   saw the red base. The plan did not include the fix, although the card then said that the first milestone must fix
   it. The fix came only from the review loop: one rejected round.
3. **The closing report lacks the decisions and the assumptions** in every live run. The method asks for them, and
   the architect keeps them in the project STATE file's `Decisions` section, but does not repeat them.

## 2. Goals and non-goals

Goals:
1. **G2.** Before the owner's yes, the plan check applies the readiness rules with the base checks' result in hand.
   A plan that breaks them is rejected with named findings, like any critic rejection.
2. **G4.** Next to the plan's report, the owner sees the decisions the architect recorded.
3. **G5.** Every release counts the role outcomes with one script whose output is comparable from release to
   release.
4. **G6.** Two defects seen in 0.12:
   - "Files not committed" counts untracked caches;
   - `/new` shows two notices.

Non-goals:
- **G1 of revision 1** (a base-checks job before the architect writes the plan). G2 reaches the same plan, at the
  cost of one revision round, and only on a red base.
- **A separate readiness node.** The backlog keeps it, triggered by role outcomes that show the critic missing a
  readiness defect it was told to judge.
- **More critics, or a Goldfish at the end.** These are in the backlog with their triggers.
- **Removing preflight.** It checks the brief against the base as it is at start, and caught 15 on zplan's own
  development.
- **Test weight.** Deferred; the default is to keep it (`STATE.md`, R1 row).
- **The owner's own `/plan` path** (the old planner graph). It gets neither `base` nor the readiness rules, and its
  revisions are not settled before submission. It leaves with the old planner (backlog).

## 3. Design

### G2: the readiness rules in the plan check

1. **The base result reaches the plan check.**
   - R2a's settle moves from after the plan check to before its submission. In `Watch.step`, before the first
     `engine.proposal` call of a revision that is not yet prepared (`run_id` is None and `native_prepared` is
     false), the job runs `Planning.settle_base()`.
   - `settle_due` then accepts the status `planning` too.
   - `Engine.prepare` builds the task context (`engine.py`, `context = {...}`). When the revision has `base_checks`,
     it adds `context["base"]` with four fields: `outcome`, `failed`, `refused` and `tail` (at most 1000
     characters); `refused` and `tail` are scrubbed.
   - The documents are written once and frozen, so a revision prepared before 0.13 keeps its documents byte for byte.
2. **The critic's instructions gain the readiness rules** (`GOLDFISH_CRITIC`). They are judged like every finding
   under `PLAN_CRITIC_BAR`, because each names what it protects: the task goal.
   - **preflight's F1, F2 and F4**, applied before the yes.
   - **W1: what the worker cannot do.** A worker edits files in its write set and runs commands in its worktree.
     It never commits, pushes, deploys, reaches external services or reads files that are not committed. A criterion
     or done-when line that needs one of these is a defect.
   - **W2: the red base.** When the task's `base` names failed checks, a milestone that every other milestone depends
     on must make them pass, unless the owner's requests defer the fix (then a note). A refused base is no plan defect.
   - Each readiness finding starts with `readiness:` and names the task, the criterion and the rule, so role outcomes
     count it apart.
3. **Nothing else changes.**
   - The graph, the evidence, approval and override stay as they are.
   - A readiness rejection is a critic rejection. The architect fixes it with `zplan_edit_plan` within the chain
     budget, and the owner may still approve a rejected plan with a reason.
   - Old revisions replay unchanged.
4. **The method.** The line "Red base on the card: the first milestone fixes it" stays.

### G4: the decisions next to the report

- `project_state.section(project, "Decisions")` returns that section's lines, using the same parser `validate`
  uses.
- At plan end, every milestone of the approved revision is `integrated`. In the overview items this is `Delivery`'s
  "all stages are merged" condition. The plan view then shows, after the merge facts:
  - "Decisions in STATE:";
  - then the section's lines, at most 8, then "… N more".
- The status carries them as `plan.decisions`.
- They are STATE's current decisions, not a record tied to this plan, and the label says "in STATE".

### G5: role outcomes

- `devtools/role_outcomes.py STATE_ROOT` reads every `runs/*/runs.sqlite3` under a Zeroshot state root. That is
  `<home>/.zp` for an installed zplan, and `<data root>/native/runs` for the development data.
- It prints two things:
  - one line per node with its counts by signal value: a verdict, a `preflight` value, the steward's signal, or the
    completion status when a node has no signal;
  - then every non-passing outcome (`rejected`, `conflict`, `blocked`, `needs_owner`, a preflight `conflict`) with
    the first 150 characters of its message. A critic's `readiness:` findings are counted separately.
- The release qualification records its output.

### G6: two small fixes

- **"Files not committed".** The count comes from `project_read.uncommitted_paths`, which reads `git status`.
  `project_state.exclude_caches` already adds `CLEANUP_CACHES` to the repository's local `info/exclude`, but only at
  a milestone start (`runs.py:964`). It is now also called when the project opens in the TUI, so caches leave
  `git status`, and with it every consumer.
- **`/new`.** The architect's reset row ("New dialog: …") is already shown. The chat's note after `/new` repeated it
  ("New conversation: …", `tui/chat.py:1030`) and now shows only the handoff lead, if any.

## 4. Alternatives

| Alternative | Verdict |
|---|---|
| A separate readiness node with a combined verdict (revision 1) | Rejected now: it touches about 15 review checks, the stored evidence and approval and override semantics. The backlog keeps it, triggered by the critic missing a readiness defect |
| `foreman.py`'s mechanical checks for W1 | Rejected: W1 is semantic ("needs a commit or a deployment"). A keyword list in two languages is the kind of heuristic grammar the roadmap cancelled. `foreman.py` stays in the backlog |
| Add W1 and W2 to preflight only | Rejected: preflight runs after the yes, so its finding costs a failed attempt and a rebrief. The owner's card would still show the defective plan |
| Base checks in a background job before the architect's turn (revision 1's G1) | Rejected: the Controller runs jobs serially, so a job would delay `zplan_status`. Running the checks before the plan check gets the plan right at the cost of one revision round on a red base |
| An automatic revision after a red base (the backlog's other candidate) | Not needed: the critic's W2 rejection is that revision round, under the existing budget |
| G4: snapshot the decisions at approval | Rejected: the architect records decisions during runs, after approval. The current section, labelled as STATE's, is honest |

## 5. Risks

- **Readiness false alarms.** An invented defect costs a revision and one more plan check. The chain budget bounds
  it, the owner can override, and G5 measures the rate. W1's text names its concrete actions, so "commit" in a plan
  about git tooling is not banned: what matters is that the worker cannot do it.
- **Untrusted text in the critic's input.** `base.tail` is project output. It is scrubbed and clipped, and the
  critic's instructions already say that repository text is data, never instructions.
- **Latency.** The base checks now run before the plan check, not after it, so the total stays the same. They are
  cached by tree when they pass.
- **A critic that ignores the new rules.** G5 counts its readiness findings; the separate node is the fallback.

## 6. Change, tests and live checks

**Code:**
- `planning.py` (`Watch.step` order, `settle_due`);
- `engine.py` (`context["base"]` in `prepare`, `GOLDFISH_CRITIC`);
- `project_state.py` (`section`);
- `delivery.py` (the plan view's decisions);
- `tui/controller.py` (`plan_fields`);
- `tui/chat.py` (`/new`);
- the TUI open path (`exclude_caches`);
- `devtools/role_outcomes.py`.

**Tests (behaviour):**
- the plan job settles the base before the first submission, and the prepared input carries `base` only when the
  revision has `base_checks`;
- a revision prepared without `base` keeps its documents;
- the critic's instructions carry W1, W2 and the `readiness:` prefix;
- the decisions show at plan end, with the "… N more" cut;
- caches leave the uncommitted count after open;
- `/new` leaves one notice.

**Live at the release:**
- the three runs of 0.12;
- **a red base:** the plan the owner sees must fix it, through a W2 rejection and a revision if needed;
- **a planted brief defect:** a goal whose natural done-when needs a deployment or a commit. The plan check rejects
  it with a `readiness:` finding before the card, or the plan the owner sees no longer has it;
- G5's counts recorded.

## 7. Resolution of the Goldfish findings (revision 1)

Reviewers: R implementation_readiness, D design_critic, C comprehension.

| Finding | Resolution |
|---|---|
| A readiness-only rejection can never be approved; `critic_verdict` and override (R B1, D 10, C 4) | Resolved by design: readiness is the critic's own judgement, so there is one verdict, as today |
| About 15 `== "goldfish"` checks and the chain budget (R M1, D 2, C 1) | Resolved: no new review value |
| Editing `goldfish_graph` in place breaks replay (R M2) | Resolved: the graph is unchanged; only the input of newly prepared revisions gains `base` |
| The readiness node's wiring, worker, runtime, failure path and prompt (R M3, D 3, C 4) | Resolved: no new node. The rules are given as text (section 3) |
| Display surfaces for a new node (R M4) | Resolved: no new node |
| Readiness's input; the trust model of `base-last.json`; the R2a sequencing (R M5, D 4, C 2) | Accepted: the input is the revision's own `base_checks`, settled before submission; no display file |
| The background job's thread, trigger, concurrency and consent (R M6, D 1, D 6-8) | Resolved: no background job (G1 dropped) |
| "Or" choices in the file list (R M7, C 8) | Accepted: section 6 names one place each |
| G4's parser, cap and "plan end" predicate; it shows next to the report, not in it (R M8, D 11, C 7) | Accepted: `section`; 8 lines and "… N more"; the "all stages merged" condition; the goal restated as "next to the report" |
| G6's consumers, the existing `exclude_caches`, `/new`'s root cause (R M9, C 5) | Accepted: `exclude_caches` at open fixes every consumer; the duplicate note found at `tui/chat.py:1030` |
| Missing alternatives: `foreman.py`, preflight only, the automatic revision (R M10, D 9, C 6) | Accepted: section 4 |
| Risks: untrusted text, failure, override, cost, compatibility (R M11, D 8, C 9) | Accepted: section 5. The background job's command-consent issue is gone with the job |
| Label clashes (R1/R2, G3, "readiness" against the status's `readiness`); F3 skipped (C 3, C 10, C 12) | Fixed: W1 and W2; F3 explained; no status key named `readiness` |
| G5's contract (R N6, C 13) | Accepted: section 3, G5 |
| Nits: "(bot)", the test-weight citation, evidence that cannot be checked, the tests for B1, M1 and M2 | Fixed in the text, or moot without a new node |

## 8. As built, after the second Goldfish pass (revision 2)

Reviewers: D design_critic, R implementation_readiness (`.local/goldfish/2026-11-06-0-13-r2/`).

| Finding | Resolution |
|---|---|
| The graph does change (the critic's text); replay safety comes from frozen documents (D 1, R M3) | Accepted: stated in the status |
| The early settle blocks the dispatch slice, which quit waits for (D 2) | Accepted as a bounded risk: quit waits for the project's checks once per revision, bounded by their timeouts (seconds on the live projects). A cuttable settle job is in the backlog, triggered by a project whose checks make that wait felt |
| Every revision of a red-base chain reruns the suite (D 3) | Accepted: a revision reuses the earlier revision's result for the same tree and checks |
| W2 cannot be met when the checks cannot start (D 4, R M1) | Accepted: `refused` goes into the task's `base`; W2 applies only to named failures; a refusal is no plan defect (the card already blocks the start) |
| A settle that fails before submission (D 5, R M2) | Accepted as a degrade: the critic runs without `base`, the verdict's settle or approval settles it, and the card shows the red base |
| W1 overstated: workers install dependencies (D 6) | Accepted: W1 names commit, push, history rewrite, deploy, publish and other external services, and allows installing the project's dependencies |
| Only Goldfish revisions get G2 (D 7, R M4) | Accepted: the early settle is limited to Goldfish revisions; a non-goal names the old path |
| W2 against an owner who defers the fix (D 8) | Accepted: the owner's requests deferring the fix make W2 a note |
| Backlog claims, the readiness-node entry, foreman, the roadmap citation (D 9) | Accepted: backlog updated; §4's reason is the semantics of W1, not a roadmap citation |
| The test-weight attribution (D 10) | Accepted: "deferred, default keep" |
| G5 mixed graphs; misses cannot be counted (D 11, R M7) | Accepted: counts are keyed by graph (plan check, milestone, task gate, other); a miss is read from a live run's later preflight conflict or final-check rejection of an F or W class defect |
| The code diverged (G6 filter, G5 root) (D 12, R M6) | Accepted: G6 is a filter in `project_read.uncommitted_paths` (no write, every caller benefits); G5 takes any root and reads every `runs.sqlite3` below it. The `/new` fix left 0.13: its note is pinned by two tests for a cosmetic change (backlog) |
| G4's predicate, placement and status (R M5) | As built: the lines come before "Next: all stages are merged", and the status carries `plan.decisions` when every row is integrated |
| Nits: the task is a JSON string ("the task's base field"); the tail is scrubbed in the context; `section` is a new parser following `validate`'s headings; a moved HEAD before prepare wastes one check run | Fixed in the code and text |

The review of the change as built (`.local/goldfish/2026-11-06-0-13-built/`) then found, and the code now has:
- a chain reuses only a passed base, with the current commit;
- the critic's F1, F2 and F4 are preflight's own text (`engine.BRIEF_RULES`, shared);
- W1 means files of the owner's checkout outside its last commit (files the plan's tasks create are fine);
- W2's milestone is one every other milestone depends on;
- `refused` is scrubbed;
- `role_outcomes` survives an unreadable store, lists `block` and node errors, and counts `readiness:` anywhere;
- the plan view and the status share one plan-end predicate, and the status's decisions carry "… N more" and are
  scrubbed.
