A7b2 — a gated merge asks the merge critic and lands only on its `go` (RELEASE_0.6.0_PLAN lane T; ARCHITECT_DESIGN.md
section 10 item 3; wiring half of A7b). Design: ~/zs-pause/critic/a7b-design.out (3-7), a7b2-design*.out.

Why: A7b core (merge_critic.py, engine `critic_run`) exists but nothing calls it; `gate_merge` (runs.py:1369) lands
any candidate whose checks passed, whatever its risk.

Reuse: runs.py `merge` :1312, `gate_merge` :1369, gate fields check :547; merge_critic.py `reasons` :56,
`input_digest` :68, `record` :95, `allows` :169; engine.py `critic_binding` :1623, `critic_run` :1640, fixture
`critic_run` :283, `gate_binding` :252; delivery.py `merge` :1037, `task_gate_engine` :667, `task_gate_new` :697,
`task_gate_recovery` (rebuild vs None); cli.py merge :762.

Write-set: terminal_planner/runs.py, terminal_planner/delivery.py, terminal_planner/cli.py,
terminal_planner/catalog.py, docs/REFERENCE.md, tests/test_merge_gate.py, tests/test_reference.py.

Acceptance criteria:
- C1 Candidate reuse: a gated merge whose `r["gate"]` names the same destination ref, head, result and config
  digest with evidence `passed` reuses that candidate and evidence (no new `commit-tree`, no check rerun); else a new
  candidate as today. `r["gate"]` gains `critic` (record id or None); a stored gate without it still loads (:547).
  Example: an old store's gate record loads; a pending merge called again lands the same candidate SHA.
- C2 Trigger and engine: after the checks pass, `reasons(risk, facts={})` (no gathering: path-less triggers are
  unchecked, so raised); no reasons -> land as today. Identity: the pinned gate fields plus milestone, plan
  revision, attempt, risk, `input_digest(reasons, changed paths, the milestone's frozen briefs)`. The engine comes
  from the planning factory of the revision (`task_gate_engine`); binding: native `critic_binding`, fixture
  `gate_binding`; role `resolved.roles()["critic"]`; a recovery uses the record's own binding.
- C3 Record and recovery: the newest `state["critics"]` record with an equal identity is reused: never prepared ->
  documents rebuilt with the same digests; prepared or submitted -> documents None (observe, never resend);
  `submission_unknown` -> today's `submission.unknown` refusal. None, or the newest ended without a verdict -> a new
  record appended and saved before dispatch (`task_gate_new` pattern). Example: a crash right after the append ->
  the next merge rebuilds the documents and dispatches once.
- C4 Bounded verdict: `Delivery.merge(r, slice=CRITIC_SLICE)` (5 s, a delivery.py constant; the Controller's call is
  unchanged; cli.py passes None = wait) reaches `critic_run`; `SliceEnded`/`ObservationDetached` -> refusal
  `merge.critic_pending`, records kept, nothing landed; other errors stay errors. `block` -> `milestone.critic_blocked`
  naming the first 3 findings; ended without a verdict -> `merge.critic_failed` (the next merge may start a new
  record); `go` and `allows(record, identity)` -> the existing `unchanged` check runs after the critic, then the
  `--ff-only` landing. Example (fixture): pending -> merge again -> go -> landed: one candidate, one qualification,
  one dispatch; separately BLOCK and no-verdict refuse and land nothing; HEAD moved during the critic ->
  `milestone.merge_refused`.
- C5 Text: the three families in catalog.py and docs/REFERENCE.md; `Delivery.merge` shows them as "Не выполнено:
  ...", the attempt stays `awaiting_merge`. Example: `merge.critic_pending` does not render as `unknown_error`.

Non-goals (reviewers must not require): gathering `facts` (Later); a TUI critic view; architect tools (A5t2); A9;
merge_critic.py, engine.py, authority.py, tui/ changes; cleanup changes.

Risk: high (merge landing, persisted records). DoD: `python3.13 devtools/fasttest.py tests.test_merge_gate
tests.test_merge_critic tests.test_merge_cleanup tests.test_reference tests.test_toolchain` exit 0; quote the
`fasttest:` lines.
