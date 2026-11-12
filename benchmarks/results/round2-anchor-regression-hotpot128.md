# Q2 lexical anchor: old development/regression comparison

Measurement validation: **PASS**.

All four modes share the model/index, archive and assembler. Lexical remains the product default.

| Mode | Token cap | Evidence recall | Complete evidence | Context tokens | Payload tokens | p50 ms | p95 ms | p99 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| lexical_native_token_budget | 512 | 66.99% | 35.16% | 479.4 | 2417.9 | 5.519 | 8.182 | 8.893 |
| legacy_rrf_k60 | 512 | 63.07% | 33.59% | 480.9 | 2472.7 | 15.138 | 21.505 | 26.631 |
| q1_score_075 | 512 | 65.03% | 32.03% | 477.8 | 2458.8 | 15.141 | 21.624 | 25.727 |
| q2_lexical_anchor | 512 | 65.36% | 34.38% | 481.4 | 2476.3 | 15.062 | 21.454 | 25.864 |
| lexical_native_token_budget | 1024 | 74.51% | 48.44% | 804.0 | 3971.8 | 4.830 | 7.379 | 8.356 |
| legacy_rrf_k60 | 1024 | 73.20% | 50.00% | 814.2 | 4058.9 | 14.609 | 20.828 | 25.361 |
| q1_score_075 | 1024 | 73.86% | 46.88% | 814.5 | 4055.8 | 14.546 | 20.818 | 25.991 |
| q2_lexical_anchor | 1024 | 74.84% | 50.78% | 814.2 | 4058.6 | 14.549 | 21.047 | 25.840 |
| lexical_native_token_budget | 2048 | 74.51% | 48.44% | 805.8 | 3979.0 | 5.014 | 7.706 | 8.561 |
| legacy_rrf_k60 | 2048 | 73.20% | 50.00% | 815.2 | 4063.1 | 14.978 | 21.717 | 25.723 |
| q1_score_075 | 2048 | 73.86% | 46.88% | 815.2 | 4059.1 | 14.982 | 21.864 | 27.519 |
| q2_lexical_anchor | 2048 | 74.84% | 50.78% | 815.2 | 4062.9 | 15.014 | 21.674 | 26.744 |

## Paired gains and losses

| Comparison | Token cap | Annotation gains | Annotation losses | Complete gains | Complete losses |
|---|---:|---:|---:|---:|---:|
| q2_vs_lexical | 512 | 15 | 20 | 9 | 10 |
| q2_vs_legacy_rrf | 512 | 11 | 4 | 2 | 1 |
| q2_vs_q1 | 512 | 17 | 16 | 11 | 8 |
| q2_vs_lexical | 1024 | 18 | 17 | 13 | 10 |
| q2_vs_legacy_rrf | 1024 | 5 | 0 | 1 | 0 |
| q2_vs_q1 | 1024 | 13 | 10 | 9 | 4 |
| q2_vs_lexical | 2048 | 18 | 17 | 13 | 10 |
| q2_vs_legacy_rrf | 2048 | 5 | 0 | 1 | 0 |
| q2_vs_q1 | 2048 | 13 | 10 | 9 | 4 |

## Preparation and limits

Ingestion 6650.3 ms; model load 1024.9 ms; index build 106797.5 ms; 2323 windows, 3568128 vector bytes.

Query timings exclude setup, scoring, export and checkpoint I/O; all three semantic modes include the same query-encoding counter. Caches are disabled. First pass follows explicit index/model preparation, not a disk-cold start. Mode order rotates per query and repetition; all three repetitions are retained.

The model/index fingerprint remains v1. Fusion cache version 3 does not require recomputing existing embeddings. Preparation is shared experimental setup, not charged separately to each mode or omitted from cost disclosure.

Reports retain low-overlap, multiple-evidence, cross-session/chapter, unsupported-query diagnostics and every question/annotation gain and loss. These old cohorts cannot establish new-domain generalization or generated-answer quality. A nonempty unsupported-query context is not automatically an incorrect generated answer.
