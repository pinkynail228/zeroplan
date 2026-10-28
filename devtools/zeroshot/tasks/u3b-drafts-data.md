u3b-drafts-data — architect drafts as data: protocol, parser, turn identity, persistence (docs/TUI_PLAN.md U3b, second half; decisions TUI_PLAN.md:46-48, :111-112). Split of the critic-gated u3b-drafts into three tasks at stable contracts (critic 01a14a11 task size; owner 2026-10-17): u3b-drafts-data (this data contract) -> u3b-drafts-goal -> u3b-drafts-answer, each run after the previous merges. Builds on u3b-chat (read its result in the code first). DeepSeek worker, sol high reviewers. Read AGENTS.md, docs/TUI_PLAN.md, docs/USER_FLOW.md, terminal_planner/architect.py (build_preamble/build_update, `_state_section`, ArchitectStore and `transcript`, `_turn`/`_conclude`, `_Turn.finish`), terminal_planner/tui/chat.py (ChatEntry, ChatState, `entries_of`, ArchitectChat `send`/`_turn`/`_apply`, `entry_lines`), terminal_planner/tui/app.py (`chat_snapshot`, `send_chat`, the chat pane), terminal_planner/tui/controller.py (Snapshot), terminal_planner/delivery.py (`Token`, `Row.token`), tests/test_architect.py and the u3b-chat tests.

Today the chat (u3b-chat) shows architect replies as text only. A proposed goal or answer has to be retyped by the owner. This task makes drafts exist as data and shows them; it adds no draft key and no UI action (u3b-drafts-goal and u3b-drafts-answer do).

Contract this task delivers for the next two: each chat entry of a successful architect turn carries a list of drafts; a draft has kind (goal / answer), text, milestone id (answer), the turn identity (below), and `actionable` (identity and success mark present). Document it in the code where ChatEntry is defined; the goal and answer tasks build only on it.

Build:
- Draft format. The preamble and every resumed-turn update (`build_update`, sent instead of the preamble when a saved `thread_id` exists) tell the architect to put a proposed goal in a fenced block ```zplan-goal``` and a proposed milestone answer in ```zplan-answer <milestone id>```. A pure parser in architect.py, with no lifecycle imports, extracts drafts from the final reply of a successfully completed turn only (never from streamed partial text, never from a cancelled or failed turn), with bounded size and count. Malformed or oversized blocks stay plain text and are never a draft.
- Identity (provenance). Each draft carries the identity of the state the turn was sent with, taken from the snapshot of that turn:
  - an answer draft carries the original `Token` of its milestone's attempt from that snapshot; several answer drafts each carry their own;
  - an unknown milestone, or a missing identity, gives no actionable draft (text only);
  - a goal draft carries the plan identity of that snapshot: "no plan" or (revision, state), where state covers changes inside a revision (submitted, plan ready, approved, override). Comparing the revision number alone is not enough.
  Today `chat_snapshot()` passes only project/branch, the summary text and milestone id/title/state; extend this projection with the revision, plan state and attempt tokens from the controller `Snapshot`, taken at send time, and keep it fixed for that turn (a later refresh never changes it).
  Define this identity exactly and state it in USER_FLOW.
- Persistence. u3b-chat rebuilds the transcript after a restart and reloads it between windows. A reply's drafts are actionable after reload only if their identity and the turn's success mark were persisted with the reply (in ArchitectStore, outside the checkout). Without that metadata they are copyable text. Old text is never bound to the current snapshot.
- Format and limits (the single definition):
  - a draft opens with a line that is exactly "```zplan-goal" or "```zplan-answer <milestone id>" (no indentation) and closes with the next line that is exactly "```";
  - a zplan fence inside another fenced block (one opened with ``` and any other info string) is quoted text, not a draft;
  - an unclosed fence, an empty body, or a body over 4000 characters is plain text;
  - at most 5 drafts per reply; from the 6th on they stay plain text;
  - the answer milestone id must be a milestone of the turn's snapshot.
- Identity, exact: plan identity = "no plan" or (revision number, plan state as the controller Snapshot names it); answer identity = the `Token` of that milestone's attempt in the turn's snapshot. Both are stored as plain data with the reply.
- Deterministic tests: the scripted architect fixture; the test controls turn completion with an explicit synchronisation point (send -> a refresh that changes the snapshot -> release completion), then asserts.
- Display. A reply with drafts shows each draft as a distinct, labelled item (kind, milestone for an answer); no key yet, the text stays copyable.
- Rules kept: the architect is advisory and never writes proposal/approval/run state. One turn per owner message, zero inference on refresh. The u3b-chat quit/cancel/lock behaviour is unchanged.
- README/USER_FLOW describe drafts only as far as shipped (shown, not yet actionable).

Acceptance criteria:
- D-0 A resumed session (saved `thread_id`, so `build_update` not `build_preamble`) gets the draft instructions: a test checks the prompt sent; no session reset is needed. An integration test shows the turn receives the identity of the state at send time and a later refresh does not change it.
- D-1 The parser is unit-tested on: one and several drafts; a goal and an answer in one reply; an unknown milestone id (not actionable); an unclosed fence; an oversized block; a block in streamed or cancelled text (not a draft); a fence inside a quoted code block (not a draft); boundary values: 0, 1, 5 and 6 drafts; body empty, 4000 and 4001 characters. architect.py still has no lifecycle imports (tests/test_architect.py import check).
- D-5 Restart/reload: drafts persisted with identity and success mark come back after an app restart and in a second window with their original identity and `actionable` true; records without that metadata come back with `actionable` false (text only).
- D-6 Receiving a reply with drafts writes nothing to Authority (spy plus store bytes) and calls no export/finish.
- D-7 u3b-chat tests stay green untouched; plain mode unchanged (chat TUI-only).
- D-8 Targeted modules green: test_architect, the TUI chat/app tests, test_reference if the catalog changes. The full suites (both), the PTY walkthrough and a real-provider chat check on a clone are the orchestrator's merge gate.

Out of scope: draft keys, the goal form and the answer modal (next tasks); the gate discussion in the context (u3b-context); plain-mode chat; drafts for task/merge gates (G2/G3 are 0.5); the architect editing files; real-provider calls in tests.
Size: estimated 450-600 added lines with tests; kept as one task because the identity and the persistence are one contract stored with the reply (splitting them would ship a reply format that changes again).
Premise: refs re-checked on main b6bdd16 after u3b-chat merged (2026-10-18).
critic u3b-drafts (session 01a1488f-9b3c-7be3-ae32-cdf3505d4b6b, effort high): CHANGE (identity/stale rule, open->send gap, no-export refusal, persistence, focus, gate context, split) -> applied, gate context split into u3b-context; re-gate both after u3b-chat merges.
critic u3b-drafts re-gate (same session, refs on zs-u3b-chat e9fd646): CHANGE (draft protocol in build_update, focus = plan pane, extend chat_snapshot identity + refs) -> applied (+ start_planning ref moved to controller) -> GO
critic u3b-drafts: split into data / goal / answer (task-size rule 45d64a5) -> CHANGE (limits, identity, keys, sync, no export) -> applied -> GO (session 01a1488f).
critic u3b-drafts re-gate on main b6bdd16 (same session, post u3b-chat merge, effort high): GO unchanged (2026-10-18).
critic u3b-drafts merge (same session, xhigh): GO on merge tree 497ee30 (D-0..D-8 met; live answer drafts not required, deterministic coverage; UX notes -> u3b-drafts-goal re-gate) (2026-10-18).
