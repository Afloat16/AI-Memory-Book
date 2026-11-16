# Incremental native acceleration: v0.8.0 to v0.8.1

This experiment measures the additional effect of translating two remaining
Python loops into C. Its baseline is the already-native v0.8.0 release. The
earlier Python-to-native experiment remains a separate
[frozen result](native-language-validation.md); its percentages must not be
presented as gains from this candidate.

**Measurement and delivery acceptance are pending at this checkpoint.** The
registered matrix is executing as
[43850332046, attempt 1](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43850332046).
Planned counts are 113,568 timed calls and 56,784 paired comparisons. This page
will record the complete observed results, including regressions and resource
costs, before the candidate can be approved for release.

## Implementation contract

`identifier_aliases` translates ASCII identifier boundaries, case folding,
component aliases, compact spellings and the legacy per-run duplicate checks.
Python retains whole-string normalization and tokenization. The index guard
runs after whole-string tokenization so supported helper mutations retain their
observable order. Token order, repetitions and qualified-name boundaries are
preserved.

`literal_positions` collects the original nonoverlapping literal occurrences,
with the original 40-match cap per term and Unicode code-point source mapping.
Duplicate and empty terms retain their existing behavior. Python still sorts
the positions, constructs windows, evaluates floating-point scores and formats
the excerpt. The C loop retains owned references while allocating results.

The change preserves schema 4, SQL/FTS indexes, ranking, project scope, stable
IDs, pagination, source spans, budgets and cache policy. It adds no cross-call
cache. The existing Python body remains available for supported overrides,
unusual argument types and environments without a compatible native extension.

## Frozen identities

| Role | Commit or identity |
|---|---|
| Released native v0.8.0 baseline | `6a8a9c6d603a812c75def258b11eb563ed590c9b` |
| Native v0.8.1 runtime candidate | `d2f13a3f44742d53c6f47e1d2cd7732e44a5524e` |
| Evaluator, host, preservation code and formal plan | `3f3c50cbbbf9dfaf023e7aa4f7fce796fa5df099` |
| Formal plan SHA-256 | `e5afadba80806dc57b615b37ca719d4c26395ee5d5a207679783e21fd9840f0f` |
| Candidate runtime SHA-256 | `8fabb49f3bf30513cc765d58b2b6192706d76571643f3cf18136d0dc6b292cf0` |

The [formal plan](../benchmarks/experiments/native_incremental_formal_plan.json)
binds both native source revisions and all helper probe counts. Both sides
build with the same compiler, command and optimization flags on the hosted
runner. Separate binary hashes, compiler logs, source-file inventories and
dependency/platform identities are retained.

## Method and evidence limits

The full matrix uses 16 fresh sequential workers: four rounds in AB / BA / BA /
AB order, two implementations and two cohorts. Every worker runs three seeded
passes of all four configurations. The primary configurations use the default
2,400-character budget through direct `MemoryBook.recall` and actual official
SDK stdio MCP. Secondary configurations add a 1,024-token limit with an
8,000-character ceiling using `cl100k_base`.

Synthetic61 has 112 sessions, 1,408 turns and 168 queries; public1015 has 216
sessions, 4,684 turns and 1,015 queries from the fixed LoCoMo text-evidence split.
These are existing compatibility/performance datasets, not new evidence of
retrieval quality. The pinned upstream input and split identities are recorded
in the run manifest.

Direct timing covers the recall call. MCP timing covers `call_tool`, including
server retrieval, the normal cache write, serialization and transport. Model
generation is excluded. Result caching is disabled for direct calls and cleared
before every MCP call, outside the timer. SQLite/OS caches are retained and
token-count memoization warms naturally. No timed-call warmups or selectively
discarded samples are permitted.

Before timing, identical public-wrapper probes verify five baseline helpers and
seven candidate helpers, then remove all instrumentation. The probe outputs
match exactly. Every worker checks source/binary identities before and after
execution. Full indexed/source contents and complete stable payload digests are
compared; only predeclared host timestamps and top-level `latency_ms` are
excluded. Source coordinates, scope, context reconstruction and budgets are
validated during execution.

The independent native suites add 28 tests, including 39,216 short ASCII
input/mode pairs, mixed Unicode and surrogate cases, dynamic helper replacements
and exact errors. Sixteen protocol/preservation tests pass. The retained
[development record](native-incremental-development.md) includes the noisy
local diagnostic with a 4.62% pooled p95 regression; it is not substituted for
the hosted experiment.

Offline audits compare recorded payload digests, invariants, source/binary
identities and attempt ledgers. They cannot reconstruct original response text
from hashes. Differential tests and execution-time coordinate/budget checks are
complementary evidence; finite tests are not a proof over every possible input.

## Durable preservation and delivery

The hosted workflow saves complete or failed attempts directly to an immutable
`evidence/native-incremental-<run_id>-1` Git branch, with raw worker reports,
ledgers, start markers, preparation events, logs, both measured binaries,
committed runtime sources and the frozen offline auditor. An Actions artifact
is an additional copy. Existing differing evidence refs are never overwritten.

The intended release must pass the complete 30-cell native-wheel matrix:
CPython 3.10–3.15 with the GIL, on Linux x86-64/AArch64, macOS Intel/Apple Silicon
and Windows x64. Both new native suites run against each installed wheel.
Receipt aggregation, fallback/source clean installs and native/fallback
installer checks precede acceptance. Final publication separately requires the
approved runtime hash, exact current main commit, all nine CI jobs, fresh
publication receipts and an installation through the public release URL.
