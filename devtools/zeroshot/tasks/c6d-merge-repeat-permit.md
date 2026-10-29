C6d — a repeated merge call of a waiting merge is admitted at the merge boundary, under the closing guard (release critic rel082d 1)

Release critic rel082d on bdf4ae7 (xhigh, reproduced through the real Controller): the c6c check `quit_begun()`
(tui/controller.py:1490) runs before `Delivery.resolve` in `_acting` (controller.py:1284-1291). A quit that begins
while the repeat resolves its token is not seen: `work` (controller.py:1475-1482) then calls `Delivery.merge` a
second time and the merge lands, without the closing line. Calls recorded: `[(1, quit=False), (2, quit=True)]`.

Reuse: `Controller._mutation` (controller.py:470-485), the permit pattern the export uses (taken under the guard that
`begin_closing` seals: admitted before the seal -> quitting waits for it; after -> refused), the c6c test of X2 in
tests/test_tui_merge_wait.py.

Write-set: terminal_planner/tui/controller.py, tests/test_tui_merge_wait.py

Acceptance criteria:
- P1 A repeat call of a waiting merge takes the `_mutation` permit inside `work`, after the token is resolved and
  right before `Delivery.merge`; refused -> no merge call and the wait ends with "zplan is closing; the merge was
  not repeated.". Example: pending, then the repeat's `Delivery.resolve` calls `begin_closing()` -> merge calls stay
  at one; the outcome carries the closing line.
- P2 A repeat admitted before the quit merges and quitting waits for it, as the export does. Example: pending, the
  repeat takes the permit, then `begin_closing()` returns True (a mutation in flight).
- P3 c6, c6b and c6c behaviour stays. Example: the existing tests in tests/test_tui_merge_wait.py pass unchanged.

Non-goals (reviewers must not require): the first merge call of a confirm (the owner's own admitted job), the
critic, the plain CLI, the architect's merge path, the UI.

Conflict rule: if a test outside the write-set pins `Controller.merge`'s calls during a quit, change nothing in it
and end with `conflict: <file:line>`.

Risk: medium (merge path). DoD: once at the end, run it in the foreground (it takes about 3 min):
`python3.13 devtools/fasttest.py tests.test_tui_merge_wait tests.test_merge_gate tests.test_tui_polish
tests.test_tui tests.test_docs tests.test_toolchain`: exit 0; budget.py: OK. New P1 test fails on today's code.
