# Architecture and development

How zplan is built and tested. For using it, see the [README](../README.md) and [USER_FLOW.md](USER_FLOW.md).

zplan is a terminal app over the [Zeroshot](https://github.com/the-open-engine/zeroshot) engine. The product rules
are in [PRODUCT_CONTRACT.md](PRODUCT_CONTRACT.md), the plan in [plans/2026-11-03-roadmap.md](plans/2026-11-03-roadmap.md)
and the current state in [STATE.md](../STATE.md).

The flow and the modules that carry it:

1. **Conversation.** `architect.py` runs the architect, a read-only Codex conversation per project, with durable
   history. `architect_tools.py` gives it zplan's tools over MCP, `bridge.py` routes the calls to the live Controller
   (`tui/controller.py`), and `project_read.py` serves its reads.
2. **The plan.** The architect writes the plan, and `authority.py` validates and stores each revision (`check_draft`).
   `engine.py` runs the plan check as a Zeroshot run: a Goldfish reader retells the plan and a critic checks it.
   `planning.py` holds the plan revisions and the owner's approval. `autonomy.py` decides what the architect may do at
   each level, and the first revision always waits for the owner.
3. **Runs.** `runs.py` starts one Zeroshot run per milestone attempt, in its own worktree, with the graph that
   `milestone.py` builds (preflight, task selection, worker, two reviews, steward, the final and scope checks,
   repair and re-check). `live.py` observes it, and `feed.py`
   wakes the architect on events.
4. **Verification and merge.** `delivery.py` exports the candidate (`export.py`), runs the project checks on that
   exact tree (`checks.py`, `process.py` for the profile), asks the merge critic on high risk (`merge_critic.py`),
   merges, and cleans up.
5. **Setup.** `setup.py` installs the pinned tools of `toolchain.py` (Zeroshot 11.0.0, Codex and restic) on macOS
   arm64, and `update.py` moves an install to the newest release.

`application.py` is the operations layer that both the full-screen UI and headless automation call.

The old planner graph in `engine.py` still serves these entry points:

- the owner's `/plan`, retry and renew;
- "back to plan" at a run's end;
- a steward proposal the owner accepts;
- revising a plan the old planner made;
- the line UI (`cli.py`).

Declining or revising the architect's own plan goes to the architect, and the decline is stored on the revision, so
only the owner's card can still approve it. 0.15 moves every remaining entry point to the architect
(`designs/2026-11-06-0-14-lean-zplan.md`).

## Tests

```sh
PYTHONPATH=.:tests python3 -m unittest discover -s tests          # the whole suite
python3.13 devtools/fasttest.py [--lane full] [tests.MODULE ...]  # in parallel; the default lane skips tests/full_lane.txt
devtools/mac-test.sh                                              # the merge gate's run on this Mac
python3 devtools/toolchain-candidate.py --help                    # qualify a candidate toolchain (UPGRADE.md)
```

Tests use deterministic fixtures and a scripted loopback provider; no test calls a real model.
`ZPLAN_TEST_WHEELHOUSE` names an offline wheelhouse (setuptools 75.8.0, wheel 0.45.1 and textual 8.2.8 with its
dependencies) for the installed-app tests; without it those tests skip.

The README GIF comes from `devtools/ui-lab/readme_gif.py` (frames) and `devtools/ui-lab/readme_gif.sh` (GIF): the
shipped app on the same fixtures, no model and no network. `devtools/ui-lab/readme_shots.py` makes still screenshots
the same way.

## Code map

One line per module of `terminal_planner/`; each module's docstring says more.

The conversation and the plan:

- architect.py: the architect's Codex turn and durable transcript; its method is `resources/architect_method.md`, or a project's `zplan.architect.md`.
- architect_tools.py: the architect's tools as an MCP server.
- bridge.py: the local endpoint that hands the architect's tool calls to the live Controller.
- project_read.py: the architect's read tools over the project or one of its worktrees.
- project_state.py: the project's STATE file: plan, next step, open questions, decisions.
- application.py: the operations both frontends call: the owner's chat turn, the plan it shows, scrubbing.
- authority.py: the locked `planning.json` in store v3: plan revisions, approval, milestone runs, validation.
- planning.py: the planning service: plan check runs, approval, decline, base checks.
- autonomy.py: what the architect may do alone at each autonomy level.
- engine.py: the native graph adapter: the plan check, the old planner graph, the task gate's wiring, a deterministic fixture.
- task_gate.py: the task gate's pure core: artifact projection, identity, output parsing.

Runs, verification and merge:

- milestone.py: the milestone manifest, its amendment rules and the driver graph.
- runs.py: one native driver run per milestone attempt, and its record.
- live.py: an attempt's observation metadata, activity tail and credential scrubbing.
- feed.py: the persisted run event queue that wakes the architect.
- delivery.py: the milestone delivery service: start, verify, merge, report.
- checks.py: the project checks, run in a disposable checkout of the exact candidate.
- check_guard.py: the restart-safe supervisor around one check.
- export.py: a verified tree as a new local branch.
- snapshot.py: a tree's byte-level identity.
- merge_critic.py: the merge critic's trigger, record and run.
- user_commit.py: the owner's own uncommitted files, committed on his yes.
- process.py: the project's process profile (`zplan.process.json`: roles, gates, limits, rules, checks) and its acceptance.

Setup and the command line:

- cli.py: the subcommands (`status`, `doctor`, `setup`, `login`, `logout`, `update`, `profile`, `roles`, `exec`) and the line UI.
- commands.py: the subcommands' help text.
- setup.py: the pinned tools, login and doctor.
- toolchain.py: the one qualified toolchain of this release.
- update.py: `zplan update`.
- agent_profile.py: the agent profile in zplan's own Codex home.
- record_home.py: the Codex home a record acts in.
- catalog.py: every persisted status, owner-facing state, screen action and error family.

`tui/`, the full-screen UI (Textual stays here):

- tui/app.py: the shell and its main screen.
- tui/controller.py: the worker thread that owns the Authority session and runs every action.
- tui/start.py: the project picker.
- tui/screens.py: the plan screen and Settings.
- tui/modals.py: the modal screens: help, confirm, bootstrap, finishing, the note and text forms, the run end screen.
- tui/chat.py: the architect chat: one conversation per project, one turn per owner message.
- tui/chat_view.py: the chat pane's layout: header fields, rows, scroll window, state line.
- tui/chat_input.py: the chat input.
- tui/slash.py: the `/` commands of the chat input.
- tui/palette.py: the `/` command palette.
- tui/cards.py: the decision cards of the chat.
- tui/card_kinds.py: the decision cards' kinds: the shared card registries and the merge, question, plan, ready and failed card sources.
- tui/card_host.py: `CardHost`, the main screen's card methods: showing, closing and routing the cards.
- tui/activity.py: the journal pane and the key bar.
- tui/scheme.py: the drawing of a Zeroshot graph, fitted to any pane.
- tui/viewer.py: a project file or a diff as a read-only view.
- tui/strings.py: every string of the main screen, in Russian, English and Chinese.
- tui/text.py: the pure text helpers: terminal-cell fitting and eliding, the escape scan, the compact counters.
- tui/flow.py: the status wrapping and clipping helpers.
- tui/theme.py: whether the terminal is light, and the theme.
