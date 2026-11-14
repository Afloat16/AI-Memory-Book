# Round-five C6 formal performance review — rejected

**The complete run fails its registered numerical acceptance; accepted:false is retained.** This is the sole frozen C6 run against published v0.3.2. All 56,784 recorded calls completed, and all 28,392 complete non-timing output pairs match. This review preserves the original decision; it does not approve a release or replace final-commit CI and packaging.

The independent arithmetic and original report both retain `numeric_gate_passed:false` and `accepted:false`. The observed aggregate p95 gain is **14.9191726889%**, best public native-token p95 gain **16.2867851334%**, and public actual-MCP token1024 p95 gain **5.7989107559%**.

## Frozen identities and retained evidence

| Role | Commit | Runtime SHA256 |
| --- | --- | --- |
| baseline | `692fb959ddf8934c5f516ba3d74ceb4385a2fa82` | `179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93` |
| candidate | `1bd97221e31e8e975498ece00f4bbfb3e0426aac` | `cfffd8a21374cbf9152bbbc98a6a9847a1e22401f16179112e2f79eef181ff78` |

Evaluator `0bd9ccf48bc9ed6a666888838ca11580c3104b98`; binding commit `4d737fc60a12b60433f6f020614b296908b4c833`; binding SHA256 `2b57caea5b3d7f12b38aba9472d798e846a5231b936551784f0963259e2a715a`; final hosted result commit `c6b384778e12ce9c72771911af37bbb2c5d3474f`. All **51 evaluator input hashes** were verified against their bound Git objects, including retained C3/C4/C5 inputs and both prior formal rejections.

[Sole run 43557136276-1](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43557136276) · [Original plan](../benchmarks/experiments/round5-plan.json) · [C6 registration](../benchmarks/experiments/round5-c6-addendum.json) · [Frozen binding](../benchmarks/experiments/round5-c6-performance-binding.json) · [Source review](../benchmarks/reports/round5-c6-source-review.json)

Saved measurement interval: **2026-11-14T04:33:19.087079+00:00 → 2026-11-14T04:46:15.985834+00:00**. The observed host reports **4 CPUs**, Linux-7.0.0-1017-azure-x86_64-with-glibc2.39, Python **3.12.16** and SQLite **3.45.1**. Frozen packages: `{"mcp": "1.30.0", "pydantic": "2.14.3", "tiktoken": "0.12.0"}`. These describe this run and do not establish a hardware-independent guarantee.

## Matrix and timing boundaries

The full old cohorts contain 168 synthetic and 1,015 public-conversation questions. Six configurations and four balanced **AB/BA/BA/AB** rounds produce sixteen sequential worker processes and twelve pooled cells. Character settings use 4,000 characters; token settings use cl100k_base, an 8,000-character ceiling, the specified 512/1,024/2,048-token cap and at most five results.

**Native query-result caching is disabled; derived exact-count reuse is enabled.** Each fresh candidate MemoryBook starts without an allocated memo. Character recall leaves it absent; native token512 starts empty. Later token1024 and token2048 configurations naturally reuse counts from earlier configurations on the same connection. All first queries remain included. No extra warmup, discarded first query or selective clearing is introduced. Earlier shorthand such as 'uncached API' describes query-result caching.

**Each actual official-SDK MCP configuration starts a fresh server process.** Query-result cache entries are cleared outside the timer. The normal server cache write, serialization, server work and SDK roundtrip remain timed. The derived memo may warm naturally inside that process; no private MCP memo counters are exposed. Native hit rates cannot be assigned to MCP. OS/SQLite warmth remains possible: this is not a cold-storage experiment or an experiment with every cache disabled.

The per-connection memo retains at most **2,048 entries / 2,097,152 post-encode text-object bytes**, shared by the supported encoders. Key/container/count/encoder overhead is additional. The separate **4,096 KiB** pager target is connection-local. Neither setting caps whole-process memory. Native RSS includes evaluator and corpus allocations; actual MCP server memory is sampled separately.

## Complete-output and saved-record audit

The [independent auditor](../scripts/audit_round5_c6_performance.py), SHA256 `fe9bf79e6c998ae6aa9523a2876ec2111f5c66a9f184c3fa1de69f3fed9027e2`, uses only standard-library saved-data and Git-object reads. It performs zero retrieval, tokenizer/model, test or timing workloads. The frozen evaluator's separate strict saved-ledger audit also adds no calls.

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

| Corpus | Configuration | Baseline p50 ms | C6 p50 ms | p50 change | Baseline p95 ms | C6 p95 ms | p95 change | Baseline mean ms | C6 mean ms | Mean change |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| synthetic61 | native-char4000 | 4.541723 | 4.228350 | -6.899892% | 14.278602 | 12.996213 | -8.981200% | 5.954210 | 5.388284 | -9.504636% |
| synthetic61 | mcp-char4000 | 6.943867 | 6.461315 | -6.949334% | 17.184052 | 15.743154 | -8.385086% | 8.326368 | 7.712924 | -7.367488% |
| synthetic61 | native-token512 | 8.391722 | 5.978261 | -28.760021% | 21.438831 | 16.321589 | -23.869037% | 9.784342 | 7.191660 | -26.498282% |
| synthetic61 | native-token1024 | 6.643844 | 4.614407 | -30.546121% | 21.838092 | 15.431031 | -29.338921% | 8.480738 | 5.971257 | -29.590359% |
| synthetic61 | native-token2048 | 5.231212 | 4.452305 | -14.889618% | 18.814027 | 15.832996 | -15.844729% | 7.236156 | 6.055399 | -16.317464% |
| synthetic61 | mcp-token1024 | 9.144079 | 7.413941 | -18.920856% | 24.759238 | 19.025318 | -23.158707% | 11.828233 | 9.700485 | -17.988728% |
| public1015 | native-char4000 | 3.182052 | 3.029792 | -4.784948% | 3.905834 | 3.677599 | -5.843441% | 3.202431 | 3.052154 | -4.692590% |
| public1015 | mcp-char4000 | 5.345829 | 5.102188 | -4.557591% | 6.455572 | 6.025798 | -6.657408% | 5.407698 | 5.161750 | -4.548099% |
| public1015 | native-token512 | 4.702672 | 3.629545 | -22.819516% | 5.636683 | 4.718648 | -16.286785% | 4.724156 | 3.695100 | -21.782854% |
| public1015 | native-token1024 | 4.002023 | 3.407140 | -14.864557% | 4.868285 | 4.083408 | -16.122253% | 4.017407 | 3.411626 | -15.078897% |
| public1015 | native-token2048 | 3.889143 | 3.300400 | -15.138117% | 4.647817 | 3.965404 | -14.682435% | 3.919954 | 3.310289 | -15.552854% |
| public1015 | mcp-token1024 | 6.101527 | 5.733859 | -6.025835% | 7.289725 | 6.867000 | -5.798911% | 6.309019 | 5.978141 | -5.244516% |

## Unchanged acceptance gates

For each cell, r is C6 pooled p95 divided by baseline pooled p95. The aggregate is 100 × (1 − exp(sum(log(r)) / 12)). Each cell has equal weight; it is not a query-weighted mean or the geometric mean of percentage gains. Native gains cannot replace an actual-MCP gate.

| Requirement | Threshold | Observed | Margin | Decision |
| --- | --- | --- | --- | --- |
| Aggregate pooled p95 improvement | at least 10% | 14.9191726889% | +4.9191726889 percentage points | Satisfied |
| Best public native-token p95 improvement | at least 15% | 16.2867851334% | +1.2867851334 percentage points | Satisfied |
| Public actual-MCP token1024 p95 improvement | at least 10% | 5.7989107559% | -4.2010892441 percentage points | **Failed** |
| Complete stable outputs and recorded invariants | all equal; zero failures | 28,392 equal pairs; zero failures | — | Satisfied |
| Pooled p50/p95 regression | no increase greater than 5% | 0 flagged comparisons | — | Satisfied |
| Resource mean increase | greater than 10% requires explicit review | 0 triggered comparisons | — | No exception needed |

The original result remains `accepted:false`. The failure or required review is not overridden by this document.

## Every round: all 48 cohort/configuration cells

Round 0 is AB, rounds 1 and 2 are BA, and round 3 is AB. Each cell retains 168 or 1,015 samples per version. No round or adverse value is omitted.

### synthetic61

| Round | Configuration | Baseline p50 ms | C6 p50 ms | p50 change | Baseline p95 ms | C6 p95 ms | p95 change | Baseline mean ms | C6 mean ms | Mean change |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | native-char4000 | 4.445037 | 4.260741 | -4.146107% | 13.986550 | 13.378135 | -4.350000% | 5.831939 | 5.412624 | -7.189981% |
| 0 | mcp-char4000 | 6.455241 | 6.459978 | +0.073374% | 15.860192 | 15.390368 | -2.962288% | 7.785517 | 7.773105 | -0.159428% |
| 0 | native-token512 | 8.378799 | 5.900980 | -29.572480% | 21.197007 | 16.071535 | -24.180169% | 9.612397 | 7.203284 | -25.062560% |
| 0 | native-token1024 | 6.587416 | 4.627156 | -29.757634% | 21.787219 | 15.293486 | -29.805241% | 8.524259 | 5.972354 | -29.936963% |
| 0 | native-token2048 | 5.279940 | 4.542848 | -13.960236% | 19.380356 | 15.876828 | -18.077731% | 7.327756 | 6.105284 | -16.682763% |
| 0 | mcp-token1024 | 9.337232 | 7.528237 | -19.373995% | 24.769309 | 19.154112 | -22.669980% | 11.865478 | 9.833777 | -17.122792% |
| 1 | native-char4000 | 4.499779 | 4.142336 | -7.943568% | 14.115046 | 12.493838 | -11.485672% | 5.871879 | 5.258718 | -10.442332% |
| 1 | mcp-char4000 | 6.580961 | 6.155813 | -6.460272% | 16.463550 | 14.836082 | -9.885278% | 7.944152 | 7.314964 | -7.920136% |
| 1 | native-token512 | 8.129108 | 5.742581 | -29.357803% | 20.630551 | 15.781992 | -23.501840% | 9.487532 | 7.040043 | -25.796894% |
| 1 | native-token1024 | 6.520783 | 4.436630 | -31.961686% | 21.319846 | 15.472257 | -27.427912% | 8.203277 | 5.870124 | -28.441726% |
| 1 | native-token2048 | 5.119535 | 4.412821 | -13.804271% | 18.617784 | 15.540849 | -16.526860% | 7.118673 | 6.011252 | -15.556561% |
| 1 | mcp-token1024 | 9.035958 | 7.122272 | -21.178568% | 24.098114 | 18.460334 | -23.395109% | 11.498408 | 9.295853 | -19.155300% |
| 2 | native-char4000 | 4.559803 | 4.228350 | -7.269031% | 14.345030 | 12.875622 | -10.243327% | 6.049980 | 5.346356 | -11.630197% |
| 2 | mcp-char4000 | 7.280017 | 6.488396 | -10.873896% | 17.204943 | 15.548977 | -9.624939% | 8.781493 | 7.710106 | -12.200512% |
| 2 | native-token512 | 8.625953 | 5.965206 | -30.845823% | 21.771209 | 16.738835 | -23.114813% | 9.969526 | 7.337950 | -26.396199% |
| 2 | native-token1024 | 6.889230 | 4.757470 | -30.943371% | 22.077734 | 15.844015 | -28.235318% | 8.609621 | 6.195696 | -28.037531% |
| 2 | native-token2048 | 5.320565 | 4.532131 | -14.818614% | 18.938118 | 16.121749 | -14.871428% | 7.277970 | 6.144061 | -15.580012% |
| 2 | mcp-token1024 | 9.370123 | 7.589975 | -18.998119% | 25.120431 | 19.239229 | -23.412027% | 12.110270 | 9.977196 | -17.613757% |
| 3 | native-char4000 | 4.591577 | 4.455470 | -2.964265% | 14.279587 | 13.250409 | -7.207338% | 6.063043 | 5.535440 | -8.701949% |
| 3 | mcp-char4000 | 7.264561 | 6.799903 | -6.396230% | 17.832675 | 16.272361 | -8.749747% | 8.794311 | 8.053521 | -8.423510% |
| 3 | native-token512 | 8.675546 | 5.994506 | -30.903413% | 22.086577 | 16.102540 | -27.093544% | 10.067914 | 7.185361 | -28.631086% |
| 3 | native-token1024 | 6.734433 | 4.551616 | -32.412781% | 21.869489 | 15.165652 | -30.653838% | 8.585796 | 5.846856 | -31.900835% |
| 3 | native-token2048 | 5.277168 | 4.404700 | -16.532875% | 18.648504 | 15.585630 | -16.424236% | 7.220226 | 5.960999 | -17.440274% |
| 3 | mcp-token1024 | 9.037255 | 7.395787 | -18.163347% | 24.752873 | 19.025809 | -23.136967% | 11.838777 | 9.695112 | -18.107153% |

### public1015

| Round | Configuration | Baseline p50 ms | C6 p50 ms | p50 change | Baseline p95 ms | C6 p95 ms | p95 change | Baseline mean ms | C6 mean ms | Mean change |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | native-char4000 | 3.139791 | 3.092882 | -1.494017% | 3.844007 | 3.725426 | -3.084825% | 3.149372 | 3.108591 | -1.294900% |
| 0 | mcp-char4000 | 5.262366 | 5.156460 | -2.012517% | 6.344172 | 6.095465 | -3.920234% | 5.312816 | 5.208653 | -1.960607% |
| 0 | native-token512 | 4.685552 | 3.633761 | -22.447537% | 5.690224 | 4.698380 | -17.430656% | 4.717048 | 3.696887 | -21.627104% |
| 0 | native-token1024 | 3.940588 | 3.403965 | -13.617841% | 4.759377 | 4.122391 | -13.383817% | 3.967220 | 3.421939 | -13.744651% |
| 0 | native-token2048 | 3.868322 | 3.297802 | -14.748514% | 4.550144 | 4.075699 | -10.427022% | 3.900646 | 3.322838 | -14.813139% |
| 0 | mcp-token1024 | 6.005693 | 5.729414 | -4.600285% | 7.079164 | 6.761008 | -4.494251% | 6.199564 | 5.932798 | -4.302977% |
| 1 | native-char4000 | 3.211271 | 2.986107 | -7.011679% | 4.030629 | 3.648771 | -9.473925% | 3.253976 | 3.010418 | -7.484949% |
| 1 | mcp-char4000 | 5.323975 | 4.992442 | -6.227170% | 6.450603 | 5.822231 | -9.741288% | 5.396222 | 5.048799 | -6.438264% |
| 1 | native-token512 | 4.676467 | 3.610351 | -22.797467% | 5.594842 | 4.731291 | -15.434768% | 4.697087 | 3.662282 | -22.030790% |
| 1 | native-token1024 | 3.966962 | 3.384150 | -14.691646% | 4.820941 | 3.980765 | -17.427639% | 3.988809 | 3.378830 | -15.292244% |
| 1 | native-token2048 | 3.850422 | 3.264932 | -15.205866% | 4.616865 | 3.887671 | -15.794142% | 3.881171 | 3.265630 | -15.859668% |
| 1 | mcp-token1024 | 6.289121 | 5.748023 | -8.603714% | 7.393943 | 6.860057 | -7.220592% | 6.461217 | 6.020152 | -6.826342% |
| 2 | native-char4000 | 3.184843 | 3.040252 | -4.539973% | 3.892956 | 3.676770 | -5.553276% | 3.198930 | 3.061632 | -4.292018% |
| 2 | mcp-char4000 | 5.550956 | 5.236261 | -5.669204% | 6.712812 | 6.125046 | -8.755875% | 5.598475 | 5.278501 | -5.715380% |
| 2 | native-token512 | 4.834866 | 3.680554 | -23.874746% | 5.848317 | 4.830809 | -17.398317% | 4.861851 | 3.771827 | -22.419936% |
| 2 | native-token1024 | 4.095747 | 3.420065 | -16.497162% | 4.987150 | 4.101532 | -17.757987% | 4.118846 | 3.433248 | -16.645383% |
| 2 | native-token2048 | 3.986753 | 3.366643 | -15.554262% | 4.782630 | 4.011588 | -16.121713% | 4.023902 | 3.365116 | -16.371829% |
| 2 | mcp-token1024 | 6.269879 | 5.861983 | -6.505644% | 7.441866 | 7.040833 | -5.388878% | 6.476206 | 6.106275 | -5.712146% |
| 3 | native-char4000 | 3.186738 | 3.009173 | -5.571999% | 3.896349 | 3.657624 | -6.126882% | 3.207443 | 3.027974 | -5.595403% |
| 3 | mcp-char4000 | 5.288098 | 5.038994 | -4.710654% | 6.142754 | 5.955440 | -3.049344% | 5.323277 | 5.111048 | -3.986814% |
| 3 | native-token512 | 4.611227 | 3.606259 | -21.793939% | 5.477058 | 4.646578 | -15.162886% | 4.620637 | 3.649403 | -21.019478% |
| 3 | native-token1024 | 3.988276 | 3.417052 | -14.322579% | 4.837362 | 4.090950 | -15.430136% | 3.994754 | 3.412487 | -14.575771% |
| 3 | native-token2048 | 3.853746 | 3.284908 | -14.760651% | 4.574503 | 3.910477 | -14.515819% | 3.874097 | 3.287573 | -15.139622% |
| 3 | mcp-token1024 | 5.903046 | 5.603238 | -5.078869% | 6.914105 | 6.734964 | -2.590947% | 6.099089 | 5.853340 | -4.029278% |

## Every adverse latency observation

### Pooled

No positive latency change was recorded in this category.

### Per round

| Corpus | Configuration | Round | Metric | Increase |
| --- | --- | --- | --- | --- |
| synthetic61 | mcp-char4000 | 0 | p50_ms | +0.073374% |

## All 28 resource comparisons

These retain the four original samples per version and cohort. Acceptance compares arithmetic means in original units; byte observations below are displayed as MiB. A mean increase above 10% requires an explicit cause and independent review. This document does not grant an exception.

| Corpus | Metric | Unit | Baseline four samples | C6 four samples | Baseline mean | C6 mean | Mean change | Resource rule |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| synthetic61 | runtime_import_ms | ms | 27.614215, 26.614543, 27.688928, 27.212004 | 29.492919, 29.971929, 29.824416, 29.869234 | 27.282423 | 29.789624 | +9.189807% | No trigger |
| synthetic61 | native_open_ms | ms | 24.432141, 20.551578, 22.514715, 28.897606 | 28.384103, 23.768313, 28.645704, 22.754989 | 24.099010 | 25.888277 | +7.424650% | No trigger |
| synthetic61 | fresh_ingestion_ms | ms | 866.203409, 849.225242, 869.709614, 885.453903 | 852.369830, 851.854489, 863.494184, 866.855068 | 867.648042 | 858.643393 | -1.037823% | No trigger |
| synthetic61 | unchanged_reingestion_ms | ms | 104.630519, 105.150068, 107.713026, 107.216025 | 104.674057, 103.865289, 104.626856, 106.498703 | 106.177410 | 104.916226 | -1.187808% | No trigger |
| synthetic61 | mcp_startup_to_initialize_ms | ms | 633.502514, 643.292472, 658.803736, 651.005713 | 651.031889, 636.303869, 638.979505, 657.428162 | 646.651109 | 645.935856 | -0.110609% | No trigger |
| synthetic61 | native_memory_after_ingestion.rss_bytes | MiB | 39.359375, 39.265625, 39.250000, 39.410156 | 41.421875, 41.472656, 41.515625, 41.347656 | 39.321289 | 41.439453 | +5.386812% | No trigger |
| synthetic61 | native_memory_after_ingestion.hwm_bytes | MiB | 39.359375, 39.265625, 39.289062, 39.570312 | 42.062500, 41.917969, 42.011719, 42.007812 | 39.371094 | 42.000000 | +6.677250% | No trigger |
| synthetic61 | native_memory_after_calls.rss_bytes | MiB | 189.929688, 190.003906, 189.734375, 190.167969 | 193.820312, 193.902344, 193.890625, 193.667969 | 189.958984 | 193.820312 | +2.032717% | No trigger |
| synthetic61 | native_memory_after_calls.hwm_bytes | MiB | 189.929688, 190.003906, 189.734375, 190.167969 | 193.820312, 193.902344, 193.890625, 193.667969 | 189.958984 | 193.820312 | +2.032717% | No trigger |
| synthetic61 | mcp_server_memory_after_calls.rss_bytes | MiB | 61.593750, 61.589844, 61.453125, 61.636719 | 60.742188, 60.941406, 60.578125, 60.878906 | 61.568359 | 60.785156 | -1.272087% | No trigger |
| synthetic61 | mcp_server_memory_after_calls.hwm_bytes | MiB | 61.593750, 61.589844, 61.453125, 61.636719 | 60.742188, 60.941406, 60.652344, 60.878906 | 61.568359 | 60.803711 | -1.241950% | No trigger |
| synthetic61 | mcp_sessions.mcp-token1024.mcp_startup_to_initialize_ms | ms | 643.795352, 642.131664, 635.342995, 640.729915 | 646.703416, 627.232222, 654.403770, 646.349037 | 640.499981 | 643.672111 | +0.495258% | No trigger |
| synthetic61 | mcp_sessions.mcp-token1024.mcp_server_memory_after_calls.rss_bytes | MiB | 104.542969, 105.312500, 104.625000, 105.437500 | 106.089844, 105.804688, 105.000000, 104.710938 | 104.979492 | 105.401367 | +0.401864% | No trigger |
| synthetic61 | mcp_sessions.mcp-token1024.mcp_server_memory_after_calls.hwm_bytes | MiB | 104.542969, 105.312500, 104.625000, 105.437500 | 106.089844, 105.804688, 105.000000, 104.710938 | 104.979492 | 105.401367 | +0.401864% | No trigger |
| public1015 | runtime_import_ms | ms | 26.902234, 27.980264, 27.943544, 27.225731 | 30.042967, 29.577706, 29.885552, 29.805284 | 27.512943 | 29.827877 | +8.413982% | No trigger |
| public1015 | native_open_ms | ms | 25.626843, 23.494566, 24.728190, 22.625410 | 23.162097, 30.094188, 25.374744, 24.420500 | 24.118752 | 25.762882 | +6.816812% | No trigger |
| public1015 | fresh_ingestion_ms | ms | 798.976260, 792.709719, 793.407731, 783.009693 | 806.249035, 798.718223, 818.582961, 788.470803 | 792.025851 | 803.005255 | +1.386243% | No trigger |
| public1015 | unchanged_reingestion_ms | ms | 203.029695, 202.115072, 205.228623, 202.358234 | 203.792670, 201.910757, 205.238774, 202.936973 | 203.182906 | 203.469793 | +0.141197% | No trigger |
| public1015 | mcp_startup_to_initialize_ms | ms | 645.668562, 643.924918, 656.346306, 661.248039 | 643.198635, 655.197403, 648.604431, 630.642798 | 651.796956 | 644.410817 | -1.133196% | No trigger |
| public1015 | native_memory_after_ingestion.rss_bytes | MiB | 42.468750, 42.542969, 42.535156, 42.402344 | 44.503906, 44.421875, 44.425781, 44.472656 | 42.487305 | 44.456055 | +4.633737% | No trigger |
| public1015 | native_memory_after_ingestion.hwm_bytes | MiB | 50.136719, 50.261719, 50.210938, 50.097656 | 51.109375, 50.847656, 50.894531, 51.011719 | 50.176758 | 50.965820 | +1.572566% | No trigger |
| public1015 | native_memory_after_calls.rss_bytes | MiB | 213.601562, 213.925781, 213.703125, 213.609375 | 218.371094, 218.531250, 218.132812, 218.257812 | 213.709961 | 218.323242 | +2.158665% | No trigger |
| public1015 | native_memory_after_calls.hwm_bytes | MiB | 213.601562, 213.925781, 213.703125, 213.609375 | 218.371094, 218.531250, 218.132812, 218.257812 | 213.709961 | 218.323242 | +2.158665% | No trigger |
| public1015 | mcp_server_memory_after_calls.rss_bytes | MiB | 60.441406, 60.542969, 60.386719, 60.480469 | 60.042969, 60.039062, 60.292969, 60.238281 | 60.462891 | 60.153320 | -0.512001% | No trigger |
| public1015 | mcp_server_memory_after_calls.hwm_bytes | MiB | 60.441406, 60.542969, 60.386719, 60.480469 | 60.042969, 60.039062, 60.292969, 60.238281 | 60.462891 | 60.153320 | -0.512001% | No trigger |
| public1015 | mcp_sessions.mcp-token1024.mcp_startup_to_initialize_ms | ms | 655.635062, 638.429794, 632.375145, 631.849510 | 640.668754, 651.987725, 652.469176, 631.582376 | 639.572378 | 644.177008 | +0.719954% | No trigger |
| public1015 | mcp_sessions.mcp-token1024.mcp_server_memory_after_calls.rss_bytes | MiB | 103.597656, 103.472656, 104.613281, 104.519531 | 104.429688, 104.386719, 105.296875, 104.246094 | 104.050781 | 104.589844 | +0.518076% | No trigger |
| public1015 | mcp_sessions.mcp-token1024.mcp_server_memory_after_calls.hwm_bytes | MiB | 103.597656, 103.472656, 104.613281, 104.519531 | 104.429688, 104.386719, 105.296875, 104.246094 | 104.050781 | 104.589844 | +0.518076% | No trigger |

RSS is a process observation, not the exact-count memo allocation. High-water marks can retain earlier peaks and do not establish equal live memory. The experiment does not isolate the cause of any individual resource change. Startup, ingestion, cache and index costs remain visible.

### Logical database storage

| Corpus | Phase | Baseline mean bytes | C6 mean bytes | Difference bytes | Change |
| --- | --- | --- | --- | --- | --- |
| synthetic61 | storage_after_ingestion_live | 20508672 | 20733952 | +225280 | +1.098462% |
| synthetic61 | storage_after_mcp_live | 20508672 | 20733952 | +225280 | +1.098462% |
| synthetic61 | storage_after_checkpoint | 20508672 | 20733952 | +225280 | +1.098462% |
| public1015 | storage_after_ingestion_live | 12881920 | 13053952 | +172032 | +1.335453% |
| public1015 | storage_after_mcp_live | 12881920 | 13053952 | +172032 | +1.335453% |
| public1015 | storage_after_checkpoint | 12881920 | 13053952 | +172032 | +1.335453% |

These are SQLite logical page-count × page-size observations, not index-only allocations or filesystem/RSS measurements. Earlier C3 one-sample upgrade/index probes retain their own source identity in the release notes; they are not new C6 upgrade measurements.

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

C6 batches at most 400 exact source-turn pairs inside the original read snapshot and permits single-span source-reference reuse at most once per page capture. Source integrity checks, custom/malformed/low-limit fallbacks and nested mutable reference independence remain intact. The pre-timing alias issue and the later isolated-import fixture correction remain in [source review](../benchmarks/reports/round5-c6-source-review.json) and [CI fixture-fix evidence](../benchmarks/reports/round5-c6-ci-fixture-fix.json). Nine green jobs on the fixture-fix commit verify the identical product tree; final release publication still needs all nine jobs on its own final commit.

The sole native development run retained **18,928 calls / 9,464 complete output pairs**, with its own native-only aggregate p95 gain **13.7581801448%**. Its 1 pooled and 5 per-round adverse metrics remain in the [development archive](../benchmarks/reports/round5-development/candidate-c6-full/README.md). It contains no actual-MCP or formal RSS acceptance evidence and supplies no missing formal gate.

Final-source C6 reproduces **2,304 / 2,304** saved default v0.3.2 Hotpot256 payload hashes: **1,536 native** calls across both encoders and three caps, plus **768 component** calls. All **4,608** original start/finish events were reconciled. The [compatibility summary](../benchmarks/reports/round5-c6-hotpot-regression.summary.json) retains exact source/input/helper identities and unchanged source/index/document projections. This reuses previously scored questions; it adds no new quality, competitor timing, Q2, generated-answer accuracy or unseen-domain claim.

The complete [C3 rejection](round5-performance-review.md) remains unchanged: aggregate p95 gain 10.4995860260%, best public native gain 10.4825741541%, public actual-MCP gain 5.1469620015%; original accepted:false. Its figures are not added to C6.

The complete [C5 rejection](round5-c5-performance-review.md) remains unchanged: aggregate p95 gain 15.2207914464%, best public native gain 15.4221732781%, public actual-MCP gain 6.6731813400%; original accepted:false. Its figures are not added to C6.

C4 has retained development evidence and was never a bound formal acceptance. C6's separate source, binding and single hosted result determine its own verdict. No successful subset, alternative source, repeated formal sample or earlier result replaces an adverse observation.

## Decision scope and reproducible evidence

The complete run fails its registered numerical acceptance; accepted:false is retained. All observed values above are from the saved C6 run. Repeated old queries on one host do not establish statistical significance, unseen-domain quality, universal speedup or whole-product superiority over another repository. Competitors were not remeasured.

[Full original report](../benchmarks/reports/round5-c6-performance-43557136276-1/report.json.gz) · [Original summary](../benchmarks/reports/round5-c6-performance-43557136276-1/report.summary.json) · [Independent arithmetic audit](../benchmarks/reports/round5-c6-performance-independent-audit.json) · [Strict saved-ledger audit](../benchmarks/reports/round5-c6-performance-local-audit.json)

| Artifact | SHA256 |
| --- | --- |
| benchmarks/reports/round5-c6-performance-43557136276-1/report.json.gz | `fce946bd7f421894f90d4ce1b553a85e7d4c03bfc7fd26f65a12540f2c5fe927` |
| benchmarks/reports/round5-c6-performance-43557136276-1/report.summary.json | `f05d011e3477eee69953ab3a5097e3d69f5657c12c6692d4d96af4f87cb6ad9e` |
| benchmarks/reports/round5-c6-performance-independent-audit.json | `9af11535d43d8aa12e6aa64225390890ba9e4233f4b664aff581228c604ac853` |
| benchmarks/reports/round5-c6-performance-local-audit.json | `3e2eb7453b0f64ebd211dcd61001e9f304763e4bfd033334e2acb0e4ad45f84e` |
| benchmarks/experiments/round5-c6-performance-binding.json | `2b57caea5b3d7f12b38aba9472d798e846a5231b936551784f0963259e2a715a` |
| benchmarks/reports/round5-c6-hotpot-regression.summary.json | `a6fcefb51f0c97e96a108f862ffe2e75f8f20d96a10dc8584a1679a73ac5c005` |
| benchmarks/reports/round5-development/candidate-c6-full/summary.json | `2426d40fe1bb89aa05300d40d8e24a2ef04869155b6aa5d3f3b1b8f100865667` |
| scripts/render_round5_c6_performance_review.py | `cdc6e999dc5c78c64513e7344bc07a9851f2c2171c97ce2e4a02999309a722cf` |

The release gate remains separate: final-commit CI, approved exact runtime, package and asset verification, public installer verification and any required explicit resource acceptance must all complete. This review never writes the runtime approval table or modifies raw reports.
