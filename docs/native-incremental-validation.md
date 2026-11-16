# Incremental native acceleration: v0.8.0 to v0.8.1

This experiment measures the additional effect of translating two remaining
Python loops into C. Its baseline is the already-native v0.8.0 release. The
earlier Python-to-native experiment remains a separate
[frozen result](native-language-validation.md); its percentages must not be
presented as gains from this candidate.

**Independent performance verification is complete; delivery acceptance is pending.** The
registered matrix completed as
[43850332046, attempt 1](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43850332046).
All 113,568 timed calls and 56,784 paired comparisons are present and equivalent.
The complete observed results, including regressions and resource costs, appear
below. The independent artifact audit passes; adoption still requires completion
of the delivery gates.

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

The actual host is an Intel Xeon 6975P-C with four allocated CPUs, CPython
3.12.16, SQLite 3.45.1 and Unicode 15.0.0. Dependencies are MCP 1.30.0,
Pydantic 2.14.3, tiktoken 0.12.0 and setuptools 80.9.0. GCC 13.3.0 builds both
sources with explicit `-O3` and forced native mode. The older experiment used
an AMD host; its absolute timings are not a baseline for this new run.

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


## Recorded recall and resource results

The hosted run completed all **113,568 calls and 56,784 pairs**, with no
recorded output, archive or invariant differences. Every primary scenario
improved in all four paired rounds. The independent artifact audit reproduces
the original summary exactly and independently recalculates every pooled and
round-level statistic from the raw records.

All times are milliseconds. Reduction is `100 × (1 − candidate / baseline)`.
Negative reductions are regressions. Pooled percentiles use every retained row,
not an average of round percentiles.

| Dataset | Configuration | v0.8.0 p50 | Candidate p50 | p50 reduction | v0.8.0 p95 | Candidate p95 | p95 reduction | Round p95 reduction range |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| synthetic61 | Direct, 2400 chars | 3.149415 | 3.074462 | 2.380% | 8.774487 | 8.505873 | 3.061% | 2.534 to 3.392% |
| synthetic61 | MCP, 2400 chars | 4.691440 | 4.609757 | 1.741% | 10.463171 | 10.200099 | 2.514% | 2.417 to 2.663% |
| synthetic61 | Direct, 1024 tokens | 3.568806 | 3.435666 | 3.731% | 9.109044 | 9.065873 | 0.474% | -0.040 to 1.088% |
| synthetic61 | MCP, 1024 tokens | 5.061657 | 4.906455 | 3.066% | 10.747730 | 10.682196 | 0.610% | -0.374 to 1.439% |
| public1015 | Direct, 2400 chars | 2.796990 | 2.670238 | 4.532% | 3.651276 | 3.472300 | 4.902% | 4.082 to 5.308% |
| public1015 | MCP, 2400 chars | 4.302492 | 4.166792 | 3.154% | 5.222376 | 5.016324 | 3.946% | 2.828 to 4.805% |
| public1015 | Direct, 1024 tokens | 2.300300 | 2.303676 | -0.147% | 2.770739 | 2.770178 | 0.020% | -0.324 to 0.489% |
| public1015 | MCP, 1024 tokens | 3.815117 | 3.826844 | -0.307% | 4.371708 | 4.386305 | -0.334% | -0.713 to 0.027% |

Token-limited results are mixed. Public direct recall is approximately flat
(p50 regresses 0.147%; p95 improves 0.020%). Public MCP regresses 0.307% at p50
and 0.334% at p95, approximately 0.012 ms and 0.015 ms respectively. Three of
its four paired p95 rounds regress, with the largest regression 0.713%.
Synthetic token p95 improves only 0.474%/0.610%, with negative individual rounds.
These results do not establish a consistent token-budget speedup.

Resource values below are medians of four workers per side and cohort.
They are separate small-sample measurements, not per-query latency percentiles.

| Dataset | Resource | v0.8.0 | Candidate | Change |
|---|---|---:|---:|---:|
| synthetic61 | Fresh ingestion | 531.675 ms | 480.724 ms | -50.950 ms |
| synthetic61 | Unchanged reingestion | 55.624 ms | 55.015 ms | -0.609 ms |
| synthetic61 | API import after evaluator bootstrap | 29.365 ms | 29.577 ms | +0.212 ms |
| synthetic61 | MCP initialization, 2400 chars | 426.527 ms | 428.143 ms | +1.617 ms |
| synthetic61 | MCP initialization, 1024 tokens | 420.140 ms | 420.282 ms | +0.142 ms |
| synthetic61 | Worker RSS after calls | 129.473 MiB | 129.512 MiB | +0.039 MiB |
| synthetic61 | Worker peak RSS after calls | 134.090 MiB | 132.855 MiB | -1.234 MiB |
| public1015 | Fresh ingestion | 488.361 ms | 488.457 ms | +0.096 ms |
| public1015 | Unchanged reingestion | 92.323 ms | 92.530 ms | +0.207 ms |
| public1015 | API import after evaluator bootstrap | 29.346 ms | 29.676 ms | +0.330 ms |
| public1015 | MCP initialization, 2400 chars | 427.343 ms | 428.766 ms | +1.423 ms |
| public1015 | MCP initialization, 1024 tokens | 421.325 ms | 420.067 ms | -1.258 ms |
| public1015 | Worker RSS after calls | 138.896 MiB | 138.795 MiB | -0.102 MiB |
| public1015 | Worker peak RSS after calls | 149.230 MiB | 149.102 MiB | -0.129 MiB |

Fresh ingestion improves 9.583% on synthetic61; public ingestion is essentially
unchanged (0.020% slower). Unchanged reingestion improves 1.095% on synthetic61
and regresses 0.224% on public1015. API import adds about 0.21–0.33 ms. Default
MCP initialization adds about 1.42–1.62 ms; token-server initialization is mixed.
Memory is approximately unchanged, with no claimed memory-saving result.
Checkpointed database sizes remain exactly 20,201,472 bytes for synthetic61
and 13,025,280 bytes for public1015, with zero-byte checkpointed WAL files.

The complete report retains per-call CPU measurements, MCP server CPU snapshots,
RSS/high-water marks, database/WAL/SHM sizes and all startup/ingestion readings.
MCP per-call CPU is the client process; it is not server CPU. No comparison
against the old experiment's absolute timings or additive speedup is inferred.

## Durable preservation and delivery

The hosted workflow saved this run directly to
[`evidence/native-incremental-43850332046-1` at `ed30ded94e00c81f381f57a6bd957bdf3322b20b`](https://github.com/Afloat16/AI-Memory-Book/tree/ed30ded94e00c81f381f57a6bd957bdf3322b20b).
Its 144-file evidence tree contains all 80 original reports, ledgers, start
markers, preparation/build/probe records and logs; 11 frozen evaluator files;
48 runtime/build source files; and five metadata/audit files. All 59 frozen
source/evaluator files match their actual Git source objects. Failed or
incomplete attempts would also be preserved, and differing existing evidence
refs are never overwritten.

The additional [Actions artifact](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43850332046/artifacts/14217956098)
is 77,031,297 bytes, SHA-256
`96fb2f972baccd009be23db35329b5ce28d2d13fcd8068e31242581ac0371602`.
The independent audit checks all 226 ZIP files, the original/retained duplicate
bytes, both measured binaries and the exact evidence Git tree. A separate
implementation recounts all 113,568 rows, 56,784 pairs and 227,136 ledger events,
and reproduces all eight pooled cells and 32 round-level statistics. No queries
are remeasured. Complete evidence is durable in Git independently of artifact
expiration.

Main retains compact [run](../benchmarks/reports/native-incremental/formal-run-1/run.json),
[summary](../benchmarks/reports/native-incremental/formal-run-1/summary.json),
[build](../benchmarks/reports/native-incremental/formal-run-1/build-manifest.json)
and [independent audit](../benchmarks/reports/native-incremental/formal-run-1/independent-audit.json)
reports. The [artifact auditor](../scripts/native_incremental_audit_artifact.py)
verifies archive bytes against the retained
[API metadata](../benchmarks/reports/native-incremental/formal-run-1/api-metadata.json)
and performs an independent numerical recount. For a
standard-library audit without downloading the original input or executing the
application, check out the immutable evidence commit and run:

```bash
python frozen-evaluator/scripts/native_incremental_performance.py --audit benchmarks/reports/native-incremental/formal-run-1
```

Compare that output with the preserved `summary.json`. The compact reports
alone do not contain the required raw attempt ledgers.

The intended release must pass the complete 30-cell native-wheel matrix:
CPython 3.10–3.15 with the GIL, on Linux x86-64/AArch64, macOS Intel/Apple Silicon
and Windows x64. Both new native suites run against each installed wheel.
Receipt aggregation, fallback/source clean installs and native/fallback
installer checks precede acceptance. Final publication separately requires the
approved runtime hash, exact current main commit, all nine CI jobs, fresh
publication receipts and an installation through the public release URL.
