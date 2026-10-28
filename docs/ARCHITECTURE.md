# Architecture and development

How zplan is built and tested. For using it, see the [README](../README.md) and [USER_FLOW.md](USER_FLOW.md).

zplan is a terminal client: the [Zeroshot](https://github.com/the-open-engine/zeroshot) engine owns planning and
milestone lifecycle state, and the terminal UI only calls it. zplan itself is built with Zeroshot runs; the current
status is in [STATE.md](../STATE.md).

## Tests

```sh
PYTHONPATH=.:tests python3 -m unittest discover -s tests          # local unit suite
python3.13 devtools/fasttest.py                                   # the same suite, in parallel
python3 devtools/toolchain-candidate.py --help                    # qualify a candidate toolchain (UPGRADE.md)
```

Tests use deterministic fixtures and a scripted loopback provider; no test calls a real model.
`ZPLAN_TEST_WHEELHOUSE` names an offline wheelhouse (setuptools 75.8.0, wheel 0.45.1 and textual 8.2.8 with its
dependencies) for the installed-app tests; without it those tests skip.

The README GIF comes from `devtools/ui-lab/readme_gif.py` (frames) and `devtools/ui-lab/readme_gif.sh` (GIF): the
shipped app on the same fixtures, no model and no network. `devtools/ui-lab/readme_shots.py` makes still screenshots
the same way.

## Code map

`terminal_planner/`:

- cli.py: interactive UI, also line-oriented PTY. tui/: full-screen UI (app.py screens, controller.py actions).
- engine.py: native planner graph adapter + deterministic fixture.
- authority.py: locked `planning.json` in store v3 (proposals, revisions, approval, milestone runs). export.py: tree -> branch plumbing.
- milestone.py: manifest, amendments, driver graph. runs.py: milestone run records + native/fixture driver adapter.
- plan_tree.py: the pure plan task tree (milestone -> slice -> task) with each task's status from a milestone
  manifest; its plain text lines.
- snapshot.py: tree identity. setup.py: pinned tools, roles, login, doctor.
- process.py: the project's process profile (`zplan.process.json`: roles, gates, limits, rules, checks) and its acceptance state.
- architect.py: the architect turn. The shipped architect method is `terminal_planner/resources/architect_method.md`; a `zplan.architect.md` at the project root replaces it on the first turn of a conversation (copy the shipped text to start).
- tui/chat.py: the architect chat of the full-screen shell: one conversation per project, one turn per owner message.
- tui/flow.py: the status wrapping and clipping helpers: `wrap_status` (cell-width wrapping of the Now status lines) and `clip` (cut to cells with a visible `…`).
- tui/text.py: the pure text helpers of the shell: terminal-cell fitting and eliding, the escape scan that shows a value, the compact counters.
- tui/chat_view.py: the chat pane's layout: the header fields, the rows, the scroll window and its clamped offset, the state line.
- tui/modals.py: the modal screens: help, confirm, bootstrap, finishing, the note and text forms, the run end screen and its journal title.
- tui/screens.py: the goal form with its readiness block, the plan screen and Settings.
- tui/card_kinds.py: the decision cards' kinds: the shared card registries and the merge, question, plan, ready and failed card sources.
- tui/card_host.py: `CardHost`, the card methods of the main screen: showing, closing and routing the cards, and the merge, question and failure card data.
