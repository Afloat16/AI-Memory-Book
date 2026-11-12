# Paired retrieval and token-cost measurements

These measurements evaluate source-evidence retrieval, not model answers or complete competitor products.

## Measurement validation

Passed recorded source-stability and context/token-budget checks. This is not a quality threshold.

## Same character-budget retrieval

| Engine | Character cap | Evidence recall | Complete evidence | Mean cl100k tokens | Mean o200k tokens | Recall p50 ms | Recall p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| score-baseline | 2000 | 52.34% | 54.22% | 606.7 | 595.3 | 3.473 | 4.756 |
| score-baseline | 8000 | 77.57% | 79.52% | 845.9 | 826.8 | 2.846 | 3.941 |
| conjunctive-candidate | 2000 | 52.34% | 54.22% | 606.7 | 595.4 | 3.849 | 5.872 |
| conjunctive-candidate | 8000 | 77.57% | 79.52% | 845.8 | 826.7 | 2.801 | 4.713 |

## Identical whole-evidence-block token packing

One retrieval at the common maximum character cap supplies candidate blocks. The same rank-order first-fit packer retains whole blocks for every engine; source spans stay intact. Its cost is additional to the retrieval latency above.

| Engine | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean tokens | Packing p95 ms |
|---|---|---:|---:|---:|---:|---:|
| score-baseline | cl100k_base | 512 | 69.16% | 71.08% | 434.9 | 1.146 |
| score-baseline | cl100k_base | 1024 | 77.57% | 79.52% | 840.6 | 1.468 |
| score-baseline | cl100k_base | 2048 | 77.57% | 79.52% | 845.9 | 3.764 |
| score-baseline | o200k_base | 512 | 69.16% | 71.08% | 441.4 | 2.056 |
| score-baseline | o200k_base | 1024 | 77.57% | 79.52% | 821.7 | 1.898 |
| score-baseline | o200k_base | 2048 | 77.57% | 79.52% | 826.8 | 1.961 |
| conjunctive-candidate | cl100k_base | 512 | 69.16% | 71.08% | 435.0 | 1.000 |
| conjunctive-candidate | cl100k_base | 1024 | 77.57% | 79.52% | 840.5 | 1.259 |
| conjunctive-candidate | cl100k_base | 2048 | 77.57% | 79.52% | 845.8 | 1.438 |
| conjunctive-candidate | o200k_base | 512 | 69.16% | 71.08% | 441.5 | 1.466 |
| conjunctive-candidate | o200k_base | 1024 | 77.57% | 79.52% | 821.5 | 1.981 |
| conjunctive-candidate | o200k_base | 2048 | 77.57% | 79.52% | 826.7 | 1.973 |

## Source identity

The Python source hash identifies measured bytes. A dirty source tree is not the recorded Git commit; that commit is only its base revision.

| Engine | Package version | Git base commit | Checkout dirty | Source dirty | Python source SHA-256 |
|---|---|---|---|---|---|
| score-baseline | 0.3.0 | 605d74e1b76fd471def8274c2a04e96e2d095075 | False | False | c8f684da97bc104a392e3884390e9f4b0eca850ed26d36394b150f469aea2b46 |
| conjunctive-candidate | 0.3.0 | 917bf88a68d183c9032ccdf0cd2da17df8432917 | True | True | f2af82a18e5b76094f1d30dd355b8bbf728b76d9eb26be8e237d66aec0df83aa |

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
