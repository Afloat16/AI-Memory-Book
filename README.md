# Comprehensive runtime evidence

Hosted run 44006165023, attempt 1, source `3c9b271a6d9757af09a435b80198dd02b94c1146`.
Preservation audit: **complete**. Incomplete or differing output is retained and fails the job.

`evidence-manifest.json` hashes every original byte under `raw/`, including failed or partial reports, logs and ledgers.
`raw/source-manifest.json` binds the frozen source, workflow, evaluator and prospective protocol.
This is component evidence; all regressions remain visible and no universal or end-to-end speedup is claimed.
Allocation values are tracemalloc-tracked peaks, including NumPy registered buffers, not total RSS or untracked SQLite/native allocations.
