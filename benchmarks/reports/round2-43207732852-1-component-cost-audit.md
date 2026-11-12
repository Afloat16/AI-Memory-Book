# Independent round-two component cost audit

Run `43207732852-1`, immutable result commit `057b814ab809dec57d4fa4c75fe540d59a0f0027`. All 6 components and 1,536 first-pass cost records passed. The separate full-stage assessment passed before this audit. No retrieval, scoring or model calls were repeated.

Every token pair below is **cl100k_base / o200k_base**. `null` is unavailable, not zero.

| Component | Native search payload | Native search content | All-read payload | All-read content | Reads/query | Mean read ms | Metadata hits / queries |
| --- | --- | --- | --- | --- | --- | --- | --- |
| baseline-component | 3983.523 / 4001.789 | 802.805 / 801.312 | 0.000 / 0.000 | 0.000 / 0.000 | 0.000000 | 0.000000 | 0 / 0 |
| candidate-component | 3983.527 / 4001.793 | 802.805 / 801.312 | 0.000 / 0.000 | 0.000 / 0.000 | 0.000000 | 0.000000 | 0 / 0 |
| claude-mem-fts | 1626.605 / 1612.273 | null | 0.000 / 0.000 | 0.000 / 0.000 | 0.000000 | 0.000000 | 0 / 0 |
| ai-memory-hybrid | 1018.898 / 1016.312 | 955.012 / 950.441 | 1818.609 / 1811.520 | 1603.664 / 1591.625 | 4.976562 | 4.294158 | 0 / 0 |
| billion-context | 585.664 / 579.328 | null | 0.000 / 0.000 | 0.000 / 0.000 | 0.000000 | 0.000000 | 0 / 0 |
| candidate-semantic-component | 4079.906 / 4099.117 | 819.117 / 817.766 | 0.000 / 0.000 | 0.000 / 0.000 | 0.000000 | 0.000000 | 0 / 0 |

## First-pass latency and total native message counts

| Component | Search bridge p50 / p95 / mean ms | Search plus all reads p50 / p95 / mean ms | Search + read payload tokens | Search + read content tokens |
| --- | --- | --- | --- | --- |
| baseline-component | 5.115633 / 8.522644 / 5.291498 | 5.115633 / 8.522644 / 5.291498 | 3983.523 / 4001.789 | 802.805 / 801.312 |
| candidate-component | 4.713320 / 8.395951 / 4.936638 | 4.713320 / 8.395951 / 4.936638 | 3983.527 / 4001.793 | 802.805 / 801.312 |
| claude-mem-fts | 16.217839 / 30.055988 / 17.041412 | 16.217839 / 30.055988 / 17.041412 | 1626.605 / 1612.273 | null |
| ai-memory-hybrid | 25.974992 / 33.288365 / 26.630384 | 30.291703 / 37.612844 / 30.924543 | 2837.508 / 2827.832 | 2558.676 / 2542.066 |
| billion-context | 0.756139 / 1.410491 / 0.875967 | 0.756139 / 1.410491 / 0.875967 | 585.664 / 579.328 | null |
| candidate-semantic-component | 13.895342 / 22.530175 / 14.659642 | 13.895342 / 22.530175 / 14.659642 | 4079.906 / 4099.117 | 819.117 / 817.766 |

## Common packed context, a separate surface

Each cell gives the mean tokens under the **same tokenizer that enforces that column's budget**. The JSON also retains the other reference encoding for every resulting context.

| Component | cl100k 512 | cl100k 1024 | cl100k 2048 | o200k 512 | o200k 1024 | o200k 2048 |
| --- | --- | --- | --- | --- | --- | --- |
| baseline-component | 450.520 | 712.867 | 713.605 | 447.309 | 706.203 | 706.941 |
| candidate-component | 450.520 | 712.867 | 713.605 | 447.309 | 706.203 | 706.941 |
| claude-mem-fts | 451.816 | 704.461 | 705.562 | 449.629 | 698.012 | 699.105 |
| ai-memory-hybrid | 452.031 | 704.039 | 704.773 | 451.641 | 697.668 | 698.402 |
| billion-context | 452.211 | 751.332 | 752.430 | 452.082 | 744.582 | 745.672 |
| candidate-semantic-component | 453.836 | 727.848 | 729.918 | 450.961 | 721.328 | 723.395 |

## Interpretation and reproducibility

- **native payload:** Stored canonical native JSON payload counts. Book, Bun/SQLite FTS, HTTP/MCP and Node return different native shapes; this is not one interchangeable whole-product interface or universal wire-envelope count.
- **native content:** Separately exposed native text content counts when available. Missing content remains null; it is never filled with zero or inferred by deleting payload fields.
- **reads:** Original per-query read_ms and read token counts already sum all declared native reads. This audit recomputes means from those stored sums; individual read timers and original text are not retained here and are not reconstructed.
- **combined latency:** For each first-pass query, bridge_ms + read_ms; then linear-interpolated p50/p95 and arithmetic mean. Percentiles are never added to each other.
- **common context:** Whole-block evidence context after the shared supplied-source packer, at each declared budget and tokenizer. It is neither native content nor native payload and must not substitute for either cost.
- **zero and null:** Zero reads means no extra read calls in this registered component policy, not a claim of a free or supported native feature. Null means the text-only surface was not available for an all-query mean.
- **billing:** Reference-encoding counts of these surfaces; no provider billing, model prompt/history overhead or complete memory write/summarize/generate lifecycle claim.

The JSON records compressed, decompressed, summary and checkpoint hashes, the auditor hash, and the digest of the exact selected numeric records. The auditor verifies local input bytes against their Git blobs at the supplied results commit. Policy strings are retained in original reports; all numerical `native_costs` fields, first-pass combined latency and context means are independently recomputed.

### Exact native text surfaces

The [frozen component producer](https://github.com/Afloat16/AI-Memory-Book/blob/057b814ab809dec57d4fa4c75fe540d59a0f0027/benchmarks/round2_eval.py)
sets Book's native text to the original `book.recall(..., budget_chars=100000)`
context before the shared whole-block packer. Its native JSON payload is the
complete direct Python recall result. These are separate from the default
compact MCP response and from the 512/1024/2048-token shared contexts above.

The [ai-memory adapter](https://github.com/Afloat16/AI-Memory-Book/blob/057b814ab809dec57d4fa4c75fe540d59a0f0027/benchmarks/competitors/ai_memory.py)
preserves the native MCP result envelope as payload and the joined native MCP
text-content string as content. That string can itself contain JSON and metadata;
it is not a count of bare document-body characters or tokens. The policy reads
every mapped top-five page on the first pass. Its mean 4.9765625 reads/query is
measured, not an assumed five reads for every query.

The [claude-mem bridge](https://github.com/Afloat16/AI-Memory-Book/blob/057b814ab809dec57d4fa4c75fe540d59a0f0027/benchmarks/competitors/claude_mem_bridge.ts)
returns the native observation-row array, and the
[billion bridge](https://github.com/Afloat16/AI-Memory-Book/blob/057b814ab809dec57d4fa4c75fe540d59a0f0027/benchmarks/competitors/billion_bridge.mjs)
returns native search rows. Neither exposes a separate `native_text` field in
this measurement, so their content means remain `null`. All six components'
first-pass metadata-hit counts are genuinely zero in this run; the counter and
the policy for preserving a native metadata slot remain present.

### Reproduce the independent aggregation

Use the [saved auditor](https://github.com/Afloat16/AI-Memory-Book/blob/d82a4229a0eafc5e653420f7195c5c88d897ea8c/scripts/audit_round2_component_costs.py)
against a checkout containing the unchanged committed result files:

```sh
python scripts/audit_round2_component_costs.py \
  --repository-root . \
  --checkpoint benchmarks/reports/round2-43207732852-1-checkpoint.json \
  --results-commit 057b814ab809dec57d4fa4c75fe540d59a0f0027 \
  --output benchmarks/reports/round2-component-cost-audit-new.json
```

Existing output paths are rejected. This command reads saved numeric records;
it does not start an upstream application, issue any query or call a model.

