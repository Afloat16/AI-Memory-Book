# Round-five final validation — NO candidate rejected

The frozen NO candidate completed all registered formal calls and passed the saved-result correctness audit. It **did not pass the original performance acceptance gates**. This is a complete adverse result, not an interrupted measurement to replay. Main remains at the previously accepted release; this document does not approve v0.3.3 publication.

## Exact version and evidence

| Item | Identity |
|---|---|
| Released baseline | v0.3.2, `692fb959ddf8934c5f516ba3d74ceb4385a2fa82` |
| Frozen NO candidate | `4a0ad4dc6aec33a91231d419239b7e90b160c695` |
| Candidate runtime SHA256 | `77310a7971677c2cebf8cd01d0aa36ab4562b55d1a3826b7fa7de895840abb32` |
| Formal launch | `cfe8a749efa4add1c62c516aa299ab18ee89b92c` |
| Formal run / attempt | [43496488712](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43496488712), first attempt |
| Complete result commit | `762500920d715b5bca6e1eba9314d8a4c970bf04` |
| Saved correctness | 16 workers, 66,248 timed calls, no validation issues |
| Saved audit | Success; measurement step exited3 because acceptance failed |

The exact [formal summary](../benchmarks/reports/round5-performance-v2-43496488712-1/report.summary.json), [completion record](../benchmarks/reports/round5-performance-v2-43496488712-1/completion.json), and [complete job log](../benchmarks/reports/round5-performance-v2-43496488712-1/run43496488712-job132130828952.log) are preserved. The job also ran148 registered measurement/runtime fixtures successfully. Original raw worker outputs, all ledgers and per-worker remote claims remain on the immutable [result commit](https://github.com/Afloat16/AI-Memory-Book/tree/762500920d715b5bca6e1eba9314d8a4c970bf04/benchmarks/reports/round5-performance-v2-43496488712-1).

The source choice was fixed before this run. It is not changed after seeing these results. No unfavorable sample, round, cell or resource observation is removed.

## Original numerical gates

| Gate | Required | Observed | Result |
|---|---:|---:|---|
| Geometric mean of14 pooled p95 ratios | At least10% improvement | 4.239507% improvement | Fail |
| Public native char4000 p95 | At least10% improvement | 7.987988% improvement | Fail |
| Public actual-SDK MCP char4000 p95 | At least5% improvement | 0.374289% improvement | Fail |
| Every pooled cell p50 and p95 | No regression above5% | Public MCP token1024 p95 +10.585735% | Fail |

The original plan and arithmetic are unchanged. Each cell pools all four registered rounds on the same VM. The overall number gives equal weight to14 cell p95 ratios; it is not a weighted average of all call latencies or a universal product-speed claim.

## Every formal cell

P95 values below are milliseconds. Negative changes mean faster; positive changes mean slower. Full-precision individual timings and per-round summaries are retained.

| Cohort | Configuration | Baseline p95 ms | NO p95 ms | p95 change | p50 change |
|---|---|---:|---:|---:|---:|
| synthetic61 | native-char4000 | 11.380354 | 10.947897 | -3.8000% | -6.5375% |
| synthetic61 | native-char100000 | 8.050075 | 7.545055 | -6.2735% | -7.7212% |
| synthetic61 | mcp-char4000 | 12.887571 | 13.118411 | +1.7912% | +0.7567% |
| synthetic61 | native-token512 | 16.753250 | 14.727207 | -12.0934% | -6.8550% |
| synthetic61 | native-token1024 | 17.439585 | 15.515451 | -11.0331% | -7.4300% |
| synthetic61 | native-token2048 | 14.897791 | 13.385543 | -10.1508% | -6.9173% |
| synthetic61 | mcp-token1024 | 19.811860 | 17.414628 | -12.1000% | -6.5584% |
| public1015 | native-char4000 | 3.284116 | 3.021781 | -7.9880% | -8.5700% |
| public1015 | native-char100000 | 3.201211 | 2.970703 | -7.2006% | -8.4379% |
| public1015 | mcp-char4000 | 5.290884 | 5.271081 | -0.3743% | -0.9461% |
| public1015 | native-token512 | 4.394010 | 4.459132 | +1.4821% | -0.2948% |
| public1015 | native-token1024 | 3.871651 | 3.877688 | +0.1559% | -3.3190% |
| public1015 | native-token2048 | 3.854567 | 3.877561 | +0.5965% | -5.5013% |
| public1015 | mcp-token1024 | 5.671159 | 6.271492 | +10.5857% | -3.4086% |

This result contains13 improved pooled p50 cells and9 improved pooled p95 cells, but these counts do not replace the failed gates. In particular, the complete public MCP token1024 distribution must retain its last-round adverse observation; no round is dropped or averaged away to produce a pass.

The earlier development result was a different fixed8-cell/128-query-per-cohort protocol:4,096 calls,2,048 paired full-payload digests,11.226438% geometric p95 improvement and8.762968% public native char4000 improvement. Those development numbers are retained in their [original independent audit](../benchmarks/reports/round5-candidate-no-development-1/independent-raw-audit.json). They are not added to, substituted for, or pooled with this larger formal run.

## Resource and initialization costs

[Independent resource and storage review](../benchmarks/reports/round5-performance-v2-43496488712-1/independent-resource-storage-audit.json) recomputed all28 original resource comparisons and364 statistics from the saved raw worker resource fields. Every value matched the stored summary. Both original resource-review flags remain:

| Cohort | Baseline import mean ms | NO import mean ms | Increase ms | Increase percent |
|---|---:|---:|---:|---:|
| synthetic61 | 23.37163925 | 30.50532175 | 7.13368250 | 30.52281624% |
| public1015 | 23.61475650 | 30.14186075 | 6.52710425 | 27.63993882% |

All eight paired import observations increased. Static source review identifies additional module-level regex compilation, fixed mapping and identity initialization, and larger imported source. It does not assign the full extra duration to any one operation. No resource exception has been accepted.

All64 storage snapshots across the four distinct boundaries were present. All256 byte values matched between corresponding baseline and candidate snapshots, and all four rounds matched within each cohort/boundary. The top-level char-MCP storage alias is not counted as a fifth boundary. Database-open outliers remain in the resource records; their effect on means is not presented as a reliable product opening-speed improvement.

The source-free interface certificate independently preserves the old tool/schema projection and instructions after removing only the approved optional `follow_titles=false` increment. The added tool-schema cost is **72 tokens under each of cl100k_base and o200k_base**, with no instruction-token change. This cost is retained separately from retrieval token budgets.

## Evidence transport and remaining audits

Some original gzip artifacts exceed the connector's1MiB file-content boundary. A separately reviewed source-free [transport run43500798881](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43500798881) exported the exact compressed Git bytes without decompression, runtime imports or another retrieval call. All17 large inputs were checked against their original Git blob, size and completion SHA256 before export. They were saved as70 contiguous base64 text chunks containing28,485,017 original compressed bytes at [transport commit860aa4c](https://github.com/Afloat16/AI-Memory-Book/tree/860aa4c7d30a0914e769d64b811c02bcbed763a3/benchmarks/reports/round5-formal-evidence-transport-1). Each original file has an intent and outcome Git checkpoint. These are transport copies, not new measurements.

Independent full worker/ledger arithmetic and payload audit is in progress. The independent resource review explicitly awaits that audit's raw-worker-to-summary projection linkage. The saved hosted audit has already completed, but the two verification boundaries are not conflated.

The separate historical lexical run43497150881 completed5,120 calls/2,560 full saved-payload pairs and passed its original audit. Independent raw verification reports the same complete matrix, with char100000 pooled p50 -3.885544% and p95 -4.933982%; the small round2 p95 regression is retained. Its final independent report is being archived.

Historical Q2 attempt1 stopped before any asset download, build or query: the controller omitted an unchanged explicitly registered file from its import-derived identity map. The complete failure and [independent root cause](../benchmarks/reports/round5-q2-preclaim-registration-independent-review.json) are preserved. A separately registered attempt2 strengthens the check to all35 paths in the union, preserves all original model/vector/payload gates, and is undergoing final source review. It does not change the failed formal candidate or its result.

No new fresh cohort metadata, query IDs or content has been selected or read. The fresh/comparator gate remains closed for this rejected candidate. Therefore this round establishes **no new cross-repository superiority claim**, and no unmeasured fresh-quality gain is reported.

## Decision

The candidate remains unaccepted for release. Main, release tag and public package are not advanced by this result. The completed negative run stays immutable, and any later candidate requires a separately declared development and validation scope, with explicit attention to import work and end-to-end MCP behavior. The [recovery entry](round5-current-state-20261113.json) identifies all exact commits and active work so interrupted sessions can resume without replaying measurements.
