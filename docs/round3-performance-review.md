# v0.3.1 performance resource review

This review covers the original frozen run
[`43246417515`, attempt 1](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43246417515).
It does not repeat, filter, or replace its timing samples. The original
[summary](../benchmarks/reports/round3-performance-43246417515-1/report.summary.json),
[full report](../benchmarks/reports/round3-performance-43246417515-1/report.json.gz),
worker files, ledgers, and automatic `accepted: false` decision remain intact.
The separate [machine-readable review](../benchmarks/reports/round3-recovery/performance-resource-review.json)
records source identities and an independent recomputation of the full
report's validation, all comparisons, automatic acceptance, summary, and
hashes. The subsequent frozen strict audit also verified the original run
identity, every worker artifact hash, all complete attempt ledgers, and
equality between the original workers and the aggregate. It exited
successfully with `verified: true`, 47,320 validated calls, 16 validated
workers, and **zero retrieval calls executed**. The audit correctly retained
the original `accepted: false`; it did not replace the resource review.

## Retrieval result

The registered run completed all **47,320 timed calls**, all **16 workers**,
and all four balanced rounds. Its complete-payload and source/scope/budget
validation passed. The numerical performance gate passed:

- Geometric-mean pooled p95 improvement across all ten cells: **11.3587%**.
- Largest public native pooled p95 improvement: **26.0501%**.
- Pooled cells with a p50 or p95 regression above 5%: **zero**.
- The synthetic 512-token cell has a **0.1248% p95 regression**; it remains in
  the aggregate. These results do not claim that every cell or round improved.

| Public-conversation configuration | Baseline p95, ms | Candidate p95, ms | Change |
|---|---:|---:|---:|
| Native, 4,000 characters | 5.053851 | 3.737317 | −26.0501% |
| Actual MCP stdio, 4,000 characters | 7.408803 | 5.936841 | −19.8677% |
| Native, 512 tokens | 7.619916 | 6.408086 | −15.9035% |
| Native, 1,024 tokens | 6.705825 | 5.504397 | −17.9162% |
| Native, 2,048 tokens | 6.683904 | 5.397920 | −19.2400% |

The token settings use `cl100k_base` and the registered 8,000-character ceiling.
These are same-host lexical retrieval measurements on old regression data.
They do not measure generated answers, first-use downloads, OS-cold caches,
or whole-product performance against another repository.

## Why the automatic result requires review

The plan requires independent review when a startup, ingestion, replay, or
memory mean rises more than 10%. Exactly one resource comparison triggered:
opening a new empty database in the public-conversation workers.

| Registered round | Baseline open, ms | Candidate open, ms |
|---|---:|---:|
| 0 | 30.283878 | 56.659038 |
| 1 | 37.007871 | 33.518346 |
| 2 | 38.258907 | 33.283959 |
| 3 | 32.272222 | 33.715070 |
| **All-four mean** | **34.455720** | **39.294103** |
| Median | 34.640047 | 33.616708 |

The all-sample mean increased **4.838384 ms, or 14.0423%**. The candidate's
round-zero measurement accounts for the elevated mean. No sample is removed
from that conclusion, and four startup samples do not establish a reliable
tail distribution. The original automatic gate and workflow failure are
correct: they prevented silent acceptance before this review.

## Cause assessment and limits

The evaluator starts the `native_open_ms` timer immediately before
`MemoryBook(new_empty_path, cache_size=0)` and stops it upon entering that
context manager. This includes creating the SQLite schema and selecting WAL
mode. Imports, data ingestion, tokenizer initialization, and every recall
operation occur outside this interval.

The frozen baseline is `dd2f88be742ed330269e7dd5915b6f75089d7fef`; the frozen
performance candidate is `2d199b93f650eccd3dd239178822b31001b880e3`.
An independent syntax-tree comparison found identical constructor,
`__enter__`, schema, schema/application constants, input validation, and
directory-token helper implementations at those two commits. The new rowid
bound code is called by `recall`, after this measurement has finished. The
semantic telemetry change is lazy and is not entered by these lexical workers.
There is no added startup operation in the candidate's measured code path.

Other retained evidence is consistent with variable fresh-database runtime
or filesystem work: the synthetic baseline also recorded a 53.763824 ms open;
its all-four mean is 42.910099 ms versus 37.649570 ms for the candidate. The
public cohort's candidate median is lower, and its actual MCP initialization
mean changed by −0.2053%. Fresh-ingestion, unchanged-replay, and all measured
RSS/high-water means remain within the registered 10% review threshold.

**Inference:** variation in the unchanged empty-database initialization path
is the supported explanation for this one small-sample resource exception,
rather than execution of the new retrieval query. The original run did not
collect syscall traces, disk-wait measurements, or scheduler events; its
specific operating-system cause cannot be reconstructed. Source equivalence
does not guarantee identical timing on every deployment.

## Independent review recommendation

Accept the **retrieval optimization with the startup exception disclosed**,
subject to the remaining round-three correctness and comparison requirements.
This recommendation accepts the observed +4.838384 ms mean rather than
reclassifying it as a passing automatic resource check. It does not support a
startup speedup or startup non-regression claim. Keep the original failure
marker and the separate review linked wherever the performance acceptance is
reported. No timing rerun is needed or justified to choose a faster result.

This is a review of the performance candidate only. It does not decide the
separate project-statistics quality experiment, qualify optional semantics,
or complete the release by itself.

## Cross-verification of the existing startup diagnostic

The separately registered [startup-only diagnostic](../benchmarks/reports/round3-startup-review-43266672875-1/summary.json)
had already completed as run `43266672875`, attempt 1. Its original result
commit is `a129e324fb4af9e821325a797edb882beecc30a4`; the subsequent
[resource decision](../benchmarks/experiments/round3-startup-resource-decision.json)
at `e1a17c2f04a806e8a8d214c2d46c841749dfd266` agrees with this review.
An additional [independent offline check](../benchmarks/reports/round3-recovery/startup-diagnostic-cross-verification.json)
recomputed all 80 samples and verified each original worker's Git blob and
SHA256 identity, the fixed schedule, registered files, pinned sources, empty
databases, matching SQL/schema, and 64 unchanged startup AST components.
This check executed no new startup measurements or retrieval calls. The prior
preparation failure's measurement step was confirmed as skipped.

The separate diagnostic retains a **+0.4799% plain startup mean** and
**+5.8219% plain p95** change; the instrumented mean changes **−0.4883%**.
Schema initialization accounts for approximately **94.4%** of instrumented
wall time, including **13.5–13.8 ms** beyond process CPU. This supports a
wait-dominated unchanged initialization stage, without identifying the OS
cause of the historical long sample. These observations are not pooled with
or substituted for the original formal results. The original **+14.0423%**
mean, automatic `accepted: false`, and strict-audit scope remain unchanged;
the resource decision explicitly accepts that disclosed cost.
