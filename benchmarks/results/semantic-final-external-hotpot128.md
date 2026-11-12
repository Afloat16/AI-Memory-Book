# Paired local semantic retrieval

Measurement validation: **PASS**.

The two modes share runtime, archive, budget assembly and source labels. Only the explicit semantic candidate route differs.

| Mode | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | p50 ms | p95 ms |
|---|---|---:|---:|---:|---:|---:|---:|
| lexical_native_token_budget | cl100k_base | 512 | 66.99% | 35.16% | 479.4 | 5.593 | 8.170 |
| semantic_native_token_budget | cl100k_base | 512 | 63.07% | 33.59% | 480.9 | 15.480 | 21.847 |
| lexical_native_token_budget | cl100k_base | 1024 | 74.51% | 48.44% | 804.0 | 5.005 | 7.789 |
| semantic_native_token_budget | cl100k_base | 1024 | 73.20% | 50.00% | 814.2 | 15.205 | 21.796 |
| lexical_native_token_budget | cl100k_base | 2048 | 74.51% | 48.44% | 805.8 | 5.159 | 7.677 |
| semantic_native_token_budget | cl100k_base | 2048 | 73.20% | 50.00% | 815.2 | 15.297 | 21.730 |

## Paired changes

| Token cap | Annotation gains | Annotation losses | Complete gains | Complete losses |
|---:|---:|---:|---:|---:|
| 512 | 17 | 29 | 7 | 9 |
| 1024 | 18 | 22 | 13 | 11 |
| 2048 | 18 | 22 | 13 | 11 |

## Costs and interpretation

Ingestion: 3296.4 ms. Model load: 1055.7 ms. Index build: 106900.5 ms; 2323 windows, 3568128 vector bytes before SQLite overhead.

Query timings exclude model load, index construction, scoring and checkpoint I/O. Caches are disabled; first-pass timings follow explicit model loading/indexing, so they are not disk-cold latency. Resume segments are retained.

Low overlap and cross-chapter groups are evaluator diagnostics declared before scoring. Evidence metrics do not measure generated answers, semantic correctness, broad generalization or complete competitor workflows.
