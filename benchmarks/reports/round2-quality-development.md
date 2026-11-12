# Q1 score-aware semantic fusion: old development record

Status: **partial**. This is a fusion-policy experiment; lexical remains the product default.

Frozen runtime `49ee4fc04efa89e0110a066094d5d5519f65e588f0ebbcce5f96961e57b29759` at [973657b](https://github.com/Afloat16/AI-Memory-Book/commit/973657b8c6ab29d2462c9d88303fb0baed2faf24); [hosted execution](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43194168722).

All three modes use the same source archive, MiniLM model/index, 900-character pages, top-five results, 8000-character cap and native token assembler. Caps are 512/1024/2048 cl100k_base tokens, each with three repetitions. The original RRF control is checked against the original function's AST and k=60; its surrounding runtime is shared with Q1.

Q1 fixes lexical/semantic weights at 0.75/0.25, preserving score margins. There was no weight search or tuning on the new 256-question cohort. Existing v1 embedding indexes are reusable; only semantic result-cache identity changes.

## Complete evidence and evidence recall

Each cell is **complete evidence / annotation recall**. All budgets and negative results are retained.

| Old cohort | Token cap | Lexical | Original RRF | Q1 |
|---|---:|---:|---:|---:|
| development-synthetic61 | 512 | 85.53% / 86.36% | 63.16% / 68.18% | 80.92% / 83.52% |
| development-synthetic61 | 1024 | 92.11% / 93.18% | 75.66% / 78.98% | 93.42% / 94.32% |
| development-synthetic61 | 2048 | 92.11% / 93.18% | 77.63% / 80.68% | 93.42% / 94.32% |
| regression-authored36 | 512 | 86.67% / 88.89% | 100.00% / 100.00% | 100.00% / 100.00% |
| regression-authored36 | 1024 | 86.67% / 88.89% | 100.00% / 100.00% | 100.00% / 100.00% |
| regression-authored36 | 2048 | 86.67% / 88.89% | 100.00% / 100.00% | 100.00% / 100.00% |
| regression-hotpot128 | 512 | 35.16% / 66.99% | 32.81% / 62.42% | 30.47% / 64.38% |
| regression-hotpot128 | 1024 | 48.44% / 74.51% | 50.78% / 74.18% | 47.66% / 74.18% |
| regression-hotpot128 | 2048 | 48.44% / 74.51% | 50.78% / 74.18% | 47.66% / 74.18% |

## Every paired gain and loss

Counts below are paired questions/annotations; full reports retain their IDs even when aggregate scores tie.

| Old cohort | Cap | Comparison | Complete gains | Complete losses | Annotation gains | Annotation losses |
|---|---:|---|---:|---:|---:|---:|
| development-synthetic61 | 512 | q1_vs_lexical | 2 | 9 | 4 | 9 |
| development-synthetic61 | 512 | q1_vs_legacy_rrf | 29 | 2 | 29 | 2 |
| development-synthetic61 | 1024 | q1_vs_lexical | 2 | 0 | 2 | 0 |
| development-synthetic61 | 1024 | q1_vs_legacy_rrf | 28 | 1 | 28 | 1 |
| development-synthetic61 | 2048 | q1_vs_lexical | 2 | 0 | 2 | 0 |
| development-synthetic61 | 2048 | q1_vs_legacy_rrf | 25 | 1 | 25 | 1 |
| regression-authored36 | 512 | q1_vs_lexical | 4 | 0 | 4 | 0 |
| regression-authored36 | 512 | q1_vs_legacy_rrf | 0 | 0 | 0 | 0 |
| regression-authored36 | 1024 | q1_vs_lexical | 4 | 0 | 4 | 0 |
| regression-authored36 | 1024 | q1_vs_legacy_rrf | 0 | 0 | 0 | 0 |
| regression-authored36 | 2048 | q1_vs_lexical | 4 | 0 | 4 | 0 |
| regression-authored36 | 2048 | q1_vs_legacy_rrf | 0 | 0 | 0 | 0 |
| regression-hotpot128 | 512 | q1_vs_lexical | 2 | 8 | 4 | 12 |
| regression-hotpot128 | 512 | q1_vs_legacy_rrf | 7 | 10 | 24 | 18 |
| regression-hotpot128 | 1024 | q1_vs_lexical | 7 | 8 | 9 | 10 |
| regression-hotpot128 | 1024 | q1_vs_legacy_rrf | 4 | 8 | 14 | 14 |
| regression-hotpot128 | 2048 | q1_vs_lexical | 7 | 8 | 9 | 10 |
| regression-hotpot128 | 2048 | q1_vs_legacy_rrf | 4 | 8 | 14 | 14 |

## Low overlap and evidence combination

These overlapping evaluator groups are fixed diagnostics, not a new independent test. Cell values are complete-evidence rates; group membership is identical across modes.

| Old cohort | Cap | Group | Questions | Lexical | Original RRF | Q1 |
|---|---:|---|---:|---:|---:|---:|
| development-synthetic61 | 512 | low_lexical_overlap_le_0.25 | 32 | 75.00% | 68.75% | 75.00% |
| development-synthetic61 | 512 | multiple_required_evidence | 24 | 41.67% | 50.00% | 50.00% |
| development-synthetic61 | 512 | cross_session | 8 | 100.00% | 100.00% | 100.00% |
| development-synthetic61 | 1024 | low_lexical_overlap_le_0.25 | 32 | 75.00% | 68.75% | 75.00% |
| development-synthetic61 | 1024 | multiple_required_evidence | 24 | 83.33% | 91.67% | 91.67% |
| development-synthetic61 | 1024 | cross_session | 8 | 100.00% | 100.00% | 100.00% |
| development-synthetic61 | 2048 | low_lexical_overlap_le_0.25 | 32 | 75.00% | 68.75% | 75.00% |
| development-synthetic61 | 2048 | multiple_required_evidence | 24 | 83.33% | 91.67% | 91.67% |
| development-synthetic61 | 2048 | cross_session | 8 | 100.00% | 100.00% | 100.00% |
| regression-authored36 | 512 | low_lexical_overlap_le_0.25 | 8 | 50.00% | 100.00% | 100.00% |
| regression-authored36 | 512 | multiple_required_evidence | 6 | 100.00% | 100.00% | 100.00% |
| regression-authored36 | 512 | cross_session | 6 | 100.00% | 100.00% | 100.00% |
| regression-authored36 | 512 | cross_chapter | 6 | 100.00% | 100.00% | 100.00% |
| regression-authored36 | 1024 | low_lexical_overlap_le_0.25 | 8 | 50.00% | 100.00% | 100.00% |
| regression-authored36 | 1024 | multiple_required_evidence | 6 | 100.00% | 100.00% | 100.00% |
| regression-authored36 | 1024 | cross_session | 6 | 100.00% | 100.00% | 100.00% |
| regression-authored36 | 1024 | cross_chapter | 6 | 100.00% | 100.00% | 100.00% |
| regression-authored36 | 2048 | low_lexical_overlap_le_0.25 | 8 | 50.00% | 100.00% | 100.00% |
| regression-authored36 | 2048 | multiple_required_evidence | 6 | 100.00% | 100.00% | 100.00% |
| regression-authored36 | 2048 | cross_session | 6 | 100.00% | 100.00% | 100.00% |
| regression-authored36 | 2048 | cross_chapter | 6 | 100.00% | 100.00% | 100.00% |
| regression-hotpot128 | 512 | low_lexical_overlap_le_0.25 | 3 | 0.00% | 33.33% | 0.00% |
| regression-hotpot128 | 512 | multiple_required_evidence | 128 | 35.16% | 32.81% | 30.47% |
| regression-hotpot128 | 512 | cross_session | 128 | 35.16% | 32.81% | 30.47% |
| regression-hotpot128 | 512 | cross_chapter | 128 | 35.16% | 32.81% | 30.47% |
| regression-hotpot128 | 1024 | low_lexical_overlap_le_0.25 | 3 | 66.67% | 100.00% | 66.67% |
| regression-hotpot128 | 1024 | multiple_required_evidence | 128 | 48.44% | 50.78% | 47.66% |
| regression-hotpot128 | 1024 | cross_session | 128 | 48.44% | 50.78% | 47.66% |
| regression-hotpot128 | 1024 | cross_chapter | 128 | 48.44% | 50.78% | 47.66% |
| regression-hotpot128 | 2048 | low_lexical_overlap_le_0.25 | 3 | 66.67% | 100.00% | 66.67% |
| regression-hotpot128 | 2048 | multiple_required_evidence | 128 | 48.44% | 50.78% | 47.66% |
| regression-hotpot128 | 2048 | cross_session | 128 | 48.44% | 50.78% | 47.66% |
| regression-hotpot128 | 2048 | cross_chapter | 128 | 48.44% | 50.78% | 47.66% |

## Query time and returned tokens

All query repetitions are retained. Timing excludes ingestion, model/index preparation, scoring and checkpoint/export I/O. The same actual query-encoding counter is included in both semantic modes. First/repeat-pass distributions are available in JSON. Each cohort has its own hosted VM; compare its paired modes, not absolute milliseconds across cohorts.

Payload tokens count stable compact JSON for the entire response, including repeated context/result text and metadata, excluding latency/cache-hit diagnostics. They are distinct from the hard context-token budget.

| Old cohort | Cap | Mode | Context tokens | Payload tokens | p50 ms | p95 ms | p99 ms | Query encodes |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| development-synthetic61 | 512 | lexical_native_token_budget | 476.8 | 2094.1 | 6.463 | 13.092 | 14.150 | 0 |
| development-synthetic61 | 512 | legacy_rrf_k60 | 490.1 | 2076.0 | 14.300 | 25.801 | 29.581 | 504 |
| development-synthetic61 | 512 | q1_score_075 | 487.6 | 2138.1 | 13.723 | 25.343 | 28.286 | 504 |
| development-synthetic61 | 1024 | lexical_native_token_budget | 905.5 | 3443.2 | 5.852 | 15.189 | 15.903 | 0 |
| development-synthetic61 | 1024 | legacy_rrf_k60 | 936.6 | 3474.1 | 13.921 | 24.619 | 29.359 | 504 |
| development-synthetic61 | 1024 | q1_score_075 | 924.2 | 3584.8 | 13.449 | 25.492 | 29.577 | 504 |
| development-synthetic61 | 2048 | lexical_native_token_budget | 1260.1 | 4395.2 | 5.009 | 12.903 | 13.569 | 0 |
| development-synthetic61 | 2048 | legacy_rrf_k60 | 1381.6 | 4600.7 | 12.531 | 23.426 | 28.137 | 504 |
| development-synthetic61 | 2048 | q1_score_075 | 1276.9 | 4468.7 | 12.015 | 23.197 | 27.386 | 504 |
| regression-authored36 | 512 | lexical_native_token_budget | 188.5 | 948.1 | 1.578 | 2.710 | 3.071 | 0 |
| regression-authored36 | 512 | legacy_rrf_k60 | 454.2 | 2209.1 | 10.188 | 15.551 | 16.186 | 108 |
| regression-authored36 | 512 | q1_score_075 | 454.2 | 2208.9 | 10.166 | 15.657 | 16.983 | 108 |
| regression-authored36 | 1024 | lexical_native_token_budget | 188.5 | 949.1 | 1.580 | 2.847 | 2.936 | 0 |
| regression-authored36 | 1024 | legacy_rrf_k60 | 485.9 | 2315.9 | 9.944 | 15.679 | 16.161 | 108 |
| regression-authored36 | 1024 | q1_score_075 | 485.9 | 2315.8 | 9.933 | 15.687 | 16.403 | 108 |
| regression-authored36 | 2048 | lexical_native_token_budget | 188.5 | 949.1 | 1.554 | 2.630 | 2.774 | 0 |
| regression-authored36 | 2048 | legacy_rrf_k60 | 485.9 | 2315.9 | 9.472 | 14.900 | 15.694 | 108 |
| regression-authored36 | 2048 | q1_score_075 | 485.9 | 2315.8 | 9.458 | 15.052 | 15.477 | 108 |
| regression-hotpot128 | 512 | lexical_native_token_budget | 479.4 | 2417.9 | 6.899 | 10.032 | 10.845 | 0 |
| regression-hotpot128 | 512 | legacy_rrf_k60 | 480.6 | 2465.4 | 17.992 | 25.568 | 31.775 | 384 |
| regression-hotpot128 | 512 | q1_score_075 | 476.7 | 2454.5 | 18.049 | 25.947 | 30.792 | 384 |
| regression-hotpot128 | 1024 | lexical_native_token_budget | 804.0 | 3971.8 | 6.052 | 9.026 | 9.713 | 0 |
| regression-hotpot128 | 1024 | legacy_rrf_k60 | 814.9 | 4064.9 | 17.103 | 24.969 | 30.416 | 384 |
| regression-hotpot128 | 1024 | q1_score_075 | 813.2 | 4048.8 | 17.249 | 25.244 | 30.257 | 384 |
| regression-hotpot128 | 2048 | lexical_native_token_budget | 805.8 | 3979.0 | 6.153 | 9.036 | 9.550 | 0 |
| regression-hotpot128 | 2048 | legacy_rrf_k60 | 816.2 | 4069.6 | 17.168 | 25.388 | 30.459 | 384 |
| regression-hotpot128 | 2048 | q1_score_075 | 814.4 | 4055.5 | 17.477 | 25.289 | 30.089 | 384 |

## Shared preparation costs

Fresh indexing here is experimental preparation, not an upgrade requirement for existing compatible indexes. Ordinary lexical operation requires no model or embedding index.

| Old cohort | Ingest ms | Model load ms | Index build ms | Windows | Vector bytes |
|---|---:|---:|---:|---:|---:|
| development-synthetic61 | 842.9 | 897.3 | 95831.0 | 4093 | 6286848 |
| regression-authored36 | 34.9 | 1293.7 | 1161.7 | 42 | 64512 |
| regression-hotpot128 | 2310.9 | 1239.7 | 131998.8 | 2323 | 3568128 |

## Unsupported questions and validity

A nonempty context on an unsupported question is a retrieval diagnostic. This experiment does not generate answers, so this is not an answer error rate.

| Old cohort | Cap | Unsupported questions | Lexical nonempty | RRF nonempty | Q1 nonempty |
|---|---:|---:|---:|---:|---:|
| development-synthetic61 | 512 | 16 | 75.00% | 100.00% | 100.00% |
| development-synthetic61 | 1024 | 16 | 75.00% | 100.00% | 100.00% |
| development-synthetic61 | 2048 | 16 | 75.00% | 100.00% | 100.00% |
| regression-authored36 | 512 | 6 | 33.33% | 100.00% | 100.00% |
| regression-authored36 | 1024 | 6 | 33.33% | 100.00% | 100.00% |
| regression-authored36 | 2048 | 6 | 33.33% | 100.00% | 100.00% |
| regression-hotpot128 | 512 | 0 | — | — | — |
| regression-hotpot128 | 1024 | 0 | — | — | — |
| regression-hotpot128 | 2048 | 0 | — | — | — |

Accepted reports passed source/index-address stability, source-span projection, project scope, character/token caps, token/model metadata, result-cache isolation and repeat-context checks. These are measurement checks, not evidence of universal semantic memory. Public raw and summary reports remain linked below; private source datasets and model artifacts are not part of Git publication.

## Reports

- development-synthetic61: [full rows](../results/round2-quality-development-synthetic61.json.gz) · [summary](../results/round2-quality-development-synthetic61.summary.json)
- regression-authored36: [full rows](../results/round2-quality-regression-authored36.json.gz) · [summary](../results/round2-quality-regression-authored36.summary.json)
- regression-hotpot128: [full rows](../results/round2-quality-regression-hotpot128.json.gz) · [summary](../results/round2-quality-regression-hotpot128.summary.json)
