# v0.3.1 performance and startup resource review

**Accept the retrieval optimization with an explicitly retained startup cost.** The original automatic report remains `accepted=false`; its resource threshold required a separate review. This decision does not rewrite that outcome or any measurement.

The frozen run completed **47,320 calls, 16 workers and four balanced rounds**. All complete non-timing outputs, source/scope/budget invariants and the independent saved-row audit passed. Across ten cohort/configuration cells, the pooled-p95 geometric mean improves **11.36%**. The largest public native p95 improvement is **26.05%**; no pooled p50 or p95 regresses by more than 5%.

## All pooled cells

Negative changes are faster. Timings are from the same formal host; they are not a cross-product or cold-cache comparison.

| Cohort | Configuration | Baseline p95 ms | Candidate p95 ms | p95 change | p50 change |
|---|---|---:|---:|---:|---:|
| synthetic61 | native-char4000 | 13.501 | 12.843 | -4.87% | -3.25% |
| synthetic61 | mcp-char4000 | 16.012 | 15.424 | -3.68% | -1.62% |
| synthetic61 | native-token512 | 21.052 | 21.079 | +0.12% | -4.35% |
| synthetic61 | native-token1024 | 23.710 | 23.643 | -0.28% | -7.86% |
| synthetic61 | native-token2048 | 20.872 | 20.682 | -0.91% | -11.96% |
| public1015 | native-char4000 | 5.054 | 3.737 | -26.05% | -12.14% |
| public1015 | mcp-char4000 | 7.409 | 5.937 | -19.87% | -10.78% |
| public1015 | native-token512 | 7.620 | 6.408 | -15.90% | -7.30% |
| public1015 | native-token1024 | 6.706 | 5.504 | -17.92% | -8.04% |
| public1015 | native-token2048 | 6.684 | 5.398 | -19.24% | -8.34% |

The synthetic 512-token p95 increases **0.125%**; that negative cell is retained. Public actual SDK/MCP p95 improves **19.87%**, while synthetic MCP improves **3.68%**.

## Explicit startup tradeoff

The one resource threshold crossing is public1015 empty-database opening: **34.4557 → 39.2941 ms mean, +4.8384 ms / +14.04%**. All four samples remain:

| Round | Baseline ms | Candidate ms | Change ms |
|---|---:|---:|---:|
| 0 | 30.283878 | 56.659038 | +26.375160 |
| 1 | 37.007871 | 33.518346 | -3.489525 |
| 2 | 38.258907 | 33.283959 | -4.974948 |
| 3 | 32.272222 | 33.715070 | +1.442848 |

The timed boundary is `MemoryBook(db_path, cache_size=0)` plus `__enter__` on a new, empty database, before ingestion or recall. Thirteen reproducible source/AST checks establish that the constructor, entry method, schema, triggers, constants and initialization dependencies are identical. The rowid optimization is in recall; the semantic telemetry change is in model construction.

The threshold is driven by the longer round-zero observation in an unchanged empty-database initialization path. The retrieval optimization and semantic model construction are outside that timed boundary. No per-SQL, scheduling or storage trace was recorded; the specific host cause is unknown.

Accept the observed +4.84 ms mean empty-database opening cost as an explicit tradeoff for verified retrieval improvements. Do not claim startup non-regression, discard any round, change the failed Actions conclusion, or replace the original accepted=false. This separate review does not make the original automatic gate pass.

An independent review confirmed the full sample set, code boundary and this limitation. Other recorded resource means increase by at most 0.72%. No startup-speed claim is made.

## Evidence and reproduction

- [Original formal run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43246417515)
- [Unmodified report and every worker](../benchmarks/reports/round3-performance-43246417515-1/)
- [Machine-readable separate review](../benchmarks/reports/round3-performance-resource-review.json)
- [Pre-registered protocol](../benchmarks/experiments/round3-plan.json)

```bash
python scripts/review_round3_startup.py
```

The command only reads committed source and saved summaries. It performs no retrieval, tokenization, model inference, or timing rerun. The original saved-row audit covers the full raw report and ledgers; this additional script checks input identities and the resource-review evidence.
