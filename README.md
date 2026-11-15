# AI-Memory-Book

**Give coding agents engineering memory they can verify and continue from.**

Projects are books, tasks are chapters, and evidence is a page you can open. AI-Memory-Book preserves normalized original text conversations, so an agent can recover constraints, parameter corrections, and failed attempts after a session or client switch, cite the source, and continue the work.

[简体中文](README.zh-CN.md) · [Quick start](#quick-start) · [2400-character results](#2400-character-results) · [Open-source comparison](#open-source-comparison)

**v0.4.0 · MIT · Python 3.10+ · Local SQLite / FTS5**

## Engineering advantages

- **Recover decisions together with their reasons.** Locate evidence by project, task, session, and original turn, retaining page IDs and source references. Open the original page to check a boundary condition, error message, or failed approach during code review or a task handoff.
- **Retrieve current corrections and historical reasoning.** Explicit current/latest queries use comparable turns within a session to surface later corrections and favor distinct source text over repeated copies. Historical questions retain historical query semantics; ranking does not determine which statement is authoritative.
- **Spend bounded context on engineering constraints.** Apply project scope before retrieval and context assembly. The default is 2400 characters and up to five results; read further only when evidence is missing. This supports recovering implementation conventions, data-split rules, and edge cases together.
- **Continue across existing clients.** Supported clients such as Claude Code, Codex, and Gemini can share the same database. Switching tools does not require abandoning the archived project history. MCP configuration and native transcript capture have separate [support matrices](docs/integrations.md#supported-profiles).
- **Keep the memory layer simple to operate.** Default ingestion and lexical retrieval make no model calls and need no embedding model, database server, or memory-service API key. Background capture skips unchanged files; stable session IDs and content hashes prevent duplicate ingestion. Changed sessions are replaced transactionally; existing client configuration files are backed up before changes.

When resuming a long-running task, ask which constraints the current implementation must satisfy, follow the citations to check later corrections and failed attempts, and then continue editing. Recovering a convention, checking its source, and continuing implementation gives a task handoff an explicit evidence trail. [Source semantics and agent guidance](docs/agent-guide.md).

## Quick start

You need **Python 3.10+ with SQLite FTS5**. The installer uses an isolated environment with MCP/client dependencies. No Git checkout or Node.js is required.

**macOS / Linux**

~~~bash
curl -fsSLo install-memory-book.sh https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/v0.4.0/scripts/install.sh
bash install-memory-book.sh
~~~

**Windows PowerShell**

~~~powershell
Invoke-WebRequest https://raw.githubusercontent.com/Afloat16/AI-Memory-Book/v0.4.0/scripts/install.py -OutFile install-memory-book.py
py -3 .\install-memory-book.py
~~~

**Connect and check**

~~~bash
memory-book setup --client claude-code --capture --background
memory-book doctor
~~~

Replace `claude-code` with your [client profile](docs/integrations.md#supported-profiles), or repeat `--client` to connect more clients. Keep the capture flags only for profiles with native capture support; omit both `--capture` and `--background` for other profiles. If the command is not on PATH, use the full launcher path printed by the installer, then restart your client.

`--capture` opts in to existing and future supported text transcripts; `--background` installs and starts the user service. Omit both flags for MCP configuration alone. The host and model control tool invocation, so connecting MCP does not guarantee automatic recall. To upgrade, rerun the installer and your setup command. [Deployment guide](docs/deployment.md#upgrading).

## Default configuration

The defaults are **native lexical retrieval, 2400 characters, and up to five results**, with no additional token cap. The character allowance includes citation headings and separators inside `context`; it does not cap the complete JSON response or model tokens.

Example call to the MCP tool `recall_memory`:

~~~json
{
  "query": "current gradient accumulation steps",
  "project": "your-project-id",
  "budget_chars": 2400,
  "limit": 5
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

The current default entry point matches the complete non-timing responses from explicit 2400/5 calls and frozen outputs on all 80 questions. The numbers below come from that retained, reproducible development experiment; repeated calls add timing samples, not independent quality cases. [Default-equivalence verification](benchmarks/reports/v040-release-preparation/default-profile/report.json).

| Strategy | Evidence-span recall | Complete evidence | Policy checks passing | Mean characters |
|---|---:|---:|---:|---:|
| **AI-Memory-Book** | **76/80 · 95.00%** | **68/72 · 94.44%** | **44/48 · 91.67%** | **1812.0** |
| Scoped flat FTS | 58/80 · 72.50% | 50/72 · 69.44% | 26/48 · 54.17% | 1803.7 |
| Recent history within budget | 64/80 · 80.00% | 56/72 · 77.78% | 32/48 · 66.67% | 2260.9 |

Book covers **18 more complete-evidence cases** than flat FTS, a **25-percentage-point** difference. Against recent history it covers **12 more cases** while returning approximately **19.9% fewer characters** on average. Flat FTS is this repository's baseline using the same scope, index, and packer. Recent history uses resident text, shorter citation headings, and no top-five limit; it is a practical strategy comparison. [Native replay data](benchmarks/results/engineering-memory-20261115/final/2-candidate-workflow/report.json).

### Where the engineering benefit appears

Complete-evidence case counts at 2400 characters, retaining all nine answerable categories:

| Scenario | Book | Flat FTS | Recent history |
|---|---:|---:|---:|
| Later decision correction | **8/8** | 2/8 | 8/8 |
| Recovery after a long gap | **8/8** | 2/8 | 0/8 |
| Recovering multiple constraints | **8/8** | 2/8 | 8/8 |
| Looking up a historical decision | **6/8** | 6/8 | 0/8 |
| Chinese/English queries | 6/8 | 6/8 | **8/8** |
| Initial decisions, code identifiers, failed attempts, source replacements combined | 32/32 | 32/32 | 32/32 |

The gains concentrate on evidence pushed back by intervening messages, corrected decisions, and combinations of constraints. Bilingual queries still have gaps. Book has zero stale-only cases versus eight for flat FTS; this does not establish a zero hallucination rate.

Local retrieval and context assembly have **p50 / p95 of 1.117 / 2.056 ms**, pooling 480 calls across two experiment blocks. Result caching is disabled; SQLite and operating-system caches are not cleared. Ingestion and model generation are excluded. [Pooled timing summary](benchmarks/results/engineering-memory-20261115/summary.json).

### An executed open-source component comparison

The benchmark runs the actual [pinned billion-context search kernel](https://github.com/ranxianglei/billion-context/tree/9674cfafbc78c50245ae0d887483d3d6ce880c15). Both engines receive **the same complete pages, project scope, top-five limit, and common whole-block packing at 2400 characters**. This track is recorded separately from the native-excerpt track above.

| Metric | Book | billion-context kernel |
|---|---:|---:|
| Evidence-span recall | **76/80 · 95.00%** | 72/80 · 90.00% |
| Complete evidence | **68/72 · 94.44%** | 64/72 · 88.89% |
| Policy checks passing | **44/48 · 91.67%** | 40/48 · 83.33% |
| Mean characters | **1812.0** | 1955.0 |
| Budget violations / source-validation failures | 0 / 0 | 0 / 0 |

Within this component comparison, Book has **5.56 percentage points** more complete evidence, **8.33 points** more passing policy checks, and **7.31% fewer characters** on average. Paired cases show **six gains and two losses**: the gains are historical-decision queries and the losses are bilingual queries. [Component data and timing boundaries](benchmarks/results/engineering-memory-20261115/final/2-candidate-components/report.json).

This is a pinned-component result. Book retains hierarchy/FTS metadata, and the engines' timing interfaces differ; no whole-product speed ratio follows. At the smaller 1200-character whole-block budget, Book has 61.11% complete evidence versus 88.89% for the kernel. All budgets and failures remain in the [detailed report](docs/engineering-memory-results.md).

**Evidence limits:** these are synthetic cases used during development, without a coding LLM or an independent holdout. A fixed consumer extracts recorded configuration and executes handwritten algorithm variants; its pass rate is not generated-code accuracy. All eight missing-evidence questions still return related context, requiring further checking or an explicit statement that evidence is missing. Real task completion time, patch success, and total model cost have not been measured. [Evaluation protocol](docs/engineering-memory-evaluation.md) · [Raw records](benchmarks/results/engineering-memory-20261115/).

## Open-source comparison

This table compares engineering roles using each project's official documentation. Except for the pinned kernel above, these projects were not benchmarked on this workload.

| Project | Main approach | When Book fits |
|---|---|---|
| [billion-context](https://github.com/ranxianglei/billion-context) | Model proxy and client plugins with model-directed reversible compression, decompression, and context search | An independent original-evidence archive queried by project through MCP, without changing model API routing |
| [claude-mem](https://github.com/thedotmack/claude-mem) | Hooks capture activity; an observer generates observations/summaries; local HTTP worker, SQLite, optional Chroma | Default capture and lexical queries add no summarization model calls; stdio MCP and capture need no HTTP listener |
| [Mem0](https://docs.mem0.ai/open-source/python-quickstart) | User/agent memory for applications; default model-based fact extraction and embeddings, with configurable local storage | Engineering conversations become original evidence without configuring additional extraction or embedding models |
| [Letta Code](https://github.com/letta-ai/letta-code) | Stateful agents managing memory, skills, and Git-backed MemFS, with local or cloud operation | A shared evidence layer for existing coding clients while retaining their tools and workflows |

Multiple clients, source lookup, and local operation are not unique to this project. Book brings **original evidence, project scope, bounded context, and low additional inference requirements** together in a lightweight memory layer for long-running development, incident review, and continuity across clients.

## Documentation and data boundaries

[Integrations](docs/integrations.md) · [Deployment and Docker](docs/deployment.md) · [Agent guide](docs/agent-guide.md) · [Token budgets](docs/token-budget.md) · [Optional semantic retrieval](docs/semantic-retrieval.md) · [Contributing](CONTRIBUTING.md)

Run `memory-book serve` and open [127.0.0.1:8765](http://127.0.0.1:8765) to inspect the archive. It is local, unencrypted data; recalled evidence enters the selected client's model context. Project filtering is not multi-user access control. Client-configuration backups are not automatic database backups. [Data locations and maintenance](docs/deployment.md#data-and-configuration-paths).

Independently implemented under the [MIT License](LICENSE). [Current release](https://github.com/Afloat16/AI-Memory-Book/releases/tag/v0.4.0) · [CI](https://github.com/Afloat16/AI-Memory-Book/actions/workflows/ci.yml).
