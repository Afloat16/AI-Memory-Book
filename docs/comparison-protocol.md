# Comparing memory retrieval without overstating the result

The goal is to reduce the time and model context needed to recover useful
evidence. A fast response that omits the answer does not meet that goal.
Neither does a small search preview whose required follow-up reads are left
out of the cost.

This protocol distinguishes shared-page retrieval, native response costs,
and a complete memory system. A result in one category must retain that
category's name in a report or README.

## 1. What the external adapters run

| Project | Immutable version | Executed implementation | Scope |
| --- | --- | --- | --- |
| billion-context | dc041dd1ab1a014efa352ba47a6f31fc47f55284 | Native searchBlocks(), default hybrid lexical ranker, native previews and document-feature cache | Search kernel over supplied common pages |
| ai-memory | v3.4.5; ee73c04c542fa41ca629b046deb4ac108518f407 | Official Linux x86-64 release, native write-page, CLI/HTTP FTS5 search, native page read | Page retrieval through a running server |
| ai-memory with local embeddings | Same release | Native MCP memory_query and memory_read_page, default all-MiniLM-L6-v2, native vector/FTS/entity/graph fusion | Default local-provider retrieval over supplied common pages |
| claude-mem | Source inspected at 6b779c06796138aeb4b0ee2fa7dbd25912e4f7fb | Not executed by these adapters | Unmeasured |

The external source is not rewritten into Python or replaced with a
similarly named algorithm. For billion-context, the runner downloads the
exact TypeScript files, checks both SHA-256 and Git blob hashes, and uses
Node's syntax-only TypeScript eraser. Its real algorithm registry selects
the shipped default. The adapter supplies uniform assistant-role messages,
so role weights do not add an engine-specific relevance hint. Project
subsets are prepared once outside the timed search function.

For ai-memory, the release archive and extracted executable are checked
against recorded SHA-256 hashes. The archive digest is also recorded in
GitHub's release metadata. The model files are checked against the hashes in
the pinned upstream Rust loader. Explicit local configuration makes a model
load failure fatal. The importer waits for native embedding backfill and
refuses a report with failed pages.

Primary references:

- [billion-context search interface and implementation](https://github.com/ranxianglei/billion-context/blob/dc041dd1ab1a014efa352ba47a6f31fc47f55284/kernel/src/search/index.ts)
- [billion-context search documentation](https://github.com/ranxianglei/billion-context/blob/dc041dd1ab1a014efa352ba47a6f31fc47f55284/kernel/src/search/SEARCH.md)
- [ai-memory v3.4.5 release](https://github.com/akitaonrails/ai-memory/releases/tag/v3.4.5)
- [ai-memory native CLI search route](https://github.com/akitaonrails/ai-memory/blob/ee73c04c542fa41ca629b046deb4ac108518f407/crates/ai-memory-cli/src/commands/search.rs)
- [ai-memory native page read route](https://github.com/akitaonrails/ai-memory/blob/ee73c04c542fa41ca629b046deb4ac108518f407/crates/ai-memory-cli/src/commands/read_page.rs)
- [ai-memory local embedding contract](https://github.com/akitaonrails/ai-memory/blob/ee73c04c542fa41ca629b046deb4ac108518f407/docs/local-embeddings.md)
- [ai-memory model hashes and inference implementation](https://github.com/akitaonrails/ai-memory/blob/ee73c04c542fa41ca629b046deb4ac108518f407/crates/ai-memory-llm/src/local.rs)
- [claude-mem search architecture](https://github.com/thedotmack/claude-mem/blob/6b779c06796138aeb4b0ee2fa7dbd25912e4f7fb/docs/public/architecture/search-architecture.mdx)

## 2. Shared inputs and document granularity

Start with a canonical conversation corpus. Preserve the original project,
session, turn, role, and timestamp information. Assign stable IDs and store
source coordinates independently of any engine. Ground truth must refer to
the original evidence, not to IDs invented by the retriever being scored.

For the retrieval-component comparison, export one fixed set of pages and
give every engine exactly the same title and text for each page. Record the
exporter version, chunking policy, document count, and corpus digest.
Metadata used only for scoring must not be added as searchable text.
Questions and expected answers must not enter the index.

Use the same project scope for the same question. When no project is given,
every engine receives the global query. ai-memory's upstream global MCP
query currently uses its separate FTS stream even when local embeddings
are enabled; the adapter preserves this behavior and records
global_fts_only.

A shared-page experiment controls representation but is still influenced
by the chosen chunker. Report that chunker explicitly. A separate native
hierarchy experiment can allow each system's normal representation, but it
then measures both representation and retrieval. Do not combine those
numbers as if only the ranker changed.

Feeding one engine concise, answer-bearing summaries while another must
search entire transcripts is not a controlled retrieval comparison.
Conversely, bypassing an upstream observer or summarizer and importing
common raw pages does not evaluate that observer's benefits or costs.

## 3. Two output views

### A. Common evidence assembly

Use the same candidate limit, ordering rule, tokenizer, and context cap for
every engine. For example, request five candidate pages, then pack their
source text into a common bounded evidence format. Record which exact
source spans survive the cap.

Score evidence only when the supporting source text is actually present in
the assembled context. A matching page ID is candidate recall, not
delivered evidence recall. A citation pointing to an omitted section does
not mean the model received that section.

This view isolates ranking and the achievable evidence/token tradeoff
under a shared assembly rule. If a report uses local fixture lookup for
full text, label its time as retrieval plus common fixture assembly.
It does not include a competitor's native follow-up read latency.

### B. Native tool payloads and reads

Keep each native search response unchanged. Count the actual text returned
to an agent, including required metadata and framing. Native previews can
locate a page without containing the requested fact. When a follow-up read
is needed, count both the search payload and the fetched page payload.
Measure the read calls too.

The billion-context kernel returns previews and references. Its production
host can then decompress the owning block. This adapter measures the
kernel; it does not instantiate the full proxy or reproduce decompression.
An external common-page read is therefore a component-level read, not a
claim about native proxy latency.

The ai-memory adapter provides real native page reads. In MCP mode it
preserves the exact content text and the full result object. These are two
representations of one response; count the chosen consumption surface once,
not both. Report whether the count covers rendered content, serialized MCP
results, or JSON-RPC wire bytes. Those quantities differ.

Native previews alone must never be scored or described as full-answer
quality when they omit the evidence.

The current component runner's native-read policy is deliberately explicit:
**search, then read every mapped top-k page once**, even when the preview
already contains the relevant evidence. Those counts describe that fixed
full-page policy. They are not the minimum required reads, an adaptive
agent's cost, or a universal native token cost. An agent that stops at a
sufficient preview or reads fewer pages can spend less. The shared context
budget is applied separately after retrieval; changing that budget does
not retroactively change the native reads already measured.

## 4. Timing

Measure on the same machine and record its OS, CPU, Python and Node
versions, corpus size, query count, and process layout. Exclude downloads
and compilation from per-query latency, but report them as setup costs.
Report ingestion, indexing, model preparation, and embedding backfill
separately.

Use named boundaries:

- **Kernel search:** only the native search function. The billion-context
  adapter records this inside its Node process.
- **Adapter roundtrip:** request serialization, local transport, native
  search, response serialization, and client decoding.
- **Evidence ready:** retrieval plus every necessary full-text read and
  final assembly.
- **Cold process:** executable/process initialization and the first query,
  when that path is explicitly measured.
- **Warm process:** later queries through an already running process with
  the implementation's normal caches.

ai-memory's reported search_ms includes a persistent loopback HTTP
roundtrip. It is not isolated SQL or vector-search time. Its MCP explain
timings do not substitute for total query time: embedding and other
overhead may fall outside an individual stream timer.

Do not compare a Python in-process function against a spawned competitor
CLI and call the difference a search-engine speedup. Report in-process and
transport-inclusive series separately, or use the same externally
observable boundary for both. Avoid re-starting a background service for
each query unless measuring that explicitly.

Keep first-query and warm-query results separate. Repeating one identical
query measures a cache-friendly workload; it does not establish performance
on new questions. A cache reset of document features is also not a cold OS
page cache or cold process.

Report median and p95, distributions when useful, and repeated-run
variation. Preserve per-query rows to expose slow tails and failures.
Avoid latency thresholds based on a single shared-runner measurement.

## 5. Tokens and model work

Use one named, versioned tokenizer for every engine within a comparison.
Token estimates based on character counts must be labeled estimates.
Count the context actually consumed, including subsequent reads and any
query-specific routing text. Count a fixed tool schema or startup
instruction once under a documented session length, rather than adding it
arbitrarily to every question.

Local embedding inference has CPU and ingestion costs even when it makes
no paid API calls. Its input tokens are not generative-model context tokens.
Report the two separately. The pinned ai-memory model produces 384
dimensions and truncates each input at its native 512-token limit; the
adapter does not alter that limit.

A lower token count is a useful improvement only at an adequate evidence
level. Present a quality-versus-context-budget curve or compare engines at
a shared budget. If one configuration recovers more evidence, do not hide
that difference behind an aggregate token-saving percentage.

## 6. Quality and held-out data

Use more than exact-string lookups. Include paraphrases, corrections,
conflicting older facts, relevant facts near the end of long pages,
multiple required evidence turns, cross-session references, multilingual
questions, explicit project boundaries, and unsupported questions.

Keep development cases separate from held-out cases. Freeze query sets and
ground truth before evaluating a release candidate. Randomizing names in
the same sentence template is useful for regression checks but is not a
substitute for an independently authored dataset.

Candidate recall, delivered evidence recall, contradiction exposure,
abstention, and answer accuracy answer different questions. Name them
separately. An evidence-retrieval test does not establish end-to-end answer
accuracy. That requires a fixed answering model and prompt, paired runs,
and a separate answer evaluation. Do not call an exact-string or
source-coordinate check an LLM judge.

An answerable question with no useful context is a miss. An unsupported
question that returns unrelated context is not a successful answer. Store
failures, budget overflows, and timeouts as failures rather than dropping
them from averages.

## 7. What these runs cannot establish

The supplied-page tests do not evaluate every product's background capture,
observer prompts, consolidation quality, memory editing, privacy filters,
session management, or long-term decay. They also do not simulate an
autonomous agent selecting tools or deciding when to decompress a block.
A real MCP retrieval call still does not make the whole capture-to-answer
pipeline an end-to-end evaluation.

claude-mem is currently unmeasured. Its full observer and search workflow
has not been reproduced here. A handwritten FTS query, or an adapter seeded
with artificial observations while bypassing the observer, must not be
labeled a full claude-mem result. If such a native component is added
later, it needs its own explicit scope and provenance.

It is valid to say a measured configuration used fewer context tokens at
the same delivered-evidence level on a specified corpus. It is not valid
to infer that AI-Memory-Book is universally faster, cheaper, or more capable
than every configuration of another memory system.

## 8. Reproduction and licensing

The optional runners and lock files are in
[benchmarks/competitors](../benchmarks/competitors/README.md). They download
upstream artifacts into a caller-selected ignored cache and verify them
on each preparation. Raw public benchmark data and downloaded binaries or
model weights are not bundled into the product package.

The billion-context benchmark adapter uses
[billion-context](https://github.com/ranxianglei/billion-context) and
[acp-kernel](https://github.com/ranxianglei/acp-kernel). Its pinned
[license](https://github.com/ranxianglei/billion-context/blob/dc041dd1ab1a014efa352ba47a6f31fc47f55284/LICENSE)
includes MIT terms and an additional attribution requirement. Attribution
is provided here and in the adapter documentation; the downloaded LICENSE
is preserved.

[ai-memory](https://github.com/akitaonrails/ai-memory) is MIT-licensed.
The local [all-MiniLM-L6-v2 model](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)
is Apache-2.0. AI-Memory-Book's production runtime does not depend on either
competitor.
