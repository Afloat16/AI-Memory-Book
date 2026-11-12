# Q1 score fusion: old development/regression comparison

Measurement validation: **PASS**.

All three modes share the model/index, archive and assembler. Lexical remains the product default.

| Mode | Token cap | Evidence recall | Complete evidence | Context tokens | Payload tokens | p50 ms | p95 ms | p99 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| lexical_native_token_budget | 512 | 88.89% | 86.67% | 188.5 | 948.1 | 1.578 | 2.710 | 3.071 |
| legacy_rrf_k60 | 512 | 100.00% | 100.00% | 454.2 | 2209.1 | 10.188 | 15.551 | 16.186 |
| q1_score_075 | 512 | 100.00% | 100.00% | 454.2 | 2208.9 | 10.166 | 15.657 | 16.983 |
| lexical_native_token_budget | 1024 | 88.89% | 86.67% | 188.5 | 949.1 | 1.580 | 2.847 | 2.936 |
| legacy_rrf_k60 | 1024 | 100.00% | 100.00% | 485.9 | 2315.9 | 9.944 | 15.679 | 16.161 |
| q1_score_075 | 1024 | 100.00% | 100.00% | 485.9 | 2315.8 | 9.933 | 15.687 | 16.403 |
| lexical_native_token_budget | 2048 | 88.89% | 86.67% | 188.5 | 949.1 | 1.554 | 2.630 | 2.774 |
| legacy_rrf_k60 | 2048 | 100.00% | 100.00% | 485.9 | 2315.9 | 9.472 | 14.900 | 15.694 |
| q1_score_075 | 2048 | 100.00% | 100.00% | 485.9 | 2315.8 | 9.458 | 15.052 | 15.477 |

## Paired gains and losses

| Comparison | Token cap | Annotation gains | Annotation losses | Complete gains | Complete losses |
|---|---:|---:|---:|---:|---:|
| q1_vs_lexical | 512 | 4 | 0 | 4 | 0 |
| q1_vs_legacy_rrf | 512 | 0 | 0 | 0 | 0 |
| q1_vs_lexical | 1024 | 4 | 0 | 4 | 0 |
| q1_vs_legacy_rrf | 1024 | 0 | 0 | 0 | 0 |
| q1_vs_lexical | 2048 | 4 | 0 | 4 | 0 |
| q1_vs_legacy_rrf | 2048 | 0 | 0 | 0 | 0 |

## Preparation and limits

Ingestion 34.9 ms; model load 1293.7 ms; index build 1161.7 ms; 42 windows, 64512 vector bytes.

Query timings exclude setup, scoring, export and checkpoint I/O; both semantic modes include the same query-encoding counter. Caches are disabled. First pass follows explicit index/model preparation, not a disk-cold start. Mode order rotates per query and repetition; all three repetitions are retained.

The model/index fingerprint remains v1. Fusion cache version 2 does not require recomputing existing embeddings. Preparation is shared experimental setup, not charged separately to each mode or omitted from cost disclosure.

Reports retain low-overlap, multiple-evidence, cross-session/chapter, unsupported-query diagnostics and every question/annotation gain and loss. These old cohorts cannot establish new-domain generalization or generated-answer quality. A nonempty unsupported-query context is not automatically an incorrect generated answer.
