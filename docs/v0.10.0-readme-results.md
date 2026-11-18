# Current release: results and evidence

The README presents the capabilities of **v0.10.0**. The tables below distinguish
the current wheel's fresh quality replay from retained component measurements.
Older source identities remain here for reproducibility, rather than becoming
version headings in the README.

## What was verified on the current release

| Check | Result |
|---|---|
| Released source | `164f48c42e88bd096bf58827d8b2ba77a9048ae3` |
| Runtime digest | `d00d84ef8436c97b45de5e5e5c2b67883ffbc03992cffa10e7f6d35a15e7fd16` |
| Executed package | Published CPython 3.12 Linux x86_64 native wheel, installed into an isolated environment |
| Package identity | All 27 installed source files and the loaded extension match the published wheel; the source files also match the release commit |
| Native excerpt replay | **640/640 responses match** across four repository strategies and two character budgets |
| Common-block Book replay | **160/160 responses match**, with no response-field exclusions |
| Independent score derivation | **800/800 scores match**, with no source-validation or budget failures |
| Timing scope | One execution per setting; retained evaluator timers are diagnostics, not a new speed experiment |

The native comparison excludes only the top-level `latency_ms` and `cache_hit`
diagnostics. Evidence text, IDs, source spans, ranking, budgets and serialized
response-field order remain in the comparison. The unchanged evaluators ran
once at both 1,200 and 2,400 characters. No external engine, model inference or
native-language performance experiment was rerun.

[Current verification report](../benchmarks/reports/readme-current/verification.json)
· [Original-byte manifest for the compressed raw records](../benchmarks/reports/readme-current/raw-manifest.json)
· [Replay script](../scripts/verify_current_readme_results.py).

## Fixed workload and comparison modes

| Property | Fixed setting |
|---|---|
| Workload | Authored synthetic engineering development fixture |
| Scope | 8 projects, 4 algorithm families, 6 chronological checkpoints |
| Questions | 80 total: 72 answerable and 8 missing-evidence cases |
| Evidence / policy denominators | 80 required spans and 48 fixed-policy cases |
| Common-block candidate boundary | Same project scope and at most 5 candidates |
| Common-block track | Same complete source pages and citation framing; oversized whole blocks are skipped |
| Native excerpt track | Book and the repository's scoped flat-FTS, recent-history and no-memory strategies |
| Model or coding evaluation | No coding LLM, independently held-out task set or generated-code accuracy measurement |

The current Book rows were replayed from the published wheel. External rows
retain the original pinned component executions, whose Book outputs match the
current replay exactly. Their configurations are explicitly limited:

| Component | Executed mode |
|---|---|
| billion-context | Pinned search kernel over supplied original pages |
| claude-mem | Raw-observation FTS; observer/summarization workflow excluded |
| Basic Memory | Explicit FTS; default full hybrid workflow excluded |
| Mem0 | `infer=False`, Chroma provider; fact extraction excluded |
| Chroma | Vector retrieval using the pinned local MiniLM representation |
| LangGraph Store | Indexed store using the same MiniLM representation |

The three MiniLM configurations were executed separately. Their equal scores
are correlated: this fixture gives them the same ordered page-body sequence,
although candidate IDs can differ for repeated maintenance text. They are
grouped in the README to make this dependence visible. The final checkpoint
contains 144 pages but only 44 distinct bodies, including 96 maintenance pages
with eight distinct bodies. [Pinned protocol](../benchmarks/competitors/memory-systems-plan.md)
· [Complete retained component report](../benchmarks/reports/v0.6.0-engineering/hosted/memory-systems/report.json)
· [Shared representation analysis](shared-minilm-audit.md).

## Complete quality results

### Common-block comparison

| Component | Budget | Evidence spans | Complete cases | Fixed-policy passes | Stale-only cases | Mean characters |
|---|---:|---:|---:|---:|---:|---:|
| **Current Book** | 2,400 | **80/80** | **72/72** | **48/48** | **0** | 1,799.2 |
| billion-context | 2,400 | 72/80 | 64/72 | 40/48 | 0 | 1,955.0 |
| claude-mem FTS | 2,400 | 72/80 | 64/72 | 40/48 | 0 | 1,488.5 |
| Basic Memory FTS | 2,400 | 72/80 | 64/72 | 40/48 | 0 | 1,333.1 |
| Each shared-MiniLM configuration | 2,400 | 55/80 | 47/72 | 25/48 | 4 | 1,963.0 |
| **Current Book** | 1,200 | **76/80** | **68/72** | **44/48** | **4** | 1,048.1 |
| billion-context | 1,200 | 72/80 | 64/72 | 40/48 | 0 | 948.5 |
| claude-mem FTS | 1,200 | 72/80 | 64/72 | 40/48 | 0 | 848.0 |
| Basic Memory FTS | 1,200 | 72/80 | 64/72 | 40/48 | 0 | 948.5 |
| Each shared-MiniLM configuration | 1,200 | 55/80 | 47/72 | 25/48 | 4 | 1,036.7 |

At 2,400 characters, current Book recovers eight more complete cases than each
tested lexical component (**11.11 percentage points**) and 25 more than the
shared-MiniLM group (**34.72 points**). Its mean context is **7.97% shorter** than
billion-context's, while it returns more text than the two other FTS components.
The mean-character values are packer measurements, not model-token or billing
costs. Rounding is to one decimal; the verification JSON retains exact values.

At 1,200 characters, Book's common-block packer still has four stale-only
training-decision cases: two replacement decisions and two long-gap queries.
Each tested lexical competitor wins those four cases and loses eight others
to Book. The aggregate improvement does not mean every question improves.

### Native excerpt strategies

| Strategy | Budget | Evidence spans | Complete cases | Fixed-policy passes | Stale-only cases | Mean characters |
|---|---:|---:|---:|---:|---:|---:|
| **Current Book** | 2,400 | **80/80** | **72/72** | **48/48** | **0** | 1,799.2 |
| Scoped flat FTS | 2,400 | 60/80 | 52/72 | 28/48 | 14 | 1,801.3 |
| Recent history | 2,400 | 64/80 | 56/72 | 32/48 | 0 | 2,260.9 |
| No memory | 2,400 | 0/80 | 0/72 | 0/48 | 0 | 0.0 |
| **Current Book** | 1,200 | **76/80** | **68/72** | **48/48** | **0** | 1,195.9 |
| Scoped flat FTS | 1,200 | 56/80 | 48/72 | 28/48 | 14 | 1,154.0 |
| Recent history | 1,200 | 40/80 | 32/72 | 16/48 | 0 | 1,184.0 |
| No memory | 1,200 | 0/80 | 0/72 | 0/48 | 0 | 0.0 |

At 2,400 characters, Book recovers **20 more complete cases than flat FTS** and
**16 more than recent history**, with **20.42% fewer mean context characters**
than recent history. These repository strategies are practical baselines, not
additional external products. Native excerpt and common-block results remain
separate, especially at the smaller budget.
Recent history has shorter citation headings and no top-five candidate limit.

All eight missing-evidence queries return related context for Book and each
tested external component. Thus 80/80 evidence spans and 72/72 complete cases
do not establish 80/80 answer correctness, abstention, real task completion or
general performance on unseen data. The fixed-policy consumer selects recorded
policies and executes handwritten variants; it is not a coding model.

## Performance figures shipped with the current release

| Figure / claim | Evidence type | Exact source |
|---|---|---|
| Native-core recall/MCP and ingestion reductions | Retained frozen native-core experiment; implementation is still shipped, timing not rerun for this README | [Native-core validation](native-core-validation.md) |
| Semantic latency and tracked allocations; model-file read/hash work | Frozen measurement of the semantic implementation shipped in the current release | [Semantic raw report](https://github.com/Afloat16/AI-Memory-Book/blob/780a99faa71da50eb0bf6e290fddc765e2b49b43/raw/reports/semantic-runtime.json) |
| Directory latency, SELECT counts and bounded preview reads | Frozen accepted directory comparison on the current implementation | [Directory raw report](https://github.com/Afloat16/AI-Memory-Book/blob/248e74ee4aabd7f53835e5aead67aa8e8f63abbb/raw/reports/directory-runtime.json) |
| All regressions, rejected candidate and interpretation limits | Retained acceptance decision | [Current runtime validation](comprehensive-v010-validation.md) |
| 30 native cells, 67 public assets and actual published installer | Final source-bound publication audit | [Publication proof](https://github.com/Afloat16/AI-Memory-Book/blob/2f57e03299ddc350c773fe3bc2fc528e1b13dbd8/benchmarks/reports/comprehensive-v010/publication-proof/README.md) |

The current replay verifies that all six native C/header files are byte-identical
to measured native-core source `238c8058f723a203eaca99f94d924ab77de4c0b3`; the
`MemoryBook.recall` method AST is also identical. Only `chapter` changes among
the class methods. This supports identifying the retained implementation, not
assigning its earlier host's elapsed times to the newly built wheel.

Performance percentages from different experiments are not multiplied or added.
The semantic and directory figures are warm synthetic component measurements.
Tracked allocation is not total process RSS; mocked model initialization excludes
real tokenizer parsing, ONNX loading and inference. Small-fixture regressions
and all paired rounds remain in the linked reports.

## Reproduce the current quality check

Use a checkout containing this replay script and the released Git objects.
Download the matching native wheel and `release-manifest.json` from the
[current release](https://github.com/Afloat16/AI-Memory-Book/releases/tag/v0.10.0).
This example uses the same CPython 3.12 Linux x86_64 package as the recorded replay:

```sh
python3.12 -m venv .artifacts/readme-venv
.artifacts/readme-venv/bin/python -I -m pip install --no-index --no-deps ./ai_memory_book-0.10.0-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl
.artifacts/readme-venv/bin/python -I scripts/verify_current_readme_results.py \
  --wheel ./ai_memory_book-0.10.0-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl \
  --manifest ./release-manifest.json \
  --output .artifacts/readme-replay-new
```

The output must be new. The script refuses changed evaluator inputs or a wheel
that differs from its manifest and released source. It preserves raw evaluator
records with lossless compression, records exact hashes, and reports failed
comparisons without replacing them with a successful run. External engines are
not prepared or executed. Their pinned versions, original calls, source maps,
failure records and full product-mode limitations remain in the archived reports.
