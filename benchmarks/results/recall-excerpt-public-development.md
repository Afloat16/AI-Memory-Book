# Paired retrieval and token-cost measurements

These measurements evaluate source-evidence retrieval, not model answers or complete competitor products.

## Measurement validation

Passed recorded source-stability and context/token-budget checks. This is not a quality threshold.

## Same character-budget retrieval

| Engine | Character cap | Evidence recall | Complete evidence | Mean cl100k tokens | Mean o200k tokens | Recall p50 ms | Recall p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| recovered-7ffb5ee | 2000 | 45.79% | 45.78% | 607.0 | 595.7 | 3.963 | 8.660 |
| recovered-7ffb5ee | 8000 | 75.70% | 78.31% | 844.2 | 825.1 | 2.892 | 3.633 |
| intact-first-development | 2000 | 52.34% | 54.22% | 606.8 | 595.4 | 3.775 | 5.222 |
| intact-first-development | 8000 | 75.70% | 78.31% | 844.2 | 825.1 | 3.023 | 4.795 |

## Identical whole-evidence-block token packing

One retrieval at the common maximum character cap supplies candidate blocks. The same rank-order first-fit packer retains whole blocks for every engine; source spans stay intact. Its cost is additional to the retrieval latency above.

| Engine | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | Packing p95 ms |
|---|---|---:|---:|---:|---:|---:|
| recovered-7ffb5ee | cl100k_base | 512 | 67.29% | 68.67% | 436.8 | 0.856 |
| recovered-7ffb5ee | cl100k_base | 1024 | 75.70% | 78.31% | 839.0 | 1.264 |
| recovered-7ffb5ee | cl100k_base | 2048 | 75.70% | 78.31% | 844.2 | 1.156 |
| recovered-7ffb5ee | o200k_base | 512 | 69.16% | 71.08% | 441.9 | 1.603 |
| recovered-7ffb5ee | o200k_base | 1024 | 75.70% | 78.31% | 819.9 | 2.011 |
| recovered-7ffb5ee | o200k_base | 2048 | 75.70% | 78.31% | 825.1 | 2.008 |
| intact-first-development | cl100k_base | 512 | 67.29% | 68.67% | 436.8 | 1.199 |
| intact-first-development | cl100k_base | 1024 | 75.70% | 78.31% | 839.0 | 1.270 |
| intact-first-development | cl100k_base | 2048 | 75.70% | 78.31% | 844.2 | 1.195 |
| intact-first-development | o200k_base | 512 | 69.16% | 71.08% | 441.9 | 1.722 |
| intact-first-development | o200k_base | 1024 | 75.70% | 78.31% | 819.9 | 1.921 |
| intact-first-development | o200k_base | 2048 | 75.70% | 78.31% | 825.1 | 2.184 |

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
