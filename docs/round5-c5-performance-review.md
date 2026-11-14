# v0.3.3 C5 formal performance review: pending independent audit

**Status: pending. No C5 performance acceptance or release approval is asserted.** This document is prepared for the sole registered hosted execution. Formal observations and decisions will be filled only after the complete saved result is available locally and the independent auditor has verified it. Every `pending` below is an unverified field, not a zero, a passing result or an omitted adverse observation.

The original [C3 rejection review](round5-performance-review.md) remains unchanged. Its failed public native and actual-MCP improvement gates are not replaced by C5 development observations.

## Frozen identities and evidence

| Role | Exact identity |
|---|---|
| Published v0.3.2 baseline commit | `692fb959ddf8934c5f516ba3d74ceb4385a2fa82` |
| Baseline runtime SHA-256 | `179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93` |
| Frozen C5 source commit | `8dc6604fa32df18d53286110b215fc6657243656` |
| C5 runtime SHA-256 | `6af876ef5ddc851f4fff56ba3dc4f20e76b2cfc9f5e31d0cc8d1a0ec20e954be` |
| Frozen C5 evaluator commit | `7852e26e582bdc9d5de2cc37e6c516c744c1c9aa` |
| Binding commit | `28b2f8923ad25643679ff17d9ee42c42abd70d67` |
| Binding SHA-256 | `bd395da21848cc01656ab45bc211a388b43b4ae63edb8690b2eabe2958d3781a` |
| Hosted run | [43552372788, attempt 1](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43552372788) |
| Result commit, timestamps and observed host | pending saved result |
| Independent audit result and script SHA-256 | pending independent audit |

The [original plan](../benchmarks/experiments/round5-plan.json), [C5 registration](../benchmarks/experiments/round5-c5-addendum.json), [C5 binding](../benchmarks/experiments/round5-c5-performance-binding.json) and [independent source review](../benchmarks/reports/round5-c5-source-review.json) identify the candidate and unmodified thresholds. The binding pins MCP 1.30.0, Pydantic 2.14.3 and tiktoken 0.12.0; actual host/package observations still require verification from the saved run.

The binding contains 42 evaluator input hashes. The independent audit must verify all of them against the bound Git objects, including the unchanged original C3 and C4 measurement files.

Expected result directory: `benchmarks/reports/round5-c5-performance-43552372788-1/`. Expected independent audit: `benchmarks/reports/round5-c5-performance-independent-audit.json`. These paths are targets, not claims that a completed result is already present.

## Matrix, timing and cold/warm boundaries

The registered formal matrix is **56,784 calls**, two complete old regression cohorts (168 synthetic and 1,015 public-conversation queries), six configurations and four balanced AB/BA/BA/AB rounds. Each worker is a fresh isolated process. Query order and source-pair membership remain fixed. Native character and actual-MCP character configurations use 4,000 characters; token configurations use `cl100k_base`, an 8,000-character ceiling, the named token cap and at most five results.

Native recall disables query-result caching with `cache_size=0` and `use_cache=False`. **C5 does enable a separate bounded exact-token-count memo.** Each MemoryBook starts without an allocated memo; character recall leaves it absent. The first native token configuration starts empty. Later native token1024 and token2048 configurations may reuse exact counts naturally retained on that same connection. First queries are included in the saved observations; no extra warmup or selective clearing is permitted.

The frozen evaluator's inherited wording **“Complete uncached API call”** refers to the disabled **query-result cache**. It must not be read as disabling C5's derived exact-count memo. The preregistration and recorded `native_token_count_memo` observations define that distinction; this review clarifies the wording without modifying the frozen evaluator or its saved fields.

Each actual official-SDK MCP configuration starts a **fresh server process**. Persistent query-result-cache entries are cleared outside the measured call, while the normal result-cache write, server work and SDK transport remain timed. The derived count memo may warm naturally across queries within that process. Its private counters are not exposed over MCP; native hit rates must not be presented as MCP hit rates. Actual MCP startup and child-process RSS remain measured. OS/SQLite cache warmth is not eliminated, so this is not a cold-storage benchmark and is not an experiment with every cache disabled.

Candidate memo bounds are shared across both registered tokenizers: **2,048 entries and 2,097,152 retained text-object bytes per MemoryBook**, charged after encoding. This text budget excludes mapping, key, value, encoder and other process allocations. The separate 4,096 KiB SQLite pager setting is connection-local and is not a whole-process memory cap. Native process RSS includes the evaluator, corpus, reference tokenizers and client imports; actual MCP child memory is measured separately.

Memo snapshots are taken before each native configuration, after its first completed retained query, and after the configuration, outside the recall timer. The independent audit must verify exact cross-configuration continuity, lazy empty starts, fixed bounds, first-query identity and nondecreasing cumulative counters.

## Complete-output and saved-record audit

The [independent auditor](../scripts/audit_round5_c5_performance.py) imports only the standard library. It checks committed source/evaluator/registration objects and complete saved reports/ledgers, and independently recomputes every numerical gate. The planned audit does not execute retrieval, tokenizer/model calls, tests or new timing. No completed audit is claimed yet.

| Check | Registered expected count | Independently observed |
|---|---:|---|
| Workers | 16 | pending |
| Pooled cohort/configuration cells | 12 | pending |
| Timed calls | 56,784 | pending |
| Start/finish ledger events | 113,568 | pending |
| Baseline/candidate complete output pairs | 28,392 | pending |
| Unique query/configuration combinations | 7,098 | pending |
| Native/actual-MCP provenance pairs | 18,928 | pending |
| Complete stable-output differences | must be 0 | pending |
| Source/scope/budget/cache invariant failures | must be 0 | pending |
| Negative, zero or nonfinite timing samples | must be 0 | pending |

The comparison excludes only the native payload's `latency_ms`. Scores, candidate counts, truncation, context, source references, metadata, MCP response/envelope digests and recorded invariants remain checked. A saved-digest/ledger audit does not rerun source reconstruction or tokenization; its output must preserve that evidence boundary.

## All twelve pooled latency cells

**Formal values pending independent audit.** Each synthetic cell should contain 672 observations per source and each public cell 4,060. Percentiles use linear interpolation at `(N - 1) * quantile` over all saved round samples; averaging round percentiles is not equivalent. Negative changes indicate lower latency. Acceptance uses unrounded values.

| Corpus | Configuration | Baseline p50, ms | C5 p50, ms | p50 change | Baseline p95, ms | C5 p95, ms | p95 change | Baseline mean, ms | C5 mean, ms | Mean change |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| synthetic61 | native-char4000 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| synthetic61 | mcp-char4000 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| synthetic61 | native-token512 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| synthetic61 | native-token1024 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| synthetic61 | native-token2048 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| synthetic61 | mcp-token1024 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| public1015 | native-char4000 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| public1015 | mcp-char4000 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| public1015 | native-token512 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| public1015 | native-token1024 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| public1015 | native-token2048 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| public1015 | mcp-token1024 | pending | pending | pending | pending | pending | pending | pending | pending | pending |

## Unchanged gates and decision

For all twelve cells, let `r_i = C5 pooled p95_i / baseline pooled p95_i`. The aggregate remains `100 * (1 - exp(sum(log(r_i)) / 12))`, with equal weight per cell. A public p50 gain does not satisfy the public p95 gate, and native speed does not substitute for actual-MCP speed.

| Registered gate | Formal observation | Decision |
|---|---|---|
| Complete stable output equal; zero invariant failures | pending | pending |
| Aggregate pooled p95 improvement at least 10% | pending | pending |
| At least one public native token p95 improvement at least 15% | pending | pending |
| Public actual-MCP token1024 p95 improvement at least 10% | pending | pending |
| No pooled p50/p95 regression greater than 5% | pending | pending |
| Every resource-mean increase greater than 10% independently reviewed | pending | pending |

`numeric_gate_passed`, the original evaluator `accepted` field, resource triggers and any independent resource decision must be reported separately. A resource review cannot waive a failed numerical gate or replace the original report's fields. Publication additionally requires the exact final-source CI and release checks.

## All 48 round-level cells

**Formal values pending independent audit.** Round 0 is AB, rounds 1 and 2 are BA, and round 3 is AB. Each round retains all 168 or 1,015 observations per source/configuration. Report every p50, p95 and mean, including all positive changes.

### synthetic61

| Round | Configuration | Baseline p50, ms | C5 p50, ms | p50 change | Baseline p95, ms | C5 p95, ms | p95 change | Baseline mean, ms | C5 mean, ms | Mean change |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | native-char4000 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 0 | mcp-char4000 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 0 | native-token512 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 0 | native-token1024 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 0 | native-token2048 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 0 | mcp-token1024 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 1 | native-char4000 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 1 | mcp-char4000 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 1 | native-token512 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 1 | native-token1024 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 1 | native-token2048 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 1 | mcp-token1024 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 2 | native-char4000 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 2 | mcp-char4000 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 2 | native-token512 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 2 | native-token1024 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 2 | native-token2048 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 2 | mcp-token1024 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 3 | native-char4000 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 3 | mcp-char4000 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 3 | native-token512 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 3 | native-token1024 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 3 | native-token2048 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 3 | mcp-token1024 | pending | pending | pending | pending | pending | pending | pending | pending | pending |

### public1015

| Round | Configuration | Baseline p50, ms | C5 p50, ms | p50 change | Baseline p95, ms | C5 p95, ms | p95 change | Baseline mean, ms | C5 mean, ms | Mean change |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | native-char4000 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 0 | mcp-char4000 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 0 | native-token512 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 0 | native-token1024 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 0 | native-token2048 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 0 | mcp-token1024 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 1 | native-char4000 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 1 | mcp-char4000 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 1 | native-token512 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 1 | native-token1024 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 1 | native-token2048 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 1 | mcp-token1024 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 2 | native-char4000 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 2 | mcp-char4000 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 2 | native-token512 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 2 | native-token1024 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 2 | native-token2048 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 2 | mcp-token1024 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 3 | native-char4000 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 3 | mcp-char4000 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 3 | native-token512 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 3 | native-token1024 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 3 | native-token2048 | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 3 | mcp-token1024 | pending | pending | pending | pending | pending | pending | pending | pending | pending |

## All 28 resource-mean comparisons

**Formal values and triggers pending independent audit.** Four samples per source/cohort are required for each metric. The original trigger is a mean increase **greater than 10%**, not a p95 increase. Every mean comparison remains in the review; triggers require a specific cause, practical impact, supporting evidence and an explicit independent decision. Byte values use 1,048,576 bytes per MiB. Neither a small mean change nor an unchanged OS high-water value proves that an added cache has zero memory cost.

### synthetic61 resource means

| Metric | Unit | Baseline mean | C5 mean | Change | >10% trigger |
|---|---|---:|---:|---:|---|
| Runtime import | ms | pending | pending | pending | pending |
| Native opening | ms | pending | pending | pending | pending |
| Fresh ingestion | ms | pending | pending | pending | pending |
| Unchanged replay | ms | pending | pending | pending | pending |
| Character MCP startup to initialization | ms | pending | pending | pending | pending |
| Native RSS after ingestion | MiB | pending | pending | pending | pending |
| Native high-water after ingestion | MiB | pending | pending | pending | pending |
| Native RSS after calls | MiB | pending | pending | pending | pending |
| Native high-water after calls | MiB | pending | pending | pending | pending |
| Character MCP child RSS after calls | MiB | pending | pending | pending | pending |
| Character MCP child high-water after calls | MiB | pending | pending | pending | pending |
| Token MCP startup to initialization | ms | pending | pending | pending | pending |
| Token MCP child RSS after calls | MiB | pending | pending | pending | pending |
| Token MCP child high-water after calls | MiB | pending | pending | pending | pending |

### public1015 resource means

| Metric | Unit | Baseline mean | C5 mean | Change | >10% trigger |
|---|---|---:|---:|---:|---|
| Runtime import | ms | pending | pending | pending | pending |
| Native opening | ms | pending | pending | pending | pending |
| Fresh ingestion | ms | pending | pending | pending | pending |
| Unchanged replay | ms | pending | pending | pending | pending |
| Character MCP startup to initialization | ms | pending | pending | pending | pending |
| Native RSS after ingestion | MiB | pending | pending | pending | pending |
| Native high-water after ingestion | MiB | pending | pending | pending | pending |
| Native RSS after calls | MiB | pending | pending | pending | pending |
| Native high-water after calls | MiB | pending | pending | pending | pending |
| Character MCP child RSS after calls | MiB | pending | pending | pending | pending |
| Character MCP child high-water after calls | MiB | pending | pending | pending | pending |
| Token MCP startup to initialization | ms | pending | pending | pending | pending |
| Token MCP child RSS after calls | MiB | pending | pending | pending | pending |
| Token MCP child high-water after calls | MiB | pending | pending | pending | pending |

### Resource decisions

Pending. For every trigger, retain the exact canonical metric path, all four baseline and candidate observations, unrounded mean change and independent assessment. Do not mark any trigger accepted merely because the speed gates pass. If no metric triggers review, say so only after recomputing all 28 comparisons.

## Native memo diagnostics

**Observed values pending independent audit.** There should be 32 candidate native configuration records across eight fresh candidate workers, with before/after-first-call/after snapshots. The eight baseline workers must explicitly report memo counters as unavailable; their missing implementation must not be represented as zero hits.

The final tables will retain every candidate worker/configuration, first query identity, start/end allocation and retained entries/bytes, first-call hit/miss deltas, total hit/miss deltas, evictions, invalidations, oversized bypasses and uncertified bypasses. The complete three snapshots remain in the independent audit JSON. Later native token configurations are naturally warm when retained entries are present; their first query is not described as a cold-cache query.

| Round | Corpus | Configuration | Start entries / bytes | After first call entries / bytes | End entries / bytes | First call hits / misses | All calls hits / misses | Evictions / invalidations | Oversized / uncertified bypasses |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | synthetic61 | native-char4000 | pending | pending | pending | pending | pending | pending | pending |
| 0 | synthetic61 | native-token512 | pending | pending | pending | pending | pending | pending | pending |
| 0 | synthetic61 | native-token1024 | pending | pending | pending | pending | pending | pending | pending |
| 0 | synthetic61 | native-token2048 | pending | pending | pending | pending | pending | pending | pending |
| 0 | public1015 | native-char4000 | pending | pending | pending | pending | pending | pending | pending |
| 0 | public1015 | native-token512 | pending | pending | pending | pending | pending | pending | pending |
| 0 | public1015 | native-token1024 | pending | pending | pending | pending | pending | pending | pending |
| 0 | public1015 | native-token2048 | pending | pending | pending | pending | pending | pending | pending |
| 1 | synthetic61 | native-char4000 | pending | pending | pending | pending | pending | pending | pending |
| 1 | synthetic61 | native-token512 | pending | pending | pending | pending | pending | pending | pending |
| 1 | synthetic61 | native-token1024 | pending | pending | pending | pending | pending | pending | pending |
| 1 | synthetic61 | native-token2048 | pending | pending | pending | pending | pending | pending | pending |
| 1 | public1015 | native-char4000 | pending | pending | pending | pending | pending | pending | pending |
| 1 | public1015 | native-token512 | pending | pending | pending | pending | pending | pending | pending |
| 1 | public1015 | native-token1024 | pending | pending | pending | pending | pending | pending | pending |
| 1 | public1015 | native-token2048 | pending | pending | pending | pending | pending | pending | pending |
| 2 | synthetic61 | native-char4000 | pending | pending | pending | pending | pending | pending | pending |
| 2 | synthetic61 | native-token512 | pending | pending | pending | pending | pending | pending | pending |
| 2 | synthetic61 | native-token1024 | pending | pending | pending | pending | pending | pending | pending |
| 2 | synthetic61 | native-token2048 | pending | pending | pending | pending | pending | pending | pending |
| 2 | public1015 | native-char4000 | pending | pending | pending | pending | pending | pending | pending |
| 2 | public1015 | native-token512 | pending | pending | pending | pending | pending | pending | pending |
| 2 | public1015 | native-token1024 | pending | pending | pending | pending | pending | pending | pending |
| 2 | public1015 | native-token2048 | pending | pending | pending | pending | pending | pending | pending |
| 3 | synthetic61 | native-char4000 | pending | pending | pending | pending | pending | pending | pending |
| 3 | synthetic61 | native-token512 | pending | pending | pending | pending | pending | pending | pending |
| 3 | synthetic61 | native-token1024 | pending | pending | pending | pending | pending | pending | pending |
| 3 | synthetic61 | native-token2048 | pending | pending | pending | pending | pending | pending | pending |
| 3 | public1015 | native-char4000 | pending | pending | pending | pending | pending | pending | pending |
| 3 | public1015 | native-token512 | pending | pending | pending | pending | pending | pending | pending |
| 3 | public1015 | native-token1024 | pending | pending | pending | pending | pending | pending | pending |
| 3 | public1015 | native-token2048 | pending | pending | pending | pending | pending | pending | pending |

## Every adverse observation

Pending. List every pooled positive p50/p95/mean change and every per-round positive p50/p95/mean change, even below the disallowed 5% pooled regression threshold. Resource triggers and logical storage increases are reported separately. Do not delete a slower round, first query, large allocation or failed gate, and do not repeat this frozen source to select a faster result.

## Logical database storage and other costs

Pending. Retain all three original logical-storage phases for both corpora: after ingestion while live, after MCP while live, and after checkpoint. Show baseline and candidate means in bytes, differences and percentage changes. Logical page count times page size is not an index-only allocation estimate; freelist reuse is not proof of a free index. Keep native and actual MCP RSS boundaries separate from the retained-text cap.

## Development history and correctness boundary

The complete [C5 development comparison](../benchmarks/reports/round5-development/candidate-c5-full/summary.json) retained 18,928 calls and 9,464 output pairs. Its best public native token p95 gain was 14.144746%, below the formal 15% requirement; a two-round native diagnostic does not predict that the hosted four-round result will pass and contains no actual-MCP evidence. The sole formal execution uses the original gates without a retry of the same source or a threshold change.

The earlier [C3 formal rejection](round5-performance-review.md) remains rejected, and [C4 development evidence](../benchmarks/reports/round5-development/candidate-c4-full/summary.json) is retained without a C4 formal acceptance claim.

The separately completed [C5 Hotpot256 compatibility check](../benchmarks/reports/round5-c5-hotpot-regression.summary.json) binds this same frozen C5 runtime and retains all 2,304 matches: 1,536 across both tokenizers and three token caps, plus 768 component outputs. Its [full report](../benchmarks/reports/round5-c5-hotpot-regression.json.gz) and [4,608 original events](../benchmarks/reports/round5-c5-hotpot-regression.attempts.jsonl.gz) show complete historical payload compatibility. This does not establish new-domain quality, Q2 results, new competitor performance or superiority across all product capabilities.

## Final decision and limits

**Pending saved formal result and independent audit.** No C5 release acceptance is currently derived from this document. The final review must state the exact numerical gate result, every resource-review decision, all adverse rows, the limits of one hosted machine and old regression queries, and the remaining CI/release requirements. It must not turn a successful point estimate into a statistical-significance or general hardware guarantee.

