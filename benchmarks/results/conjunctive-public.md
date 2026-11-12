# Paired retrieval and token-cost measurements

These measurements evaluate source-evidence retrieval, not model answers or complete competitor products.

## Measurement validation

Passed recorded source-stability and context/token-budget checks. This is not a quality threshold.

## Same character-budget retrieval

| Engine | Character cap | Evidence recall | Complete evidence | Mean cl100k tokens | Mean o200k tokens | Recall p50 ms | Recall p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| score-aware-recall | 2000 | 47.59% | 50.23% | 607.4 | 594.9 | 3.636 | 5.658 |
| score-aware-recall | 8000 | 69.54% | 72.88% | 867.1 | 845.0 | 3.160 | 4.889 |
| conjunctive-recall | 2000 | 47.72% | 50.23% | 607.4 | 594.9 | 3.816 | 6.535 |
| conjunctive-recall | 8000 | 69.67% | 72.88% | 866.8 | 844.7 | 3.074 | 5.545 |

## Identical whole-evidence-block token packing

One retrieval at the common maximum character cap supplies candidate blocks. The same rank-order first-fit packer retains whole blocks for every engine; source spans stay intact. Its cost is additional to the retrieval latency above.

| Engine | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | Packing p95 ms |
|---|---|---:|---:|---:|---:|---:|
| score-aware-recall | cl100k_base | 512 | 61.17% | 65.33% | 444.5 | 1.417 |
| score-aware-recall | cl100k_base | 1024 | 69.54% | 72.88% | 855.5 | 1.419 |
| score-aware-recall | cl100k_base | 2048 | 69.54% | 72.88% | 867.1 | 2.030 |
| score-aware-recall | o200k_base | 512 | 62.06% | 65.95% | 446.6 | 1.800 |
| score-aware-recall | o200k_base | 1024 | 69.54% | 72.88% | 839.3 | 2.199 |
| score-aware-recall | o200k_base | 2048 | 69.54% | 72.88% | 845.0 | 2.337 |
| conjunctive-recall | cl100k_base | 512 | 60.91% | 64.87% | 444.6 | 1.261 |
| conjunctive-recall | cl100k_base | 1024 | 69.67% | 72.88% | 855.3 | 1.408 |
| conjunctive-recall | cl100k_base | 2048 | 69.67% | 72.88% | 866.8 | 1.892 |
| conjunctive-recall | o200k_base | 512 | 61.80% | 65.49% | 447.0 | 3.264 |
| conjunctive-recall | o200k_base | 1024 | 69.67% | 72.88% | 839.1 | 2.440 |
| conjunctive-recall | o200k_base | 2048 | 69.67% | 72.88% | 844.7 | 3.052 |

## Source identity

The Python source hash identifies measured bytes. A dirty source tree is not the recorded Git commit; that commit is only its base revision.

| Engine | Package version | Git base commit | Checkout dirty | Source dirty | Python source SHA-256 |
|---|---|---|---|---|---|
| score-aware-recall | 0.3.0 | 605d74e1b76fd471def8274c2a04e96e2d095075 | False | False | c8f684da97bc104a392e3884390e9f4b0eca850ed26d36394b150f469aea2b46 |
| conjunctive-recall | 0.3.0 | 08af90466c379f7c4e8cb89b7d239bc0f8f0ca81 | True | False | f2af82a18e5b76094f1d30dd355b8bbf728b76d9eb26be8e237d66aec0df83aa |

## Measurement boundaries

- Both versions run in independent Python processes with identical records, query order, scope, result limit, page settings, and budgets.
- Display labels are caller-selected. Imported package versions, absolute source roots, Git base commits, dirty flags, and measured source hashes are recorded independently; dirty source bytes must not be attributed to the base commit.
- Context tokens are actual tiktoken 0.12.0 counts for cl100k_base and o200k_base; they are reference encodings, not every provider's tokenizer or billed API usage.
- Recall latency excludes token counting, ingestion, MCP, networking and model inference. Result caching is disabled; SQLite and OS caches are not flushed.
- Fresh-process CLI measurements include Python startup, imports, database open, recall and JSON serialization, with warm disk caches; they are not cold-disk latency.
- The common token packer sees no evidence labels, retains whole returned blocks, and never invokes retrieval again. Packing latency is reported separately.
- Evidence requires original source identity and span plus the complete annotated text in the actual returned context. Unanswerable nonempty retrieval is not a hallucination rate.
- A split name does not prove independence: previously observed public questions and synthetic seeds are regression data. The separate transfer manifest records newly authored synthetic diagnostics and their limits; no synthetic corpus establishes real-world generalization. Public LoCoMo data remains separately downloaded under CC BY-NC 4.0; reports contain IDs and metrics, not dataset text.
- This paired version comparison does not execute external competitor products. See the separate component comparison for any measured upstream kernels.

See the complete compressed JSON for category results, failures, source references, fingerprints, ingest cost, and fresh-process CLI measurements.
