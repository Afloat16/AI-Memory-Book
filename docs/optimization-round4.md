# v0.3.2 round-four optimization: candidate and evidence

**Status: fixed C2 passes the registered formal performance gate with no resource exception; the fresh comparison is still running.** All 56,784 formal calls were retained and audited. The pooled geometric-mean p95 improvement is 10.1294%, only 0.1294 percentage points above the registered threshold. This page records the accepted result, its limits and the complete development history. No partial fresh-comparison scores or superiority claim are presented. [Formal review](round4-performance-review.md) · [Independent arithmetic audit](../benchmarks/reports/round4-performance-independent-audit.json)

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
| **C2 — `2d7b5e3`** | Corrected the demonstrated encoder-origin fallback gap and restored historical highlight SQL, retaining dictionary reuse and token/source work reduction. The removal is conservative; the record does not attribute every noisy C1 timing to that query. This unchanged candidate subsequently passed the registered formal gate, with the narrow margin and retained regression described below. [Selection record](../benchmarks/experiments/round4-candidate-selection.json), [formal review](round4-performance-review.md). |

## Completed Q2 compatibility

The [final independent audit](../benchmarks/reports/round4-compatibility-final/paired-audit.json) verifies **1,968 completed calls and 984 exact full non-latency payload pairs** on authored36 and historical Hotpot128, both tokenizers and token budgets 512/1024/2048. Recorded source, projection, scope, token and metadata error totals are zero.

For each cohort, the baseline built one semantic index and SQLite backups supplied identical vectors to both sources. The audit checks exact vector BLOBs and coordinates, model identity, originals, empty result caches, runtime/evaluator identities and every saved ledger event. It repeats no retrieval or inference.

An earlier helper omitted an explicit preparation cohort/fingerprint/count guard. Its correctly matched baseline-only 216 calls remain preserved. The fixed helper used new preparation and report paths; old receipts were not rewritten. The final audit validates saved hashes and flags, not omitted response bodies, and establishes compatibility on already scored data rather than new quality gains.

## Diagnostic limits and interruptions

The initial historical Hotpot first-use diagnostic was interrupted after **512 baseline calls**. The candidate stopped during ingestion with **zero attempted retrievals**; both second-round workers remained unstarted. The [interruption receipt](../benchmarks/reports/round4-development/final-hotpot-first-use-interruption.json) records lossless archives and the lost execution session. Its underlying cause is not established. The original attempt remains unchanged and supplies no paired performance evidence or OS-cold claim.

The separate [actual-MCP development helper](../scripts/round4_mcp_development.py) attempted its 512-call old-public diagnostic once. The real SDK initialized and listed tools, but this sandbox's procfs did not expose the live child for RSS collection. The resource guard stopped before any recall call. Its [zero-call failure receipt](../benchmarks/reports/round4-development/candidate-c2-mcp512-preservation.json) preserves all reports and the empty ledger. The guard is unchanged and this diagnostic was not repeated. The subsequently completed hosted formal matrix measures actual MCP with its required resource records; the failed local diagnostic supplies no speed evidence.

An independent readiness review found that C2 still needed its own full old-cohort differential and complete historical first-use check. The [prelaunch recovery record](../benchmarks/experiments/round4-prelaunch-recovery.json) registers those checks before new calls and before the final committed formal freeze. It explicitly preserves the first attempt and acknowledges that a separately identified complete first-use attempt repeats its baseline worker. All samples and negative cells remain separate; no attempt is selected for its speed. The single draft binding and fixed C2 source remain unchanged.

Both registered recovery checks completed. The [final-C2 full profile](../benchmarks/reports/round4-development/candidate-c2-manifest.json) contains 4,732 calls, and its [payload audit](../benchmarks/reports/round4-development/candidate-c2-profile-payload-audit.json) matches every complete output with the preserved baseline without replaying baseline queries. The separate [first-use recovery](../benchmarks/reports/round4-development/final-hotpot-first-use-recovery-manifest.json) contains all 2,048 calls and 1,024 matching complete payload pairs. Its character4000/token512/token1024/token2048 p95 changes are respectively −17.96%, −24.15%, −12.00% and −23.20%. These are historical development diagnostics on new worker connections with warm OS/tokenizer caches. They neither establish C2's public1015 character-tail result nor replace the formal matrix.

## Completed: formal performance

Hosted run **43361086255, attempt 1** completed all **56,784 calls**, **16 workers** and **12 pooled cohort/configuration cells**, using the registered source order **AB, BA, BA, AB**. Its result is preserved at [`1bd76f3b70eb60ead444f05c5a94148e9e384bba`](https://github.com/Afloat16/AI-Memory-Book/commit/1bd76f3b70eb60ead444f05c5a94148e9e384bba). The [original binding](../benchmarks/experiments/round4-performance-binding.json), [full saved report](../benchmarks/reports/round4-performance-43361086255-1/report.json.gz), [summary](../benchmarks/reports/round4-performance-43361086255-1/report.summary.json) and [completion record](../benchmarks/reports/round4-performance-43361086255-1/completion.json) preserve the exact candidate, baseline, evaluator, samples and execution identities.

**Every automatic acceptance gate passed; no gate or resource exception was used.** Independent arithmetic gives **10.1294257732%** geometric-mean pooled p95 improvement across the twelve cells. The margin over the required 10% is just **0.1294257732 percentage points**. All 28,392 paired observations have equal complete stable outputs and zero recorded invariant failures; all twelve pooled p50 values improve. The separate native-token and actual-MCP-token gates also pass. [Independent audit](../benchmarks/reports/round4-performance-independent-audit.json) · [Full review and all twelve cells](round4-performance-review.md)

The public-conversation cohort's six p95 results are shown together. A negative change means lower latency. Each cell contains 4,060 calls per source, pooled across four rounds; token configurations use `cl100k_base`. Native timings cover complete recall. MCP timings cover the actual official-SDK stdio call, including normal server cache writes and the returned result.

| Public configuration | v0.3.1 p95, ms | C2 p95, ms | p95 change |
|---|---:|---:|---:|
| Native, 4,000 characters | 2.361452 | 2.198754 | −6.8897% |
| Actual MCP, 4,000 characters | 3.467968 | 3.518062 | **+1.4445%** |
| Native, 512 tokens | 3.793969 | 3.070323 | −19.0736% |
| Native, 1,024 tokens | 3.199822 | 2.610729 | −18.4102% |
| Native, 2,048 tokens | 3.129763 | 2.560117 | −18.2009% |
| Actual MCP, 1,024 tokens | 4.357927 | 3.887177 | −10.8021% |

The **+1.4445% public MCP character p95 regression** is the only pooled latency increase and remains within the registered 5% p50/p95 limit. The largest of 28 registered resource mean increases is **+6.0231%**, for public MCP token-1024 startup through initialization; its mean rises from 345.683341 ms to 366.504056 ms. No resource mean exceeds the 10% review trigger, and the report's `resource_review` is empty. Startup, ingestion, RSS, storage, response-token costs and every adverse per-round result remain in the [full review](round4-performance-review.md) and [machine-readable audit](../benchmarks/reports/round4-performance-independent-audit.json).

The [local strict-ledger audit](../benchmarks/reports/round4-performance-local-audit.json) independently reruns the unchanged frozen verifier against the preserved workers, raw/compressed ledgers, full report and summary, with **zero retrieval calls**. The separate arithmetic audit recomputes percentiles and acceptance from saved observations. Both agree with the hosted result. These checks validate this measured run; they provide no statistical-significance or universal-speedup claim. The repeated old queries, one measured host, four resource samples per source/cohort and narrow aggregate margin limit generalization. They also establish no whole-product advantage over a comparator repository.

## Frozen fresh cohort: scoring in progress

The fresh comparison's exact sources, evaluator, dependencies, Q2 model and component assets were bound before selection. Freeze run **43362624147, attempt 1** published its [completion record](../benchmarks/reports/round4-freeze-43362624147-1/completion.json), [validation binding](../benchmarks/experiments/round4-validation-binding.json) and [256-ID manifest](../benchmarks/experiments/round4-hotpot256-manifest.json). The [independent selection audit](../benchmarks/reports/round4-freeze-independent-audit.json) confirms deterministic selection, **640 distinct historical exclusions** and **zero selected-ID overlap** with the earlier cohorts. The manifest was committed before scoring began.

Comparison run **43363060062, attempt 1** is still scoring the frozen matrix of **4,608 native calls and 4,608 component searches**. Final quality, cost and comparative conclusions await its complete verified assessment; partial stage scores are not interpreted here. This is another selection from the same public HotpotQA source, not another domain, and it becomes regression data after scoring. The final comparison must retain per-query gains and losses, all token budgets, native/read/adapter costs and the comparator repositories' advantages as well as Book's strengths.

Hosted controllers preserve execution claims, running intents, each completed worker and original attempt ledgers in Git. Incomplete attempts remain visible; no fastest-run selection or gate relaxation is authorized.
