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

## Hosted comparison and delivery

The dedicated hosted protocol, complete raw results, independent review and
exact-commit release verification are recorded before publication. Current
implementation checkpoints are development candidates until those gates pass.
No local timing result is presented as a universal or end-to-end speedup.

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
