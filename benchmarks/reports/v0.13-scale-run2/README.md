# Original v0.13 longitudinal run 2 artifact

This directory permanently retains the exact original GitHub Actions ZIP for
[run 44331778554, attempt 1](https://github.com/Afloat16/AI-Memory-Book/actions/runs/44331778554).
The original ZIP was split into ten binary parts without recompression or
modifying any member. All parts, offsets, byte counts and SHA-256 hashes are
listed in [manifest.json](manifest.json).

| Identity | Value |
|---|---|
| Candidate | `e0e2515f6e16404cfb9b676cd2eab01ce84b81cc` |
| Baseline | `8044e4bafe18e73ea422af5eeb47ef961e65246c` |
| Frozen protocol | `b3fd165cb632c439ff28873fdba7f33e9d258178` |
| Job | `134897797385` |
| Original artifact | `14439324717`, `v013-long-history-main-44331778554-1` |
| Original ZIP bytes | 29,394,152 |
| Original ZIP SHA-256 | `47df01825bf4e14baadf3154a24683e5f18aaa238790e013fde381610be6ceac` |
| ZIP inventory | 570 members, 85,698,042 uncompressed bytes |

The downloaded bytes matched the original artifact API's size and digest;
ZIP CRC checks also passed. [artifact-api.json](artifact-api.json) and
[run-api.json](run-api.json) preserve decoded API snapshots. A real restoration
from the saved parts independently reproduced the original ZIP digest:
[restore-verification.json](restore-verification.json). That temporary duplicate
was removed after verification; the original download and all parts remain.

From a clone containing these parts, restore to a new destination:

```sh
python benchmarks/reports/v0.13-scale-run2/restore.py --output /absolute/new-run2-artifact.zip
```

The script refuses to overwrite an existing file and checks every part before
accepting the final complete byte count and digest. This is exact artifact
reassembly, not a fresh experiment. The original workflow excluded working
SQLite databases and compressed database snapshots; their hashes, fingerprints
and generation protocol remain inside the artifact. Saved-response audits do
not independently restore those databases.

See the [independent run-2 saved-response review](../v0.13-development/scale-run2-review/)
for quality and latency analysis. Archival integrity and successful workflow
execution are separate from evidence completeness or speed claims. The
[original run-1 artifact](../v0.13-scale-run1/README.md) and all failed development
attempts remain unchanged.
