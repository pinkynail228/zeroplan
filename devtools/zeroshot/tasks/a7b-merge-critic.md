A7b — merge critic core: trigger rule, durable record, read-only critic graph and its run (RELEASE_0.6.0_PLAN lane
T; ARCHITECT_DESIGN.md section 10 item 3). No merge wiring (A7b2, after A5e). Design: ~/zs-pause/critic/a7b-design.out, a7b-brief.out.

Why: `gate_merge` (runs.py:1370) classifies the risk but nothing acts on it; a risky merge needs a fresh critic
whose BLOCK stops it.

Reuse: task_gate.py (record validation, output parser), authority.py:471/:480 (optional state lists),
engine.py `task_gate_graph` :863, `gate_run` :1354, `gate_prepare` :1426, `gate_observe` :1480, the fixture
driver's `gate_run` :257; checks.py `checkout` :77 (detaching at an unreferenced commit; do not import it: test_checks pins its caller).

Write-set: terminal_planner/merge_critic.py (new), terminal_planner/engine.py, terminal_planner/authority.py,
tests/test_merge_critic.py (new).

Acceptance criteria:
- C1 Trigger: `merge_critic.reasons(risk, facts)` -> sorted names: `tier:high` for tier high, each risk trigger
  name, and each path-less preset trigger (process.py:110: data_loss, process_kill, disagreement) that `facts`
  marks true or omits (omitted = unchecked, never "no"). Example: tier medium, triggers [], facts
  {"data_loss": False, "process_kill": False} -> ["disagreement"].
- C2 Record: optional `state["critics"]`, strictly validated on load like `state["gates"]`: id, identity
  (milestone, plan_revision, attempt, destination ref and base, result commit, candidate, tree, config digest,
  input digest, risk), reasons, binding, documents digests, submission_key, run_id, receipt, status, terminal
  output, verdict `go`|`block`|None, findings, diagnostic; the parser reproduces verdict and findings from the
  stored output. Example: a record whose stored output says `block` but verdict `go` fails to load.
- C3 Graph: `merge_critic_graph()`: one `verifier` node `critic` (plan_verifier role, `attempts` 1, session scope
  execution), input = identity, reasons, changed paths, the milestone's task briefs; signal verdict [go, block];
  error -> `fail("critic_failed")`. Example: it passes `--validate-only` admission like task_gate_graph.
- C4 Run: `critic_run(authority, record, documents, progress)` with gate_run's lifecycle: documents and intent
  saved before dispatch, `submission_unknown` refuses a resend, a recorded run id is observed, never resent; the
  read-only checkout is detached at `candidate` with `tree` verified; the fixture driver scripts the verdict.
  Example: a crash after run_id and receipt are saved -> the next call observes that run; a crash before that
  save -> `submission_unknown`, no resend.
- C5 Allows: `merge_critic.allows(record, identity)` is True only for verdict `go` and an identical identity;
  `block`, error, no verdict or any identity change -> False. Example: same record, other candidate -> False.

Non-goals (reviewers must not require): calling it from gate_merge or Delivery (A7b2); gathering the facts
(A7b2); task gate changes; UI; A9 reservations.

Risk: high (persisted store schema, native graph). DoD: `python3.13 devtools/fasttest.py tests.test_merge_critic
tests.test_task_gate tests.test_toolchain` exit 0; quote the `fasttest:` lines. AdmissionTests skip on this Mac
(no pinned 10.16.0); the orchestrator runs them on the Linux host.
