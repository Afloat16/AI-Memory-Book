# Native claude-mem supplied-source component comparison

This experiment executes unchanged claude-mem code at
[2cfed762](https://github.com/thedotmack/claude-mem/tree/2cfed7620c1b44db87c7f04cbf073ec37efca38d)
(package version 15.18.0). It is a **supplied-source SQLite FTS retrieval
component**, not the normal observer/Chroma/MCP workflow.

The native SessionStore creates the complete upstream schema. A harness bulk
INSERT puts each frozen original page's title in title and body in text, with
the original project/date and empty semantic fields. Synthetic parent sessions
satisfy foreign keys; they are not claimed as captured sessions. Native
SessionSearch creates the FTS tables/triggers and executes searchObservations.
The adapter does not rewrite questions, emulate ranking, or insert ground truth.

## Frozen controls

The [registered plan](../benchmarks/experiments/claude-mem-component-plan.json)
fixes all 1,015 eligible LoCoMo text questions (649 answerable), 1,339 supplied
pages, top five, three repetitions, both cl100k_base and o200k_base, and
512/1,024/2,048-token caps. Questions are already observed regression data.

The exporter must be Book commit 6f5299004642618e606d001b4c574e1bae572a7e.
Its source hash, exact page bundle hash, cohort hash and query counts are
mandatory guards. The historical Book/Billion/ai-memory quality rows are
reused only after the identical-page/cohort/packing-axis checks pass.

The common assembler adds identical source citations and packs complete
original pages in rank order. This is the historical whole-page policy,
not the newer Book native token-budget API and not claude-mem's production
progressive-disclosure presentation.

## Completed run: 2026-11-12

**The full registered component run completed successfully.** It executed
1,015 original queries three times (3,045 native searches), scored all six
tokenizer/budget settings and reported no failed calls. FTS integrity,
unchanged upstream source, exact returned source/project, native process
exit, corpus and timing-count gates passed. All six settings had zero
token-cap violations, context-size mismatches and duplicate source characters.

The actual run is preserved in
[GitHub Actions 43179914071](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43179914071)
and [result commit 5c268dc](https://github.com/Afloat16/AI-Memory-Book/commit/5c268dc8d0bd9a3d75fce0ca63badba969a3280c).
Read the [summary JSON](../benchmarks/results/claude-mem-components-public.summary.json),
[full compressed report](../benchmarks/results/claude-mem-components-public.json.gz),
[generated result table](../benchmarks/results/claude-mem-components-public.md)
and [completion manifest](../benchmarks/reports/hosted-claude-mem-completion.json).
The manifest preserves all 6,090 started/finished attempt states.

### Source-evidence quality and shared-context costs

Complete evidence is measured over 649 answerable questions and evidence
recall over 788 annotated spans. Mean packed tokens use all 1,015 queries.
MRR follows the existing shared evidence scorer. The Book, billion-context
and ai-memory rows below are the exact historical, identical-page results
embedded in this report after the frozen-data checks; they were not rerun
on the new claude-mem timing host.

| Component | Tokenizer | Cap | Evidence recall | Complete evidence | MRR | Mean packed tokens |
|---|---|---:|---:|---:|---:|---:|
| Book 0ab49d4 score-aware | cl100k_base | 512 | 62.44% | 66.26% | 0.6379 | 447.6 |
| claude-mem 2cfed762 native FTS | cl100k_base | 512 | 59.52% | 63.79% | 0.6027 | 440.8 |
| billion-context dc041dd search | cl100k_base | 512 | 58.88% | 62.71% | 0.6109 | 442.8 |
| ai-memory ee73c04 hybrid | cl100k_base | 512 | 56.60% | 58.86% | 0.5511 | 451.1 |
| Book 0ab49d4 score-aware | cl100k_base | 1,024 | 69.54% | 72.88% | 0.6547 | 827.2 |
| claude-mem 2cfed762 native FTS | cl100k_base | 1,024 | 66.24% | 70.11% | 0.6193 | 804.8 |
| billion-context dc041dd search | cl100k_base | 1,024 | 65.48% | 68.72% | 0.6287 | 862.6 |
| ai-memory ee73c04 hybrid | cl100k_base | 1,024 | 64.47% | 66.72% | 0.5718 | 779.3 |
| Book 0ab49d4 score-aware | cl100k_base | 2,048 | 69.54% | 72.88% | 0.6547 | 832.1 |
| claude-mem 2cfed762 native FTS | cl100k_base | 2,048 | 66.24% | 70.11% | 0.6193 | 807.9 |
| billion-context dc041dd search | cl100k_base | 2,048 | 65.48% | 68.72% | 0.6287 | 871.0 |
| ai-memory ee73c04 hybrid | cl100k_base | 2,048 | 64.59% | 66.87% | 0.5721 | 782.4 |
| Book 0ab49d4 score-aware | o200k_base | 512 | 62.94% | 66.72% | 0.6394 | 451.5 |
| claude-mem 2cfed762 native FTS | o200k_base | 512 | 59.64% | 63.79% | 0.6032 | 444.1 |
| billion-context dc041dd search | o200k_base | 512 | 59.39% | 63.02% | 0.6120 | 445.8 |
| ai-memory ee73c04 hybrid | o200k_base | 512 | 56.98% | 59.17% | 0.5523 | 451.8 |
| Book 0ab49d4 score-aware | o200k_base | 1,024 | 69.54% | 72.88% | 0.6547 | 809.2 |
| claude-mem 2cfed762 native FTS | o200k_base | 1,024 | 66.24% | 70.11% | 0.6193 | 786.2 |
| billion-context dc041dd search | o200k_base | 1,024 | 65.48% | 68.72% | 0.6287 | 844.6 |
| ai-memory ee73c04 hybrid | o200k_base | 1,024 | 64.47% | 66.72% | 0.5718 | 760.4 |
| Book 0ab49d4 score-aware | o200k_base | 2,048 | 69.54% | 72.88% | 0.6547 | 810.0 |
| claude-mem 2cfed762 native FTS | o200k_base | 2,048 | 66.24% | 70.11% | 0.6193 | 787.4 |
| billion-context dc041dd search | o200k_base | 2,048 | 65.48% | 68.72% | 0.6287 | 848.5 |
| ai-memory ee73c04 hybrid | o200k_base | 2,048 | 64.59% | 66.87% | 0.5721 | 762.4 |

At the 1,024-token cl100k_base cap, the frozen score-aware Book component
covers complete evidence on 72.88% of answerable questions, compared with
70.11% for claude-mem native FTS: a **2.77 percentage-point difference**.
Evidence recall differs by **3.30 points**, 69.54% versus 66.24%.
Book's mean packed context is **2.8% larger**, 827.2 versus 804.8 tokens.
The same Book row exceeds billion-context and ai-memory in complete evidence
by 4.16 and 6.16 points, respectively. These are descriptive observations on
previously seen regression questions, without a claim of broad generalization.

Claude-mem covers 455/649 complete questions and 522/788 evidence spans at
1,024 and 2,048 tokens under either tokenizer. At 512 tokens it covers
414/649 complete questions, with 469/788 spans for cl100k_base and 470/788
for o200k_base. Raising the cap above 1,024 does not improve its measured
quality in this top-five/full-page configuration.

**All four measured components return nonempty context for all 366
unanswerable questions at every setting.** This is an unsupported-query
retrieval diagnostic, not a hallucination rate, answer-abstention result
or final-answer accuracy score. The common packer uses original pages and
citations, so these context-token counts are also distinct from each
product's native output payload.

### Actual search timing

Measurements used a separate GitHub Actions Linux x86-64 runner with four
CPUs, Python 3.12.16, Bun 1.3.13, SQLite 3.51.2 and tiktoken 0.12.0.
The native function and persistent Python/Bun JSON bridge are measured
separately. No adapter result cache is enabled; natural process/SQLite
warming remains, and no OS-cold-cache condition is claimed.

| claude-mem operation | Samples | p50 ms | p95 ms | Mean ms |
|---|---:|---:|---:|---:|
| Native searchObservations | 3,045 | 59.073 | 99.973 | 60.529 |
| Native search + persistent JSON bridge | 3,045 | 59.664 | 100.450 | 61.112 |
| First-pass bridge roundtrip | 1,015 | 59.389 | 100.487 | 60.996 |
| Repeated-pass bridge roundtrip | 2,030 | 59.777 | 100.297 | 61.171 |

For reference, the historical component report records Book in-process
p50/p95 of 2.945/4.555 ms, Book actual MCP of 5.764/9.181 ms,
billion-context kernel plus bridge of 1.298/2.413 ms and ai-memory HTTP/MCP
query of 29.720/37.315 ms. The latter excludes a separate mean 5.468 ms for
five full reads. Those values have different operation boundaries, and
claude-mem ran on a different host. **Do not turn this table into a
cross-product speed multiplier or complete-workflow ranking.**

### Returned payload, setup, storage and process memory

The native result is an unmodified observation-row array containing the
full stored source text. Token counting uses its compact, key-sorted JSON
serialization without the bridge envelope. This is the component's native
payload surface, not claude-mem's production MCP presentation.

| Item | Actual measurement | Boundary |
|---|---:|---|
| Mean native row-array tokens, cl100k_base | 1,719.6 | 1,015 successful first-pass queries |
| Mean native row-array tokens, o200k_base | 1,691.3 | Same row-array serialization |
| Mean native row-array UTF-8 bytes | 6,281.3 | Bridge envelope excluded |
| Cached source/runtime preparation and verification | 966.46 ms | Downloads and runtime installation excluded |
| Bun process startup | 39.04 ms | Readiness ping, before database initialization |
| Native schema / FTS creation | 30.83 ms | SessionStore and SessionSearch constructors |
| 1,339 supplied pages with native FTS indexing | 213.65 ms | Harness bulk INSERT and original FTS triggers |
| Logical DB / DB file | 3,522,560 B / 3,522,560 B | At end of indexing and before final checkpoint |
| WAL / SHM before checkpoint | 6,505,512 B / 32,768 B | Additional live SQLite files |
| WAL checkpoint | 1.316 ms | WAL becomes 0 B; DB and SHM sizes unchanged |
| RSS after supplied-page loading | 86,605,824 B | Native Bun process |
| RSS after queries | 90,165,248 B | Native Bun process |
| Linux high-water RSS after queries | 95,141,888 B | Peak process RSS from /proc/self/status |
| Known generative calls in this component | 0 | Observer and answer generation not run |
| Full-workflow model calls / provider cost | Unmeasured | Not zero by inference |

Historical payload figures illustrate why serialization and delivery policy
must remain explicit. Book's separate actual MCP recall returns 1,465.1 mean
o200k_base tokens. Ai-memory's native result **content** averages 876.6 tokens
for search plus 1,698.1 for the fixed policy of reading every top-five page;
the corresponding full **payloads** average 942.5 and 1,913.7 tokens.
Billion's native preview payload averages 569.2 tokens and excludes unmeasured
decompression. Those are different surfaces from claude-mem's complete
observation-row JSON; none establishes equal-cap native-agent answer cost.

Historical preparation also measures different operations: ai-memory's
143.797 s cached-model setup includes 141.637 s of native page writes/indexing
and 2.138 s of readiness, while billion-context's 0.340 s covers adapter/bridge
and harness-list preparation. A separate Book public-source import recorded
1,166.016 ms. Do not infer ingestion speed ratios from these rows. Equivalent
closed-state storage and process-wide RSS were not recorded for every
historical component; the new claude-mem figures cannot fill those gaps.

### Report integrity without rerunning native code

The completed run has these SHA-256 identities:

| Artifact or input | SHA-256 |
|---|---|
| Full report, compressed .json.gz bytes | 46eb187c99213dbf224367f1e2460213afad069125103029aecd3949a9cfa479 |
| Full report, decompressed original JSON bytes | 484f8b1f47d5b12c1752bfc14a10c23e0aa9677c046741b03a2aa53c2bee0279 |
| Summary JSON bytes | 52aa7d8be60360386962ad14ae7858f735559a6f3b19304d16dfd049d7b0295b |
| Supplied-page bundle | 54aa61fd41b7b4058d07fd018bb6d99c6d34a7d73134fb567b67c56536df972a |
| Registered query corpus | 8910da0c1472312fed23b8c7af66d206c872ad41a855f584859f2b446855a857 |
| Frozen exporter source | 191d0bf023fa3589c4832440cde86482563e223bec8a79a25b2b4fe020f2fb85 |

A lightweight aggregation check can hash the existing compressed and summary
files, decompress the report in memory, and compare the raw JSON hash to
the summary's full_report_sha256. The summary must equal the full report
after removing native_query_costs, timing_rows and each configuration's
query_results, then adding that raw hash. Verify the exact six-axis matrix,
1,015 rows per configuration, 3,045 distinct query/repetition timing rows,
the corpus/page/exporter hashes, empty failures and passed validation.
This checks the saved evidence; it does not rescore answers or download the
native runtime.

The completion manifest's attempt states are a public projection of the
fsynced private ledger. Check that each of the 1,015 query IDs has one start
and successful finish per repetition, and that its ledger_sha256 matches
the report. Do not treat hashing that reduced projection as verification
of the original ledger bytes.

## Runtime integrity

[claude-mem-lock.json](../benchmarks/competitors/claude-mem-lock.json) pins
the source archive and official Bun 1.3.13 Linux x64 archive/executable by
SHA-256 and size. During initial preparation all 981 selected source/package/
license files were also checked against the official fixed Git tree's blob
IDs. Native SessionSearch and SessionStore built without npm dependencies
(18 and 54 input modules respectively). The runner imports original verified
TypeScript directly with Bun; it does not run a handwritten clone or a patched
ranker.

Archive extraction reads selected regular members only. Every prepared source
file must equal its pinned archive before and after evaluation. Runtime
configuration and all data stay in the chosen benchmark state directory;
the component does not start an observer, install client hooks, inherit
provider keys, or use an existing user's archive.

## Execute

Run on an otherwise idle Linux x86-64 worker using the project's benchmark
extra. Download the separate pinned LoCoMo file to the path below using the
existing data-preparation workflow; its upstream CC-BY-NC-4.0 license applies.

~~~bash
python -m pip install -e ".[benchmark]"
git fetch origin 6f5299004642618e606d001b4c574e1bae572a7e
git worktree add --detach .artifacts/claude-mem-baseline 6f5299004642618e606d001b4c574e1bae572a7e

python -m benchmarks.competitors.claude_mem \
  --cache .artifacts/competitors/claude-mem

python -m benchmarks.claude_mem_component_eval \
  --smoke --offline \
  --cache .artifacts/competitors/claude-mem \
  --state-dir .artifacts/claude-mem-smoke

python -m benchmarks.claude_mem_component_eval \
  --exporter-src .artifacts/claude-mem-baseline/src \
  --locomo-path .artifacts/data/locomo10.json \
  --cache .artifacts/competitors/claude-mem --offline \
  --state-dir .artifacts/claude-mem-public1015 \
  --output benchmarks/results/claude-mem-components-public
~~~

The smoke uses three fictional pages and tests scope, exact source preservation,
Chinese substring handling and punctuation. It is not a benchmark score.
State directories and report prefixes must be fresh. Preserve interrupted
runs as separate attempts; never blend their timing samples into a new run.

## What the report means

- Evidence recall and complete evidence require intact original annotations
  and matching source spans. They are not generated-answer scores.
- Native function latency and Python/Bun JSON roundtrip are separate.
  Startup, source/runtime preparation, native schema creation, supplied-page
  load with FTS, checkpoint, logical/file DB bytes and process RSS are separate.
  Supplied-page loading is not native observer/capture cost.
- Native returned JSON is the unmodified observation row array, which already
  contains full text. Its tokens are a component consumption surface, not a
  production MCP response and not provider billing.
- Historical comparator timings retain their original host/process metadata
  and differing boundaries. Do not calculate a full-product speedup ratio
  from historical in-process, kernel/bridge and HTTP/MCP rows.
- Chroma, observer summaries, timeline/detail selection, native MCP, host hooks,
  session injection and final answer generation remain unmeasured here.
  claude-mem can use a local OpenAI-compatible observer; missing measurements
  do not imply a commercial API key is required.
- Every attempted query is fsynced to a ledger. Failed queries stay in the
  denominators with empty evidence; errors invalidate successful measurement
  claims. Missing costs are unknown, not zero. Public reports contain only
  IDs, metrics and hashes; source/query text remains in the ignored workspace.

For the product architecture and local observer configuration see the
[official search architecture](https://github.com/thedotmack/claude-mem/blob/2cfed7620c1b44db87c7f04cbf073ec37efca38d/docs/public/architecture/search-architecture.mdx)
and
[official compatible-provider guide](https://github.com/thedotmack/claude-mem/blob/2cfed7620c1b44db87c7f04cbf073ec37efca38d/docs/public/usage/openai-compatible-provider.mdx).
