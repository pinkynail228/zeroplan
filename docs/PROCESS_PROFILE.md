# Process profile — design

Status: 2026-10-15. Gate: critic profile1 GO WITH CHANGES (10 edits + split G1), applied.

## Why

Today the owner gets a disciplined process only by chatting with an external orchestrator (Claude Code) that keeps
project rules (AGENTS.md), argues every key stage with a strong critic, runs Zeroshot, checks the result, runs
qualification, merges and keeps STATE.md. The owner wants that process inside zplan, on by default for a new or an
existing project, and configured once instead of re-asked every session. A prompt-driven framework (GSD-style) failed
the owner because the agent graded and tracked its own work; zplan must not repeat that: every gate is a separate
native run, its verdict is evidence bound to an exact artifact, and moving on is refused without it.

## Non-goals (cut)

- Arbitrary stage topology, a workflow language, profile inheritance or a profile marketplace.
- Importing prose rules as executable policy. Rules are context for agents, never authority.
- A new scheduler, a second lifecycle store next to `planning.json` (Authority), or a second registry of
  graph/runtime profiles next to native `RunProfile`.
- Mixed harnesses in one run (native fixes harness/provider per run, upstream runtime-plan.md:24).
- This repository's own setup (the Linux test host, devtools/linux-test.sh) as product defaults; it is one profile instance.

## Owner requirements -> stages

| # | Requirement | Artifact | Gate | Evidence | Owner approval | Recovery | Stage |
|---|---|---|---|---|---|---|---|
| R1 | Process on by default, configured once | `zplan.process.json` + resolved config | bootstrap | resolved-config digest | accept / later | edit file / screen | G1a |
| R2 | Plan argued with a strong critic | plan revision | plan gate | discussion + critic verdict | approve plan | revise / override | G1b |
| R3 | Task briefs checked before they run | frozen task briefs of a milestone | task gate | discussion + verdict on briefs digest | start milestone | owner revises plan | G2 |
| R4 | Merge only after qualification + critic | exported result commit | merge gate | check results + discussion + verdict | merge | new attempt / override | G3 |
| R5 | Release decisions reviewed | release milestone result + release decision/checklist | merge gate (release mode) | as R4 + checklist verdict | merge | as R4 | G3 |
| R6 | Scope changes reviewed | changed goal/scope | plan gate on the new revision | as R2 | approve | as R2 | G1b |
| R7 | Project truth without a chat | Authority records | — | derived status | — | — | G3 |
| R8 | Work survives closing zplan | gate records | — | submission protocol | — | reopen | G1b-G3 |

A release is a milestone marked `release` in the plan; its merge gate gets the owner's release decision, checklist
and proposed verdict, not just the diff. A scope change is always a new plan revision, so it passes the plan gate.

## Profile (tracked, versioned)

File `zplan.process.json` at the project root (not under `.zplan/`: tracked content there blocks export,
runs.py:1053). Credentials, sessions, transcripts, gate records and receipts stay outside the checkout.

```json
{
  "preset": "zplan.default/1",
  "rules": ["AGENTS.md"],
  "roles": {"planner": {"model": "...", "effort": "high"}, "critic": {"model": "gpt-6.1-sol", "effort": "xhigh"},
            "worker": {"model": "...", "effort": "medium"}, "reviewer": {"model": "...", "effort": "high"},
            "steward": {"model": "...", "effort": "high"}, "architect": {"model": "...", "effort": "high"}},
  "gates": {"plan": "required", "task": "required", "merge": "required"},
  "limits": {"plan_rounds": 3, "task_rounds": 2, "merge_rounds": 2},
  "checks": [{"name": "unit", "argv": ["python3", "-m", "unittest"], "timeout_s": 1800}]
}
```

- `preset` names shipped defaults. A shipped preset version is frozen: `zplan.default/1` (G1a) has task/merge `off`; turning new gates on ships `/2` with a migration shown to the owner (accept to move), never a silent change of `/1`. Unknown keys are refused (a typo must not silently disable a gate). `gates`:
  `required` or `off`; `off` is shown everywhere as "без проверки". A `required` gate whose stage is not built yet
  blocks its action with a named refusal (no silent pass).
- Resolution precedence per key: project file -> compatible user `roles.json` (roles only) -> versioned preset.
  `plan_verifier` in `roles.json` is read as `critic`. The **resolved** configuration (with defaults and fallback)
  is hashed and frozen into each revision/gate; frozen roles/runtime of existing revisions are never rewritten
  (engine.py:394).
- `rules`: repository files given to agents as owner rules, in the listed order; their digest is part of the
  resolved config. Agents keep refusing rules that contradict the frozen task or graph mechanics.
- `checks`: argv run by zplan; a remote host is just a command (e.g. `["devtools/linux-test.sh"]`). No `checks` =
  "без квалификации" shown on the merge screen.

## Bootstrap and profile states

| State | Behaviour |
|---|---|
| No file, never accepted | One screen: proposed profile (preset; found AGENTS.md/CLAUDE.md as rules in shown order; an obvious test argv shown exactly, detected without executing anything: `npm test` (package.json `scripts.test`), `make test` (a Makefile `test:` target), `python3 -m pytest` (pytest configured in pytest.ini, pyproject.toml `[tool.pytest` or setup.cfg `[tool:pytest]`), `python3 -m unittest discover -s tests` (`test_*.py` under tests/) or `python3 -m unittest` (`test_*.py` files directly in the project root), in that order, each only when one of those files imports unittest (`import unittest` or `from unittest`; a pytest-style file gives no check); the proposal turns `gates.merge` to `required` when it found a check and leaves it `off` otherwise). Keys: accept (writes the file, says to commit it) / edit / later |
| "Later" | The effective resolved snapshot is stored in Authority and used; header shows "профиль не сохранён" |
| Accepted file present | Used; changes are picked up at the next action and invalidate open gates (below) |
| Accepted file deleted or malformed | New actions blocked with a clear refusal and the fix; existing frozen runs can still be watched and finished |

## Ownership

| Layer | Owns |
|---|---|
| Native engine | agent execution, in-graph argue/repair loops, sessions within a run, retries/timeouts, checkpoint/resume, terminal results; `RunProfile` = graph + runtime |
| zplan service | project configuration (rules, gates, limits, checks — what `RunProfile` does not hold), materializing graphs submitted via `--graph`/`--runtime-config`, order between runs, gate records, checks, owner approvals, Git delivery, derived truth |
| TUI / plain / chat | commands and presentation only; the process continues with the chat closed and in plain mode |

`sessionScope: node_instance` is one conversation inside one native run. A finished run's provider session is never
resumed by a new run; a new artifact or a lost session (`session_lost`) means a new gate record.

## Gate discussion

Every gate graph is a bounded loop of two read-only nodes: a **proposer** that presents the artifact with its
proposed verdict and, from round 2, answers the critic's findings (fixed / disputed + why), and the **critic**
(`node_instance`) that accepts, accepts a reasoned dispute, or repeats concrete unresolved findings. For the plan
gate the proposer is the existing planner, which also repairs the proposal. For task/merge gates the proposer cannot
change the artifact; it only argues, so rounds settle disputes, and a final rejection goes to recovery.
The graph's terminal output carries a versioned bounded `discussion` (`[{round, findings, response}]`, capped);
old four-field results stay readable (`completed_review`, authority.py:680). Evidence history is never rebuilt
from UI logs.

## Gate record

Reuses the plan submission protocol: frozen graph/runtime/input, native binding and state location, submission key,
uncertainty recorded before dispatch, terminal identity and output digest (authority.py:460). Adds:
`{gate, artifact_digest, resolved_config_digest, head, discussion, critic_verdict, override}`.
- Native failure (`*_failed`, `session_lost`) and semantic rejection are different outcomes; native `succeeded` is
  not acceptance — only `critic_verdict == accepted`.
- Invalid when the artifact, resolved config, rules or relevant HEAD change: "проверка устарела" + rerun key.
- Override: a separate owner record with a typed reason; the critic verdict stays as it was. Policy is
  "accepted or overridden" (today approval requires `accepted`, authority.py:598). Shown on the result and status.
- Exhausted rounds = rejected.

## Stages on native graphs

- Plan gate (G1b): the existing planner graph; `critic` binding with `node_instance` (today `execution`,
  engine.py:224); planner returns `planResponse` next to the proposal; `maxIterations = limits.plan_rounds`.
- Task gate (G2): a separate small run before a milestone starts, over its frozen task briefs + HEAD. Final
  rejection: findings -> owner revise -> new approval -> new task gate. 0.5 limitation: task gates protect new attempt starts.
  In-run steward amendments may reach subsequent workers without regating; deterministic prevention and detection
  of every worker's received contract are not provided. The amendment barrier is deferred beyond 0.5.
- Merge gate (G3): after a `done` attempt is exported (tree/commit fixed, runs.py:1041), zplan runs `checks` in a
  clean checkout of that result commit and records result SHA/tree, destination HEAD, checks digest, exit statuses.
  Failing checks block a normal merge regardless of the critic. Then the critic run over the exact diff + check
  results (+ release decision/checklist for a release milestone). Before `[m]` the identities are rechecked.
  Rejected -> new attempt with the findings as feedback, or override.
- Truth (G3): `zplan status` and a TUI panel derived from Authority: current gate, last verdicts, next action,
  owner notes; `--markdown` exports a STATE-like file.

## Risks

- Cost and non-convergence: bounded rounds, spend/elapsed shown, exhaustion visible, no silent retry.
- Native verifier complexity ceiling (milestone.py:350): gates are separate small runs, never nested into the
  milestone graph; each new graph is qualified natively on the Linux host before merge.
- Unsupported model/effort pair (native does not check): doctor shows each binding; a gate failure names the role
  and its binding. No paid probe in doctor.

## Acceptance scenarios (each stage)

reject -> repair -> accept; reasoned dispute accepted; exhaustion blocks approve/start/merge; override needs a
reason, keeps the critic verdict and is shown; artifact/config/rules/HEAD change invalidates; crash after dispatch
does not duplicate the run; restart mid-gate resumes or reports; when `gates.task == "required"`, a new attempt never starts without a valid task gate;
a `required` but unbuilt gate blocks its action; every required gate is unbypassable from TUI, plain and CLI;
deleted/malformed accepted profile blocks new actions but not watching old runs.

## Order

1. This doc (critic profile1, applied) -> TUI_PLAN/STATE.
2. G1a: profile schema + resolver + roles.json fallback + effective snapshot + minimal bootstrap (TUI and plain) +
   doctor. No editor, no planner graph change.
3. G1b: argued plan graph, versioned discussion/evidence, gate lifecycle, invalidation/override, `[i]`; native
   qualification on the Linux host. Then a critic accumulated-diff review (replaces owner review #2).
4. U3b chat on top of the service (drafts goal/task/decision; shows gate discussions; transcript is not authority).
5. Orchestrator runs dogfood-polish (revised per critic polish, item 5 dropped) through zplan on a clone.
6. U4 release 0.4.0 with G1 only; P0 before any public show.
7. 0.5: G2 task gate before new attempts (amendment barrier deferred); G3 checks + merge/release gate + derived truth; preset `/2` migration.

0.4 boundary (plan reset 2026-10-16 (owner; critic plan-reset GO WITH CHANGES)): 0.4 ships G1a/G1b. `/1` stays unchanged; R3-R5/R7 are shown as not built,
`required` on them still refuses with `process.unbuilt`, nothing is switched to `off` automatically. Not protected
in 0.4: an amendment can reach the next worker inside a milestone without a gate (R3); merge/release are gated by
the orchestrator by hand, not by zplan.

A7a (0.6, lane T step 5): the merge gate is built. With `gates.merge: required` a merge builds one candidate commit
(destination head + result, `Risk-Tier:` and `Checks:` in its message), runs `checks` on that exact commit and
fast-forwards the destination to it only when they pass and nothing moved meanwhile; `process.unbuilt` for the merge
gate no longer exists (`gates.task` still refuses). The critic over the merge, its triggers and the cleanup after the
merge are A7b.
