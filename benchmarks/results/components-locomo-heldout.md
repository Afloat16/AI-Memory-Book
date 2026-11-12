# Shared-page retrieval component comparison

Actual upstream kernels/executables; no generated answers. Scope and transport differ as documented below.

| Engine | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean context tokens | Adapter p50 ms | Adapter p95 ms |
|---|---|---:|---:|---:|---:|---:|---:|
| v0.2.1 | cl100k_base | 512 | 68.59% | 70.45% | 451.7 | 3.992 | 7.442 |
| v0.2.1 | cl100k_base | 1024 | 73.30% | 75.57% | 813.6 | 3.992 | 7.442 |
| v0.2.1 | cl100k_base | 2048 | 73.30% | 75.57% | 818.5 | 3.992 | 7.442 |
| v0.2.1 | o200k_base | 512 | 68.59% | 70.45% | 455.1 | 3.992 | 7.442 |
| v0.2.1 | o200k_base | 1024 | 73.30% | 75.57% | 796.5 | 3.992 | 7.442 |
| v0.2.1 | o200k_base | 2048 | 73.30% | 75.57% | 796.5 | 3.992 | 7.442 |
| candidate | cl100k_base | 512 | 68.59% | 70.45% | 449.2 | 2.758 | 4.601 |
| candidate | cl100k_base | 1024 | 72.77% | 75.00% | 815.7 | 2.758 | 4.601 |
| candidate | cl100k_base | 2048 | 72.77% | 75.00% | 819.7 | 2.758 | 4.601 |
| candidate | o200k_base | 512 | 68.59% | 70.45% | 454.3 | 2.758 | 4.601 |
| candidate | o200k_base | 1024 | 72.77% | 75.00% | 797.9 | 2.758 | 4.601 |
| candidate | o200k_base | 2048 | 72.77% | 75.00% | 797.9 | 2.758 | 4.601 |
| billion-context | cl100k_base | 512 | 67.02% | 67.05% | 442.5 | 1.367 | 2.952 |
| billion-context | cl100k_base | 1024 | 73.30% | 73.86% | 862.3 | 1.367 | 2.952 |
| billion-context | cl100k_base | 2048 | 73.30% | 73.86% | 869.9 | 1.367 | 2.952 |
| billion-context | o200k_base | 512 | 68.59% | 68.75% | 443.4 | 1.367 | 2.952 |
| billion-context | o200k_base | 1024 | 73.30% | 73.86% | 842.9 | 1.367 | 2.952 |
| billion-context | o200k_base | 2048 | 73.30% | 73.86% | 847.2 | 1.367 | 2.952 |
| ai-memory-hybrid | cl100k_base | 512 | 63.87% | 63.64% | 452.0 | 29.972 | 66.727 |
| ai-memory-hybrid | cl100k_base | 1024 | 71.73% | 72.16% | 772.0 | 29.972 | 66.727 |
| ai-memory-hybrid | cl100k_base | 2048 | 72.25% | 72.73% | 773.7 | 29.972 | 66.727 |
| ai-memory-hybrid | o200k_base | 512 | 64.92% | 64.77% | 452.9 | 29.972 | 66.727 |
| ai-memory-hybrid | o200k_base | 1024 | 71.73% | 72.16% | 752.7 | 29.972 | 66.727 |
| ai-memory-hybrid | o200k_base | 2048 | 72.25% | 72.73% | 753.5 | 29.972 | 66.727 |

## Interpretation and limits

- Every component receives identical adaptive-900 pages exported once from frozen v0.2.1, with the same queries, project scope, and top-k limit. No answer labels enter a backend.
- A common assembler expands selected IDs to complete original pages, adds identical citations, and applies identical rank-order whole-block token packing. Quality and context tokens describe this shared policy, not each product's native preview behavior.
- Book ranking retains its native hierarchy/FTS fields; external backends receive each page's title/body/project. Equal granularity does not mean identical indexed features or complete product workflows.
- Native metadata pages absent from the shared corpus consume top-k slots and search payload tokens but earn no evidence; they are counted as unmapped hits and excluded from harness full-page expansion.
- AI-Memory-Book latency is in-process recall including its own context assembly; Billion reports both native searchBlocks kernel time and JSON IPC roundtrip; ai-memory reports actual persistent loopback HTTP/MCP roundtrip. These transport boundaries differ.
- All native feature/embedding caches may warm naturally. First-pass and repeated-query latencies are separate; no OS cold-cache or process-startup claims are made.
- Billion executes pinned upstream searchBlocks only, not its summarization/proxy workflow. ai-memory uses the pinned official native binary; hybrid uses its default local MiniLM with embedding backfill complete. Upstream global hybrid requests are FTS-only.
- Native search payloads and actual ai-memory full-page reads are counted separately. Canonical JSON payload counts exclude tool definitions, initialization, requests, model inference, and provider chat wrappers; they are not billed tokens or an equal-cap native product comparison.
- Common full-page expansion for Billion is a harness-side lookup; it does not pretend to measure a native fetch API. ai-memory native reads are executed and checked against the shared page text before evidence is scored.
- The two measured tiktoken encodings are references, not every provider's tokenizer. Packing and full-read costs are additional to retrieval and separately reported.
- Evidence coverage requires complete annotated text and source identity/span. It is not generated-answer accuracy, semantic equivalence, or a hallucination metric.
- Public LoCoMo data remains outside git under CC BY-NC 4.0. Published reports contain IDs and metrics only. Synthetic heldout templates are not an independent domain test.
- The fixed ai-memory cost policy reads every mapped top-k page even when its preview already contains enough evidence. It is not a minimum-read strategy or a token-budget-adaptive native policy; a preview-only consumer can spend less.
- Structural source preflight verified every required/stale annotation fits one complete canonical page and matching original source span in both versions. Zero labels are affected by the evaluator's lack of cross-page annotation union; no labels were dropped.
