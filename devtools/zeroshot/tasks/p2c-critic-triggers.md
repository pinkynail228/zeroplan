# p2c — the merge critic runs on high risk and path triggers only, not on every gated merge

Owner decision F1 (docs/PLAN_0.9.md, P2). `merge_critic.reasons(risk, facts)` raises every path-less preset trigger
(`data_loss`, `process_kill`, `disagreement`) that `facts` omits (merge_critic.py:64), and its only caller passes
`{}` (delivery.py:1187), so every gated merge starts a critic run (rc1 walk N1: a 10-minute wait the owner could not
read). The owner asked for a critic on a high risk tier (docs/ARCHITECT_DESIGN.md:91).

Change: an omitted path-less trigger counts as not raised; an explicit `True` fact still raises it, an explicit
`False` drops it. `tier:high` and matched path triggers raise the critic as today.

Write-set: terminal_planner/merge_critic.py, tests/test_merge_critic.py, tests/test_merge_gate.py,
tests/test_tui_merge_wait.py (a fixture that needs a critic run gets a high tier or a trigger path, same assertions)

Acceptance criteria:
- A1 A low-risk gated merge needs no critic. Example: `reasons({"tier": "low", "triggers": [], "unmatched": []},
  {})` -> []; through Delivery a fixture gated merge of a low-risk change lands with no critic record added.
- A2 High risk and triggers still raise it. Example: `reasons({"tier": "high", "triggers": ["installer"],
  "unmatched": []}, {})` -> ["installer", "tier:high"]; `reasons(low risk, {"data_loss": True})` -> ["data_loss"].

Non-goals (reviewers must not require): gathering semantic facts, the critic's prompt, the merge wait UI, the
autonomy matrix (p2a), the critic record schema.

Conflict rule: if a test outside the write-set needs a critic run for a low-risk merge, change nothing in it and end
with `conflict: <file:line>`.

Risk: high (merge gate). DoD: `python3.13 devtools/fasttest.py tests.test_merge_critic tests.test_merge_gate
tests.test_tui_merge_wait`: exit 0.
