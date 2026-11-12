# Shared-page retrieval component comparison

Actual upstream kernels/executables; no generated answers. Scope and transport differ as documented below.

## Measurement validation

Passed recorded source-stability and context/token-budget checks. This is not a quality threshold.

| Engine | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean context tokens | Adapter p50 ms | Adapter p95 ms |
|---|---|---:|---:|---:|---:|---:|---:|
| preserved-v0.3 | cl100k_base | 512 | 60.41% | 64.87% | 447.4 | 2.702 | 3.878 |
| preserved-v0.3 | cl100k_base | 1024 | 66.24% | 70.11% | 821.4 | 2.702 | 3.878 |
| preserved-v0.3 | cl100k_base | 2048 | 66.24% | 70.11% | 825.6 | 2.702 | 3.878 |
| preserved-v0.3 | o200k_base | 512 | 60.53% | 65.02% | 452.6 | 2.702 | 3.878 |
| preserved-v0.3 | o200k_base | 1024 | 66.24% | 70.11% | 802.8 | 2.702 | 3.878 |
| preserved-v0.3 | o200k_base | 2048 | 66.24% | 70.11% | 803.8 | 2.702 | 3.878 |
| optimized-recall | cl100k_base | 512 | 62.31% | 66.72% | 449.2 | 2.983 | 5.444 |
| optimized-recall | cl100k_base | 1024 | 68.78% | 71.96% | 823.2 | 2.983 | 5.444 |
| optimized-recall | cl100k_base | 2048 | 68.78% | 71.96% | 827.2 | 2.983 | 5.444 |
| optimized-recall | o200k_base | 512 | 62.69% | 67.03% | 452.7 | 2.983 | 5.444 |
| optimized-recall | o200k_base | 1024 | 68.78% | 71.96% | 804.3 | 2.983 | 5.444 |
| optimized-recall | o200k_base | 2048 | 68.78% | 71.96% | 805.4 | 2.983 | 5.444 |
| billion-context | cl100k_base | 512 | 58.88% | 62.71% | 442.8 | 1.225 | 2.317 |
| billion-context | cl100k_base | 1024 | 65.48% | 68.72% | 862.6 | 1.225 | 2.317 |
| billion-context | cl100k_base | 2048 | 65.48% | 68.72% | 871.0 | 1.225 | 2.317 |
| billion-context | o200k_base | 512 | 59.39% | 63.02% | 445.8 | 1.225 | 2.317 |
| billion-context | o200k_base | 1024 | 65.48% | 68.72% | 844.6 | 1.225 | 2.317 |
| billion-context | o200k_base | 2048 | 65.48% | 68.72% | 848.5 | 1.225 | 2.317 |
| ai-memory-hybrid | cl100k_base | 512 | 56.60% | 58.86% | 451.1 | 30.108 | 41.657 |
| ai-memory-hybrid | cl100k_base | 1024 | 64.47% | 66.72% | 779.3 | 30.108 | 41.657 |
| ai-memory-hybrid | cl100k_base | 2048 | 64.59% | 66.87% | 782.4 | 30.108 | 41.657 |
| ai-memory-hybrid | o200k_base | 512 | 56.98% | 59.17% | 451.8 | 30.108 | 41.657 |
| ai-memory-hybrid | o200k_base | 1024 | 64.47% | 66.72% | 760.4 | 30.108 | 41.657 |
| ai-memory-hybrid | o200k_base | 2048 | 64.59% | 66.87% | 762.4 | 30.108 | 41.657 |

## Interpretation and limits

- Every component receives identical adaptive-900 pages exported once from the supplied frozen baseline (preserved-v0.3), with the same queries, project scope, and top-k limit. Its actual package version, source hash and checkout provenance are recorded in frozen_corpus. No answer labels enter a backend.
- Display labels and legacy engine selectors do not establish source identity. Git base commits, source roots, checkout/source dirty flags and measured source hashes identify the executed core; a dirty source tree is not the base commit.
- A common assembler expands selected IDs to complete original pages, adds identical citations, and applies identical rank-order whole-block token packing. Quality and context tokens describe this shared policy, not each product's native preview behavior.
- Book ranking retains its native hierarchy/FTS fields; external backends receive each page's title/body/project. Equal granularity does not mean identical indexed features or complete product workflows.
- Native metadata pages absent from the shared corpus consume top-k slots and search payload tokens but earn no evidence; they are counted as unmapped hits and excluded from harness full-page expansion.
- AI-Memory-Book latency is in-process recall including its own context assembly; Billion reports both native searchBlocks kernel time and JSON IPC roundtrip; ai-memory reports actual persistent loopback HTTP/MCP roundtrip. These transport boundaries differ.
- All native feature/embedding caches may warm naturally. First-pass and repeated-query latencies are separate; no OS cold-cache or process-startup claims are made.
- Billion executes pinned upstream searchBlocks only, not its summarization/proxy workflow. ai-memory uses the pinned official native binary; hybrid uses its default local MiniLM with embedding backfill complete. Upstream global hybrid requests are FTS-only.
- Native search payloads and actual ai-memory full-page reads are counted separately. Canonical JSON payload counts exclude tool definitions, initialization, requests, model inference, and provider chat wrappers; they are not billed tokens or an equal-cap native product comparison.
- The fixed ai-memory cost policy reads every mapped top-k page even when its preview already contains enough evidence. It is not a minimum-read strategy or a token-budget-adaptive native policy; a preview-only consumer can spend less.
- Common full-page expansion for Billion is a harness-side lookup; it does not pretend to measure a native fetch API. ai-memory native reads are executed and checked against the shared page text before evidence is scored.
- The two measured tiktoken encodings are references, not every provider's tokenizer. Packing and full-read costs are additional to retrieval and separately reported.
- Evidence coverage requires complete annotated text and source identity/span. It is not generated-answer accuracy, semantic equivalence, or a hallucination metric.
- Public LoCoMo data remains outside git under CC BY-NC 4.0. Published reports contain IDs and metrics only. Synthetic heldout templates are not an independent domain test.
