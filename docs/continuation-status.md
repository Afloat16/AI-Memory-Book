# Completed validation and recovery record — 2026-11-12

**The registered continuation is complete.** All fixed cohorts have published
results, and the [strict final audit](../benchmarks/reports/hosted-final-aggregation.json)
is `complete-verified-snapshot`: **80 input files checked, eight derived
reports verified, all four strict summarizers exited successfully**.

The native workflow is correctly recorded as `completed_with_failures`.
Its full attempt matrix exists; 35 model consolidations reached the fixed
output limit and were rejected by the native product. Those outcomes remain
part of the measurement, rather than missing work or an infrastructure pass.

## Completed work

| Work item | Verified result | Evidence |
|---|---|---|
| Native token-budget matrix | 8 cohorts; 2,019 query instances; 24,228 paired query/configuration cases; 251 complete-case gains, zero complete-case or fitting-block losses | [Native report](../benchmarks/RESULTS-native-token-budget.md) |
| Optional local semantics | 4 cohorts; 1,347 questions; 24,246 actual recall calls; all gains and losses retained | [Semantic report](../benchmarks/RESULTS-semantic-retrieval.md) |
| Actual local answers | 128 LoCoMo + 128 HotpotQA questions × 3 modes = 768 completed model calls; zero transport errors or truncated responses | [Answer report](../benchmarks/RESULTS-local-answers.md) |
| Native Book / ai-memory workflow | 42 accepted capture sessions, 42 consolidation-model calls and 72 answer calls; all usage known; 7/42 consolidations succeed under the fixed model/output cap | [Workflow report](../benchmarks/RESULTS-full-workflow.md) |
| claude-mem native FTS | 1,015 questions × 3 repetitions = 3,045 native calls; six context configurations, fixed source/runtime and identical supplied pages | [Component report](../benchmarks/results/claude-mem-components-public.md) |
| Latest token-counting optimization | All 2,016 complete development payloads unchanged; p95 improves 7.73%–14.45% in every 512-token setting; larger-budget costs retained | [Performance report](token-prefix-performance.md) |

The two main READMEs now show the recommended default and latest verified
comparison, rather than a chronological sequence of intermediate results.
Detailed curves, unsuccessful cases, token-surface corrections and historical
records remain in the linked reports and [comparison guide](comparison.md).

## Decisions from the four original concerns

1. **Semantic paraphrases and distant evidence.** The optional model improves
   the authored low-overlap diagnostic from 2/6 to 6/6, and some public
   low-overlap/multi-session subsets. It also loses useful lexical matches:
   public 512-token completeness is 66.41% lexical versus 62.56% semantic.
   Default retrieval therefore stays lexical. This is a measured tradeoff,
   not a claim that general semantic memory is solved.
2. **Small budgets and tails.** Native assembly preserves every previously
   fitting block across the registered matrix. The separate latest
   exact-output optimization reduces p95 in all four 512-token development
   settings. Three 2,048-token settings have p95 regressions of 0.50%–2.43%.
   The original whole-page 66.72% to 66.26% regression has a different baseline
   and remains recorded; it is not erased by the native API result.
3. **Generated answers and full workflow costs.** These now have actual
   measurements: 768 answer calls plus 114 calls in the separate workflow,
   with fixed models, process ownership, source/request/response hashes,
   usage, timings, failed attempts and explicit phase boundaries.
   The small Qwen model does not establish a stable general answer-quality
   gain, and native consolidation failures under its 1,000-output-token cap
   cannot be generalized to other model configurations.
4. **Independent transfer.** The fixed HotpotQA diagnostic contains 128
   independently authored multi-hop questions, all 1,272 supplied paragraphs
   and 306 support facts. It broadens the evidence beyond synthetic templates,
   within a scoped-distractor setting. All 128 are answerable, and model
   pretraining overlap is unknown. After inspection it is regression data,
   not a new untouched test set for further tuning.

## Source and experiment identities

| Identity | Fixed value / role |
|---|---|
| Common-page Book comparison | `0ab49d4f2be6aabe5e51c3314bb9369041af5369`; its original shared-packing report is retained |
| Native baseline | `5abc85eef00097555366f8524fc81f8b5711ad7a` |
| Frozen native/semantic/answer candidate | `407cda1c5f1dac0e67dfe527d3c23febdad5e818`; src hash `63cb5eb55cc0356e9c94499739a9d8dcca0307fd6e7a00188b4e25d59fc6a625` |
| Latest exact-output performance candidate | `e8a878ec2d8c4b0930e9a5cff20ce954f7ac6818`; src hash `6fdad7b9bf0eef50ec925ceeed3ca45fe84d2eb22973c753118df2d0f67f6ba2` |
| claude-mem component | `2cfed7620c1b44db87c7f04cbf073ec37efca38d`, package 15.18.0, Bun 1.3.13 |
| Generated answers | Qwen2.5-0.5B-Instruct Q4_K_M, llama.cpp b12110, 4 CPU threads; 4,096 context for the 768-answer experiment |
| Native workflow | Same model artifact, separately registered 16,384 context and 1,000-token consolidation limit; maximum 128 answer tokens |

Only `src/memory_book/token_budget.py` changes between the frozen candidate
and the latest performance candidate; the other 16 source files match.
The development proof compares every returned payload field except latency.
Its timings are not substituted into the older public or synthetic regression
reports. The semantic mode, ranking parameters, source corpus and scored
generation requests were not retuned or replayed.

## Published execution and verification

- [Hosted measurements](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43178953381):
  every registered cohort produced its reports. The workflow job's failure
  conclusion preserves the 35 native consolidation rejections; its dedicated
  assessor accepted the complete recorded attempt matrix.
- [claude-mem actual native run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43179914071):
  successful source/runtime checks, native smoke and full 3,045-call run.
- [Latest exact-output performance run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43183816029):
  successful equivalence and all 12 timing configurations.
- [Final strict aggregation](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43185554831):
  success; reports saved at `dbdb38084d65b69700e1e1ff2fa3b6408c7d786f`.
- [Integrated code CI](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43185554873):
  all nine jobs passed. [Current main CI](https://github.com/Afloat16/AI-Memory-Book/actions/workflows/ci.yml)
  tracks subsequent documentation and recovery-tool integration.

## Recovery and reproduction

Completed data remains in Git with its original hashes and result branches;
no large model or dataset download is needed to audit the saved reports.
From a checkout containing all results:

```bash
python -m pip install -e ".[mcp,clients,tokens,semantic]" pyarrow
python scripts/aggregate_hosted_validation.py
```

This derives the reports without retrieval or generation calls. See
[the exact aggregation inventory](final-validation-aggregation.md) and
[hosted interruption recovery](hosted-validation-recovery.md) and
[fixed-run automatic result collection](automatic-final-validation.md).
The collector executes trusted main code, imports only verified public files,
and publishes its own result branch; it never replays model requests or moves main.
This completed snapshot does not require another collector run.
New generation experiments must use fresh state and output prefixes; unknown
in-flight requests must not be silently replayed.

The continuation recovered prior published commits through `07a440b`,
saved recovery plans at `d858c8d`, moved execution off the disconnected chat
workspace at `4193623`, and retained every completed cohort separately.
The original failure record remains in
[the interruption audit](../benchmarks/reports/native-environment-interruption-20261112.json).
All registered work above is now finished; broad semantic capability,
larger-model answer quality, production concurrency, watcher overhead,
provider billing and electricity remain outside the established results.
