# Release validation

This document separates measured behavior from configuration compatibility.
Product fixtures, examples, screenshots, and capture measurements are synthetic;
the published experiments also evaluate LoCoMo and HotpotQA text corpora. No private
user conversation history was used in development or published.

## Current: v0.3.4 startup accepted and fresh comparison complete

The [prospective startup plan](../benchmarks/experiments/round6-startup-plan.json)
and [frozen binding](../benchmarks/experiments/round6-startup-binding.json)
compare published v0.3.3 source `796cedfd1f5368144037a1fb72292b8d13884b8c`
with selected A source `df35007c29e4af61dd96146232fe4651cfc74391`.
The candidate runtime SHA256 is
`f361d2bf64a4e1088cbd5cff6ffdaf19aa15e7f1b7ea1de4577d7a488d2ac242`;
the baseline runtime SHA256 is
`55529a217e6dcf6af0c81639cfc0e88b3ea94c39e6911f659fcfb7543e853d45`.
B's rejected dense-rank experiment is excluded. Publication must retain this
exact selected A runtime.

**Startup scope is accepted after the required independent resource review.**
The [separate explicit decision](../benchmarks/experiments/round6-startup-decision.json)
records `startup_accepted:true` and `publication_approved:false`. The original
automatic report remains `numeric_gate_passed:true`, `accepted:false`, and its
workflow conclusion remains `failure`: one resource increase required review.
Neither that verdict nor any threshold, sample or flag was rewritten.

The sole [confirmation run 43598913606](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43598913606)
retains all **480 samples and 960 start/finish events**, with zero missing or
invalid observations. Measurement and saved-result audit return codes are both
zero. Four AB/BA/BA/AB rounds provide forty fresh observations per source and
boundary on Ubuntu 24.04 / Python 3.12, with MCP 1.30.0 and Pydantic 2.14.3.
No first sample or outlier was removed; no measurement was repeated. OS caches
evolve naturally, so this is not an OS-cold or statistical-significance claim.

| Startup boundary | Median v0.3.3 → A, ms | p95 v0.3.3 → A, ms | Median / p95 change |
|---|---:|---:|---:|
| New empty-archive constructor | 24.518 → 4.164 | 27.374 → 6.358 | -83.02% / -76.77% |
| Actual CLI `--help` process | 102.903 → 48.750 | 104.104 → 49.547 | -52.63% / -52.41% |
| Actual CLI `--version` process | 101.346 → 47.479 | 103.116 → 48.259 | -53.15% / -53.20% |
| Full API import, including `MemoryBook` | 33.506 → 33.920 | 33.822 → 34.433 | +1.24% / +1.81% |
| Existing empty-archive constructor | 0.640 → 0.632 | 0.668 → 0.666 | -1.23% / -0.30% |
| Official SDK transport/server initialization | 627.601 → 620.104 | 632.233 → 624.837 | -1.19% / -1.17% |

Negative changes mean less elapsed time. The new-archive median falls by
**20.354 ms**; CLI help/version medians fall by **54.153 / 53.867 ms**. All
three prospective primary percentage/absolute targets and all six secondary
guards pass. Constructor timing starts after the full API import and excludes
validation/close; CLI timing covers the complete actual process; MCP timing
ends at successful initialization. These are separate boundaries, and the
existing-archive/MCP observations are secondary results.

The import regression remains visible: **+0.414 ms median / +0.611 ms p95**.
The sole >10% resource flag is existing-archive **whole-helper system CPU**:
**18.646175 → 21.120575 ms**, or **+2.474400 ms / +13.270282%**. All four
rounds increase. The same saved rows show total user+system CPU **+1.228375 ms**
and whole-helper wall mean **+1.233748 ms / +0.889110%**, while constructor
median/p95 slightly improve. Total CPU is arithmetic on saved samples, not a
new measurement. The exact phase cause is unresolved; the existing schema-3
path does not execute new-schema DDL. The increase is neither dismissed as
noise nor attributed to the new transaction.

The [independent resource review](round6-startup-resource-review.md) and
[separate saved-result review](../benchmarks/reports/round6-startup-43598913606-1-local-audit/review.md)
support the bounded startup tradeoff accepted in the explicit decision. All
**30 resource comparisons**, **9 pooled / 27 per-round resource increases**,
and **6 pooled / 26 per-round adverse timing entries** remain retained.
Child `wait4` RSS high-water values do not isolate post-exec product memory;
MCP RSS/HWM is sampled after initialization. These records do not establish
equal, lower or superior product-memory use.

The immutable [complete report](../benchmarks/reports/round6-startup-43598913606-1/report.json.gz)
has SHA256 `381f5d99e5844af1d6d1681723f489ac98f099bb86551abcc6dd9cfd162a5b5a`
at result commit `ffcc0a6f01b3b4acdf755ecd4c01b1e564d279b6`.
[Hosted saved-ledger audit](../benchmarks/reports/round6-startup-43598913606-1/independent-audit.json),
[local audit](../benchmarks/reports/round6-startup-43598913606-1-local-audit/independent-audit.json)
and [Git/blob verification](../benchmarks/reports/round6-startup-43598913606-1-local-audit/verification.json)
retain the original source, evaluator, ledger and result identities.

### Recall and fresh-comparison limits

The original **10% aggregate / 15% public native / 10% actual-MCP p95** recall
targets remain unchanged and unpassed. A's [complete development review](../benchmarks/reports/round6-development-43592983218-review.json)
records roughly 1% recall gains; B's [complete rejected development review](../benchmarks/reports/round6-development-43595785770-review.json)
retains public native p95 regressions around 19–29% and actual-MCP p95
**+23.9246%**. Neither candidate ran or passed the original four-round formal
recall matrix. Startup acceptance does not substitute for that study or imply
a retrieval-quality improvement.

The [fresh-comparison plan](../benchmarks/experiments/round6-comparison-plan.json)
retains the original **256 selected IDs**, excludes all **896 historical IDs**
with zero overlap, and preserves their content fingerprints. The
[original freeze audit](../benchmarks/reports/round6-comparison-freeze-43597613304-local-audit.json)
records preparation and selection without scoring or human question/answer
inspection. A unit fixture's real manifest-path dependency caused the
[preserved first CI failure](../benchmarks/reports/round6-comparison-fixture-failure-43598914326/receipt.json).
The [prospective fixture-only recovery](../benchmarks/experiments/round6-comparison-fixture-recovery-addendum.json)
requires separate new binding/manifest paths while retaining the original
files, all 256 IDs, content/statistics, freeze time and measurement logic.
It corrects evaluator provenance before first scoring; it is not a new sample
selection or product retuning.

### Complete fresh comparison and interpretation

The [single fresh run 43601518020](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43601518020)
completed all **eight stages, 6,912 retrieval/search calls and 42 quality cells**
at original result commit `3e6e492422705feda61b9c967d0a07dd7766dd72`.
These comprise 3,072 native calls and 3,840 component searches; **1,280 ai-memory
page reads** are counted separately. All **1,536 native and 768 component
complete-output pairs** match between v0.3.3 and A, excluding only
`latency_ms`. The original [assessment](../benchmarks/results/round6-comparison-43601518020-1/assessment.json)
records `complete-verified`, zero validation failures and
`performance_gate_evaluated:false`. The [frozen saved-result audit](../benchmarks/reports/round6-comparison-43601518020-1-local-audit.json)
verifies all **28 original files and 13,824 ledger events** against the exact
result commit without dataset reads or new measurement. Retrieval quality is
retained, not newly improved relative to v0.3.3.

The [complete original report](../benchmarks/results/round6-comparison-43601518020-1/report.md)
and [independent complete technical review](../benchmarks/reports/round6-comparison-43601518020-1-independent-review.json)
retain every budget/tokenizer cell, paired evidence/query gain and loss,
latency distribution, resource observation and native payload/read cost.
**Two historical template statements in the immutable report need this scope
clarification:** the original v1 evaluator/assets were committed before the
original ID selection; the v2 fixture-only correction was committed **after
those same 256 IDs were fixed and before first scoring**. The new binding and
copied manifest retain all original IDs, content statistics and freeze time;
the [recovery freeze audit](../benchmarks/reports/round6-comparison-recovery-freeze-audit.json)
verifies the separate commits and 75-file closure. Also, the report's inherited
statement that an old-data ABBA recall experiment supplies the release gate
does not apply to this startup-scoped version. The original recall
**10% / 15% / 10%** gates remain unchanged and unpassed, and that formal matrix
was not run. The prospective startup study above supplies this version's
measured improvement. Neither template statement changes the stored results.

At **1,024 cl100k tokens**, the common whole-block projection gives all five
components the same supplied-page evidence representation and budget:

| Component | Evidence recall | Complete evidence | Packed-context MRR | Mean packed tokens | First search + all reads p95, ms |
|---|---:|---:|---:|---:|---:|
| Book v0.3.3 default | 75.93% | 53.12% | 0.8556 | 715.5 | 3.535 |
| Book v0.3.4 default | 75.93% | 53.12% | 0.8556 | 715.5 | 3.573 |
| claude-mem 15.18.1 supplied-source FTS | 70.60% | 48.05% | 0.8060 | 710.6 | 43.137 |
| ai-memory v3.4.5 local hybrid | 77.87% | 57.42% | 0.8279 | 715.3 | 46.338 |
| billion-context locked search kernel | 80.94% | 60.55% | 0.8481 | 760.4 | 2.279 |

Book's complete-evidence lead over claude-mem FTS is **5.0781 percentage
points** (24 query gains / 11 losses). Book trails ai-memory by **4.2969 points**
(16 gains / 27 losses) and billion-context by **7.4219 points** (28 gains /
47 losses). Book's packed-context MRR is higher in this cell, but that does not
remove the complete-evidence deficits. The same Book quality values appear
for v0.3.3 and v0.3.4. Across both tokenizers and all three caps, Book leads
claude-mem in complete evidence, trails ai-memory, and leads billion-context
only narrowly at the 512-token caps; billion-context has higher evidence recall
in all six component cells. The full 42-cell record remains available rather
than treating this one table as the entire experiment.

Latency columns describe distinct component boundaries: Book runs in-process
Python with context assembly, claude-mem uses native SQLite/Bun, ai-memory uses
local hybrid HTTP/MCP and its locked embedding model, and billion-context uses
its Node search kernel. First-search-plus-reads percentiles sum each query's
roundtrips before aggregation; offline token counting and common packing are
excluded. The billion kernel is faster than Book at this boundary. These
measurements do not establish a whole-product speed ratio. The six quality
projections reuse each first response; three search repetitions remain in the
raw records without replacement queries. Native payload, native content and
packed evidence are separate token surfaces.

### Retained fresh timing and resource costs

All six native p50/p95 comparisons are retained here. Positive changes mean
slower. Each cell has 256 calls per source, with an 8,000-character cap,
registered token cap, top five and disabled result cache; the stages are
sequential descriptive measurements, not the unrun balanced recall gate.

| Tokenizer / cap | p50 baseline → A, ms | p50 change | p95 baseline → A, ms | p95 change |
|---|---:|---:|---:|---:|
| cl100k_base / 512 | 2.994 → 3.091 | +3.23% | 4.289 → 4.415 | +2.92% |
| cl100k_base / 1024 | 2.865 → 2.885 | +0.70% | 3.987 → 4.087 | +2.49% |
| cl100k_base / 2048 | 2.694 → 2.702 | +0.31% | 3.899 → 3.923 | +0.60% |
| o200k_base / 512 | 3.374 → 3.345 | -0.84% | 4.988 → 4.819 | -3.39% |
| o200k_base / 1024 | 2.977 → 3.010 | +1.11% | 4.245 → 4.334 | +2.11% |
| o200k_base / 2048 | 2.729 → 2.782 | +1.92% | 3.990 → 4.000 | +0.23% |

Five of six native p50 and p95 cells increase, and all six native means
increase (**+0.1360% to +3.4936%**). Component search p95 rises
**3.517899 → 3.582246 ms**; first-search-plus-reads p95 rises
**3.535148 → 3.572512 ms**. Book component setup rises
**840.939681 → 843.362073 ms**, and its recorded open step rises
**0.894878 → 0.906219 ms**. These costs are retained; no fresh recall-speed
improvement is claimed.

Native query sampled RSS rises **533.12 → 537.18 MiB**
(**+4,255,744 bytes**); component query sampled RSS falls
**511.84 → 504.87 MiB**. The complete stage records retain setup, finalization,
worker peaks and every other resource field. Sampling covers the evaluator
worker and live descendants every 20 ms, includes loaded-corpus/evaluator
memory, can count shared mappings more than once and records observed lower
bounds. It does not isolate product memory or prove general memory savings.

Book's raw search payload averages **3,992.9 cl100k tokens**, above claude-mem's
**1,634.7**, ai-memory's **1,019.3 search + 1,836.3 read** payload tokens and the
billion kernel's **585.0**. Book needs no separate page reads at this boundary,
while ai-memory records five per question; this does not imply the smallest
total payload. Book component state is **34,340,864 bytes**, compared with
claude-mem's **20,659,514** and ai-memory's **74,208,780**; billion-context's
in-memory kernel records no persisted native state, so that zero is not a
like-for-like persistence advantage. Symlinked model caches are excluded.

The small low-lexical-overlap group remains adverse: at 512 cl100k tokens,
both Book modes return complete evidence for **0/7** questions, versus
claude-mem **1/7**, ai-memory **2/7** and billion-context **2/7**. These seven
examples limit any generalization. All 256 selected questions are answerable;
this evaluates evidence retrieval from another selection of the same HotpotQA
source, not new-domain transfer, abstention, hallucination or generated-answer
accuracy. Cross-session/chapter groups reflect the supplied-paragraph mapping.
Q2 is excluded; its older results retain their historical versions and scope.

### Final publication requirements

The completed fresh comparison establishes output retention and scoped
component comparisons. It does not change the startup resource decision or
approve publication by itself. Publication requires a separate final release
decision bound to the exact A runtime, nine successful CI jobs for the exact
publication commit, and matching `main` and release refs. An earlier source CI
is not a substitute for that final-commit gate.

The release workflow builds wheel/sdist archives, verifies every runtime and
reader file against committed source, installs the two packages in separate
clean environments, and verifies all seven remote asset hashes. Normal
publication uses `prerelease:false` and verifies Latest. Its subsequent
public-install job exercises the real public installer URL and default release
wheel, including the expected version and MCP/client extras. Publication
receipts must identify those exact commits, workflow runs and asset hashes;
these requirements do not rewrite any original experiment verdict.

## Historical: v0.3.3 completed fifth-round methods and evidence

The [original plan](../benchmarks/experiments/round5-plan.json),
[C7 continuation](../benchmarks/experiments/round5-c7-addendum.json) and
[frozen binding](../benchmarks/experiments/round5-c7-performance-binding.json)
retain published v0.3.2 as baseline. Final C7 source is `d0c84cbfc9bad440ad447d41e211d070ef5b2cae`,
runtime SHA256 `55529a217e6dcf6af0c81639cfc0e88b3ea94c39e6911f659fcfb7543e853d45`; 60 evaluator inputs are bound before timing.

The [single formal run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43563390252)
completes all **56,784 calls**, sixteen workers and four balanced rounds.
Independent arithmetic and the frozen saved-ledger auditor verify **113,568
start/finish events**, **28,392 baseline/candidate complete-output pairs** and
**18,928 native/MCP provenance pairs**, with zero differences or recorded
invariant failures. Only `latency_ms` is excluded from payload comparisons.

Pooled p95 geometric mean improves **14.7976%** against published v0.3.2. Public native token512/token1024/token2048 p95 changes **-15.1867% / -14.2362% / -15.7406%**. Actual public SDK MCP token1024 p95 is **6.711 → 5.894 ms**, an improvement of **12.1734%**.

C7 combines the official MCP SDK's native stdout write and immediate flush in one worker dispatch, reducing dispatch overhead while preserving complete messages, serialization and lifecycle.

All twelve pooled p50 and p95 values improve.

All fixed numerical gates pass. The original automated verdict remains `accepted:false` because three startup resource increases required review: import means rise 3.197 / 2.990 ms, and public-labeled fresh-empty-database opening rises 5.100 ms (21.4109%). A [separate resource review](round5-c7-resource-review.md) accepts these startup costs with all samples and attribution limits retained. No timing was repeated, threshold lowered or original automatic verdict rewritten.
The [explicit resource decision](../benchmarks/experiments/round5-c7-resource-decision.json)
binds both independent reviews to the unchanged original report and source.
The [complete review](round5-c7-performance-review.md) retains all twelve pooled
cells, forty-eight per-round cells, adverse observations and twenty-eight
resource comparisons. [Independent audit](../benchmarks/reports/round5-c7-performance-independent-audit.json) ·
[Frozen saved-ledger audit](../benchmarks/reports/round5-c7-performance-local-audit.json).

Query-result caching is disabled or cleared before timing.
The per-book exact-count memo is enabled under its registered 2,048-entry /
2 MiB retained-text cap. Each native book starts empty, character recall does
not allocate it, and later token configurations reuse earlier counts. Each
MCP configuration uses a fresh official SDK stdio server process; no MCP memo
hit rate is inferred from native diagnostics. Transport and normal server
result-cache writes remain inside MCP timers. Container/keys/counts and
vocabulary memory are additional to the text-object cap, and actual process
RSS remains part of the registered resource measurements.

[Final-source historical compatibility](../benchmarks/reports/round5-c7-hotpot-regression.summary.json)
reproduces all **2,304** saved default Hotpot256 payload hashes: 1,536 native
calls over both encoders and three caps plus 768 component calls. All 4,608
attempt events and unchanged source/index/document projections are checked.
This supports retention of the old default quality result on these same
questions. It adds no new competitor timing, Q2 measurement, generated-answer
accuracy or unseen-domain quality claim.

The complete [C3 formal rejection](round5-performance-review.md),
[C5 formal rejection](round5-c5-performance-review.md),
[C6 formal rejection](round5-c6-performance-review.md) and
[C4/C5/C6/C7 development records](optimization-round5.md) remain unchanged.
C5 and C6 retain `accepted:false`: their actual-MCP p95 gains were
6.673181% and 5.798911%, below the unchanged 10% gate. The retained C5
development best public native p95 was below the formal 15% threshold, and is
not used as a passed gate. Saved hashes and invariants support output equality;
the offline audit cannot independently re-tokenize omitted response bodies.
Exact release-commit CI and package/public-installer verification are separate
publication requirements.

## Historical: v0.3.2 completed fourth-round methods and evidence

The [registered plan](../benchmarks/experiments/round4-plan.json),
[development addendum](../benchmarks/experiments/round4-development-addendum.json)
and [exact-counting addendum](../benchmarks/experiments/round4-counting-addendum.json)
retain the published v0.3.1 baseline and freeze each extension before its
measurements. The final C2 runtime is commit
`2d7b5e38839fb21724ad3beec6b6ebabbda45636`, SHA256
`179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93`.
Ranking, indexed content, schemas, Q2 model/vector policy and fusion remain
unchanged. Complete-payload comparisons exclude only `latency_ms`.

The [C2 profile](../benchmarks/reports/round4-development/candidate-c2-manifest.json)
preserves 4,732 complete payload matches on the two old cohorts. The separate
[historical first-use recovery](../benchmarks/reports/round4-development/final-hotpot-first-use-recovery-manifest.json)
preserves 2,048 calls, 1,024 exact pairs and every start/finish event. Its four
fresh workers each reuse a connection across four configurations; neither
profiled timings nor these first-use diagnostics establish an OS-cold or formal
speed result. The [Q2 audit](../benchmarks/reports/round4-compatibility-final/paired-audit.json)
verifies 1,968 calls, 984 exact pairs, both tokenizers and all three budgets,
alongside committed source/evaluator bytes, model files and unchanged persisted
vectors/originals. Recorded source, projection, scope, token and metadata
errors are zero. Saved hashes support equality and ledger integrity; omitted
response bodies cannot be independently re-tokenized by the offline audit.

The [prelaunch recovery registration](../benchmarks/experiments/round4-prelaunch-recovery.json)
and [independent prelaunch audit](../benchmarks/reports/round4-development/final-prelaunch-audit.json)
preserve the original interrupted 512-call attempt and local MCP failure before
any recall, together with earlier rejected candidates and adverse cells. No
favorable-round pooling or replacement of those records is permitted.

**Formal performance and the complete fresh 256-question comparison passed.**
[Run 43361086255](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43361086255)
used the committed [formal binding](../benchmarks/experiments/round4-performance-binding.json)
and triggering source `f8f1653c0653654ed574569fff1aaf4dbaeef6d1`. The
[full report](../benchmarks/reports/round4-performance-43361086255-1/report.json.gz),
[summary](../benchmarks/reports/round4-performance-43361086255-1/report.summary.json)
and [independent arithmetic audit](../benchmarks/reports/round4-performance-independent-audit.json)
verify all **56,784 calls**, 16 sequential workers, four balanced rounds and
twelve pooled cells. Complete native/MCP outputs and source/scope/cache/budget
invariants pass. Actual SDK MCP includes roundtrip and normal cache-write cost;
persistent cache clearing is outside query timers.

Pooled p95 geometric mean improves **10.1294%**. Public native token512/1024/2048
p95 improves **19.0736% / 18.4102% / 18.2009%**, and public MCP token1024 improves
**10.8021%**. The adverse public MCP character-budget p95 change, **+1.4445%**,
remains recorded. The largest registered resource mean increase is **+6.0231%**;
none exceeds the 10% review trigger, so **no resource exception or waiver** was
needed. The [performance review](round4-performance-review.md) retains all
individual-round regressions and resource samples. The aggregate pass has a
narrow 0.1294-percentage-point margin; it is not a statistical-significance or
universal-speedup result.

The [independent freeze audit](../benchmarks/reports/round4-freeze-independent-audit.json)
reconstructs the exact ordered 256 IDs after excluding all 640 historical IDs,
with zero overlap, and verifies candidate/assets/evaluator/binding/manifest Git
ordering. The [existing selection verifier](../benchmarks/reports/round4-selection-local-audit.json)
also checks the filtered canonical content and dataset fingerprint; the frozen
cohort records 635 required annotations and 2,548 supplied paragraphs. This
distinguishes independently checked IDs/history from hosted asset receipts and
the separate content verifier.

[Fresh scoring](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43363060062)
completed all ten stages, **4,608 native calls and 4,608 component searches**,
at [`eff3941`](https://github.com/Afloat16/AI-Memory-Book/commit/eff394119105d59186c730e2480d86d1436401a6).
The [assessment](../benchmarks/results/round4-comparison-43363060062-1/assessment.json)
is `complete-verified`, with no failures. All **1,536 native and 768 component
complete default-payload pairs** match. Six whole-block budget/tokenizer
projections reuse each component's first response; they add no searches.

The [offline audit](../benchmarks/reports/round4-comparison-independent-audit.json)
ran the unchanged `scripts/round4_comparison.py audit --verify-existing` once
and exactly reproduced the published assessment and Markdown. Independent
arithmetic then checked all **54 quality cells / 13,824 quality rows**, all
**12 Q2 delta cells**, **18,432 attempt events**, output hashes and source
identities. All 32 result artifacts plus the checkpoint match the immutable
result commit. This distinguishes reusing the original strict verifier from
independently implemented arithmetic; it repeats no retrieval or inference.
Saved payload hashes and reported invariants cannot reconstruct omitted text
or independently re-tokenize original responses.

At the common 1,024-cl100k cap, default complete evidence is 53.91% versus
claude-mem's 44.53%; Q2 reaches 55.08%, ai-memory 55.86% and billion-context
60.55%. Native Q2 retains 512-token completeness losses under both encoders.
The fresh 100,000-character component path has **+5.56% p95 / +5.12% p50**,
and setup tree RSS rises **548.65 → 943.53 MiB** against v0.3.1. Native lexical
finalization tree RSS also rises **655.16 → 1,107.09 MiB**. All 27 saved
setup/query/finalization phases for the nine measured modes are retained. Their sampled process
trees include evaluator/data memory; causes are not established, and these
unbalanced fresh observations are separate from the formal resource means.

The [full comparison guide](comparison.md) retains all costs and competitor
strengths. New selection does not mean a new domain; all questions are
answerable, and generated answers/abstention are outside this experiment.
Native API, component adapter, complete-read and resource costs remain distinct.
Release publication additionally requires exact-commit CI and package checks.

## Historical: v0.3.1 completed measurement and recovery

The [round-three checkpoint](../benchmarks/reports/round3-comparison-43267797247-1-checkpoint.json)
is **complete-verified**: ten completed stages, 4,608 native calls and 4,608
component searches. All 1,536 complete default native payload pairs and 768
component payload pairs match. Independent offline recomputation verifies the
original assessment and report, all 32 result blobs and all 71 prebound
evaluator file hashes, with no retrieval replay. The
[independent verification](../benchmarks/reports/round3-recovery/comparison-cross-verification.json)
retains every Q2 gain/loss cell and exact report/checkpoint identities.

The separate [formal performance review](round3-performance-review.md) checks
47,320 original calls from four balanced rounds and ten configurations. Its
query-speed and exact-output checks pass. Original startup mean +14.04%, the
automatic `accepted: false` flag and all individual regressions stay intact;
the explicit resource review accepts the guarded query change with that cost
disclosed. The existing startup-only diagnostic is independently reconstructed
from all 80 original samples, not a replacement performance run.

The [quality-screen recovery](round3-quality-review.md) reconstructs 8,082
original calls from preserved workers without scoring again. All 20 recovered
files match the canonical hosted recovery. The project-local statistics
candidate fails 14 registered checks and remains excluded from the release.
See [source/code review](round3-code-review.md),
[registration reconciliation](round3-reconciliation.md), and the
[full result index](../benchmarks/README.md).

The published v0.3.1 source is `7b7a5d7336b9350a128f5e0a888811b1b3015e68`.
[All nine exact-commit Tests jobs](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43273167370)
passed. The [release workflow](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43273455233)
verified all seven assets and their downloaded hashes, then successfully
installed through the actual public tagged URL in a clean environment.
The [release](https://github.com/Afloat16/AI-Memory-Book/releases/tag/v0.3.1)
includes its exact source SHA and successful CI link. The supplemental offline
audit used the original executed evaluator. A separate
[published-source comparison](../benchmarks/reports/round3-recovery/published-release-cross-verification.json)
confirms all 71 bound evaluator files and 17 runtime/static files are identical
to the audited checkout. See
[audit provenance](round3-continuation.md#published-release-and-supplemental-audit)
and [publishing procedure](releasing.md).

The dated sections below retain evidence for their historical source pins.

## Historical completed continuation — 2026-11-12

The [strict final audit](../benchmarks/reports/hosted-final-aggregation.json)
has status `complete-verified-snapshot`: 80 fixed inputs checked, eight
derived reports verified, all four summarizers successful. It covers eight
native-budget cohorts, four semantic cohorts, 768 actual generated answers,
the 42-session/72-answer native workflow, and the completed claude-mem
component experiment.

The latest source includes a separate exact-output token-counting optimization:
2,016 development payloads match the frozen reference, while all four
512-token configurations improve p95 by 7.73%–14.45%. All 12 settings,
including larger-budget regressions, remain in the
[performance report](token-prefix-performance.md).

The integrated runtime/report tools passed
[all nine CI jobs](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43185554873).
The [final aggregation job](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43185554831)
also succeeded after testing its verification code. The separately reviewed
automatic recovery collector passed
[all nine jobs](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43186469865).
[Current main CI](https://github.com/Afloat16/AI-Memory-Book/actions/workflows/ci.yml)
records the final integrated head.

The native workflow is a complete measurement **with failures**: 42/42
capture sessions and all 72 answer requests completed; 35 of 42 native
consolidations were rejected after the fixed model reached its 1,000-token
output limit. Their full usage and later answer scores remain counted.
Integrity/completeness gates do not assert that every quality metric improved.

[Completed result index](../benchmarks/README.md) ·
[Source identities and recovery record](continuation-status.md) ·
[Exact final aggregation](final-validation-aggregation.md).

The dated sections below describe the evidence available at those older commits.

## Historical checkpoint: recall-quality continuation, then unreleased

### Recovered native-budget checkpoint: e70bc3d

The interrupted continuation was already preserved on the remote branch at
[`e70bc3d2581ff96959711509b3eef11ab14f564d`](https://github.com/Afloat16/AI-Memory-Book/commit/e70bc3d2581ff96959711509b3eef11ab14f564d).
It includes the native token-budget API from
[`c73b5f8`](https://github.com/Afloat16/AI-Memory-Book/commit/c73b5f8aa086e597a3c921bf6340c385b350e332),
registered semantic and local-answer plans, the external HotpotQA input freeze,
and the native-budget development report. Those plans are not implementation or
model-result claims.

For that exact head, both the
[push workflow](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43152979344)
and [pull-request workflow](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43152987680)
completed **9/9 jobs successfully**: Python 3.10/3.12/3.13 core checks, actual
MCP stdio, the browser reader, Linux/macOS/Windows installers, and container
persistence. The [push MCP job](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43152979344/job/130966302150)
records **294 tests in 17.972 seconds, OK**. This exact committed-tree count
supersedes neither the earlier 266-test snapshot nor an uncommitted-workspace
count mentioned in the checkpoint message.

The checked continuation was merged into `main` through
[PR #1](https://github.com/Afloat16/AI-Memory-Book/pull/1), at merge commit
[`ce7837f`](https://github.com/Afloat16/AI-Memory-Book/commit/ce7837fb8db7c221f39e27a531f2383385782eb1).
The CI links above identify the reviewed `e70bc3d` source head, not a claim about
every future `main` revision. The published installer remains pinned to v0.2.1.

The token API's focused checks cover citation-inclusive character and token
caps, both supported encodings, old-block preservation, source reconstruction,
code-fence boundaries, literal special-token strings, isolated caches and strict
numeric validation over real MCP stdio. See
[token API tests](../tests/test_token_budget.py),
[MCP token tests](../tests/test_token_budget_mcp.py), and
[API contract](token-budget.md).

The [frozen 128-question development report](../benchmarks/results/native-token-dev128-frozen.md)
passes its measurement gates and retains every per-query change. At 8,000
characters and 512 tokens, complete evidence rises 71.08% → 73.49% against the
prior native-excerpt packer in both tokenizers: two complete-question gains,
zero losses and zero missing previously accepted blocks. Total local p95 rises
4.690 → 11.460 ms (`cl100k_base`) and 4.728 → 17.230 ms (`o200k_base`). The
separate historical whole-page policy achieves 75.90% on this development
subset. These are distinct policies; this result cannot be substituted for the
full-public 66.72% → 66.26% historical comparison.

The [external sentence preflight](../benchmarks/reports/hotpot-sentence-preflight.json)
checks all 128 frozen HotpotQA problems and all 306 supporting facts. It records
1,272 sessions, 5,195 original sentence turns and 1,915 pages, with no supporting
fact structurally unattainable by the strict single-page metric. It is a source
attainability check performed before candidate scoring, not a retrieval or
generated-answer result. The [registered protocol](native-budget-evaluation.md)
separates regression, external transfer, generation and complete workflow costs.

### Optional coverage and real-answer evaluation

The final wrapper uses runtime SHA-256
`88f5f749be55dd4f1094d236340bec645edb6b9306fd45c720dbebac91767e57`.
Its full local suite passes **266 tests with no failures or skips** with MCP,
client and benchmark extras. The recorded run took 16.969 seconds while a
separate equivalence check was running; this is a test-run observation, not a
product performance result. New checks include actual MCP stdio and CLI
coverage opt-in, mode-specific caches, invalid parameters, provider errors,
credential echoes, HTTP disconnects, missing usage and model identity changes.

The [complete-payload equivalence check](../benchmarks/reports/coverage-mode-equivalence.json)
compares 1,387 queries at two character caps for each mode. All **2,774 default
payloads** equal the score-aware baseline; all **2,774 opt-in payloads** equal
the frozen automatic-clause experiment. Only `latency_ms` is excluded; source
text, scores, result ordering, references, warnings and truncation participate.
The query sets are regression checks, not new heldout evidence.

The earlier automatic-clause runtime is publicly preserved at
[`7a472ce`](https://github.com/Afloat16/AI-Memory-Book/commit/7a472ce35698360382d8d15a1be101343d8a2c3b).
Its Git tree equals locally measured `1cdaf8f`; this API publication changes the
commit identity, not the source bytes. Its **11 sequential stages, 29 output
hashes and 68 frozen input hashes** are recorded in the
[integrity record](../benchmarks/reports/conjunctive-integrity.json).
The experiment's timings describe that frozen automatic variant. They are not
relabeled as timings of the final opt-in API. See the
[full report](../benchmarks/RESULTS-conjunctive-recall.md).

[Answer-evaluation readiness](../benchmarks/reports/answer-eval-readiness.json)
records 128 paired public-development contexts (83 answerable, 45 unsupported)
and **zero actual generation calls**. HTTP test fixtures verify plumbing only.
Generated answers, native observer workflows and full memory costs remain
unmeasured. The older CI links below refer to their named historical snapshots;
the publication's GitHub Actions runs must be checked separately.

### Score-aware continuation

The second-round runtime is frozen at
**`0ab49d4f2be6aabe5e51c3314bb9369041af5369`**. Its full local suite completed
**244 tests in 26.498 seconds**, with no failures or skips. The ranker combines
normalized BM25 relevance from the exact and Porter routes with a fixed **2:1
exact-route preference**. `RECALL_VERSION = 7` gives the changed ranking its own
recall-cache identity, so earlier cached rankings are not reused.

Three [independent regression fixtures](../tests/test_score_fusion.py), fixed
before the score-aware development comparison, verify that a multi-term exact
fact survives Porter word collisions, an inflected query still returns the
original source evidence, and stronger matches in another project cannot enter
scoped results. Each fixture also checks delivered character budgets and source
spans. These correctness checks are separate from the measured quality and cost
interpretation in the
[score-aware continuation results](../benchmarks/RESULTS-recall-score-quality.md).

For this exact head, the
[push run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43044441657)
and [pull-request run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43044450305)
both completed **9 of 9 jobs successfully**: core Python 3.10/3.12/3.13, MCP,
Linux/macOS/Windows installers, Docker, and reader-browser. Both actual browser
logs recorded **13 successful checks**, including scoped Chinese search,
English/Chinese source-text preservation, import confirmation, keyboard focus,
390px mobile layout, and no page, console, request, or unexpected-dialog errors.
The same immutable Noto font pin and hashes documented below were verified in
both runs. Their screenshots and browser reports are retained in the
[push artifacts](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43044441657/artifacts/13865718642)
and [pull-request artifacts](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43044450305/artifacts/13866836901).

### First-round continuation

The final local suite with MCP, client, and benchmark extras completed
**241 tests in 18.420 seconds**, with no failures or skips. This continues the
preserved performance work with bounded word-form retrieval, intact evidence
selection, connection reuse, and reproducible evaluation. Quality, latency,
token costs, and remaining limitations are reported separately in the
[recall-quality continuation results](../benchmarks/RESULTS-recall-quality.md).

The recorded CI head is **`bfb09d46f41a6a734bb8e434688f196fe8723c9d`**.
Both its [push run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43041835462)
and [pull-request run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43041847121)
completed **9 of 9 jobs successfully**: core Python 3.10/3.12/3.13, MCP,
Linux/macOS/Windows installers, Docker, and the actual browser reader.
These links identify the verified head rather than an unspecified latest run.

| Area | Verified behavior |
|---|---|
| MCP connection lifetime | One lazy connection is reused on its owning transport thread, closes on normal or exceptional lifespan exit, and preserves response content and tool declarations. Direct SDK calls, foreign threads, and unavailable file identities use temporary connections. |
| External changes and isolation | Real stdio recall observes another writer's revision and invalidates cached evidence. Replacing the database file reopens the connection. Separate servers retain their own databases and write permissions. |
| Bounded cached work | Directory-token caching is bounded, immutable, and connection-local; warmed and cold paths return identical evidence after a rename. Persistent recall-cache limits and invalidation across connections remain covered. |
| Evidence and storage integrity | Scoped word-form recall, complete fitting lines/sentences, citation-inclusive budgets, Unicode source offsets, original-turn spans, and tiny-budget behavior are checked. Schema upgrades preserve source rows and page addresses, roll back failures, and remain compatible with an already-open legacy writer. |
| Evaluation and recovery | Recorded source changes and character/token accounting failures produce failed diagnostic reports. Sequential resumption checks source, dataset, runtime, manifest, and output hashes; rejects stale or invalid reports; and reruns an invalidated suffix. Real subprocess tests cover SIGTERM recovery and POSIX process-group cleanup when a failed leader leaves a worker that ignores SIGTERM. |

The corresponding focused tests are
[MCP lifecycle](../tests/test_mcp_lifecycle.py),
[lexical caching](../tests/test_lexical_cache.py),
[recall budgets and word forms](../tests/test_recall_quality.py),
[excerpt boundaries](../tests/test_excerpt_boundaries.py),
[index migration](../tests/test_index_migration.py),
[measurement gates](../tests/test_benchmark_gates.py), and
[resumption](../tests/test_benchmark_resume.py).

### First-round browser and font verification

The same browser smoke script executed **13 successful checks** in both CI runs.
It covered desktop project/chapter navigation, scoped Chinese search, source
reading and keyboard-focus restoration, English/Chinese text preservation,
JSON preview followed by confirmed import, inert imported content, and 390px
mobile navigation. Desktop and mobile layouts had no horizontal overflow; the
run recorded no page errors, console errors, failed requests, or unexpected
dialogs. Each run uploaded three screenshots and the browser JSON report:
[push artifacts](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43041835462/artifacts/13865502206)
and [pull-request artifacts](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43041847121/artifacts/13865137770).
CI artifacts expire after seven days; the earlier checked-in browser images
below remain historical evidence for their documented release.

The font preparation uses the official `notofonts/noto-cjk` commit
[`f8d157532fbfaeda587e826d4cd5b21a49186f7c`](https://github.com/notofonts/noto-cjk/commit/f8d157532fbfaeda587e826d4cd5b21a49186f7c),
with bounded download retries and timeouts. Both CI logs verified
`NotoSansCJKsc-Regular.otf` at **16,437,364 bytes**, Git blob
`dc15562470b4f842321894787a0d066879ccff8b`, and SHA-256
`2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b`.
The SHA-256 comes from that commit's
[official SPDX manifest](https://github.com/notofonts/noto-cjk/blob/f8d157532fbfaeda587e826d4cd5b21a49186f7c/_manifest/spdx_2.2/manifest.spdx.json).
The checked OFL license accompanies the font in the user font directory;
`fc-cache` and `fc-match` must succeed before browser testing starts.

## v0.3.0: retrieval and actual response costs

The complete local suite passed **174 tests** with MCP, client, and benchmark
extras, including real-tokenizer CJK/Unicode packing checks. Current CI status is
available in [GitHub Actions](https://github.com/Afloat16/AI-Memory-Book/actions).
Measured quality, response cost, and regressions are in the
[v0.3.0 results](../benchmarks/RESULTS-v0.3.0.md).

The retrieval changes are covered by source-offset, complementary-evidence,
current-versus-historical, and excerpt-boundary regressions. Actual official-SDK
stdio checks verify that compact and detailed recall return identical evidence,
that detailed mode retains exact provenance, and that responses do not duplicate
the context in `structuredContent`.

The new evaluation separates paired core retrieval, fresh-process CLI startup,
actual MCP subprocess calls, and external retrieval components. It uses exact
named tokenizers, frozen sources, new synthetic seeds, and an independent public
conversation split. The external adapters execute pinned upstream code or release
binaries; ai-memory's local MiniLM embeddings are active and completely indexed.
See [the comparison protocol](comparison-protocol.md) and
[reproduction commands](../benchmarks/README.md) for metric and transport limits.

The public text-evidence scores require full annotated utterances and matching
source coordinates. They are not generated-answer accuracy. External shared-page
scores preserve each ranker's implementation while controlling page content,
project scope, candidate count, and packing; they do not evaluate each product's
capture or summarization pipeline. Native ai-memory cost totals use the explicit
policy of reading every mapped top-k page once, not an optimized agent's minimum
required follow-up calls.

## v0.2.1: agent workflow and headless default

The updated local suite passed **159 tests** with MCP and client extras. A new
official-SDK stdio test performs the agent workflow end to end:
`remember_session` → `recall_memory` with a bounded project query → `read_page`
using the returned page ID. It verifies the write-enabled initialization policy,
the remembered fact, character budget, and source identity without a browser.
The read-only handshake verifies its distinct instructions and tool visibility.

The real-daemon regression now leaves `reader_enabled` at its default while
another socket occupies the configured reader port. Capture, configuration
reload, explicit database selection, and clean termination still succeed. This
checks that new background configurations do not require an HTTP listener.
Existing saved reader preferences remain explicit configuration values.

These checks establish the MCP protocol path and headless behavior. They do not
establish that every host model chooses the right tool without prompting; host
approval policies and model tool selection still apply. The
[agent operating guide](agent-guide.md) documents the actual contract.

## v0.2.0: verified implementation

The release candidate at `1d6a881faeb811504941d9bbb0682f587d5de344` passed
**all nine GitHub Actions jobs**:
[complete CI run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/42998379672).
The full suite with the MCP and client extras installed ran **158 tests with no
failures or skips**, both locally and in the separate MCP CI job. The dependency-free
core also passed on Python **3.10, 3.12, and 3.13**, skipping optional-dependency
cases when their extras were absent.

| Area | What actually ran |
|---|---|
| Core and source integrity | Transactional import/replacement, exact provenance, scoped retrieval, character budgets, cache invalidation, export round trips, safe paths, and HTTP protections |
| Client configuration | Schema fixtures, preservation of unrelated settings and credentials, backups, ownership, repeat setup/removal, stale-plan rejection, malformed JSON/JSONC fallback, TOML preservation, and path collisions |
| Background capture | Incremental identity and hashing, database replacement/generation, moved/removed sources, partial JSONL/UTF-8, retry deadlines, repaired files, workspace isolation, cross-process locks, metadata-only logs, and worker shutdown |
| Actual daemon process | A subprocess imported a fixture, honored an explicit database, reloaded a removed source, stopped importing its files, and exited cleanly on SIGTERM |
| MCP protocol | The official SDK client initialized a real stdio subprocess, listed tools, recalled evidence, and checked explicit write enablement |
| Linux/macOS/Windows installers | Each OS ran its shell/PowerShell wrapper, installed a local wheel into paths with spaces and Unicode, exercised reinstall and failed-install recovery, preserved existing data, refused an unrelated launcher, and installed the normal MCP/client extras |
| Docker | Built the image, ran as the non-root user, initialized MCP over container stdio, read persisted evidence, served the reader through host loopback, checked Host validation, and retained data after a container restart |
| Browser | Chrome operated the actual reader, exercised English/Chinese UI and imports, and checked desktop/mobile layouts and source-text preservation |

The installer jobs use a wheel built from the candidate source; they test the
installation mechanism and its dependencies. The project is distributed through
GitHub source releases and is not published to PyPI.

```bash
python -m pip install -e ".[mcp,clients]"
python -m unittest discover -s tests -v
python tests/installer_smoke.py --with-extras
```

## Browser evidence

The candidate used **Python 3.12.16 and Chrome 156.0.8078.79**. Its report records
**13 successful checks**, zero page exceptions, console errors, failed requests,
or unexpected dialogs. Desktop document width equals its 1440px viewport; the
mobile document width equals its 390px viewport. A fresh `en-US` browser context
selects English, and changing UI language preserves the exact conversation text
and titles.

The checked flow covers project selection, cross-session chapter browsing,
project-scoped Chinese search, source reading, focus restoration, canonical JSON
preview and confirmation, and inert display of script-like imported text. The
screenshots are actual browser captures, not design mockups:

- [English desktop](assets/reader-desktop-en.png)
- [Chinese desktop](assets/reader-desktop.png)
- [Mobile](assets/reader-mobile.png)
- [Machine-readable browser report](assets/reader-browser.json)

These files are preserved in the repository because CI artifacts expire after
seven days. The browser check intentionally lives outside unittest discovery,
so the dependency-free core does not require Playwright.

```bash
python -m pip install . playwright
python -m playwright install --with-deps chromium
python tests/browser_smoke.py
```

## v0.2.0 capture overhead sample

The reproducible [capture smoke measurement](../benchmarks/capture_smoke.py)
used **300 synthetic canonical files** across three projects and 30 chapters,
totaling **246,192 source bytes**. On the recorded Linux environment with
Python 3.12.14 and SQLite 3.53.1:

| Stage | Measured wall time | Actual import result |
|---|---:|---|
| Initial import into a new database | 435.83 ms | 300 files imported; 300 sessions updated |
| Eight unchanged scans | Median 36.95 ms; maximum 51.21 ms | Each skipped 300 files and imported/updated zero sessions |
| One changed file | 30.06 ms | One session updated; 299 files skipped |
| Next unchanged scan | 26.16 ms | 300 files skipped; zero sessions updated |

[Raw timings, counts, environment, and implementation fingerprint](../benchmarks/reports/capture-v0.2.0.json)
are retained. Run it from the repository with:

```bash
PYTHONPATH=src python benchmarks/capture_smoke.py
```

These are consecutive `sync_once` calls with warm filesystem caches, without
the normal polling sleep. The measurement includes state loading and locking.
Unchanged scans still update the manifest and heartbeat; zero imports do not
mean zero disk writes. This small sample does not measure resident CPU, RAM,
battery use, vendor-client latency, or performance at other scales.

## Historical v0.1.0 retrieval measurements

The [experiment record](../benchmarks/EXPERIMENTS.md) retains the initial short
corpus, development page-size sweep, all six segmentation/ranking combinations,
two untouched-seed evaluations, and unsuccessful query categories. Complete
per-query output is retained in compressed JSON next to readable reports. Source
fingerprints before and after those final runs match their original version.

These are **v0.1.0 measurements**, retained as historical evidence rather than
presented as a new v0.2.0 benchmark. Recall requires the exact annotated evidence
to survive into the budgeted context with its correct source span; it is not an
LLM answer score. Local latency excludes process startup, transcript capture,
MCP transport, networking, and inference. Result caching was disabled while
SQLite/OS page caches remained available.

The original v0.1 core and browser evidence is also available in its
[core run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/42990594538)
and [browser run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/42991673979).

## What these checks do not establish

- Client profiles follow official configuration schemas and have fixture tests;
  every vendor application was not interactively launched and authenticated.
- Native service definitions and command flows have focused tests. The installer
  matrix does not exercise real login/logout, sleep/resume, or long-running user
  sessions under systemd, launchd, and Task Scheduler.
- Import formats are covered by representative synthetic records, not every
  historical vendor version or multimodal format. Current Kimi Code has MCP
  configuration support; native capture is limited to the separately named
  legacy Python Kimi format.
- Generated histories and a small local capture measurement do not establish
  performance on a large personal archive, network disk, or every operating
  system. Browser coverage is Chrome/Chromium at the stated sizes.
- Lexical retrieval does not guarantee semantic recall, authoritative conflict
  resolution, automatic host injection, or end-to-end model answer quality.
- Component comparisons cover pinned implementations and common supplied pages.
  claude-mem's observer/Chroma workflow and billion-context's full proxy
  compression/decompression remain unmeasured. The separate Book/ai-memory
  workflow does measure native capture, explicitly enabled consolidation and
  answers under its fixed small model, including native truncation failures.
  These results do not establish another configuration's quality or cost,
  and the declared transport boundaries differ.
