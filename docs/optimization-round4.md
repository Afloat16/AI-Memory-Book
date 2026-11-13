# v0.3.2 round-four optimization: candidate and evidence

**Status: C2 source is fixed; formal performance acceptance and the new comparison are pending.** This page records implementation decisions and completed regression evidence. Development timings do not establish a release speedup or superiority over another repository.

The candidate is [`2d7b5e38839fb21724ad3beec6b6ebabbda45636`](https://github.com/Afloat16/AI-Memory-Book/commit/2d7b5e38839fb21724ad3beec6b6ebabbda45636), with runtime SHA256 `179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93`. The baseline is published v0.3.1 at [`7b7a5d7336b9350a128f5e0a888811b1b3015e68`](https://github.com/Afloat16/AI-Memory-Book/commit/7b7a5d7336b9350a128f5e0a888811b1b3015e68), runtime SHA256 `9c8118d26ae1a0eae4f31d9d4f44b2afa0ee5c54314bde5187deb27c473dee46`.

The original [registered plan](../benchmarks/experiments/round4-plan.json), [B addendum](../benchmarks/experiments/round4-development-addendum.json), [C addendum](../benchmarks/experiments/round4-counting-addendum.json) and [final candidate decision](../benchmarks/experiments/round4-candidate-selection.json) preserve the sequence of hypotheses and decisions. Their performance gates remain unchanged.

## What C2 changes

The implementation reduces repeated work in [token budgeting](../src/memory_book/token_budget.py) and [recall assembly](../src/memory_book/store.py).

1. **Delay unnecessary source parsing.** Original turns and source maps are still captured inside the existing SQLite read transaction. An affirmative comparison of complete mapped segments certifies pages whose projected units must match. Those pages are parsed only if supplemental evidence is requested. Uncertified maps still execute the historical eager projection checks and preserve their errors. Deferred computation uses captured immutable text and performs no database reads after the transaction.
2. **Narrow projection scans.** Bisection skips sorted source units whose starting offsets cannot belong to the mapped segment. The original end-boundary, containment and exact-text checks remain, including overlapping and nested units.
3. **Reuse accepted counts.** Assembly retains the exact count associated with the last accepted context. A later rejected candidate cannot replace it. The existing list-returning assembly interface remains available.
4. **Reuse certified token work within one call.** Accepted citation blocks are separated by exactly two LF characters, and the next block begins with `[`. For the two inspected tokenizer patterns, this is a verified tokenization boundary. Earlier blocks plus their separators can be counted once. A strict UTF-8 byte-length upper bound can prove that a new block fits; final `context_tokens` is still exact. This does not assume arbitrary token additivity or monotonic counts.
5. **Avoid a redundant metadata copy.** Recall reuses an already private candidate dictionary without changing candidate order, ranking inputs or public fields.

The counting certificate requires tiktoken 0.12.0, the exact `cl100k_base` or `o200k_base` pattern, ordinary counter/encoder methods and valid text boundaries. C2 additionally checks method origin before the first trusted-method capture, including wrappers installed before initialization. Unsupported versions, custom counters, unknown origins, non-citation headers and surrogate cases retain the complete-context fallback and historical prefix-count behavior. A late fallback rebuilds the complete supplemental prefix.

**C2 removes both experimental SQL/cache specializations.** The connection-local indexed-body feature cache is absent. Highlight retrieval uses the original point whitelist for every rowid span; the proposed bounded highlight scan is not enabled. The final decision supersedes the C addendum's tentative intention to retain that scan.

## Preserved behavior and correctness coverage

Lexical normalization, indexed text, global BM25, exact/stem routes, scope filtering before LIMIT, deterministic ties, candidate limits, novelty and temporal rules remain unchanged. Source coordinates, first-fit packing order, character/token budgets, literal special-token strings and code-fence handling retain their existing contracts. The revision adds no schema migration, model, runtime dependency, cross-call query/result cache or retained source-feature cache.

Q2's model, persisted vectors and fusion rules are unchanged. There is no quality candidate; earlier rejected novelty and project-local-statistics experiments remain closed. This round targets exact-output efficiency.

Fresh [source/projection fixtures](../tests/test_round4_token_work.py), [sealed-count fixtures](../tests/test_round4_sealed_counts.py) and [highlight fixtures](../tests/test_round4_highlight.py) cover budget edges, nonmonotonic counts, later rejection, source corruption, external writers, Unicode, surrogate errors, custom encoders and restored SQL behavior. The [independent boundary check](../benchmarks/reports/round4-development/sealed-boundary-independent-proof.json) verifies complete token-ID equality on 9,834 artificial pairs per encoding. Its conclusion concerns the specific certified boundary.

## Development decisions: A, B, C1 and C2

Each profile used 4,732 old-data calls. The separate native diagnostics used 128 deterministic old queries from each of synthetic61 and public1015, four configurations, two balanced rounds and both implementations: 4,096 calls, or 2,048 complete-payload pairs per candidate. Profiler timings include instrumentation overhead. These smaller diagnostics do not substitute for the formal matrix.

| Candidate | Decision and retained evidence |
|---|---|
| **A — `cf712787`** | Lazy projection, bisection and accepted-count reuse preserved all compared payloads. Public native token p95 gains were approximately 4–7%, insufficient to justify the formal speed claim. [Paired manifest](../benchmarks/reports/round4-development/candidate-a-paired-manifest.json). |
| **B — `ec45162`** | Added a revision-scoped feature cache bounded to 256 entries and 2 MiB, dictionary reuse and the highlight specialization. Payloads matched, but public token512 p95 regressed **11.82%** in development. The cache was rejected; its original source, fixtures and negative samples remain archived. [Decision/archive](../benchmarks/experiments/round4-candidate-b/README.md), [paired manifest](../benchmarks/reports/round4-development/candidate-b-paired-manifest.json). |
| **C1 — `bb17c8c`** | Removed the cache and added certified counting. All profile and paired payloads matched. The eight native development cells showed **16.67%** geometric-mean p95 improvement, alongside **20.49% worse public character p95** and only **5.02% public token1024 p95 improvement**. All adverse cells remain. [Paired manifest](../benchmarks/reports/round4-development/candidate-c-paired-manifest.json). |
| **C2 — `2d7b5e3`** | Corrected the demonstrated encoder-origin fallback gap and restored historical highlight SQL, retaining dictionary reuse and token/source work reduction. The removal is conservative; the record does not attribute every noisy C1 timing to that query. C2 is the candidate for formal evaluation, without a formal speed verdict yet. [Selection record](../benchmarks/experiments/round4-candidate-selection.json). |

## Completed Q2 compatibility

The [final independent audit](../benchmarks/reports/round4-compatibility-final/paired-audit.json) verifies **1,968 completed calls and 984 exact full non-latency payload pairs** on authored36 and historical Hotpot128, both tokenizers and token budgets 512/1024/2048. Recorded source, projection, scope, token and metadata error totals are zero.

For each cohort, the baseline built one semantic index and SQLite backups supplied identical vectors to both sources. The audit checks exact vector BLOBs and coordinates, model identity, originals, empty result caches, runtime/evaluator identities and every saved ledger event. It repeats no retrieval or inference.

An earlier helper omitted an explicit preparation cohort/fingerprint/count guard. Its correctly matched baseline-only 216 calls remain preserved. The fixed helper used new preparation and report paths; old receipts were not rewritten. The final audit validates saved hashes and flags, not omitted response bodies, and establishes compatibility on already scored data rather than new quality gains.

## Diagnostic limits and interruptions

The initial historical Hotpot first-use diagnostic was interrupted after **512 baseline calls**. The candidate stopped during ingestion with **zero attempted retrievals**; both second-round workers remained unstarted. The [interruption receipt](../benchmarks/reports/round4-development/final-hotpot-first-use-interruption.json) records lossless archives and the lost execution session. Its underlying cause is not established. The original attempt remains unchanged and supplies no paired performance evidence or OS-cold claim.

The separate [actual-MCP development helper](../scripts/round4_mcp_development.py) attempted its 512-call old-public diagnostic once. The real SDK initialized and listed tools, but this sandbox's procfs did not expose the live child for RSS collection. The resource guard stopped before any recall call. Its [zero-call failure receipt](../benchmarks/reports/round4-development/candidate-c2-mcp512-preservation.json) preserves all reports and the empty ledger. The guard is unchanged and this diagnostic will not be repeated; actual MCP remains a required part of the hosted formal matrix.

An independent readiness review found that C2 still needed its own full old-cohort differential and complete historical first-use check. The [prelaunch recovery record](../benchmarks/experiments/round4-prelaunch-recovery.json) registers those checks before new calls and before the final committed formal freeze. It explicitly preserves the first attempt and acknowledges that a separately identified complete first-use attempt repeats its baseline worker. All samples and negative cells remain separate; no attempt is selected for its speed. The single draft binding and fixed C2 source remain unchanged.

Both registered recovery checks completed. The [final-C2 full profile](../benchmarks/reports/round4-development/candidate-c2-manifest.json) contains 4,732 calls, and its [payload audit](../benchmarks/reports/round4-development/candidate-c2-profile-payload-audit.json) matches every complete output with the preserved baseline without replaying baseline queries. The separate [first-use recovery](../benchmarks/reports/round4-development/final-hotpot-first-use-recovery-manifest.json) contains all 2,048 calls and 1,024 matching complete payload pairs. Its character4000/token512/token1024/token2048 p95 changes are respectively −17.96%, −24.15%, −12.00% and −23.20%. These are historical development diagnostics on new worker connections with warm OS/tokenizer caches. They neither establish C2's public1015 character-tail result nor replace the formal matrix.

## Pending: formal performance and new comparison

**Formal performance: pending.** The registered hosted run has 56,784 calls, four ABBA rounds and twelve cohort/configuration cells. Acceptance requires complete-payload/invariant equality, at least 10% overall geometric-mean p95 improvement, 15% in at least one public native token cell, 10% for actual public MCP token1024, and no pooled p50/p95 regression above 5%. Resource mean increases above 10% require explicit assessment and independent review. Final documentation must link the binding, complete raw/summary evidence, audit, all negative cells and any resource decision.

**New comparison: selection and results pending.** Exact sources, evaluator, dependencies, model and component assets must be committed before the deterministic 256-ID selection, excluding all 640 historical IDs. The planned matrix includes 4,608 native calls and 4,608 component searches. This is another selection from the same public source, not another domain; it becomes regression data after scoring. Publish quality, actual costs and weaknesses together, without inferring universal superiority from old-data timing.

Hosted controllers preserve execution claims, running intents, each completed worker and original attempt ledgers in Git. Incomplete attempts remain visible; no fastest-run selection or gate relaxation is authorized.
