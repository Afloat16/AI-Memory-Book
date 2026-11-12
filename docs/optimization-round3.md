# v0.3.1 optimization protocol

Baseline: published **v0.3.0**, commit `dd2f88be742ed330269e7dd5915b6f75089d7fef`.
The machine-readable [registered plan](../benchmarks/experiments/round3-plan.json)
is authoritative. This round has two separate hypotheses.

## Preserve results while reducing query work

Old-data profiling points to SQLite execution as a major cost. For a project
query, its smallest and largest page rowids provide a safe envelope for FTS.
An explicit FTS outer loop can let SQLite skip postings outside that envelope;
the exact project/chapter/session filters, global BM25, ties and candidate limit
remain in place. Artificial interleaved projects made an unconditional bound
slower, so the single candidate enables it only when the project spans at most
half the table's inclusive rowid range. Otherwise it keeps the original query.
Bounds are read in the existing transaction, without a Python cache.

Acceptance requires identical complete non-timing outputs, unchanged indexed
content and source/cache/budget invariants. The formal measurement has **47,320
calls**, ten cohort/configuration cells and four balanced rounds. Every round,
including regressions, is retained. The performance gate requires at least 5%
geometric-mean p95 improvement, a public native p95 improvement of at least 10%,
and no pooled cell's p50 or p95 worsening by more than 5%.

## Test one project-statistics candidate

The current project filter limits results, while SQLite BM25 still uses global
FTS statistics. An artificial fixture confirms that adding another project's
pages can alter the first project's ordering. This does not establish a cause
for historical evidence failures or guarantee that local statistics are better.

The sole quality candidate is an explicit opt-in, one-project TEMP exact/stem
index built from existing indexed text. It retains all other ranking rules.
The active revision/project marker is transactional; a main revision change
invalidates and rebuilds the derived index. Default behavior remains global.

The candidate receives one development screen: four old cohorts, three budgets,
baseline and candidate, **8,082 calls**. No cohort/budget evidence metric may
decline, and the primary 512-token diagnostic groups also have a non-regression
gate. Record all per-question losses, cold builds, project-switch costs, memory
and temporary storage. A failed candidate is archived, not retuned or shipped.

## Freeze before the new selection

Only after implementation and evaluator/source/model/upstream identities are
frozen will an independent validator select another 256 HotpotQA IDs. Exclude
both historical selections; sort by the plan's fixed salted ID hash, never by
questions or outcomes. This is a new selection from the same source, not a new
domain. Its first score makes it regression data thereafter.

Measure v0.3.0 lexical, the accepted candidate's lexical and existing optional
Q2 modes across both reference tokenizers and three budgets. The same-host
component comparison includes **claude-mem, ai-memory and billion-context**,
with common pages, top-5 and whole-block packing. Keep native search/read costs
separate from common context costs and from unmeasured observer/generation
workflows. The optional statistics mode is included only if it passes its
registered old-data gate.

## Keep progress durable and claims bounded

Publish source/plan checkpoints before expensive runs and preserve every
completed worker. Historical frozen helpers and reports remain unchanged;
the rejected novelty experiments remain closed. Only accepted improvements
enter the next release. README highlights current measured advantages and
retains material weaknesses; it does not claim to beat every product on every
metric or present evidence recall as answer accuracy.
