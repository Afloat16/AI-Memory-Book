# Current v0.13 source results and evidence

**Status: v0.13 source experiments and exact-source CI are verified; v0.13
publication is a separate gate.** The quick-start commands target v0.13.0 after its publication gates pass;
the currently published release remains v0.12.0. The long-history replay is independently audited from its original ZIP,
and the unchanged small engineering/declaration suites retain their own source
identities. Source tests, CI and public release delivery are not interchangeable.

The [v0.12 results snapshot](v0.12.0-readme-results.md) preserves the previous
`current-results.md` byte for byte. The [v0.11 results](v0.11.0-readme-results.md),
[original v0.12 publication proof](../benchmarks/reports/v0.12-publication/README.md)
and all failed development attempts remain available. No historical external
run or older speed measurement is relabelled as a new v0.13 execution.

## Source and experiment identities

| Evidence | Actual identity / scope |
|---|---|
| Published baseline runtime | Main checkpoint `8044e4bafe18e73ea422af5eeb47ef961e65246c`, preserving v0.12.0 runtime bytes |
| Final local engineering, directory and short-page replay | `91412b438a0da95549cc9a3b85eccb4915359a2d` |
| Remote formal / CI candidate | `e0e2515f6e16404cfb9b676cd2eab01ce84b81cc`; complete Git tree `b150f4dfa45a01d407301b60c3fd0f40dac1c420` equals local `91412b43` |
| Formal long-history run | `44331778554`, attempt 1; candidate `e0e2515f`, original unchanged protocol |
| Original run-2 artifact | SHA-256 `47df01825bf4e14baadf3154a24683e5f18aaa238790e013fde381610be6ceac` |
| Exact-source ordinary CI | Run `44331775791`, attempt 1; 11 successful jobs |
| Separate declaration / control replay | `4e4a8eb2fefe31a136033a37fcc844c36162ffae`; recall cache version 26 |
| Engineering evaluator | `6cf692ba3595cb236c5b9ea050bf0f8730b53c4c`; original frozen evaluator bytes |
| Engineering dataset | SHA-256 `87e8ccad3510fb7e8a4c68c9fa3f284473abf8381ef6444ad179e3d4196b3ac3` |
| Frozen 62-question diagnostic | `296cce97a05488224960e28065f35f594d755732` |
| Frozen longitudinal protocol | `b3fd165cb632c439ff28873fdba7f33e9d258178`; unchanged queries, source requirements and scorer |
| Currently published installation | v0.12.0 at `62508a1ce681111ec5702c88e3aa42f67b9fc9c0` |

The [complete-tree equivalence receipt](../benchmarks/reports/v0.13-development/postscale-sources/run2-source-equivalence.json)
binds local `91412b43` to remote `e0e2515f`; it does not rewrite measured commit
IDs. The earlier `4e4a8eb2` declaration replay remains labelled with that actual
source. The final source also contains the subsequent narrow SQL scope-planner
correction. Exact source histories can be recovered from the retained
[development bundles](../benchmarks/reports/v0.13-development/postscale-sources/manifest.json).

## Long histories across similar projects

The formal second run uses the original questions, requirements, scorer and
protocol after the first run exposed missing multi-source evidence. This is
**development evidence after observing failures**, not a new holdout. The
v0.12 baseline and frozen v0.13 candidate are compared within the same run on
separately restored baseline-built snapshots. Each source imports its recorded
runtime and native binary; the original hosted binary hashes are retained,
without claiming a local reconstruction of those binaries.

[Original run-2 artifact, manifest and lossless restorer](../benchmarks/reports/v0.13-scale-run2/README.md)
· [Independent saved-response audit](../benchmarks/reports/v0.13-development/scale-run2-review/scale-run2-saved-response-review.json)
· [Full run-2 review](../benchmarks/reports/v0.13-development/scale-run2-review/scale-run2-summary.md).

| Checkpoint | Pages | Projects | Controlled change | Complete recall, baseline → v0.13 |
|---|---:|---:|---|---:|
| `age-reference-1024` | 1,024 | 22 | Reference archive | 48/56 → **56/56** |
| `age-shift-1024` | 1,024 | 22 | Same content/order; all timestamps 3,650 days earlier | 48/56 → **56/56** |
| `foreign-10016` | 10,016 | 163 | Only similar foreign-project growth | 48/56 → **56/56** |
| `foreign-50016` | 50,016 | 788 | Further foreign-project growth | 48/56 → **56/56** |
| `own-100000` | 100,000 | 788 | Six target projects acquire their own long histories | 48/56 → **56/56** |
| `interleaved-100000` | 100,000 | 788 | Same logical sources and page IDs, different insertion order | 48/56 → **56/56** |
| `replacement-100000` | 100,000 | 788 | Six existing configuration sources replaced | 48/56 → **56/56** |

The eight target projects initially have 16 pages each. Two archived projects
stay at that size; six active/new targets grow. At the largest stages, 780 other
similar projects share the database. The age-shift and interleaving controls
preserve evidence projections within each arm. The repeated maintenance text
and authored cases limit extrapolation to arbitrary real archives.

| Quality outcome across seven stages | Baseline | v0.13 candidate |
|---|---:|---:|
| Answerable recall configurations complete | 336/392 | **392/392** |
| Required recall spans recovered | 392/448 | **448/448** |
| Current source first, where evaluated | 80/168 | **112/168** |
| Stale source before current source | 32 | **0** |
| Complete directory evidence | 56/56 | **56/56** |
| Missing-evidence queries returning nonempty context | 56/56 | **56/56** |
| Source errors / cross-project output | 0 | **0** |

Each version has 448 recall quality calls: 392 answerable configurations and
56 missing-evidence controls. They repeat 56 answerable and eight missing
questions across seven stages, so 392 is not an independent-question count.
The same query can be repeated further for timing without creating new quality
cases. All eight multi-source cases at every stage now include current policy
and boundary constraints, with required ranks **[2, 1]**: boundary first,
current policy second. The recorded current-first result is therefore 112/168,
not 168/168. The original baseline has eight omissions per stage; its incomplete
multi-source timings remain in the record. Both versions still return context
for every missing-evidence query; no calibrated abstention is established.

The original run-1 candidate had the same 48/56 complete cases per stage as the
baseline. Its failures and intermediate corrections remain in the
[development record](v0.13.0-validation.md). New evidence does not overwrite
those original scores. The independent run-2 auditor made no retrieval calls;
it checked 84 completed blocks, 13,608 original measurements and 66,136 source
references, and completed 166,409 saved-record checks. Those checks establish
integrity under the frozen scorer, not universal factual correctness.

## Fixed engineering replay

Both the v0.12 baseline and final v0.13 source were freshly executed in the same
environment. Each has **800 scored response configurations**: 640 responses
from four repository strategies and 160 Book common-block responses. This
amounts to 320 Book configurations and 480 no-memory/flat/recent-history
controls per runtime, drawn from the same 80 logical questions. It is not 800
independent questions or 800 fully correct Book answers.

The original worker and a separate offline auditor verified source coordinates,
budgets, runtime/evaluator identities and saved scores. There are **zero score
changes and zero regressions** between the two versions on this matrix. For
Book, every budget/surface configuration retains **80/80 required spans,
72/72 complete cases, 48/48 fixed-policy checks and zero stale-only cases**.
The eight missing-evidence queries still return nonempty related context.
[Final source replay](../benchmarks/reports/v0.13-development/legacy-gates-integrated/91412b43-attempt1/summary.json)
· [Independent saved-response audit](../benchmarks/reports/v0.13-development/legacy-gates-integrated/91412b43-attempt1/independent-review/legacy-91412b43-saved-response-review-attempt1.json).

| Property | Fixed setting |
|---|---|
| Workload | Authored synthetic engineering development/regression fixture |
| Scope | 8 projects, 4 algorithm families, 6 chronological checkpoints |
| Questions | 80 total: 72 answerable, 8 missing-evidence queries |
| Denominators | 80 required evidence spans; 48 fixed-policy cases |
| Budgets | 1,200 and 2,400 characters, including citation framing |
| External candidate boundary | Same original page bodies, exact project scope, at most 5 native candidates |
| Common packing | Original whole blocks; oversized blocks skipped, with no query rewriting or candidate supplementation |
| Native excerpt track | Book plus repository scoped-flat-FTS, recent-history and no-memory strategies |
| Excluded conclusions | Coding-LLM accuracy, independent holdout quality, production task success, calibrated abstention, universal superiority |

All external rows use the original workload and six supplied-page checkpoints
of 24/56/80/104/120/144 visible pages. The final checkpoint has only 44 distinct
page bodies among 144 pages, including repeated maintenance text. External
indexes were rebuilt at each checkpoint; their results do not establish native
update/delete lifecycle behavior or large-archive performance. The
[LanceDB/Whoosh input audit](../benchmarks/reports/v0.12-search-components/same-input-audit.json)
and original source bundles bind the shared input bytes.

## Eleven executed external configurations

These are the **historical tested pins**, not a claim to test every current
upstream release or every product's full default workflow. Ten configurations
have scored rows below; Memvid's native-query limitation is reported separately.

| Configuration | Retained pin | Actual tested boundary |
|---|---|---|
| billion-context | `9674cfafbc78c50245ae0d887483d3d6ce880c15` | Pinned search kernel, not the complete proxy workflow |
| claude-mem | 15.18.1 at `c4a9f5725f420bf9c6e866cdd3b94bd36498af09` | Supplied raw-observation FTS; no observer |
| Basic Memory | 1.0.0 at `c9bd187b83baba549d5cd16bacc180f8023d51c8` | Explicit FTS; no full default hybrid pipeline |
| Mem0 | `mem0ai==2.2.1` | `infer=False`, Chroma provider, shared MiniLM representation |
| Chroma | `chromadb==1.5.9` | Native vector retrieval with the same MiniLM representation |
| LangGraph Store | `langgraph-checkpoint==4.3.2` | Store retrieval with the same MiniLM representation |
| Haystack | `haystack-ai==3.5.0` | InMemoryBM25Retriever native BM25L and exact project filter |
| BM25S | `bm25s==0.3.16` | Native defaults, one index per project |
| LanceDB | `lancedb==0.41.0` | Native FTS and exact project prefilter |
| Whoosh | `Whoosh==2.7.4` | Default analyzer / BM25F, explicitly configured OR parser |
| Memvid | `memvid-sdk==2.0.160` | Explicit lexical mode and native URI-prefix scope |

Original source/package/model locks: [billion-context](../benchmarks/competitors/billion-round2-lock.json),
[claude-mem](../benchmarks/competitors/claude-mem-round2-lock.json),
[six-component matrix](../benchmarks/competitors/memory-systems-lock.json),
[Haystack/BM25S/Memvid](../benchmarks/competitors/extended-lexical-lock.json) and
[LanceDB/Whoosh](../benchmarks/competitors/v012_search_components.lock.json).
The shared MiniLM model and its content hash remain in the original lock;
three interfaces using it are correlated evidence.

## Complete common-block results

Book's rows are the final v0.13 source replay at `91412b43`. The six original
external configurations, Haystack/BM25S extension and LanceDB/Whoosh extension
retain their original pinned executions. None was rerun in the 100,000-page
v0.13 experiment. The three shared-MiniLM configurations are grouped for display,
not counted as one execution or three independent model evaluations.

| Component / tested mode | Budget | Required spans | Complete cases | Fixed-policy checks | Stale-only | Mean characters |
|---|---:|---:|---:|---:|---:|---:|
| **Book, v0.13 source replay** | 2,400 | **80/80** | **72/72** | **48/48** | **0** | 1,798.9 |
| BM25S 0.3.16, native defaults | 2,400 | 80/80 | 72/72 | 48/48 | 0 | 1,846.7 |
| Whoosh 2.7.4, BM25F / configured OR | 2,400 | 80/80 | 72/72 | 48/48 | 0 | 1,457.8 |
| Haystack 3.5.0, native BM25 | 2,400 | 74/80 | 66/72 | 42/48 | 0 | 1,884.7 |
| LanceDB 0.41.0, native FTS | 2,400 | 72/80 | 64/72 | 40/48 | 4 | 1,876.7 |
| billion-context, pinned search kernel | 2,400 | 72/80 | 64/72 | 40/48 | 0 | 1,955.0 |
| claude-mem, supplied-observation FTS | 2,400 | 72/80 | 64/72 | 40/48 | 0 | 1,488.5 |
| Basic Memory, explicit FTS | 2,400 | 72/80 | 64/72 | 40/48 | 0 | 1,333.1 |
| Each shared-MiniLM configuration | 2,400 | 55/80 | 47/72 | 25/48 | 4 | 1,963.1 |
| **Book, v0.13 source replay** | 1,200 | **80/80** | **72/72** | **48/48** | **0** | 1,041.5 |
| BM25S 0.3.16, native defaults | 1,200 | 80/80 | 72/72 | 48/48 | 0 | 1,045.3 |
| Whoosh 2.7.4, BM25F / configured OR | 1,200 | 80/80 | 72/72 | 48/48 | 0 | 884.5 |
| Haystack 3.5.0, native BM25 | 1,200 | 74/80 | 66/72 | 42/48 | 0 | 969.9 |
| LanceDB 0.41.0, native FTS | 1,200 | 72/80 | 64/72 | 40/48 | 4 | 1,035.8 |
| billion-context, pinned search kernel | 1,200 | 72/80 | 64/72 | 40/48 | 0 | 948.5 |
| claude-mem, supplied-observation FTS | 1,200 | 72/80 | 64/72 | 40/48 | 0 | 848.0 |
| Basic Memory, explicit FTS | 1,200 | 72/80 | 64/72 | 40/48 | 0 | 948.6 |
| Each shared-MiniLM configuration | 1,200 | 55/80 | 47/72 | 25/48 | 4 | 1,036.7 |

**Book, BM25S and configured Whoosh tie on complete evidence and fixed-policy
counts at both budgets. Whoosh uses fewer mean packed characters than Book at
both budgets.** At 2,400 Book finds six more complete cases than Haystack and
eight more than LanceDB and each of the three historical lexical modes. It
recovers 25 more than each shared-MiniLM configuration. A better aggregate does
not imply a win on every question or a ranking of complete products. Characters
are not model tokens or billing costs. Displayed means use decimal round-half-up
to one decimal place; original reports retain exact values.

Mem0 (`infer=False`, Chroma provider), Chroma and LangGraph Store were executed
separately with the same real local MiniLM representation. Mem0 fact extraction,
claude-mem's observer and Basic Memory's default semantic/hybrid workflow were
not run. Whoosh's OR parser was explicitly selected before quality execution;
its default parser is AND. The other tested Whoosh analyzer/scorer settings
remain native defaults. LanceDB's native FTS uses an exact project prefilter.
Haystack, BM25S, LanceDB and Whoosh are framework/store/retrieval components,
not complete conversation-memory products. Source-mapping checks authenticate
adapter mappings to supplied originals, not identical native citation features.

BM25S and Whoosh complete 8/8 in each answerable category. Haystack has 2/8
historical decisions and 8/8 in the others. LanceDB has 4/8 bilingual and 4/8
historical-decision cases and 8/8 in the others. Historical per-category and
per-question records are retained unchanged. All ten scored external
configurations and Book return context for all eight missing-evidence questions;
this is not a measurement of model refusal or invented answers.

### Memvid: retained query limitation

`memvid-sdk==2.0.160`, explicit `mode="lex"`, returned native `hits=[]` for all
80 unchanged natural-language questions in all three repetitions. The adapter
did not discard candidates. Its 0/72 complete-evidence count remains in the raw
report; the README reports the configured-query limitation separately, rather
than assigning the whole product a zero-score ranking.

A separate 14-call diagnosis uses the first checkpoint's unchanged pages. The
original full question has no hits with or without scope; original-text keyword
controls retrieve source-verified pages. Diagnostic queries do not replace
scored questions. The tested API normalizes whitespace and adds metadata framing;
the adapter verifies the entire normalized text and frame/URI/project/title/time
identity before mapping back to original bytes. It does not establish byte-exact
native source reading. An all-empty result is not calibrated abstention.

[Protocol and pre-quality failures](../benchmarks/competitors/extended-lexical-plan.md)
· [Original report](../benchmarks/reports/v0.11-extended-lexical/attempt1/report.json)
· [Independent audit](../benchmarks/reports/v0.11-extended-lexical/attempt1/audit.json)
· [Diagnostic](../benchmarks/reports/v0.11-extended-lexical/memvid-query-diagnostic-1/report.json).

## Native excerpt strategies

All rows below come from the final source's fresh engineering replay. The flat
strategy shares Book's native excerpt assembler; it is a repository control,
not a separately installed competitor. All its previous score outcomes remain.

| Strategy | Budget | Required spans | Complete cases | Fixed-policy checks | Stale-only | Mean characters |
|---|---:|---:|---:|---:|---:|---:|
| Book | 2,400 | 80/80 | 72/72 | 48/48 | 0 | 1,798.9 |
| Scoped flat FTS | 2,400 | 60/80 | 52/72 | 28/48 | 14 | 1,801.3 |
| Recent history | 2,400 | 64/80 | 56/72 | 32/48 | 0 | 2,260.9 |
| No memory | 2,400 | 0/80 | 0/72 | 0/48 | 0 | 0.0 |
| Book | 1,200 | 80/80 | 72/72 | 48/48 | 0 | 1,196.6 |
| Scoped flat FTS | 1,200 | 60/80 | 52/72 | 28/48 | 14 | 1,154.6 |
| Recent history | 1,200 | 40/80 | 32/72 | 16/48 | 0 | 1,184.0 |
| No memory | 1,200 | 0/80 | 0/72 | 0/48 | 0 | 0.0 |

At 2,400 Book recovers 20 more complete cases than scoped flat FTS and 16 more
than recent history with 20.4% fewer mean context characters. Recent history
has shorter citation headings and no top-five candidate limit. Native-excerpt
and common-block rows remain separate protocols even where their aggregate
counts agree.

The v0.11 → v0.12 1,200-character improvement is retained in the
[historical snapshot](v0.12.0-readme-results.md#what-changed-at-1200-characters).
The v0.13 replay has no new score gain on this particular fixture. Zero
stale-only is the fixed metric above, not removal of all historical evidence.

## Current declarations and bounded assessment

The final declaration/control replay is bound to `4e4a8eb2`, separately from
the final `91412b43` legacy replay. Python and native outputs agree on **914
saved entry pairs** after excluding only latency and cache-hit fields: 1,828
original entries in total. These are response/configuration counts, not that
many independent accuracy questions.
[Development report](../benchmarks/reports/v0.13-development/scale-correctness-review/development-review.json)
· [Independent offline audit](../benchmarks/reports/v0.13-development/scale-correctness-review/final-offline-audit-attempt2.json).

| Registered diagnostic | Per-backend observed result | Counting boundary |
|---|---|---|
| v0.13 62-question matrix | 38/38 answerable questions have expected first source and complete evidence in every auto setting | 496 response configurations per backend; 1,200/2,400 characters × one/five results × auto/relevance modes |
| Existing 38-question matrix | 32/32 answerable questions have expected first source and complete evidence in every auto setting | 304 configurations per backend; controls and relevance-mode outcomes retained separately |
| Additional correctness controls | 37/37 explicit expected outcomes met per backend | Quoted/conditional/negated references, revocation, fields/scopes and independently queried report/check facts |
| New regression unit methods | 10/10 per backend | Methods, not a count of every subtest as an independent question |

All 496 v0.13 configurations per backend match their registered assessment and
occurrence-intent labels. This is a diagnostic-contract result; it is not
496/496 factual answers. The original 13-entry independent review was replayed; its outputs match
the preceding `0a48eadd` candidate, including pure-prose `最终输出维度` and `current.phase_size`
limitations. These are different cases from the two original 38-question
Chinese diagnostic cases now passing. The tuned small replay is development
evidence, not a new holdout.

The added comparison rules use complete authenticated sources, local scope,
whole field identity and exact literal agreement. A quoted, conditional,
negated or differently scoped mention cannot automatically validate repeated
values. A complete explicit no-change report may yield its relevance position
to a comparable decision, but an explicitly requested report action, report
object or independent check result keeps its own source. Unknown extra clauses
retain conservative behavior. These are finite syntactic rules, not general
natural-language interpretation; repeated non-ASCII field identities remain
conservative.

| Assessment status | Meaning within the inspected candidate pool |
|---|---|
| `comparable_declaration` | At least one authenticated comparable declaration was established |
| `potential_conflict` | Latest equal-time comparable declarations contain distinct literals; page IDs identify sources to inspect |
| `no_comparable_declaration` | No comparable declaration was established by the inspected routes; related text can still be returned |
| `no_matching_evidence` | The assessed route produced no matching candidates; this is not an exhaustive archive search |
| `not_assessed` | Declaration assessment did not run for this request, including relevance/history, occurrence or skipped retrieval routes |

MCP compact output retains assessed status and conflict page IDs. It does not
silently turn a conflict into an authoritative value. Query scope and source
reads still require the same project identity. Equal timestamps alone do not
establish factual authority; source order inside a session remains distinct
from a conflict across comparable sources. Missing evidence and unrecognized
syntax remain uncertainty, not proof that no decision exists.

## Directory navigation, source scope and budgets

The final `91412b43` replay passes **119/119 directory contracts per backend**.
Each backend performs 130 locator calls and 161 original-page reads covering
80 distinct pages. The saved-source audit preserves 36 expected error outcomes
and finds zero source mismatches. These repeated operations test exact scope,
metadata navigation, pagination and follow-up reads; they are not additional
answer-quality questions. [Final contracts and operations](../benchmarks/reports/v0.13-development/legacy-gates-integrated/91412b43-attempt1/summary.json).

Directory hits explicitly have `evidence=false`; titles and summaries are
navigation hints. Following their addresses reaches the original evidence.
A project-bound MCP connection inherits its configured project when omitted
and rejects conflicting project or foreign-page requests. Unbound requests can
search across books. This prevents accidental scope switching within a bound
connection; it is not multi-user authentication or automatic inference of the
project from the current terminal directory.

The short-page replay executes **482 configurations per backend**. All **434**
recorded current-evidence presences remain present; 48 original insufficient-
budget controls remain. The original 34 regressions from an earlier unprotected
candidate are retained and their available control payloads independently
verified. The other original controls retain their recorded presence observations;
missing historical payloads were not reconstructed. Characters include citation
headings and separators in `context`, not the whole JSON response or model
billing tokens. Optional token caps are a separate interface.

## Long-history performance and remaining costs

The formal run contains **84 execution blocks, 1,008 quality calls and 12,600
performance calls: 13,608 total**. Seven recall queries and two full directory
chains repeat at each stage, across six balanced rounds ordered
`AB, BA, BA, AB, AB, BA`. Each recall query/version/stage has **30 cold-result-cache
calls and 90 immediate warm-result-cache calls**; directory chains have 30.
The optional 200,000-page extension was not executed.

Cold means deleting the recall-result cache before timing. OS, SQLite page and
helper caches are not flushed. Warm calls use the immediate result-cache path.
Directory timing includes discovery, section access and original-page reading.
Snapshot restore, opening the database, scoring and journaling are outside the
query timer. The single hosted Linux x86_64 runner reports Python 3.12.16,
SQLite 3.45.1 and AMD EPYC 7763 with four logical CPUs exposed. These are API
measurements on one authored workload, not model generation or coding-task
completion time. [Raw timing review](../benchmarks/reports/v0.13-development/scale-run2-review/scale-run2-summary.md).

| Timing family | Query-stage groups | Lower candidate pooled p50 | Higher candidate pooled p50 | Lower / higher median paired-round p50 ratio |
|---|---:|---:|---:|---:|
| Cold-result-cache recall | 49 | 12 | **37** | 14 / **35** |
| Warm-result-cache recall | 49 | 42 | **7** | 42 / **7** |
| Complete directory chain | 14 | **14** | 0 | **14** / 0 |

Pooled p50 is the median of all calls in a group. The paired summary first
compares baseline/candidate medians within each of the six rounds, then takes
the median of those ratios. The two statistics answer different questions and
can differ in direction; the cold 12/37 and 14/35 counts are not interchangeable.
They are observed directions, not statistical-significance claims. p95 uses
nearest rank with n=30 for cold/directory and n=90 for warm.

| Checkpoint / query | Baseline p50 → v0.13 p50, ms | Baseline p95 → v0.13 p95, ms |
|---|---:|---:|
| Interleaved 100k · archived current | 166.898 → **102.478** | 175.218 → **113.145** |
| Interleaved 100k · archived historical | 133.222 → **67.912** | 134.992 → **69.078** |
| Interleaved 100k · archived directory chain | 159.154 → **26.707** | 163.496 → **30.749** |
| Interleaved 100k · active current | 332.062 → **338.309** | 337.134 → **341.403** |
| Reference 1,024 · archived current | 6.726 → **10.516** | 16.026 → **20.485** |
| Reference 1,024 · multi-source | 7.235 → **11.316** | 7.595 → **11.674** |

Recall rows in this table are cold-result-cache calls; the directory row is the
complete uncached navigation chain. The worst cold pooled p50 increase is
**56.4%** for the small multi-source query, whose baseline omits the current
policy. The small archived-current query also rises **56.3%**, so the costs
cannot all be attributed to fixing an incomplete answer. All seven warm
slowdowns are multi-source queries; their additional complete evidence and
extra latency are both retained. The largest warm pooled p50 increase is 9.3%.
No failure or slower row is discarded from the complete tables.

Cold recall still depends on archive size, even when an archived project's own
pages do not grow. A better 100k archived query is not constant-time access.
The implementation reuses directory/chronology matching work and can use exact
small project membership when a row-ID range is unhelpful, preserving ownership
joins, fallback routes and source/result semantics. [FTS5 BM25 scoring](https://www.sqlite.org/fts5.html#the_bm25_function) still uses
whole-table document counts, average length and phrase document frequencies; bounded output does not bound every scan, rank computation
or source authentication step. Initialization, storage and process-lifetime peak
RSS are separate resource observations, not included in the query latency or
claimed as per-query allocation.

Earlier [v0.10 semantic/directory timings](comprehensive-v010-validation.md) and
[native-core timings](native-core-validation.md) remain historical, including
their startup costs and slower cases. Unchanged C/header bytes establish
component continuity only; these historical percentages are not v0.13 speedups
or additions to the new experiment.

## CI and publication boundary

Exact-source [CI run 44331775791, attempt 1](https://github.com/Afloat16/AI-Memory-Book/actions/runs/44331775791)
passed all 11 jobs at `e0e2515f`: five Python core jobs, MCP, browser reader,
three installer jobs and container. The MCP log records 1,719 discovered tests,
1,705 passes, 14 skips and zero failures/errors.
[Retained metadata and complete MCP log](../benchmarks/reports/v0.13-development/final-source-ci/review.json).
These results do not cover a future source commit containing release registration
or establish a new wheel matrix/public installation.

The published v0.12.0 remains separately proven by release run `44275753685`,
attempt 1: 30 native cells, 4,245 passes plus 75 permitted skips, 67 independently
downloaded assets and successful real public-URL installation. Its exact-source
CI is `44275753683`, attempt 1. These facts remain [v0.12 delivery evidence](../benchmarks/reports/v0.12-publication/README.md),
not v0.13 publication counts. Archive schema remains 4.

## Architecture coverage and reproduction

The retained official-source review covers **26 external project families**,
including six retrieval/store libraries or frameworks. Eleven configurations
were actually executed on the small original fixture; other families receive
feature/deployment coverage with pinned sources, without invented runtime
scores. [Architecture comparison and exact source references](open-source-memory-comparison.md).

Use immutable runtime/evaluator commits and fresh output directories. Preserve
failed attempts and no-answer/control cases. The
[engineering replay driver](../scripts/validate_v012_engineering.py),
[62-question evaluator](../benchmarks/v013_accuracy_eval.py) and
[38-question evaluator](../benchmarks/v012_revision_eval.py) retain their
registered protocols. Saved-response auditing is independent of rerunning
retrieval. The [LanceDB/Whoosh restorer](../benchmarks/reports/v0.12-search-components/README.md#evidence-and-lossless-restoration)
verifies archive parts and original files before offline audit; it does not
re-execute the upstream search engine.
