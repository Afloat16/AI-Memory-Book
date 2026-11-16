# Native core compatibility formal run 1: complete metric extraction

This report retains every registered query and ingestion cell, every paired round, and all resource observations. It makes no release-acceptance decision.

## Evidence and method

- Hosted first attempt: [43886529702](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43886529702).
- Frozen evaluator: `cfdb3ca2c8ff2d71792e820923057d6613ea08b7`; baseline: native v0.8.1 `56eccd8c3a6f1d5637664607936da2595ce50c62`; candidate: `4390d013986ab9c96b49cc6964f075f3866f21ee`.
- Immutable evidence: [51e8d022c164ba714f68db562c9ae280a62c2312](https://github.com/Afloat16/AI-Memory-Book/tree/51e8d022c164ba714f68db562c9ae280a62c2312).
- Fetched run/summary bytes match the evidence manifest. This extraction repeats no timed calls; the separately retained artifact audit verifies every raw row, ledger and source.
- Host: AMD EPYC 7763 64-Core Processor; Python 3.12.16, SQLite 3.45.1. Four AB/BA/BA/AB rounds, three passes per worker, 113,568 calls and 56,784 pairs.
- Positive reduction means faster: 100 * (1 - candidate / baseline). Negative values remain regressions. All latency values are milliseconds; resource values are medians of four workers per side/cohort.
- No model generation or query-result cache hits. SQLite/OS caches are not cleared. Existing regression cohorts give no new retrieval-quality or large-archive guarantee. Different experiments/hosts are not added together.

## All eight query cells

| Cohort | Configuration | Baseline p50 | Candidate p50 | p50 reduction | Baseline p95 | Candidate p95 | p95 reduction | Improving p95 rounds |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| synthetic61 | native-char2400 | 4.465 | 4.288 | +3.947% | 12.231 | 12.008 | +1.823% | 3/4 |
| synthetic61 | mcp-char2400 | 6.221 | 6.053 | +2.696% | 14.158 | 13.783 | +2.645% | 4/4 |
| synthetic61 | native-token1024 | 4.886 | 4.646 | +4.904% | 12.636 | 11.621 | +8.033% | 4/4 |
| synthetic61 | mcp-token1024 | 6.741 | 6.476 | +3.927% | 14.764 | 13.548 | +8.232% | 4/4 |
| public1015 | native-char2400 | 3.842 | 3.606 | +6.140% | 4.950 | 4.663 | +5.791% | 4/4 |
| public1015 | mcp-char2400 | 5.592 | 5.383 | +3.734% | 6.714 | 6.479 | +3.513% | 4/4 |
| public1015 | native-token1024 | 3.296 | 3.138 | +4.772% | 3.942 | 3.752 | +4.804% | 4/4 |
| public1015 | mcp-token1024 | 5.091 | 4.968 | +2.423% | 5.766 | 5.702 | +1.120% | 3/4 |

## Every paired query round

Each entry is p50 / p95 reduction (%), in chronological round order.

| Cohort | Configuration | Round 1 | Round 2 | Round 3 | Round 4 |
|---|---|---:|---:|---:|---:|
| synthetic61 | native-char2400 | +4.499 / +1.626 | +1.364 / -0.892 | +4.169 / +2.639 | +5.197 / +2.377 |
| synthetic61 | mcp-char2400 | +3.231 / +2.926 | +1.316 / +1.177 | +2.600 / +2.591 | +3.232 / +3.097 |
| synthetic61 | native-token1024 | +6.570 / +8.912 | +4.323 / +8.247 | +5.535 / +8.459 | +4.628 / +7.455 |
| synthetic61 | mcp-token1024 | +6.399 / +10.343 | +5.129 / +8.174 | +2.268 / +6.227 | +1.845 / +5.854 |
| public1015 | native-char2400 | +4.852 / +4.649 | +6.528 / +6.670 | +6.331 / +5.485 | +7.091 / +6.810 |
| public1015 | mcp-char2400 | +2.362 / +1.788 | +3.404 / +3.483 | +4.393 / +4.561 | +4.519 / +4.380 |
| public1015 | native-token1024 | +1.762 / +0.939 | +5.494 / +5.271 | +4.432 / +4.583 | +7.458 / +8.261 |
| public1015 | mcp-token1024 | -0.775 / -3.178 | +3.410 / +3.150 | +3.083 / +3.103 | +3.316 / +3.453 |

## All four ingestion cells

The registered percentage compares the sum of all four paired batches. Medians and every raw batch time remain in the JSON. Each batch contains 112 synthetic or 216 public sessions.

| Cohort | Batch | Baseline total (ms) | Candidate total (ms) | Total reduction | Baseline median (ms) | Candidate median (ms) | Improving rounds |
|---|---|---:|---:|---:|---:|---:|---:|
| synthetic61 | fresh_ingestion_ms | 3033.433 | 2752.058 | +9.276% | 757.598 | 685.542 | 4/4 |
| synthetic61 | unchanged_reingestion_ms | 326.946 | 317.252 | +2.965% | 81.870 | 78.926 | 4/4 |
| public1015 | fresh_ingestion_ms | 3013.275 | 2700.332 | +10.385% | 752.389 | 672.649 | 4/4 |
| public1015 | unchanged_reingestion_ms | 564.014 | 541.809 | +3.937% | 141.072 | 135.083 | 4/4 |

| Cohort | Batch | Round 1 | Round 2 | Round 3 | Round 4 |
|---|---|---:|---:|---:|---:|
| synthetic61 | fresh_ingestion_ms | +8.577% | +7.592% | +10.144% | +10.783% |
| synthetic61 | unchanged_reingestion_ms | +2.492% | +1.793% | +3.421% | +4.151% |
| public1015 | fresh_ingestion_ms | +9.726% | +11.472% | +10.712% | +9.648% |
| public1015 | unchanged_reingestion_ms | +3.949% | +4.840% | +3.392% | +3.561% |

## Every negative query or ingestion observation

Negative pooled, individual-round and ingestion-total reductions are listed without filtering.

| Kind | Cohort | Configuration / metric | Round | Reduction |
|---|---|---|---:|---:|
| query_round | synthetic61 | native-char2400 p95 | 2 | -0.892% |
| query_round | public1015 | mcp-token1024 p50 | 1 | -0.775% |
| query_round | public1015 | mcp-token1024 p95 | 1 | -3.178% |

## Startup, memory and CPU: all 38 resource cells

Positive delta means a higher candidate value. JSON retains all four raw values per side, the exact sampling boundary, and every original worker resource snapshot.

| Cohort | Resource | Unit | Baseline median | Candidate median | Delta |
|---|---|---|---:|---:|---:|
| synthetic61 | runtime_import_ms | ms | 44.913 | 46.956 | +2.043 |
| synthetic61 | new_database_ms | ms | 4.283 | 4.385 | +0.102 |
| synthetic61 | existing_database_open_ms | ms | 0.665 | 0.677 | +0.012 |
| synthetic61 | worker_rss_after_ingestion | MiB | 43.621 | 44.016 | +0.395 |
| synthetic61 | worker_hwm_after_ingestion | MiB | 44.836 | 45.135 | +0.299 |
| synthetic61 | worker_rss_after_calls | MiB | 129.334 | 129.566 | +0.232 |
| synthetic61 | worker_hwm_after_calls | MiB | 133.660 | 133.801 | +0.141 |
| synthetic61 | worker_cpu_after_ingestion | s | 1.095 | 1.160 | +0.065 |
| synthetic61 | worker_cpu_after_calls | s | 10.070 | 9.820 | -0.250 |
| synthetic61 | mcp-char2400_startup_to_initialize_ms | ms | 645.329 | 641.067 | -4.262 |
| synthetic61 | mcp-char2400_server_rss_before_calls | MiB | 57.174 | 57.305 | +0.131 |
| synthetic61 | mcp-char2400_server_rss_after_calls | MiB | 60.447 | 60.574 | +0.127 |
| synthetic61 | mcp-char2400_server_hwm_after_calls | MiB | 60.447 | 60.574 | +0.127 |
| synthetic61 | mcp-char2400_server_cpu_during_calls | s | 3.670 | 3.530 | -0.140 |
| synthetic61 | mcp-token1024_startup_to_initialize_ms | ms | 645.220 | 630.288 | -14.932 |
| synthetic61 | mcp-token1024_server_rss_before_calls | MiB | 57.051 | 57.273 | +0.223 |
| synthetic61 | mcp-token1024_server_rss_after_calls | MiB | 104.455 | 104.623 | +0.168 |
| synthetic61 | mcp-token1024_server_hwm_after_calls | MiB | 104.455 | 104.623 | +0.168 |
| synthetic61 | mcp-token1024_server_cpu_during_calls | s | 3.800 | 3.625 | -0.175 |
| public1015 | runtime_import_ms | ms | 44.430 | 46.627 | +2.197 |
| public1015 | new_database_ms | ms | 4.243 | 4.297 | +0.054 |
| public1015 | existing_database_open_ms | ms | 0.667 | 0.681 | +0.014 |
| public1015 | worker_rss_after_ingestion | MiB | 46.279 | 46.484 | +0.205 |
| public1015 | worker_hwm_after_ingestion | MiB | 54.971 | 55.154 | +0.184 |
| public1015 | worker_rss_after_calls | MiB | 139.693 | 139.711 | +0.018 |
| public1015 | worker_hwm_after_calls | MiB | 150.141 | 150.162 | +0.021 |
| public1015 | worker_cpu_after_ingestion | s | 1.125 | 1.180 | +0.055 |
| public1015 | worker_cpu_after_calls | s | 38.295 | 37.165 | -1.130 |
| public1015 | mcp-char2400_startup_to_initialize_ms | ms | 637.546 | 644.898 | +7.352 |
| public1015 | mcp-char2400_server_rss_before_calls | MiB | 57.125 | 57.305 | +0.180 |
| public1015 | mcp-char2400_server_rss_after_calls | MiB | 60.572 | 60.670 | +0.098 |
| public1015 | mcp-char2400_server_hwm_after_calls | MiB | 61.080 | 61.184 | +0.104 |
| public1015 | mcp-char2400_server_cpu_during_calls | s | 16.225 | 15.595 | -0.630 |
| public1015 | mcp-token1024_startup_to_initialize_ms | ms | 629.788 | 630.542 | +0.754 |
| public1015 | mcp-token1024_server_rss_before_calls | MiB | 57.184 | 57.219 | +0.035 |
| public1015 | mcp-token1024_server_rss_after_calls | MiB | 104.621 | 104.736 | +0.115 |
| public1015 | mcp-token1024_server_hwm_after_calls | MiB | 104.904 | 105.154 | +0.250 |
| public1015 | mcp-token1024_server_cpu_during_calls | s | 14.890 | 14.445 | -0.445 |

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
| baseline | 126648 | `22d18696a0214b43601d856ff9a37c110c2c80611fd06af6e417c89eb2ea0214` |
| candidate | 646128 | `ace1c0a6e4e73fd799a9a445d62e806867d3227834cdbef02e356b62b9bab605` |

Native extension size changes by +519,480 bytes on this host. These are compiled extension files, not wheel download or all-platform installation sizes.
