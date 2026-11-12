# v0.3.1 completed optimization and evidence

The accepted runtime remains
[`2d199b93f650eccd3dd239178822b31001b880e3`](https://github.com/Afloat16/AI-Memory-Book/commit/2d199b93f650eccd3dd239178822b31001b880e3),
compared with published v0.3.0
[`dd2f88be742ed330269e7dd5915b6f75089d7fef`](https://github.com/Afloat16/AI-Memory-Book/commit/dd2f88be742ed330269e7dd5915b6f75089d7fef).
The original [registered plan](../benchmarks/experiments/round3-plan.json)
remains authoritative and unchanged. This page records its completed decisions.

## Accepted: bounded FTS work with identical default results

For project-scoped recall, an indexed MIN/MAX query finds the project's page
rowid envelope. The optimized statement applies those bounds and an explicit
FTS outer loop only if the project spans at most half the table's inclusive
rowid range. Broader or interleaved projects retain the original statement.

Bounds are read inside the existing transaction, without a Python cache.
Global BM25, exact project/chapter/session filtering before LIMIT, deterministic
tie order and the candidate limit remain unchanged. No persistent schema or
source data migration is introduced. This reduces unnecessary query work
while preserving the original evidence contract.

The [formal run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43246417515)
completed **47,320 calls, 16 workers and four balanced ABBA rounds** over the
registered synthetic and public-conversation regression cohorts. The
[saved summary](../benchmarks/reports/round3-performance-43246417515-1/report.summary.json)
and raw workers preserve every measurement. Complete non-timing payload,
source, scope, cache, index and budget checks pass.

| Cohort | Configuration | Baseline p95 ms | v0.3.1 p95 ms | Change |
|---|---|---:|---:|---:|
| Synthetic | Native, 4,000 characters | 13.500917 | 12.842840 | −4.8743% |
| Synthetic | Actual MCP, 4,000 characters | 16.011965 | 15.423507 | −3.6751% |
| Synthetic | Native, 512 tokens | 21.052449 | 21.078729 | **+0.1248%** |
| Synthetic | Native, 1,024 tokens | 23.710123 | 23.643494 | −0.2810% |
| Synthetic | Native, 2,048 tokens | 20.872050 | 20.682109 | −0.9100% |
| Public conversations | Native, 4,000 characters | 5.053851 | 3.737317 | **−26.0501%** |
| Public conversations | Actual MCP, 4,000 characters | 7.408803 | 5.936841 | **−19.8677%** |
| Public conversations | Native, 512 tokens | 7.619916 | 6.408086 | −15.9035% |
| Public conversations | Native, 1,024 tokens | 6.705825 | 5.504397 | −17.9162% |
| Public conversations | Native, 2,048 tokens | 6.683904 | 5.397920 | −19.2400% |

The pooled p95 geometric-mean improvement is **11.3587%**, above the registered
5% gate. The public native gain exceeds 10%, and no pooled p50 or p95 cell
regresses by more than 5%. The small synthetic 512-token regression remains
part of the calculation. Old-data performance is regression evidence.

### Startup cost accepted separately

The original automatic `accepted: false` remains correct and unchanged: one
resource mean crossed the separate review threshold. Opening a fresh empty
database in the public workers took **34.4557195 → 39.29410325 ms**
(**+4.83838375 ms / +14.0423%**, four samples per implementation). No sample was
dropped, and no retrieval timing was repeated to improve the result.

The [independent review](round3-performance-review.md) and separate
[startup decision](../benchmarks/experiments/round3-startup-resource-decision.json)
explicitly accept that measured cost. Startup source/SQL/schema checks found
no new initialization operation. A fixed 80-sample startup-only diagnostic
retains a +0.4799% plain mean and **+5.8219% plain p95**; its timings are not
pooled with or substituted for the formal experiment. The dominant unchanged
schema initialization includes substantial waiting, but the exact OS cause of
the original long sample cannot be proven retrospectively.

### Local ONNX telemetry

Book's optional local ONNX path disables telemetry through both the environment
and runtime API. This change applies to the Book model path. It makes no
statement about telemetry behavior inside separately executed competitor
binaries and does not change model weights, scoring or default lexical recall.

## Rejected: project-local ranking statistics

The sole registered quality candidate used a transactional, one-project TEMP
exact/stem index while retaining all other ranking rules. The development
screen had four old cohorts, three budgets and **8,082 actual calls**.

A prior interruption left aggregate upload chunks incomplete. Recovery located
all eight original workers and their eight ledgers, rebuilt the aggregate and
verified the preserved compressed/uncompressed prefixes. No retrieval was
rerun. The [quality review](round3-quality-review.md), independent audit and
original files record the decision **`rejected_loss_or_no_gain`**:
**14 registered loss checks**, despite ten aggregate improvements.

Examples explain the rejection. Synthetic 512-token complete evidence declines
85.5263% → 82.2368%; public 512-token completeness declines
66.4099% → 65.6394%. Better Hotpot or larger-budget results do not satisfy a
gate that forbids these losses. The candidate is archived, is not shipped,
and was not included in the new comparison. There was no post-score retuning.

## Completed: the registered same-host comparison

The single [authoritative run 43267797247](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43267797247)
is saved at
[`c99f20531053b1c164fc5a5d3fa8e0c831eeb4de`](https://github.com/Afloat16/AI-Memory-Book/commit/c99f20531053b1c164fc5a5d3fa8e0c831eeb4de).
All ten stages completed. The [assessment](../benchmarks/results/round3-comparison-43267797247-1/assessment.json)
reports **`complete-verified`**, 4,608 native calls, 4,608 component searches,
and no validation failures. Complete default payload equivalence passes for
1,536 native and 768 component baseline/candidate pairs.

Candidate/evaluator/dependency/model/upstream identities were committed before
selecting 256 IDs with the plan's fixed salted ID-only algorithm. Both prior
cohorts are excluded (zero overlap); 607 required evidence annotations are
retained. The selected ID digest is
`ccca7b09ad37e74652d84c26c0c2a823ffaf9a64f9fd911cf72d0e468dec1d0f`.
The source is the same public HotpotQA corpus and becomes regression data
after the first score. See [run reconciliation](round3-reconciliation.md)
for the two unused registrations and their original immutable histories.

The [current comparison guide](comparison.md) publishes both reference
tokenizers, native versus common-page boundaries, actual search/read costs,
setup, memory, storage and material weaknesses. At 1,024 cl100k tokens,
default Book complete evidence is 52.34%, versus claude-mem 45.31%,
ai-memory 55.86% and billion-context 58.20%. Optional Q2 is 54.69% but loses
quality at 512 native tokens and adds model/index costs. It stays optional.
The billion-context kernel remains faster at its measured boundary.

## Durable checkpoints and release provenance

Plans and source identities precede measurement. Controllers commit each
completed stage and its attempt ledger before starting the next. All original
failure markers, partial-upload history, rejected candidates and resource
exceptions stay in Git. Recovery and integration reuse existing object hashes;
they do not require chat-sized transfers of large reports.

The final product runtime uses SHA256
`9c8118d26ae1a0eae4f31d9d4f44b2afa0ee5c54314bde5187deb27c473dee46`;
the complete `src/` tree, including the reader, is
`4f9a6ff7d7de644c1ce34f1780bef62c94dddfde`.
The active evaluator, binding and manifest retain their actual executed
bytes. Later diagnostic/recovery helpers remain separately checkpointed and
do not relabel the recorded experiment.

[Release notes](releases/v0.3.1.md) describe the product change and tradeoffs.
The [release procedure](releasing.md) requires all nine CI jobs on the exact
final source commit, matching main/tag provenance, deterministic package checks,
seven verified assets and a real published-installer smoke test. The release
manifest records the final source and asset hashes.
