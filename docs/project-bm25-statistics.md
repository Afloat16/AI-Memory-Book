# Global BM25 statistics for small project retrieval

An exact project filter previously limited the returned rows while SQLite's
`bm25()` still calculated query document frequencies from the global FTS posting
lists. Repeated engineering identifiers in many unrelated projects therefore
made an unchanged old project more expensive to search.

The new default route avoids that repeated global frequency calculation for
complete small projects in larger archives. It retains the same **global**
document count, average document length, document frequency, column weights,
candidate limit and deterministic tie ordering. It does not change to
project-local BM25 or discard old pages.

## Derived statistics and source preservation

Three ordinary SQLite tables store the derived statistics:

| Table | Contents |
| --- | --- |
| `bm25_corpus` | Exact/stem document counts and total token counts |
| `bm25_terms` | Exact/stem document frequencies over all columns, body only, and the directory metadata column union |
| `bm25_pages` | Compressed per-page term frequencies for all four indexed columns, plus a decoded-size bound |

The SQLite build itself supplies `unicode61` and `porter unicode61` tokens.
No independent Porter implementation or approximate tokenizer is substituted.
The rank formula follows [SQLite FTS5 BM25](https://www.sqlite.org/fts5.html#the_bm25_function),
including its negative sign, `k1=1.2`, `b=0.75`, nonpositive-IDF floor and
column-specific phrase frequencies. Repeated phrases produced by stemming
remain repeated in the formula. Unsupported token-to-phrase shapes use the
original FTS route.

Original sessions, turns, sections, pages, source coordinates, both FTS indexes,
source hashes and the database schema version remain unchanged. The statistics
are not an alternative source of evidence. Every final excerpt is still read
from its original page and authenticated through the existing source path.

## Complete scope and resource bounds

The fast route activates when the archive contains at least 4,096 pages and the
requested exact project contains at most 256 pages. A project-index lookup reads
at most 257 rows before deciding whether the **entire** scope fits. Chapter and
session predicates are applied within that complete project. A 257-page project
falls back to the complete original search; its first 256 pages are never used
as a substitute for its history.

The sum of compressed summaries must fit 2 MiB and their recorded decoded size
must fit 8 MiB. Invalid/missing metadata, unsupported query phrase shapes,
customized connections, reduced SQLite limits and larger scopes retain the
original route. Coverage and semantic retrieval also retain the original route.
These are performance eligibility bounds, not retention policies.

Recall scores the complete eligible scope before keeping the original top 96
exact/stem candidates. Current-state supplementation uses the same complete
exact-match set, with the unchanged timestamp/session/section/page ordering and
per-chapter quota. Its diagnostic identifies this route as
`complete_project_statistics` and marks its database scan bounded. The other
assessment and evidence rules are unchanged.

Directory search scores the complete metadata matches with its original global
weights, preserves the full ownership chain, groups pages into chapters and
sections, and only then paginates. An unrelated project's matching pages cannot
consume the requested project's result slots.

The principal retrieval work for an eligible fixed project is bounded by its
page count, summary bytes and query terms. B-tree point lookups still depend on
database size and storage/cache behavior. This is not a universal constant-time
claim. Large active projects still use the original full-history route and may
grow more expensive as their own history increases.

## Migration, writes and older connections

Opening an older archive performs one atomic statistics backfill. This is an
archive-size-dependent migration and must be measured separately from recall.
The migration does not increment the source revision or invalidate unchanged
cached responses. An interruption rolls back the new derived tables and leaves
sources and prior evidence intact. Concurrent openers recheck under the SQLite
write lock and do not repeat an already completed backfill.

Current ingestion, same-ID source replacement, chapter relinking/renaming,
session deletion and project deletion update the statistics in the same
transaction as the original indexes. The next revision marker certifies that
both sets changed together. The additional tokenization, summaries and aggregate
updates consume write time and disk space; query measurements must not hide
those costs.

An already-open older lexical-aware writer retains its historical behavior.
A revision trigger atomically marks the new statistics `stale` when that writer
does not provide the matching marker. Existing readers then use the original
FTS route. A current opener or writer rebuilds the statistics before using or
updating them. Existing lexical compatibility guards still reject writers that
cannot maintain the original token semantics.

The implementation does not certify arbitrary manual database edits that skip
the archive's revision/index protocol. This is the same source/cache contract
as the existing API.

## Verification boundary

`tests/test_bm25_statistics.py` compares unrounded ranks and tie order directly
with SQLite's real `bm25()`, checks both tokenizers' corpus/term statistics with
FTS5 vocabulary tables, and compares complete recall/directory responses with
the original path. It also exercises replacement, rename, relinking, deletion,
transaction rollback, migration rollback, cross-connection snapshots, old-writer
invalidation, scope/byte limits and a reduced-SQL-length fallback.

These checks establish specific compatibility properties. Large-scale latency,
resource costs and generalization require separately recorded experiments on
the integrated source. Historical performance measurements do not transfer
automatically to this implementation.
