# Paired retrieval and token-cost measurements

These measurements evaluate source-evidence retrieval, not model answers or complete competitor products.

## Measurement validation

Passed recorded source-stability and context/token-budget checks. This is not a quality threshold.

## Same character-budget retrieval

| Engine | Character cap | Evidence recall | Complete evidence | Mean cl100k tokens | Mean o200k tokens | Recall p50 ms | Recall p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| first-round-recall | 2000 | 46.83% | 49.46% | 607.5 | 595.1 | 3.761 | 6.212 |
| first-round-recall | 8000 | 68.78% | 71.96% | 862.2 | 840.3 | 3.047 | 4.986 |
| conjunctive-recall | 2000 | 47.72% | 50.23% | 607.4 | 594.9 | 4.275 | 7.684 |
| conjunctive-recall | 8000 | 69.67% | 72.88% | 866.8 | 844.7 | 3.160 | 5.954 |

## Identical whole-evidence-block token packing

One retrieval at the common maximum character cap supplies candidate blocks. The same rank-order first-fit packer retains whole blocks for every engine; source spans stay intact. Its cost is additional to the retrieval latency above.

| Engine | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | Packing p95 ms |
|---|---|---:|---:|---:|---:|---:|
| first-round-recall | cl100k_base | 512 | 61.42% | 65.95% | 445.2 | 1.122 |
| first-round-recall | cl100k_base | 1024 | 68.78% | 71.96% | 854.5 | 1.426 |
| first-round-recall | cl100k_base | 2048 | 68.78% | 71.96% | 862.2 | 1.421 |
| first-round-recall | o200k_base | 512 | 62.06% | 66.41% | 446.7 | 1.711 |
| first-round-recall | o200k_base | 1024 | 68.78% | 71.96% | 835.9 | 2.778 |
| first-round-recall | o200k_base | 2048 | 68.78% | 71.96% | 840.3 | 2.796 |
| conjunctive-recall | cl100k_base | 512 | 60.91% | 64.87% | 444.6 | 1.490 |
| conjunctive-recall | cl100k_base | 1024 | 69.67% | 72.88% | 855.3 | 1.719 |
| conjunctive-recall | cl100k_base | 2048 | 69.67% | 72.88% | 866.8 | 1.991 |
| conjunctive-recall | o200k_base | 512 | 61.80% | 65.49% | 447.0 | 2.401 |
| conjunctive-recall | o200k_base | 1024 | 69.67% | 72.88% | 839.1 | 2.670 |
| conjunctive-recall | o200k_base | 2048 | 69.67% | 72.88% | 844.7 | 3.143 |

## Source identity

The Python source hash identifies measured bytes. A dirty source tree is not the recorded Git commit; that commit is only its base revision.

| Engine | Package version | Git base commit | Checkout dirty | Source dirty | Python source SHA-256 |
|---|---|---|---|---|---|
| first-round-recall | 0.3.0 | 6f5299004642618e606d001b4c574e1bae572a7e | False | False | 191d0bf023fa3589c4832440cde86482563e223bec8a79a25b2b4fe020f2fb85 |
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
