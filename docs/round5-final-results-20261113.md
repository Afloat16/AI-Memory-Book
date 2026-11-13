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
| Saved audit | Success; measurement step exited 3 because acceptance failed |

The exact [formal summary](../benchmarks/reports/round5-performance-v2-43496488712-1/report.summary.json), [completion record](../benchmarks/reports/round5-performance-v2-43496488712-1/completion.json), and [complete job log](../benchmarks/reports/round5-performance-v2-43496488712-1/run43496488712-job132130828952.log) are preserved. The job also ran 148 registered measurement/runtime fixtures successfully. Original raw worker outputs, all ledgers and per-worker remote claims remain on the immutable [result commit](https://github.com/Afloat16/AI-Memory-Book/tree/762500920d715b5bca6e1eba9314d8a4c970bf04/benchmarks/reports/round5-performance-v2-43496488712-1).

The source choice was fixed before this run. It is not changed after seeing these results. No unfavorable sample, round, cell or resource observation is removed.

## Original numerical gates

| Gate | Required | Observed | Result |
|---|---:|---:|---|
| Geometric mean of 14 pooled p95 ratios | At least 10% improvement | 4.239507% improvement | Fail |
| Public native char4000 p95 | At least 10% improvement | 7.987988% improvement | Fail |
| Public actual-SDK MCP char4000 p95 | At least 5% improvement | 0.374289% improvement | Fail |
| Every pooled cell p50 and p95 | No regression above 5% | Public MCP token1024 p95 +10.585735% | Fail |

The original plan and arithmetic are unchanged. Each cell pools all four registered rounds on the same VM. The overall number gives equal weight to 14 cell p95 ratios; it is not a weighted average of all call latencies or a universal product-speed claim.

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

This result contains 13 improved pooled p50 cells and 9 improved pooled p95 cells, but these counts do not replace the failed gates. In particular, the complete public MCP token1024 distribution must retain its last-round adverse observation; no round is dropped or averaged away to produce a pass.

The earlier development result was a different fixed 8-cell/128-query-per-cohort protocol: 4,096 calls, 2,048 paired full-payload digests, 11.226438% geometric p95 improvement and 8.762968% public native char4000 improvement. Those development numbers are retained in their [original independent audit](../benchmarks/reports/round5-candidate-no-development-1/independent-raw-audit.json). They are not added to, substituted for, or pooled with this larger formal run.

## Resource and initialization costs

[Independent resource and storage review](../benchmarks/reports/round5-performance-v2-43496488712-1/independent-resource-storage-audit.json) recomputed all 28 original resource comparisons and 364 statistics from the saved raw worker resource fields. Every value matched the stored summary. Both original resource-review flags remain:

| Cohort | Baseline import mean ms | NO import mean ms | Increase ms | Increase percent |
|---|---:|---:|---:|---:|
| synthetic61 | 23.37163925 | 30.50532175 | 7.13368250 | 30.52281624% |
| public1015 | 23.61475650 | 30.14186075 | 6.52710425 | 27.63993882% |

All eight paired import observations increased. Static source review identifies additional module-level regex compilation, fixed mapping and identity initialization, and larger imported source. It does not assign the full extra duration to any one operation. No resource exception has been accepted.

All 64 storage snapshots across the four distinct boundaries were present. All 256 byte values matched between corresponding baseline and candidate snapshots, and all four rounds matched within each cohort/boundary. The top-level char-MCP storage alias is not counted as a fifth boundary. Database-open outliers remain in the resource records; their effect on means is not presented as a reliable product opening-speed improvement.

The source-free interface certificate independently preserves the old tool/schema projection and instructions after removing only the approved optional `follow_titles=false` increment. The added tool-schema cost is **72 tokens under each of cl100k_base and o200k_base**, with no instruction-token change. This cost is retained separately from retrieval token budgets.

## Evidence transport and completed independent audit

Some original gzip artifacts exceed the connector's 1 MiB file-content boundary. The separately reviewed, source-free [transport run 43500798881](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43500798881) exported the exact compressed Git bytes without runtime imports, decompression or another retrieval call. Its 17 large inputs were checked against the original Git blobs, sizes and completion SHA256 values before export. They were saved as 70 contiguous base64 text chunks containing 28,485,017 original compressed bytes at [transport commit 860aa4c](https://github.com/Afloat16/AI-Memory-Book/tree/860aa4c7d30a0914e769d64b811c02bcbed763a3/benchmarks/reports/round5-formal-evidence-transport-1). These are transport copies of the original measurements.

The [final independent primary-data audit](../benchmarks/reports/round5-formal-readonly-auditor/final-independent-audit.json), originally committed as `683ada59e86d8c63c19ece27c958ab5bc01649db`, is complete:

| Independent check | Result |
|---|---|
| Original worker results and complete ledgers | All 16 worker gzip files and 16 ledger gzip files verified |
| Calls / ledger events | 66,248 / 132,496, complete |
| Baseline/candidate full non-timing result pairs | 33,124 pairs, zero differences |
| Paired recorded order and cross-round consistency | All 14 cells and 4 rounds verified |
| Complete worker content excluding configurations | All 16 projections equal the original summary |
| Independent derived statistics and declarations | 1,186 values compared; maximum absolute difference 0 |
| Original numerical acceptance | Failure reproduced without changing any gate |

The first independent recomputation recorded one metadata false positive: it expected the aggregate status to be `completed`. The fixed producer writes `measurements_completed`; the separate completion file uses `completed`. The [source-based adjudication](../benchmarks/reports/round5-formal-readonly-auditor/aggregate-status-adjudication.json) preserves the frozen auditor and first false-positive report and resolves only that incorrect assumption. It changes no timing, arithmetic, threshold or product source.

The independent input coverage is precise: 48 chunks reassembled all 16 large primary worker/ledger files; another 16 smaller gzip inputs were read directly. The redundant 10,132,375-byte aggregate `report.json.gz` was not independently decompressed a second time, and its 22 exported chunks were not independently read. The original hosted audit's aggregate check remains part of the saved execution record. This independent audit directly covers every primary worker/ledger and all summary projections and derived statistics. It also does not claim a second tokenizer execution or a second implementation of Python's seeded shuffle.

The [resource cross-link](../benchmarks/reports/round5-performance-v2-43496488712-1/independent-resource-storage-raw-cross-link.json) independently matches all 16 raw-worker header hashes to the prior resource review. That closes its pending provenance check. Both import-cost flags and the numerical rejection remain unchanged.

## Historical compatibility results

### Lexical compatibility passed

The separate [historical lexical run 43497150881](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43497150881) completed 5,120 calls and 2,560 full saved-payload pairs. Its [independent raw audit](../benchmarks/reports/round5-lexical-compat-hosted-1-independent-raw-audit.json), originally committed as `20f968439942336a8d5c385b4dbb7c2178323bef`, verified all 10 worker reports, 10 complete ledgers, 10,240 events and the actual Git checkpoint chain.

The historical char100000 configuration improved pooled p50 by 3.885544% and p95 by 4.933982%. Its round 2 p95 regression of 2.254453% is retained. This historical result is separate from the formal 14-cell matrix and does not replace the failed release gates.

### Q2 reconstruction stopped before query workers

Both Q2 attempts are terminal and preserved:

| Attempt | Run | Actual terminal boundary | Query calls |
|---|---|---|---:|
| 1 | [43497153581](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43497153581) | Source-registration failure before claim/assets/build: one unchanged, explicitly registered helper was absent from the import-derived identity map | 0 |
| 2 | [43505846977](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43505846977) | First authored36 snapshot built once; subsequent sidecar assertion refused the snapshot before query workers | 0 |

Attempt2 source `c23c5d5c9e1b8521ed78bf28e34896bc0755ee86` strengthened the preclaim check to the complete 35-file union while preserving all original operational gates. Its 20 source/protocol fixtures, real 35-file check and general 9-job CI passed. Root and a separate reviewer accepted only that exact implementation and launch; they did not pre-accept its result.

The actual attempt2 result is `14e2432adbf519d2cccabc038e4e1f0e9d805279`. Its [failure record](../benchmarks/reports/round5-q2-recovery-hosted-2/failure.json), all 12 original result files, [complete log and independent failure audit](../benchmarks/reports/round5-q2-recovery-hosted-2-independent-audit/final-failure-audit.json), and 8 actual Git parent checkpoints are retained. The preparation child exited 0 after one 42-window page-vector index build. The hotpot128 preparation and all 8 query workers never started. Zero retrieval calls therefore does not imply zero model computation in this attempt.

The actual exception was `New prepared database has a sidecar`. Exact source lines 614–620 first call the database identity reader, then check for `-wal`, `-shm` or `-journal`, and only afterward would record the returned identity and validate preparation. The reader was closed before the sidecar check, but no before-reader sidecar inventory, suffix or size was saved. The sidecar's origin cannot be determined from this record. The [root review](../benchmarks/reports/round5-q2-recovery-hosted-2-independent-audit/root-failure-review.json) also corrects one report-only source-line typo from 515 to 615; the original report and all outcomes remain intact.

A separate read-only comparison found that the builder's saved vector-table composite digest is `976cf1e7ec9df5a05d7bc4a19357d6107e7d63faf8825b1af68f5eab914eccf5`, while the registered historical digest is `c1cecaacdf47d7db3a790e46589a03e3d895aabbe7fb4069a65c050f7efd0a2e`. The other vector identity fields match: 42 rows, 64,512 bytes, revision 42 and the same model fingerprint. Non-timing semantic-index metadata also matches. The full composite identity nevertheless differs.

That hash includes ordered row IDs, ordinals, character offsets, lengths and exact vector BLOB bytes. It does not isolate numerical vector errors, identify the changed row/field or establish a CPU, ONNX, floating-point or timestamp cause. The actual run stopped before reaching this vector gate; the preserved preparation receipt independently fails the unchanged historical identity predicate. Clearing a sidecar would not establish the other required equality.

The planned 1,968-call / 984-pair Q2 matrix was not executed. No compatibility pass is inferred, no lost original SQLite snapshot is claimed to have been restored, and no cleanup, vector rebuild, retry or threshold relaxation followed.

## Decision and subsequent work boundary

**This candidate is not accepted for release.** Main, tag and public release remain at the previously accepted version. Formal and lexical measurements, their complete independent audits, and both Q2 failures are now closed records.

No fresh cohort metadata, query IDs or content has been selected or read. The fresh/comparator gate remains closed for this rejected source. Therefore this round establishes no new cross-repository superiority claim, no fresh-quality gain and no all-axis improvement claim.

Two concrete future directions are identified by source inspection only. First, the O lexical exclusion regex repeats an already compiled CJK range; factoring the union into a guarded reuse of the existing native CJK predicate and a smaller non-ASCII-word predicate may reduce import initialization. It needs complete Unicode/custom-hook equivalence tests and a new declared measurement: two searches may increase per-call scanning. Second, end-to-end MCP overhead needs attention because native improvements did not produce the required public MCP gains. Deferring compatibility-regex/table initialization is a lower-priority hypothesis that moves work to first use and must include that cold cost. None of these suggestions has been implemented or timed.

Any later candidate must have its own declared source and development/validation scope. This completed NO attempt is not a replay opportunity, and its adverse MCP round and import cost remain part of the evidence.

## Durable recovery

The optimization branch contains the exact source/controller changes, complete formal audit artifacts, original Q2 failure outputs and logs, and linked immutable result commits. Code and scopes are committed before execution; each hosted stage has a remote start/result checkpoint. The per-call ledger fsync is local, so unuploaded partial rows are not represented as remote Git evidence.

Use [the current machine-readable state](round5-current-state-20261113.json) and [the recovery entry](round5-resume-20261113.md) to resume. They identify the final candidate, completed attempts, failed acceptance conditions and the boundary for any subsequent work. No launched measurement or audit remains in progress.
