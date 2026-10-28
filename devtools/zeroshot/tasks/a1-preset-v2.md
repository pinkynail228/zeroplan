A1 — preset `zplan.default/2` with an `autonomy` section, as data (RELEASE_0.6.0_PLAN A1; ARCHITECT_DESIGN 4.2, 4.3).

Why: the architect slices (A4 foreman, A5 autonomy gate, A6 wake-ups and stuck rules, A9 admission) read their
levels and thresholds from the preset, never from code. This slice only adds the data; nothing acts on it yet.

Reuse: `PRESETS` and the comment at process.py:56 (a change ships as /2, `/1` is never edited); `validate_profile`,
`_object`, `invalid`, `resolve`, `complete`, `describe` and `NEXT_STAGES`. Today `resolve` (:305) and `complete`
(:330) hard-code one key set; make the key set depend on the preset.

Write-set: terminal_planner/process.py, tests/test_process.py.

Acceptance criteria:
- C1 `zplan.default/2` = the /1 roles, gates and limits plus `autonomy`: `level` auto (one of auto, supervised,
  manual), `max_runs` 3 (1..5), `worker_round_minutes` 45 (5..240), `run_minutes` 120 (10..1440),
  `structural_round` 3 (2..10), `wakeups_per_hour` 12 (1..60), `architect_retries` 3 (0..10). A project file with
  `"preset": "zplan.default/2"` may set any subset of `autonomy`; the rest comes from the preset.
  Example: `{"preset":"zplan.default/2","autonomy":{"level":"manual"}}` -> resolved `autonomy.level` manual,
  `max_runs` 3, sources `file` for level and `preset` for the others.
- C2 Invalid values are refused like other keys. Example: `"autonomy":{"level":"yolo"}` -> «zplan.process.json: ключ
  «autonomy.level» — допустимы auto, manual, supervised. Исправьте значение.»; `max_runs: 9` names the range 1..5;
  an unknown `autonomy.x` -> «неизвестный ключ».
- C3 `/1` is unchanged: with no project file, or a file naming /1, the resolved config, its digest and the
  `describe` lines are byte-identical to today; a stored /1 acceptance snapshot loads. `autonomy` in a /1 file is
  refused with the fix «укажите "preset": "zplan.default/2"».
- C4 `describe` under /2 adds one line after «раунды», e.g. «  автономия: auto · прогонов до 3 · раунд воркера 45 мин ·
  прогон 120 мин · проверка после раунда 3 · пробуждений 12/ч · повторов 3  [пресет zplan.default/2] (для следующих
  этапов)»; the «пресет» line names /2.
- C5 The default stays /1 (no file -> /1; `propose()` still proposes /1); switching the default is a later slice
  with a migration note to the owner.

Non-goals (reviewers must not require): any consumer of `autonomy`; critic triggers (A7); a TUI settings editor;
changing zplan.process.json of this repo; a migration of stored records.

Risk: medium (process profile; /1 identity must hold). DoD: `python3.13 devtools/fasttest.py tests.test_process
tests.test_toolchain` exit 0; quote the `fasttest:` lines.
