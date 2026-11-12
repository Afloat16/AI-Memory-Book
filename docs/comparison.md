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

## v0.3.1 comparison

The accepted runtime is frozen at
[`2d199b9`](https://github.com/Afloat16/AI-Memory-Book/commit/2d199b93f650eccd3dd239178822b31001b880e3),
Python-source SHA-256
`9c8118d26ae1a0eae4f31d9d4f44b2afa0ee5c54314bde5187deb27c473dee46`.
It preserves the default lexical ranking while using a guarded project rowid
range to reduce FTS work. Q2 and indexed MCP references remain optional. The
project-local statistics research candidate failed its gate and is excluded.

The [complete round-three report](../benchmarks/results/round3-comparison-43267797247-1/report.md)
and [assessment](../benchmarks/results/round3-comparison-43267797247-1/assessment.json)
have status **complete-verified**. All ten stages completed on one host: **4,608
native calls and 4,608 component searches**. All **1,536 native default payload
pairs and 768 component default payload pairs** match after excluding only
the measured `latency_ms` field. An
[independent offline audit](../benchmarks/reports/round3-recovery/comparison-cross-verification.json)
recomputed the unchanged evaluator's assessment and report, checked all 32
result blobs and all 71 bound evaluator files, and performed no new searches.

### Shared-page evidence and measured search

The 256 selected HotpotQA questions exclude the previous 128-question and
256-question selections. They retain 2,559 supplied paragraphs, 3,896 canonical
pages and 607 required evidence annotations. This is a new selection from the
same public source, not a new domain. Every component receives the same source
pages, scope, top-five limit, citation format and whole-block packer.

The view below uses **1,024 cl100k_base tokens**. Quality uses the first result
per question; latency includes all three actual searches. Search p50/p95 uses
the recorded `native_search_latency` surface. The generated report separately
lists adapter roundtrips and first-search-plus-all-reads, so its adapter column
is not substituted for this native-search column.

| Component | Evidence recall | Complete evidence | Packed-context MRR | Mean context tokens | Search p50 / p95 ms |
|---|---:|---:|---:|---:|---:|
| Book — default lexical | 76.28% | 52.34% | 0.8132 | 719.8 | 1.766 / 2.784 |
| Book — optional Q2 | 76.77% | 54.69% | 0.8239 | 739.0 | 7.415 / 11.226 |
| claude-mem 15.18.1 FTS | 70.68% | 45.31% | 0.7674 | 715.8 | 11.494 / 22.484 |
| ai-memory v3.4.5 local hybrid | 77.27% | 55.86% | 0.8182 | 716.8 | 21.168 / 27.545 |
| billion-context 9674cfa kernel | 78.91% | 58.20% | 0.8277 | 762.3 | 0.189 / 0.793 |

Default Book exceeds claude-mem complete evidence by **7.03 percentage points**
and has lower recorded search p95 than claude-mem and ai-memory. Q2 exceeds
Book's default by **2.34 points** and claude-mem by **9.38 points**. ai-memory
has higher completeness than both Book modes. Billion-context leads displayed
recall, completeness, MRR and search latency. These results support specific
advantages; they do not establish overall product superiority.

![Current component comparison and separate paired performance study](assets/v0.3.1-comparison.svg)

Book measures in-process Python retrieval including native context assembly;
claude-mem uses SQLite/Bun; ai-memory uses local HTTP/MCP; billion-context uses
its supplied-source Node search kernel. Book's component **2.784 ms** p95 is
not its actual MCP p95. Full capture, compression, generation, preparation and
common packing are separate; no whole-product speed ratio follows.

### Native budgets and retained losses

Native Book uses excerpt assembly, an 8,000-character cap, a top-five limit,
both tokenizers, budgets 512/1,024/2,048, no result cache and one repetition.
Default baseline/candidate output and quality remain identical in every
registered cell. The native single-pass speed measurements do not replace
the separate balanced-order release performance gate.

| Native view | Default complete evidence | Q2 complete evidence | Interpretation |
|---|---:|---:|---|
| 512 cl100k_base | 35.94% | 33.59% | Q2 evidence recall also falls: 65.73% → 64.74% |
| 512 o200k_base | 35.55% | 33.20% | Q2 evidence recall also falls: 65.73% → 64.58% |
| 1,024 or 2,048, either tokenizer | 52.34% | 54.69% | Aggregate gain; each cell still has 18 complete-question losses and 30 annotation losses |

Q2 remains optional. The full assessment records every gain/loss identity for
native and common-packed responses; their 512-token values differ because
the packing policies differ. Only **six questions** are in the low-lexical-
overlap diagnostic. All 256 questions are answerable. This run does not
measure abstention, hallucination rates or generated-answer accuracy, and
mapping encyclopedia paragraphs to sessions does not establish transfer to
private conversations. Once scored, these questions are regression data.

### Response, read and setup costs

These are **o200k_base reference tokens**, averaged over first-pass questions.
Payload tokens describe native returned objects, not the common capped
evidence context. Latency sums each question's first search and all its reads
before computing a percentile; separate p95 values are never added.

| Component | Search payload tokens | Extra read payload tokens | Reads/query | First search + all reads p95 ms |
|---|---:|---:|---:|---:|
| Book — default | 3998.4 | 0.0 | 0 | 2.818 |
| Book — Q2 | 4112.5 | 0.0 | 0 | 11.046 |
| claude-mem FTS | 1625.7 | 0.0 | 0 | 22.931 |
| ai-memory hybrid | 1023.4 | 1834.9 | 5 | 30.532 |
| billion-context kernel | 575.8 | 0.0 | 0 | 1.480 |

Default Book returns a larger full native JSON object at this boundary. Its
separately measured optional indexed MCP representation must not be inserted
into this table. ai-memory reads all five mapped pages under the registered
policy; an agent could request fewer. Native text, native payload and common
packed context stay separate throughout the complete summaries.

Book native fresh ingestion is **4.214 s**. Q2 native preparation separately
records **4.148 s** ingestion, **0.863 s** model loading and **110.094 s** index
construction for 4,831 windows; its vector payload is 7,420,416 bytes.
ai-memory's full registered setup takes **644.735 s**. These preparation
operations differ and are not an end-to-end ingestion race. All configured
generative-model calls are zero; Q2 and hybrid modes still perform embedding
work. Full model/download/state costs remain in the original summaries.
Sampled worker-plus-descendants RSS includes evaluator and corpus memory,
can double-count shared pages and is an observed lower bound, not pure
product RAM. Reference-token counts are not provider bills.

### Separate baseline efficiency and release decisions

The original [47,320-call ABBA study](round3-performance-review.md) compares
v0.3.0 with this runtime across two regression corpora, four balanced rounds
and ten configurations. It preserves complete evidence payloads and gives
**11.36% geometric mean pooled p95 improvement**. On the public cohort at
4,000 characters, native p95 falls **5.054 → 3.737 ms (26.05%)**, and actual
SDK MCP p95 falls **7.409 → 5.937 ms (19.87%)**. Synthetic 512-token p95 rises
0.12%; no pooled p50/p95 regression exceeds 5%.

The original startup mean rises **34.46 → 39.29 ms (+14.04%)** and its
automatic `accepted: false` is preserved. Independent source/resource review
accepts the query optimization with the startup observation disclosed.
An existing 80-sample startup-only diagnostic is supplemental; it does not
replace the original run or prove its exact operating-system cause.

The [quality recovery review](round3-quality-review.md) reconstructs 8,082
original calls without rerunning scoring and matches the canonical hosted
recovery. The project-local FTS-statistics candidate fails 14 registered
checks and remains unshipped. The [reconciliation record](round3-reconciliation.md)
preserves the authoritative earlier registration, the unused later local
binding, the raw-source exposure disclosure, and the interruption history.
No completed result was rerun to select better timings or scores.

## Historical: v0.3.0 implementation and evidence

The following round-two sections retain their original measurements. Their
uses of “current” refer to that historical source, not the v0.3.1 view above.

The selected implementation is frozen at
[`cbf6260`](https://github.com/Afloat16/AI-Memory-Book/commit/cbf626037b42f11f8bc5b6d46f56caac771e54ba).
Its default path remains lexical. The improvements included in v0.3.0
have separate measurement boundaries:

| Area | Completed evidence | Interpretation |
|---|---|---|
| Default retrieval and ingestion | [56,784-call paired performance report](default-recall-performance.md) | Identical complete evidence payloads; lower pooled p95 in all 12 configurations; fresh import and unchanged replay costs measured separately |
| Optional semantic fusion | [48,492-call Q2 development matrix](../benchmarks/reports/round2-anchor-development.md) | Aggregate complete evidence and annotation recall meet or exceed original RRF in 12 old cohort/budget settings; individual and diagnostic-group losses remain visible |
| Indexed MCP references | [Operator configuration and format](indexed-references.md) | Explicit, reversible representation; original context and detailed offsets preserved; default schemas and instructions unchanged |
| Current component comparison | [Complete 32,256-call same-host matrix](../benchmarks/results/round2-43207732852-1/report.md) | Fixed-source recovery completed; all budgets, native/shared-context costs, source checks and negative results preserved |

The older LoCoMo component measurements below retain their original source
pins and interface boundaries. They are regression evidence. The new upstream
[registration](../benchmarks/experiments/round2-upstream-registration.json)
pins claude-mem 15.18.1, ai-memory v3.4.5 and the current billion-context kernel
for the independent comparison without rewriting those historical records.

## Current frozen 256-question comparison

The complete [same-host report](../benchmarks/results/round2-43207732852-1/report.md) measures the current source at `cbf6260` and the upstream revisions in the [registration](../benchmarks/experiments/round2-upstream-registration.json). It contains **10 completed stages and 32,256 timed search calls**, including 3,072 distinct lexical baseline/candidate native query/configuration pairs. Default contexts and their evidence scores are identical in all those pairs. The two lexical component modes also have identical quality. No generative model calls are configured in this retrieval experiment.

The 256 preselected HotpotQA questions retain all 2,539 supplied paragraphs, 3,769 canonical pages and 614 required annotations. All questions are answerable. One annotation cannot be fully represented by a single canonical page under the fixed scorer; it stays in the denominator. Each paragraph maps to a separate source session/chapter, so the multi-hop groups do not establish transfer to private conversations. This is another selection from the previously used external distractor corpus, not a new-domain generalization claim.

### Current shared-page quality and search latency

This display uses **1,024 cl100k_base tokens**. The complete report retains both encodings at all three budgets. Every component sees the same source pages, project scope, top-five limit, citations and whole-block packer. Quality uses the first result for each question; search timings pool all three repetitions. MRR measures the first evidence position in the packed context, after metadata or oversized blocks omitted by packing.

| Current component | Evidence recall | Complete evidence | Packed-context MRR | Mean context tokens | Search p50 / p95 / mean ms |
|---|---:|---:|---:|---:|---:|
| Book — default lexical | 75.41% | 51.95% | 0.8596 | 712.9 | 4.712 / 8.301 / 4.919 |
| Book — optional Q2 | 78.66% | 57.81% | 0.8686 | 727.8 | 14.014 / 22.523 / 14.638 |
| claude-mem 15.18.1 FTS | 72.31% | 48.83% | 0.8348 | 704.5 | 16.254 / 29.948 / 17.076 |
| ai-memory v3.4.5 hybrid | 76.22% | 53.91% | 0.8633 | 704.0 | 25.947 / 33.251 / 26.516 |
| billion-context 9674cfa kernel | 80.94% | 61.72% | 0.8622 | 751.3 | 0.349 / 1.092 / 0.505 |

Q2 improves complete evidence by **5.86 percentage points over the current lexical default**, **8.98 points over claude-mem FTS**, and **3.91 points over ai-memory** in this view. It has the highest packed-context MRR here. Billion-context has higher annotation recall and complete evidence and a faster search kernel. Default Book remains the model-free recommendation; optional Q2 adds model/index costs and does not improve every question or budget.

Book measures Python retrieval and native context assembly; claude-mem executes unchanged Bun/SQLite FTS; ai-memory uses local HTTP/MCP; billion-context executes its Node search kernel. Common packing, preparation, full product observation/compression and answer generation are separate. These same-host component timings are not interchangeable whole-product speed ratios. First-pass and repeat-pass values remain in each complete summary; no fastest repeat is selected.

### Native API packing and small-budget tradeoffs

Native Book assembles excerpts and original source units rather than the shared whole-page benchmark response. At the same displayed 1,024 cl100k budget its exact measurements are:

| Current native mode | Character cap | Complete evidence | Evidence recall | Mean context tokens | p50 / p95 ms |
|---|---:|---:|---:|---:|---:|
| Book native — default lexical | 2000 | 28.52% | 59.12% | 674.1 | 7.931 / 13.325 |
| Book native — default lexical | 8000 | 51.95% | 75.57% | 801.7 | 6.150 / 9.841 |
| Book native — optional Q2 | 2000 | 32.81% | 60.75% | 674.6 | 17.177 / 28.208 |
| Book native — optional Q2 | 8000 | 57.42% | 78.50% | 816.2 | 15.517 / 24.227 |

The current lexical implementation preserves all 3,072 baseline contexts and lowers p50 and p95 in every one of the 12 native configurations on this host: p50 by **4.53%–5.97%**, p95 by **1.88%–4.49%**. Its source ingestion takes **4.884 s versus 6.550 s** for the baseline. The separate [balanced-order regression performance study](default-recall-performance.md) supplies four-round evidence on the old synthetic/public cohorts.

Q2 native completeness at 8,000 characters / 1,024 cl100k tokens has **23 gains and 9 losses** against lexical; the component view has **24 gains and 9 losses**. At **512 o200k tokens**, native completeness falls **24.22% → 23.83%** with 2,000 characters and **42.19% → 41.02%** with 8,000. At 512 cl100k tokens the native complete rates tie, while annotation recall decreases. These losses are retained, and Q2 stays optional.

The low-overlap group contains only **nine questions**. At 1,024 cl100k tokens / 8,000 characters, native lexical/Q2 completeness is **1/9 → 2/9**. With shared whole-page packing it is **1/9 lexical, 2/9 Q2, 2/9 claude-mem, 3/9 ai-memory and 3/9 billion-context**. At 512 tokens the component Q2 result is still **0/9**. These small overlapping diagnostics do not show that low-overlap or multi-hop memory is solved.

### Returned payloads and declared full reads

The following are **o200k_base reference tokens**, averaged over the 256 first-pass questions. Native payload and native text are separate surfaces; neither is the common capped context above. The [independent cost audit](../benchmarks/reports/round2-43207732852-1-component-cost-audit.md) recomputes every numerical cost field for both tokenizers and all 36 component/context configurations.

| Current component | Search payload tokens | Native text tokens | Extra read payload tokens | Extra read text tokens | Reads/query | Mean read ms | First search + all reads p50 / p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| Book — default lexical | 4001.8 | 801.3 | 0.0 | 0.0 | 0.0000 | 0.000 | 4.713 / 8.396 |
| Book — optional Q2 | 4099.1 | 817.8 | 0.0 | 0.0 | 0.0000 | 0.000 | 13.895 / 22.530 |
| claude-mem 15.18.1 FTS | 1612.3 | unavailable | 0.0 | 0.0 | 0.0000 | 0.000 | 16.218 / 30.056 |
| ai-memory v3.4.5 hybrid | 1016.3 | 950.4 | 1811.5 | 1591.6 | 4.9766 | 4.294 | 30.292 / 37.613 |
| billion-context 9674cfa kernel | 579.3 | unavailable | 0.0 | 0.0 | 0.0000 | 0.000 | 0.756 / 1.410 |

Book here returns the full Python recall object; its native text is the context at the registered **100,000-character ranking cap before common packing**. It is not compact MCP output. ai-memory text is its actual MCP text content, which can still contain JSON/metadata; its payload is the MCP result envelope. Claude-mem and billion bridges do not expose a separate text surface, so unavailable stays unavailable. Default Book has a larger native JSON payload at this boundary; the separately measured [opt-in indexed MCP format](indexed-references.md) must not be substituted into this table.

ai-memory reads every mapped top-five page on the first pass under the fixed policy. An agent could choose fewer reads. Its search-plus-read means are **2,827.8 payload tokens / 2,542.1 text tokens** under o200k_base. Combined latency first sums each question’s search roundtrip and all its reads, then computes percentiles; it never adds two p95 values. All six measured component modes, including baseline, have zero metadata hits and zero repeated-hit changes in this run. The native metadata-slot policy remains explicit and earns no evidence credit when such hits occur.

### Preparation, memory and live state

Every setup value excludes query time. Book native rows perform source ingestion; its component rows open/copy the already-ingested common archive, with an explicit index build for Q2. Those are different preparation operations and must not be presented as one ingestion-speed race.

| Current mode | Setup s | Setup tree RSS MiB | Query tree RSS MiB | Worker peak RSS MiB | Live native state MiB |
|---|---:|---:|---:|---:|---:|
| Book native — default lexical | 4.941 | 333.63 | 280.68 | 844.18 | 35.50 |
| Book native — optional Q2 | 213.432 | 1012.74 | 1041.29 | 1069.42 | 52.83 |
| Book — default lexical | 0.226 | 333.62 | 224.00 | 844.18 | 30.62 |
| Book — optional Q2 | 208.929 | 969.62 | 970.07 | 1011.91 | 48.93 |
| claude-mem 15.18.1 FTS | 2.005 | 415.58 | 377.07 | 844.18 | 19.13 |
| ai-memory v3.4.5 hybrid | 679.307 | 469.82 | 469.20 | 844.18 | 67.42 |
| billion-context 9674cfa kernel | 0.173 | 333.51 | 401.94 | 844.18 | 0.00 |

Tree RSS is sampled every 20 ms and includes the evaluator, loaded corpus and descendants. It is an observed lower bound and shared mappings can be counted more than once. Worker peak RSS is the separate OS high-water measurement, also including the harness; it is not pure product RAM. Live state includes product-specific native files/logs, excludes the attempt ledger and symlinked model caches, and is not peak disk usage. Billion’s zero persistent state describes this in-memory search-kernel harness, not its complete proxy. The full reports retain exact regular-file and SQLite main/WAL/SHM bytes before/after close.

Current native Book ingestion is **4.884 s**. Q2 separately loads its model in **1.029 s** and builds **4,566 windows over 3,769 pages in 207.559 s**, with **7,013,376 vector bytes**; native setup totals 213.432 s. A compatible existing index can be reused across the fusion update. ai-memory’s native page ingestion takes **677.086 s**; its subsequent 1.172 s backfill reports zero new embeds and 3,770 skipped pages, so it is not a second full embedding-build measurement. Claude-mem’s cached source verification, startup, schema/FTS creation and supplied-page loading remain separate fields in its summary.

Initial download/verification preparation began with empty measured caches. Cache bytes below include the resulting artifacts, and for some tasks extracted/compiled files; they are **not network-transfer bytes**. Python/Node provisioning and dependency installation are outside these task timers.

| Preparation task | Measured wall s | Prepared regular-file bytes | Files |
|---|---:|---:|---:|
| verified hotpot download and conversion | 1.515 | 73,383,918 | 2 |
| reference tokenizers | 1.408 | 5,295,048 | 2 |
| ai memory binary and embedding | 1.994 | 174,868,526 | 6 |
| claude mem source and bun | 4.657 | 178,639,496 | 986 |
| billion context source | 1.968 | 163,611 | 31 |
| book semantic model | 1.416 | 127,535,388 | 2 |

The default lexical Book path has no semantic model requirement. Its optional pinned model consists of **127,535,388 verified bytes**. Tokenizer cache costs are needed for these exact-budget reference measurements; ordinary character-only retrieval has no tokenizer dependency. No API dollar cost, energy use or concurrent throughput is inferred from these phase measurements.

### Fixed source, failure retention and independent checks

The runtime was frozen at [`cbf6260`](https://github.com/Afloat16/AI-Memory-Book/commit/cbf626037b42f11f8bc5b6d46f56caac771e54ba) before the first score. The original run stopped at an adapter-field parsing error; all 13 original files remain preserved. The registered recovery changes that evaluator interface only, runs the entire matrix on one new host, and retains the original data, budgets, optional modes and source pins. The completed result commit is [`057b814`](https://github.com/Afloat16/AI-Memory-Book/commit/057b814ab809dec57d4fa4c75fe540d59a0f0027); [Actions 43207732852](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43207732852) succeeded.

An independent strict recomputation verifies all 23 published files and every declared stage/axis/attempt. The [recovery audit](round2-recovery-audit.md) finds identical supplied pages, query/evidence/group records and repeated non-timing samples across the five shared completed stages. It also retains five copies of one differing full original-store snapshot hash. The snapshot includes automatic write-time metadata, but absent the old databases the cause cannot be proven to be only timestamps. That audit is explicitly `completed_with_differences`; no timing samples from the two hosts are pooled. The separate [numeric cost audit](../benchmarks/reports/round2-43207732852-1-component-cost-audit.json) passes all six components and 1,536 first-pass cost records.

The candidate was not retuned from this selection. The questions become regression data after scoring. These checks establish measurement integrity within the stated boundaries; they do not establish final-answer accuracy, abstention on unanswerable queries, native observation/compression workflows for all products, or universal superiority.

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

## Historical search and delivery latency

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

## Historical returned tokens, preparation and storage

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
