# Paired local semantic retrieval

Measurement validation: **PASS**.

The two modes share runtime, archive, budget assembly and source labels. Only the explicit semantic candidate route differs.

| Mode | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | p50 ms | p95 ms |
|---|---|---:|---:|---:|---:|---:|---:|
| lexical_native_token_budget | cl100k_base | 512 | 88.89% | 86.67% | 188.5 | 1.539 | 2.526 |
| semantic_native_token_budget | cl100k_base | 512 | 100.00% | 100.00% | 454.2 | 9.478 | 14.894 |
| lexical_native_token_budget | cl100k_base | 1024 | 88.89% | 86.67% | 188.5 | 1.504 | 2.521 |
| semantic_native_token_budget | cl100k_base | 1024 | 100.00% | 100.00% | 485.9 | 9.001 | 14.423 |
| lexical_native_token_budget | cl100k_base | 2048 | 88.89% | 86.67% | 188.5 | 1.511 | 2.517 |
| semantic_native_token_budget | cl100k_base | 2048 | 100.00% | 100.00% | 485.9 | 8.998 | 14.446 |

## Paired changes

| Token cap | Annotation gains | Annotation losses | Complete gains | Complete losses |
|---:|---:|---:|---:|---:|
| 512 | 4 | 0 | 4 | 0 |
| 1024 | 4 | 0 | 4 | 0 |
| 2048 | 4 | 0 | 4 | 0 |

## Costs and interpretation

Ingestion: 32.8 ms. Model load: 1231.2 ms. Index build: 1142.0 ms; 42 windows, 64512 vector bytes before SQLite overhead.

Query timings exclude model load, index construction, scoring and checkpoint I/O. Caches are disabled; first-pass timings follow explicit model loading/indexing, so they are not disk-cold latency. Resume segments are retained.

Low overlap and cross-chapter groups are evaluator diagnostics declared before scoring. Evidence metrics do not measure generated answers, semantic correctness, broad generalization or complete competitor workflows.
