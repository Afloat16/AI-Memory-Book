# AI-Memory-Book

**Keep engineering decisions available across projects, sessions, and AI clients.**

AI-Memory-Book gives coding agents a shared local archive of earlier work. Projects become books, tasks become chapters, and a scoped MCP query returns original evidence with source references—so the agent can recover a decision, check a correction, and continue the task.

[简体中文](README.zh-CN.md) · [Quick start](#quick-start) · [Default configuration](#default-configuration) · [Measured results](#measured-results) · [v0.4.0 release](https://github.com/Afloat16/AI-Memory-Book/releases/tag/v0.4.0)

**v0.4.0 · Engineering memory with original evidence · MIT · Python 3.10+ · Local SQLite**

## What it adds to your workflow

- **Recover the reasoning behind earlier work.** Keep decisions, constraints, failed attempts, and original conversations addressable by project, session, turn, and page.
- **Find corrections in a long conversation.** Explicit current/latest queries use source turn order to help surface later corrections. Distinct source text gets priority over repeated copies within the same project and task.
- **Keep similar projects in scope.** Pass the known project ID when recalling its history; multiple supported clients can use the same archive.
- **Run a lightweight memory layer.** Default ingestion and lexical retrieval make no model calls and need no embedding download, database server, or memory-service API key.

Capture and retrieval are separate. Opt-in background capture updates supported transcripts; an agent recalls when history matters and opens a cited page only if it needs more detail. [Agent workflow and source semantics](docs/agent-guide.md).

## Quick start

You need **Python 3.10+ with SQLite FTS5**. The installer downloads the release wheel into an isolated environment with MCP/client dependencies. No Git checkout or Node.js is needed.

**macOS / Linux**

```bash
curl -fsSLo install-memory-book.sh https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/v0.4.0/scripts/install.sh
bash install-memory-book.sh
```

**Windows PowerShell**

```powershell
Invoke-WebRequest https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/v0.4.0/scripts/install.py -OutFile install-memory-book.py
py -3 .\install-memory-book.py
```

**Connect your agent**

```bash
memory-book setup --client claude-code --capture --background
memory-book doctor
```

If `memory-book` is not on your PATH yet, use the full launcher path printed by the installer. Restart the client and ask: **“Recall the current decision for this project, cite the original source, and continue the task.”**

Replace `claude-code` with your [client profile](docs/integrations.md#supported-profiles), or repeat `--client` to connect more clients. MCP profiles include Claude Code/Desktop, Codex, Gemini, Cursor and others. Native transcript capture supports Claude Code, Codex, Gemini and legacy Python Kimi; other profiles use explicit imports or enabled MCP writing.

`--capture` opts in to existing and future supported text transcripts. Omit it for MCP access alone. The host and model control tool invocation; connecting MCP does not install an automatic recall hook.

**Upgrade:** re-run the installer, then your `setup` command with the same client and capture options. Existing memory and the previous environment are retained. [Upgrade details](docs/deployment.md#upgrading).

## Default configuration

v0.4.0 uses **native lexical recall, a 2,400-character context budget, and up to five results**. There is no token cap by default. The character budget includes citation headings and separators in `context`; it does not cap the complete JSON response.

Start with one query scoped to the active project. For example, call the MCP tool `recall_memory` with:

```json
{
  "query": "current gradient accumulation steps",
  "project": "your-project-id",
  "budget_chars": 2400,
  "limit": 5
}
```

Replace `your-project-id` with an existing project ID. MCP returns compact source references; use the returned page ID to read more evidence when needed. The same configuration is available from the CLI:

```bash
memory-book projects
memory-book recall "current gradient accumulation steps" \
  --project your-project-id --budget 2400 --limit 5
```

Use “original” or a specific historical question when you need the earlier decision. Current-query preferences help rank evidence; they do not make every later mention authoritative. [Handling conflicting or missing evidence](docs/agent-guide.md#when-evidence-is-insufficient).

## Measured results

The default retrieval profile was evaluated on **80 chronological engineering questions across eight projects and four algorithm families**. All cases are retained. The table compares v0.3.4 with the retrieval implementation adopted in v0.4.0, using **2,400 characters and five results**; result caching was disabled for timing.

| Native retrieval metric | v0.3.4 baseline | v0.4.0 profile |
|---|---:|---:|
| Complete evidence in answerable cases | 44/72 · 61.11% | **68/72 · 94.44%** |
| Fixed known-policy consumer: all checks pass | 20/48 · 41.67% | **44/48 · 91.67%** |
| Local recall p95, including context assembly | 1.986 ms | 2.056 ms · **+3.54%** |

Evidence completeness improves with a small local p95 increase. The consumer extracts an explicit recorded policy and applies handwritten algorithm variants; its pass rate is not generated-code accuracy.

A separate **shared-page component comparison** gives both engines the same complete source pages, project scope, top-five limit, and common whole-block packing at 2,400 characters. Book returns complete evidence for **68/72 cases (94.44%)**, versus **64/72 (88.89%)** for the [pinned billion-context search kernel](https://github.com/ranxianglei/billion-context/tree/9674cfafbc78c50245ae0d887483d3d6ce880c15): six case gains and two losses. This measures that pinned component and packing boundary, not the complete products or their latest versions.

**These are synthetic development replays, not measurements of coding-LLM productivity.** Full budget results, failed cases, timing boundaries, and tradeoffs are retained in the [detailed engineering report](docs/engineering-memory-results.md), with [raw evidence and recomputation](benchmarks/results/engineering-memory-20261115/). The [evaluation protocol](docs/engineering-memory-evaluation.md) defines the next step: real project replay with hidden tests and time to a correct patch.

Earlier measurements remain available in the [v0.3.4 startup record](docs/releases/v0.3.4.md), [full HotpotQA component comparison](benchmarks/results/round6-comparison-43601518020-1/report.md), and [benchmark history](benchmarks/README.md).

## Documentation

| Task | Guide |
|---|---|
| Connect clients or import conversations | [Client profiles and formats](docs/integrations.md) |
| Install, upgrade, use Docker, or manage capture | [Deployment](docs/deployment.md) |
| Recall, cite sources, and resolve missing evidence | [Agent guide](docs/agent-guide.md) |
| Inspect the archive in a browser | Run `memory-book serve`, then open [127.0.0.1:8765](http://127.0.0.1:8765) |
| Configure advanced retrieval options | [Token budgets](docs/token-budget.md) · [Semantic retrieval](docs/semantic-retrieval.md) · [Reference formats](docs/indexed-references.md) |
| Review engineering experiments or contribute | [Results](docs/engineering-memory-results.md) · [Validation](docs/validation.md) · [Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md) |

The archive is local, unencrypted data. Evidence returned to an AI client enters that client's model context. The optional browser reader is for inspection; normal MCP and capture need no HTTP listener. [Data and configuration locations](docs/deployment.md#data-and-configuration-paths).

Independently implemented under the [MIT License](LICENSE). [CI](https://github.com/Afloat16/AI-Memory-Book/actions/workflows/ci.yml).
