# Paired retrieval and token-cost measurements

These measurements evaluate source-evidence retrieval, not model answers or complete competitor products.

## Measurement validation

Passed recorded source-stability and context/token-budget checks. This is not a quality threshold.

## Same character-budget retrieval

| Engine | Character cap | Evidence recall | Complete evidence | Mean cl100k tokens | Mean o200k tokens | Recall p50 ms | Recall p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| score-baseline | 2000 | 93.18% | 92.11% | 951.6 | 781.3 | 4.409 | 11.799 |
| score-baseline | 8000 | 93.18% | 92.11% | 1520.2 | 1235.9 | 3.809 | 9.450 |
| conjunctive-candidate | 2000 | 94.32% | 93.42% | 951.6 | 781.3 | 5.759 | 18.331 |
| conjunctive-candidate | 8000 | 94.32% | 93.42% | 1520.1 | 1235.8 | 3.924 | 11.087 |

## Identical whole-evidence-block token packing

One retrieval at the common maximum character cap supplies candidate blocks. The same rank-order first-fit packer retains whole blocks for every engine; source spans stay intact. Its cost is additional to the retrieval latency above.

| Engine | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | Packing p95 ms |
|---|---|---:|---:|---:|---:|---:|
| score-baseline | cl100k_base | 512 | 75.00% | 72.37% | 358.4 | 0.993 |
| score-baseline | cl100k_base | 1024 | 90.91% | 89.47% | 835.8 | 1.652 |
| score-baseline | cl100k_base | 2048 | 93.18% | 92.11% | 1162.1 | 2.022 |
| score-baseline | o200k_base | 512 | 77.27% | 75.00% | 358.8 | 1.610 |
| score-baseline | o200k_base | 1024 | 93.18% | 92.11% | 790.0 | 2.269 |
| score-baseline | o200k_base | 2048 | 93.18% | 92.11% | 1115.0 | 3.694 |
| conjunctive-candidate | cl100k_base | 512 | 77.27% | 73.68% | 358.5 | 1.043 |
| conjunctive-candidate | cl100k_base | 1024 | 92.05% | 90.79% | 835.7 | 1.798 |
| conjunctive-candidate | cl100k_base | 2048 | 94.32% | 93.42% | 1162.0 | 2.108 |
| conjunctive-candidate | o200k_base | 512 | 79.55% | 76.32% | 358.5 | 1.851 |
| conjunctive-candidate | o200k_base | 1024 | 94.32% | 93.42% | 789.8 | 3.070 |
| conjunctive-candidate | o200k_base | 2048 | 94.32% | 93.42% | 1114.9 | 5.106 |

## Source identity

The Python source hash identifies measured bytes. A dirty source tree is not the recorded Git commit; that commit is only its base revision.

| Engine | Package version | Git base commit | Checkout dirty | Source dirty | Python source SHA-256 |
|---|---|---|---|---|---|
| score-baseline | 0.3.0 | 605d74e1b76fd471def8274c2a04e96e2d095075 | False | False | c8f684da97bc104a392e3884390e9f4b0eca850ed26d36394b150f469aea2b46 |
| conjunctive-candidate | 0.3.0 | 605d74e1b76fd471def8274c2a04e96e2d095075 | True | True | f2af82a18e5b76094f1d30dd355b8bbf728b76d9eb26be8e237d66aec0df83aa |

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
