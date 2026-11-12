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

## Measured outcomes — 2026-11-12

The Q2 development matrix has completed actual local inference:
**1,347 questions × 3 token budgets × 4 modes × 3 repetitions = 48,492 recalls**.
The four paired modes are lexical, original RRF, frozen Q1 score fusion and Q2.
All questions below are old development/regression data. These results do not
establish new-domain generalization or generated-answer accuracy. The default
remains lexical; Q2 is the selected replacement candidate for the explicitly
enabled semantic route. Q1 remains a research comparison.

| Old cohort, 512 cl100k_base tokens | Lexical complete evidence | Current Q2 complete evidence |
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
cause is not established. The new report retains those differences and uses
the four modes sharing one actual index within the Q2 run for its main
comparisons. Repeated contexts within each run passed their consistency checks.

[Current Q2 comparison, all budgets and costs](../benchmarks/reports/round2-anchor-development.md) ·
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
sent with the download. Runtime loading, index building and querying use those
local files and make no endpoint calls. See the
[predeclared model and retrieval plan](../benchmarks/experiments/semantic-local-plan.json)
for the repository, revision, file hashes and Apache-2.0 model license.

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
