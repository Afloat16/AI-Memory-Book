# Paired local semantic retrieval

Measurement validation: **PASS**.

The two modes share runtime, archive, budget assembly and source labels. Only the explicit semantic candidate route differs.

| Mode | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | p50 ms | p95 ms |
|---|---|---:|---:|---:|---:|---:|---:|
| lexical_native_token_budget | cl100k_base | 512 | 62.18% | 66.41% | 491.9 | 8.078 | 10.184 |
| semantic_native_token_budget | cl100k_base | 512 | 60.03% | 62.56% | 492.4 | 18.074 | 22.691 |
| lexical_native_token_budget | cl100k_base | 1024 | 69.54% | 72.88% | 861.1 | 6.340 | 8.334 |
| semantic_native_token_budget | cl100k_base | 1024 | 68.78% | 71.49% | 863.8 | 16.363 | 21.061 |
| lexical_native_token_budget | cl100k_base | 2048 | 69.54% | 72.88% | 867.1 | 6.254 | 8.127 |
| semantic_native_token_budget | cl100k_base | 2048 | 68.91% | 71.49% | 871.9 | 15.943 | 20.353 |

## Paired changes

| Token cap | Annotation gains | Annotation losses | Complete gains | Complete losses |
|---:|---:|---:|---:|---:|
| 512 | 58 | 75 | 39 | 64 |
| 1024 | 52 | 58 | 37 | 46 |
| 2048 | 52 | 57 | 37 | 46 |

## Costs and interpretation

Ingestion: 1509.0 ms. Model load: 1270.8 ms. Index build: 116553.6 ms; 2032 windows, 3121152 vector bytes before SQLite overhead.

Query timings exclude model load, index construction, scoring and checkpoint I/O. Caches are disabled; first-pass timings follow explicit model loading/indexing, so they are not disk-cold latency. Resume segments are retained.

Low overlap and cross-chapter groups are evaluator diagnostics declared before scoring. Evidence metrics do not measure generated answers, semantic correctness, broad generalization or complete competitor workflows.
