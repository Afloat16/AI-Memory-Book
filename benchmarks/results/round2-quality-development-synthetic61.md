# Q1 score fusion: old development/regression comparison

Measurement validation: **PASS**.

All three modes share the model/index, archive and assembler. Lexical remains the product default.

| Mode | Token cap | Evidence recall | Complete evidence | Context tokens | Payload tokens | p50 ms | p95 ms | p99 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| lexical_native_token_budget | 512 | 86.36% | 85.53% | 476.8 | 2094.1 | 6.463 | 13.092 | 14.150 |
| legacy_rrf_k60 | 512 | 68.18% | 63.16% | 490.1 | 2076.0 | 14.300 | 25.801 | 29.581 |
| q1_score_075 | 512 | 83.52% | 80.92% | 487.6 | 2138.1 | 13.723 | 25.343 | 28.286 |
| lexical_native_token_budget | 1024 | 93.18% | 92.11% | 905.5 | 3443.2 | 5.852 | 15.189 | 15.903 |
| legacy_rrf_k60 | 1024 | 78.98% | 75.66% | 936.6 | 3474.1 | 13.921 | 24.619 | 29.359 |
| q1_score_075 | 1024 | 94.32% | 93.42% | 924.2 | 3584.8 | 13.449 | 25.492 | 29.577 |
| lexical_native_token_budget | 2048 | 93.18% | 92.11% | 1260.1 | 4395.2 | 5.009 | 12.903 | 13.569 |
| legacy_rrf_k60 | 2048 | 80.68% | 77.63% | 1381.6 | 4600.7 | 12.531 | 23.426 | 28.137 |
| q1_score_075 | 2048 | 94.32% | 93.42% | 1276.9 | 4468.7 | 12.015 | 23.197 | 27.386 |

## Paired gains and losses

| Comparison | Token cap | Annotation gains | Annotation losses | Complete gains | Complete losses |
|---|---:|---:|---:|---:|---:|
| q1_vs_lexical | 512 | 4 | 9 | 2 | 9 |
| q1_vs_legacy_rrf | 512 | 29 | 2 | 29 | 2 |
| q1_vs_lexical | 1024 | 2 | 0 | 2 | 0 |
| q1_vs_legacy_rrf | 1024 | 28 | 1 | 28 | 1 |
| q1_vs_lexical | 2048 | 2 | 0 | 2 | 0 |
| q1_vs_legacy_rrf | 2048 | 25 | 1 | 25 | 1 |

## Preparation and limits

Ingestion 842.9 ms; model load 897.3 ms; index build 95831.0 ms; 4093 windows, 6286848 vector bytes.

Query timings exclude setup, scoring, export and checkpoint I/O; both semantic modes include the same query-encoding counter. Caches are disabled. First pass follows explicit index/model preparation, not a disk-cold start. Mode order rotates per query and repetition; all three repetitions are retained.

The model/index fingerprint remains v1. Fusion cache version 2 does not require recomputing existing embeddings. Preparation is shared experimental setup, not charged separately to each mode or omitted from cost disclosure.

Reports retain low-overlap, multiple-evidence, cross-session/chapter, unsupported-query diagnostics and every question/annotation gain and loss. These old cohorts cannot establish new-domain generalization or generated-answer quality. A nonempty unsupported-query context is not automatically an incorrect generated answer.
