# Bounded novelty: a separate old-data development probe

**Final adoption decision: neither experimental formula is adopted.** Removing the novelty bonus is rejected by this development probe. The 0.25 cap passes the old-data screen below, then fails the separately registered [strict Hotpot256 regression qualification](novelty-cap-qualification.md) in all eight small-budget default/Q2 settings. The default runtime and completed round-two comparison remain unchanged.

The original development result is preserved: the cap adds three complete source-evidence hits in old LoCoMo at 512 tokens, with no annotation or complete-question losses observed in these four old cohorts. The other eleven cohort/budget cells are unchanged on both quality metrics. This is a small regression-data signal, not evidence of general superiority, generated-answer accuracy or a speed improvement.

The [preregistered plan](../benchmarks/experiments/novelty-probe-plan.json) was saved at [`cdf19eb`](https://github.com/Afloat16/AI-Memory-Book/commit/cdf19eb7de1339702231fe2ae0fbb70d96b8dacf) before source binding or measurement. The [complete raw records](../benchmarks/reports/novelty-probe-43214192647-1.json.gz), [summary](../benchmarks/reports/novelty-probe-43214192647-1.summary.json), [original Markdown](../benchmarks/reports/novelty-probe-43214192647-1.md), [preserved failed completion marker](../benchmarks/reports/novelty-probe-43214192647-1.completion.json) and [supplemental audit](../benchmarks/reports/novelty-probe-43214192647-1.supplemental-audit.json) retain all outcomes. The measure step completed; its final historical audit failed only because the two final candidate bullets were rendered in a different order after JSON serialization. That failure is preserved and explained below.

## Fixed scope and source identity

Twelve sequential, isolated cohort/mode workers ran on one hosted VM, using one pass, top 5, 8,000 characters, cl100k_base token caps of 512/1024/2048, lexical search, coverage disabled, and no query-result cache. Every worker used its exact source commit and a freshly ingested archive. Mode order rotated by cohort; the query order was fixed with seed 61. The experiment made **12,123 native calls**: (168 + 36 + 1,015 + 128) × 3 budgets × 3 modes. It reused the frozen native source-span scoring and token assembly helpers without modifying them.

The three formulas multiply the existing relevance score by 1 + the indicated bonus. The single bounded candidate was specified in advance: it retains smaller existing bonuses and limits the multiplier to 1.25. A page with a positive pre-bonus relevance more than 25% greater cannot be overtaken solely by this bonus. This is a mathematical bound on this greedy selection step, not a claim about relevance quality.

| Mode | Bonus | Exact runtime commit | Runtime SHA-256 |
|---|---|---|---|
| `default` | newly covered terms / query terms | [`cbf6260`](https://github.com/Afloat16/AI-Memory-Book/commit/cbf626037b42f11f8bc5b6d46f56caac771e54ba) | `d4558f6649762a09e10ad2906c06ab36b21786ef32be131906fc3213cf1a3c57` |
| `no_novelty` | 0 | [`38d4c5c`](https://github.com/Afloat16/AI-Memory-Book/commit/38d4c5cf678907974035923ea1c179d50c5769c8) | `62dca4f100b16060bbbc1761662af4f961a69df4d33d5e1ab8777073956de31b` |
| `capped_novelty_025` | min(0.25, newly covered terms / query terms) | [`506f1c6`](https://github.com/Afloat16/AI-Memory-Book/commit/506f1c6140e7ff4a1106f05e049b5285438e7268) | `8dbebff4035e653de8a6ffa1e01e0f8201b9d29f53df9f78c92f3e55e8b465f1` |

Both experimental source commits change only the one registered expression in `src/memory_book/store.py`; the other 16 tracked runtime files are identical. The source SHA covers the 16 Python files by sorted relative path and bytes; the file-identity check also includes the static reader HTML, for 17 runtime files total. The first selected page, original scores and tie order, current-query revision handling, 96-candidate route limit, `limit * 4` novelty pool, exact/stem fusion, field weights, token packing and source coordinates are unchanged. The tools and evidence branch itself retains the baseline product source. See the [binding](../benchmarks/experiments/novelty-probe-binding.json) and [supplemental source audit](../benchmarks/reports/novelty-probe-43214192647-1.supplemental-audit.json).

| Old cohort | Queries | Answerable | Required evidence annotations | Corpus fingerprint |
|---|---:|---:|---:|---|
| synthetic61 | 168 | 152 | 176 | `117cd11814cfa5ffba3c2a6f984b0fbdf05767ee99034c0da56c610cf0069b26` |
| authored36 | 36 | 30 | 36 | `ecc46c474d5184995938419fa985b8e08c0ddb51560da49990247465db6db0b0` |
| public1015 | 1015 | 649 | 788 | `8910da0c1472312fed23b8c7af66d206c872ad41a855f584859f2b446855a857` |
| hotpot128 | 128 | 128 | 306 | `0791515aca6bccf19a97895cad681e06a07536d6c08050d54189cc64cb819822` |

### New Hotpot256 was excluded

The experiment does not import `round2_data` or open the new 256 manifest. Its pinned preparation code downloads and verifies the original Parquet, filters it with the **old 128 IDs before normalization and Dataset conversion**, and validates the original old-cohort fingerprint. The recorded query IDs for all three Hotpot workers match the old manifest exactly; the supplemental audit verifies that equality without loading question text or any new cohort manifest or result. Only those 128 old question rows become a Dataset. The [pinned preparation and loader](https://github.com/Afloat16/AI-Memory-Book/blob/848c0eb812e87e1cb5e3fb715c48459dcd1c4de8/scripts/run_novelty_probe.py) and the recorded cohort hashes provide source and data provenance, not an operating-system file-access trace.

## Quality: every cohort and budget

Each triple below is **default / no novelty / cap 0.25**. Complete evidence uses answerable questions as the denominator; annotation recall uses all required evidence annotations. These are retrieval/source-evidence scores, not final-answer accuracy. Values are percentages; exact integer counts, float values and per-question records remain in the raw and summary.

| Cohort | Token cap | Complete evidence % (D / N / C) | Annotation recall % (D / N / C) |
|---|---:|---:|---:|
| synthetic61 | 512 | 85.5263 / 84.2105 / 85.5263 | 86.3636 / 84.0909 / 86.3636 |
| synthetic61 | 1024 | 92.1053 / 91.4474 / 92.1053 | 93.1818 / 92.6136 / 93.1818 |
| synthetic61 | 2048 | 92.1053 / 91.4474 / 92.1053 | 93.1818 / 92.6136 / 93.1818 |
| authored36 | 512 | 86.6667 / 86.6667 / 86.6667 | 88.8889 / 88.8889 / 88.8889 |
| authored36 | 1024 | 86.6667 / 86.6667 / 86.6667 | 88.8889 / 88.8889 / 88.8889 |
| authored36 | 2048 | 86.6667 / 86.6667 / 86.6667 | 88.8889 / 88.8889 / 88.8889 |
| public1015 | 512 | 66.4099 / 67.4884 / 66.8721 | 62.1827 / 63.0711 / 62.5635 |
| public1015 | 1024 | 72.8814 / 73.0354 / 72.8814 | 69.5431 / 69.5431 / 69.5431 |
| public1015 | 2048 | 72.8814 / 73.1895 / 72.8814 | 69.5431 / 69.6701 / 69.5431 |
| hotpot128 | 512 | 35.1562 / 28.9062 / 35.1562 | 66.9935 / 64.3791 / 66.9935 |
| hotpot128 | 1024 | 48.4375 / 44.5312 / 48.4375 | 74.5098 / 72.5490 / 74.5098 |
| hotpot128 | 2048 | 48.4375 / 44.5312 / 48.4375 | 74.5098 / 72.5490 / 74.5098 |

For cap 0.25 at LoCoMo/512, complete evidence is **431/649 → 434/649**, or **66.4098613251% → 66.8721109399%** (+0.4622496148 percentage points). Annotation recall is **490/788 → 493/788**, or **62.1827411168% → 62.5634517766%** (+0.3807106599 points). All three added annotations occur without an annotation loss; all three newly complete questions occur without a complete-question loss. Other eleven cells preserve both aggregate metrics. The supplementary MRR metric also changes in LoCoMo: 0.6361068310 → 0.6373908577 at 512, and 0.6547252183 → 0.6552645095 at both larger budgets; it is unchanged in the other nine cells. MRR was not used to relax the registered screen. Raw ranking and changed-context records remain available; quality equality does not mean payload equality.

### Paired gains and losses are not pooled away

Counts refer to query/budget samples, so the same question can appear at more than one budget. The raw `comparisons[].paired_changes` preserves every original ID and annotation index. A changed context is not necessarily a quality change.

| Cohort | Candidate | Cap | Complete gains / losses | Annotation gains / losses | Changed contexts |
|---|---|---:|---:|---:|---:|
| synthetic61 | none | 512 | 0 / 2 | 0 / 4 | 24 |
| synthetic61 | none | 1024 | 0 / 1 | 0 / 1 | 42 |
| synthetic61 | none | 2048 | 0 / 1 | 0 / 1 | 46 |
| synthetic61 | cap 0.25 | 512 | 0 / 0 | 0 / 0 | 0 |
| synthetic61 | cap 0.25 | 1024 | 0 / 0 | 0 / 0 | 0 |
| synthetic61 | cap 0.25 | 2048 | 0 / 0 | 0 / 0 | 0 |
| authored36 | none | 512 | 0 / 0 | 0 / 0 | 1 |
| authored36 | none | 1024 | 0 / 0 | 0 / 0 | 1 |
| authored36 | none | 2048 | 0 / 0 | 0 / 0 | 1 |
| authored36 | cap 0.25 | 512 | 0 / 0 | 0 / 0 | 0 |
| authored36 | cap 0.25 | 1024 | 0 / 0 | 0 / 0 | 0 |
| authored36 | cap 0.25 | 2048 | 0 / 0 | 0 / 0 | 0 |
| public1015 | none | 512 | 12 / 5 | 13 / 6 | 272 |
| public1015 | none | 1024 | 1 / 0 | 1 / 1 | 379 |
| public1015 | none | 2048 | 2 / 0 | 2 / 1 | 379 |
| public1015 | cap 0.25 | 512 | 3 / 0 | 3 / 0 | 10 |
| public1015 | cap 0.25 | 1024 | 0 / 0 | 0 / 0 | 11 |
| public1015 | cap 0.25 | 2048 | 0 / 0 | 0 / 0 | 11 |
| hotpot128 | none | 512 | 0 / 8 | 2 / 10 | 30 |
| hotpot128 | none | 1024 | 0 / 5 | 0 / 6 | 42 |
| hotpot128 | none | 2048 | 0 / 5 | 0 / 6 | 42 |
| hotpot128 | cap 0.25 | 512 | 0 / 0 | 0 / 0 | 2 |
| hotpot128 | cap 0.25 | 1024 | 0 / 0 | 0 / 0 | 2 |
| hotpot128 | cap 0.25 | 2048 | 0 / 0 | 0 / 0 | 2 |

Cap 0.25 has **3 complete gains / 0 losses**, **3 annotation gains / 0 losses**, and 38 changed-context samples across its 4,041 calls. No novelty has **15 complete gains / 27 losses** and **18 annotation gains / 36 losses**. Its positive LoCoMo aggregate therefore does not offset the regressions on synthetic and old Hotpot cases.

### The declared 512-token group gate

The plan required no complete-evidence or annotation-recall decline in each of the 12 cohort/budget cells; no increase in unsupported nonempty counts; and no decline in the four named diagnostic groups at 512 tokens whenever a group has at least 10 queries. At least one aggregate quality value must improve. It is a conservative development screen, not a statistical test.

Each triple is again **default / no novelty / cap 0.25**. All eight represented group cells with n ≥ 10 pass for the cap. The six smaller represented group cells also have no cap quality loss; absent groups have no observation. All original category and diagnostic groups, at all budgets, remain in the summary and raw. No cap decrease occurs in either quality metric in any recorded group, including small groups.

| Cohort | Group | n | In declared n ≥ 10 gate? | Complete evidence % (D / N / C) | Annotation recall % (D / N / C) |
|---|---|---:|---|---:|---:|
| synthetic61 | Low lexical overlap ≤ 0.25 | 32 | Yes | 75.0000 / 75.0000 / 75.0000 | 80.0000 / 80.0000 / 80.0000 |
| synthetic61 | Multiple required annotations | 24 | Yes | 41.6667 / 33.3333 / 41.6667 | 66.6667 / 58.3333 / 66.6667 |
| synthetic61 | Cross-session | 8 | No; retained | 100.0000 / 100.0000 / 100.0000 | 100.0000 / 100.0000 / 100.0000 |
| synthetic61 | Cross-chapter | 0 | No observation | — | — |
| authored36 | Low lexical overlap ≤ 0.25 | 8 | No; retained | 50.0000 / 50.0000 / 50.0000 | 60.0000 / 60.0000 / 60.0000 |
| authored36 | Multiple required annotations | 6 | No; retained | 100.0000 / 100.0000 / 100.0000 | 100.0000 / 100.0000 / 100.0000 |
| authored36 | Cross-session | 6 | No; retained | 100.0000 / 100.0000 / 100.0000 | 100.0000 / 100.0000 / 100.0000 |
| authored36 | Cross-chapter | 6 | No; retained | 100.0000 / 100.0000 / 100.0000 | 100.0000 / 100.0000 / 100.0000 |
| public1015 | Low lexical overlap ≤ 0.25 | 326 | Yes | 46.0123 / 46.6258 / 46.6258 | 41.1622 / 41.8886 / 41.6465 |
| public1015 | Multiple required annotations | 104 | Yes | 16.3462 / 16.3462 / 17.3077 | 31.2757 / 31.2757 / 31.6872 |
| public1015 | Cross-session | 76 | Yes | 10.5263 / 11.8421 / 11.8421 | 26.7380 / 27.8075 / 27.2727 |
| public1015 | Cross-chapter | 0 | No observation | — | — |
| hotpot128 | Low lexical overlap ≤ 0.25 | 3 | No; retained | 0.0000 / 0.0000 / 0.0000 | 50.0000 / 50.0000 / 50.0000 |
| hotpot128 | Multiple required annotations | 128 | Yes | 35.1562 / 28.9062 / 35.1562 | 66.9935 / 64.3791 / 66.9935 |
| hotpot128 | Cross-session | 128 | Yes | 35.1562 / 28.9062 / 35.1562 | 66.9935 / 64.3791 / 66.9935 |
| hotpot128 | Cross-chapter | 128 | Yes | 35.1562 / 28.9062 / 35.1562 | 66.9935 / 64.3791 / 66.9935 |

The saved screen rejects no novelty with **20 declared loss checks**. Across every recorded group and all budgets, it has 62 decreasing group/metric cells (overlapping groups are not independent failures). Cap 0.25 has zero declared loss checks and two improved aggregate metric cells, both at LoCoMo/512. The [saved screening decision](../benchmarks/reports/novelty-probe-43214192647-1.summary.json) is recomputed unchanged by the supplemental audit.

### Unsupported questions remain a limitation

All three modes and all three budgets return the same nonempty counts below. A nonempty unsupported context is retained as a negative result; it is not evidence of successful abstention. Hotpot has no unsupported cases, so that rate is not applicable.

| Cohort | Unsupported queries | Nonempty responses at each budget, every mode | Rate |
|---|---:|---:|---:|
| synthetic61 | 16 | 12 | 75.00% |
| authored36 | 6 | 2 | 33.33% |
| public1015 | 366 | 366 | 100.00% |
| hotpot128 | 0 | 0 | N/A |

## All development cost observations

These are one-pass observations on the same hosted VM, not repeated paired latency evidence. The native call timer includes recall and token assembly; ingestion, source scoring, token recounting and report writing are outside it. Each worker has fresh process/index state, and mode order rotates across cohorts rather than alternating per query. Scheduling, warmup and order effects remain possible. Do not interpret small differences as a proven performance improvement or regression.

Environment recorded by the run: Python 3.12.16, SQLite 3.45.1, tiktoken 0.12.0, Linux x86_64, four logical CPUs. The following table retains every configured percentile, including slower cap observations. Each triple is **default / no novelty / cap 0.25**, in milliseconds.

| Cohort | Cap | Mean ms (D / N / C) | p50 ms (D / N / C) | p95 ms (D / N / C) | p99 ms (D / N / C) |
|---|---:|---:|---:|---:|---:|
| synthetic61 | 512 | 10.9391 / 10.9014 / 10.9226 | 10.0032 / 9.9979 / 9.8952 | 21.4283 / 21.3025 / 21.2536 | 22.2860 / 21.9806 / 22.0550 |
| synthetic61 | 1024 | 10.2302 / 10.1787 / 10.2484 | 8.7718 / 8.7773 / 8.8509 | 23.7420 / 23.8530 / 23.8433 | 24.4196 / 24.4972 / 24.5631 |
| synthetic61 | 2048 | 9.3958 / 9.1657 / 9.1921 | 7.8079 / 7.7090 / 7.7150 | 21.2899 / 21.3642 / 21.2691 | 22.6943 / 22.6323 / 21.7597 |
| authored36 | 512 | 1.5057 / 1.4096 / 1.4128 | 1.3884 / 1.2914 / 1.2871 | 2.4428 / 2.3116 / 2.3418 | 4.5307 / 4.3667 / 4.3938 |
| authored36 | 1024 | 1.3234 / 1.2908 / 1.2853 | 1.3089 / 1.2864 / 1.2736 | 2.2226 / 2.2082 / 2.2128 | 2.2828 / 2.2309 / 2.2475 |
| authored36 | 2048 | 1.3280 / 1.2847 / 1.2854 | 1.2804 / 1.2399 / 1.2496 | 2.2595 / 2.1835 / 2.2113 | 2.2795 / 2.2281 / 2.2401 |
| public1015 | 512 | 6.2951 / 6.2767 / 6.3637 | 6.1770 / 6.1583 / 6.2393 | 7.9426 / 7.8663 / 7.9986 | 8.7344 / 8.4799 / 8.6659 |
| public1015 | 1024 | 5.4260 / 5.3949 / 5.4693 | 5.2297 / 5.2159 / 5.2724 | 6.9412 / 6.9235 / 6.9718 | 7.6044 / 7.4885 / 7.6885 |
| public1015 | 2048 | 5.4708 / 5.4814 / 5.4569 | 5.2871 / 5.2870 / 5.2826 | 7.0057 / 7.0125 / 6.9218 | 7.7080 / 7.6838 / 7.5079 |
| hotpot128 | 512 | 6.5147 / 6.4157 / 6.4895 | 6.3640 / 6.2872 / 6.3530 | 9.1955 / 9.0827 / 9.0638 | 10.0710 / 9.6410 / 9.7948 |
| hotpot128 | 1024 | 5.6649 / 5.6528 / 5.6886 | 5.5399 / 5.5542 / 5.5496 | 8.0963 / 8.1021 / 8.2007 | 8.4061 / 8.4880 / 8.3984 |
| hotpot128 | 2048 | 5.6913 / 5.6520 / 5.6197 | 5.5478 / 5.5663 / 5.5622 | 8.1303 / 8.1311 / 7.9272 | 9.2200 / 8.4611 / 8.3843 |

Cap p95 is higher in four cells: synthetic/1024 (+0.427%), LoCoMo/512 (+0.706%), LoCoMo/1024 (+0.440%) and Hotpot/1024 (+1.290%). Other cap p95 observations range from −0.098% to −4.136%. These figures justify preserving complete observations and requiring a separate repeated performance validation; they do not establish a speed gain.

### Recorded index construction time

The one ingestion observation for each isolated worker is also retained. Each worker uses that same index for its three budgets. These times are excluded from the recall timer, and this formula-only candidate does not change the ingestion implementation. The unexpectedly larger synthetic cap observation is therefore preserved without attributing it to the candidate; no repeat was run to select a preferred value. All three modes have identical recorded indexed-content digests for each cohort. This probe does not measure process RSS, database bytes or an end-to-end model workflow.

| Cohort | Ingestion ms (default / no novelty / cap 0.25) |
|---|---:|
| synthetic61 | 836.415 / 842.652 / 1778.317 |
| authored36 | 30.515 / 32.436 / 30.604 |
| public1015 | 777.660 / 795.128 / 783.610 |
| hotpot128 | 1813.176 / 1782.781 / 1788.133 |

In particular, synthetic cap ingestion is 1,778.317 ms versus 836.415 ms for the default, despite identical ingestion source and indexed contents. This single observation is not evidence of a reproducible slowdown or improvement.

### Context and full native-response reference tokens

Each triple is **default / no novelty / cap 0.25**. The token budget is enforced with cl100k_base; o200k_base is an independent count of the same returned text and JSON. The full native payload includes all returned data except the host-varying `latency_ms` and `cache_hit` diagnostics. This is neither the MCP wire envelope nor model-provider billing. Values are means across every query, including unsupported questions.

| Cohort | Cap | Context cl100k (D / N / C) | Native JSON cl100k (D / N / C) | Native JSON o200k (D / N / C) |
|---|---:|---:|---:|---:|
| synthetic61 | 512 | 476.821 / 476.560 / 476.821 | 2094.137 / 2093.815 / 2094.137 | 1967.179 / 1966.470 / 1967.179 |
| synthetic61 | 1024 | 905.536 / 906.036 / 905.536 | 3443.208 / 3464.149 / 3443.208 | 3175.524 / 3195.696 / 3175.524 |
| synthetic61 | 2048 | 1260.060 / 1255.458 / 1260.060 | 4395.244 / 4385.429 / 4395.244 | 3923.833 / 3915.268 / 3923.833 |
| authored36 | 512 | 188.528 / 188.528 / 188.528 | 948.139 / 948.139 / 948.139 | 912.056 / 912.056 / 912.056 |
| authored36 | 1024 | 188.528 / 188.528 / 188.528 | 949.139 / 949.139 / 949.139 | 913.056 / 913.056 / 913.056 |
| authored36 | 2048 | 188.528 / 188.528 / 188.528 | 949.139 / 949.139 / 949.139 | 913.056 / 913.056 / 913.056 |
| public1015 | 512 | 491.887 / 492.118 / 491.785 | 2415.572 / 2416.518 / 2415.316 | 2402.129 / 2403.204 / 2401.872 |
| public1015 | 1024 | 861.058 / 861.469 / 861.058 | 4071.046 / 4072.552 / 4071.047 | 4040.930 / 4042.303 / 4040.931 |
| public1015 | 2048 | 867.074 / 866.941 / 867.074 | 4093.665 / 4092.885 / 4093.666 | 4063.054 / 4062.164 / 4063.055 |
| hotpot128 | 512 | 479.383 / 478.445 / 478.750 | 2417.859 / 2413.422 / 2413.695 | 2431.836 / 2427.250 / 2427.695 |
| hotpot128 | 1024 | 804.008 / 805.797 / 804.008 | 3971.836 / 3974.516 / 3971.836 | 3994.242 / 3997.164 / 3994.242 |
| hotpot128 | 2048 | 805.773 / 806.898 / 805.773 | 3978.969 / 3980.305 / 3978.969 | 4001.414 / 4002.992 / 4001.414 |

Cap payload cost also has small increases: LoCoMo/1024 and /2048 each add 1 token over all 1,015 responses in each reference tokenizer (mean +0.000985). Its mean cl100k full-payload reductions are 0.256158 at LoCoMo/512 and 4.164063 at Hotpot/512. The other cells have unchanged mean full-payload token counts. All individual context-token counts and both reference-tokenizer aggregates are retained in the original artifacts.

## Preserved audit failure and supplemental verification

The [measurement workflow](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43214192647) completed all workers between 12:02:01 and 12:05:46 UTC on 2026-11-12. Its numerical matrix, paired comparisons, screen and summary/hash checks passed. The final Markdown byte check failed: `save_report()` rendered the candidate dictionary in the registered order (`no_novelty`, `capped_novelty_025`), but canonical JSON used `sort_keys=True`; the auditor deserialized the reverse alphabetic order and rendered its two final bullets in that order. The **only diff is that two-bullet swap**. All table content and numbers match.

The original raw, summary, Markdown and `failed_or_incomplete` completion marker are immutable at [`0f6b5da`](https://github.com/Afloat16/AI-Memory-Book/commit/0f6b5da03b80f6119f050cd0d4116f19274cda07). No workflow was rerun, no measurement was repeated, and no original artifact or producer script was altered. The supplemental auditor at [`8ee165b`](https://github.com/Afloat16/AI-Memory-Book/commit/8ee165bd44410c4ef39a73b2193d115c0987376f) executes the unchanged numerical gates, verifies each original Git blob and SHA-256, verifies producer/helper and three runtime identities, checks all old-cohort bindings, then requires exact saved Markdown bytes after restoring only the registered candidate display order. Its fake-record tests reject altered numbers, text and extra candidates. Its status is deliberately `passed_with_documented_presentation_order_failure`, leaving the original workflow failure visible.

| Original file | SHA-256 |
|---|---|
| `novelty-probe-43214192647-1.json.gz` | `b656e0eb286421f7a51357cb3aaa9d2bac191b87b9430531953d3713bf80a5f9` |
| `novelty-probe-43214192647-1.summary.json` | `98cdd3d4113b477bc1fe4024ba70c3a41d855fae56fddbd0b7c32ef74a53f1e6` |
| `novelty-probe-43214192647-1.md` | `4289b01e623e2d449b1329be0c3d44d3a6d3d70cbe3b98ab4138c7ff3bda4349` |
| `novelty-probe-43214192647-1.completion.json` | `3ecc2e38b568d6d49abe2c859745f71027f13cf5f1683e47f71597b1157f6e37` |

Decompressed raw SHA-256: `eedc953a3bd7dab84e36918e007c68da51f3a6be76dedfedfd7b10b8287e5ed9`.

The supplemental audit verifies 12 workers, all 36 mode/cohort/budget configurations, all 24 candidate-versus-default comparisons, 12,123 query/configuration/mode samples, zero source-span/page-projection/scope/cache/budget invariant errors, and unchanged source archives. It recomputes the saved group aggregates and declared screening rule from the original per-query records; it does not rejudge evidence, re-retrieve or load question text.

### Ordinary CI remains part of the evidence

- [Default-source probe tooling CI43214192259](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43214192259): passed all nine jobs.
- [Cap 0.25 source CI43212728980](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43212728980): passed.
- [No-novelty source CI43212723576](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43212723576): failed the existing `test_complementary_query_facets_survive_similar_results` test; removing novelty returned temperature pages without the required “18 pascals” facet. The test and source formula were not changed to hide this failure. The completed development measurement does not make that ablation mergeable.

## Reproduce the saved-result audit

Use the supplemental-audit commit or a descendant containing the unchanged original files. Fetch the immutable variant commits if using a shallow checkout. The following performs no corpus download or retrieval; choose a new output path because the auditor refuses to overwrite any previous audit.

```bash
git fetch origin 0f6b5da03b80f6119f050cd0d4116f19274cda07
git fetch origin 38d4c5cf678907974035923ea1c179d50c5769c8
git fetch origin 506f1c6140e7ff4a1106f05e049b5285438e7268
python3.12 -m unittest tests.test_novelty_probe_result_audit -v
python3.12 scripts/audit_novelty_probe_results.py \
  --output .artifacts/novelty-probe-independent-audit.json
```

The [original pinned workflow](https://github.com/Afloat16/AI-Memory-Book/blob/848c0eb812e87e1cb5e3fb715c48459dcd1c4de8/.github/workflows/novelty-old-development.yml) records the full original measurement recipe. Any later validation needs its own preregistration, source binding and fresh output paths. This probe ends after these two candidates: no further bound tuning, no new Hotpot256 access, no README/default change, and no claim that the cap already generalizes beyond the old cohorts.

That separate [qualification](novelty-cap-qualification.md) has now completed its registered stopping condition: all 4,096 stage-A calls executed, all eight configurations lost complete evidence, and stage B stayed `not-run`. It used a new cache-isolated source binding without changing the formula or rewriting this development record. No further candidate tuning or performance study follows this rejection.
