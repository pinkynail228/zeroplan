A11 — the architect starts with the shipped method (preset zplan.default)

Owner: the delivery method the orchestrator follows ships as zplan's default architect method; settings that
tune it come in later releases. The text exists: terminal_planner/resources/architect_method.md (do not edit it).
Today the first-turn prompt (architect.py `build_preamble` :266) calls the architect "advisory" and carries no method.

Reuse: `agent_profile.py:48` (packaged bytes through `importlib.resources`); pyproject.toml package-data :20;
the wheel test tests/test_install.py:372.

Write-set: terminal_planner/architect.py, pyproject.toml, tests/test_architect.py, tests/test_install.py.

Acceptance criteria:
- C1 The first turn of a conversation carries the whole method text, read from the packaged resource, after the
  role lines and before the tool list; a resumed turn (`build_update`) does not repeat it.
  Example: a new conversation -> the first prompt contains "## Brief" and "At most 5 acceptance criteria"; the
  second prompt of the same thread contains neither.
- C2 The role line says the architect leads delivery for the owner within the autonomy level the Controller
  enforces; "advisory" is gone. The files rule and the tool list (:72) admit the one write that exists: the
  project STATE file through zplan_state_update (architect_tools.py:51-58, both state tools listed); other
  draft and tool rules stay. Example: first prompt contains "lead delivery" and "zplan_state_update", not
  "advisory" nor "There are no file-writing tools".
- C3 The wheel ships the method: package-data includes resources/*.md, and `build_preamble` imported from the
  built wheel outside the checkout contains the method. Example: the wheel member set includes
  terminal_planner/resources/architect_method.md.
- C4 The shipped method stays a generic preset: at most 4096 bytes, no date, no path under devtools/.
  Example: a line "since 2026-10-25" added to the method -> the test fails.

Tests: assertions of the old "advisory" wording are replaced by C2's, not duplicated.

Non-goals (reviewers must not require): a project override of the method, settings or profile keys for it
(later releases); editing the method text; the module docstring history; tests/test_tui_chat.py docstrings;
README or USER_FLOW wording.

Risk: high (packaging). DoD: `python3.13 devtools/fasttest.py tests.test_architect tests.test_install
tests.test_toolchain`, exit 0; quote `fasttest:` lines.
