# Q1 score fusion: old development/regression comparison

Measurement validation: **PASS**.

All three modes share the model/index, archive and assembler. Lexical remains the product default.

| Mode | Token cap | Evidence recall | Complete evidence | Context tokens | Payload tokens | p50 ms | p95 ms | p99 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| lexical_native_token_budget | 512 | 66.99% | 35.16% | 479.4 | 2417.9 | 6.899 | 10.032 | 10.845 |
| legacy_rrf_k60 | 512 | 62.42% | 32.81% | 480.6 | 2465.4 | 17.992 | 25.568 | 31.775 |
| q1_score_075 | 512 | 64.38% | 30.47% | 476.7 | 2454.5 | 18.049 | 25.947 | 30.792 |
| lexical_native_token_budget | 1024 | 74.51% | 48.44% | 804.0 | 3971.8 | 6.052 | 9.026 | 9.713 |
| legacy_rrf_k60 | 1024 | 74.18% | 50.78% | 814.9 | 4064.9 | 17.103 | 24.969 | 30.416 |
| q1_score_075 | 1024 | 74.18% | 47.66% | 813.2 | 4048.8 | 17.249 | 25.244 | 30.257 |
| lexical_native_token_budget | 2048 | 74.51% | 48.44% | 805.8 | 3979.0 | 6.153 | 9.036 | 9.550 |
| legacy_rrf_k60 | 2048 | 74.18% | 50.78% | 816.2 | 4069.6 | 17.168 | 25.388 | 30.459 |
| q1_score_075 | 2048 | 74.18% | 47.66% | 814.4 | 4055.5 | 17.477 | 25.289 | 30.089 |

## Paired gains and losses

| Comparison | Token cap | Annotation gains | Annotation losses | Complete gains | Complete losses |
|---|---:|---:|---:|---:|---:|
| q1_vs_lexical | 512 | 4 | 12 | 2 | 8 |
| q1_vs_legacy_rrf | 512 | 24 | 18 | 7 | 10 |
| q1_vs_lexical | 1024 | 9 | 10 | 7 | 8 |
| q1_vs_legacy_rrf | 1024 | 14 | 14 | 4 | 8 |
| q1_vs_lexical | 2048 | 9 | 10 | 7 | 8 |
| q1_vs_legacy_rrf | 2048 | 14 | 14 | 4 | 8 |

## Preparation and limits

Ingestion 2310.9 ms; model load 1239.7 ms; index build 131998.8 ms; 2323 windows, 3568128 vector bytes.

Query timings exclude setup, scoring, export and checkpoint I/O; both semantic modes include the same query-encoding counter. Caches are disabled. First pass follows explicit index/model preparation, not a disk-cold start. Mode order rotates per query and repetition; all three repetitions are retained.

The model/index fingerprint remains v1. Fusion cache version 2 does not require recomputing existing embeddings. Preparation is shared experimental setup, not charged separately to each mode or omitted from cost disclosure.

Reports retain low-overlap, multiple-evidence, cross-session/chapter, unsupported-query diagnostics and every question/annotation gain and loss. These old cohorts cannot establish new-domain generalization or generated-answer quality. A nonempty unsupported-query context is not automatically an incorrect generated answer.
