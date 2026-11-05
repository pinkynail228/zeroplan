# zplan product contract

Status: active product direction. This document defines behavior, not a release roadmap. Current implementation gaps belong in `STATE.md`.

## 1. Product promise

The owner describes a software goal. zplan helps refine it, produces a reviewable plan, executes milestones through Zeroshot, verifies the exact result, and presents a merge-ready Git branch. The owner can understand and control the process at every stage.

The product is successful only when the whole path works without a manual workaround:

```text
goal -> conversation -> plan -> independent critique -> execution -> verification -> merge
```

An engine success, an accepted review, a passed check, and a merged result are distinct facts.

## 2. Roles and authority

### Owner

Sets direction and autonomy; can inspect and control every run. Push, tags, releases, publishing, and credential operations always remain explicit owner actions.

### Architect

The only LLM role that owns the product plan. It discusses the goal, asks only necessary questions, creates and revises milestones and briefs, starts and stops work within autonomy, interprets evidence, and explains outcomes.

There is no separate planner. Removing a second planner avoids translating the owner's intent through two different planning conversations.

### Independent critic

Reviews a non-trivial proposed plan, a material replan, or a requested high-risk decision. It identifies missing requirements, invalid assumptions, unsafe boundaries, and poor decomposition. The architect may fix or dispute a finding with evidence. A re-review is limited to unresolved findings; there is no default multi-round debate.

### Zeroshot workers and reviewers

Execute the selected graph. Workers implement; independent reviewers judge evidence and repairs. Their output is input to zplan's verification and delivery policy, not proof of delivery by itself.

### Deterministic controller and verification runner

Own commands, transitions, authorization, idempotency, durable state, check execution, candidate identity, and merge admission. Model output cannot override these rules.

### Delegation

The owner is needed twice: to approve the plan (its goal, requirements, non-goals and acceptance examples) and to read the final report. In between, the architect acts within the approved plan without asking:

- Questions come before the start, each with the default the architect will take; a question never stops work.
- Required checks run on the base before the first attempt. A check that cannot run or fails there is settled while planning, never mid-run.
- A worker's question, a blocked task or a review conflict goes to the architect. It decides within the approved plan, records the decision and its assumption, and starts a new attempt. It asks the owner only when the answer would change the goal, a requirement or a non-goal; other milestones keep running.
- Without the owner, a milestone gets at most two new attempts; the next decision is the owner's.
- A provider limit pauses the run until the limit resets; then the run continues.
- When the plan ends, the architect reports what was merged, the decisions and assumptions it made, the checks that passed, and what is not verified.

Push, tags, releases, publishing and credentials stay the owner's actions at every level.

## 3. One application core

TUI, headless automation, and qualification use the same operations:

```text
send_message
create_or_revise_plan
critique_plan
approve_plan
start_milestone
stop_milestone
resume_milestone
inspect_result
verify_candidate
merge_candidate
change_autonomy
```

Each operation has a typed request and result, a durable operation id, and an idempotency rule. All frontends read the same state projections.

The core owns current state plus an append-only operation/event journal. Full event sourcing infrastructure is not required; the existing durable stores may be migrated incrementally.

Important state distinctions include:

```text
draft -> validated -> criticized -> approved -> dispatched
      -> implemented -> reviewed -> verified -> ready_to_merge -> merged
```

A blocked, failed, stopped, detached, or needs-owner state always retains its reason and the available recovery actions.

## 4. Conversation user flow

### Sending a message

1. The owner types plain text and presses Enter.
2. Before any model call, zplan persists an owner message with a unique id, project id, conversation id, turn id, text, and timestamp.
3. The message appears immediately in the conversation timeline and the input clears. A send failure does not erase the text; a failed owner action offers retry or edit.
4. zplan creates an architect turn. The timeline shows pending/running state without removing earlier messages.
5. Tool calls produce typed operation results and visible activity entries. They do not create a second hidden conversation.
6. The architect response is persisted with the same turn id and a completed, failed, stopped, or partial status. Only then is it rendered as a final response.
7. A provider or process failure leaves the owner message, partial response, operation results, and recovery action intact.

Plain text is a conversation with the architect. A `/command` is a deterministic owner operation and never needs model availability.

### History and sessions

- One visible project timeline contains owner messages, architect messages, and clearly marked system/operation entries. Filters may hide entries but never delete them.
- Every entry has stable identity and ordering; reopening reproduces the same timeline without duplicates.
- Changing from conversation to plan, graph, diff, or logs does not change the conversation or clear scrollback.
- `/new` starts a fresh architect model session, not a new project and not a deleted history. A session divider is added; earlier messages remain readable.
- Reopening a project restores its timeline, current plan, active runs, pending decisions, and latest operation results before accepting new autonomous actions.
- A message typed while setup is incomplete is stored as a pending owner message for that project and is sent once when possible. It is never silently dropped or sent to another project.

### Questions and decisions

The architect asks before the start, and every question carries the default it will take (section 2, Delegation). When the architect needs owner input, the question is persisted and linked to the turn and relevant plan/run. The owner can answer in words or use a deterministic action. The answer and the resulting decision remain in the timeline.

A decision view states what is being decided, the evidence, and the available actions. It does not disappear merely because another event arrived.

## 5. Planning user flow

1. The owner states a goal in the conversation.
2. The architect asks a question only when the answer changes the product outcome. Otherwise it proposes a plan directly.
3. The plan appears as structured milestones, not only as prose in chat. The conversation entry links to that exact plan revision.
4. Deterministic validation checks schema, dependencies, paths, executable checks, budgets, and known invariants before any worker starts.
5. The independent critic reviews the proposed plan where required. Findings, fixes, and disputes are summarized in the timeline and linked to the revision.
6. The owner approves the first revision of every plan chain at every autonomy level, with one key or a yes in words to the plan he has seen. A later revision the architect makes in that chain is approved by the critic's accepted verdict; that approval still requires deterministic validation and the required independent critique.
7. Approval freezes the plan revision, base SHA, configuration, graph/preset identity, and checks.
8. Execution evidence may cause the architect to propose a material replan. It is a new revision, not a silent mutation of an approved plan.

A milestone is a coherent user-visible or architectural outcome with an integration check. Size limits are warnings, not a reason to fragment one contract across artificial microtasks.

## 6. Execution and graph user flow

Starting a milestone creates a durable attempt bound to the plan revision and base. Work occurs in an isolated worktree. The result is committed before final verification so reviews, checks, export, and merge can name the same tree.

The execution view is generated from the actual Zeroshot graph document and observed engine events. It supports at least:

- `seq` and nested sequences;
- `par` and parallel join states;
- `choice` and taken/untaken branches;
- `loop`, current iteration, and exhaustion;
- worker/verifier nodes and execution attempts;
- retries, repairs, failure exits, and success exits;
- prefixed or generated node instances.

It is a real block diagram, not a hardcoded linear sequence. A graph preset editor added later must reuse the same graph model and renderer.

The default graph view shows node name, role, state, current attempt, duration, and available result. Selecting a node opens its evidence. Raw logs are optional detail, not the main status interface.

No separate UI-only status flag is required to mark a node done: the projection derives that fact from the engine journal.

## 7. Verification and merge user flow

1. Task and milestone checks run through the deterministic verification runner in the project's declared environment.
2. Every check records argv, environment/interpreter identity, cwd, commit, tree, start/end, exit status, and bounded output.
3. A model may summarize or review the evidence but cannot change its outcome.
4. No configured checks means automatic merge is blocked. Manual merge, if allowed, is explicitly labelled unverified.
5. A baseline failure blocks automatic merge. An exception requires reproduction on a named base SHA and an explicit owner decision.
6. The merge gate integrates the destination, reruns required checks on the exact integrated candidate, applies critic/policy rules, and only then merges that candidate.
7. Any change after review or verification invalidates the corresponding evidence and returns the attempt to the required stage.

The merge view shows changed files, diff access, check results, critic/policy result, and the exact actions available.

## 8. Terminal UI contract

`zplan` always opens the terminal UI; there is no line UI. Non-interactive subcommands (`status`, `doctor`, `setup`, `login`, `exec`) serve scripts and automation. The default screen has:

- a plan/goal area with milestones, status, and blockers;
- a main area for the selected conversation, plan, graph, diff, check, or decision;
- a persistent event/timeline area;
- a persistent input for natural language and `/commands`;
- the project, branch, autonomy, and highest-priority current state.

The UI answers: what is happening, what is complete, why it is waiting, and what the owner can do next.

At wide sizes the plan and selected object are visible side by side. At 80x24 the same objects use compact panes or full-screen detail without hiding input and required decisions.

Control remains available without a model: stop, resume, inspect, diff, logs, merge when permitted, autonomy changes, and new architect session.

## 9. Required evidence for qualification

At minimum, the installed product must demonstrate:

1. a complete goal-to-merge flow with persistent conversation;
2. a non-linear graph with parallel reviews and a visible repair path;
3. reopen during execution without duplicate/lost messages or submissions;
4. `/new` with preserved project history;
5. a failing check that cannot be accepted or auto-merged;
6. no-check and baseline-failure merge refusals;
7. a real-provider flow with zero manual interventions;
8. stop, resume, and owner control while the architect is unavailable.

Fixtures may prove deterministic behavior. They do not replace the real-provider qualification of the same installed product path.
