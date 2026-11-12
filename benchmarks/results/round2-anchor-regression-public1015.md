# Q2 lexical anchor: old development/regression comparison

Measurement validation: **PASS**.

All four modes share the model/index, archive and assembler. Lexical remains the product default.

| Mode | Token cap | Evidence recall | Complete evidence | Context tokens | Payload tokens | p50 ms | p95 ms | p99 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| lexical_native_token_budget | 512 | 62.18% | 66.41% | 491.9 | 2415.6 | 5.846 | 7.364 | 8.035 |
| legacy_rrf_k60 | 512 | 59.77% | 62.40% | 492.6 | 2465.3 | 13.478 | 17.083 | 19.406 |
| q1_score_075 | 512 | 66.12% | 69.65% | 492.7 | 2456.3 | 13.617 | 17.123 | 19.876 |
| q2_lexical_anchor | 512 | 64.47% | 68.10% | 492.5 | 2463.4 | 13.527 | 16.997 | 19.778 |
| lexical_native_token_budget | 1024 | 69.54% | 72.88% | 861.1 | 4071.0 | 4.771 | 6.136 | 6.790 |
| legacy_rrf_k60 | 1024 | 68.27% | 70.88% | 864.7 | 4121.8 | 12.339 | 15.729 | 17.923 |
| q1_score_075 | 1024 | 73.48% | 76.43% | 871.2 | 4132.8 | 12.481 | 15.804 | 18.054 |
| q2_lexical_anchor | 1024 | 71.70% | 74.27% | 865.9 | 4125.3 | 12.414 | 15.782 | 19.682 |
| lexical_native_token_budget | 2048 | 69.54% | 72.88% | 867.1 | 4093.7 | 4.783 | 6.082 | 6.568 |
| legacy_rrf_k60 | 2048 | 68.40% | 70.88% | 872.4 | 4151.2 | 12.331 | 15.686 | 18.079 |
| q1_score_075 | 2048 | 73.48% | 76.43% | 877.6 | 4157.4 | 12.473 | 15.773 | 17.630 |
| q2_lexical_anchor | 2048 | 71.83% | 74.27% | 873.0 | 4152.4 | 12.413 | 15.683 | 18.520 |

## Paired gains and losses

| Comparison | Token cap | Annotation gains | Annotation losses | Complete gains | Complete losses |
|---|---:|---:|---:|---:|---:|
| q2_vs_lexical | 512 | 46 | 28 | 30 | 19 |
| q2_vs_legacy_rrf | 512 | 51 | 14 | 46 | 9 |
| q2_vs_q1 | 512 | 17 | 30 | 10 | 20 |
| q2_vs_lexical | 1024 | 47 | 30 | 33 | 24 |
| q2_vs_legacy_rrf | 1024 | 30 | 3 | 25 | 3 |
| q2_vs_q1 | 1024 | 14 | 28 | 8 | 22 |
| q2_vs_lexical | 2048 | 47 | 29 | 33 | 24 |
| q2_vs_legacy_rrf | 2048 | 30 | 3 | 25 | 3 |
| q2_vs_q1 | 2048 | 15 | 28 | 8 | 22 |

## Preparation and limits

Ingestion 1316.3 ms; model load 1054.1 ms; index build 94516.1 ms; 2032 windows, 3121152 vector bytes.

Query timings exclude setup, scoring, export and checkpoint I/O; all three semantic modes include the same query-encoding counter. Caches are disabled. First pass follows explicit index/model preparation, not a disk-cold start. Mode order rotates per query and repetition; all three repetitions are retained.

The model/index fingerprint remains v1. Fusion cache version 3 does not require recomputing existing embeddings. Preparation is shared experimental setup, not charged separately to each mode or omitted from cost disclosure.

Reports retain low-overlap, multiple-evidence, cross-session/chapter, unsupported-query diagnostics and every question/annotation gain and loss. These old cohorts cannot establish new-domain generalization or generated-answer quality. A nonempty unsupported-query context is not automatically an incorrect generated answer.
