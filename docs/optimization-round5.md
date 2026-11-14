# v0.3.3 optimization and release checkpoint

Status: C3 completed all formal measurements but failed two fixed speed gates; release acceptance is rejected. A substantive C4 source is under diagnosis. No release runtime is approved.

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

Current next steps: profile and select an exact-output candidate; prepare the v0.3.2 comparison source and pinned data; implement the new runner without modifying historical results; add explicit stable-release policy while preserving all existing source/CI/package guards.

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
