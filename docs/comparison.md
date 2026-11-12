# Comparison guide: evidence quality, cost and deployment

AI-Memory-Book keeps original conversations in a local Python/SQLite archive and
returns a bounded evidence context with exact source addresses. Default retrieval
needs no generative model, embedding download or separate database service.
Optional Q2 semantic fusion adds a local model and index.

## v0.3.1: measured advantages and remaining gaps

The accepted runtime is frozen at
[`2d199b9`](https://github.com/Afloat16/AI-Memory-Book/commit/2d199b93f650eccd3dd239178822b31001b880e3).
The [registered protocol](../benchmarks/experiments/round3-plan.json), complete
[round-three comparison](../benchmarks/results/round3-comparison-43267797247-1/report.md) and
[performance resource review](round3-performance-review.md) separate
version-to-version performance from cross-repository retrieval quality.

- The formal **47,320-call / 16-worker / four-round balanced-order** version
  comparison preserves complete non-timing payloads. Geometric-mean pooled p95
  improves **11.3587%** across ten cells; public native p95 improves **26.0501%**
  and actual MCP stdio p95 **19.8677%**.
- On the registered current HotpotQA selection, default Book has higher evidence
  recall and complete evidence than the tested claude-mem FTS component at every
  displayed budget/tokenizer. At 1,024 cl100k tokens, the differences are
  **+5.60 and +7.03 percentage points**, respectively.
- ai-memory and billion-context have higher complete evidence than default Book
  in that current 1,024-token view. Billion-context also has a faster search
  kernel. These results do not establish universal product superiority.
- Default Book keeps its model-free operational path and one complete recall
  response. This component benchmark returns the full Python object, whose
  native JSON payload is larger than the other adapters' payloads. The separate
  [indexed MCP format](indexed-references.md) is optional and is not substituted
  into the measurements below.

The historical v0.3.0 guide is preserved byte for byte as
[comparison-v0.3.0.md](comparison-v0.3.0.md). Historical LoCoMo results,
generated-answer experiments and the earlier small-model workflow remain
available there with their original sources, limitations and negative results.

![Current component and separate baseline performance results](assets/v0.3.1-comparison.svg)

The figure uses the recorded search-adapter boundary, matching the current
README and generated report. Native-search-only timings remain separate in
the raw summaries. The [supplemental offline verification](../benchmarks/reports/round3-recovery/comparison-cross-verification.json)
checks all 32 result blobs, all 71 original bound evaluator hashes and exact
assessment/report recomputation. A separate [release byte comparison](../benchmarks/reports/round3-recovery/published-release-cross-verification.json)
confirms that the published source preserves all 71 bound evaluator files and
all 17 runtime/static files exactly.

## Current frozen 256-question comparison

[Run 43267797247](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43267797247)
completed all **ten stages and 9,216 actual search calls**: 4,608 native Book
calls and 4,608 component searches. Its immutable result is
[`c99f205`](https://github.com/Afloat16/AI-Memory-Book/commit/c99f20531053b1c164fc5a5d3fa8e0c831eeb4de).
The [strict assessment](../benchmarks/results/round3-comparison-43267797247-1/assessment.json)
is `complete-verified`, with no validation failures. All **1,536 native
baseline/candidate pairs and 768 component pairs** have identical complete
non-timing payload hashes.

Runtime, evaluator, upstream, dependency and model identities were committed
before the ID selection. The 256 questions exclude both earlier selections and
contain **607 required evidence annotations**. The fixed ID-only selection is
another sample of the same public HotpotQA source, not a new domain or an
unexposed corpus. After the first score these IDs are regression data.
[Reconciliation](round3-reconciliation.md) identifies the single executed
registration and two unused preparations; no additional scoring run was started
to choose a better result.

All selected questions are answerable. The test measures returned source
evidence, not generated-answer accuracy, abstention, or a complete
capture/summarize/retrieve/answer workflow. No generative calls are configured.

### Common supplied-page quality

The table shows **1,024 cl100k_base tokens**, common source pages, project scope,
top five and the same citation-inclusive whole-page packer. Both tokenizers and
all three budgets (512/1,024/2,048) remain in the [full report](../benchmarks/results/round3-comparison-43267797247-1/report.md).
Quality uses the first response. MRR measures the first evidence position in
the packed context, after packing omits metadata or oversized pages.

| Component | Evidence recall | Complete evidence | Packed-context MRR | Mean context tokens |
|---|---:|---:|---:|---:|
| Book v0.3.1, default lexical | 76.28% | 52.34% | 0.8132 | 719.8 |
| Book v0.3.1, optional Q2 | 76.77% | 54.69% | 0.8239 | 739.0 |
| claude-mem 15.18.1 FTS | 70.68% | 45.31% | 0.7674 | 715.8 |
| ai-memory v3.4.5 hybrid | 77.27% | 55.86% | 0.8182 | 716.8 |
| billion-context 9674cfa kernel | 78.91% | 58.20% | 0.8277 | 762.3 |

The current default improves complete evidence over claude-mem by **7.03
percentage points**, while Q2's difference is **9.38 points**. Q2 improves over
Book lexical by **2.34 points** here, but remains below ai-memory and
billion-context. Current results supersede older samples for this selection;
historical improvements over all three components do not imply the same
ordering on every cohort.

### Native Book API and optional Q2 tradeoffs

These are actual native context responses, with an 8,000-character ceiling,
top five, no result cache and one call per query/configuration. Native packing
is distinct from the common whole-page projection.

| Native mode | cl100k cap | Evidence recall | Complete evidence | Mean context tokens | p50 / p95 ms |
|---|---:|---:|---:|---:|---:|
| v0.3.0 lexical | 512 | 65.73% | 35.94% | 476.5 | 4.695 / 7.485 |
| v0.3.1 lexical | 512 | 65.73% | 35.94% | 476.5 | 3.150 / 4.316 |
| v0.3.1 Q2 | 512 | 64.74% | 33.59% | 479.2 | 8.661 / 13.043 |
| v0.3.0 lexical | 1,024 | 76.28% | 52.34% | 808.0 | 4.213 / 7.295 |
| v0.3.1 lexical | 1,024 | 76.28% | 52.34% | 808.0 | 2.707 / 3.828 |
| v0.3.1 Q2 | 1,024 | 76.77% | 54.69% | 824.4 | 9.058 / 12.895 |

At 1,024 cl100k tokens, Q2 has **24 complete-question gains and 18 losses**.
At 512 tokens it has **22 gains and 28 losses**; both complete evidence and
annotation recall decline. The o200k 512-token native result also declines,
from **35.55% to 33.20%** complete evidence. Q2 remains optional; the default
ranking is unchanged. These native timings are descriptive single-run values,
while the independent balanced-order study supplies the release speed gate.

The low lexical-overlap group has only **six questions**. At 512 cl100k tokens,
native lexical/Q2 completeness is **0/6 for both**, although evidence recall
rises from 33.33% to 50.00%. In the component view, Book lexical, Q2 and
claude-mem also complete 0/6; ai-memory and billion-context complete 1/6.
Every question is mapped across supplied paragraph sessions/chapters, so those
labels do not prove transfer across private conversational sessions.

### Search, reads and actual payload costs

Search-adapter timings pool three real repetitions; the six offline budget
projections reuse the first response. Search-plus-reads sums each first-pass
query's actual roundtrips before computing percentiles. It does not add p95
values. No replacement searches or extra scoring calls occur.

| Component | Search p50 / p95 ms | First search + all reads p50 / p95 ms | Search payload cl100k / o200k tokens | Read payload cl100k / o200k tokens | Reads/query |
|---|---:|---:|---:|---:|---:|
| Book lexical | 1.766 / 2.784 | 1.756 / 2.818 | 3983.5 / 3998.4 | 0.0 / 0.0 | 0.00 |
| Book Q2 | 7.415 / 11.226 | 7.365 / 11.046 | 4097.3 / 4112.5 | 0.0 / 0.0 | 0.00 |
| claude-mem FTS | 11.781 / 22.826 | 11.982 / 22.931 | 1641.3 / 1625.7 | 0.0 / 0.0 | 0.00 |
| ai-memory hybrid | 21.168 / 27.545 | 23.966 / 30.532 | 1026.3 / 1023.4 | 1843.1 / 1834.9 | 5.00 |
| billion-context kernel | 0.285 / 1.010 | 0.689 / 1.480 | 582.7 / 575.8 | 0.0 / 0.0 | 0.00 |

Book is in-process Python including native context assembly; claude-mem is
unchanged SQLite/Bun; ai-memory is local hybrid HTTP/MCP; billion-context is its
supplied-source search kernel/Node. These are distinct component boundaries,
not interchangeable whole-product timings. The complete Book object uses a
100,000-character ranking cap before common packing; it is not compact MCP
output. Native response payload, native text and capped packed context are
different token surfaces.

ai-memory's policy reads every mapped top-five page on the first pass. An agent
could choose fewer reads. Metadata hits retain their original top-five slots
and payload cost but earn no evidence credit; there is no replacement search.
Original ranks, returned IDs, read calls, repeat changes and costs remain in
the raw reports and ledgers.

### Setup, memory and persistent state

Book native setup freshly ingests source. Book component setup copies a
canonical archive; Q2 additionally loads its model and builds the index.
The different setup operations are not a common ingestion-speed race.

| Mode | Setup s | Setup tree RSS MiB | Query tree RSS MiB | Native state bytes |
|---|---:|---:|---:|---:|
| Book native lexical | 4.236 | 549.47 | 533.07 | 40,280,936 |
| Book native Q2 | 115.130 | 1286.11 | 1269.98 | 54,988,384 |
| Book component lexical | 0.547 | 549.66 | 529.17 | 33,808,384 |
| Book component Q2 | 112.553 | 1233.96 | 1234.28 | 54,016,064 |
| claude-mem FTS | 1.590 | 675.75 | 635.18 | 20,626,650 |
| ai-memory hybrid | 644.735 | 716.75 | 714.48 | 73,818,921 |
| billion-context kernel | 0.163 | 558.29 | 675.97 | 0 |

RSS is sampled worker-plus-descendants every 20 ms. It includes evaluator/data
memory, may count shared pages more than once, and is an observed lower bound;
it is not pure product RAM. Native state excludes symlinked model caches.
Billion's zero describes this in-memory kernel harness, not its complete proxy.
SQLite main/WAL/SHM and detailed phase costs remain in the summaries. Q2's
persisted native/component index-vector digests match; this does not assert
separately measured query-embedding identity.

### Version performance and accepted resource cost

The [formal performance review](round3-performance-review.md) preserves all
47,320 calls, all rounds and original automatic decisions. Its numeric speed
gate passed. Synthetic 512-token p95 changes **+0.1248%** and remains visible.
The empty-database opening mean changes **34.455720 → 39.294103 ms**
(**+4.838384 ms / +14.0423%**), triggering the registered resource review.
The separate [decision](../benchmarks/experiments/round3-startup-resource-decision.json)
accepts that disclosed cost; the original automatic `accepted: false` remains
unchanged. Static/SQL checks found no new initialization operation, but do not
prove the exact OS cause of the longest historical sample. The supplemental
80-sample diagnostic is separate and retains its **+5.8219% plain p95**.

The project-local statistics experiment recovered all **8,082 original calls**
without rerunning retrieval, failed **14 registered loss checks**, and was
rejected. It is not enabled in the shipped runtime or the current comparison.
See [quality review](round3-quality-review.md) and
[completed optimization record](optimization-round3.md).

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

## Historical and unmeasured boundaries

The [preserved v0.3.0 comparison](comparison-v0.3.0.md) contains the full
historical LoCoMo matrix, older Hotpot selection, native answer experiment and
small-model consolidation workflow. Each retains its original source pin,
host, failure records and denominator. Do not pool those timings with this run
or present historical scores as fresh v0.3.1 answer measurements.

Mem0, Graphiti, PageIndex and Letta are architectural comparisons here, not
executed performance victories. Neither this round nor its integrity checks
measure production concurrency, adaptive agent policies, provider billing,
energy, private-user data, unanswerable-query abstention, or all competitors'
native observation/compression/generation workflows. Unknown costs stay unknown.
