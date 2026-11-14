# v0.3.3 optimization and release checkpoint

Status: development started; no v0.3.3 speed or superiority claim is accepted yet.

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
