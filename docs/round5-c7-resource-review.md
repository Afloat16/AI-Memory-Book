# C7 startup resource review

**Independent recommendation: accept the three disclosed startup tradeoffs for frozen C7.** This resolves the resource-review requirement only. The original automatic `accepted: false`, three flags and failed measurement-job status remain unchanged. The original numerical retrieval gate passed. Full result audits, exact-commit CI, packaging and publication are separate gates.

Review date: **2026-11-14 (Asia/Shanghai)**. No new retrieval, startup test or timing sample was run for this review.

## Decision basis and immutable evidence

The [original round-five plan](../benchmarks/experiments/round5-plan.json) requires explicit cause assessment and independent review whenever a recorded resource mean rises by more than 10%. It does not authorize changing the threshold or deleting samples. This review accepts the original observed costs, with their limitations, under that registered review rule.

Run [43563390252, attempt 1](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43563390252) completed all **56,784 calls and 16 workers**. The [saved raw report](../benchmarks/reports/round5-c7-performance-43563390252-1/report.json.gz) and [summary](../benchmarks/reports/round5-c7-performance-43563390252-1/report.summary.json) are retained at result commit `03838687f7d8d5995c2afa4c22ff5c30e7b12750`. The reviewer checked both against that Git commit, all 16 saved worker objects, every resource mean, and all original samples below.

- Baseline: `692fb959ddf8934c5f516ba3d74ceb4385a2fa82`, runtime SHA256 `179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93`.
- Candidate: `d0c84cbfc9bad440ad447d41e211d070ef5b2cae`, runtime SHA256 `55529a217e6dcf6af0c81639cfc0e88b3ea94c39e6911f659fcfb7543e853d45`.
- Raw compressed report SHA256: `156087043702b5f223f898800547c576f469ac780066b0af431227cfeda66b25`.
- Summary SHA256: `16af31606dcfcbd2a443b56bf4ec9c0aa0f0bf89da8de5811c07fb7d924c4262`.
- Machine-readable independent review: [round5-c7-resource-independent-review.json](../benchmarks/reports/round5-c7-resource-independent-review.json).

The original numerical results remain: **14.797576%** pooled-p95 geometric-mean improvement, **15.740557%** best public native-token p95 improvement, **12.173438%** public actual-SDK MCP token1024 p95 improvement, and no pooled p50/p95 regression beyond 5%. These satisfy the original 10% / 15% / 10% requirements. They do not make the startup regressions disappear.

## The three original flags

All times below are milliseconds. Each mean has four observations; no outlier is removed and no source/cohort is pooled with another to resolve a flag.

| Cohort | Metric | Baseline mean ms | Candidate mean ms | Absolute increase ms | Relative increase |
|---|---|---:|---:|---:|---:|
| synthetic61 | `runtime_import_ms` | 27.89452125 | 31.09176525 | +3.197244000 | +11.461907% |
| public1015 | `runtime_import_ms` | 27.76485525 | 30.755210 | +2.990354750 | +10.770288% |
| public1015 | `native_open_ms` | 23.82188725 | 28.92236675 | +5.100479500 | +21.410896% |

### synthetic61 — `runtime_import_ms`

| Round | Baseline ms | Candidate ms | Candidate minus baseline ms |
|---|---:|---:|---:|
| 0 | 28.189789 | 31.749188 | +3.559399 |
| 1 | 27.732217 | 30.849470 | +3.117253 |
| 2 | 28.119725 | 31.097510 | +2.977785 |
| 3 | 27.536354 | 30.670893 | +3.134539 |

### public1015 — `runtime_import_ms`

| Round | Baseline ms | Candidate ms | Candidate minus baseline ms |
|---|---:|---:|---:|
| 0 | 28.134701 | 30.899379 | +2.764678 |
| 1 | 27.847884 | 30.980737 | +3.132853 |
| 2 | 27.579635 | 30.920366 | +3.340731 |
| 3 | 27.497201 | 30.220358 | +2.723157 |

### public1015 — `native_open_ms`

| Round | Baseline ms | Candidate ms | Candidate minus baseline ms |
|---|---:|---:|---:|
| 0 | 23.103435 | 28.614300 | +5.510865 |
| 1 | 25.172806 | 39.683334 | +14.510528 |
| 2 | 22.757635 | 22.066283 | -0.691352 |
| 3 | 24.253673 | 25.325550 | +1.071877 |

The public round-one candidate open of **39.683334 ms**, including its **+14.510528 ms** paired difference, remains in the mean and distribution. The negative round-two difference also remains. Neither is a replacement estimate of the other rounds.

## Cause assessment: native runtime import

The frozen evaluator times `import memory_book` and `from memory_book import MemoryBook` before dataset loading. The package imports `store`, which imports `segmentation` and `text`. **Neither `mcp_server` nor `token_budget` has been imported by this product path at that point.** The C7 stdout adapter is therefore not an explanation for this native-import interval, and tokenizer encoding/memo lookup does not run in it. The interval is not a full interpreter-launch or end-user application-start measurement. [Evaluator](../scripts/round5_c7_performance.py) · [Package entry](../src/memory_book/__init__.py).

Compared with v0.3.2, `store.py` grows from **61,126 to 74,966 bytes** (+13,840); its AST grows from 8,931 to 10,925 nodes. Added functions, class methods and the ordinary-JSON-loader certificate introduce source compilation/definition and small initialization work. The fixed workflow creates fresh source worktrees and sets `PYTHONDONTWRITEBYTECODE=1`; `segmentation.py` and `text.py` are unchanged. C7's `store.py` is byte-identical to C6, so the candidate name does not imply that the new stdout edit caused this import increase. [Frozen source](https://github.com/Afloat16/AI-Memory-Book/blob/d0c84cbfc9bad440ad447d41e211d070ef5b2cae/src/memory_book/store.py) · [Workflow](../.github/workflows/round5-c7-performance.yml).

Every paired import observation is slower, by **2.723157–3.559399 ms**. Larger source/definition work is an identifiable and credible contributor, but the formal run has no compilation, CPU or module-stage trace. **This review does not assign all of the observed increase to compilation or quantify each contributor.**

The accepted user cost is the original **+3.197244 ms / +2.99035475 ms mean fresh-process import cost** in these two cohorts. It is paid when importing this runtime into a fresh native process, not on every recall in the same continuing process. Applications starting a new process for each operation may pay it more often. No universal import-speed or startup-non-regression claim is made.

## Cause assessment: fresh empty-database opening

`native_open_ms` surrounds `MemoryBook(new_path, cache_size=0)` and context entry **before ingestion**. Both cohort labels describe the data loaded later: the database is empty for this measurement. The +21.410896% flag is not evidence that a larger public corpus makes opening slower, and it is not a timed upgrade of an existing populated archive.

Compared with v0.3.2, the constructor adds the connection-local `PRAGMA cache_size=-4096`, the new `pages_recall_metadata` covering index inside `SCHEMA`, and a subsequent `CREATE INDEX IF NOT EXISTS` check. On a fresh archive the schema statement creates an **empty** index; it runs before the existing `journal_mode=WAL` and `synchronous=NORMAL` statements. The later index statement finds the index already created. Two added connection attributes retain `None` or an existing cache reference; the token-count memo is not allocated at opening. These are concrete setup changes in the frozen source, retained from the earlier round-five candidates. [Index registration](../benchmarks/experiments/round5-index-addendum.json) · [Pager registration](../benchmarks/experiments/round5-cache-addendum.json).

Extra SQL/schema setup is an identifiable source of work. The original measurement does not separate its CPU or storage cost from ordinary filesystem/scheduler waits, so **the +5.1004795 ms mean and 39.683334 ms sample are not assigned to a proved I/O event or a quantified index-only cost**. The sample is retained without being labeled a proven outlier.

The earlier [C3 populated-archive upgrade observation](../benchmarks/reports/round5-development/final-index-upgrade-review.json) records 200,704/151,552 bytes allocated to the same index and one warm-cache first-open observation per source/cohort. This establishes a separately disclosed upgrade/storage cost; it is **not C7 timing**, is not pooled with this run, and cannot replace the fresh-empty-archive flag. Zero file growth in those copied archives meant free pages were reused, not a free index.

The reviewer accepts the original **+5.1004795 ms mean new-archive creation cost**, with the full four-sample spread. It applies to first creation/setup, not each query. Existing-archive opens and future data sizes retain their own limits; the review establishes no worst-case upper bound on them.

## Other resource costs and practical tradeoff

All 25 remaining registered means are below the unchanged 10% review trigger. The largest other increase is **6.492167%** for synthetic native post-ingestion high-water memory. All memory observations are process RSS/HWM, including evaluator dependencies; they are not unique product allocations. The token memo's retained text budget is 2 MiB with at most 2,048 entries, plus container overhead; its cost is not zero.

Actual SDK initialization means across both cohorts and the two MCP settings change by **−0.286676% to +1.579351%**. Public token1024 startup is **540.3105195 → 538.76157825 ms**; public character startup is **547.18559225 → 552.80835975 ms**. These protocol-startup intervals already include process/import work and must not be added to standalone import numbers. The MCP connection opens its archive lazily at a tool call, so initialization is not the fresh-empty-database measurement.

The continuing memory-service workload can incur startup work once while benefiting from repeated retrieval. For example, the original public native token2048 p95 is **4.47828505 → 3.77337805 ms**, and actual MCP token1024 p95 is **6.7114132 → 5.8944035 ms**. These are the retained complete-call observations, not a newly timed amortization experiment. Short-lived applications and workloads frequently creating archives may value the startup tradeoff differently.

### All 28 original resource means

Timing fields are milliseconds; `.rss_bytes` and `.hwm_bytes` are bytes. Every field's original four baseline and four candidate values is retained in the machine-readable review, together with the complete original distribution.

| Cohort | Metric | Baseline mean | Candidate mean | Change | Review |
|---|---|---:|---:|---:|---|
| synthetic61 | `runtime_import_ms` | 27.894521250 | 31.091765250 | +11.461907% | Reviewed |
| synthetic61 | `native_open_ms` | 254.501598750 | 24.613843500 | -90.328609% | No trigger |
| synthetic61 | `fresh_ingestion_ms` | 859.723781750 | 853.093461000 | -0.771215% | No trigger |
| synthetic61 | `unchanged_reingestion_ms` | 104.861748000 | 104.164834750 | -0.664602% | No trigger |
| synthetic61 | `mcp_startup_to_initialize_ms` | 546.882848250 | 555.520048500 | +1.579351% | No trigger |
| synthetic61 | `native_memory_after_ingestion.rss_bytes` | 41517056.000000000 | 43760640.000000000 | +5.404006% | No trigger |
| synthetic61 | `native_memory_after_ingestion.hwm_bytes` | 41703424.000000000 | 44410880.000000000 | +6.492167% | No trigger |
| synthetic61 | `native_memory_after_calls.rss_bytes` | 199260160.000000000 | 203655168.000000000 | +2.205663% | No trigger |
| synthetic61 | `native_memory_after_calls.hwm_bytes` | 199260160.000000000 | 203655168.000000000 | +2.205663% | No trigger |
| synthetic61 | `mcp_server_memory_after_calls.rss_bytes` | 64428032.000000000 | 63703040.000000000 | -1.125274% | No trigger |
| synthetic61 | `mcp_server_memory_after_calls.hwm_bytes` | 64460800.000000000 | 63703040.000000000 | -1.175536% | No trigger |
| synthetic61 | `mcp_sessions.mcp-token1024.mcp_startup_to_initialize_ms` | 534.819922000 | 540.539963250 | +1.069527% | No trigger |
| synthetic61 | `mcp_sessions.mcp-token1024.mcp_server_memory_after_calls.rss_bytes` | 110572544.000000000 | 110776320.000000000 | +0.184292% | No trigger |
| synthetic61 | `mcp_sessions.mcp-token1024.mcp_server_memory_after_calls.hwm_bytes` | 110572544.000000000 | 110776320.000000000 | +0.184292% | No trigger |
| public1015 | `runtime_import_ms` | 27.764855250 | 30.755210000 | +10.770288% | Reviewed |
| public1015 | `native_open_ms` | 23.821887250 | 28.922366750 | +21.410896% | Reviewed |
| public1015 | `fresh_ingestion_ms` | 792.575261250 | 800.799995500 | +1.037723% | No trigger |
| public1015 | `unchanged_reingestion_ms` | 204.500809000 | 201.015741500 | -1.704183% | No trigger |
| public1015 | `mcp_startup_to_initialize_ms` | 547.185592250 | 552.808359750 | +1.027580% | No trigger |
| public1015 | `native_memory_after_ingestion.rss_bytes` | 44803072.000000000 | 46819328.000000000 | +4.500263% | No trigger |
| public1015 | `native_memory_after_ingestion.hwm_bytes` | 52830208.000000000 | 53645312.000000000 | +1.542875% | No trigger |
| public1015 | `native_memory_after_calls.rss_bytes` | 224233472.000000000 | 229137408.000000000 | +2.186978% | No trigger |
| public1015 | `native_memory_after_calls.hwm_bytes` | 224233472.000000000 | 229137408.000000000 | +2.186978% | No trigger |
| public1015 | `mcp_server_memory_after_calls.rss_bytes` | 63536128.000000000 | 63172608.000000000 | -0.572147% | No trigger |
| public1015 | `mcp_server_memory_after_calls.hwm_bytes` | 63536128.000000000 | 63172608.000000000 | -0.572147% | No trigger |
| public1015 | `mcp_sessions.mcp-token1024.mcp_startup_to_initialize_ms` | 540.310519500 | 538.761578250 | -0.286676% | No trigger |
| public1015 | `mcp_sessions.mcp-token1024.mcp_server_memory_after_calls.rss_bytes` | 109349888.000000000 | 109369344.000000000 | +0.017792% | No trigger |
| public1015 | `mcp_sessions.mcp-token1024.mcp_server_memory_after_calls.hwm_bytes` | 109349888.000000000 | 109369344.000000000 | +0.017792% | No trigger |

### Preserved large synthetic opening observation

Synthetic baseline round zero is **946.793415 ms**; the other baseline values are **22.422942 / 24.996153 / 23.793885 ms**. Candidate values are **25.130586 / 27.140976 / 22.560302 / 23.623510 ms**. The resulting original mean change of **−90.328609%** remains in the table. Its cause is unestablished. **It is not used as a speedup, compensating benefit or reason to accept the public startup regression.**

### Logical archive storage

The following values repeat in all four original rounds after checkpoint. They are separate from RSS and first-open costs.

| Cohort | Baseline bytes | Candidate bytes | Increase bytes | Change |
|---|---:|---:|---:|---:|
| synthetic61 | 20,508,672 | 20,733,952 | +225,280 | +1.098462% |
| public1015 | 12,881,920 | 13,053,952 | +172,032 | +1.335453% |

## Acceptance limits

This is an explicit engineering acceptance of the original three measured startup costs for the exact frozen source. It is not an automatic waiver, a newly passing resource measurement or proof of a complete causal decomposition. No threshold changed; no sample was removed, reweighted or replaced. Original `accepted: false` and the measurement-job failure remain readable; the separate resource decision is the only place where this review is applied.

There are four observations per source/cohort on one host. No significance, cold-OS guarantee, universal non-regression, answer-quality gain or all-dimensions competitor superiority follows. Prior C3/C5/C6 numerical rejections remain rejected. Publication still requires independent complete-result integrity and all existing release checks.
