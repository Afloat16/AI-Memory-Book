# LanceDB and Whoosh: preregistered component extension

Protocol: `engineering-v012-search-components-v1`, registered 2026-11-18 before
the first engineering quality execution by these adapters. API smoke uses only
arbitrary marker pages and does not select parameters using benchmark results.

## Scope and exact configurations

This evaluates actual upstream **retrieval components** on the existing authored
engineering development workload. LanceDB is an embedded database with native
full-text search; Whoosh is a text-search library. Neither row represents a full
AI-memory product, generated-answer accuracy, coding productivity or an unseen
evaluation. Previously inspected questions remain development/regression data.

| Component | Pinned version | Registered API and configuration |
| --- | --- | --- |
| LanceDB native FTS | `lancedb==0.41.0` | Shared local table; `table.create_index('text', config=FTS())`; native FTS defaults and default OR query behavior; exact project equality with `prefilter=True` before `limit(5)` |
| Whoosh BM25F with OR parsing | `Whoosh==2.7.4` | Shared native index; stored `TEXT` with default StandardAnalyzer; native default BM25F (`B=0.75`, `K1=1.2`); `QueryParser('text', group=OrGroup)`; exact native `Term('project', project)` filter before `limit=5` |

Whoosh's OR group is an **explicit nondefault configuration** for natural
questions. Its QueryParser defaults to AND. There is no per-query configuration
selection, OR coverage bonus, stemming change, rank rescaling, query rewrite or
adapter threshold. LanceDB's unmodified FTS configuration object is saved with
each index setup. Both index only the complete original text as retrieval text;
project ID is an exact filter, while page ID, title and creation time are stored
unchanged. Titles are not a second scored text field.

Primary references:

- [LanceDB source](https://github.com/lancedb/lancedb) and
  [FTS API documentation](https://docs.lancedb.com/search/full-text-search).
  The actual installed 0.41.0 package bytes and configuration are authoritative
  for this replay; current online documentation can change.
- [Whoosh source](https://github.com/mchaput/whoosh),
  [QueryParser and OrGroup](https://whoosh.readthedocs.io/en/latest/parsing.html),
  and [BM25F and native filters](https://whoosh.readthedocs.io/en/latest/searching.html).

## Fixed comparison boundary

Import the unchanged `engineering_workflow.workload`,
`engineering_components.export_documents`, `engineering_components.common_pack`
and `engineering_workflow.score`. The baseline Book runtime at immutable commit
`78cc906d81818a16884de7de2e613e5a56346f93` only ingests and materializes original
pages; no Book recall is scored or timed inside this extension. Its loaded
native backend and complete tracked runtime are authenticated before and after
execution against the baseline Git objects.

All **80 original questions**, **six chronological checkpoints**, **eight
projects**, **1200/2400 character budgets**, **five native candidates** and
**three repetitions** are fixed. The complete matrix is **480 actual native
search calls** (80 × 2 components × 3 repeats), **160 query/component pairs** and
**320 packed responses** (80 × 2 components × 2 budgets). Repeats are stability
observations, not independent quality examples. Eight missing-evidence queries
are retained; nonempty context does not by itself measure a generated answer or
an abstention error.

At each checkpoint, each upstream index is rebuilt from exactly the currently
visible pages, after source replacements. Future or replaced source records
must be absent. This measures ranking on supplied current snapshots, not either
product's native update/delete behavior. Native filtering occurs before top-k;
foreign, duplicate, unmapped or altered returned pages fail integrity checks.
No invalid result may be silently removed and no omitted result may be refilled.

Every original query is passed verbatim. Preserve native result order, scores,
all returned stored fields, empty native results and the explicit original
request. Verify every returned complete body, project, identity, title and time
against the supplied page before applying the unchanged common whole-block
packer. It skips whole blocks that do not fit and never truncates or adds a
candidate. Gold labels are available only to the controller's scorer, never to
the isolated upstream worker.

## Source, dependency and execution evidence

The separate lock records the exact transitive dependency closure of both
installed distributions with no extras: **17 distributions and 3015 installed
files** in the prepared environment. Every file listed in each installed RECORD
is hashed, including RECORD itself and entries without an upstream digest.
Every declared SHA-256 and byte size must match; there are no exceptions.
The actual resolved dependency versions must satisfy all active requirements.
The lock describes this installed environment, including platform-specific
native files; it is not an independently reproducible native build claim.

Before and after every checkpoint worker, verify the entire installed file and
RECORD inventory against the frozen lock. Record full native-library hashes.
Use the isolated upstream environment with an allowlist of platform variables,
an empty separate pycache prefix and bytecode writing disabled. No model or
remote service is configured. A Python socket tripwire rejects INET attempts;
it is not an OS network sandbox and does not establish interception of Rust
syscalls. Setup/search/transport timings are diagnostic only; this is not a
registered speed comparison.

Freeze the adapter, harness, lock, protocol and complete evaluator dependency
closure in Git before quality execution. The controller records the actual
loaded evaluator paths, frozen commit and byte hashes before/after the run.
It writes the dataset and initial binding before setups, and flushes a journal
before/after every native query. Save all full responses, original source
bundles, native scores, packed contexts, independently recomputable scores,
metadata, stderr logs and exceptions. Use a fresh output directory for each
attempt; failures are retained and never overwritten. A failed component stays
failed for the remainder of that attempt and cannot enter a completed table.

The offline audit requires the complete registered Cartesian product, original
query/scope/checkpoint/category labels, ordered repetition inventory, exact
source bundles, initial/final source bindings and complete package identity.
It independently reconstructs native mappings, packing, per-case scores and
overall/per-category summaries. Comparisons to Book or earlier component rows
require matching dataset and all six supplied-page digests, not just matching
aggregate denominators. Small-budget ties or losses must be disclosed.

## API smoke and execution

The smoke contains twelve marker pages: singleton scopes, a slash-prefix scope,
a quoted SQL-like literal scope and nine matching pages in a distracting scope.
It checks exact scope before the five-result cap and an absent project. These
are API/source/scope checks, not scored engineering questions. Any failed setup
or native API error remains in its own original attempt directory.

`api-smoke-1` completed all ten native marker searches, but review found that
its initial harness closure still named the earlier extension files. It is
retained as an API preparation observation, not an exact-source quality proof.
The final harness explicitly binds its own adapter, harness, protocol and new
lock; a regression check protects that inventory. No engineering quality call
occurred before this correction. Later smoke records use an explicit
working-tree-only binding instead of attributing uncommitted files to Git HEAD.

After the protocol commit, use a main interpreter that can load the immutable
baseline native extension, and the prepared separate upstream interpreter:

```sh
PYTHONPATH=/absolute/path/to/immutable-v011/src:. \
MEMORY_BOOK_TEXT_BACKEND=native \
python -B -m benchmarks.v012_search_components \
  --backend-python /absolute/path/to/external-v012/bin/python \
  --output /absolute/path/to/new-quality-attempt
python -B -m benchmarks.v012_search_components --audit \
  --output /absolute/path/to/new-quality-attempt
```

Add `--self-test` with a separate new output directory for the marker-only API
smoke. A smoke pass alone does not establish any quality result. The current
source must still match the committed evaluator closure when the audit runs.
