# AI-Memory-Book

**Background memory for AI agents. Projects become books, tasks become chapters, and agents retrieve the cited evidence they need to continue working.**

[简体中文](README.zh-CN.md) · [Agent guide](docs/agent-guide.md) · [Installation & background mode](docs/deployment.md) · [Client compatibility](docs/integrations.md) · [Measured results](benchmarks/EXPERIMENTS.md) · [Releases](https://github.com/Afloat16/AI-Memory-Book/releases)

AI-Memory-Book gives AI agents a shared, local memory of earlier work. After you connect a client and opt in to capture, a background worker indexes supported conversations. When a task depends on a previous decision, constraint, or unfinished step, the agent can call MCP once, receive bounded original evidence with source references, and continue the task. It does not need to read a directory or an entire conversation first.

The primary interface is **MCP for the agent**. Background capture runs headlessly by default; the optional web reader is for inspecting and debugging the archive. The server supplies guidance for conditional recall, while the host and model control tool invocation and permissions. Automatic use in every client or on every question is not guaranteed.

**v0.2.1 · Experimental · MIT · Local storage · No memory-service API key**

## Get started

You need **Python 3.10+ with SQLite FTS5**. The installer creates an isolated environment and includes MCP and client-configuration dependencies. This route does not require a Git checkout, Node.js, an embedding server, or a database server.

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

The shared Python installer also works on macOS/Linux. A PowerShell wrapper is available in [`scripts/install.ps1`](scripts/install.ps1). Installation does not change your shell profile or execution policy.

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

The response contains `context`, page IDs, and source references such as `project`, `session_id`, `turn_index`, and character spans. With the [example archive](examples/conversations.json), the cache review records a change from 300 to 45 seconds while retaining revision invalidation. The agent can cite `atlas / atlas-cache-review / turn 0`, check the source date, and use that decision in the implementation. Historical text remains evidence to assess, including possible outdated or conflicting decisions.

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

A reproducible **v0.2.0** local sample with 300 synthetic files measured unchanged scans at a **36.95 ms median** across eight cycles, with zero reimports; changing one file updated one session and skipped 299. Scans still write state/heartbeat data. This is a small warm-cache measurement, not a CPU, battery, or large-archive guarantee, and has not been relabeled as a v0.2.1 measurement. [Method and raw results](docs/validation.md#v020-capture-overhead-sample).

## Try it without connecting a client

From a source checkout:

```bash
git clone https://github.com/Afloat16/AI-Memory-Book.git
cd AI-Memory-Book
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[mcp,clients]"

memory-book import examples/conversations.json
memory-book recall "搜索缓存为什么改成45秒？" --project atlas
```

On Windows, activate `.venv\Scripts\Activate.ps1`, or call `.venv\Scripts\python.exe` directly. The dependency-free core remains installable with `pip install -e .`; MCP and TOML configuration are optional extras. This project is not published to PyPI, so an unqualified `pip install ai-memory-book` is not the documented installation method. [uv, pipx, and installer alternatives](docs/deployment.md).

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

## Evidence, costs, and limitations

The published **v0.1.0 retrieval experiments** compare session, turn, and adaptive segmentation under identical budgets. Two heldout synthetic datasets each contain 112 sessions, 1,408 user turns, 168 queries, and about 1.143 million source characters. At an 8,000-character budget:

| Segmentation | Evidence recall | Complete evidence | Mean context chars | Uncached local p95 |
|---|---:|---:|---:|---:|
| Session | 69.32–69.89% | 73.68–74.34% | 5,411 | 112.87–141.15 ms |
| Turn | 64.77–65.34% | 59.87–60.53% | 3,879–3,881 | 22.41–24.03 ms |
| Adaptive | **77.27%** | **78.95%** | **3,701–3,706** | **7.42–7.46 ms** |

Ranges show two individual seeds, not confidence intervals. Timings disable result caching but retain SQLite/OS page caches; they exclude startup, watcher work, MCP transport, networking, and model inference. Each retrieved unit contributes one relevant window; an unmeasured whole-session multi-window implementation could narrow the gap. These are synthetic retrieval results, not comparisons against other memory products or LLM answer scores. v0.2.0 added deployment and capture; v0.2.1 makes the agent workflow and headless default explicit. Neither relabels earlier retrieval measurements as new benchmarks.

Measured limits remain: low-overlap paraphrases had zero recall; distant two-fact queries retrieved only 25% of required evidence and completed none; old evidence preceded current evidence in half of current-decision queries. Directory re-ranking did not improve aggregate recall. The 2,000-character budget did not show a universal win. [Full experiments, failures, and raw results](benchmarks/EXPERIMENTS.md).

`--budget` limits the assembled context in **characters**, including citation headings, not transport JSON or exact model tokens. The engine uses lexical FTS rather than embeddings. It has no authoritative conflict resolver, cloud sync, public multi-user server, or guaranteed automatic context injection. Client permission decisions remain in the client.

## Optional archive inspection

For human inspection or troubleshooting, start the local reader explicitly:

```bash
memory-book serve
```

It opens an HTTP listener at [http://127.0.0.1:8765](http://127.0.0.1:8765); open that address in your browser. Agent capture and MCP recall work without it. The **EN / 中文** switch changes interface labels while original conversations retain their language. [Desktop screenshot using fictional conversations](docs/assets/reader-desktop-en.png) · [Container reader setup](docs/deployment.md#docker).

## Development and verification

```bash
python -m pip install -e ".[mcp,clients]"
python -m unittest discover -s tests -v
python tests/installer_smoke.py --with-extras
```

The **v0.2.0** candidate passed [all nine CI jobs](https://github.com/Afloat16/AI-Memory-Book/actions/runs/42998379672), including the 158-test suite with optional extras, Python 3.10/3.12/3.13 core checks, actual MCP stdio communication, browser interactions, Linux/macOS/Windows installers, and container MCP/reader/volume behavior. These counts describe that candidate; [validation details](docs/validation.md) track subsequent patch verification. Native service definitions and configuration merges have focused tests; successful configuration generation does not prove every vendor app or login manager accepted it. [GitHub Actions](https://github.com/Afloat16/AI-Memory-Book/actions).

## Design references

We studied [claude-mem](https://github.com/thedotmack/claude-mem), [billion-context](https://github.com/ranxianglei/billion-context), [ai-memory](https://github.com/akitaonrails/ai-memory), [PageIndex](https://github.com/VectifyAI/PageIndex), and [RAPTOR](https://arxiv.org/abs/2401.18059). The agent-facing design combines hierarchical source addresses, one setup command, an optional capture worker, and budgeted MCP recall. This implementation uses local transcript polling plus on-demand retrieval; it does not claim to reproduce another project's hooks, request proxy, observer model, or session-start injection. See [research notes](docs/research.md).

Independently implemented under the [MIT License](LICENSE). Contributions with a minimal reproduction and measurable validation are welcome: [CONTRIBUTING.md](CONTRIBUTING.md).
