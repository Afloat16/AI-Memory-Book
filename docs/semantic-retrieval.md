# Optional local semantic retrieval

Semantic retrieval adds candidates for paraphrases with little shared wording.
It is explicitly enabled and uses a local, pinned multilingual sentence model.
The default Python, CLI and MCP path remains lexical SQLite retrieval, with no
model download, embedding computation or semantic index requirement.

This option changes candidate ranking. It can improve recall and also displace
useful lexical matches. It does not guarantee complete evidence, resolve old
versus current decisions, or establish final-answer accuracy. Keep using the
returned source references to check the original conversation.

## Measured outcomes — 2026-11-12

The registered four-cohort matrix has completed actual local inference:
**1,347 questions × 3 token budgets × 2 modes × 3 repetitions**. The default
remains lexical because the measured quality tradeoff is not uniformly positive.

| Cohort, 512 cl100k_base tokens | Lexical complete evidence | Semantic complete evidence |
|---|---:|---:|
| Synthetic development seed 61 | 85.53% | 63.16% |
| Authored diagnostic, 30 answerable questions | 86.67% | 100.00% |
| Public LoCoMo, 649 answerable questions | 66.41% | 62.56% |
| External HotpotQA, 128 answerable questions | 35.16% | 33.59% |

The authored low-overlap subset improves 2/6 to 6/6. Public low-overlap
complete evidence improves 46.01% to 47.55%, and cross-session completeness
10.53% to 15.79%, while overall public complete questions have **39 gains and
64 losses**. At 1,024 tokens, HotpotQA improves 48.44% to 50.00%; public
complete evidence decreases 72.88% to 71.49%. Synthetic low-overlap questions
remain unresolved. A passing source/budget gate is not a quality-improvement
claim.

On the public cohort's runner, initial model loading takes 1.271 s and building
2,032 windows over 1,339 pages takes 116.554 s. The 384-float vectors alone use
3,121,152 bytes; SQLite and the original archive add overhead. At 512 tokens,
lexical/semantic p50 is 8.078/18.074 ms and p95 is 10.184/22.691 ms.
These times belong to that paired host, not to the other cohorts or historical
MCP benchmarks. There are no endpoint model calls in this retrieval mode;
local embedding CPU work and downloaded artifacts are still costs.

[Public results](../benchmarks/results/semantic-final-regression-public1015.md) ·
[Authored diagnostic](../benchmarks/results/semantic-final-regression-authored36.md) ·
[External results](../benchmarks/results/semantic-final-external-hotpot128.md) ·
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

This first implementation rebuilds the complete index. A continuously changing
capture archive therefore needs a deliberate rebuild schedule; it does not yet
have an incremental embedding worker. The build holds the source snapshot and
derived vectors in memory until publication.

## Ranking and cost boundary

The registered candidate uses the quantized ONNX model
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` at revision
`e8f8c211226b894fcb81acc59f3b34ba3efd5f42`. It produces normalized 384-dimensional
float32 vectors with attention-mask mean pooling. Long pages and queries are
covered by overlapping tokenizer windows of at most 128 model tokens, including
special tokens, with a 32-token overlap. No beginning-only truncation is used.

Project, chapter and session filters are applied before semantic ranking and
the 96-page candidate limit. Page similarity is the maximum cosine similarity
over its windows and the query windows. The existing lexical page order and
the semantic order are combined by equal-weight reciprocal rank fusion with
`k=60`; ties use page IDs. The top requested pages pass through the existing
original-text excerpt and budget assembly. The model never rewrites evidence.

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
publication, failure rollback, cache isolation and scope before candidate
limits. Its deterministic fixture vectors test implementation correctness and
are not semantic quality evidence. Real-model experiments must use the pinned
artifacts and report their source/model hashes and actual results separately.
