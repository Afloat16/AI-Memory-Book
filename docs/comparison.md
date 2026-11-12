# Comparison guide: evidence quality, cost and deployment

AI-Memory-Book is designed for an agent that needs to continue a project from
verifiable original conversations. Its default memory path uses Python and
SQLite, keeps exact source addresses, and returns a bounded evidence context
in one MCP recall call. Generative memory writing, an embedding download and
a separate database service are optional rather than core requirements.

The tables distinguish a documented architecture, an executed retrieval
component, and an actual capture/summary/retrieval/answer workflow. A fast
search function is not a complete memory workflow, and source-evidence recall
is not the accuracy of a generated answer.

## Popular projects and the workload they address

Popularity is a dated selection aid, not a quality score. The star counts below
come from the [official metadata snapshot](../benchmarks/reports/upstream-landscape-2026-11-12.json)
on **2026-11-12**; implementations are linked to the inspected source version.

| Project | Stars at snapshot | Main memory representation and retrieval | Operational/model boundary | What Book emphasizes |
|---|---:|---|---|---|
| **AI-Memory-Book** | — | Original sessions organized as projects, chapters and addressable pages; lexical recall plus optional local semantic candidates | Default Python + SQLite; no generative write or embedding stage; optional exact tokenizer and local semantic model | Direct original evidence, scope filters, exact context caps, local inspectability |
| [claude-mem](https://github.com/thedotmack/claude-mem/tree/a2eb8c56bfa530fb1079b2abfa60085f57a62a11) | 116,332 | Model-derived observations and session summaries; SQLite FTS and Chroma; progressive search/timeline/detail tools | Bun worker and a selected observer model; a local OpenAI-compatible provider is supported | Original transcript spans and a complete bounded recall context without an observer phase in the default path |
| [Mem0](https://github.com/mem0ai/mem0/tree/f1791daa86d469249c9b002f62644d58a1eb96a0) | 68,842 | Extracted facts and configurable memory infrastructure; semantic, keyword and entity signals | Standard extraction/embedding pipeline depends on chosen model and storage providers; managed platform is a separate product | A small local source archive for project continuation, with no mandatory model-generated memory |
| [PageIndex](https://github.com/VectifyAI/PageIndex/tree/2ac8694bf8fe89a3840dda9bdb88db5119b77fc4) | 40,385 | Hierarchical document tree and model-directed retrieval | Indexing/query model usage depends on configuration; vectorless does not mean model-free | Conversation source addresses and low-cost local recall rather than document-tree reasoning |
| [Graphiti](https://github.com/getzep/graphiti/tree/ebef986a0b2360211b65751c111cacb4a7d790eb) | 32,767 | Temporal entities and relationships; semantic, keyword and graph traversal | Model-assisted ingestion, embeddings and a graph backend; retrieval need not invoke an LLM every time | Inspectable source text with SQLite deployment instead of constructing a knowledge graph |
| [ai-memory](https://github.com/akitaonrails/ai-memory/tree/57dac7348e739dbb552c059a55c103e4ca5cfd27) | 15,694 | Git-backed Markdown wiki plus derived SQLite; FTS/entity/link and optional vector fusion | **Its default path also supports zero LLM calls.** Generative consolidation and local embeddings are configuration choices | Exact transcript spans, chapter/session scope and citation-inclusive native context budgets |
| [billion-context](https://github.com/ranxianglei/billion-context/tree/9674cfafbc78c50245ae0d887483d3d6ce880c15) | 6,924 | Request proxy with model-directed hierarchical compression and retrieval/decompression | Compression and reconstruction are separate from the measured search kernel | Direct bounded source delivery without adopting a model-request proxy |

The [Letta repository](https://github.com/letta-ai/letta/blob/8816d3a8516893bfdc0fa14bfb1235226012e295/README.md)
had 25,420 stars in the snapshot, but its current implementation moved to
letta-ai/letta-code and the older server lives on an archive branch. Those
implementations and star counts must not be mixed into one measured runtime.

The [claude-mem local-provider documentation](https://github.com/thedotmack/claude-mem/blob/2cfed7620c1b44db87c7f04cbf073ec37efca38d/docs/public/usage/openai-compatible-provider.mdx)
explicitly supports loopback endpoints without a commercial API key. Book's
advantage is the combination of its default architecture and measured source
delivery, not a claim that competitors universally require paid keys.

## Historical common-context retrieval results

The [complete frozen report](../benchmarks/RESULTS-recall-score-quality.md#6-native-components-common-context-and-their-cost-boundaries)
uses all **1,015** eligible text-only LoCoMo questions (**649 answerable**),
identical supplied pages, project scope, top-five candidates and a shared
citation/whole-page packer. The following setting is **1,024 cl100k_base tokens**.

| Frozen component | Evidence recall | Complete evidence | Mean common-context tokens |
|---|---:|---:|---:|
| **Book 0ab49d4** | **69.54%** | **72.88%** | 827.2 |
| billion-context dc041dd search kernel | 65.48% | 68.72% | 862.6 |
| ai-memory v3.4.5 ee73c04 local hybrid | 64.47% | 66.72% | **779.3** |

Book returns complete evidence **4.16 percentage points** more often than the
tested billion-context component and **6.16 points** more often than ai-memory.
Its mean context is **4.1% smaller than billion-context** at this setting.
Across both tokenizers and all three caps, it leads both evidence metrics in
12/12 pairwise settings; mean token savings occur in 6/12, not every setting.

These are previously observed regression questions. The historical common-page
policy is separate from the newer native token-budget API and its per-question
block-preservation contract. Do not replace one policy's baseline with another.

## Search and delivery latency, with the measured boundaries

All numbers in this table are from the same historical frozen report; they
are not measurements of a later source revision or a new hosted runner.

| Executed operation | p50 | p95 | Included boundary | Excluded work |
|---|---:|---:|---|---|
| Book score-aware recall | 2.945 ms | 4.555 ms | Python in-process recall and native context assembly | MCP transport, answering |
| **Book actual MCP recall** | **5.764 ms** | **9.181 ms** | Official SDK subprocess stdio request/response, serialization and evidence | Host startup, answering |
| billion-context search + bridge | 1.298 ms | 2.413 ms | Native search kernel and persistent JSON bridge | Original proxy compression and decompression |
| ai-memory native local hybrid | 29.720 ms | 37.315 ms | Persistent loopback HTTP/MCP query and response decoding | Follow-up full reads and answering |

Billion's kernel-only median is 1.088 ms. It is faster at its measured search
boundary. Different transports and omitted phases make an overall “N times
faster” product claim inappropriate.

For Book's **same-boundary version comparison**, actual MCP response tokens
drop **54.7%** (3,233.5 to 1,465.1 o200k_base tokens) relative to v0.2.1, while
first-call p50 falls **31.1%** (8.371 to 5.764 ms). Against the already optimized
prior v0.3 branch, the same continuation uses 0.38% more response tokens and
has a 15.5% lower observed median. These are distinct baselines.

## Returned tokens, follow-up reads, preparation and storage

| Recorded item | Measurement | Interpretation |
|---|---:|---|
| Book one actual MCP recall | 1,465.1 mean o200k_base response tokens | Includes its actual returned JSON and metadata |
| ai-memory native search | 876.6 mean returned tokens | Native search preview/payload under the fixed policy |
| ai-memory full reads of every mapped top-five page | 1,698.1 additional mean tokens; 5.468 ms additional mean read time | Explicit read-all policy; an adaptive agent can choose fewer reads |
| ai-memory search plus those full reads | 2,574.6 mean returned tokens | Book uses 43.1% fewer returned tokens under these declared policies |
| billion-context native preview | 569.2 mean returned tokens | Does not include unmeasured native decompression |
| Book public-source import | 1,166.016 ms, one recorded pass | Book import boundary only |
| ai-memory cached-model adapter setup | 143.797 s | Includes 141.637 s page writes/indexing and 2.138 s readiness |
| billion-context bridge/list preparation | 0.340 s | Different preparation operation; not equivalent native ingestion |

Preparation rows are deliberately not converted into cross-product speed
ratios. Closed database/index sizes, optional model bytes, per-stage model
usage and generation timings belong to their exact experiment reports.
Unknown provider dollar costs, energy, production concurrency and watcher
overhead are not zero.

## Reading the continued measurements

The [continuation status](continuation-status.md) and registered plans identify
the pending or completed native-budget, semantic, generated-answer and native
workflow cohorts. Only completed reports with matching source/model/data
identities supply numerical results. Public and repeated synthetic questions
remain regression data; the frozen HotpotQA cohort is an externally authored,
scoped multi-hop diagnostic rather than a broad generalization proof.

The separately registered claude-mem comparison will execute its pinned supplied-source SQLite FTS
component. Its original observer, Chroma retrieval, host injection and complete
workflow must be reported separately. Mem0, Graphiti and PageIndex appear in
the official architecture comparison above; no local performance number is
invented for an unexecuted product.

A useful evaluation reports source correctness, complete evidence, paired
gains/losses, context and actual response tokens, p50/p95/tail latency, model
loading/index build, capture/consolidation/reads/answering, storage, errors and
unknown costs. The repository keeps those boundaries visible rather than
turning one favorable figure into a universal ranking.
