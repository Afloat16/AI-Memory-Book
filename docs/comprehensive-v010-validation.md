# v0.10.0 comprehensive optimization validation

This round compares against released v0.9.0 source
`238c8058f723a203eaca99f94d924ab77de4c0b3`. It reduces repeated work in optional
semantic retrieval and chapter directories, fixes reproduced capture and
installation defects, and strengthens release verification. The 22 native
entry points and lexical recall algorithms remain unchanged.

## Compatibility boundary

The archive remains on schema 4. Normal retrieval outputs retain source/page
IDs, source coordinates measured in Unicode code points, project scope,
ranking, segmentation, character/token budgets and cache behavior. Existing
schema-4 archives need no migration.

- Semantic ranking keeps the original SQL ordering, 4,096-row numerical
  boundaries, NumPy operation, per-page winning window, tie behavior and final
  sorting. Every vector is still checked for dimensions and finite values.
  Cursor cleanup runs on success, empty queries and exceptions.
- Model initialization validates one retained byte snapshot before importing
  optional runtimes and passes those exact bytes to them. Identity, fingerprint,
  telemetry opt-out and inference settings retain their existing behavior.
  The public file verifier still streams its input.
- Chapter previews retain pagination, fields, ordering and project checks.
  Standard readers use one coherent snapshot and bounded per-section previews;
  customized section readers keep the original dispatch. Caller-owned
  transactions remain owned by the caller.
- Valid JSONL strings containing U+0085/U+2028/U+2029 now survive import and
  partial-tail recovery. Physical record separators remain LF, CRLF and CR.
  This corrects previously rejected valid input.
- Import reads enforce the existing 64 MiB limit on actual bytes, including
  files that grow after the initial stat check.
- Windows worker-status queries use a process handle and a zero-time wait;
  they do not send a signal. POSIX permission-denied results retain a live
  process indication. Malformed PID values are rejected before probing.

## Development records

The [original local records](../benchmarks/reports/comprehensive-v010/development/)
remain unchanged, including adverse observations. The first full semantic v1
run measured a **1.692 candidate/baseline wall-time ratio** for 32,768 windows.
Its separate process-CPU diagnostic does not replace that result or establish
why the wall times varied. A later reduced v2 run validates the evaluator only.

That first run measured tracked allocation peaks of 85,005,064 and 28,637,125
bytes for the 32,768-window fixture, and 16,580,073 and 16,547,361 bytes for
4,096 windows. Tracemalloc may include NumPy-registered buffers; these values
do not measure total process RSS or every SQLite/native allocation.

The synthetic model-artifact fixture contains 127,535,388 bytes. Verified
artifact reads and hashes fall from 255,070,776 to 127,535,388 bytes. Mock
runtimes exclude actual ONNX loading, tokenizer parsing, inference and answer
generation. This establishes less verification work without predicting
full-model startup time.

## First frozen hosted comparison

[Run 44006165023](https://github.com/Afloat16/AI-Memory-Book/actions/runs/44006165023)
completed on attempt 1 from candidate `3c9b271a6d9757af09a435b80198dd02b94c1146`.
Its parentless [evidence commit 780a99fa](https://github.com/Afloat16/AI-Memory-Book/tree/780a99faa71da50eb0bf6e290fddc765e2b49b43)
retains 239 raw files, including 220 frozen runtime/evaluator inputs. The
standard-library auditor reproduces all summaries and verifies the complete
ledgers without remeasurement. The independent review also checks each raw
file hash and the frozen bytes against their original commits.

The runner used Ubuntu 24.04, CPython 3.12.16, NumPy 2.5.5 and SQLite 3.45.1.
Both arms use the same component dependencies and the Python text backend.
The native code is unchanged and outside this component comparison. Four
alternating AB/BA rounds retain every observation; allocation trials are
separate from latency trials. These are warm synthetic component measurements,
with no new model-inference, full-recall, MCP or retrieval-quality claim.

### Semantic resource and latency results

| Component | Baseline median | Candidate median | Median paired wall-time change |
|---|---:|---:|---:|
| Ranking, 4,096 vector windows | 19.330 ms | 19.659 ms | **+1.41%** |
| Ranking, 32,768 vector windows | 188.620 ms | 176.934 ms | **−6.38%** |
| Verified artifact initialization with mock runtimes | 200.899 ms | 117.187 ms | **−41.50%** |

Positive changes mean more elapsed time. The small-window case is slower in
all four paired observations, by about 0.329 ms between pooled medians; this
regression is retained. The large-window case improves in every pair. Paired
percentage changes are medians of the four candidate/baseline ratios, so they
need not equal the percentage change between the two pooled medians.

Tracked peak allocations for 32,768 windows fall from **85,005,064 to
28,637,125 bytes (−66.31%)**; the 4,096-window case falls from 16,579,344 to
16,546,632 bytes (−0.20%). Both allocation pairs produce the same values.
The cursor audit confirms 4,096-row batches and explicit closure. Per-page
winning-result metadata still grows with the number of matched pages.

Artifact reads and hashes each fall from **255,070,776 to 127,535,388 bytes**.
Identity and the exact bytes supplied to the mocked runtimes remain equal.
Actual tokenizer parsing, ONNX model loading and inference are excluded.
[Raw semantic report](https://github.com/Afloat16/AI-Memory-Book/blob/780a99faa71da50eb0bf6e290fddc765e2b49b43/raw/reports/semantic-runtime.json).

### Directory candidate 1: rejected

The first directory implementation reduced SELECT counts to five through a
compound preview query, but **seven of nine configurations became slower in
all four paired rounds**. It is not accepted for release as an optimization.

| Sections | Preview pages per section | Median paired wall-time change |
|---:|---:|---:|
| 1 | 1 | +5.23% |
| 1 | 20 | +15.10% |
| 1 | 100 | +20.11% |
| 20 | 1 | −9.47% |
| 20 | 20 | +22.79% |
| 20 | 100 | +33.08% |
| 100 | 1 | −12.48% |
| 100 | 20 | +27.76% |
| 100 | 100 | +36.82% |

CPU results agree with the direction of each wall-time result. All 1,440 calls
pass exact output and bounded-materialization checks; correctness does not
turn the regressions into a speedup. The
[rejection decision](../benchmarks/experiments/comprehensive_v010_directory_v1_decision.json)
and [raw directory report](https://github.com/Afloat16/AI-Memory-Book/blob/780a99faa71da50eb0bf6e290fddc765e2b49b43/raw/reports/directory-runtime.json)
remain unchanged. A separately frozen directory-only comparison evaluates the
replacement that keeps batch counts and uses the original indexed per-section
LIMIT/OFFSET query. The semantic source and its first-run evidence are retained.

### Directory candidate 2: accepted

[Run 44008503529](https://github.com/Afloat16/AI-Memory-Book/actions/runs/44008503529)
completed on attempt 1 from frozen source `d5876b6e7640623d4ce3d63cb649b0401dc578d0`.
Its [evidence commit 248e74ee](https://github.com/Afloat16/AI-Memory-Book/tree/248e74ee4aabd7f53835e5aead67aa8e8f63abbb)
retains all 232 original files, including the unchanged workload, frozen sources,
raw observations and complete event ledger. The new evaluator changes only its
plan path and protocol ID; the first evaluator and its rejected results remain
unchanged. The semantic source is byte-identical to the first hosted candidate.
Independent review verifies all 232 raw file hashes and all 219 frozen inputs
against their original commits, then reproduces the frozen audit with zero
remeasured calls. The hosted preflight passes all 20 focused tests.

All **1,440 timed calls** and **1,487 ledger events** pass the exact payload,
serialized order, query-count and materialization checks. The prospective gate
requires every median paired wall ratio to be at most 1.05 and strict improvement
for both 20 × 20 and 100 × 20. All nine configurations pass without waivers.

| Sections | Pages per section | Baseline median | Candidate median | Median paired wall-time change |
|---:|---:|---:|---:|---:|
| 1 | 1 | 0.075810 ms | 0.075093 ms | −0.48% |
| 1 | 20 | 0.138099 ms | 0.140058 ms | +1.07% |
| 1 | 100 | 0.399630 ms | 0.403592 ms | +0.42% |
| 20 | 1 | 0.521635 ms | 0.415196 ms | −20.48% |
| 20 | 20 | 1.857856 ms | 1.757063 ms | −5.31% |
| 20 | 100 | 7.339468 ms | 7.193670 ms | −1.86% |
| 100 | 1 | 2.387888 ms | 1.813116 ms | −23.97% |
| 100 | 20 | 9.004408 ms | 8.417977 ms | −6.46% |
| 100 | 100 | 38.011260 ms | 37.251585 ms | −1.98% |

All six multi-section configurations improve in every paired round. The two
single-section regressions are retained: 1 × 20 rises by about **1.96 microseconds**
between pooled medians, and 1 × 100 by **3.96 microseconds**. Each regresses in
three of four pairs; 1 × 1 also has one regressing pair despite its lower median
paired ratio. Process-CPU summaries have the same configuration-level direction.
These warm synthetic directory measurements do not establish cold-cache, full
recall, concurrent-load or end-to-end gains.

The accepted implementation uses 5, 24 and 104 SELECTs for 1, 20 and 100 sections,
versus 6, 63 and 303 at baseline. It retains the baseline indexed page query for
each section and releases each raw row list after conversion. At the maximum
100 × 100 request, only 100 raw previews are read ahead of conversion, and
content length is evaluated exactly 10,000 times. The returned output itself
still grows with the requested number of previews.

[Raw directory report](https://github.com/Afloat16/AI-Memory-Book/blob/248e74ee4aabd7f53835e5aead67aa8e8f63abbb/raw/reports/directory-runtime.json)
· [Frozen acceptance audit](https://github.com/Afloat16/AI-Memory-Book/blob/248e74ee4aabd7f53835e5aead67aa8e8f63abbb/audit.json).

## Acceptance and delivery

The [explicit acceptance decision](../benchmarks/experiments/comprehensive_v010_acceptance.json)
binds both component experiments to runtime digest
`d00d84ef8436c97b45de5e5e5c2b67883ffbc03992cffa10e7f6d35a15e7fd16`.
It retains all small-fixture costs, rejects directory candidate 1, and states
the remaining exact-source publication gates. The large-fixture resource and
latency benefits justify semantic streaming while the small-fixture regression
remains visible; no claim is made that every workload is faster.

The first complete candidate passed all 11 CI jobs in
[run 44006128221](https://github.com/Afloat16/AI-Memory-Book/actions/runs/44006128221).
Its Windows job passed the real native executable and PowerShell installer
smoke plus all 53 capture/import/export/isolation tests. The frozen second
directory candidate and evaluator also pass all 11 jobs in
[run 44008145062](https://github.com/Afloat16/AI-Memory-Book/actions/runs/44008145062).
Publication requires fresh exact-commit CI, the complete 30-cell release matrix,
all 67 asset checks and the actual public installer. Final evidence is kept
separately in the
[publication-proof branch](https://github.com/Afloat16/AI-Memory-Book/tree/validation/comprehensive-v0.10.0-publication-proof),
so the release source and historical observations remain fixed.

## Reproduced reliability and installation fixes

Windows capture tests use a real owned child process: repeated status probes
must leave it running, and exit code 259 must still be recognized as an exited
process. The first Windows CI then exposed a separate completed-file-update
failure. Path and descriptor metadata can report different ctime semantics;
capture now compares ctime before/after through the same API, while comparing
file identity, size and mtime across APIs. Regressions retain concurrent-write
rejection, including changes that restore the original size and mtime.

JSONL regressions retain LF, CRLF and CR physical records while preserving
U+0085, U+2028 and U+2029 inside valid message strings. Capture still defers
partial UTF-8 or incomplete JSON tails and imports their later completion.
Import reads stop at the existing limit plus one byte, so a file that grows
after its initial metadata check cannot cause an unbounded read.

The installer reproduction used owned synthetic modules in the working
directory and `PYTHONPATH`, plus an invalid `PYTHONHOME`. Managed launchers,
bootstrap helpers and package probes now use `-I -X utf8`. Pip's copied child
environment removes those two Python variables to protect nested build hooks;
application variables, pip/proxy configuration and the caller's environment
retain their behavior. The Windows executable is generated through the
existing pip-vendored launcher facility with explicit interpreter arguments.

The three operating-system installer jobs exercise actual installed launchers,
Unicode paths, environment isolation, default extras, reinstall and failed-stage
rollback. Newly generated isolated MCP commands retain those flags; services
also receive `-u` explicitly. Existing configurations must be regenerated and
their processes restarted to gain the new command flags. Source-based,
nonisolated configurations keep their existing interpreter prefixes.

The original Windows capture failure, Python 3.10 test-cleanup incompatibility,
and Windows installer-test encoding failure remain in the development evidence.
Their corrected checks passed before the final publication gate; successful
runs do not replace those earlier records.

## Release verification changes

Native wheel and cell-evidence artifact names include both workflow run ID
and attempt. Aggregation selects that same attempt; existing 30-cell receipt
provenance checks remain required. Native cell testing accepts exactly one
complete 144-test outcome and only the explicitly named optional skips.
Unexpected skips, expected failures and duplicate or inconsistent summaries
prevent a receipt from being issued.

The current [release runbook](releasing.md) documents all 11 CI jobs, all 30
native build/install/test cells and the 67-asset release contract. Historical
experiments and frozen auditors remain untouched.
The new [offline publication audit](comprehensive-release-audit.md) connects
the same run/attempt's original logs and artifacts to the public download bytes,
source commit, main and tag without rebuilding or remeasuring.
