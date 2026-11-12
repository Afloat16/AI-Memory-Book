# Paired retrieval and token-cost measurements

These measurements evaluate source-evidence retrieval, not model answers or complete competitor products.

## Measurement validation

Passed recorded source-stability and context/token-budget checks. This is not a quality threshold.

## Same character-budget retrieval

| Engine | Character cap | Evidence recall | Complete evidence | Mean cl100k tokens | Mean o200k tokens | Recall p50 ms | Recall p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| v0.3.0-3ee4094 | 2000 | 42.06% | 40.96% | 603.3 | 592.1 | 2.621 | 4.652 |
| v0.3.0-3ee4094 | 8000 | 75.70% | 77.11% | 841.3 | 822.3 | 2.689 | 4.775 |
| recovered-7ffb5ee | 2000 | 45.79% | 45.78% | 607.0 | 595.7 | 4.000 | 6.540 |
| recovered-7ffb5ee | 8000 | 75.70% | 78.31% | 844.2 | 825.1 | 3.350 | 4.766 |

## Identical whole-evidence-block token packing

One retrieval at the common maximum character cap supplies candidate blocks. The same rank-order first-fit packer retains whole blocks for every engine; source spans stay intact. Its cost is additional to the retrieval latency above.

| Engine | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | Packing p95 ms |
|---|---|---:|---:|---:|---:|---:|
| v0.3.0-3ee4094 | cl100k_base | 512 | 63.55% | 63.86% | 439.2 | 2.823 |
| v0.3.0-3ee4094 | cl100k_base | 1024 | 75.70% | 77.11% | 831.1 | 3.161 |
| v0.3.0-3ee4094 | cl100k_base | 2048 | 75.70% | 77.11% | 841.3 | 1.814 |
| v0.3.0-3ee4094 | o200k_base | 512 | 64.49% | 65.06% | 439.7 | 1.970 |
| v0.3.0-3ee4094 | o200k_base | 1024 | 75.70% | 77.11% | 814.1 | 3.321 |
| v0.3.0-3ee4094 | o200k_base | 2048 | 75.70% | 77.11% | 822.3 | 3.819 |
| recovered-7ffb5ee | cl100k_base | 512 | 67.29% | 68.67% | 436.8 | 1.396 |
| recovered-7ffb5ee | cl100k_base | 1024 | 75.70% | 78.31% | 839.0 | 3.036 |
| recovered-7ffb5ee | cl100k_base | 2048 | 75.70% | 78.31% | 844.2 | 2.304 |
| recovered-7ffb5ee | o200k_base | 512 | 69.16% | 71.08% | 441.9 | 1.842 |
| recovered-7ffb5ee | o200k_base | 1024 | 75.70% | 78.31% | 819.9 | 3.960 |
| recovered-7ffb5ee | o200k_base | 2048 | 75.70% | 78.31% | 825.1 | 2.325 |

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
