s2b3-agent-warnings — 0.5 item S2, slice 3 of 3 of devtools/zeroshot/tasks/s2b-agent-profile.md (the parent). Where cited, these apply verbatim:
- the parent's R-5 `agent_drift`/`agent_sources`, R-6, and R-7 for the two `readiness.*` families;
- A-5 and the A-8 mutations "drop the mcp_servers rule" and "skip the skills WARN under the profile".

Slicing: split out of s2b2 by critic gate9 B (size). The authoritative coverage map is s2b2-profile-activation.md "Coverage map"; this slice owns its s2b3 row. Lane: Environment (L1). DeepSeek worker, sol reviewers. Critic gate10: GO WITH CHANGES (applied).

Base: main with s2b2-profile-activation merged, which itself sits after s2a and s2b1. Lines below are cited at 08fe3e3; re-check every line on the base. Record the base and this brief's sha256 in the receipt.
- Stop and report if the base lacks either of these:
  - `setup.agent_home(env)`;
  - `item(..., severity="warn")`.

Write-set (exclusive for this slice):
- setup.py:
  - new `agent_drift(home)` and `agent_sources(home, project)` item builders, called from `readiness` after the `auth` item;
  - module-level `ETC_CODEX = Path("/etc/codex")` and a `user_home()` indirection for HOME, which tests replace.
- agent_profile.py: the module docstring only (the R-6 table).
- catalog.py:
  - `readiness.agent_drift` and `readiness.agent_sources` in ERRORS next to :178-196;
  - CHECK_REMEDY_FREE entries for both ids :33-46;
  - docs/REFERENCE.md regenerated only.
- docs/INSTALLATION.md: the R-6 precedence table and one warnings paragraph. docs/USER_FLOW.md: one doctor WARN example.
- new `tests/test_agent_warnings.py`.
- Allowed existing test files (closed list): tests/test_setup.py, tests/test_ux.py, tests/test_warn_contract.py.
  - Edits there are only doctor/readiness golden lines that now carry a WARN, and a setUp patch pointing `ETC_CODEX`/`user_home()` into the fixture tree, so host /etc/codex never leaks into a golden.
  - Assertions are not weakened, and each edit is listed in the receipt.
  - Any other test file → stop and report.
- The receipt `devtools/zeroshot/tasks/s2b3-agent-warnings-receipt.md`.

Not touched: cli.py (the dedup at :245-246 already exists), tui/* (s5a1 renders warn rows), architect.py, engine.py, runs.py, authority.py, delivery.py, process.py, task_gate.py.

Parallelism:
- With s1a1b1: disjoint → parallel.
- With s1a1b2: product overlap is catalog.py (a different group) and the generated REFERENCE. On tests, s1a1b2's named list (test_runs, test_lifecycle_guard, test_live, test_fixture_scope, the tui suites) is disjoint from this slice's closed list. s1a1b2 may also edit "any other the run finds" (s1a1b2-gate-barrier.md write-set), so before the second integration the orchestrator compares the two receipts' file lists. On an overlap, integration is sequential with a conflict re-run. Otherwise parallel. Integrate completed candidates only; the second integration SHA regenerates REFERENCE and runs the full gates.
- With s2b2: strictly after.

Audit (08fe3e3):
- `readiness` setup.py:478-562 and its `auth` item :513-536.
- `read_toml` :423-429.
- WARN: `item` :256-272, the doctor prefix :599, exit :604-607.
- Plain start shows each distinct warn `line` once (cli.py:245-246). Settings shows the full doctor text per row (s5a1-warn-contract.md:15).
- Every item id needs a `readiness.<id>` family (tests/test_reference.py:92, :386-387).
- The parent's source list and qualification state: s2b-agent-profile.md R-5, R-6, A-9 and the "Unverified" premise.

Rules:
- R-5d Drift: parent R-5 `agent_drift`, one item per finding, against the effective home's config.toml (zplan or override). A finding is one of:
  - an R-2 expected key (`agent_profile.EXPECTED`) that is missing or has another value;
  - a forbidden table present (`mcp_servers` non-empty, `apps`, `hooks`, `plugins`, `projects`, `profile`, `profiles`);
  - a global `AGENTS.md`/`AGENTS.override.md` in the home.
  An unreadable config gives no drift item; it stays the existing `codex_home` block.
- R-5s Sources: parent R-5 `agent_sources`, one item per existing source, whatever the profile says:
  - `ETC_CODEX/{config.toml, managed_config.toml, requirements.toml}`;
  - non-empty `user_home()/.agents/skills`, `<home>/skills`, `ETC_CODEX/skills`, and the target's `.agents/skills`;
  - a target `.codex/` directory → "may apply to agents (not verified for this launch mode)";
  - for an override home, a `[projects]` trust entry is never treated as absent.
- R-5w Display (gate9 B):
  - Every drift and sources item has `severity="warn"` (ok=True) and the same short `line`: "Окружение агентов Codex отличается от профиля zplan — подробности: zplan doctor". So plain start shows it once (cli.py:245-246).
  - Each item's `doctor` text names its own finding: a key path, a table or a file path, so doctor and Settings keep the separate findings.
  - No text contains a config value.
  - No text says "hidden" or "not loaded".
- R-5g Gating: warnings never change `ok`, the planning gate or the doctor exit code. Doctor writes nothing, takes no lock and spawns nothing.
- R-6 Precedence table: parent R-6, in the agent_profile.py module docstring and in docs/INSTALLATION.md. It describes "the pinned Codex of the current toolchain" without any version literal: tests/test_toolchain.py:64-79 rejects toolchain version strings outside the toolchain module, so the parent's "Codex 0.162.1" wording is not copied. Every row that A-9 has not qualified is marked "unknown".
- R-7 Text: the two families (summary/cause/remedy) and the two key-free remedies ("see zplan doctor"); REFERENCE regenerated.
- R-8 Fixtures: as in s2b2 R-8. The /etc root and HOME are always the replaced module values, never the runner's.

Acceptance (tests/test_agent_warnings.py; temporary HOME, XDG_DATA_HOME and ETC_CODEX; no network; spies prove that nothing is spawned):
- A-5 (parent A-5, every bullet), through `cli.main(["doctor"])`:
  - a seeded `[mcp_servers.x]` → WARN, exit 0;
  - a missing `features.apps` → WARN;
  - `[projects."/p"]` → WARN;
  - the clean profile → no agent_drift WARN;
  - `ETC_CODEX/managed_config.toml` → WARN;
  - `~/.agents/skills/s/SKILL.md` → WARN under the profile too;
  - a target `.codex/config.toml` → the "may apply" WARN;
  - no line contains "hidden" or "not loaded";
  - doctor spawns nothing and leaves an absent private home absent.
- A-5v: a drifted key holding a sentinel value (the `mcp_servers.x.env.TOKEN` entry set to a sentinel string) → the sentinel appears in no doctor line, no plain-start line and no Settings row.
- A-5w: three findings → doctor prints three WARN lines with distinct texts, while plain start (`cli` start path with every block absent) prints exactly one `! ` line. A block item plus warnings → exit 1 only because of the block.
- A-8 Mutations, each killed by a named test:
  - (c) drop the mcp_servers rule;
  - (d) skip the skills WARN under the profile;
  - (h) print a drifted value;
  - (l) a per-finding `line` (plain start prints several lines);
  - (m) a warning with ok=False.
  - Base replay: A-5 fails on the base at its WARN assertion; record it.
- A-9 (one orchestrator gate after this slice, Linux test host; the worker does not run it):
  - the parent A-9 (skills, project config, native permissions), which decides the R-6 rows and whether any WARN may later be dropped;
  - plus the extra auth qualification of s2b2 R-4b: a real architect turn with only OPENAI_API_KEY set and no auth.json, and a native worker under the same env;
  - commands and results are recorded once, for both slices.

Size: the whole diff counts except the receipt and REFERENCE. Estimate ~330: product ~100, catalog ~8, docs ~40, tests ~180. Above 600: report the measured overrun and rationale in the receipt; merge requires explicit critic disposition (ORCHESTRATOR step 1).

Out of scope: everything in s2b2; s2c; suppressing or editing any source (zplan never edits project or system config); A-9.

DoD:
- Worker: `PYTHONPATH=.:tests python3 -m unittest tests.test_agent_warnings tests.test_agent_activation tests.test_agent_profile tests.test_setup tests.test_warn_contract tests.test_ux tests.test_tui tests.test_tui_polish tests.test_toolchain tests.test_reference` passes.
- Orchestrator: the full suite at the merge gate, then the A-9 gate above (parent A-9 + the s2b2 R-4b OPENAI-only architect check) on the Linux test host.
- `git diff --stat <base>` lists only the write-set.
- `python3 devtools/export_check.py` on the committed candidate reports no home-path finding.
- Receipt: base, sha256, file list, the closed-list test edits, base replay, mutation table.
