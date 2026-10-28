A9 — parallel core: several milestone attempts run at once, admitted by disjoint write-sets (RELEASE_0.6.0_PLAN
lane T step 7; ARCHITECT_DESIGN.md section 4 item 4). The Controller/screen side (Snapshot.busy, the [g] pick gate,
provider pause, N from the preset) is A9t.

Why: `Runs.start` (runs.py:734) and `Runs.resume` (:1251) refuse any second active attempt ("Один writer на
проект") and `Runs.reconcile` (:923) repairs only the first active record, so two disjoint slices never run together.

Reuse: runs.py `ACTIVE` :47 (includes the undispatched states: a reservation while a run's status is unknown),
`active_run` :52, `active` :693, `gate_manifest` :706, `critic_briefs` :700, `start` :716, `reconcile` :923,
`observe` :961, `resume` :1240, `waiting` :1549, `refresh` :1520; authority.py `BRIEF_KEYS` :244 (`write_set`,
validated :258); delivery.py `preview` :635, `start` :808, `step` :836.

Write-set: terminal_planner/runs.py, terminal_planner/delivery.py, tests/test_parallel_runs.py (new),
tests/test_runs.py.

Acceptance criteria:
- C1 Admission at start: the single-writer refusal becomes `admit(milestone_id, plan_revision, context=None, exclude=None)`:
  refused (family `action.refused`) when the active records (ACTIVE, in store order, `exclude` left out) number
  `MAX_RUNS` (3, runs.py constant) or more, when one of them is the same milestone, or when the milestone's write-set
  overlaps an active one's. An attempt's write-set is the union of `write_set` over the tasks of the bootstrap
  manifest it runs (`bootstrap_manifest(baseline, context)`: the revision's baseline plus an accepted candidate's
  added tasks; an active record's from its own frozen baseline and context). Paths are normalized first
  (`posixpath.normpath`, trailing "/" dropped; "." is the whole repository); two sets overlap when a path equals or
  is a directory prefix (`p + "/"`) of a path of the other; an attempt with a task lacking `write_set` overlaps
  every active record (fail closed) and is admitted only alone. Dependencies-merged (`waiting`) and every other
  start check stay. Admission schedules; the gated merge of each attempt on the current head stays the integrity
  guard, so live amendments inside a running attempt are not re-checked (Later).
- C2 Resume and follow-ups: `resume` (and a new attempt/answer of a milestone, through `start`) use `admit` with the
  resumed record excluded. Joint example (C1, C2): M1 running with {a.py}; start M2 {b.py} -> admitted, both
  running; start M3 {a.py} -> refused "Milestone M3 пересекается с M1 (a.py): ждёт его завершения."; M2 failed
  recoverable, then resumed while M1 runs -> admitted; M4 {./src/} while M1 holds {src/x.py} -> refused;
  M5 accepted candidate adding a task on {a.py} while M1 runs -> refused.
- C3 Reconcile per attempt: `reconcile` settles every active record in store order (preparing, submission_unknown,
  stopping, resume_pending as today, each its own); a refusal of one does not skip the others: the first refusal is
  raised after all were tried. It returns the first record still active (today's callers unchanged). Example: M1
  submission_unknown and M2 stopping after a crash -> one `reconcile` replays M1 and resends M2's stop.
- C4 Independence: two admitted attempts are observed, concluded, stopped and merged independently through
  Delivery (`preview`, `start`, `step`, `stop`, `merge`), and `overview` shows each row's own state. Example
  (fixture): M1, M2 running; M2 steps to `awaiting_merge` and merges while M1 is still `running`; stopping M1 leaves
  M2 integrated; the home rows show M1 `stopped`, M2 `integrated`.

Non-goals (reviewers must not require): Snapshot.busy / Home.busy, the [g] pick gate (delivery.py:591) and every
TUI change (A9t); provider pause and a preset N (A9t); free-disk check (Later); `Authority.begin` still refuses a
new revision while any run is active (authority.py:753, unchanged); the merge queue (the Controller's one worker
already serializes merges); cli.py `follow`; native parallel qualification (D-B).

Risk: high (lifecycle, persisted records). DoD: `python3.13 devtools/fasttest.py tests.test_parallel_runs
tests.test_runs tests.test_lifecycle_guard tests.test_toolchain` exit 0; quote the `fasttest:` lines.
