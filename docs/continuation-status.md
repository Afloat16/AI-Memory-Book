# Validation continuation status — 2026-11-12

This is the recovery entry point. Numerical claims come from the linked
completed reports; an implemented runner or downloaded model is not a score.

## Current checkpoint

The original chat executor disconnected again. Work continues through isolated
GitHub Actions jobs, and completed results are committed to durable Git branches.
The [registered hosted run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43178953381)
preserves all source, model, dataset, budget, tokenizer and repetition settings.

| Work item | Current state |
|---|---|
| Native token budgets | All eight cohorts completed; 24,228 paired cases; all cohort integrity gates passed |
| Optional local semantic retrieval | All four cohorts completed, including measured negative results |
| claude-mem supplied-page native FTS | Completed 3,045 native calls and all six context configurations; [run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43179914071) succeeded |
| Actual answers, LoCoMo | All 384 attempts completed; source-free export and model proof saved |
| Actual answers, HotpotQA | Running independently in the registered hosted run |
| Book / native ai-memory workflow | Running independently in the registered hosted run |
| Final aggregate | Tested strict runner ready; activate after both remaining jobs publish their results |

The source tree remains frozen at
`407cda1c5f1dac0e67dfe527d3c23febdad5e818`,
SHA-256 `63cb5eb55cc0356e9c94499739a9d8dcca0307fd6e7a00188b4e25d59fc6a625`.
The native baseline is `5abc85eef00097555366f8524fc81f8b5711ad7a`.
Default retrieval remains lexical. Optional semantic results do not justify
a default change.

## What is already safely published

- The previous interrupted work was recovered from `07a440b` and fast-forwarded
  to main after its existing CI passed. A fresh local check passed 332 tests
  before the executor disconnected.
- Initial recovery manifests and audit records were saved at `d858c8d`.
- Native integrity fixes, semantic cost/model-process checks and hosted
  execution were integrated at `4193623`; its
  [standard CI](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43178953345)
  passed all nine jobs.
- Main `419795c` already published the tested hosted runner and the first
  expanded English/Chinese comparison documentation.
- Integration `e894fea` preserves all eight native and four semantic cohorts,
  the claude-mem harness and its actual completed reports. Original cohort
  branches remain accessible with the pattern
  `validation/20261112-<stage>-43178953381-1`.
- LoCoMo actual answers are saved at `7e99a9050a5db36ba654dfb09fc3e2dee058c169`,
  branch `validation/20261112-answers-locomo-43178953381-1`.
- The claude-mem result is `5c268dc8d0bd9a3d75fce0ca63badba969a3280c`,
  branch `validation/20261112-claude-mem-43179914071-1`.
- Strict final aggregation tools at `c26391d` passed
  [all nine CI jobs](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43181437030).
  Their workflow only activates on `ci/aggregate-memory-validation`.

## Continue without duplicating completed work

1. Check the two running model jobs in the hosted run above. Do not replay them
   or modify their registered inputs. Each job saves public results and its
   completion/failure marker to its own branch.
2. Integrate the exact report blobs and original marker from each finished
   result branch. Preserve failures and unknown request outcomes.
3. Once all required inputs are present, follow
   [final aggregation](final-validation-aggregation.md). It verifies all
   eight native cohorts, four semantic cohorts, 768 actual answer attempts,
   the 72-attempt/42-session workflow and the claude-mem result, then saves
   the eight derived reports and one audit to another Git result branch.
4. Integrate that verified snapshot, update both READMEs and this status file
   with actual generated-answer/workflow scores, and confirm the final main CI.

The original manifests and old completed checkpoints are immutable evidence.
The earlier workspace interruption is recorded in
[its failure audit](../benchmarks/reports/native-environment-interruption-20261112.json).
Only three native cohorts used those older completed checkpoints; the other
five use explicit hosted checkpoints. Never treat an old stale `running`
entry as a completed measurement.

## Interpretation rules

Native block preservation, semantic retrieval quality, actual answer quality,
and complete-workflow costs are distinct claims. Source/budget checks passing
does not mean quality improved. The historical whole-page 512-token regression
remains recorded separately from the native API's improvements. Public and
reused synthetic questions are regression data; the external HotpotQA diagnostic
is bounded and becomes regression data after inspection.

The [comparison guide](comparison.md) includes claude-mem, ai-memory,
billion-context and high-star related architectures. claude-mem's native FTS
experiment does not measure its observer or Chroma pipeline. The ai-memory
workflow explicitly enables generative consolidation; its current default can
also operate without an LLM.

Content-only token counts, native payload tokens and full MCP response tokens
are different surfaces. The historical 43.1% mixed-surface wording is corrected
in the comparison guide without rewriting any frozen raw report.
