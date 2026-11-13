# Round-four formal performance review: v0.3.2 candidate C2

## Decision and scope

**The frozen C2 candidate passes the registered formal performance gate, with no resource exception or waiver.** Independent recalculation from all **56,784 saved calls**, **16 workers**, **12 pooled cells** and **28 resource comparisons** agrees with the original accepted result. The geometric-mean pooled p95 improvement is **10.1294257732%**. Its margin above the 10% threshold is only **0.1294257732 percentage points**: this is a narrow observed pass, not evidence of statistical significance or a universal speedup. [Independent arithmetic audit][audit] · [Completed report][summary]

The public actual SDK MCP token-1024 p95 improves **10.8021336431%**, a margin of **0.8021336431 percentage points** above its separate 10% threshold. Public native token-512, token-1024 and token-2048 p95 improve **19.0736%, 18.4102% and 18.2009%**. These are complete default lexical recall measurements against v0.3.1. They establish no whole-product result against another repository. Fresh comparison/validation and release checks remain separate. [Registered plan][plan] · [Audit decision][audit]

## Evidence identity and verification

| Item | Frozen identity |
|---|---|
| Hosted run / attempt | `43361086255` / `1` |
| Result commit | `1bd76f3b70eb60ead444f05c5a94148e9e384bba` |
| Workflow commit | `f8f1653c0653654ed574569fff1aaf4dbaeef6d1` |
| Baseline | v0.3.1, `7b7a5d7336b9350a128f5e0a888811b1b3015e68` |
| Candidate C2 | `2d7b5e38839fb21724ad3beec6b6ebabbda45636` |
| Evaluator commit | `6532d8388187c6af4cd3ab3ef71f6ef285ed8fad` |
| Baseline runtime SHA256 | `9c8118d26ae1a0eae4f31d9d4f44b2afa0ee5c54314bde5187deb27c473dee46` |
| Candidate runtime SHA256 | `179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93` |
| Original binding SHA256 | `d535df483cc41cc0b2381104fd99b17f4639fa2160e3b73a6661ceb8c4e58915` |

Before decompressing or analyzing the full report, this review checked its compressed SHA256 and the summary SHA256 against `completion.json`. The completion bytes were matched to their Git blob in the named result commit. The decompressed report then matched the summary's full-report SHA256. [Completion record][completion] · [Independent audit][audit]

```text
compressed report: 3ff580ea923e6a41188387f62c01eff1d86bdd68c2d1e25b215283d39254d8e2
full report:       dbd47f4f5d750bb6e7bb61d8c3d579c66507d64ab33f0a5f743143bffe8d8bfa
summary:           c7b5a8e9283e7c5d73b9c39cae6d4f2a308098e523d2df70f9f472438a15c4e8
```

The review independently recomputed percentiles, means, all gate arithmetic, first/repeat partitions, output-cost summaries and resource means from the saved rows and worker samples; it did not invoke the evaluator's comparisons or acceptance functions. It also checked the complete schedule, deterministic query orders, unchanged source/index identities, recorded cache/budget invariants, and full stable-row equality across sources and rounds. There are **28,392 paired baseline/candidate observations** over **7,098 distinct cohort/configuration/query keys**. The same old queries are repeated across rounds; 56,784 calls do not mean 56,784 independent queries. [Audit method and row checks][audit]

The hosted completion reports that its strict full-ledger audit succeeded. After all 72 public files were materialized locally, the unchanged frozen auditor also passed against the original workers, raw and compressed ledgers, execution identities, full report and summary, with zero retrieval calls. Its receipt's SHA256 is `f73b85b82f30cbf1aa8d063fd0c14965d300fcab44e07b6c2227527868ed3ca1`; this review verified that receipt's report hashes and auditor identity against the frozen binding. The independent arithmetic and the strict ledger verification are separate checks. Neither repeats measurement. [Completion record][completion] · [Local strict-audit receipt][local-audit] · [Frozen auditor][evaluator]

## Timing boundary and registered calculation

Each cohort uses the registered source order **AB, BA, BA, AB**, with a fresh process/database worker for each source and round. The cohorts contain 168 synthetic queries and 1,015 old public-conversation queries. Every source/configuration therefore contributes **672 synthetic** or **4,060 public** samples to its pooled percentile. Query order is equal for paired engines. Token configurations use `cl100k_base`, an 8,000-character ceiling and limit 5; character configurations use 4,000 characters. [Plan][plan] · [Full saved report][full]

Native timing covers the complete uncached `MemoryBook.recall` call. Actual MCP timing covers the official SDK stdio call through the returned `CallToolResult`, including normal server cache writes and roundtrip costs. Persistent cache deletion/commit occurs before the timer. Reference token counting, response auditing and Git checkpoint publication occur outside query timing. Native reference encodings are prepared before the calls; ordinary initialization in a fresh MCP server is not replaced by a native-only estimate. No OS-cold-cache measurement is claimed. [Frozen evaluator][evaluator] · [Report interpretation][summary]

The aggregate is `100 × (1 − exp(mean(log(candidate_p95 / baseline_p95))))`, with equal weight for the **twelve pooled cell ratios**. It is neither a percentile over mixed configurations nor an average of the four round percentages. p50 and p95 use the registered linearly interpolated order statistics. [Plan][plan] · [Independent arithmetic][audit]

| Registered requirement | Recomputed result | Assessment |
|---|---:|---|
| Complete payload equality and all invariants | All saved stable rows agree; zero recorded invariant errors | Pass |
| Geometric-mean pooled p95 improvement ≥10% | 10.1294257732% | Pass; margin 0.1294257732 pp |
| At least one public native token p95 improvement ≥15% | 19.0735801151% at token-512 | Pass; all three token cells exceed 15% |
| Public actual MCP token-1024 p95 improvement ≥10% | 10.8021336431% | Pass; margin 0.8021336431 pp |
| No pooled p50/p95 regression >5% | Largest regression is +1.4444829508% | Pass |
| Review any registered resource mean increase >10% | Largest increase is +6.0230600656% | No trigger; no waiver |

## All twelve pooled cells

A negative change means lower latency. Absolute p95 values below are milliseconds; complete p50/mean values and distributions remain in the independent JSON audit. All twelve pooled p50 and mean values improve. The sole pooled latency increase is **public MCP character-budget p95**, from **3.467968 ms to 3.518062 ms**, or **+1.4445%**. The synthetic native character improvement is only **0.0391%** and should not be presented as a substantial gain. [Recomputed cells][audit]

| Cohort | Configuration | v0.3.1 p95, ms | C2 p95, ms | p95 change | p50 change |
|---|---|---:|---:|---:|---:|
| synthetic61 | Native, 4,000 characters | 7.829769 | 7.826710 | -0.0391% | -1.0180% |
| synthetic61 | SDK MCP, 4,000 characters | 9.385577 | 9.313084 | -0.7724% | -0.1786% |
| synthetic61 | Native, 512 tokens | 12.340915 | 11.620417 | -5.8383% | -13.2798% |
| synthetic61 | Native, 1,024 tokens | 13.784621 | 11.928046 | -13.4684% | -21.7872% |
| synthetic61 | Native, 2,048 tokens | 12.253276 | 10.258256 | -16.2815% | -27.6478% |
| synthetic61 | SDK MCP, 1,024 tokens | 15.000020 | 13.524275 | -9.8383% | -15.9856% |
| public1015 | Native, 4,000 characters | 2.361452 | 2.198754 | -6.8897% | -3.0591% |
| public1015 | SDK MCP, 4,000 characters | 3.467968 | 3.518062 | +1.4445% | -0.0365% |
| public1015 | Native, 512 tokens | 3.793969 | 3.070323 | -19.0736% | -21.4475% |
| public1015 | Native, 1,024 tokens | 3.199822 | 2.610729 | -18.4102% | -19.5676% |
| public1015 | Native, 2,048 tokens | 3.129763 | 2.560117 | -18.2009% | -20.7479% |
| public1015 | SDK MCP, 1,024 tokens | 4.357927 | 3.887177 | -10.8021% | -12.7665% |

## Every round, including adverse observations

The following table retains all **48 paired round/configuration cells**. It shows p95 changes rather than selecting favorable rounds. The descriptive aggregate gains calculated separately within rounds 0–3 are **7.9998%, 9.6256%, 10.6865% and 11.1748%**. Those are not additional acceptance gates: the preregistered decision uses all four rounds pooled. Their variation is another reason not to turn the narrow pooled margin into a statistical or universal claim. [All per-round cells][audit]

| Cohort | Configuration | Round 0 | Round 1 | Round 2 | Round 3 |
|---|---|---:|---:|---:|---:|
| synthetic61 | Native, 4,000 characters | -1.6728% | +2.2887% | -0.8260% | +1.7205% |
| synthetic61 | SDK MCP, 4,000 characters | +4.6261% | +3.5806% | +0.9584% | -6.2601% |
| synthetic61 | Native, 512 tokens | -3.9639% | -6.1502% | -4.7002% | -6.1619% |
| synthetic61 | Native, 1,024 tokens | -10.8807% | -11.4203% | -14.9957% | -12.1009% |
| synthetic61 | Native, 2,048 tokens | -17.1592% | -15.0040% | -15.2783% | -14.3263% |
| synthetic61 | SDK MCP, 1,024 tokens | -8.5464% | -9.5122% | -11.8538% | -10.6089% |
| public1015 | Native, 4,000 characters | -7.2419% | -1.9979% | -3.2875% | -9.0620% |
| public1015 | SDK MCP, 4,000 characters | +4.1390% | -4.1801% | +1.7556% | +3.7487% |
| public1015 | Native, 512 tokens | -14.0217% | -21.7140% | -20.2322% | -22.7773% |
| public1015 | Native, 1,024 tokens | -17.0402% | -17.1104% | -20.3708% | -20.2535% |
| public1015 | Native, 2,048 tokens | -13.4831% | -18.7204% | -21.6660% | -20.9655% |
| public1015 | SDK MCP, 1,024 tokens | -7.5347% | -11.5238% | -13.1357% | -12.7848% |

All **19 positive per-round metric changes** are retained below: six p50, eight p95 and five mean increases. A dash means that metric did not increase in that cell; its signed value remains in the JSON. For example, synthetic MCP character round 1 has p50 **+5.8158%** and mean **+5.3981%**. The 5% gate applies to pooled p50/p95, not to isolated rounds, so this observation is preserved without changing the registered decision. [Adverse observations][audit]

| Cohort | Configuration | Round | p50 increase | p95 increase | Mean increase |
|---|---|---:|---:|---:|---:|
| synthetic61 | Native, 4,000 characters | 1 | +4.5227% | +2.2887% | +4.7376% |
| synthetic61 | Native, 4,000 characters | 3 | — | +1.7205% | — |
| synthetic61 | SDK MCP, 4,000 characters | 0 | +3.4809% | +4.6261% | +2.2514% |
| synthetic61 | SDK MCP, 4,000 characters | 1 | +5.8158% | +3.5806% | +5.3981% |
| synthetic61 | SDK MCP, 4,000 characters | 2 | +0.8993% | +0.9584% | — |
| public1015 | SDK MCP, 4,000 characters | 0 | +0.4206% | +4.1390% | +0.4045% |
| public1015 | SDK MCP, 4,000 characters | 2 | — | +1.7556% | — |
| public1015 | SDK MCP, 4,000 characters | 3 | +2.2408% | +3.7487% | +1.6290% |

## All registered resource costs

Each table entry is the arithmetic mean of **four raw worker samples** for that cohort/source. All 28 comparisons were independently recalculated. No registered mean exceeds the 10% review threshold, so this result requires no exception or cause-based waiver. Small increases remain visible. [Raw samples and recomputed means][audit]

### Import, initialization, ingestion and replay

Durations are milliseconds. MCP startup is process/session start through completed initialization, measured separately for character and token sessions.

| Metric | Synthetic baseline | Synthetic C2 | Change | Public baseline | Public C2 | Change |
|---|---:|---:|---:|---:|---:|---:|
| Runtime import | 16.3903 | 16.3823 | -0.0493% | 16.4970 | 16.3098 | -1.1347% |
| Open empty native database | 24.9717 | 20.2172 | -19.0396% | 19.8053 | 19.9799 | +0.8814% |
| Fresh ingestion | 629.4762 | 628.9816 | -0.0786% | 724.8364 | 685.6489 | -5.4064% |
| Unchanged reingestion | 52.6876 | 53.0661 | +0.7185% | 106.7521 | 105.1955 | -1.4581% |
| MCP character session: start to initialize | 365.9965 | 366.3779 | +0.1042% | 378.0048 | 377.9670 | -0.0100% |
| MCP token session: start to initialize | 366.0218 | 367.7673 | +0.4769% | 345.6833 | 366.5041 | +6.0231% |

The largest mean increase is public MCP token-session startup: **345.683341 → 366.504056 ms**, or **+6.0231%**. Its four baseline samples are 352.881788, 345.849642, 343.331191 and 340.670742 ms; the corresponding C2 samples are 376.015318, 378.556598, 348.393659 and 363.050649 ms. No sample was removed, and no traced causal explanation is asserted. [Resource samples][audit]

Individual resource comparisons can exceed 10% even when their four-round mean does not. Synthetic round-1 fresh ingestion is **591.497103 → 670.935038 ms (+13.4300%)**. Its full four-round mean is **629.476234 → 628.981628 ms (−0.0786%)**, which is the registered resource criterion. The apparent **19.04%** reduction in synthetic empty-database opening is also sensitive to the baseline round-0 value of **41.211566 ms**, compared with its other values near 19–20 ms. These four-sample resource observations do not establish a population tail or a general startup optimization. [All raw resource samples][audit]

### Resident and high-water memory

Values are MiB (1,048,576 bytes). RSS is resident memory at the recorded point; HWM is the process high-water reading. Native evaluator memory includes reference tokenizers and retained audit rows. It is not an isolated measurement of incremental library memory. Actual MCP child processes are recorded separately.

| Metric | Synthetic baseline | Synthetic C2 | Change | Public baseline | Public C2 | Change |
|---|---:|---:|---:|---:|---:|---:|
| Native evaluator after ingestion: RSS | 40.4854 | 40.5244 | +0.0965% | 43.6328 | 43.6113 | -0.0492% |
| Native evaluator after ingestion: HWM | 40.5830 | 40.5869 | +0.0096% | 51.4365 | 51.3135 | -0.2392% |
| Native evaluator after calls: RSS | 190.9570 | 191.1670 | +0.1100% | 214.9785 | 214.8418 | -0.0636% |
| Native evaluator after calls: HWM | 190.9570 | 191.1670 | +0.1100% | 214.9785 | 214.8418 | -0.0636% |
| MCP character server after calls: RSS | 61.4941 | 61.4531 | -0.0667% | 60.5156 | 60.4971 | -0.0307% |
| MCP character server after calls: HWM | 61.4941 | 61.4531 | -0.0667% | 60.5156 | 60.4971 | -0.0307% |
| MCP token server after calls: RSS | 104.3262 | 104.7490 | +0.4053% | 103.5342 | 103.8457 | +0.3009% |
| MCP token server after calls: HWM | 104.3262 | 104.7490 | +0.4053% | 103.5342 | 103.8457 | +0.3009% |

### Database, WAL and shared-memory files

Every recorded size below is identical between sources and across their four worker samples at the named phase. Logical size is distinct from the current main-file size while WAL pages are live. All values are bytes. Character and token MCP sessions each retain their own live-storage record. [Storage records][audit]

| Cohort / phase | Logical database | Main file | WAL | SHM |
|---|---:|---:|---:|---:|
| Synthetic, after ingestion | 20,508,672 | 20,508,672 | 5,772,152 | 32,768 |
| Synthetic, after either MCP session | 20,508,672 | 20,508,672 | 5,772,152 | 32,768 |
| Synthetic, after checkpoint | 20,508,672 | 20,508,672 | 0 | 32,768 |
| Public, after ingestion | 12,881,920 | 12,447,744 | 4,894,592 | 32,768 |
| Public, after either MCP session | 12,881,920 | 12,881,920 | 4,894,592 | 32,768 |
| Public, after checkpoint | 12,881,920 | 12,881,920 | 0 | 32,768 |

### Output and reference-token costs

The complete stable-row checks preserve native payload hashes, MCP response text and SDK envelope hashes, UTF-8 byte counts, context sizes, and both reference encoders' token counts. Their source-to-source cost summaries agree exactly. This optimization therefore makes no output-token saving claim. The envelope measurement is the returned SDK `CallToolResult` JSON; it is not a claim to have counted every stdio protocol byte. [Per-cell cost summaries][audit] · [Measurement implementation][evaluator]

| Reference encoder | Tool-schema tokens | Instruction tokens |
|---|---:|---:|
| `cl100k_base` | 912 | 168 |
| `o200k_base` | 954 | 167 |

The evaluator's own preparation of reference tokenizers, outside query timing, averages **254.875647 → 256.404002 ms** for synthetic workers and **256.473688 → 257.836689 ms** for public workers. These are evaluator preparation costs, not product startup measurements and not additional registered resource gates. [Recorded preparation costs][audit]

## Interpretation and remaining limits

This review supports the frozen formal decision for **this source pair, these old regression queries and this hosted run**. The host record reports four CPUs, Python 3.12.16, SQLite 3.45.1, MCP 1.30.0, Pydantic 2.14.3 and tiktoken 0.12.0. Four process rounds on one machine provide useful balanced repeated measurements, but they do not provide independent new workloads, a confidence interval, or proof that the small aggregate margin will persist elsewhere. [Host and binding][audit]

The arithmetic audit checks the recorded hashes, costs, invariant flags and budgets. It does not reconstruct omitted response bodies, re-tokenize them, infer answers, or rescore quality. Full original rows, first/repeat partitions, resource samples, controller records and worker ledgers remain in the canonical result directory. No completed run is replaced or repeated to select better timing. [Full report][full] · [Completion][completion]

C1's development gains and adverse character result, the interrupted first-use attempt, the zero-query local MCP/RSS failure, and the registered C2 recovery remain separate evidence. The successful hosted measurements do not rewrite those records. The separate prelaunch audit documents completion of the final-source development prerequisites; passing this formal performance gate does not by itself complete fresh validation, external component comparison, installer verification or release approval. [Prelaunch audit][prelaunch] · [Recovery registration][recovery] · [Original plan][plan]

[plan]: ../benchmarks/experiments/round4-plan.json
[evaluator]: ../scripts/round4_performance.py
[audit]: ../benchmarks/reports/round4-performance-independent-audit.json
[full]: ../benchmarks/reports/round4-performance-43361086255-1/report.json.gz
[summary]: ../benchmarks/reports/round4-performance-43361086255-1/report.summary.json
[completion]: ../benchmarks/reports/round4-performance-43361086255-1/completion.json
[local-audit]: ../benchmarks/reports/round4-performance-local-audit.json
[prelaunch]: ../benchmarks/reports/round4-development/final-prelaunch-audit.json
[recovery]: ../benchmarks/experiments/round4-prelaunch-recovery.json
