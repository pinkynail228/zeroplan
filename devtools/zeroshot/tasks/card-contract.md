Card contract for the 0.5.2 card runs (i3b, i3c, i3d, i3e1, i3e2, i3-chat-inline); frozen on main at the i3a merge.
The code comment above `CARD_ROUTES` in terminal_planner/tui/app.py is the source; this is its summary.

- A card is a `cards.CardSpec`; builders in terminal_planner/tui/cards.py (`plan_card`, `merge_card`,
  `question_card`, `error_card`), strings `card.*` in strings.py. Keys are `kind:<id>`; `card_kind(key)` = kind.
  The milestone-card keys carry the plan revision the card belongs to: `merge:r<version>:<milestone>:<attempt>`
  (i3c), `question:r<version>:<milestone>:<attempt>` (i3d) and `failed:r<version>:<milestone>:<attempt>` (i3e2);
  `failed:plan:<version>` already carried its revision and is unchanged. The version is the current plan revision
  (`snapshot.version`), so a card the owner closed under one revision never suppresses the same stage's card under
  the next, and caches keyed by a card key are per revision.
- Showing: `CARD_SOURCES[kind] = callable(screen) -> iterable of CardSpec`. `render_state` shows what the source
  returns and takes off that kind's open cards it no longer returns, so a stale card never acts. A key the owner
  dropped, or a closed card, is never brought back.
- Commands: a card button and a typed `/command` both go through `MainScreen.run_command(name, argument, key)`
  (`COMMAND_ACTIONS`). Commands shared by kinds (`/approve`, `/decline`) go through
  `CARD_ROUTES[(command, kind)] = callable(screen, argument, key)`; a typed line (key None) acts on the newest open
  card whose kind routes the command.
  Card-only commands `/retry` and `/details` (error cards) are routed the same way; they are not in slash.py.
- `MainScreen.close_card(key, done_text)` leaves a receipt without buttons; `drop_card(key)` takes it off.
- `AUTO_END_CARDS`: end states (`EndView.state`) whose automatic RunScreen after a watch is replaced by the card;
  [o] still opens RunScreen.
- `NoteScreen(..., enter=True)`: a card-origin note submits with enter, esc cancels.
- In narrow mode an open card shows the chat pane (`show_chat`).

Parallel rule: these runs edit app.py at the same time. Register with module-level statements in one block of your own at
the end of app.py (`CARD_SOURCES["plan"] = ...`, `CARD_ROUTES[("/approve", "plan")] = ...`,
`AUTO_END_CARDS.add(...)`), never by editing the literals; add only your kind's methods and tests; new strings ids in one block at the end of `card.*`; never edit another kind's rows
or move other code.

Tests on a stand-in screen/app that call `render_card_sources` patch `CARD_SOURCES` to their own kind
(`patch.dict(ui.CARD_SOURCES, {"kind": ui.CARD_SOURCES["kind"]}, clear=True)`): other kinds' sources read app state
the double lacks (2026-10-24: i3b/i3e2 broke when i3e1's `ready` source merged).
