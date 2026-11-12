# v0.3.1 round-three optimization: measured outcome

This report covers the **v0.3.1 runtime candidate**, compared with published v0.3.0. It records a verified implementation and its measured tradeoffs; it is not an announcement of a tag or public release. The [registered plan](../benchmarks/experiments/round3-plan.json) remains unchanged.

The default lexical optimization preserves returned results while reducing the work SQLite performs on eligible project queries. The original 47,320-call experiment passed its correctness checks and all numeric performance gates: pooled p95 improved by **11.36% as a geometric mean across ten cells**, with **26.05%** improvement in the best public native cell. Its automatic acceptance remains false because empty-database startup increased by **14.04%** in one resource measurement. A separate, fixed startup-only diagnostic and [documented resource review](round3-startup-resource-review.md) explicitly accept that measured startup tradeoff without changing or replacing the original result.

The separate project-local BM25-statistics experiment **failed its registered quality gate** and is excluded from this candidate and the fresh comparison. The existing optional Q2 mode remains a choice with additional indexing/query costs and budget-dependent quality losses. The detailed fresh comparison is in [round3-comparison.md](round3-comparison.md).

## Exact implementations and evidence

| Item | Frozen identity |
|---|---|
| Published baseline | v0.3.0, `dd2f88be742ed330269e7dd5915b6f75089d7fef` |
| Measured candidate source | `2d199b93f650eccd3dd239178822b31001b880e3` |
| Baseline runtime SHA-256 | `d4558f6649762a09e10ad2906c06ab36b21786ef32be131906fc3213cf1a3c57` |
| Candidate runtime SHA-256 | `9c8118d26ae1a0eae4f31d9d4f44b2afa0ee5c54314bde5187deb27c473dee46` |
| Original performance run | [43246417515](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43246417515), evidence commit `35b8618a078fe377ecd6c5acc331c1281dbf61e7` |
| Resource-review decision | [round3-startup-resource-decision.json](../benchmarks/experiments/round3-startup-resource-decision.json), decision commit `e1a17c2f04a806e8a8d214c2d46c841749dfd266` |
| Recovered quality experiment | [decision.json](../benchmarks/reports/round3-project-stats-recovery-43266603949-1/decision.json), evidence commit `f0f6a5eeaa797c01fcba12e17882c9089f44df87` |

These runtime hashes identify the evaluated implementation even when later integration commits add reports, packaging or documentation. Later integration validation must keep the frozen source identity explicit.

## What changed in the default path

For a project-scoped FTS query, `_project_rowid_bounds(project)` reads the project's minimum and maximum page rowids, along with the archive's rowid range, through existing indexes in the current read transaction. The candidate applies the rowid envelope and an explicit FTS outer loop only when the project's inclusive rowid span is at most half the archive's inclusive span. Wider or interleaved projects retain the original query plan. There is no Python-side bounds cache.

The exact project/chapter/session predicate still applies **before the per-route LIMIT 96**. The optimization retains global BM25 statistics, indexed text, exact/stem normalization, deterministic ties, body-match requirements, later ranking and packing, provenance, cache identity and returned schema. It changes query execution, not which project's data is eligible. Session-specific handling continues through its original path.

This guard was fixed before formal timing. Development diagnostics found that unconditional bounds could slow an artificial 20,000-page interleaved fixture by about 18% at SQL p50, while bounds without the explicit FTS outer loop could choose a poor plan. Those variants were rejected. They are not hidden alternate formal candidates. See the hypothesis, negative diagnostics and preservation rules in the [registered plan](../benchmarks/experiments/round3-plan.json).

The optional ONNX path also disables runtime telemetry before initialization and through the runtime API. This is a telemetry setting, not a claim that installing tokenizers or preparing model files never uses a network.

## Formal performance: all ten cells

The original experiment ran 16 isolated workers sequentially on one runner, with four balanced baseline/candidate orders: AB, BA, BA, AB. It retained all four rounds and every query sample. The two regression cohorts contain 168 and 1,015 queries; each of five configurations has four samples per question per implementation. Total measured calls are **47,320**.

Native calls disable result caching. The MCP cells use the real official SDK stdio path and retain normal cache-write cost; persistent recall-cache clearing occurs outside timing. These are warm OS/SQLite-cache measurements, without an OS-cold-cache claim. All complete non-timing payload hashes, indexed-content digests and source/scope/cache/budget invariants passed. The [original summary](../benchmarks/reports/round3-performance-43246417515-1/report.summary.json) contains every round, mean, percentile and resource distribution; the [full report](../benchmarks/reports/round3-performance-43246417515-1/report.json.gz) and worker ledgers retain the samples.

Times are milliseconds; a negative change is faster. Samples are per implementation.

| Cohort | Surface / cap | Samples | p50 baseline → candidate | p95 baseline → candidate | p95 change |
|---|---|---:|---:|---:|---:|
| synthetic61 | native-char4000 | 672 | 4.459 → 4.314 | 13.501 → 12.843 | -4.87% |
| synthetic61 | mcp-char4000 | 672 | 6.718 → 6.609 | 16.012 → 15.424 | -3.68% |
| synthetic61 | native-token512 | 672 | 9.651 → 9.231 | 21.052 → 21.079 | +0.12% |
| synthetic61 | native-token1024 | 672 | 8.550 → 7.878 | 23.710 → 23.643 | -0.28% |
| synthetic61 | native-token2048 | 672 | 7.447 → 6.557 | 20.872 → 20.682 | -0.91% |
| public1015 | native-char4000 | 4060 | 3.456 → 3.036 | 5.054 → 3.737 | -26.05% |
| public1015 | mcp-char4000 | 4060 | 5.732 → 5.114 | 7.409 → 5.937 | -19.87% |
| public1015 | native-token512 | 4060 | 5.960 → 5.525 | 7.620 → 6.408 | -15.90% |
| public1015 | native-token1024 | 4060 | 5.081 → 4.672 | 6.706 → 5.504 | -17.92% |
| public1015 | native-token2048 | 4060 | 5.076 → 4.652 | 6.684 → 5.398 | -19.24% |

The geometric mean uses all ten pooled p95 ratios, not just the public cells. It exceeds the registered 5% improvement requirement; at least one public native cell exceeds the 10% requirement; no cell's pooled p50 or p95 worsens by more than 5%. The small synthetic 512-token p95 regression is retained. These findings support a bounded improvement on the measured workloads, not a guarantee that every archive layout or deployment gets the same speedup.

## Startup resource review: original flag retained

The original public-cohort `native_open_ms` mean was **34.4557195 → 39.29410325 ms**, an increase of **4.83838375 ms / 14.0423%**. This constructs a fresh empty database before ingestion and before the optimized recall path executes. The candidate's four original values were 56.659038, 33.518346, 33.283959 and 33.715070 ms; no value was removed.

The fixed follow-up measured startup only: 16 plain ABBA blocks (32 processes per implementation), then four separately instrumented ABBA blocks (8 processes per implementation), for **80 fresh processes and zero repeated retrieval calls**. Every sample, process CPU time, phase measurement, SQL trace and schema hash is retained in the [diagnostic report](../benchmarks/reports/round3-startup-review-43266672875-1/report.json).

All 64 non-recall store AST components, startup SQL sequences and resulting schemas matched. In the instrumented runs, schema `executescript` accounted for about 94.4% of startup wall time, with roughly 13.5–13.8 ms beyond process CPU. This locates the dominant wait-heavy initialization phase and is consistent with filesystem/scheduling variability. It does **not** establish the exact OS cause of the historical 56.659038 ms sample; no historical syscall trace exists.

Plain follow-up mean startup was 24.3869 → 24.5039 ms (+0.48%); process CPU was essentially unchanged. Plain p95 was 27.7444 → 29.3597 ms (**+5.82%**), also retained. Instrumented and plain samples remain separate, and neither is pooled with the original measurements.

The independent decision is `accepted-with-documented-resource-review`: accept the original measured startup cost explicitly for this frozen runtime. The decision retains `original_numeric_gate_passed=true`, `original_resource_review_retained=true` and **`original_report_accepted=false`**. The historical workflow remains a failure because its automatic acceptance required the review; there is no retroactive green result. The other original ingestion/reingestion/RSS measurements did not trigger the >10% review rule, and persistent logical database sizes were unchanged. See the [full rationale and distributions](round3-startup-resource-review.md).

## Rejected project-local statistics experiment

Global BM25 can change a project's ranking when other projects change the archive's global statistics. That observation motivated one explicit opt-in experiment; it did not establish that local statistics would improve real evidence retrieval.

The candidate built a connection-local TEMP exact/stem FTS pair from existing project text, using original rowids and transactional revision markers. The registered development screen evaluated four existing cohorts at three token budgets, baseline and candidate, with **8,082 calls across eight workers**. Acceptance required no aggregate evidence/complete-evidence loss in any cohort/budget cell, additional 512-token group non-regression checks, and at least one aggregate gain.

The full recovered evidence failed that gate: **14 loss checks and 10 aggregate improvement checks**, with `qualified=false` and status `rejected_loss_or_no_gain`. These are counts of metric/group checks, not counts of lost questions. For example:

- Synthetic 512-token complete evidence fell 85.53% → 82.24%, with five complete-evidence question losses and no gains.
- Public 1,015-query 512-token complete evidence fell 66.41% → 65.64%, with 13 question gains and 18 losses.
- Old Hotpot128 improved substantially, including 35.16% → 50.78% complete evidence at 512 tokens. Those gains do not cancel failures in the other registered cells.

The [recovered summary](../benchmarks/reports/round3-project-stats-recovery-43266603949-1/round3-project-stats-20261112-1.summary.json) and [detailed report](../benchmarks/reports/round3-project-stats-recovery-43266603949-1/round3-project-stats-20261112-1.md) preserve every cell, group and paired gain/loss, including construction/switch costs and TEMP storage. This mode is excluded from the runtime candidate and the fresh cohort; it was not retuned after failure.

The original aggregate gzip had been truncated. Recovery used all eight completed worker reports and all eight attempt ledgers, reconstructed the aggregate, passed the original evaluator audit, and verified the **9,401,417-byte surviving decoded prefix byte for byte**. The incomplete gzip prefix remains archived. Recovery made **zero new measurement calls**; it is evidence restoration, not another quality trial. See [recovery-manifest.json](../benchmarks/reports/round3-project-stats-recovery-43266603949-1/recovery-manifest.json).

## Fresh validation: another 256 HotpotQA questions

The candidate source, evaluator, dependency/model and upstream identities were frozen before selecting another 256 IDs. The selection excludes both prior Hotpot128 and round-two Hotpot256, giving **zero overlap with the 384 prior IDs**. It uses the plan's fixed salted ID hash rather than questions or outcomes. This is another selection from the same public source, not a new domain; after first scoring it is regression data.

Run [43267797247](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43267797247) completed successfully with all ten registered stages. The [assessment](../benchmarks/results/round3-comparison-43267797247-1/assessment.json) is `complete-verified`: **4,608 native recall calls**, **4,608 component searches**, and **1,280 additional ai-memory native page reads** are retained. Default lexical complete payload equality passed for **1,536 native pairs and 768 component pairs**. All 607 supporting annotations were attainable within the supplied pages; no annotation was dropped. The new measurements preserve the formal candidate's retrieval behavior on new IDs.

The common supplied-page reference view uses cl100k at 1,024 tokens. It is one of six registered cells, not a replacement primary metric or a whole-product benchmark:

| Component, common cl100k 1024 | Evidence recall | Complete evidence | Packed MRR | Adapter p95 ms |
|---|---|---|---|---|
| v0.3.0 lexical | 76.28% | 52.34% | 0.8132 | 5.828 |
| v0.3.1 lexical | 76.28% | 52.34% | 0.8132 | 2.784 |
| v0.3.1 Q2 | 76.77% | 54.69% | 0.8239 | 11.226 |
| claude-mem FTS | 70.68% | 45.31% | 0.7674 | 22.826 |
| ai-memory local hybrid | 77.27% | 55.86% | 0.8182 | 27.545 |
| billion-context kernel | 78.91% | 58.20% | 0.8277 | 1.010 |

The measured strengths and limitations are both concrete:

- Against the tested claude-mem supplied-source FTS component, default Book has higher evidence recall and complete-evidence rate in every budget/tokenizer cell. At 1,024/2,048 tokens, the differences are **+5.60 and +7.03 percentage points**. Its measured adapter p95 is also lower, 2.784 versus 22.826 ms.
- Against ai-memory's released local hybrid component, Book has lower measured query latency, while its quality is lower at 1,024/2,048: lexical complete evidence is 134/256 versus 143/256. Optional Q2 reaches 140/256, still below 143/256. At 512 tokens lexical matches one more annotation in each tokenizer but completes fewer questions.
- The billion-context search kernel has both lower measured latency and better quality at 1,024/2,048: 149/256 complete questions versus Book lexical's 134/256 and Q2's 140/256. At 512, Book lexical has a modest complete-evidence advantage: 98 versus 96 questions with cl100k, and 100 versus 97 with o200k.

These compare supplied-page retrieval under common scopes, top five and common packing. Book runs in-process Python with native hierarchy/context assembly; claude-mem uses SQLite/Bun, ai-memory actual HTTP/MCP plus full page reads, and billion-context a Node kernel. Their times do not support a whole-product speed multiplier. The detailed [comparison report](round3-comparison.md) includes all 54 quality cells, means and p50/p95, first/repeated passes, native payload versus context tokens, setup/indexing, RSS, live state and preparation costs.

### Optional Q2: preserve all budget losses

Q2 is an existing opt-in local semantic mode; this optimization does not change its model or fusion rules. On the fresh native API, its complete-evidence outcome is:

| Tokenizer | Token cap | Default complete evidence | Q2 complete evidence | Recall change pp | Complete questions gained / lost |
|---|---:|---:|---:|---:|---:|
| cl100k_base | 512 | 35.94% (92/256) | 33.59% (86/256) | -0.99 | 22 / 28 |
| cl100k_base | 1024 | 52.34% (134/256) | 54.69% (140/256) | +0.49 | 24 / 18 |
| cl100k_base | 2048 | 52.34% (134/256) | 54.69% (140/256) | +0.49 | 24 / 18 |
| o200k_base | 512 | 35.55% (91/256) | 33.20% (85/256) | -1.15 | 22 / 28 |
| o200k_base | 1024 | 52.34% (134/256) | 54.69% (140/256) | +0.49 | 24 / 18 |
| o200k_base | 2048 | 52.34% (134/256) | 54.69% (140/256) | +0.49 | 24 / 18 |

At 512 tokens the native complete-evidence rate falls by 2.34 points for both tokenizers, with 22 gained and 28 lost questions. At 1,024/2,048 it rises by 2.34 points, with 24 gained and 18 lost questions; annotation recall rises by only three of 607 annotations. The common packer also loses complete questions at 512: cl100k 98 → 97, o200k 100 → 97. Every paired change remains in the assessment.

Q2 also costs more. Fresh native semantic indexing takes **110.09 seconds**, and total setup is **115.13 seconds**, versus **4.24 seconds** for lexical on this run. It creates 4,831 windows and 7,420,416 raw vector bytes and requires the separately prepared 127,535,388-byte model/tokenizer files. At common component boundaries its adapter p95 is 11.226 ms versus lexical's 2.784 ms. These costs, the native 512-token losses and its remaining quality deficit against ai-memory/billion-context preclude calling Q2 a universal improvement.

Default lexical remains the predictable behavior-preserving choice. For this corpus, increasing the cap from 1,024 to 2,048 does not improve top-five evidence quality. A caller considering Q2 should weigh its larger-budget evidence gain against indexing/query costs and the tight-budget losses; the six-question low-overlap subgroup is too small to establish broad semantic superiority.

## What this round establishes

The evidence supports a default retrieval execution improvement with preserved outputs, an explicitly accepted startup-resource tradeoff, and specific fresh-cohort advantages over the tested claude-mem component. It also establishes that the sole project-statistics experiment failed and remains excluded, that optional Q2 has losses, and that the candidate does not beat every comparison on every metric.

The new cohort consists entirely of answerable encyclopedia multi-hop questions. Its artificial paragraph-to-session/chapter mapping is not a measurement of private conversational transfer. Evidence recall is not generated-answer accuracy, and no abstention/hallucination improvement follows. All compared stages configure zero generative model calls; local embedding costs still apply to Q2 and ai-memory, so zero-LLM operation is not unique to Book.

The runtime candidate is verified by the cited performance, integrity and fresh-cohort evidence. Packaging, integration CI, PR merge and public release remain distinct lifecycle events; this document does not assert that a v0.3.1 tag or public release already exists. Historical reports, rejected experiments and the original automatic resource flag remain unchanged.
