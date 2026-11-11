# Paired retrieval and token-cost measurements

These measurements evaluate source-evidence retrieval, not model answers or complete competitor products.

## Same character-budget retrieval

| Engine | Character cap | Evidence recall | Complete evidence | Mean cl100k tokens | Mean o200k tokens | Recall p50 ms | Recall p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| v0.2.1 | 2000 | 72.16% | 73.03% | 958.7 | 789.2 | 5.906 | 10.505 |
| v0.2.1 | 8000 | 77.27% | 78.95% | 1596.6 | 1308.5 | 4.705 | 9.050 |
| candidate | 2000 | 77.84% | 79.61% | 927.7 | 771.4 | 3.844 | 8.982 |
| candidate | 8000 | 81.82% | 84.21% | 1486.7 | 1222.8 | 3.177 | 6.485 |

## Identical whole-evidence-block token packing

One retrieval at the common maximum character cap supplies candidate blocks. The same rank-order first-fit packer retains whole blocks for every engine; source spans stay intact. Its cost is additional to the retrieval latency above.

| Engine | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | Packing p95 ms |
|---|---|---:|---:|---:|---:|---:|
| v0.2.1 | cl100k_base | 512 | 59.09% | 57.89% | 382.7 | 1.231 |
| v0.2.1 | cl100k_base | 1024 | 77.27% | 78.95% | 871.8 | 5.558 |
| v0.2.1 | cl100k_base | 2048 | 77.27% | 78.95% | 1258.0 | 2.151 |
| v0.2.1 | o200k_base | 512 | 61.36% | 60.53% | 354.2 | 2.148 |
| v0.2.1 | o200k_base | 1024 | 77.27% | 78.95% | 793.5 | 3.200 |
| v0.2.1 | o200k_base | 2048 | 77.27% | 78.95% | 1185.9 | 3.568 |
| candidate | cl100k_base | 512 | 68.18% | 68.42% | 371.3 | 3.226 |
| candidate | cl100k_base | 1024 | 81.82% | 84.21% | 852.2 | 2.753 |
| candidate | cl100k_base | 2048 | 81.82% | 84.21% | 1169.5 | 2.267 |
| candidate | o200k_base | 512 | 72.73% | 73.68% | 376.1 | 2.308 |
| candidate | o200k_base | 1024 | 81.82% | 84.21% | 830.4 | 2.948 |
| candidate | o200k_base | 2048 | 81.82% | 84.21% | 1106.5 | 5.682 |

## Measurement boundaries

- Both versions run in independent Python processes with identical records, query order, scope, result limit, page settings, and budgets.
- Context tokens are actual tiktoken 0.12.0 counts for cl100k_base and o200k_base; they are reference encodings, not every provider's tokenizer or billed API usage.
- Recall latency excludes token counting, ingestion, MCP, networking and model inference. Result caching is disabled; SQLite and OS caches are not flushed.
- Fresh-process CLI measurements include Python startup, imports, database open, recall and JSON serialization, with warm disk caches; they are not cold-disk latency.
- The common token packer sees no evidence labels, retains whole returned blocks, and never invokes retrieval again. Packing latency is reported separately.
- Evidence requires original source identity and span plus the complete annotated text in the actual returned context. Unanswerable nonempty retrieval is not a hallucination rate.
- Synthetic heldout seeds were reserved after development selection; shared templates still limit generalization. Public LoCoMo data remains separately downloaded under CC BY-NC 4.0; reports contain IDs and metrics, not dataset text.
- This paired version comparison does not execute external competitor products. See the separate component comparison for any measured upstream kernels.
- Structural source preflight verified every required/stale annotation fits one complete canonical page and matching original source span in both versions. Zero labels are affected by the evaluator's lack of cross-page annotation union; no labels were dropped.

See the complete compressed JSON for category results, failures, source references, fingerprints, ingest cost, and fresh-process CLI measurements.
