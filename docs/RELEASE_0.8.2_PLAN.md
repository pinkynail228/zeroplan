# Plan: 0.8.2 fixes and the 0.9 chat-first design

Status 2026-10-28. Inputs: the 0.8.1 tester round (feedback file 0.8.1-testers.md in the pause dir, folder feedback,
rows F1-F8b), the surface inventory (chat-first-inventory.md in the pause dir, folder design: 28 surfaces, architect
powers, demo mode), STATE.md Next. Every new report becomes a row in the feedback file first, then lands in one track
below; nothing is fixed from memory. Critic plan082 (Astra, xhigh, 2026-10-28): AGREE WITH CHANGES, 17 should and 1
nit, all taken; in the one argued turn she kept five of my six
counter-proposals and changed the exFAT fallback to her version (A7).
Verdict and argument: plan082.out and plan082-argue.out in the pause dir, folder critic.

## Track A — 0.8.2: bugs from the tester round

One release, fixes only. Schedule (critic plan082, item 11; F12 2026-10-28): A8 first, in parallel with A7 (the
plan loop burns the most model runs and stalls every rejected plan); A10 and A2 next; A3 after A10 merges,
A4 after A3, A9 after A4 (all change tui/app.py); A1b and A6 fill free slots, but d1 never beside a8
(engine.py) and s5 never beside s3 (tui/start.py) (critic scope082b Q4). No rc until every A item is merged (owner
2026-10-28). Each brief carries the
criteria below; a probe comes before every brief marked so.

| # | Item | Source | Brief | State |
|---|---|---|---|---|
| A1 | No project in the home folder or `/`; the start screen never freezes counting files | F5 | s4-start-home | merged 37865eb |
| A1b | Also no «Create a project here» at a mount point (`os.path.ismount`, e.g. `/Volumes/X`), which is what "disk root" promised; opening an existing repo at HOME stays allowed; `~/.git` is never deleted | plan082 3 | s5 | merged |
| A2 | `zplan login` outside a usable terminal: the guard sits in the shared login path (setup.py:505), so the CLI and the TUI callbacks both pass it, before device auth, refresh or any preparatory write; non-zero exit, a plain "run this yourself in your terminal", no auth side effect; plain `logout` gets no new terminal check | F2, plan082 4 | l2, l2b (the CLI's retry hint after the refusal) | merged b926e70, bd1178a |
| A7 | Profile save on exFAT ("[Errno 45]", `unknown_error`). Probe done 2026-10-28 (local `hdiutil` ExFAT image): `os.link` and `renamex_np(RENAME_EXCL)` both ENOTSUP; the brief's probe still checks the other writes (`_replace` with chmod, process.py:1098; project_state's replace and directory fsync, project_state.py:88; the profile's Git commit, process.py:1073). Fix (owner 2026-10-28: "just make it work"): the temp is fully written and fsynced as today (process.py:1107); when `os.link` fails with ENOTSUP/EOPNOTSUPP only, try `renamex_np(RENAME_EXCL)`, and when that is unsupported too, publish with `os.rename` only if the name is absent, checked under the profile's lock right before. A half-written profile is never visible; zplan never overwrites an existing profile; the one gap is a writer outside zplan creating the file in that window (critic fresh-eye-1028 wanted a refusal instead; overruled: a refusal leaves exFAT broken, the owner's ask, and no realistic second writer exists). EEXIST, permissions and a full disk keep their own messages; any other OS error gets a plain message instead of `unknown_error`; a regression test with `os.link` and the exclusive rename raising ENOTSUP. No general FAT support promised | F8, F8b, plan082 1-2 | p1 | merged d3c2628 |
| A3 | Light terminals. Probe first: what pinned Textual 8.2.8 detects on its own; a self-written OSC 11 query only if it lacks one, and then one owner of terminal input, one shared deadline, terminal settings restored, no lost keys, no late reply bytes in the field. Light and dark styles agree in both apps: the owner's white text (zplan.tcss:135), the code theme (app.py:720), the start screen's colours. One theme resolver for both apps, precedence `ZPLAN_THEME` (auto, dark, light) -> ui.json -> auto, so the first screen already obeys; `/theme` writes ui.json keeping the language, and the language setter (strings.py:630) stops dropping other keys | F4, plan082 5-6, critic s3brief BLOCK (flush loses keys, late reply becomes keys) | s3a (resolver + safe query), then s3b (styles, `/theme`, pins test_tui_look.py:240, test_tui_chat_messages.py:176, renderables rebuilt) | s3a merged c6a00f6 (real pty 7/7 PASS); s3b merged a83f267 (Terminal.app light and dark shots); A3 done |
| A4 | Multiline chat input at the bottom: wraps, grows up to 8 visual rows then scrolls; Enter sends, Alt+Enter and Ctrl+J add a line, checked in a real terminal protocol. The brief maps the ~15 places tied to `Input` (handlers app.py:1782, history, palette, priority arrows, forwarded typing app.py:3070) and pins cursor movement, palette and card precedence (an empty Enter answers a card, app.py:1802), a slash command with a newline, paste never sends, text kept when a send is refused, resize | F3, plan082 7 | s2a (one-line TextArea swap), then s2b (lines, growth, keys) | s2a merged bd7ad10 (real pty A/B 8/8 same); s2b merged (real pty 9/9); A4 done |
| A5 | Docs: installing through an AI agent; no AppleScript change needed | F1 | none (docs) | committed 35e29b3 |
| A6 | Release critic's notes on 0.8.1: README approve/merge steps qualified by autonomy, USER_FLOW.md `/scheme` exception; separately, DRIVER_MECHANICS wording: the final check repeats on `incomplete` (milestone.py:416), not on any refusal | rel081b, plan082 8 | docs + d1 (own small brief, not joined to A2) | merged fb1bb23 (docs), 5ac1dac (d1) |
| A8 | A rejected plan's findings travel: zplan_status gives the architect the latest checked revision's findings (today only version, status, verdict: tui/controller.py:243-252; findings in planning.json, authority.py:687-698); the next revision's planner gets that revision's proposal and findings, with its number, frozen in the input (engine.py:1356-1363), while the new check's discussion starts empty and old findings never become its evidence (critic scope082b Q3); the architect gets a checked revise-with-feedback tool under autonomy `edit` (planning.py:402-407; the planner repairs), the byte-for-byte edit stays for the owner's own text (engine.py:793-797); EDIT_CRITIC's "report any problem as a finding" falls under PLAN_CRITIC_BAR (engine.py:709). The English notes in a Russian chat (F11) are not fixed here: the UI offers English only (strings.py:70), Later | F11, F12 | a8 | merged b26774a |
| A10 | The loop brake, a persisted repair episode (critic scope082b Q2): the first review_exhausted allows one automatic architect revision, the next closes automatic revisions until the owner decides; checked where an automatic revision is created (tui/controller.py:805), not only in the feed's wake (feed.py:49-50, 156-160), and it survives a restart, an edit or another message. A card on the main screen from the first rejection at every autonomy level (today `idle`, tui/app.py:518-524; card_kinds.py:663) with the findings and three choices: revise with my words, approve anyway with a reason (the existing override, authority.py:899), stop planning (Planning.stop refuses a finished rejected run today, planning.py:457, slash.py:78: route it); the [i] text stops saying "cannot be approved" (planning.py:701); the architect, asked to approve a rejected plan, says so and points to the card | F12 | a10 merged c379b14; a10b merged 0e1ea2b (card refusals and outcomes on the main screen); a10c merged (a refused card /approve says why once); A10 done |
| A9 | After an approval or a start the screen follows the work: the pane switches once per confirmed event (approval of revision N -> the plan, start of run R -> the run) unless the owner chose a pane since (tracked apart from programmatic switches); the same on the architect's tool paths (tui/controller.py:851, 884), not only plan_decision/begin_run; the chat says the milestone started (today no switch by design, app.py:1408; app.py:3113-3118, 3287-3290) | F9 | a9 | done 2026-10-29 |

Lessons that bind every brief here: no blocking call on the UI thread without a timeout (A1); reproduce a UI defect
with a probe before the brief (s1); a query to the terminal must never wait without a limit (A3); an automatic wake
that can start a model run has a stop condition and carries the reason it fired (F12).

Release (owner 2026-10-28: stages, not one release per fix; ORCHESTRATOR.md, Release): A items merge to main as
they pass; `v0.8.2-rc1` as a GitHub pre-release once A1-A10 and A1b are merged (A5 and A6 are in its scope); a soak
with the agent walk from a clean HOME and the cases F1-F8 found (home folder, light terminal, external drive,
install through an agent, no GitHub origin, a plan the check rejects twice); testers pin `ZPLAN_VERSION=0.8.2-rc1`; `v0.8.2` on the same commit
once the soak walk leaves no open blocker.

## Track B — 0.9: the architect as companion, chat first

Goal (owner 2026-10-28, F6-F7): setup and decisions happen in the chat with the architect, who reads the project,
suggests, explains and asks for one-key consent; cards and forms stay only where code must decide. Facts first,
then the design; no code before the owner's decision.

| # | Step | Method | Output | Independent evidence |
|---|---|---|---|---|
| B0 | Inventory of surfaces and architect powers | read-only survey | the inventory file | done 2026-10-28 |
| B1 | Which instruction files reach which role (architect, planner, worker, reviewers, final check): root and nested AGENTS.md, CLAUDE.md, the zplan Codex home, `zplan.architect.md`, the profile's rules | a canary line per file in a scratch repo; read the prompts and outputs in the run store | precedence matrix, each cell with its run id | rerunnable with one command; source tracing done 2026-10-29 (docs/spikes/B1_B3_B4_RULES_AND_FACTS.md): Codex gives every role the root AGENTS.md unranked; canaries K1-K4 still to run |
| B2 | Where project rules fight the Zeroshot graph or zplan | 50+ public AGENTS.md and CLAUDE.md plus the owner's two projects, classified (branching, commit policy, test commands, ask-before-act, tooling); fixture repos with conflicting rules | conflict taxonomy and a precedence proposal in which no side overrides the other silently | on the corpus, every conflict is either resolved by the order or reported to the owner |
| B3 | Project facts the architect starts from | a read-only, time-bounded probe: Git root, home or root guard, origin, `gh auth`, push permission, branch protection, default branch, rule files, test command, dirty tree, size | a facts schema the architect reads (today `zplan_status` has no readiness or profile) | probe output on the three project types below; draft schema done 2026-10-29 (same file); the probe still to run |
| B4 | Prior art | Claude Code and Codex `/init`, the Copilot coding agent (instructions and setup steps), Cursor rules, Aider conventions | what they read, write and ask; what we reuse | links and quotes; done 2026-10-29 (same file) |
| B5 | Design doc | a decision for each of the 28 surfaces: code, chat with one-key consent, or removed, with the reason; the bootstrap (9 surfaces before any login); autonomy "ask" turned into a consent card in the chat; missing architect tools; demo mode; the onboarding ritual (the architect proposes rules and rituals as diffs, never edits AGENTS.md without consent); threat model (repository text is untrusted); metrics | the design file in the pause dir | B6-B8 |
| B6 | Rehearsal before code | a person plays the architect in the chat on the owner's project | the gaps it finds | notes |
| B7 | Critic | Astra, xhigh, on B1-B6 | verdict | critic file |
| B9 | The project's own workflow: at `auto` zplan merges into the destination branch itself (docs/USER_FLOW.md:171, :306) and knows nothing of the project's branch protection, PR flow or release habits | B3 reads them; onboarding asks where finished work goes: merge locally, an integration branch, or a branch left for the owner's PR (zplan pushes nothing) | a decision in B5 | the three project types |
| B10 | Class "the owner is the system's hands" (F9-F11): every place where zplan or the architect knows the state but tells the owner to act or relay (10 found 2026-10-28: /view and /run pointers, findings the architect cannot read, the no-auto-switch rule, the typed "Another folder" path); cause per place: architect blind, UI never acts on events, message points to a command instead of doing it | a read-only survey on top of B0 | the list with a decision per place, folded into B5 as the rule "a message never sends the owner to an action the code or the architect can take within the autonomy level" | B6 rehearsal finds no relay step |
| B8 | Owner's decision, then briefs | — | the 0.9 scope | — |

Acceptance for 0.9: new testers (not this round's) on three project types (an empty folder, a repository with
AGENTS.md and GitHub, a repository without GitHub) reach a first plan; measured: success rate, time to the first plan,
manual inputs; `git diff` after onboarding holds only changes the owner accepted.

Method rules for B (critic plan082, 10 and 13-17):
- Order: cheap first. Source tracing (engine.py:1365 already declares part of the precedence), a small classified
  B2 corpus (quality over the count), B4 prior art and the B3 specification; then targeted B1 canaries on an agreed
  test login and call limit, never the owner's credentials.
- Evidence keeps three levels apart: delivered (freeze_rules, process.py:358, proves the payload only), read, and
  acted on. Contaminants: a canary named in the task prompt, model self-report, a resumed thread, a corpus fitted to
  the proposed precedence. Use hidden control cases, fresh sessions, a held-out rehearsal.
- B3 separates what the bootstrap needs from today's UI order: a preset works without an accepted profile
  (chat.py:506), the language is no auth prerequisite, a GitHub origin is a readiness gate of its own
  (setup.py:596). Each fact has provenance, freshness and `unknown`; a missing `gh auth` or unreadable branch
  protection never blocks a first plan by itself.
- B5: the 28 surfaces are a checklist, not the model. Per operation: authority, bootstrap dependencies, cancel and
  recovery, the plain and demo path; "one-key consent" defines focus and the exact action confirmed. The architect
  stays read-only (architect.py:175); new powers come as checked tools. `autonomy.ask` as a card needs a stored
  pending action, the plan revision and profile identity, a re-check of conditions and protection against a
  repeated consent; enforcement stays in the Controller and the engine.
- Demo start (`--fixture` still runs the real picker with init, identity, origin, cli.py:1106): B5, not 0.8.2.
- Acceptance checks more than `git diff`: refs and commits, repo config, index, untracked paths (start.py:165 and the
  profile commit, process.py:1073, leave an empty diff); metrics fixed before the runs.

Folded into B5 (they are card or demo issues): the owner's R6 0.8.0 items F3-F5, F7-F8 and the demo cards from the
cold README run (STATE Next 2).

## Track C — later, after a measurement

Fewer model calls (the select trio, scope_verify); merge-critic facts (needs a design); the empty-queue final
check's live count; the README rework from this round's feedback (after the 0.8.2 soak; STATE Next 4).

## Owner decisions open

1. Decided 2026-10-28: 0.8.2 goes out as rc1 after the A items, final after the soak.
2. B1 needs real model runs: which login and what budget.
3. New testers for the 0.9 acceptance.
4. Carried from STATE Open: `/merge` at `auto` in a folder without checks; the rule-file diffs from the test-prune report.
