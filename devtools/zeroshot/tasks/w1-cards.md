W1 — chat card widget (0.5.2, docs/RELEASE_0.5.2_PLAN.md, run w1). New module only; nothing wires it into the app yet.

Why: the main-path decisions (goal draft -> plan, approve plan, merge, owner question, error) become cards in the chat
(docs/ui-redesign/WORK_SCREEN.md, GLOSSARY.md). The approved look is the lab: `devtools/ui-lab/work.py` `_card` and
the `.card*` rules in `devtools/ui-lab/work.tcss` (walk all states with ctrl+t: draft, approve, merge, question, error).

Build `terminal_planner/tui/cards.py`:
- `CardSpec` (frozen dataclass): `key` (opaque identity of the decision the card stands for, e.g. a draft id or an
  end token; set by the caller, never shown), `title`, `text`, `buttons` (tuple of (label, command line) pairs, command lines are
  slash commands such as "/approve"), `hint` (None = "or " + the commands joined by " · ", from strings id `card.hint`),
  `at` (time string shown as the border subtitle), `done` (None, or the closed-card line), `alarm` (bool).
- `Card(Vertical)` widget built from a spec: border title = title, subtitle = at; an open card shows text, one row of
  compact buttons and the dim hint; a done card shows only the green done line and no buttons; `alarm` adds the red
  style. A button press posts `Card.Chosen(command, card)` (a Textual Message carrying the command line and the `Card`
  itself, so the receiver reads `card.spec.key`) and nothing else.
- Builders returning a `CardSpec`, texts through `strings.text(id, **values)` with exactly these existing ids and
  values (terminal_planner/tui/strings.py is frozen: do not add or change ids):
  `draft_card(key, at)`: title `card.draft_title`, text `card.draft_text`, buttons `card.plan_yes` -> "/plan",
  `card.no` -> "/decline"; `plan_card(key, at, stages, tasks)`: title `card.plan_title(stages=, tasks=)` (the caller
  passes ready words such as "3 этапа"), text `card.plan_text`, buttons `card.approve_yes` -> "/approve",
  `card.revise` -> "/decline"; `merge_card(key, at, stage, done, total)`: title `card.merge_title(stage=)`, text
  `card.merge_text(done=, total=)`, buttons `card.merge_yes` -> "/merge", `card.merge_changes` -> "/diff";
  `question_card(key, at, task, text, buttons)`: title `card.question_title(task=)`, text and buttons from the caller,
  hint `card.question_hint`; `error_card(key, at, task, text, buttons, fix=None)`: title `card.error_title(task=)`,
  alarm, text and buttons from the caller (`card.error_text` is a lab sample, not used), `fix` = an exact shell
  command shown verbatim on its own line (the no-origin case); `closed(spec, done_text)` returns the spec as a done
  card (callers use `card.draft_sent(time=)` / `card.plan_done(time=)`). Default hint: `card.hint(commands=...)` with
  the button commands joined by " · ".
- CSS for the card in a `DEFAULT_CSS` on the widget (so the app needs no tcss edit later), matching the lab's look.

Write-set: terminal_planner/tui/cards.py, tests/test_tui_cards.py. Do not edit any other file.

Acceptance criteria:
- A1 Each builder's spec uses the `strings.text` result for its ids and values (test compares with `strings.text`).
- A2 An open card mounted in a minimal test App at 80 and 120 columns shows title, text, every button label and the
  hint; no button row is wider than the card.
- A3 Clicking a button (Pilot) posts exactly one `Card.Chosen` with that button's command line and the card whose
  `spec.key` is the one the builder got.
- A4 A done card shows the done line, no buttons, and posts nothing on click.
- A5 `error_card(..., fix="git remote add origin URL")` shows the fix command verbatim on its own line.
- A6 Tests run without a project, controller or network.

Non-goals: wiring into app.py, which controller action a command calls, chat ordering, new string ids, translations.

DoD: `python3.13 -m unittest tests.test_tui_cards tests.test_tui_strings tests.test_toolchain tests.test_reference` with TMPDIR short (preamble), all green.
