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
