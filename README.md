# AI-Memory-Book

**Background memory for AI agents. Projects become books, tasks become chapters, and agents retrieve the cited evidence they need to continue working.**

[简体中文](README.zh-CN.md) · [Agent guide](docs/agent-guide.md) · [Installation & background mode](docs/deployment.md) · [Client compatibility](docs/integrations.md) · [Measured results](benchmarks/README.md) · [Releases](https://github.com/Afloat16/AI-Memory-Book/releases)

AI-Memory-Book gives AI agents a shared, local memory of earlier work. After you connect a client and opt in to capture, a background worker indexes supported conversations. When a task depends on a previous decision, constraint, or unfinished step, the agent can call MCP once, receive bounded original evidence with source references, and continue the task. It does not need to read a directory or an entire conversation first.

The primary interface is **MCP for the agent**. Background capture runs headlessly by default; the optional web reader is for inspecting and debugging the archive. The server supplies guidance for conditional recall, while the host and model control tool invocation and permissions. Automatic use in every client or on every question is not guaranteed.

**v0.3 development · Experimental · MIT · Local storage · No memory-service API key**

## Why use AI-Memory-Book?

AI-Memory-Book is built for continuing project work with a small, inspectable memory service:

| Advantage | What you get |
|---|---|
| **Model-free default memory path** | Local Python + SQLite indexing and lexical retrieval; no per-turn summarization bill, embedding download, or separate database service in the core. Your answering model remains your choice. |
| **Original evidence with citations** | Recall returns source text and project/session/turn references. Exact character spans and full pages remain available when you need to verify a decision. |
| **Useful context in one MCP call** | `recall_memory` assembles bounded evidence directly. Project, chapter and session filters help the agent focus on the work at hand. |
| **Exact context limits when you need them** | An optional named-tokenizer cap includes citations and separators, alongside the character cap. Fitting original evidence blocks stay intact; remaining capacity can carry additional source sentences. |
| **Optional indexed source references** | A response-wide session table encodes repeated references without losing their identities or detailed offsets. Enable it at MCP startup; default clients keep their existing schemas and instructions. |
| **One archive across clients** | Supported clients point to the same local database. Opt-in background capture keeps supported text transcripts available for later tasks. |
| **A small operational footprint** | The default worker and MCP server run without an HTTP listener; the optional reader, export tools, and source-preserving migrations make the archive inspectable. |

See the [agent workflow](docs/agent-guide.md), [capture and deployment guide](docs/deployment.md), and [source/migration checks](benchmarks/RESULTS-recall-score-quality.md#8-source-preserving-schema-migration).

### Latest verified comparison

With the same **1,024-token `cl100k_base` context cap**, Book delivers more complete original evidence than the three tested native retrieval components:

| Retrieval component | Evidence recall ↑ | Complete evidence ↑ | Mean context tokens ↓ |
|---|---:|---:|---:|
| **AI-Memory-Book, score-aware** | **69.54%** | **72.88%** | 827.2 |
| [claude-mem](docs/claude-mem-component-evaluation.md), native SQLite FTS | 66.24% | 70.11% | 804.8 |
| [billion-context](docs/comparison.md), search kernel | 65.48% | 68.72% | 862.6 |
| [ai-memory](docs/comparison.md), local hybrid | 64.47% | 66.72% | **779.3** |

Book's complete-evidence advantage is **+2.77 percentage points over claude-mem FTS**, **+4.16 over billion-context**, and **+6.16 over ai-memory**. Its context is 4.1% smaller than billion-context at this setting; claude-mem and ai-memory use fewer context tokens.

**Scope:** all 1,015 eligible text-only LoCoMo questions, the same 1,339 supplied source pages, project scope, top-five candidates, and one citation/whole-page packer. Complete evidence uses 649 answerable questions; evidence recall uses 788 required source utterances; mean tokens use all 1,015 questions. Evidence must survive intact with its original source span. This measures source delivery, separately from generated answers and complete product workflows.

The [full comparison](docs/comparison.md) records the exact source revisions, all six tokenizer/budget settings, MRR and unsupported-query behavior. The latest added claude-mem measurement executes unmodified upstream `SessionStore` / `SessionSearch`, with **3,045 successful native calls**. Its observer, Chroma, host injection and generation are outside that component test. The native token-budget API has a separate packing policy and report.

### Speed, response size and operating costs

The current source has a separately verified **lossless indexed-reference mode**.
On all 1,015 public-conversation questions at the default 4,000-character cap,
actual MCP response text uses **19.63% fewer `o200k_base` tokens**. Including the
complete tool schema, initialization instructions and call arguments, the
first-call reference count falls **8.15%**.

| Current MCP format | p50 | p95 | Mean response-text tokens | First-call reference tokens |
|---|---:|---:|---:|---:|
| Default `objects` | 5.503 ms | 7.126 ms | 1,464.8 | 2,621.0 |
| **Opt-in `indexed`** | **5.466 ms** | 7.131 ms | **1,177.2** | **2,407.4** |

Both rows run the **same frozen implementation**, official SDK and source
archive, with four balanced rounds and cleared query-result caches. Context,
page IDs and complete source fields are recoverable without alteration. The
indexed setting adds 74 initialization tokens in this encoding and no tool-schema
or argument tokens; default clients incur none of that increment. First-call
net tokens improve on 1,014 of 1,015 questions. Sparse references can cost more,
and this format does not promise a speed improvement: the displayed p95 changes
by +0.005 ms. Reference counts are measured SDK text/metadata surfaces, not a
provider billing estimate. [All 12 configurations, both tokenizers, per-query
losses and reproduction](docs/indexed-references.md).

The **default core optimization** has its own paired, identical-output test:
all 12 cohort/interface/character-budget configurations have lower pooled p95,
by **1.32%–13.65% in process** and **1.25%–9.50% through actual MCP**. On the
public corpus, fresh ingestion is **46.45% faster** and unchanged-session replay
is **61.38% faster**. Those improvements retain the same returned tokens and
source/index content; the [full report](docs/default-recall-performance.md)
keeps every round and the small individual-round regressions.

Default memory writing and lexical retrieval use **zero model calls** and
require no embedding download or separate database service. Optional local
semantics has its own model, index and query costs. Your answering model remains
your choice. [Full component costs and deployment comparison](docs/comparison.md)
cover **claude-mem, ai-memory and billion-context**, with separately labeled
native search/read, preparation, storage and RSS boundaries. The same guide
covers **Mem0, Graphiti, PageIndex and Letta** using official sources. ai-memory
also supports a zero-LLM default path; claude-mem supports local model providers.

## Get started

You need **Python 3.10+ with SQLite FTS5**. The installer creates an isolated environment and includes MCP and client-configuration dependencies. This route does not require a Git checkout, Node.js, an embedding server, or a database server.

### Choose a version

| Version | What you get | How to use it |
|---|---|---|
| **Published experimental release v0.2.1** | Agent-first MCP, shared local memory and optional headless background capture | Use the pinned installers below. |
| **Available v0.3 development source** | Faster local retrieval and ingestion, optional indexed references, exact token budgets, multi-fact coverage, local semantic retrieval and reproducible component/answer evaluation | Use the [source checkout](#try-it-without-connecting-a-client) on `main`. |

The installers below still use the published **v0.2.1**; there is no `v0.3.0` release tag yet. Use the `main` source checkout to try the additional capabilities.

### macOS / Linux

```bash
curl -fsSLo install-memory-book.sh https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/v0.2.1/scripts/install.sh
bash install-memory-book.sh
```

The installer prints the exact launcher path and any PATH instructions. Use that path if `memory-book` is not yet on your PATH.

### Windows PowerShell

```powershell
Invoke-WebRequest https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/v0.2.1/scripts/install.py -OutFile install-memory-book.py
py -3 .\install-memory-book.py
```

The shared Python installer also works on macOS/Linux. A [v0.2.1 PowerShell wrapper](https://github.com/Afloat16/AI-Memory-Book/blob/v0.2.1/scripts/install.ps1) is also available. Installation does not change your shell profile or execution policy.

### Connect your agent and enable background memory

```bash
# Configure MCP and opt in to supported transcript capture at login
# The background service has no HTTP listener by default
memory-book setup --client claude-code --capture --background

memory-book doctor
memory-book service status
```

Restart the client or refresh its MCP servers. The client may still ask you to approve its connection or tools. Continue working in that client: the intended agent workflow is to recall relevant history when the current task needs it, use its sources, and proceed. To check the connection explicitly, ask: **“Use memory-book to find the cache decision from our earlier work, cite the source, and continue the implementation.”**

`--capture` explicitly enables reading existing and future supported text transcripts from the paths displayed by setup. `memory-book setup --client claude-code` configures MCP alone, for an archive populated by another source or explicit imports. Use `--dry-run` to inspect changes first. Configure several clients with repeated `--client`, or use `--all` for detected clients.

```bash
memory-book setup --client claude-code --client codex --capture --background
memory-book setup --all --dry-run
```

For one workspace only:

```bash
memory-book setup --client codex --capture --workspace /absolute/path/to/project \
  --project my-project --background
```

Setup preserves existing settings, backs up changed files, and updates an owned entry without duplicating it. It leaves malformed/JSONC files untouched and prints a manual snippet. See [configuration behavior and host checks](docs/integrations.md).

## How an agent uses memory

The normal path is **client setup → background capture → conditional MCP recall → bounded cited evidence → continue the task**. Capture updates the archive independently of the agent's retrieval call. A self-contained question needs no memory lookup; a task that refers to previous work usually does.

For example, an agent continuing the fictional `atlas` project's cache work can call `recall_memory` on the `memory-book` MCP server. These are the parameters of a `tools/call` request; the client's displayed server/tool prefix may differ:

```json
{
  "name": "recall_memory",
  "arguments": {
    "query": "搜索缓存最终保留多久？为什么从300秒调整？",
    "project": "atlas",
    "budget_chars": 2000,
    "limit": 5
  }
}
```

The response contains `context`, page IDs, and compact source references: `project`, `session_id`, and `turn_index`. Request `details: true` or use `read_page` for exact character spans. With the [example archive](examples/conversations.json), the cache review records a change from 300 to 45 seconds while retaining revision invalidation. The agent can cite `atlas / atlas-cache-review / turn 0`, check the source date, and use that decision in the implementation. Historical text remains evidence to assess, including possible outdated or conflicting decisions.

For reference-heavy workloads, the development MCP server also supports
`memory-book mcp --source-format indexed`. It returns the same evidence with a
versioned session table and reversible reference arrays. This operator setting
adds no tool argument or schema cost to default clients. Indexed clients receive
decoding instructions; small or empty responses can cost more. See the
[format, client configuration and measured costs](docs/indexed-references.md).

**Choose the context budget:** `budget_chars` in Python/MCP and `--budget` in the CLI cap the assembled context in characters. The development source also supports an **exact optional token cap** with `budget_tokens` / `--budget-tokens` and either `cl100k_base` or `o200k_base`. Both caps include citations and separators in `context`; outer JSON metadata, tool schemas and the rest of the conversation are outside them. Install the `tokens` extra and add these arguments to the recall call:

```bash
python -m pip install -e ".[tokens]"
memory-book recall "cache expiry and retry window" --project atlas \
  --budget 4000 --budget-tokens 512 --tokenizer cl100k_base --json
```

For MCP, add `"budget_tokens": 512` and `"tokenizer": "cl100k_base"` to `arguments`; Python uses the same parameter names. The response reports the exact `context_tokens` and tokenizer version. `estimated_tokens` remains a character-based estimate. Without the optional token cap, the dependency-free character path is unchanged. First-time vocabulary initialization may require a public download; offline deployments should preload it. [API, offline setup, source-preservation contract and costs](docs/token-budget.md).

The component comparison uses a shared **whole-page benchmark packer**. The new API assembles **native excerpts and intact source units**; its results have a separate baseline and do not retroactively change those tables. See [budget verification and measured tradeoffs](#validation-and-optional-modes).

The agent can navigate the hierarchy when a direct recall leaves a concrete gap:

| Address level | Meaning | MCP tool |
|---|---|---|
| Bookshelf | Discover project IDs when the project is unknown | `browse_projects` |
| Book | One project namespace and its chapters | `browse_book(project)` |
| Chapter | Sessions sharing an explicit task ID | `browse_chapter(chapter_id)` |
| Section | Related consecutive questions within a session | `browse_section(section_id)` |
| Page | Bounded original text with exact source references | `read_page(page_id)` |

These are optional navigation tools for the agent, not a mandatory sequence before recall. Pass IDs returned by the server to open a chapter, section, or page. Known project/chapter/session filters narrow retrieval directly. Short follow-ups can stay together; long answers receive continuation pages. The default adaptive page cap is 900 characters, and cross-session chapters use explicit task IDs.

The [agent guide](docs/agent-guide.md) covers when to recall, how to use citations and budgets, what to do when evidence is missing or contradictory, and how to treat imported instructions as untrusted historical text. No vendor lifecycle hooks or forced context injection are installed.

## Client compatibility

MCP access and automatic transcript capture are separate capabilities. Profiles follow linked official schemas and are tested with fixtures; this is **not a claim of an interactive end-to-end test in every vendor application**.

| Client / profile | MCP configuration | Background text capture |
|---|---|---|
| Claude Code — `claude-code` | Automatic JSON merge | Native JSONL |
| Claude Desktop — `claude-desktop` | Automatic JSON merge | Explicit import / MCP writing |
| Codex CLI, desktop and IDE — `codex` | Automatic TOML merge | Local rollout JSONL |
| Gemini CLI — `gemini` | Automatic JSON merge | Current JSONL and legacy JSON |
| Kimi Code, current — `kimi` | Automatic JSON merge | Explicit import / MCP writing |
| Kimi CLI, legacy Python — `kimi-legacy` | Automatic JSON merge | Active `context.jsonl` |
| Cursor — `cursor` | Automatic JSON merge | Explicit import / MCP writing |
| OpenCode v2 — `opencode` | Automatic strict-JSON merge | Explicit import / MCP writing |
| GitHub Copilot CLI — `copilot-cli` | Automatic JSON merge | Explicit import / MCP writing |
| Qwen Code — `qwen-code` | Automatic JSON merge | Explicit import / MCP writing |
| LM Studio — `lm-studio` | Automatic JSON merge | Explicit import / MCP writing |
| Other MCP hosts — `generic-json` | Export a snippet | Canonical imports / MCP writing |

**DeepSeek and other providers:** configure the MCP-capable host in which you use the model, such as OpenCode, instead of assuming every model provider has the same local configuration. AI-Memory-Book does not change your model provider, credentials, or API routing. A standalone DeepSeek host configuration is not verified here. [Exact paths, sources, and version boundaries](docs/integrations.md).

## What runs in the background?

The MCP client starts its own stdio server when it needs tools. A separate, optional user service polls configured transcript directories and imports changed conversations. **New background configurations are headless by default**: no web reader or HTTP listener is required for capture or agent recall. The worker does not call an LLM to summarize every turn.

- Linux: `systemd --user`.
- macOS: a per-user LaunchAgent.
- Windows: a current-user Scheduled Task at logon, with limited privileges and no stored password.

```bash
memory-book service status
memory-book service stop
memory-book service start
memory-book service uninstall
```

Uninstalling the service keeps your database and client settings. Removing a watched source keeps its archived memory. A running daemon reloads changes to its configuration, including reduced capture scope. On machines without a usable user service manager, run `memory-book daemon` under your existing supervisor, or run `memory-book sync --once` when convenient.

Unchanged, successfully imported files are skipped. The worker skips symlinks and known credential/config files, retries incomplete active logs, isolates malformed files, and never deletes memory just because a source file disappears. Source text is stored locally; when a model calls a memory tool, the returned evidence becomes part of that client's model context. [Capture scope and operations](docs/deployment.md).

Capture behavior and its historical overhead samples are retained in the
[deployment verification](docs/validation.md#v020-capture-overhead-sample).

## Try it without connecting a client

From the current **development branch** (the branch can advance beyond the frozen benchmark commit):

```bash
git clone --branch main https://github.com/Afloat16/AI-Memory-Book.git
cd AI-Memory-Book
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[mcp,clients,benchmark]"

memory-book import examples/conversations.json
memory-book recall "搜索缓存为什么改成45秒？" --project atlas
```

On Windows, activate `.venv\Scripts\Activate.ps1`, or call `.venv\Scripts\python.exe` directly. Reproduce a measurement using the exact source commit and protocol linked in the [benchmark index](benchmarks/README.md); `main` can advance beyond those frozen commits. The dependency-free core remains installable with `pip install -e .`; MCP and TOML configuration are optional extras. This project is not published to PyPI, so an unqualified `pip install ai-memory-book` is not the documented installation method. [uv, pipx, and installer alternatives](docs/deployment.md).

## Bring your own conversations

```json
{
  "project": "atlas",
  "session_id": "cache-review",
  "task_id": "search-cache",
  "messages": [
    {"role": "user", "content": "What cache expiry did we agree on?"},
    {"role": "assistant", "content": "45 seconds, with revision invalidation."}
  ]
}
```

```bash
memory-book import session.json
memory-book watch add /absolute/path/to/exports --format canonical --project atlas
memory-book sync --once
memory-book recall "cache expiry" --project atlas --budget 2000 --json
memory-book export-book atlas --output ./atlas-book
```

Exports contain a Markdown table of contents, original evidence pages, and normalized source JSON. ChatGPT current-branch exports and supported native text logs have dedicated importers. Image/audio content and structured tool blocks are not reconstructed. [Input formats and limits](docs/integrations.md#import-formats).

## Shared data location

All configured clients use the same absolute database path, independent of their working directory.

| Platform | Default data directory |
|---|---|
| Linux | `$XDG_DATA_HOME/ai-memory-book`, or `~/.local/share/ai-memory-book` |
| macOS | `~/Library/Application Support/AI-Memory-Book` |
| Windows | `%LOCALAPPDATA%\AI-Memory-Book` |

Set `MEMORY_BOOK_HOME` for a portable data directory, `MEMORY_BOOK_DB` for a database override, or pass `--db` before the subcommand. **Upgrading from v0.1?** Its `.memory-book/memory.db` is not moved automatically. `doctor` reports it when present in your working directory; use that explicit path or follow [migration instructions](docs/deployment.md#upgrading-from-v010).

## Docker

The image's default command is a headless stdio MCP server. From a source checkout, build it and configure your MCP host to launch the following `docker run` command:

```bash
docker build -t ai-memory-book:local .
docker run --rm -i \
  --mount type=volume,src=ai-memory-book-data,dst=/data \
  ai-memory-book:local mcp
```

The named volume persists the archive across server processes. No HTTP port is published for MCP. Docker does not automatically gain access to host transcripts: capture requires explicit source mounts and configuration. The optional Compose reader shares this volume and publishes only on host loopback. [Docker commands and MCP configuration](docs/deployment.md#docker).

## Validation and optional modes

The latest default-path optimization preserves complete evidence payloads while
reducing pooled p95 across all 12 measured cohort/interface/character-budget
settings: **1.32%–13.65% in process and 1.25%–9.50% through actual MCP**.
All 56,784 timed calls, unchanged source/index checks, balanced run orders and
per-round exceptions remain in the [performance report](docs/default-recall-performance.md).

The current recommendation is **default score-aware lexical recall**. Optional
exact token limits, multi-fact coverage and local semantic candidates are
explicit choices for a workload and context budget.

The native token-budget validation covers **eight cohorts, 2,019 query
instances and 24,228 query/configuration pairs**. It records **251
complete-evidence gains, zero complete-evidence losses and zero losses of
previously fitting baseline blocks**. These are configuration-level counts.
Source, exact-budget, context-size and repetition checks passed. Filling more
of a small budget adds work; each report retains the paired latency costs.

| Capability | Current verification |
|---|---|
| Exact token budgets | Both reference tokenizers, three token caps, two character caps, source-preserving assembly and complete paired results |
| Optional semantic candidates | Four complete local-model cohorts; default stays lexical because the quality/cost tradeoff depends on the workload |
| Optional multi-fact coverage | Explicit `coverage=True` / `--coverage`; tested default/optional mode equivalence and published category-level results |
| Native competitor components | Executed claude-mem FTS, ai-memory hybrid and billion-context search with pinned source/runtime versions |
| Actual generated answers | 768 completed calls across two fixed cohorts; verified model identity, usage and per-question scores |
| Native workflow diagnostic | 42 captured sessions, 42 consolidation attempts and 72 answers; native failures and their costs retained |

[All result tables and reproducible artifacts](benchmarks/README.md) ·
[Native token-budget protocol](docs/native-budget-evaluation.md) ·
[Semantic setup and measured tradeoffs](docs/semantic-retrieval.md) ·
[Coverage details](benchmarks/RESULTS-conjunctive-recall.md) ·
[Real-answer results](benchmarks/RESULTS-local-answers.md) ·
[Native workflow results](benchmarks/RESULTS-full-workflow.md) ·
[Completion audit](docs/continuation-status.md).

The comparison above uses a fixed shared-page policy. Native API packing,
semantic ranking, generated-answer scores and capture/consolidation workflows
are measured separately. Public and reused synthetic questions are regression
data; the externally authored HotpotQA diagnostic broadens coverage within a
defined scope. Full reports retain the measured limitations, unsupported
questions, errors, negative results and historical comparisons.

## Optional archive inspection

For human inspection or troubleshooting, start the local reader explicitly:

```bash
memory-book serve
```

It opens an HTTP listener at [http://127.0.0.1:8765](http://127.0.0.1:8765); open that address in your browser. Agent capture and MCP recall work without it. The **EN / 中文** switch changes interface labels while original conversations retain their language. [Desktop screenshot using fictional conversations](docs/assets/reader-desktop-en.png) · [Container reader setup](docs/deployment.md#docker).

## Development and verification

```bash
python -m pip install -e ".[mcp,clients,benchmark]"
python -m unittest discover -s tests -v
python tests/installer_smoke.py --with-extras
```

The test matrix covers Python 3.10/3.12/3.13, actual MCP stdio, the browser reader, Linux/macOS/Windows installers and container persistence. [Current CI](https://github.com/Afloat16/AI-Memory-Book/actions/workflows/ci.yml) · [Completed validation and reproduction](docs/validation.md).

Implementation tests and benchmark experiments have separate records. Configuration fixtures do not establish an interactive test in every vendor application.

## Design references

We studied [claude-mem](https://github.com/thedotmack/claude-mem), [billion-context](https://github.com/ranxianglei/billion-context), [ai-memory](https://github.com/akitaonrails/ai-memory), [PageIndex](https://github.com/VectifyAI/PageIndex), and [RAPTOR](https://arxiv.org/abs/2401.18059). The agent-facing design combines hierarchical source addresses, one setup command, an optional capture worker, and budgeted MCP recall. This implementation uses local transcript polling plus on-demand retrieval; it does not claim to reproduce another project's hooks, request proxy, observer model, or session-start injection. See [research notes](docs/research.md).

Independently implemented under the [MIT License](LICENSE). Contributions with a minimal reproduction and measurable validation are welcome: [CONTRIBUTING.md](CONTRIBUTING.md).
