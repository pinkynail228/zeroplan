# p2b — the profile screen and the docs say what the merge gate and the levels now mean

After p2a the merge gate decides only whether checks (and the critic) run before a merge; who merges follows the
level: auto merges after the reviews, supervised merges unless the change is high risk, manual asks. Texts that
still promise the old rule:
- tui/modals.py `MERGES` (`required` "automatic on green checks", `off` "you merge, no check") and `NO_CHECKS`
  ("... merging automatically on green checks is unavailable");
- process.py `LEVEL_NAMES["supervised"]` "ask about the plan";
- README.md:30-31 ("ends as a branch that you merge"), :55 (diagram: merged by zplan "when the profile has a merge
  check"), :104-106 (warning: "a project with no test check waits for your /merge"; supervised "approve plans and
  merges yourself");
- docs/INSTALLATION.md:37-40 ("supervised asks for ... every merge"; "Merges stay yours unless ... required at level
  auto").

Write-set: terminal_planner/tui/modals.py, terminal_planner/process.py, tests/test_tui_profile_choice.py, README.md,
docs/INSTALLATION.md, docs/USER_FLOW.md

Acceptance criteria:
- A1 The profile screen names what the gate does. Example: configure -> merge row buttons read "checks before
  merging" and "no check before merging"; without checks only the second, with the reason "There are no checks, so
  the merge check is unavailable."; supervised reads "ask about the plan and risky merges".
- A2 README and INSTALLATION state the matrix. Example: the README warning says that at `auto` zplan merges each
  milestone after its reviews pass, and without a test check it merges without one and says so; `supervised` asks
  for plans and high-risk merges; `manual` for everything. No live doc says "waits for your /merge" for auto.
- A3 USER_FLOW.md's profile and merge sections match A1/A2. Example: its "merge" rule row names the two new labels.

Non-goals (reviewers must not require): the scheme's "(your ok)" line, the merge card, catalog texts, other
languages' strings, product docs under docs/product/, ARCHITECT_DESIGN.md (a dated design).

Conflict rule: if a test outside the write-set pins a changed label, change nothing in it and end with
`conflict: <file:line>`.

Risk: low (labels and docs). DoD: `python3.13 devtools/fasttest.py tests.test_tui_profile_choice tests.test_process
tests.test_docs`: exit 0.
