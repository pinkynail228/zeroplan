# UI redesign (after 0.5.1)

Owner brief, accepted 2026-10-22. Live plan for the terminal UI/UX redesign.

## Scope
- UI/UX of the zplan terminal app only (`terminal_planner/tui/`). No backend changes, no new features,
  no Zeroshot worker runs: the orchestrator session writes the code itself.
- Target: one chat screen. Planning and milestone runs are background jobs shown inside it, not separate
  modes; closing the screen or the terminal stops nothing (the engine already behaves this way, U17).
- Terminal-agnostic: the release must work the same in any terminal (owner uses Ghostty; also check
  Terminal.app, iTerm2, a Linux terminal, inside tmux). No reliance on truecolor, ligatures, Nerd Font
  glyphs or terminal-specific keys; usable at 256 colors, 16 colors and `NO_COLOR`.

## Order
0. References: the owner sends visuals/references -> stored locally under the ignored `build/ui-lab-refs/` (third-party images stay out of git) with one note each
   (what to take, what not to take).
1. Scenarios and pains -> JTBD: together with the owner, from T1-T5/U1-U18 (RELEASE_0.5_SCOPE.md) and the
   references. Then baseline: run the 5-6 scenarios on 0.5.1, record keystrokes, dead ends, screenshots.
2. Screen state model and component vocabulary.
3. ASCII mockup per state at 80x24 and 120x40; the owner approves each.
4. Code only after approval: recorded fixtures (no backend, no tokens), shared tmux session the owner
   watches live, SVG gallery before/after after every step.

## Done when
- The owner completes the scenarios without hints, faster than the 0.5.1 baseline.
- A fresh agent without context, given only a screenshot, says correctly what is happening and what to do next.
- Snapshot tests clean at 80x24, 120x40 and after resize; colors degrade cleanly (256/16/`NO_COLOR`).
- All keys work with the Russian layout active.

## Status
2026-10-22: brief accepted; waiting for the owner's references (step 0).
2026-10-22: lab prototype of the welcome screen (`devtools/ui-lab/`, live in tmux session `zplan-ui`):
braille mascot, block word mark, prompt, status + commands, one dim key line; terminal ANSI palette only.
Owner: "наконец-то пошла жара" — this visual direction is the baseline for further screens.
