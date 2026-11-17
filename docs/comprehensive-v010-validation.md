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

## Delivery status

The first complete candidate passed all 11 CI jobs in
[run 44006128221](https://github.com/Afloat16/AI-Memory-Book/actions/runs/44006128221).
Its Windows job passed the real native executable and PowerShell installer
smoke plus all 53 capture/import/export/isolation tests. Final source still
requires fresh exact-commit CI and the full release matrix before publication.

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
