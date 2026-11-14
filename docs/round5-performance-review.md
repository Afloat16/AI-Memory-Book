# v0.3.3 C3 formal performance review: release acceptance rejected

**Decision for candidate C3: reject release acceptance despite clear general improvement.** The complete formal run is valid and independently audited. C3 improves all twelve pooled p50 and p95 values and achieves **10.499586% aggregate p95 improvement**, but misses both registered public-workload improvement thresholds: **10.482574%** native token512 improvement against a **15%** requirement, and **5.146962%** actual-MCP token1024 improvement against a **10%** requirement. The original `numeric_gate_passed:false` and `accepted:false` remain unchanged.

This is a completed negative acceptance result. All **56,784 calls** and **28,392 version pairs** are present; no missing data or interrupted worker explains the failure. The source and result records remain available for subsequent work, but this candidate does not qualify for the promised release under the fixed gates.

[Original full report](../benchmarks/reports/round5-performance-43547085915-1/report.json.gz) · [Original summary](../benchmarks/reports/round5-performance-43547085915-1/report.summary.json) · [Original completion record](../benchmarks/reports/round5-performance-43547085915-1/completion.json) · [Independent arithmetic and ledger audit](../benchmarks/reports/round5-performance-independent-audit.json) · [Development history](optimization-round5.md)

## Bound experiment and identities

| Role | Exact commit | Runtime SHA-256 |
|---|---|---|
| Published v0.3.2 baseline | `692fb959ddf8934c5f516ba3d74ceb4385a2fa82` | `179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93` |
| Frozen C3 candidate and evaluator | `1c9a6d3f611608e8dbce8e729fdd3099513d80e6` | `7a927601b5ce710059d5a2640b3642c58a2bd4985d9ccdc48f69159938ee3623` |

The [plan](../benchmarks/experiments/round5-plan.json), [index addendum](../benchmarks/experiments/round5-index-addendum.json), [pager addendum](../benchmarks/experiments/round5-cache-addendum.json) and [source/evaluator binding](../benchmarks/experiments/round5-performance-binding.json) were committed before formal timing. The evaluator and dependency pins are checked independently against their original Git objects.

Run [43547085915, attempt 1](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43547085915) executed from **2026-11-14 02:35:25 UTC to 02:47:21 UTC** on one four-CPU Linux host, Python **3.12.16**, SQLite **3.45.1**, MCP **1.30.0**, Pydantic **2.14.3** and tiktoken **0.12.0**. These are environment observations from the saved run, not a general hardware performance guarantee.

The matrix contains 168 synthetic queries and 1,015 public-conversation queries from old regression cohorts, six configurations and four balanced **AB/BA/BA/AB** rounds. Each worker is a fresh isolated process. Query order is fixed and identical within every source pair. Character configurations use 4,000 characters; token configurations use `cl100k_base`, their stated token cap, an 8,000-character ceiling and at most five results.

The complete native call uses `cache_size=0` and `use_cache=False`. Actual SDK MCP stdio clears persistent recall-cache entries outside timing, then includes the normal response cache-write and transport costs. Reference tokenizer counting and invariant validation happen outside the measured call. OS/SQLite caches are warm; this is not a cold-storage comparison.

## Complete-output and saved-record audit

The [independent auditor](../scripts/audit_round5_performance.py) imports only the Python standard library and reads saved JSON/gzip plus committed Git objects. It does not import the retrieval runtime or reuse the evaluator's numerical functions. It executed **zero retrieval calls, tokenizers, models, tests or timing runs** during this review.

| Check | Independently verified count |
|---|---:|
| Completed workers | 16 |
| Cohort/configuration cells | 12 |
| Timed call observations | 56,784 |
| Original start/finish ledger events | 113,568 |
| Baseline/candidate complete stable-output pairs | 28,392 |
| Unique query/configuration combinations | 7,098 |
| Native/actual-MCP cached-provenance pairs | 18,928 |
| Complete stable-output differences | 0 |
| Recorded source/scope/budget/cache invariant failures | 0 |
| Negative, zero or nonfinite/invalid timing samples | 0 |

Every worker's complete saved record matches the aggregate report. Each original gzip ledger matches its recorded hash and every start/finish event matches the corresponding saved response in original order. The audit compares complete native/MCP non-timing output digests, actual MCP envelope digests, context digests, token counts and metadata, and recorded invariant fields. The sole excluded native response field is `latency_ms`; evidence, scores, context, metadata and source references remain part of the compared payload digest.

This is independent verification of the saved measurements and recorded invariants. The audit does not reconstruct the original source text or rerun tokenization to create new source/budget evidence. That distinction remains explicit in the audit output.

## All twelve pooled latency cells

All values below are calculated from the original saved samples. Negative changes mean lower latency. Synthetic cells contain **672 samples per source** and public cells **4,060 samples per source**. Percentiles linearly interpolate at `(N − 1) × quantile`; they pool all four rounds, rather than averaging the round percentiles.

| Corpus | Configuration | Baseline p50, ms | C3 p50, ms | p50 change | Baseline p95, ms | C3 p95, ms | p95 change | Mean change |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| synthetic61 | native-char4000 | 4.149622 | 3.862207 | -6.9263% | 12.502514 | 11.531041 | -7.7702% | -9.2076% |
| synthetic61 | mcp-char4000 | 6.264300 | 5.851049 | -6.5969% | 14.989412 | 13.727908 | -8.4160% | -7.3743% |
| synthetic61 | native-token512 | 7.514309 | 5.358099 | -28.6947% | 19.026128 | 14.913689 | -21.6147% | -23.5502% |
| synthetic61 | native-token1024 | 6.020354 | 4.565251 | -24.1697% | 19.517815 | 14.992351 | -23.1863% | -22.2697% |
| synthetic61 | native-token2048 | 4.655526 | 4.349005 | -6.5840% | 16.805888 | 15.804268 | -5.9599% | -7.0624% |
| synthetic61 | mcp-token1024 | 8.196440 | 6.673285 | -18.5831% | 22.231939 | 17.669624 | -20.5214% | -15.8974% |
| public1015 | native-char4000 | 2.893682 | 2.769403 | -4.2948% | 3.528887 | 3.366532 | -4.6008% | -4.5975% |
| public1015 | mcp-char4000 | 4.787085 | 4.649166 | -2.8810% | 5.515043 | 5.347720 | -3.0339% | -2.9666% |
| public1015 | native-token512 | 4.190024 | 3.497722 | -16.5226% | 4.956286 | 4.436740 | -10.4826% | -15.6367% |
| public1015 | native-token1024 | 3.563959 | 3.358016 | -5.7785% | 4.245260 | 3.955467 | -6.8263% | -5.8030% |
| public1015 | native-token2048 | 3.484911 | 3.336082 | -4.2707% | 4.106514 | 3.899688 | -5.0365% | -5.1203% |
| public1015 | mcp-token1024 | 5.522149 | 5.253425 | -4.8663% | 6.278956 | 5.955781 | -5.1470% | -4.7586% |

All twelve pooled p50, p95 and mean values improve. Public token512's **p50** improves by 16.5226%, but the preregistered 15% requirement concerns **p95**, which improves by 10.4826%. Substituting the median would change the acceptance rule.

## Fixed gates and rejection decision

For each of the twelve cells, let `r_i = C3 pooled p95_i / baseline pooled p95_i`. The registered aggregate is:

```text
geometric p95 improvement = 100 × (1 − exp(sum(log(r_i)) / 12))
                          = 10.499586026010144%
```

Each cell has equal weight in this geometric mean. It is not a query-count-weighted mean and is not the geometric mean of percentage gains. Each relative change is calculated from the unrounded values; table rounding does not determine acceptance.

| Registered requirement | Observed C3 result | Decision |
|---|---|---|
| Complete stable output equal; zero invariant failures | 28,392 complete version pairs equal; zero recorded failures | Satisfied |
| Aggregate pooled p95 improvement ≥10% | 10.4995860260%; margin +0.499586 percentage points | Satisfied |
| At least one public native token p95 improvement ≥15% | Best: token512, 10.4825741541%; shortfall **4.517426 percentage points** | **Failed** |
| Public actual-MCP token1024 p95 improvement ≥10% | 5.1469620015%; shortfall **4.853038 percentage points** | **Failed** |
| No pooled p50/p95 regression >5% | All 24 pooled p50/p95 comparisons improve | Satisfied |
| Resource means above +10% receive explicit review | Largest increase +7.236920% for public native opening; no trigger | No exception needed |

The independent arithmetic reproduces **`numeric_gate_passed:false`**, **`accepted:false`**, an empty regression-above-5% list and an empty resource-review list. The two failed improvement thresholds are sufficient to reject C3. Passing correctness, the aggregate threshold and resource checks does not waive either failed threshold.

The [original completion record](../benchmarks/reports/round5-performance-43547085915-1/completion.json) retains `measurement_outcome:"failure"`, `audit_outcome:"success"`, and the workflow's generic `status:"failed_or_incomplete"`. Here that generic completion label means **failed numerical acceptance**: the underlying report explicitly has `status:"measurements_completed"`, `validation.passed:true`, 56,784 valid observations and no error. The audit confirms that interpretation without altering the original fields.

## Every round: all 48 cohort/configuration observations

The following tables retain all round-level p50, p95 and mean values and changes. Round 0 uses AB, rounds 1–2 BA, and round 3 AB. Each round has 168 samples per source/configuration for synthetic61 and 1,015 for public1015. A positive sign would indicate a regression; **none of these 144 round-level latency comparisons is positive**. Consistent observed improvement still does not satisfy the two unmet magnitude thresholds.

### synthetic61

| Round | Configuration | Baseline p50, ms | C3 p50, ms | p50 change | Baseline p95, ms | C3 p95, ms | p95 change | Baseline mean, ms | C3 mean, ms | Mean change |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | native-char4000 | 4.299489 | 3.824115 | -11.0565% | 12.502448 | 11.608756 | -7.1481% | 5.455824 | 4.837936 | -11.3253% |
| 0 | mcp-char4000 | 6.142383 | 5.825670 | -5.1562% | 14.839534 | 13.565287 | -8.5868% | 7.372536 | 6.877324 | -6.7170% |
| 0 | native-token512 | 7.461340 | 5.487897 | -26.4489% | 18.787521 | 15.070415 | -19.7850% | 8.621151 | 6.673715 | -22.5890% |
| 0 | native-token1024 | 5.971842 | 4.623388 | -22.5802% | 19.361111 | 15.166036 | -21.6675% | 7.427518 | 5.903011 | -20.5251% |
| 0 | native-token2048 | 4.523343 | 4.386680 | -3.0213% | 16.462591 | 15.855921 | -3.6851% | 6.349959 | 6.007529 | -5.3926% |
| 0 | mcp-token1024 | 8.373561 | 6.712236 | -19.8401% | 22.398041 | 17.674427 | -21.0894% | 10.583071 | 8.813823 | -16.7177% |
| 1 | native-char4000 | 4.193481 | 3.952716 | -5.7414% | 12.549826 | 11.435249 | -8.8812% | 5.434423 | 4.893776 | -9.9486% |
| 1 | mcp-char4000 | 6.630864 | 6.047994 | -8.7903% | 15.074812 | 14.143512 | -6.1779% | 7.762551 | 7.155771 | -7.8168% |
| 1 | native-token512 | 7.594952 | 5.467541 | -28.0109% | 19.354308 | 15.122864 | -21.8631% | 8.896309 | 6.743048 | -24.2040% |
| 1 | native-token1024 | 6.049010 | 4.605586 | -23.8622% | 19.552217 | 14.960473 | -23.4845% | 7.581870 | 5.904481 | -22.1237% |
| 1 | native-token2048 | 4.692775 | 4.365892 | -6.9657% | 16.779302 | 15.836679 | -5.6178% | 6.517371 | 6.024348 | -7.5648% |
| 1 | mcp-token1024 | 8.287625 | 6.876430 | -17.0277% | 22.209198 | 17.833496 | -19.7022% | 10.525182 | 9.060242 | -13.9184% |
| 2 | native-char4000 | 4.119710 | 3.910189 | -5.0858% | 12.233951 | 11.542539 | -5.6516% | 5.251437 | 4.893914 | -6.8081% |
| 2 | mcp-char4000 | 5.955589 | 5.749305 | -3.4637% | 14.448691 | 13.369474 | -7.4693% | 7.196771 | 6.699967 | -6.9032% |
| 2 | native-token512 | 7.381634 | 5.236828 | -29.0560% | 18.866498 | 14.804074 | -21.5325% | 8.602337 | 6.570751 | -23.6167% |
| 2 | native-token1024 | 5.972610 | 4.507062 | -24.5378% | 19.683586 | 14.939599 | -24.1012% | 7.574649 | 5.798697 | -23.4460% |
| 2 | native-token2048 | 4.675050 | 4.319887 | -7.5970% | 16.761536 | 15.732032 | -6.1421% | 6.437782 | 5.943879 | -7.6720% |
| 2 | mcp-token1024 | 8.125850 | 6.673285 | -17.8759% | 22.126799 | 17.586120 | -20.5212% | 10.467402 | 8.800884 | -15.9210% |
| 3 | native-char4000 | 4.131626 | 3.873001 | -6.2596% | 12.491838 | 11.442025 | -8.4040% | 5.294057 | 4.836401 | -8.6447% |
| 3 | mcp-char4000 | 6.295539 | 5.826866 | -7.4445% | 14.928571 | 13.829796 | -7.3602% | 7.487280 | 6.887120 | -8.0157% |
| 3 | native-token512 | 7.490035 | 5.177839 | -30.8703% | 19.044329 | 14.794239 | -22.3168% | 8.653305 | 6.596449 | -23.7696% |
| 3 | native-token1024 | 6.034211 | 4.495131 | -25.5059% | 19.720209 | 14.967023 | -24.1031% | 7.547282 | 5.814981 | -22.9526% |
| 3 | native-token2048 | 4.655526 | 4.334345 | -6.8989% | 16.806763 | 15.683009 | -6.6863% | 6.413523 | 5.926515 | -7.5935% |
| 3 | mcp-token1024 | 8.140529 | 6.484814 | -20.3392% | 22.050581 | 17.136787 | -22.2842% | 10.454972 | 8.673891 | -17.0357% |

### public1015

| Round | Configuration | Baseline p50, ms | C3 p50, ms | p50 change | Baseline p95, ms | C3 p95, ms | p95 change | Baseline mean, ms | C3 mean, ms | Mean change |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | native-char4000 | 2.913920 | 2.772436 | -4.8555% | 3.545136 | 3.351407 | -5.4646% | 2.931510 | 2.775997 | -5.3049% |
| 0 | mcp-char4000 | 4.856842 | 4.662730 | -3.9967% | 5.670738 | 5.378249 | -5.1579% | 4.896458 | 4.681031 | -4.3996% |
| 0 | native-token512 | 4.241129 | 3.504132 | -17.3774% | 5.024535 | 4.468500 | -11.0664% | 4.252213 | 3.559210 | -16.2975% |
| 0 | native-token1024 | 3.610092 | 3.371797 | -6.6008% | 4.274402 | 3.968851 | -7.1484% | 3.603672 | 3.363482 | -6.6651% |
| 0 | native-token2048 | 3.502344 | 3.344457 | -4.5080% | 4.129295 | 3.935501 | -4.6932% | 3.531627 | 3.338433 | -5.4704% |
| 0 | mcp-token1024 | 5.545517 | 5.339864 | -3.7085% | 6.287265 | 6.034283 | -4.0237% | 5.684661 | 5.478372 | -3.6289% |
| 1 | native-char4000 | 2.889474 | 2.774077 | -3.9937% | 3.561782 | 3.366411 | -5.4852% | 2.909462 | 2.781571 | -4.3957% |
| 1 | mcp-char4000 | 4.782874 | 4.651465 | -2.7475% | 5.468001 | 5.326454 | -2.5886% | 4.803545 | 4.669000 | -2.8009% |
| 1 | native-token512 | 4.202837 | 3.498399 | -16.7610% | 4.956416 | 4.434864 | -10.5228% | 4.203551 | 3.546425 | -15.6326% |
| 1 | native-token1024 | 3.544364 | 3.360327 | -5.1924% | 4.229513 | 3.957420 | -6.4332% | 3.543366 | 3.359393 | -5.1920% |
| 1 | native-token2048 | 3.472663 | 3.328749 | -4.1442% | 4.091762 | 3.884999 | -5.0532% | 3.493194 | 3.319957 | -4.9592% |
| 1 | mcp-token1024 | 5.567438 | 5.300649 | -4.7920% | 6.326645 | 5.966111 | -5.6987% | 5.697284 | 5.441733 | -4.4855% |
| 2 | native-char4000 | 2.882497 | 2.761248 | -4.2064% | 3.524411 | 3.372293 | -4.3161% | 2.902423 | 2.770731 | -4.5373% |
| 2 | mcp-char4000 | 4.732091 | 4.632164 | -2.1117% | 5.452395 | 5.322067 | -2.3903% | 4.760951 | 4.650441 | -2.3212% |
| 2 | native-token512 | 4.158600 | 3.483898 | -16.2243% | 4.933563 | 4.428928 | -10.2286% | 4.170280 | 3.539372 | -15.1287% |
| 2 | native-token1024 | 3.542529 | 3.326474 | -6.0989% | 4.231535 | 3.916511 | -7.4447% | 3.545405 | 3.322103 | -6.2984% |
| 2 | native-token2048 | 3.460119 | 3.322738 | -3.9704% | 4.072413 | 3.887904 | -4.5307% | 3.471400 | 3.307771 | -4.7136% |
| 2 | mcp-token1024 | 5.454429 | 5.164957 | -5.3071% | 6.184310 | 5.814343 | -5.9824% | 5.588874 | 5.310398 | -4.9827% |
| 3 | native-char4000 | 2.884692 | 2.775509 | -3.7849% | 3.505504 | 3.374943 | -3.7245% | 2.904546 | 2.784125 | -4.1460% |
| 3 | mcp-char4000 | 4.776924 | 4.649748 | -2.6623% | 5.457061 | 5.375303 | -1.4982% | 4.774123 | 4.663985 | -2.3070% |
| 3 | native-token512 | 4.169282 | 3.502424 | -15.9946% | 4.936564 | 4.428844 | -10.2849% | 4.202889 | 3.552439 | -15.4763% |
| 3 | native-token1024 | 3.558128 | 3.374102 | -5.1720% | 4.226271 | 4.002155 | -5.3029% | 3.555919 | 3.376557 | -5.0440% |
| 3 | native-token2048 | 3.506486 | 3.350746 | -4.4415% | 4.143330 | 3.908404 | -5.6700% | 3.521087 | 3.333413 | -5.3300% |
| 3 | mcp-token1024 | 5.543797 | 5.193438 | -6.3198% | 6.286372 | 5.888139 | -6.3349% | 5.681732 | 5.344112 | -5.9422% |

## All 28 resource-mean comparisons

Each source/cohort has **four resource samples**. The registered trigger is a **mean increase greater than 10%**; it does not use p95. The audit retains the per-source means, p50/p95, minima, maxima and all original samples. The tables below show means; milliseconds remain milliseconds, and byte counts are converted to MiB using 1,048,576 bytes per MiB.

Native-process memory includes the evaluator, loaded corpus, reference tokenizers and SDK client imports. Actual MCP child-process memory is sampled separately for its character and token sessions. RSS snapshots and OS high-water values do not isolate causal allocation costs. In particular, the lower observed MCP RSS does not prove that the larger pager has no memory cost.

### synthetic61 resource means

| Metric | Unit | Baseline mean | C3 mean | Change | >10% review trigger |
|---|---|---:|---:|---:|---|
| Runtime import | ms | 23.664019 | 23.876918 | +0.8997% | No |
| Fresh native database opening | ms | 32.784053 | 32.272017 | -1.5618% | No |
| Fresh ingestion | ms | 933.408100 | 882.556885 | -5.4479% | No |
| Unchanged replay | ms | 91.770595 | 90.933943 | -0.9117% | No |
| MCP character-session initialization | ms | 557.740790 | 560.443656 | +0.4846% | No |
| Native post-ingestion RSS | MiB | 38.328125 | 40.348633 | +5.2716% | No |
| Native post-ingestion HWM | MiB | 38.749023 | 40.348633 | +4.1281% | No |
| Native post-call RSS | MiB | 189.037109 | 191.196289 | +1.1422% | No |
| Native post-call HWM | MiB | 189.037109 | 191.196289 | +1.1422% | No |
| MCP character-session RSS | MiB | 61.467773 | 60.737305 | -1.1884% | No |
| MCP character-session HWM | MiB | 61.467773 | 60.737305 | -1.1884% | No |
| MCP token1024-session initialization | ms | 547.410775 | 550.640652 | +0.5900% | No |
| MCP token1024-session RSS | MiB | 104.860352 | 104.266602 | -0.5662% | No |
| MCP token1024-session HWM | MiB | 104.860352 | 104.266602 | -0.5662% | No |

### public1015 resource means

| Metric | Unit | Baseline mean | C3 mean | Change | >10% review trigger |
|---|---|---:|---:|---:|---|
| Runtime import | ms | 23.488143 | 24.193513 | +3.0031% | No |
| Fresh native database opening | ms | 32.229954 | 34.562410 | +7.2369% | No |
| Fresh ingestion | ms | 963.779495 | 1011.170816 | +4.9172% | No |
| Unchanged replay | ms | 181.824834 | 182.245530 | +0.2314% | No |
| MCP character-session initialization | ms | 555.525687 | 558.521450 | +0.5393% | No |
| Native post-ingestion RSS | MiB | 41.394531 | 43.346680 | +4.7160% | No |
| Native post-ingestion HWM | MiB | 49.046875 | 49.169922 | +0.2509% | No |
| Native post-call RSS | MiB | 212.837891 | 215.178711 | +1.0998% | No |
| Native post-call HWM | MiB | 212.837891 | 215.178711 | +1.0998% | No |
| MCP character-session RSS | MiB | 60.460938 | 60.025391 | -0.7204% | No |
| MCP character-session HWM | MiB | 60.460938 | 60.025391 | -0.7204% | No |
| MCP token1024-session initialization | ms | 550.239833 | 550.798178 | +0.1015% | No |
| MCP token1024-session RSS | MiB | 103.978516 | 103.800781 | -0.1709% | No |
| MCP token1024-session HWM | MiB | 103.978516 | 103.800781 | -0.1709% | No |

The largest registered resource mean increase is **+7.236920%** for public native opening (**32.229954 → 34.562410 ms**). Public fresh ingestion rises **4.917237%** (**963.779495 → 1,011.170816 ms**). Native post-ingestion RSS rises about **2.02 MiB** on synthetic61 and **1.95 MiB** on public1015. These adverse resource observations are retained even though none crosses the 10% trigger. There is no resource waiver and no substitution of another measurement.

## Logical database storage and existing-archive upgrade

Formal logical database size is SQLite `page_count × page_size`, not an index-only allocation estimate. The fresh-ingestion, live-MCP and post-checkpoint measurements each record the same source-specific sizes in this run:

| Corpus | Baseline bytes | C3 bytes | Difference | Change |
|---|---:|---:|---:|---:|
| synthetic61 | 20,508,672 | 20,733,952 | +225,280 bytes | +1.0985% |
| public1015 | 12,881,920 | 13,053,952 | +172,032 bytes | +1.3355% |

The [separate existing-archive upgrade observation](../benchmarks/reports/round5-development/final-index-upgrade.json) uses **one observation per source/cohort**, fresh copies of old databases and warm OS caches. It is descriptive upgrade evidence, not a p50/p95 comparison or an additional performance-gate run. The [upgrade review](../benchmarks/reports/round5-development/final-index-upgrade-review.json) retains its limitations.

| Old archive | Baseline first open, ms | C3 first open, ms | Baseline open + close, ms | C3 open + close, ms | New index allocation | Observed file growth |
|---|---:|---:|---:|---:|---:|---:|
| synthetic61 | 0.910320 | 5.419327 | 0.999775 | 9.494591 | 200,704 bytes | 0 bytes |
| public1015 | 0.843670 | 4.501765 | 0.929700 | 7.791396 | 151,552 bytes | 0 bytes |

Both upgraded copies preserve the complete logical-content digest, revision and schema version. Their new indexes occupy existing free pages: **zero observed file extension does not mean zero storage cost**. The indexes allocate 200,704 and 151,552 bytes respectively. The upgrade probe's identical `ru_maxrss` values can retain launch/fork high-water usage and do not establish equal live memory or zero overhead; the formal resource samples above are the relevant memory observations.

C3 also sets a connection-local SQLite pager target of **4,096 KiB**, replacing the observed SQLite default target of 2,000 KiB. This is separate from the application's query/result cache and does not allocate an unconditional extra 4 MiB at connection creation. The [standalone cache diagnostic](../benchmarks/reports/round5-development/sqlite-cache-probe-1/README.md) preserves all 6,144 calls, its roughly 2.1 MiB observed RSS increase for 4 MiB, and the 8 MiB alternative's public-character p95 regression of **5.37%**. Those baseline-only gains cannot be added to the covering-index gains or treated as a measured C3 benefit. C3's actual combined behavior is the failed formal result recorded here.

## Retention, reproducibility and next-candidate boundary

The binding has one remote execution claim; each worker publishes start and completion checkpoints. The completed result is retained on `validation/v033-round5-performance-43547085915-1`, including the original negative acceptance and completion fields. The independent audit checks every source/response pair, every call ledger and all numerical comparisons without repeating retrieval.

To recompute the **offline audit only**, use a new output name so the original audit remains intact:

```bash
python scripts/audit_round5_performance.py \
  --report benchmarks/reports/round5-performance-43547085915-1/report.json.gz \
  --output benchmarks/reports/round5-c3-additional-offline-audit.json
```

No completed C3 timing is rerun or selected for better performance. A subsequent materially changed implementation must have its own source identity, documented selection rationale, binding and retained formal result. This C3 report remains a failed acceptance record; a later candidate cannot relabel or overwrite it.

| Integrity item | SHA-256 |
|---|---|

| Source/evaluator binding | `790ca15f3fbe2a5ba19fe08f83ab663bdb313a8569bfb1ee7677456ca4817c40` |
| Registered plan | `b83c385c2e7160318ca2c8fded161937f716d43803c03799fd86fd4f63d484a8` |
| Uncompressed complete report | `aaa6f5b9c494ef775d06eb5e5444507a2314942f22f329e80a98911493b6d68a` |
| Compressed complete report | `4a9b870d6bd64c2b3b8e463033cb578831c0e459add1117c946bdfbf00058e33` |
| Independent audit script | `2747d64f99c5bfe85a2dd69ac159260e5dbc1e6229d24074d22c5a50543c86e1` |

## Interpretation limits

This is **one host, two old regression cohorts and repeated queries across four process rounds**. There are 1,183 distinct original queries; the 28,392 version pairs do not represent that many independent new questions. First/repeat partitions in the saved audit mean round 0 versus rounds 1–3, not cold versus warm operating-system storage. No statistical-significance claim is made.

Complete-output equality preserves the evidence observed from the baseline on these inputs. It is not a new-domain retrieval evaluation, an assessment of generated answers or hallucinations, or proof of private-conversation transfer. The offline audit validates source identities, saved records and arithmetic; it does not manufacture additional evidence by rerunning a model.

No competitor is retimed in this formal experiment. Historical component comparisons keep their original repository revisions, corpora, budgets and interface boundaries. This candidate's measured Book-versus-Book gains establish no new cross-product speed ratio or across-the-board competitive superiority. The positive improvements and the failed release decision must both remain visible.
