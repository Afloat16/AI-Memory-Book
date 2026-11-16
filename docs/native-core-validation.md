# v0.9.0: broader native execution with preserved behavior

The final candidate expands the existing optional C backend from seven to
**22 entry points**. The final hosted comparison against native v0.8.1 records
equivalent results for **113,568 calls / 56,784 pairs**, lower pooled p50 and p95
in all eight query cells (two cohorts × four configurations), and lower total time in all four ingestion
configurations. It also records two slower p95 rounds, a slower p50 round,
slightly higher memory, a larger extension and mixed startup costs.

This report applies to candidate
`4390d013986ab9c96b49cc6964f075f3866f21ee`, whose runtime SHA256 is
`6ec51c906de94c97f90ec9be3dc50d066c9abedcff283c1e118ef6d6847eb3b7`.
Later documentation/release-control commits must retain those runtime bytes.
The [machine-readable acceptance](../benchmarks/experiments/native_core_acceptance.json)
records the adoption decision and remaining publication gates.

## What changed

| Execution path | Added native entry points | Preserved contract |
|---|---|---|
| Lexical processing | `strip_nonspacing_marks`, `identifier_has_boundary` | Unicode category behavior, identifier boundaries, helper dispatch |
| Excerpt construction | `excerpt_window` | Complete window construction, floating-point evaluation order, ties, rendering, code-point positions |
| Candidate/result handling | `rank_candidates`, `select_novelty`, `context_allocations`, `refs_from_parsed` | Existing ordering, duplicate/novelty decisions, allocations and reference fields |
| Source projection | `source_units`, `projected_units`, `source_map_matches` | Exact original coordinates, intervals, clipping and dynamic reads |
| Segmentation and pages | `make_turns`, `page_cuts`, `build_pages`, `segment_turns`, `segmentation_ready` | Existing turns, page cuts, grouping, IDs and guarded public dispatch |

The seven earlier entry points remain: `terms_ascii`, `ascii_tokens`,
`unicode_tokens`, `identifier_aliases`, `literal_positions`,
`fold_excerpt_source`, and `evidence_units`.
The extension comprises `_native.c` and five private headers, totaling 4,118
source lines in the frozen candidate. This is an implementation inventory,
not a performance metric.

The Python reference functions remain available for portable installations,
supported dynamic overrides, unusual argument types, and differential tests.
Python also retains the CLI, MCP protocol, capture/client integration, storage
orchestration and the existing optional semantic/model interfaces. SQLite
continues to execute the same SQL and FTS5 operations. Existing native
dependencies retain their responsibilities. The rewrite does not introduce
a new query algorithm, vector index, cache policy or parallel-query strategy.

Schema 4, source/content hashing, page IDs, project filtering, temporal ordering,
character/token budgets, database transactions and archive behavior remain
unchanged. Strings retain Python Unicode code-point counting and slicing,
including non-BMP characters and tested surrogate edge cases; UTF-8 byte
positions are not substituted for original offsets. Existing schema-4
archives require no new migration.

Twenty-seven immutable names and separators are held in per-module C state.
The extension uses multiphase initialization and traverse/clear/free hooks.
Class, field, global and helper dependencies are still read dynamically in
their original order. This reuses constant objects; it does not cache a
segmentation-readiness decision or application result.

The public Python `_joined` function is deliberately retained, with its AST
matching v0.8.1. The attempted C replacement made its measured public wrapper
slower. `build_pages` still invokes that Python function dynamically, with
the corresponding compatibility guard.

## Frozen experiment and timing boundaries

The [formal run 43886529702, attempt 1](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43886529702)
uses protocol `native-core-compatibility-performance-5`, with the plan,
evaluator, host builder, preservation code, protocol tests and independent
auditor frozen at `cfdb3ca2c8ff2d71792e820923057d6613ea08b7`.

| Identity | Value |
|---|---|
| Baseline | Released native v0.8.1, `56eccd8c3a6f1d5637664607936da2595ce50c62` |
| Candidate | `4390d013986ab9c96b49cc6964f075f3866f21ee` |
| Formal plan SHA256 | `a721f8a68378bf41a663367a99f1f2b24dc644e204be04aae98615e49d6863e0` |
| Immutable Git evidence | [`51e8d022c164ba714f68db562c9ae280a62c2312`](https://github.com/Afloat16/AI-Memory-Book/tree/51e8d022c164ba714f68db562c9ae280a62c2312) |
| Evidence tree | `0ce5b0278f9dfcd33d86b3d7ae1d97eb876e4ca4` |
| Additional Actions artifact | `14234453695`, 77,821,913 bytes |
| Artifact SHA256 | `3758248a1ac85b20146a69d4b8a457c7f62059c663b621fe6988785b9c76b04a` |

The host was Ubuntu 24.04, AMD EPYC 7763 with four visible CPUs, CPython 3.12.16,
GCC 13.3.0, SQLite 3.45.1 and Unicode 15.0.0. Both versions use forced native
builds and identical compiler commands/flags, including `-O3`. Packages are
pinned to MCP 1.30.0, Pydantic 2.14.3, setuptools 80.9.0 and tiktoken 0.12.0.
The source/build identities and actual loaded binary hashes are retained.
Both compile logs contain real compiler/link commands; their bytes are equal
because the commands use identical relative paths under separate source roots.

The existing synthetic seed-61 development cohort contains 112 sessions,
1,408 turns, 1,143,252 source characters and 168 queries across eight projects.
The public cohort contains 216 sessions, 4,684 turns, 616,994 source characters
and 1,015 eligible text-evidence queries from the repository's fixed LoCoMo
split. Its source is pinned to LoCoMo commit
`3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376`; its CC-BY-NC-4.0 attribution,
selection/exclusion rules and exact input hash remain in
[run.json](../benchmarks/reports/native-core-compatibility/formal-run-1/run.json).
Although that historical split is named heldout, it has already been reused
for regressions. This experiment makes no new holdout, retrieval-quality or
model-answer claim.

Four balanced rounds use AB/BA/BA/AB order, with fresh sequential workers and
three passes per worker. Every worker runs direct recall and actual official-SDK
stdio MCP at a 2400-character budget and at the separately registered 1024-token
configuration. This yields 2,016 observations per side/cell for synthetic data
and 12,180 for public data. All observations enter pooled percentiles; no timed
sample is discarded and there is no timed-call warmup.

Direct timing measures `MemoryBook.recall`, including optional token-budget
work. MCP timing measures the SDK call round trip, including server recall,
normal cache writing, serialization and transport. MCP cache clearing is outside
the timer; native result caching is disabled. There are no query-result cache
hits, but Python, SQLite and operating-system caches are not cleared.
The common isolated non-corpus wrapper probe precedes measured database
creation and may warm code/import/regex/SQLite-library state. Every wrapper is
also run with one helper instrumented at a time: the baseline uses all seven
entries and the candidate all 22, with zero observed fallback in the registered
probe. Instrumentation is removed before timings.

The reference token vocabulary is initialized before worker token calls;
each fresh token-budget MCP server retains its natural first-call initialization
cost. Validation, hashing and ledger writes are outside query timers.
Only the direct response's diagnostic `latency_ms` field is excluded from
its output comparison. Query content, IDs, source positions, ordering, budget
results, cache outcome and MCP output remain checked. Fresh/unchanged ingestion
timers include complete batches and ordinary list appends; ordered return
values and hashes are preserved outside those timers.

All reductions below mean **100 × (1 − candidate / baseline)**. Positive
values mean lower elapsed time; negative values are retained regressions.
These are observed measurements, without a statistical-significance or
universal-optimality claim.

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


## Decision and unfavorable evidence

The final runtime provides lower pooled p50 and p95 in all eight registered
query cells. Default-budget p95 improves in 15/16 paired rounds; all-query p95
improves in 30/32 paired rounds. Every one of the 16 fresh/unchanged ingestion
batch pairs improves. This supports adopting the broader native implementation
for the tested workload, subject to complete delivery verification.

The decision explicitly retains the slower synthetic direct-character p95
round and the slower public token-budget MCP p50/p95 round. API import and
database opening are slightly slower; several RSS snapshots are higher and
the extension is larger. Public default-budget MCP initialization increases by
7.352 ms. Startup/resource comparisons have only four samples per side/cohort;
there is no claim of universal startup or memory improvement.

All earlier experiments remain available:

1. [Protocol3, run 43871304560](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43871304560)
   tested the first broad candidate `0be1f095`. Outputs were equivalent, but
   unchanged reingestion was 19.41%/21.41% slower on synthetic/public data.
   That candidate was rejected. Its original raw data and audit remain under
   [native-core/formal-run-1](../benchmarks/reports/native-core/formal-run-1/).
2. Local diagnostics identified repeated dynamic guard allocations and the
   slower attempted C text join. The final design reuses per-module immutable
   names while still performing live checks, and restores the original Python
   join. No negative local batch is removed from the
   [development record](native-core-development.md).
3. [Protocol4, run 43883672930](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43883672930)
   tested `e91183bf` and improved its pooled query/ingestion measurements, but
   native packaging exposed exact unpack-exception differences on CPython
   3.14/3.15. It was not released. Its complete results and audit remain under
   [native-core-refinement/formal-run-1](../benchmarks/reports/native-core-refinement/formal-run-1/).
4. The compatibility fix matches CPython 3.14/3.15's size-bearing exception
   messages for exact tuple/list/dict inputs, retaining iterator/subclass
   consumption and messages. New cases strengthen the original tests.
   A separate full protocol5 experiment then measured the exact repaired
   candidate; protocol4's favorable numbers were not substituted for it.

The older experiments used different CPUs/runtimes. Their absolute milliseconds
and percentage reductions are not added to the final EPYC 7763 results.
The recorded queries and archives are bounded development/regression workloads.
They do not prove faster execution for every input, archive size, platform,
concurrent client mix or model-generation task.

## Correctness and independent audit

The final source passes the 144-test native suite on Python 3.12:
142 passed with two explicit optional-tokenizer skips. The same exact
source/test files also pass ASAN/UBSAN execution without sanitizer diagnostics
or C compiler warnings. These suites cover Unicode, surrogate edge cases,
mapping positions, excerpt ties/floating-point order, dynamic helper mutations,
fallback types, original exceptions, segmentation/page identity and module
lifecycle. Three module-state cases run, including two shared-GIL
subinterpreters when the interpreter supplies the test module.
[Exact-source native receipt](../benchmarks/reports/native-core-compatibility/development/native-core-4390d013-144tests.json)
and [sanitizer receipt](../benchmarks/reports/native-core-compatibility/development/native-core-4390d013-asan-ubsan.json)
retain the detailed scope.

General CI now permanently covers Python 3.10, 3.12, 3.13, 3.14 and 3.15, plus
MCP, reader-browser, container and three installer operating systems: **11
required jobs**. The final-runtime
[CI run 43885311822](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43885311822)
passes all 11. Its full MCP suite runs 1,415 tests with 16 reported skips;
the Python 3.14/3.15 core jobs also run 1,415 tests each with 144 dependency/
interpreter-specific skips. A historical nine-job CI run cannot satisfy the
updated release gate. Publication requires fresh exact-final-commit CI.

The 26 frozen evaluator/preservation tests pass before formal execution.
The pre-registered independent standard-library auditor performs no new
application calls. It verifies the one downloaded ZIP, complete manifests,
Git source identities, binary/probe bindings, original attempt records,
call ledgers, every comparison and the exact recomputed summary. It covers
151 manifest files, 80 duplicate files, 71 frozen Git files, 156 publication-index
entries, 227,136 ledger events and all 56,784 pairs. Its hostile identity/API
counterexample checks were saved before the final result.

The [independent audit](../benchmarks/reports/native-core-compatibility/formal-run-1/independent-audit.json),
[receipt](../benchmarks/reports/native-core-compatibility/formal-run-1/audit-receipt.json),
[complete metrics JSON](../benchmarks/reports/native-core-compatibility/formal-run-1/metrics-extract.json)
and [frozen summary](../benchmarks/reports/native-core-compatibility/formal-run-1/summary.json)
make these checks reviewable. The immutable evidence branch also retains
the original reports, ledgers and source/build files, independently of
time-limited Actions artifacts. Hash equality verifies retained recorded
outputs; it does not recover source payload text from digests or prove every
possible input equivalent.

## Native packaging and installation

Native delivery remains pending. Two complete attempts using the frozen
4390 runtime did not satisfy the one-run/one-attempt 30-cell gate:
[43885419074](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43885419074)
finished with 28 wheels passed and two unallocated macOS ARM jobs cancelled;
[43888785867](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43888785867)
then also encountered an unallocated cancelled macOS ARM job. Their successful
packages are not mixed into a passing matrix.

The [runner investigation](../benchmarks/reports/native-core-compatibility/development/native-core-macos-runner-investigation.json)
first retained the second run when allocations resumed. After the additional
cancellation, the [recovery plan](../benchmarks/reports/native-core-compatibility/development/native-core-macos26-recovery-plan.json)
changes only the ARM hosted image label from macOS 15 to the officially
supported, explicit macOS 26 ARM image. All 30 cells, native architecture,
deployment-target rules, installed tests and exact receipt gates remain.
A fresh complete preparation must pass on that workflow. This does not change
the application runtime or add a performance experiment.

Publication still requires the final approved runtime/commit, all eleven
exact-commit CI jobs, a fresh full release matrix, verified assets and an
actual public default installation. v0.8.1 remains the published release at
this checkpoint.

Use the pinned v0.9.0 installer from the [deployment guide](deployment.md).
It creates an isolated environment, selects a wheel from that environment's
own compatibility tags and verifies the wheel and loaded extension hashes.
Default installation includes the MCP and client configuration dependencies.
Platforms without a matching native wheel use the compiler-free Python fallback;
free-threaded CPython also retains that fallback.

Using the interpreter path printed by the installer, check:

~~~bash
python -I -c "import memory_book; from memory_book._text_backend import BACKEND_NAME; print(memory_book.__version__, BACKEND_NAME)"
~~~

The native installation should print `0.9.0 native`.
`MEMORY_BOOK_TEXT_BACKEND=python` selects the reference; `native` requires the
extension; `auto` is the default. Source builds accept
`MEMORY_BOOK_BUILD_NATIVE=1` to require compilation, or `0` for the fallback.
The Docker build compiles and verifies its native stage. The extension targets
the supported GIL-enabled CPython matrix; this work makes no free-threaded
native support or parallel-execution claim.

Keep existing archive/config paths, update client/service launchers and restart
their processes when upgrading. Schema-4 archives need no new migration;
earlier archives follow the documented backup/schema-4 upgrade procedure.
Defaults remain 2400 characters and five results. The MIT project license is
unchanged.
