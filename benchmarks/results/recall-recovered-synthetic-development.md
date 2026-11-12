# Paired retrieval and token-cost measurements

These measurements evaluate source-evidence retrieval, not model answers or complete competitor products.

## Measurement validation

Passed recorded source-stability and context/token-budget checks. This is not a quality threshold.

## Same character-budget retrieval

| Engine | Character cap | Evidence recall | Complete evidence | Mean cl100k tokens | Mean o200k tokens | Recall p50 ms | Recall p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| v0.3.0-3ee4094 | 2000 | 90.34% | 90.13% | 951.5 | 780.9 | 3.993 | 8.813 |
| v0.3.0-3ee4094 | 8000 | 93.18% | 92.11% | 1519.6 | 1235.3 | 3.706 | 6.908 |
| recovered-7ffb5ee | 2000 | 91.48% | 90.13% | 952.6 | 782.2 | 4.338 | 11.410 |
| recovered-7ffb5ee | 8000 | 92.61% | 91.45% | 1519.0 | 1234.6 | 3.621 | 7.982 |

## Identical whole-evidence-block token packing

One retrieval at the common maximum character cap supplies candidate blocks. The same rank-order first-fit packer retains whole blocks for every engine; source spans stay intact. Its cost is additional to the retrieval latency above.

| Engine | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | Packing p95 ms |
|---|---|---:|---:|---:|---:|---:|
| v0.3.0-3ee4094 | cl100k_base | 512 | 75.00% | 72.37% | 358.4 | 1.474 |
| v0.3.0-3ee4094 | cl100k_base | 1024 | 90.91% | 89.47% | 835.2 | 1.927 |
| v0.3.0-3ee4094 | cl100k_base | 2048 | 93.18% | 92.11% | 1161.5 | 2.368 |
| v0.3.0-3ee4094 | o200k_base | 512 | 77.27% | 75.00% | 358.8 | 1.823 |
| v0.3.0-3ee4094 | o200k_base | 1024 | 93.18% | 92.11% | 789.4 | 3.946 |
| v0.3.0-3ee4094 | o200k_base | 2048 | 93.18% | 92.11% | 1114.4 | 3.182 |
| recovered-7ffb5ee | cl100k_base | 512 | 72.73% | 71.05% | 359.6 | 1.379 |
| recovered-7ffb5ee | cl100k_base | 1024 | 90.34% | 88.82% | 834.6 | 2.649 |
| recovered-7ffb5ee | cl100k_base | 2048 | 92.61% | 91.45% | 1160.9 | 1.995 |
| recovered-7ffb5ee | o200k_base | 512 | 75.00% | 73.68% | 362.0 | 1.698 |
| recovered-7ffb5ee | o200k_base | 1024 | 92.61% | 91.45% | 788.6 | 2.783 |
| recovered-7ffb5ee | o200k_base | 2048 | 92.61% | 91.45% | 1113.7 | 4.149 |

## Source identity

The Python source hash identifies measured bytes. A dirty source tree is not the recorded Git commit; that commit is only its base revision.

| Engine | Package version | Git base commit | Checkout dirty | Source dirty | Python source SHA-256 |
|---|---|---|---|---|---|
| v0.3.0-3ee4094 | 0.3.0 | 3ee40946c5407e65fd375a8d47472066a82ae472 | False | False | ab31378c3ed7eb486aea9a6f237139000ed6b30b8cc5dcf719b53f1b864caa1f |
| recovered-7ffb5ee | 0.3.0 | 7ffb5ee17a35118dd104e52484e917f48326a34e | False | False | d9a6dc279867a4532cca6f111f1cbbbe4f369c13a334696f65db925a94b1d017 |

## Measurement boundaries

- Both versions run in independent Python processes with identical records, query order, scope, result limit, page settings, and budgets.
- Display labels are caller-selected. Imported package versions, absolute source roots, Git base commits, dirty flags, and measured source hashes are recorded independently; dirty source bytes must not be attributed to the base commit.
- Context tokens are actual tiktoken 0.12.0 counts for cl100k_base and o200k_base; they are reference encodings, not every provider's tokenizer or billed API usage.
- Recall latency excludes token counting, ingestion, MCP, networking and model inference. Result caching is disabled; SQLite and OS caches are not flushed.
- Fresh-process CLI measurements include Python startup, imports, database open, recall and JSON serialization, with warm disk caches; they are not cold-disk latency.
- The common token packer sees no evidence labels, retains whole returned blocks, and never invokes retrieval again. Packing latency is reported separately.
- Evidence requires original source identity and span plus the complete annotated text in the actual returned context. Unanswerable nonempty retrieval is not a hallucination rate.
- Synthetic heldout seeds were reserved after development selection; shared templates still limit generalization. Public LoCoMo data remains separately downloaded under CC BY-NC 4.0; reports contain IDs and metrics, not dataset text.
- This paired version comparison does not execute external competitor products. See the separate component comparison for any measured upstream kernels.

See the complete compressed JSON for category results, failures, source references, fingerprints, ingest cost, and fresh-process CLI measurements.
