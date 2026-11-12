# Round-three startup resource review

**Decision: accepted with a documented resource review for the exact frozen candidate.** This resolves only the startup-cost review. New-cohort, quality, integration and release checks remain separate. The original formal report remains `accepted: false`; its measurements and failed workflow status are not rewritten.

Review date: **2026-11-13 (Asia/Shanghai)**. The new diagnostic ran on 2026-11-12 UTC.

## Original result and retained tradeoff

The [formal report](https://github.com/Afloat16/AI-Memory-Book/blob/35b8618a078fe377ecd6c5acc331c1281dbf61e7/benchmarks/reports/round3-performance-43246417515-1/report.summary.json) contains all 47,320 calls and 16 workers. Complete-payload integrity and the registered numeric retrieval gate passed. Its sole resource flag is public1015 `native_open_ms`: mean **34.4557195 → 39.29410325 ms**, **+14.0423% / +4.83838375 ms**. Each engine has four startup observations.

| Round | Baseline startup ms | Candidate startup ms |
|---|---:|---:|
| 0 | 30.283878 | 56.659038 |
| 1 | 37.007871 | 33.518346 |
| 2 | 38.258907 | 33.283959 |
| 3 | 32.272222 | 33.715070 |

The larger round-zero candidate observation remains in every original statistic. The resource review explicitly accepts the measured startup cost; it does not remove that sample or declare it a proven OS outlier.

## What the fixed diagnostic establishes

The [registered plan](../benchmarks/experiments/round3-startup-review-plan.json) fixes 16 ABBA blocks without SQLite instrumentation (32 fresh processes per engine), followed by four instrumented ABBA blocks (eight fresh processes per engine). Each opens a fresh empty database. No corpus is loaded, no recall runs, and no model or network operation is measured. Ordinary and instrumented results are separate; they are never pooled with the old run.

All **80/80** samples completed in [run 43266672875](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43266672875). [Raw report](https://github.com/Afloat16/AI-Memory-Book/blob/a129e324fb4af9e821325a797edb882beecc30a4/benchmarks/reports/round3-startup-review-43266672875-1/report.json), [summary](https://github.com/Afloat16/AI-Memory-Book/blob/a129e324fb4af9e821325a797edb882beecc30a4/benchmarks/reports/round3-startup-review-43266672875-1/summary.json), all start markers and all worker files are immutable inputs. A separate review recomputed the ordinary/instrumented summary from all 80 rows, checked the fixed order, zero page/cache/revision counts and identical schemas/SQL sequences.

| Separate diagnostic | Baseline | Candidate | Change |
|---|---:|---:|---:|
| Plain mean startup ms (32 each) | 24.386860 | 24.503892 | +0.4799% |
| Plain median startup ms | 24.616202 | 23.945741 | −2.7237% |
| Plain p95 startup ms | 27.744400 | 29.359651 | **+5.8219%** |
| Plain mean process CPU ms | 8.368611 | 8.356788 | −0.1413% |
| Instrumented mean startup ms (8 each) | 22.861039 | 22.749419 | −0.4883% |
| Instrumented schema-script mean wall ms | 21.581551 | 21.464991 | Diagnostic stage only |
| Instrumented schema-script mean CPU ms | 7.807016 | 7.947517 | Diagnostic stage only |

The plain p95 regression is retained. These follow-up times describe another isolated runner with the same Python 3.12.16 and SQLite 3.45.1 versions; they are not a replacement estimate of the original four-round startup result. Instrumented runs occur later and include tracing overhead, so comparing their times to the plain phase would be misleading.

## Cause assessment and review judgment

`native_open_ms` measures `MemoryBook` construction and context entry **before ingestion**. The rowid-bounds optimization executes only during recall. Independent AST comparison found **64 unchanged store components** outside the registered recall methods, including initialization, validation and schema definitions. Both implementations execute the same startup SQL and produce the same schema.

In the instrumented phase, `executescript(SCHEMA)` accounts for approximately **94.4%** of wall time. That stage has roughly **13.5–13.8 ms** more wall time than process CPU. This locates the dominant waiting stage in the existing schema bootstrap; filesystem I/O and scheduler waits are plausible contributors. No new initialization work was found. **The exact OS cause of the historical 56.659038 ms sample is not established**, because that run did not collect syscall or stage traces.

The reviewer accepts the original +4.8384 ms mean empty-database startup cost as an explicit, bounded tradeoff for the pinned candidate. This judgment uses the unchanged initialization operations, the fixed supplemental observations, unchanged storage, no other >10% resource flag and the formal recall improvements below. It does not assert universal startup non-regression or startup acceleration.

## All ten formal retrieval cells

These retain the original run; percentage changes below are candidate minus baseline. Negative means faster. Each synthetic cell contains 672 calls per engine; each public cell contains 4,060 calls per engine.

| Cohort | Configuration | Baseline p95 ms | Candidate p95 ms | Mean change | p50 change | p95 change |
|---|---|---:|---:|---:|---:|---:|
| synthetic61 | native-char4000 | 13.500917 | 12.842840 | -5.258% | -3.249% | -4.874% |
| synthetic61 | mcp-char4000 | 16.011964 | 15.423507 | -3.440% | -1.624% | -3.675% |
| synthetic61 | native-token512 | 21.052449 | 21.078729 | -2.581% | -4.348% | +0.125% |
| synthetic61 | native-token1024 | 23.710123 | 23.643494 | -3.146% | -7.858% | -0.281% |
| synthetic61 | native-token2048 | 20.872050 | 20.682109 | -3.412% | -11.961% | -0.910% |
| public1015 | native-char4000 | 5.053851 | 3.737317 | -15.151% | -12.136% | -26.050% |
| public1015 | mcp-char4000 | 7.408803 | 5.936841 | -12.226% | -10.776% | -19.868% |
| public1015 | native-token512 | 7.619916 | 6.408086 | -8.587% | -7.301% | -15.903% |
| public1015 | native-token1024 | 6.705825 | 5.504397 | -9.885% | -8.044% | -17.916% |
| public1015 | native-token2048 | 6.683904 | 5.397920 | -10.055% | -8.338% | -19.240% |

Pooled p95 geometric-mean improvement is **11.3587%**. Best public native p95 improves **26.0501%**. No pooled cell's p50 or p95 regresses by over 5%. Synthetic token512 p95 is **+0.1248%** and remains visible.

## All formal resource means

Timing fields are milliseconds; RSS/HWM fields are bytes. Each value summarizes four original worker observations. Full min/median/p95/max distributions remain in the linked formal summary.

| Cohort | Metric | Baseline mean | Candidate mean | Change |
|---|---|---:|---:|---:|
| synthetic61 | runtime_import_ms | 24.455720 | 24.621223 | +0.677% |
| synthetic61 | native_open_ms | 42.910098 | 37.649570 | -12.259% |
| synthetic61 | fresh_ingestion_ms | 1061.122682 | 1067.960630 | +0.644% |
| synthetic61 | unchanged_reingestion_ms | 94.276822 | 94.453494 | +0.187% |
| synthetic61 | mcp_startup_to_initialize_ms | 574.168074 | 576.446268 | +0.397% |
| synthetic61 | native_memory_after_ingestion.rss_bytes | 41401344 | 41232384 | -0.408% |
| synthetic61 | native_memory_after_ingestion.hwm_bytes | 41403392 | 41511936 | +0.262% |
| synthetic61 | native_memory_after_calls.rss_bytes | 198396928 | 198306816 | -0.045% |
| synthetic61 | native_memory_after_calls.hwm_bytes | 198396928 | 198306816 | -0.045% |
| synthetic61 | mcp_server_memory_after_calls.rss_bytes | 64532480 | 64327680 | -0.317% |
| synthetic61 | mcp_server_memory_after_calls.hwm_bytes | 64532480 | 64409600 | -0.190% |
| public1015 | runtime_import_ms | 24.926114 | 24.697389 | -0.918% |
| public1015 | native_open_ms | 34.455720 | 39.294103 | +14.042% |
| public1015 | fresh_ingestion_ms | 1143.325160 | 1141.991978 | -0.117% |
| public1015 | unchanged_reingestion_ms | 185.541290 | 185.920099 | +0.204% |
| public1015 | mcp_startup_to_initialize_ms | 578.599952 | 577.412006 | -0.205% |
| public1015 | native_memory_after_ingestion.rss_bytes | 44628992 | 44701696 | +0.163% |
| public1015 | native_memory_after_ingestion.hwm_bytes | 52585472 | 52963328 | +0.719% |
| public1015 | native_memory_after_calls.rss_bytes | 214924288 | 215052288 | +0.060% |
| public1015 | native_memory_after_calls.hwm_bytes | 214924288 | 215052288 | +0.060% |
| public1015 | mcp_server_memory_after_calls.rss_bytes | 64411648 | 63472640 | -1.458% |
| public1015 | mcp_server_memory_after_calls.hwm_bytes | 64411648 | 63472640 | -1.458% |

Post-checkpoint logical database sizes are identical in every original worker: synthetic61 **20,508,672 bytes**, public1015 **12,881,920 bytes**; WAL is zero and SHM is 32,768 bytes. All indexed-content digests match. RSS/HWM are labeled process measurements including evaluator imports, not unique physical-memory allocations.

## Preserved preparation failure and evidence identities

Initial supplemental run [43266483583](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43266483583) failed before measurements because sparse checkout omitted the workflow that registration verification reads. Its result branch `validation/v031-startup-review-43266483583-1` retains the failure. Two integrity tests had passed; **zero diagnostic samples ran**. The only correction added `.github` to sparse checkout and rebound the corrected workflow; the fixed plan, script, tests, counts and order stayed unchanged.

- Baseline runtime: `dd2f88be742ed330269e7dd5915b6f75089d7fef`; SHA256 `d4558f6649762a09e10ad2906c06ab36b21786ef32be131906fc3213cf1a3c57`.
- Candidate runtime: `2d199b93f650eccd3dd239178822b31001b880e3`; SHA256 `9c8118d26ae1a0eae4f31d9d4f44b2afa0ee5c54314bde5187deb27c473dee46`.
- Original compressed report SHA256: `0b4c8dd968b1386818a99788c13e2a724c62c8119b2488ee959d2a6b8e96da86`.
- Supplemental report SHA256: `46e94925e0d67edc86f1444aaea217b95edace3443e4eebbd5b9b3dd34cb92e5`.
- Machine-readable decision: [round3-startup-resource-decision.json](../benchmarks/experiments/round3-startup-resource-decision.json). This decision resolves only the documented resource flag; it does not mutate the formal report or authorize unmeasured product claims.
