# Broader native core migration after v0.8.1

The user requested a substantially wider rewrite after the two additional
helpers released in v0.8.1. This round starts from native release
`56eccd8c3a6f1d5637664607936da2595ce50c62`, with seven native helpers already
active. Earlier Python-to-native and v0.8.0-to-v0.8.1 results remain separate,
immutable experiments.

All five new implementation families are integrated. The first frozen broad
candidate, `0be1f09502aff1d4ddc0a9e644be7a62be6a944f`, completed its
formal experiment and independent audit but was not accepted: unchanged
reingestion became slower in all four rounds of both cohorts. The current
refinement at `cff1d9a3c183bf3c84183476f0485926f55abe56` has passed
correctness checks, but its local reingestion diagnostic also retains a
regression. v0.9.0 remains a development candidate; this document does not
approve or announce a release.

The [development plan](../benchmarks/experiments/native_core_plan.json) defines
the boundary. SQL, transactions, database schema, public interfaces, ranking
policies, scope, source identities, budgets and caches retain their existing
behavior.

## Implemented native families

One optional CPython extension contains the following implementation units,
included and registered by
[`_native.c`](../src/memory_book/_native.c). The five headers initially added 15
entry points to the seven already present in v0.8.1. A live segmentation
readiness check was subsequently translated to C, making 23 entry points at
`cff1d9a3`.

| Implementation unit | New entry points | Responsibility |
| --- | --- | --- |
| [`_native_lexical.h`](../src/memory_book/_native_lexical.h) | `strip_nonspacing_marks`, `identifier_has_boundary` | Whole-string removal of nonspacing marks using the running interpreter's Unicode category function, and the existing fixed ASCII identifier-boundary predicate. |
| [`_native_excerpt.h`](../src/memory_book/_native_excerpt.h) | `excerpt_window` | Complete candidate-window construction, source-unit coverage, sliding counts, score comparison and original-text rendering. |
| [`_native_rank.h`](../src/memory_book/_native_rank.h) | `rank_candidates`, `select_novelty`, `context_allocations`, `refs_from_parsed` | Batch scoring and stable ordering, the existing bounded novelty-selection loop, cited character-budget allocation and source-reference clipping. |
| [`_native_source.h`](../src/memory_book/_native_source.h) | `source_units`, `projected_units`, `source_map_matches` | Original-turn evidence units, their projection onto pages and source-map validation used by exact-token packing. Tokenizer behavior and final budget checks remain unchanged. |
| [`_native_segmentation.h`](../src/memory_book/_native_segmentation.h) | `make_turns`, `joined_turns`, `page_cuts`, `build_pages`, `segment_turns`, `segmentation_ready` | Conversation grouping, joined source references, paragraph/newline cuts, continuation pages, sections and live dependency/class checks without a result cache. |

The existing seven entry points remain `terms_ascii`, `ascii_tokens`,
`unicode_tokens`, `identifier_aliases`, `literal_positions`,
`fold_excerpt_source` and `evidence_units`. All implementations keep CPython
Unicode code-point coordinates and Python objects at public boundaries.

Exact Python reference bodies remain available for portability, differential
verification and supported customizations. `MEMORY_BOOK_TEXT_BACKEND=python`
selects the reference backend; unsupported ordinary-input shapes, subclasses
and changed dynamic dependencies use the relevant reference body. Keeping these
bodies in the repository is intentional. Repository language percentages do not
measure how much work a running request executes in C.

The implementation preserves source grouping and page identities, arithmetic
and tie order, query-term order and frequency, and character/token accounting.
Excerpt scoring retains integer position sums, Python integer true division,
Counter deletion/reinsertion order and the original `math.log1p` /
`math.fsum` functions. Segmentation retains short-circuit order, the existing
separator-size accounting, shallow sharing of nested reference lists and key
evaluation before headline callbacks. Source units retain Unicode line breaks,
fences, sentence boundaries, map errors and exact reconstruction. Guarded
fallbacks are designed to avoid replaying observable custom callbacks.

## Validation and checkpoints

The read-only native v0.8.1 profile was frozen before implementation, including
source and binary identities; see the
[profile findings](../benchmarks/reports/native-core/development/v0.8.1-profile-findings.md).
Independent oracle tests and public-entrypoint dispatch checks accompany each
family. The wider candidate and its new formal protocol must be frozen before
hosted A/B measurement. Earlier frozen plans, evaluators and results are not
rewritten to accommodate this round.

### Development findings retained

The first integrated 17-helper candidate compiled successfully. Its initial
59-test differential run exposed Unicode translation deletion semantics,
Counter method certification and a SQLite internal-cache trace comparison.
These findings were fixed rather than removed from the checks. Checkpoint
`5ebb695d9635134d9bad3ccf643dc3720c10236c` then passed 62 of 63 focused
tests, with one token-extra test skipped locally. The hosted core and MCP jobs
at that stage each ran 1,312 tests and identified a subprocess path error:
native imports were forced from an unbuilt checkout instead of the actual
installed package. Subprocess tests now use the loaded package location. The
token-dependent ranking tests passed in the MCP job.

Independent review found that a pre-import `functools.wraps` modification
of `Counter.__missing__` could change the Python excerpt but be incorrectly
certified for native execution. Certification now checks actual code origin
and globals as well as runtime method identities. It also covers inherited
`__contains__` and `__getattribute__` behavior used by the original
Counter path. Regressions check changed output coordinates, callback counts
and exceptions, including replacements that preserve a function's metadata.

Segmentation testing caught the ASCII-only format-string requirement of
`PyUnicode_FromFormat` for continuation-page titles; the middle dot now
uses a Unicode code-point conversion in an ASCII format string. Review also
found that a custom key inserted into an ordinary Turn instance dictionary
could invoke equality code during field lookup. The preflight now rejects
non-string dictionary keys before reading any fields. A collision-key
regression verifies that native preflight performs no callback and the Python
fallback retains the original exception and callback behavior.

The local workspace was replaced during development. Recovery used committed
Git checkpoints and saved blobs. All post-recovery local timings are
correctness diagnostics, not speed comparisons against the earlier host.
The [independent family-build receipt](../benchmarks/reports/native-core/development/segmentation-core-local-37tests.json)
records its deliberately isolated package scope. The full integrated checks
below supersede it for repository-wide correctness coverage.

### Verified integrated checkpoint

For exact source commit
`0be1f09502aff1d4ddc0a9e644be7a62be6a944f`:

| Check | Observed result and evidence |
| --- | --- |
| Complete hosted CI | [Run 43868862846, attempt 1](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43868862846) completed successfully with all nine jobs passing: core on Python 3.10, 3.12 and 3.13; MCP; installers on Linux, macOS and Windows; container integration; and the real-browser reader. |
| Full core and MCP discovery | The inspected Python 3.12 core job reported 1,349 tests with 141 skips. The MCP job reported 1,349 tests with 16 skips. Both completed successfully; these totals include their skipped optional tests. |
| ASAN and UBSAN | The [instrumented receipt](../benchmarks/reports/native-core/development/native-core-0be1f095-asan-ubsan.json) records one combined AddressSanitizer/UndefinedBehaviorSanitizer build and all eight native-backend suites: 132 tests, 130 passed and two optional tokenizer tests skipped, exit code 0, with no sanitizer diagnostic. |

The sanitizer run verified all 34 materialized source/test files against the
commit's Git blobs and recorded their SHA256 hashes. It used GCC 14.2.0,
`-fsanitize=address,undefined`, `-fno-sanitize-recover=all`,
`PYTHONMALLOC=malloc` and the preloaded ASAN runtime. The receipt includes
the complete runner, compiler command, environment, binary identity and logs.
CPython and SQLite themselves were not sanitizer builds; leak detection was
disabled for the embedding CPython process. The two skips require the optional
`tiktoken` dependency. These checks establish the recorded correctness and
memory-access results, not a speed improvement.

## First formal attempt: retained and not accepted

[Run 43871304560](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43871304560)
compares released native v0.8.1 with the 22-helper `0be1f095` candidate.
All 113,568 timed calls / 56,784 paired results are equivalent under the
complete-output, archive, index and source-coordinate checks. Four balanced
AB/BA/BA/AB rounds and three passes per worker were preserved. The
[independent artifact audit](../benchmarks/reports/native-core/formal-run-1/audit-receipt.json)
verified the original ZIP, frozen source/build identities, raw ledgers and
Git evidence publication, replayed the frozen summary exactly, and separately
recomputed the statistics. No application queries were remeasured for that audit.

All eight pooled query p50/p95 cells improved. The four default 2400-character
p95 reductions were 2.8021% / 1.1781% for synthetic direct/MCP calls and
5.5442% / 5.1743% for public direct/MCP calls. These pooled values do not mean
every round improved: the fourth synthetic MCP round regressed for both
character and token budgets.

The acceptance blocker was unchanged reingestion. The four-batch totals were
**19.4149% slower on synthetic61 and 21.4095% slower on public1015**, with
all four individual rounds slower in each cohort. Fresh ingestion totals
improved 6.9361% and 4.3360%, respectively, while one public fresh-ingestion
round regressed. The complete eight-cell, four-ingestion and resource
statistics remain in the [metrics extract](../benchmarks/reports/native-core/formal-run-1/metrics-extract.md),
including startup, CPU, memory, binary size and every negative result.
This candidate was not published.

The first independent auditor was registered before the results. The stricter
eight-field ingestion schema/identity check was added after the results and
is explicitly identified as a
[post-result audit amendment](../benchmarks/reports/native-core/development/artifact-auditor-schema-amendment.json).
The frozen protocol 3 files, timing boundaries, source commits and raw results
were not changed. Passing the audit verifies the evidence; it does not turn a
performance regression into an accepted release.

## Readiness refinement and current validation

A paired diagnostic profile located repeated Python class-field generators
inside the live segmentation check. `segmentation_ready` translates those
checks to C while keeping their dependency scope, short-circuit order,
ordinary descriptor reads and errors. It caches no readiness result, keeps
strong references across callbacks and returns `NotImplemented` before
observable callbacks for unsupported metadata shapes. The preserved Python
guard remains the fallback.

At exact checkpoint `cff1d9a3c183bf3c84183476f0485926f55abe56`:

| Check | Observed result |
| --- | --- |
| Native differential suites | 140 tests: 138 passed; two optional tiktoken tests skipped locally. |
| Sanitizers | The same eight suites passed under ASAN and UBSAN, with no compiler warning or sanitizer diagnostic; the two optional tiktoken skips remain explicit. |
| Full hosted CI | [Run 43876906098](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43876906098): all nine jobs passed. Python 3.12 core discovered 1,385 tests with 142 skips; MCP discovered 1,385 with 16 skips. |
| Public-wrapper dispatch | All 23 helpers produced effective native returns; no helper returned `NotImplemented` in the common fixture. The new readiness method executed 53 times. All singly instrumented outputs matched the uninstrumented outputs and released baseline fixture. |
| New evaluator | Protocol 4's 26 tests passed with no skips in the SDK-equipped diagnostic environment, including a real stdio MCP fixture. Thirteen timing/ledger/probe AST contracts remain unchanged from frozen protocol 3. |

The [local preflight](../benchmarks/reports/native-core/development/native-core-cff1d9a3-local-preflight.json),
[CI receipt](../benchmarks/reports/native-core/development/native-core-cff1d9a3-ci.json),
[sanitizer receipt](../benchmarks/reports/native-core/development/native-core-cff1d9a3-asan-ubsan.json)
and [independent guard review](../benchmarks/reports/native-core/development/segmentation-readiness-independent-review.json)
retain exact source, binary and validation identities.

The subsequent local four-round diagnostic covers both cohorts and retains
all 160 unchanged-ingestion batches, fresh ingestion, complete return values
and before/after source and binary identities. It still shows unchanged
reingestion regressions, including four slower public rounds. Timing noise is
visible and these are development diagnostics, not hosted release results.
Moving the guard alone is insufficient; the remaining segmentation
allocation/call costs are being profiled before another formal experiment.

## Remaining acceptance work

The independently named
[protocol 4 plan](../benchmarks/experiments/native_core_refinement_formal_plan.json)
remains **UNFROZEN**. Its candidate source and 23 helper total/effective/fallback
counts must be frozen after the next measured refinement. It retains the
first rejected attempt as prior evidence and uses the same complete matrix,
with stronger offline ingestion schema checks. There has been no formal
protocol 4 run and no selective replacement of protocol 3 results.

After correctness and a useful measured direction are established, a new
formal run must compare the released native v0.8.1 baseline with the exact
refined runtime. Full output/source/index equality and all resource costs
remain gates. Diagnostic probes are removed before timed calls.

The original candidate's wheel preparation completed 29 native cells; its
remaining macOS arm64 Python 3.12 job was cancelled after staying queued.
The downstream artifact-preparation and installation jobs did not run, and
that attempt is not a complete packaging receipt. The accepted refined
candidate will require a fresh complete 30-wheel preparation matrix,
installed-package checks and a fresh final release build. The exact approved
runtime must then be published and tested through the real installer.

The prior v0.8.1 release remains the completed baseline. No accepted v0.9.0
latency, throughput or resource improvement is claimed while these gates
remain open.
