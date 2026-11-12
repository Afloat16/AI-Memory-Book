# Q2 lexical-anchor semantic fusion: old development record

Status: **completed**. This is a fusion-policy experiment; lexical remains the product default.

Frozen runtime `cce621cbe62b0e8d7a94fbdb023372e0ff2004ca390e2ffd5c01863596059b43` at [6286564](https://github.com/Afloat16/AI-Memory-Book/commit/6286564e33f09db9863a80613771722c32ba363b); [hosted execution](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43196880064).

All four modes use the same source archive, MiniLM model/index, 900-character pages, top-five results, 8000-character cap and native token assembler. Caps are 512/1024/2048 cl100k_base tokens, each with three repetitions. Original RRF(k=60) and Q1 score-fusion controls are checked against their original Git function bodies and constants; all four modes share the Q2 surrounding runtime.

Q2 promotes only the first page from the existing lexical order, preserving every other page in original RRF relative order and retaining every page original RRF score. It adds no model call or score threshold. Frozen Q1 remains a .75/.25 control. The new 256-question cohort was not inspected or used for tuning. Existing v1 indexes are reusable; Q2 result-cache identity is version 3.

## Complete evidence and evidence recall

Each cell is **complete evidence / annotation recall**. All budgets and negative results are retained.

| Old cohort | Token cap | Lexical | Original RRF | Q1 | Q2 |
|---|---:|---:|---:|---:|---:|
| development-synthetic61 | 512 | 85.53% / 86.36% | 63.16% / 68.18% | 80.92% / 83.52% | 81.58% / 84.09% |
| development-synthetic61 | 1024 | 92.11% / 93.18% | 75.66% / 78.98% | 93.42% / 94.32% | 92.11% / 93.18% |
| development-synthetic61 | 2048 | 92.11% / 93.18% | 77.63% / 80.68% | 93.42% / 94.32% | 92.11% / 93.18% |
| regression-authored36 | 512 | 86.67% / 88.89% | 100.00% / 100.00% | 100.00% / 100.00% | 100.00% / 100.00% |
| regression-authored36 | 1024 | 86.67% / 88.89% | 100.00% / 100.00% | 100.00% / 100.00% | 100.00% / 100.00% |
| regression-authored36 | 2048 | 86.67% / 88.89% | 100.00% / 100.00% | 100.00% / 100.00% | 100.00% / 100.00% |
| regression-public1015 | 512 | 66.41% / 62.18% | 62.40% / 59.77% | 69.65% / 66.12% | 68.10% / 64.47% |
| regression-public1015 | 1024 | 72.88% / 69.54% | 70.88% / 68.27% | 76.43% / 73.48% | 74.27% / 71.70% |
| regression-public1015 | 2048 | 72.88% / 69.54% | 70.88% / 68.40% | 76.43% / 73.48% | 74.27% / 71.83% |
| regression-hotpot128 | 512 | 35.16% / 66.99% | 33.59% / 63.07% | 32.03% / 65.03% | 34.38% / 65.36% |
| regression-hotpot128 | 1024 | 48.44% / 74.51% | 50.00% / 73.20% | 46.88% / 73.86% | 50.78% / 74.84% |
| regression-hotpot128 | 2048 | 48.44% / 74.51% | 50.00% / 73.20% | 46.88% / 73.86% | 50.78% / 74.84% |

## Every paired gain and loss

Counts below are paired questions/annotations; full reports retain their IDs even when aggregate scores tie.

| Old cohort | Cap | Comparison | Complete gains | Complete losses | Annotation gains | Annotation losses |
|---|---:|---|---:|---:|---:|---:|
| development-synthetic61 | 512 | q2_vs_lexical | 1 | 7 | 3 | 7 |
| development-synthetic61 | 512 | q2_vs_legacy_rrf | 29 | 1 | 29 | 1 |
| development-synthetic61 | 512 | q2_vs_q1 | 5 | 4 | 5 | 4 |
| development-synthetic61 | 1024 | q2_vs_lexical | 2 | 2 | 2 | 2 |
| development-synthetic61 | 1024 | q2_vs_legacy_rrf | 25 | 0 | 25 | 0 |
| development-synthetic61 | 1024 | q2_vs_q1 | 1 | 3 | 1 | 3 |
| development-synthetic61 | 2048 | q2_vs_lexical | 2 | 2 | 2 | 2 |
| development-synthetic61 | 2048 | q2_vs_legacy_rrf | 22 | 0 | 22 | 0 |
| development-synthetic61 | 2048 | q2_vs_q1 | 1 | 3 | 1 | 3 |
| regression-authored36 | 512 | q2_vs_lexical | 4 | 0 | 4 | 0 |
| regression-authored36 | 512 | q2_vs_legacy_rrf | 0 | 0 | 0 | 0 |
| regression-authored36 | 512 | q2_vs_q1 | 0 | 0 | 0 | 0 |
| regression-authored36 | 1024 | q2_vs_lexical | 4 | 0 | 4 | 0 |
| regression-authored36 | 1024 | q2_vs_legacy_rrf | 0 | 0 | 0 | 0 |
| regression-authored36 | 1024 | q2_vs_q1 | 0 | 0 | 0 | 0 |
| regression-authored36 | 2048 | q2_vs_lexical | 4 | 0 | 4 | 0 |
| regression-authored36 | 2048 | q2_vs_legacy_rrf | 0 | 0 | 0 | 0 |
| regression-authored36 | 2048 | q2_vs_q1 | 0 | 0 | 0 | 0 |
| regression-public1015 | 512 | q2_vs_lexical | 30 | 19 | 46 | 28 |
| regression-public1015 | 512 | q2_vs_legacy_rrf | 46 | 9 | 51 | 14 |
| regression-public1015 | 512 | q2_vs_q1 | 10 | 20 | 17 | 30 |
| regression-public1015 | 1024 | q2_vs_lexical | 33 | 24 | 47 | 30 |
| regression-public1015 | 1024 | q2_vs_legacy_rrf | 25 | 3 | 30 | 3 |
| regression-public1015 | 1024 | q2_vs_q1 | 8 | 22 | 14 | 28 |
| regression-public1015 | 2048 | q2_vs_lexical | 33 | 24 | 47 | 29 |
| regression-public1015 | 2048 | q2_vs_legacy_rrf | 25 | 3 | 30 | 3 |
| regression-public1015 | 2048 | q2_vs_q1 | 8 | 22 | 15 | 28 |
| regression-hotpot128 | 512 | q2_vs_lexical | 9 | 10 | 15 | 20 |
| regression-hotpot128 | 512 | q2_vs_legacy_rrf | 2 | 1 | 11 | 4 |
| regression-hotpot128 | 512 | q2_vs_q1 | 11 | 8 | 17 | 16 |
| regression-hotpot128 | 1024 | q2_vs_lexical | 13 | 10 | 18 | 17 |
| regression-hotpot128 | 1024 | q2_vs_legacy_rrf | 1 | 0 | 5 | 0 |
| regression-hotpot128 | 1024 | q2_vs_q1 | 9 | 4 | 13 | 10 |
| regression-hotpot128 | 2048 | q2_vs_lexical | 13 | 10 | 18 | 17 |
| regression-hotpot128 | 2048 | q2_vs_legacy_rrf | 1 | 0 | 5 | 0 |
| regression-hotpot128 | 2048 | q2_vs_q1 | 9 | 4 | 13 | 10 |

## Low overlap and evidence combination

These overlapping evaluator groups are fixed diagnostics, not a new independent test. Cell values are complete-evidence rates; group membership is identical across modes.

| Old cohort | Cap | Group | Questions | Lexical | Original RRF | Q1 | Q2 |
|---|---:|---|---:|---:|---:|---:|---:|
| development-synthetic61 | 512 | low_lexical_overlap_le_0.25 | 32 | 75.00% | 68.75% | 75.00% | 68.75% |
| development-synthetic61 | 512 | multiple_required_evidence | 24 | 41.67% | 50.00% | 50.00% | 45.83% |
| development-synthetic61 | 512 | cross_session | 8 | 100.00% | 100.00% | 100.00% | 100.00% |
| development-synthetic61 | 1024 | low_lexical_overlap_le_0.25 | 32 | 75.00% | 68.75% | 75.00% | 68.75% |
| development-synthetic61 | 1024 | multiple_required_evidence | 24 | 83.33% | 91.67% | 91.67% | 91.67% |
| development-synthetic61 | 1024 | cross_session | 8 | 100.00% | 100.00% | 100.00% | 100.00% |
| development-synthetic61 | 2048 | low_lexical_overlap_le_0.25 | 32 | 75.00% | 68.75% | 75.00% | 68.75% |
| development-synthetic61 | 2048 | multiple_required_evidence | 24 | 83.33% | 91.67% | 91.67% | 91.67% |
| development-synthetic61 | 2048 | cross_session | 8 | 100.00% | 100.00% | 100.00% | 100.00% |
| regression-authored36 | 512 | low_lexical_overlap_le_0.25 | 8 | 50.00% | 100.00% | 100.00% | 100.00% |
| regression-authored36 | 512 | multiple_required_evidence | 6 | 100.00% | 100.00% | 100.00% | 100.00% |
| regression-authored36 | 512 | cross_session | 6 | 100.00% | 100.00% | 100.00% | 100.00% |
| regression-authored36 | 512 | cross_chapter | 6 | 100.00% | 100.00% | 100.00% | 100.00% |
| regression-authored36 | 1024 | low_lexical_overlap_le_0.25 | 8 | 50.00% | 100.00% | 100.00% | 100.00% |
| regression-authored36 | 1024 | multiple_required_evidence | 6 | 100.00% | 100.00% | 100.00% | 100.00% |
| regression-authored36 | 1024 | cross_session | 6 | 100.00% | 100.00% | 100.00% | 100.00% |
| regression-authored36 | 1024 | cross_chapter | 6 | 100.00% | 100.00% | 100.00% | 100.00% |
| regression-authored36 | 2048 | low_lexical_overlap_le_0.25 | 8 | 50.00% | 100.00% | 100.00% | 100.00% |
| regression-authored36 | 2048 | multiple_required_evidence | 6 | 100.00% | 100.00% | 100.00% | 100.00% |
| regression-authored36 | 2048 | cross_session | 6 | 100.00% | 100.00% | 100.00% | 100.00% |
| regression-authored36 | 2048 | cross_chapter | 6 | 100.00% | 100.00% | 100.00% | 100.00% |
| regression-public1015 | 512 | low_lexical_overlap_le_0.25 | 326 | 46.01% | 47.55% | 52.15% | 50.00% |
| regression-public1015 | 512 | multiple_required_evidence | 104 | 16.35% | 18.27% | 20.19% | 15.38% |
| regression-public1015 | 512 | cross_session | 76 | 10.53% | 13.16% | 13.16% | 11.84% |
| regression-public1015 | 1024 | low_lexical_overlap_le_0.25 | 326 | 54.91% | 56.75% | 59.51% | 57.98% |
| regression-public1015 | 1024 | multiple_required_evidence | 104 | 25.00% | 25.96% | 32.69% | 25.96% |
| regression-public1015 | 1024 | cross_session | 76 | 18.42% | 18.42% | 22.37% | 18.42% |
| regression-public1015 | 2048 | low_lexical_overlap_le_0.25 | 326 | 54.91% | 56.75% | 59.51% | 57.98% |
| regression-public1015 | 2048 | multiple_required_evidence | 104 | 25.00% | 25.96% | 32.69% | 25.96% |
| regression-public1015 | 2048 | cross_session | 76 | 18.42% | 18.42% | 22.37% | 18.42% |
| regression-hotpot128 | 512 | low_lexical_overlap_le_0.25 | 3 | 0.00% | 33.33% | 0.00% | 33.33% |
| regression-hotpot128 | 512 | multiple_required_evidence | 128 | 35.16% | 33.59% | 32.03% | 34.38% |
| regression-hotpot128 | 512 | cross_session | 128 | 35.16% | 33.59% | 32.03% | 34.38% |
| regression-hotpot128 | 512 | cross_chapter | 128 | 35.16% | 33.59% | 32.03% | 34.38% |
| regression-hotpot128 | 1024 | low_lexical_overlap_le_0.25 | 3 | 66.67% | 100.00% | 66.67% | 100.00% |
| regression-hotpot128 | 1024 | multiple_required_evidence | 128 | 48.44% | 50.00% | 46.88% | 50.78% |
| regression-hotpot128 | 1024 | cross_session | 128 | 48.44% | 50.00% | 46.88% | 50.78% |
| regression-hotpot128 | 1024 | cross_chapter | 128 | 48.44% | 50.00% | 46.88% | 50.78% |
| regression-hotpot128 | 2048 | low_lexical_overlap_le_0.25 | 3 | 66.67% | 100.00% | 66.67% | 100.00% |
| regression-hotpot128 | 2048 | multiple_required_evidence | 128 | 48.44% | 50.00% | 46.88% | 50.78% |
| regression-hotpot128 | 2048 | cross_session | 128 | 48.44% | 50.00% | 46.88% | 50.78% |
| regression-hotpot128 | 2048 | cross_chapter | 128 | 48.44% | 50.00% | 46.88% | 50.78% |

## Query time and returned tokens

All query repetitions are retained. Timing excludes ingestion, model/index preparation, scoring and checkpoint/export I/O. The same actual query-encoding counter is included in all three semantic modes. First/repeat-pass distributions are available in JSON. Each cohort has its own hosted VM; compare its paired modes, not absolute milliseconds across cohorts.

Payload tokens count stable compact JSON for the entire response, including repeated context/result text and metadata, excluding latency/cache-hit diagnostics. They are distinct from the hard context-token budget.

| Old cohort | Cap | Mode | Context tokens | Payload tokens | p50 ms | p95 ms | p99 ms | Query encodes |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| development-synthetic61 | 512 | lexical_native_token_budget | 476.8 | 2094.1 | 8.936 | 18.330 | 19.399 | 0 |
| development-synthetic61 | 512 | legacy_rrf_k60 | 490.1 | 2076.0 | 21.487 | 33.207 | 38.286 | 504 |
| development-synthetic61 | 512 | q1_score_075 | 487.6 | 2138.1 | 20.306 | 33.394 | 37.611 | 504 |
| development-synthetic61 | 512 | q2_lexical_anchor | 490.7 | 2110.7 | 21.516 | 34.163 | 39.164 | 504 |
| development-synthetic61 | 1024 | lexical_native_token_budget | 905.5 | 3443.2 | 8.095 | 20.520 | 21.838 | 0 |
| development-synthetic61 | 1024 | legacy_rrf_k60 | 936.6 | 3474.1 | 20.568 | 33.761 | 40.654 | 504 |
| development-synthetic61 | 1024 | q1_score_075 | 924.2 | 3584.8 | 20.088 | 34.041 | 39.582 | 504 |
| development-synthetic61 | 1024 | q2_lexical_anchor | 934.9 | 3465.2 | 20.816 | 34.696 | 40.109 | 504 |
| development-synthetic61 | 2048 | lexical_native_token_budget | 1260.1 | 4395.2 | 6.962 | 18.084 | 19.117 | 0 |
| development-synthetic61 | 2048 | legacy_rrf_k60 | 1381.6 | 4600.7 | 18.981 | 31.047 | 37.903 | 504 |
| development-synthetic61 | 2048 | q1_score_075 | 1276.9 | 4468.7 | 17.979 | 34.282 | 37.339 | 504 |
| development-synthetic61 | 2048 | q2_lexical_anchor | 1375.9 | 4609.0 | 19.127 | 32.075 | 37.210 | 504 |
| regression-authored36 | 512 | lexical_native_token_budget | 188.5 | 948.1 | 0.906 | 1.525 | 1.651 | 0 |
| regression-authored36 | 512 | legacy_rrf_k60 | 453.1 | 2199.8 | 5.705 | 8.052 | 8.395 | 108 |
| regression-authored36 | 512 | q1_score_075 | 453.1 | 2199.5 | 5.587 | 8.115 | 8.505 | 108 |
| regression-authored36 | 512 | q2_lexical_anchor | 453.1 | 2199.8 | 5.496 | 8.086 | 8.624 | 108 |
| regression-authored36 | 1024 | lexical_native_token_budget | 188.5 | 949.1 | 0.909 | 1.539 | 1.656 | 0 |
| regression-authored36 | 1024 | legacy_rrf_k60 | 485.5 | 2314.3 | 5.592 | 7.783 | 8.067 | 108 |
| regression-authored36 | 1024 | q1_score_075 | 485.5 | 2314.0 | 5.621 | 7.758 | 8.223 | 108 |
| regression-authored36 | 1024 | q2_lexical_anchor | 485.5 | 2314.3 | 5.598 | 7.792 | 8.107 | 108 |
| regression-authored36 | 2048 | lexical_native_token_budget | 188.5 | 949.1 | 0.890 | 1.524 | 1.655 | 0 |
| regression-authored36 | 2048 | legacy_rrf_k60 | 485.5 | 2314.3 | 5.477 | 7.581 | 8.160 | 108 |
| regression-authored36 | 2048 | q1_score_075 | 485.5 | 2314.0 | 5.500 | 7.721 | 8.189 | 108 |
| regression-authored36 | 2048 | q2_lexical_anchor | 485.5 | 2314.3 | 5.496 | 7.679 | 8.336 | 108 |
| regression-public1015 | 512 | lexical_native_token_budget | 491.9 | 2415.6 | 5.846 | 7.364 | 8.035 | 0 |
| regression-public1015 | 512 | legacy_rrf_k60 | 492.6 | 2465.3 | 13.478 | 17.083 | 19.406 | 3045 |
| regression-public1015 | 512 | q1_score_075 | 492.7 | 2456.3 | 13.617 | 17.123 | 19.876 | 3045 |
| regression-public1015 | 512 | q2_lexical_anchor | 492.5 | 2463.4 | 13.527 | 16.997 | 19.778 | 3045 |
| regression-public1015 | 1024 | lexical_native_token_budget | 861.1 | 4071.0 | 4.771 | 6.136 | 6.790 | 0 |
| regression-public1015 | 1024 | legacy_rrf_k60 | 864.7 | 4121.8 | 12.339 | 15.729 | 17.923 | 3045 |
| regression-public1015 | 1024 | q1_score_075 | 871.2 | 4132.8 | 12.481 | 15.804 | 18.054 | 3045 |
| regression-public1015 | 1024 | q2_lexical_anchor | 865.9 | 4125.3 | 12.414 | 15.782 | 19.682 | 3045 |
| regression-public1015 | 2048 | lexical_native_token_budget | 867.1 | 4093.7 | 4.783 | 6.082 | 6.568 | 0 |
| regression-public1015 | 2048 | legacy_rrf_k60 | 872.4 | 4151.2 | 12.331 | 15.686 | 18.079 | 3045 |
| regression-public1015 | 2048 | q1_score_075 | 877.6 | 4157.4 | 12.473 | 15.773 | 17.630 | 3045 |
| regression-public1015 | 2048 | q2_lexical_anchor | 873.0 | 4152.4 | 12.413 | 15.683 | 18.520 | 3045 |
| regression-hotpot128 | 512 | lexical_native_token_budget | 479.4 | 2417.9 | 5.519 | 8.182 | 8.893 | 0 |
| regression-hotpot128 | 512 | legacy_rrf_k60 | 480.9 | 2472.7 | 15.138 | 21.505 | 26.631 | 384 |
| regression-hotpot128 | 512 | q1_score_075 | 477.8 | 2458.8 | 15.141 | 21.624 | 25.727 | 384 |
| regression-hotpot128 | 512 | q2_lexical_anchor | 481.4 | 2476.3 | 15.062 | 21.454 | 25.864 | 384 |
| regression-hotpot128 | 1024 | lexical_native_token_budget | 804.0 | 3971.8 | 4.830 | 7.379 | 8.356 | 0 |
| regression-hotpot128 | 1024 | legacy_rrf_k60 | 814.2 | 4058.9 | 14.609 | 20.828 | 25.361 | 384 |
| regression-hotpot128 | 1024 | q1_score_075 | 814.5 | 4055.8 | 14.546 | 20.818 | 25.991 | 384 |
| regression-hotpot128 | 1024 | q2_lexical_anchor | 814.2 | 4058.6 | 14.549 | 21.047 | 25.840 | 384 |
| regression-hotpot128 | 2048 | lexical_native_token_budget | 805.8 | 3979.0 | 5.014 | 7.706 | 8.561 | 0 |
| regression-hotpot128 | 2048 | legacy_rrf_k60 | 815.2 | 4063.1 | 14.978 | 21.717 | 25.723 | 384 |
| regression-hotpot128 | 2048 | q1_score_075 | 815.2 | 4059.1 | 14.982 | 21.864 | 27.519 | 384 |
| regression-hotpot128 | 2048 | q2_lexical_anchor | 815.2 | 4062.9 | 15.014 | 21.674 | 26.744 | 384 |

## Shared preparation costs

Fresh indexing here is experimental preparation, not an upgrade requirement for existing compatible indexes. Ordinary lexical operation requires no model or embedding index.

| Old cohort | Ingest ms | Model load ms | Index build ms | Windows | Vector bytes |
|---|---:|---:|---:|---:|---:|
| development-synthetic61 | 1247.0 | 1127.3 | 188061.6 | 4093 | 6286848 |
| regression-authored36 | 31.3 | 862.0 | 454.9 | 42 | 64512 |
| regression-public1015 | 1316.3 | 1054.1 | 94516.1 | 2032 | 3121152 |
| regression-hotpot128 | 6650.3 | 1024.9 | 106797.5 | 2323 | 3568128 |

## Unsupported questions and validity

A nonempty context on an unsupported question is a retrieval diagnostic. This experiment does not generate answers, so this is not an answer error rate.

| Old cohort | Cap | Unsupported questions | Lexical nonempty | RRF nonempty | Q1 nonempty | Q2 nonempty |
|---|---:|---:|---:|---:|---:|---:|
| development-synthetic61 | 512 | 16 | 75.00% | 100.00% | 100.00% | 100.00% |
| development-synthetic61 | 1024 | 16 | 75.00% | 100.00% | 100.00% | 100.00% |
| development-synthetic61 | 2048 | 16 | 75.00% | 100.00% | 100.00% | 100.00% |
| regression-authored36 | 512 | 6 | 33.33% | 100.00% | 100.00% | 100.00% |
| regression-authored36 | 1024 | 6 | 33.33% | 100.00% | 100.00% | 100.00% |
| regression-authored36 | 2048 | 6 | 33.33% | 100.00% | 100.00% | 100.00% |
| regression-public1015 | 512 | 366 | 100.00% | 100.00% | 100.00% | 100.00% |
| regression-public1015 | 1024 | 366 | 100.00% | 100.00% | 100.00% | 100.00% |
| regression-public1015 | 2048 | 366 | 100.00% | 100.00% | 100.00% | 100.00% |
| regression-hotpot128 | 512 | 0 | — | — | — | — |
| regression-hotpot128 | 1024 | 0 | — | — | — | — |
| regression-hotpot128 | 2048 | 0 | — | — | — | — |

Accepted reports passed source/index-address stability, source-span projection, project scope, character/token caps, token/model metadata, result-cache isolation and repeat-context checks. These are measurement checks, not evidence of universal semantic memory.

## Repeated controls across experiments

This compares each current lexical/RRF/Q1 context and evidence outcome with the completed Q1 experiment. Differences are retained as diagnostics; timings are never pooled across runs or hosts. The JSON separately records verified model identity, recorded runtime environment and indexed page-text/ID fingerprint agreement. A hardware or numerical cause for any changes is not established by these records. The quality conclusions above use the four modes paired within the current run.

| Old cohort | Cap | Control | Changed contexts | Changed evidence ranks | Changed annotation presence | Complete gains | Complete losses |
|---|---:|---|---:|---:|---:|---:|---:|
| development-synthetic61 | 512 | lexical_native_token_budget | 0 | 0 | 0 | 0 | 0 |
| development-synthetic61 | 512 | legacy_rrf_k60 | 0 | 0 | 0 | 0 | 0 |
| development-synthetic61 | 512 | q1_score_075 | 0 | 0 | 0 | 0 | 0 |
| development-synthetic61 | 1024 | lexical_native_token_budget | 0 | 0 | 0 | 0 | 0 |
| development-synthetic61 | 1024 | legacy_rrf_k60 | 0 | 0 | 0 | 0 | 0 |
| development-synthetic61 | 1024 | q1_score_075 | 0 | 0 | 0 | 0 | 0 |
| development-synthetic61 | 2048 | lexical_native_token_budget | 0 | 0 | 0 | 0 | 0 |
| development-synthetic61 | 2048 | legacy_rrf_k60 | 0 | 0 | 0 | 0 | 0 |
| development-synthetic61 | 2048 | q1_score_075 | 0 | 0 | 0 | 0 | 0 |
| regression-authored36 | 512 | lexical_native_token_budget | 0 | 0 | 0 | 0 | 0 |
| regression-authored36 | 512 | legacy_rrf_k60 | 9 | 0 | 0 | 0 | 0 |
| regression-authored36 | 512 | q1_score_075 | 8 | 0 | 0 | 0 | 0 |
| regression-authored36 | 1024 | lexical_native_token_budget | 0 | 0 | 0 | 0 | 0 |
| regression-authored36 | 1024 | legacy_rrf_k60 | 9 | 0 | 0 | 0 | 0 |
| regression-authored36 | 1024 | q1_score_075 | 8 | 0 | 0 | 0 | 0 |
| regression-authored36 | 2048 | lexical_native_token_budget | 0 | 0 | 0 | 0 | 0 |
| regression-authored36 | 2048 | legacy_rrf_k60 | 9 | 0 | 0 | 0 | 0 |
| regression-authored36 | 2048 | q1_score_075 | 8 | 0 | 0 | 0 | 0 |
| regression-public1015 | 512 | lexical_native_token_budget | 0 | 0 | 0 | 0 | 0 |
| regression-public1015 | 512 | legacy_rrf_k60 | 0 | 0 | 0 | 0 | 0 |
| regression-public1015 | 512 | q1_score_075 | 0 | 0 | 0 | 0 | 0 |
| regression-public1015 | 1024 | lexical_native_token_budget | 0 | 0 | 0 | 0 | 0 |
| regression-public1015 | 1024 | legacy_rrf_k60 | 0 | 0 | 0 | 0 | 0 |
| regression-public1015 | 1024 | q1_score_075 | 0 | 0 | 0 | 0 | 0 |
| regression-public1015 | 2048 | lexical_native_token_budget | 0 | 0 | 0 | 0 | 0 |
| regression-public1015 | 2048 | legacy_rrf_k60 | 0 | 0 | 0 | 0 | 0 |
| regression-public1015 | 2048 | q1_score_075 | 0 | 0 | 0 | 0 | 0 |
| regression-hotpot128 | 512 | lexical_native_token_budget | 0 | 0 | 0 | 0 | 0 |
| regression-hotpot128 | 512 | legacy_rrf_k60 | 27 | 8 | 3 | 1 | 0 |
| regression-hotpot128 | 512 | q1_score_075 | 16 | 6 | 2 | 2 | 0 |
| regression-hotpot128 | 1024 | lexical_native_token_budget | 0 | 0 | 0 | 0 | 0 |
| regression-hotpot128 | 1024 | legacy_rrf_k60 | 57 | 17 | 7 | 2 | 3 |
| regression-hotpot128 | 1024 | q1_score_075 | 30 | 9 | 1 | 0 | 1 |
| regression-hotpot128 | 2048 | lexical_native_token_budget | 0 | 0 | 0 | 0 | 0 |
| regression-hotpot128 | 2048 | legacy_rrf_k60 | 57 | 17 | 7 | 2 | 3 |
| regression-hotpot128 | 2048 | q1_score_075 | 30 | 9 | 1 | 0 | 1 |

Public raw and summary reports remain linked below; private source datasets and model artifacts are not part of Git publication.

## Reports

- development-synthetic61: [full rows](../results/round2-anchor-development-synthetic61.json.gz) · [summary](../results/round2-anchor-development-synthetic61.summary.json)
- regression-authored36: [full rows](../results/round2-anchor-regression-authored36.json.gz) · [summary](../results/round2-anchor-regression-authored36.summary.json)
- regression-public1015: [full rows](../results/round2-anchor-regression-public1015.json.gz) · [summary](../results/round2-anchor-regression-public1015.summary.json)
- regression-hotpot128: [full rows](../results/round2-anchor-regression-hotpot128.json.gz) · [summary](../results/round2-anchor-regression-hotpot128.summary.json)
