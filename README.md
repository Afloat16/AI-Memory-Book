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
| **No model call to create or search memory** | Local Python + SQLite indexing and lexical retrieval; no per-turn summarization bill, embedding download, or separate database service in the core. Your answering model remains your choice. |
| **Original evidence with citations** | Recall returns source text and project/session/turn references. Exact character spans and full pages remain available when you need to verify a decision. |
| **Useful context in one MCP call** | `recall_memory` assembles bounded evidence directly. Project, chapter and session filters help the agent focus on the work at hand. |
| **Exact context limits when you need them** | An optional named-tokenizer cap includes citations and separators, alongside the character cap. Fitting original evidence blocks stay intact; remaining capacity can carry additional source sentences. |
| **One archive across clients** | Supported clients point to the same local database. Opt-in background capture keeps supported text transcripts available for later tasks. |
| **A small operational footprint** | The default worker and MCP server run without an HTTP listener; the optional reader, export tools, and source-preserving migrations make the archive inspectable. |

See the [agent workflow](docs/agent-guide.md), [capture and deployment guide](docs/deployment.md), and [source/migration checks](benchmarks/RESULTS-recall-score-quality.md#8-source-preserving-schema-migration).

### Measured retrieval advantage

At a **1,024-token `cl100k_base` cap**, Book delivers more complete original evidence than all three tested native retrieval components:

| Frozen retrieval component | Evidence recall ↑ | Complete evidence ↑ | Mean context tokens ↓ |
|---|---:|---:|---:|
| **AI-Memory-Book, score-aware `0ab49d4`** | **69.54%** | **72.88%** | 827.2 |
| [claude-mem `2cfed76`](benchmarks/results/claude-mem-components-public.md), native SQLite FTS | 66.24% | 70.11% | 804.8 |
| [billion-context `dc041dd`](benchmarks/RESULTS-recall-score-quality.md#6-native-components-common-context-and-their-cost-boundaries), search kernel | 65.48% | 68.72% | 862.6 |
| [ai-memory v3.4.5](benchmarks/RESULTS-recall-score-quality.md#6-native-components-common-context-and-their-cost-boundaries), local hybrid | 64.47% | 66.72% | **779.3** |

Complete evidence is **2.77 percentage points higher than claude-mem FTS**, **4.16 points higher than billion-context**, and **6.16 points higher than ai-memory** at this setting. Book uses 4.1% fewer context tokens than billion-context; claude-mem and ai-memory use fewer than Book.

**Comparable quality inputs:** the same 1,339 source pages, all 1,015 eligible text-only LoCoMo questions, project scope, top-five candidates, and one citation/whole-page packer. Complete evidence is scored over **649 answerable questions**; evidence recall over **788 required source utterances**; mean tokens over all 1,015 questions. Every required utterance must survive intact with its original source span. The 366 unsupported questions remain in the reports; a nonempty retrieval is not an answer or abstention score.

The claude-mem experiment executes unmodified upstream `SessionStore` / `SessionSearch` under pinned Bun, with **3,045 successful native calls** and six tokenizer/budget settings. Its observer, Chroma, host injection, MCP serialization and generated answers are outside this component test. The other two component results retain their own pinned implementations and boundaries. [Complete comparison and all costs](docs/comparison.md) · [claude-mem method and report](docs/claude-mem-component-evaluation.md).

These are **source-delivery measurements on regression data**, not whole-product rankings. The current native token API and optional semantic mode have separate packing/ranking experiments below; their scores do not replace this frozen table.

### Compare quality, speed and deployment

The default memory path needs **no generative writer, embedding download or separate database service**. It preserves original source addresses and delivers bounded evidence in one MCP recall. That operational combination is useful independently of any single benchmark win.

| Executed operation | p50 | p95 | Measured boundary |
|---|---:|---:|---|
| Book in-process recall, historical frozen run | 2.945 ms | 4.555 ms | Recall and native context assembly |
| **Book actual MCP recall**, same historical run | **5.764 ms** | **9.181 ms** | Official SDK, subprocess stdio and returned JSON |
| billion-context search + bridge, historical run | 1.298 ms | 2.413 ms | Search; native decompression excluded |
| ai-memory v3.4.5 local hybrid, historical run | 29.720 ms | 37.315 ms | HTTP/MCP query; follow-up reads excluded |
| claude-mem native FTS + Bun bridge, 2026-11-12 runner | 59.664 ms | 100.450 ms | Full observation-row JSON; MCP and observer excluded |

Billion is faster at its measured search boundary. The claude-mem run used a different host from the historical rows. Different hosts and interfaces do not establish a whole-product speed multiplier.

Against **our own v0.2.1 at the same actual MCP boundary**, the frozen Book runtime returns **54.7% fewer response tokens** (3,233.5 → 1,465.1 `o200k_base`) and has a **31.1% lower observed first-call p50** (8.371 → 5.764 ms). Under ai-memory's separately measured search-plus-all-five-reads policy, mean payload tokens are 942.5 + 1,913.7 = **2,856.2**; its content-only tokens are **2,574.6**. An agent can choose fewer reads. Those two token surfaces are labeled separately in the [cost table](docs/comparison.md); the old 43.1% mixed-surface comparison is not used as a complete-response saving claim.

The comparison guide also covers **Mem0, Graphiti, PageIndex and Letta**, with dated popularity snapshots, official sources and operational boundaries. Their unexecuted workflows have no invented scores. ai-memory also supports a zero-LLM default path; claude-mem supports local model providers.

## Get started

You need **Python 3.10+ with SQLite FTS5**. The installer creates an isolated environment and includes MCP and client-configuration dependencies. This route does not require a Git checkout, Node.js, an embedding server, or a database server.

### Choose a version

| Version | What you get | How to use it |
|---|---|---|
| **Published experimental release v0.2.1** | Agent-first MCP, shared local memory and optional headless background capture | Use the pinned installers below. |
| **Available v0.3 development source** | Score-aware retrieval, compact cited evidence, optional exact token budgets, multi-fact coverage, optional local semantic retrieval and the paired-answer evaluation runner | Use the [source checkout](#try-it-without-connecting-a-client) on `main`. |
| **Frozen comparison runtime `0ab49d4`** | The exact source used for the retrieval and MCP cost figures above | Follow the [reproduction guide](benchmarks/RESULTS-recall-score-quality.md#11-reproduction-and-artifact-index). |

The validated continuation, including exact token budgets, was merged into `main` through [PR #1](https://github.com/Afloat16/AI-Memory-Book/pull/1) at [`ce7837f`](https://github.com/Afloat16/AI-Memory-Book/commit/ce7837fb8db7c221f39e27a531f2383385782eb1). The installers below still use the published **v0.2.1**; there is no `v0.3.0` release tag yet. Use the `main` source checkout to try the additional capabilities.

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

**Choose the context budget:** `budget_chars` in Python/MCP and `--budget` in the CLI cap the assembled context in characters. The development source also supports an **exact optional token cap** with `budget_tokens` / `--budget-tokens` and either `cl100k_base` or `o200k_base`. Both caps include citations and separators in `context`; outer JSON metadata, tool schemas and the rest of the conversation are outside them. Install the `tokens` extra and add these arguments to the recall call:

```bash
python -m pip install -e ".[tokens]"
memory-book recall "cache expiry and retry window" --project atlas \
  --budget 4000 --budget-tokens 512 --tokenizer cl100k_base --json
```

For MCP, add `"budget_tokens": 512` and `"tokenizer": "cl100k_base"` to `arguments`; Python uses the same parameter names. The response reports the exact `context_tokens` and tokenizer version. `estimated_tokens` remains a character-based estimate. Without the optional token cap, the dependency-free character path is unchanged. First-time vocabulary initialization may require a public download; offline deployments should preload it. [API, offline setup, source-preservation contract and costs](docs/token-budget.md).

The historical competitor tables use a shared **whole-page benchmark packer**. The new API assembles **native excerpts and intact source units**; its results have a separate baseline and do not retroactively change those tables. See [budget measurements and remaining gaps](#what-remains-to-improve).

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

On Windows, activate `.venv\Scripts\Activate.ps1`, or call `.venv\Scripts\python.exe` directly. To reproduce the frozen measurements, check out `0ab49d4f2be6aabe5e51c3314bb9369041af5369` before installing and follow the [benchmark preparation guide](benchmarks/RESULTS-recall-score-quality.md#11-reproduction-and-artifact-index). The dependency-free core remains installable with `pip install -e .`; MCP and TOML configuration are optional extras. This project is not published to PyPI, so an unqualified `pip install ai-memory-book` is not the documented installation method. [uv, pipx, and installer alternatives](docs/deployment.md).

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

### Completed native token-budget matrix

The frozen candidate `407cda1` was measured against `5abc85e` across **eight cohorts, 2,019 query instances, and 24,228 paired query/configuration cases**: five synthetic seeds, the 1,015-question public set, the 36-question authored diagnostic and 128 external HotpotQA questions. Each cohort covers two character caps, both reference tokenizers, three token caps and three repetitions.

Across these paired cases, **251 gain complete evidence, zero lose complete evidence, and zero lose a baseline block that already fitted**. These are query/configuration counts, not 251 distinct questions. Every cohort's source, scope, exact-budget and repetition checks passed.

At **8,000 characters and 512 `cl100k_base` tokens**:

| Cohort | Baseline complete evidence | Native token API | Paired p95, baseline → candidate |
|---|---:|---:|---:|
| Public LoCoMo, 649 answerable / 1,015 total | 65.33% | **66.41%** | 7.120 → 10.076 ms |
| Synthetic regression seed 883, 152 answerable / 168 total | 68.42% | **84.21%** | 12.550 → 26.448 ms |
| Authored diagnostic, 30 answerable / 36 total | 86.67% | 86.67% | 1.644 → 1.721 ms |
| External HotpotQA, all 128 answerable | 34.38% | **35.16%** | 7.873 → 9.188 ms |

Public `o200k_base` at 512 tokens improves **65.95% → 66.72%**, with five complete-question gains and no losses. At 1,024 and 2,048 tokens, public complete evidence remains 72.88%. The API spends otherwise unused space on intact source units; the CPU cost is real. Keep the timings within each paired cohort: the cohorts ran on different hosts.

[Protocol and reproduction](docs/native-budget-evaluation.md) · [Public native report](benchmarks/results/native-completion-regression-public1015.md) · [External native report](benchmarks/results/native-completion-external-hotpot128.md).

### Optional local semantic retrieval: measured tradeoffs

Semantic candidates are **explicitly enabled**; the default remains lexical. The four registered cohorts now have actual local MiniLM measurements. At 512 `cl100k_base` tokens and 8,000 characters:

| Cohort | Lexical complete evidence | Semantic complete evidence |
|---|---:|---:|
| Synthetic development seed 61 | **85.53%** | 63.16% |
| Authored diagnostic, 30 answerable | 86.67% | **100.00%** |
| Public LoCoMo, 649 answerable | **66.41%** | 62.56% |
| External HotpotQA, 128 answerable | **35.16%** | 33.59% |

The authored low-overlap subset improves **2/6 → 6/6**. On public low-overlap questions, complete evidence improves **46.01% → 47.55%**, and cross-session complete evidence **10.53% → 15.79%**. Those subset gains coexist with **39 complete-question gains and 64 losses overall** on the public 512-token setting. At 1,024 tokens, external HotpotQA improves **48.44% → 50.00%**, while public complete evidence falls **72.88% → 71.49%**. Synthetic low-overlap questions remain unresolved.

Costs are separate: the pinned model/tokenizer download totals **127,535,388 bytes**. On the public semantic runner, model load took 1.271 s and index build 116.554 s; lexical/semantic query p50 was **8.078 / 18.074 ms**, p95 **10.184 / 22.691 ms** at 512 tokens. This is not evidence for making semantic mode the default.

[Setup, measured cases and model/index costs](docs/semantic-retrieval.md) · [Public semantic report](benchmarks/results/semantic-final-regression-public1015.md) · [External semantic report](benchmarks/results/semantic-final-external-hotpot128.md).

### What remains to improve

The historical **whole-page** 512-token regression, **66.72% → 66.26%** with `cl100k_base`, remains in its original report. The native API above uses another delivery policy and a separate baseline; its no-loss contract does not erase that historical result. Some synthetic tail latencies rise substantially.

Low-overlap semantics and evidence spread across distant sessions are still difficult. The semantic experiment exposes gains and losses rather than establishing a general semantic memory system. A retrieved context may be nonempty even when no answer is supported; only a generation experiment can assess the answering model's response.

The public questions and repeated synthetic templates are regression data. The frozen HotpotQA transfer cohort contributes **128 independently authored multi-hop questions, 1,272 supplied paragraphs and 306 support facts**, with all supplied distractor paragraphs retained. It is a scoped external diagnostic; all questions are answerable, and neither its size nor its domain mix establishes universal generalization. Once inspected, it becomes regression evidence for further tuning.

### Optional coverage for multi-fact questions

The development version adds **`coverage=True` / `--coverage`**, disabled by default. It recognizes explicit `and`, `和`, `以及` and `并且` clauses, preserves the original top result, and reserves results for additional clauses within the scoped candidate set. This can help when several pages repeat one subject while another requested fact is missing:

```bash
memory-book recall "cache expiry and retry window" --project atlas --coverage --budget 2000
```

MCP callers set `"coverage": true` on `recall_memory`; Python callers pass `coverage=True` to `MemoryBook.recall`. The option requires book ranking and cannot be combined with CLI `--flat`.

In the [frozen automatic-clause experiment](benchmarks/RESULTS-conjunctive-recall.md), multi-section complete evidence improves **0/16 → 8/16** per synthetic regression seed at 8,000 characters. But public complete evidence stays **72.88%**, and common-full-page completeness at 512 `cl100k_base` tokens declines **66.26% → 65.79%**. The public MCP p95 also rises **9.564 → 13.510 ms**. The new 36-question authored diagnostic has equal complete evidence (**86.67%**) in both versions. These tradeoffs are why coverage is explicit rather than the default. This is a clause-coverage heuristic, with no demonstrated semantic paraphrase gain. Frozen automatic-mode timings are separate from the final opt-in API build.

[Independent mode checks](benchmarks/reports/coverage-mode-equivalence.json) compare **2,774 complete payloads per mode** against the prior default and frozen experiment, with **zero differences** after excluding only latency. The prior 512-token deficit remains a separate improvement target.

### Actual generated answers and native workflow

The registered local-model jobs are executing independently of the chat workspace: 128 LoCoMo and 128 HotpotQA questions, three retrieval modes and **768 planned actual answer attempts**. A separate 42-session/36-question Book-versus-native-ai-memory workflow measures capture, explicitly enabled consolidation, retrieval, follow-up reads and **72 planned answer attempts**. These stages use the pinned Qwen2.5-0.5B model and verified llama.cpp process; transport fixtures are not counted as model calls.

Results will be claimed only after the strict report assessors check the completed matrices, request ledgers, model proofs and cost accounting. The [continuation record](docs/continuation-status.md) identifies the live jobs and durable result branches. The [answer guide](docs/answer-evaluation.md) gives the exact registered commands.

[Historical score-aware report](benchmarks/RESULTS-recall-score-quality.md) · [Coverage experiment](benchmarks/RESULTS-conjunctive-recall.md) · [First frozen round](benchmarks/RESULTS-recall-quality.md) · [Comparison and token-surface clarification](docs/comparison.md).

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

The runtime at [`b36f044`](https://github.com/Afloat16/AI-Memory-Book/commit/b36f044651553d75485bd26801ef3f1f65e393bb) passed **266 tests**, with no failures or skips, using MCP, client, and benchmark extras. Its [push workflow](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43075055048) and [PR workflow](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43075068353) each passed **9/9 jobs**, covering Python 3.10/3.12/3.13, actual MCP stdio, the browser reader, Linux/macOS/Windows installers, and container persistence. The PR workflow succeeded after its initially cancelled macOS job was retried.

The later native-budget checkpoint [`e70bc3d`](https://github.com/Afloat16/AI-Memory-Book/commit/e70bc3d2581ff96959711509b3eef11ab14f564d) passed **294 tests** in its MCP CI job. Its [push workflow](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43152979344) and [PR workflow](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43152987680) each passed **9/9 jobs**. That checked continuation is now on `main` through [PR #1](https://github.com/Afloat16/AI-Memory-Book/pull/1); test counts and benchmark figures remain attributed to their named commits. [GitHub Actions status](https://github.com/Afloat16/AI-Memory-Book/actions) · [Validation details and historical runs](docs/validation.md). Configuration fixtures do not establish that every vendor application or login manager has been interactively verified.

## Design references

We studied [claude-mem](https://github.com/thedotmack/claude-mem), [billion-context](https://github.com/ranxianglei/billion-context), [ai-memory](https://github.com/akitaonrails/ai-memory), [PageIndex](https://github.com/VectifyAI/PageIndex), and [RAPTOR](https://arxiv.org/abs/2401.18059). The agent-facing design combines hierarchical source addresses, one setup command, an optional capture worker, and budgeted MCP recall. This implementation uses local transcript polling plus on-demand retrieval; it does not claim to reproduce another project's hooks, request proxy, observer model, or session-start injection. See [research notes](docs/research.md).

Independently implemented under the [MIT License](LICENSE). Contributions with a minimal reproduction and measurable validation are welcome: [CONTRIBUTING.md](CONTRIBUTING.md).
