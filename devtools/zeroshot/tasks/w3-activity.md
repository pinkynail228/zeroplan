W3 — «Что происходит» pane and bottom bar widgets (0.5.2, docs/RELEASE_0.5.2_PLAN.md, run w3). New module only;
nothing wires it into the app yet.

Why: the journal moves from a tab to an always-visible pane under the canvas, with "last: … ago" so a silent run is
visible, and a bottom bar names the job, its timer and the keys (docs/ui-redesign/WORK_SCREEN.md). The approved look
is the lab: `devtools/ui-lab/work.py` `_render_log` and `_render_bar`, `#log-pane` and `#bar` in
`devtools/ui-lab/work.tcss`. Strings: ids `pane.activity`, `canvas.log_empty`, `live.last_event`, `live.job_timer`, `bar.*`
(terminal_planner/tui/strings.py; do not add or change ids).

Build `terminal_planner/tui/activity.py`:
- `Activity(Static)` widget: `show(lines, silence)` where `lines` are the ready journal lines the app already has
  (`Snapshot.journal`: formatted strings, oldest first) and `silence` is seconds since the last activity or None
  (`flow.silence`). Shows the newest lines that fit its height, oldest first, no wrapping (ellipsis); no lines -> one
  dim `canvas.log_empty` line. No role colouring or alarm parsing in 0.5.2. Border title = `pane.activity`; border
  subtitle = `live.last_event(what=<last line clipped to 40 cells>, m=<silence as m:ss>)` when there are lines and
  `silence` is an int, else empty (never an invented 0:00).
- `bar_text(project, branch, job, stage, elapsed, keys, width)` -> Rich Text, pure: project name bold, " · branch",
  then the job: None -> `bar.idle`; "planning" -> `bar.job_planning(clock=<elapsed h:mm:ss>)`; "running" ->
  `live.job_timer(stage=stage, h=<elapsed h:mm:ss>)`; "approve" -> `bar.waiting_approve`; "merge" / "question" /
  "error" -> `bar.waiting_merge` / `bar.waiting_question` / `bar.stopped_error` with `stage=stage` (error in red);
  `elapsed` None -> the clock shows "—". Then the keys: `keys` is a list of (key, string id among `bar.key_*`) pairs,
  shown as "key label"; `bar.continue` appended only when job is "planning" or "running" and at least 24 cells remain;
  never wider than `width` (ellipsis). strings.py is frozen (no new ids).
- `Bar(Static)` widget that shows `bar_text` for its own width on `update_bar(...)` and on resize.
- CSS in `DEFAULT_CSS`, matching the lab.

Write-set: terminal_planner/tui/activity.py, tests/test_tui_activity.py. Do not edit any other file.

Acceptance criteria:
- A1 With 10 lines in a 4-row pane only the newest 4 show, oldest first; no lines -> the `canvas.log_empty` text.
- A2 Subtitle with silence 187 reads the `live.last_event` text with "3:07"; silence None or no lines -> empty subtitle.
- A3 A line wider than the pane ends in an ellipsis and does not wrap.
- A4 `bar_text` for each job value contains the matching strings.text result; running with elapsed 3725 shows
  "1:02:05"; elapsed None shows "—".
- A5 `bar_text` is never wider than `width` for widths 40, 80, 120; `bar.continue` shows at 120 and not at 40.
- A6 Tests run in a minimal test App without a project, controller or network.

Non-goals: wiring into app.py, role colours and alarm rows (0.6.0), the Журнал tab, spinner animation, new string ids, translations.

DoD: `python3.13 -m unittest tests.test_tui_activity tests.test_tui_strings tests.test_toolchain tests.test_reference` with TMPDIR short (preamble), all green.
