# Paired retrieval and token-cost measurements

These measurements evaluate source-evidence retrieval, not model answers or complete competitor products.

## Measurement validation

Passed recorded source-stability and context/token-budget checks. This is not a quality threshold.

## Same character-budget retrieval

| Engine | Character cap | Evidence recall | Complete evidence | Mean cl100k tokens | Mean o200k tokens | Recall p50 ms | Recall p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| score-aware-recall | 2000 | 88.89% | 86.67% | 188.5 | 172.9 | 0.785 | 1.678 |
| score-aware-recall | 8000 | 88.89% | 86.67% | 188.5 | 172.9 | 0.675 | 1.479 |
| conjunctive-recall | 2000 | 88.89% | 86.67% | 188.5 | 172.9 | 0.586 | 1.702 |
| conjunctive-recall | 8000 | 88.89% | 86.67% | 188.5 | 172.9 | 0.614 | 1.693 |

## Identical whole-evidence-block token packing

One retrieval at the common maximum character cap supplies candidate blocks. The same rank-order first-fit packer retains whole blocks for every engine; source spans stay intact. Its cost is additional to the retrieval latency above.

| Engine | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | Packing p95 ms |
|---|---|---:|---:|---:|---:|---:|
| score-aware-recall | cl100k_base | 512 | 88.89% | 86.67% | 188.5 | 0.571 |
| score-aware-recall | cl100k_base | 1024 | 88.89% | 86.67% | 188.5 | 0.519 |
| score-aware-recall | cl100k_base | 2048 | 88.89% | 86.67% | 188.5 | 0.570 |
| score-aware-recall | o200k_base | 512 | 88.89% | 86.67% | 172.9 | 0.534 |
| score-aware-recall | o200k_base | 1024 | 88.89% | 86.67% | 172.9 | 0.571 |
| score-aware-recall | o200k_base | 2048 | 88.89% | 86.67% | 172.9 | 0.533 |
| conjunctive-recall | cl100k_base | 512 | 88.89% | 86.67% | 188.5 | 0.423 |
| conjunctive-recall | cl100k_base | 1024 | 88.89% | 86.67% | 188.5 | 0.348 |
| conjunctive-recall | cl100k_base | 2048 | 88.89% | 86.67% | 188.5 | 0.360 |
| conjunctive-recall | o200k_base | 512 | 88.89% | 86.67% | 172.9 | 0.524 |
| conjunctive-recall | o200k_base | 1024 | 88.89% | 86.67% | 172.9 | 0.548 |
| conjunctive-recall | o200k_base | 2048 | 88.89% | 86.67% | 172.9 | 0.505 |

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
