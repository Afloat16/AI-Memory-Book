# C6: complete saved development comparison

**The saved-data audit passes; this is development evidence, not formal release acceptance.** All 18,928 original native calls and 9,464 complete non-timing payload pairs are retained. All eight pooled p50/p95 comparisons improve. The eight-cell geometric-mean p95 reduction is **13.7581801448%**, and the best public native token p95 reduction is **16.5315976886%** at 1,024 tokens. Actual MCP latency and the formal resource gates are not measured by this development run.

There is one adverse pooled mean and five adverse per-round metrics. They are preserved below without discarded calls, replacement samples or a second performance invocation. The pooled public 512-token p95 reduction is 6.8319784962%, with only 0.0783767821% improvement in round 0; the complete results do not establish uniform gains across rounds or settings.

## Scope and provenance

- Baseline: published v0.3.2, commit `692fb959ddf8934c5f516ba3d74ceb4385a2fa82`, runtime SHA256 `179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93`.
- Candidate: repaired C6, commit `1bd97221e31e8e975498ece00f4bbfb3e0426aac`, runtime SHA256 `cfffd8a21374cbf9152bbbc98a6a9847a1e22401f16179112e2f79eef181ff78`.
- Preregistration: commit `099cbaf427c28351d71f3995fd0ff42f9c881b38`, [C6 addendum](../../../experiments/round5-c6-addendum.json), SHA256 `7ad88598c9ccb3492083be06448e92a76da7025501a1aa578a0e39d8bd94c9d5`.
- [Development plan](../../../experiments/round5-c6-development-plan.json), SHA256 `40d626fea37f9a410a7c77e9aa4bff7f4019f5441090d3f3ff14c07ea67dcb7a`; [measurement helper](../../../../scripts/round5_c6_development_pair.py), SHA256 `aad8590ad2dc465e5a34ea82d2e8fa250028612647e15d4aabdc0575a83215d2`.
- Original manifest SHA256 `7caf9e69fd6196d99e9bb6c49b854e3762fe248dbb423a72c07ab39b2c459071`; original fixed query-order reference SHA256 `5c042cbb299db837a9c9c5b1b3f3e2205042287915e77b696bc5376b3075d93c`.
- Recorded start: `2026-11-14T04:27:42.637883+00:00`; finish: `2026-11-14T04:28:53.533236+00:00`.
- All 168 fixed synthetic questions and 1,015 fixed public questions; character budget 4,000 and token budgets 512/1,024/2,048 with character cap 8,000 and `cl100k_base`. Two rounds per cohort, AB then BA, with the original deterministic per-configuration query order. A = baseline; B = candidate.

The candidate batches eligible original-turn reads inside the existing recall snapshot and reuses parsed source references locally. It retains the C5 exact token-count memo and the ordinary driver statement-cache limit. The superseded pre-timing C6 source `ae6208e302036f5dce420297d56aa3c95c525e8e` was corrected for nested-reference object freshness before this invocation; none of its performance calls are relabeled as final-source evidence.

## Complete-output and retention checks

Exactly eight worker files and both sources contribute 9,464 calls each. The audit verifies all 9,464 full-payload hash pairs, the exact expected question IDs and order in every cell, all character/token/revision/cache invariants, unchanged source/index/revision projections, and zero query-result-cache entries before and after each worker. It verifies that every saved worker equals its corresponding object in the aggregate manifest. There are **zero payload mismatches and zero invariant failures**.

All 32 first-query timings are retained in the raw rows, pooled statistics and per-round statistics; the candidate is not prewarmed and the first queries are not discarded. The original aggregate and eight worker JSON byte streams are compressed deterministically, with both compressed and uncompressed SHA256 values in [receipt.json](receipt.json).

## All eight pooled cells

Each cell pools its two rounds per version. Values below are milliseconds, rounded to six decimals; [summary.json](summary.json) and the original rows retain full precision. Change is `100 × (candidate / baseline − 1)`: negative values improve latency. Percentiles interpolate at `(N − 1) × q`. The geometric-mean p95 improvement is `100 × (1 − exp(mean(log(candidate_p95 / baseline_p95))))` across these eight native cells. This is not the formal 12-cell matrix.

| Cohort | Configuration | Calls per version | Mean, baseline → candidate ms (change) | p50, baseline → candidate ms (change) | p95, baseline → candidate ms (change) |
|---|---|---:|---|---|---|
| synthetic61 | native-char4000 | 336 | 4.153034 → 4.188159 (+0.845772%) | 3.228895 → 3.078858 (-4.646668%) | 9.575957 → 9.365724 (-2.195428%) |
| synthetic61 | native-token512 | 336 | 7.525754 → 5.693304 (-24.349051%) | 6.140460 → 4.475815 (-27.109443%) | 15.935662 → 12.237531 (-23.206641%) |
| synthetic61 | native-token1024 | 336 | 5.954931 → 4.383011 (-26.396946%) | 4.686267 → 3.295108 (-29.685864%) | 15.480699 → 11.123772 (-28.144254%) |
| synthetic61 | native-token2048 | 336 | 5.220803 → 4.831324 (-7.460135%) | 3.760208 → 3.468209 (-7.765501%) | 13.550488 → 11.692187 (-13.713903%) |
| public1015 | native-char4000 | 2030 | 2.145626 → 2.135879 (-0.454300%) | 2.097016 → 2.079179 (-0.850590%) | 2.766917 → 2.732532 (-1.242719%) |
| public1015 | native-token512 | 2030 | 3.338157 → 2.674173 (-19.890745%) | 3.243079 → 2.523948 (-22.174356%) | 4.004694 → 3.731094 (-6.831978%) |
| public1015 | native-token1024 | 2030 | 2.855550 → 2.422845 (-15.153107%) | 2.709376 → 2.341137 (-13.591282%) | 3.515043 → 2.933951 (-16.531598%) |
| public1015 | native-token2048 | 2030 | 2.782802 → 2.369521 (-14.851242%) | 2.674658 → 2.253728 (-15.737713%) | 3.445063 → 2.947794 (-14.434232%) |

## All sixteen per-round cells

| Cohort | Configuration | Round / order | Calls per version | Mean, baseline → candidate ms (change) | p50, baseline → candidate ms (change) | p95, baseline → candidate ms (change) |
|---|---|---|---:|---|---|---|
| synthetic61 | native-char4000 | 0 / AB | 168 | 4.079126 → 4.577754 (+12.223894%) | 3.221615 → 3.109976 (-3.465327%) | 10.225293 → 10.534411 (+3.023074%) |
| synthetic61 | native-char4000 | 1 / BA | 168 | 4.226941 → 3.798563 (-10.134461%) | 3.269825 → 3.040156 (-7.023922%) | 9.533862 → 8.792696 (-7.774040%) |
| synthetic61 | native-token512 | 0 / AB | 168 | 6.995849 → 5.303108 (-24.196366%) | 5.946709 → 4.378194 (-26.376194%) | 15.605271 → 11.834641 (-24.162545%) |
| synthetic61 | native-token512 | 1 / BA | 168 | 8.055659 → 6.083501 (-24.481648%) | 6.376535 → 4.554820 (-28.569050%) | 16.629226 → 12.480958 (-24.945649%) |
| synthetic61 | native-token1024 | 0 / AB | 168 | 5.829962 → 4.432706 (-23.966812%) | 4.675090 → 3.289986 (-29.627320%) | 15.113835 → 11.083848 (-26.664225%) |
| synthetic61 | native-token1024 | 1 / BA | 168 | 6.079900 → 4.333316 (-28.727179%) | 4.793408 → 3.360587 (-29.891496%) | 15.890290 → 11.123376 (-29.998915%) |
| synthetic61 | native-token2048 | 0 / AB | 168 | 5.308420 → 5.403368 (+1.788633%) | 3.965728 → 4.132889 (+4.215140%) | 13.775838 → 12.864355 (-6.616538%) |
| synthetic61 | native-token2048 | 1 / BA | 168 | 5.133186 → 4.259280 (-17.024633%) | 3.554810 → 3.143676 (-11.565556%) | 13.532763 → 11.079283 (-18.129924%) |
| public1015 | native-char4000 | 0 / AB | 1015 | 2.163338 → 2.132941 (-1.405127%) | 2.139279 → 2.095396 (-2.051299%) | 2.808370 → 2.793047 (-0.545633%) |
| public1015 | native-char4000 | 1 / BA | 1015 | 2.127914 → 2.138817 (+0.512357%) | 2.072529 → 2.066932 (-0.270057%) | 2.713788 → 2.666661 (-1.736598%) |
| public1015 | native-token512 | 0 / AB | 1015 | 3.328985 → 2.740776 (-17.669324%) | 3.241496 → 2.570117 (-20.712011%) | 4.025554 → 4.022399 (-0.078377%) |
| public1015 | native-token512 | 1 / BA | 1015 | 3.347329 → 2.607570 (-22.099991%) | 3.245654 → 2.468294 (-23.950797%) | 3.993406 → 3.449138 (-13.629172%) |
| public1015 | native-token1024 | 0 / AB | 1015 | 2.890178 → 2.340179 (-19.029937%) | 2.725510 → 2.331818 (-14.444709%) | 3.542360 → 2.931176 (-17.253585%) |
| public1015 | native-token1024 | 1 / BA | 1015 | 2.820922 → 2.505512 (-11.181097%) | 2.693143 → 2.361384 (-12.318655%) | 3.452808 → 2.955822 (-14.393663%) |
| public1015 | native-token2048 | 0 / AB | 1015 | 2.842440 → 2.327591 (-18.112902%) | 2.694133 → 2.202824 (-18.236256%) | 3.510528 → 2.729041 (-22.261240%) |
| public1015 | native-token2048 | 1 / BA | 1015 | 2.723164 → 2.411451 (-11.446720%) | 2.649264 → 2.324258 (-12.267785%) | 3.361878 → 3.157276 (-6.085969%) |

## Every adverse metric

| Scope | Cohort | Configuration | Round | Metric | Change |
|---|---|---|---:|---|---:|
| Pooled | synthetic61 | native-char4000 | — | mean_ms | +0.845771938% |
| Per round | synthetic61 | native-char4000 | 0 | mean_ms | +12.223894232% |
| Per round | synthetic61 | native-char4000 | 0 | p95_ms | +3.023073853% |
| Per round | synthetic61 | native-token2048 | 0 | mean_ms | +1.788633030% |
| Per round | synthetic61 | native-token2048 | 0 | p50_ms | +4.215140322% |
| Per round | public1015 | native-char4000 | 1 | mean_ms | +0.512356576% |

The largest adverse round metric is synthetic character-mode mean latency in round 0 (+12.223894232%); its p95 also regresses by 3.023073853%. The pooled character-mode mean is 0.845771938% slower. No pooled p50 or p95 regresses, but this does not remove the adverse mean or round-level observations.

## Native token memo observations

All four candidate workers begin with an empty, unallocated memo. Character-mode before/first-call/after snapshots remain unchanged and unallocated. The first token configuration starts empty; later native token configurations retain exactly the preceding configuration's ending snapshot. All recorded counters are nonnegative and cumulative, and all saved entry/text-size observations remain within the registered 2,048-entry / 2,097,152-byte caps. Baseline observations explicitly report that this memo is unavailable.

| Candidate worker | Final entries | Final retained text bytes | Cumulative hits | Cumulative misses | Evictions | Uncertified bypasses |
|---|---:|---:|---:|---:|---:|---:|
| synthetic61-0-candidate | 1117 | 1749265 | 2314 | 1117 | 0 | 3995 |
| synthetic61-1-candidate | 1117 | 1749265 | 2314 | 1117 | 0 | 3995 |
| public1015-0-candidate | 2048 | 1513152 | 13206 | 3319 | 1271 | 12132 |
| public1015-1-candidate | 2048 | 1518772 | 13189 | 3336 | 1288 | 12132 |

The largest retained-text value among the saved snapshots is 1,749,265 bytes; both public workers reach the entry cap and evict entries. All recorded invalidation and oversized-bypass counters are zero. The text-byte cap does not include memo key/container/encoder overhead or the rest of the process. These observations do not establish RSS or total-memory cost, and no private memo counters are inferred for MCP.

## Decision boundary

This result supports evaluating the frozen repaired C6 source in its separately bound formal run. The public 1,024-token pooled p95 reduction exceeds the numerical 15% reference by 1.5315976886 percentage points in this diagnostic, but public round 1 at that setting improves by only 14.3936632901%. The eight-cell aggregate and single public cell do not substitute for formal acceptance. The fixed formal matrix still requires 56,784 valid calls, all complete-output and provenance checks, the original 12-cell aggregate/public-native/actual-MCP numerical thresholds, regression limits, and resource review.

These are old regression questions on one host and two development rounds. This archive makes no fresh-domain, statistical-significance, competitor-superiority or release-readiness claim. It does not compare C6 timing against historical C5 timing from a different execution. Query-result caching is disabled, while the registered derived token-count memo naturally persists within each book. First-query observations are not cold-OS-cache measurements. The audit runs only on saved JSON and gzip bytes; it issues no product calls or timing runs.

## Reproduce the saved-data audit

Run from the repository root with a fresh output directory. This command reads the saved samples and never invokes recall:

```bash
python benchmarks/reports/round5-development/candidate-c6-full/audit_saved.py \
  --root . \
  --manifest benchmarks/reports/round5-development/candidate-c6-full/manifest.json.gz \
  --state-dir benchmarks/reports/round5-development/candidate-c6-full \
  --archive-dir .artifacts/c6-saved-data-audit-reproduction
```

The archived auditor differs from its initial C6 copy only by correction of three offline provenance constants: the published baseline commit, the true C6 registration SHA, and the frozen query-reference SHA. These corrections were made before reading the completed saved rows; measurement code, raw observations, statistics and acceptance rules were not changed.
