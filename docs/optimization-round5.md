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
