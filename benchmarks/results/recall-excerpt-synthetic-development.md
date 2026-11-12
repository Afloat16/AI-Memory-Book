# Paired retrieval and token-cost measurements

These measurements evaluate source-evidence retrieval, not model answers or complete competitor products.

## Measurement validation

Passed recorded source-stability and context/token-budget checks. This is not a quality threshold.

## Same character-budget retrieval

| Engine | Character cap | Evidence recall | Complete evidence | Mean cl100k tokens | Mean o200k tokens | Recall p50 ms | Recall p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| recovered-7ffb5ee | 2000 | 91.48% | 90.13% | 952.6 | 782.2 | 4.856 | 12.381 |
| recovered-7ffb5ee | 8000 | 92.61% | 91.45% | 1519.0 | 1234.6 | 4.204 | 9.549 |
| intact-first-development | 2000 | 92.61% | 91.45% | 952.3 | 782.0 | 7.818 | 21.989 |
| intact-first-development | 8000 | 92.61% | 91.45% | 1519.0 | 1234.6 | 6.693 | 19.038 |

## Identical whole-evidence-block token packing

One retrieval at the common maximum character cap supplies candidate blocks. The same rank-order first-fit packer retains whole blocks for every engine; source spans stay intact. Its cost is additional to the retrieval latency above.

| Engine | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | Packing p95 ms |
|---|---|---:|---:|---:|---:|---:|
| recovered-7ffb5ee | cl100k_base | 512 | 72.73% | 71.05% | 359.6 | 1.504 |
| recovered-7ffb5ee | cl100k_base | 1024 | 90.34% | 88.82% | 834.6 | 2.845 |
| recovered-7ffb5ee | cl100k_base | 2048 | 92.61% | 91.45% | 1160.9 | 5.433 |
| recovered-7ffb5ee | o200k_base | 512 | 75.00% | 73.68% | 362.0 | 3.002 |
| recovered-7ffb5ee | o200k_base | 1024 | 92.61% | 91.45% | 788.6 | 3.306 |
| recovered-7ffb5ee | o200k_base | 2048 | 92.61% | 91.45% | 1113.7 | 3.931 |
| intact-first-development | cl100k_base | 512 | 72.73% | 71.05% | 359.6 | 2.082 |
| intact-first-development | cl100k_base | 1024 | 90.34% | 88.82% | 834.6 | 3.142 |
| intact-first-development | cl100k_base | 2048 | 92.61% | 91.45% | 1160.9 | 3.658 |
| intact-first-development | o200k_base | 512 | 75.00% | 73.68% | 362.0 | 7.888 |
| intact-first-development | o200k_base | 1024 | 92.61% | 91.45% | 788.6 | 4.820 |
| intact-first-development | o200k_base | 2048 | 92.61% | 91.45% | 1113.7 | 4.502 |

## Source identity

The Python source hash identifies measured bytes. A dirty source tree is not the recorded Git commit; that commit is only its base revision.

| Engine | Package version | Git base commit | Checkout dirty | Source dirty | Python source SHA-256 |
|---|---|---|---|---|---|
| recovered-7ffb5ee | 0.3.0 | 7ffb5ee17a35118dd104e52484e917f48326a34e | False | False | d9a6dc279867a4532cca6f111f1cbbbe4f369c13a334696f65db925a94b1d017 |
| intact-first-development | 0.3.0 | 7ffb5ee17a35118dd104e52484e917f48326a34e | True | True | ce1ecf8d53596489738392412077067e7d913e78bd5d4f0de737422bbe98af45 |

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
