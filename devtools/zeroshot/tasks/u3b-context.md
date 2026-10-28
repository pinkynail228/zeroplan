u3b-context — the plan gate's discussion in the architect's context (docs/TUI_PLAN.md U3b "shows gate discussions", :111; docs/PROCESS_PROFILE.md "Gate discussion" and "Gate record"). Builds on u3b-chat. Split from u3b-drafts (critic u3b-drafts). DeepSeek worker, sol high reviewers. Read AGENTS.md, docs/PROCESS_PROFILE.md, terminal_planner/authority.py (plan gate result: critic verdict, discussion, override; `completed_review` old format ~:680), terminal_planner/tui/controller.py (Snapshot building on the worker), terminal_planner/architect.py (build_preamble/build_update, `_state_section`), the u3b-chat chat wiring, tests/test_architect.py.

Today the architect's state snapshot has no plan gate evidence, so the owner cannot discuss the critic's findings with it.

Build:
- The controller worker projects, for the current plan revision only, read-only gate evidence into the immutable UI Snapshot:
  - the critic verdict;
  - the override, if any, shown next to the verdict and never replacing it;
  - a bounded discussion `[{round, findings, response}]`, capped by round count and chars per field and in total.
- The chat builds the architect snapshot from the UI Snapshot only; the chat thread never reads Authority. `build_preamble` and `build_update` render this evidence, marked "read-only evidence, may be stale".
- Old-format results: the verdict stays when it is available and the discussion is absent (stated as "нет обсуждения"). Missing results mean no gate section.
- A revision change never carries the old revision's discussion into the new context.
- Rules kept: zero inference on refresh; the architect never writes state; u3b-chat behaviour unchanged.

Acceptance criteria:
- X-1 An end-to-end test: Authority fixture with a gate discussion -> controller Snapshot (built on the worker thread) -> chat snapshot -> `build_preamble`/`build_update` text. It asserts the content and that no Authority read happens on the chat thread. Injecting a ready dict into the builder does not pass.
- X-2 Caps: count, per-field and total limits are tested; an oversized discussion is truncated with a marker.
- X-3 A rejected verdict with an override shows both, and the verdict stays "rejected".
- X-4 Old-format result: verdict kept, discussion "нет обсуждения".
- X-5 Revision change: after a new revision, the update carries no old discussion.
- X-6 Each X test fails when its part is removed (say how you checked).
- X-7 Targeted modules green: test_architect, the TUI chat/controller tests, tests touching the Snapshot. u3b-chat tests untouched. The full suites are the orchestrator's merge gate.
- X-8 Diff: architect.py (render only, no lifecycle imports), tui/controller.py and tui/app.py (projection and wiring), authority.py only for a read helper, tests/.

Out of scope: task/merge gate evidence (G2/G3, 0.5); drafts (u3b-drafts-data, -goal, -answer).
critic u3b-drafts (session 01a1488f-9b3c-7be3-ae32-cdf3505d4b6b): split out on its CHANGE 7; to be gated after u3b-chat merges.
