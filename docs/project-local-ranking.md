# Project-local ranking and explicit evidence requirements

This is an unreleased development option. The compatible default remains
`ranking_scope="global"`. The option changes the corpus used for BM25 statistics;
it must be evaluated as a retrieval-policy change, not an exact-score optimization.

## Fixed old projects in a growing archive

Filtering a global FTS query to a project does not make its BM25 statistics local.
SQLite's document frequency and average document length refer to the FTS table.
The optional project mode copies one complete, bounded project's existing rows
into a private in-memory SQLite index and runs the same retrieval and evidence
assembly code there. It does not resegment or rewrite the original archive.

```python
from memory_book import MemoryBook

with MemoryBook("memory.db", ranking_scope="project") as book:
    result = book.recall("current production retry_limit", project="engine")
    print(result["context"])
    print(result["ranking_scope"])
```

CLI and persistent MCP examples:

```bash
memory-book --db memory.db --ranking-scope project recall \
  "current production retry_limit" --project engine --json

memory-book --db memory.db --ranking-scope project locate \
  "Production limits" --project engine

memory-book --db memory.db --ranking-scope project mcp --project engine
```

The CLI also accepts `MEMORY_BOOK_RANKING_SCOPE=project`. Direct Python and
`create_server(..., ranking_scope="project")` use explicit configuration. The
browser reader and background capture configuration retain their existing
global ranking behavior. A persistent MCP process can reuse an index; a fresh
one-shot CLI command pays its preparation cost again.

### Admission, invalidation and fallback

| Constraint | Behavior |
|---|---|
| An explicit project ID | Required for local statistics; names are not scope keys |
| At most 256 project pages | Larger scopes use the original global retrieval path |
| At most 8,192 copied rows and 4 MiB of source/index-column payload per project | Oversized scopes fall back without dropping or truncating their original evidence |
| At most two retained projects, 8 MiB of admitted source/index-column payload | LRU eviction closes the old local connection |
| Other projects change | Recheck a bounded fingerprint; reuse an unchanged local index |
| This project's source, owner, chapter or index changes | Rebuild from a consistent read snapshot |
| Semantic mode, customized instances/connections or unsupported SQLite limits | Explicitly fall back to the compatible global route |

The byte limits describe admitted payload, **not total process RSS**. SQLite
indexes, result caches, token memoization and temporary serialization need
additional memory. The current optimization is for small fixed projects; it
does not promise constant latency as a target project's own history grows.
Python runtimes without SQLite `getlimit` currently use the explicit fallback.

Every opted-in response includes `ranking_scope.requested`, `actual`,
`statistics`, `fallback_reason`, `index_cache_hit`, `fingerprint_checked` and
`preparation_ms`. Recall's total `latency_ms` includes preparation. Global-mode
responses preserve the prior payload. Original page IDs, project IDs, source
turns and coordinates are retained in either mode. Local BM25 can choose a
different order from global BM25, so compare evidence completeness, not only
speed. A read reflects one coherent snapshot; another connection's later
commit becomes visible on a subsequent call.

## A narrow gate for explicitly required fields

Related source text is not proof that a requested value is present. The optional
`required_fields` argument withholds context unless **every named field has a
complete supported declaration in the actual returned pages**:

```python
result = book.recall(
    "current production retry_limit lease_window",
    project="engine",
    required_fields=["retry_limit", "lease_window"],
)
print(result["evidence_gate"]["status"])  # supported or abstained
```

```bash
memory-book --db memory.db recall "current production retry_limit" \
  --project engine --require-field retry_limit --json
```

MCP's `recall_memory` accepts the same `required_fields` list. Its compact and
indexed responses preserve both the gate status and ranking-scope metadata.

This is a conservative syntactic contract for simple current declarations,
not a general answerability classifier or an authoritative state resolver:

- Require an explicit project and current intent; history/occurrence requests
  are not treated as current declarations.
- Preserve literal field identities and dotted namespaces. Query qualifiers
  must match the declared local scope; an unspecified environment is not guessed.
- Authenticate a complete source turn in the same read snapshot and check
  project/session ownership. Only complete, untruncated delivered pages support
  a field; a candidate outside the context cannot lend its evidence.
- Compare each field independently across overlapping field groups. Equal-time
  conflicting values and unclassified newer evidence prevent support.
- Accept only turns made entirely of simple declarations. Quotations,
  conditional examples, revocations, unknown surrounding prose and unsupported
  forms cause conservative abstention.

An abstention preserves candidate counts, reasons and withheld page addresses,
but clears the evidence context and its character/token counts. It does not
claim that no answer exists elsewhere in the archive. This narrow grammar can
reject answerable prose or small-budget results. Evaluate these false
abstentions alongside missing-evidence controls before enabling it in a workflow.
Normal recall remains unchanged when `required_fields` is omitted.

## Evaluation boundaries

The v0.14 development protocol separates timestamp age, growth of unrelated
similar projects, growth of the target, interleaved insertion, replacement and
deletion. It measures initial preparation, cold **result-cache** queries, warm
queries, directory-to-original-reading chains, and revalidation after foreign
writes. Cold result-cache timing does not mean a cold operating-system cache.

The new public-source holdout uses immutable release snapshots from four
official projects, fixed original spans and all three supported segmentation
modes. Neither this source-retrieval evaluation nor the synthetic scale matrix
measures coding-LLM task success. The final development report records actual
executed counts, absolute quality, regressions and all scope fallbacks.

Reference: [SQLite FTS5 BM25 documentation](https://www.sqlite.org/fts5.html#the_bm25_function).
