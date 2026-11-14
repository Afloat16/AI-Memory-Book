# Round-five C7 formal performance review — resource review required

**Numerical gates pass; the original automatic accepted:false records three resource costs requiring explicit review.** This is the sole frozen C7 run against published v0.3.2. All 56,784 recorded calls completed, and all 28,392 complete non-timing output pairs match. This review preserves the original decision; it does not approve a release or replace final-commit CI and packaging.

**Separate resource review completed on 2026-11-14.** The title and original acceptance tables describe the automatic verdict, which remains unchanged. After two independent reviews, the release coordinator accepted the three disclosed startup tradeoffs in a [separate decision](../benchmarks/experiments/round5-c7-resource-decision.json). The [reviewed decision section](#separate-reviewed-release-decision) below records that acceptance and its limits; final release CI, packaging and installer gates still apply.

The independent arithmetic and original report both retain `numeric_gate_passed:true` and `accepted:false`. The observed aggregate p95 gain is **14.7975756457%**, best public native-token p95 gain **15.7405567562%**, and public actual-MCP token1024 p95 gain **12.1734376301%**.

## Frozen identities and retained evidence

| Role | Commit | Runtime SHA256 |
| --- | --- | --- |
| baseline | `692fb959ddf8934c5f516ba3d74ceb4385a2fa82` | `179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93` |
| candidate | `d0c84cbfc9bad440ad447d41e211d070ef5b2cae` | `55529a217e6dcf6af0c81639cfc0e88b3ea94c39e6911f659fcfb7543e853d45` |

Evaluator `259fde01a3d189cf01b55b9765457daebc953bff`; binding commit `f0d51d62c60b61047f96b4a6b7a9771f8b0668f7`; binding SHA256 `2560b0eae9d3332fb09da43fd49ebef069b8e41ddaef0fe9df1880db1e132588`; final hosted result commit `03838687f7d8d5995c2afa4c22ff5c30e7b12750`. All **60 evaluator input hashes** were verified against their bound Git objects, including retained C3/C4/C5/C6 inputs and all three prior formal rejections.

[Sole run 43563390252-1](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43563390252) · [Original plan](../benchmarks/experiments/round5-plan.json) · [C7 registration](../benchmarks/experiments/round5-c7-addendum.json) · [Frozen binding](../benchmarks/experiments/round5-c7-performance-binding.json) · [Source review](../benchmarks/reports/round5-c7-source-review.json)

Saved measurement interval: **2026-11-14T05:50:35.987415+00:00 → 2026-11-14T06:03:08.815599+00:00**. The observed host reports **4 CPUs**, Linux-7.0.0-1017-azure-x86_64-with-glibc2.39, Python **3.12.16** and SQLite **3.45.1**. Frozen packages: `{"mcp": "1.30.0", "pydantic": "2.14.3", "tiktoken": "0.12.0"}`. These describe this run and do not establish a hardware-independent guarantee.

## Matrix and timing boundaries

The full old cohorts contain 168 synthetic and 1,015 public-conversation questions. Six configurations and four balanced **AB/BA/BA/AB** rounds produce sixteen sequential worker processes and twelve pooled cells. Character settings use 4,000 characters; token settings use cl100k_base, an 8,000-character ceiling, the specified 512/1,024/2,048-token cap and at most five results.

**Native query-result caching is disabled; derived exact-count reuse is enabled.** Each fresh candidate MemoryBook starts without an allocated memo. Character recall leaves it absent; native token512 starts empty. Later token1024 and token2048 configurations naturally reuse counts from earlier configurations on the same connection. All first queries remain included. No extra warmup, discarded first query or selective clearing is introduced. Earlier shorthand such as 'uncached API' describes query-result caching.

**Each actual official-SDK MCP configuration starts a fresh server process.** Query-result cache entries are cleared outside the timer. The normal server cache write, serialization, server work and SDK roundtrip remain timed. The derived memo may warm naturally inside that process; no private MCP memo counters are exposed. Native hit rates cannot be assigned to MCP. OS/SQLite warmth remains possible: this is not a cold-storage experiment or an experiment with every cache disabled.

The per-connection memo retains at most **2,048 entries / 2,097,152 post-encode text-object bytes**, shared by the supported encoders. Key/container/count/encoder overhead is additional. The separate **4,096 KiB** pager target is connection-local. Neither setting caps whole-process memory. Native RSS includes evaluator and corpus allocations; actual MCP server memory is sampled separately.

## Complete-output and saved-record audit

The [independent auditor](../scripts/audit_round5_c7_performance.py), SHA256 `432a9c784c32aa242138e8200294e4c6d6ced3c7bdbea5b459998bb1d20f77fe`, uses only standard-library saved-data and Git-object reads. It performs zero retrieval, tokenizer/model, test or timing workloads. The frozen evaluator's separate strict saved-ledger audit also adds no calls.

| Check | Verified count |
| --- | --- |
| workers | 16 |
| cells | 12 |
| timed calls | 56,784 |
| ledger events | 113,568 |
| baseline candidate pairs | 28,392 |
| unique query configuration pairs | 7,098 |
| native mcp provenance pairs | 18,928 |
| complete output differences | 0 |
| recorded invariant failures | 0 |
| negative timing samples | 0 |
| zero timing samples | 0 |
| nonfinite or invalid timing samples | 0 |

Every worker and every original start/finish event is retained in original order. Complete non-timing native/MCP payload digests, MCP envelope/provenance digests and all recorded source/scope/budget/cache invariants are compared. Only latency_ms is excluded from stable response equality. The audit verifies saved digests and calculations; omitted response bodies are not reconstructed or re-tokenized. audit_passed:true means the records check out, independently of the numerical acceptance result.

## All twelve pooled latency cells

Each synthetic cell has 672 samples per version and each public cell has 4,060. Percentiles linearly interpolate at (N − 1) × quantile over all four rounds' samples; round percentiles are not averaged. Negative changes mean lower latency. Decisions use the unrounded values.

| Corpus | Configuration | Baseline p50 ms | C7 p50 ms | p50 change | Baseline p95 ms | C7 p95 ms | p95 change | Baseline mean ms | C7 mean ms | Mean change |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| synthetic61 | native-char4000 | 4.513837 | 4.215153 | -6.617086% | 14.137126 | 12.892497 | -8.803974% | 5.916978 | 5.299922 | -10.428578% |
| synthetic61 | mcp-char4000 | 6.603706 | 6.104952 | -7.552623% | 16.359655 | 15.111370 | -7.630265% | 7.984313 | 7.273902 | -8.897583% |
| synthetic61 | native-token512 | 8.163190 | 5.828095 | -28.605176% | 20.644509 | 16.021344 | -22.394162% | 9.472006 | 7.004360 | -26.051992% |
| synthetic61 | native-token1024 | 6.713316 | 4.453771 | -33.657659% | 21.228758 | 14.959201 | -29.533320% | 8.178845 | 5.725361 | -29.997923% |
| synthetic61 | native-token2048 | 5.005927 | 4.379491 | -12.513877% | 18.306601 | 15.382632 | -15.972211% | 6.999862 | 5.886661 | -15.903183% |
| synthetic61 | mcp-token1024 | 8.737662 | 6.840350 | -21.714178% | 23.597330 | 18.107263 | -23.265628% | 11.203747 | 9.013731 | -19.547175% |
| public1015 | native-char4000 | 3.120267 | 2.975110 | -4.652085% | 3.805544 | 3.583489 | -5.835041% | 3.137429 | 2.983879 | -4.894144% |
| public1015 | mcp-char4000 | 4.999490 | 4.767187 | -4.646534% | 5.740315 | 5.580336 | -2.786940% | 5.007606 | 4.827459 | -3.597459% |
| public1015 | native-token512 | 4.547860 | 3.541386 | -22.130719% | 5.407803 | 4.586537 | -15.186681% | 4.569487 | 3.588459 | -21.469109% |
| public1015 | native-token1024 | 3.853768 | 3.335869 | -13.438771% | 4.599450 | 3.944666 | -14.236152% | 3.853517 | 3.332496 | -13.520647% |
| public1015 | native-token2048 | 3.775416 | 3.215225 | -14.837837% | 4.478285 | 3.773378 | -15.740557% | 3.801162 | 3.227210 | -15.099395% |
| public1015 | mcp-token1024 | 5.798058 | 5.170008 | -10.832083% | 6.711413 | 5.894404 | -12.173438% | 5.974386 | 5.332500 | -10.743963% |

## Unchanged acceptance gates

For each cell, r is C7 pooled p95 divided by baseline pooled p95. The aggregate is 100 × (1 − exp(sum(log(r)) / 12)). Each cell has equal weight; it is not a query-weighted mean or the geometric mean of percentage gains. Native gains cannot replace an actual-MCP gate.

| Requirement | Threshold | Observed | Margin | Decision |
| --- | --- | --- | --- | --- |
| Aggregate pooled p95 improvement | at least 10% | 14.7975756457% | +4.7975756457 percentage points | Satisfied |
| Best public native-token p95 improvement | at least 15% | 15.7405567562% | +0.7405567562 percentage points | Satisfied |
| Public actual-MCP token1024 p95 improvement | at least 10% | 12.1734376301% | +2.1734376301 percentage points | Satisfied |
| Complete stable outputs and recorded invariants | all equal; zero failures | 28,392 equal pairs; zero failures | — | Satisfied |
| Pooled p50/p95 regression | no increase greater than 5% | 0 flagged comparisons | — | Satisfied |
| Resource mean increase | greater than 10% requires explicit review | 3 triggered comparisons | — | **Review required; no automatic waiver** |

The original result remains `accepted:false`. The failure or required review is not overridden by this document.

## Every round: all 48 cohort/configuration cells

Round 0 is AB, rounds 1 and 2 are BA, and round 3 is AB. Each cell retains 168 or 1,015 samples per version. No round or adverse value is omitted.

### synthetic61

| Round | Configuration | Baseline p50 ms | C7 p50 ms | p50 change | Baseline p95 ms | C7 p95 ms | p95 change | Baseline mean ms | C7 mean ms | Mean change |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | native-char4000 | 4.732620 | 4.263562 | -9.911170% | 14.935268 | 13.115075 | -12.187211% | 6.182797 | 5.412056 | -12.465884% |
| 0 | mcp-char4000 | 6.880826 | 6.514575 | -5.322770% | 16.413000 | 15.540392 | -5.316569% | 8.253808 | 7.712881 | -6.553661% |
| 0 | native-token512 | 8.477946 | 5.968676 | -29.597621% | 21.076410 | 16.195098 | -23.160075% | 9.635260 | 7.119908 | -26.105698% |
| 0 | native-token1024 | 6.665393 | 4.502255 | -32.453270% | 21.422070 | 15.240622 | -28.855508% | 8.314716 | 5.846822 | -29.681041% |
| 0 | native-token2048 | 5.126304 | 4.467006 | -12.861070% | 18.485534 | 15.684611 | -15.151972% | 7.125783 | 6.055235 | -15.023590% |
| 0 | mcp-token1024 | 8.831435 | 6.947198 | -21.335566% | 24.158375 | 18.587099 | -23.061470% | 11.385302 | 9.200286 | -19.191553% |
| 1 | native-char4000 | 4.496626 | 4.124407 | -8.277730% | 13.804553 | 12.728095 | -7.797848% | 5.822708 | 5.247599 | -9.877007% |
| 1 | mcp-char4000 | 6.594027 | 6.047978 | -8.280957% | 16.257086 | 14.927554 | -8.178167% | 7.881808 | 7.161016 | -9.145005% |
| 1 | native-token512 | 8.072441 | 5.728278 | -29.039085% | 20.372579 | 15.997818 | -21.473773% | 9.353099 | 7.028793 | -24.850651% |
| 1 | native-token1024 | 6.746527 | 4.328430 | -35.842101% | 21.198927 | 14.715089 | -30.585690% | 8.158371 | 5.651875 | -30.722990% |
| 1 | native-token2048 | 4.953622 | 4.324022 | -12.709911% | 18.332635 | 15.269850 | -16.706734% | 7.016260 | 5.851080 | -16.606859% |
| 1 | mcp-token1024 | 8.693229 | 7.019246 | -19.256171% | 23.289168 | 18.187637 | -21.905169% | 10.990483 | 9.118603 | -17.031821% |
| 2 | native-char4000 | 4.408920 | 4.228112 | -4.100959% | 13.945291 | 12.821717 | -8.057013% | 5.862070 | 5.302713 | -9.541976% |
| 2 | mcp-char4000 | 6.643711 | 6.048320 | -8.961716% | 16.309420 | 14.845205 | -8.977722% | 7.981169 | 7.180164 | -10.036183% |
| 2 | native-token512 | 8.093017 | 5.808059 | -28.233692% | 20.603760 | 16.112494 | -21.798285% | 9.452839 | 7.008815 | -25.854913% |
| 2 | native-token1024 | 6.485940 | 4.472776 | -31.038899% | 21.273983 | 14.950935 | -29.721976% | 8.181384 | 5.763566 | -29.552684% |
| 2 | native-token2048 | 5.032790 | 4.537945 | -9.832438% | 18.159542 | 15.347993 | -15.482490% | 6.956927 | 5.856516 | -15.817486% |
| 2 | mcp-token1024 | 8.983894 | 6.785139 | -24.474414% | 23.701234 | 17.843503 | -24.714878% | 11.312408 | 8.935398 | -21.012414% |
| 3 | native-char4000 | 4.465091 | 4.193121 | -6.091019% | 13.900644 | 12.897562 | -7.216082% | 5.800339 | 5.237319 | -9.706673% |
| 3 | mcp-char4000 | 6.384283 | 5.956381 | -6.702428% | 16.295046 | 14.748604 | -9.490261% | 7.820466 | 7.041546 | -9.960027% |
| 3 | native-token512 | 8.123718 | 5.652656 | -30.417870% | 20.308441 | 15.710808 | -22.639023% | 9.446826 | 6.859922 | -27.383841% |
| 3 | native-token1024 | 6.455170 | 4.325770 | -32.987518% | 21.045039 | 14.682202 | -30.234380% | 8.060908 | 5.639183 | -30.042841% |
| 3 | native-token2048 | 5.007289 | 4.275225 | -14.619957% | 17.991913 | 15.133450 | -15.887487% | 6.900479 | 5.783815 | -16.182413% |
| 3 | mcp-token1024 | 8.564767 | 6.607589 | -22.851504% | 23.554765 | 17.518898 | -25.624824% | 11.126796 | 8.800637 | -20.905918% |

### public1015

| Round | Configuration | Baseline p50 ms | C7 p50 ms | p50 change | Baseline p95 ms | C7 p95 ms | p95 change | Baseline mean ms | C7 mean ms | Mean change |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | native-char4000 | 3.170461 | 2.956429 | -6.750816% | 3.843945 | 3.567242 | -7.198394% | 3.178499 | 2.965547 | -6.699760% |
| 0 | mcp-char4000 | 5.004464 | 4.780160 | -4.482078% | 5.774780 | 5.627366 | -2.552733% | 5.023290 | 4.842064 | -3.607727% |
| 0 | native-token512 | 4.561112 | 3.545415 | -22.268627% | 5.463007 | 4.557913 | -16.567684% | 4.598168 | 3.591216 | -21.898975% |
| 0 | native-token1024 | 3.902786 | 3.330042 | -14.675260% | 4.665161 | 3.963298 | -15.044780% | 3.894795 | 3.340086 | -14.242306% |
| 0 | native-token2048 | 3.787640 | 3.215125 | -15.115349% | 4.449739 | 3.787682 | -14.878571% | 3.810130 | 3.232842 | -15.151390% |
| 0 | mcp-token1024 | 5.686022 | 5.182057 | -8.863226% | 6.495452 | 5.897357 | -9.207903% | 5.850133 | 5.335008 | -8.805354% |
| 1 | native-char4000 | 3.114986 | 2.975946 | -4.463583% | 3.760523 | 3.571823 | -5.017920% | 3.124544 | 2.988625 | -4.350055% |
| 1 | mcp-char4000 | 4.936307 | 4.713779 | -4.507985% | 5.641249 | 5.375875 | -4.704181% | 4.951184 | 4.746897 | -4.126018% |
| 1 | native-token512 | 4.519403 | 3.551237 | -21.422431% | 5.332067 | 4.614511 | -13.457367% | 4.523697 | 3.588370 | -20.676179% |
| 1 | native-token1024 | 3.802919 | 3.337335 | -12.242806% | 4.516522 | 3.923771 | -13.124053% | 3.796855 | 3.334562 | -12.175667% |
| 1 | native-token2048 | 3.686959 | 3.229663 | -12.403067% | 4.344397 | 3.785338 | -12.868512% | 3.720000 | 3.254532 | -12.512589% |
| 1 | mcp-token1024 | 5.862474 | 5.136031 | -12.391407% | 6.704444 | 5.872710 | -12.405711% | 6.033941 | 5.288743 | -12.350092% |
| 2 | native-char4000 | 3.104881 | 3.015305 | -2.885006% | 3.775770 | 3.634914 | -3.730519% | 3.115652 | 3.023858 | -2.946229% |
| 2 | mcp-char4000 | 4.960700 | 4.934308 | -0.532022% | 5.641839 | 5.776622 | +2.388985% | 4.972420 | 4.990661 | +0.366838% |
| 2 | native-token512 | 4.521773 | 3.586883 | -20.675297% | 5.359340 | 4.643716 | -13.352832% | 4.528738 | 3.634185 | -19.752813% |
| 2 | native-token1024 | 3.795951 | 3.367874 | -11.277200% | 4.507772 | 3.968859 | -11.955193% | 3.790829 | 3.361640 | -11.321784% |
| 2 | native-token2048 | 3.706099 | 3.218544 | -13.155477% | 4.363854 | 3.774596 | -13.503143% | 3.722142 | 3.215815 | -13.603092% |
| 2 | mcp-token1024 | 5.662715 | 5.240595 | -7.454375% | 6.440318 | 6.014290 | -6.615013% | 5.826841 | 5.435284 | -6.719888% |
| 3 | native-char4000 | 3.103476 | 2.940155 | -5.262519% | 3.787122 | 3.518907 | -7.082286% | 3.131022 | 2.957486 | -5.542467% |
| 3 | mcp-char4000 | 5.070969 | 4.685075 | -7.609867% | 5.838600 | 5.363733 | -8.133234% | 5.083529 | 4.730215 | -6.950166% |
| 3 | native-token512 | 4.587431 | 3.498277 | -23.742134% | 5.458044 | 4.507671 | -17.412333% | 4.627346 | 3.540066 | -23.496842% |
| 3 | native-token1024 | 3.917566 | 3.288443 | -16.059027% | 4.680852 | 3.868847 | -17.347369% | 3.931589 | 3.293698 | -16.224770% |
| 3 | native-token2048 | 3.935768 | 3.201089 | -18.666725% | 4.683336 | 3.738044 | -20.184159% | 3.952378 | 3.205650 | -18.893128% |
| 3 | mcp-token1024 | 6.006615 | 5.113178 | -14.874218% | 7.006035 | 5.784003 | -17.442569% | 6.186629 | 5.270965 | -14.800692% |

## Every adverse latency observation

### Pooled

No positive latency change was recorded in this category.

### Per round

| Corpus | Configuration | Round | Metric | Increase |
| --- | --- | --- | --- | --- |
| public1015 | mcp-char4000 | 2 | p95_ms | +2.388985% |
| public1015 | mcp-char4000 | 2 | mean_ms | +0.366838% |

## All 28 resource comparisons

These retain the four original samples per version and cohort. Acceptance compares arithmetic means in original units; byte observations below are displayed as MiB. A mean increase above 10% requires an explicit cause and independent review. This document does not grant an exception.

| Corpus | Metric | Unit | Baseline four samples | C7 four samples | Baseline mean | C7 mean | Mean change | Resource rule |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| synthetic61 | runtime_import_ms | ms | 28.189789, 27.732217, 28.119725, 27.536354 | 31.749188, 30.849470, 31.097510, 30.670893 | 27.894521 | 31.091765 | +11.461907% | Review required |
| synthetic61 | native_open_ms | ms | 946.793415, 22.422942, 24.996153, 23.793885 | 25.130586, 27.140976, 22.560302, 23.623510 | 254.501599 | 24.613844 | -90.328609% | No trigger |
| synthetic61 | fresh_ingestion_ms | ms | 877.634367, 867.206167, 847.428900, 846.625693 | 859.773554, 852.954518, 853.416326, 846.229446 | 859.723782 | 853.093461 | -0.771215% | No trigger |
| synthetic61 | unchanged_reingestion_ms | ms | 105.320121, 105.641393, 104.064164, 104.421314 | 104.499458, 103.780318, 104.506460, 103.873103 | 104.861748 | 104.164835 | -0.664602% | No trigger |
| synthetic61 | mcp_startup_to_initialize_ms | ms | 553.993673, 552.981530, 541.312448, 539.243742 | 563.294342, 549.017753, 563.631090, 546.137009 | 546.882848 | 555.520049 | +1.579351% | No trigger |
| synthetic61 | native_memory_after_ingestion.rss_bytes | MiB | 39.625000, 39.527344, 39.621094, 39.601562 | 41.769531, 41.769531, 41.765625, 41.628906 | 39.593750 | 41.733398 | +5.404006% | No trigger |
| synthetic61 | native_memory_after_ingestion.hwm_bytes | MiB | 39.835938, 39.769531, 39.714844, 39.765625 | 42.375000, 42.460938, 42.281250, 42.296875 | 39.771484 | 42.353516 | +6.492167% | No trigger |
| synthetic61 | native_memory_after_calls.rss_bytes | MiB | 190.265625, 189.777344, 190.046875, 190.027344 | 194.164062, 194.347656, 194.136719, 194.234375 | 190.029297 | 194.220703 | +2.205663% | No trigger |
| synthetic61 | native_memory_after_calls.hwm_bytes | MiB | 190.265625, 189.777344, 190.046875, 190.027344 | 194.164062, 194.347656, 194.136719, 194.234375 | 190.029297 | 194.220703 | +2.205663% | No trigger |
| synthetic61 | mcp_server_memory_after_calls.rss_bytes | MiB | 61.597656, 61.156250, 61.585938, 61.433594 | 60.730469, 60.894531, 60.652344, 60.730469 | 61.443359 | 60.751953 | -1.125274% | No trigger |
| synthetic61 | mcp_server_memory_after_calls.hwm_bytes | MiB | 61.597656, 61.281250, 61.585938, 61.433594 | 60.730469, 60.894531, 60.652344, 60.730469 | 61.474609 | 60.751953 | -1.175536% | No trigger |
| synthetic61 | mcp_sessions.mcp-token1024.mcp_startup_to_initialize_ms | ms | 538.212015, 527.632247, 546.299695, 527.135731 | 545.824802, 535.779039, 544.468958, 536.087054 | 534.819922 | 540.539963 | +1.069527% | No trigger |
| synthetic61 | mcp_sessions.mcp-token1024.mcp_server_memory_after_calls.rss_bytes | MiB | 105.386719, 105.425781, 105.542969, 105.445312 | 105.000000, 106.820312, 105.945312, 104.812500 | 105.450195 | 105.644531 | +0.184292% | No trigger |
| synthetic61 | mcp_sessions.mcp-token1024.mcp_server_memory_after_calls.hwm_bytes | MiB | 105.386719, 105.425781, 105.542969, 105.445312 | 105.000000, 106.820312, 105.945312, 104.812500 | 105.450195 | 105.644531 | +0.184292% | No trigger |
| public1015 | runtime_import_ms | ms | 28.134701, 27.847884, 27.579635, 27.497201 | 30.899379, 30.980737, 30.920366, 30.220358 | 27.764855 | 30.755210 | +10.770288% | Review required |
| public1015 | native_open_ms | ms | 23.103435, 25.172806, 22.757635, 24.253673 | 28.614300, 39.683334, 22.066283, 25.325550 | 23.821887 | 28.922367 | +21.410896% | Review required |
| public1015 | fresh_ingestion_ms | ms | 803.744570, 788.547733, 786.608462, 791.400280 | 804.229853, 806.297096, 795.347512, 797.325521 | 792.575261 | 800.799996 | +1.037723% | No trigger |
| public1015 | unchanged_reingestion_ms | ms | 204.820951, 204.577145, 204.723618, 203.881522 | 202.165077, 203.562421, 197.086045, 201.249423 | 204.500809 | 201.015741 | -1.704183% | No trigger |
| public1015 | mcp_startup_to_initialize_ms | ms | 550.285791, 542.203103, 537.641724, 558.611751 | 547.376665, 552.447768, 568.688083, 542.720923 | 547.185592 | 552.808360 | +1.027580% | No trigger |
| public1015 | native_memory_after_ingestion.rss_bytes | MiB | 42.722656, 42.656250, 42.726562, 42.804688 | 44.738281, 44.617188, 44.628906, 44.617188 | 42.727539 | 44.650391 | +4.500263% | No trigger |
| public1015 | native_memory_after_ingestion.hwm_bytes | MiB | 50.292969, 50.320312, 50.460938, 50.457031 | 51.269531, 51.042969, 51.265625, 51.062500 | 50.382812 | 51.160156 | +1.542875% | No trigger |
| public1015 | native_memory_after_calls.rss_bytes | MiB | 213.867188, 213.761719, 213.808594, 213.945312 | 218.515625, 218.652344, 218.484375, 218.437500 | 213.845703 | 218.522461 | +2.186978% | No trigger |
| public1015 | native_memory_after_calls.hwm_bytes | MiB | 213.867188, 213.761719, 213.808594, 213.945312 | 218.515625, 218.652344, 218.484375, 218.437500 | 213.845703 | 218.522461 | +2.186978% | No trigger |
| public1015 | mcp_server_memory_after_calls.rss_bytes | MiB | 60.582031, 60.625000, 60.578125, 60.585938 | 60.218750, 60.246094, 60.250000, 60.269531 | 60.592773 | 60.246094 | -0.572147% | No trigger |
| public1015 | mcp_server_memory_after_calls.hwm_bytes | MiB | 60.582031, 60.625000, 60.578125, 60.585938 | 60.218750, 60.246094, 60.250000, 60.269531 | 60.592773 | 60.246094 | -0.572147% | No trigger |
| public1015 | mcp_sessions.mcp-token1024.mcp_startup_to_initialize_ms | ms | 536.510598, 539.375901, 529.220740, 556.134839 | 538.753634, 535.133368, 544.472989, 536.686322 | 540.310520 | 538.761578 | -0.286676% | No trigger |
| public1015 | mcp_sessions.mcp-token1024.mcp_server_memory_after_calls.rss_bytes | MiB | 104.527344, 104.386719, 103.597656, 104.625000 | 104.167969, 104.410156, 104.292969, 104.339844 | 104.284180 | 104.302734 | +0.017792% | No trigger |
| public1015 | mcp_sessions.mcp-token1024.mcp_server_memory_after_calls.hwm_bytes | MiB | 104.527344, 104.386719, 103.597656, 104.625000 | 104.167969, 104.410156, 104.292969, 104.339844 | 104.284180 | 104.302734 | +0.017792% | No trigger |

RSS is a process observation, not the exact-count memo allocation. High-water marks can retain earlier peaks and do not establish equal live memory. The experiment does not isolate the cause of any individual resource change. Startup, ingestion, cache and index costs remain visible.

### Logical database storage

| Corpus | Phase | Baseline mean bytes | C7 mean bytes | Difference bytes | Change |
| --- | --- | --- | --- | --- | --- |
| synthetic61 | storage_after_ingestion_live | 20508672 | 20733952 | +225280 | +1.098462% |
| synthetic61 | storage_after_mcp_live | 20508672 | 20733952 | +225280 | +1.098462% |
| synthetic61 | storage_after_checkpoint | 20508672 | 20733952 | +225280 | +1.098462% |
| public1015 | storage_after_ingestion_live | 12881920 | 13053952 | +172032 | +1.335453% |
| public1015 | storage_after_mcp_live | 12881920 | 13053952 | +172032 | +1.335453% |
| public1015 | storage_after_checkpoint | 12881920 | 13053952 | +172032 | +1.335453% |

These are SQLite logical page-count × page-size observations, not index-only allocations or filesystem/RSS measurements. Earlier C3 one-sample upgrade/index probes retain their own source identity in the release notes; they are not new C7 upgrade measurements.

## All 32 native memo configuration observations

Snapshots occur outside timers: before the configuration, immediately after its retained first call, and after the configuration. Entries and text bytes show those three snapshots. Counter deltas below belong only to that configuration. A first call may already hit because later native settings inherit the same connection; this is disclosed, not removed from the samples.

| Worker | Configuration | First query ID | Entries before/first/after | Text bytes before/first/after | First-call hits/misses | All hits/misses | Evictions | Uncertified bypasses | Oversized bypasses | Invalidations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| r0-synthetic61-candidate | native-char4000 | orchid-journal-indigo-manual-middle | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 |
| r0-synthetic61-candidate | native-token512 | comet-cache-paraphrase | 0 / 7 / 767 | 0 / 9519 / 1217779 | 0 / 7 | 548 / 767 | 0 | 2616 | 0 | 0 |
| r0-synthetic61-candidate | native-token1024 | orchid-cache-current | 767 / 767 / 943 | 1217779 / 1217779 / 1488100 | 6 / 0 | 907 / 176 | 0 | 1088 | 0 | 0 |
| r0-synthetic61-candidate | native-token2048 | umber-poison | 943 / 946 / 1117 | 1488100 / 1496203 / 1749265 | 5 / 3 | 859 / 174 | 0 | 291 | 0 | 0 |
| r0-public1015-candidate | native-char4000 | conv-48-q0092 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 |
| r0-public1015-candidate | native-token512 | conv-43-q0229 | 0 / 8 / 2048 | 0 / 6031 / 1546625 | 0 / 8 | 4131 / 2194 | 146 | 9913 | 0 | 0 |
| r0-public1015-candidate | native-token1024 | conv-44-q0081 | 2048 / 2048 / 2048 | 1546625 / 1546599 / 1501628 | 3 / 2 | 4099 / 1028 | 1028 | 2219 | 0 | 0 |
| r0-public1015-candidate | native-token2048 | conv-43-q0171 | 2048 / 2048 / 2048 | 1501628 / 1501628 / 1516725 | 5 / 0 | 4952 / 121 | 121 | 0 | 0 | 0 |
| r1-synthetic61-candidate | native-char4000 | xenon-canary | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 |
| r1-synthetic61-candidate | native-token512 | comet-worker-concurrency | 0 / 5 / 767 | 0 / 4492 / 1217779 | 0 / 5 | 548 / 767 | 0 | 2616 | 0 | 0 |
| r1-synthetic61-candidate | native-token1024 | comet-journal-cedar-multi-section | 767 / 768 / 943 | 1217779 / 1218789 / 1488100 | 4 / 1 | 907 / 176 | 0 | 1088 | 0 | 0 |
| r1-synthetic61-candidate | native-token2048 | pebble-refresh | 943 / 944 / 1117 | 1488100 / 1490592 / 1749265 | 4 / 1 | 859 / 174 | 0 | 291 | 0 | 0 |
| r1-public1015-candidate | native-char4000 | conv-41-q0181 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 |
| r1-public1015-candidate | native-token512 | conv-50-q0177 | 0 / 7 / 2048 | 0 / 5566 / 1542373 | 0 / 7 | 4131 / 2194 | 146 | 9913 | 0 | 0 |
| r1-public1015-candidate | native-token1024 | conv-42-q0219 | 2048 / 2048 / 2048 | 1542373 / 1542455 / 1501039 | 3 / 2 | 4084 / 1043 | 1043 | 2219 | 0 | 0 |
| r1-public1015-candidate | native-token2048 | conv-43-q0029 | 2048 / 2048 / 2048 | 1501039 / 1501039 / 1516509 | 5 / 0 | 4952 / 121 | 121 | 0 | 0 | 0 |
| r2-synthetic61-candidate | native-char4000 | umber-unrelated | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 |
| r2-synthetic61-candidate | native-token512 | umber-cache-paraphrase | 0 / 8 / 767 | 0 / 16364 / 1217779 | 0 / 8 | 548 / 767 | 0 | 2616 | 0 | 0 |
| r2-synthetic61-candidate | native-token1024 | pebble-journal-indigo-manual-middle | 767 / 769 / 943 | 1217779 / 1222447 / 1488100 | 8 / 2 | 907 / 176 | 0 | 1088 | 0 | 0 |
| r2-synthetic61-candidate | native-token2048 | solstice-journal-cedar-manual-middle | 943 / 945 / 1117 | 1488100 / 1490008 / 1749265 | 3 / 2 | 859 / 174 | 0 | 291 | 0 | 0 |
| r2-public1015-candidate | native-char4000 | conv-50-q0197 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 |
| r2-public1015-candidate | native-token512 | conv-26-q0087 | 0 / 7 / 2048 | 0 / 8426 / 1546474 | 0 / 7 | 4138 / 2187 | 139 | 9913 | 0 | 0 |
| r2-public1015-candidate | native-token1024 | conv-42-q0178 | 2048 / 2048 / 2048 | 1546474 / 1546330 / 1507938 | 2 / 3 | 4106 / 1021 | 1021 | 2219 | 0 | 0 |
| r2-public1015-candidate | native-token2048 | conv-43-q0206 | 2048 / 2048 / 2048 | 1507938 / 1507938 / 1516367 | 5 / 0 | 4952 / 121 | 121 | 0 | 0 | 0 |
| r3-synthetic61-candidate | native-char4000 | xenon-journal-cedar-manual-middle | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 |
| r3-synthetic61-candidate | native-token512 | willow-journal-cedar-manual-late | 0 / 7 / 767 | 0 / 7727 / 1217779 | 0 / 7 | 548 / 767 | 0 | 2616 | 0 | 0 |
| r3-synthetic61-candidate | native-token1024 | xenon-poison | 767 / 768 / 943 | 1217779 / 1218426 / 1488100 | 4 / 1 | 907 / 176 | 0 | 1088 | 0 | 0 |
| r3-synthetic61-candidate | native-token2048 | orchid-journal-cedar-multi-section | 943 / 943 / 1117 | 1488100 / 1488100 / 1749265 | 8 / 0 | 859 / 174 | 0 | 291 | 0 | 0 |
| r3-public1015-candidate | native-char4000 | conv-43-q0106 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 |
| r3-public1015-candidate | native-token512 | conv-41-q0116 | 0 / 7 / 2048 | 0 / 4549 / 1546574 | 0 / 7 | 4138 / 2187 | 139 | 9913 | 0 | 0 |
| r3-public1015-candidate | native-token1024 | conv-43-q0232 | 2048 / 2048 / 2048 | 1546574 / 1546879 / 1505000 | 3 / 2 | 4091 / 1036 | 1036 | 2219 | 0 | 0 |
| r3-public1015-candidate | native-token2048 | conv-50-q0150 | 2048 / 2048 / 2048 | 1505000 / 1504644 / 1513939 | 4 / 1 | 4952 / 121 | 121 | 0 | 0 | 0 |

The maximum **recorded snapshot** contains 2,048 entries and 1,749,265 retained text-object bytes. These sampled maxima are not a continuously observed peak. The independent audit checks every snapshot against 2,048 entries and 2,097,152 bytes and checks exact continuity across native configurations.

### Aggregate eligible count-lookup shares

| Corpus | Configuration | Hits | Misses | Hits / (hits + misses) | Evictions | Uncertified bypasses |
| --- | --- | --- | --- | --- | --- | --- |
| synthetic61 | native-token512 | 2192 | 3068 | 41.673004% | 0 | 10464 |
| synthetic61 | native-token1024 | 3628 | 704 | 83.748846% | 0 | 4352 |
| synthetic61 | native-token2048 | 3436 | 696 | 83.155857% | 0 | 1164 |
| public1015 | native-token512 | 16538 | 8762 | 65.367589% | 570 | 39652 |
| public1015 | native-token1024 | 16380 | 4128 | 79.871270% | 4128 | 8876 |
| public1015 | native-token2048 | 19808 | 484 | 97.614824% | 484 | 0 |

These are text-count lookup shares, not query hit rates or causal speedup estimates. Bypassed custom/uncertified count operations are outside that denominator. Published v0.3.2 has no such counters and is recorded as unavailable. Actual MCP counters were not collected; no MCP hit rate is inferred.

## Correctness history, development and old-cohort compatibility

C7 changes only MCP stdout scheduling relative to C6. On the certified official SDK 1.30.0 standard-stream path, the same native UTF-8 write and immediate flush run in one default worker dispatch per message. The paired SDK flush acknowledges the successful flush; standalone/error paths still delegate. Official serialization, framing, stdin, initialization, lifespan, normal cache writes and non-abandoning thread cancellation remain intact. Unknown SDK versions, replaced/custom methods and unsupported streams use the original FastMCP path. No cross-message text buffer or deferred flushing is added. C6's bounded source-turn batches and single-use reference parsing remain unchanged, including snapshot integrity and mutable-output independence.

The [directed correctness receipt](../benchmarks/reports/round5-c7-correctness.json) records 26 unique passing cases, including 11 new C7 cases. Its dependency-free invocation executes six of the same cases and skips twenty; these are not additional unique tests. The [independent source review](../benchmarks/reports/round5-c7-source-review.json) and retained earlier test logs preserve the pre-timing stream/method guard corrections. Complete SDK initialization/tool/result payloads and five immediate response flushes are checked, with five combined dispatches instead of ten separate write/flush dispatches. These operation counts are correctness evidence, not a substitute for measured latency. Final release publication still needs all nine CI jobs on its own exact commit.

The sole native development run retained **18,928 calls / 9,464 complete output pairs**, with its own native-only aggregate p95 gain **9.1179243523%**. Its 2 pooled and 6 per-round adverse metrics remain in the [native development archive](../benchmarks/reports/round5-development/candidate-c7-full/summary.json). It contains no actual-MCP or formal RSS acceptance evidence and supplies no missing formal gate.

Final-source C7 reproduces **2,304 / 2,304** saved default v0.3.2 Hotpot256 payload hashes: **1,536 native** calls across both encoders and three caps, plus **768 component** calls. All **4,608** original start/finish events were reconciled. The [compatibility summary](../benchmarks/reports/round5-c7-hotpot-regression.summary.json) retains exact source/input/helper identities and unchanged source/index/document projections. This reuses previously scored questions; it adds no new quality, competitor timing, Q2, generated-answer accuracy or unseen-domain claim.

### Actual-MCP development: original aggregation failure retained

The same hosted development invocation completed all **4,060 actual-SDK calls** after the 18,928 native calls, for **22,988 calls** in total. Its original MCP aggregate remains **failed** with `Cross-source archive/ingestion differs`; the original helper and report were not edited or rerun. A separate [saved-data supplement](../benchmarks/reports/round5-c7-mcp-development-supplement.json) verifies **2,030 complete output pairs**, **8,120 attempt events**, all worker/call checks, first calls and recorded resources. That supplemental audit is a development diagnosis, not formal or release acceptance.

Independently ingested archives have different full snapshot hashes, including the two baseline archives. Each full snapshot remains unchanged within its own worker. Full snapshots include host creation/update timestamps; the saved indexed projections omit some of those fields. Only hashes and projections were retained, so the supplement cannot prove timestamps are the only differing bytes or establish equality of omitted project fields. The mismatch and this limit remain explicit.

| Development round | Baseline p50 ms | C7 p50 ms | p50 change | Baseline p95 ms | C7 p95 ms | p95 change | Baseline mean ms | C7 mean ms | Mean change |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| pooled | 4.039552 | 3.550806 | -12.099027% | 4.789967 | 4.089882 | -14.615657% | 4.176652 | 3.672844 | -12.062497% |
| 0 | 4.211630 | 3.550503 | -15.697652% | 4.955983 | 4.140774 | -16.448988% | 4.326681 | 3.679432 | -14.959492% |
| 1 | 3.929513 | 3.553472 | -9.569659% | 4.463989 | 4.021676 | -9.908465% | 4.026623 | 3.666256 | -8.949623% |

Round 0 uses AB and round 1 uses BA. Pooled development p95 improves 14.615657%; round 1 improves only 9.908465%. These two-round observations and their original failed aggregation cannot supply a missing gate in the separate four-round formal run. All development adverse latency and resource observations remain in the supplement.

The complete [C3 rejection](round5-performance-review.md) remains unchanged: aggregate p95 gain 10.4995860260%, best public native gain 10.4825741541%, public actual-MCP gain 5.1469620015%; original accepted:false. Its figures are not added to C7.

The complete [C5 rejection](round5-c5-performance-review.md) remains unchanged: aggregate p95 gain 15.2207914464%, best public native gain 15.4221732781%, public actual-MCP gain 6.6731813400%; original accepted:false. Its figures are not added to C7.

The complete [C6 rejection](round5-c6-performance-review.md) remains unchanged: aggregate p95 gain 14.9191726889%, best public native gain 16.2867851334%, public actual-MCP gain 5.7989107559%; original accepted:false. Its figures are not added to C7.

C4 has retained development evidence and was never a bound formal acceptance. C7's separate source, binding and single hosted result determine its own verdict. No successful subset, alternative source, repeated formal sample or earlier result replaces an adverse observation.

## Decision scope and reproducible evidence

Numerical gates pass; the original automatic accepted:false records three resource costs requiring explicit review. All observed values above are from the saved C7 run. Repeated old queries on one host do not establish statistical significance, unseen-domain quality, universal speedup or whole-product superiority over another repository. Competitors were not remeasured.

[Full original report](../benchmarks/reports/round5-c7-performance-43563390252-1/report.json.gz) · [Original summary](../benchmarks/reports/round5-c7-performance-43563390252-1/report.summary.json) · [Independent arithmetic audit](../benchmarks/reports/round5-c7-performance-independent-audit.json) · [Strict saved-ledger audit](../benchmarks/reports/round5-c7-performance-local-audit.json)

| Artifact | SHA256 |
| --- | --- |
| benchmarks/reports/round5-c7-performance-43563390252-1/report.json.gz | `156087043702b5f223f898800547c576f469ac780066b0af431227cfeda66b25` |
| benchmarks/reports/round5-c7-performance-43563390252-1/report.summary.json | `16af31606dcfcbd2a443b56bf4ec9c0aa0f0bf89da8de5811c07fb7d924c4262` |
| benchmarks/reports/round5-c7-performance-independent-audit.json | `f5464289fabf478af390a3f45313768c825f4cfa57f3caf0a8ab995e5be1056f` |
| benchmarks/reports/round5-c7-performance-local-audit.json | `9e9fbc2cb79a3060276d7d7d4560c5aef3dcbcaea76fcf5c4c2552e28d35c225` |
| benchmarks/experiments/round5-c7-performance-binding.json | `2560b0eae9d3332fb09da43fd49ebef069b8e41ddaef0fe9df1880db1e132588` |
| benchmarks/reports/round5-c7-hotpot-regression.summary.json | `78fa9bf20a79921b8234d90c627d92ba470c9c83400ced5014a2f5cdb89250db` |
| benchmarks/reports/round5-development/candidate-c7-full/summary.json | `cb613c3ec0006c3eba5c16bdb7c03e11547e6783cdc4f00e70484470caad7cf5` |
| benchmarks/reports/round5-c7-mcp-development-supplement.json | `4f5540e480711cad2ba1375cabfe981de154bf298e2a0dd07d9242e073bfdeef` |
| scripts/render_round5_c7_performance_review.py | `43190b72799086fa5e520f7899022694d4cbd0a49010e7a7ac72d69a2d8b996a` |

The release gate remains separate: final-commit CI, approved exact runtime, package and asset verification, public installer verification and any required explicit resource acceptance must all complete. This review never writes the runtime approval table or modifies raw reports.

## Separate reviewed release decision

The [recorded decision](../benchmarks/experiments/round5-c7-resource-decision.json), dated 2026-11-14 and SHA256 `6f011ed654ca30bcd7a3833021b53f45af1afa967f84d722f760ec479b3c4f72`, records `release_accepted:true` after two independent resource reviews under the original registered policy. This is a distinct reviewed decision. The original report, audits, automatic `numeric_gate_passed:true`, `accepted:false`, failed workflow conclusion and all tables above are retained. No timing, threshold, sample, source or original verdict was replaced.

The coordinator accepted the following measured startup costs for the measured persistent-service use, with the unchanged numerical retrieval gates satisfied. These arithmetic differences use the same four retained samples per source and cohort:

| Corpus label | Startup metric | Baseline mean ms | C7 mean ms | Additional mean ms | Mean change |
| --- | --- | --- | --- | --- | --- |
| synthetic61 | runtime_import_ms | 27.89452125 | 31.09176525 | +3.19724400 | +11.461907% |
| public1015 | runtime_import_ms | 27.76485525 | 30.75521000 | +2.99035475 | +10.770288% |
| public1015 | native_open_ms | 23.82188725 | 28.92236675 | +5.10047950 | +21.410896% |

The [independent resource explanation](round5-c7-resource-review.md) records the cause assessment and its limits. Added Python source compilation, definitions and initialization, and added empty-database schema/index/pager setup are code-supported cost sources; their quantitative contributions were not isolated. The import probe does not execute the MCP stdout adapter or token_budget module, so these import increases cannot be assigned to C7's transport change. Both native-open cohort labels measure a fresh empty database before ingestion; the public label does not show a corpus-size cause.

The public candidate opening sample of **39.683334 ms** remains included without a proven I/O or scheduler explanation. The synthetic baseline opening sample of **946.793415 ms** also remains included; its apparent improvement is not treated as a benefit or used to offset the three costs. Startup intervals overlap and must not be added. Short-lived processes and workloads that repeatedly create archives may place more weight on these startup costs; four rounds do not establish worst-case bounds or universal superiority.

The decision and both reviews are pinned to the same baseline/candidate runtime hashes, final result commit, original report and summary. The decision also binds the original plan and performance binding, and reproduces the exact three resource triggers. The renderer checks these identities and all review-file hashes before emitting this section. No new measurement was made for either review or this decision.

[First independent review](../benchmarks/reports/round5-c7-resource-independent-review.json) · [Second independent review](../benchmarks/reports/round5-c7-resource-secondary-review.json) · [Detailed resource explanation](round5-c7-resource-review.md)

| Reviewed artifact | SHA256 |
| --- | --- |
| benchmarks/experiments/round5-c7-resource-decision.json | `6f011ed654ca30bcd7a3833021b53f45af1afa967f84d722f760ec479b3c4f72` |
| benchmarks/reports/round5-c7-resource-independent-review.json | `656dd5562b06fe37b279f812b3ca5dfa3d38c348b6e19ce7c7faad68f52a2725` |
| benchmarks/reports/round5-c7-resource-secondary-review.json | `df6b7b8cceeafb4e09ae674c19cd695ce7477831ddedc92ccb532662d0d3ac2f` |
| docs/round5-c7-resource-review.md | `0501664f517ebf741a26bd665fe2cfcf54b5a1f03e519b88ad65132df71f5649` |

This resource decision satisfies the original plan's explicit-review requirement; it does not assert that publication gates have already passed. The remaining recorded release gates are: final exact-source nine-job CI; approved runtime hash gate; wheel and sdist source/install verification; remote release asset hash verification; public installer acceptance. The old C3/C5/C6 formal rejections, original C7 development aggregation failure and historical competitor limits above remain unchanged. Competitors were not remeasured for C7.
