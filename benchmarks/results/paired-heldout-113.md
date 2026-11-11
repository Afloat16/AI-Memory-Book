# Paired retrieval and token-cost measurements

These measurements evaluate source-evidence retrieval, not model answers or complete competitor products.

## Same character-budget retrieval

| Engine | Character cap | Evidence recall | Complete evidence | Mean cl100k tokens | Mean o200k tokens | Recall p50 ms | Recall p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| v0.2.1 | 2000 | 71.02% | 71.71% | 956.1 | 788.1 | 5.755 | 11.609 |
| v0.2.1 | 8000 | 77.27% | 78.95% | 1590.2 | 1304.9 | 4.716 | 7.749 |
| candidate | 2000 | 78.41% | 80.26% | 925.1 | 770.0 | 3.479 | 8.256 |
| candidate | 8000 | 81.82% | 84.21% | 1480.3 | 1219.2 | 3.123 | 6.290 |

## Identical whole-evidence-block token packing

One retrieval at the common maximum character cap supplies candidate blocks. The same rank-order first-fit packer retains whole blocks for every engine; source spans stay intact. Its cost is additional to the retrieval latency above.

| Engine | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | Packing p95 ms |
|---|---|---:|---:|---:|---:|---:|
| v0.2.1 | cl100k_base | 512 | 59.09% | 57.89% | 383.6 | 5.977 |
| v0.2.1 | cl100k_base | 1024 | 77.27% | 78.95% | 870.1 | 2.006 |
| v0.2.1 | cl100k_base | 2048 | 77.27% | 78.95% | 1257.3 | 2.741 |
| v0.2.1 | o200k_base | 512 | 61.36% | 60.53% | 352.0 | 1.797 |
| v0.2.1 | o200k_base | 1024 | 77.27% | 78.95% | 793.6 | 2.347 |
| v0.2.1 | o200k_base | 2048 | 77.27% | 78.95% | 1186.1 | 6.403 |
| candidate | cl100k_base | 512 | 68.18% | 68.42% | 370.8 | 1.143 |
| candidate | cl100k_base | 1024 | 81.82% | 84.21% | 865.0 | 1.853 |
| candidate | cl100k_base | 2048 | 81.82% | 84.21% | 1168.7 | 2.265 |
| candidate | o200k_base | 512 | 72.73% | 73.68% | 375.8 | 2.281 |
| candidate | o200k_base | 1024 | 81.82% | 84.21% | 836.4 | 2.367 |
| candidate | o200k_base | 2048 | 81.82% | 84.21% | 1106.5 | 3.817 |

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
