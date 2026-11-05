# R1 design: tests in proportion

Status: built (97bdd77) and measured (2026-11-05): every goal merged at its first attempt and every held-out check
passed, the follow-up included, but test lines did not fall (358 against 324): the architect asked for tests in
every brief, naming a risk each time, and the workers wrote what was asked. Revision 2 (2026-11-05), after one Goldfish pass on revision 1 (`.local/goldfish/2026-11-05-r1/`:
comprehension, design_critic, implementation_readiness; section 7 resolves every finding). This is roadmap
revision 12, step R1. It narrows W0 3.2 (`docs/designs/2026-11-04-w0-worker-contract.md`) to what the live runs
showed. Only instruction texts change.

Terms:
- *Milestone run*: one Zeroshot run of one milestone. It has these nodes:
  - the *worker* writes the code;
  - the *acceptance review* judges a task against its criteria and runs nothing;
  - the *code review* judges the change itself;
  - the *final check* verifies the whole milestone at its end, with evidence it gathers itself;
  - *repair* fixes what the final check found.
- *Brief*: what the plan gives each task: goal, write set, acceptance criteria, non-goals, and *done-when* (the
  brief's `dod` field).
- *Durable test*: a test that is merged and kept.
- *Project check*: a command from the project's `zplan.process.json`, executed by code on the exact candidate before
  any merge.
- *Workspace*: the attempt's Git worktree. Everything left in it, untracked files included, becomes part of the
  candidate (`runs.py:213-220`, `export.py:118`).

## 1. Problem, with evidence

- **The volume of tests.** In two live runs on a FigmaPot copy (0.11; private evidence in `.local/diag/`), workers
  added 144 test lines for 24 product lines of Python, then 180 for 33. On the probe's projects the ratio was 656 to
  256 (W0 1, P2).
- **Advice did nothing.** Advice about proportion was added at least four times (W0 1, P1, citing `NOTES.md:30-32`),
  and once more in b11051d ("a test is the smallest one that proves its criterion"). The second run after b11051d
  still came out at 180 to 33.
- **The cause is a requirement, not missing advice.** Three texts require or invite tests:
  - the worker's `VERIFY_RULE` (`terminal_planner/milestone.py:35-39`): a behaviour change that existing tests do not
    cover "gets a relevant test";
  - the acceptance review (`milestone.py:520-521`): "do not accept a worker claim without evidence in the diff or
    tests", while it runs nothing;
  - the architect: both briefs of the 0.11 runs put "tests through the existing harness" in done-when. Its method
    (`terminal_planner/resources/architect_method.md`, Brief) says nothing about when a durable test is wanted.

## 2. Goals and non-goals

Goals, measured in section 6:
1. Fewer test lines per goal, in sum over the goals.
2. Every goal still merges, and its behaviour passes a held-out check.
3. The follow-up goal keeps the first goal's held-out check green.

Non-goals:
- the project checks and the merge gate: unchanged;
- the code review and `REVIEW_BAR`: unchanged, so a test nobody asked for stays a non-blocking `note:`;
- counting lines in code: that is R4;
- a tester role: it is in the backlog;
- this repository's own development rules, which are already done (F0 and the ratchet).

## 3. Design

Four instruction texts change, and no code path changes. All four land as one commit, so the revert rule reverts
them together.

**1. `VERIFY_RULE` is replaced.** It is shared by the worker, `repair` and `empty_repair`. Repair has no single task,
so the text names no task:
> Prove what you change by running it the project's own way, and report every command you ran with its output. Add
> or extend a durable test only when a brief's criteria or done-when ask for one, the project's root AGENTS.md asks
> for tests, the change introduces the project's first check, or it fixes a defect that escaped a merge. Such a test
> goes through a public boundary: it may assert output that is the contract (a command's format, words the owner must
> see), and it does not break on a change of wording or private structure that changes no behaviour. Any other check
> you write is throwaway: write it outside the workspace (the system temp directory) and leave nothing of it in the
> workspace. A change to docs, copy or config files alone gets only the project's existing checks.

**2. The acceptance review** (`milestone.py:520-521`) currently reads: "Judge the diff, the tests and the results
workerReport reports; run no checks (the final check runs them); do not accept a worker claim without evidence in the
diff or tests." It becomes:
> Judge the diff together with the commands workerReport reports and their output; run no checks (the final check
> runs them). Accept a criterion only with evidence in the diff or in a reported command and its output. A missing
> test is not a defect unless a brief's criteria or done-when ask for one, the project's root AGENTS.md asks for tests,
> the change introduces the project's first check, or it fixes a defect that escaped a merge.

**3. The final check** (`final_body`, `milestone.py:417-423`) is told to verify "every frozen requirement, every
acceptance criterion of the frozen task briefs and every derived milestone check". The briefs are already in its
input (`input.baseline`). So a criterion that the acceptance review accepted on a reported command is proved again,
by evidence the final check gathers itself.

**4. The architect's method.** The Brief line "Replacing a UI element deletes the tests pinning its text or keys; one
invariant test covers the surface." is replaced by:
> DoD names the commands that prove the criteria; ask for a durable test only for a named risk, a project's first
> check, or the owner's wish.

The method has 2 bytes of headroom under the 4600-byte cap that ten tests assert (`tests/test_architect.py:365`,
`:398`, `:410`, `:423`, `:857`, `:882`, `:895`; `tests/test_goldfish_architect.py:111`;
`tests/test_limit_resume_surfaces.py:72`). The line it replaces is about 107 bytes, and other lines are shortened
without changing their meaning until the cap holds. The cap itself stays.

## 4. Alternatives

| Alternative | Verdict |
|---|---|
| More advice about proportion | Rejected: tried at least five times (section 1) |
| A separate tester role (W0 3.7) | Deferred to the backlog: it adds a role before the cheaper change is measured; it comes back if R1 loses correctness |
| The acceptance review reruns the reported commands | Rejected: a second runner of model-chosen commands in a role that is read-only by design. The final check (change 3) re-proves the criteria instead |
| `REVIEW_BAR` rejects a test nobody asked for (W0 4) | Deferred: a rejection for an extra test costs a round; the measurement shows first whether the instructions suffice |
| Remove unrequested tests after the fact, at repair or merge | Rejected: it rewrites the verified candidate and wastes the work |
| A merge refusal on test volume | Rejected: it refuses work for its size, not for a defect |
| Change only the worker, or only the architect | Rejected: the worker's rule and the review must say the same thing, and the architect's briefs asked for tests in both runs |

## 5. Risks

- **Less protection over time.** Fewer kept tests guard later changes. Guards:
  - the follow-up goal and the revert rule;
  - a project check still runs whatever tests the project has.
- **Weaker evidence in the acceptance review.** A reported command is the worker's own text. Change 3 makes the final
  check re-prove every criterion with its own evidence. The deterministic gate, the project checks run by code, is
  unchanged.
- **A throwaway check left in the workspace is merged.** Untracked files become part of the candidate. The rule names
  the place for throwaway checks, outside the workspace, and the diff shows any new file to the code review and to
  the owner. The deterministic fact "paths outside the write sets" is in the backlog with `BLOCKED`, and its trigger
  includes a stray file reaching `main`.
- **Two goals detect only a large loss.** The result is reported as such, never as equivalence.
- **A confound.** FigmaPot's root `AGENTS.md` does not ask for tests (checked 2026-11-05). This is checked again on
  the copy that is used.

## 6. Change, tests and measurement

**The edits:**
- `milestone.py`: `VERIFY_RULE`, the acceptance review text and `final_body`;
- `architect_method.md`: one line replaced, others shortened.

**The tests:**
- `tests/test_milestone.py`, test_the_worker_and_repair_verify_in_proportion_to_the_change, pins the new rule's
  parts: "report every command you ran with its output", "only when a brief's criteria or done-when ask for one",
  "the project's root AGENTS.md", "the project's first check", "a defect that escaped a merge", "outside the
  workspace", "output that is the contract".
- The same test asserts that the acceptance review contains "A missing test is not a defect unless" and that the
  final check contains "every acceptance criterion of the frozen task briefs". Its docstring describes the new rule.
- The method's cap and its pinned sentences stay as they are.
- The fast tests of the touched modules run.

**The measurement.** The runs use the real flow: the architect plans again from the same goal text, so the worker,
review and architect changes are measured together, as one change.
1. *Goal A, help*: the goal text of run 1, from the base of run 1 (`824da524a3` in the copy).
2. *Goal B, status, then help and README*: the goal text of run 2, on A's merge. This is the follow-up goal.
3. *Before*: the 0.11 merges. Goal A added 144 test lines and 24 product lines; goal B added 180 and 33.
4. *Held-out checks*: `.local/diag/r1/checks/behaviour_checks.py`, written before the runs and kept out of the
   project. They drive the bot through its own test harness.
   - help: one reply in the same thread, naming the task command with an example; no Jira issue; no second reply
     after a restart.
   - status: the thread's issue key and link, or a reply without a key; no new issue; help names status.

   They pass on the 0.11 result and fail on the bases, so the before state is known.
5. *Pass*: every goal merges; the held-out checks of A pass on A's merge and again on B's merge (the follow-up), and
   B's pass on B's merge; total test lines of A and B are lower in sum than 324.
6. *Revert*: if any held-out check fails where it passed on 0.11, the commit is reverted.

## 7. Resolution of the Goldfish findings (revision 1)

Reviewers: R implementation_readiness, D design_critic, C comprehension.

| Finding | Resolution |
|---|---|
| The method's 4600-byte cap, with 2 bytes of headroom (R B1, D M5, C6) | Accepted: one line replaced, others shortened, cap kept; the cap's tests listed |
| `VERIFY_RULE` names `input.task`, which repair lacks (R B2, C2) | Accepted: the text names no task |
| "Unrequested" cannot be measured when both briefs asked for tests; reused or regenerated briefs; goal 3 has no before (D B1, R M4, C3) | Accepted: total test lines; plans regenerated through the real flow; the new goal dropped (no before); held-out checks run on 0.11 first |
| A throwaway check left in the workspace is merged, and the stated guards do not stop it (C B1, R M3, D M2) | Accepted: the risk restated as the code behaves; a named place outside the workspace; the deterministic fact's trigger in the backlog |
| Command-only proof weakens acceptance, and the final check did not re-prove criteria (D M3) | Accepted: change 3, the final check verifies every criterion of the briefs |
| Missing alternatives (D M4) | Accepted: rerun commands, `REVIEW_BAR`, removal after the fact |
| Conflict with R2's first check (D M6) | Accepted: a project's first check is a reason in all three texts |
| Behaviour checks and revert unspecified (R M5, C4) | Accepted: section 6, items 4-6 |
| Done-when versus `dod`; undefined terms; the confound only in the roadmap (C5, C7, C8) | Accepted: Terms; Risks |
| Nits: the contract-output exception; one name for AGENTS.md; "at least four"; "outside the workspace"; the pins to change; the cost of alternatives | Fixed in the text |
