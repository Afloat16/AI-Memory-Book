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
