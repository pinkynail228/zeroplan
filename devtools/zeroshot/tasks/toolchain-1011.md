Activate Zeroshot 10.11.0 as the default toolchain and fix small issues found in the U5 walkthrough. Read AGENTS.md, docs/UPGRADE.md, terminal_planner/toolchain.py, install.py, README.md, docs/INSTALLATION.md, docs/REFERENCE.md, terminal_planner/live.py, tui/app.py, catalog.py and their tests. Do not touch prototype/, upstream/, reference/, docs/history/, STATE.md, AGENTS.md, LICENSE. No real provider; no network (the candidate archives are local, see below). Russian UI, English code.

The orchestrator qualified the candidate with devtools/toolchain-candidate.py: macOS arm64 and Linux x86_64 PASS (quiescence, install, contracts: only `run --help` gained the per-node "lane" text, installed tests, driver_qual). Release archives were checked against the release's SHA256SUMS:
- aarch64-apple-darwin 0d8ec54d83ee484ad25bc31c9b93982d26bda7b85fcbdcb430a7d32a58afeb74
- x86_64-unknown-linux-musl b9b068940cb10093b5ccb37fbecf9c0dc9a7d2791700cc9425c6c2dc5db916f4
- aarch64-unknown-linux-musl a8557ac88b54d31db00c3f5c1659be7f40049656f54d014ef2aeeb29cdf0ed51
Codex 0.160.1, restic 0.19.1 and runtime tag stay the same. Local copies: /tmp/zs-zplan/cand/zeroshot-v10.11.0-aarch64-apple-darwin.tar.gz (Mac) and the tag checkout /tmp/zs-zplan/cand/zeroshot.

Build:
1. Bump the default in toolchain.py to Zeroshot 10.11.0 with the three checksums, following docs/UPGRADE.md. The new tool dir name follows from the versions (zeroshot-10.11.0-codex-0.160.1-runtime2); the 10.10.1 dir and older bindings stay valid by shape (Z1). Update every doc that names the current versions; docs/UPGRADE.md gets a short dated line in its history/log section if it has one (do not rewrite old receipts).
2. zplan version 0.3.1 (pyproject, terminal_planner version constant if any, install.py OWNED keeps "0.3.0"). Tag-free: the orchestrator tags.
3. install.py: print "Добавьте <bin> в PATH" only when that dir is not on PATH already; otherwise say the command is ready.
4. Panel wording: "0/2 milestones влито" -> Russian with correct plural ("этапов"); search for other English words in Russian UI lines of live.py/app.py/planning.py/delivery.py and fix them (keep identifiers like M1, r2, HEAD, Zeroshot, Codex).
5. After a stop is confirmed, the run log must not end with the stale pending line "Остановка M2 запрошена; жду подтверждения Zeroshot" after "M2 завершён" (walkthrough frame 25-m2-stopped): the pending line goes away or comes before the result. While a stop is pending, the key bar does not offer [x].
6. The catalog.bar docstring matches the shrink order the code uses.
7. README: a blank line before the "Required tools" list (or whichever heading/list renders glued); check README renders as intended Markdown.

Acceptance criteria:
- T-A1 toolchain.current() is 10.11.0 with the three checksums; tool dir name test updated; a binding to 10.10.1 still loads and observes with its own executable (existing Z1 tests stay green); no stray "10.10.1" outside toolchain.py/tests/docs history lines.
- T-A2 Version 0.3.1 everywhere it is reported (zplan --version, doctor); install.py OWNED still includes 0.3.0.
- T-A3 Items 3-7 each covered by a test that fails when the fix is reverted (say how you checked).
- T-A4 devtools/ux_walkthrough.py still green: `/tmp/zs-zplan/ux/venv/bin/python devtools/ux_walkthrough.py <dir> --python ~/.local/share/planning-kit/app/0.3.0/bin/python`.
- T-A5 Full suite green with ZPLAN_TEST_WHEELHOUSE=/tmp/zs-zplan/wheelhouse.
