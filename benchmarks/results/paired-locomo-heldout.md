# Paired retrieval and token-cost measurements

These measurements evaluate source-evidence retrieval, not model answers or complete competitor products.

## Same character-budget retrieval

| Engine | Character cap | Evidence recall | Complete evidence | Mean cl100k tokens | Mean o200k tokens | Recall p50 ms | Recall p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| v0.2.1 | 2000 | 26.18% | 27.27% | 611.8 | 599.5 | 4.623 | 7.285 |
| v0.2.1 | 8000 | 73.30% | 75.57% | 939.9 | 915.2 | 3.594 | 7.849 |
| candidate | 2000 | 45.03% | 46.59% | 604.8 | 592.4 | 2.777 | 4.280 |
| candidate | 8000 | 72.77% | 75.00% | 854.6 | 832.8 | 2.770 | 4.438 |

## Identical whole-evidence-block token packing

One retrieval at the common maximum character cap supplies candidate blocks. The same rank-order first-fit packer retains whole blocks for every engine; source spans stay intact. Its cost is additional to the retrieval latency above.

| Engine | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | Packing p95 ms |
|---|---|---:|---:|---:|---:|---:|
| v0.2.1 | cl100k_base | 512 | 67.02% | 69.32% | 429.8 | 1.457 |
| v0.2.1 | cl100k_base | 1024 | 72.77% | 75.00% | 900.3 | 1.535 |
| v0.2.1 | cl100k_base | 2048 | 73.30% | 75.57% | 939.9 | 1.327 |
| v0.2.1 | o200k_base | 512 | 67.02% | 69.32% | 430.5 | 1.594 |
| v0.2.1 | o200k_base | 1024 | 73.30% | 75.57% | 889.0 | 7.556 |
| v0.2.1 | o200k_base | 2048 | 73.30% | 75.57% | 915.2 | 2.361 |
| candidate | cl100k_base | 512 | 67.54% | 69.32% | 444.0 | 1.038 |
| candidate | cl100k_base | 1024 | 72.77% | 75.00% | 844.1 | 1.315 |
| candidate | cl100k_base | 2048 | 72.77% | 75.00% | 854.6 | 1.324 |
| candidate | o200k_base | 512 | 68.59% | 70.45% | 443.7 | 1.825 |
| candidate | o200k_base | 1024 | 72.77% | 75.00% | 827.2 | 2.876 |
| candidate | o200k_base | 2048 | 72.77% | 75.00% | 832.8 | 2.784 |

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
