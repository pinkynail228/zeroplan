# The architect writes the plan in its own shape; zplan derives the stored plan

Status: CANCELLED by roadmap revision 12 (2026-11-05): on a real project the format was not the bottleneck. Kept as a
record. Revision 2 (2026-11-05), after one Goldfish pass on revision 1 (`.local/goldfish/2026-11-05-plan-as-text/`:
comprehension, design_critic, zoom_out; section 7 resolves every finding). It is the step the A0 design plans when
the typed schema misses G4 (`docs/designs/2026-11-04-a0-architect.md` 3.5: "a lean shape normalized into the stored
one").

Terms:
- *Architect*: zplan's Codex session that talks to the owner and writes plans through the `zplan_plan` and
  `zplan_edit_plan` tools.
- *Stored plan*: the plan revision format (requirements; milestones holding slices holding tasks; a brief per task),
  validated by `authority.check_draft`.
- *Plan check*: the Goldfish review a saved revision gets (a reader retells it, a critic judges it).
- *Plan card*: what the owner approves.
- *Final check*: the milestone's `final_verify` node.
- *A0 rig*: `devtools/arch_eval/`. Its goals (A0 design section 2):
  - G1: an answer comes first;
  - G2: no unwanted plan;
  - G3: no plan turn without a saved plan;
  - G4: format refusals per plan-writing turn;
  - wrong approvals.

Evidence (private, gitignored):
- `.local/a0/plan-corpus/`: the model's first plan in 32 rig cases. Reproduce with the extraction script in
  `.local/a0/REPORT.md` section 9.
- `.local/a0/plan_text_proto.py`: the prototype.
- The rig runs `.local/a0/eval/p3-main2/` and `.local/a0/eval/p3d/`.

## 1. Problem, with evidence

- **The owner's cost.** A plan request took about 10 minutes before the format work (`REPORT.md` section 5). Today
  8 of 15 plan requests end with no plan at all (P3d), and the owner then has to ask again.
- **Patches did not converge.** Format refusals per plan-writing turn:

  | Variant | Refusals per turn |
  |---|---|
  | Baseline | 7.2 |
  | Typed schema | 6.3 |
  | A refusal naming every problem, plus a valid example | 2.8, cut by a cap of 3 |
  | Cap 6 | 5.1, a partial run with no explore turns |

  Missed plans went from 0 of 16 to 9 of 16 at cap 3 and 8 of 15 at cap 6.
- **The model does not write the stored shape.** In its first `zplan_plan` call it sends the plan as text in 32 of
  35 cases. The text is a brief with labels: goal, write-set, acceptance criteria (numbered, "situation -> expected
  result"), non-goals, implementation, done when. 29 of the 32 have one milestone and 3 have two.
- **Its second call, after the refusal, is lean JSON** in 30 of 35 cases: milestones with the brief fields at the
  milestone level (goal, write_set, criteria), with no slices and usually no requirements list. The stored shape
  wants requirements beside the milestones, and slices, then tasks, then a brief inside each milestone.

## 2. Goals and non-goals

Measured on the A0 rig, each scenario twice:

| Goal | Target |
|---|---|
| G4 format refusals per plan-writing turn | at most 1.0 |
| G3 plan turns without a saved plan | 0 |
| Wrong approvals | 0 (an absolute target; 2 of 4 on 19316e1 followed a missed plan) |
| G1, G2 | 18/18 and 0/14, as on 19316e1 |
| Time to a saved plan | the median plan turn under 3 minutes (about 10 before) |
| Fidelity | every milestone, dependency and criterion of the source reaches the stored plan, or the text is refused (section 3, tested on golden cases) |

Non-goals:
- changing the stored plan format, which keeps stored revisions replaying unchanged;
- the plan check's input;
- removing the slice level from the stored format;
- several tasks per milestone from text.

A JSON plan in the stored shape keeps several tasks.

## 3. Design

**One normalizer, three inputs.** `terminal_planner/plan_text.py` turns any of them into the stored plan, then
`check_draft` validates it as today:
- a stored-shape object, or its JSON text, passes through unchanged;
- a lean object (JSON): milestones carrying the brief's fields at the milestone level (slice PT1c, built only on
  evidence: section 6);
- a labelled text, parsed into that same lean form.

**The lean form**, which is also what the text parses into. A list of milestones, each with:
- `id` (optional) and `title`;
- `depends_on` (milestone ids);
- `goal`, `why` (optional), `approach` (optional), `write_set`;
- `criteria`, 1-5 items, each a text with an optional example;
- `non_goals` (optional), `risk` (optional);
- `done_when`, `checks` (optional).

**Text: finding the milestones.**
- A milestone starts at a heading or line of the form `M<n> <title>`, `Milestone <name>`, `Веха <name>` or
  `Этап <name>`, at line start, with or without `#` (the corpus writes `Milestone stats` without either).
- One such line, or none, makes one milestone.
- A second goal, write-set or acceptance-criteria label inside one milestone refuses ("milestone M1: write set:
  given twice; start each milestone with a line `M<n> <title>`"), so milestones the grammar misses are never
  folded. Done-when and non-goals may repeat (`Проверка:` and `Готово:`; `Non-goals:` and `Later`); their texts join.
- Ids: `M<n>` as written, else `M1`, `M2` in order.
- Titles, in order of preference:
  1. the heading's rest;
  2. the first heading of the text;
  3. the first line's rest after "One milestone:" or its aliases;
  4. otherwise a refusal.

  The single task takes the milestone's title.

**Text: labels.**
- A label is a line `<label>: <value>` or a heading `<label>`, matched against the alias table ignoring case,
  bullets, bold, a parenthetical suffix (`Критерии приёмки (5):`) and spaces around `/` (`Проверки/DoD`).
- The alias table lives in one place, the module, and its contract test pins every alias the corpus uses. `Later`
  and `Позже` are non-goals: deferred work is not this plan's. The Cyrillic aliases are input words, like
  `setup.YES_ANSWERS`, so they live in `INPUT_*` constants, which the English-only test exempts.
- Where a section ends:
  - at a heading, or at a line of a known label, always;
  - in a section opened by a `<label>: <value>` line, also at an unknown label (a line, not a list item, whose
    text before its first `:` is at most 40 characters and holds no backtick: `Интерфейс фиксирован: ...`) and at a
    blank line followed by a line that is not a list item;
  - in a section opened by a heading, nowhere else (`Тесты на временном SHELF_HOME: ...` under a `Validation / DoD`
    heading stays done-when), except that in a list section (write set, criteria, non-goals) the first paragraph
    after its list ends it.
- Text that is not under a known label (an unknown label's section, a paragraph that ended a section) goes, with
  its label, into `approach`. A plan's preamble, before its first milestone, goes into every milestone's
  `approach`, because it holds plan-wide decisions. Nothing is dropped.
- `depends_on` comes from the earlier milestones a dependency label names (Depends on, Dependencies, Зависимости,
  Зависимость, Зависит от), by id or by the name of a `Milestone <name>` line. A later milestone named there ("до
  начала M2") adds the inverse edge: that milestone depends on this one. The label's whole text also goes into
  `approach`.
- Milestones whose write sets share a path also run in the text's order: the later depends on the earlier, because
  they cannot run in parallel anyway.
- Otherwise a milestone depends on nothing. An order stated only in free text between milestones with disjoint
  write sets is not derived; the derived summary in the tool result shows the architect the edges.

**Text: the write set.**
- Items are its list lines, else the comma- or semicolon-separated parts of its value. A one-line value ends at its
  first sentence end (`.` followed by a space); the rest goes into `approach`.
- An item's first token, stripped of quotes, backticks and trailing punctuation, is the path. The rest of the item
  (a note such as "(new)") goes into `approach` with its path.
- A path holds ASCII letters, digits and `_ . / - +`, does not start with `-` and has no `..` part. An item whose
  first token is not a path is refused. Files without an extension (`Makefile`) are kept.

**Text: limits and refusals.**
- More than 5 criteria, more than 32 write-set paths or more than 16 non-goals refuse; nothing is cut.
- A labelled text over 64 KB refuses before parsing. The stored-shape pass-through comes first, so a stored-shape
  JSON text keeps `check_draft`'s own size limit.
- Risk accepts low, medium, high, низкий, средний and высокий; the default is medium; another value refuses.

**What the stored plan gets.**
- Per milestone: one requirement `R-<id>` (text: the goal), one slice `S-<id>` and one task `<id>-T1`, all titled
  with the milestone's title.
- The brief:
  - goal, write_set and non_goals;
  - criteria `C1`..`C5`: the text before `->`, `→`, `=>`, `Example:` or `Пример:`, and the text after it as the
    example; an item without a separator uses itself as its example, and the owner's view prints it once;
  - risk;
  - dod: the done-when text;
  - why: the why text, else the plan's goal;
  - reuse: the approach text. The brief's "reuse" field holds "the existing code and the approach" from now on,
    and the worker's contract reads it as written.
- **The task's checks are the criteria's texts, then the backticked commands of done-when; more than 32 refuse.** The reviews reject on
  a failed check and the final check verifies every check (`milestone.py:31`, `:412`), so every criterion the owner
  approved binds them.

**Refusals.** A text that cannot be normalized gets one `FormatRefused`:
- it starts "Invalid proposal (plan text):", so the rig counts it;
- it names each problem by milestone and label;
- it ends with the text template filled in for a small example.

A `check_draft` refusal of a normalized text plan is restated the same way: stored ids are mapped back to the
milestone, and it ends with the template, not the JSON example.

**Tool results.** A saved plan's result carries a compact summary of what was derived: per milestone the id,
title, dependencies, criteria count and write set. The architect, who holds the source, sees at once if something
was misread.

**Edits.** `zplan_edit_plan` takes the same three inputs. The goal comes from the current revision. A text or lean
edit of a revision that holds more tasks than milestones is refused ("edit this plan as JSON"), so tasks are never
collapsed. Ids are derived the same way, and criteria keep their order.

**The Controller.** `_plan_argument` routes `plan` to the normalizer. `FORMAT_REFUSALS` stays at 6 as a bound, and
the rig says whether it is ever reached.

**The tools.** `plan` is declared as a string described by the text template and one filled example. The lean and
stored objects are accepted without being declared. `PLAN_SCHEMA`, `PLAN_FORMAT` and the JSON `PLAN_EXAMPLE` leave
the descriptions, so the prompt gets shorter. The schema agreement test (`tests/test_architect_tools.py:339-381`)
changes with them.

**Prototype evidence.** On the 32 corpus texts, the revision 1 prototype gave 30 stored plans `check_draft`
accepts, and 2 lacked one alias. Review showed that its 3 multi-milestone results are wrong, so this revision
replaces shape with fidelity as the oracle.

## 4. Alternatives

| Alternative | Verdict |
|---|---|
| More patches to the stored-shape path | Rejected: four tried (section 1) |
| Lean JSON only | Rejected as the only input: the first call is text in 32 of 35 cases. Kept as a possible second input (PT1c): it is the second call's shape in 30 of 35, but those calls answered refusals that taught JSON |
| Text only | Rejected: a retry after a text refusal is lean JSON |
| A model call that turns text into JSON | Rejected: another nondeterministic step, at a model's cost |
| One tool call per milestone or task | Rejected: more calls, partial plans in the store |
| No cap (`FORMAT_REFUSALS` removed) | Kept as a bound at 6: with first calls accepted the cap should never bind, and the rig measures that |
| Store the source text on the revision and give it to the reader | Deferred: it changes the stored format; the derived summary in the tool result gives the architect the same comparison now |

## 5. Risks

- **Fidelity.** The parse could misread or merge milestones. Guards:
  - refusals instead of folding;
  - golden cases in PT1: the three multi-milestone corpus plans (milestones, dependency edges, every criterion) and
    four single-milestone ones (title, write set, criteria);
  - the derived summary in the tool result;
  - the owner's `[i]` view of criteria, non-goals and dependencies.
- **A narrow corpus.** It is 9 scenarios on one small fixture. The live run on a copy of PenPot after PT2 is the
  held-out test, and the grammar grows only from its evidence.
- **One task per milestone from text.** It means more runs and merge gates than a milestone of many tasks. Accepted
  for text; JSON keeps several tasks.
- **Security.** Checks now come from criteria texts and backticked commands. They are read by model reviewers, not
  executed by zplan. The deterministic project checks of the profile are unchanged and still gate merge. Text is
  bounded before parsing.
- **Prompt and cost.** The descriptions shrink. Each rig run costs about 72 minutes for the full run, or about 40
  for the plan scenarios, plus a few million tokens.

## 6. Slices

| Slice | Result | Acceptance |
|---|---|---|
| PT1 | `plan_text.py`: the text grammar into the stored plan (and a stored-shape object passing through), refusals with the template | all 32 corpus texts normalize with their goals and non-goals; the golden cases match; refusals instead of cuts or folds; `tests/test_plan_text.py`, the grammar's contract test on its own small texts: `M<n>` headings; `Milestone <name>` lines with a dependency by name; a backward dependency by id and by name between milestones with disjoint write sets; a forward mention as the inverse edge; a shared path as an order; repeated done-when and non-goals joined; more than 32 checks refused; a repeated label refused; an unknown label ending a `label: value` section; a write-set sentence and note kept; every alias the corpus uses reaching its field; risk mapped and refused; one refusal per limit; the template; a stored object passing through |
| PT1c | only if PT2's rig shows lean JSON retries after text refusals: the lean JSON input through the same alias table (`brief` as text or object, `tasks` inside a milestone) | the second-call shapes of the rig normalize |
| PT1b | Controller wiring: `_plan_argument` for plan and edit, the edit rules, the derived summary in the result, `check_draft` refusals restated | behaviour tests through the bridge |
| PT2 | the tool descriptions and the rules (the template, one example; the JSON shapes accepted, not declared); the owner's view prints an example equal to its criterion once | the A0 rig: the goals of section 2 |

**Stop rule.** The format work ends with PT2's rig, whatever its numbers. If the goals of section 2 are missed,
the live run on the PenPot copy still goes next, and the format's next change comes from its evidence, not from
another rig loop.

## 7. Resolution of the Goldfish findings (revision 1)

Reviewers: D design_critic, Z zoom_out, C comprehension.

| Finding | Resolution |
|---|---|
| Multi-milestone plans are misread silently; the oracle tests shape, not fidelity (D B1, Z B1, C B1) | Accepted: milestone lines without `#` or `M<n>`, dependencies parsed from names, refusals instead of cuts, no dropped text, golden fidelity cases |
| Criteria do not bind the reviews when checks are commands only (D B2) | Accepted: the task's checks are the criteria, then the commands |
| The rig may not count the new refusals; fidelity and event turns unmeasured; no delivery run (D 3) | Accepted: a fixed refusal prefix the rig counts; a fidelity goal; the PenPot live run delivers. Event-turn edits stay unscored (a rig change for later) |
| Titles are unspecified (D 4) | Accepted: the title rule |
| The edit path is undesigned (D 5, Z 8, C 5) | Accepted: section 3, Edits |
| The single-task claim rests on a narrow corpus (D 6, Z 7) | Accepted: stated as a risk; the PenPot run holds it out |
| Refusals after parsing teach JSON; the cap, the prompt and the schema test are unstated (D 7, Z 9, Z 10, C 6, C 7, C 9, C 19) | Accepted: restated refusals; the cap kept as a bound; the JSON descriptions leave; the agreement test changes |
| Lean JSON rejected without measuring it (D 8, Z 3, C 10) | Accepted, measured: the second call is lean JSON in 30 of 35, after refusals that taught JSON; PT1c takes it if the rig after PT2 still shows it |
| The prototype's grammar differs from the document; no held-out data (D 9, Z 6, C 3) | Accepted: the alias table lives in the module only; the PenPot run is the held-out test |
| Security, limits and cost missing; paths without extensions (D 10, C 8, C 13) | Accepted: section 5; the path and size rules |
| The owner's cost and the no-cap alternative (Z 4) | Accepted: the time goal; the no-cap row |
| The wrong-approvals baseline (D 11, Z 5, C 2) | Accepted: an absolute target of 0 |
| `depends on` without evidence (C 4) | Accepted: the dependency labels and "after M1" from the corpus |
| `reuse` changes meaning silently (C 11, D 13) | Accepted: stated |
| Not self-contained (C 12) | Accepted: Terms; the evidence paths and how to reproduce |
| The PT1 contract review (after revision 2): section ends, the write set's sentences and notes, Russian aliases against the English-only test | Fixed: Text: labels and Text: the write set; `INPUT_*` |
| Nits: counts (29 and 3; labels in 32 of 32), "every patch reduced", the duplicated example, Russian risk values, `=>` | Fixed in the text |
