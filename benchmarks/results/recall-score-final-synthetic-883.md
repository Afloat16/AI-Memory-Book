# Paired retrieval and token-cost measurements

These measurements evaluate source-evidence retrieval, not model answers or complete competitor products.

## Measurement validation

Passed recorded source-stability and context/token-budget checks. This is not a quality threshold.

## Same character-budget retrieval

| Engine | Character cap | Evidence recall | Complete evidence | Mean cl100k tokens | Mean o200k tokens | Recall p50 ms | Recall p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| first-round-recall | 2000 | 78.98% | 78.95% | 931.6 | 774.0 | 4.229 | 12.736 |
| first-round-recall | 8000 | 81.25% | 81.58% | 1495.9 | 1229.9 | 3.371 | 8.511 |
| score-aware-recall | 2000 | 79.55% | 81.58% | 932.6 | 774.9 | 4.497 | 13.998 |
| score-aware-recall | 8000 | 81.82% | 84.21% | 1495.5 | 1229.5 | 3.751 | 9.719 |

## Identical whole-evidence-block token packing

One retrieval at the common maximum character cap supplies candidate blocks. The same rank-order first-fit packer retains whole blocks for every engine; source spans stay intact. Its cost is additional to the retrieval latency above.

| Engine | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | Packing p95 ms |
|---|---|---:|---:|---:|---:|---:|
| first-round-recall | cl100k_base | 512 | 65.91% | 65.79% | 371.3 | 0.983 |
| first-round-recall | cl100k_base | 1024 | 80.68% | 81.58% | 855.8 | 1.508 |
| first-round-recall | cl100k_base | 2048 | 81.25% | 81.58% | 1172.3 | 2.542 |
| first-round-recall | o200k_base | 512 | 70.45% | 71.05% | 380.0 | 1.713 |
| first-round-recall | o200k_base | 1024 | 81.25% | 81.58% | 828.2 | 2.280 |
| first-round-recall | o200k_base | 2048 | 81.25% | 81.58% | 1109.6 | 3.547 |
| score-aware-recall | cl100k_base | 512 | 68.18% | 68.42% | 373.9 | 1.207 |
| score-aware-recall | cl100k_base | 1024 | 81.82% | 84.21% | 855.2 | 1.639 |
| score-aware-recall | cl100k_base | 2048 | 81.82% | 84.21% | 1171.9 | 2.080 |
| score-aware-recall | o200k_base | 512 | 72.73% | 73.68% | 379.6 | 1.707 |
| score-aware-recall | o200k_base | 1024 | 81.82% | 84.21% | 825.3 | 2.289 |
| score-aware-recall | o200k_base | 2048 | 81.82% | 84.21% | 1109.2 | 3.292 |

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
