W2 — slash palette widget (0.5.2, docs/RELEASE_0.5.2_PLAN.md, run w2). New module only; nothing wires it into the app yet.

Why: commands replace the letter hotkeys (they break in the Russian layout, baseline C02). Typing `/` in the chat input
shows the matching commands with their descriptions. The approved look is the lab: `devtools/ui-lab/work.py`
`on_input_changed` and `#palette` in `devtools/ui-lab/work.tcss`. The command registry exists:
terminal_planner/tui/slash.py (`COMMANDS`, `parse`, `matches`, `available`, `problem`); descriptions are strings ids
`cmd.*` (terminal_planner/tui/strings.py).

Build `terminal_planner/tui/palette.py`:
- `Palette(Static)` widget: `show_for(value, state)` hides itself unless `value` starts with "/"; otherwise lists
  `[c for c in slash.matches(value, state) if slash.available(c, state)][:7]` (matches orders but does not filter):
  the name in bold, its `strings.text(description id)` dimmed, one row each, no wrapping (ellipsis); an empty list ->
  one dim row `strings.text("note.palette_empty")`. slash.py and strings.py are frozen (no new ids or API).
- `submit(line, state)` -> `Submitted(command_name, argument)` when `slash.problem` is None, else
  `Refused(note_text)` where the text is `strings.text(problem id, ...)` with the values the ids need; a line not
  starting with "/" -> None. Pure function, no widget needed.
- CSS in `DEFAULT_CSS`, matching the lab's palette (docked above the input, auto height).

Write-set: terminal_planner/tui/palette.py, tests/test_tui_palette.py. Do not edit any other file.

Acceptance criteria:
- A1 `show_for("/", "idle")` lists exactly the first 7 of the commands available in idle, in `slash.matches` order,
  with their descriptions from strings.text; no unavailable command appears.
- A2 `show_for("/ap", "plan_ready")` lists /approve only; `show_for("/ap", "idle")` shows the `note.palette_empty` row.
- A3 `show_for("hello", s)` and `show_for("", s)` hide the palette.
- A4 `submit("/open README.md", "idle")` -> Submitted("/open", "README.md"); `submit("/merge", "idle")` -> Refused with
  the `note.not_now` text; `submit("/nope", "idle")` -> Refused with the `note.unknown_command` text; `submit("hi", s)`
  -> None.
- A5 At 40 columns no palette row is wider than the widget (Pilot, minimal test App).
- A6 Tests run without a project, controller or network.

Non-goals: wiring into the chat input, executing commands, keys, new string ids, translations.

DoD: `python3.13 -m unittest tests.test_tui_palette tests.test_tui_slash tests.test_tui_strings tests.test_toolchain
tests.test_reference` with TMPDIR short
(preamble), all green.
