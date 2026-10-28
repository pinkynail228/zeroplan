s1b2-qualification-records — 0.5 item S1b, slice 2 of devtools/zeroshot/tasks/s1b-checks.md. Superseded by a split before dispatch; not dispatched itself.

Why: critic gate12 (~/zs-pause/critic/gate12.out:8, point 4): the estimate (560-610) already crossed 600 and the agreed UI cut existed, so the slice is split now. A records slice must not offer a button that does nothing.

Order: s1b1 → s1b1b1-check-guard.md → s1b1b2-check-sweep.md → s1b1c-git-bound.md → s1b2a → s1b2b; s1b2a also needs s1a1b1.
- s1b2a-qualification-records.md: the store list, `Delivery.qualify` (sweep → HEAD read → marker → executor → save), validity, restart, the display texts in Delivery; no key. Estimated 470-560.
- s1b2b-qualification-ui.md: `[v]`/`[i]` on plain and TUI, the long-job rule, `UNBUILT["merge"]` text, describe, docs. Estimated 260-340.

Decisions carried (gate11:13-16, gate12:12): no subcommand (TUI + `zplan --plain`); one `v` letter shared with the task gate on different screens; cancel UX parked after the boundary. A death of zplan while a guard is alive is cleaned up at once by that guard; with no guard alive (between calls, power loss, the guard itself killed) the checkout stays until `sweep` at the next `qualify` (parent s1b1b R-2/R-3, owned by s1b1b1; `sweep` in s1b1b2); a directly killed guard is outside the cleanup guarantee (gate14).
