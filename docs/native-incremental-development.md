# Incremental native acceleration after v0.8.0

The user requested continued acceleration with existing logic unchanged. This
round starts from released commit `6a8a9c6d603a812c75def258b11eb563ed590c9b`,
already using all five native helpers from v0.8.0. It does not reuse the old
Python baseline to describe the gain from new work. The original experiment and
its preserved evidence remain immutable.

The [development plan](../benchmarks/experiments/native_incremental_plan.json)
freezes the implementation boundary and acceptance requirements. The intended
next version is v0.8.1 only if new measurements justify adoption; this checkpoint
is not a release decision or a formal performance result.

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
