# Development runtime economics (0.4.0)

Status: measuring (2026-10-16). Owner task: finish 0.4.0 within Claude limits with a DeepSeek worker and show that quality did not drop.
critic econ-method (session 01a1459e-10f1-7c82-9364-93ccf75a1776): GO WITH CHANGES (applied below; A/B dropped).

## Method

- M1 cost: unit = merged task of a comparable class (easy / medium / product / core); cost per acceptance criterion is secondary.
  Raw sources: `~/.local/state/zeroshot/runs/*/runs.sqlite3`, `~/.codex/sessions/**` (usage metadata only, cumulative
  counters deduplicated), the orchestrator's `~/.claude/projects/**` usage fields, git merges, task files. Failed and
  repair attempts and critic spend are included; experiment spend is shown separately; runs before and after the
  2026-10-16 targeted-test preamble are kept apart. Each number carries its command, window and run/session/SHA.
  Without the provider quotas this gives spend and a forecast, not "fits the limits".
- M2 seeded review (diagnostic, small sample): defects seeded into scratch copies of merged DeepSeek diffs, reviewed by
  fresh sol xhigh code-reviewer sessions that see the original task and the diff against its real base, with the seed
  count and key hidden. Seeds are modelled on historical findings, use only dummy secrets, and are scored per class and
  severity. Clean controls count unfounded findings; a real defect found in a control is checked separately. This
  measures the static code reviewer only (production also has the acceptance reviewer and tests); recall is not
  attributed to a runtime.
- M3 A/B Claude vs DeepSeek: dropped (one run proves little and spends the Claude budget this work saves). Revisit only
  for a concrete doubt with a set budget, in separate NAME/worktrees on a fixed SHA.

## Quality criterion (fixed before the data)

A material regression is any of the following:
- a P1, or two or more P2s in one stage, found by the critic accumulated-diff review (replaces owner review #2) or the release gate in code written on the DeepSeek
  runtime, with causation confirmed beyond `git blame`;
- a post-merge defect of the same severity in such code;
- seeded P1-class recall below 3/4.

Either one → the stage's next tasks pause and the runtime choice is re-argued with the critic.

## Stop rule

A task whose Codex spend exceeds 2x the median of its class is a signal to review it, not an automatic stop. With few
samples an absolute per-task cap also applies (set from M1). A stop pauses the next runs; a live run is never interrupted.

## Results

M1 (2026-10-16; scripts copied to ~/zs-pause/econ/: econ_runs, econ_codex, econ_orch, econ_tasks, econ_eras, econ_forecast; M = million tokens, cached+cache-write / output):

| Class | Runtime | n | Claude per task (run + orchestrator) | Codex per task | Yandex per task | Wall min |
|---|---|---|---|---|---|---|
| core | Claude | 17 | 25.2M / 248K + ~5.0M / 26K | critic only | - | 68 |
| medium product | Claude | 3 | 23.5M / 147K + ~5.0M / 26K | critic only | - | 77 |
| medium product | DeepSeek | 1 | orchestrator ~7.7M / 44K | 13.6M / 93K + critic ~1.4M / 17K | 49.9M / 269K | 495 (stalls incl.) |
| medium | DeepSeek | 2 | orchestrator ~7.7M / 44K | 11.7M / 119K | 14.1M / 92K | 86 |
| easy | DeepSeek | 2 | orchestrator ~7.7M / 44K | 1.7M / 18K | 1.4M / 7K | 18 |

- On the DeepSeek runtime, Claude spend drops about 4x per task: only the orchestrator is left, and that is now the main Claude cost to cut.
- The sample is small: medium product n=1 per runtime side, and no DeepSeek core run yet.
- Forecast for the rest of 0.4.0 (8-14 tasks, all DeepSeek), cached+cw / out:

| Payer | Low | High |
|---|---|---|
| Claude | 41M / 0.2M | 135M / 0.9M |
| Codex | 59M / 0.6M | 247M / 2.8M |
| Yandex | 91M / 0.5M | 592M / 3.8M |

- The high case is exceeded if core tasks need 7+ rounds.
- Gaps: force-stopped visits record no usage in Zeroshot (DeepSeek ones recovered from Codex sessions); subagent usage is undercounted; `/code-review ultra` has no local log.

M2 (2026-10-16; 10 copies of 4 merged DeepSeek diffs: ds-walk-stale-index, ds-walkthrough-installed, tui-quit-race,
ds-export-check; one fresh sol xhigh code-reviewer session each; reviews in /tmp/zs-seed/cNN/review.md):
- Seeds 8/8 found and rejected, each at the seeded line. KEY.json was lost with the seeding session; the key was
  reconstructed as the line diff of each candidate against its merged diff (checkable from the same files).
- By class: P1-class 4/4 (c03 release before hand-over, c05 refusal turned into a warning, c07 private path not
  redacted, c10 inverted Release condition); P2-class 3/3 (c01 glob width, c02 finish out of `finally`, c04 timeout
  900 -> 600); test weakening 1/1 (c09 count -> presence).
- Severity: reviewer P1 on c07, c10; P2 on c03, c05 (under-rated by one level); P2 on the rest.
- Controls 2/2 accepted, no findings (0 unfounded).
- Criterion "seeded P1-class recall below 3/4" is not met (4/4); small sample, static reviewer only.
