# C0 spike: where the architect's tokens go (2026-10-26)

Verdict: **the cost driver is tool round trips, each re-sending the whole thread**; the reported 5.88M was also
inflated 5.55x by zplan's own accounting. Measured on the re-smoke 2026-10-25b architect session (codex-cli 0.162.1,
gpt-6.1-sol, 11 turns: 4 owner messages, 7 event batches, two trivial slices) from the Codex rollout and zplan's
transcript.

## Accounting bug (fixed in 0.6.0 by RS4)
On `codex exec resume`, `turn.completed.usage` is the thread's running total. zplan added it per turn
(architect.py:624-626, :1096-1097): the 11 running totals (77,699 ... 1,052,821 input) summed to the session file's
5,842,903. Real thread totals: input 1,052,821 (cached 1,018,880, 96.8%), uncached 33.9k, output 5,533. The header
and `session_long` (tui/chat.py:402-417, ROT_TOKENS 2,000,000 of input+output) read the inflated sum: `/new` was
suggested after turn 7 on a real 603k with a 35k context.

## Where the real 1.05M goes
| Request cause | Requests | Input | Share |
|---|---|---|---|
| Turn openings | 11 | 349k | 33% |
| Follow-up after `zplan_status` | 11 | 330k | 31% |
| Follow-up after `zplan_state_update` | 8 | 250k | 24% |
| Tool schema lookups (ALL_TOOLS) | 4 | 79k | 8% |
| Other tool follow-ups | 2 | 45k | 4% |

36 requests x 29.2k average context. The context starts at 14.3k (Codex base instructions ~5.4k, the turn-1 preamble
with method, TOOL_RULES and DRAFT_RULES, tool schemas) and grows ~2.8k per turn: tool output (status ~3.3k per call),
~0.75k of rules repeated by `build_update` (architect.py:314-320) on every resumed turn, call code and reasoning.
The snapshot (0.2-0.5k) and event payloads (150-355 chars) are small. Cost grows roughly with turns squared.

## Matched workload for 0.6.1 targets
Fresh copy of the dogfood repository (one small Python package with unittest tests, checks detected), goal "add a
pure function and its test", profile `/2` accepted, autonomy `auto`, same model and effort, codex-cli pinned; boundary:
from the goal message to milestone merged, counting real thread totals (after RS4) of the architect only (planner and
run workers measured apart). Baseline to re-measure on 0.6.0 + RS4 before C1; provisional target -50%.

## Cuts for 0.6.1 C1 (estimated on this session)
1. Event turns without `zplan_status` + `zplan_state_update` round trips: status-level facts go into the snapshot of
   `build_update`; STATE updates only on a decision or the handoff (method lines 14 and 54,
   resources/architect_method.md). ~45-55%.
2. No schema lookups: exact call signatures in TOOL_RULES (architect.py:73). ~15%.
3. Rules sent once: keep TOOL_RULES and DRAFT_RULES out of `build_update` (or send them only after `/new`), weighed
   against the reason given at architect.py:314-317. ~11%.
4. Rot by context size (last request's input, ~60-80k), not the session sum; the turn counter resets on `/new`.

Reproduce: the analysis scripts were scratch work; the inputs are the Codex rollout of the architect thread (thread id
in the session file of the architect data dir) and that dir's transcript.jsonl; the `usage` of each architect row is
the running total.
