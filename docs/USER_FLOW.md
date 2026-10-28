# zplan 0.8: user flow

## Full-screen shell and `--plain`

On a terminal `zplan` opens a full-screen shell (Python ≥ 3.11 and Textual; see INSTALLATION.md). The shell has
no letter keys: every action is a `/` command typed in the chat input (see «`/` commands»), every screen and modal
answers with buttons, and the keys are `Tab`, `←`/`→`, `↑`/`↓`, `PgUp`/`PgDn`, `Enter`, `Esc` and `Ctrl+Q` (see
«Keys»). The part of this document that starts at its «Line UI» heading describes the line UI, which `zplan --plain`
always gives you and which is used automatically for `TERM=dumb`, piped stdin/stdout and every subcommand
(`status`, `doctor`, `setup`, `login`, `roles`, `profile`); those never print escape codes, and the line UI keeps its
letter keys. The architect chat belongs to the full-screen shell only: the line session says so on its home screen
and keeps every other action.

```
╭─ Conversation with the architect ╮╭─ my-project · nothing runs ───────────────────────╮
│ CODEX_HOME … · openai         ││ Scheme  Plan                                      │
│ architect · 21:01             ││ ◌ picking the first task · waiting                │
│   here is the plan draft …    ││ ↻ tasks in turn                                   │
│ you · 21:02                   ││ │ ◌ picking a task · waiting                      │
│   make a CSV export           ││ │ ◌ checking the pick · waiting                   │
│ ╭───────────────────────────╮ ││ ◌ recording the result · waiting                  │
│ │ › Write to the architect… │ │╰───────────────────────────────────────────────────╯
│ ╰───────────────────────────╯ │┌─ What's happening ────────────────────────────────┐
╰───────────────────────────────╯│ nothing has happened yet                          │
                                 └───────────────────────────────────────────────────┘
```

The left pane is split: the planner progress and the live run watch take their lines off the top (at most
40% of the pane), the architect chat gets the rest, so both stay visible at once and neither hides the other's
latest state for more than one key press; at the pane's bottom sits the prompt box (`›` and the input), and
the `/` palette opens straight above it, inside the same pane. With nothing to report the pane is the chat, its
prompt box and, while `/` is typed, the palette.

The bottom bar names the project, the branch, the job and the keys that always work: while nothing runs it reads
`notes · main · nothing runs · ←→ tabs · / commands · ctrl+q quit` (`esc close` joins it while a job runs or a
file or diff tab is open). Decisions (merge, an answer, the plan, a failure) arrive as cards in the chat, answered
by the card's buttons or the matching `/` command; every other action is a `/` command typed in the chat input.

The right column is two tabs, «Scheme» and «Plan», over the always-visible «What's happening» pane. «Plan» is the
plan of the current revision (the summary, one line per milestone, the live lines of an active attempt and the
hint); the milestone row `↑`/`↓` select there is the one the `/run`, `/attempt`, `/answer`, `/log` and `/details`
commands act on. «Scheme» is the
live state: the live lines of the active attempt first, then the planner's or the run's lines the area above the
chat shows (the same sources, in the same order), inside a frame whose border wraps the tab strip and whose border
title names that state (`my-project · nothing runs` while nothing runs, `M2 <title> · running` while stage M2 runs);
with nothing to report it says so and repeats the snapshot's own
«Next:» step, so the command or button that starts the next step is named there too. Under the canvas the «What's happening»
pane is always visible, whichever tab is shown: it keeps the observed attempt's own session log — its stored
journal entries, one per line, oldest first, the newest lines that fit — with `last: … · m:ss ago` in its
bottom border while a live run's quiet is measured, and the one line «nothing has happened yet» while nothing has
been recorded. The tab shown at start is «Scheme» while a planner or a milestone attempt is active, else «Plan»,
and the app never switches a tab by itself afterwards: `←`/`→` do, from anywhere on the main screen, and a click on
a tab label switches it too; the bottom row names the arrows (`←→ tabs`). While the chat input holds text the
arrows keep moving its cursor and switch no tab. `Tab` shows the «Plan» tab and moves the focus to the pane; `Tab` again returns to
the input, leaving the shown tab where it was. A return to «Plan» after reading «Scheme» gives the pane its focus
back when it had it, so the pane's `↑`/`↓` keep working across the trip. The planner and run lines above the chat stay
exactly where they were.

Below 100 columns (`app.NARROW_COLUMNS`) the shell no longer shows the chat and the canvas side by side — at 80x24
both would be too narrow to read — and shows one pane at a time, full width. The tab cycle then gains «Conversation» in
front of the canvas (`Conversation` -> `Scheme` -> `Plan` -> the open file/diff tabs -> `Conversation`), driven by the same
`←`/`→` (an input holding text still keeps its cursor). The first frame is «Conversation»: the chat alone, its pane
titled `chat.title_narrow` with the arrow hint, and no canvas. The canvas strip — shown whenever the canvas page is
— carries a «Conversation» label so the cycle's first page is named, and the canvas keeps the tab that was active;
opening a file or a diff (`/open`, `/diff`) or re-opening a file brings the canvas page up, and `show_chat()`, which
the card runs call when a card appears, brings the chat back. Input, palette and the key bar stay full width in both
modes: the chat pane, its prompt box and the `/` palette above it all take the full width. At 100 columns and
up both panes show again, the canvas keeping its tab, and nothing (no logo, no header) sits above the panes.

The bottom row of the main screen is one status bar: the project and the branch (the only place they show since
the header went), what is
running with its clock (the planner `drafting the plan 0:00:12`, a milestone `M1 running 0:03:07`, a stage waiting
its turn `M1 waits to merge`, an error `M1 stopped: error · /status`, or `nothing runs` while nothing runs; `—`
stands in for a clock that is not known yet), and the four keys the screen offers: `←→ tabs`, `/ commands`,
`esc close`, `ctrl+q quit`. A screen or modal keeps its own key row (the keys that work in it, named as the
catalog labels them) under its buttons.

Typing `/` in the chat input opens a command palette just above it: the commands the current state allows, the
word after the `/` narrows the list, and deleting the `/` closes it. `Enter` runs the chosen line; a line that is
not a command still goes to the chat as a message to the architect. A command that cannot act now (or is not wired yet) shows a note
above the chat and keeps the text in the input. `Esc` closes the palette (clearing its input) before it cancels the
turn.

Two more kinds of read-only canvas tab open beside «Scheme» and «Plan», and only while no work runs (neither the
planner nor a milestone): a project file and a finished stage's diff. `←`/`→` cycle every open tab, the file and
diff tabs included, and `Esc` on such a tab closes it and returns to the tab that was active before it — «Scheme»
and «Plan» themselves never close. A file tab is titled with the file's name and shows its first lines with line
numbers; at most three file tabs stay open at once and opening a fourth closes the oldest. A stage's diff opens as
one tab titled «Changes <stage>», replaced in place when another is asked for. While the planner or a stage runs
both open nothing: the status line above the chat says so, and a tab already open stays. A name outside the project
or a missing file opens no tab either — the viewer's own refusal text lands on the same status line. The run-end
screen's button «changes» still opens the diff in a scrollable modal.

### Keys

A letter typed in the chat input is text, never an action. Help is `/help` and settings are `/setup`; no key opens
either.

| Where | Key | Action |
| --- | --- | --- |
| anywhere | `Ctrl+Q` | Quit; the terminal is restored. Runs and the plan are untouched. During a submission, start, merge or setup it first finishes the job («Finishing the operation without interrupting it. Exit right after.») and then exits. A running architect turn is cancelled at once and the exit follows within seconds (its process group goes with it); a watch slice is cut at once too, and the run it watched keeps going |
| main | `Tab` | Move focus between the input line and the plan pane; the pane lives on the «Plan» tab, so the move shows that tab |
| main | `←` / `→` | Show the previous / next canvas tab — cycling «Scheme» -> «Plan» -> «Scheme». The keys work with the focus anywhere on the main screen, the plan pane included; while the chat input holds text they move its cursor instead and switch no tab. A click on a tab label switches to it too |
| main, plan pane | `↑` `↓` | Select a milestone: the row the `/run`, `/attempt`, `/answer`, `/log` and `/details` commands act on |
| main, plan pane | `PgUp` / `PgDn` | Scroll the chat history up / down |
| main, input line | `Enter` | Send the typed message to the architect as one turn, or run the typed `/` command. While the chat is preparing or a turn runs nothing is queued: the refusal stays on the chat line and the text is kept |
| main, input line | `Esc` | Close the `/` palette and clear its input when it is open; otherwise cancel the running architect turn (SIGTERM, then SIGKILL after 2 s, its own process group); a milestone keeps running. The partial reply is shown marked `(interrupted)` |
| plan screen, run-end screen, Settings, confirmations, notes | `Tab` / `←` `→` | Move to the next / previous button (in a note: from the text field to its send button) |
| plan screen, run-end screen, Settings, confirmations, notes | `Enter` | Press the focused button. In a note's text field `Enter` is a new line and the note is sent by its button; the one exception is the owner-question card's answer note, where `Enter` in the text field sends the answer at once |
| plan screen, run-end screen, diff, details | `↑` `↓` `PgUp` `PgDn` | Scroll the screen |
| plan screen, run-end screen, Settings, notes, diff, details, help | `Esc` | Close, or go back one level (the plan screen closes its open note first); nothing is changed. In a confirmation `Esc` is «no» |

### `/` commands

Typing `/` in the chat input lists the commands the current state allows; the word after it narrows the list.
Commands act in the screen's state: `idle` (nothing to decide), `draft` (a goal-draft card is open), `planning`
(the planner runs), `plan_ready` (a plan is proposed), `running` (a stage runs), `merge` (a stage waits for its
merge), `question` (a stage needs an owner answer) and `error` (a failure or a blocked start).

| Command | Acts in | What it does |
| --- | --- | --- |
| `/plan GOAL` | `idle`, `draft`, `error` | Start the planner on the goal typed after it; readiness is re-checked first and a goal is never lost. With no text it decides the open goal-draft card (the same as its «yes, draft the plan») or sends the unsent revision |
| `/approve` | `plan_ready`, `question`, `error` | Approve the proposed plan (the plan card's «yes, approve»); on an owner-question card send the answer draft, or open the answer note when there is none, and `/approve simplify`, `/approve split` or `/approve skip` sends that quick answer. With no card it opens the plan screen, whose button «approve» approves |
| `/decline` | `draft`, `plan_ready`, `question` | Say «no» to the open card: a goal draft is dropped from the conversation, a proposed plan opens the revision note, an owner question opens the answer note, where `Enter` sends |
| `/run` | any | The «Next:» action of the selected milestone (else the first one that has an action): start a ready one (the confirmation names milestone, plan revision and attempt; its buttons are «yes» and «no»), resume a recoverable failure, begin a new attempt, or check an unconfirmed submission or stop |
| `/stop` | `running`, `planning` | The stop confirmation of the running milestone — it names that milestone even when another row is selected — or of the planner. The unfinished work of the attempt is not accepted |
| `/merge` | `merge` | Merge the stage whose card is open, with no modal; with no card open it opens the run-end screen, which holds «merge» and «changes» |
| `/diff` | `merge`, `idle` | Open the selected finished stage's diff as a canvas tab |
| `/open PATH` | `idle`, `draft`, `plan_ready`, `merge`, `question`, `error` | Open the project file as a read-only canvas tab (`Esc` closes it) |
| `/view` | any | Open the plan screen; with no plan a note names `/plan GOAL` |
| `/attempt` | any | Open the run-end screen of the selected milestone's attempt; a running attempt is watched again |
| `/answer` | any | Open the newest actionable answer draft of the selected milestone in the answer note, prefilled and editable; starts nothing. With no draft a note says so |
| `/log` | any | The last lines of the Zeroshot log of the running or failed attempt, read on request, never on refresh |
| `/details` | any | The outcome first, then the plan, diagnostics last; on a failure or readiness card it is that card's «details» |
| `/status` | any | Switch the canvas to the «Scheme» tab |
| `/setup` | any | Settings |
| `/new` | any | Start a new architect session (refused while a turn runs); the transcript keeps a `reset` entry |
| `/help` | any | The key and command help of the current screen |
| `/quit` | any | Quit; the terminal is restored (the same as `Ctrl+Q`) |
| `/language [CODE]` | any | Not offered in 0.8.0: the interface is English only (see «UI language»); the command is not listed and a typed `/language` is an unknown command |
| `/retry` | card only | Never typed: the «try again» button of a failure card or of a readiness card |

### Screens and buttons

Every screen below answers with buttons; `Tab` and `←`/`→` move between them and `Enter` presses the focused one.
The labels are the catalog's (docs/REFERENCE.md lists them).

The plan screen (`/view`) shows the goal, the planner's progress and the proposal. Opening it sends nothing; only
its button «start the planner» starts the planner. Its buttons follow the plan's state:

| Button | What it does |
| --- | --- |
| «start the planner» | Re-check readiness and send the goal; a stale unsent revision is rebuilt on the current project first (one line says «rN → rN+1») |
| «new revision» | Prepare a new revision of the same goal on the current project without calling the model |
| «log in» | Codex login in the terminal (the screen is suspended and restored) |
| «watch» | Watch the planner again |
| «log» | The tail of the planner's Zeroshot log |
| «approve» | Approve the revision (asks «yes» / «no» first); nothing is started |
| «approve despite the check» | Approve a plan the critic rejected, with a typed reason in a note |
| «revise» | Open the revision note: describe the change, press «send revision»; a new revision is planned |
| «decline» | Decline the proposal (asks «yes» / «no» first) |
| «details» | Full requirements and checks; for a failed planning run the diagnostics |

The planner is stopped with `/stop`. `Esc` closes an open note first, then goes back one level.

The run-end screen opens with `/attempt` (or `/merge` with no card open, or a card's «details»). It shows the
outcome and only the buttons the state allows:

| State | Buttons |
| --- | --- |
| `done, waiting for merge` | «merge» (asks `Merge the result of M1 into main?`), «changes», «details» |
| `conflict` | «retry the merge», «changes», «details»; or merge `zplan/...` by hand, commit, then `zplan` |
| `needs an answer` | «accept» (when a proposal exists), «answer» (the answer note, then a new attempt), «leave» |
| `blocked` | «answer» (answer and restart), «to plan» (a scope change becomes a plan revision) |
| `failed · can continue` | «continue» (the same attempt in its worktree), «new attempt» (from the current HEAD), «plan», «back» |
| `failed · cannot continue`, `stopped` | «new attempt» (from the current HEAD; the attempt note is optional), «to plan» |
| `submission status unknown` | «check» (reconcile with Zeroshot, never a second submission) |

Every run-end screen also has «log» (the tail of the Zeroshot log) when the attempt has a native run that failed
or is still going, and «details» (the attempt's stored journal entries, a read-only screen); `Esc` closes it.

Notes are short text screens: the answer note, the revision note and the new-attempt note. Type in the text field,
`Tab` to the send button («send», «send revision», «new attempt») and press `Enter`; `Esc` closes
without changes, and an empty answer starts nothing. The owner-question card's answer note is the exception: `Enter` in
its text field sends at once. Settings holds the readiness checks and the roles; its buttons
are «install» (the pinned tools, the same as `zplan setup`, the output streams into the setup log), «log in»
(Codex login in the terminal, then a re-check), «check» (check again) and «roles» (show or hide the roles, model
and effort per role, read-only); `Esc` goes back. The setup log reads `The install log is empty so far: use the "install" or "log in" button.` until there is
one. The first start in a project whose process profile was never decided shows «accept» and «later» (see «First
start in a project: the process profile»); `Ctrl+Q` leaves without deciding.

### UI language

0.8.0 ships an English-only interface: the shell's texts (the bottom bar, the chat pane's titles and status lines, the
canvas tabs «Scheme»/«Plan» and the plan pane's own lines, the key hints and the input placeholder), the line UI, the
modals and the plan and journal lines the engine produces are all English. The catalog (`terminal_planner/tui/strings.py`)
keeps its Russian and Chinese columns for a later localisation release, but only English is offered: there is no
language chooser and `/language` is not listed. The setting is kept in `ui.json` outside the project
(`$XDG_CONFIG_HOME/planning-kit/ui.json`, by default `~/.config/planning-kit/ui.json`); a stored `"ru"` or `"zh"`
(written by an earlier version) is read as English. Conversation turns and events stored by 0.7.x stay as they were
written, in Russian.

The plan pane is the same overview as `zplan status`, refreshed every few seconds without starting or
polling anything; a slow check or setup never blocks the keys. Planning (goal, planner progress, proposal,
approve / revise / reject) works in the shell with the same rules as the line UI: the goal is typed as
`/plan GOAL` (or an architect's goal draft is accepted on its card), readiness is re-checked right before the
planner is called, a goal is never lost, a stale unsent revision is replaced only by the plan screen's button
«new revision» (or rebuilt by «start the planner»), and a sent or unconfirmed submission is observed, never
sent again. Planner progress goes to the left pane while you keep typing; `Ctrl+Q` leaves the planner running and
reopening the shell resumes watching it.

The architect chat is advisory and read-only: it never writes proposal, approval or run state, and its
preparation (install, login and version checks, then the chat itself) runs off the event loop, so the pane shows
«preparing chat…» until it is ready and every other key keeps working meanwhile. Its header shows the effective
`CODEX_HOME`, provider, model and the session turn/token counters, refreshed after each turn. One message is one
turn on the chat's own thread, so a turn never blocks the milestone observe loop; streamed text appears live on
a «The architect is thinking… M:SS» line and partial text of a cancelled or failed turn is kept and marked. A missing install,
login or `architect` role shows the plain refusal with its remedy (`zplan setup`, Codex login, the roles), and
the rest of the shell is unchanged. After a restart the history is rebuilt from the stored transcript; two
windows on one project can both send, each reloading the other's turns, and a send or reset while the other
window holds the lock is refused with `architect.locked` and writes nothing. On screen those header fields and the
pane's one state line sit in a block above the conversation, and the conversation itself is a scroll of one
row-block per entry — the owner's lines, the architect's replies, the system notes and the decision cards — so
`PgUp`/`PgDn` page through it (with the focus on the plan pane). A new entry, or a
message the owner sends, returns the view to the bottom; a live «The architect is thinking… M:SS» update or a background refresh
leaves a view the owner scrolled up where it is.

The chat tells the architect to put a proposed goal in a fenced `zplan-goal` block and a proposed answer for a
milestone in a `zplan-answer <milestone id>` block. Only the final reply of a successfully completed turn is read
for drafts (never streamed partial text, never a cancelled or failed turn), and each draft shows as its own labelled
line, `architect · goal draft: …` for a goal and `architect · answer draft M1: …` for an answer, always copyable. A
malformed or oversized block, a block past the fifth, an unknown milestone and a block inside another fenced block
stay ordinary text. Every draft line is `<reply> · <label>: <text>`: the reply the draft comes from is named by
its place among the replies the pane holds (`reply 1`, `reply 2`, …), so two replies that each carry a draft are
told apart. A goal draft is a decision card: the newest actionable goal draft of the retained history — its entry on its own
row, label first — shows as the card «Goal draft» in the chat (see «Decision cards»), and the whole draft opens
as a canvas tab. Nothing is typed again and no form opens: the card's «yes, draft the plan» (or a typed `/plan`)
starts the planner from the draft's own text and identity, and a goal the owner types as `/plan GOAL` is never
overwritten by a draft. The draft keeps its original identity rather than the current view's, and `/plan` re-checks
it against the current plan before the planner starts: a stale draft is refused with «draft is outdated» and its
reason — a new revision, or the plan state changing, including `no plan` that became a plan — writing nothing and
starting nothing; the draft's text stays copyable. An answer draft is opened by `/answer`: it opens the newest
actionable answer draft of the milestone the plan pane selects in the answer note — the draft's text prefilled and
editable, its original attempt identity held apart from the screen — and starts nothing; a milestone with no
actionable answer draft gets a note saying so (the owner-question card offers «send the answer draft» only for a
draft that exists). The note's button «send» sends the answer through the existing path behind a provenance
re-check on the worker: a draft whose plan, attempt, run or delivery moved on, or whose milestone finished, is
refused with «draft is outdated» and its reason and sends nothing (no export, no run finished), and the draft's text
stays copyable.

Each draft carries the identity of the state the turn was sent with, frozen at send time and never bound to the
current screen: a goal draft carries the plan identity — `no plan`, or the pair (revision number, plan state),
where the state is the plan status the plan pane names together with whether the owner approved over a rejected
gate, so the revision number alone is not enough. `no plan` is the confirmed absence of a plan; a turn sent before
the first snapshot arrives names no plan identity at all, because an unknown state is not the absence of a plan,
and its drafts are not actionable. An answer draft carries the attempt token of that milestone in the turn's
snapshot, so two answers keep their own and an unknown milestone, or a milestone without an attempt, gives no
actionable draft. The reply, its drafts and that identity are stored with the turn's success mark (in the architect
store outside the checkout), so a restart or a second window rebuilds the drafts with their original identity; a
reply stored without that metadata comes back as copyable text only.

Milestones follow the same rules in the shell and in the line UI, because both call one delivery service:
readiness is re-checked before a start, a start never sends a second submission for an attempt that already
has one (an unconfirmed submission is shown as `submission status unknown` and only checked), and a merge is
confirmed. Progress comes in short slices, so typing and navigation stay responsive; the plan pane rows show the
live state (`running · task 1/3 (T2) · review`). `Ctrl+Q` while a milestone runs leaves it running;
reopening the shell observes it again, also when it was started in the line UI. The end-of-run screen
shows the outcome and only the actions the state allows (done, awaiting merge with the diff, conflict,
needs an owner answer, blocked, recoverable or final failure with its cause, stopped, unknown submission). If the
run, attempt or plan revision changed while a screen was open, the action is refused and the screen is
redrawn with the current state. A stop that Zeroshot did not confirm is shown as `stopping`; `/run` on
the milestone resends it. A scope change (the button «to plan» of a blocked or needs-owner screen) becomes a plan revision.

### Decision cards

A decision the chat leads to is a card *in the conversation*: the card mounts into the chat's own history right
after its newest entry at the moment it is shown, and it keeps that place — a card that just appeared is scrolled
into view with its own buttons, the view resting at the conversation's bottom (a goal draft followed by the
proposed plan fits with both cards at 80x24: in the narrow pane a card sits flush in the conversation — no indent
and no drop below it, like the history's own entries — and leaves out the dim command line under its buttons, the
very commands those buttons stand for, so two cards and every button fit the view at once). A card re-read on a live render (a source whose own `HH:MM` moved on
with the clock) is that card replaced in place: it stays where it stood and the view the owner scrolled is left
alone — only a card that was not in the history yet is scrolled to. A card the owner closes stays where it stood as
its own receipt (the `✓` line, no buttons); only a dropped card — or one whose source stops returning it — leaves
the history, and a dropped key is never shown again. Its first card is the goal draft: the newest actionable goal draft of a reply,
while it has not been decided yet, shows «Goal draft» in the chat — the card text asks
whether to draft the plan from that draft and points to the full text, its two buttons are «yes, draft the plan» and
«no» (they run `/plan` and `/decline`, and typing either line in the chat does the same), it carries its own
`HH:MM` — the time of the reply the draft came from, not the moment the card is drawn — and the whole draft opens
beside «Plan» as the «Goal draft» canvas tab (`Esc` closes it like a file tab). While that card is open the
state is `draft` — a card is a decision of its own, so it stays
`draft` even while a proposed plan, a failed planning run or a running stage would otherwise be the screen's state,
and the typed `/plan` reaches it exactly as the button does. A card belongs to the reply it came from: its key
carries that reply's own place in the stored transcript, so two identical replies are two cards, a refresh and a
poll of the same history never bring a decided card back, and a newer card mounts below the open ones (a closed
receipt keeps its place for good; a reopened shell shows the newest undecided draft again).

The card's «yes» — or a typed `/plan` — re-checks the draft against the current plan first: a stale draft
(`draft is outdated` and its reason) is refused on the status line, nothing starts and the card stays; otherwise
the planner starts from the draft's own text and identity with nothing typed in between, and the card becomes
`✓ sent to the planner HH:MM` with no buttons (a second `/plan` finds no open decision then). A submission the
planner did not start — a readiness refusal, a revision that turned stale before it reached the planner, or an
error from the controller — writes no receipt: the card stays an open decision and the reason shows on the status
line above the chat, for the button and the typed line alike.
A stage that is `done, waiting for merge` has the card of its own: «M1 ready» shows in the chat with the
numbers of the attempt's own tasks line («2 of 3 tasks accepted, the final check passed. Merge into main?»; while
that line is not read yet the same card asks without the counts), the buttons «merge» and «see the changes»,
and its `HH:MM` — the moment the card appeared. The automatic end-of-run screen no longer opens for this state: the
card is the decision, and `/attempt` still opens the run screen with its button «merge» when the owner wants it. «merge» — or a
typed `/merge` — merges exactly that attempt, with no confirmation modal: the outcome goes on the status line above
the chat and the card becomes `✓ M1 merged into main HH:MM` with no buttons. A stage whose accepted attempt was not
exported yet (a cut export, a reopen) is exported by that same first click — «merge» or «see the changes» —
exactly as `/attempt` would, so one click still suffices; a refresh never exports. Uncommitted changes of the project never block
the merge; one that would be written over (a changed path, or a parent of it, that exists as an untracked, ignored or
modified file) turns the card into the red card that names those files, with «merge later» (`/merge later`: the card
closes, the branch is kept) and «show the differences» (`/diff`). A refusal, or the merge's own conflict,
leaves the card where it is — a conflict also moves the stage to `conflict`, so the card goes with the state that no
longer asks for a merge and the run screen (or the hand merge it names) remains. A second `/merge` while the first
is in flight is refused with `Already in progress: …`. The typed `/merge` reaches that card even when another decision
card is open beside it (a goal-draft card sets the screen's `draft` state): the merge card a typed command names
answers it exactly as its own button does, while the other card's commands stay in reach. «see the changes»
selects that stage in the panel and opens its diff as a canvas tab (`Esc` closes it like any other).
«no» — or a typed `/decline` — drops the card from the history, and that reply's draft never brings a card back
(an identical reply stored later is a card of its own); a decision the owner did make keeps its card as the receipt
where it stood.

Its second card is the owner question. A milestone whose attempt stopped on `needs_owner` (the row reads
`needs an answer`) shows the end screen's own question body in the chat — its `Question:` and task lines, fetched once
for that attempt — titled «Your decision is needed · <milestone>» and carrying its three quick answers «simplify»,
«split», «skip» (each answers the attempt with that word and watches the new one). The card sizes that body
to the room it has and keeps it to six lines at most — the question and every button stay visible at 80x24 and after a
resize, and a body that does not fit is elided. When an answer draft of that milestone is in the chat, a leading draft
button sends it through the answer-draft path; its wording is always the full «send the answer draft», and the
card wraps its buttons onto a second row where the full label and the three quick answers cannot share one (its label
is never shortened or dropped). A draft that went stale is refused on the status line and the card stays. The automatic end-of-run screen no longer opens at a `needs_owner` end — the card is the decision
— and `/attempt` still opens that screen. `/decline` opens the answer note, where `Enter` in the text field sends the
owner's own words at once (`Esc` keeps the card); `/approve` with no argument sends the answer draft when there is one and opens the note otherwise,
`/approve simplify`, `/approve split` or `/approve skip` sends that choice's word, and any other argument is refused. A started answer turns the card into `✓ answer sent
HH:MM`; a refusal (a stale draft, an unready start, an error) keeps it an open decision and shows the reason on the
status line. The card key names the attempt (`question:<milestone>:<attempt>`), so each new attempt gets its own card,
and a closed one keeps its place like the draft's receipt.

The proposed plan is the next card: while a plan is proposed (its revision is the current one and its status is
`proposed`) the chat holds a card «Plan · N stages · M tasks», the counts taken verbatim from the plan summary
line the «Plan» tab shows (a proposed plan whose line carries no counts shows just «Plan»), with the buttons
«yes, approve» and «no, revise». «yes, approve» — or a typed `/approve` — approves in one click, with no
plan screen and no confirmation modal: the decision runs once and the card becomes `✓ approved HH:MM` with no
buttons. A refusal — the plan is no longer the current proposed one — keeps the card open and shows the reason on
the status line above the chat. «no, revise» — or a typed `/decline` — opens the plan screen's revision note (type the change, `Tab` to the button «send revision» and press
`Enter`; `Esc` leaves it unchanged): the card stays while the note is open or cancelled, and the revision the note starts
ends the proposed state, so the card is dropped from the history on the next render. The plan screen and its buttons
stay as they are, and approving there (or by any other path) also drops the card: only a proposed plan ever shows
it.

A start the readiness refuses (a `! ` item of the last check, e.g. `No GitHub origin`) shows its own red card in
the chat while the block stands — for the planner start (the goal draft's `/plan` or the plan screen's button «start the planner») and
for a milestone start alike. Its title names the project, its text is the failing checks' own lines (at most six)
and, when one of them is the missing GitHub `origin`, the exact fix command stands on a line of its own
(`git remote add origin https://github.com/OWNER/REPO.git`), read out of that check's own instruction. Its buttons
are «try again» (`/retry`) and «details» (`/details`): the first asks for one fresh readiness check (one
request per press), the second opens the readiness detail — the «Readiness» pane of Settings, every check with its
own line and its fix, the same pane `/setup` opens. The failing checks are the card's key
(`ready:origin`, `ready:origin+identity`): a recheck that passes drops the block — the milestone start's own blocked
note and the screen's error state go with it — and the card leaves the history by itself. A recheck that still fails
leaves the very same card where it was — never a second one. A key whose card has left is a seen key like every
other card's, so the removed card never comes back, whether the block ended or the failing set changed and then
returned (`origin` → `origin+identity` → `origin`); only a *different* failing set is a card of its own. Nothing starts
until the checks pass; the plan screen's `!` lines stay as they are.

A failed stage — one that cannot continue, can continue, is blocked, was stopped or conflicted — no longer pops
the end-of-run screen; both it and a failed planning run (before, only a pane line) show the failure card in the
conversation. A red card «! Error · M1» shows what that screen leads with — at most six lines of the outcome, the full body `/attempt`
still opens — and its buttons are the card-only commands «try again» (`/retry`) and «details» (`/details`).
«try again» starts the first action the state offers — for a recoverable failure the same attempt resumed in
its worktree, for a final one a new attempt from the current HEAD, for an unknown submission a check, each without
a form (a new attempt starts with an empty note) — and a started retry closes the card with
`↻ try again HH:MM`; a stage that offers none of those three (blocked waits for the owner's answer, a conflict
for the merge) gets «details» alone. For a failed planning run «try again» runs the plan screen's own
restart and restarts the planner. «details» opens the attempt's end-of-run screen (the plan screen for a
planning run), the full view the card summarizes. A refusal — a readiness check that fails, a run that moved —
starts nothing, keeps the card and says so on the status line.

### Live run

While a planner or milestone run is active the panel below the milestone rows is always current:

```
  now: task 2/3 (T2) · review
  Working now: worker, code review
  T2: round 2 of 4
  running 14 min · last event 2 min ago · checked 12:41:07
```

- **Roles and progress**: every active role (parallel ones all shown) and `k/n` tasks.
- **Review round**: while a task under review has a proven worker record, a line `<task>: round N of M` names the
  round the current task is in (the first worker is round 1) and the bound of the submitted review loop (one
  implementation pass plus the revision's frozen `limits.task_rounds`, or the fixed 4 without a frozen profile).
- **Last event** counts from the last *new* Zeroshot record; a replayed record or a successful quiet check does
  not reset it, so a long silence is visible as such. «checked HH:MM:SS» is the moment zplan last looked.
- **Interrupted observation** is shown as `watching interrupted at HH:MM:SS` (the shell's catalog
  wording is `! not watched — /status reconnect`): `/attempt` watches it again; the run itself continues in Zeroshot.
- **Journal** (`/details`, section «Journal M1 (attempt N)»; the planner has «Planner journal rN»): the last ~20 distinct steps with the time of each, per attempt,
  kept across a restart (`T1: implementation`, `T1: rework, round 2`). Only steps Zeroshot reported
  are listed; no verdict is invented. The run-end screen's button «details» opens the same stored entries.
- **Activity tail** (`/log`): the last ~40 lines of the Zeroshot log, masked for secrets, read when you ask; an empty
  log says so. A slow log never blocks the keys.
- **Pending actions**: a confirmed start or stop shows `starting M1…` / `stopping M1…` at once and a repeated
  press answers `Already in progress: …`. While a stop is unconfirmed `/run` only checks, never starts.

Every home and plan screen ends with «Next:» for the selected state, taken from the same table as the end
screens; the command or button it names works from the home screen.

## Developing zplan with zplan

Run `zplan` from this repository to develop zplan itself. Give the planner a small goal, review and approve
the plan, then start the ready milestone with `/run` and confirm with «yes».

While it runs, use the live panel to follow the work:

- `Working now` lists all active roles, including roles working in parallel.
- `<task>: round N of M` shows which repair round the current task is in and the bound of its review loop.
- `running` is the elapsed run time.
- `last event` is the time since the last new Zeroshot event; quiet checks and replayed events do not reset it.
- `checked` is the time zplan last observed the run.

`/details` opens the journal of distinct steps in this attempt; `/log` shows the activity tail of the Zeroshot log
on request. You can quit and reopen `zplan` to keep observing the same run.

When the milestone is `done, waiting for merge`, its card offers «see the changes» for the full diff.
With a Git identity configured, the target branch checked out and its working tree clean, press the card's «merge»
(or type `/merge`) to merge the result. zplan never pushes; dependent milestones become ready after the merge.

# Line UI

zplan is line-oriented: type a key (optionally followed by a milestone id, e.g. `g M2`) and press Enter.
A bare Enter on the home screen follows the "Next" hint only when it opens a view (plan, observe, open);
starting, submitting or checking always needs its letter (`g`, `n`, `y`). `q` goes back from every screen and
exits from the home screen. Installation: [INSTALLATION.md](INSTALLATION.md).

## Commands

| Command | What it does |
| --- | --- |
| `zplan` | Interactive session for the Git project in the current directory (`--project PATH` selects another) |
| `zplan status` | Prints the home screen once; no prompts, nothing started |
| `zplan setup` | Installs the pinned Zeroshot 10.16.0 and Codex 0.162.1 (the readiness screen offers it as `u`) |
| `zplan login` | Codex device login into zplan's own Codex home (file store); a login already there is kept. In your own `$CODEX_HOME` it runs no Codex (sign in with `codex login`) |
| `zplan logout` | `codex logout` of zplan's own Codex home only; refused while a run or the architect is live there |
| `zplan doctor` | Checks tools, Codex home/provider/login, Git identity, socket path, roles and the current project |
| `zplan roles` | Edits the default model / effort per role; in a project with `zplan.process.json` shows the roles that live there |
| `zplan profile` | Prints the project's process profile (state, file, digest, each role with its source, gates, checks); never asks or runs anything |
| `zplan profile init` | Writes the proposed `zplan.process.json` without questions; refuses when the file exists |
| `zplan --fixture ID` | Demo against a deterministic fixture in an isolated namespace; never submits native runs |

`zplan doctor` prints one `OK:`, `WARN:` or `BLOCKED:` line per check; every `BLOCKED:` line says how to fix it,
and the exit code is 1 when anything is blocked. A `WARN:` line names a non-blocking issue and keeps the exit
code 0. It never prints secrets and never sends a model request.
Project checks need a commit, an attached branch and a GitHub `origin`; uncommitted changes never block (the last commit is what planning sees).

## Demo mode (`--fixture ID`)

`zplan --fixture ID` walks the whole flow against a deterministic fixture in its own namespace: the planner,
milestones, driver and the process profile all come from fixture stores, and milestone work uses local Git refs,
worktrees, merges and checker runs only — nothing is fetched, pushed or sent over the network. The demo has no
architect chat: the full-screen chat pane says «The architect chat is unavailable in the demo (--fixture).», makes no provider
call and runs no tool probe, and accepting the profile keeps the snapshot in the fixture state without creating or
changing `<project>/zplan.process.json`. `--fixture` needs a nonempty id of letters, digits, `-` or `_`; an empty
or invalid id is refused before anything runs. The rest of this document describes the native flow; a fixture
session is the same screens over the fixture stores.

## First start in a project: the process profile

The first `zplan` in a project whose process profile was never decided shows one screen before home (full-screen
shell and `--plain` alike): the rules files found (`AGENTS.md`, then `CLAUDE.md`), the test command when it is
obvious without running anything (`package.json` `scripts.test` → `npm test`, a Makefile `test:` target → `make
test`; otherwise «no qualification»), the gates (plan check required, task and merge checks «no check»), and
the role bindings. Keys: `a` accept — writes `zplan.process.json` in the project root (commit it so the profile is
shared; an existing valid file is only recorded, never rewritten); `l` later — nothing is written to the project,
the shown values apply and the header says «profile not saved»; `q` leaves without deciding (new plans and
runs are refused until you decide; watching, stopping and export keep working).

Once accepted, the file is the source: roles, `gates.plan: required`, `limits.plan_rounds` (1–5) and the rules
files apply to planning (the rules reach the planner and the critic; at most 64 KiB in total); checks and the other
limits are stored and shown as «for later stages». An edit made while zplan is open
applies to the next planning or milestone start (never to a revision already created). A deleted or malformed
accepted file refuses new planning and milestone starts with the fix; a profile that changed between the preview
and the confirmation is refused and the preview is shown again. `zplan roles` in a project with the file only
shows the roles — they live in the file.

## Readiness screen

`zplan` runs the same checks as `zplan doctor` at start. When everything is ready it goes straight to the home
screen. When something is missing it shows only what matters, with the key that fixes it:

```
zplan · my-project · main
✓ Codex: login found in ~/.local/share/planning-kit/codex-home · provider openai
! No GitHub origin — [i] instructions
[g] check again  [i] details  [q] quit
```

| Key | Action |
| --- | --- |
| `u` | Install the pinned tools (same as `zplan setup`) |
| `l` | Codex login (only for a provider that signs in with a login file; an API-key provider shows `export VAR=...` under `i`) |
| `d` | Show the uncommitted changes (`git status --short`); changes nothing |
| `i` | The fix for each `!` line |
| `g` | Check again; when nothing is missing, continue |
| `q` | Exit (Enter opens the home screen anyway: viewing plans and runs needs nothing) |

zplan never stashes or changes `origin` for you, never copies Codex credentials and never rewrites
Codex config. It commits your own files only on your explicit «yes» (see «Commit card» below), and the profile file it writes itself. Login and every run use zplan's own Codex home, `~/.local/share/planning-kit/codex-home`; an
explicit `CODEX_HOME` (your own Codex, signed in with `codex login`) overrides it for the runs, and zplan never logs in or out there.

The check runs again right before every planner submission and milestone start. If something is missing then,
the same screen appears (`q` goes back) and nothing is sent; a goal you have typed is already saved.

Why zplan keeps its own tools: the planner and milestone graphs are qualified against exactly Zeroshot 10.16.0
and Codex 0.162.1, so zplan installs those checksum-verified under its data directory and never uses or changes
a global `zeroshot` or `codex`.

## Home screen

```
zplan · my-project (main, clean)
Goal: Add CSV export to the report page
Plan r1 · approved · 1/3 stages merged
  ✓ M1 Export format and parser       merged 3f2a9c1
  ▶ M2 Export endpoint                running
  · M3 UI button                      waiting for M2
Next: [w] watch M2
[w] watch  [o] open  [p] plan  [r] reconsider  [s] settings  [i] details  [q] quit
```

Without a plan the screen says `No plan.` and offers `[p] plan  [s] settings  [q] quit`.

| Key | Action |
| --- | --- |
| `w` | Observe the running milestone |
| `g` | The «Next:» action: start the ready milestone (`start`), `continue` a recoverable failure, `new attempt` after a stop or failure, or reconcile an unconfirmed submission / pending stop (`check`) |
| `e` | Tail of the Zeroshot log of the running or failed milestone, on request |
| `o` | Open a milestone that needs attention (finished, waiting for merge, failed, stopped, needs an answer) |
| `p` | Plan: write the goal, run the planner, approve |
| `r` | Revise the plan: describe what to change; the planner builds a new revision that you approve again |
| `s` | Roles (model / effort per role) for the next planning and the next milestone start |
| `i` | Details: plan, the run journal, every run record, worktree and branches, and ready-to-copy Zeroshot diagnostics |
| `q` | Quit; running milestones keep running |

When readiness fails, home names each failing check with its key (`! No GitHub origin — [i] instructions`). The
plan screen re-checks before it says a start is blocked: a tree that was fixed since drops the message, a moved
baseline stays and points to `[n]`. Refresh and status only read; they never renew or submit anything.

Milestone states: `waiting for M1` (dependency not merged yet), `ready`, `running`, `stopping`,
`waiting for merge`, `conflict`, `needs an answer`, `blocked`, `failed · can continue`, `failed · cannot continue`,
`stopped`, `submission status unknown`, `merged <commit>`. One milestone runs at a time.

## Plan

1. `p`, then type the goal; several lines are fine, an empty line ends it.
2. zplan shows the roles; `g` runs the planner (`s` changes roles first, `q` cancels).
3. While the planner works, zplan prints plain phases as they happen (`Drafting the plan…`,
   `Checking that the plan covers the goal…`, `Refining the plan from the findings…`) and, when nothing new happens for a
   while, `…still working, N min elapsed`. Ctrl-C leaves; planning continues and `p` then `w` watches again.
4. The proposal, summary first:

   ```
   Plan r2 · 1 milestone · 1 task · checked
   Goal: Add a README paragraph about installation
     M1 Installation paragraph  (after: —)
       T1 Write the installation paragraph in README.md · 2 checks
   [a] approve  [r] revise  [x] decline  [i] requirements and checks  [q] back
   ```

   `i` shows every requirement, slice and check and how the plan was argued: the critic's verdict, rounds used of
   the limit, for each round the findings and the planner's reply, and the short digest of the configuration it was
   checked under. A plan the critic did not accept within the rounds cannot be approved with `a`; `r` revises it,
   `g` plans again, and `o` approves it anyway (below).
5. `a` approves (`Plan r1 approved. Nothing was started; start with [g] on the home screen.`),
   `r` asks for changes (type the feedback; a new revision is planned), `x` declines. Enter and `q` only go back.

Plans contain product work only: the milestone driver already runs independent reviews, repairs and resume
for every task, so those never appear as tasks or checks unless your goal asks for them. A small goal gets a
small plan (a README paragraph: 1 milestone, 1 task, 1-2 checks).

**Approving over a rejected plan check.** When the critic rejected the plan within the rounds (`the check did not accept
it`), `o` «approve despite the check» asks for a reason: one line, 10 to 500 characters (empty input or
`Esc` cancels and writes nothing; a shorter or longer reason is refused). The plan becomes approved and
milestones run from it as from an accepted plan. The critic's verdict, findings and discussion stay in the record
unchanged and are never hidden: the plan screen keeps `The plan check did not accept it: "…"` and adds
`Approved despite the check: "reason"`, the status reads `approved despite the check` (also on the main screen
and in `i`), and the reason is part of what the approval is bound to. The same refusals as for `a` apply (project
changed after planning, process settings changed since the critic ran: «the check is out of date»); a plan of the
first execution version has no plan check and offers no override. There is no command-line path to approve or
override a plan.

If the repository changed after planning, approval is refused; `r` replans against the current tree. The same
happens when the process settings (roles, limits, rules) changed after the critic accepted: `a` answers
«the check is out of date», writes nothing, and `r` plans and argues again under the current settings.

**Commit card (your own uncommitted files).** Planning and runs see the last commit, never uncommitted files. When the goal
needs some, the architect can offer to commit them (`zplan_propose_commit`: paths and a message); it never commits itself,
at any autonomy level. zplan shows the card «Commit your files»: the message, the `git diff --stat HEAD --` of those
paths (new files listed as «new file»), the warning «the plan goes stale first; a running milestone will not see the commit», and
«yes» / «no». «no» runs nothing. «yes» suspends the terminal as the login does (hooks and signing may ask you) and runs
`git commit --only -- <paths>` with your identity and your hooks (never `--no-verify`). The committed paths are the
proposal met with the live `git status` at «yes»: files only, a rename needs both sides, credential files (`.env`,
`*.pem`, ...) are refused and named, ignored files stay out (nothing is `add -f`), other staged changes stay staged and
out of the commit. A hook that refuses leaves HEAD and the index as they were. After the commit the card says which
extra files the hooks changed, if any. Refused with the fix to run: no Git user, no commit yet, a detached HEAD, a merge
(`MERGE_HEAD`) or rebase in progress, a held `index.lock`, or a merge being landed. The architect sees only the stat and
a scrubbed, bounded diff, never raw file content, and learns the answer from its status.

**Plan not sent yet, project changed.** A plan that was never sent to the planner is tied to the project as it
was when you wrote the goal. If you commit (or otherwise change the tree) first, `p` shows:

```
The plan has not been sent yet. The project changed after it was created. The goal and settings are saved.
[g] start the planner  [n] prepare a new plan on the current project  [q] back
```

The same screen appears, with «It was made for another Zeroshot version or state…», when the plan was
prepared for another Zeroshot (a different toolchain, a rebuilt binary or another state directory).

`g` checks readiness and, when it passes, prepares a new revision with the same goal and roles on the current
tree and sends it in the same step (one line says «rN → rN+1»); the old revision stays as it was. If readiness
still fails nothing is prepared or sent. `n` only prepares the new revision without calling the model; then `g`
sends it. A plan that was already sent is never resent: if zplan
knows the run it watches it again (`w`); if the submission is unconfirmed it says so and `i` prints how to check
Zeroshot by hand.

**Stopping the planner.** While the planner runs (or its run is observed from a previous session), the plan
screen offers `s` «stop planning». `s` saves the stop request and force-stops the run; a refused or
unanswered call keeps the revision as it was and says `Not done: …`, and `s` is offered again. Once the
observation sees the run end, the plan is `stopped` and the screen shows `Plan rN stopped by you at HH:MM.` with
`g` «start the planner again» and `i`; the stopped run is never resubmitted, `g` prepares a new revision of
the same goal on the current project and sends it. The cause line survives reopening zplan.

**Planning stopped.** The plan screen names the cause and the next step, for example
`Planning stopped: the service rejected the authorization. Next: [l] refresh login, then [g] check readiness.`
Limits/quota and network problems get their own lines; when the cause is not visible zplan says so and points
to `i`. Raw logs and secrets are never shown. `g` checks readiness and plans the same goal again.

## Run a milestone

`g` shows what will happen before anything starts:

```
Start M1 · Export format and parser (attempt 1)
  Worktree:        ~/.local/share/planning-kit/worktrees/...
  Work branch:     zplan-work/...
  Result branch:   zplan/...
  Merge into:      main (from HEAD 3f2a9c1)
  Roles:           planner gpt-6.1-sol/high · worker gpt-6.1-terra/max · ...
  Limits:          3 tasks (+ up to 2 new), 2 repairs per task, 1 final repairs
Start M1? [y/N]
```

`y` shows `starting M1…` and submits one native Zeroshot run for the milestone, then starts observing:

```
Watching M1 · Export format and parser — Ctrl-C: detach (the run continues) · k + Enter: stop
  now: task 1/3 (T1) · ...
```

- **Ctrl-C** detaches: `Detached; the run continues. Come back with: zplan`. `zplan` later shows the state; `w` reattaches.
- **k + Enter** asks `Stop M1? The attempt's unfinished work will not be accepted. [y/N]`; `y` requests the stop.

## End screens

Each screen starts with `M1 · <title> — <state>` and a line with the run status, outcome and delivery.
`q` goes back to the home screen.

| Screen | Keys |
| --- | --- |
| done, waiting for merge: tasks done, plan changes made by the run, diff stat against the base | `m` merge into `<branch>` (asks `Merge the result of M1 into main?`; the result branch is named under `i`; prints `Merged: M1 → main`), `d` full diff, `l` later |
| merge conflict: conflicting files; your tree is untouched | `m` retry the merge, `d` diff, `l` later; or merge `zplan/...` by hand, commit, then `zplan` |
| needs an answer: the question, or a proposed change to the milestone tasks | `a` accept the proposal, `t` answer (starts a new attempt), `x` leave it |
| blocked: the reason in one line (the model's words in «…»; internal markers stay under `i`) and task notes | `t` answer and restart, `p` change the plan |
| failed, can continue | `g` resume the same attempt in its worktree, `t` new attempt from the current HEAD (a fresh run, not a resubmission of the frozen attempt), `p` plan |
| failed, cannot continue | `g` (or `t`) new attempt from the current HEAD of the target branch: the form explains that the model runs again, takes an optional note and starts with `Ctrl+G`; `p` plan |
| stopped | `g` (or `t`) new attempt, `p` plan |
| submission status unknown | `g` check: reconciles with Zeroshot, never submits a second run |

Every end screen also names the keys it offers in its own «Next:» line, and then the retained journal of that
attempt (`Journal:`, oldest entry first; `The attempt journal is empty: observation has not recorded anything yet.` when it has
none) — `i` opens those stored entries in a read-only screen with or without a native run, `e` the tail of the
Zeroshot log where a run exists. On a terminal of at least 80×24 the panel opens at the top of the body (no logo
or header sits above the panes) and grows with
its content down to the bottom of the screen, then scrolls inside; a smaller terminal keeps the centred 90%x80%
box.

Merging needs a Git identity and the target branch checked out; uncommitted changes do not block it, and zplan never pushes. After a
merge, milestones that depended on it become `ready`.

## Details (`i`)

`i` (the same text in the shell and in the line UI) leads with what really happened (`M1 merged e78f740`,
`M2 running: T3 review`), then the plan. Claims that stopped being true are dropped: after a merge the plan no longer
says that the repository changed after approval or that nothing was implemented. Everything technical sits in
a tail marked `For diagnosis`: milestone, plan revision, attempt, run id, status, outcome, delivery,
worktree and branches, and the last diagnostic. For each native run (the planner's included) the tail has
ready-to-copy commands with the exact Zeroshot executable and state the run used:

```
  Zeroshot diagnostics (root run):
    ZEROSHOT_STATE_DIR=<root>/runs ZEROSHOT_CONFIG_DIR=<root>/config <zeroshot> status <run id>
    ZEROSHOT_STATE_DIR=<root>/runs ZEROSHOT_CONFIG_DIR=<root>/config <zeroshot> logs <run id>
```

A resumed attempt is a successor run: it is labelled `continuation of <root run id>` and has its own run id.

## First-run checklist

1. **Start on a throwaway repository.** Create a small repo with one commit, a branch and a GitHub-shaped
   `origin` (it is never pushed to), e.g.
   `git init -b main demo && cd demo && echo demo > README.md && git add README.md && git commit -m init &&
   git remote add origin https://github.com/you/demo.git`.
   Give it a small goal, approve, run M1, merge. Move to a real project after that works.
2. **Codex home.** Login, doctor and every run use zplan's own Codex home,
   `~/.local/share/planning-kit/codex-home`, where zplan writes its versioned `config.toml` profile; your own
   `~/.codex` stays as it is. zplan never copies or links those credentials (a shared refresh token can log out the
   other copy). To use your own Codex home (or another one) instead, sign in there with `codex login` and
   export `CODEX_HOME=...` before `zplan`; zplan never logs in or out of it. Never copy `auth.json` between homes. A malformed `config.toml` or an unknown provider blocks.
3. **Run `zplan` inside the project.** In the full-screen shell Settings (`/setup`) lists anything missing; fix
   it and press «check». The line UI's readiness screen shows the same list; there fix it and press `g`
   (`zplan doctor` prints the same list).
4. **If a run stops or looks stuck:** run `zplan`; the plan pane and `/attempt` show the state and reason, `/log`
   the tail of the Zeroshot log. `/details` (line UI: `i`) prints the `status` / `logs` commands for the root run
   and any successor run; copy them as printed (they carry `ZEROSHOT_STATE_DIR` / `ZEROSHOT_CONFIG_DIR` and the
   exact executable). `failed · can continue` → «continue» (line UI: `g`) resumes; otherwise «new attempt»
   (`t`) starts a new attempt or «to plan» (`p`) changes the plan.
5. **Stop safely.** In the full-screen shell type `/stop` and answer «yes»; in the line UI use `k` + Enter while
   observing, then `y`. The stop is recorded first; if zplan exits before Zeroshot confirms, the milestone shows
   `stopping`, and `/run` (line UI: `g`, check) resends the stop. `Ctrl+Q`, Ctrl-C, closing the
   terminal or `q` only detach — the run continues and costs tokens until it ends or is stopped. Do not delete
   `~/.zp`, the worktrees or `planning.json` while a milestone is running.
