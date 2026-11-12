# Native competitor adapters

These optional benchmark adapters execute pinned upstream implementations.
They are not dependencies of AI-Memory-Book, and are not installed by its
normal installer. They never configure hooks, inspect a user's chat history,
or connect to an existing memory server.

See [the comparison protocol](../../docs/comparison-protocol.md) before using
their measurements in a claim.

## Implementations

| Adapter | Code actually executed | Runtime |
| --- | --- | --- |
| BillionKernel | billion-context's unchanged searchBlocks() and shipped default hybrid BM25 + fuzzy ranker | Node 24+ |
| AiMemoryNative, fts | ai-memory's official v3.4.5 executable; the /admin/search route used by its search CLI | Linux x86-64 |
| AiMemoryNative, hybrid | The same executable, native MCP memory_query, and its default local all-MiniLM-L6-v2 model | Linux x86-64; approximately 92 MB of model files |
| claude-mem FTS component | Unmodified upstream SessionStore / SessionSearch at 2cfed762, package 15.18.0 | Pinned Bun 1.3.13, Linux x86-64 |

The TypeScript adapter uses Node's syntax eraser. It does not translate or
reimplement ranking logic. The Python files provide transport, process
lifecycle, stable fixture IDs, and integrity checking.

The ai-memory adapter starts its own authenticated loopback service with an
empty temporary data directory and a minimal environment. It imports supplied
pages through the native write route. The hybrid mode explicitly configures
the shipped local provider and waits for a successful native embedding
backfill, so unavailable embeddings fail the run instead of becoming an
unreported lexical fallback. The server and temporary store are removed on
normal exit.

## Completed claude-mem component and native workflow

The separate `benchmarks.claude_mem_component_eval` runner has completed
1,015 queries × 3 repetitions over the same 1,339 supplied source pages.
See [its execution guide](../../docs/claude-mem-component-evaluation.md) and
[all actual results](../results/claude-mem-components-public.md). It executes
native SQLite FTS; it does not synthesize observer records with an LLM or
claim to measure Chroma, host injection or the complete claude-mem product.

The [Book/ai-memory workflow report](../RESULTS-full-workflow.md) separately
covers 42 native capture/consolidation sessions and 72 actual answers,
including every failed consolidation and its usage. Component and complete
workflow reports have different inputs and scope.

## Run

From a repository checkout with Python 3.10+ and, for billion-context, Node
24+:

    python -m benchmarks.competitors.billion \
      --input .artifacts/component-input.json \
      --cache .artifacts/competitors/billion-context \
      --output .artifacts/billion-native.json

    python -m benchmarks.competitors.ai_memory \
      --input .artifacts/component-input.json \
      --cache .artifacts/competitors/ai-memory \
      --retrieval hybrid \
      --output .artifacts/ai-memory-hybrid-native.json

Use --retrieval fts for the native CLI search mode. Add --offline once the
source, executable, and relevant model files have been downloaded. Pinned
hashes are always verified, including when files already exist in the cache.
Downloads and generated files belong under an ignored cache directory.

The low-level CLI saves native responses for inspection. It does not itself
score quality or impose a context budget. The scoring harness must use the
same source documents, candidate limit, assembly policy, and tokenizer for
every engine.

### Input bundle

An input JSON object contains a documents array and a queries array.
Each document has string fields id, project, title, and text. Optional source
metadata stays outside the foreign engine. Each query has id, query, and an
optional project.

Example:

    {
      "documents": [
        {
          "id": "page-1",
          "project": "atlas",
          "title": "Release process",
          "text": "Deployment runs release.sh and checks /health/live.",
          "source_refs": [
            {"project": "atlas", "session_id": "s1", "turn_index": 2}
          ]
        }
      ],
      "queries": [
        {"id": "q1", "query": "How is Atlas deployed?", "project": "atlas"}
      ]
    }

### Python API

    from pathlib import Path
    from benchmarks.competitors.billion import BillionKernel
    from benchmarks.competitors.ai_memory import AiMemoryNative

    with BillionKernel(documents, Path(".artifacts/competitors/billion-context")) as engine:
        result = engine.search(query, project=project, limit=5)
        # Native results use ref == the input document id.
        print(result["search_ms"], result["bridge_ms"])

    with AiMemoryNative(
        documents,
        Path(".artifacts/competitors/ai-memory"),
        retrieval="hybrid",
    ) as engine:
        result = engine.search(query, project=project, limit=5)
        # hit_ids is parallel to results. Native UUIDs are preserved.
        # None means a native hit is not one of the imported fixture pages.
        native_read = engine.read(result["hit_ids"][0])
        # Both modes can use this same store; no second import is required.
        lexical_result = engine.search_fts(query, project=project, limit=5)

For native MCP calls, native_text is the exact tool content text and
native_payload is the unmodified MCP result object. Decoded hits are also
provided for scoring. Do not sum duplicate representations of one payload.
Native reads must be counted when they are needed to obtain the evidence.
The low-level ai-memory CLI and current component evaluator fetch every
mapped top-k page once. Their native read totals describe this fixed policy,
including reads whose preview was already sufficient; they are not an
estimate of an adaptive agent's minimum required reads.

preview_chars controls billion-context's documented previewLength option.
ai-memory's native snippet format is unchanged: the shared signature accepts
that argument but does not impose an unsupported upstream option.

## Pins and attribution

The JSON lock files record immutable commits, release hashes, source URLs,
and model hashes. Downloaded upstream LICENSE files are preserved with the
cache.

The billion-context benchmark adapter uses
[billion-context](https://github.com/ranxianglei/billion-context) and its
[acp-kernel](https://github.com/ranxianglei/acp-kernel) search implementation.
Its license includes MIT terms **and an additional product-surface
attribution condition**; it is not described here as unmodified MIT.
AI-Memory-Book's production engine is independent of this benchmark adapter.

The ai-memory adapter executes
[ai-memory by Fabio Akita](https://github.com/akitaonrails/ai-memory), released
under MIT. Its optional local embedding model is
[all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2),
under Apache-2.0. Model hashes are taken from the pinned ai-memory source.
