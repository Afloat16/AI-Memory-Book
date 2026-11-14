# v0.3.3 optimization and release checkpoint

Status: C7 stdout scheduling source is frozen at `d0c84cbfc9bad440ad447d41e211d070ef5b2cae` after directed correctness and independent review; no C7 performance measurement has begun. C6 completed its sole formal run [43557136276](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43557136276), but remains numerically rejected: aggregate p95 improves 14.919173%, the best public native token setting improves 16.286785%, and actual public MCP token1024 improves only 5.798911%, below the unchanged 10% gate. All 56,784 calls and 28,392 complete output pairs are valid; no resource-review threshold is triggered. C3 and C5 remain rejected, C4 remains development-only, and no v0.3.3 runtime is approved.

## Source and purpose

Continue from main `de6e2652572c4867cda2aac5637a4a6630638c7e` and compare against the published v0.3.2 tag at `692fb959ddf8934c5f516ba3d74ceb4385a2fa82`. The user requested measurable improvement, frequent remote Git checkpoints, a promptly reviewable version, and a new non-prerelease publication.

## Acceptance fixed before candidate measurement

- Preserve complete retrieval output apart from timing fields; validate evidence, source spans, scope, budgets and actual MCP transport.
- Reuse the historical synthetic61 and public1015 performance matrix, six configurations and four balanced AB/BA/BA/AB rounds (56,784 total calls).
- Require at least 10% pooled p95 geometric-mean improvement, at least one 15% public native token p95 gain, at least 10% public MCP token1024 p95 gain, and no cell with more than 5% pooled p50/p95 regression. Resource mean increases above 10% require explicit evidence review; retain all resource measurements and negative results.
- Keep exploratory diagnostics separate from the single frozen formal attempt. Publish the candidate/evaluator/input identities before the formal run. Preserve interrupted attempts; never select the fastest repeated run.
- Reuse previous competitor findings only with their original version, corpus and timing-boundary labels. Do not claim across-the-board superiority: ai-memory and billion-context currently lead some recall/completeness measures, and billion-context has a faster measured search component. A new same-output Book speed result is not a new competitor benchmark.
- Require the exact release commit to pass all nine existing CI jobs, verify wheel/sdist contents and hashes, publish seven expected assets, and exercise the public installer.
- v0.3.2 and earlier releases are published GitHub prereleases. v0.3.3 is intended to be a normal, non-draft, non-prerelease GitHub release; this does not itself certify universal production fitness.

## Work ownership and interruption recovery

Core performance implementation, independent benchmark validation, and release-policy review run separately. Commit small completed changes to `optimization/round5-v0.3.3`; update this checkpoint with source SHAs and saved results as they become available. Main and the release tag advance only after acceptance. Code, benchmark receipts and release notes belong in this Git repository, with no dependency on transient conversation blobs.

Current next steps: bind the reviewed C7 source and run the one complete native development comparison followed by the one complete actual-MCP development comparison on a compatible isolated Linux runner. The local unchanged resource selector cannot enumerate its live child, so the zero-product-call preflight failure is retained and mandatory RSS is not waived. The same original formal gates and a new source/evaluator binding remain required. Only a passing final-source result can approve the runtime and advance main. The final release commit must then pass all nine CI jobs and package checks before a normal v0.3.3 release and public-installer verification. Do not rerun an unchanged binding for a more favorable sample.

## Candidate A checkpoint

The implementation removes rank/score maps and duplicate row conversions when exact and stem routes already return the same ordered IDs. It also reuses exact accepted-block counts when sealing a token-budget prefix, recalculating only a certified ASCII punctuation/whitespace suffix. Existing tiktoken pattern/version/method-origin guards, UTF-8 handling and complete-count fallbacks remain. No schema, dependency, ranking rule, result-cache policy or source evidence is changed.

The candidate is under development validation; no speed claim is accepted at this checkpoint. Dedicated and prior correctness fixtures passed 62 tests. The formal controller retains all six configurations, all 16 workers and every started/finished call, and saves a remote Git checkpoint before and after each worker. Gzip contains the original complete attempt ledger bytes; offline auditing accepts those retained ledgers without replaying recall.

Release-policy checkpoint: `65bcfc1182216ed4fffac241716ee0fbb314280a` prepares version 0.3.3 and an explicitly normal GitHub release. Publication is blocked until the accepted runtime hash is registered and all exact-commit CI/package checks pass.

## Candidate A development result: not accepted for release

Checkpoint `df5c073fc0ad0bbcc0440f569363247ec570bd76` retains candidate A (runtime SHA256 `a46983c7c4a4c58e92d6895a677efcc565314b3645b49fa687ad541ffba86dfb`). Its two balanced native diagnostic rounds ran 4,096 calls; all 2,048 complete non-timing payload pairs matched. All observations, including regressions, are retained in [the raw diagnostic](../benchmarks/reports/round5-development/candidate-a-paired-manifest.json) and [its summary](../benchmarks/reports/round5-development/candidate-a-paired-summary.json).

The apparent aggregate p95 improvement is not accepted as sufficient evidence: one baseline public token1024 tail is unusually high, while public character p95 is 3.09% worse, public token2048 is 1.24% worse and synthetic token512 is 14.99% worse. Public token512 improves only 9.66%. No formal run has started, and these development results do not support a release speed claim. Further profiling focuses on reducing actual SQL/source processing rather than selecting faster noisy measurements. The independent [token-boundary audit](../benchmarks/reports/round5-sealing-independent-audit.json) preserves its 11,568 pairs and 23,136 full token-ID equalities.

## Candidate B: reduce provably unused source processing

Candidate B retains A and adds a stable citation-header token lower bound. When the already certified exact prefix plus the stable header prefix cannot fit the budget, it skips supplemental span parsing and term extraction. Existing source-map checks still occur in the original SQLite snapshot. Headers outside the strict ASCII-alphanumeric-plus-LF boundary keep the old path. Candidate metadata is consumed in one ordered pass, and each distinct directory overlap is calculated once per query.

Runtime SHA256 at this checkpoint: `a31f988c7ce42ec3e8e13cb07e69e4027f8e7b913cca9242b86a5071ef0c582d`. Dedicated and historical source/token/fusion tests pass; this checkpoint has no accepted speed result. A pure-text cache was explored only by a read-only reuse simulation and rejected: 512 entries under a 2 MiB cap would hit only about 7.1% of supplemental term texts, too little to justify the retained memory. No such cache was implemented.

Candidate B completed a second 4,096-call native diagnostic with all 2,048 complete-output pairs equal. Its aggregate p95 reduction of 6.48% does not establish the registered formal gate. Public character p95 increased 4.99%; public token512 and token1024 improved only 3.91% and 1.89%. All [raw B observations](../benchmarks/reports/round5-development/candidate-b-paired-manifest.json), [summary](../benchmarks/reports/round5-development/candidate-b-paired-summary.json) and the [B-bound boundary audit](../benchmarks/reports/round5-candidate-b-boundary-audit.json) remain available. Neither A nor B has been represented as an accepted release.

## Candidate C registration

The [index addendum](../benchmarks/experiments/round5-index-addendum.json), committed as `8b4ab127c3bab924ed3072cff8b857c96b752230` before candidate C timing, permits a small additive covering index for candidate metadata. It retains all source records, scopes, ordering, global BM25 and numeric/resource gates. Its purpose is to avoid reading wide content rows for each FTS hit. Development, migration, storage and ingestion costs must be reported before release acceptance.

A separate [SQLite page-cache diagnostic](../benchmarks/reports/round5-development/sqlite-cache-probe-1/README.md) retained 6,144 calls and all 24 workers. Four MiB showed small gains with about 2.1 MiB extra RSS; eight MiB increased public character p95 by 5.37%. These settings alone did not establish the formal gate. Candidate C retains the original cache size.

Candidate C's fixed 4,096-call diagnostic matched all 2,048 full-output pairs, and all eight pooled native p50/p95 cells improved. Aggregate p95 improved 11.05%; public char4000/token512/token1024/token2048 changes were -12.63%/-12.97%/-9.16%/-4.04%. These development results still do not establish the separate public native-token or actual-MCP formal gates. [Raw observations](../benchmarks/reports/round5-development/candidate-c-paired-manifest.json) and [summary](../benchmarks/reports/round5-development/candidate-c-paired-summary.json) retain every round. Apply [the archived C patch](../benchmarks/experiments/round5-candidate-c.patch) to `c1b1ed437b9c7b670c2a96baec77cf187dfb12ee` to reconstruct runtime SHA256 `753ce96a005ef7378622452a9d4ee233cadb5db99a41fe36b7b4a91db243a3a0`.

C2 retains the index but preserves the previous selective query-planner options for chapter/session scopes unless an existing project envelope already forces FTS outermost. Fixed-rowid metadata reads use the covering index. The correction does not change any query route in the old native development matrix; it is covered by explicit chapter-only/session-only and old-schema fixtures and will be measured in the final frozen formal source. C2 runtime SHA256 is `00c927df480b923621643e07351a3dbd0b275b3f1f13d87af491fa15365573a6`.

## Final C3 source freeze

The [cache addendum](../benchmarks/experiments/round5-cache-addendum.json) was committed at `f3e41d0d6042e8f35defa373d02abcf2bf576e06` before final formal measurement. C3 sets a 4,096 KiB connection-local SQLite pager target while preserving the separate result-cache API and the previous database format. The smaller metadata index may already remove some cache pressure, so independent cache-probe gains are not added to C gains.

Final runtime SHA256: `7a927601b5ce710059d5a2640b3642c58a2bd4985d9ccdc48f69159938ee3623`. No further runtime edits are planned. The final source will be bound to the published v0.3.2 source, exact evaluator bytes and fixed dependencies before the one registered 56,784-call hosted comparison. Formal acceptance remains pending at this checkpoint.

### Existing-archive upgrade cost

The final C3 [one-sample upgrade observation](../benchmarks/reports/round5-development/final-index-upgrade.json) preserves old logical content, revision and schema in both copied archives. First open including index construction took 5.419 ms versus 0.910 ms on synthetic61 and 4.502 ms versus 0.844 ms on public1015; open plus close/checkpoint took 9.495/7.791 ms versus 1.000/0.930 ms. The added index occupied 200,704/151,552 bytes. Reused free pages meant zero observed file growth in these copies, not zero storage cost. These warm-OS single observations are descriptive; formal workers separately measure repeated startup, ingestion and RSS. [Interpretation and reproduction](../benchmarks/reports/round5-development/final-index-upgrade-review.json).

## Completed historical Hotpot256 compatibility

Final C3 matches all 2,304 saved v0.3.2 complete output hashes on the already scored round-four 256-question set: 1,536 native calls (both tokenizers, 512/1,024/2,048 token caps) and 768 component-ranker calls (100,000 characters, three repeats). There are zero mismatches/errors. Original source, index and canonical-document projections remain unchanged and result caches remain empty. The complete report, all 4,608 start/finish events and source identities are retained in [the summary](../benchmarks/reports/round5-hotpot-regression.summary.json) and its linked gzip files. Only latency_ms is excluded from response equality.

This supports retention of the historical default Book quality results on these same questions; it is not new-domain generalization, a new competitor speed comparison or a quality gain. The old comparison's third-party measurements and competitors' strengths remain separately labelled.

## C3 complete formal result: not accepted for release

The sole C3 run [43547085915](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43547085915) completed all 56,784 calls. All 28,392 complete non-timing output pairs and recorded invariants pass. Aggregate pooled p95 improves **10.499586%**, and every pooled p50/p95 cell improves. However, the best public native token gain is **10.482574%**, below its fixed 15% threshold; actual public MCP token1024 improves **5.146962%**, below its fixed 10% threshold. The numeric gate and release acceptance are therefore **false**. Resource review is not triggered.

The complete original result is `e0c30deb7cdae18bb19c83534646630dfb3f673b`, merged without replacing any sample at `1cf1fde744a1f65a662b4350f88114d9e7140e70`. [Full raw evidence](../benchmarks/reports/round5-performance-43547085915-1/report.json.gz), [summary](../benchmarks/reports/round5-performance-43547085915-1/report.summary.json) and [completion](../benchmarks/reports/round5-performance-43547085915-1/completion.json) retain the measurement step's failure and the saved-result audit's success. This is a completed numerical rejection, not missing data.

C3 will not be rerun to select a faster sample. Further work requires a materially changed candidate, a separate preregistered continuation, a new source/evaluator binding, the same strict numerical gates and explicit retention of this failed result.

## C4 continuation registered

[The C4 addendum](../benchmarks/experiments/round5-c4-addendum.json) was committed before implementation at `3b8035268cc8ceae2e7e1a19db346cc5fdff37a3`. It permits deduplicated in-snapshot directory metadata and a strict existing-score upper bound, with full invalid-metadata fallbacks and original candidate counts. Semantic/coverage/custom-factory paths stay unpruned. [C3 profiling and work-count diagnosis](../benchmarks/reports/round5-development/c4-preregistration/README.md) motivate this substantive change; they are not new performance acceptance. The complete original C3 rejection above is retained.

## C4 implementation and complete development result

Source `0141adf1dde6cd69cf96d8eea23f4b6ebab36477` implements shared-directory metadata and the exact score upper bound; runtime SHA256 is `1c7c644c5187332e6fb5034fef0e232b5c1ae1e5f352b53fea90f7fd8acc4fb3`. Dedicated correctness and optional-token environment fixtures pass, and all nine CI jobs pass on evaluator commit `c92d4049b3d488fa7ef06792198075b91592644e` ([run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43549534451)). The independent source review found no correctness blocker.

The [fixed full-cohort development run](../benchmarks/reports/round5-development/candidate-c4-full/README.md) completed all 18,928 calls and 9,464 matching full-output pairs, with every saved source/index/revision/cache/count invariant passing. Native aggregate p95 improves 11.3339%, but public token512/token1024 improve only 12.7253%/8.8411%, and public token2048 p95 regresses 1.3269%. All raw worker records, the complete aggregate and every per-round cell are retained. This is development evidence, not formal acceptance.

C4's separately prepared evaluator, workflow and independent auditor are preserved as **unused preparation**. No C4 formal binding or execution was created. The limited public margin does not justify representing C4 as accepted. Further investigation will preserve this source and all adverse results; changing cache policy requires an explicit new continuation rather than silently extending C4's no-new-cache registration.


## C5 registration: bounded exact token-count reuse

The [C5 addendum](../benchmarks/experiments/round5-c5-addendum.json) and [full native development plan](../benchmarks/experiments/round5-c5-development-plan.json) were saved remotely at `7753e7566b1cd57bf5bcaad02d15ce1fa970f839` before implementation or C5 timing. They retain all original numerical gates and every failed C3/C4 observation. C4 formal files remain unused preparation; there is no C4 binding or formal timing run.

One observational trace of unchanged C4 counts on all 1,015 public questions matched every saved full payload. Replaying only that saved trace with conservative Unicode size accounting gave 63.98% eligible count reuse at 2,048 entries / 2 MiB, versus 64.74% at 4,096 entries / 4 MiB. The smaller setting is fixed for C5. Instrumented count work is not an end-to-end speed gain; no C5 latency result exists at this checkpoint. The [trace, all capacity alternatives and size-accounting correction](../benchmarks/reports/round5-development/c5-preregistration/receipt.json) remain available.

C5 explicitly extends C4's feature-cache restriction: one lazy per-connection memo may retain the exact count of a complete native text string under certified, unchanged encoder objects. Both tokenizers share the 2,048-entry / 2 MiB retained-text limits. The text budget excludes container/key/value/encoder overhead; actual process RSS remains part of formal acceptance. Full source retrieval, corruption checks, assembly and query-result cache behavior are preserved. Native memo diagnostics are observed outside timers; actual SDK MCP command and wire format stay unchanged. New connections start empty, and all first calls remain in the measurements.


## C5 source freeze and full native development result

Final C5 source is `8dc6604fa32df18d53286110b215fc6657243656`, runtime SHA256 `6af876ef5ddc851f4fff56ba3dc4f20e76b2cfc9f5e31d0cc8d1a0ec20e954be`. Its [72 directed checks](../benchmarks/reports/round5-c5-correctness.json), [independent static review](../benchmarks/reports/round5-c5-source-review.json) and [nine source CI jobs](../benchmarks/reports/round5-c5-source-ci.json) pass. The overlapping dependency-free suite ran 28 cases with 12 tokenizer-only skips; these are not added to the 72 checks. Static review fixed custom encoder private-state fallback, deleted pattern fallback, and original methods rebound to a different receiver before timing.

The sole registered [full native development invocation](../benchmarks/reports/round5-development/candidate-c5-full/summary.json) retained all 18,928 calls and 9,464 complete payload pairs, with zero mismatches or invariant failures. All eight pooled p50/p95/mean values improve; pooled p95 geometric-mean improvement is 13.429705%. Public native token512/1024/2048 p95 improves 11.141053% / 14.144746% / 11.364435%. The best public value is still 0.855254 percentage points below the formal 15% gate. One per-round adverse value remains: public char4000 round 1 p95 increases 1.591165%.

These are development observations, not a passed performance gate. They support proceeding to the already registered single hosted four-round comparison, which still must pass every unchanged threshold, including actual SDK MCP and resource review. No timing is repeated on this source to seek a favorable sample. All candidate memo snapshots respect the empty initial state, character-only nonallocation, native configuration continuity and fixed capacity.


### C5 final-source historical compatibility

The [C5 Hotpot256 compatibility check](../benchmarks/reports/round5-c5-hotpot-regression.summary.json) completes once on frozen source `8dc6604`: all 1,536 native and 768 component complete output hashes match saved v0.3.2 observations. There are zero errors/differences and all 4,608 original start/finish records align. The helper, dataset, references, source/runtime and unchanged source/index/document projections are verified. This is final-source historical compatibility, not a new quality or timing result; it does not replace the pending formal speed verdict.


## C5 complete formal result: actual MCP gate not met

The sole C5 hosted run [43552372788, attempt 1](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43552372788) completed all **56,784 calls** and all **28,392 matching complete non-timing payload pairs**. The aggregate pooled p95 improvement is **15.220791%**; the best public native token result is **15.422173%** (token512). These two gates pass. Public actual-SDK MCP token1024 improves **6.673181%**, below the unchanged **10%** gate, so `numeric_gate_passed` and `accepted` remain **false**. Every pooled p50, p95 and mean improves, and no resource-review threshold is triggered. These facts do not override the failed MCP gate.

All 54 result files are retained from final result commit `3982ceab2bdce0e9a189135ce261445a3a38d779`, losslessly merged at `d40ac2c00b1b00653ca6b92db3c37f62e8317429`. Their 53-file completion inventory and every Git blob match the downloaded files. The full report, every original worker, all start/finish ledgers, resource values and native memo snapshots remain in [the result directory](../benchmarks/reports/round5-c5-performance-43552372788-1/). The measurement step fails its numerical gate while the saved-row audit succeeds; this is a complete rejection, not an interrupted or missing run.

[The independent rejection review](round5-c5-performance-review.md) and [read-only independent audit](../benchmarks/reports/round5-c5-performance-independent-audit.json) retain all pooled/per-round cells, adverse samples and costs. C5 is not rerun for a more favorable sample. Any continuation requires materially changed product work, a new registered source/evaluator binding, and the same 10% / 15% / 10% gains, 5% pooled-regression limit and resource-review policy. No release tag or approved v0.3.3 runtime exists at this checkpoint.


## C6 preregistration: reduce repeated source work in one snapshot

The [C6 addendum](../benchmarks/experiments/round5-c6-addendum.json) and [full development plan](../benchmarks/experiments/round5-c6-development-plan.json) were saved at `099cbaf427c28351d71f3995fd0ff42f9c881b38` before C6 product edits or timing. They retain the complete C3/C5 formal rejections, the C4/C5 development evidence and every original numerical/resource gate.

A [single non-timing observation of unchanged C5](../benchmarks/reports/round5-development/c6-preregistration/README.md) completed all 1,015 original public round-0 SDK calls with every full native/MCP/envelope hash and invariant matching. One connection opened and closed on the same thread. Its 20,464 application SQL executions used only 97 distinct original templates: every registered 128/256/512/1,024-entry LRU model had zero repeated misses. This rejects enlarging the statement cache; no cache-size or IN-shape change is selected. The complete raw trace and every modeled capacity are retained, along with the earlier zero-call diagnostic harness failure and its separately registered repair.

The trace also records 4,289 original-turn queries and 5,073 duplicate source-reference JSON loads (3,542,467 input bytes repeated). C6 may batch the exact requested `(session_pk, ordinal)` pairs inside the existing snapshot and reuse already parsed references within that same recall. Native normal-path batches are capped at 400 pairs / 800 parameters and guarded by actual SQLite limits. Single-session, unknown-limit, restrictive-limit, malformed and custom paths retain the original loop. Parsed references never persist across calls or appear as extra output/row metadata; ordinary identity and unchanged raw-object checks guard reuse. All original source-map validation and clipping arithmetic remain required.

These counts explain the implementation target, not an accepted latency gain. C6 source, final compatibility, the 18,928-call native development comparison and its separate 56,784-call formal verdict remain pending at this checkpoint. There is still no approved v0.3.3 runtime or release tag.

## C6 final source and pre-formal evidence

The frozen C6 product source is `1bd97221e31e8e975498ece00f4bbfb3e0426aac`, runtime SHA256 `cfffd8a21374cbf9152bbbc98a6a9847a1e22401f16179112e2f79eef181ff78`. It adds the registered same-snapshot original-turn batch and guarded request-local reference reuse to C5. Reference reuse applies only to a single span and consumes each page's captured parse at most once; repeated pages and multiple spans retain independent nested reference objects through the original parsing path. Prepared-statement cache size, persistent schema, result-cache behavior and all source corruption checks are unchanged from C5.

The [final directed correctness receipt](../benchmarks/reports/round5-c6-correctness.json) records 96 unique passing tests. The overlapping dependency-free suite runs 44 cases with 21 tokenizer-dependent skips; its passes are not added to the 96. [Independent source review](../benchmarks/reports/round5-c6-source-review.json) passes. A pre-timing source version exposed nested-reference aliasing in two added regression cases; its failure and subsequent fix are retained in [the supersession record](../benchmarks/reports/round5-c6-pre-timing-superseded.json). Neither that superseded source nor the final source was timed before the registered development invocation.

The final-source commit's initial full CI failed one isolated-import fixture: `-S` removed the installed package path, while the local test environment had supplied `PYTHONPATH`. The [fixture-only correction](../benchmarks/reports/round5-c6-isolated-import-fixture.json) passes the explicit package root to the isolated child, preserving all assertions and exposing stderr on failure. Product source bytes are unchanged. All nine jobs then pass on `3ad5b591f4cb403f43cb2b92d21a842a1d8a5bb6`; [the exact CI receipt](../benchmarks/reports/round5-c6-ci-fixture-fix.json) retains both runs. Final release-commit CI is still required.

### C6 complete development comparison

The sole [registered invocation](../benchmarks/experiments/round5-c6-development-invocation.json) completes all eight sequential workers, 18,928 calls and 9,464 matching complete non-timing output pairs. Every original query, source/index/revision/cache invariant, cold first call and bounded native memo snapshot is retained in [the complete archive](../benchmarks/reports/round5-development/candidate-c6-full/README.md). The eight pooled native p50 and p95 values improve. Geometric-mean p95 improvement is **13.758180%**; public native token512/token1024/token2048 p95 improves **6.831978% / 16.531598% / 14.434232%**.

Adverse observations remain visible: pooled synthetic char4000 mean increases **0.845772%**. Synthetic char4000 round 0 mean/p95 increase **12.223894% / 3.023074%**; synthetic token2048 round 0 mean/p50 increase **1.788633% / 4.215140%**; public char4000 round 1 mean increases **0.512357%**. Public token512 round 0 p95 improves only **0.078377%**, and public token1024 round 1 improves **14.393663%**. The full eight pooled and sixteen per-round tables are retained. This two-round native diagnostic does not measure actual MCP or formal process RSS and does not replace release acceptance.

The saved-data archiver's baseline, registration and original-query-reference identifiers were corrected against the frozen files before it was run. This changed only offline identity checks; the measured helper, runtime, query order and all raw observations are unchanged. The corrected archiver is retained beside the raw evidence and performs no retrieval or timing.

### C6 final-source historical compatibility

The [C6 Hotpot256 compatibility check](../benchmarks/reports/round5-c6-hotpot-regression.summary.json) completes all 2,304 calls once: 1,536 native calls over both tokenizers and all three caps, plus 768 component calls. Every complete non-timing payload hash matches the saved v0.3.2 result. All 4,608 start/finish events align, and source/index/documents/revision remain unchanged. The separate C6 report binds the exact runtime, helper, environment and execution time. The ledger's bytes match C5 because case/configuration/output hashes are the same; neither source identity nor execution provenance is inferred from that shared ledger alone. This is historical compatibility, with no new quality, competitor or timing claim.

All development, compatibility and CI evidence was committed before formal binding at `0bd9ccf48bc9ed6a666888838ca11580c3104b98`.

## C6 sole formal execution and complete rejection

The [new binding](../benchmarks/experiments/round5-c6-performance-binding.json) was committed at `4d737fc60a12b60433f6f020614b296908b4c833`, SHA256 `2b57caea5b3d7f12b38aba9472d798e846a5231b936551784f0963259e2a715a`, with evaluator commit `0bd9ccf48bc9ed6a666888838ca11580c3104b98` and the frozen C6 source above. Its 51 measurement files, pinned SDK/tokenizer versions and original v0.3.2 source are verified before timing.

The single [hosted run 43557136276, attempt 1](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43557136276) used an isolated VM and published immutable progress to `validation/v033-round5-c6-performance-43557136276-1`. It completed four balanced rounds, all 56,784 calls and all 28,392 matching complete non-timing output pairs, with native and actual SDK MCP surfaces, cold first calls, resource measurements and every adverse sample retained.

The original numerical gates remain unchanged: aggregate p95 gain at least 10%, at least one public native token p95 gain at least 15%, public actual-MCP token1024 p95 gain at least 10%, and no pooled p50/p95 regression above 5%. A resource mean increase above 10% requires explicit independent review. Passing development or compatibility alone cannot authorize a release, and a completed numerical failure cannot be relabeled as an interrupted run.

The final result commit is `c6b384778e12ce9c72771911af37bbb2c5d3474f`; all 54 original files were verified against the 53-file completion inventory and their Git blob IDs, then losslessly merged at `5126acfd7fe6d94055d9b056b188d4948857b25e`. [Integrity receipt](../benchmarks/reports/round5-c6-result-integrity.json). The complete [independent review](round5-c6-performance-review.md) retains all twelve pooled and forty-eight per-round latency cells, all twenty-eight resource comparisons, storage and memo observations. Both saved-result audits pass without retrieval or timing, while `accepted:false` and `numeric_gate_passed:false` remain unchanged.

Aggregate p95 improves **14.919173%** and the best public native token configuration improves **16.286785%**. Actual public SDK MCP token1024 p95 is **7.289725 → 6.867000 ms**, only **5.798911%** better, so this gate fails. Its four individual round gains are **4.494251% / 7.220592% / 5.388878% / 2.590947%**, all below 10%. Every pooled p50, p95 and mean improves. The only adverse per-round latency metric is synthetic MCP char4000 round 0 p50, **+0.073375%**. Maximum resource mean increase is runtime import on synthetic61, **+9.189807%**, below the 10% review trigger. None of these favorable results overrides the failed MCP requirement.

The workflow measurement step therefore fails; its saved-observation audit, completion checkpoint and artifact upload succeed. The completion schema's generic `failed_or_incomplete` status accompanies a complete `measurements_completed` report with no errors or missing calls. C6 is not rerun, the original gate is not lowered, and the v0.3.3 approved runtime, main branch, tag and release remain untouched.


## C7 registration and unchanged-C6 transport observation

The [C7 continuation](../benchmarks/experiments/round5-c7-addendum.json), [native development plan](../benchmarks/experiments/round5-c7-development-plan.json) and [actual-MCP development plan](../benchmarks/experiments/round5-c7-mcp-development-plan.json) were saved remotely at `718ce3bbe42e23774e616219bd8ae60d143fb76f` before C7 implementation or timing. C7 may combine each standard SDK response's native write and immediate flush into one default thread call. The official SDK still serializes each message and controls framing, stdin, initialization, context and lifespan. Unknown SDK versions, custom methods and unsupported stdout streams retain the original path. No cross-response text buffer, delayed cache write, additional persistent cache or changed query timer is permitted.

The sole [unchanged-C6 diagnostic](../benchmarks/reports/round5-development/c7-preregistration/README.md) completed all 1,015 SDK calls and 2,030 original attempt events, but its final profiler-root-count assertion failed. That failure and every raw pstats byte remain preserved. A subsequent saved-data-only audit verifies the complete output hashes, source/index/revision state and explicit tool counts without rerunning retrieval or profiling. The anomalous root profiler record cannot establish request count or total duration. Count-only observations establish 1,017 stdout writes and 1,017 flushes, with one thread dispatch for each. They motivate the scheduling change; they do not establish a latency gain.

C7 correctness must cover successful and failed writes/flushes, standalone and paired flushes, cancellation, EOF, native-stream identity, SDK fallbacks, complete protocol output and normal cache behavior. Only after exact source freeze may the fixed 18,928-call native comparison and separate 4,060-call public actual-SDK comparison run once, in order on one host. Both retain all first calls, adverse values and complete output pairs. The original 56,784-call formal run is still independently required for release acceptance.


### C7 source freeze and correctness

Final C7 source is `d0c84cbfc9bad440ad447d41e211d070ef5b2cae`, runtime SHA256 `55529a217e6dcf6af0c81639cfc0e88b3ea94c39e6911f659fcfb7543e853d45`. Only `mcp_server.py` changes the C6 runtime. The [directed correctness receipt](../benchmarks/reports/round5-c7-correctness.json) records 26 passing tests, including 11 new adapter/guard/protocol cases. The same suite without optional site packages executes six tests and skips 20 dependency-specific cases; these are overlapping tests, not 52 unique cases. The [independent source review](../benchmarks/reports/round5-c7-source-review.json) finds no remaining blocker.

Real official-SDK correctness sessions compare the full initialization result, tools, recall/read-page results, normal cache writes/hits and EOF/lifespan. Five responses use five combined output dispatches, versus five write plus five flush dispatches on the original path. Both follow the official serializer and reader. Unknown/replaced SDK and AnyIO methods or aliases, unsupported native streams and custom/closed stdin/stdout retain the original path. The native stdin guard also preserves the SDK's failure/ownership order when input construction would fail. The first overly strict native built-in-method guard failure and all subsequent correctness logs remain archived. These operation counts and tests establish no performance acceptance; source-bound development and the original formal matrix remain required.
