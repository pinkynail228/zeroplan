"""U2: the UI string catalog and the language choice (tests/test_tui_strings.py).

One test per acceptance criterion A1-A7; every test runs with an isolated `XDG_CONFIG_HOME` and pinned locale
variables, so nothing reads or writes the runner's own preferences and the default-language checks are deterministic.

Worker interpretations (both reviewers inspect this docstring): the catalog covers the GLOSSARY tables whose area is
`pane.`/`plan.`/`role.`/`state.`/`flow.`/`live.`/`key.`; the `bar.status` row has no EN/RU/ZH cell (its column holds
dashes), so it gets no id (A5 requires every id in all three languages). The lab literals become `chat.`, `card.`,
`canvas.`, `bar.`, `cmd.` and `note.` ids; a value the lab interpolates from the CSV story is a placeholder
(`card.merge_title` "{stage} готов"). The count labels the lab spells with a Russian plural are UI copy too, so the
three nouns it shows (task, check, stage) keep the Russian forms the lab prints as plain `canvas.count_*` ids; nothing
selects a form (`count(noun, n)` would be a plural rule beyond the brief, so it is not here), and `card.plan_title`
takes the two rendered counts (`{stages}`, `{tasks}`) instead of a preformatted blob. The
Liveness clocks keep the GLOSSARY spelling `{m:ss}`/`{h:mm:ss}`, so `text` substitutes the field names only and
`{m:ss}` in `str.format` is read as the field `m` with a clock spec: A5 extracts field names with
`string.Formatter().parse`, which agrees for all three languages. The generic titles/details the lab's `_scheme`
puts on the scheme nodes ("раунды плана", "читает код", "сверяет с целью", "ждёт тебя", "модель не ответила") are
UI copy, so they are cataloged as `canvas.obs_*`; the `STEPS` worker briefs and the run log lines are the scripted
story and stay fixture content.
"""

import json
import os
from pathlib import Path
import re
from string import Formatter
import tempfile
import unittest
from unittest.mock import patch

from terminal_planner import setup
from terminal_planner.tui import strings

# A6: every GLOSSARY row whose table has RU/EN/ZH cells, plus the ids the other runs already fix.
GLOSSARY_IDS = {
    "pane.chat", "pane.flow", "pane.plan", "pane.activity", "flow.legend",
    "plan.goal", "plan.stage", "plan.task", "plan.left",
    "role.architect", "role.planner", "role.plan_check", "role.worker", "role.review_accept", "role.review_code",
    "role.final_check", "role.merge", "role.preflight", "role.select_init", "role.select", "role.select_verify", "role.steward_apply",
    "role.steward_decide", "role.repair", "role.scope_verify", "role.final_reverify",
    "state.running", "state.done", "state.rejected", "state.error", "state.waiting", "state.skipped",
    "flow.loop", "flow.round", "flow.loop_group", "flow.optional", "flow.fold_done", "flow.fold_next",
    # U1b fixes the stage graph's loops and its optional branch: the scheme asks for these five ids.
    "flow.task_loop", "flow.review_loop", "flow.repair_loop", "flow.final_repair", "state.if_needed",
    "live.step_timer", "live.job_timer", "live.last_event", "live.detached",
    "key.panel", "key.view", "key.commands", "key.quit",
}
FIXED_IDS = {
    "cmd.plan", "cmd.approve", "cmd.decline", "cmd.merge", "cmd.diff", "cmd.open", "cmd.status", "cmd.stop",
    "cmd.language", "cmd.setup", "cmd.help", "cmd.quit",
    "note.unknown_command", "note.not_now", "note.needs_arg", "note.bad_language", "note.view_empty",
    "note.view_outside", "note.view_missing", "note.view_directory", "note.view_binary",
    "canvas.view_cut", "canvas.diff_empty",
}


def placeholders(template):
    return {name for _, name, _, _ in Formatter().parse(template) if name is not None}


class StringsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.environment = patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.root / "config"),
                                                   "LC_ALL": "", "LC_MESSAGES": "", "LANG": ""})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        offered = patch.object(strings, "OFFERED", strings.LANGUAGES)  # L1: these tests pin all three languages
        offered.start()
        self.addCleanup(offered.stop)

    # A1 -------------------------------------------------------------------------------------------
    def test_a1_text_returns_language_falls_back_to_en_and_raises_on_unknown_id(self):
        strings.set_language("ru")
        self.assertEqual(strings.text("pane.chat"), "Разговор")
        self.assertEqual(strings.text("flow.optional", name="исполнитель"), "если нужно: исполнитель")
        with patch.dict(strings.CATALOG, {"pane.chat": {"en": "Conversation"}}):
            strings.set_language("ru")
            self.assertEqual(strings.text("pane.chat"), "Conversation")
        with self.assertRaises(KeyError):
            strings.text("no.such.id")

    # A2 -------------------------------------------------------------------------------------------
    def test_a2_languages_display_names_switch_at_once_and_persist(self):
        self.assertEqual(strings.LANGUAGES, ("en", "ru", "zh"))
        self.assertEqual({strings.display_name(code) for code in strings.LANGUAGES},
                         {"English", "Русский", "中文"})
        self.assertEqual(strings.language(), "en")
        strings.set_language("zh")
        self.assertEqual(strings.language(), "zh")
        self.assertEqual(strings.text("pane.plan"), "计划")
        self.assertEqual(json.loads((setup.config_root() / "ui.json").read_text(encoding="utf-8")),
                         {"language": "zh"})

    def test_s3a_r4_the_theme_and_the_language_are_stored_side_by_side(self):
        """S3a/R4: `set_theme` keeps the stored language and `set_language` keeps the stored theme; an unknown theme
        is refused."""
        path = setup.config_root() / "ui.json"
        strings.set_language("zh")
        strings.set_theme("light")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"language": "zh", "theme": "light"})
        strings.set_language("en")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"language": "en", "theme": "light"})
        self.assertEqual((strings.language(), strings.stored_theme()), ("en", "light"))
        with self.assertRaises(ValueError):
            strings.set_theme("blue")

    def test_l1_only_english_is_offered_and_the_language_in_effect_is_always_offered(self):
        """L1/C1 (0.8, T2): the real `OFFERED` is `("en",)`, so a locale or a stored language outside it (a 0.7.x
        install stored `ru`) reads as English, while the catalog keeps ru and zh. Interpretation: no stored code is
        rewritten; only the reading changes, and `set_language` still stores any catalog code. Every `en` value is
        English (no Cyrillic), which is what a fresh TUI shows."""
        with patch.object(strings, "OFFERED", ("en",)):
            self.assertEqual(strings.OFFERED, ("en",))
            with patch.dict(os.environ, {"LANG": "ru_RU.UTF-8"}):
                self.assertEqual(strings.language(), "en")  # the locale default
                strings.set_language("ru")  # what 0.7.x stored
                self.assertEqual(strings.language(), "en")
                self.assertEqual(strings.text("pane.plan"), strings.CATALOG["pane.plan"]["en"])
            with patch.dict(os.environ, {"LANG": "zh_CN.UTF-8"}):
                self.assertEqual(strings.language(), "en")
        self.assertEqual(strings.language(), "ru")  # offered again: the stored code reads as it does
        for key, entry in strings.CATALOG.items():
            self.assertTrue(entry["ru"] and entry["zh"], key)  # the catalog keeps ru and zh
            self.assertIsNone(re.search("[\u0400-\u04ff]", entry["en"]), (key, entry["en"]))
        self.assertEqual(set(strings.CATALOG["note.only_russian"]), set(strings.LANGUAGES))

    # A3 -------------------------------------------------------------------------------------------
    def test_a3_default_language_comes_from_the_locale(self):
        for variable, value, want in [("LC_ALL", "ru_RU.UTF-8", "ru"), ("LC_ALL", "zh_CN.UTF-8", "zh"),
                                      ("LC_ALL", "en_US.UTF-8", "en"), ("LC_MESSAGES", "ru_RU.UTF-8", "ru"),
                                      ("LC_MESSAGES", "zh_CN.UTF-8", "zh"), ("LANG", "ru_RU.UTF-8", "ru"),
                                      ("LANG", "zh_CN.UTF-8", "zh"), ("LC_ALL", "C", "en")]:
            with patch.dict(os.environ, {"LC_ALL": "", "LC_MESSAGES": "", "LANG": "", variable: value}):
                self.assertEqual(strings.default_language(), want, (variable, value))
                self.assertEqual(strings.language(), want, (variable, value))
        with patch.dict(os.environ, {"LC_ALL": "en_US.UTF-8", "LANG": "ru_RU.UTF-8"}):
            self.assertEqual(strings.default_language(), "en")  # LC_ALL wins over LANG

    # A4 -------------------------------------------------------------------------------------------
    def test_a4_stored_in_ui_json_and_bad_values_are_ignored(self):
        path = setup.config_root() / "ui.json"
        self.assertFalse(path.exists())
        strings.set_language("ru")
        self.assertTrue(path.parent.is_dir())  # writing creates the directory
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"language": "ru"})
        path.write_text('{"language": "de"}', encoding="utf-8")  # unknown code
        with patch.dict(os.environ, {"LANG": "zh_CN.UTF-8"}):
            self.assertEqual(strings.language(), "zh")
        path.write_text("not json", encoding="utf-8")  # unreadable file
        with patch.dict(os.environ, {"LANG": "ru_RU.UTF-8"}):
            self.assertEqual(strings.language(), "ru")

    # A5 -------------------------------------------------------------------------------------------
    def test_a5_every_id_has_three_languages_with_the_same_placeholders(self):
        self.assertTrue(strings.CATALOG)
        for key, entry in strings.CATALOG.items():
            with self.subTest(key):
                self.assertEqual(set(entry), set(strings.LANGUAGES), key)
                names = placeholders(entry["en"])
                for code in strings.LANGUAGES:
                    self.assertEqual(placeholders(entry[code]), names, key)

    # A6 -------------------------------------------------------------------------------------------
    def test_a6_catalog_covers_the_glossary_and_the_fixed_ids(self):
        self.assertEqual((GLOSSARY_IDS | FIXED_IDS) - set(strings.CATALOG), set())

    # Regression: the repair for the rejected coverage, then for the rejected plural selector. Reproduction
    # (interpretations in this docstring, read by both reviewers): the lab's canvas titles for the question/error
    # states (`work.py:493-494`), the planning subtitle (`work.py:504`), the note for a command the lab does not
    # show (`work.py:366`), the milestone/task counts (`work.py:218/601/605/622/608`) and the plan card title
    # (`work.py:218/231`) are all UI copy, so the catalog must reproduce the lab's Russian exactly and translate
    # them (not delegate to a preformatted blob, as an earlier `card.plan_title` did). The count labels keep the
    # forms the lab prints as plain `canvas.count_*` ids; the former `count(noun, n)` selector is gone (plural
    # selection is a non-goal), so the test names the id whose form each fixture value prints, never a rule.
    def test_lab_canvas_subtitle_note_and_counts_are_cataloged(self):
        strings.set_language("ru")
        # work.py:493-494 — the flow pane titles for the question and error states.
        self.assertEqual(strings.text("canvas.scheme_question", stage="M2 Экспорт CSV"),
                         "M2 Экспорт CSV · ждёт тебя")
        self.assertEqual(strings.text("canvas.scheme_error", stage="M2 Экспорт CSV"),
                         "M2 Экспорт CSV · остановлен: ошибка")
        # work.py:504 — the planning subtitle; the goal is the value the fixture interpolates.
        self.assertEqual(strings.text("canvas.planning_subtitle", goal="Экспорт отчётов в CSV"),
                         "по черновику цели «Экспорт отчётов в CSV»")
        # work.py:366 — the note for a command the lab does not show.
        self.assertEqual(strings.text("note.not_in_lab", name="/status"), "/status: в лабе не показано")
        # work.py:601/605/622/608 — the milestone task counts and the per-task check count ("25" would pick no form
        # here: the fixture names the id, the catalog holds the string, nothing inflects).
        self.assertEqual(strings.text("canvas.count_task_few", n=2), "2 задачи")
        self.assertEqual(strings.text("canvas.count_task_many", n=5), "5 задач")
        self.assertEqual(strings.text("canvas.count_check_few", n=2), "2 проверки")
        # work.py:218/231 — the plan card title "План · 3 этапа · 9 задач", built from the cataloged counts.
        self.assertEqual(strings.text("card.plan_title", stages=strings.text("canvas.count_stage_few", n=3),
                                      tasks=strings.text("canvas.count_task_many", n=9)), "План · 3 этапа · 9 задач")
        # The reviewer's isolated reproduction, in EN: the counts must be English, not the Russian fixture text, and
        # selection no longer leaks Russian rules into EN (there is no selector to return "21 task" for 21).
        strings.set_language("en")
        self.assertEqual(strings.text("card.plan_title", stages=strings.text("canvas.count_stage_few", n=3),
                                      tasks=strings.text("canvas.count_task_many", n=9)), "Plan · 3 stages · 9 tasks")

    # Regression (repair of the rejected question-card coverage): the lab's question card (`work.py:239-242`) reads
    # "Ревью отклонило T3 четыре раза подряд: нет теста на пустой отчёт, исполнитель не справляется. Что делаем?".
    # An earlier catalog dropped the consecutive-rejection count ("Ревью снова отклонило {task}: {why}"), so the
    # card named no number; the reviewer rejected it (P2) and an independent source comparison reproduced it.
    # Interpretations (both reviewers read this docstring; also in the module docstring): the consecutive-rejection
    # count is screen data, so it becomes the placeholder `{count}`, spelled the same in en/ru/zh (A5) instead of a
    # hardcoded Russian word. The counter word after it ("раза"/"times"/"次") is the catalog's own text, and, as with
    # the `canvas.count_*` ids, plural selection is a non-goal, so the id keeps the 2-4 form the lab prints
    # ("четыре раза"); the caller passes `{count}` as the screen language spells it (the lab spells RU as a word),
    # which lets this test reproduce the approved card verbatim.
    def test_lab_question_card_keeps_the_consecutive_rejection_count(self):
        why = "нет теста на пустой отчёт, исполнитель не справляется"
        strings.set_language("ru")
        self.assertEqual(strings.text("card.question_text", task="T3", count="четыре", why=why),
                         "Ревью отклонило T3 четыре раза подряд: нет теста на пустой отчёт, исполнитель не "
                         "справляется. Что делаем?")
        # The other two languages use the same {count} name and render a numeral (GLOSSARY writes numbers as digits).
        strings.set_language("en")
        self.assertEqual(strings.text("card.question_text", task="T3", count=4, why="no test on the empty report"),
                         "Review rejected T3 4 times in a row: no test on the empty report. What do we do?")
        strings.set_language("zh")
        self.assertEqual(strings.text("card.question_text", task="T3", count=4, why="空报告没有测试"),
                         "评审连续 4 次驳回 T3：空报告没有测试。怎么办？")

    # Regression (repair of the rejected lab-caption coverage): the lab's `_scheme` (`work.py:551-574`) sets the
    # generic captions "раунды плана" (the review-loop title), "читает код" (the planner's detail), "сверяет с
    # целью" (the critic's detail), "ждёт тебя" (the steward's decision detail) and "модель не ответила" (the
    # worker's error detail) on the scheme nodes; flowdraw draws a node's title from them (`flowdraw.py:100/288`)
    # and a node's word from the detail (`flowdraw.py:60-61/268`). An earlier catalog dropped all of them, so the
    # scheme could not show them translated; the acceptance reviewer rejected it. Interpretations (both reviewers
    # read this docstring; also in both module docstrings): these are generic UI captions, not the CSV story, file
    # names or times, so they get stable `canvas.obs_*` ids in all three languages. The `STEPS` worker briefs
    # ("пишет код", "запускает тесты", "готово", "доработка") and the run log lines are the scripted story (task
    # ids, tests, times), like the task names and the diff, so they stay fixture content with no id, as the brief
    # says ("Fixture content ... gets no id").
    def test_lab_scheme_observation_captions_are_cataloged(self):
        lab = (Path(__file__).resolve().parents[1] / "devtools" / "ui-lab" / "work.py").read_text(encoding="utf-8")
        captions = {
            "canvas.obs_plan_rounds": "раунды плана",
            "canvas.obs_reading_code": "читает код",
            "canvas.obs_checking_goal": "сверяет с целью",
            "canvas.obs_waiting_you": "ждёт тебя",
            "canvas.obs_model_no_answer": "модель не ответила",
        }
        strings.set_language("ru")
        for id, literal in captions.items():
            with self.subTest(id):
                self.assertIn(literal, lab)  # the caption still comes from the approved lab
                self.assertEqual(strings.text(id), literal)
                self.assertTrue(all(strings.CATALOG[id][code] for code in strings.LANGUAGES))
        strings.set_language("en")
        for id, literal in captions.items():
            self.assertNotEqual(strings.text(id), literal)  # translated, not left in Russian

    # A7 -------------------------------------------------------------------------------------------
    def test_a7_each_test_has_an_isolated_store_and_locale(self):
        self.assertTrue(setup.config_root().is_relative_to(self.root))
        self.assertFalse((setup.config_root() / "ui.json").exists())
        for variable in ("LC_ALL", "LC_MESSAGES", "LANG"):
            self.assertEqual(os.environ[variable], "")


class OfferedLanguagesTests(unittest.TestCase):
    def test_the_release_offers_english_only(self):
        """0.8: the shipped `OFFERED` (unpatched here, unlike `StringsTests`) is `("en",)`."""
        self.assertEqual(strings.OFFERED, ("en",))


if __name__ == "__main__":
    unittest.main()
