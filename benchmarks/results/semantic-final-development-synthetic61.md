# Paired local semantic retrieval

Measurement validation: **PASS**.

The two modes share runtime, archive, budget assembly and source labels. Only the explicit semantic candidate route differs.

| Mode | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | p50 ms | p95 ms |
|---|---|---:|---:|---:|---:|---:|---:|
| lexical_native_token_budget | cl100k_base | 512 | 86.36% | 85.53% | 476.8 | 8.033 | 17.511 |
| semantic_native_token_budget | cl100k_base | 512 | 68.18% | 63.16% | 490.1 | 18.894 | 30.055 |
| lexical_native_token_budget | cl100k_base | 1024 | 93.18% | 92.11% | 905.5 | 6.360 | 17.633 |
| semantic_native_token_budget | cl100k_base | 1024 | 78.98% | 75.66% | 936.6 | 16.006 | 29.169 |
| lexical_native_token_budget | cl100k_base | 2048 | 93.18% | 92.11% | 1260.1 | 5.813 | 15.048 |
| semantic_native_token_budget | cl100k_base | 2048 | 80.68% | 77.63% | 1381.6 | 15.815 | 27.725 |

## Paired changes

| Token cap | Annotation gains | Annotation losses | Complete gains | Complete losses |
|---:|---:|---:|---:|---:|
| 512 | 4 | 36 | 2 | 36 |
| 1024 | 2 | 27 | 2 | 27 |
| 2048 | 2 | 24 | 2 | 24 |

## Costs and interpretation

Ingestion: 946.8 ms. Model load: 966.4 ms. Index build: 101580.0 ms; 4093 windows, 6286848 vector bytes before SQLite overhead.

Query timings exclude model load, index construction, scoring and checkpoint I/O. Caches are disabled; first-pass timings follow explicit model loading/indexing, so they are not disk-cold latency. Resume segments are retained.

Low overlap and cross-chapter groups are evaluator diagnostics declared before scoring. Evidence metrics do not measure generated answers, semantic correctness, broad generalization or complete competitor workflows.
