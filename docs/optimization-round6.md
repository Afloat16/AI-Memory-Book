# v0.3.4 optimization and recovery checkpoint

Status: registered before implementation or scored timing. Published v0.3.3 remains the baseline and current release; no v0.3.4 runtime is approved.

## User goal and immutable baseline

The user requests another measurable improvement, continuing progress against comparison repositories, and frequent remote commits so conversation/blob interruptions do not lose the work. Baseline tag `v0.3.3` identifies source `796cedfd1f5368144037a1fb72292b8d13884b8c`, runtime SHA256 `55529a217e6dcf6af0c81639cfc0e88b3ea94c39e6911f659fcfb7543e853d45`. Main starts at its publication-receipt commit `e51498d3c797146e5a1ce94461f0d767fc732541`.

## Work and acceptance

The [round-six plan](../benchmarks/experiments/round6-plan.json) retains the fixed 56,784-call, four-round, twelve-cell paired native/actual-MCP matrix. Numerical gates remain 10% aggregate p95, 15% at least one public native-token p95, and 10% public actual-MCP token1024 p95 improvement; no pooled p50/p95 regression may exceed 5%. Both versions now contain the same bounded exact-count memo, so both start naturally empty and both are observed. Every resource mean and adverse sample is retained; increases over 10% require separate cause assessment and independent review.

Initial code-supported targets are atomic new-database schema creation, repeated request-local retrieval work identified from old-data profiles, and optional command-specific lazy imports. Atomic schema creation must preserve rollback, unrelated-database rejection, existing-archive behavior and complete initial schema. No implementation or version-only edit is an accepted speed result.

Historical Hotpot256 output compatibility is checked against all 2,304 previously reproduced complete hashes. A new third-party component comparison requires a separate plan, exact source/evaluator/dependency freeze and fresh deterministic ID-only selection before any scoring. Historical competing quality and speed advantages remain visible. Claims must follow the new measured boundaries, not the user's desired result.

## Ownership and durable execution

- Runtime work: `store.py` and focused new regression cases, after concrete hypothesis review.
- Measurement work: new round6 controllers, independent audits, ledgers and hosted checkpoint workflows; immutable round4 primitives may be reused.
- Comparative evidence: new round6 fresh-selection/comparison controls and fair adapter boundaries.
- Coordinator: version changes, explicit preregistration, review, remote commits, exact-source CI and any accepted release.

Incremental work is checkpointed on `validation/v034-round6-work`. This branch avoids rerunning the full CI matrix for each report-only checkpoint; the final candidate will be sent to `optimization/round6-v0.3.4` for all nine exact-source CI jobs. Main and release tags advance only after applicable acceptance and package gates. Existing tags, raw benchmark reports and original acceptance decisions are immutable.

## Recovery instructions

Read this file and the plan, then inspect the latest remote work-branch commit and any new round6 binding/run records. Do not replay an already claimed unchanged formal experiment or select a favorable repeat. Resume incomplete work from retained per-worker ledgers only when the original controller permits it; otherwise preserve the interruption and register a materially justified continuation. Keep newly completed work in remote Git before starting long measurements.


## Command loading checkpoint

The package exposes the same `MemoryBook` class lazily, keeping its original identity, star import and discovery. CLI help/version now load only command metadata; transcript format names live in a lightweight shared module, and archive, capture configuration and command-specific helpers load only when used. Explicit database commands avoid unrelated capture configuration. The [correctness receipt](../benchmarks/reports/round6-command-correctness.json) records 92 passing tests, including four isolated process checks of imports, type hints, class overrides and real database creation. This is an implementation/correctness checkpoint, not a measured CLI speed claim or final-source release approval.


## Candidate A implementation ready for source freeze

Version metadata and installers now identify candidate v0.3.4. Runtime SHA256 is `f361d2bf64a4e1088cbd5cff6ffdaf19aa15e7f1b7ea1de4577d7a488d2ac242` (17 Python files). The new archive schema runs under one immediate transaction with a locked empty/schema recheck; partial failures roll back and close, and competing initializers safely recheck. Native FTS results carry already-read narrow metadata within the same recall, avoiding a second union query. All candidate-directory checks remain; custom factories and restrictive/uninspectable SQLite limits keep the original query path. Python 3.10 uses that conservative metadata fallback.

[Candidate correctness](../benchmarks/reports/round6-candidate-a-correctness.json) records the overlapping 40-test protocol/release/startup check and final 10-test atomic/metadata suite. [Baseline diagnostics](../benchmarks/reports/round6-development/baseline-profile/manifest.json) preserve all 4,732 old-data cProfile calls and 1,183 operation-count calls, including preflight failure evidence. These are diagnostic observations, not an accepted speed result.

The new performance/compatibility and fresh-comparison controllers are checkpointed as scaffolds, with no bound final evaluation and no fresh selected/scored questions. Runtime release approval remains absent. Next: exact-source CI, once-per-source development runs and complete historical output compatibility, then the independent frozen formal comparison under the original 10/15/10 gates.
