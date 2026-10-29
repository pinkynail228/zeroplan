"""U1 — the scheme renderer `terminal_planner/tui/scheme.py` (port of `devtools/ui-lab/flowdraw.py`): A1-A5;
U1b — the stage graph's loops and its optional branch in the owner's words (A1-A4).

The tests read the plain text of the result (`.plain`), never styles, except A5, which is the one style check (a
failed reviewer and a failed worker must not look the same). Only `render`, `legend` and `observation_from_flow`
are used; the graphs are the two the task names, built from `milestone.milestone_graph(3)` and
`engine.planner_graph_v2(3)` (the same shapes as `devtools/ui-lab/fixtures/*.json`).

Interpretations recorded here (the worker's final summary is not shown to reviewers):
- The word table is keyed by GLOSSARY ids in the `role.*`, `state.*`, `flow.*` namespaces. The GLOSSARY gives no id
  for a loop group's own name (only `flow.loop_group`, the count phrase), so a loop with an unmapped name keeps
  A3's name fallback: its visible title is the node name with `_` -> space ("review loop"), unless the observation
  carries a `title`. A loop of the stage graph has a mapped name, so it is drawn from its own id (`flow.task_loop`,
  `flow.review_loop`, `flow.repair_loop`; U1b) and an observation `title` still wins. For the same reason the
  running word is the GLOSSARY `state.running` "идёт"; flowdraw's lab word "работает" is not in the GLOSSARY. Only
  words change: layout, marks, colours and the three fitting modes are flowdraw's.
- `flow.loop_group` is one GLOSSARY row that documents both a counted form and an open form
  ("{name} · {n} из {max} / до {max} раз"). No second id is invented for the open form: the renderer requests only
  `flow.loop_group`, picks the form the observation allows (a `count` is known or not) and fills its `{name}`/`{n}`/
  `{max}` placeholders, so a `words` callable built from GLOSSARY values works (see `test_a3_glossary_derived_callable`).
- `flow.optional` is the `?`/`┆` header of a conditional branch only; it is filled with the branch name (the
  GLOSSARY template is "если нужно: {name}"), so no `{name}` is left unformatted. A step inside that branch that has
  not run says `state.if_needed` "если нужно" alone, without the branch name (U1b A2): the header names the branch
  once, the branch name is not repeated on every step, as the approved lab `_leaf` does.
- U1b maps the stage graph's own loops and optional branch to their GLOSSARY ids: node `task_loop` -> `flow.task_loop`
  "задачи по очереди", `review_loop` -> `flow.review_loop` "раунды ревью", `repair_loop` -> `flow.repair_loop`
  "раунды доработки", `final_repair` -> `flow.final_repair` "доработка после итоговой проверки". These ids name the
  node, not the count phrase (`flow.loop_group` still carries the round), so the approved lines read
  "↻ задачи по очереди · 3 из 20" and "? если нужно: доработка после итоговой проверки".
- A `count` of `0` is a real round: presence is tested with `is not None`, so `0` shows "0 из {max}" and a box
  badge "0/{max}", never the open "до {max} раз" form (see `test_a2_zero_count_is_shown_not_treated_as_unset`).
- A branch whose state is `skipped` is evidence the path was *not* taken, so choice selection ignores it and draws
  the branch that actually ran (see `test_a2_skipped_branch_is_not_the_taken_one`).
"""

import unittest
from unittest.mock import patch

# The source-hygiene scan (`tests.test_toolchain`) imports every test module with neither Textual nor Rich
# importable, so Rich — and `scheme`, which draws with it — is imported only when it is there; the tests are then
# declared and skipped, never hidden (unittest discovery must see them).
try:
    from rich.cells import cell_len
    from terminal_planner import engine, milestone
    from terminal_planner.tui import scheme
except ImportError:  # pragma: no cover - covered by the bare import scan of tests.test_toolchain
    cell_len = engine = milestone = scheme = None
HAVE_RICH = scheme is not None
RICH_REASON = "Rich unavailable: ZPLAN_TEST_WHEELHOUSE with the rich wheels is needed"

SIZES = ((40, 10), (70, 30), (120, 40))  # the sizes A1 names
# An active attempt's observation: the worker running with a timer, one reviewer rejected, the task loop counting.
RUNNING = {"worker": {"state": "running", "timer": "0:10"}, "acceptance_review": {"state": "failed"},
           "review_loop": {"count": 2}}

# The GLOSSARY RU column (`docs/ui-redesign/GLOSSARY.md`) for every id the renderer may ask for, placeholders as
# written: role.*, state.* and the templated flow rows. A `words` callable built only from these must render both
# graphs; any id outside this set (e.g. the invented `flow.loop_group_open`) is a KeyError, i.e. a bug.
GLOSSARY_RU = {
    "role.preflight": "предпроверка", "role.select_init": "выбор первой задачи", "role.select": "выбор задачи", "role.select_verify": "проверка выбора",
    "role.worker": "исполнитель", "role.review_accept": "ревью: приёмка", "role.review_code": "ревью: код",
    "role.steward_apply": "учёт результата", "role.steward_decide": "решение по задаче",
    "role.final_check": "итоговая проверка", "role.repair": "доработка этапа", "role.scope_verify": "проверка объёма",
    "role.final_reverify": "повторная итоговая проверка", "role.planner": "планирование",
    "role.plan_check": "проверка плана",
    "state.running": "идёт", "state.done": "готово", "state.rejected": "отклонено", "state.error": "ошибка",
    "state.waiting": "ждёт", "state.skipped": "пропущено",
    "state.if_needed": "если нужно",
    "flow.loop_group": "{name} · {n} из {max} / до {max} раз",
    "flow.optional": "если нужно: {name}",
    "flow.task_loop": "задачи по очереди", "flow.review_loop": "раунды ревью",
    "flow.repair_loop": "раунды доработки", "flow.final_repair": "доработка после итоговой проверки",
    "flow.fold_done": "✓ ещё {n} позади ↑",
    "flow.fold_next": "◌ ещё {n} впереди: {names} ↓",
}


@unittest.skipUnless(HAVE_RICH, RICH_REASON)
class SchemeTests(unittest.TestCase):
    def milestone_graph(self):
        return milestone.milestone_graph(3)["root"]

    def planner_graph(self):
        return engine.planner_graph_v2(3)["root"]

    def test_a1_fits_width_and_height_in_all_three_modes(self):
        """A1: `render` is pure and its `Text` never exceeds the pane, in boxes, tree and window modes."""
        for graph in (self.milestone_graph(), self.planner_graph()):
            for width, height in SIZES:
                for observation in ({}, RUNNING):
                    with self.subTest(width=width, height=height, active=bool(observation)):
                        text = scheme.render(graph, observation, width, height, tick=3)
                        lines = text.plain.split("\n")
                        self.assertLessEqual(len(lines), height)
                        self.assertLessEqual(max(cell_len(line) for line in lines), width)
        # The three modes are each reached; their evidence is in the plain text (marks, no box frame in tree/window).
        self.assertIn("╭", scheme.render(self.planner_graph(), {}, 120, 40).plain)  # boxes fit
        tree = scheme.render(self.milestone_graph(), {}, 70, 30).plain
        self.assertIn("↻", tree)
        self.assertNotIn("╭", tree)  # one line per step
        window = scheme.render(self.milestone_graph(), RUNNING, 40, 10).plain
        self.assertIn("ahead", window)  # the folded ends
        self.assertNotIn("╭", window)

    def test_a2_states_choice_and_loop(self):
        """A2: the mark of each state, the spinner by `tick`, one choice branch, the loop round."""
        graph = self.milestone_graph()
        running0 = scheme.render(graph, {"worker": {"state": "running"}}, 70, 30, tick=0).plain
        running1 = scheme.render(graph, {"worker": {"state": "running"}}, 70, 30, tick=1).plain
        self.assertIn("◐ worker", running0)
        self.assertIn("◓ worker", running1)
        self.assertIn("✓ worker", scheme.render(graph, {"worker": {"state": "succeeded"}}, 70, 30).plain)
        self.assertIn("✗ acceptance review",
                      scheme.render(graph, {"acceptance_review": {"state": "failed"}}, 70, 30).plain)
        self.assertIn("! worker", scheme.render(graph, {"worker": {"state": "failed"}}, 70, 30).plain)
        self.assertIn("◌ worker", scheme.render(graph, {}, 70, 30).plain)
        # A choice draws only the taken branch; before anything ran, the default (the first) one.
        choice = {"kind": "seq", "name": "g", "children": [
            {"kind": "choice", "name": "pick", "branches": [
                {"node": {"kind": "step", "name": "left_step"}},
                {"node": {"kind": "step", "name": "right_step"}}]}]}
        default = scheme.render(choice, {}, 70, 30).plain
        self.assertIn("left step", default)
        self.assertNotIn("right step", default)
        taken = scheme.render(choice, {"right_step": {"state": "running"}}, 70, 30).plain
        self.assertIn("right step", taken)
        self.assertNotIn("left step", taken)
        # A loop shows ↻ with its round (count) out of maxIterations, or "up to N times" when no count is set.
        loop = {"kind": "loop", "name": "review_loop", "maxIterations": 4, "body": {"kind": "step", "name": "worker"}}
        self.assertIn("↻ review rounds · 2 of 4", scheme.render(loop, {"review_loop": {"count": 2}}, 70, 2).plain)
        self.assertIn("↻ review rounds · up to 4 times", scheme.render(loop, {}, 70, 2).plain)
        unmapped = {"kind": "loop", "name": "mystery_loop", "maxIterations": 4,
                    "body": {"kind": "step", "name": "worker"}}
        self.assertIn("↻ mystery loop · up to 4 times", scheme.render(unmapped, {}, 70, 2).plain)

    def test_a3_words_table_legend_and_name_fallback(self):
        """A3: every word from the one GLOSSARY-keyed table, a `words` callable replacing it, unknown names spaced."""
        self.assertEqual(scheme.legend().plain, "◐ running  ✓ done  ✗ rejected  ◌ waiting  ")
        graph = self.milestone_graph()
        observation = {"worker": {"state": "succeeded"}, "review_loop": {"count": 1}}
        english = scheme.render(graph, observation, 70, 30).plain
        self.assertIn("worker", english)
        self.assertIn("done", english)
        self.assertIn("1 of 4", english)
        self.assertIn("if needed", english)

        seen = []

        def words(gid):
            seen.append(gid)
            return "«%s»" % gid

        custom = scheme.render(graph, observation, 70, 30, words=words).plain
        self.assertIn("«role.worker»", custom)
        self.assertIn("«state.done»", custom)
        self.assertIn("«flow.loop_group»", custom)
        self.assertIn("«flow.optional»", custom)
        self.assertNotIn(" worker ", custom)  # the catalog word is gone, only ids remain
        self.assertIn("role.worker", seen)
        self.assertEqual(scheme.legend(words=words).plain,
                         "◐ «state.running»  ✓ «state.done»  ✗ «state.rejected»  ◌ «state.waiting»  ")
        unknown = {"kind": "seq", "name": "g", "children": [{"kind": "step", "name": "mystery_node"}]}
        self.assertIn("mystery node", scheme.render(unknown, {}, 70, 30).plain)

    def test_a4_observation_from_flow(self):
        """A4: the observation built from `live.flow`'s facts; `None`/`{}` give `{}`."""
        self.assertEqual(scheme.observation_from_flow(None), {})
        self.assertEqual(scheme.observation_from_flow({}), {})
        flow = {"worker": {"state": "running"},
                "reviewers": [{"role": "acceptance_review", "name": "приёмка", "state": "accepted", "text": "ok"},
                              {"role": "code_review", "name": "ревью кода", "state": "rejected", "text": "no"}],
                "final": {"state": "running"}, "select": True, "round": 2, "command": "pytest -q"}
        self.assertEqual(scheme.observation_from_flow(flow),
                         {"worker": {"state": "running", "detail": "pytest"},
                          "acceptance_review": {"state": "succeeded"},
                          "code_review": {"state": "failed"},
                          "final_verify": {"state": "running"},
                          "select": {"state": "running"},
                          "review_loop": {"count": 2}})
        idle = scheme.observation_from_flow({"worker": {"state": "done"},
                                             "reviewers": [{"role": "acceptance_review", "state": "waiting"}],
                                             "final": {"state": "waiting"}, "select": False, "round": None,
                                             "command": None})
        self.assertEqual(idle, {"worker": {"state": "succeeded"}, "acceptance_review": {"state": "idle"}})

    def test_observation_marks_the_steps_before_a_picked_task_succeeded(self):
        """C4 J3: a flow with a picked task and no pick running has preflight, select_init and select_verify
        behind it; a running pick, or a flow without a task, marks none of them."""
        done = {"state": "succeeded"}
        obs = scheme.observation_from_flow({"task": "T1", "worker": {"state": "running"}, "select": False})
        self.assertEqual((obs["preflight"], obs["select_init"], obs["select_verify"]), (done, done, done))
        self.assertNotIn("preflight", scheme.observation_from_flow({"task": "T1", "select": True}))
        self.assertNotIn("preflight", scheme.observation_from_flow({"task": None, "worker": {"state": "running"}}))

    def test_preflight_word_and_conflict_reviewer_state(self):
        """C3: an active `preflight` node renders «preflight» in the milestone scheme, and a reviewer whose
        verdict is `conflict` is observed as failed (like a rejection)."""
        graph = self.milestone_graph()
        self.assertIn("preflight", scheme.render(graph, {"preflight": {"state": "running"}}, 120, 40).plain)
        flow = {"reviewers": [{"role": "acceptance_review", "state": "conflict"},
                              {"role": "code_review", "state": "accepted"}]}
        self.assertEqual(scheme.observation_from_flow(flow),
                         {"acceptance_review": {"state": "failed"}, "code_review": {"state": "succeeded"}})

    def test_a5_failed_and_error_styles_differ(self):
        """A5: the one style check — a rejected reviewer's ✗ and a broken worker's ! must not look the same."""
        graph = self.milestone_graph()

        def mark_styles(text, glyph):
            found = set()
            for line in text.split():
                for span in line.spans:
                    if glyph in line.plain[span.start:span.end]:
                        found.add(str(span.style))
            return found

        rejected = mark_styles(scheme.render(graph, {"acceptance_review": {"state": "failed"}}, 70, 30), "✗")
        broken = mark_styles(scheme.render(graph, {"worker": {"state": "failed"}}, 70, 30), "!")
        self.assertTrue(rejected)
        self.assertTrue(broken)
        self.assertNotEqual(rejected, broken)

    def test_a1_cjk_words_fit_in_cells(self):
        """A1 regression: two-cell CJK characters never push a line past `width` (boxes clip in cells, not chars).

        Interpretation: the reject's reproduction — Chinese role/state words — must fit at 40x10 (the planner graph
        lands in box mode there) and at the three A1 sizes, with a Chinese box title as well."""
        cjk = lambda gid: "计划审查" if gid.startswith("role.") else scheme.WORDS[gid]  # noqa: E731
        observation = {"planner": {"state": "running", "title": "计划编写者"}}
        for graph in (self.milestone_graph(), self.planner_graph()):
            for width, height in SIZES + ((40, 10),):
                for obs in ({}, observation):
                    lines = scheme.render(graph, obs, width, height, words=cjk).plain.split("\n")
                    self.assertLessEqual(len(lines), height)
                    self.assertLessEqual(max(cell_len(line) for line in lines), width)
        self.assertIn("计划编写者", scheme.render(self.planner_graph(), observation, 120, 40, words=cjk).plain)

    def test_a1_multiline_detail_fits_one_row(self):
        """A1 regression: a multiline `detail`/`title` never adds physical rows past `height` (boxes and tree alike).

        Interpretation: the observation contract allows an ordinary string, so `detail` may carry embedded newlines.
        The renderer folds every line break in a display field (`detail`, `title`) to a space before layout, so the
        one-row-per-item count in `_lines` still holds and neither `Canvas` (boxed labels) nor `_paint` appends the
        extra breaks after fitting. The reject's reproduction at 40x10 (milestone, worker detail
        "checking build\\nrunning tests") now draws the worker on its single row instead of two."""
        detail = "checking build\nrunning tests"
        for graph in (self.milestone_graph(), self.planner_graph()):
            for width, height in SIZES + ((40, 10),):
                for observation in ({"worker": {"state": "running", "detail": detail}},
                                    {"planner": {"state": "running", "title": "multi\nline title"}}):
                    lines = scheme.render(graph, observation, width, height).plain.split("\n")
                    self.assertLessEqual(len(lines), height)
                    self.assertLessEqual(max(cell_len(line) for line in lines), width)
        small = {"kind": "seq", "name": "g", "children": [{"kind": "step", "name": "worker"}]}
        folded = scheme.render(small, {"worker": {"state": "running", "detail": "build\nrun"}}, 120, 10).plain
        self.assertIn("build run", folded)
        self.assertNotIn("\nrun", folded)

    def test_a2_zero_count_is_shown_not_treated_as_unset(self):
        """A2 regression: `count` 0 is a real round, so the loop shows "0 of 4" (tree) and "0/4" (box), not "up to 4 times".

        Interpretation: presence of a count is tested with `is not None`; `0` must not fall through to the open form."""
        loop = {"kind": "loop", "name": "review_loop", "maxIterations": 4, "body": {"kind": "step", "name": "worker"}}
        self.assertIn("↻ review rounds · 0 of 4", scheme.render(loop, {"review_loop": {"count": 0}}, 70, 2).plain)
        boxed = scheme.render(loop, {"review_loop": {"count": 0}}, 70, 10).plain
        self.assertIn("0/4", boxed)
        self.assertNotIn("≤4", boxed)

    def test_a2_skipped_branch_is_not_the_taken_one(self):
        """A2 regression: a `skipped` branch is not the taken one; the branch that actually ran is drawn.

        Interpretation: a skipped node is evidence the path was *not* taken, so `_touched` ignores it and choice
        selection picks the running branch instead of the first (skipped) one."""
        choice = {"kind": "seq", "name": "g", "children": [
            {"kind": "choice", "name": "pick", "branches": [
                {"node": {"kind": "step", "name": "left_step"}},
                {"node": {"kind": "step", "name": "right_step"}}]}]}
        observed = {"left_step": {"state": "skipped"}, "right_step": {"state": "running"}}
        plain = scheme.render(choice, observed, 70, 30).plain
        self.assertIn("right step", plain)
        self.assertNotIn("left step", plain)

    def test_a3_glossary_derived_callable(self):
        """A3 regression: a callable holding only GLOSSARY ids/placeholders renders both graphs, count set and unset.

        Interpretation: every requested id must be one the GLOSSARY lists (no `flow.loop_group_open`), and every
        templated word must be filled (`flow.loop_group` {name}/{n}/{max}, `flow.optional` {name}, the folds
        {n}/{names}), so no "{" survives into the plain text and a glossary-only catalog never raises KeyError."""
        requested = set()

        def words(gid):
            requested.add(gid)
            return GLOSSARY_RU[gid]  # KeyError if the renderer asks for an id the GLOSSARY does not list

        for graph in (self.milestone_graph(), self.planner_graph()):
            for width, height in SIZES + ((40, 7),):
                for obs in ({}, RUNNING, {"review_loop": {"count": 1}}):
                    with self.subTest(graph=bool(graph), size=(width, height), active=bool(obs)):
                        plain = scheme.render(graph, obs, width, height, words=words).plain
                        self.assertNotIn("{", plain)
        self.assertLessEqual(requested, set(GLOSSARY_RU))

    def test_render_accepts_graph_root_keyword(self):
        """A1 regression: `render`'s first parameter is named `graph_root`, callable by keyword.

        Interpretation: the public contract is `render(graph_root, observation, width, height, ...)`, so a keyword
        call must not raise `TypeError`; the positional call stays valid. The planner graph is the case the contract
        names."""
        from terminal_planner import engine
        root = engine.planner_graph_v2(3)["root"]
        by_kw = scheme.render(graph_root=root, observation={}, width=40, height=10)
        self.assertEqual(by_kw.plain, scheme.render(root, {}, 40, 10).plain)

    def test_a3_unknown_name_keeps_empty_prefix(self):
        """A3 regression: an unmapped name is shown whole (`_` -> space), never truncated past `empty_`.

        Interpretation: the `empty_` prefix marks a production variant only when the remainder has a role mapping
        (`empty_final_verify` -> the role word); a name with no mapping keeps its full text, so `empty_cache` is
        `empty cache`, not `cache`."""
        graph = {"kind": "step", "name": "empty_cache"}
        self.assertIn("empty cache", scheme.render(graph, {}, 70, 3).plain)
        mapped = {"kind": "step", "name": "empty_final_verify"}
        self.assertIn("final check", scheme.render(mapped, {}, 70, 3).plain)

    # ── U1b: the stage graph's loops and its optional branch in the owner's words ─────────────────────────────

    # U1b A1: the approved observation (the bug paragraph names the running stage with the task loop on round 3 of
    # 20 and the review loop on round 1 of 4, no other node set) and the owner-approved lines the lab draws
    # (`devtools/ui-lab/flowdraw.py` NAMES/`_leaf`; `flowdraw.render(milestone graph, obs, 110, 34, 0)`).
    U1B_OBS = {"task_loop": {"count": 3}, "review_loop": {"count": 1}}
    U1B_LINES = ("↻ tasks one by one · 3 of 20", "↻ review rounds · 1 of 4",
                 "? if needed: fix-up after the final check", "↻ fix-up rounds · up to 3 times",
                 "┆ │ ◌ stage fix-up · if needed")

    def test_u1b_a1_loops_and_branch_use_the_owner_words(self):
        """U1b A1: `task_loop`/`review_loop`/`repair_loop`/`final_repair` map to their `flow.*` ids, and the
        milestone graph at 110x34 with the approved observation renders the approved lines.

        Interpretations (both reviewers read this docstring): the task quotes the observation only as "the
        observation above" — the bug paragraph fixes the two counts it names (task loop 3 of 20, review loop 1 of
        4, nothing else set), so the fixture is `{"task_loop": {"count": 3}, "review_loop": {"count": 1}}`. The id
        names the node, not the round: `flow.loop_group` still carries the count, so the approved lines read
        "↻ tasks one by one · 3 of 20". A step inside the branch keeps its own role word and only its tail changes
        ("stage fix-up · if needed")."""
        for name, gid in (("task_loop", "flow.task_loop"), ("review_loop", "flow.review_loop"),
                          ("repair_loop", "flow.repair_loop"), ("final_repair", "flow.final_repair")):
            with self.subTest(name):
                self.assertEqual(scheme.NODE_IDS.get(name), gid)
        plain = scheme.render(self.milestone_graph(), self.U1B_OBS, 110, 34, 0).plain
        for line in self.U1B_LINES:
            with self.subTest(line):
                self.assertIn(line, plain)
        for engine_name in ("task loop", "review loop", "repair loop", "final repair"):
            with self.subTest(engine_name):
                self.assertNotIn(engine_name, plain)  # no engine name survives

    def test_final_check_retry_is_a_count_on_its_box_not_a_frame(self):
        """H1/I5: the final check's retry loop has no frame of its own; a retry observation puts `↻2/2` on the final
        check box at 120 columns, and nothing is added before the retry (count 1) or without a count."""
        graph = self.milestone_graph()
        loops = lambda text: [line for line in text.split("\n") if "↻" in line]  # noqa: E731
        base = scheme.render(graph, {}, 120, 60).plain
        retry = scheme.render(graph, {"final_verify_loop": {"count": 2}, "final_verify": {"state": "running"}}, 120, 60)
        self.assertTrue(all(cell_len(line) <= 120 for line in retry.plain.split("\n")))
        self.assertIn("final check ↻2/2", retry.plain)
        self.assertEqual(len(loops(retry.plain)), len(loops(base)) + 1)
        self.assertEqual(len(loops(base)), len(loops(scheme.render(graph, {"final_verify_loop": {"count": 1}}, 120, 60).plain)))
        self.assertNotIn("final verify loop", scheme.render(graph, {"final_verify_loop": {"count": 2}}, 70, 60).plain)

    def test_l2_the_flows_final_attempt_is_the_count_of_its_retry_loop(self):
        """L2: `observation_from_flow` puts the final check's attempt as `count` on the loop of the check named in
        the flow; the scheme draws `↻2/2` for attempt 2 and nothing for attempt 1, on the final check before a repair and on the
        final re-check (the role word of that box) after one."""
        graph = self.milestone_graph()
        for check, title in (("final_verify", "final check"), ("final_reverify", "final re-check")):
            for attempt, drawn in ((2, True), (1, False)):
                flow = {"final": {"state": "running", "attempt": attempt, "check": check}}
                with self.subTest(check=check, attempt=attempt):
                    obs = scheme.observation_from_flow(flow)
                    self.assertEqual(obs[check + "_loop"], {"count": attempt})
                    self.assertEqual(title + " ↻2/2" in scheme.render(graph, obs, 120, 60).plain, drawn)
        self.assertNotIn("_loop", "".join(scheme.observation_from_flow({"final": {"state": "running"}})))

    def test_u1b_a2_waiting_step_in_optional_branch_says_state_if_needed(self):
        """U1b A2: a waiting step inside an "if needed" branch shows `state.if_needed` as its word, never the
        branch name.

        Interpretation (both reviewers read this docstring): the branch is named once by the `?` header
        (`flow.optional`, templated with the branch name); every step inside it that has not run says only the
        `state.if_needed` word, as the approved lab `_leaf` does. A `words` callable returning its id shows which
        id each part requests."""
        graph = self.milestone_graph()
        plain = scheme.render(graph, self.U1B_OBS, 110, 34, 0).plain
        self.assertEqual(plain.count("fix-up after the final check"), 1)  # the header names the branch once
        self.assertIn("◌ stage fix-up · if needed", plain)  # the step's word is the plain if_needed word
        seen = []

        def words(gid):
            seen.append(gid)
            return "«%s»" % gid

        ids = scheme.render(graph, self.U1B_OBS, 110, 34, 0, words=words).plain
        self.assertIn("«state.if_needed»", ids)  # the step inside the branch asks for state.if_needed
        self.assertIn("«flow.optional»", ids)  # the branch header asks for flow.optional
        self.assertIn("flow.optional", seen)
        self.assertIn("state.if_needed", seen)

    def test_u1b_a4_english_words_from_the_string_catalog(self):
        """U1b A4: `words=strings.text` with language en renders "tasks one by one" and "if needed".

        Interpretation (both reviewers read this docstring): the language is pinned by patching `strings.language`
        to "en", never by reading or writing the runner's own preferences. `strings.text` is the renderer's words
        callable, so it must leave a placeholder the renderer fills (`flow.loop_group`) verbatim; a value it is
        given is still substituted here."""
        from terminal_planner.tui import strings
        with patch("terminal_planner.tui.strings.language", return_value="en"):
            plain = scheme.render(self.milestone_graph(), self.U1B_OBS, 110, 34, 0, words=strings.text).plain
        self.assertIn("↻ tasks one by one · 3 of 20", plain)
        self.assertIn("↻ review rounds · 1 of 4", plain)
        self.assertIn("? if needed: fix-up after the final check", plain)
        self.assertIn("↻ fix-up rounds · up to 3 times", plain)
        self.assertIn("◌ stage fix-up · if needed", plain)
        self.assertIn("if needed", plain)
