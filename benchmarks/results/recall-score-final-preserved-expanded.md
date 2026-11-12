# Paired retrieval and token-cost measurements

These measurements evaluate source-evidence retrieval, not model answers or complete competitor products.

## Measurement validation

Passed recorded source-stability and context/token-budget checks. This is not a quality threshold.

## Same character-budget retrieval

| Engine | Character cap | Evidence recall | Complete evidence | Mean cl100k tokens | Mean o200k tokens | Recall p50 ms | Recall p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| preserved-v0.3 | 2000 | 39.97% | 42.37% | 606.0 | 593.7 | 2.776 | 4.284 |
| preserved-v0.3 | 8000 | 66.24% | 70.11% | 860.5 | 838.8 | 2.898 | 4.961 |
| score-aware-recall | 2000 | 47.59% | 50.23% | 607.4 | 594.9 | 3.758 | 6.224 |
| score-aware-recall | 8000 | 69.54% | 72.88% | 867.1 | 845.0 | 2.952 | 4.369 |

## Identical whole-evidence-block token packing

One retrieval at the common maximum character cap supplies candidate blocks. The same rank-order first-fit packer retains whole blocks for every engine; source spans stay intact. Its cost is additional to the retrieval latency above.

| Engine | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | Packing p95 ms |
|---|---|---:|---:|---:|---:|---:|
| preserved-v0.3 | cl100k_base | 512 | 58.76% | 63.48% | 443.6 | 1.390 |
| preserved-v0.3 | cl100k_base | 1024 | 66.24% | 70.11% | 852.0 | 1.736 |
| preserved-v0.3 | cl100k_base | 2048 | 66.24% | 70.11% | 860.5 | 1.867 |
| preserved-v0.3 | o200k_base | 512 | 60.15% | 64.71% | 445.4 | 2.206 |
| preserved-v0.3 | o200k_base | 1024 | 66.24% | 70.11% | 834.4 | 2.789 |
| preserved-v0.3 | o200k_base | 2048 | 66.24% | 70.11% | 838.8 | 2.360 |
| score-aware-recall | cl100k_base | 512 | 61.17% | 65.33% | 444.5 | 1.267 |
| score-aware-recall | cl100k_base | 1024 | 69.54% | 72.88% | 855.5 | 1.625 |
| score-aware-recall | cl100k_base | 2048 | 69.54% | 72.88% | 867.1 | 1.870 |
| score-aware-recall | o200k_base | 512 | 62.06% | 65.95% | 446.6 | 2.148 |
| score-aware-recall | o200k_base | 1024 | 69.54% | 72.88% | 839.3 | 2.388 |
| score-aware-recall | o200k_base | 2048 | 69.54% | 72.88% | 845.0 | 2.711 |

## Source identity

The Python source hash identifies measured bytes. A dirty source tree is not the recorded Git commit; that commit is only its base revision.

| Engine | Package version | Git base commit | Checkout dirty | Source dirty | Python source SHA-256 |
|---|---|---|---|---|---|
| preserved-v0.3 | 0.3.0 | 3ee40946c5407e65fd375a8d47472066a82ae472 | False | False | ab31378c3ed7eb486aea9a6f237139000ed6b30b8cc5dcf719b53f1b864caa1f |
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
