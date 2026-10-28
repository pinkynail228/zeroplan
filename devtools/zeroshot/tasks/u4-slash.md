U4 — the `/` command registry for the chat input (release 0.5.2, docs/RELEASE_0.5.2_PLAN.md, run u4-slash).

Goal: `terminal_planner/tui/slash.py` knows the main screen's commands: their English names, the id of their
description, the screen states where each one acts, how a typed line parses, and which commands the palette lists for
a typed prefix. Pure data and functions; nothing imports it yet (integration run i2 wires it to the app's actions).
Approved behaviour: lab `devtools/ui-lab/work.py` (`COMMANDS`, `on_input_changed`, `command`).

Commands (name -> description id): /plan cmd.plan, /approve cmd.approve, /decline cmd.decline, /merge cmd.merge,
/diff cmd.diff, /open cmd.open (one argument: a project-relative path), /status cmd.status, /stop cmd.stop,
/language cmd.language (optional argument: en|ru|zh), /setup cmd.setup, /help cmd.help, /quit cmd.quit.
Screen states: idle, draft, planning, plan_ready, running, merge, question, error.
Acts in: /plan draft; /approve plan_ready, question, error; /decline draft, plan_ready, question; /merge merge;
/diff merge, idle; /open idle, draft, plan_ready, merge, question, error; /stop running (stopping planning has no engine action yet: 0.6.0); the rest everywhere.

Write-set: terminal_planner/tui/slash.py (new), tests/test_tui_slash.py (new). Nothing else.

Acceptance criteria:
- A1 `COMMANDS`: a tuple of frozen records `Command(name, description_id, states, arg)` with exactly the twelve
  commands and state sets above, in that order.
- A2 `parse(line) -> Parsed | None`: None when the line (after stripping spaces) does not start with "/"; otherwise
  the command (or None when unknown), the raw name typed, and the argument text (rest of the line, stripped).
  Names match case-insensitively; a Cyrillic look-alike typed on a Russian layout is not translated (the user sees
  "unknown" and the palette).
- A3 `available(command, state) -> bool` follows the table; an unknown state raises ValueError.
- A4 `matches(prefix, state=None) -> list[Command]`: commands whose name starts with the typed first word, in
  registry order; with a state, the ones that act in it come first, the rest keep their order after them; "/" alone
  lists all.
- A5 `problem(parsed, state) -> str | None`: None when the command can act; otherwise an id: `note.unknown_command`
  (unknown name), `note.not_now` (not available in this state), `note.needs_arg` (/open without a path),
  `note.bad_language` (/language with an argument outside en|ru|zh).
- A6 One test per criterion.

Non-goals: executing commands, palette drawing, the string texts themselves (ids only), aliases, history, completion
of file paths.

DoD: `python3.13 -m unittest tests.test_tui_slash tests.test_toolchain tests.test_reference` with TMPDIR short, green.
