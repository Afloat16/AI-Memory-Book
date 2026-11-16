# Open-source memory systems: scope, configuration and evidence

Official sources were checked on **2026-11-16 (Asia/Shanghai)**. This comparison
covers **18 external project families**, including two retrieval/store building
blocks. It separates the executed supplied-page experiment from documentation
about complete products. ReMe, OpenViking, Hindsight and doobidoo's MCP Memory
Service add four families to the original review. A component score is not a
score for its parent product's default end-to-end workflow, and a reviewed
family is not automatically an experimentally ranked backend.

The [project-navigation source review](v0.7.0-open-source-research.md) records the
new commit pins, directory/source interfaces, licensing details and adapter
boundaries. ReMe's native file/BM25 adapter is prepared; its real hosted smoke and
scored run are still pending. No new numerical result is claimed for it here.

## What the shared experiment measures

The retained [registered protocol](../benchmarks/competitors/memory-systems-plan.md) uses
the existing 80-question engineering workload without changing questions,
evidence labels or scoring. Every backend receives the same visible original
page bodies and a project boundary, with at most five native candidates.
The same whole-block packer applies 1200- and 2400-character budgets, including
citations. Book's native excerpt results are a separate track.

Supplying an exact project boundary to every backend tests retrieval within that
boundary. It does not test whether a product discovers the intended project,
rejects an ambiguous request, or keeps a later page/source read inside the
selected book. Those behaviors require a separate native navigation track;
adapter-provided selection must not be credited as a product's own guard.

The measured modes are Book, billion-context's actual search kernel,
claude-mem's supplied-observation SQLite/FTS component, Basic Memory's explicit
text component, Chroma's local vector collection, an explicitly indexed
LangGraph store, and Mem0's `infer=False` raw-memory path. The dependency lock,
source/model hashes, full native responses, failed attempts and effective
configuration accompany the results. No missing backend receives an invented
zero score.

Chroma, LangGraph and Mem0 use the same real local MiniLM embedding model.
Their results are correlated evidence of that model and their configured
retrieval interfaces, not three independent model evaluations. Mem0's tested
path omits its normal fact-extraction LLM. Basic Memory's text path omits its
semantic/hybrid stage. claude-mem receives original pages as observations,
without running its observer. These choices are fixed before scoring.

## Project families and engineering roles

The links below identify the official source snapshots used for the feature
review. Tested package versions and source locks are specified separately in
the protocol; a current main-branch README does not establish the identity of
an older or newer installed release.

| Project family | Memory representation and retrieval | Local/model requirements | Source and scope relevant to engineering |
|---|---|---|---|
| [billion-context](https://github.com/ranxianglei/billion-context/tree/9674cfafbc78c50245ae0d887483d3d6ce880c15) | Proxy/client context management, reversible compression and searchable blocks | Full workflow can involve model-directed compression; the pinned search kernel runs locally | Stored block references and project filtering; the experiment covers the kernel, not proxy routing or decompression |
| [Mem0 / its OpenMemory tools][mem0] | Application memory, model-extracted facts and an explicit raw-memory ingestion mode | Configurable LLM, embeddings and vector stores; local providers are possible | User/agent/run and metadata filters; IDs and memory history; exact original-conversation offsets were not verified |
| [Letta / Letta Code][letta] | Stateful agents, editable memory blocks and Git-backed MemFS | Local or cloud backend; the agent uses an LLM; MemFS need not have a vector index | Git history, transcripts and message/file search; per-agent and shared memory |
| [Graphiti][graphiti] | Episodes, entities, temporal relationships and graph retrieval | Graph backend plus extraction/embedding models, with configurable providers | Raw episodes, source descriptions and valid times are retained; `group_id` scopes graph data |
| [MemOS][memos] | MemCubes and service/local memory paths, including text, tools and policies | REST quickstart uses graph/vector services; the local plugin offers SQLite/FTS5 and local embeddings | Cube ownership and scope; local bundle import preserves relevant ownership/profile information |
| [Memori][memori] | Captured conversation/trace records enriched into facts, attributes and relationships | Cloud or bring-your-own database; enrichment includes model processing | Entity/process/session attribution and stored conversation messages; database ownership alone does not establish a fully offline pipeline |
| [Cognee][cognee] | Documents, sessions and code transformed into chunks, graphs and vectors | A local GLiNER/embedding path works without an LLM API key; some other capabilities need models or separately licensed extensions | Dataset boundaries and document/chunk provenance; COGX supports memory migration and export |
| [claude-mem][claude] | Activity hooks, model-produced observations/summaries and progressive retrieval | Local Node/Bun worker and SQLite/FTS5; optional Chroma; observer model/provider | Observation/session/project/date/type identifiers and detailed reads; JSON import/export is documented |
| [memvid][memvid] | Immutable content frames and indexes in a portable `.mv2` file | Local lexical BM25 and optional ONNX vector search; API embeddings are optional | Frame contents, timestamps, checksums, URIs and tags; project tags were not independently verified as an access-control boundary |
| [Official MCP memory server][mcp] | Explicit entities, observation strings and relations in a JSONL graph | Node/stdio or container; the server itself does not require an embedding model | `open_nodes` and `read_graph` retrieve stored strings; separate files/instances can separate projects; `search_nodes` is literal substring lookup |
| [LangGraph store][langgraph] | Application-defined namespace/key/JSON values, separate from thread checkpoints | In-memory and persistent implementations; semantic search requires an explicit embedding index | Tuple namespaces, keys and timestamps; an application can preserve its own source references in values |
| [LongMemory, formerly Cavira OpenMemory][longmemory] | Project memory, immutable provenance and temporal facts | TypeScript engine with memory/SQLite backends; configurable real embedding providers and a documented synthetic fallback | Rich scope/provenance and strict/historical modes are documented; their correctness was not independently measured here |
| [Basic Memory][basic] | Markdown notes, observations and links, indexed for text/semantic retrieval | Local SQLite or server storage; the tested 1.0.0 release enables a semantic path by default | Original notes, permalinks, matched chunks and project scope; explicit FTS component results do not represent its default full pipeline |
| [Chroma][chroma] | Documents, IDs, metadata and vectors | Local client/persistence or server; default text embedding downloads a local MiniLM model | ID-based document reads, metadata filtering and collection/tenant/database boundaries; it does not supply an application-specific conversation policy |
| [ReMe][reme] | Local workspace files, Markdown/frontmatter, wikilinks, native BM25 and optional vector retrieval | Python 3.11+; default embeddings are off and basic file/BM25/link operations need no LLM key; memory evolution uses a model | Search exposes paths and line ranges for read/traversal; native local filters support exact paths and metadata. Markdown chunks may be rendered rather than byte-identical to the source |
| [OpenViking][openviking] | A `viking://` filesystem for resources, memories and skills; directory abstracts/overviews guide retrieval before full detail | Self-hosted service with model configuration; documented setup uses embedding and visual/language models, including local-provider options | Filesystem-style navigation and original files; documented account/user isolation and opt-in resource ACLs. These are broader service capabilities than a caller-supplied project filter |
| [Hindsight][hindsight] | Extracted facts, evidence-backed observations, mental models and generated pages in a wiki-like folder tree | Supported database deployment plus extraction/synthesis models; reading an existing mental model itself does not require an LLM call | Memory-bank boundaries, provenance and supporting evidence; pages can be searched and exported/projected as Markdown. Generated pages are a derived view, not the original transcript |
| [MCP Memory Service by doobidoo][mcp-service] | Memory records, semantic/BM25 search, document ingestion, entity relationships and capture integrations | Local SQLite/ONNX path plus MCP/REST/CLI; the pinned README requires the `[sqlite]` extra for real ONNX embeddings and otherwise warns of a hash-embedding fallback | Tags and store partitions scope retrieval; optional summaries validate source references. Its bootstrap profiles specifically are not project-isolated; that limit must not be generalized to every API |

Directory navigation is already present in several systems. ReMe provides file
and link traversal; OpenViking offers layered directory retrieval; Hindsight
provides page trees. Basic Memory's pinned 1.0.0 implementation includes
[`bm_project` project discovery][basic-projects], [`bm_list` directory listing
with a required project][basic-listing], and [ambiguous multi-project path
refusal][basic-routing]. It must not be described as lacking project selection
or directory guards.

Book's engineering role is to make original conversations navigable as project
books: choose an exact project identity, inspect its task/chapter directory,
read a page, and follow its source coordinates back to the original session and
turn. The meaningful boundary is preserved through retrieval and subsequent
page/source navigation, with exact project checks rather than inference from a
similar display name. Bounded context, code-identifier aliases and archive
maintenance support that workflow without a default extraction or embedding
model. These combined choices should be assessed through source validation,
scope behavior and evidence completeness, not a claim that local operation or
folders are unique to Book.

A project namespace/filter prevents accidental mixing when correctly applied;
it is not, by itself, authentication or multi-user authorization. This distinction
also applies to evaluator-supplied scope mappings. A team needing graph
reasoning, editable agent state, authored Markdown knowledge, automatic knowledge
synthesis or a vector-store API may prefer a different architecture.

## What has and has not been tested

| Family | Status and experiment scope | Outside this experiment |
|---|---|---|
| billion-context | Pinned supplied-page search kernel | Proxy operation, model-directed compression and follow-up decompression |
| claude-mem | Pinned native SQLite observation search over supplied pages | Observer extraction, generated summaries, Chroma and complete capture workflow |
| Basic Memory | Pinned native text search and official query/fallback handling | Default semantic/hybrid pipeline and note-authoring workflow |
| Mem0 | Pinned raw-memory `infer=False`, real local embedding and native search | Fact extraction, graph memory, reranking and managed-platform features |
| Chroma | Pinned local vector collection and project metadata filter | A complete memory application or all products built on Chroma |
| LangGraph | Pinned indexed `InMemoryStore` with the same real embedding model | Durable-store behavior, checkpoint recovery and an agent's extraction policy |
| Letta / Graphiti / MemOS / Memori / Cognee / memvid / LongMemory | Official-source feature review only | Numerical quality, speed, resource use and production correctness in this workload |
| ReMe | Adapter prepared from pinned upstream source; real hosted smoke and scored run pending | Automatic memory evolution, Markdown authoring/watchers, embeddings, link expansion and the complete client workflow |
| OpenViking / Hindsight / doobidoo MCP Memory Service | Official-source feature review only | Numerical quality, speed, resource use and production correctness in this workload |
| Official MCP memory | Official API/source review; a separate native graph/archive capability track is eligible | Generic ranked natural-language retrieval; an empty literal-string search is not a semantic-search failure score |

All seven registered backends completed the [retained matrix](../benchmarks/reports/v0.6.0-engineering/hosted/memory-systems/report.json).
The [independent audit](../benchmarks/reports/v0.6.0-engineering/audit.json) recomputes every score and packed context and verifies all 320 complete-response pairs with the unchanged two-component harness.
At 2400 characters, Book has 72/72 complete-evidence cases; billion, claude-mem FTS and Basic Memory FTS each have 64/72; the shared-MiniLM configurations each have 47/72.
At 1200, Book has 68/72 but retains four stale-only training-decision failures that each tested lexical competitor avoids.
All seven return related context for all eight missing-evidence cases in both budgets.

External indexes are rebuilt from the visible page snapshot at each checkpoint;
this does not validate their native update/delete lifecycle. Source-validation
checks authenticate the adapters' mappings to common original pages, not identical
native citation features across all products. The first Chroma configuration-JSON
integration failure occurred before quality scoring and is retained separately.
Unmeasured projects are not ranked below Book. Published scores from different
datasets, prompts, budgets or managed services are not copied into these tables.

The prepared ReMe mode uses the official plain-text file chunker and local BM25
index, retaining one complete original page per native chunk and rejecting a
split or rewritten page. It passes an exact set of registered project paths to
the native filter **before** top-k selection and preserves the native order and
payload. That mapping does not create a native project-selection guard or an
access-control feature. ReMe's default Markdown watcher and parser have different
input semantics and are not silently represented by this component mode. Its
[source, dependency and API specification](v0.7.0-open-source-research.md#additional-real-adapter-reme-native-bm25)
remains separate from any eventual scores.

The official MCP server's `search_nodes` performs whole-query, case-insensitive
substring lookup in stored order. `open_nodes` and `read_graph` can test real
archive and graph reads. Separate graph files/instances can provide a deployment
boundary, but a custom adapter ranker or a post-filtered global search would not
measure the server's native ranked retrieval.

## Identity, naming and license notes

- Mem0's old OpenMemory MCP/dashboard is [archived][openmemory-archive]. Its
  current [OpenMemory repository][openmemory] concerns coding-agent session
  portability. Those tools count as one project family here. Cavira's
  LongMemory is a different project.
- Letta, MemGPT and Letta Code are not counted as three competing systems.
  Graphiti refers to the open-source graph library, not the entire hosted Zep
  service. Chroma and LangGraph are identified as building blocks throughout.
- The fixed Basic Memory release declares AGPL-3.0-or-later. LangGraph is MIT.
  Most other reviewed cores declare Apache-2.0, but the exact repository
  license and any component/asset exclusions must be checked for reuse.
- ReMe and doobidoo's MCP Memory Service declare Apache-2.0; Hindsight declares
  MIT. OpenViking's pinned main LICENSE is AGPLv3, with different licenses for
  some components. Its README also states additional rewriting/translation
  restrictions. Record both sources instead of labeling the whole repository
  Apache-2.0 or assuming all reviewed projects have the same reuse terms.
- [MCP's repository license][mcp-license] describes a MIT-to-Apache-2.0 code
  transition and separately licensed documentation; its memory README retains
  an MIT label. [Memori's LICENSE][memori-license] and README declare
  Apache-2.0, while its GitHub license metadata returned `NOASSERTION`.
  These observations are retained rather than reduced to a blanket license
  claim. The pinned billion-context binding records its additional attribution
  wording; Letta branding and some Cognee extensions have separate terms.

## Official supporting interfaces

- [Letta MemFS](https://docs.letta.com/concepts/memfs)
- [Graphiti original episode definition](https://github.com/getzep/graphiti/blob/869c1b279e01a2767a464581e1cb657ce0e39271/graphiti_core/nodes.py)
- [MemOS local plugin](https://github.com/MemTensor/MemOS/blob/3a16e5fe3048a209f722806f4123fa2e533588fd/apps/memos-local-plugin/README.md)
- [Memori BYODB](https://memorilabs.ai/docs/memori-byodb/) and [augmentation](https://memorilabs.ai/docs/memori-byodb/concepts/advanced-augmentation/)
- [Cognee architecture](https://docs.cognee.ai/core-concepts/architecture) and [memory migration](https://docs.cognee.ai/examples/migrate-memory-systems)
- [claude-mem import/export](https://github.com/thedotmack/claude-mem/blob/5cc2fb16aa6d36b47d777d58dfd6456065510f9f/docs/public/usage/export-import.mdx)
- [Basic Memory 1.0.0 package](https://github.com/basicmachines-co/basic-memory/blob/c9bd187b83baba549d5cd16bacc180f8023d51c8/pyproject.toml) and [SQLite search implementation](https://github.com/basicmachines-co/basic-memory/blob/c9bd187b83baba549d5cd16bacc180f8023d51c8/src/basic_memory/repository/sqlite_search_repository.py)
- [LangGraph store reference](https://docs.langchain.com/oss/python/langgraph/stores)
- [Chroma embedding functions](https://docs.trychroma.com/docs/embeddings/embedding-functions)
- [LongMemory embedding configuration](https://github.com/CaviraOSS/LongMemory/blob/aec98ced33a7586a2fcd198a04bc38b5590750c4/docs/embeddings.md)
- [ReMe native filtering and BM25 source](https://github.com/agentscope-ai/ReMe/blob/b13034ba2ff7339bb03df4fa4ee130b47a731c6c/reme/components/file_store/local_file_store.py) and [default configuration](https://github.com/agentscope-ai/ReMe/blob/b13034ba2ff7339bb03df4fa4ee130b47a731c6c/reme/config/default.yaml)
- [OpenViking context layers](https://docs.openviking.ai/en/concepts/03-context-layers) and [account/user model](https://docs.openviking.ai/en/concepts/11-multi-tenant)
- [Hindsight pages](https://hindsight.vectorize.io/developer/pages) and [page-tree/search API](https://hindsight.vectorize.io/developer/api/knowledge-pages)
- [MCP Memory Service configuration and feature boundaries][mcp-service]

[mem0]: https://github.com/mem0ai/mem0/blob/f1791daa86d469249c9b002f62644d58a1eb96a0/README.md
[openmemory]: https://github.com/mem0ai/openmemory/blob/2df78cc48e5f688a771fee5b39899325accc2450/README.md
[openmemory-archive]: https://github.com/mem0ai/openmemory/blob/2df78cc48e5f688a771fee5b39899325accc2450/openmemory-archive/README.md
[letta]: https://github.com/letta-ai/letta-code/blob/eadef1c6c3594d1bf81517efd4b68fce54644ad4/README.md
[graphiti]: https://github.com/getzep/graphiti/blob/869c1b279e01a2767a464581e1cb657ce0e39271/README.md
[memos]: https://github.com/MemTensor/MemOS/blob/3a16e5fe3048a209f722806f4123fa2e533588fd/README.md
[memori]: https://github.com/MemoriLabs/Memori/blob/574b1ea3e876f100ef82c37817d603eb7e258e59/README.md
[memori-license]: https://github.com/MemoriLabs/Memori/blob/574b1ea3e876f100ef82c37817d603eb7e258e59/LICENSE
[cognee]: https://github.com/topoteretes/cognee/blob/4053f6cc5536757f26a3665eed95c50088e6dc0b/README.md
[claude]: https://github.com/thedotmack/claude-mem/blob/5cc2fb16aa6d36b47d777d58dfd6456065510f9f/README.md
[memvid]: https://github.com/memvid/memvid/blob/e6bd9f7b9c38cd8d5370fa0fc936ac1dcd751813/README.md
[mcp]: https://github.com/modelcontextprotocol/servers/blob/e1dc4b18dbb948921da37f3d4224a628730b43b0/src/memory/README.md
[mcp-license]: https://github.com/modelcontextprotocol/servers/blob/e1dc4b18dbb948921da37f3d4224a628730b43b0/LICENSE
[langgraph]: https://github.com/langchain-ai/langgraph/blob/41fb001df9313d5edb5aaac32851d894b1750a1b/README.md
[longmemory]: https://github.com/CaviraOSS/LongMemory/blob/aec98ced33a7586a2fcd198a04bc38b5590750c4/README.md
[basic]: https://github.com/basicmachines-co/basic-memory/blob/8a9e3ea2346c628876abc39b0d804dafb8e4b64c/README.md
[chroma]: https://github.com/chroma-core/chroma/blob/1a3ac2c7c623adbd03ed2508dc27b98cdf26016d/README.md
[reme]: https://github.com/agentscope-ai/ReMe/blob/b13034ba2ff7339bb03df4fa4ee130b47a731c6c/README.md
[openviking]: https://github.com/volcengine/OpenViking/blob/f9bf90b398df1c0ee6732d257dcdba793f02e2b5/README.md
[hindsight]: https://github.com/vectorize-io/hindsight/blob/5318be8ea572aa00ceae636c71c1d8d334f805b6/README.md
[mcp-service]: https://github.com/doobidoo/mcp-memory-service/blob/f8bbc654326627a6dc2fad8d15f2b705adef5259/README.md
[basic-projects]: https://github.com/basicmachines-co/basic-memory/blob/c9bd187b83baba549d5cd16bacc180f8023d51c8/src/basic_memory/mcp/tools/projects.py
[basic-listing]: https://github.com/basicmachines-co/basic-memory/blob/c9bd187b83baba549d5cd16bacc180f8023d51c8/src/basic_memory/mcp/tools/listing.py
[basic-routing]: https://github.com/basicmachines-co/basic-memory/blob/c9bd187b83baba549d5cd16bacc180f8023d51c8/src/basic_memory/mcp/project_context.py
