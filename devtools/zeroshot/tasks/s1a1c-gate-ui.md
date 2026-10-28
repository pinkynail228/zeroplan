s1a1c-gate-ui — 0.5 item S1a, slice 3 of devtools/zeroshot/tasks/s1a1-task-gate.md. Superseded by a split before dispatch; not dispatched itself.

Why: critic gate11 B (~/zs-pause/critic/gate11.out:9-11) required Delivery.home/g_id/pick and the cli.py:301 dispatch in the write-set, plus an owner-context path (answer/accept → gate → continue) for plain and TUI. With those additions the estimate is ~830-1010 changed lines, above 600, so the slice is split before launch (gate11:11).

Slices (serial):
- s1a1c1-gate-plain.md: service offer/dispatch, the owner-context path, the plain gate screen, display, describe, docs. Estimated 500-590.
- s1a1c2-gate-tui.md: the TUI panel key, the gate modal, the owner-context routing in the TUI. Estimated 330-420. Built on s1a1c1's integration branch; the pair is integrated together (gate12:11).

Decisions carried into both (gate11:13-16): no subcommand, the parent's "plain and CLI command" reads as TUI + `zplan --plain`; one `v` for the task gate and s1b2's qualification; a dedicated gate screen; cancel UX parked after the s1b1b boundary.
