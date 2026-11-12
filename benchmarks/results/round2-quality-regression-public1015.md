# Q1 score fusion: old development/regression comparison

Measurement validation: **PASS**.

All three modes share the model/index, archive and assembler. Lexical remains the product default.

| Mode | Token cap | Evidence recall | Complete evidence | Context tokens | Payload tokens | p50 ms | p95 ms | p99 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| lexical_native_token_budget | 512 | 62.18% | 66.41% | 491.9 | 2415.6 | 4.366 | 5.699 | 6.627 |
| legacy_rrf_k60 | 512 | 59.77% | 62.40% | 492.6 | 2465.3 | 9.382 | 12.204 | 15.179 |
| q1_score_075 | 512 | 66.12% | 69.65% | 492.7 | 2456.3 | 9.488 | 12.199 | 14.034 |
| lexical_native_token_budget | 1024 | 69.54% | 72.88% | 861.1 | 4071.0 | 3.911 | 5.357 | 6.448 |
| legacy_rrf_k60 | 1024 | 68.27% | 70.88% | 864.7 | 4121.8 | 9.981 | 12.548 | 14.522 |
| q1_score_075 | 1024 | 73.48% | 76.43% | 871.2 | 4132.8 | 10.065 | 12.689 | 15.247 |
| lexical_native_token_budget | 2048 | 69.54% | 72.88% | 867.1 | 4093.7 | 3.903 | 5.318 | 5.929 |
| legacy_rrf_k60 | 2048 | 68.40% | 70.88% | 872.4 | 4151.2 | 9.944 | 12.663 | 14.741 |
| q1_score_075 | 2048 | 73.48% | 76.43% | 877.6 | 4157.4 | 10.056 | 12.759 | 15.521 |

## Paired gains and losses

| Comparison | Token cap | Annotation gains | Annotation losses | Complete gains | Complete losses |
|---|---:|---:|---:|---:|---:|
| q1_vs_lexical | 512 | 47 | 16 | 32 | 11 |
| q1_vs_legacy_rrf | 512 | 73 | 23 | 62 | 15 |
| q1_vs_lexical | 1024 | 38 | 7 | 27 | 4 |
| q1_vs_legacy_rrf | 1024 | 57 | 16 | 46 | 10 |
| q1_vs_lexical | 2048 | 38 | 7 | 27 | 4 |
| q1_vs_legacy_rrf | 2048 | 57 | 17 | 46 | 10 |

## Preparation and limits

Ingestion 1308.4 ms; model load 837.8 ms; index build 45990.7 ms; 2032 windows, 3121152 vector bytes.

Query timings exclude setup, scoring, export and checkpoint I/O; both semantic modes include the same query-encoding counter. Caches are disabled. First pass follows explicit index/model preparation, not a disk-cold start. Mode order rotates per query and repetition; all three repetitions are retained.

The model/index fingerprint remains v1. Fusion cache version 2 does not require recomputing existing embeddings. Preparation is shared experimental setup, not charged separately to each mode or omitted from cost disclosure.

Reports retain low-overlap, multiple-evidence, cross-session/chapter, unsupported-query diagnostics and every question/annotation gain and loss. These old cohorts cannot establish new-domain generalization or generated-answer quality. A nonempty unsupported-query context is not automatically an incorrect generated answer.
