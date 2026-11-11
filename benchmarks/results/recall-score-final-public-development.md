# Paired retrieval and token-cost measurements

These measurements evaluate source-evidence retrieval, not model answers or complete competitor products.

## Measurement validation

Passed recorded source-stability and context/token-budget checks. This is not a quality threshold.

## Same character-budget retrieval

| Engine | Character cap | Evidence recall | Complete evidence | Mean cl100k tokens | Mean o200k tokens | Recall p50 ms | Recall p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| first-round-recall | 2000 | 52.34% | 54.22% | 606.8 | 595.4 | 3.290 | 5.383 |
| first-round-recall | 8000 | 75.70% | 78.31% | 844.2 | 825.1 | 2.598 | 3.589 |
| score-aware-recall | 2000 | 52.34% | 54.22% | 606.7 | 595.3 | 3.236 | 4.178 |
| score-aware-recall | 8000 | 77.57% | 79.52% | 845.9 | 826.8 | 2.696 | 4.004 |

## Identical whole-evidence-block token packing

One retrieval at the common maximum character cap supplies candidate blocks. The same rank-order first-fit packer retains whole blocks for every engine; source spans stay intact. Its cost is additional to the retrieval latency above.

| Engine | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | Packing p95 ms |
|---|---|---:|---:|---:|---:|---:|
| first-round-recall | cl100k_base | 512 | 67.29% | 68.67% | 436.8 | 1.144 |
| first-round-recall | cl100k_base | 1024 | 75.70% | 78.31% | 839.0 | 4.510 |
| first-round-recall | cl100k_base | 2048 | 75.70% | 78.31% | 844.2 | 1.514 |
| first-round-recall | o200k_base | 512 | 69.16% | 71.08% | 441.9 | 1.925 |
| first-round-recall | o200k_base | 1024 | 75.70% | 78.31% | 819.9 | 2.425 |
| first-round-recall | o200k_base | 2048 | 75.70% | 78.31% | 825.1 | 3.015 |
| score-aware-recall | cl100k_base | 512 | 69.16% | 71.08% | 434.9 | 1.054 |
| score-aware-recall | cl100k_base | 1024 | 77.57% | 79.52% | 840.6 | 1.460 |
| score-aware-recall | cl100k_base | 2048 | 77.57% | 79.52% | 845.9 | 1.335 |
| score-aware-recall | o200k_base | 512 | 69.16% | 71.08% | 441.4 | 2.286 |
| score-aware-recall | o200k_base | 1024 | 77.57% | 79.52% | 821.7 | 5.795 |
| score-aware-recall | o200k_base | 2048 | 77.57% | 79.52% | 826.8 | 1.986 |

## Source identity

The Python source hash identifies measured bytes. A dirty source tree is not the recorded Git commit; that commit is only its base revision.

| Engine | Package version | Git base commit | Checkout dirty | Source dirty | Python source SHA-256 |
|---|---|---|---|---|---|
| first-round-recall | 0.3.0 | 6f5299004642618e606d001b4c574e1bae572a7e | False | False | 191d0bf023fa3589c4832440cde86482563e223bec8a79a25b2b4fe020f2fb85 |
| score-aware-recall | 0.3.0 | 0ab49d4f2be6aabe5e51c3314bb9369041af5369 | True | False | c8f684da97bc104a392e3884390e9f4b0eca850ed26d36394b150f469aea2b46 |

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
