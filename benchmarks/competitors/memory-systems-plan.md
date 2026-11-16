# Supplied-page memory systems protocol

Protocol fixed on 2026-11-16, before executing this matrix or inspecting its
quality scores. This extends the retained engineering component workload; it
does not replace or edit any frozen evaluator, dataset, result, or acceptance
threshold.

## Inputs and scoring

- Use the unchanged `engineering_workflow.workload()` with 80 questions,
  chronological visibility, source replacement and project isolation.
- Export the same complete original pages with
  `engineering_components.export_documents()`. No answer labels, expected
  policies, case categories, or future documents enter an adapter.
- Send each original question unchanged. Retain native candidate ordering and
  take at most five candidates from the requested project. Do not introduce
  query expansion, handcrafted keywords, answer-dependent filtering, or a
  replacement ranker.
- Reuse the unchanged `common_pack()` at both 1200 and 2400 characters and the
  unchanged source-grounded `score()`. Oversized whole blocks are skipped; no
  native excerpts are mixed into this track. Native Book excerpts are a separate
  evaluation.
- Retain full native responses, native IDs, source mappings, every packed
  context, failures and all eight missing-evidence questions. A failed or
  unavailable backend is not scored as an empty successful response.
- Three repetitions measure stability and timing, not independent quality
  cases. No tuning follows inspection of this workload's scores.

## Fixed implementations and modes

| Backend | Fixed executed interface and configuration | What this measures |
|---|---|---|
| Book | Current frozen source; `recall`, project, limit 5, 100000-character native allowance, result cache off | Native candidate selection with shared whole-block packing |
| billion-context | Existing round-2 immutable source lock and unchanged `BillionKernel.search` | Actual supplied-page search kernel, not the full proxy product |
| claude-mem | Existing round-2 immutable source/Bun lock and unchanged `ClaudeMemFTS.search`; native `SessionSearch.searchObservations`, relevance order | Original pages supplied as raw observations with empty generated semantic fields; no observer, summary generation or complete product workflow |
| Basic Memory 1.0.0 | Official `SearchReader` + `SQLiteFts`, explicit `SearchRetrievalMode.FTS`, `ProjectScope.single`; upstream query preparation and relaxed-fallback eligibility; original pages indexed as entity rows using upstream schema and accepted-note indexing helpers | Native text search component; not the released product's default hybrid/semantic workflow |
| Chroma 1.5.9 | Native local collection, original page body as document, project metadata filter, `query_texts`, 5 results; official ONNX MiniLM embedding implementation and backend default metric | Local vector retrieval infrastructure, not a complete memory product |
| LangGraph checkpoint 4.3.2 | Actual `InMemoryStore(index={dims:384, fields:['text'], embed:...})`, per-project namespace, native `search(query, limit=5)`; real MiniLM embeddings | Explicitly configured semantic memory-store component; not the unindexed default or a persistent store |
| Mem0 2.2.1 | Actual `Memory.add` with `infer=False`, original text messages and source-mapping metadata; native local vector store and `search(query, filters={user_id:project}, top_k=5)`; shared real MiniLM through the official LangChain embedding adapter | Raw-memory retrieval component; no default LLM fact extraction, graph memory or reranker |

The exact Mem0 vector-store choice is Chroma's local persistent provider. Its
unused Ollama client points to `http://127.0.0.1:9`; no API key, model server,
LLM response, or mock embedding is supplied. Any attempted inference is a
failure, not a fallback. Preserve the native search threshold and rerank default.

Basic Memory's explicit text-mode preparation and relaxed eligibility are
determined by its pinned official helper, before looking at results. The harness
does not force a fallback or switch to a different mode after a low score.

Chroma, LangGraph and Mem0 share the **same real embedding model**. Similar or
identical rankings are correlated evidence of that shared model, not three
independent demonstrations of model quality. Book and billion retain additional
native indexed metadata. Common original text does not mean identical features
or equivalent complete products.

Official MCP memory `search_nodes` is literal substring lookup. If exercised,
it belongs in a separate archive/API compatibility report, not this ranked
retrieval matrix. A natural-language question's zero substring matches cannot
establish that another complete memory product is better.

## Integrity, environment and timing

Use a separate Python 3.12 dependency environment. The complete dependency lock,
official distribution hashes, upstream source locks, executed package-file
hashes, runtime/evaluator hashes and actual settings are retained. Download the
official Chroma ONNX archive and verify its published implementation's SHA-256
`913d7300ceae3b2dbc2c50d1de4baacab4be7b9380491c27fab7418616a16ec3`.
Verify the extracted files against the archive before model use.

Workers receive an allowlisted environment with isolated application config,
cache and database paths, telemetry disabled, and no provider credentials.
Only public dependency/model preparation may access the network. Measured
Python workers reject network connections after preparation. Never read personal
archives or use a paid service.

Record dependency/model preparation, process startup, indexing/embedding,
native search (including real query embedding where applicable), process
roundtrip and common in-memory packing separately. Model load and first-query
costs are visible. Cross-process versus in-process measurements do not imply a
whole-product speed ratio. Model weights and derived indexes are not original
evidence or returned context.

The small adapter contracts verify API execution, original text, identity,
project filtering and failure handling. The final quality run waits for the
parent's runtime freeze. Raw logs and partial failures survive unsuccessful
runs; later attempts use new directories.
