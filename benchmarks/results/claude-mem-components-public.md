# claude-mem supplied-source SQLite FTS component

**Scope:** unchanged native SessionSearch over supplied original source pages. Observer, Chroma, native worker/MCP and generated answers are not measured.

Validation: **PASS**.

| Component | Tokenizer | Cap | Evidence recall | Complete evidence | Mean context tokens |
|---|---|---:|---:|---:|---:|
| claude-mem supplied-source native FTS | cl100k_base | 512 | 59.52% | 63.79% | 440.8 |
| claude-mem supplied-source native FTS | cl100k_base | 1024 | 66.24% | 70.11% | 804.8 |
| claude-mem supplied-source native FTS | cl100k_base | 2048 | 66.24% | 70.11% | 807.9 |
| claude-mem supplied-source native FTS | o200k_base | 512 | 59.64% | 63.79% | 444.1 |
| claude-mem supplied-source native FTS | o200k_base | 1024 | 66.24% | 70.11% | 786.2 |
| claude-mem supplied-source native FTS | o200k_base | 2048 | 66.24% | 70.11% | 787.4 |
| first-round-recall | cl100k_base | 512 | 62.31% | 66.72% | 449.2 |
| first-round-recall | cl100k_base | 1024 | 68.78% | 71.96% | 823.2 |
| first-round-recall | cl100k_base | 2048 | 68.78% | 71.96% | 827.2 |
| first-round-recall | o200k_base | 512 | 62.69% | 67.03% | 452.7 |
| first-round-recall | o200k_base | 1024 | 68.78% | 71.96% | 804.3 |
| first-round-recall | o200k_base | 2048 | 68.78% | 71.96% | 805.4 |
| score-aware-recall | cl100k_base | 512 | 62.44% | 66.26% | 447.6 |
| score-aware-recall | cl100k_base | 1024 | 69.54% | 72.88% | 827.2 |
| score-aware-recall | cl100k_base | 2048 | 69.54% | 72.88% | 832.1 |
| score-aware-recall | o200k_base | 512 | 62.94% | 66.72% | 451.5 |
| score-aware-recall | o200k_base | 1024 | 69.54% | 72.88% | 809.2 |
| score-aware-recall | o200k_base | 2048 | 69.54% | 72.88% | 810.0 |
| billion-context | cl100k_base | 512 | 58.88% | 62.71% | 442.8 |
| billion-context | cl100k_base | 1024 | 65.48% | 68.72% | 862.6 |
| billion-context | cl100k_base | 2048 | 65.48% | 68.72% | 871.0 |
| billion-context | o200k_base | 512 | 59.39% | 63.02% | 445.8 |
| billion-context | o200k_base | 1024 | 65.48% | 68.72% | 844.6 |
| billion-context | o200k_base | 2048 | 65.48% | 68.72% | 848.5 |
| ai-memory-hybrid | cl100k_base | 512 | 56.60% | 58.86% | 451.1 |
| ai-memory-hybrid | cl100k_base | 1024 | 64.47% | 66.72% | 779.3 |
| ai-memory-hybrid | cl100k_base | 2048 | 64.59% | 66.87% | 782.4 |
| ai-memory-hybrid | o200k_base | 512 | 56.98% | 59.17% | 451.8 |
| ai-memory-hybrid | o200k_base | 1024 | 64.47% | 66.72% | 760.4 |
| ai-memory-hybrid | o200k_base | 2048 | 64.59% | 66.87% | 762.4 |

## Observed component costs

| Boundary | p50 ms | p95 ms | Mean ms |
|---|---:|---:|---:|
| kernel_or_native_search_latency | 59.073 | 99.973 | 60.529 |
| adapter_roundtrip_latency | 59.664 | 100.450 | 61.112 |
| first_pass_roundtrip_latency | 59.389 | 100.487 | 60.996 |
| repeat_roundtrip_latency | 59.777 | 100.297 | 61.171 |

Startup, schema creation, supplied-page loading, DB sizes and RSS are recorded separately in the JSON summary. They are not complete-product ingestion costs.

Historical Book/Billion/ai-memory rows reuse the exact matched pages and packing policy; their transport boundaries and original host remain separately attributed. No full-product latency ranking or generated-answer conclusion follows from this table.

This is previously observed LoCoMo regression data. Quality counts complete original annotated evidence and source spans, not answer generation. All failed attempts remain in the ledger and invalidate successful measurement claims.
