# Native core refinement formal run 1: complete metric extraction

This report retains every registered query and ingestion cell, every paired round, and all resource observations. It makes no release-acceptance decision.

## Evidence and method

- Hosted first attempt: [43883672930](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43883672930).
- Frozen evaluator: `0267f6cce5189e42ce9432e228366372e121cf38`; baseline: native v0.8.1 `56eccd8c3a6f1d5637664607936da2595ce50c62`; candidate: `e91183bf6dd9e125d6549ec3fe5d9c81598cd131`.
- Immutable evidence: [1b1f71606140b2eade960fb4618b9a5723469b7e](https://github.com/Afloat16/AI-Memory-Book/tree/1b1f71606140b2eade960fb4618b9a5723469b7e).
- Fetched run/summary bytes match the evidence manifest. This extraction repeats no timed calls; the separately retained artifact audit verifies every raw row, ledger and source.
- Host: AMD EPYC 9V45 96-Core Processor; Python 3.12.16, SQLite 3.45.1. Four AB/BA/BA/AB rounds, three passes per worker, 113,568 calls and 56,784 pairs.
- Positive reduction means faster: 100 * (1 - candidate / baseline). Negative values remain regressions. All latency values are milliseconds; resource values are medians of four workers per side/cohort.
- No model generation or query-result cache hits. SQLite/OS caches are not cleared. Existing regression cohorts give no new retrieval-quality or large-archive guarantee. Different experiments/hosts are not added together.

## All eight query cells

| Cohort | Configuration | Baseline p50 | Candidate p50 | p50 reduction | Baseline p95 | Candidate p95 | p95 reduction | Improving p95 rounds |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| synthetic61 | native-char2400 | 2.701 | 2.579 | +4.503% | 7.241 | 6.981 | +3.592% | 4/4 |
| synthetic61 | mcp-char2400 | 4.274 | 4.082 | +4.498% | 9.191 | 8.801 | +4.235% | 4/4 |
| synthetic61 | native-token1024 | 2.948 | 2.817 | +4.456% | 8.081 | 7.562 | +6.425% | 4/4 |
| synthetic61 | mcp-token1024 | 4.523 | 4.306 | +4.794% | 10.207 | 9.429 | +7.629% | 4/4 |
| public1015 | native-char2400 | 2.268 | 2.148 | +5.308% | 3.031 | 2.792 | +7.903% | 3/4 |
| public1015 | mcp-char2400 | 3.550 | 3.371 | +5.062% | 4.536 | 4.150 | +8.519% | 4/4 |
| public1015 | native-token1024 | 1.972 | 1.890 | +4.175% | 2.407 | 2.299 | +4.481% | 4/4 |
| public1015 | mcp-token1024 | 3.214 | 3.097 | +3.646% | 3.879 | 3.747 | +3.397% | 4/4 |

## Every paired query round

Each entry is p50 / p95 reduction (%), in chronological round order.

| Cohort | Configuration | Round 1 | Round 2 | Round 3 | Round 4 |
|---|---|---:|---:|---:|---:|
| synthetic61 | native-char2400 | +4.283 / +4.078 | +3.443 / +2.348 | +2.327 / +1.566 | +7.043 / +6.573 |
| synthetic61 | mcp-char2400 | +5.870 / +2.658 | +4.715 / +0.721 | +1.625 / +2.640 | +2.311 / +2.475 |
| synthetic61 | native-token1024 | +9.338 / +11.011 | +2.909 / +6.074 | +4.075 / +3.689 | +3.318 / +4.075 |
| synthetic61 | mcp-token1024 | +5.257 / +7.629 | +6.346 / +9.684 | +3.078 / +7.246 | +2.338 / +2.364 |
| public1015 | native-char2400 | +6.678 / +7.147 | -1.512 / -1.201 | +9.227 / +36.729 | +6.671 / +6.225 |
| public1015 | mcp-char2400 | +9.190 / +8.555 | -0.085 / +1.528 | +7.546 / +10.953 | +4.502 / +4.618 |
| public1015 | native-token1024 | +4.449 / +3.028 | +3.103 / +3.488 | +4.793 / +5.321 | +4.295 / +5.081 |
| public1015 | mcp-token1024 | +3.897 / +4.050 | +1.536 / +1.404 | +2.176 / +3.010 | +6.551 / +8.602 |

## All four ingestion cells

The registered percentage compares the sum of all four paired batches. Medians and every raw batch time remain in the JSON. Each batch contains 112 synthetic or 216 public sessions.

| Cohort | Batch | Baseline total (ms) | Candidate total (ms) | Total reduction | Baseline median (ms) | Candidate median (ms) | Improving rounds |
|---|---|---:|---:|---:|---:|---:|---:|
| synthetic61 | fresh_ingestion_ms | 2375.521 | 2248.292 | +5.356% | 591.828 | 558.267 | 4/4 |
| synthetic61 | unchanged_reingestion_ms | 174.663 | 168.863 | +3.321% | 43.735 | 42.228 | 4/4 |
| public1015 | fresh_ingestion_ms | 2757.309 | 2702.526 | +1.987% | 688.039 | 651.362 | 2/4 |
| public1015 | unchanged_reingestion_ms | 295.771 | 281.168 | +4.937% | 74.372 | 70.601 | 4/4 |

| Cohort | Batch | Round 1 | Round 2 | Round 3 | Round 4 |
|---|---|---:|---:|---:|---:|
| synthetic61 | fresh_ingestion_ms | +8.908% | +3.314% | +3.426% | +5.559% |
| synthetic61 | unchanged_reingestion_ms | +3.641% | +1.720% | +0.674% | +7.123% |
| public1015 | fresh_ingestion_ms | -4.436% | +6.391% | +7.874% | -1.703% |
| public1015 | unchanged_reingestion_ms | +2.422% | +4.924% | +5.215% | +7.292% |

## Every negative query or ingestion observation

Negative pooled, individual-round and ingestion-total reductions are listed without filtering.

| Kind | Cohort | Configuration / metric | Round | Reduction |
|---|---|---|---:|---:|
| query_round | public1015 | native-char2400 p50 | 2 | -1.512% |
| query_round | public1015 | native-char2400 p95 | 2 | -1.201% |
| query_round | public1015 | mcp-char2400 p50 | 2 | -0.085% |
| ingestion_round | public1015 |  fresh_ingestion_ms | 1 | -4.436% |
| ingestion_round | public1015 |  fresh_ingestion_ms | 4 | -1.703% |

## Startup, memory and CPU: all 38 resource cells

Positive delta means a higher candidate value. JSON retains all four raw values per side, the exact sampling boundary, and every original worker resource snapshot.

| Cohort | Resource | Unit | Baseline median | Candidate median | Delta |
|---|---|---|---:|---:|---:|
| synthetic61 | runtime_import_ms | ms | 29.032 | 29.168 | +0.137 |
| synthetic61 | new_database_ms | ms | 3.422 | 3.342 | -0.080 |
| synthetic61 | existing_database_open_ms | ms | 0.623 | 0.659 | +0.036 |
| synthetic61 | worker_rss_after_ingestion | MiB | 43.861 | 43.859 | -0.002 |
| synthetic61 | worker_hwm_after_ingestion | MiB | 44.953 | 45.092 | +0.139 |
| synthetic61 | worker_rss_after_calls | MiB | 129.414 | 129.225 | -0.189 |
| synthetic61 | worker_hwm_after_calls | MiB | 133.750 | 133.674 | -0.076 |
| synthetic61 | worker_cpu_after_ingestion | s | 0.655 | 0.680 | +0.025 |
| synthetic61 | worker_cpu_after_calls | s | 6.310 | 6.185 | -0.125 |
| synthetic61 | mcp-char2400_startup_to_initialize_ms | ms | 423.831 | 430.038 | +6.207 |
| synthetic61 | mcp-char2400_server_rss_before_calls | MiB | 57.102 | 57.156 | +0.055 |
| synthetic61 | mcp-char2400_server_rss_after_calls | MiB | 60.516 | 60.486 | -0.029 |
| synthetic61 | mcp-char2400_server_hwm_after_calls | MiB | 60.516 | 60.486 | -0.029 |
| synthetic61 | mcp-char2400_server_cpu_during_calls | s | 2.320 | 2.240 | -0.080 |
| synthetic61 | mcp-token1024_startup_to_initialize_ms | ms | 416.915 | 418.213 | +1.297 |
| synthetic61 | mcp-token1024_server_rss_before_calls | MiB | 57.115 | 57.234 | +0.119 |
| synthetic61 | mcp-token1024_server_rss_after_calls | MiB | 104.607 | 104.730 | +0.123 |
| synthetic61 | mcp-token1024_server_hwm_after_calls | MiB | 104.607 | 104.730 | +0.123 |
| synthetic61 | mcp-token1024_server_cpu_during_calls | s | 2.505 | 2.365 | -0.140 |
| public1015 | runtime_import_ms | ms | 28.281 | 30.170 | +1.889 |
| public1015 | new_database_ms | ms | 5.370 | 3.632 | -1.738 |
| public1015 | existing_database_open_ms | ms | 0.627 | 0.622 | -0.005 |
| public1015 | worker_rss_after_ingestion | MiB | 46.256 | 46.496 | +0.240 |
| public1015 | worker_hwm_after_ingestion | MiB | 54.945 | 55.061 | +0.115 |
| public1015 | worker_rss_after_calls | MiB | 139.627 | 139.777 | +0.150 |
| public1015 | worker_hwm_after_calls | MiB | 150.064 | 150.066 | +0.002 |
| public1015 | worker_cpu_after_ingestion | s | 0.705 | 0.730 | +0.025 |
| public1015 | worker_cpu_after_calls | s | 23.705 | 22.805 | -0.900 |
| public1015 | mcp-char2400_startup_to_initialize_ms | ms | 425.992 | 413.103 | -12.889 |
| public1015 | mcp-char2400_server_rss_before_calls | MiB | 57.141 | 57.322 | +0.182 |
| public1015 | mcp-char2400_server_rss_after_calls | MiB | 60.586 | 60.715 | +0.129 |
| public1015 | mcp-char2400_server_hwm_after_calls | MiB | 60.967 | 61.268 | +0.301 |
| public1015 | mcp-char2400_server_cpu_during_calls | s | 10.215 | 9.695 | -0.520 |
| public1015 | mcp-token1024_startup_to_initialize_ms | ms | 412.903 | 415.134 | +2.231 |
| public1015 | mcp-token1024_server_rss_before_calls | MiB | 57.076 | 57.336 | +0.260 |
| public1015 | mcp-token1024_server_rss_after_calls | MiB | 104.654 | 104.672 | +0.018 |
| public1015 | mcp-token1024_server_hwm_after_calls | MiB | 104.973 | 105.000 | +0.027 |
| public1015 | mcp-token1024_server_cpu_during_calls | s | 9.245 | 9.045 | -0.200 |

API import starts after evaluator/bootstrap imports and is not full CLI startup. MCP initialization starts at fresh server launch. Worker RSS/CPU includes probes, ingestion, evaluation and output validation; cumulative worker CPU is not isolated recall CPU. MCP server CPU is the user+system snapshot difference with procfs tick granularity; per-call calling-process CPU is the client. Four resource samples per side do not establish a universal startup or memory gain.

## Storage and native binaries

Every live and checkpointed DB/WAL/SHM observation is retained in JSON.

| Cohort | Side | Checkpointed DB sizes (bytes) | WAL sizes | SHM sizes |
|---|---|---|---|---|
| synthetic61 | baseline | 20201472 | 0 | 32768 |
| synthetic61 | candidate | 20201472 | 0 | 32768 |
| public1015 | baseline | 13025280 | 0 | 32768 |
| public1015 | candidate | 13025280 | 0 | 32768 |

| Side | Native extension bytes | SHA256 |
|---|---:|---|
| baseline | 126640 | `a01a3a79215c7948035f0193d3e27768afc0b686f0cdb9d18a3d7d89a32e6216` |
| candidate | 645368 | `15b156e414cf3eae254466a9c338be525779a09de01437b2885e8c0e4b91ba70` |

Native extension size changes by +518,728 bytes on this host. These are compiled extension files, not wheel download or all-platform installation sizes.
