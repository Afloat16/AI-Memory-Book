# Paired retrieval and token-cost measurements

These measurements evaluate source-evidence retrieval, not model answers or complete competitor products.

## Measurement validation

Passed recorded source-stability and context/token-budget checks. This is not a quality threshold.

## Same character-budget retrieval

| Engine | Character cap | Evidence recall | Complete evidence | Mean cl100k tokens | Mean o200k tokens | Recall p50 ms | Recall p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| main-v0.2.1 | 2000 | 23.10% | 23.88% | 611.7 | 599.7 | 4.977 | 7.452 |
| main-v0.2.1 | 8000 | 66.37% | 70.42% | 946.8 | 922.2 | 3.859 | 5.696 |
| optimized-recall | 2000 | 46.83% | 49.46% | 607.5 | 595.1 | 3.740 | 6.005 |
| optimized-recall | 8000 | 68.78% | 71.96% | 862.2 | 840.3 | 3.055 | 4.591 |

## Identical whole-evidence-block token packing

One retrieval at the common maximum character cap supplies candidate blocks. The same rank-order first-fit packer retains whole blocks for every engine; source spans stay intact. Its cost is additional to the retrieval latency above.

| Engine | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | Packing p95 ms |
|---|---|---:|---:|---:|---:|---:|
| main-v0.2.1 | cl100k_base | 512 | 58.38% | 63.64% | 432.3 | 1.769 |
| main-v0.2.1 | cl100k_base | 1024 | 65.99% | 70.11% | 900.7 | 1.835 |
| main-v0.2.1 | cl100k_base | 2048 | 66.37% | 70.42% | 946.8 | 1.993 |
| main-v0.2.1 | o200k_base | 512 | 58.63% | 63.94% | 434.2 | 2.459 |
| main-v0.2.1 | o200k_base | 1024 | 66.12% | 70.26% | 891.3 | 2.528 |
| main-v0.2.1 | o200k_base | 2048 | 66.37% | 70.42% | 922.2 | 2.579 |
| optimized-recall | cl100k_base | 512 | 61.42% | 65.95% | 445.2 | 1.184 |
| optimized-recall | cl100k_base | 1024 | 68.78% | 71.96% | 854.5 | 1.965 |
| optimized-recall | cl100k_base | 2048 | 68.78% | 71.96% | 862.2 | 1.646 |
| optimized-recall | o200k_base | 512 | 62.06% | 66.41% | 446.7 | 1.811 |
| optimized-recall | o200k_base | 1024 | 68.78% | 71.96% | 835.9 | 2.270 |
| optimized-recall | o200k_base | 2048 | 68.78% | 71.96% | 840.3 | 2.478 |

## Source identity

The Python source hash identifies measured bytes. A dirty source tree is not the recorded Git commit; that commit is only its base revision.

| Engine | Package version | Git base commit | Checkout dirty | Source dirty | Python source SHA-256 |
|---|---|---|---|---|---|
| main-v0.2.1 | 0.2.1 | a05f88a79ce20be3fd5912c62fc020f8b11ba4a9 | False | False | 910eeabc9780a086d4176adf5a905142924a4694ba601f27cf31408570efa88a |
| optimized-recall | 0.3.0 | 6f5299004642618e606d001b4c574e1bae572a7e | True | False | 191d0bf023fa3589c4832440cde86482563e223bec8a79a25b2b4fe020f2fb85 |

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
