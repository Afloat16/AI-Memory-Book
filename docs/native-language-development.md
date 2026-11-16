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
