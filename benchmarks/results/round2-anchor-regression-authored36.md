# Q2 lexical anchor: old development/regression comparison

Measurement validation: **PASS**.

All four modes share the model/index, archive and assembler. Lexical remains the product default.

| Mode | Token cap | Evidence recall | Complete evidence | Context tokens | Payload tokens | p50 ms | p95 ms | p99 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| lexical_native_token_budget | 512 | 88.89% | 86.67% | 188.5 | 948.1 | 0.906 | 1.525 | 1.651 |
| legacy_rrf_k60 | 512 | 100.00% | 100.00% | 453.1 | 2199.8 | 5.705 | 8.052 | 8.395 |
| q1_score_075 | 512 | 100.00% | 100.00% | 453.1 | 2199.5 | 5.587 | 8.115 | 8.505 |
| q2_lexical_anchor | 512 | 100.00% | 100.00% | 453.1 | 2199.8 | 5.496 | 8.086 | 8.624 |
| lexical_native_token_budget | 1024 | 88.89% | 86.67% | 188.5 | 949.1 | 0.909 | 1.539 | 1.656 |
| legacy_rrf_k60 | 1024 | 100.00% | 100.00% | 485.5 | 2314.3 | 5.592 | 7.783 | 8.067 |
| q1_score_075 | 1024 | 100.00% | 100.00% | 485.5 | 2314.0 | 5.621 | 7.758 | 8.223 |
| q2_lexical_anchor | 1024 | 100.00% | 100.00% | 485.5 | 2314.3 | 5.598 | 7.792 | 8.107 |
| lexical_native_token_budget | 2048 | 88.89% | 86.67% | 188.5 | 949.1 | 0.890 | 1.524 | 1.655 |
| legacy_rrf_k60 | 2048 | 100.00% | 100.00% | 485.5 | 2314.3 | 5.477 | 7.581 | 8.160 |
| q1_score_075 | 2048 | 100.00% | 100.00% | 485.5 | 2314.0 | 5.500 | 7.721 | 8.189 |
| q2_lexical_anchor | 2048 | 100.00% | 100.00% | 485.5 | 2314.3 | 5.496 | 7.679 | 8.336 |

## Paired gains and losses

| Comparison | Token cap | Annotation gains | Annotation losses | Complete gains | Complete losses |
|---|---:|---:|---:|---:|---:|
| q2_vs_lexical | 512 | 4 | 0 | 4 | 0 |
| q2_vs_legacy_rrf | 512 | 0 | 0 | 0 | 0 |
| q2_vs_q1 | 512 | 0 | 0 | 0 | 0 |
| q2_vs_lexical | 1024 | 4 | 0 | 4 | 0 |
| q2_vs_legacy_rrf | 1024 | 0 | 0 | 0 | 0 |
| q2_vs_q1 | 1024 | 0 | 0 | 0 | 0 |
| q2_vs_lexical | 2048 | 4 | 0 | 4 | 0 |
| q2_vs_legacy_rrf | 2048 | 0 | 0 | 0 | 0 |
| q2_vs_q1 | 2048 | 0 | 0 | 0 | 0 |

## Preparation and limits

Ingestion 31.3 ms; model load 862.0 ms; index build 454.9 ms; 42 windows, 64512 vector bytes.

Query timings exclude setup, scoring, export and checkpoint I/O; all three semantic modes include the same query-encoding counter. Caches are disabled. First pass follows explicit index/model preparation, not a disk-cold start. Mode order rotates per query and repetition; all three repetitions are retained.

The model/index fingerprint remains v1. Fusion cache version 3 does not require recomputing existing embeddings. Preparation is shared experimental setup, not charged separately to each mode or omitted from cost disclosure.

Reports retain low-overlap, multiple-evidence, cross-session/chapter, unsupported-query diagnostics and every question/annotation gain and loss. These old cohorts cannot establish new-domain generalization or generated-answer quality. A nonempty unsupported-query context is not automatically an incorrect generated answer.
