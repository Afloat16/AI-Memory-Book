# Original v0.13 scale run 1 evidence

This directory retains the exact ZIP returned by GitHub Actions for run
[44314074983, attempt 1](https://github.com/Afloat16/AI-Memory-Book/actions/runs/44314074983),
artifact 14430799762, as ten ordered binary parts. Concatenation recovers the
original 29,249,994 bytes with SHA-256
`a15df28d653c08dbd447e4ec3308c79df43ac7ebd997d8baab88706c92c1fed3`.
It is not a reconstructed or filtered results archive.

The source is `9ea37a7c72aec21b6f106d9631d72d72199e283b`, baseline
`8044e4bafe18e73ea422af5eeb47ef961e65246c`, and the protocol was frozen at
`b3fd165cb632c439ff28873fdba7f33e9d258178` before any formal query.
All 13,608 registered API measurements and 84 arm blocks completed. The original
CI audit, raw responses, observations, input fingerprints, build identities,
logs, failed-quality records and per-case scores are inside the ZIP.

**Completed execution is not quality acceptance.** The initial candidate and
baseline both missed the current-policy evidence in all eight multi-source
cases at every checkpoint. Each stage's recall completeness was 48/56; the
8/8 directory completeness result is a separate channel. These original
failures must remain visible when a later candidate is evaluated. No universal
superiority, constant-time scaling or calibrated abstention follows from this run.

Restore from this checkout, using a new destination path:

```sh
python benchmarks/reports/v0.13-scale-run1/restore.py --output /YOUR/NEW/PATH/v013-scale-run1.zip
```

The script verifies every part and the full original ZIP. Reading the archive
directly with Python's zipfile avoids allocating an 85,495,124-byte extracted
copy. The original workflow excluded large SQLite working snapshots; recorded
hashes and the deterministic ingestion generator remain. This does not claim
an independent restoration of those databases.
