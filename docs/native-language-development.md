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

## Distribution checkpoint

The installer now resolves a schema-2 release manifest with the newly created
environment's own pip compatibility tags, verifies the selected wheel SHA-256,
and checks the installed default backend and extension SHA before activation.
Historical release URLs still use their original route. The source and local
wheel paths report the implementation that actually loaded. Existing launcher
and installation records remain in place when preparation fails.

The new release preparation path requires receipts for CPython 3.10–3.15 on
Linux x86-64/AArch64, macOS Intel/Apple Silicon and Windows x64: 30 planned native
wheels, alongside the compiler-free Python fallback and source archive. These
platform builds have not yet been executed at this checkpoint. The container
build compiles the extension in a separate stage and verifies native loading in
the final image. Legacy release manifests and assets remain unchanged.

Forty-two local installer/release contract tests passed. Most release cases use
explicit metadata fixtures and must not be reported as platform build results.
The suite includes a real isolated wheel-selection subprocess and a real
historical-package backend probe. Independent review identified and fixed a
packaging incompatibility with auditwheel's explicit zero-byte ZIP directory
entries. Source bytes, wheel RECORD entries, ABI tags and installed binary
hashes continue to be verified.

The general core CI installs no optional MCP dependency. Its tiny real-protocol
fixture now skips explicitly when that SDK is absent; the MCP CI job continues
to execute it. The formal experiment remains pinned to its original evaluator
commit `b0d3e6157394bda44d5abb468d75dff6472a1692`, where the SDK was installed and
all 11 evaluator checks passed before timing. This later CI-only availability
guard does not modify that running checkout, its source hashes or its samples.

## Recovery checkpoint, 2026-11-16

The interrupted conversation left source at `4a05f16a4732d906e0e33ba361657439797542a1`
on `optimization/native-language-v0.8.0`. No reachable raw-evidence branch had
been created. The successful original run `43822446202`, attempt 1, retained
artifact `14205446971` (38,192,300 bytes). Its complete SHA-256 was independently
verified, and the frozen evaluator reproduced its original summary exactly:
113,568 timed calls, 56,784 pairs, no output/archive or recorded invariant
differences. The [validation record](native-language-validation.md) and four
compact JSON reports now contain all primary/secondary results and resource
costs. No timed worker was rerun.

The container-only failure in CI `43823460858` came from the missing `!setup.py`
entry in `.dockerignore`. Repair `c094bdb6344aff48b82b6ed9e430d65f9f00aa7b`
passes all nine CI jobs in run `43826226943`. The subsequent packaging-workflow
checkpoint `d44704de3e72685a17551b9421d154db314468f2` also passes all nine jobs
in `43826369780`. Local forced-native verification executes 75 passing tests
with one explicit optional-tokenizer skip; 28 release/installer tests pass.
All 24 measured runtime/build source-file hashes still match the frozen
candidate. There has been no runtime change during recovery.

The first actual 30-cell wheel matrix `43826370750` found platform packaging
defects after native tests succeeded: Windows checkout converted source to CRLF,
and macOS framework Python selected universal2 instead of the declared target.
Repair `ef9b4eaf970101dc0b225225ab6f1de220abc8ee` applies source LF attributes,
builds the actual macOS architecture and verifies it with `lipo`. Raw compiler
logs are retained separately from accepted wheel artifacts. A fresh exact-commit
matrix is running as `43826807431`; earlier receipts cannot be mixed into it.

The dedicated evidence workflow will preserve all 69 original artifact members,
the measured binary and ten hash-verified evaluator files on
`evidence/native-language-formal-43822446202`, independently of expiring Actions
artifacts. Remaining acceptance gates are that verified evidence ref, the real
complete wheel matrix and installer preparation, final exact-commit CI and
the release's existing main/approved-runtime/public-install checks. Main and
the published release still remain v0.7.0 at this checkpoint.
