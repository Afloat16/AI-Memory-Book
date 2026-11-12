# Shared-page retrieval component comparison

Actual upstream kernels/executables; no generated answers. Scope and transport differ as documented below.

| Engine | Tokenizer | Token cap | Evidence recall | Complete evidence | Mean context tokens | Adapter p50 ms | Adapter p95 ms |
|---|---|---:|---:|---:|---:|---:|---:|
| v0.2.1 | cl100k_base | 512 | 71.03% | 73.49% | 446.1 | 3.410 | 4.218 |
| v0.2.1 | cl100k_base | 1024 | 75.70% | 77.11% | 807.5 | 3.410 | 4.218 |
| v0.2.1 | cl100k_base | 2048 | 75.70% | 77.11% | 807.5 | 3.410 | 4.218 |
| v0.2.1 | o200k_base | 512 | 71.03% | 73.49% | 445.6 | 3.410 | 4.218 |
| v0.2.1 | o200k_base | 1024 | 75.70% | 77.11% | 788.2 | 3.410 | 4.218 |
| v0.2.1 | o200k_base | 2048 | 75.70% | 77.11% | 788.2 | 3.410 | 4.218 |
| billion-context | cl100k_base | 512 | 62.62% | 62.65% | 442.7 | 1.838 | 5.774 |
| billion-context | cl100k_base | 1024 | 71.96% | 73.49% | 853.1 | 1.838 | 5.774 |
| billion-context | cl100k_base | 2048 | 71.96% | 73.49% | 864.2 | 1.838 | 5.774 |
| billion-context | o200k_base | 512 | 62.62% | 62.65% | 449.1 | 1.838 | 5.774 |
| billion-context | o200k_base | 1024 | 71.96% | 73.49% | 838.5 | 1.838 | 5.774 |
| billion-context | o200k_base | 2048 | 71.96% | 73.49% | 843.4 | 1.838 | 5.774 |
| ai-memory-hybrid | cl100k_base | 512 | 67.29% | 67.47% | 455.6 | 29.203 | 54.075 |
| ai-memory-hybrid | cl100k_base | 1024 | 71.96% | 72.29% | 761.7 | 29.203 | 54.075 |
| ai-memory-hybrid | cl100k_base | 2048 | 71.96% | 72.29% | 761.7 | 29.203 | 54.075 |
| ai-memory-hybrid | o200k_base | 512 | 67.29% | 67.47% | 455.0 | 29.203 | 54.075 |
| ai-memory-hybrid | o200k_base | 1024 | 71.96% | 72.29% | 744.1 | 29.203 | 54.075 |
| ai-memory-hybrid | o200k_base | 2048 | 71.96% | 72.29% | 744.1 | 29.203 | 54.075 |

## Interpretation and limits

- Every component receives identical adaptive-900 pages exported once from frozen v0.2.1, with the same queries, project scope, and top-k limit. No answer labels enter a backend.
- A common assembler expands selected IDs to complete original pages, adds identical citations, and applies identical rank-order whole-block token packing. Quality and context tokens describe this shared policy, not each product's native preview behavior.
- Book ranking retains its native hierarchy/FTS fields; external backends receive each page's title/body/project. Equal granularity does not mean identical indexed features or complete product workflows.
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
