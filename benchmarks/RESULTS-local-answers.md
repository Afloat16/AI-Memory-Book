# Real local-model answers: completed registered evaluation

**768 actual answer attempts** across 128 LoCoMo and 128 HotpotQA questions, each with three retrieval modes.

The model is the pinned Qwen2.5-0.5B-Instruct Q4_K_M artifact served by llama.cpp b12110 on CPU. All modes use the same fixed prompt, 4096-token model context, 512-token cl100k_base evidence cap, 8000-character cap, top-five limit, temperature 0 and maximum 128 output tokens. Engine order rotates per question. Prompt reuse is disabled. There is one generation per question/mode; these results do not establish performance for larger or hosted models.

## Answer quality

EM is normalized exact match; F1 is the fixed lexical token-overlap metric. Both use answerable questions only. Unsupported questions have a separate exact `INSUFFICIENT_EVIDENCE` abstention rate. Failed/interrupted attempts retain zero quality credit and remain in denominators. These are actual generated-answer scores, not evidence completeness or a semantic judge.

| Cohort | Retrieval mode | Answerable / unsupported | EM | F1 | Exact abstention | Errors / truncated |
|---|---|---:|---:|---:|---:|---:|
| locomo | Prior default + excerpt pack | 86 / 42 | 4.65% | 25.58% | 0.00% | 0 / 0 |
| locomo | Native token budget | 86 / 42 | 3.49% | 24.07% | 0.00% | 0 / 0 |
| locomo | Semantic + native token budget | 86 / 42 | 3.49% | 25.13% | 0.00% | 0 / 0 |
| hotpotqa | Prior default + excerpt pack | 128 / 0 | 10.16% | 19.72% | n/a | 0 / 0 |
| hotpotqa | Native token budget | 128 / 0 | 10.94% | 20.02% | n/a | 0 / 0 |
| hotpotqa | Semantic + native token budget | 128 / 0 | 9.38% | 17.46% | n/a | 0 / 0 |

## Generation and context costs

Endpoint latency includes the sequential loopback HTTP request, actual inference and decoded response. It excludes ingestion and retrieval preparation. Prompt/output counts are reported by the verified local model server; they are not a provider bill. The evidence cap uses cl100k_base, whereas these usage counts use the model's tokenizer.

| Cohort | Mode | Mean evidence tokens | Answer p50 / p95 / p99 ms | Reported prompt tokens | Reported output tokens | Reported total tokens |
|---|---|---:|---:|---:|---:|---:|
| locomo | Prior default + excerpt pack | 442.3 | 2606.032 / 3109.209 / 3426.894 | 78629 | 2439 | 81068 |
| locomo | Native token budget | 491.4 | 2879.796 / 3271.855 / 3449.737 | 86622 | 2409 | 89031 |
| locomo | Semantic + native token budget | 492.1 | 2865.529 / 3253.758 / 3530.685 | 86920 | 2291 | 89211 |
| hotpotqa | Prior default + excerpt pack | 451.4 | 4797.126 / 5825.333 / 6331.170 | 88447 | 2120 | 90567 |
| hotpotqa | Native token budget | 479.4 | 4951.165 / 5847.108 / 6392.085 | 93371 | 2031 | 95402 |
| hotpotqa | Semantic + native token budget | 480.6 | 4993.055 / 5852.129 / 6872.990 | 93672 | 2056 | 95728 |

## Once-per-cohort preparation

Each engine independently imports the same histories. Semantic mode explicitly builds its local index. All configured summaries are extractive and make zero generative summary calls. Retrieval and packing totals cover one preparation call per question. They are separate stage observations, not a complete workflow stopwatch; source exports retain original session and page coordinates.

| Cohort | Mode | Import ms | Semantic preparation ms | Recall ms total | External packing ms total | Closed database bytes |
|---|---|---:|---:|---:|---:|---:|
| locomo | Prior default + excerpt pack | 1419.158 | n/a | 457.225 | 107.541 | 12881920 |
| locomo | Native token budget | 1377.902 | n/a | 794.917 | 0.000 | 12881920 |
| locomo | Semantic + native token budget | 3482.260 | 96938.486 | 2126.193 | 0.000 | 16830464 |
| hotpotqa | Prior default + excerpt pack | 2371.842 | n/a | 591.038 | 127.756 | 16625664 |
| hotpotqa | Native token budget | 2318.991 | n/a | 911.254 | 0.000 | 16625664 |
| hotpotqa | Semantic + native token budget | 2409.779 | 133767.620 | 2508.854 | 0.000 | 21504000 |

## Paired gains and losses

The first comparison isolates the saved native-budget continuation relative to the prior default. The second adds semantic candidate ranking while retaining native packing. Every changed question ID and its before/after score is preserved in the machine-readable assessment.

| Cohort | Comparison | Metric | Improved questions | Regressed questions |
|---|---|---|---:|---:|
| locomo | Prior default + excerpt pack → Native token budget | normalized_exact_match | 0 | 1 |
| locomo | Prior default + excerpt pack → Native token budget | lexical_token_f1 | 9 | 9 |
| locomo | Native token budget → Semantic + native token budget | normalized_exact_match | 1 | 1 |
| locomo | Native token budget → Semantic + native token budget | lexical_token_f1 | 22 | 22 |
| hotpotqa | Prior default + excerpt pack → Native token budget | normalized_exact_match | 1 | 0 |
| hotpotqa | Prior default + excerpt pack → Native token budget | lexical_token_f1 | 2 | 1 |
| hotpotqa | Native token budget → Semantic + native token budget | normalized_exact_match | 5 | 7 |
| hotpotqa | Native token budget → Semantic + native token budget | lexical_token_f1 | 11 | 24 |

## Boundaries and reproducibility

- LoCoMo is previously observed retrieval regression data. HotpotQA is the separately frozen scoped-distractor multi-hop diagnostic; after scoring it also becomes regression data. Model pretraining overlap is unknown.
- Lexical EM/F1 can penalize correct paraphrases and reward partial word overlap. No human or model semantic judge is claimed. One small quantized model and 256 bounded questions cannot establish general answer quality or broad transfer.
- The owned-process proof verifies model/archive/extracted-runtime hashes and launch arguments, and binds them to the completed trace and prepared inputs. Identical model identity does not guarantee deterministic generation.
- The original licensed passages, prompts and answer text remain in ignored private work artifacts. Public reports retain request/response/context/answer hashes, per-attempt scores, failure state, usage and timing.
- Native competitor observation, consolidation and adaptive follow-up are outside this experiment. The separate full-workflow diagnostic uses different model context settings and must not be pooled with these scores.

- locomo: [full exported metrics](results/local-answer-final-locomo.json.gz), [summary](results/local-answer-final-locomo.summary.json); reported model comparability: `same_reported_identity`.
- hotpotqa: [full exported metrics](results/local-answer-final-hotpotqa.json.gz), [summary](results/local-answer-final-hotpotqa.summary.json); reported model comparability: `same_reported_identity`.

[Frozen model and cohort plan](experiments/local-answer-plan.json) · [Execution plan](experiments/local-answer-execution.json) · [Evaluation guide](../docs/answer-evaluation.md) · [Machine-readable assessment](results/local-answer-final-assessment.json)

Reproduce the verification and tables without making model calls:

```bash
python scripts/summarize_local_answers.py
```
