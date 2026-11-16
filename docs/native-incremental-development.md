# Incremental native acceleration after v0.8.0

The user requested continued acceleration with existing logic unchanged. This
round starts from released commit `6a8a9c6d603a812c75def258b11eb563ed590c9b`,
already using all five native helpers from v0.8.0. It does not reuse the old
Python baseline to describe the gain from new work. The original experiment and
its preserved evidence remain immutable.

The [development plan](../benchmarks/experiments/native_incremental_plan.json)
freezes the implementation boundary and acceptance requirements. The sections
below retain the successive development checkpoints. The completed experiment
now supports the [v0.8.1 acceptance decision](../benchmarks/experiments/native_incremental_acceptance.json),
including secondary costs; final publication has separate exact-commit gates.

## Baseline profile, 2026-11-16

The [raw native profile](../benchmarks/reports/native-incremental/development/synthetic61-native-v080.json)
uses synthetic61 (112 sessions, 1,408 turns, 168 queries) in an in-memory SQLite
database, with result caching disabled and the default 2,400-character budget.
After warming, three query passes produced 504 profiled recalls. Source hashes
before and after profiling agree with released v0.8.0. The accompanying
[runner](../benchmarks/reports/native-incremental/development/profile_synthetic61.py)
documents how to repeat this diagnostic.

With profiler overhead included, `identifier_terms` accounts for 37.48% of fresh
ingestion cumulative elapsed time (7.81% self time), and 8.42% of recall time.
`excerpt` accounts for 13.50% cumulative recall time (4.66% self time). SQLite
execution and fetching together remain about half of recall time. Cumulative
percentages overlap and must not be added as independent costs. These are local
profile shares, not CPU utilization, expected speedups or hosted timing results.

The next candidates are equivalent C loops for identifier aliases and literal
excerpt occurrences. Whole-string Unicode normalization, retrieval rules,
floating-point excerpt scoring, SQL and cache behavior retain their existing
implementations. Independent differential tests must preserve token order and
frequency, exact source coordinates, patched helpers and unusual input types.

Formal measurement will build both the v0.8.0 baseline and the frozen candidate
as native extensions in the same hosted environment. It will preserve all
attempts and include actual SDK MCP roundtrips. Existing Python/native
measurements cannot be represented as gains from this new candidate.

## Candidate implementation checkpoint

Two additional helpers now translate the identifier alias loop and literal
excerpt occurrence loop. The existing ASCII scanner is shared internally to
preserve the legacy per-identifier deduplication rule. Query rewrites retain the
same component order and compact aliases. Literal matches remain nonoverlapping,
term-major and capped at 40 per term before the original Python sorting and
window scoring. Empty-term terminal matches retain the original mapped-index
error. No cross-call cache is introduced.

Review corrected an owned-reference lifetime in literal matching, and moved the
index-mode dependency guard after whole-string tokenization so a customized
normalizer's mutations remain observable. Public helper overrides, unusual
container types and string subclasses continue through the Python body.

The [independent test receipt](../benchmarks/reports/native-incremental/development/independent-tests.json)
records 28 passing new tests, including 39,216 exhaustive short-ASCII input/mode
pairs, seeded Unicode cases, source mappings, original error behavior and
pre-/post-import helper replacements. The existing native/core/identifier suites
also pass locally with the optional-tokenizer case explicitly skipped. The
[compiler log](../benchmarks/reports/native-incremental/development/candidate-build.log)
retains the forced GCC build; the local runtime's default clang was unavailable.
These local checks do not replace the complete platform wheel matrix.

The four planned balanced local diagnostic rounds are retained in
[raw compressed JSON](../benchmarks/reports/native-incremental/development/local-native-paired.json.gz)
with their [runner](../benchmarks/reports/native-incremental/development/paired_native_diagnostic.py).
All 4,032 recall outputs and the eight archive/index digests agree between the
released native baseline and the candidate, and source hashes remain unchanged.
The shared host showed substantial timing variation: pooled candidate p95 was
20.233 ms versus 19.340 ms for the baseline (a 4.62% regression), while fresh
ingestion medians were 784.081 versus 1,609.946 ms. This diagnostic uses in-memory
SQLite, no MCP and no exact-token cap. Neither number is a release speed claim;
both are retained rather than selecting the favorable measurement.

The new protocol-2 hosted evaluator will compare native builds on both sides,
verify all five baseline and seven candidate helpers before timing, and save
every raw attempt plus frozen sources and auditor directly to a Git evidence
branch. Runtime acceptance remains pending that complete experiment.

## Hosted freeze and distribution follow-up

The runtime candidate is committed as
`d2f13a3f44742d53c6f47e1d2cd7732e44a5524e`. Evaluator commit
`3f3c50cbbbf9dfaf023e7aa4f7fce796fa5df099` freezes protocol 2 and the
[formal plan](../benchmarks/experiments/native_incremental_formal_plan.json)
(SHA-256 `e5afadba80806dc57b615b37ca719d4c26395ee5d5a207679783e21fd9840f0f`).
Both untimed public-wrapper probes produce SHA-256
`ebe4761b17ec0b2f34154558416815713d4a831c10e7b51401f6d1168c9151b8`, with
the exact registered native-helper counts and all instrumentation restored.
All 16 evaluator/preservation tests pass, including the real SDK transport
fixture and the corrupt-run preservation regression found by independent review.

[Hosted run 43850332046](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43850332046)
is the first attempt of the complete registered matrix: 113,568 planned calls,
56,784 pairs. These remain planned counts until the final audit confirms them.
The original protocol-1 files and their evidence are unchanged.

General CI at the candidate commit
[43849957981](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43849957981)
found one release-default assertion still tied to v0.8.0 after the package was
prepared as v0.8.1. The installer entry points and current-version assertions
are now synchronized; historical release fixtures remain unchanged. All 42
targeted installer/release tests pass. This distribution-only follow-up does
not alter the measured runtime or frozen evaluator. No v0.8.1 runtime approval
hash has been registered while the formal performance result is pending.

## Completed formal verification

Run 43850332046 completed all 16 workers and every registered call on its first
attempt. The same workflow saved immutable evidence commit
`ed30ded94e00c81f381f57a6bd957bdf3322b20b` before uploading its additional
artifact copy. There are 113,568 calls, 56,784 exact-output pairs and zero
recorded invariant/archive differences. The independent
[artifact audit](../benchmarks/reports/native-incremental/formal-run-1/independent-audit.json)
checks all 226 ZIP files, frozen source objects, both binaries, the exact Git
tree and all 227,136 attempt events. It exactly reproduces the frozen summary
and independently recalculates every pooled and per-round percentile.

Default-budget p95 reductions are 3.061%/2.514% on synthetic61 and
4.902%/3.946% on public1015 for direct/MCP respectively, with every primary
paired round improving. Token-budget results are mixed: public MCP p95
regresses 0.334%, with three of four rounds regressing. Fresh synthetic
ingestion improves 9.583%, public ingestion is effectively flat, startup is
slightly slower and memory is approximately unchanged. The complete
[validation record](native-incremental-validation.md) retains every result and
the earlier unfavorable local diagnostic.

Distribution repair `7d20667ac585506d10238dd32412c53a0cf4786a` passes all nine
CI jobs in run 43850669866. Preparation run 43850729647 passes all 30 native
wheel cells, each running the 53 native tests with one optional-tokenizer skip,
then aggregates 67 assets and verifies both native and Python fallback
installers with default MCP/client extras. The preparation run does not publish
a release or change the frozen runtime. Final acceptance/publication still
requires its own approved runtime record and exact-main release gates.

## Acceptance and final publication gates

The independent packaging audit passes: all 67 assets, 30 wheel records and
receipts, exact source/build inputs, installed native tests and default-extra
installer checks agree with preparation run 43850729647. Compact
[audit evidence](../benchmarks/reports/native-incremental/packaging-43850729647/audit.json)
is retained with the actual manifest, job matrix and installer record.

The [acceptance record](../benchmarks/experiments/native_incremental_acceptance.json)
adopts the frozen runtime hash
`8fabb49f3bf30513cc765d58b2b6192706d76571643f3cf18136d0dc6b292cf0`.
It records all eight latency cells, every paired p95 round, resource medians,
the unfavorable local diagnostic and the small token/startup regressions.
All 24 measured runtime/build files and 11 frozen evaluator files still match
the formal run. The release approval registry now binds v0.8.1 to that hash.

The publication workflow must still verify all nine CI jobs on the final
approved commit, exact main/release refs, a fresh 30-wheel matrix with receipts,
complete assets and an actual installation through the public release URL.
The README has changed since preparation, so its packaging metadata and all
final receipts must be rebuilt. This acceptance checkpoint does not describe
those future checks as already completed.
