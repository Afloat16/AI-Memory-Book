# AI-Memory-Book

**Give coding agents engineering memory they can verify and continue from.**

Projects are books, tasks are chapters, and evidence is a page you can open. AI-Memory-Book preserves normalized original text conversations, so an agent can recover constraints, parameter corrections, and failed attempts after a session or client switch, cite the source, and continue the work.

[简体中文](README.zh-CN.md) · [Quick start](#quick-start) · [2400-character results](#2400-character-results) · [Open-source comparison](#open-source-comparison)

**v0.5.0 · MIT · Python 3.10+ · Local SQLite / FTS5**

## Engineering advantages

- **Recover decisions together with their reasons.** Locate evidence by project, task, session, and original turn, retaining page IDs and source references. Open the original page to check a boundary condition, error message, or failed approach during code review or a task handoff.
- **Find code identifiers across naming styles.** Queries such as `http_parser`, `JSONLReader` and `kv_cache` can match their acronym, camel-case and snake-case counterparts. The index adds lexical aliases while keeping original spelling, source offsets and project boundaries intact.
- **Control current evidence and historical review explicitly.** Python, CLI, MCP and HTTP share `temporal=auto/current/relevance`. Automatic inference distinguishes original source evidence from an original historical decision; callers can also choose current-evidence ordering directly. Comparable later turns remain eligible under both character and token truncation. Check the source when judging authority.
- **Spend bounded context on engineering constraints.** Apply project scope before retrieval and context assembly. The default is 2400 characters and up to five results; read further only when evidence is missing. This supports recovering implementation conventions, data-split rules, and edge cases together.
- **Continue across existing clients.** Supported clients such as Claude Code, Codex, and Gemini can share the same database. Switching tools does not require abandoning the archived project history. MCP configuration and native transcript capture have separate [support matrices](docs/integrations.md#supported-profiles).
- **Keep the memory layer simple to operate.** Default ingestion and lexical retrieval make no model calls and need no embedding model, database server, or memory-service API key. Background capture skips unchanged files; stable session IDs and content hashes prevent duplicate ingestion. Changed sessions are replaced transactionally; existing client configuration files are backed up before changes.
- **Maintain a recoverable archive.** Online SQLite backup includes committed WAL data and verifies a new snapshot before publication. Read-only checks expose integrity and runtime state without migrating the source. Derived-index upgrades preserve existing page addresses and reject incompatible older writers atomically.

**Import and hand off archives reliably.** CLI import validates every session before opening the database, so an invalid later input cannot first overwrite earlier records. `export-book` reads Markdown and JSON from one database snapshot and stages the complete output before publication. Failed exports can be cleaned up and retried; existing nonempty destinations stay protected.

When resuming a long-running task, ask which constraints the current implementation must satisfy, follow the citations to check later corrections and failed attempts, and then continue editing. Recovering a convention, checking its source, and continuing implementation gives a task handoff an explicit evidence trail. [Source semantics and agent guidance](docs/agent-guide.md).

## Quick start

You need **Python 3.10+ with SQLite FTS5**. The v0.5.0 package includes the identifier retrieval, temporal controls, archive maintenance, and import/export improvements described here. The installer creates an isolated environment with MCP/client dependencies and needs no Git checkout or Node.js. For an existing archive, follow the [schema 4 upgrade procedure](docs/deployment.md#schema-4-upgrade), including a snapshot and restarting every writer.

**macOS / Linux**

~~~bash
curl -fsSLo install-memory-book.sh https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/v0.5.0/scripts/install.sh
bash install-memory-book.sh
~~~

**Windows PowerShell**

~~~powershell
Invoke-WebRequest https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/v0.5.0/scripts/install.py -OutFile install-memory-book.py
py -3 .\install-memory-book.py
~~~

**Connect and check**

~~~bash
memory-book setup --client claude-code --capture --background
memory-book doctor
~~~

Replace `claude-code` with your [client profile](docs/integrations.md#supported-profiles), or repeat `--client` to connect more clients. Keep the capture flags only for profiles with native capture support; omit both `--capture` and `--background` for other profiles. If the command is not on PATH, use the full launcher path printed by the installer, then restart your client.

`--capture` opts in to existing and future supported text transcripts; `--background` installs and starts the user service. Omit both flags for MCP configuration alone. The host and model control tool invocation, so connecting MCP does not guarantee automatic recall. Upgrade through the same installation method, then refresh setup and restart clients. [Deployment guide](docs/deployment.md#schema-4-upgrade).

## Algorithm and engineering workflows

The [runnable example](examples/engineering-workflow.json) contains five synthetic sessions across four projects: a negative-edge shortest-path correction, training-data split constraints, an HTTP parser contract, an inference configuration change, and a separate project's conflicting value. It exercises source lookup and project isolation without a model API.

~~~bash
memory-book --db ./demo-memory.db import examples/engineering-workflow.json --format canonical
memory-book --db ./demo-memory.db recall "jsonl_reader input contract and split" --project training-demo
memory-book --db ./demo-memory.db recall "kv_cache block_size source evidence" --project inference-demo --temporal current
memory-book --db ./demo-memory.db backup --output ./backups/demo-snapshot.db
memory-book --db ./backups/demo-snapshot.db check-database
~~~

Get the example from the [v0.5.0 source](https://github.com/Afloat16/AI-Memory-Book/tree/v0.5.0), run it from the repository directory, and use new database/output paths. The [developer workflow guide](docs/engineering-workflows.md) covers algorithm constraints, failed attempts, symbol lookup, Python integration, exact token limits, source verification and recovery. Recorded example settings are illustrative, not recommended production values.

## Default configuration

The defaults are **native lexical retrieval, 2400 characters, and up to five results**, with no additional token cap. The character allowance includes citation headings and separators inside `context`; it does not cap the complete JSON response or model tokens.

Example call to the MCP tool `recall_memory`:

~~~json
{
  "query": "current gradient accumulation steps",
  "project": "your-project-id",
  "budget_chars": 2400,
  "limit": 5,
  "temporal": "current"
}
~~~

Use an actual project ID. Read the returned page ID when more evidence is needed. The CLI supports the same configuration:

~~~bash
memory-book projects
memory-book recall "current gradient accumulation steps" --project your-project-id --budget 2400 --limit 5
~~~

## 2400-character results

### Engineering replay against practical strategies

The workload contains **eight projects, four algorithm families, six chronological checkpoints, and 80 questions**. Only history available before each question is ingested. There are 72 answerable questions with 80 required evidence spans, 48 questions with executable policy checks, and eight missing-evidence questions. Algorithm families cover negative-edge shortest paths, Top-k ties, data splitting, and fully masked softmax.

The frozen v0.5.0 runtime has been replayed on the unchanged 80-question workload. Its default entry point matches all complete non-timing responses from explicit 2400/5 calls and this v0.5.0 replay's saved outputs. Repeated calls add timing samples, not independent quality cases. [Default-equivalence verification](benchmarks/reports/v0.5.0-engineering/default-profile/report.json).

| Strategy | Evidence-span recall | Complete evidence | Policy checks passing | Mean characters |
|---|---:|---:|---:|---:|
| **AI-Memory-Book** | **80/80 · 100%** | **72/72 · 100%** | **48/48 · 100%** | **1799.0** |
| Scoped flat FTS | 60/80 · 75.00% | 52/72 · 72.22% | 28/48 · 58.33% | 1801.3 |
| Recent history within budget | 64/80 · 80.00% | 56/72 · 77.78% | 32/48 · 66.67% | 2260.9 |

Book covers **20 more complete-evidence cases** than flat FTS, a **27.78-percentage-point** difference. Against recent history it covers **16 more cases** while returning approximately **20.4% fewer characters** on average. Flat FTS is this repository's baseline using the same scope, index, and packer. Recent history uses resident text, shorter citation headings, and no top-five limit; it is a practical strategy comparison. [Native replay data](benchmarks/reports/v0.5.0-engineering/current-workflow/report.json).

### Where the engineering benefit appears

Complete-evidence case counts at 2400 characters, retaining all nine answerable categories:

| Scenario | Book | Flat FTS | Recent history |
|---|---:|---:|---:|
| Later decision correction | **8/8** | 2/8 | 8/8 |
| Recovery after a long gap | **8/8** | 2/8 | 0/8 |
| Recovering multiple constraints | **8/8** | 2/8 | 8/8 |
| Looking up a historical decision | **8/8** | 8/8 | 0/8 |
| Chinese/English queries | **8/8** | 6/8 | **8/8** |
| Initial decisions | 8/8 | 8/8 | 8/8 |
| Code identifier lookup | 8/8 | 8/8 | 8/8 |
| Recovering failed attempts | 8/8 | 8/8 | 8/8 |
| Replaced source sessions | 8/8 | 8/8 | 8/8 |

The gains concentrate on evidence pushed back by intervening messages, corrected decisions, combinations of constraints, and bilingual queries. At this budget, Book has complete evidence in **8/8 cases in each of the nine categories**, with **zero stale-only cases**, versus 14 for flat FTS. These counts measure recovery of the required source evidence in this workload; source references still need to be checked when judging factual correctness. [Category and paired-case audit](benchmarks/reports/v0.5.0-engineering/comparison.json).

This local replay records retrieval and context assembly **p50 / p95 of 2.036 / 7.059 ms** over 240 calls at 2400 characters. Result caching is disabled; SQLite and operating-system caches are not cleared. Ingestion and model generation are excluded. These are diagnostic timings from one environment, not a controlled speedup or production latency guarantee. [Current validation and limits](docs/v0.5.0-engineering-validation.md).

### An executed open-source component comparison

The benchmark runs the actual [pinned billion-context search kernel](https://github.com/ranxianglei/billion-context/tree/9674cfafbc78c50245ae0d887483d3d6ce880c15). Both engines receive **the same complete pages, project scope, top-five limit, and common whole-block packing at 2400 characters**. This track is recorded separately from the native-excerpt track above.

| Metric | Book | billion-context kernel |
|---|---:|---:|
| Evidence-span recall | **80/80 · 100%** | 72/80 · 90.00% |
| Complete evidence | **72/72 · 100%** | 64/72 · 88.89% |
| Policy checks passing | **48/48 · 100%** | 40/48 · 83.33% |
| Mean characters | **1799.0** | 1955.0 |
| Stale-only cases | 0 | 0 |
| Budget violations / source-validation failures | 0 / 0 | 0 / 0 |

Within this component comparison, Book has **11.11 percentage points** more complete evidence, **16.67 points** more passing policy checks, and **7.98% fewer characters** on average. Paired cases show **eight gains and zero losses** in complete evidence; the gains are historical-decision queries. [Component data and timing boundaries](benchmarks/reports/v0.5.0-engineering/current-components/report.json).

This is a pinned-component result. Book retains hierarchy/FTS metadata, and the engines' timing interfaces differ; no whole-product speed ratio or general superiority over other memory systems follows.

**Smaller-budget boundary:** at 1200 characters with the same whole-block packing, Book has **52/72 complete-evidence cases (72.22%)**, versus **64/72 (88.89%)** for the kernel. Policy checks pass in **28/48 versus 40/48** cases, and stale-only cases are **12 versus 0**. This setting remains a weakness; the [detailed validation report](docs/v0.5.0-engineering-validation.md) retains the regression and all paired failures.

The separate native-excerpt track at 1200 characters records **76/80 evidence spans, 68/72 complete cases, 48/48 passing policy checks, and zero stale-only cases** for Book. Those results use different packing; use the matched whole-block track for the component comparison.

**Evidence limits:** these are synthetic cases used during development, without a coding LLM or an independent holdout. A fixed consumer extracts recorded configuration and executes handwritten algorithm variants; its pass rate is not generated-code accuracy. All eight missing-evidence questions still return related context, requiring further checking or an explicit statement that evidence is missing. Real task completion time, patch success, and total model cost have not been measured. [Evaluation protocol](docs/engineering-memory-evaluation.md) · [Raw records](benchmarks/reports/v0.5.0-engineering/).

## Open-source comparison

This review covers **14 external project families**, using official sources checked on 2026-11-16. Numerical results apply only to the explicitly configured components in the experiment; unmeasured complete products have no inferred score. [Pinned sources, tested modes, deployment requirements and license notes](docs/open-source-memory-comparison.md).

| Project | Main approach | When Book fits |
|---|---|---|
| [billion-context](https://github.com/ranxianglei/billion-context) | Model proxy and client plugins with model-directed reversible compression, decompression, and context search | An independent original-evidence archive queried by project through MCP, without changing model API routing |
| [claude-mem](https://github.com/thedotmack/claude-mem) | Hooks capture activity; an observer generates observations/summaries; local HTTP worker, SQLite, optional Chroma | Default capture and lexical queries add no summarization model calls; stdio MCP and capture need no HTTP listener |
| [Mem0](https://docs.mem0.ai/open-source/python-quickstart) | User/agent memory for applications; default model-based fact extraction and embeddings, with configurable local storage | Engineering conversations become original evidence without configuring additional extraction or embedding models |
| [Letta Code](https://github.com/letta-ai/letta-code) | Stateful agents managing memory, skills, and Git-backed MemFS, with local or cloud operation | A shared evidence layer for existing coding clients while retaining their tools and workflows |
| [Graphiti](https://github.com/getzep/graphiti) | Temporal knowledge graphs with retained original episodes, entity extraction and relationship retrieval | Project conversations and exact source coordinates without operating a graph backend or default extraction models |
| [MemOS](https://github.com/MemTensor/MemOS) | MemCubes and service/local memory paths; a local plugin also supports SQLite/FTS5 | A focused conversation archive with project/task navigation and a single local SQLite database |
| [Memori](https://github.com/MemoriLabs/Memori) | Captured conversations and traces enriched into facts and relationships, with cloud or own-database options | Original evidence and bounded retrieval without a separate enrichment pipeline |
| [Cognee](https://github.com/topoteretes/cognee) | Document/code memory using chunks, graphs and vectors; a local GLiNER path can avoid an LLM API key | Default lexical conversation retrieval with no embedding model and direct original-turn lookup |
| [memvid](https://github.com/memvid/memvid) | Portable `.mv2` content frames, lexical search and optional vector retrieval | Client transcript capture, project/task organization and source-linked handoff workflows |
| [Official MCP memory](https://github.com/modelcontextprotocol/servers/tree/main/src/memory) | Explicit entities, observations and relationships in a JSONL graph, including literal substring search | Ingesting complete conversations and assembling ranked, source-cited context within a budget |
| [LangGraph store](https://docs.langchain.com/oss/python/langgraph/stores) | Application-defined namespace/key/value stores; semantic indexes are explicit and separate from thread checkpoints | A ready-to-use archive, capture and retrieval layer for existing clients; LangGraph supplies lower-level application infrastructure |
| [LongMemory](https://github.com/CaviraOSS/LongMemory) | Project memory, provenance and temporal APIs with configurable embedding providers | A no-model default, stable page addresses and directly replayable engineering retrieval evidence |
| [Basic Memory](https://github.com/basicmachines-co/basic-memory) | Markdown knowledge, linked observations and project-scoped text/semantic search | Keeping source conversations as the primary archive without first authoring or rewriting knowledge notes |
| [Chroma](https://github.com/chroma-core/chroma) | Document/vector collections, local persistence and metadata filtering | Conversation capture, task navigation, source coordinates and context assembly without a default embedding dependency |

Multiple clients, source lookup, and local operation occur in several projects. Book brings **original evidence, project scope, bounded context, and low additional inference requirements** together in a lightweight memory layer for long-running development, incident review, and continuity across clients. Graph reasoning, editable agent state, authored Markdown knowledge and vector-store infrastructure address other needs; this table does not establish a universal winner. Mem0/OpenMemory and Letta/Letta Code each count as one family; Chroma and LangGraph are identified as infrastructure.

## Documentation and data boundaries

[Developer workflows](docs/engineering-workflows.md) · [Integrations](docs/integrations.md) · [Deployment and Docker](docs/deployment.md) · [Agent guide](docs/agent-guide.md) · [Token budgets](docs/token-budget.md) · [Optional semantic retrieval](docs/semantic-retrieval.md) · [Contributing](CONTRIBUTING.md)

Run `memory-book serve` and open [127.0.0.1:8765](http://127.0.0.1:8765) to inspect the archive. It is local, unencrypted data; recalled evidence enters the selected client's model context. Project filtering is not multi-user access control. Client-configuration backups are not automatic database backups. [Data locations and maintenance](docs/deployment.md#data-and-configuration-paths).

Independently implemented under the [MIT License](LICENSE). [Current release](https://github.com/Afloat16/AI-Memory-Book/releases/tag/v0.5.0) · [CI](https://github.com/Afloat16/AI-Memory-Book/actions/workflows/ci.yml).
