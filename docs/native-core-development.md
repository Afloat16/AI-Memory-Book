# Broader native core migration after v0.8.1

The user requested a substantially wider rewrite after the two additional
helpers released in v0.8.1. This round starts from native release
`56eccd8c3a6f1d5637664607936da2595ce50c62`, with seven native helpers already
active. Earlier Python-to-native and v0.8.0-to-v0.8.1 results remain separate,
immutable experiments.

All five new implementation families are integrated. The first frozen broad
candidate, `0be1f09502aff1d4ddc0a9e644be7a62be6a944f`, completed its
formal experiment and independent audit but was not accepted: unchanged
reingestion became slower in all four rounds of both cohorts. The guard-only
refinement at `cff1d9a3c183bf3c84183476f0485926f55abe56` also retained a
local reingestion regression. Further constant reuse and selection of the
faster original Python joining path produced the final 22-entry scope. The
cross-version-compatible candidate is now
`4390d013986ab9c96b49cc6964f075f3866f21ee`. Its complete formal experiment
and independent raw-data audit pass. The [final validation report](native-core-validation.md)
and [acceptance record](../benchmarks/experiments/native_core_acceptance.json)
record the final gains, retained costs and exact delivery/publication status.
This document preserves the full development history, including rejected paths.

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
`cff1d9a3`. The final scope removes the unhelpful, unreleased
`joined_turns` entry and retains `segmentation_ready`, for 22 entries: seven
from the released baseline and fifteen new entries.

| Implementation unit | New entry points | Responsibility |
| --- | --- | --- |
| [`_native_lexical.h`](../src/memory_book/_native_lexical.h) | `strip_nonspacing_marks`, `identifier_has_boundary` | Whole-string removal of nonspacing marks using the running interpreter's Unicode category function, and the existing fixed ASCII identifier-boundary predicate. |
| [`_native_excerpt.h`](../src/memory_book/_native_excerpt.h) | `excerpt_window` | Complete candidate-window construction, source-unit coverage, sliding counts, score comparison and original-text rendering. |
| [`_native_rank.h`](../src/memory_book/_native_rank.h) | `rank_candidates`, `select_novelty`, `context_allocations`, `refs_from_parsed` | Batch scoring and stable ordering, the existing bounded novelty-selection loop, cited character-budget allocation and source-reference clipping. |
| [`_native_source.h`](../src/memory_book/_native_source.h) | `source_units`, `projected_units`, `source_map_matches` | Original-turn evidence units, their projection onto pages and source-map validation used by exact-token packing. Tokenizer behavior and final budget checks remain unchanged. |
| [`_native_segmentation.h`](../src/memory_book/_native_segmentation.h) | `make_turns`, `page_cuts`, `build_pages`, `segment_turns`, `segmentation_ready` | Conversation grouping, paragraph/newline cuts, continuation pages, sections and live dependency/class checks without a result cache. Joining remains the original Python implementation. |

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

## Constant reuse and measured path selection

The readiness-only refinement exposed another execution cost: repeated C API
construction of attribute names and dictionary keys. The implementation now
keeps 27 immutable names/separators in each extension module's own state.
Multiphase initialization, traversal, clearing and freeing manage those
references. Actual attributes, dictionaries, globals, class states and
helper identities are still read live at the original positions; no business
result or readiness decision is cached.

The complete fixed-shape diagnostic showed that the public C joining wrapper
remained slower than the original Python `_joined` in all three tested
shapes, even after name reuse. The selected candidate removes that unreleased
C entry and its wrapper. An independent review verifies that `_joined`'s
AST equals released v0.8.1. The C page builder's body is unchanged: it still
checks the current `_joined` identity and calls the current global function
at the original point. This is the
[recorded path selection](../benchmarks/reports/native-core-refinement/development/joined-path-selection.json)
and [independent review](../benchmarks/reports/native-core-refinement/development/joined-selection-independent-review.json).

### Complete refinement experiment

[Run 43883672930](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43883672930),
frozen at evaluator `0267f6cce5189e42ce9432e228366372e121cf38`,
compared exact candidate `e91183bf` with released v0.8.1. All 113,568 calls /
56,784 pairs are equivalent, and an
[independent raw-artifact audit](../benchmarks/reports/native-core-refinement/formal-run-1/audit-receipt.json)
reproduces the recorded statistics and frozen summary.

All eight pooled query p50/p95 cells improved. The default character-budget
p95 reductions were 3.5916% / 4.2348% for synthetic direct/MCP and
7.9025% / 8.5187% for public direct/MCP. Unchanged reingestion totals improved
3.3207% and 4.9371%, with all four rounds improving in each cohort. Fresh
ingestion totals improved 5.3559% and 1.9868%.

These pooled values retain uneven rounds: public direct-character p95
regressed 1.2009% in round two and improved 36.7286% in round three;
public fresh ingestion regressed 4.4361% and 1.7030% in rounds one and four.
The [full metrics extract](../benchmarks/reports/native-core-refinement/formal-run-1/metrics-extract.md)
retains all eight cells, all individual rounds and every startup, CPU, memory,
binary and storage cost. This experiment used an AMD EPYC 9V45 host, distinct
from the first broad experiment's EPYC 9V74; their absolute times and
percentages are not a continuous before/after series.

### Cross-version compatibility finding

The e911 wheel matrix then found a strict exception difference on CPython
3.14 and 3.15. Their exact tuple/list/dict unpack failures report the actual
container size; the new C readiness guard still emitted the older wording.
This candidate was therefore
[not accepted for release](../benchmarks/reports/native-core-refinement/formal-run-1/decision.json),
even though its measured query and ingestion results improved.

Candidate `4390d013986ab9c96b49cc6964f075f3866f21ee` matches those
version-specific messages. Other iterators and subclasses retain the same
bounded `N + 1` consumption and original error behavior. Only error
formatting changes; normal source grouping, callbacks, guards, ranking,
coordinates, budgets, SQL and caches remain unchanged. The
[official-source review](../benchmarks/reports/native-core-compatibility/development/unpack-message-independent-review.json)
and [implementation receipt](../benchmarks/reports/native-core-compatibility/development/native-core-unpack-compatibility-fix.json)
record the CPython sources and added strict differential cases.

Core CI now includes Python 3.14 and 3.15 as well as 3.10, 3.12 and 3.13.
Publication requires exactly the full eleven-job set, including every
installer, MCP, browser and container job; the old nine-job-only set is
insufficient.

## Final candidate verification

The selected runtime is exactly `4390d013`, with release runtime SHA256
`6ec51c906de94c97f90ec9be3dc50d066c9abedcff283c1e118ef6d6847eb3b7`.

| Gate | Observed evidence |
| --- | --- |
| Exact-source CI | [Run 43885311822](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43885311822), all eleven jobs successful. Python 3.14 and 3.15 each discovered 1,415 tests with 144 optional skips; MCP discovered 1,415 with 16 skips. |
| Ordinary native suites | 144 tests: 142 passed, two optional tiktoken tests skipped locally; no compiler warning. |
| ASAN/UBSAN | The same 144 tests passed with the same two optional skips, no sanitizer diagnostic, and unchanged source/test bytes. All three module-lifecycle tests actually ran, including shared-GIL subinterpreters. |
| Effective dispatch | The released baseline's seven helpers and the candidate's 22 helpers all produced effective native results in the identical common fixture. No helper returned `NotImplemented`; readiness executed 36 times. Ordinary and singly wrapped outputs all match. |
| Protocol validation | 26 tests passed without skips, including a real stdio MCP fixture; 14 timing/statistics/probe AST contracts equal the preceding frozen evaluator. |

The [CI receipt](../benchmarks/reports/native-core-compatibility/development/native-core-4390d013-ci.json),
[ordinary native receipt](../benchmarks/reports/native-core-compatibility/development/native-core-4390d013-144tests.json),
[sanitizer receipt](../benchmarks/reports/native-core-compatibility/development/native-core-4390d013-asan-ubsan.json)
and [complete probe archive review](../benchmarks/reports/native-core-compatibility/development/probe-4390d013-review.json)
retain the exact identities and qualifications. One local optimized-build
configuration produced identical Python 3.12 binaries across the version-gated
error fix; separate builds containing path/debug information have different
complete binary hashes. Neither observation substitutes for the final
exact-source hosted experiment.

## Final formal experiment and delivery

The [protocol 5 plan](../benchmarks/experiments/native_core_compatibility_formal_plan.json)
was frozen at `cfdb3ca2c8ff2d71792e820923057d6613ea08b7` before the single
first-attempt [run 43886529702](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43886529702).
It compares exact 4390 with released native v0.8.1 in the full unchanged
113,568-call / 56,784-pair matrix and binds both earlier experiments. The
independent auditor was
[registered before results](../benchmarks/reports/native-core-compatibility/development/artifact-auditor-preregistration.json)
and independently reviewed. There are no selective reruns or replaced samples.

All recorded outputs, source positions, archives and indexes match, with only
the direct diagnostic `latency_ms` excluded. The
[independent audit](../benchmarks/reports/native-core-compatibility/formal-run-1/independent-audit.json)
verifies the 77,821,913-byte artifact, 151 manifest files, 227,136 ledger events
and the exact frozen summary without re-executing the application. The
[immutable evidence commit](https://github.com/Afloat16/AI-Memory-Book/tree/51e8d022c164ba714f68db562c9ae280a62c2312)
and reports checkpoint `c2edd920` preserve the results independently of the
Actions artifact's retention period.

All eight pooled query cells improve at p50/p95. Default 2400-character
p95 reductions are 1.8233% / 2.6446% for synthetic direct/MCP and
5.7909% / 3.5134% for public direct/MCP. Synthetic direct-character round
two p95 regresses 0.8917%; public token-budget MCP round one p50/p95
regress 0.7751% / 3.1778%. Those values remain in the
[complete metrics extract](../benchmarks/reports/native-core-compatibility/formal-run-1/metrics-extract.md).

All four paired batches improve for every ingestion cell. Four-batch total
reductions are 9.2758% / 10.3855% for synthetic/public fresh ingestion and
2.9652% / 3.9370% for unchanged reingestion. API import adds 2.043 / 2.197 ms,
ending worker RSS adds 0.232 / 0.018 MiB, startup results are mixed and the
extension grows 519,480 bytes on this host. The final EPYC 7763 host differs
from the preceding EPYC 9V45 and original EPYC 9V74 hosts; their absolute
times and percentages remain separate evidence.

Native delivery remains pending. Two complete attempts using the frozen
4390 runtime did not satisfy the one-run/one-attempt 30-cell gate:
[43885419074](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43885419074)
finished with 28 wheels passed and two unallocated macOS ARM jobs cancelled;
[43888785867](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43888785867)
then also encountered an unallocated cancelled macOS ARM job. Their successful
packages are not mixed into a passing matrix.

The [runner investigation](../benchmarks/reports/native-core-compatibility/development/native-core-macos-runner-investigation.json)
first retained the second run when allocations resumed. After the additional
cancellation, the [recovery plan](../benchmarks/reports/native-core-compatibility/development/native-core-macos26-recovery-plan.json)
changes only the ARM hosted image label from macOS 15 to the officially
supported, explicit macOS 26 ARM image. All 30 cells, native architecture,
deployment-target rules, installed tests and exact receipt gates remain.
A fresh complete preparation must pass on that workflow. This does not change
the application runtime or add a performance experiment.

Publication still requires the final approved runtime/commit, all eleven
exact-commit CI jobs, a fresh full release matrix, verified assets and an
actual public default installation. v0.8.1 remains the published release at
this checkpoint.

The final [acceptance record](../benchmarks/experiments/native_core_acceptance.json)
binds runtime SHA256
`6ec51c906de94c97f90ec9be3dc50d066c9abedcff283c1e118ef6d6847eb3b7`.
Final publication requires the exact approved main commit, all eleven CI jobs,
a fresh complete native-wheel matrix, verified release assets and a real
public-installer check. Earlier development, interrupted preparation and
failed compatibility runs retain their own identities; they are not
final-publication receipts.
