# Real engineering history replay pilot

This pilot checks whether a retrieval system returns the right original source
evidence from several versions of similar engineering projects. It uses genuine
NetworkX and SymPy Git history, with **20 questions and evidence annotations
written by an AI research agent**. The questions are not observed developer
conversations, and the source-document ingestion records are not real chat
transcripts. No generated answer or patch is scored in this pilot.

The fixed inputs are the [protocol](../benchmarks/fixtures/engineering_protocol.json),
[questions](../benchmarks/fixtures/engineering_cases.json),
[upstream pins](../benchmarks/fixtures/engineering_upstream.json),
[source manifest](../benchmarks/fixtures/engineering_source_manifest.json),
[ancestry receipts](../benchmarks/fixtures/engineering_ancestry.json), and separate
[gold source spans](../benchmarks/fixtures/engineering_gold.json). The runner is
[engineering_replay.py](../benchmarks/engineering_replay.py).

## Original data and provenance

Each chain retains every Python source or test file changed by the pinned fix,
at both the fix and its first parent, plus the repository's license at each
revision. The 40 original records comprise 32 source/test snapshots and eight
license texts: 1,508,126 UTF-8 bytes in total. The manifest preserves each exact
commit, path, author and committer timestamp, official GitHub contents URL,
upstream Git blob SHA, content SHA256 and byte count. Decoded bytes have been
checked against the blob identities returned by the official GitHub API; they
are not merely assigned a new local checksum.

| Chain | Base commit | Fix commit | Main implementation and regression file |
| --- | --- | --- | --- |
| NetworkX rooted product | `74af3e63d21406680ae21a60975135472d3ca412` | [`fbd96ecfb58b39d0265c6011504a00f1534eb727`](https://github.com/networkx/networkx/commit/fbd96ecfb58b39d0265c6011504a00f1534eb727) | `networkx/algorithms/operators/product.py`; `tests/test_product.py` in the same directory |
| NetworkX reaching centrality | `b48317b78efa511c49dc2fb9bd2e27aa71665238` | [`7aa7467a92e07d66c9f161104a7ccfb34f0d64ab`](https://github.com/networkx/networkx/commit/7aa7467a92e07d66c9f161104a7ccfb34f0d64ab) | `networkx/algorithms/centrality/reaching.py`; `tests/test_reaching.py` in the same directory |
| SymPy zero equality | `863fc643b47c08399045c98e6e661d5731d4520e` | [`9d6100a13d62999ea36420ed14aa403c1966f2e9`](https://github.com/sympy/sympy/commit/9d6100a13d62999ea36420ed14aa403c1966f2e9) | `sympy/core/numbers.py`; `sympy/core/tests/test_numbers.py`; all ten changed Python files are retained |
| SymPy finite-field integers | `03b3b6b32f5f4b23495e136a67b9f2ad512ce373` | [`0a7615ee874c1ee07df55ced4651cc2979787a8e`](https://github.com/sympy/sympy/commit/0a7615ee874c1ee07df55ced4651cc2979787a8e) | `sympy/polys/domains/finitefield.py`; `sympy/polys/domains/tests/test_domains.py` |

NetworkX and SymPy use BSD-3-Clause; their original license texts and copyright
notices are retained alongside the source snapshots. The external BillionKernel
component is pinned by the existing
[lock](../benchmarks/competitors/billion-round2-lock.json) to
[`9674cfafbc78c50245ae0d887483d3d6ce880c15`](https://github.com/ranxianglei/billion-context/commit/9674cfafbc78c50245ae0d887483d3d6ce880c15).
Its license is MIT text **with an additional attribution-on-product-surfaces
term**; it is not described here as unrestricted plain MIT.

### Registration chronology

The protocol, source pool and question drafts were written before source
materialization. The original sources were then fetched while the draft was
being reviewed. The authorship wording was corrected to identify AI authorship,
and the three protocol files were committed at
`d783065473093cacb5b544e0e4e5de196730be20`; the raw sources, manifest and ancestry
receipts were committed separately afterward. The old protocol status and
sequence text saying “before-data-materialization” therefore does **not** mean
that the protocol Git commit preceded the download. There were no retrieval
scores, generated answers, generated patches or upstream test executions during
preparation. The four chains and 20 question strings were not selected or
replaced based on retrieval results. The complete evaluator, annotations and
separate runtime binding must be committed before the first scored matrix.

## Public inputs and shared availability control

Each chain contributes five fixed slices: project/API scope, current update,
historical base, cross-artifact resumption, and an unsupported operational
decision. There are 16 answerable questions with 28 required original-source
spans, and four unsupported questions. Historical-base questions expose only
sources available at their base revision; resume questions may intentionally
require both older and newer evidence.

The question supplies a repository, snapshot commit and UTC availability
cutoff. **The harness applies repository, timestamp and ancestor filtering
equally to every engine before ingestion.** It uses the saved official ancestry
receipts to exclude a later or divergent commit, even when its timestamp would
otherwise fit. This is an external control, not a claim that Memory Book can
natively infer a project, reason about branches, or implement historical
`as-of` retrieval. Because the target repository is supplied and filtered,
wrong-project hits are an integrity failure rather than a measured test of
automatic repository disambiguation.

The 32 source/test snapshots become 1,694 deterministic blocks of at most 900
Unicode characters, ending at the last available newline where possible, with
zero overlap. Every original character is preserved. Each block carries only
its original body and repository/path/commit/time/line metadata. Question text,
answerability, gold spans and answer templates are never ingested. Workers
check the annotation file's bound bytes but do not parse or expose its labels.

## Fixed matrix and boundaries

| Arm | Retrieval boundary |
| --- | --- |
| `flat-fts` | Independent SQLite FTS5 BM25 over original source and metadata, with literal, underscore, camel-case and acronym identifier pieces; deterministic ID tie-break |
| `v0.3.4` | Exact published Memory Book Python source, native `recall`, cache disabled |
| `candidate` | Separately bound frozen candidate source, the same native API and controls |
| `billion-context` | Unchanged locked BillionKernel shared-source component and native search, with the same filtered blocks |
| `no-memory` | Explicit empty-context projection; no retrieval call and no invented zero-millisecond measurement |

The baseline is commit `8ad9cbe50a0e387e8baf89690b85cac5e9d575d4`, runtime SHA256
`f361d2bf64a4e1088cbd5cff6ffdaf19aa15e7f1b7ea1de4577d7a488d2ac242`.
The candidate's full commit and runtime hash are recorded in the separate
binding. Round 7's initial candidate changes query-time acronym/identifier
compatibility only. Results from other slices remain part of this diagnostic
even if that change provides no improvement.

Four actual arms each make one lookup for every question: **80 retrieval calls
and 160 intent/completion events**. Each native response supplies at most five
hits. Two common context projections, 1,024 and 4,096 `cl100k_base` tokens with
`tiktoken==0.12.0`, reuse that one response. The result contains 160 measured
quality cells and 40 empty-control cells, **200 total cells**. The deterministic
question shuffle uses seed 7321 and is grouped into eight repository/revision
views for setup. Arms execute sequentially in isolated Python workers, once.
This small sequence is not a balanced latency acceptance experiment.

Memory Book receives `max_page_chars=900`, `cache_size=0`, and native recall
uses `limit=5`, `budget_chars=100000`, `use_cache=False`, `coverage=False`, and
`semantic=False`. The same controls apply to both sources. Native response
payloads are preserved, including their timing and generated context fields.

For quality scoring, native IDs map back to the common original blocks. There
is no replacement search for duplicate or unmapped hits. Duplicate IDs are
counted and deduplicated; an unknown, future or incorrectly scoped ID stops
the run as an integrity failure. The readback is a local in-memory lookup in
the saved source pool, **not a product's document-read API**. Both budgets use
the same citation header, original body and rank-order first-fit packing: a
block that does not fit is skipped, later blocks may fit, and no block is
truncated. The scored context therefore describes the shared retrieval
component boundary; it is distinct from each product's native context format.

## Metrics and limits

Evidence recall measures complete coverage of the predeclared exact source
spans, including a span split across adjacent source blocks. Complete evidence
requires every span for the question. Reciprocal rank uses the first prefix
that covers at least one required span. Source identity matters: the same text
from the wrong revision is not substituted for the annotated evidence.
Stale-only and stale-before-current flags apply only to the explicitly
annotated obsolete spans; intentional historical evidence in a resume question
is not marked stale merely because it is old.

For an unsupported question, nonempty context is a retrieval observation. It
does not demonstrate a fabricated answer or failed abstention: there is no
answer-generating model in this pilot. The empty control likewise receives no
answer-correctness score. Every quality gain, tie and loss relative to v0.3.4 is
retained. No engineering-replay improvement threshold is used to accept the
product; an independently registered identifier gate cannot stand in for this
matrix or for actual AI task success.

Cost records include native lookup wall time, native payload reference-token
count, common original-block readback time, per-budget packing time, setup
time, engine state-file bytes and Python worker peak RSS. Payload tokens are
reference counts, not provider billing. Memory Book lookup includes its native
context assembly; the other components have different native response work.
Setup includes the harness and validation boundary. Worker RSS includes the
Python evaluator and source data; the live Node child's RSS is not sampled, so
these fields do not support an isolated product-memory comparison. Every raw
cost is retained, including increases. The 20 sequential samples per arm are
descriptive and do not establish end-to-end AI completion speed.

This pilot does not execute the upstream fixes, generate a patch, measure
regression-test success, or call an LLM. A later coding-agent benchmark must
use a separately frozen task protocol, the same real model and budgets, real
tool transcripts and executable base/fix oracles. For the SymPy finite-field
chain, the changed `nmod`/`fmpz_mod_ctx` path requires the optional
`python-flint` backend; passing only the pure Python path would not validate
that repair. Future pre-fix coding tasks must use their own base-only evidence
pool so that this replay's post-fix material cannot leak the solution.

## Execution and saved-result audit

The following preparation performs no product retrieval or upstream tests:

```bash
python benchmarks/engineering_replay.py verify
python -m unittest discover -s tests -p 'test_engineering_replay.py' -v
```

After all evaluator closure files have been committed, create the binding with
that exact commit. The paths below refer to the separately prepared source
trees and offline competitor cache:

```bash
python benchmarks/engineering_replay.py bind \
  --baseline-source .artifacts/round7-v034/src \
  --candidate-source .artifacts/round7-i1/src \
  --candidate-commit 517cf6f77a2f9bd36062da7bcf7a3ef9b05e85c4 \
  --evaluator-commit EVALUATOR_COMMIT \
  --billion-cache .artifacts/round7-billion-source \
  --output benchmarks/fixtures/engineering_binding_i1.json
```

Commit and save that exact binding separately before authorizing the first
matrix. The runner requires the binding bytes to exist in the current Git
commit and verifies every evaluator and runtime file against its pinned
commit. After authorization, execute the matrix only once:

```bash
python benchmarks/engineering_replay.py run \
  --binding benchmarks/fixtures/engineering_binding_i1.json \
  --output .artifacts/round7-engineering-replay-i1
```

A source-pair/protocol claim is created exclusively before any lookup, and
each worker requires the same claim. Changing only a binding filename or
timestamp does not create a new claim identity. Each call has a flushed intent
record before invocation and a flushed completion record, with output hashes,
afterward. Worker reports are checkpointed atomically after each call and on
failure. Preserve the entire output directory and claim, including an
incomplete run, original errors and unattempted matrix entries. No automatic
retry, fastest-run selection or question replacement is allowed. Save these
artifacts to the Git evidence checkpoint without modifying the measured bytes.

The saved-result audit rechecks all 80 responses, 160 ledger events, original
source readbacks, both budgets and all 200 cells without making new queries:

```bash
python benchmarks/engineering_replay.py audit \
  --binding benchmarks/fixtures/engineering_binding_i1.json \
  --run-dir .artifacts/round7-engineering-replay-i1 \
  --output .artifacts/round7-engineering-replay-i1-audit.json
```

This command is the runner's reproducible integrity recheck. An independent
review must inspect the saved artifacts and scientific claims separately;
calling the same implementation twice does not make the statistics independent.
