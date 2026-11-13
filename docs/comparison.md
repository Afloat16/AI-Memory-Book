# Comparison guide: evidence quality, cost and deployment

AI-Memory-Book keeps original conversations in a local Python/SQLite archive and
returns a bounded evidence context with exact source addresses. Default retrieval
needs no generative model, embedding download or separate database service.
Optional Q2 semantic fusion adds a local model and index.

## v0.3.2: verified performance, fresh comparison pending

**The fixed C2 candidate passes the registered formal performance gate. The new
256-question comparison and final release verification remain pending.** This
page separates completed version-to-version measurements from the still
unassessed cross-repository comparison. It makes no v0.3.2 publication claim.

C2 is frozen at
[`2d7b5e3`](https://github.com/Afloat16/AI-Memory-Book/commit/2d7b5e38839fb21724ad3beec6b6ebabbda45636).
It reduces repeated source projection and exact token-counting work while
preserving default ranking, source coordinates, budgets and response formats.
Q2's model, vectors and fusion are unchanged. The [implementation and decision
history](optimization-round4.md) records the retained changes, rejected cache,
restored highlight query and all development attempts.

The [formal review][formal-review] verifies **56,784 calls, 16 workers and four
balanced rounds**. All complete non-timing outputs agree. The geometric mean of
pooled p95 improves **10.1294%** across twelve cells, with **10.8021%** lower
public actual-MCP token-1024 p95. All automatic gates pass without a resource
exception. The aggregate clears its 10% threshold by only **0.1294 percentage
points**; it does not establish statistical significance or a universal speedup.

Tradeoffs remain visible: public MCP character-budget p95 rises **1.4445%**, and
the largest registered resource mean increase is **6.0231%** for public MCP
token-session startup. Exact costs and all adverse rounds appear below and in
[the independent audit][formal-audit]. No output-token saving is claimed.

The previous guide is preserved byte for byte as
[comparison-v0.3.1.md](comparison-v0.3.1.md). Its completed Hotpot scores and
competitor ordering belong to that earlier selection. [The round-three report](round3-comparison.md)
and [v0.3.0 archive](comparison-v0.3.0.md) retain earlier evidence and limitations.
No prior score is carried into the pending tables on this page.

## Version performance and resource costs

The sole hosted formal run is
[43361086255-1](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43361086255),
with immutable results at
[`1bd76f3`](https://github.com/Afloat16/AI-Memory-Book/commit/1bd76f3b70eb60ead444f05c5a94148e9e384bba).
It compares published v0.3.1 at `7b7a5d7336b9350a128f5e0a888811b1b3015e68`
with C2 on 168 synthetic and 1,015 previously used public-conversation queries.
Each cohort runs source orders **AB, BA, BA, AB** in fresh workers. Every public
source/configuration contributes **4,060 calls**; every synthetic one contributes
672. These repetitions do not create new independent questions. [Plan][plan] ·
[Completed summary][formal-summary]

| Public-conversation configuration | v0.3.1 p95, ms | C2 p95, ms | Change |
|---|---:|---:|---:|
| Native, 4,000 characters | 2.361452 | 2.198754 | −6.8897% |
| Actual SDK MCP, 4,000 characters | 3.467968 | 3.518062 | **+1.4445%** |
| Native, 512 tokens | 3.793969 | 3.070323 | −19.0736% |
| Native, 1,024 tokens | 3.199822 | 2.610729 | −18.4102% |
| Native, 2,048 tokens | 3.129763 | 2.560117 | −18.2009% |
| Actual SDK MCP, 1,024 tokens | 4.357927 | 3.887177 | −10.8021% |

Token configurations use `cl100k_base`, an 8,000-character ceiling and limit 5.
Native timing covers the complete uncached recall. MCP timing covers the actual
SDK stdio call through its returned result, including normal server cache writes;
cache deletion/commit happens before timing. Validation and reference token
counting happen outside the timer. OS/SQLite caches warm naturally. These are
not OS-cold measurements or estimates derived from native calls. [Timing boundary][formal-review]

Acceptance uses the equal-weight geometric mean of all **twelve pooled p95
ratios**. It requires at least 10% overall improvement, 15% in at least one
public native token cell, 10% in public actual MCP token-1024, and no pooled
p50/p95 regression above 5%. All pass. The synthetic native character p95
improvement is just **0.0391%**. Round-specific aggregate improvements are
**7.9998%, 9.6256%, 10.6865% and 11.1748%**; the registered gate uses all rounds
pooled. [All twelve cells and every adverse round][formal-review]

Individual round metrics can exceed 5%: synthetic MCP character round 1 has
**+5.8158% p50** and **+5.3981% mean** latency. The 5% gate applies to pooled
p50/p95. All 19 positive per-round metric changes remain in the review.

The independent review retains all **28 resource comparisons** and their raw
four-sample inputs. Public MCP token-session startup changes
**345.683341 → 366.504056 ms (+6.0231%)**. No registered resource mean crosses
its 10% review threshold, so no waiver is needed. Individual samples can still
regress: synthetic round-1 ingestion rises **13.4300%**, while its four-round
mean changes **−0.0786%**. These observations support neither a general startup
improvement nor a population-tail claim. [Resource samples][formal-audit]

Complete native payloads, actual MCP text/envelopes, source references, response
bytes and both reference encoders' token-cost summaries match. The strict ledger
audit and independent arithmetic review performed no new retrieval or timing.
All original rows, first/repeat partitions and negative metrics remain available.
This formal comparison concerns Book versions; it supplies no whole-product
speed ratio against another repository. [Strict audit][formal-local-audit] ·
[Raw report][formal-raw]

## Current frozen 256-question comparison

**Pending: run 43363060062-1 has not yet been accepted from a complete-verified
checkpoint and strict audit.** The sections below describe the frozen protocol;
all fresh scores, costs and competitor conclusions remain pending. Partial
stage outputs are not used to fill them.

The [registered plan][plan] and [runtime/evaluator binding][comparison-binding]
fix source, model, dependency and component identities and were committed before
ID selection. The resulting [selection manifest][comparison-manifest] was
committed before scoring. Selection reads IDs first and excludes
all **640** earlier Hotpot IDs. This selection has **256 questions and 635
required evidence annotations**, with zero prior-ID overlap. It is another
selection from the same public HotpotQA source, not a new domain or an unexposed
corpus. After scoring, its questions become regression data.

| Frozen item | Identity |
|---|---|
| Baseline / candidate | v0.3.1 `7b7a5d7` / C2 `2d7b5e3` |
| Comparison evaluator commit | `d6aa80c7df80f017d301dd93102210b4c968231c` |
| Binding SHA-256 | `84dbe28c068a3067f9706c6439d42301eaddfef95c44ae2633398346c66a8c79` |
| Selection manifest SHA-256 | `b0485b3a089c9b04fc4453fd9f129364e123ce1b9f25b593edf4f6ee6df4a20b` |
| Dataset SHA-256 | `fb3cd70ea58fafa5bd9cef0f04dba7399aaafba76f5f92605eee9e516f115e1b` |
| Source revision | HotpotQA dev distractor `1908d6afbbead072334abe2965f91bd2709910ab` |

The target matrix has **ten stages, 4,608 native calls and 4,608 component
searches**. Its **54 quality cells** comprise 18 native cells (three Book modes
× two tokenizers × three budgets) and 36 common-packing cells (six component
modes × the same six budget/tokenizer settings). Common packing reuses the
first response; it does not add search calls. The component baseline is kept
for complete-payload equivalence, even where the overview displays only C2 and
external components. [Registered axes][plan]

All questions are answerable. Metrics concern returned source evidence, not
generated-answer accuracy, hallucination/abstention, or a complete
capture/summarize/retrieve/answer workflow. No generative model calls are
configured. Strict checks must cover sources, scope, character/token limits,
all planned calls and baseline/candidate complete-payload equality. Passing
integrity does not itself prove a quality advantage.

### Common supplied-page quality

**Pending: no new quality scores or repository ranking are asserted.** The
reference view will use the same supplied pages, project scope, top five and
citation-inclusive whole-page packing at **1,024 `cl100k_base` tokens**.
Evidence recall uses the 635 required annotations; complete evidence requires
all annotations for a question. MRR measures the first evidence position in
the packed context after metadata or oversized pages have been omitted.
All six budget/tokenizer cells remain part of the assessment.

| Component | Evidence recall | Complete evidence | Packed-context MRR | Mean context tokens |
|---|---:|---:|---:|---:|
| Book v0.3.2, default lexical | Pending | Pending | Pending | Pending |
| Book v0.3.2, optional Q2 | Pending | Pending | Pending | Pending |
| claude-mem 15.18.1 FTS | Pending | Pending | Pending | Pending |
| ai-memory v3.4.5 hybrid | Pending | Pending | Pending | Pending |
| billion-context 9674cfa kernel | Pending | Pending | Pending | Pending |

The final comparison must retain competitors' strengths, every Book shortfall,
budget-specific changes and per-question gains/losses. The saved-results figure
will be generated only after the full checkpoint and audit pass; the earlier
v0.3.1 figure remains in its archived guide.

### Native Book API and optional Q2 tradeoffs

Native calls use an 8,000-character ceiling, top five, no result cache and one
call per query/configuration. Native source-unit packing is distinct from the
common whole-page projection. **All 18 native cells are pending**, including
recall, completeness, MRR, context tokens and p50/p95.

| Tokenizer / cap | v0.3.1 lexical completeness | C2 lexical completeness | C2 Q2 completeness | Q2 complete-question gains / losses |
|---|---:|---:|---:|---:|
| cl100k / 512 | Pending | Pending | Pending | Pending |
| cl100k / 1,024 | Pending | Pending | Pending | Pending |
| cl100k / 2,048 | Pending | Pending | Pending | Pending |
| o200k / 512 | Pending | Pending | Pending | Pending |
| o200k / 1,024 | Pending | Pending | Pending | Pending |
| o200k / 2,048 | Pending | Pending | Pending | Pending |

Q2 remains optional. Its completed, separate [old-data compatibility audit](../benchmarks/reports/round4-compatibility-final/paired-audit.json)
verifies 1,968 calls and 984 complete non-latency payload pairs against v0.3.1
using identical saved vectors. That is compatibility evidence, not a new quality
result. Fresh Q2 gains/losses, small-group denominators, semantic setup costs and
native/component vector checks remain pending. Cross-session/chapter labels
come from supplied encyclopedia paragraphs mapped into archive structure; they
do not demonstrate private conversational transfer.

### Search, reads and actual payload costs

**Pending: exact fresh latency, read and payload costs.** Search-adapter timing
pools three actual repetitions; six offline packing projections reuse only the
first response. Search-plus-reads adds each first-pass query's real roundtrips
before computing percentiles. It does not add independently computed p95 values.

| Component | Adapter search p50 / p95 ms | First search + all reads p50 / p95 ms | Search payload cl100k / o200k tokens | Read payload cl100k / o200k tokens | Reads/query |
|---|---:|---:|---:|---:|---:|
| Book lexical | Pending | Pending | Pending | Pending | Pending |
| Book Q2 | Pending | Pending | Pending | Pending | Pending |
| claude-mem FTS | Pending | Pending | Pending | Pending | Pending |
| ai-memory hybrid | Pending | Pending | Pending | Pending | Pending |
| billion-context kernel | Pending | Pending | Pending | Pending | Pending |

The overview uses `adapter_roundtrip_latency`; native-search-only values and
additional reads remain separately reported. Book is in-process Python including
native recall assembly; claude-mem uses SQLite/Bun; ai-memory uses local hybrid
HTTP/MCP; billion-context is the supplied-source search kernel in Node. These
boundaries do not represent equivalent complete products. [Frozen adapters][comparison-evaluator]

Book returns the full native object with a 100,000-character ranking cap before
common packing. This is not its compact MCP response or the optional
[indexed-reference format](indexed-references.md). Native response JSON, native
content text and capped packed context are different token surfaces. The
ai-memory policy reads each mapped top-five page on the first pass; a real agent
could choose fewer reads. Metadata retains its original slot and payload cost
without evidence credit. No replacement search fills an omitted slot.

### Setup, memory and persistent state

**Pending: canonical page count, all preparation times, RSS, live state and
model/index details.** Native Book workers ingest the original sources;
component Book workers copy the canonical archive. Q2 separately loads its
model and builds an index. Different setup paths are not a common ingestion race.

| Mode | Setup s | Setup tree RSS MiB | Query tree RSS MiB | Native state bytes |
|---|---:|---:|---:|---:|
| v0.3.1 native lexical | Pending | Pending | Pending | Pending |
| C2 native lexical | Pending | Pending | Pending | Pending |
| C2 native Q2 | Pending | Pending | Pending | Pending |
| v0.3.1 component lexical | Pending | Pending | Pending | Pending |
| C2 component lexical | Pending | Pending | Pending | Pending |
| C2 component Q2 | Pending | Pending | Pending | Pending |
| claude-mem FTS | Pending | Pending | Pending | Pending |
| ai-memory hybrid | Pending | Pending | Pending | Pending |
| billion-context kernel | Pending | Pending | Pending | Pending |

RSS is sampled every 20 ms across the worker and descendants. It includes
evaluator/data memory, may count shared pages more than once and can miss peaks;
it is not isolated product RAM. Persistent state is reported before cleanup,
with main/WAL/SHM and model-cache boundaries kept explicit. A kernel's in-memory
state is distinct from its full proxy. Native writes, embedding/backfill work,
model downloads and separately measured preparation phases must remain visible.

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

The [preserved v0.3.1 comparison](comparison-v0.3.1.md) retains its completed
607-annotation selection, Q2 losses, competitor strengths, full cost tables and
separate startup-review decision. The [round-three report](round3-comparison.md)
provides its detailed six-cell results and fixed source identities. Its
project-local statistics experiment remains rejected; no later timing result
reopens that quality candidate.

The [preserved v0.3.0 comparison](comparison-v0.3.0.md) contains the historical
LoCoMo matrix, earlier Hotpot selection, generated-answer experiment and
small-model consolidation workflow. Each keeps its original source, host,
failure records and denominator. Those results are not fresh v0.3.2 answer
measurements and are not pooled with this run.

Mem0, Graphiti, PageIndex and Letta are architectural comparisons here, not
executed performance victories. The current work does not measure production
concurrency, adaptive agent policies, provider billing, energy, private-user
data, unanswerable-query abstention, or every competitor's native observation,
compression and generation workflow. Unknown costs stay unknown. Final release
verification and publication remain separate from benchmark acceptance.

[plan]: ../benchmarks/experiments/round4-plan.json
[formal-review]: round4-performance-review.md
[formal-audit]: ../benchmarks/reports/round4-performance-independent-audit.json
[formal-summary]: ../benchmarks/reports/round4-performance-43361086255-1/report.summary.json
[formal-local-audit]: ../benchmarks/reports/round4-performance-local-audit.json
[formal-raw]: ../benchmarks/reports/round4-performance-43361086255-1/report.json.gz
[comparison-binding]: ../benchmarks/experiments/round4-validation-binding.json
[comparison-manifest]: ../benchmarks/experiments/round4-hotpot256-manifest.json
[comparison-evaluator]: ../scripts/round4_comparison.py
