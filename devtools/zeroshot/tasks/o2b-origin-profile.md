O2b — an empty folder reaches its first run with no shell step

The orchestrator's newcomer check 2026-10-26 (0.6.1 on a clean HOME, empty folder): the start screen created the
project, but `/plan` refused with «Нет GitHub origin» and «Закоммитьте zplan.process.json» (terminal_planner/setup.py
readiness, ~:411 and ~:427), two shell detours. The engine only reads OWNER/NAME from a GitHub origin URL and pushes
nothing (upstream/zeroshot/src/native_v2_cli/execution/named_source.rs `parse_github_repository`); with
`origin https://github.com/newcomer/hello-mvp.git` (no such repository) the run planned, ran and merged.

Write-set: terminal_planner/tui/start.py, terminal_planner/process.py, terminal_planner/tui/strings.py,
tests/test_tui_start.py, tests/test_process.py, tests/test_tui.py.

Acceptance criteria:
- C1 Start screen: after a project is chosen or created, a project whose `origin` is not a GitHub URL (setup.py
  `GITHUB_ORIGIN`) shows one step «Нет GitHub origin» saying Zeroshot names the project by it, zplan pushes nothing
  and the repository need not exist; a field prefilled `local/<folder name>`; «Добавить origin» runs `git remote add
  origin https://github.com/<OWNER/REPO>.git` (or `set-url` when a non-GitHub origin exists); «Пропустить» goes on
  unchanged. An invalid value (not `name/name` of `[A-Za-z0-9_.-]`) keeps the step with a note. Example: empty
  folder -> Create -> step -> Enter -> `git remote get-url origin` = https://github.com/local/<folder>.git.
- C2 Accepting the proposal that writes `zplan.process.json` also commits that file alone (`git commit -m "zplan
  profile" -- zplan.process.json`), other changes untouched; the modal line says so instead of «закоммитьте его». A
  failed commit leaves the file, keeps today's readiness item and names the command. An existing file or a fixture
  session commits nothing. Example: accept in a clean repo -> HEAD «zplan profile», `git status` clean.
- C3 Without a TTY nothing changes (line prompts). The PTY tests in tests/test_tui.py that meet the new step answer
  it (or their fixture repo gets a GitHub origin) and check what they checked before. Example: `zplan` with
  stdin piped -> the line prompt as today; PtySmokeTests main-screen test -> exit 0.

Non-goals (reviewers must not require): pushing; creating a GitHub repository; sign-in; English; readiness texts.

Risk: medium (writes to the target's git config and history only on the owner's choice). DoD: `python3.13
devtools/fasttest.py` tests.test_tui_start, tests.test_process, tests.test_tui, tests.test_terminal_planner,
tests.test_tui_strings, tests.test_toolchain: exit 0.
