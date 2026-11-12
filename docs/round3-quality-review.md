# Round-three project-statistics decision

**Reject the single project-local FTS statistics candidate.** The original
registered screen completed all **8,082 calls across eight workers**, and the
unchanged evaluator's strict saved-data audit passes. Its gate records **14 loss
checks and 10 aggregate improvements**. The default global-statistics retrieval
path is retained; the research candidate is excluded from this release and the
new-selection comparison.

## What the measurements show

| Old-data cohort, 512-token budget | Complete evidence: global → local | Annotation recall: global → local |
|---|---:|---:|
| Synthetic61 | 85.53% → 82.24% | 86.36% → 83.52% |
| Authored36 | 86.67% → 86.67% | 88.89% → 88.89% |
| Public1015 | 66.41% → 65.64% | 62.18% → 62.18% |
| Hotpot128 | 35.16% → 50.78% | 66.99% → 74.84% |

The Hotpot gains and larger-budget public gains coexist with the failures. The
registered rule requires preservation in every cohort/budget cell and in the
primary 512-token groups with at least ten questions. Public cross-session
completeness falls from **10.53% to 6.58%**, and synthetic low-overlap completeness
falls from **75.00% to 65.63%**. These losses cannot be offset by gains elsewhere.
All question-level gains and losses, temporary-index construction and switching
costs, memory measurements and timing diagnostics remain in the
[complete recovered report](../benchmarks/reports/round3-project-stats-recovery-43266603949-1/round3-project-stats-20261112-1.md)
and its adjacent raw worker files. These are evidence-retrieval measurements on
old development/regression questions, not final-answer accuracy or a new-domain
claim.

## Interruption recovery and independent verification

The upload stopped after 48 of 78 chunks. Complete original worker and ledger
bytes survived in the first-four-worker commit `36dbd82` and transfer checkpoint
`2bd5f27`. The earlier hosted recovery at `f0f6a5e` reconstructs the full result
without replaying any call and preserves the original incomplete aggregate.

A separate reconstruction verifies all **20 comparable files** against that
hosted commit: eight worker gzips, eight ledgers, the partial aggregate prefix,
the full reconstructed gzip, its summary and Markdown. Every Git blob ID agrees.
The unchanged 68 bound evaluator files, both exact runtime sources, full matrix,
ledger row hashes and original rejection were checked again without new scoring.
The [cross-verification record](../benchmarks/reports/round3-recovery/quality-cross-verification.json)
contains the source refs, individual identities and report hashes.

The original complete aggregate hash was never uploaded. Both recoveries derive
the same complete report from intact original workers and controller metadata;
they do not invent an independent original hash for the missing compressed
suffix. The canonical hosted result remains the preserved record. This closes
the quality candidate under the existing protocol, without retuning or replay.
