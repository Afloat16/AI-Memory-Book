# Native language acceleration: development record

This is a work record, not a benchmark result. The reference is commit
`b1434ca8b218d096d5506aaea02631ca31306d21` (the v0.7.0 runtime plus documentation).
The requested change is execution language only. Retrieval policy, SQL, scope,
ranking, source coordinates, context budgets, caches and the MIT license remain
the reference contract.

The initial candidate is a CPython C extension for measured text-processing
loops. These functions already operate on Python Unicode objects; direct access
can avoid representation conversion. This is an implementation hypothesis, not
a claim that C outperforms Rust or that a language rewrite accelerates SQLite.
The Python implementation remains available for exact differential validation
and for environments without a compatible native extension.

The measurement requirements are recorded in
[`native_language_plan.json`](../benchmarks/experiments/native_language_plan.json).
Development profiling and microbenchmarks will be identified separately from
frozen end-to-end measurements. The old synthetic61/public1015 data can establish
performance and behavior regressions only. No new quality or language speedup
result has been measured or accepted at this checkpoint.

Before publication, installers and release archives must be verified to deliver
the implementation that was actually measured; a locally compiled extension is
not sufficient. Every checkpoint is committed with the repository owner's
verified identity. Failed experiments are retained and not silently replaced.

## First implementation checkpoint

A fresh diagnostic profiled the fixed reference source on synthetic61 (112
sessions, 168 questions) with the current 2,400-character default. Its call
records identify `_fold_excerpt_source` and `terms` as useful native candidates;
ingestion also spends time in `identifier_terms`. Profiler overhead is included,
so these timings are not an end-to-end performance result. The
[raw profile](../benchmarks/reports/native-language/development/baseline-profile.json.gz)
and [runner](../benchmarks/reports/native-language/development/baseline-profile-runner.py)
retain the exact source, environment and dataset identities.

The initial C candidate translates ASCII terms, per-character source folding,
and evidence-unit boundary loops. Python retains Unicode normalization and
retrieval decisions. `MEMORY_BOOK_TEXT_BACKEND=python|native|auto` selects the
implementation; forced native mode fails if the extension is unavailable.
Dynamic helper overrides and nonstandard argument types retain the Python path.
No cross-call cache is added. This is still a development candidate.

The existing 62 targeted text/identifier/core tests and the first 20 independent
native contract tests passed locally on CPython 3.12.14. Those results do not
establish end-to-end speed or cross-platform release readiness. The build first
encountered an unavailable `clang` from the runtime configuration; an explicit
`CC=gcc MEMORY_BOOK_BUILD_NATIVE=1` build succeeded. Forced builds will be used in
native validation so an optional fallback cannot masquerade as acceleration.

## Candidate freeze preparation

The C path now also translates the prepared Unicode token loop. Its categories
were checked against the Python regular-expression reference across all
1,114,112 Unicode code points, including surrogate values and unassigned values
inside the historical fixed CJK ranges. The fold cache uses a local ASCII array
alongside the existing per-call character mapping; normalization calls retain
their order, and nothing is shared between requests. The independent native
contract suite now has 25 passing tests on the local CPython 3.12 environment.

Review found two first-import customization cases where capturing an overridden
regular-expression helper could incorrectly certify it for the C path. Explicit
default-rule checks now select Python for those cases; a pre-import Unicode
normalizer override is covered as well. The failed contract fixtures were fixed,
not omitted. A first microbenchmark accidentally compared inappropriate
reference paths. Its setup errors are retained in the
[diagnostic record](../benchmarks/reports/native-language/development/native_microbench_diagnostic.json.gz),
separately from the later
[seven-round microbenchmark](../benchmarks/reports/native-language/development/native_microbench_v2_raw.json.gz).
Neither record is a formal end-to-end result.

Concurrent local diagnostics encountered transient disk exhaustion and large
timing variation even in untouched SQLite calls. Formal performance measurement
will use a separate hosted runner with sequential paired workers. The local
measurements cannot support a README speedup claim. The runtime is prepared as
the v0.8.0 candidate; acceptance and publication are still pending.

## Frozen hosted protocol

Runtime candidate `22a29df0a920e526d3af594db92728d9b9c16d57` is bound by the
[formal plan](../benchmarks/experiments/native_language_formal_plan.json). The
matrix contains 16 fresh workers, four balanced pairs per cohort, three passes
per configuration, 113,568 timed calls and 56,784 baseline/candidate pairs.
Those are planned counts until the execution report confirms completion.

An independent review of the new evaluator found no blocking timing or equality
issue. Eleven evaluator contract tests passed, including real SDK MCP traffic,
full payload comparison, source offsets, incomplete attempts and tamper
rejection. The managed local environment lacks the usual child-process procfs
entry; the tiny protocol fixture explicitly marks its resource reading as
unavailable. The hosted measurement retains the strict Linux resource checks.
Both implementations execute the same fixed dispatch probe before ingestion or
timed queries; the native probe must actually call all five C helpers.

The [candidate diagnostic](../benchmarks/reports/native-language/development/candidate-profile.json.gz)
and [its runner](../benchmarks/reports/native-language/development/candidate-profile-runner.py)
retain the variable local environment result. They are separate from the frozen
hosted execution, and are not used to infer an end-to-end speedup.
