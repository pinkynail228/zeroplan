# zplan terminal UI principles

Rules every screen must pass before the owner sees it. Derived from the owner's findings
(RELEASE_0.5_SCOPE.md T1-T5, U1-U18) and the welcome-screen review of 2026-10-22.

## 1. Every screen answers three questions, in this order, in fixed zones
| Zone | Question | Example |
|---|---|---|
| Context | Where am I, where does my input go? | `uFactorGame · codex/noir… · 3 файла изменены` |
| Attention | What needs me, and what do I press? | `! Не выполнен вход в Codex … /login` |
| Keys | What can I do right now? | `enter отправить   / команды   ctrl+o проект` |
A zone keeps its place across screens and states; nothing jumps (U16).

## 2. Silent when healthy
- Show a fact only if it changes what the user does. "Engine ready", "version current",
  "logged in" are not shown; their absence of a warning says it.
- Every warning names its fix on the same line (a command or key). No warning without an action.
- Running background work is attention, not status: one line with what, step, elapsed time (U9, U14, U17).

## 3. One fact per line, nothing wraps
- Long values (branch, path, project) are clipped in the middle with `…`; a line never wraps
  into the next row (the 2026-10-22 screenshot: a long branch pushed "есть изменения" under the labels).
- Test every screen with the longest real values: long branch, long Cyrillic project name, 80x24.

## 4. Rows read left to right
- Never place unrelated columns side by side: the eye reads `ветка … /setup` as one sentence.
- Two columns only when the right column belongs to the left one (message -> its action).

## 5. Hierarchy: position, then weight, then colour
- The primary action (the input) is the visual centre; everything else supports it.
- Colour is never the only carrier: every coloured mark also has a symbol (`!` `↑` `◐` `●` `◆`).
- Fixed meaning, terminal ANSI palette only:
  | Colour | Meaning |
  |---|---|
  | bright yellow | brand, focus, current item |
  | red | blocks work, act now |
  | yellow | in progress or unsaved changes |
  | cyan | optional news (update) |
  | green | marker of a project/repo, never "all is fine" decoration |
  | dim | secondary text, hints |
  | bold | names and keys |

## 6. Progressive disclosure
- Commands are not a permanent list: `/` opens them, filtered as you type (U4, U18).
- One dropdown component serves commands, projects and folders: same look, same keys.
- Details (logs, ids, paths, tokens) live behind an explicit action, never in the default view (U3, U10).

## 7. The user's words, not ours
- No internal names: architect, planner, engine, r1, run id, CODEX_HOME (U6, U9, U15).
- Describe outcomes and next steps: "войти в Codex", "обновить zplan", "что сейчас идёт".
- Every on-screen term, state and its EN/RU/ZH text: [GLOSSARY.md](GLOSSARY.md). New term -> glossary first.

## 8. Keys
- One key line, at the bottom, at most 4-5 entries, changes with the mode.
- Every key works in the Russian layout (U13); destructive actions need confirmation.
- No function keys (F1-F12): on a MacBook they need fn or are taken by the system (owner 2026-10-22).
  Every action is reachable by a `/command`; frequent ones also by `ctrl+<letter>`, `esc`, `tab`, arrows.
- `esc` always backs out; `ctrl+q` always quits; closing never stops background work, and the
  screen says so where it matters.

## 9. Terminal-agnostic
- 16 ANSI colours and the terminal's own background; readable with `NO_COLOR`.
- Box drawing and `▀▄█` blocks are safe; braille is used only for the mascot (fallback: half blocks).
- Layout checked at 80x24 and 120x40, and after resize.

## Review checklist (per screen, per state)
1. Can a newcomer say in five seconds where they are, what is happening and what to press?
2. Is anything shown that would not change their next action? Remove it.
3. Does any line wrap or any column read across into another? Fix it.
4. Does every warning carry its action? Is colour backed by a symbol?
5. Does it hold at 80x24, with long values, in the Russian layout?
