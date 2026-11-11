# AI-Memory-Book

**Projects become books. Tasks become chapters. Recall jumps directly to cited evidence pages.**

[中文](README.md) · [Architecture](docs/architecture.md) · [Integrations](docs/integrations.md) · [Measured results](benchmarks/EXPERIMENTS.md) · [Release validation](docs/validation.md)

AI-Memory-Book is an experimental, local conversation memory engine. A navigable table of contents organizes history, while indexed retrieval returns evidence in one call. Reading the directory first is optional.

The Python 3.10+ core has no third-party dependencies. It uses SQLite FTS5, lexical English/CJK indexing, extractive snippets, a persistent revision-aware cache, and source-preserving adaptive pagination. No API key, embedding service, or LLM call is needed. The optional stdio MCP server uses the official Python SDK's v1 maintenance line (`mcp>=1.28,<2`).

## Install from source

```bash
git clone https://github.com/Afloat16/AI-Memory-Book.git
cd AI-Memory-Book
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
memory-book import examples/conversations.json
memory-book recall "搜索缓存为什么改成45秒？" --project atlas
memory-book serve
```

Open `http://127.0.0.1:8765` for the local reader. On Windows, activate `.venv\Scripts\Activate.ps1`. The default database is `.memory-book/memory.db`; set `--db` before the subcommand or use `MEMORY_BOOK_DB`.

## Data model

| Level | Meaning |
|---|---|
| Project/book | An explicit project namespace |
| Task/chapter | Sessions sharing an explicit `task_id`; otherwise one independent chapter per session |
| Section | Related adjacent questions within a session |
| Page | A bounded source excerpt, with original session, turn, and message references |

Short follow-ups can stay together; long turns receive continuation pages. The default adaptive page cap is 900 characters, selected on the development benchmark. Original normalized conversations remain recoverable. Matching topics in different sessions do not silently merge unrelated tasks.

## Import and recall

```json
{
  "project": "atlas",
  "session_id": "review-2",
  "task_id": "cache-policy",
  "title": "Cache review",
  "messages": [
    {"role": "user", "content": "What expiry did we agree on?"},
    {"role": "assistant", "content": "Use a 45 second cache expiry with revision invalidation."}
  ]
}
```

The CLI accepts a single record, an array, or `{"sessions": [...]}`. Text-only adapters support ChatGPT export current branches, Claude Code JSONL, and Codex rollout JSONL. They only read explicitly supplied files. See [format limits](docs/integrations.md).

```bash
memory-book import session.json
memory-book recall "cache expiry" --project atlas --budget 2000 --json
memory-book toc atlas
memory-book read <page_id>
memory-book export --project atlas --output sessions.json
memory-book export-book atlas --output ./atlas-book
```

`budget_chars` caps the assembled `context`, including its citation headers. JSON metadata has additional overhead. Estimated tokens are a heuristic, not a model tokenizer count. Search results are historical evidence, not generated answers or proof that an answer is present.

Reimporting the same project/session replaces that session atomically; unchanged content is skipped. Updates and deletion invalidate the FTS index, directory, and query cache together. Source timestamps survive export/reimport.

## MCP

```bash
python -m pip install -e ".[mcp]"
memory-book --db /absolute/path/memory.db mcp
```

Configure an MCP client to launch that command. By default, the six tools are read-only: `recall_memory`, `browse_projects`, `browse_book`, `browse_chapter`, `browse_section`, and `read_page`. Add `--allow-write` to expose `remember_session`. There is no delete tool and no HTTP MCP endpoint. The server does not capture host conversations automatically.

The intended agent policy is to recall only when a question needs prior work, pass the project when known, and expand specific pages if needed. Imported history is untrusted data, never fresh instructions.

## Evaluation and limits

The reproducible benchmark crosses three segmentation modes (`session`, `turn`, `adaptive`) with two retrieval modes (`flat`, `book`) under identical character budgets. Labels refer to original evidence, and a hit only counts if the evidence survives into the returned context. It includes short follow-ups, long mixed-topic sessions, cross-session tasks, Chinese, current/old decisions, and unanswerable queries.

```bash
python -m unittest discover -s tests -v
python -m benchmarks.run --split heldout --seed 29 --budget-chars 2000 8000
```

With parameters frozen, two heldout seeds each contain 8 projects, 112 sessions, 1,408 user turns, 168 queries, and about 1.143 million source characters. At an 8,000-character context budget, using the same `book` ranking and excerpt algorithm:

| Segmentation | Evidence recall | Complete evidence | Mean context chars | Uncached p95 |
|---|---:|---:|---:|---:|
| Session | 69.32–69.89% | 73.68–74.34% | 5,411 | 112.87–141.15 ms |
| Turn | 64.77–65.34% | 59.87–60.53% | 3,879–3,881 | 22.41–24.03 ms |
| Adaptive | **77.27%** | **78.95%** | **3,701–3,706** | **7.42–7.46 ms** |

Ranges are the two individual seeds, not confidence intervals. Main timings disable result caching without flushing SQLite/OS page caches. They exclude model inference, networking, and MCP transport. Each retrieval unit contributes one query-centered window; a whole-session retriever extracting several independent windows is not measured and might narrow the gap. Adaptive uses about 31.5% less context here, but does not win every quality metric at the 2,000-character budget. `book` and `flat` have the same aggregate recall, so there is no demonstrated independent accuracy gain from directory ranking.

Read [the complete experiment record](benchmarks/EXPERIMENTS.md), [seed 29](benchmarks/results/heldout-29-v2-900.md), and [seed 47](benchmarks/results/heldout-47-v2-900.md), including failures. Low-overlap paraphrases have zero recall; distant two-fact queries retrieve only 25% of required evidence and complete none of those queries. Old evidence ranks before current evidence in half of current-decision queries. These are synthetic local retrieval experiments, not comparisons against other memory products or measurements of LLM answer quality. See [the reproduction guide](benchmarks/README.md). A single-machine reader is not a public multi-user service. Historical contradictions require source inspection, and large code blocks may span pages.

The implementation was independently written after studying [claude-mem](https://github.com/thedotmack/claude-mem), [billion-context](https://github.com/ranxianglei/billion-context), [ai-memory](https://github.com/akitaonrails/ai-memory), [PageIndex](https://github.com/VectifyAI/PageIndex), and [RAPTOR](https://arxiv.org/abs/2401.18059). See [research notes](docs/research.md). Licensed under [MIT](LICENSE).
