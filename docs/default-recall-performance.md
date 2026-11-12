# Default recall performance with identical payloads

The text-processing optimization reduced pooled p95 latency in all 12 measured configurations: **1.32%–13.65% for direct default recall** and **1.25%–9.50% for actual MCP stdio**. Fresh source ingestion improved by **25.04% on synthetic61** and **46.45% on public1015**. Complete returned payloads, source coordinates, indexed values, and reference-token counts stayed identical.

These results describe four balanced rounds on one hosted VM. They include three small single-round p95 regressions, an almost unchanged memory footprint, and a 0.085% public-corpus MCP startup increase. Changes close to 1% should be read with the measured variability in mind. This is a performance and equivalence experiment on old regression corpora; it establishes no new-domain retrieval quality or generated-answer improvement.

## Evidence and scope

- [Preregistered protocol](../benchmarks/experiments/round2-default-recall-performance-plan.json), saved before A/B timing.
- [Full compressed per-query report](../benchmarks/reports/round2-default-recall-43194664986-1.json.gz) and [complete summary](../benchmarks/reports/round2-default-recall-43194664986-1.summary.json).
- [Independent audit](../benchmarks/reports/round2-default-recall-audit-43196379004-1.json): 16 workers, **56,784 timed calls**, **3,549 unique query/configuration pairs per surface**, zero payload or source/index mismatches.
- [Measurement workflow](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43194664986), [successful post-write audit](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43196379004), and [candidate CI](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43194664868).

| Input | Queries | Sessions | Source characters | Role |
|---|---:|---:|---:|---|
| synthetic61 | 168 | 112 | 1,143,252 | Old development fixture, seed 61, eight projects |
| public1015 | 1,015 | 216 | 616,994 | Existing LoCoMo text-evidence regression split, all eligible query IDs |

Each engine processed every query at character budgets **2,000 / 4,000 / 8,000**, limit 5. There was no token cap in this default-interface experiment. Two reference tokenizers measured the returned MCP text and envelope outside latency timing.

Four independent worker rounds used A/B, B/A, A/B, B/A engine order, with the same deterministic shuffled query order inside each pair. Each worker created a fresh database and measured both interfaces. Direct recall used `MemoryBook(cache_size=0)` and `recall(use_cache=False)`. MCP used the actual official SDK and CLI subprocess; a committed external SQLite clear preceded **every** timed request, including duplicate question/project pairs. Clearing was excluded from timing; the server's normal cache write remained included. OS and SQLite caches were warm.

The direct response hash excludes only `latency_ms`; every other field is compared. The default compact MCP text and SDK response envelope are compared without dropping fields. Source loading, ingestion, MCP startup, payload hashing and tokenizer counting are measured separately or excluded from recall timing. The native process memory snapshots precede tokenizer/SDK imports; they include the loaded dataset and benchmark bookkeeping. MCP memory comes from the live child process.

Host: Ubuntu 24.04 hosted runner, four logical CPUs; Python **3.12.16**, SQLite **3.45.1**, MCP **1.30.0**, tiktoken **0.12.0**; `Linux-7.0.0-1017-azure-x86_64-with-glibc2.39`.

## What changed

Only `src/memory_book/text.py` and `src/memory_book/store.py` changed among the 17 runtime Python files. The other 15 runtime files, ranking policies, candidate limits, context budgets, source data and MCP format were unchanged.

1. After the existing whole-string normalization, camel-case splitting and case folding, ASCII text uses the equivalent `[a-z0-9]+` matcher. Stop-word behavior, duplicate tokens and token order stay the same.
2. Whole-string NFKD normalization retains canonical ordering. Category-`Mn` removal checks distinct decomposed characters once and deletes them through `str.translate`.
3. The existing excerpt source-map fallback reuses single-character folds within one excerpt. It preserves the historical per-character transform and every original position; it retains no text between calls.
4. Changed-session ingestion computes the identical directory index text once, then supplies the same value to every page in both FTS indexes.

Exhaustive ASCII character pairs, deterministic Unicode cases, canonical reordering, `Mn` versus combining-class distinctions, full source-offset comparisons, and directory rename/inheritance checks passed. The candidate's nine CI jobs passed, covering three Python versions, MCP, browser, container, and installers on three operating systems.

## All 12 pooled latency configurations

Milliseconds; all four rounds are pooled. Each synthetic cell has **672 calls per engine**; each public cell has **4,060**. A negative delta means lower latency.

| Cohort | Interface | Chars | p50 before | p50 after | p95 before | p95 after | Mean before | Mean after | p95 delta |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| synthetic61 | In process | 2000 | 5.809 | 5.260 | 16.453 | 14.696 | 7.676 | 7.002 | -10.68% |
| synthetic61 | In process | 4000 | 4.801 | 4.471 | 16.471 | 14.223 | 6.658 | 6.071 | -13.65% |
| synthetic61 | In process | 8000 | 4.683 | 4.276 | 9.941 | 9.809 | 5.571 | 5.148 | -1.32% |
| synthetic61 | MCP stdio | 2000 | 8.306 | 7.456 | 18.996 | 17.191 | 9.974 | 9.223 | -9.50% |
| synthetic61 | MCP stdio | 4000 | 6.929 | 6.677 | 18.841 | 17.156 | 8.807 | 8.260 | -8.95% |
| synthetic61 | MCP stdio | 8000 | 6.796 | 6.605 | 12.134 | 11.982 | 7.711 | 7.356 | -1.25% |
| public1015 | In process | 2000 | 4.890 | 4.461 | 7.059 | 6.602 | 5.072 | 4.637 | -6.47% |
| public1015 | In process | 4000 | 4.198 | 3.496 | 5.902 | 5.141 | 4.336 | 3.645 | -12.89% |
| public1015 | In process | 8000 | 4.197 | 3.477 | 5.858 | 5.125 | 4.316 | 3.631 | -12.51% |
| public1015 | MCP stdio | 2000 | 7.042 | 6.601 | 9.255 | 8.830 | 7.217 | 6.780 | -4.59% |
| public1015 | MCP stdio | 4000 | 6.363 | 5.667 | 8.146 | 7.482 | 6.494 | 5.825 | -8.15% |
| public1015 | MCP stdio | 8000 | 6.339 | 5.633 | 8.097 | 7.379 | 6.478 | 5.789 | -8.88% |

## Every round, including regressions

Each row uses its full registered query set. The percentages are `100 × (candidate / baseline − 1)`, computed separately for p50, p95 and mean. The full report retains every absolute timing sample and the summary retains every round's absolute percentiles. No fastest-round selection is used.

| Cohort | Interface | Chars | Round | p50 delta | p95 delta | Mean delta |
|---|---|---:|---:|---:|---:|---:|
| synthetic61 | In process | 2000 | 0 | -8.37% | -7.97% | -7.54% |
| synthetic61 | In process | 2000 | 1 | -11.19% | -10.89% | -9.00% |
| synthetic61 | In process | 2000 | 2 | -10.11% | -11.66% | -9.52% |
| synthetic61 | In process | 2000 | 3 | -10.06% | -11.09% | -9.05% |
| synthetic61 | In process | 4000 | 0 | -6.28% | -11.21% | -7.61% |
| synthetic61 | In process | 4000 | 1 | -8.78% | -14.99% | -9.43% |
| synthetic61 | In process | 4000 | 2 | -7.80% | -15.49% | -9.46% |
| synthetic61 | In process | 4000 | 3 | -5.03% | -13.09% | -8.74% |
| synthetic61 | In process | 8000 | 0 | -7.81% | 0.30% | -6.37% |
| synthetic61 | In process | 8000 | 1 | -8.92% | -1.51% | -7.85% |
| synthetic61 | In process | 8000 | 2 | -7.64% | -2.31% | -8.53% |
| synthetic61 | In process | 8000 | 3 | -9.29% | -1.29% | -7.60% |
| synthetic61 | MCP stdio | 2000 | 0 | -12.13% | -11.26% | -8.34% |
| synthetic61 | MCP stdio | 2000 | 1 | -7.16% | -7.68% | -6.53% |
| synthetic61 | MCP stdio | 2000 | 2 | -7.54% | -8.22% | -6.21% |
| synthetic61 | MCP stdio | 2000 | 3 | -10.76% | -9.58% | -9.01% |
| synthetic61 | MCP stdio | 4000 | 0 | -5.62% | -11.40% | -6.71% |
| synthetic61 | MCP stdio | 4000 | 1 | -6.16% | -9.83% | -7.51% |
| synthetic61 | MCP stdio | 4000 | 2 | -2.01% | -6.11% | -4.57% |
| synthetic61 | MCP stdio | 4000 | 3 | -1.84% | -9.21% | -6.04% |
| synthetic61 | MCP stdio | 8000 | 0 | -2.12% | 1.12% | -3.35% |
| synthetic61 | MCP stdio | 8000 | 1 | -5.39% | -2.41% | -5.77% |
| synthetic61 | MCP stdio | 8000 | 2 | -3.18% | 0.32% | -3.53% |
| synthetic61 | MCP stdio | 8000 | 3 | -3.53% | -2.50% | -5.75% |
| public1015 | In process | 2000 | 0 | -9.10% | -6.95% | -8.79% |
| public1015 | In process | 2000 | 1 | -9.05% | -5.78% | -8.55% |
| public1015 | In process | 2000 | 2 | -8.82% | -6.48% | -8.54% |
| public1015 | In process | 2000 | 3 | -8.50% | -6.55% | -8.39% |
| public1015 | In process | 4000 | 0 | -16.06% | -11.00% | -15.18% |
| public1015 | In process | 4000 | 1 | -16.39% | -12.17% | -15.69% |
| public1015 | In process | 4000 | 2 | -17.11% | -13.79% | -16.25% |
| public1015 | In process | 4000 | 3 | -17.35% | -14.11% | -16.68% |
| public1015 | In process | 8000 | 0 | -17.58% | -13.45% | -16.31% |
| public1015 | In process | 8000 | 1 | -17.13% | -12.51% | -15.81% |
| public1015 | In process | 8000 | 2 | -16.33% | -11.84% | -15.33% |
| public1015 | In process | 8000 | 3 | -17.17% | -11.83% | -16.03% |
| public1015 | MCP stdio | 2000 | 0 | -7.30% | -5.14% | -6.82% |
| public1015 | MCP stdio | 2000 | 1 | -6.96% | -5.60% | -7.23% |
| public1015 | MCP stdio | 2000 | 2 | -4.98% | -3.41% | -4.68% |
| public1015 | MCP stdio | 2000 | 3 | -5.69% | -3.33% | -5.44% |
| public1015 | MCP stdio | 4000 | 0 | -11.79% | -9.01% | -11.06% |
| public1015 | MCP stdio | 4000 | 1 | -9.24% | -4.81% | -8.36% |
| public1015 | MCP stdio | 4000 | 2 | -12.08% | -9.52% | -11.45% |
| public1015 | MCP stdio | 4000 | 3 | -10.75% | -8.80% | -10.35% |
| public1015 | MCP stdio | 8000 | 0 | -11.21% | -8.52% | -10.71% |
| public1015 | MCP stdio | 8000 | 1 | -9.77% | -6.64% | -9.43% |
| public1015 | MCP stdio | 8000 | 2 | -11.45% | -10.02% | -10.85% |
| public1015 | MCP stdio | 8000 | 3 | -11.82% | -10.20% | -11.56% |

The three positive p95 deltas are synthetic61 at 8,000 characters: direct recall round 0 **+0.30%**, MCP round 0 **+1.12%**, and MCP round 2 **+0.32%**. Their pooled p95 deltas remain −1.32% and −1.25%. These small differences do not establish a universal latency guarantee.

## Ingestion, unchanged replay and startup

Means across four fresh worker processes, in milliseconds. Unchanged replay still runs the existing source normalization and segmentation path; this patch did not introduce a bypass for duplicate imports or change transaction semantics.

| Cohort | Engine | Fresh ingestion mean | Unchanged replay mean | MCP initialize mean |
|---|---|---:|---:|---:|
| synthetic61 | baseline | 1137.761 | 135.172 | 637.273 |
| synthetic61 | candidate | 852.810 | 104.840 | 632.958 |
| public1015 | baseline | 1468.589 | 518.912 | 646.130 |
| public1015 | candidate | 786.435 | 200.415 | 646.676 |

Fresh-ingestion changes are **−25.04% / −46.45%** for synthetic/public. Unchanged-replay changes are **−22.44% / −61.38%**. Startup changes are **−0.68% / +0.085%**; no startup improvement is claimed for public1015.

All per-round resource timings are retained below:

| Cohort | Engine | Round | Fresh ingestion ms | Unchanged replay ms | MCP initialize ms |
|---|---|---:|---:|---:|---:|
| synthetic61 | baseline | 0 | 1138.869 | 134.985 | 639.541 |
| synthetic61 | candidate | 0 | 863.832 | 104.905 | 634.582 |
| public1015 | baseline | 0 | 1490.450 | 518.188 | 638.348 |
| public1015 | candidate | 0 | 786.916 | 200.572 | 636.250 |
| synthetic61 | candidate | 1 | 843.851 | 104.678 | 630.097 |
| synthetic61 | baseline | 1 | 1140.207 | 135.532 | 635.394 |
| public1015 | candidate | 1 | 783.509 | 200.755 | 641.842 |
| public1015 | baseline | 1 | 1455.140 | 520.046 | 653.995 |
| synthetic61 | baseline | 2 | 1135.166 | 135.430 | 638.364 |
| synthetic61 | candidate | 2 | 852.490 | 105.087 | 635.263 |
| public1015 | baseline | 2 | 1462.340 | 518.210 | 639.294 |
| public1015 | candidate | 2 | 787.653 | 200.873 | 672.620 |
| synthetic61 | candidate | 3 | 851.068 | 104.690 | 631.891 |
| synthetic61 | baseline | 3 | 1136.801 | 134.742 | 635.791 |
| public1015 | candidate | 3 | 787.663 | 199.461 | 635.991 |
| public1015 | baseline | 3 | 1466.427 | 519.206 | 652.883 |

## Memory and storage

MiB use 1,048,576 bytes. These are Linux `/proc` current-RSS and process high-water observations after the calls; they are not system-wide allocation peaks. Memory varied slightly across paired workers and is effectively unchanged at this scale.

| Cohort | Engine | Round | Direct process RSS MiB | Direct HWM MiB | MCP child RSS MiB | MCP child HWM MiB |
|---|---|---:|---:|---:|---:|---:|
| synthetic61 | baseline | 0 | 48.215 | 50.719 | 61.625 | 61.625 |
| synthetic61 | candidate | 0 | 47.215 | 50.117 | 61.828 | 61.828 |
| public1015 | baseline | 0 | 50.953 | 58.500 | 61.824 | 61.824 |
| public1015 | candidate | 0 | 51.031 | 58.676 | 61.813 | 61.813 |
| synthetic61 | candidate | 1 | 47.148 | 49.598 | 61.613 | 61.613 |
| synthetic61 | baseline | 1 | 47.324 | 49.871 | 61.816 | 61.816 |
| public1015 | candidate | 1 | 51.078 | 58.867 | 61.793 | 61.793 |
| public1015 | baseline | 1 | 51.105 | 58.906 | 61.801 | 61.801 |
| synthetic61 | baseline | 2 | 47.410 | 49.727 | 61.566 | 61.566 |
| synthetic61 | candidate | 2 | 47.348 | 49.785 | 61.309 | 61.359 |
| public1015 | baseline | 2 | 50.922 | 58.660 | 61.723 | 61.723 |
| public1015 | candidate | 2 | 50.902 | 58.605 | 61.836 | 61.836 |
| synthetic61 | candidate | 3 | 48.168 | 50.645 | 61.750 | 61.750 |
| synthetic61 | baseline | 3 | 48.223 | 50.777 | 61.754 | 61.754 |
| public1015 | candidate | 3 | 51.027 | 58.641 | 61.691 | 61.691 |
| public1015 | baseline | 3 | 51.066 | 58.867 | 61.699 | 61.699 |

The database is identical in logical size for both engines and all rounds after the direct-call checkpoint: **20,508,672 bytes** for synthetic61 and **12,881,920 bytes** for public1015. The seven indexed/content projections also have identical hashes across engines and rounds. The full summary includes live DB/WAL/SHM sizes immediately after ingestion, after the native checkpoint, and after MCP calls; cache/WAL growth is separate from the source index.

## MCP output costs

All complete response hashes and reference-token counts are identical between engines. The following means therefore apply to both engines; response text and response envelope are distinct surfaces. Counts use exact tiktoken 0.12.0 encodings and do not imply model-provider billing.

| Cohort | Chars | Encoding | Context tokens mean | Response text tokens mean | Envelope tokens mean | Envelope tokens p95 |
|---|---:|---|---:|---:|---:|---:|
| synthetic61 | 2000 | cl100k_base | 951.589 | 1347.399 | 1429.685 | 2032.000 |
| synthetic61 | 2000 | o200k_base | 781.345 | 1185.435 | 1263.310 | 1702.000 |
| synthetic61 | 4000 | cl100k_base | 1426.756 | 1841.030 | 1943.881 | 3548.000 |
| synthetic61 | 4000 | o200k_base | 1162.435 | 1584.845 | 1683.458 | 2786.000 |
| synthetic61 | 8000 | cl100k_base | 1520.190 | 1929.982 | 2037.738 | 4257.000 |
| synthetic61 | 8000 | o200k_base | 1235.946 | 1653.875 | 1757.393 | 3305.000 |
| public1015 | 2000 | cl100k_base | 607.363 | 1129.636 | 1198.444 | 1313.000 |
| public1015 | 2000 | o200k_base | 594.877 | 1123.432 | 1187.098 | 1298.000 |
| public1015 | 4000 | cl100k_base | 866.599 | 1480.638 | 1567.385 | 1755.000 |
| public1015 | 4000 | o200k_base | 844.521 | 1464.844 | 1546.255 | 1730.000 |
| public1015 | 8000 | cl100k_base | 867.074 | 1480.874 | 1567.652 | 1755.000 |
| public1015 | 8000 | o200k_base | 844.986 | 1465.070 | 1546.512 | 1730.000 |

This performance change supplies **zero token savings**: unchanged output is an explicit acceptance condition.

## Provenance and audit correction

| Item | Identity |
|---|---|
| Baseline commit | `cb7486b4937a3ecb7ccbf94a746c0bbbf44eb41f` |
| Implementation commit | `e7a92e43835881099ff177935e81a4abc32f8e81` |
| Measured candidate + controller | `841cedb0cc52ff2b199e7c24832b64973a2e306d` |
| Original result commit | `558bac15d09dbd7ec659d97c0b686a74097f91f1` |
| Audit repair commit | `209a42b582c1045ec179dedf1734ffd63f441168` |
| Successful independent audit commit | `c650326f509b0100b245cd5b486ef7ff5d368795` |
| Baseline runtime SHA-256 | `6fdad7b9bf0eef50ec925ceeed3ca45fe84d2eb22973c753118df2d0f67f6ba2` |
| Candidate runtime SHA-256 | `a7c3a3e39677770809022a3289d8337c54b3bfec992cf1fef4779fd081fc8bdb` |
| Uncompressed report SHA-256 | `ded0d6908fd1f5926b3ac379e496c9e05df7fea63cb0ed5e1d3f1b8b93a6d77d` |
| Compressed report SHA-256 | `dfd087e2c51bb52a41a944df660f25d71ff043ba8b4e7e0f4ad4a584bb61878d` |
| Protocol SHA-256 | `78f533c0ebd280bf9312bbbb5fc39e58e6705e2e2de959c04777ee0834e77a82` |

The measurement step and its complete-payload gate passed. Its first post-write audit compared a matrix list reconstructed from dictionary insertion order. Sorted-key JSON reordered the cohort mapping, which changed list order while leaving every cell unchanged. The [original attempt marker](../benchmarks/reports/round2-default-recall-completion-43194664986-1.json) remains preserved with that failed audit status.

The follow-up auditor uses the preregistered cohort order, has a JSON-roundtrip regression test, and rechecks all 12 cells, all source/payload gates, exact gzip/plaintext hashes, the original evaluator/plan Git blobs, and summary reconstruction. It passed on the **same saved measurement** with **zero retrieval calls**. No timing sample, runtime source file, metric or historical result was replaced.

## Reproduce

Use separate worktrees for the frozen baseline and candidate. Install the candidate with `.[mcp,clients,benchmark]` plus `mcp==1.30.0`, and obtain the exact old LoCoMo file recorded in [the split manifest](../benchmarks/locomo_split.json). Its external data license remains separate from this repository's code license. The [workflow](../.github/workflows/round2-default-recall-validation.yml) verifies its byte count and SHA-256 before running.

```sh
python scripts/benchmark_default_recall.py \
  --baseline-src /absolute/baseline/src \
  --candidate-src /absolute/candidate/src \
  --locomo-path /absolute/data/locomo10.json \
  --output benchmarks/reports/default-recall-NEW-RUN.json.gz
```

To verify the published measurement without executing retrieval:

```sh
python scripts/audit_default_recall_report.py \
  --prefix benchmarks/reports/round2-default-recall-43194664986-1 \
  --candidate-commit 841cedb0cc52ff2b199e7c24832b64973a2e306d \
  --output /absolute/new-output/audit.json
```

The source package must match its Git commit exactly; existing output paths are rejected. The benchmark does not download or evaluate the new blinded cohort. Native token-capped assembly and optional semantic retrieval have separate registered evaluations.

