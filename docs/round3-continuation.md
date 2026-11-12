# v0.3.1 completion and recovery checkpoint — 2026-11-13

The round-three measurements, independent reviews and documentation are
complete. This continuation started from
`93cea9544d024708d8fa9a423914bb255b9476d1` on
`validation/v031-round3-integration`. The comparison baseline is v0.3.0 at
`dd2f88be742ed330269e7dd5915b6f75089d7fef`; the accepted runtime is
`2d199b93f650eccd3dd239178822b31001b880e3`, Python-source SHA-256
`9c8118d26ae1a0eae4f31d9d4f44b2afa0ee5c54314bde5187deb27c473dee46`.

## Completed evidence

| Work | Preserved result | Decision |
|---|---|---|
| Original formal performance, run `43246417515` | All 47,320 calls and 16 workers; full non-timing payload and invariant checks pass; ten cells across four balanced rounds | Query-speed gate passes, geometric mean pooled p95 improves 11.36%; independent review accepts the startup resource exception without changing the original `accepted: false` |
| Original project-statistics quality screen | All 8,082 calls reconstructed from original workers without replay; 20 recovered files match canonical hosted recovery | Reject: 14 registered checks fail; candidate remains unshipped |
| Existing startup-only diagnostic, run `43266672875` | All 80 original samples, Git/SHA256 identities and source/SQL checks independently reconstructed | Supplemental resource evidence; original startup +14.04% and diagnostic p95 regression remain visible |
| New component/native comparison, run `43267797247` | Ten stages, 4,608 native calls plus 4,608 component searches; 1,536 native and 768 component default payload pairs match | `complete-verified`; all budgets, costs and Q2 losses retained |

The [independent comparison audit](../benchmarks/reports/round3-recovery/comparison-cross-verification.json)
checks all 32 original result blobs, all 71 bound evaluator files and the
unchanged evaluator's exact assessment/report recomputation. It performs no
retrieval, timing or model calls. The final original result commit is
`c99f20531053b1c164fc5a5d3fa8e0c831eeb4de` on
`validation/round3-comparison-43267797247-1`.

Read the [full comparison](comparison.md#v031-comparison),
[performance review](round3-performance-review.md),
[quality recovery review](round3-quality-review.md),
[source review](round3-code-review.md), and
[release notes](releases/v0.3.1.md) for conclusions and limitations.

## Authoritative registration and interruption history

An earlier hosted registration appeared during recovery. Its existing
[comparison run](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43267797247)
was adopted as authoritative. Source, evaluator, dependencies, model and
upstream identities were committed before its selection. The later local
selection reproduced the same exact IDs and dataset but was never scored;
its binding and manifest are archived as unused. The
[reconciliation record](round3-reconciliation.md) retains all source and
registration identities and the local raw-source exposure disclosure.

The original quality transfer stopped at commit
`2bd5f27d1ae478c1735f36b5354fddd81114182b`, checkpoint 48 of 78 chunks.
Recovery used complete workers and preserved control metadata, not scoring
again. The reconstructed aggregate matches every surviving original prefix
byte; the missing original suffix has no independent original hash. Canonical
hosted recovery and independent reconstruction match byte for byte. Failed
and incomplete checkpoints stay in Git history.

No completed performance or quality measurement is rerun to choose better
results. The new HotpotQA IDs exclude both earlier selections but use the same
public source; after first scoring they are regression data. The authoritative
acceptance rules remain
[`round3-plan.json`](../benchmarks/experiments/round3-plan.json).

## Durable checkpoints and release gates

Work is preserved on `optimization/v0.3.1-completion`. Meaningful checkpoints
include `0bd236b` (recovery and source review), `6f9050d` (original performance
evidence and unused local selection), `3e9194d` (authoritative registration and
quality recovery), and `879a53e` (original startup diagnostic and independent
80-sample audit). Large existing reports reuse their original Git tree/blob
objects instead of transferring them through chat-sized blob payloads.

Publication follows [the existing release procedure](releasing.md): all nine
Tests jobs must pass on the exact candidate SHA, then `main` and
`release/v0.3.1` point to that same commit. The workflow builds and verifies
seven assets and tests installation through the actual public tagged URL.
[CI](https://github.com/Afloat16/AI-Memory-Book/actions/workflows/ci.yml),
[release runs](https://github.com/Afloat16/AI-Memory-Book/actions/workflows/release.yml)
and the [v0.3.1 release](https://github.com/Afloat16/AI-Memory-Book/releases/tag/v0.3.1)
record the distribution state and exact source identity. A future continuation
should inspect those records and the latest branch heads before doing new work;
it must not rerun the completed round-three experiments.
