# Round-six startup resource review

**Recommendation: accept the one disclosed whole-process CPU tradeoff for the startup-scoped candidate.** This independent resource assessment does not change the original automatic verdict and does not approve the entire release. A separate explicit decision must accept the tradeoff; fresh comparison, final CI, packaging and public-installer requirements remain separate.

The sole [startup confirmation run 43598913606](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43598913606) completed all 480 original samples and 960 ledger events. Measurement and saved-result audit return codes are both zero. All three primary startup targets and all six secondary guards pass. The original report remains `numeric_gate_passed:true`, `accepted:false` because the registered resource rule requires review of one mean increase above 10%. The workflow's original failure outcome remains recorded.

## Immutable evidence

- Original result commit: `ffcc0a6f01b3b4acdf755ecd4c01b1e564d279b6`.
- [Complete raw report](../benchmarks/reports/round6-startup-43598913606-1/report.json.gz) SHA256: `381f5d99e5844af1d6d1681723f489ac98f099bb86551abcc6dd9cfd162a5b5a`.
- [Original hosted audit](../benchmarks/reports/round6-startup-43598913606-1/independent-audit.json) and [local saved-result audit](../benchmarks/reports/round6-startup-43598913606-1-local-audit/independent-audit.json).
- [Original prospective startup plan](../benchmarks/experiments/round6-startup-plan.json), [binding](../benchmarks/experiments/round6-startup-binding.json), and [machine-readable independent resource review](../benchmarks/reports/round6-startup-resource-review.json).
- Published v0.3.3 baseline: source `796cedfd1f5368144037a1fb72292b8d13884b8c`, runtime SHA256 `55529a217e6dcf6af0c81639cfc0e88b3ea94c39e6911f659fcfb7543e853d45`.
- Selected A: source `df35007c29e4af61dd96146232fe4651cfc74391`, runtime SHA256 `f361d2bf64a4e1088cbd5cff6ffdaf19aa15e7f1b7ea1de4577d7a488d2ac242`. B's rejected dense-rank route is excluded.

## The retained resource flag

The flagged field is `api-existing / process.system_cpu_s`: kernel CPU time for the whole fresh helper child, collected through `wait4` for that PID. It includes the child's interpreter/bootstrap/import work, its constructor and outside-timer validation/close work. It is not a constructor-only CPU measurement.

Across 40 observations per source, mean system CPU rises from **18.646175 to 21.120575 ms**, an increase of **2.474400 ms / 13.270282%**. The original metric is recorded in seconds; the table below changes units only.

| Round and source order | Baseline mean system CPU, ms | A mean system CPU, ms | Absolute increase, ms | Relative increase |
|---|---:|---:|---:|---:|
| 0 (AB) | 18.386800 | 20.899600 | +2.512800 | +13.6663% |
| 1 (BA) | 17.201200 | 19.589000 | +2.387800 | +13.8816% |
| 2 (BA) | 18.310600 | 20.989700 | +2.679100 | +14.6314% |
| 3 (AB) | 20.686100 | 23.004000 | +2.317900 | +11.2051% |

Each row contains ten samples per source. All four rounds increase, including both AB and BA orders. This consistent observation must not be dismissed as one outlier, rounded away, or relabeled as proven measurement noise.

## Absolute cost and causal limits

The same saved samples put the cost in context:

| Existing-archive boundary | Baseline, ms | A, ms | Change, ms |
|---|---:|---:|---:|
| Whole-child system CPU mean | 18.646175 | 21.120575 | +2.474400 |
| Whole-child user CPU mean | 119.742400 | 118.496375 | −1.246025 |
| Derived user + system CPU mean | 138.388575 | 139.616950 | +1.228375 |
| Whole-helper wall mean | 138.762209 | 139.995957 | +1.233748 |
| Constructor median | 0.640361 | 0.632477 | −0.007884 |
| Constructor p95 | 0.667592 | 0.665576 | −0.002017 |

The total-CPU row is arithmetic on the original per-sample user/system CPU values, not a new timing or a replacement resource gate. Whole-helper wall time rises 0.889110%; the constructor's own median and p95 slightly decrease.

Static inspection of the two frozen sources shows that a valid schema-3 existing archive does not execute the newly transaction-wrapped initialization DDL. The changed fresh-initialization branch therefore cannot be asserted as the cause of this existing-archive system-CPU increase. The complete helper lifetime also covers imports, process/bootstrap and validation work that the constructor timer excludes. No syscall-level or component CPU trace was captured, so the exact cause is unresolved. The review accepts the observed bounded cost, not a fabricated causal explanation.

## Startup scope and every adverse result

All six original pooled latency boundaries are retained below. Changes are candidate relative to baseline; positive percentages mean slower. Each source contributes forty original samples per boundary across four balanced rounds.

| Boundary | Median baseline → A, ms | p95 baseline → A, ms | Median / p95 change |
|---|---:|---:|---:|
| cli-help | 102.902619 → 48.749533 | 104.103962 → 49.546675 | -52.6256% / -52.4065% |
| cli-version | 101.345546 → 47.478763 | 103.116280 → 48.259182 | -53.1516% / -53.1993% |
| api-import | 33.506216 → 33.920427 | 33.821928 → 34.432927 | +1.2362% / +1.8065% |
| api-new | 24.517632 → 4.163528 | 27.373841 → 6.358100 | -83.0182% / -76.7731% |
| api-existing | 0.640361 → 0.632477 | 0.667592 → 0.665576 | -1.2312% / -0.3021% |
| mcp-initialize | 627.601162 → 620.104423 | 632.233029 → 624.837497 | -1.1945% / -1.1697% |

New archive construction saves 20.354104 ms at the median; CLI help/version save 54.153086 / 53.866784 ms. These are the primary confirmed improvements. Full API import becomes slower by 0.414211 ms at the median and 0.610998 ms at p95; both remain inside the prospective secondary guard and must be disclosed. Existing-archive opening and MCP initialization remain secondary observations, not new broad speed claims.

The complete raw report and machine-readable review preserve **all 30 resource comparisons**, **9 pooled resource increases**, **27 per-round resource increases**, **6 pooled adverse timing entries**, and **26 adverse per-round timing entries**. The single >10% pooled resource flag remains unchanged. Empty database size is 159,744 bytes for both sources in these fixtures.

`process.max_rss_bytes` is the actual child's `wait4` high-water observation. CLI values are equal between sources within each round and rise across rounds; this evidence does not isolate post-exec product memory. Do not advertise equal or reduced product memory from those values. The MCP server RSS/HWM values are samples after initialization, not a measured whole-lifetime peak; helper rusage can also include descendants reaped by that helper. No memory-efficiency superiority is claimed.

## Decision boundary

Accepting an observed approximately 2.47 ms whole-child system-CPU increase, with approximately 1.23 ms higher total CPU and wall means in the existing-empty-archive helper, is a bounded tradeoff for the measured new-archive and CLI startup gains. It is not a promise that every workload becomes faster or cheaper. The result covers one Linux/Python 3.12 environment with natural OS cache evolution; the balanced descriptive gates are not statistical-significance or cold-OS claims.

The original recall 10% / 15% / 10% targets remain unchanged and unpassed. No four-round recall formal matrix was run for A or B. The startup study does not establish new retrieval-quality superiority, competitor wins, generated-answer quality, or universal performance superiority. Fresh external-component comparison and corrected exact final CI are still required before release. The resource recommendation must be recorded in a separate explicit decision while every original automatic result, flag, sample and failed workflow remains intact.
