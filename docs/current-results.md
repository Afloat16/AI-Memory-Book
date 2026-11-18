# Current development results and evidence

The README describes the **v0.11 source under validation**. Its original
v0.10 published-wheel verification remains unchanged in
[the archived results](v0.10.0-readme-results.md). New source replay, navigation
contracts, upstream component executions and historical timings have distinct
boundaries. A source replay is not a published-wheel or delivery verification.

## Source and experiment identities

| Evidence | Identity / execution |
|---|---|
| Baseline | v0.10 main `234891619d7bed88ddf3fae37e7f3e1b14a808b6` |
| Candidate 1 engineering replay | `da0ad5bac2395e6d196f4c8cf3af9d508eed7210`; 800 responses per runtime |
| Candidate 2 engineering replay | `a7d36322f77a3fca9f5907db3edcce4a7dd3652c`; 800 responses per runtime |
| Directory v2 | Same candidate-2 snapshot; 119 contracts, 130 locator calls and 161 original-page reads |
| New upstream adapters | Frozen before quality execution at `db96c704a26be944399ec491630da73de8c5dd71` |
| New evaluator closure | SHA-256 `249556338fef641eb6221daf5796cba792dbe10047f795f7e323a2d6bcca933a` |
| Engineering dataset | SHA-256 `87e8ccad3510fb7e8a4c68c9fa3f284473abf8381ef6444ad179e3d4196b3ac3` |
| New external execution | 18 setups, 720 native calls, 480 packed responses; independent audit verified |

Both source engineering replays independently check all scores, original source
references and budgets and have zero per-case score changes or regressions
against the baseline. They are not full serialized-response equivalence claims:
new diagnostic fields are present. An independent review subsequently found a
candidate-2 unclassified-proposal regression outside that fixture. The
[validation record](v0.11.0-validation.md) retains that blocker and its resolution
history; the original 80-question replay alone does not authorize a release.

## Fixed workload and common comparison boundary

| Property | Fixed setting |
|---|---|
| Workload | Authored synthetic engineering development/regression fixture |
| Scope | 8 projects, 4 algorithm families, 6 chronological checkpoints |
| Questions | 80 total: 72 answerable, 8 missing-evidence queries |
| Denominators | 80 required evidence spans; 48 fixed-policy cases |
| External candidate boundary | Same original page bodies, exact project scope, at most 5 native candidates |
| Common packing | Original whole blocks with citation framing; oversized blocks are skipped |
| Native excerpt track | Book plus repository flat-FTS, recent-history and no-memory strategies |
| Excluded conclusions | Coding-LLM accuracy, independent holdout performance, production task success, universal superiority |

The six original external executions and the three new ones have identical
dataset and all six checkpoint page-bundle digests, with 24/56/80/104/120/144
visible pages. New executions rebuild native indexes at each checkpoint;
they do not establish native update/delete correctness. The final checkpoint
has only 44 distinct page bodies among 144 pages, including repeated maintenance
text. This limits the fixture's discrimination.

## Complete common-block results

Historical rows retain their original pinned runs. BM25S and Haystack are new
executions of actual upstream library/framework APIs. Memvid's configured-query
limitation is disclosed separately below instead of presented as a product score.

| Component / tested mode | Budget | Required spans | Complete cases | Fixed-policy checks | Stale-only | Mean characters |
|---|---:|---:|---:|---:|---:|---:|
| **Book, source replay** | 2,400 | **80/80** | **72/72** | **48/48** | **0** | 1,799.2 |
| BM25S 0.3.16, native defaults | 2,400 | 80/80 | 72/72 | 48/48 | 0 | 1,846.7 |
| Haystack 3.5.0, native BM25 | 2,400 | 74/80 | 66/72 | 42/48 | 0 | 1,884.7 |
| billion-context, pinned search kernel | 2,400 | 72/80 | 64/72 | 40/48 | 0 | 1,955.0 |
| claude-mem, supplied-observation FTS | 2,400 | 72/80 | 64/72 | 40/48 | 0 | 1,488.5 |
| Basic Memory, explicit FTS | 2,400 | 72/80 | 64/72 | 40/48 | 0 | 1,333.1 |
| Each shared-MiniLM configuration | 2,400 | 55/80 | 47/72 | 25/48 | 4 | 1,963.1 |
| **Book, source replay** | 1,200 | **76/80** | **68/72** | **44/48** | **4** | 1,048.1 |
| BM25S 0.3.16, native defaults | 1,200 | 80/80 | 72/72 | 48/48 | 0 | 1,045.3 |
| Haystack 3.5.0, native BM25 | 1,200 | 74/80 | 66/72 | 42/48 | 0 | 969.9 |
| billion-context, pinned search kernel | 1,200 | 72/80 | 64/72 | 40/48 | 0 | 948.5 |
| claude-mem, supplied-observation FTS | 1,200 | 72/80 | 64/72 | 40/48 | 0 | 848.0 |
| Basic Memory, explicit FTS | 1,200 | 72/80 | 64/72 | 40/48 | 0 | 948.6 |
| Each shared-MiniLM configuration | 1,200 | 55/80 | 47/72 | 25/48 | 4 | 1,036.7 |

**BM25S ties Book's complete-evidence and policy counts at 2,400 and leads at
1,200 characters.** At 2,400 Book finds six more complete cases than Haystack
and eight more than each of the three historical lexical modes. At 1,200
Book's four stale-only cases are retained. A better aggregate does not imply a
win on every question. Character counts are not token counts or billing costs. Displayed means use
one decimal place with decimal round-half-up; source reports retain exact values.

Mem0 (`infer=False`, Chroma provider), Chroma and LangGraph Store were executed
separately with the same real local MiniLM representation. Their scores are
correlated, not three independent model evaluations. Mem0 fact extraction,
claude-mem's observer and Basic Memory's full default hybrid workflow were not
run. Haystack/BM25S do not constitute complete memory products. Source mapping
checks belong to the experiment's adapter boundary, not identical native
citation functionality. [All modes and official sources](open-source-memory-comparison.md).

BM25S completes 8/8 cases in each answerable category. Haystack has 2/8 for
historical decisions and 8/8 in the other answerable categories. Detailed
historical categories and all per-question records remain in their original
reports. All eight scored external configurations and Book return context for
the eight missing-evidence queries; that is not a measurement of refusal or
invented answers by a model.

### Memvid: retained empty-query result and separate diagnosis

`memvid-sdk==2.0.160`, explicit `mode="lex"`, returned native `hits=[]` for all
80 unchanged natural-language questions in all three repetitions. This is an
actual execution result, not adapter filtering or an invented failure score.
Its 0/72 complete-evidence count remains in the raw report; the README reports
the query limitation instead of calling the whole product inferior.

A separately recorded 14-call diagnosis uses the first checkpoint's unchanged
pages. The original full question returns no hits both with and without scope.
Original-text keywords such as `edge_policy` and `routing` return source-verified
pages; `edge_policy routing kernel` also returns hits, while `current edge_policy`
does not. These controls demonstrate a usable index and a query-behavior
boundary in this configuration. They do not identify every internal matcher
rule or justify replacing scored questions with rewritten ones. An all-empty
result is not evidence of calibrated abstention.

The pinned API normalizes whitespace and adds metadata framing. Validation
compares full normalized text and native frame/URI/project/title/time identities
before mapping to the supplied original page bytes. It does not establish
byte-exact native source reading. The original wheel's one inconsistent RECORD
entry and absent-scope native error are disclosed in the fixed protocol.

[Protocol and pre-quality failures](../benchmarks/competitors/extended-lexical-plan.md)
· [Formal report](../benchmarks/reports/v0.11-extended-lexical/attempt1/report.json)
· [Independent audit](../benchmarks/reports/v0.11-extended-lexical/attempt1/audit.json)
· [Exact counts](../benchmarks/reports/v0.11-extended-lexical/verified-metrics.json)
· [Diagnostic](../benchmarks/reports/v0.11-extended-lexical/memvid-query-diagnostic-1/report.json)
· [Original-byte restoration and reproduction](../benchmarks/reports/v0.11-extended-lexical/README.md).

## Native excerpt strategies

| Strategy | Budget | Required spans | Complete cases | Fixed-policy checks | Stale-only | Mean characters |
|---|---:|---:|---:|---:|---:|---:|
| Book | 2,400 | 80/80 | 72/72 | 48/48 | 0 | 1,799.2 |
| Scoped flat FTS | 2,400 | 60/80 | 52/72 | 28/48 | 14 | 1,801.3 |
| Recent history | 2,400 | 64/80 | 56/72 | 32/48 | 0 | 2,260.9 |
| No memory | 2,400 | 0/80 | 0/72 | 0/48 | 0 | 0.0 |
| Book | 1,200 | 76/80 | 68/72 | 48/48 | 0 | 1,195.9 |
| Scoped flat FTS | 1,200 | 56/80 | 48/72 | 28/48 | 14 | 1,154.0 |
| Recent history | 1,200 | 40/80 | 32/72 | 16/48 | 0 | 1,184.0 |
| No memory | 1,200 | 0/80 | 0/72 | 0/48 | 0 | 0.0 |

At 2,400 characters Book recovers 20 more complete cases than scoped flat FTS
and 16 more than recent history with 20.42% fewer mean context characters.
These are repository strategies, not additional external products. Recent
history has shorter citation headings and no top-five candidate limit. Book's
native excerpt policy result at 1,200 must not be substituted for its different
common-block result when comparing external components.

## Historical performance, not new runtime timings

The README's semantic/directory figures retain the original
[v0.10 component experiment](comprehensive-v010-validation.md), including its
small-fixture regressions and rejected first directory candidate. Its native
figures retain the [earlier native-core experiment](native-core-validation.md),
including slower rounds, startup and resource costs. No timing from those hosts
is assigned to v0.11. Current-state recall and directory transaction behavior
have changed; identical C/header bytes prove component continuity only.

The new current-revision three-repeat probes are development diagnostics,
including a configuration slower than baseline. No cross-component speed
ranking, whole-system speedup or combination of percentages is claimed.
[New probe details and limits](v0.11.0-validation.md#current-revision-recovery).

## Reproduce without replacing evidence

Every output path must be new. The source replay driver requires immutable
baseline/candidate directories whose tracked runtime bytes match their Git
commits; it retains failures and independently recomputes scores. Run the
[driver](../scripts/validate_v011_engineering.py) with `--baseline-source`,
`--candidate-source`, `--candidate-commit` and a new `--output` directory.
Native snapshots need a compatible built extension matching their recorded C
source. Directory v1 and v2 retain their separate preregistered protocol hashes.

For new upstream components, use the exact hash-pinned environment and commands
in [the extension protocol](../benchmarks/competitors/extended-lexical-plan.md).
The evidence recovery helper restores compressed original records into a new
directory and checks both compressed and original-byte hashes before the frozen
offline evaluator runs. It does not redo quality searches or revise scores.
