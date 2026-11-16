# AI-Memory-Book

**Find the right engineering evidence through a project book, without mixing similar projects.**

Projects are books, tasks are chapters, related turns form sections, and original evidence is a page you can open. AI-Memory-Book preserves normalized original text conversations, so an agent can recover constraints, parameter corrections, and failed attempts after a session or client switch, cite the source, and continue the work.

[简体中文](README.zh-CN.md) · [Quick start](#quick-start) · [2400-character results](#2400-character-results) · [Open-source comparison](#open-source-comparison)

**v0.7.0 · MIT · Python 3.10+ · Local SQLite / FTS5**

## Engineering advantages

- **Keep follow-up reads in the selected project.** Bind an MCP connection to one exact project ID. Omitted tool scopes inherit the binding, and copied chapter/section/page IDs from another project cannot silently switch books. Ordinary client setup preserves the binding.
- **Recover decisions together with their reasons.** Locate evidence by project, task, session, and original turn, retaining page IDs and source references. Open the original page to check a boundary condition, error message, or failed approach during code review or a task handoff.
- **Find code identifiers across naming styles.** Queries such as `http_parser`, `JSONLReader` and `kv_cache` can match their acronym, camel-case and snake-case counterparts. The index adds lexical aliases while keeping original spelling, source offsets and project boundaries intact.
- **Control current evidence and historical review explicitly.** Python, CLI, MCP and HTTP share `temporal=auto/current/relevance`. Automatic inference distinguishes original source evidence from an original historical decision; callers can also choose current-evidence ordering directly. Comparable later turns remain eligible under both character and token truncation. Check the source when judging authority.
- **Keep configuration revisions separate from maintenance mentions.** Current queries group comparable field declarations within the same task and query constraints. `retryLimit=3`, `retry_limit=5` and clear prose updates can be linked while recognized quoted logs/code examples and incomplete turns do not supply that declaration hint. Detailed results explain the classification; the original evidence remains available for review.
- **Spend bounded context on engineering constraints.** Apply project scope before retrieval and context assembly. The default is 2400 characters and up to five results; read further only when evidence is missing. This supports recovering implementation conventions, data-split rules, and edge cases together.
- **Continue across existing clients.** Supported clients such as Claude Code, Codex, and Gemini can share the same database. Switching tools does not require abandoning the archived project history. MCP configuration and native transcript capture have separate [support matrices](docs/integrations.md#supported-profiles).
- **Keep the memory layer simple to operate.** Default ingestion and lexical retrieval make no model calls and need no embedding model, database server, or memory-service API key. Background capture skips unchanged files; stable session IDs and content hashes prevent duplicate ingestion. Changed sessions are replaced transactionally; existing client configuration files are backed up before changes.
- **Maintain a recoverable archive.** Online SQLite backup includes committed WAL data and verifies a new snapshot before publication. Read-only checks expose integrity and runtime state without migrating the source. Derived-index upgrades preserve existing page addresses and reject incompatible older writers atomically.

**Import and hand off archives reliably.** CLI import validates every session before opening the database, so an invalid later input cannot first overwrite earlier records. `export-book` reads Markdown and JSON from one database snapshot and stages the complete output before publication. Failed exports can be cleaned up and retried; existing nonempty destinations stay protected.

When resuming a long-running task, ask which constraints the current implementation must satisfy, follow the citations to check later corrections and failed attempts, and then continue editing. Recovering a convention, checking its source, and continuing implementation gives a task handoff an explicit evidence trail. [Source semantics and agent guidance](docs/agent-guide.md).

## Quick start

You need **Python 3.10+ with SQLite FTS5**. The v0.7.0 package adds bound-project MCP connections and project assertions on directory/source reads, alongside identifier retrieval, temporal controls and archive maintenance. The installer creates an isolated environment with MCP/client dependencies and needs no Git checkout or Node.js. For an existing archive, follow the [upgrade procedure](docs/deployment.md#upgrading). An archive already on schema 4 needs no new schema migration in v0.7.0; the schema-4 migration procedure applies only to earlier schemas.

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

**Connect and check**

~~~bash
memory-book setup --client claude-code --capture --background
memory-book doctor
~~~

Replace `claude-code` with your [client profile](docs/integrations.md#supported-profiles), or repeat `--client` to connect more clients. Keep the capture flags only for profiles with native capture support; omit both `--capture` and `--background` for other profiles. If the command is not on PATH, use the full launcher path printed by the installer, then restart your client.

`--capture` opts in to existing and future supported text transcripts; `--background` installs and starts the user service. Omit both flags for MCP configuration alone. The host and model control tool invocation, so connecting MCP does not guarantee automatic recall. Upgrade through the same installation method, then refresh setup and restart clients. [Deployment guide](docs/deployment.md#upgrading).

## Algorithm and engineering workflows

The [runnable example](examples/engineering-workflow.json) contains five synthetic sessions across four projects: a negative-edge shortest-path correction, training-data split constraints, an HTTP parser contract, an inference configuration change, and a separate project's conflicting value. It exercises source lookup and project isolation without a model API.

~~~bash
memory-book --db ./demo-memory.db import examples/engineering-workflow.json --format canonical
memory-book --db ./demo-memory.db recall "jsonl_reader input contract and split" --project training-demo
memory-book --db ./demo-memory.db recall "kv_cache block_size source evidence" --project inference-demo --temporal current
memory-book --db ./demo-memory.db backup --output ./backups/demo-snapshot.db
memory-book --db ./backups/demo-snapshot.db check-database
~~~

Get the example from the [v0.7.0 source](https://github.com/Afloat16/AI-Memory-Book/tree/v0.7.0), run it from the repository directory, and use new database/output paths. The [developer workflow guide](docs/engineering-workflows.md) covers algorithm constraints, failed attempts, symbol lookup, Python integration, exact token limits, source verification and recovery. Recorded example settings are illustrative, not recommended production values.

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

## One project per MCP connection

Use the exact stored project ID to keep similar services, training runs or algorithm implementations separate. A book's display name is not its identity; different books may use the same task title, session ID or symbol names.

| Book structure | Engineering use | Read only what is needed |
|---|---|---|
| Project book | Select the actual engineering project | `browse_projects` / `browse_book` |
| Task chapter | Group known sessions for one task | `browse_chapter` |
| Question section | Locate a related group of source pages | `browse_section` |
| Evidence page | Verify the original turn and its coordinates | `read_page` |

You can recall directly within the project, or follow its directory when you need to inspect a task. Directory traversal is optional; the project constraint continues into exact chapter, section and page reads.

~~~bash
memory-book projects
# Replace service-alpha with an exact ID returned above.
memory-book setup --client codex --mcp-project service-alpha
# Or launch one explicitly bound stdio connection:
memory-book mcp --project service-alpha
~~~

On a bound MCP connection, omitted project arguments inherit the binding, including `browse_book`. A conflicting explicit project is rejected before opening the database. Foreign chapter/section/page IDs are unavailable even if copied from an earlier project. `remember_session`, when enabled, still requires the same explicit `payload.project`; it does not silently relabel messages.

Ordinary setup preserves an existing managed binding. Change it with `--mcp-project OTHER_ID`; explicitly remove it with `--clear-mcp-project`. `setup --project` controls **capture mapping** and still requires `--capture`; `--mcp-project` controls the **MCP connection**. Binding a client profile affects that configured connection, and does not automatically switch with the terminal's current directory. [Project scope and configuration](docs/agent-guide.md#bound-project-connections).

Python `chapter`, `section` and `read` accept `project=...`; their CLI equivalents accept `--project`, and HTTP follow-up reads accept a `project` query parameter. The reader carries the selected book into these requests and ignores stale reader responses when switching books. Unbound calls can still browse the whole archive. This is protection against scope mistakes, not user authentication or an access-control boundary for another server or direct database access.

### Executed v0.7.0 scope checks

A separate authored diagnostic uses **four similar projects and twelve source sessions**, with identical display names, task IDs and session IDs but conflicting settings. The candidate completes **186 core API calls with zero contract failures**, including **36 foreign-ID rejections**, **12 unknown-project rejections**, paginated source reconstruction, interleaved warm caches, source replacement and project deletion. Four directory checks verify source coverage against the original sessions. **35/35 existing-API responses/errors match v0.6.0** after the documented removal of timing/cache and directory wall-clock metadata; evidence text, IDs, coordinates and source dates remain in the comparison.

The v0.6.0 diagnostic records **37 passed calls and 77 unsupported assertions**, not 77 failed isolation checks. The new supported directory traversal performs additional reads, so the versions' total call counts differ. These are development contract checks, not answer accuracy, a holdout, a speed benchmark, or a claim of perfect isolation. [Raw calls and comparison](benchmarks/reports/v0.7.0-project-scope/final/scope-candidate/) · [Validation and reproduction](docs/v0.7.0-project-scope-validation.md).

The corrected final runtime also replays the unchanged **80 native engineering questions at 1200 and 2400 characters, once per setting**, against the retained, previously executed v0.6.0 baseline. All **160/160 Book responses** and **640/640 responses across the four repository strategies** match after excluding only top-level latency/cache diagnostics. An independent auditor passes **16,861 checks**. This is regression evidence, with no new speed claim or external-component run. [Raw replay and audit](benchmarks/reports/v0.7.0-project-scope/final/native-replay-audit.json).

## 2400-character results

The external comparison below retains the **frozen v0.6.0 experiment**. The v0.7.0 scope diagnostic above is a separate measurement; no newly reviewed project receives a numerical score.

### Six real open-source implementations, one fixed workload

The frozen **v0.6.0 runtime** was evaluated on **eight projects, four algorithm families, six chronological checkpoints and 80 questions**. There are **72 answerable questions, 80 required evidence spans, 48 fixed-policy cases and eight missing-evidence questions**. Families cover negative-edge shortest paths, Top-k ties, data splitting and fully masked softmax. Only previously visible history is ingested. Three repeats measure timing and stability; they do not create additional quality cases.

The comparison runs actual pinned upstream code for **billion-context, claude-mem, Basic Memory, Mem0, Chroma and LangGraph Store**. Every backend receives the same complete original pages, unchanged questions, project filter and top-five limit. The same whole-block packer applies the 2400-character budget, including citations; oversized blocks are skipped. Book retains its native hierarchy/index metadata. [Fixed protocol and package/model locks](benchmarks/competitors/memory-systems-plan.md).

External components are rebuilt from the visible source-page snapshot at each checkpoint. The source-replacement category measures retrieval from that updated snapshot; it does not validate every product's native incremental update/delete workflow. The seven-backend matrix contains 560 query/backend pairs, 1680 actual native calls across three repeats, and 1120 packed outputs across the two budgets. Both budgets reuse the same native candidates.

**Read the tested modes with the scores.** Basic Memory uses explicit FTS, claude-mem searches supplied raw observations without its observer, and Mem0 uses `infer=False` without fact extraction. Chroma and LangGraph are retrieval/store infrastructure. Mem0, Chroma and LangGraph share the same real local MiniLM model and its native 256-token truncation. These are configured component results; default full-product workflows are outside this experiment.

| Measured component / mode | Evidence spans | Complete evidence | Policy passes | Stale-only | Mean chars |
|---|---:|---:|---:|---:|---:|
| **AI-Memory-Book** | 80/80 | 72/72 · 100.00% | 48/48 | 0 | 1799.2 |
| billion-context · pinned kernel | 72/80 | 64/72 · 88.89% | 40/48 | 0 | 1955.0 |
| claude-mem 15.18.1 · raw-observation FTS | 72/80 | 64/72 · 88.89% | 40/48 | 0 | 1488.5 |
| Basic Memory 1.0.0 · explicit FTS | 72/80 | 64/72 · 88.89% | 40/48 | 0 | 1333.1 |
| Mem0 2.2.1 · `infer=False` + MiniLM | 55/80 | 47/72 · 65.28% | 25/48 | 4 | 1963.0 |
| Chroma 1.5.9 · MiniLM collection | 55/80 | 47/72 · 65.28% | 25/48 | 4 | 1963.0 |
| LangGraph checkpoint 4.3.2 · indexed Store | 55/80 | 47/72 · 65.28% | 25/48 | 4 | 1963.0 |

At 2400 characters, Book recovers **eight more complete-evidence cases** than each tested lexical component, a **11.11-percentage-point** difference, and passes **eight more fixed-policy cases**, a **16.67-point** difference. Against each of the three shared-MiniLM configurations, it recovers **25 more complete cases**. Their identical quality counts are correlated evidence of the shared model, not three independent demonstrations of model superiority. [Complete component report](benchmarks/reports/v0.6.0-engineering/hosted/memory-systems/report.json).

The context tradeoff is visible: Book uses **7.97% fewer characters than billion**, but returns more text than claude-mem FTS and Basic Memory FTS while recovering the additional evidence. It does not have the shortest context among all engines. Every backend has **zero source-validation failures, zero budget violations and stable repeated output** in both budgets. [Raw outputs and source mappings](benchmarks/reports/v0.6.0-engineering/hosted/memory-systems/).

“Stale-only” counts cases containing a marked obsolete span without required evidence. It does not count every kind of wrong answer: billion's historical-decision misses, for example, still have zero stale-only cases. Complete-evidence coverage and the category table must be read alongside that count.

Source validation authenticates each adapter's mapping back to the common original pages. It does not imply that every upstream product natively exposes Book's exact citation coordinates.

### Which engineering scenarios explain the difference?

Complete-evidence counts under the same 2400-character whole-block protocol:

| Scenario (8 cases each) | Book | billion | claude-mem FTS | Basic Memory FTS | Three MiniLM modes¹ |
|---|---:|---:|---:|---:|---:|
| Later decision correction | 8/8 | 8/8 | 8/8 | 8/8 | 0/8 |
| Recovery after a long gap | 8/8 | 8/8 | 8/8 | 8/8 | 0/8 |
| Multiple constraints | 8/8 | 8/8 | 8/8 | 8/8 | 6/8 |
| Historical decision | 8/8 | 0/8 | 8/8 | 8/8 | 1/8 |
| Chinese/English queries | 8/8 | 8/8 | 0/8 | 0/8 | 8/8 |
| Initial decisions | 8/8 | 8/8 | 8/8 | 8/8 | 8/8 |
| Code identifier lookup | 8/8 | 8/8 | 8/8 | 8/8 | 8/8 |
| Failed attempts | 8/8 | 8/8 | 8/8 | 8/8 | 8/8 |
| Replaced source sessions | 8/8 | 8/8 | 8/8 | 8/8 | 8/8 |

¹ Chroma, indexed LangGraph Store and raw-memory Mem0 have the same counts in every category here; each remains separately recorded in the main table and raw data. Book's gains over billion are historical-decision queries; its gains over claude-mem/Basic Memory FTS are the bilingual queries. The MiniLM configurations lose most evidence on later corrections, long-gap recovery and historical lookup. These patterns describe this authored dataset, not each product's general language or reasoning capability. [Category and paired-case audit](benchmarks/reports/v0.6.0-engineering/audit.json).

### The 1200-character boundary remains visible

The same pages, queries, candidate limit and whole-block packer give:

| Measured component / mode | Evidence spans | Complete evidence | Policy passes | Stale-only | Mean chars |
|---|---:|---:|---:|---:|---:|
| **AI-Memory-Book** | 76/80 | 68/72 · 94.44% | 44/48 | 4 | 1048.1 |
| billion-context · pinned kernel | 72/80 | 64/72 · 88.89% | 40/48 | 0 | 948.5 |
| claude-mem 15.18.1 · raw-observation FTS | 72/80 | 64/72 · 88.89% | 40/48 | 0 | 848.0 |
| Basic Memory 1.0.0 · explicit FTS | 72/80 | 64/72 · 88.89% | 40/48 | 0 | 948.5 |
| Mem0 2.2.1 · `infer=False` + MiniLM | 55/80 | 47/72 · 65.28% | 25/48 | 4 | 1036.7 |
| Chroma 1.5.9 · MiniLM collection | 55/80 | 47/72 · 65.28% | 25/48 | 4 | 1036.7 |
| LangGraph checkpoint 4.3.2 · indexed Store | 55/80 | 47/72 · 65.28% | 25/48 | 4 | 1036.7 |

Book has **68/72 complete cases and 44/48 policy passes**, but still returns only stale evidence in **four training-decision cases**: two replacement decisions and two long-gap queries. Each tested lexical competitor wins those four cases and loses eight others to Book. Its higher aggregate coverage does not mean it wins every question or has fewer stale results at this budget. Those failures remain in the [validation record](docs/v0.6.0-engineering-validation.md).

### Native retrieval versus practical strategies

This separate track retains the **frozen v0.6.0 native excerpt experiment**, comparing Book and the existing in-repository strategies at 2400 characters. Flat FTS and recent history are baselines, not additional open-source products.

| Strategy | Evidence spans | Complete evidence | Policy passes | Mean chars |
|---|---:|---:|---:|---:|
| **AI-Memory-Book** | 80/80 | 72/72 | 48/48 | 1799.2 |
| Scoped flat FTS | 60/80 | 52/72 | 28/48 | 1801.3 |
| Recent history within budget | 64/80 | 56/72 | 32/48 | 2260.9 |
| No memory | 0/80 | 0/72 | 0/48 | 0.0 |

Book finds complete evidence in **20 more cases than flat FTS** and **16 more than recent history**, with about **20.4% fewer context characters** than recent history. Flat FTS shares the scope/index/native packer; recent history uses resident text, shorter citation headings and no top-five limit. Native Book at 1200 characters has **76/80 spans, 68/72 complete cases, 48/48 policy passes and zero stale-only cases**. These excerpt results must not be substituted into the common-block competitor table. [Native report](benchmarks/reports/v0.6.0-engineering/hosted/native/report.json).

The **frozen v0.6.0 native replay** at 2400 characters records retrieval/context assembly **p50 / p95 of 1.560 / 4.846 ms** over 240 calls. Result caching is disabled; SQLite/OS caches are not cleared. This excludes ingestion and model generation. Foreign-process calls and embedding-backed searches have different timing boundaries, so no whole-product speed ratio is claimed. The single-execution v0.7.0 regression above adds no timing claim.

### Reproduction and evidence limits

An independent audit recomputed the scores and complete packed responses, passing **116,693 checks with zero failures**. All **320 Book/billion response pairs** match between the original two-component evaluator and the expanded harness, across both budgets. Default calls also match explicit 2400/5 calls and all 80 saved v0.6.0-runtime outputs. [Audit](benchmarks/reports/v0.6.0-engineering/audit.json) · [Default equivalence](benchmarks/reports/v0.6.0-engineering/hosted/default-profile/report.json) · [Successful run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43788979015).

These are **synthetic development cases**, without an independent holdout or coding LLM. The fixed consumer extracts recorded policies and executes handwritten variants; its pass rate is not generated-code accuracy. **All seven backends return related context for all eight missing-evidence questions** at both budgets, so this is not an abstention benchmark or 80/80 answer correctness. Real task completion time, patch success and total model cost remain unmeasured. The [validation record](docs/v0.6.0-engineering-validation.md) retains every failure, test boundary, source identity and the pre-quality Chroma integration failure. Heavy comparison dependencies are separate from the normal Book installation.

## Open-source comparison

This review covers **19 external project families**, using official sources checked on 2026-11-16. Numerical results apply only to the explicitly configured components in the experiment; unmeasured complete products have no inferred score. [Pinned sources, tested modes, deployment requirements and license notes](docs/open-source-memory-comparison.md).

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
| [OpenViking](https://github.com/volcengine/OpenViking) | A context filesystem with directory abstracts, overviews and scoped vector retrieval | Original conversation pages and source coordinates through a default model-free lexical path; directory navigation is also supported by OpenViking |
| [Serena](https://github.com/oraios/serena) | Coding tools with project Markdown memories, topic directories and explicit references | Preserving full conversation evidence alongside project/task navigation; Serena also supports progressive memory reads |
| [EverOS / EverMemOS](https://github.com/EverMind-AI/EverOS) | Markdown sources, extracted memories, SQLite/LanceDB indexes and app/project partitions | A focused conversation archive without a default extraction model; project partitioning is also documented upstream |
| [SimpleMem](https://github.com/aiming-lab/SimpleMem) | Model-extracted atomic facts and semantic/keyword/metadata retrieval | Read original engineering turns and their coordinates without first reducing them to extracted facts |
| [Supermemory](https://github.com/supermemoryai/supermemory) | Extracted memories/profiles and hybrid search, with project/container tags and local/hosted options | A lightweight original-conversation archive with explicit project assertions and no default embedding dependency |

Multiple clients, directory/progressive reading, project scopes, source lookup, and local operation occur in several projects. Book brings **original evidence, project scope, bounded context, and low additional inference requirements** together in a lightweight memory layer for long-running development, incident review, and continuity across clients. Graph reasoning, editable agent state, authored Markdown knowledge and vector-store infrastructure address other needs; this table does not establish a universal winner. Mem0/OpenMemory and Letta/Letta Code each count as one family; Chroma and LangGraph are identified as infrastructure.

## Documentation and data boundaries

[Developer workflows](docs/engineering-workflows.md) · [Integrations](docs/integrations.md) · [Deployment and Docker](docs/deployment.md) · [Agent guide](docs/agent-guide.md) · [Token budgets](docs/token-budget.md) · [Optional semantic retrieval](docs/semantic-retrieval.md) · [Contributing](CONTRIBUTING.md)

Run `memory-book serve` and open [127.0.0.1:8765](http://127.0.0.1:8765) to inspect the archive. It is local, unencrypted data; recalled evidence enters the selected client's model context. Project filtering is not multi-user access control. Client-configuration backups are not automatic database backups. [Data locations and maintenance](docs/deployment.md#data-and-configuration-paths).

Independently implemented under the [MIT License](LICENSE). [Current release](https://github.com/Afloat16/AI-Memory-Book/releases/tag/v0.7.0) · [CI](https://github.com/Afloat16/AI-Memory-Book/actions/workflows/ci.yml).
