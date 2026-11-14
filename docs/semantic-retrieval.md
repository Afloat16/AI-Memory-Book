# Optional local semantic retrieval

Semantic retrieval adds candidates for paraphrases with little shared wording.
It is explicitly enabled and uses a local, pinned multilingual sentence model.
The current optional ranking policy is **Q2: one lexical anchor with an RRF tail**.
The default Python, CLI and MCP path remains lexical SQLite retrieval, with no
model download, embedding computation or semantic index requirement.

This option changes candidate ranking. It can improve recall and also displace
useful lexical matches. It does not guarantee complete evidence, resolve old
versus current decisions, or establish final-answer accuracy. Keep using the
returned source references to check the original conversation.

## Historical v0.3.2 C2 validation — 2026-11-13

The round-four candidate is frozen at
[`2d7b5e3`](https://github.com/Afloat16/AI-Memory-Book/commit/2d7b5e38839fb21724ad3beec6b6ebabbda45636),
runtime SHA256
`179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93`.
C2 reduces repeated source preparation and exact token-counting work. It keeps
the Q2 model, persisted-vector rules and fusion policy unchanged; it introduces
no new semantic quality candidate. The model fingerprint remains
`2e033409dceae3e08a48980eb82c2fa463363fc950fb64bc8bbff02bf9c0cd25`, with
`SEMANTIC_VERSION=1` and `FUSION_VERSION=3`.

The [completed Q2 compatibility audit](../benchmarks/reports/round4-compatibility-final/paired-audit.json)
checks **1,968 calls and 984 exact complete-payload pairs** against v0.3.1 on
authored36 and historical Hotpot128, using both `cl100k_base` and `o200k_base`
at 512/1,024/2,048 tokens. Only `latency_ms` is excluded from payload equality.
Both sources use copies of one baseline-built vector snapshot per cohort.
Source, projection, scope, token-budget and semantic/model/cache checks pass;
the independent audit also verifies source/evaluator bytes, model artifacts,
every ledger event and unchanged originals/vectors. These are old-cohort
compatibility results, not new quality gains or semantic speed measurements.

The [fresh round-four manifest](../benchmarks/experiments/round4-hotpot256-manifest.json)
contains **256 questions**, excludes all **640 historical IDs**, and has
**zero historical overlap**. The
[independent freeze audit](../benchmarks/reports/round4-freeze-independent-audit.json)
reconstructs the exact ID-only selection and verifies the source/evaluator,
asset, binding and manifest commit order. The
[existing content verifier](../benchmarks/reports/round4-selection-local-audit.json)
separately validates the selected canonical content and dataset fingerprint.
This is another selection from the same HotpotQA source, not a new domain.

**The fresh comparison is complete and its offline audit passed.**
[Run 43363060062](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43363060062)
published the [complete report](../benchmarks/results/round4-comparison-43363060062-1/report.md)
at result commit
[`eff3941`](https://github.com/Afloat16/AI-Memory-Book/commit/eff394119105d59186c730e2480d86d1436401a6).
The [independent audit](../benchmarks/reports/round4-comparison-independent-audit.json)
checks all 32 result files and the checkpoint against that commit, 4,608 native
calls, 4,608 component searches and 18,432 start/finish ledger events. It
recomputes 54 quality cells and all 12 Q2 gain/loss cells from saved rows,
and verifies complete-payload equality between baseline and C2 lexical
retrieval for 1,536 native and 768 component pairs. The unchanged strict
saved-report verifier also passed, without executing a new query.

### Fresh Q2 gains and losses

All 256 questions are answerable, with 635 required evidence annotations
across 2,548 supplied paragraphs. Native recall uses an 8,000-character cap,
top five results and no result cache. The component view packs common source
pages from each ranker's first search; its six token projections reuse that
search. These are Q2-versus-lexical policy comparisons within C2, not quality
changes introduced by the v0.3.2 optimization.

| View | Tokenizer | Token budget | Lexical complete evidence | Q2 complete evidence | Complete-question gains / losses |
|---|---|---:|---:|---:|---:|
| Native | cl100k_base | 512 | 39.45% | 36.33% | 19 / 27 |
| Native | cl100k_base | 1,024 | 53.91% | 55.08% | 26 / 23 |
| Native | cl100k_base | 2,048 | 53.91% | 55.08% | 26 / 23 |
| Native | o200k_base | 512 | 39.45% | 36.72% | 19 / 26 |
| Native | o200k_base | 1,024 | 53.91% | 55.08% | 26 / 23 |
| Native | o200k_base | 2,048 | 53.91% | 55.08% | 26 / 23 |
| Common-page component | cl100k_base | 512 | 41.02% | 39.84% | 21 / 24 |
| Common-page component | cl100k_base | 1,024 | 53.91% | 55.08% | 26 / 23 |
| Common-page component | cl100k_base | 2,048 | 53.91% | 55.08% | 26 / 23 |
| Common-page component | o200k_base | 512 | 41.41% | 40.62% | 22 / 24 |
| Common-page component | o200k_base | 1,024 | 53.91% | 55.08% | 26 / 23 |
| Common-page component | o200k_base | 2,048 | 53.91% | 55.08% | 26 / 23 |

At 1,024 and 2,048 tokens, Q2 gains three net complete questions
(**+1.171875 percentage points**) while losing 23 cases that lexical completes.
Annotation recall rises 75.75% to 76.69%, with 40 annotation gains and 34
losses. At 512 tokens Q2 loses completeness in every tokenizer/view pair.
Native annotation recall falls 67.87% to 66.14% with cl100k_base and to 66.30%
with o200k_base; the corresponding annotation gains/losses are 29/40 and 29/39.
Component annotation gains/losses are 36/39 and 35/39. The low-overlap group
contains only four questions: native 512-cl100k completeness falls from 1/4
to 0/4, while the component rates remain 1/4 each. These small groups cannot
establish broad paraphrase robustness. Every changed-query and annotation list
remains in the [saved assessment](../benchmarks/results/round4-comparison-43363060062-1/assessment.json).

At the common 1,024-cl100k projection, Q2's 55.08% completeness exceeds
claude-mem FTS's 44.53%, but is below ai-memory hybrid's 55.86% and
billion-context's 60.55%. Q2's packed MRR is 0.8663. Supplied-page adapters,
answerable-only questions and different native transports limit whole-product,
abstention and generated-answer claims; see the [complete comparison](comparison.md).

### Fresh semantic costs and retained adverse observations

The native Q2 index has 4,810 windows over 3,953 pages and **7,388,160 vector
bytes**. Its measured build takes **277.876 s**, with a separate **1.220 s**
model load; total engine setup is **282.970 s**. The component Q2 build takes
275.426 s, with a separate 1.224 s model load and 277.600 s total setup.
The independently built native/component persisted-vector digests match.
These are fresh-build costs on this runner; compatible existing vectors remain
reusable. They are not upgrade-time measurements.

| Query boundary | C2 lexical p50 / p95 | Q2 p50 / p95 |
|---|---:|---:|
| Native, 8,000 chars, 1,024 cl100k tokens, one call/question | 2.918 / 4.105 ms | 13.998 / 21.022 ms |
| Component ranker, 100,000 chars, three search repetitions | 2.353 / 3.488 ms | 12.832 / 20.406 ms |

Native mean context size at 1,024 cl100k tokens is 803.63 lexical versus
818.07 Q2. The component search returns 3,972.57 versus 4,079.44 mean
cl100k payload tokens before the common page-packing projection; these payload
counts include metadata and are not the projected context budget.

| Sampled process-tree peak RSS | C2 lexical | Q2 |
|---|---:|---:|
| Native setup / queries / finalization | 558.42 / 541.79 / 1,107.09 MiB | 1,294.50 / 1,278.19 / 1,313.59 MiB |
| Component setup / queries / finalization | 943.53 / 524.91 / 1,061.41 MiB | 1,247.69 / 1,247.69 / 1,301.83 MiB |

Fresh C2-versus-v0.3.1 lexical costs also retain adverse observations:
component p50 rises **2.239 to 2.353 ms (+5.12%)**, p95 rises
**3.304 to 3.488 ms (+5.56%)**, and sampled component setup RSS rises
**548.65 to 943.53 MiB (+71.97%)**. Sampled native finalization RSS rises
**655.16 to 1,107.09 MiB (+68.98%)**. Their cause is unresolved. These
unbalanced descriptive observations are separate from the registered old-data
[formal lexical performance review](round4-performance-review.md); that
formal resource gate does not waive these fresh costs.

The resource audit checks all 27 setup/query/finalization phase summaries.
RSS sampling includes the evaluator, loaded corpus and live descendants,
with up to two processes observed; shared mappings may be counted repeatedly.
The reports retain maxima and sample counts, without per-sample process
traces, so they cannot isolate runtime memory or establish the cause of the
increases. The offline arithmetic audit likewise uses saved ranks, hashes and
metric fields: omitted question/response text is not rescored or retokenized.
The source/projection invariants and complete losses remain available in the
canonical reports; no retrieval or timing was repeated to choose a better result.

## Historical round-two fixed-source validation — 2026-11-12

The round-two integrated runtime was frozen at
[`cbf6260`](https://github.com/Afloat16/AI-Memory-Book/commit/cbf626037b42f11f8bc5b6d46f56caac771e54ba).
The complete [256-question comparison](../benchmarks/results/round2-43207732852-1/report.md)
contains both native and shared-page semantic stages, every budget, and three
actual repetitions. The candidate and all settings remained unchanged through
the [explicit evaluator recovery](round2-recovery.md).

| Round-two view, cl100k_base | Lexical complete evidence | Q2 complete evidence | Complete-question gains / losses |
|---|---:|---:|---:|
| Native, 8,000 chars, 512 tokens | 41.41% | 41.41% | 16 / 16 |
| Native, 8,000 chars, 1,024 tokens | 51.95% | 57.42% | 23 / 9 |
| Native, 8,000 chars, 2,048 tokens | 51.95% | 57.81% | 24 / 9 |
| Shared-page component, 512 tokens | 41.41% | 42.19% | 16 / 14 |
| Shared-page component, 1,024 tokens | 51.95% | 57.81% | 24 / 9 |
| Shared-page component, 2,048 tokens | 51.95% | 57.81% | 24 / 9 |

That run retains small-budget Q2 losses. With 512 `o200k_base` tokens, native
completeness falls 24.22% to 23.83% at 2,000 characters and 42.19% to 41.02%
at 8,000. The 512-cl100k native complete rates tie while annotation recall
decreases. The round-two shared-page Q2 result at 1,024 cl100k tokens exceeds
claude-mem FTS and ai-memory, but remains below billion-context's 61.72%.

The nine-question low-overlap group has native 1,024-token completeness
1/9 lexical versus 2/9 Q2; the corresponding component scores are 1/9 and
2/9. At 512 tokens the component scores are both 0/9. All 256 cases combine
evidence across supplied paragraphs mapped into sessions/chapters; this is not
a new real-conversation corpus or proof that general semantic memory is solved.

Costs remain substantial: native 1,024-token / 8,000-character p50/p95 is
6.150/9.841 ms lexical and 15.517/24.227 ms Q2. Q2 builds 4,566 windows over
3,769 pages in 207.559 s, with 7,013,376 vector bytes and a separate 1.029 s
model load. Sampled query process-tree RSS is 280.68 MiB lexical and 1,041.29
MiB Q2, including the evaluator and corpus; the [round-two comparison guide](comparison-v0.3.0.md)
also retains OS worker peaks, cache downloads, live state and exact interfaces.
These are fresh-build observations; compatible existing vectors remain reusable.

## Historical Q2 development selection on old data

The Q2 development matrix has completed actual local inference:
**1,347 questions × 3 token budgets × 4 modes × 3 repetitions = 48,492 recalls**.
The four paired modes are lexical, original RRF, frozen Q1 score fusion and Q2.
All questions below are old development/regression data. These results do not
establish new-domain generalization or generated-answer accuracy. The default
remains lexical; Q2 was selected as the policy for the explicitly enabled
semantic route in that round. Q1 remains a historical research comparison.

| Old cohort, 512 cl100k_base tokens | Lexical complete evidence | Q2 complete evidence |
|---|---:|---:|
| Synthetic development seed 61 | 85.53% | 81.58% |
| Authored diagnostic, 30 answerable questions | 86.67% | 100.00% |
| Public LoCoMo regression, 649 answerable questions | 66.41% | 68.10% |
| HotpotQA regression, 128 answerable questions | 35.16% | 34.38% |

At 512 tokens, LoCoMo complete questions have **30 gains and 19 losses** against
lexical retrieval. Its 326-question low-overlap group improves 46.01% to 50.00%.
Its 76 cross-session questions improve 10.53% to 11.84% against lexical, but
regress against original RRF: **9/76 versus 10/76**, with one gain and two losses.
At 1024/2048 tokens, Q2 reaches 74.27% overall LoCoMo completeness versus lexical
72.88%, and 50.78% on Hotpot versus lexical 48.44%. Synthetic low-overlap
completeness remains 68.75%, below lexical's 75%; synthetic and Hotpot overall
512-token completeness also remain below lexical. A passing source/budget gate
is not a claim of universal quality improvement.

The Q2 report separately records model loading, full index construction,
window/vector storage and query latency. On the public cohort's paired runner,
512-token lexical/Q2 p50 is **5.846/13.527 ms** and p95 is **7.364/16.997 ms**.
Initial model loading took 1.054 s and building 2,032 windows over 1,339 pages
took 94.516 s. The vectors alone used 3,121,152 bytes, before SQLite and original
archive storage. These fresh-build costs are not an upgrade requirement for an
existing compatible index.
These timings belong to that pair, not to other hosts or historical MCP results.
Q2 adds no embedding operation relative to original RRF: each semantic mode
performed 12,123 query encodes across the complete matrix, versus zero for
lexical. There are no endpoint model calls in this retrieval mode; local CPU
work, model files and index storage remain costs.

Some semantic control contexts and evidence differ between the Q1 and Q2 runs
despite matching verified model and indexed page-text/ID fingerprints. The
cause is not established. The round-two report retains those differences and uses
the four modes sharing one actual index within the Q2 run for its main
comparisons. Repeated contexts within each run passed their consistency checks.

[Round-two Q2 development comparison, all budgets and costs](../benchmarks/reports/round2-anchor-development.md) ·
[Q2 selection and limitations](../benchmarks/reports/round2-anchor-decision.md) ·
[Q2 registered policy](../benchmarks/experiments/round2-anchor-plan.json) ·
[Q1 research comparison and regressions](../benchmarks/reports/round2-quality-development.md).

### Historical original-RRF results

The reports below measured the earlier **unanchored, equal-weight RRF** policy.
They remain audit records and are **not measurements of current Q2**. The old
Hotpot128 cohort is regression data in this optimization round.

[Historical public results](../benchmarks/results/semantic-final-regression-public1015.md) ·
[Historical authored diagnostic](../benchmarks/results/semantic-final-regression-authored36.md) ·
[Historical Hotpot128 results](../benchmarks/results/semantic-final-external-hotpot128.md) ·
[Historical four-cohort aggregate](../benchmarks/RESULTS-semantic-retrieval.md) ·
[Result index](../benchmarks/README.md).

## Prepare and build explicitly

From a source checkout, install the optional dependencies and download the
registered model artifacts:

```bash
python -m pip install -e ".[semantic,tokens,mcp,clients]"
python scripts/prepare_semantic_model.py --output /absolute/path/to/semantic-model
```

Preparation downloads **127,535,388 bytes** of model and tokenizer data in
total, plus the separately installed Python dependencies. It checks the exact
size and SHA-256 of each artifact before using it. No memory or query text is
sent with the download. Embedding computation, index building and querying use
those local files, without a model-provider endpoint. See the
[predeclared model and retrieval plan](../benchmarks/experiments/semantic-local-plan.json)
for the repository, revision, file hashes and Apache-2.0 model license.

From v0.3.1, Book sets `ORT_DISABLE_TELEMETRY=1` before importing ONNX Runtime
and calls `disable_telemetry_events()` before creating an inference session.
Normal CLI and MCP use needs no extra setting. If another application imports
ONNX Runtime before Book, set that environment variable before starting the
application: an opt-out made after import cannot undo an initialization event.
This follows [ONNX Runtime's privacy guidance](https://github.com/microsoft/onnxruntime/blob/main/docs/Privacy.md)
and does not change the model, vectors or ranking policy.

```python
from memory_book import MemoryBook

with MemoryBook("memory.db", semantic_model_dir="/absolute/path/to/semantic-model") as book:
    # Import all desired conversations before building derived vectors.
    report = book.build_semantic_index()
    result = book.recall(
        "What accommodation helps someone with poor eyesight read the exhibits?",
        project="museum",
        semantic=True,
        budget_chars=4000,
        budget_tokens=512,
        tokenizer="cl100k_base",
    )
```

`semantic_model_dir` configures which local artifacts may be loaded;
`semantic=True` enables their use for one call. Merely configuring a model
directory does not initialize it during lexical recall. Both exact token and
character caps still include citations and separators in the returned context.
Outer MCP/JSON fields remain outside the context cap, as documented in
[token budgets](token-budget.md).

## Index freshness and source preservation

Building an index takes a read snapshot of the current original pages, releases
that read transaction, and embeds the snapshot without holding a write lock.
The new vectors are published in one write transaction only if the archive's
revision is unchanged. A concurrent import makes the build fail with a clear
rebuild message; it does not overwrite sources or publish a stale partial index.
An earlier derived index remains intact on a failed build.

Vectors live in two separate SQLite tables, `semantic_vectors` and
`semantic_meta`. Building them does not change page IDs, source text, character
offsets or the archive revision. It clears result caches. An archive created
without semantic indexing does not acquire these tables on the default path.

An import, deletion, relink or relevant metadata change advances the archive
revision and invalidates semantic retrieval. Unchanged idempotent imports do
not. A semantic request checks the revision and model fingerprint **before**
returning a cached answer. Missing, stale or mismatched indexes raise
`SemanticIndexError`; the service never silently falls back to lexical-only
results. Rebuild explicitly after capture has updated the archive. Lexical
retrieval continues to work while the semantic index is stale.

The embedding/model identity remains `SEMANTIC_VERSION=1`. Q2 uses the separate
`FUSION_VERSION=3` in semantic result-cache keys. **A compatible existing v1
embedding index does not need to be rebuilt solely because fusion changed.**
Old fusion-result cache entries are not reused, while lexical cache behavior
remains unchanged. Changes to source revision, model artifacts or embedding
rules still require the explicit rebuild described above.

The current index builder rebuilds the complete index. A continuously changing
capture archive therefore needs a deliberate rebuild schedule; it does not yet
have an incremental embedding worker. The build holds the source snapshot and
derived vectors in memory until publication.

## Ranking and cost boundary

The semantic route uses the quantized ONNX model
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` at revision
`e8f8c211226b894fcb81acc59f3b34ba3efd5f42`. It produces normalized 384-dimensional
float32 vectors with attention-mask mean pooling. Long pages and queries are
covered by overlapping tokenizer windows of at most 128 model tokens, including
special tokens, with a 32-token overlap. No beginning-only truncation is used.

Project, chapter and session filters are applied before semantic ranking and
the 96-page candidate limit. Page similarity is the maximum cosine similarity
over its windows and the query windows. The existing lexical page order and
the semantic order first undergo equal-weight reciprocal rank fusion with
`k=60`; ties use page IDs. When both routes have candidates, **Q2 then promotes
the first candidate from the existing lexical order to the first position**.
The lexical ordering already includes its current novelty/current/optional
coverage priorities. Every other candidate retains its original RRF relative
order, and no candidate is added or removed by fusion itself. If the lexical
route is empty, the original pure-semantic route remains available.

Each page retains its own original RRF score and semantic similarity. Scores
therefore need not be monotonic after the anchor promotion; they are diagnostic
values, not answer probabilities. Current character allocation and token
assembly do not use those numeric scores. Q2 acts through the top-page limit
and rank-order first-fit packing. An anchor outside the previous top-five may
displace a useful fifth page, and a wrong lexical leader can consume scarce
budget. The top requested pages pass through the existing original-text
excerpt and budget assembly. The model never rewrites evidence.

There is no learned abstention threshold. Semantic ranking can return an
unrelated nearest page when the requested fact is absent. A returned page is
evidence to assess, not proof that the answer exists. The caller can inspect
the page, narrow its scope, or state that the evidence does not answer the
question.

The model runs with one ONNX inference thread. Model loading, full index
construction and each uncached query add CPU work and memory use. Vector data
uses 1,536 bytes per window before SQLite overhead. The current search scans
all scoped vectors; this is not an approximate-nearest-neighbor index and its
cost grows with the scope size. A result cache can serve repeated unchanged
queries, but is isolated from lexical results and checked for index freshness.

`build_semantic_index()` reports model identity, package versions, model-load
time, build time, page/window counts, vector bytes and the source fingerprint.
Semantic recall returns `semantic: true` and `semantic_model_fingerprint` in
addition to the normal evidence. Benchmark model loading and indexing
separately from retrieval, and retain quality losses and tail-latency costs.

## Verification

`tests/test_semantic.py` checks explicit opt-in, unchanged lexical behavior,
source and address preservation, stale/mismatched index rejection, concurrent
publication, failure rollback, reuse of compatible indexes across fusion
upgrades, result-cache isolation and scope before candidate limits.
`tests/test_anchor_fusion.py` checks lexical-leader preservation, unchanged
per-page RRF scores, non-anchor relative order and candidate membership.
These deterministic fixtures test implementation correctness and
are not semantic quality evidence. Real-model experiments must use the pinned
artifacts and report their source/model hashes and actual results separately.
