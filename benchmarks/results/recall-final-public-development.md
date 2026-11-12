# Paired retrieval and token-cost measurements

These measurements evaluate source-evidence retrieval, not model answers or complete competitor products.

## Measurement validation

Passed recorded source-stability and context/token-budget checks. This is not a quality threshold.

## Same character-budget retrieval

| Engine | Character cap | Evidence recall | Complete evidence | Mean cl100k tokens | Mean o200k tokens | Recall p50 ms | Recall p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| preserved-v0.3 | 2000 | 42.06% | 40.96% | 603.3 | 592.1 | 2.374 | 3.099 |
| preserved-v0.3 | 8000 | 75.70% | 77.11% | 841.3 | 822.3 | 2.429 | 3.661 |
| optimized-recall | 2000 | 52.34% | 54.22% | 606.8 | 595.4 | 3.403 | 5.136 |
| optimized-recall | 8000 | 75.70% | 78.31% | 844.2 | 825.1 | 2.635 | 3.335 |

## Identical whole-evidence-block token packing

One retrieval at the common maximum character cap supplies candidate blocks. The same rank-order first-fit packer retains whole blocks for every engine; source spans stay intact. Its cost is additional to the retrieval latency above.

| Engine | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | Packing p95 ms |
|---|---|---:|---:|---:|---:|---:|
| preserved-v0.3 | cl100k_base | 512 | 63.55% | 63.86% | 439.2 | 1.359 |
| preserved-v0.3 | cl100k_base | 1024 | 75.70% | 77.11% | 831.1 | 1.341 |
| preserved-v0.3 | cl100k_base | 2048 | 75.70% | 77.11% | 841.3 | 1.399 |
| preserved-v0.3 | o200k_base | 512 | 64.49% | 65.06% | 439.7 | 1.708 |
| preserved-v0.3 | o200k_base | 1024 | 75.70% | 77.11% | 814.1 | 2.109 |
| preserved-v0.3 | o200k_base | 2048 | 75.70% | 77.11% | 822.3 | 2.633 |
| optimized-recall | cl100k_base | 512 | 67.29% | 68.67% | 436.8 | 1.115 |
| optimized-recall | cl100k_base | 1024 | 75.70% | 78.31% | 839.0 | 1.425 |
| optimized-recall | cl100k_base | 2048 | 75.70% | 78.31% | 844.2 | 1.586 |
| optimized-recall | o200k_base | 512 | 69.16% | 71.08% | 441.9 | 6.017 |
| optimized-recall | o200k_base | 1024 | 75.70% | 78.31% | 819.9 | 2.124 |
| optimized-recall | o200k_base | 2048 | 75.70% | 78.31% | 825.1 | 2.117 |

## Source identity

The Python source hash identifies measured bytes. A dirty source tree is not the recorded Git commit; that commit is only its base revision.

| Engine | Package version | Git base commit | Checkout dirty | Source dirty | Python source SHA-256 |
|---|---|---|---|---|---|
| preserved-v0.3 | 0.3.0 | 3ee40946c5407e65fd375a8d47472066a82ae472 | False | False | ab31378c3ed7eb486aea9a6f237139000ed6b30b8cc5dcf719b53f1b864caa1f |
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
