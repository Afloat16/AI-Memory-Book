# AI-Memory-Book

**Browse engineering memory as project books, then verify the original turn.**

An exact project ID identifies a book. Tasks form chapters; sections and pages lead back to the original conversation. AI-Memory-Book preserves normalized source text so a coding agent can recover a decision, its constraints and its failed alternatives, even after switching sessions or clients.

[简体中文](README.zh-CN.md) · [Quick start](#quick-start) · [Read a project book](#read-a-project-book) · [2400-character evaluation](#2400-character-evaluation) · [18 project families](#open-source-comparison)

**v0.7.0 · MIT · Python 3.10+ · Local SQLite / FTS5 · Default context: 2400 characters**

## Keep similar projects in separate books

- **Choose by identity.** Display names can repeat. `route-kernel`, `route_kernel` and `Route-Kernel` are distinct project IDs; code-identifier aliases do not merge project identities. The reader shows the ID beside the display name.
- **Resolve scope before recalling.** In a multi-project archive, select an exact project or a known chapter ID. An omitted scope is refused; intentional cross-project recall uses `--all-projects` or `all_projects=true`. A single-book archive can resolve its only book automatically.
- **Carry the selected project into navigation.** Chapter, section and page reads accept a `project` guard and reject an ID belonging to another book. The reader carries that guard; API callers should pass it when following returned IDs.
- **Follow evidence to a complete original turn.** A page is a reading unit, not necessarily a complete answer. Direct turn reads support pagination independently of page splitting. Carry `source_hash` across reads so a replaced session causes a clear error instead of joining different source versions.

These checks prevent accidental mixing under the supplied project scope. They are not authentication or multi-user access control. [Navigation and source API details](docs/engineering-workflows.md#browse-one-project-book).

Try the [similar-project example](examples/similar-projects.json) from a source checkout after installation. Two books are both named **Routing Kernel** and reuse session `design-review`, task names and code symbols, but their contracts differ:

~~~bash
memory-book --db ./similar-projects.db import examples/similar-projects.json --format canonical
memory-book --db ./similar-projects.db projects
memory-book --db ./similar-projects.db index "routing policy" --project routing-prod
memory-book --db ./similar-projects.db recall "edge_policy relaxation_limit" --project routing-prod
memory-book --db ./similar-projects.db recall "edge_policy relaxation_limit" --project routing-eval
~~~

The synthetic `routing-prod` book records `edge_policy=bellman_ford` and `routing.relaxation_limit=128`; `routing-eval` records `edge_policy=reject_negative` and `routing.relaxation_limit=32`. Use the exact project IDs to keep those opposite policies separate. [Follow the directory through to complete original turns](docs/book-navigation.md).

## Quick start

You need **Python 3.10+ with SQLite FTS5**. The installer creates an isolated environment with MCP/client dependencies. Default capture and lexical retrieval need no embedding model, database server or memory-service API key.

**macOS / Linux**

~~~bash
curl -fsSLo install-memory-book.sh https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/v0.7.0/scripts/install.sh
bash install-memory-book.sh
~~~

**Windows PowerShell**

~~~powershell
Invoke-WebRequest https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/v0.7.0/scripts/install.py -OutFile install-memory-book.py
py -3 .\install-memory-book.py
~~~

**Connect a coding client**

~~~bash
memory-book setup --client claude-code --capture --background
memory-book doctor
~~~

Choose a supported [client profile](docs/integrations.md#supported-profiles), such as Claude Code, Codex or Gemini; repeat `--client` for multiple clients. `--capture` opts in to supported existing and future text transcripts, and `--background` starts the user capture service. Omit both for MCP configuration alone or a profile without native capture support. Restart the client after setup.

MCP tool invocation remains the host/model's choice. Use the full launcher path printed by the installer if the command is not on PATH. Existing archives and managed installations are covered by the [deployment and upgrade guide](docs/deployment.md).

## Read a project book

The [runnable example](examples/engineering-workflow.json) contains five synthetic sessions in four projects. Run from a source checkout with a new demo database:

~~~bash
memory-book --db ./demo-memory.db import examples/engineering-workflow.json --format canonical
memory-book --db ./demo-memory.db projects
memory-book --db ./demo-memory.db toc inference-demo
memory-book --db ./demo-memory.db index "KVCache" --project inference-demo
~~~

`toc` lists chapters. `index` searches titles, questions and task/session directory fields, returning section addresses and breadcrumbs without loading complete page bodies. Shared `task_id` values group a project's related sessions into a chapter; without a task ID, each session has its own chapter.

Use IDs actually returned by the directory:

~~~bash
memory-book --db ./demo-memory.db chapter CHAPTER_ID --project inference-demo
memory-book --db ./demo-memory.db section SECTION_ID --project inference-demo
memory-book --db ./demo-memory.db read PAGE_ID --project inference-demo
~~~

Follow the page's source reference to its original turn. In this example, turn index `1` is the second question-and-answer turn:

~~~bash
memory-book --db ./demo-memory.db turn inference-demo cache-configuration 1
~~~

A turn contains normalized original messages, including role labels. If `next_offset` is non-null, continue with `--offset NEXT_OFFSET --source-hash RETURNED_SOURCE_HASH` until it is null. When following a page, its `source_hash` can also pin the first turn read. [Complete source-reading examples](docs/engineering-workflows.md#read-the-evidence-before-applying-it).

| Action | MCP tool |
|---|---|
| Select a project book | `browse_projects` |
| Browse or search its directory | `browse_book`, `search_directory` |
| Open a chapter or section | `browse_chapter`, `browse_section` with the selected `project` |
| Read a page | `read_page` with the selected `project` |
| Read the original turn | `read_source_turn` with `project`, `session_id`, `turn_index` |

For a visual reader, run `memory-book --db ./demo-memory.db serve` and open **http://127.0.0.1:8765**. Select a book, use its directory, and open **Full original turn** from a page. The reader is optional; agents can use MCP directly.

## Engineering work this supports

**Recover the implementation contract.** The example records why a negative-edge routing task requires Bellman–Ford instead of the failed visited-once prototype, which `JSONLReader` fields are mandatory, and which split/normalization rules prevent training-data leakage. Preserve the reasons and constraints alongside the selected method.

**Find symbols without rewriting source.** Lexical aliases connect forms such as `HTTPParser`, `httpParser` and `http_parser`, while returned evidence keeps its original spelling and coordinates. This is naming normalization, not semantic synonym inference.

**Separate a correction from another project's value.** In the example, `inference-demo` records a current `KVCache block_size` of 32 and explains why 128 was superseded; a gateway test double separately records 256. Ask within the intended project, then open the source before applying the value:

~~~bash
memory-book --db ./demo-memory.db recall "current KVCache block_size and reason" --project inference-demo --json
~~~

**Maintain an archive that can be handed off.** Unchanged sessions are skipped; changed sessions are replaced transactionally. `backup` creates a verified SQLite snapshot, `check-database` inspects it read-only, and `export-book` produces navigable Markdown plus normalized source JSON from one snapshot. [Capture support](docs/integrations.md) · [Backup and handoff](docs/engineering-workflows.md#maintain-and-move-the-archive).

## Default recall

Recall can go directly to evidence; directory traversal is optional. Defaults are **lexical retrieval, 2400 characters and up to five results**. The character budget covers the assembled `context`, including citations and separators; it does not cap all JSON metadata or model tokens.

An MCP `recall_memory` call:

~~~json
{
  "query": "current KVCache block_size and reason",
  "project": "inference-demo",
  "budget_chars": 2400,
  "limit": 5,
  "temporal": "current"
}
~~~

`temporal=auto/current/relevance` controls conservative time-intent ordering. Current mode prefers comparable later evidence; it is not an authoritative state resolver or an as-of-date database. Historical evidence remains available. An exact token cap is optional through `budget_tokens` and the `tokens` extra; semantic retrieval and coverage expansion are separate opt-ins. [Recall semantics](docs/agent-guide.md) · [Token budgets](docs/token-budget.md).

## 2400-character evaluation

**v0.7.0 formal execution is pending. This README does not yet report v0.7.0 quality, latency or navigation pass rates.** The [registered protocol](benchmarks/project_navigation-plan.md) separates shared ranked retrieval from native book-navigation contracts. Source reviews and adapter preparation are not scored results.

The first hosted preparation run passed ReMe's real native API smoke. claude-mem's supplied-observation component intentionally uses case-insensitive project scope; this is incompatible with this experiment's exact-case contract for `scope-a` versus `Scope-a` and triggered `Native project scope violation`. Preparation stopped before formal quality execution. This remains a contract incompatibility, not a zero quality score or a claim that claude-mem lacks project filtering. [Retained preparation report](benchmarks/reports/v0.7.0-engineering/preparation-attempt1/adapter-smoke/report.json).

The target matrix is **Book plus seven external implementations**, using actual pinned upstream code:

| External target | Registered component mode | v0.7.0 status |
|---|---|---|
| billion-context | Native supplied-page search kernel | Formal run pending |
| claude-mem | Supplied raw observations, native SQLite/FTS search | Case-insensitive scope incompatible with the exact-case contract |
| Basic Memory | Explicit native text/FTS component | Formal run pending |
| Mem0 | `infer=False`, real local MiniLM and native vector-store search | Formal run pending |
| Chroma | Real local MiniLM document collection | Formal run pending |
| LangGraph Store | Explicitly indexed Store with the same real MiniLM | Formal run pending |
| ReMe | Official plain-text file chunker, local BM25 and native exact-path filter | Native API smoke passed; formal run pending |

Two distinct cohorts are registered: an **80-question engineering regression cohort** and an **80-question same-topic project cohort**. The latter uses eight books with the same display name and colliding session names/symbols, including case, underscore, hyphen and suffix differences in exact project IDs. It includes facts that exist only in a neighboring project, so missing local evidence is distinguishable from evidence absent everywhere.

The common ranked track supplies identical visible original pages, unchanged questions, exact project scope and a native top-five limit. One whole-block packer applies **1200 and 2400 characters**, including citations. Native Book excerpts remain a separate track. The planned audit reports complete evidence, required spans, fixed-policy outcomes, stale-only cases, source/scope failures, budget violations and both kinds of missing evidence.

Native navigation separately checks directory lookup, chapter/section/page traversal, full-turn reconstruction, wrong-book address rejection and explicit scope selection. These contracts measure Book's interfaces; a wrapper's project selection is not counted as a competing product's native capability.

**Interpretation limits:** these are authored development cases, without an independent holdout or a coding LLM. Fixed-policy tests are not generated-code accuracy. Chroma, LangGraph and Mem0 share one embedding model, so their results are correlated. Supplied-page FTS/raw-memory modes omit the products' extraction or synthesis pipelines; rebuilding checkpoint indexes does not test every native update/delete workflow. Source mapping validates the common originals, not identical citation features. Failed or unavailable backends must remain visible.

## Open-source comparison

Official sources checked on **2026-11-16** cover **18 external project families**. The table describes architecture and native capabilities; it does not rank unmeasured products. [Pinned sources, exact modes and license notes](docs/open-source-memory-comparison.md) · [Navigation-focused research](docs/v0.7.0-open-source-research.md).

| Project family | Native approach and engineering scope |
|---|---|
| [billion-context](https://github.com/ranxianglei/billion-context) | Proxy/client context management, reversible compression and searchable blocks with project filtering |
| [claude-mem](https://github.com/thedotmack/claude-mem) | Activity capture, model-generated observations/summaries and progressive SQLite/optional-vector retrieval |
| [Mem0 / OpenMemory](https://github.com/mem0ai/mem0) | Application memory and session tools; fact extraction or explicit raw-memory ingestion, with user/agent/run and metadata scope |
| [Letta / Letta Code](https://github.com/letta-ai/letta-code) | Stateful agents, editable memory and Git-backed MemFS, with file/message search and agent-specific or shared state |
| [Graphiti](https://github.com/getzep/graphiti) | Temporal knowledge graphs retaining episodes, entities and relationships; `group_id` scopes graph data |
| [MemOS](https://github.com/MemTensor/MemOS) | MemCubes and service/local memory paths; a local plugin also supports SQLite/FTS5 |
| [Memori](https://github.com/MemoriLabs/Memori) | Captured conversations and traces, with model enrichment and entity/process/session attribution |
| [Cognee](https://github.com/topoteretes/cognee) | Documents/code transformed into chunks, graphs and vectors; dataset scope and document provenance |
| [memvid](https://github.com/memvid/memvid) | Portable immutable content frames, native lexical search and optional vector retrieval in `.mv2` files |
| [Official MCP memory](https://github.com/modelcontextprotocol/servers/tree/main/src/memory) | JSONL entities/observations/relations with exact reads and literal substring lookup; separate instances can separate graphs |
| [LangGraph Store](https://github.com/langchain-ai/langgraph) | Namespace/key/value storage and optional semantic indexing, distinct from thread checkpoints; retrieval infrastructure |
| [LongMemory](https://github.com/CaviraOSS/LongMemory) | Project memory, provenance and temporal APIs with configurable embedding providers |
| [Basic Memory](https://github.com/basicmachines-co/basic-memory) | Markdown knowledge, directory tools, explicit project routing and ambiguous-path guards; text and semantic retrieval |
| [Chroma](https://github.com/chroma-core/chroma) | Document/vector collections with metadata filters and collection/tenant/database boundaries; retrieval infrastructure |
| [ReMe](https://github.com/agentscope-ai/ReMe) | Local files and wikilinks, source line ranges and native BM25; embeddings are off by default, with exact-path/metadata filtering |
| [OpenViking](https://github.com/volcengine/OpenViking) | Hierarchical context filesystem, directory abstracts/overviews and full-source reads; account/user isolation and optional resource ACLs |
| [Hindsight](https://github.com/vectorize-io/hindsight) | Memory banks, evidence-backed observations and generated pages in a searchable/exportable folder tree |
| [MCP Memory Service](https://github.com/doobidoo/mcp-memory-service) | Local semantic/BM25 memory, capture, document ingestion and graph exploration, with tag/store scope |

Directories, source lookup, project filters and local operation already exist in several of these projects. Book fits work that needs **original conversations as the primary archive, explicit project-book navigation, source-version checks, and bounded evidence retrieval with no model in the default path**. Graph reasoning, generated knowledge pages, editable agent state and vector-store infrastructure serve other needs. Mem0/OpenMemory and Letta/Letta Code each count as one family; licenses differ by project and sometimes by component.

## Practical limits and further reading

Only imported supported text can be recovered; normalization does not retain every vendor's multimodal payload. A short result can omit a necessary constraint, and a related result is not proof of a correct answer. Open the original turn and run the project's own tests. Keep source version hashes during paginated reads; replacing a session may also change its page addresses.

[Engineering workflows](docs/engineering-workflows.md) · [Agent guide](docs/agent-guide.md) · [Deployment](docs/deployment.md) · [Client integrations](docs/integrations.md) · [Evaluation protocol](benchmarks/project_navigation-plan.md)

Independently implemented under the [MIT License](LICENSE). [Release](https://github.com/Afloat16/AI-Memory-Book/releases/tag/v0.7.0) · [CI](https://github.com/Afloat16/AI-Memory-Book/actions/workflows/ci.yml).
