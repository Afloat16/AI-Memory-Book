# Frozen suffix-scope correction replay

The unchanged [original probe](../resumed-suffix-scope-review-attempt1/probe.py)
was executed on v0.11 baseline `78cc906d81818a16884de7de2e613e5a56346f93`
and corrected candidate `021a384567db5aa64fde155f090d2eb399f55c03`.
The probe SHA-256 remains
`73f941662352da8a11e78499cdec1cfec55ebef67f2fedbbb34f68ee04d34389`.
Neither the original failed attempt nor its scenarios were changed.

## Results

Each row below describes the same two negative statement formulations, one
valid causal update, three old-record counts (2/8/104), and two temporal modes.
The primary comparison uses the Python reference with the same interpreter as
the original review. Native runs are explicitly additional consistency checks,
not more independent questions.

| Backend | Responses per arm | Candidate incorrect promotions in six negative settings | Valid causal update | Relevance payload changes |
|---|---:|---:|---:|---:|
| Python reference | 18 | 0/6 | 3/3 | 0/9 |
| Native | 18 | 0/6 | 3/3 | 0/9 |

The four regressions introduced by candidate `01032a69`—two suffix formulations
with 8 or 104 old records—are all resolved on each backend. With only two old
records, the v0.11 baseline still incorrectly promotes both negative statements;
these old failures remain in the full records, and the corrected candidate
retains the decision in both settings. The valid causal update is recovered in
3/3 settings by the corrected candidate, compared with 1/3 by the baseline.
These are configuration counts of three authored formulations, not general
accuracy percentages or independent quality-question counts.

The complete Python/native replies and original-page follow-ups agree after
excluding only `latency_ms`, for all 18 cells in each runtime arm. The fresh
Python baseline also agrees with the original attempt's baseline under that
same comparison. Every latency remains recorded; this is not a speed experiment.

## Source and saved-record verification

`execution.json` records every exact command and interpreter, all tracked
runtime-file hashes verified against the requested Git commit, actual package
and backend imports, and native-extension paths and SHA-256 values. The source,
probe and native binary were unchanged before and after each execution.
`execution_driver.py` preserves the exact driver bytes and original absolute
execution paths; its hash matches the execution record.

All four arm directories retain complete raw responses, source sessions,
project-scoped page follow-ups and their own original probe source inventories.
The separate `audit_saved.py` does not call retrieval. Its verified result in
`audit.json` checks all **72 responses**, the complete request matrix, every
original source body, complete page reference, source/excerpt coordinates,
project scope, one-result limit, 1,200-character budget and exact citation
framing. It recomputes every first-source label and the comparisons above.

The auditor also verifies the actual execution wrapper against each probe
record, checks complete Git source inventories and authenticates the recorded
native binaries. Rerunning that audit requires the recorded source worktrees
and native binaries to remain available at their recorded paths:

```sh
python benchmarks/reports/v0.12-development/resumed-suffix-scope-review-attempt2/audit_saved.py \
  --output /absolute/path/to/new-suffix-audit.json
```

To execute the original probe again, use the commands in the failed attempt's
README with fresh output paths and the corrected source commit above. Use
`MEMORY_BOOK_TEXT_BACKEND=native` for the separately labeled native arms. Do not
overwrite either saved attempt. This review establishes recovery of these
specific source-scoping cases and controls; complete source-suite, broader
benchmark and publication acceptance remain separate.
