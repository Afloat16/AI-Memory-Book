# Why the three MiniLM configurations have equal scores

The Mem0, Chroma and LangGraph rows in the frozen v0.6.0 comparison have the
same aggregate quality and character counts. **Their complete native responses
and cited contexts are not all identical.** Reanalysis of the saved records
shows exactly where they differ and why those differences do not change the
published metrics.

This is an audit of existing evidence, performed on 2026-11-16. It is not a new
retrieval run, a new benchmark, or third-party certification. The original
dataset, adapters, model, queries, packer, scores and archived outputs remain
unchanged. [Executable audit](../scripts/audit_shared_minilm.py) ·
[Machine-readable summary](../benchmarks/reports/v0.6.0-engineering/reanalysis/shared-minilm-audit.json) ·
[Per-case differences, gzip JSONL](../benchmarks/reports/v0.6.0-engineering/reanalysis/shared-minilm-audit.cases.jsonl.gz).

## What was checked

The audit revalidates the complete seven-backend matrix: **560 query/backend
records, 1,680 saved native-call samples and 1,120 packed outputs**. The existing
source-mapping auditor checks the visible source pages, project identities,
native-to-original mappings, three-repeat stability, character budgets,
reconstructed packed responses, recomputed scores, aggregate/category tables
and timing summaries. It passes **64,900 checks with zero failures**. This count
describes internal consistency checks, not independent quality observations.

Six execution files, including the workload, scorer, common packer, runner,
adapters and dependency lock, match their SHA-256 identities in the frozen
execution binding. The new report records its input and auditor hashes. The
pair comparisons below use the first repetition; all three repetitions of each
backend were separately checked for stability.

## Equality at different output levels

Each denominator is the same **80 questions**. No percentage treats the three
repetitions or two budgets as extra independent questions.

| Pair | Same ordered candidate IDs | Same candidate ID set | Same ordered page-body text | Same cited context, 1200 chars | Same cited context, 2400 chars |
|---|---:|---:|---:|---:|---:|
| Chroma / LangGraph | 33/80 | 39/80 | 80/80 | 59/80 | 33/80 |
| Chroma / Mem0 | 39/80 | 39/80 | 80/80 | 65/80 | 39/80 |
| LangGraph / Mem0 | 67/80 | 72/80 | 80/80 | 72/80 | 67/80 |

For every pair, **all 80 per-question score objects and context lengths agree
at each budget**, including evidence ranks and fixed-policy outcomes. The
body-only comparison excludes source identities and citation headings; the
cited-context comparison includes them. Neither comparison says the complete
native payloads are interchangeable: those have different schemas, native IDs
or scores and are unequal in all 80 pairwise comparisons.

At 1200 characters, complete packed JSON agrees in 33, 39 and 67 cases,
respectively, even though more delivered contexts agree. The remaining JSON
differences can be in `omitted_for_budget`: different candidate IDs were skipped
without changing the delivered context. At 2400 characters, the corresponding
complete-response equality counts are also 33, 39 and 67.

### Why even the mean character counts match

The workload contains maintenance notes repeated across chronological
checkpoints. Copies have **identical body text but different session IDs,
timestamps and page IDs**. The source identities are meaningful and remain in
the archive. Their citation headers happen to have the same character length
in this synthetic dataset.

Across Chroma/LangGraph, Chroma/Mem0 and LangGraph/Mem0, there are respectively
**128, 102 and 35 differing candidate-rank positions**. Every one of these
positions substitutes a maintenance record with **the same body text and the
same framed character length**. These are pairwise position counts, not unique
questions or unique source pages. The audit records both source references for
every substitution.

Consequently, the three configurations deliver the same sequence of page-body
strings for each question. The common packer sees the same block costs in the
same positions, so the same positions fit each budget. Different provenance
can change the cited context without changing its length. The specified target
evidence and fixed-policy outcomes also remain the same, as verified by
rescoring every response. The equal means are therefore exact consequences of
these per-question counts, not just a one-decimal rounding coincidence.

For example, `m3:attention-batch:replacement` retrieves five maintenance notes.
At one position Chroma returns `maintenance-1-1` while LangGraph returns
`maintenance-3-1`. Both bodies are 371 characters. Each packed context is 2318
characters at the 2400-character cap, and neither contains the required
replacement-decision span. The complete cited contexts differ because their
source references differ.

**This exposes a limitation of the development workload:** repeated template
bodies and fixed evidence labels do not distinguish these source substitutions
in the headline quality metrics. The table is useful for diagnosing this
specific supplied-page task; it does not establish equivalence of the products,
their ranking behavior, or their performance on diverse real histories.

At the final checkpoint, the 144 visible pages contain 44 distinct body strings
across projects. Of these pages, 96 are maintenance records drawn from only
eight distinct body strings. Within one project, an identical maintenance body
can occur six times. The audit reports these counts at every checkpoint.

## Shared configuration and separate execution

The [registered protocol](../benchmarks/competitors/memory-systems-plan.md)
and [worker implementation](../benchmarks/competitors/memory_systems_worker.py)
show three distinct API paths:

| Configuration | Actual interface | Connection to the other rows |
|---|---|---|
| Chroma 1.5.9 | Local `PersistentClient`, collection `add` and `query` with project metadata filtering | Official ONNX MiniLM embedding; native vector search |
| LangGraph Store, checkpoint 4.3.2 distribution | `InMemoryStore.put` and `search`; text-only semantic index; per-project namespace | The same ONNX MiniLM representation, with a separate in-memory store |
| Mem0 2.2.1 | `Memory.add(infer=False)` and `Memory.search`; project supplied as `user_id` | The same MiniLM representation **and Chroma as the vector-store provider** |

The runner creates a separate worker/state directory for each Python backend
at every checkpoint and calls its own search method for every repetition.
Results are mapped back through backend-specific native fields. No shared
result cache or cross-backend result assignment was found in those code paths.
This source inspection and the retained native traces support separate API
execution; they do not prove the absence of every possible implementation bug.

All three receive the same original page bodies, unchanged questions and
project scope. They share Chroma's real local `ONNXMiniLM_L6_V2` implementation
and its native 256-token truncation. The requested output limit is five, but
this does **not** mean identical internal search procedures. For example,
[Mem0 2.2.1's native search](https://github.com/mem0ai/mem0/blob/v2.2.1/mem0/memory/main.py)
retrieves a larger internal candidate pool before its final top-k selection;
its raw-memory configuration here does not exercise fact extraction, graph
memory or reranking.

The [common packer](../benchmarks/engineering_components.py) uses the returned
IDs and order to retrieve original bodies from the shared document mapping.
It applies the same citation format and whole-block budget rule, without
reading queries, answer labels or native similarity scores. Thus “mean packed
characters” measures the common packing protocol, not a product's native
context injection, token consumption or model cost.

The frozen direct-Chroma configuration records cosine distance, while the
LangGraph implementation uses cosine similarity. The frozen trace does not
record Mem0's internal collection metric or the original embedding vectors.
This audit does not fill those gaps with inferred measurements or claim
bit-for-bit equality of embeddings. A shared model alone would not guarantee
identical candidates or scores on another dataset.

## How the README presents the evidence

The two headline tables now show **one explicitly related MiniLM group**,
listing all three configurations in the footnote. Each interface's original
individual row remains in the [complete report](../benchmarks/reports/v0.6.0-engineering/hosted/memory-systems/report.json).
The quality numbers have not been altered. This avoids counting three
correlated configurations as three independent demonstrations of an advantage.

The tables identify an authored development workload before presenting results.
The eight missing-evidence questions, 1200-character failures, native-versus-
common-packing distinction and lack of a held-out coding experiment remain
visible. Repetition of synthetic maintenance text is now an explicit
limitation, rather than being hidden behind an explanation about the model.

## Reproduce the audit

From a checkout containing the frozen report directory, install the repository
as documented for development, then run:

```bash
python scripts/audit_shared_minilm.py --output .artifacts/shared-minilm-audit.json
```

The script accepts the committed gzip traces, needs no external model or
memory-product dependencies, and performs no retrieval. A failure returns a
nonzero exit code and remains in the written report. Comparison counts are
computed from the validated records; the script does not require them to match
hard-coded expectations. The output timestamp and output-dependent paths can change on rerun. Other
evidence fields should match when the inputs and audit code are unchanged. A
companion `*.cases.jsonl.gz` file retains all 240 pair/question comparisons;
its compressed and uncompressed hashes are in the summary.
