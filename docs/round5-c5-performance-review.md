# v0.3.3 C5 formal performance review: release acceptance rejected

**Decision for candidate C5: reject release acceptance.** The complete formal run is valid and independently audited. C5 improves all twelve pooled p50, p95 and mean values and passes the registered aggregate and public native improvement gates: **15.220791% aggregate p95 improvement** and **15.422173% public native token512 p95 improvement**. Public actual-MCP token1024 improves by only **6.673181%**, below its **10%** requirement by **3.326819 percentage points**. This is the sole failed numerical gate. The original **`numeric_gate_passed:false` and `accepted:false` remain unchanged**.

All **56,784 calls** and **28,392 complete version pairs** are present, with no output differences or recorded invariant failures. There is no pooled p50/p95 regression above 5% and no resource-mean review trigger. Those results do not waive the failed actual-MCP requirement or approve this source for release.

[Original full report](../benchmarks/reports/round5-c5-performance-43552372788-1/report.json.gz) · [Original summary](../benchmarks/reports/round5-c5-performance-43552372788-1/report.summary.json) · [Original completion record](../benchmarks/reports/round5-c5-performance-43552372788-1/completion.json) · [Independent arithmetic, ledger and memo audit](../benchmarks/reports/round5-c5-performance-independent-audit.json) · [Unchanged C3 rejection](round5-performance-review.md)

## Frozen experiment and identities

| Role | Exact commit | Runtime SHA-256 |
|---|---|---|
| Published v0.3.2 baseline | `692fb959ddf8934c5f516ba3d74ceb4385a2fa82` | `179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93` |
| Frozen C5 source | `8dc6604fa32df18d53286110b215fc6657243656` | `6af876ef5ddc851f4fff56ba3dc4f20e76b2cfc9f5e31d0cc8d1a0ec20e954be` |

The frozen evaluator commit is `7852e26e582bdc9d5de2cc37e6c516c744c1c9aa`; the binding commit is `28b2f8923ad25643679ff17d9ee42c42abd70d67`, with binding SHA-256 `bd395da21848cc01656ab45bc211a388b43b4ae63edb8690b2eabe2958d3781a`. The final hosted result commit is `3982ceab2bdce0e9a189135ce261445a3a38d779`.

The [original plan](../benchmarks/experiments/round5-plan.json), [C5 registration](../benchmarks/experiments/round5-c5-addendum.json), [C5 binding](../benchmarks/experiments/round5-c5-performance-binding.json) and [independent source review](../benchmarks/reports/round5-c5-source-review.json) were saved before this formal measurement. The independent audit verifies all **42 evaluator input hashes** against their bound Git objects, including the unchanged original C3 and C4 inputs, their registration, and the retained negative C3 result.

Run [43552372788, attempt 1](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43552372788) measured from **2026-11-14 03:35:29 UTC to 03:46:35 UTC** on one four-CPU Linux host, Python **3.12.16**, SQLite **3.45.1**, MCP **1.30.0**, Pydantic **2.14.3** and tiktoken **0.12.0**. These are observations from the saved run, not general hardware guarantees.

## Matrix, timing and cold/warm boundaries

The registered matrix contains both complete old regression cohorts, 168 synthetic and 1,015 public-conversation queries, six configurations and four balanced **AB/BA/BA/AB** rounds. Each worker is a fresh isolated process. Query order and source-pair membership remain fixed. Native and actual-MCP character configurations use 4,000 characters; token configurations use `cl100k_base`, an 8,000-character ceiling, the named token cap and at most five results.

Native recall disables **query-result caching** with `cache_size=0` and `use_cache=False`. **C5 enables a separate bounded exact-token-count memo.** Every fresh candidate MemoryBook begins without an allocated memo, and character recall leaves it absent. The first native token512 configuration starts empty. Later native token1024 and token2048 configurations naturally reuse retained exact counts on that same connection. Their first queries are included; no extra prewarming, discarded first query or selective clearing is introduced.

Any earlier shorthand such as “uncached API call” refers to query-result caching, not to every derived cache. The saved C5 report itself explicitly describes query-result caching as disabled and the bounded exact-count memo as naturally retained. This review preserves that distinction and does not edit the frozen evaluator or its saved fields.

Each actual official-SDK MCP configuration starts a **fresh server process**. Persistent query-result-cache entries are cleared outside the measured call, while the normal result-cache write, server work and SDK transport remain timed. The derived count memo may warm naturally across queries within that process. Its private counters are not exposed over MCP, so native hit rates are not MCP hit rates. Actual MCP startup and child-process RSS are recorded separately. OS/SQLite cache warmth is not eliminated: this is not a cold-storage benchmark and not an experiment with every cache disabled.

The memo shares **2,048 entries and 2,097,152 retained text-object bytes per MemoryBook** across the two supported tokenizer names, charged after encoding. Mapping/key/value/encoder overhead and other process allocations are outside that text cap. The separate 4,096 KiB SQLite pager setting is connection-local and is not a whole-process memory cap. Native process RSS includes the evaluator, corpus, reference tokenizers and client imports; actual MCP child memory is sampled separately.

## Complete-output and saved-record audit

The [independent auditor](../scripts/audit_round5_c5_performance.py) imports only the standard library, reads saved JSON/gzip and committed Git objects, and independently recomputes the original arithmetic. It executed **zero retrieval calls, tokenizer/model calls, tests or timing runs** during this review. Its own recorded SHA-256 is `78bcde8d0a0c161ad4d4dab7768dbb7ba435effd8a86ced2815b1e7625d2e7a0`.


| Check | Independently verified count |
| --- | --- |
| Completed workers | 16 |
| Pooled cohort/configuration cells | 12 |
| Timed call observations | 56,784 |
| Original start/finish ledger events | 113,568 |
| Baseline/candidate complete stable-output pairs | 28,392 |
| Unique query/configuration combinations | 7,098 |
| Native/actual-MCP provenance pairs | 18,928 |
| Complete stable-output differences | 0 |
| Recorded source/scope/budget/cache invariant failures | 0 |
| Negative timing samples | 0 |
| Zero timing samples | 0 |
| Nonfinite or invalid timing samples | 0 |


Every saved worker matches the aggregate report. Each original gzip ledger matches its recorded hash, and every start/finish event matches the retained response in original order. The comparison retains complete native/MCP non-timing output digests, actual MCP envelope digests, context, token counts, metadata and recorded invariant fields. The sole excluded native response field is `latency_ms`; scores, candidate counts, truncation, source references and evidence remain compared.

This verifies saved measurements and recorded invariants. It does not reconstruct source text or rerun tokenization to create new source/budget evidence. The audit's `audit_passed:true` means that the records and calculations check out; it does **not** mean that the failed performance gate passed.

## All twelve pooled latency cells

Each synthetic cell contains **672 samples per source** and each public cell **4,060 samples per source**. Percentiles linearly interpolate at `(N - 1) * quantile` over all saved samples from the four rounds. They do not average round percentiles. Negative changes mean lower latency; acceptance uses unrounded values.


| Corpus | Configuration | Baseline p50, ms | C5 p50, ms | p50 change | Baseline p95, ms | C5 p95, ms | p95 change | Baseline mean, ms | C5 mean, ms | Mean change |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| synthetic61 | native-char4000 | 3.525399 | 3.183870 | -9.6877% | 11.008328 | 9.814946 | -10.8407% | 4.605155 | 4.030331 | -12.4822% |
| synthetic61 | mcp-char4000 | 5.142404 | 4.681878 | -8.9555% | 12.719630 | 11.435206 | -10.0980% | 6.250274 | 5.596177 | -10.4651% |
| synthetic61 | native-token512 | 6.414151 | 4.341392 | -32.3154% | 16.364684 | 12.285971 | -24.9239% | 7.461455 | 5.362639 | -28.1288% |
| synthetic61 | native-token1024 | 5.321316 | 3.438017 | -35.3916% | 16.956480 | 11.698119 | -31.0109% | 6.474158 | 4.451949 | -31.2351% |
| synthetic61 | native-token2048 | 4.019760 | 3.374827 | -16.0441% | 14.509940 | 11.930266 | -17.7787% | 5.570673 | 4.568375 | -17.9924% |
| synthetic61 | mcp-token1024 | 6.967815 | 5.302155 | -23.9051% | 18.756881 | 14.190991 | -24.3425% | 8.758006 | 7.095427 | -18.9835% |
| public1015 | native-char4000 | 2.434568 | 2.300925 | -5.4894% | 2.976303 | 2.794602 | -6.1050% | 2.445110 | 2.318618 | -5.1732% |
| public1015 | mcp-char4000 | 3.878881 | 3.768275 | -2.8515% | 4.472793 | 4.349683 | -2.7524% | 3.892492 | 3.789203 | -2.6535% |
| public1015 | native-token512 | 3.536880 | 2.759833 | -21.9698% | 4.196762 | 3.549530 | -15.4222% | 3.550321 | 2.801778 | -21.0838% |
| public1015 | native-token1024 | 3.019293 | 2.620553 | -13.2064% | 3.603165 | 3.098782 | -13.9983% | 3.011595 | 2.619583 | -13.0168% |
| public1015 | native-token2048 | 2.941618 | 2.529052 | -14.0252% | 3.467317 | 2.986206 | -13.8756% | 2.959424 | 2.552557 | -13.7482% |
| public1015 | mcp-token1024 | 4.461015 | 4.155597 | -6.8464% | 5.100384 | 4.760026 | -6.6732% | 4.632242 | 4.334790 | -6.4213% |


All twelve pooled p50, p95 and mean values improve. The largest public native p95 gain is token512's **15.422173%**; public native token1024 improves by **13.998333%**, while actual MCP token1024 improves by **6.673181%**. Native and MCP include different call costs and connection histories. The saved experiment does not isolate how much of that gap comes from memo warmth, transport, cache writing or other server work.

## Unchanged gates and rejection decision

For each of the twelve cells, let `r_i = C5 pooled p95_i / baseline pooled p95_i`. The registered aggregate is:

```text
geometric p95 improvement = 100 * (1 - exp(sum(log(r_i)) / 12))
                          = 15.220791446446002%
```

Each cell has equal weight. This is neither a query-count-weighted mean nor the geometric mean of percentage gains. A public p50 gain cannot satisfy the p95 gate, and native speed cannot substitute for actual-MCP speed.


| Registered requirement | Observed C5 result | Decision |
| --- | --- | --- |
| Complete stable output equal; zero invariant failures | 28,392 complete version pairs equal; zero recorded failures | Satisfied |
| Aggregate pooled p95 improvement at least 10% | 15.2207914464%; margin +5.220791 percentage points | Satisfied |
| At least one public native token p95 improvement at least 15% | Best: token512, 15.4221732781%; margin +0.422173 percentage points | Satisfied |
| Public actual-MCP token1024 p95 improvement at least 10% | 6.6731813400%; shortfall 3.326819 percentage points | **Failed** |
| No pooled p50/p95 regression greater than 5% | All 24 pooled p50/p95 comparisons improve | Satisfied |
| Resource means above +10% receive explicit independent review | Largest increase +6.947602%; no trigger | No exception needed |


The independent arithmetic reproduces **`numeric_gate_passed:false`**, **`accepted:false`**, an empty regression-above-5% list and an empty resource-review list. The public actual-MCP improvement threshold is the sole failed numerical gate and is sufficient to reject C5 release acceptance. No resource exception is needed or applied.

The original completion record retains `measurement_outcome:"failure"` and `audit_outcome:"success"`. The underlying report has `status:"measurements_completed"`, `validation.passed:true`, 56,784 calls and `error:null`. This is a completed negative numerical result, not an interrupted or incomplete experiment. The original fields remain unchanged.

## Every round: all 48 cohort/configuration cells

Round 0 uses AB, rounds 1 and 2 use BA, and round 3 uses AB. Each round retains 168 or 1,015 samples per source/configuration. All p50, p95 and mean values are shown, including the single positive round-level change.


### synthetic61


| Round | Configuration | Baseline p50, ms | C5 p50, ms | p50 change | Baseline p95, ms | C5 p95, ms | p95 change | Baseline mean, ms | C5 mean, ms | Mean change |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | native-char4000 | 3.459688 | 3.159886 | -8.6656% | 10.906807 | 9.741043 | -10.6884% | 4.563316 | 4.030019 | -11.6866% |
| 0 | mcp-char4000 | 5.217196 | 4.623718 | -11.3754% | 12.614837 | 11.284402 | -10.5466% | 6.400654 | 5.524864 | -13.6828% |
| 0 | native-token512 | 6.414151 | 4.515658 | -29.5985% | 16.326848 | 12.356327 | -24.3190% | 7.434578 | 5.393340 | -27.4560% |
| 0 | native-token1024 | 5.199376 | 3.443597 | -33.7690% | 16.904721 | 11.605180 | -31.3495% | 6.455164 | 4.472198 | -30.7191% |
| 0 | native-token2048 | 3.965803 | 3.440988 | -13.2335% | 14.493550 | 11.886370 | -17.9886% | 5.533620 | 4.589119 | -17.0684% |
| 0 | mcp-token1024 | 7.034471 | 5.358129 | -23.8304% | 18.904964 | 14.411476 | -23.7688% | 8.795122 | 7.130005 | -18.9323% |
| 1 | native-char4000 | 3.531188 | 3.178106 | -9.9989% | 10.934877 | 9.576125 | -12.4259% | 4.594620 | 3.993670 | -13.0794% |
| 1 | mcp-char4000 | 5.099711 | 4.874708 | -4.4121% | 12.804646 | 11.644445 | -9.0608% | 6.170279 | 5.748934 | -6.8286% |
| 1 | native-token512 | 6.428850 | 4.308130 | -32.9875% | 16.246164 | 12.061486 | -25.7579% | 7.424665 | 5.338120 | -28.1029% |
| 1 | native-token1024 | 5.295755 | 3.426838 | -35.2908% | 16.740604 | 11.869577 | -29.0971% | 6.439800 | 4.436987 | -31.1005% |
| 1 | native-token2048 | 3.999194 | 3.332589 | -16.6685% | 14.370054 | 11.846525 | -17.5610% | 5.607383 | 4.541854 | -19.0022% |
| 1 | mcp-token1024 | 6.927922 | 5.294173 | -23.5821% | 18.420690 | 14.143898 | -23.2173% | 8.676735 | 7.022107 | -19.0697% |
| 2 | native-char4000 | 3.506462 | 3.224861 | -8.0309% | 10.993187 | 9.878563 | -10.1392% | 4.599257 | 4.089495 | -11.0836% |
| 2 | mcp-char4000 | 4.986864 | 4.643201 | -6.8914% | 12.482773 | 11.321885 | -9.2999% | 6.108522 | 5.527717 | -9.5081% |
| 2 | native-token512 | 6.450633 | 4.242734 | -34.2276% | 16.487291 | 12.254361 | -25.6739% | 7.563828 | 5.368944 | -29.0182% |
| 2 | native-token1024 | 5.407576 | 3.481815 | -35.6123% | 17.032623 | 11.716831 | -31.2095% | 6.529007 | 4.468813 | -31.5545% |
| 2 | native-token2048 | 4.049238 | 3.388577 | -16.3157% | 14.511506 | 12.038073 | -17.0446% | 5.578984 | 4.595664 | -17.6254% |
| 2 | mcp-token1024 | 6.757119 | 5.356253 | -20.7317% | 18.759965 | 14.135247 | -24.6521% | 8.788968 | 7.163550 | -18.4938% |
| 3 | native-char4000 | 3.648841 | 3.176808 | -12.9365% | 11.335350 | 9.698082 | -14.4439% | 4.663428 | 4.008140 | -14.0516% |
| 3 | mcp-char4000 | 5.246224 | 4.752652 | -9.4081% | 13.123685 | 11.465267 | -12.6368% | 6.321640 | 5.583192 | -11.6813% |
| 3 | native-token512 | 6.335534 | 4.390853 | -30.6948% | 16.129237 | 11.944673 | -25.9440% | 7.422747 | 5.350151 | -27.9222% |
| 3 | native-token1024 | 5.298151 | 3.391215 | -35.9925% | 16.959292 | 11.604036 | -31.5771% | 6.472663 | 4.429798 | -31.5614% |
| 3 | native-token2048 | 4.060861 | 3.290201 | -18.9777% | 14.505766 | 11.854035 | -18.2805% | 5.562705 | 4.546864 | -18.2616% |
| 3 | mcp-token1024 | 7.010778 | 5.265315 | -24.8969% | 18.768267 | 14.176596 | -24.4651% | 8.771199 | 7.066044 | -19.4404% |



### public1015


| Round | Configuration | Baseline p50, ms | C5 p50, ms | p50 change | Baseline p95, ms | C5 p95, ms | p95 change | Baseline mean, ms | C5 mean, ms | Mean change |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | native-char4000 | 2.440721 | 2.295783 | -5.9383% | 2.976322 | 2.765258 | -7.0915% | 2.444907 | 2.309789 | -5.5265% |
| 0 | mcp-char4000 | 3.889044 | 3.734067 | -3.9850% | 4.486265 | 4.307508 | -3.9845% | 3.910986 | 3.760389 | -3.8506% |
| 0 | native-token512 | 3.543174 | 2.768711 | -21.8579% | 4.196992 | 3.516924 | -16.2037% | 3.547590 | 2.800968 | -21.0459% |
| 0 | native-token1024 | 3.010077 | 2.623347 | -12.8478% | 3.596081 | 3.100301 | -13.7867% | 3.006876 | 2.619702 | -12.8763% |
| 0 | native-token2048 | 2.953487 | 2.523388 | -14.5624% | 3.462413 | 2.978428 | -13.9783% | 2.964815 | 2.543196 | -14.2207% |
| 0 | mcp-token1024 | 4.470095 | 4.166857 | -6.7837% | 5.213366 | 4.745762 | -8.9693% | 4.789210 | 4.287599 | -10.4738% |
| 1 | native-char4000 | 2.430291 | 2.313228 | -4.8168% | 2.989923 | 2.853791 | -4.5530% | 2.445063 | 2.338995 | -4.3380% |
| 1 | mcp-char4000 | 3.867765 | 3.758945 | -2.8135% | 4.456523 | 4.325661 | -2.9364% | 3.883324 | 3.783741 | -2.5644% |
| 1 | native-token512 | 3.534773 | 2.752980 | -22.1172% | 4.209448 | 3.553540 | -15.5818% | 3.553014 | 2.793415 | -21.3790% |
| 1 | native-token1024 | 3.024781 | 2.608935 | -13.7480% | 3.591911 | 3.076529 | -14.3484% | 3.008500 | 2.614967 | -13.0807% |
| 1 | native-token2048 | 2.932703 | 2.520294 | -14.0624% | 3.460581 | 2.957258 | -14.5445% | 2.956780 | 2.545383 | -13.9137% |
| 1 | mcp-token1024 | 4.449224 | 4.132476 | -7.1192% | 5.060629 | 4.708239 | -6.9634% | 4.568567 | 4.266889 | -6.6033% |
| 2 | native-char4000 | 2.437401 | 2.302042 | -5.5534% | 2.983069 | 2.790692 | -6.4490% | 2.448949 | 2.320247 | -5.2554% |
| 2 | mcp-char4000 | 3.879632 | 3.802409 | -1.9905% | 4.453055 | 4.456411 | +0.0754% | 3.888999 | 3.834948 | -1.3898% |
| 2 | native-token512 | 3.543386 | 2.760839 | -22.0847% | 4.192549 | 3.575067 | -14.7281% | 3.549750 | 2.810544 | -20.8242% |
| 2 | native-token1024 | 3.008424 | 2.624237 | -12.7704% | 3.602878 | 3.099417 | -13.9739% | 3.011363 | 2.623773 | -12.8709% |
| 2 | native-token2048 | 2.944700 | 2.543719 | -13.6170% | 3.467337 | 3.036781 | -12.4175% | 2.957245 | 2.572903 | -12.9966% |
| 2 | mcp-token1024 | 4.443095 | 4.172836 | -6.0827% | 5.068611 | 4.859651 | -4.1226% | 4.566583 | 4.493557 | -1.5991% |
| 3 | native-char4000 | 2.431393 | 2.291026 | -5.7731% | 2.954758 | 2.758972 | -6.6261% | 2.441520 | 2.305441 | -5.5735% |
| 3 | mcp-char4000 | 3.873514 | 3.775911 | -2.5198% | 4.450368 | 4.299248 | -3.3957% | 3.886658 | 3.777733 | -2.8025% |
| 3 | native-token512 | 3.526441 | 2.756755 | -21.8261% | 4.156491 | 3.533322 | -14.9927% | 3.550932 | 2.802184 | -21.0859% |
| 3 | native-token1024 | 3.023719 | 2.615706 | -13.4937% | 3.618918 | 3.116047 | -13.8956% | 3.019640 | 2.619888 | -13.2384% |
| 3 | native-token2048 | 2.942258 | 2.525513 | -14.1641% | 3.472299 | 2.981968 | -14.1212% | 2.958858 | 2.548744 | -13.8606% |
| 3 | mcp-token1024 | 4.488083 | 4.150380 | -7.5244% | 5.101241 | 4.737111 | -7.1381% | 4.604607 | 4.291114 | -6.8082% |



## Every adverse latency observation

There are **zero pooled positive p50/p95/mean changes**. Of the 144 round-level p50/p95/mean comparisons, exactly one is positive and remains in the saved result:


| Corpus | Configuration | Round | Metric | Change |
| --- | --- | --- | --- | --- |
| public1015 | mcp-char4000 | 2 | p95_ms | +0.0754% |


That round-level increase does not trigger the rule about pooled p50/p95 regressions above 5%, but it is still disclosed. No worker, round, first query or slower observation was dropped, and this frozen source is not remeasured to select a faster result.

## All 28 resource-mean comparisons

Each source/cohort has **four resource observations per metric**. The original trigger is a **mean increase greater than 10%**, not p95. All comparisons are retained. The independent audit also retains per-source means, p50/p95, minima and maxima, with original observations in the worker records. Milliseconds remain milliseconds; memory means are converted using 1,048,576 bytes per MiB.

RSS snapshots and OS high-water values do not isolate causal allocations. Native-process memory includes the evaluator and reference tokenizers; character and token MCP child processes are separate. An unchanged or lower RSS/high-water observation does not establish that the memo, index or larger pager is free.


### synthetic61 resource means


| Metric | Unit | Baseline mean | C5 mean | Change | >10% review trigger |
| --- | --- | --- | --- | --- | --- |
| Runtime import | ms | 22.464276 | 23.654351 | +5.2976% | No |
| Native opening | ms | 23.777138 | 25.429079 | +6.9476% | No |
| Fresh ingestion | ms | 1011.767941 | 893.056264 | -11.7331% | No |
| Unchanged replay | ms | 75.650096 | 75.563163 | -0.1149% | No |
| Character MCP startup to initialization | ms | 483.579918 | 489.430261 | +1.2098% | No |
| Native RSS after ingestion | MiB | 38.942383 | 41.102539 | +5.5471% | No |
| Native high-water after ingestion | MiB | 39.482422 | 41.102539 | +4.1034% | No |
| Native RSS after calls | MiB | 189.734375 | 193.438477 | +1.9523% | No |
| Native high-water after calls | MiB | 189.734375 | 193.438477 | +1.9523% | No |
| Character MCP child RSS after calls | MiB | 61.329102 | 60.878906 | -0.7341% | No |
| Character MCP child high-water after calls | MiB | 61.386719 | 60.878906 | -0.8272% | No |
| Token MCP startup to initialization | ms | 483.047192 | 478.453428 | -0.9510% | No |
| Token MCP child RSS after calls | MiB | 105.125977 | 105.043945 | -0.0780% | No |
| Token MCP child high-water after calls | MiB | 105.125977 | 105.043945 | -0.0780% | No |



### public1015 resource means


| Metric | Unit | Baseline mean | C5 mean | Change | >10% review trigger |
| --- | --- | --- | --- | --- | --- |
| Runtime import | ms | 22.374723 | 23.550048 | +5.2529% | No |
| Native opening | ms | 38.159765 | 25.565437 | -33.0042% | No |
| Fresh ingestion | ms | 1043.793509 | 1030.855636 | -1.2395% | No |
| Unchanged replay | ms | 144.206055 | 143.585848 | -0.4301% | No |
| Character MCP startup to initialization | ms | 483.804876 | 485.292896 | +0.3076% | No |
| Native RSS after ingestion | MiB | 42.138672 | 44.080078 | +4.6072% | No |
| Native high-water after ingestion | MiB | 49.793945 | 50.048828 | +0.5119% | No |
| Native RSS after calls | MiB | 213.455078 | 217.889648 | +2.0775% | No |
| Native high-water after calls | MiB | 213.455078 | 217.889648 | +2.0775% | No |
| Character MCP child RSS after calls | MiB | 60.530273 | 60.143555 | -0.6389% | No |
| Character MCP child high-water after calls | MiB | 60.530273 | 60.143555 | -0.6389% | No |
| Token MCP startup to initialization | ms | 480.343365 | 477.577627 | -0.5758% | No |
| Token MCP child RSS after calls | MiB | 103.836914 | 104.564453 | +0.7007% | No |
| Token MCP child high-water after calls | MiB | 103.836914 | 104.564453 | +0.7007% | No |



### Independent resource decision

None of the 28 means increases by more than 10%; the recomputed resource-review list is empty. The largest increase is **synthetic61 / `native_open_ms`: 23.777138 to 25.429079 ms, +6.947602%**. No resource waiver is requested or granted. Passing this separate resource rule does not change the rejected numerical decision.

## Native memo observations and natural reuse

All **eight candidate workers** start with an empty, unallocated memo. All eight native character configurations leave it unallocated, and all eight token512 configurations therefore begin empty. The audit verifies fixed bounds and exact state continuity across native configurations; token1024 and token2048 begin with counts naturally retained by prior native configurations. Each first query is included in the timing samples. A first query that starts empty may still reuse work within that same call; no pre-query warmup is added.

The **eight baseline workers** explicitly report the memo as unavailable, not as having zero hits. Candidate snapshots are taken before each native configuration, after its first retained query and after all queries, outside the measured recall call. The complete snapshots and first query IDs are preserved in the independent audit JSON.

The following table retains all **32 candidate configuration records**. Entries/bytes are retained text state at the stated snapshot; hit/miss, eviction/invalidation and bypass columns are deltas within that configuration, not cumulative values carried from earlier configurations. `uncertified_bypasses` also counts ordinary inputs ineligible for the memo, such as short prefixes/suffixes; it does not imply a tokenizer fault.


| Round | Corpus | Configuration | Start entries / bytes | After first call entries / bytes | End entries / bytes | First call hits / misses | All calls hits / misses | Evictions / invalidations | Oversized / ineligible-or-uncertified bypasses |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | synthetic61 | native-char4000 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| 0 | synthetic61 | native-token512 | 0 / 0 | 7 / 9,519 | 767 / 1,217,779 | 0 / 7 | 548 / 767 | 0 / 0 | 0 / 2,616 |
| 0 | synthetic61 | native-token1024 | 767 / 1,217,779 | 767 / 1,217,779 | 943 / 1,488,100 | 6 / 0 | 907 / 176 | 0 / 0 | 0 / 1,088 |
| 0 | synthetic61 | native-token2048 | 943 / 1,488,100 | 946 / 1,496,203 | 1,117 / 1,749,265 | 5 / 3 | 859 / 174 | 0 / 0 | 0 / 291 |
| 0 | public1015 | native-char4000 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| 0 | public1015 | native-token512 | 0 / 0 | 8 / 6,031 | 2,048 / 1,546,625 | 0 / 8 | 4,131 / 2,194 | 146 / 0 | 0 / 9,913 |
| 0 | public1015 | native-token1024 | 2,048 / 1,546,625 | 2,048 / 1,546,599 | 2,048 / 1,501,628 | 3 / 2 | 4,099 / 1,028 | 1,028 / 0 | 0 / 2,219 |
| 0 | public1015 | native-token2048 | 2,048 / 1,501,628 | 2,048 / 1,501,628 | 2,048 / 1,516,725 | 5 / 0 | 4,952 / 121 | 121 / 0 | 0 / 0 |
| 1 | synthetic61 | native-char4000 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| 1 | synthetic61 | native-token512 | 0 / 0 | 5 / 4,492 | 767 / 1,217,779 | 0 / 5 | 548 / 767 | 0 / 0 | 0 / 2,616 |
| 1 | synthetic61 | native-token1024 | 767 / 1,217,779 | 768 / 1,218,789 | 943 / 1,488,100 | 4 / 1 | 907 / 176 | 0 / 0 | 0 / 1,088 |
| 1 | synthetic61 | native-token2048 | 943 / 1,488,100 | 944 / 1,490,592 | 1,117 / 1,749,265 | 4 / 1 | 859 / 174 | 0 / 0 | 0 / 291 |
| 1 | public1015 | native-char4000 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| 1 | public1015 | native-token512 | 0 / 0 | 7 / 5,566 | 2,048 / 1,542,373 | 0 / 7 | 4,131 / 2,194 | 146 / 0 | 0 / 9,913 |
| 1 | public1015 | native-token1024 | 2,048 / 1,542,373 | 2,048 / 1,542,455 | 2,048 / 1,501,039 | 3 / 2 | 4,084 / 1,043 | 1,043 / 0 | 0 / 2,219 |
| 1 | public1015 | native-token2048 | 2,048 / 1,501,039 | 2,048 / 1,501,039 | 2,048 / 1,516,509 | 5 / 0 | 4,952 / 121 | 121 / 0 | 0 / 0 |
| 2 | synthetic61 | native-char4000 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| 2 | synthetic61 | native-token512 | 0 / 0 | 8 / 16,364 | 767 / 1,217,779 | 0 / 8 | 548 / 767 | 0 / 0 | 0 / 2,616 |
| 2 | synthetic61 | native-token1024 | 767 / 1,217,779 | 769 / 1,222,447 | 943 / 1,488,100 | 8 / 2 | 907 / 176 | 0 / 0 | 0 / 1,088 |
| 2 | synthetic61 | native-token2048 | 943 / 1,488,100 | 945 / 1,490,008 | 1,117 / 1,749,265 | 3 / 2 | 859 / 174 | 0 / 0 | 0 / 291 |
| 2 | public1015 | native-char4000 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| 2 | public1015 | native-token512 | 0 / 0 | 7 / 8,426 | 2,048 / 1,546,474 | 0 / 7 | 4,138 / 2,187 | 139 / 0 | 0 / 9,913 |
| 2 | public1015 | native-token1024 | 2,048 / 1,546,474 | 2,048 / 1,546,330 | 2,048 / 1,507,938 | 2 / 3 | 4,106 / 1,021 | 1,021 / 0 | 0 / 2,219 |
| 2 | public1015 | native-token2048 | 2,048 / 1,507,938 | 2,048 / 1,507,938 | 2,048 / 1,516,367 | 5 / 0 | 4,952 / 121 | 121 / 0 | 0 / 0 |
| 3 | synthetic61 | native-char4000 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| 3 | synthetic61 | native-token512 | 0 / 0 | 7 / 7,727 | 767 / 1,217,779 | 0 / 7 | 548 / 767 | 0 / 0 | 0 / 2,616 |
| 3 | synthetic61 | native-token1024 | 767 / 1,217,779 | 768 / 1,218,426 | 943 / 1,488,100 | 4 / 1 | 907 / 176 | 0 / 0 | 0 / 1,088 |
| 3 | synthetic61 | native-token2048 | 943 / 1,488,100 | 943 / 1,488,100 | 1,117 / 1,749,265 | 8 / 0 | 859 / 174 | 0 / 0 | 0 / 291 |
| 3 | public1015 | native-char4000 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| 3 | public1015 | native-token512 | 0 / 0 | 7 / 4,549 | 2,048 / 1,546,574 | 0 / 7 | 4,138 / 2,187 | 139 / 0 | 0 / 9,913 |
| 3 | public1015 | native-token1024 | 2,048 / 1,546,574 | 2,048 / 1,546,879 | 2,048 / 1,505,000 | 3 / 2 | 4,091 / 1,036 | 1,036 / 0 | 0 / 2,219 |
| 3 | public1015 | native-token2048 | 2,048 / 1,505,000 | 2,048 / 1,504,644 | 2,048 / 1,513,939 | 4 / 1 | 4,952 / 121 | 121 / 0 | 0 / 0 |


Across the recorded snapshots, the largest retained entry count is **2,048** and the largest retained text size is **1,749,265 bytes**, within the registered caps. These are observed snapshot maxima, not measurements of every intermediate memory peak. Public native configurations exercise real LRU eviction; all final counters report zero invalidations and zero oversized-text bypasses. The snapshot limits exclude container/key/value/encoder overhead and other process memory.

Eligible exact-count lookup totals across the four candidate workers per corpus show the effect of natural connection reuse. Hit share below is `hits / (hits + misses)` over eligible certified lookups, not a query-result-cache hit rate, not a fraction of all token-count calls, and not an MCP measurement.


| Corpus | Native configuration | Hits | Misses | Eligible lookup hit share | Evictions |
| --- | --- | --- | --- | --- | --- |
| synthetic61 | native-token512 | 2,192 | 3,068 | 41.6730% | 0 |
| synthetic61 | native-token1024 | 3,628 | 704 | 83.7488% | 0 |
| synthetic61 | native-token2048 | 3,436 | 696 | 83.1559% | 0 |
| public1015 | native-token512 | 16,538 | 8,762 | 65.3676% | 570 |
| public1015 | native-token1024 | 16,380 | 4,128 | 79.8713% | 4,128 |
| public1015 | native-token2048 | 19,808 | 484 | 97.6148% | 484 |


The actual-MCP token1024 configuration starts a separate server without the native token512 prehistory. Its private memo counters are deliberately not observed. The native reuse table cannot establish an MCP hit rate or identify the exact cause of the remaining actual-MCP speed shortfall. That requires a new diagnostic or substantive candidate, not a changed gate or a selective repeat of this measurement.

## Logical database storage and other costs

All three original logical-storage phases are retained for each cohort. These numbers are SQLite logical page count times page size; they are not index-only allocation costs. Freelist reuse would not prove that an index is free. Retained text state, logical database storage and process RSS are different quantities.


| Corpus | Phase | Baseline mean bytes | C5 mean bytes | Mean difference bytes | Change |
| --- | --- | --- | --- | --- | --- |
| synthetic61 | storage_after_ingestion_live | 20,508,672 | 20,733,952 | +225,280 | +1.0985% |
| synthetic61 | storage_after_mcp_live | 20,508,672 | 20,733,952 | +225,280 | +1.0985% |
| synthetic61 | storage_after_checkpoint | 20,508,672 | 20,733,952 | +225,280 | +1.0985% |
| public1015 | storage_after_ingestion_live | 12,881,920 | 13,053,952 | +172,032 | +1.3355% |
| public1015 | storage_after_mcp_live | 12,881,920 | 13,053,952 | +172,032 | +1.3355% |
| public1015 | storage_after_checkpoint | 12,881,920 | 13,053,952 | +172,032 | +1.3355% |


## Development history and correctness boundary

The complete [C5 development comparison](../benchmarks/reports/round5-development/candidate-c5-full/summary.json) retained 18,928 calls and 9,464 equal output pairs. Its best public native token p95 gain was 14.144746%, below the formal 15% requirement; this two-round native diagnostic contained no actual-MCP measurement. It was retained in full. The sole hosted formal run used the original four-round plan, thresholds and frozen source rather than replacing or repeatedly selecting among native diagnostic results. Different point estimates on the local and hosted machines do not establish statistical significance or general portability.

The earlier [C3 formal rejection](round5-performance-review.md) remains rejected. [C4 development evidence](../benchmarks/reports/round5-development/candidate-c4-full/summary.json) is also retained; no C4 formal acceptance was obtained. C5 explicitly registered its new derived-count memo and never relabeled a C3/C4 result as C5 evidence.

The separately completed [C5 Hotpot256 compatibility check](../benchmarks/reports/round5-c5-hotpot-regression.summary.json) binds this same frozen C5 runtime and retains **2,304 exact matches**: 1,536 across both supported tokenizers and three caps, plus 768 component outputs. The [full report](../benchmarks/reports/round5-c5-hotpot-regression.json.gz) and [4,608 original events](../benchmarks/reports/round5-c5-hotpot-regression.attempts.jsonl.gz) provide complete historical payload compatibility. This does not establish unseen-domain quality improvement, Q2 retesting, a new competitor evaluation or superiority across all product capabilities.

## Final decision and limits

**C5 is not accepted for the promised formal release.** Its correctness checks, native and aggregate improvements, and resource rule all pass, but the public actual-MCP token1024 p95 gain does not meet the unchanged 10% gate. The saved `accepted:false` and numerical rejection are final for this frozen source.

Further work must target a substantive implementation change under a new source/binding while preserving this complete negative result and all original gates. A later candidate must pass its own complete-output, performance and resource requirements before final-source CI and release publication. Neither this audit's success nor Hotpot compatibility authorizes a release or filling an approved-runtime entry for C5.

This experiment covers one hosted machine, old regression queries and the stated fixed workloads. It does not establish statistical significance, production workload coverage, cold-storage performance, universal memory savings or whole-product competitor dominance. No sample, round, adverse observation or failed gate has been removed, and no measurement was rerun by this independent audit.

