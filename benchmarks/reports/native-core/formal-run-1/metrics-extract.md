# Native core formal run 1: complete metric extraction

The `0be1f09502aff1d4ddc0a9e644be7a62be6a944f` candidate is **not accepted for release**. All eight pooled query cells improve, but unchanged reingestion is slower in every paired round in both cohorts. This first attempt remains immutable; any refinement is a separate experiment.

## Evidence and method

- Hosted run: [43871304560](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43871304560), attempt 1.
- Frozen evaluator: `346e5ede35851fd6283bc8be8a34bf4243dc34dd`; baseline: native v0.8.1 `56eccd8c3a6f1d5637664607936da2595ce50c62`.
- Evidence commit: [`4e1e6177e9af188a582b2f2e28aafe6290dfae36`](https://github.com/Afloat16/AI-Memory-Book/tree/4e1e6177e9af188a582b2f2e28aafe6290dfae36).
- Exact fetched `run.json` and `summary.json` bytes independently match the evidence manifest SHA256/length; extraction does not repeat timed calls. Full raw-row/ledger and ZIP validation belongs to the separately retained artifact audit.
- AMD EPYC 9V74, Ubuntu-hosted Linux, CPython 3.12.16, SQLite 3.45.1. Four AB/BA/BA/AB rounds; three passes per worker; 113,568 calls / 56,784 pairs. The frozen summary reports full-output and archive equivalence with no differences.
- Reduction is `100 * (1 - candidate / baseline)`; negative values mean a regression. All query timings below are milliseconds. Pooled p50/p95 are the exact frozen summary values, with percentages independently recomputed. Resource medians use only four workers per side and cohort.
- Results exclude model generation and contain no query-result cache hits; SQLite/OS caches are not cleared. Existing regression cohorts supply no new quality or large-archive claim. Do not combine this host's numbers with prior release experiments.

## All eight query cells

| Cohort | Configuration | Baseline p50 | Candidate p50 | p50 reduction | Baseline p95 | Candidate p95 | p95 reduction | Improved p95 rounds |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| synthetic61 | native-char2400 | 4.512 | 4.357 | +3.438% | 12.400 | 12.053 | +2.802% | 4/4 |
| synthetic61 | mcp-char2400 | 6.359 | 6.325 | +0.540% | 14.448 | 14.278 | +1.178% | 3/4 |
| synthetic61 | native-token1024 | 4.924 | 4.699 | +4.570% | 13.268 | 12.226 | +7.854% | 4/4 |
| synthetic61 | mcp-token1024 | 6.846 | 6.706 | +2.051% | 15.379 | 14.754 | +4.064% | 3/4 |
| public1015 | native-char2400 | 3.836 | 3.611 | +5.874% | 4.958 | 4.683 | +5.544% | 4/4 |
| public1015 | mcp-char2400 | 5.751 | 5.452 | +5.203% | 6.972 | 6.611 | +5.174% | 4/4 |
| public1015 | native-token1024 | 3.347 | 3.176 | +5.114% | 4.019 | 3.823 | +4.887% | 4/4 |
| public1015 | mcp-token1024 | 5.373 | 5.095 | +5.168% | 6.304 | 5.925 | +6.011% | 4/4 |

## Every paired query round

Each cell is **p50 / p95 reduction (%)**, in actual chronological round order. Both synthetic MCP configurations regress in round 4; those rows are retained.

| Cohort | Configuration | Round 1 | Round 2 | Round 3 | Round 4 |
|---|---|---:|---:|---:|---:|
| synthetic61 | native-char2400 | +1.559 / +1.961 | +7.212 / +4.535 | +3.570 / +1.490 | +2.831 / +1.353 |
| synthetic61 | mcp-char2400 | +1.739 / +1.420 | +2.453 / +2.577 | +3.467 / +3.409 | -4.725 / -1.923 |
| synthetic61 | native-token1024 | +3.534 / +4.860 | +4.697 / +9.387 | +6.617 / +9.080 | +4.176 / +6.242 |
| synthetic61 | mcp-token1024 | +2.006 / +4.691 | +3.768 / +7.406 | +2.110 / +5.080 | -1.266 / -0.949 |
| public1015 | native-char2400 | +5.439 / +5.233 | +4.971 / +4.787 | +5.733 / +5.276 | +6.806 / +6.739 |
| public1015 | mcp-char2400 | +4.477 / +4.646 | +10.045 / +9.844 | +1.894 / +2.446 | +4.261 / +3.834 |
| public1015 | native-token1024 | +4.485 / +4.636 | +6.741 / +6.788 | +4.460 / +3.511 | +4.636 / +5.126 |
| public1015 | mcp-token1024 | +2.189 / +0.937 | +7.667 / +7.612 | +5.312 / +4.962 | +6.020 / +6.887 |

## All four ingestion cells

The registered headline percentage uses the **sum of all four paired batch times**, not the ratio of medians. Each fresh/unchanged batch has 112 sessions for synthetic61 or 216 for public1015. One unchanged pass per worker verifies the same session inputs are skipped; it still incurs input processing. The JSON extraction retains every individual baseline/candidate time and both types of aggregate.

| Cohort | Batch | Baseline four-batch total (ms) | Candidate total (ms) | Total reduction | Baseline median (ms) | Candidate median (ms) | Improved rounds |
|---|---|---:|---:|---:|---:|---:|---:|
| synthetic61 | fresh_ingestion_ms | 2942.774 | 2738.660 | +6.936% | 735.502 | 684.557 | 4/4 |
| synthetic61 | unchanged_reingestion_ms | 314.370 | 375.405 | -19.415% | 78.628 | 91.901 | 0/4 |
| public1015 | fresh_ingestion_ms | 2950.056 | 2822.142 | +4.336% | 737.531 | 692.922 | 3/4 |
| public1015 | unchanged_reingestion_ms | 523.319 | 635.359 | -21.410% | 130.826 | 156.419 | 0/4 |

| Cohort | Batch | Round 1 reduction | Round 2 reduction | Round 3 reduction | Round 4 reduction |
|---|---|---:|---:|---:|---:|
| synthetic61 | fresh_ingestion_ms | +7.471% | +7.010% | +6.427% | +6.844% |
| synthetic61 | unchanged_reingestion_ms | -16.593% | -28.077% | -17.161% | -15.816% |
| public1015 | fresh_ingestion_ms | +5.047% | -2.185% | +7.397% | +7.023% |
| public1015 | unchanged_reingestion_ms | -19.971% | -18.886% | -27.107% | -19.654% |

Unchanged reingestion total wall time increases **19.415% / 21.410%** for synthetic/public. Its per-round increases range from **15.816% to 28.077%** and **18.886% to 27.107%** respectively. Public fresh ingestion also regresses **2.185%** in round 2 despite its overall improvement. These costs block adopting this candidate as the performance-focused release.

## Startup, memory and CPU costs

Positive delta is an increase. All values are medians of four workers per side/cohort, not per-query latency percentiles. The full JSON includes four raw values for all 38 resource cells, including pre-call and post-ingestion snapshots.

| Cohort | Resource | Unit | Baseline median | Candidate median | Delta |
|---|---|---|---:|---:|---:|
| synthetic61 | runtime_import_ms | ms | 46.487 | 48.320 | +1.833 |
| synthetic61 | new_database_ms | ms | 3.774 | 3.629 | -0.145 |
| synthetic61 | existing_database_open_ms | ms | 0.715 | 0.715 | -0.000 |
| synthetic61 | worker_rss_after_calls | MiB | 129.121 | 129.178 | +0.057 |
| synthetic61 | worker_hwm_after_calls | MiB | 133.498 | 135.463 | +1.965 |
| synthetic61 | worker_cpu_after_calls | s | 10.285 | 10.225 | -0.060 |
| synthetic61 | mcp-char2400_startup_to_initialize_ms | ms | 643.525 | 645.313 | +1.787 |
| synthetic61 | mcp-char2400_server_rss_after_calls | MiB | 60.553 | 60.533 | -0.020 |
| synthetic61 | mcp-char2400_server_cpu_during_calls | s | 3.710 | 3.625 | -0.085 |
| synthetic61 | mcp-token1024_startup_to_initialize_ms | ms | 633.460 | 639.145 | +5.685 |
| synthetic61 | mcp-token1024_server_rss_after_calls | MiB | 104.547 | 103.607 | -0.939 |
| synthetic61 | mcp-token1024_server_cpu_during_calls | s | 3.875 | 3.790 | -0.085 |
| public1015 | runtime_import_ms | ms | 46.811 | 48.742 | +1.931 |
| public1015 | new_database_ms | ms | 3.759 | 3.596 | -0.164 |
| public1015 | existing_database_open_ms | ms | 0.726 | 0.708 | -0.018 |
| public1015 | worker_rss_after_calls | MiB | 139.467 | 139.609 | +0.143 |
| public1015 | worker_hwm_after_calls | MiB | 150.035 | 150.012 | -0.023 |
| public1015 | worker_cpu_after_calls | s | 39.335 | 37.795 | -1.540 |
| public1015 | mcp-char2400_startup_to_initialize_ms | ms | 653.617 | 644.079 | -9.539 |
| public1015 | mcp-char2400_server_rss_after_calls | MiB | 60.559 | 60.725 | +0.166 |
| public1015 | mcp-char2400_server_cpu_during_calls | s | 16.615 | 15.690 | -0.925 |
| public1015 | mcp-token1024_startup_to_initialize_ms | ms | 640.033 | 641.575 | +1.542 |
| public1015 | mcp-token1024_server_rss_after_calls | MiB | 104.641 | 104.260 | -0.381 |
| public1015 | mcp-token1024_server_cpu_during_calls | s | 15.715 | 14.815 | -0.900 |

API import is `MemoryBook` import after evaluator/bootstrap imports, not full CLI/process startup. MCP initialization runs from launching a fresh server process through the SDK initialize response. Worker RSS/CPU includes probes, ingestion, evaluation, output validation and all configurations; worker CPU is cumulative process lifetime and cannot be called isolated recall CPU. MCP server CPU is the user+system snapshot difference across its three query passes, with procfs tick granularity. MCP per-call calling-process CPU measures the **client**, and is not substituted for server CPU here.

API import increases **1.833 / 1.931 ms**. Synthetic MCP startup increases **1.787 ms** at 2400 chars and **5.685 ms** with the token cap; public startup changes **-9.539 / +1.542 ms**. Worker live RSS changes **+0.057 / +0.143 MiB**; synthetic peak RSS increases **1.965 MiB**. These four-worker values do not establish a general startup or memory improvement.

## Storage and native binary

All checkpointed workers retain the same database size per cohort: **20,201,472 bytes** for synthetic61 and **13,025,280 bytes** for public1015; checkpointed WAL is **0 bytes** and SHM is **32,768 bytes** on both sides. The extraction retains every live and post-ingestion DB/WAL/SHM observation as well.

The hosted baseline extension is **126,632 bytes**; the candidate extension is **619,464 bytes**, an increase of **492,832 bytes**. These are this host's compiled extension files, not wheel download sizes or all-platform installation sizes. Both exact binary hashes remain in the extraction and evidence manifest.
