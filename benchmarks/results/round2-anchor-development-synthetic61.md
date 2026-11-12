# Q2 lexical anchor: old development/regression comparison

Measurement validation: **PASS**.

All four modes share the model/index, archive and assembler. Lexical remains the product default.

| Mode | Token cap | Evidence recall | Complete evidence | Context tokens | Payload tokens | p50 ms | p95 ms | p99 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| lexical_native_token_budget | 512 | 86.36% | 85.53% | 476.8 | 2094.1 | 8.936 | 18.330 | 19.399 |
| legacy_rrf_k60 | 512 | 68.18% | 63.16% | 490.1 | 2076.0 | 21.487 | 33.207 | 38.286 |
| q1_score_075 | 512 | 83.52% | 80.92% | 487.6 | 2138.1 | 20.306 | 33.394 | 37.611 |
| q2_lexical_anchor | 512 | 84.09% | 81.58% | 490.7 | 2110.7 | 21.516 | 34.163 | 39.164 |
| lexical_native_token_budget | 1024 | 93.18% | 92.11% | 905.5 | 3443.2 | 8.095 | 20.520 | 21.838 |
| legacy_rrf_k60 | 1024 | 78.98% | 75.66% | 936.6 | 3474.1 | 20.568 | 33.761 | 40.654 |
| q1_score_075 | 1024 | 94.32% | 93.42% | 924.2 | 3584.8 | 20.088 | 34.041 | 39.582 |
| q2_lexical_anchor | 1024 | 93.18% | 92.11% | 934.9 | 3465.2 | 20.816 | 34.696 | 40.109 |
| lexical_native_token_budget | 2048 | 93.18% | 92.11% | 1260.1 | 4395.2 | 6.962 | 18.084 | 19.117 |
| legacy_rrf_k60 | 2048 | 80.68% | 77.63% | 1381.6 | 4600.7 | 18.981 | 31.047 | 37.903 |
| q1_score_075 | 2048 | 94.32% | 93.42% | 1276.9 | 4468.7 | 17.979 | 34.282 | 37.339 |
| q2_lexical_anchor | 2048 | 93.18% | 92.11% | 1375.9 | 4609.0 | 19.127 | 32.075 | 37.210 |

## Paired gains and losses

| Comparison | Token cap | Annotation gains | Annotation losses | Complete gains | Complete losses |
|---|---:|---:|---:|---:|---:|
| q2_vs_lexical | 512 | 3 | 7 | 1 | 7 |
| q2_vs_legacy_rrf | 512 | 29 | 1 | 29 | 1 |
| q2_vs_q1 | 512 | 5 | 4 | 5 | 4 |
| q2_vs_lexical | 1024 | 2 | 2 | 2 | 2 |
| q2_vs_legacy_rrf | 1024 | 25 | 0 | 25 | 0 |
| q2_vs_q1 | 1024 | 1 | 3 | 1 | 3 |
| q2_vs_lexical | 2048 | 2 | 2 | 2 | 2 |
| q2_vs_legacy_rrf | 2048 | 22 | 0 | 22 | 0 |
| q2_vs_q1 | 2048 | 1 | 3 | 1 | 3 |

## Preparation and limits

Ingestion 1247.0 ms; model load 1127.3 ms; index build 188061.6 ms; 4093 windows, 6286848 vector bytes.

Query timings exclude setup, scoring, export and checkpoint I/O; all three semantic modes include the same query-encoding counter. Caches are disabled. First pass follows explicit index/model preparation, not a disk-cold start. Mode order rotates per query and repetition; all three repetitions are retained.

The model/index fingerprint remains v1. Fusion cache version 3 does not require recomputing existing embeddings. Preparation is shared experimental setup, not charged separately to each mode or omitted from cost disclosure.

Reports retain low-overlap, multiple-evidence, cross-session/chapter, unsupported-query diagnostics and every question/annotation gain and loss. These old cohorts cannot establish new-domain generalization or generated-answer quality. A nonempty unsupported-query context is not automatically an incorrect generated answer.
