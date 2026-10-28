u3b-drafts-answer-fix — close the two P2 findings of the u3b-drafts-answer merge critic (BLOCK, session 01a1488f). Run u3b-drafts-answer (01a14f6e) succeeded; its candidate 4bc8889 passed Linux 846 OK, the mutation check, the PTY walkthrough and the installed mixed check (D-8). Runs on the existing worktree /tmp/zs-zplan/u3b-drafts-answer (branch zs-u3b-drafts-answer, HEAD 4bc8889, base main 4cc80bc). u3b-drafts-answer.md still applies unchanged. Reviewers review the whole diff 4cc80bc..HEAD. DeepSeek worker, sol reviewers. Read terminal_planner/tui/controller.py (`token_identity`, `open_answer_draft`, `answer_draft`), terminal_planner/tui/app.py (`action_open_answer_draft`, `send_answer_draft`), terminal_planner/tui/chat.py (`newest_answer_draft`), terminal_planner/delivery.py (`view`, `END_ACTIONS`, `run_state`), terminal_planner/runs.py:1269 and tests/test_tui_chat.py `AnswerDraftTests`.

Findings:
- F-1 The draft's milestone and its identity are not checked against each other. `chat.newest_answer_draft` picks a draft by `draft.milestone`, but the controller receives only `draft.identity`; a retained draft with `milestone=M1` and a well-formed token of M2 opens (and sends to) M2 while M1 is selected.
- F-2 A finished but unexported attempt (`done`, result not exported) is refused through `Delivery.view` -> `runs.diff` ("Результат ещё не экспортирован.", family `action.refused`) rather than through the declared `draft.unavailable` contract (catalog.py:462, REFERENCE.md:347/532); tests/test_tui_chat.py:3308 pins that bypass.

Rules:
- R-1 Open and send both receive the draft's milestone with its identity. On the worker, after the token is rebuilt and before `resolve`, a token whose `milestone` differs from the draft's milestone is refused as `draft.malformed` (same refusal as any other malformed identity): no resolve, no view, no answer, no write, no export.
- R-2 At open, after `resolve(exact=True)` and the existing active check, decide whether the resolved attempt's end offers `answer` from its state alone (the same `END_ACTIONS` table `Delivery.view` uses), before any view is built. If it does not, refuse as `draft.unavailable` with the existing ANSWER_DRAFT_UNAVAILABLE text; `Delivery.view` is called only for a state that offers `answer`. The post-view `"answer" in view.names` check stays as a guard. No other refusal path, wording or family changes; the typed answer, `[o]` and the goal draft are untouched.
- R-3 Docs/catalog change only if their text no longer matches; no new catalog family.

Acceptance criteria:
- A-1 F-1 regression: a retained draft with `milestone=M1` and a valid M2 token, with M1 selected: `t` shows the `draft.malformed` refusal and opens nothing; a send with such a draft (drive the form's send callback directly with the draft) is refused with `draft.malformed` and creates no attempt. Store bytes, `export.create_branch`, `MilestoneRuns.finish` and `Authority.save` spies are unchanged/not called, before and after the UI callback.
- A-2 F-2: the test at tests/test_tui_chat.py:3308 (a done, unexported attempt) asserts the `draft.unavailable` refusal (`ANSWER_DRAFT_UNAVAILABLE % "M1"`, `[код: draft.unavailable]`) and keeps every no-write/no-export spy; additionally assert `Delivery.view` is not called (spy) for that state.
- A-3 Each new or changed assertion fails on 4bc8889 (state the command and the failing assertion) and passes after the fix.
- A-4 All existing AnswerDraftTests, DraftChoiceTests and GoalDraftTests stay green; tests/test_reference.py green.

Size: ~60-150 lines with tests.

Out of scope: everything else, including the macOS PTY timeout in test_terminal_planner (handled by the orchestrator gate).
critic u3b-drafts-answer merge: BLOCK (mac error unclassified; P2 milestone/identity mismatch; P2 unexported done bypasses draft.unavailable) -> this repair task -> task review GO (session 01a1488f).
