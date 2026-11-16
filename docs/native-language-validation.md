# Native text acceleration: frozen validation

The v0.8.0 candidate replaces five measured text-processing loops with a
CPython C extension. In this frozen experiment, all **56,784 paired results**
matched, and all **113,568 timed calls** passed the recorded source, scope and
budget checks. At the default 2,400-character budget, pooled p95 latency fell
**9.44% for direct recall and 8.15% for MCP on synthetic61**, and **2.07% and
1.85% on public1015**. These are results on one host and two existing regression
datasets, not a whole-product or cross-platform speed guarantee.

## Delivery status

**Performance validation is complete; delivery acceptance is pending.** The
first native wheel matrix, [43826370750](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43826370750),
exposed macOS architecture-tag and Windows checkout-line-ending defects after
native behavior tests passed. Commit `ef9b4eaf970101dc0b225225ab6f1de220abc8ee`
preserves LF source bytes and explicitly builds/verifies the declared Mach-O
architecture. The repaired full matrix,
[43826807431](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43826807431),
is pending at this checkpoint. Its configuration is not proof of successful
wheels. The raw evidence destination below is being finalized.
The current `main` branch and published release remain v0.7.0; this document does
not announce a published v0.8.0 release. Update this paragraph only after checking
the final source, complete CI, durable evidence and actual distribution results.

## Contract and frozen sources

The change translates `terms_ascii`, `ascii_tokens`, `unicode_tokens`,
`fold_excerpt_source` and `evidence_units`. Python keeps normalization and
retrieval decisions. SQL, ranking, project isolation, source coordinates,
pagination, identifiers, budgets and query-cache policy retain the reference
contract. The Python implementation remains available for differential checks
and unsupported platforms; supported helper overrides use that reference path.
No retrieval algorithm change or cross-request cache was introduced to obtain
these measurements.

| Role | Frozen source |
|---|---|
| Python baseline | [`b1434ca8b218d096d5506aaea02631ca31306d21`](https://github.com/Afloat16/AI-Memory-Book/tree/b1434ca8b218d096d5506aaea02631ca31306d21) |
| C runtime candidate | [`22a29df0a920e526d3af594db92728d9b9c16d57`](https://github.com/Afloat16/AI-Memory-Book/tree/22a29df0a920e526d3af594db92728d9b9c16d57) |
| Evaluator and registered plan | [`b0d3e6157394bda44d5abb468d75dff6472a1692`](https://github.com/Afloat16/AI-Memory-Book/tree/b0d3e6157394bda44d5abb468d75dff6472a1692) |
| Original execution | [43822446202, attempt 1](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43822446202) |

The [development record](native-language-development.md) retains profiling,
unsuitable local timing observations, implementation reviews and Unicode tests.
It is separate from this hosted result. Later packaging changes do not replace
the frozen runtime or create new performance samples.

## Method and measurement boundaries

The [registered plan](../benchmarks/experiments/native_language_formal_plan.json)
uses 16 fresh sequential workers on one Ubuntu 24.04 hosted VM: two datasets,
four paired rounds, two implementations. Order is **AB, BA, BA, AB**. Each worker
executes three seeded passes of four configurations. Every started attempt and
completed sample is retained; there are no selectively discarded samples,
timed-call warmups or replacement measurements.

Synthetic61 contains 112 sessions, 1,408 turns and 168 questions; public1015
contains 216 sessions, 4,684 turns and 1,015 questions from the fixed LoCoMo
text-evidence split. Each implementation contributes 2,016 samples per synthetic
configuration and 12,180 per public configuration. These previously used datasets
test performance and compatibility; they do not establish new retrieval quality.
The [run manifest](../benchmarks/reports/native-language/formal-run-1/run.json)
records dataset hashes, selection rules, exclusions and LoCoMo's upstream commit
and CC-BY-NC-4.0 license.

Direct timing measures `MemoryBook.recall`, including optional exact token
budget work. MCP timing measures a real official-SDK stdio `call_tool` round
trip: server recall, normal cache write, serialization and transport. Output
validation, hashing and ledger writes are outside these timers. MCP cache
clearing is also outside its timer. No model-generated answer is included.

Query-result caching is disabled for direct recall and cleared before each MCP
call. SQLite and operating-system caches are not cleared; token-count memoization
warms naturally. The direct worker initializes `cl100k_base` before token calls;
each fresh MCP token server retains its natural first-call tokenizer cost.
Token configurations use a 1,024-token limit and an 8,000-character ceiling.

Both implementations execute the same fixed dispatch probe before ingestion and
query timing. The candidate must call each of the five C helpers; probe wrappers
must then be restored. Each worker verifies source and binary identities before
and after execution. The hosted environment used CPython 3.12.16, SQLite 3.45.1,
Unicode 15.0.0, MCP 1.30.0, Pydantic 2.14.3 and tiktoken 0.12.0, with four allocated
CPUs on an AMD EPYC 9V45. GCC 13.3.0 built the extension with explicit `-O3` and
`MEMORY_BOOK_BUILD_NATIVE=1`; the [build manifest](../benchmarks/reports/native-language/formal-run-1/build-manifest.json)
preserves the command, compiler, flags and build-log hash.

## Recall latency

All times are milliseconds. Reduction is `100 × (1 − C / Python)`; it is a
latency reduction, not the same percentage increase in throughput. Pooled
percentiles use all retained samples. The final column gives the minimum and
maximum p95 reduction across the four paired rounds.

| Dataset | Configuration | Python p50 | C p50 | p50 reduction | Python p95 | C p95 | p95 reduction | Round p95 reduction range |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| synthetic61 | Direct, 2400 chars | 2.775376 | 2.415524 | 12.966% | 7.454618 | 6.751034 | 9.438% | 8.574–9.771% |
| synthetic61 | MCP, 2400 chars | 3.835108 | 3.518497 | 8.256% | 8.681968 | 7.974309 | 8.151% | 7.074–9.091% |
| public1015 | Direct, 2400 chars | 2.238762 | 2.176644 | 2.775% | 2.885779 | 2.825964 | 2.073% | 1.843–2.734% |
| public1015 | MCP, 2400 chars | 3.316449 | 3.247910 | 2.067% | 4.008595 | 3.934267 | 1.854% | 0.714–3.783% |
| synthetic61 | Direct, 1024 tokens | 2.842992 | 2.699330 | 5.053% | 8.188481 | 6.910682 | 15.605% | 15.020–15.796% |
| synthetic61 | MCP, 1024 tokens | 3.934098 | 3.778724 | 3.949% | 9.328370 | 8.066220 | 13.530% | 13.646–13.867% |
| public1015 | Direct, 1024 tokens | 1.873899 | 1.796302 | 4.141% | 2.239264 | 2.153733 | 3.820% | 3.460–3.941% |
| public1015 | MCP, 1024 tokens | 2.980843 | 2.886317 | 3.171% | 3.398384 | 3.301476 | 2.852% | 1.550–4.382% |

All 32 scenario/round p95 comparisons improved. The public MCP default-budget
benefit is small and varies across rounds. A pooled percentile need not lie
within the round-level percentage range because it is computed from pooled
samples, rather than averaged round percentiles. Exact values, means, extrema
and each round are retained in [summary.json](../benchmarks/reports/native-language/formal-run-1/summary.json).

## Ingestion, startup and memory

The following values are medians of four workers per implementation and dataset.
Fresh and unchanged ingestion improved in all paired rounds. Four observations
on one host provide limited evidence for startup or resource conclusions; these
are not independent deployments or a cross-platform capacity study.

| Measurement | Synthetic Python → C | Public Python → C |
|---|---:|---:|
| Fresh ingestion | 670.943 → 568.428 ms (15.28% lower) | 691.191 → 580.852 ms (15.96% lower) |
| Unchanged reingestion | 52.099 → 40.646 ms (21.98% lower) | 103.263 → 70.537 ms (31.69% lower) |
| API import | 24.086 → 24.857 ms (3.20% higher) | 24.319 → 24.887 ms (2.34% higher) |
| MCP initialization, char2400 | 353.994 → 355.359 ms | 352.490 → 355.237 ms |
| RSS after ingestion | 42.342 → 42.521 MiB | 44.973 → 44.973 MiB |
| Worker RSS after all calls | 128.668 → 129.307 MiB | 138.719 → 138.766 MiB |
| Worker high-water RSS | 132.580 → 132.936 MiB | 148.982 → 149.199 MiB |

API import means importing `MemoryBook` after the common evaluator/bootstrap
imports, not full process or CLI startup. It regressed by approximately
0.57–0.77 ms. MCP initialization did not consistently improve across configurations.
Memory was approximately unchanged or slightly higher; no memory-saving claim is
supported. These worker memory snapshots also include benchmark bookkeeping and
the token-path workload, so they are not a production server memory forecast.

Checkpointed database sizes matched exactly in every worker: 20,201,472 bytes
for synthetic61 and 13,025,280 for public1015. Direct per-call CPU measures the
calling process; MCP per-call CPU measures the **client only**. Separate server
snapshots include process lifetime activity. The [independent audit](../benchmarks/reports/native-language/formal-run-1/independent-audit.json)
retains min/median/max resource observations and the full timing definitions.

## Equality and offline audit

During execution, the frozen evaluator validates project scope, source spans,
page projections, context reconstruction, response metadata, result limits and
character/token budgets. It hashes complete native/MCP payloads, context and
MCP envelopes. Only native `latency_ms` is excluded from native response equality.
Archive comparisons cover the source tables and index contents, excluding only
declared host-generated timestamps. All checks passed; archive, ingestion,
reingestion, protocol metadata and repeated-query results matched.

After recovery, the original evaluator's exact source hash was checked and its
offline audit reproduced the archived summary exactly using an in-memory ZIP
reader. A separate pass recalculated percentiles from every raw row and checked
paired stable fields, worker-start records, build metadata and the native binary.
All attempt ledgers matched their reports and hashes; no raw timings were replaced.

This offline validation checks recorded output digests and invariants. The
artifact contains output hashes, not all original payload text: it cannot
reconstruct that text or independently rerun source-span validation from hashes.
The execution-time checks and differential tests supply that complementary
evidence. Equality on the tested corpus is not proof for every possible input.

## Durable evidence and reproduction

The full raw destination is the
[`evidence/native-language-formal-43822446202` branch](https://github.com/Afloat16/AI-Memory-Book/tree/evidence/native-language-formal-43822446202).
Keep its original worker reports, attempt ledgers, start markers, logs and build
evidence intact. Main keeps only the four compact JSON files linked above.

The original [Actions artifact](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43822446202/artifacts/14205446971)
is `native-language-formal-43822446202-1`, ID **14205446971**: **69 ZIP members**,
**38,192,300 bytes**, SHA-256
`9c8a2b32458d08d2009011d915e4b6f8c21c49a27d0ddf684bbb8334b54ef0a3`.
Its recorded expiration is **2026-12-16 07:22:12 UTC**; durable Git evidence must
remain usable after that deadline. The independent audit lists all 69 member
hashes. The compiled measurement binary is bound to SHA-256
`a7b4ca0126508b33f95ffe5fbf97159022509647531a5762eec5fa597ad4e7d6`.
It is measurement evidence, not a portable installation artifact.

To re-audit preserved raw files, use the frozen evaluator commit and its pinned
dependencies, materialize the original report directory, then run:

```bash
python scripts/native_language_performance.py --audit benchmarks/reports/native-language/formal-run-1
```

That command audits existing evidence without collecting new timings. The four
compact files alone are insufficient; raw worker reports and attempt ledgers
are required. A new measurement is a separate run and must preserve its own
attempts and provenance.

## Installation and backend selection

The release matrix targets CPython 3.10–3.15 with the GIL on Linux
x86-64/AArch64, macOS Intel/Apple Silicon and Windows x64. Each wheel must build,
install, pass native behavior tests and produce a receipt binding its source,
ABI, platform and installed binary hash. The installer resolves compatibility
tags using its own isolated Python environment and verifies the selected wheel
and loaded extension before activation. Other environments retain a
compiler-free Python fallback. Platform build status is stated above.

For a source build, `MEMORY_BOOK_BUILD_NATIVE=1` requires a supported CPython
and a C compiler; `MEMORY_BOOK_BUILD_NATIVE=0` builds the Python fallback. The
default `auto` build may fall back if the toolchain is absent. The extension does
not currently target free-threaded CPython. Existing schema-4 archives require
no migration for this execution-language change.

Use the same Python interpreter as the installed application:

```bash
python -I -c "from memory_book._text_backend import BACKEND_NAME; print(BACKEND_NAME)"
```

`native` confirms the extension loaded; `python` identifies the reference path.
Before importing the package, `MEMORY_BOOK_TEXT_BACKEND=auto` allows native loading
with Python fallback, `python` forces the reference, and `native` requires the
extension and fails if it is unavailable. For a portable check that requires the
native backend in a fresh process:

```bash
python -I -c "import os; os.environ['MEMORY_BOOK_TEXT_BACKEND']='native'; from memory_book._text_backend import BACKEND_NAME; assert BACKEND_NAME == 'native'; print(BACKEND_NAME)"
```

A source checkout or successful Python installation alone does not establish
native execution. Confirm the active backend after installation; platform-wheel
availability remains subject to the delivery status above.
