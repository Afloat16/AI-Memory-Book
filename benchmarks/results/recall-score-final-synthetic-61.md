# Paired retrieval and token-cost measurements

These measurements evaluate source-evidence retrieval, not model answers or complete competitor products.

## Measurement validation

Passed recorded source-stability and context/token-budget checks. This is not a quality threshold.

## Same character-budget retrieval

| Engine | Character cap | Evidence recall | Complete evidence | Mean cl100k tokens | Mean o200k tokens | Recall p50 ms | Recall p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| first-round-recall | 2000 | 92.61% | 91.45% | 952.3 | 782.0 | 4.132 | 11.600 |
| first-round-recall | 8000 | 92.61% | 91.45% | 1519.0 | 1234.6 | 3.434 | 7.800 |
| score-aware-recall | 2000 | 93.18% | 92.11% | 951.6 | 781.3 | 4.730 | 13.035 |
| score-aware-recall | 8000 | 93.18% | 92.11% | 1520.2 | 1235.9 | 4.044 | 9.318 |

## Identical whole-evidence-block token packing

One retrieval at the common maximum character cap supplies candidate blocks. The same rank-order first-fit packer retains whole blocks for every engine; source spans stay intact. Its cost is additional to the retrieval latency above.

| Engine | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | Packing p95 ms |
|---|---|---:|---:|---:|---:|---:|
| first-round-recall | cl100k_base | 512 | 72.73% | 71.05% | 359.6 | 1.750 |
| first-round-recall | cl100k_base | 1024 | 90.34% | 88.82% | 834.6 | 3.108 |
| first-round-recall | cl100k_base | 2048 | 92.61% | 91.45% | 1160.9 | 2.206 |
| first-round-recall | o200k_base | 512 | 75.00% | 73.68% | 362.0 | 1.703 |
| first-round-recall | o200k_base | 1024 | 92.61% | 91.45% | 788.6 | 2.512 |
| first-round-recall | o200k_base | 2048 | 92.61% | 91.45% | 1113.7 | 3.859 |
| score-aware-recall | cl100k_base | 512 | 75.00% | 72.37% | 358.4 | 8.937 |
| score-aware-recall | cl100k_base | 1024 | 90.91% | 89.47% | 835.8 | 1.892 |
| score-aware-recall | cl100k_base | 2048 | 93.18% | 92.11% | 1162.1 | 2.221 |
| score-aware-recall | o200k_base | 512 | 77.27% | 75.00% | 358.8 | 1.889 |
| score-aware-recall | o200k_base | 1024 | 93.18% | 92.11% | 790.0 | 2.499 |
| score-aware-recall | o200k_base | 2048 | 93.18% | 92.11% | 1115.0 | 13.097 |

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
