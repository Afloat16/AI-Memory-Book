# v0.13 scoped-query development diagnosis

Status: completed **development pilot**, not a formal benchmark or release
acceptance result. The baseline is commit
`8044e4bafe18e73ea422af5eeb47ef961e65246c`. Runtime source was unchanged throughout.
Each temporary database contained at most 1,920 pages, inserted through normal
ingestion, and was removed after its original inputs and results were saved.

## Reproduction and original outputs

Run from this worktree with the shared Python 3.12 environment:

```sh
MEMORY_BOOK_TEXT_BACKEND=python PYTHONDONTWRITEBYTECODE=1 /workspace/scratch/428c08bef2bc/.venv/bin/python benchmarks/experiments/v013_scoped_work_probe.py --output benchmarks/reports/v0.13-development/performance-scope-probe-attempt1
MEMORY_BOOK_TEXT_BACKEND=python PYTHONDONTWRITEBYTECODE=1 /workspace/scratch/428c08bef2bc/.venv/bin/python benchmarks/experiments/v013_scoped_sql_probe.py --baseline-report benchmarks/reports/v0.13-development/performance-scope-probe-attempt1/report.json --output benchmarks/reports/v0.13-development/performance-sql-probe-attempt1
```

The output directories are exclusive: reproduction must choose new paths to
avoid replacing this evidence. The first report records completion of eight
cells and 78 full responses, repeat-payload equality and project-source checks,
the eight complete compressed input sets, actual SQL and query plans, source
hashes, and six cumulative profiles. The SQL replay completed with exit code 0;
its compressed report retains every query, every original row, seven timing
samples per route, plans, and separate observed replays. All 48 SQL join/range
candidate comparisons were exactly equal to their baseline rows, including
scores and ordering. Equality alone did not make a slower candidate acceptable.

The first pilot includes tracing/progress callbacks in timing; the second keeps
timing and observation separate. OS caches were not cleared. The backend is
Python and SQLite is 3.53.1. These small authored and inspected workloads do not
replace the separately frozen large-archive protocol.

## Observed work and rejected route

The target project stays at 120 one-page sessions in three chapters. Other
similar projects grow from 0 to 1,800 pages. Both a contiguous target layout and
one spread across the full rowid span are retained.

| Operation | Observation on this pilot |
| --- | --- |
| Directory lookup | Five global MATCH cursors for three selected chapters: count, chapter grouping, and one preview query per chapter. All plans use `M4` without rowid bounds. First-call VM instruction lower bounds grow from 33,000 to 75,000. |
| Relevance recall | Contiguous projects can use the existing `M4><` bounded route. The interleaved layout cannot meet the existing favorable-span heuristic; first-call VM lower bounds grow from 14,000 to 34,000. |
| Current supplementation | One global `M4` cursor plus a temporary chronology sort per chapter. The 96 combined returned-row quota does not bound the rows examined. |
| Connection initialization | Observed 0.46–0.90 ms in this instrumented pilot. Source inspection shows metadata/schema checks and existing-index lookup, not an intentional archive scan for an already current schema. This is not evidence for constant time at large scale. |
| Current declaration work | At the largest interleaved cell the extra cumulative profile spends about 0.037 s of 0.047 s in declaration qualification. Its semantics are a separate change; this workstream does not alter them. |

Driving FTS with the existing project/chapter page index was **rejected**. At
1,920 pages, the directory chapter-grouping query changes from approximately
0.87 ms to 41 ms. The chronology query changes from approximately 0.71 ms to
2.10 ms with contiguous target rowids and 0.72 ms to 7.08 ms when interleaved.
Plans show repeated `=M4` cursors, and traced SQL calls increase substantially.
Applying rowid bounds to chronology without controlling join order can choose
the same unfavorable page-first plan. These negative results remain in the
original report.

A distinct, explicitly non-product diagnostic fixes one target rowid while
varying archive size. Its BM25 median grows from approximately 0.20 ms at 120
rows to 0.52 ms at 1,920 rows, whereas the same one-row projection without BM25
is approximately 0.08 ms and 0.04 ms. These are warm, small-archive observations,
not a complexity proof. The score-free query is not an equivalent retrieval
candidate and must not replace ranking.

[SQLite's FTS5 documentation](https://www.sqlite.org/fts5.html#the_bm25_function)
defines BM25 with table-wide document count, average length, and phrase document
frequency. A rowid-range cursor does not make these statistics project-local.
Its [index documentation](https://www.sqlite.org/fts5.html#the_fts_index_idx_and_data_tables_)
describes rowid skip structures, while the
[SELECT documentation](https://www.sqlite.org/lang_select.html#special_handling_of_cross_join)
describes CROSS JOIN's loop-order constraint. Consequently no constant-time or
fully bounded global-work claim is justified here.

## Implementation direction

1. Reuse one MATCH and aggregation for directory counts, chapter ranking and
   section previews. Retain every ownership predicate, every matching page,
   global BM25 score, complete aggregation, pagination and exact tie breakers.
2. Reuse one MATCH for the selected current-revision chapters, retaining the
   existing full chronology order and exact per-chapter quotas. Do not change
   which chapters can propose revisions, qualification, evidence or sources.
3. Add only favorable project rowid bounds, keeping FTS as the outer loop when
   bounded. Interleaved layouts must remain covered without pretending this
   removes global phrase-frequency work.
4. Prefer statement-local CTE/window computation with an older-SQLite fallback;
   avoid new persistent tables, schema migrations, write triggers and caches.
5. Retain global revision-based cache invalidation: foreign writes can change
   global BM25 statistics. Project-only invalidation would not preserve exact
   ranking behavior without a separate justified design.

Any candidate must first pass full field/score/order comparisons against the
old query on the same database, scope and snapshot, including empty scopes,
pagination, repeated sources, tie timestamps and malformed ownership. Formal
large-archive measurements must use the independently frozen protocol and
separate candidate commits. This diagnosis promises no superiority over other
projects and no constant-time archive behavior.
