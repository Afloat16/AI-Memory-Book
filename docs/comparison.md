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

## Frozen common-context retrieval results

The [historical frozen report](../benchmarks/RESULTS-recall-score-quality.md#6-native-components-common-context-and-their-cost-boundaries)
and the completed [claude-mem component report](../benchmarks/results/claude-mem-components-public.summary.json)
use all **1,015** eligible text-only LoCoMo questions (**649 answerable**),
the same **1,339 supplied source pages**, project scope, top-five candidates
and a shared citation/whole-page packer. The claude-mem addition ran on
2026-11-12 and passed the exact dataset, page-bundle and exporter hash guards
before reusing the historical comparators. It executes unchanged upstream
SessionSearch code, with original queries and no answer-informed rewriting.

The following setting is **1,024 cl100k_base tokens**. Complete evidence uses
the 649 answerable questions as its denominator; evidence recall uses 788
annotated evidence spans. Mean context tokens include all 1,015 queries.

| Frozen component | Evidence recall | Complete evidence | Mean common-context tokens |
|---|---:|---:|---:|
| **Book 0ab49d4 score-aware recall** | **69.54%** | **72.88%** | 827.2 |
| claude-mem 15.18.0 / 2cfed762 native SQLite FTS | 66.24% | 70.11% | 804.8 |
| billion-context dc041dd search kernel | 65.48% | 68.72% | 862.6 |
| ai-memory v3.4.5 / ee73c04 local hybrid | 64.47% | 66.72% | **779.3** |

Book returns complete evidence **2.77 percentage points** more often than the
tested claude-mem FTS component, **4.16 points** more often than billion-context
and **6.16 points** more often than ai-memory. Its mean context is **4.1%
smaller than billion-context** at this setting, but **2.8% larger than
claude-mem** and **6.2% larger than ai-memory**. The result supports a source
coverage advantage; it does not support a universal token-saving claim.

Here is the complete registered matrix. Each cell is **evidence recall /
complete evidence / mean packed tokens**; percentages are shown before the
token count. The [component evaluation](claude-mem-component-evaluation.md#completed-run-2026-11-12)
also provides the expanded table and exact provenance.

| Tokenizer | Cap | Book score-aware | claude-mem native FTS | billion-context search | ai-memory hybrid |
|---|---:|---:|---:|---:|---:|
| cl100k_base | 512 | 62.44% / 66.26% / 447.6 | 59.52% / 63.79% / 440.8 | 58.88% / 62.71% / 442.8 | 56.60% / 58.86% / 451.1 |
| cl100k_base | 1,024 | 69.54% / 72.88% / 827.2 | 66.24% / 70.11% / 804.8 | 65.48% / 68.72% / 862.6 | 64.47% / 66.72% / 779.3 |
| cl100k_base | 2,048 | 69.54% / 72.88% / 832.1 | 66.24% / 70.11% / 807.9 | 65.48% / 68.72% / 871.0 | 64.59% / 66.87% / 782.4 |
| o200k_base | 512 | 62.94% / 66.72% / 451.5 | 59.64% / 63.79% / 444.1 | 59.39% / 63.02% / 445.8 | 56.98% / 59.17% / 451.8 |
| o200k_base | 1,024 | 69.54% / 72.88% / 809.2 | 66.24% / 70.11% / 786.2 | 65.48% / 68.72% / 844.6 | 64.47% / 66.72% / 760.4 |
| o200k_base | 2,048 | 69.54% / 72.88% / 810.0 | 66.24% / 70.11% / 787.4 | 65.48% / 68.72% / 848.5 | 64.59% / 66.87% / 762.4 |

Across this matrix, Book has higher measured evidence recall and complete
evidence than all three compared components. Its mean context is smaller in
6 of the 18 component/setting comparisons. The earlier first-round Book
baseline still has a higher 512-token cl100k_base complete-evidence rate:
66.72%, compared with 66.26% for this frozen score-aware version. The newer
native-budget continuation is a separate experiment and does not erase that
historical regression.

All four components return nonempty context for **100% of the 366 unanswerable
questions** at every setting. None of these retrieval tables demonstrates
answer abstention or generated-answer accuracy. Public questions have already
been observed and are regression data.

The historical whole-page policy is separate from the newer Book native
token-budget API and its per-question block-preservation contract. Do not
replace one policy's baseline with another.

## Search and delivery latency, with the measured boundaries

The Book, billion-context and ai-memory rows retain their original historical
run and transport boundaries. The claude-mem rows are from a **separate
2026-11-12 GitHub Actions runner**: Linux x86-64, four CPUs, Python 3.12.16,
Bun 1.3.13 and SQLite 3.51.2. Same-source quality is comparable under the frozen
controls; these timings must not be converted into cross-host speed ratios.

| Executed operation | Run | p50 | p95 | Included boundary | Excluded work |
|---|---|---:|---:|---|---|
| Book score-aware recall | Historical | 2.945 ms | 4.555 ms | Python in-process recall and native context assembly | MCP transport, answering |
| **Book actual MCP recall** | Historical | **5.764 ms** | **9.181 ms** | Official SDK subprocess stdio request/response, serialization and evidence | Host startup, answering |
| billion-context search + bridge | Historical | 1.298 ms | 2.413 ms | Native search kernel and persistent JSON bridge | Original proxy compression and decompression |
| ai-memory native local hybrid | Historical | 29.720 ms | 37.315 ms | Persistent loopback HTTP/MCP query and response decoding | Follow-up full reads and answering |
| claude-mem native SQLite FTS function | Separate 2026-11-12 runner | 59.073 ms | 99.973 ms | Unchanged SessionSearch.searchObservations on supplied original pages | JSON bridge, observer, Chroma, production MCP, answering |
| claude-mem function + persistent bridge | Separate 2026-11-12 runner | 59.664 ms | 100.450 ms | Python/Bun JSON request/response and full native observation rows | Observer, Chroma, production MCP, answering |

Claude-mem's native-function mean was 60.529 ms and bridge mean was 61.112 ms
over 3,045 successful query attempts. Its first-pass bridge p50/p95 was
59.389/100.487 ms; subsequent repetitions were 59.777/100.297 ms. There is no
adapter result cache; SQLite/process caches warm naturally, so these are not
OS-cold-cache claims. All six configurations had zero token-cap violations,
and the native process, FTS integrity and unchanged-source checks passed.

Billion's historical kernel-only median is 1.088 ms. It is faster at its
measured search boundary. Different hosts, transports and omitted phases make
an overall "N times faster" product claim inappropriate.

For Book's **same-boundary version comparison**, actual MCP response tokens
drop **54.7%** (3,233.5 to 1,465.1 o200k_base tokens) relative to v0.2.1, while
first-call p50 falls **31.1%** (8.371 to 5.764 ms). Against the already optimized
prior v0.3 branch, the same continuation uses 0.38% more response tokens and
has a 15.5% lower observed median. These are distinct baselines.

## Returned tokens, follow-up reads, preparation and storage

The common packed context above is separate from each component's actual
returned payload. Native payloads also have different serialization and
follow-up policies; a smaller preview does not imply a smaller completed
answer workflow.

| Recorded item | Measurement | Interpretation |
|---|---:|---|
| Book one actual MCP recall | 1,465.1 mean o200k_base response tokens | Historical run; includes its actual returned JSON and metadata |
| ai-memory native search content / full payload | 876.6 / 942.5 mean o200k_base tokens | Historical result content and complete decoded payload are distinct surfaces |
| ai-memory full reads of every mapped top-five page | 1,698.1 content / 1,913.7 payload mean tokens; 5.468 ms additional mean read time | Explicit read-all policy; an adaptive agent can choose fewer reads |
| ai-memory search plus those full reads | 2,574.6 content / 2,856.2 payload mean o200k_base tokens | Both totals are retained; neither is an equal-cap native-agent answer-cost comparison |
| billion-context native preview | 569.2 mean o200k_base returned tokens | Does not include unmeasured native decompression |
| claude-mem native full observation rows | 1,719.6 cl100k_base / 1,691.3 o200k_base mean tokens; 6,281.3 mean bytes | Compact key-sorted row-array JSON; excludes bridge envelope; not production MCP or provider billing |
| Book public-source import | 1,166.016 ms, one historical recorded pass | Book import boundary only |
| ai-memory cached-model adapter setup | 143.797 s | Historical run; includes 141.637 s page writes/indexing and 2.138 s readiness |
| billion-context bridge/list preparation | 0.340 s | Historical run; not equivalent native ingestion |
| claude-mem cached source/runtime preparation and verification | 966.46 ms | Separate runner; excludes downloading/installing the pinned source and runtime |
| claude-mem Bun startup / native schema and FTS creation | 39.04 / 30.83 ms | Separate phases, before supplied-page loading |
| claude-mem 1,339 supplied pages + native FTS indexing | 213.65 ms | Harness bulk INSERT with native triggers; no capture or observer summarization |

The historical results text derived a **43.1%** difference by comparing Book's
1,465.1-token actual MCP response with ai-memory's 2,574.6-token search/read
**content** total. That mixes complete-response and content-only surfaces;
it must **not** be presented as a complete-response token-saving rate.
The frozen historical result files remain unchanged for audit, while this
guide reports ai-memory's content and full-payload totals separately. Book's
54.7% same-boundary version improvement above is a different comparison.

The claude-mem run recorded **3,522,560 bytes** of logical/file DB, plus
**6,505,512 bytes** of WAL and **32,768 bytes** of SHM before checkpoint.
The 1.316 ms checkpoint reduced WAL to zero; DB and SHM sizes were unchanged.
Bun RSS was **86,605,824 bytes** after loading and **90,165,248 bytes** after
querying; Linux high-water RSS was **95,141,888 bytes**. These measurements
cover the native component process and its benchmark database, not a full
claude-mem worker, Chroma database, model files or a multi-process deployment.

Preparation and storage values are deliberately not converted into
cross-product speed or footprint ratios. Equivalent closed-state storage and
process-wide memory figures are not available for every historical component.
This claude-mem component makes zero generative calls; full observer/write/
summary/answer model usage remains unknown. Unknown provider dollar costs,
energy, production concurrency and watcher overhead are not zero.

## Actual generated answers and native workflow

The missing model measurements are complete and have their own reports.
[The answer experiment](../benchmarks/RESULTS-local-answers.md) records
**768 real calls** using pinned Qwen2.5-0.5B Q4_K_M / llama.cpp b12110, a
4,096-token model context and a 512-token cl100k_base evidence cap. There
is one generation per question/mode and no transport errors or truncated
responses. Lexical EM/F1 are distinct from evidence completeness and are
not semantic-judge or original LoCoMo answer scores.

| Cohort | Retrieval mode | Answer EM | Lexical F1 | Answer p50 / p95 |
|---|---|---:|---:|---:|
| LoCoMo, 86 answerable / 42 unsupported | Prior native excerpts | 4.65% | 25.58% | 2,606.0 / 3,109.2 ms |
| LoCoMo | Native token budget | 3.49% | 24.07% | 2,879.8 / 3,271.9 ms |
| LoCoMo | Semantic + native budget | 3.49% | 25.13% | 2,865.5 / 3,253.8 ms |
| HotpotQA, 128 answerable | Prior native excerpts | 10.16% | 19.72% | 4,797.1 / 5,825.3 ms |
| HotpotQA | Native token budget | 10.94% | 20.02% | 4,951.2 / 5,847.1 ms |
| HotpotQA | Semantic + native budget | 9.38% | 17.46% | 4,993.1 / 5,852.1 ms |

Exact unsupported abstention is 0/42 for all three LoCoMo modes. A small
model and strict lexical scoring do not establish a general answer-quality
ranking. The two cohorts used separate hosts; timings stay within their
paired cohort. Full reports include prompt/output usage, preparation,
storage, changed question IDs and verified process identity.

The separate [native Book/ai-memory workflow](../benchmarks/RESULTS-full-workflow.md)
uses 42 fictional source sessions, 36 previously authored questions
(30 answerable / 6 unsupported), a separately registered 16,384 context
and 1,000-output-token consolidation cap. Both engines later answer with
the same pinned model and 512-token evidence budget.

| Measured item | Book | ai-memory v3.4.5, generative consolidation enabled |
|---|---:|---:|
| Accepted source sessions | 42/42 | 42/42 |
| Generative consolidation calls | 0 | 42 |
| Validated native consolidations | Not a model-writing phase | 7/42 |
| Actual answer calls | 36 | 36 |
| Answer EM / lexical F1 | 13.33% / 40.37% | 0.00% / 10.99% |
| Retrieval p50 / p95 | 2.27 / 15.05 ms | 147.12 / 158.91 ms |
| Answer p50 / p95 | 3,713.90 / 5,365.71 ms | 4,975.25 / 5,514.40 ms |
| Mean evidence tokens | 269.11 | 498.08 |
| Mean native returned tokens | 1,392.53 | 5,116.67 |
| Answer-model prompt / output tokens | 14,877 / 982 | 25,827 / 680 |
| Consolidation prompt / output tokens | 0 / 0 | 103,797 / 36,706 |

This result is **completed_with_failures**. All 35 unsuccessful native
consolidations report `truncated-response`; each corresponding model
response hits the configured 1,000-token output limit. The 7 model
responses ending normally correspond to the 7 successful consolidations.
All 114 model requests and their usage are recorded. The 35 failed
consolidations alone use **121,508 tokens**, included in the **140,503-token**
consolidation total; failures are not free or silently retried. Each engine
also has one truncated answer, retained in scoring.

Book import takes 46.24 ms for all 42 sessions. Native capture takes
10,147.88 ms, consolidation 1,981,084.49 ms and embedding backfill 22.98 ms.
These are different native phase boundaries, not interchangeable indexing
operations. Book's closed SQLite files total 376,832 bytes; the native
sandbox totals 2,243,214 bytes including logs and wiki Git history, excluding
the shared model symlink. Full stage clocks, p99 and storage definitions
remain in the workflow report.

Current ai-memory's default can also run without an LLM. This fixed
small-model consolidation diagnostic does not measure its best possible
configuration or show that every deployment incurs those costs or failures.
claude-mem's observer/Chroma and billion-context's full compression workflow
are not covered by this experiment.

## Completed continuation and interpretation

The [completion record](continuation-status.md) and
[strict audit](../benchmarks/reports/hosted-final-aggregation.json) verify
the full native, semantic, answer and workflow matrices. The
[latest performance optimization](token-prefix-performance.md) preserves
all 2,016 development payloads and improves all four 512-token p95 settings;
its larger-budget tradeoffs are retained separately.

Public and reused synthetic questions remain regression data. The fixed
HotpotQA cohort contributes independently authored scoped multi-hop
questions, then becomes regression evidence after inspection. Mem0,
Graphiti, PageIndex and Letta appear in the official architecture comparison;
unexecuted product configurations have no invented performance scores.

A defensible comparison keeps source correctness, evidence completeness,
generated-answer scores, exact abstention, latency, native payload/context
tokens, preparation, capture/consolidation/read phases, storage, model usage,
errors and unknown costs distinct. Production concurrency, adaptive agent
policies, provider billing and electricity remain unmeasured.
