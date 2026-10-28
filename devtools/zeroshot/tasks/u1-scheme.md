U1 — the scheme renderer as a product module (release 0.5.2, docs/RELEASE_0.5.2_PLAN.md, run u1-scheme).

Goal: `terminal_planner/tui/scheme.py` draws any Zeroshot graph plus a per-node observation as a Rich `Text` that fits a
given width x height. It is a port of the approved lab prototype `devtools/ui-lab/flowdraw.py` (read it first: `project`,
`render`, `_full`, `_tree`, `_window`, LEGEND, NAMES); behaviour and look stay the same. Nothing imports it yet; the
integration run i1 does.

Data: graphs come from `terminal_planner.milestone.milestone_graph(...)["root"]` and
`terminal_planner.engine.planner_graph_v2(rounds)["root"]` (structure fixtures: `devtools/ui-lab/fixtures/*.json`). An
observation maps a node name to `{"state": running|succeeded|failed|idle|skipped|recorded, "detail": str|None,
"timer": "m:ss"|None, "count": int|None, "title": str|None}`; every key optional.

Write-set: terminal_planner/tui/scheme.py (new), tests/test_tui_scheme.py (new). Nothing else.

Acceptance criteria:
- A1 `render(graph_root, observation, width, height, tick=0, words=None) -> rich.text.Text`, pure (no I/O, no clock),
  same three fitting modes as flowdraw: boxes when they fit, else one-line tree, else a window around the running
  step with folded ends; the result never has a line wider than `width` cells nor more than `height` lines, for the
  milestone graph (rounds 3) and the planner graph, at sizes 40x10, 70x30, 120x40.
- A2 States: running shows a spinner frame chosen by `tick`, succeeded ✓, failed in a reviewer (verifier) ✗ and in a
  worker step `!`, idle ◌; a choice draws only the taken branch (or the default before start); a `loop` shows ↻ with
  `count` of `maxIterations` when count is set, "до N раз" otherwise.
- A3 Words: every visible word comes from one table keyed by GLOSSARY ids (`docs/ui-redesign/GLOSSARY.md`: role.*,
  state.*, flow.*); `words` (a callable id -> text, or None for the built-in Russian table) replaces them. Unknown
  node names show as the name with `_` -> space. `LEGEND` is exported as a function `legend(words=None) -> Text`.
- A4 `observation_from_flow(flow: dict) -> dict` builds an observation from `terminal_planner.live.flow(...)` output
  (read live.py:322-395): worker state, the two reviewers (verdict accepted -> succeeded, rejected -> failed),
  final step running -> `final_verify` running, `select` true -> `select` running, `round` -> `review_loop.count`,
  `command` -> worker detail; `None` or an empty dict gives `{}`.
- A5 One test per criterion; tests read plain text of the result (`.plain`), not styles, except one style check that
  failed and error differ.

Non-goals (reviewers must not require): wiring into app.py, a planner observation builder, animation timing, colour
themes beyond the 16 ANSI names flowdraw uses, any change to flowdraw.py, flow.py or live.py.

DoD: `python3.13 -m unittest tests.test_tui_scheme tests.test_toolchain tests.test_reference` with TMPDIR short
(preamble), all green.
