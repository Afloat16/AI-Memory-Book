# v0.3.2 / round-four continuation checkpoint

## Current stage

Protocol registered before development measurements at `4f239ea`. Development begins from
`ea0541326f6869cd32a9573a111134622ec6b38c`; the named baseline is published
v0.3.1 at `7b7a5d7336b9350a128f5e0a888811b1b3015e68`. Their runtime files are
identical. The first bounded v0.3.2 candidate is implemented; no formal timing
or fresh quality score exists at this checkpoint.

The v0.3.1 development profile completed all 4,732 calls. Its complete
non-timing payload hashes and source-free profiler data are preserved in
`benchmarks/reports/round4-development/baseline-manifest.json` and eight
individually compressed cell files. These timings include profiler overhead
and are not a formal performance claim. The runtime candidate retains source
reads and corruption validation inside the existing SQLite snapshot, delays
certified source parsing until needed, bisects sorted projection starts, and
reuses the exact count of the last accepted context. The first candidate
runtime SHA-256 is `ca8d2d1a227252d4048780ac4b6ed8eac7d2c931fa99b1338a238f490fc9e02f`.

All 41 token tests (17 fresh) passed, including actual SDK MCP and a concurrent
writer; both installer release-routing tests passed after the v0.3.2 bump.
Independent runtime and formal-harness reviews are in progress. These are
development checkpoints, not acceptance or release approval.

The [registered plan](../benchmarks/experiments/round4-plan.json) targets
complete-output-equivalent reductions in token-budget source preparation,
projection and final counting. Actual MCP token1024 is added to the balanced
performance matrix. Quality rankings, Q2, schemas and dependencies remain
unchanged. Older project-statistics and novelty candidates remain rejected.

## Safe next steps

1. Preserve old-data development profiles and fresh correctness fixtures.
2. Implement and independently review one bounded combined candidate.
3. Commit candidate, evaluator and dependency/source binding before formal timing.
4. Execute the new claimed hosted run once, committing each completed worker.
5. Freeze component/model inputs before ID-only selection of another 256 IDs;
   exclude all three historical selections, execute one complete comparison,
   and retain costs and negative results.
6. Publish only after the fixed gates and exact-commit release checks pass.

Progress is preserved on `optimization/v0.3.2-round4`. Never overwrite original
experiment files or repeat a completed measurement to select a faster result.
Read the latest branch and this checkpoint before resuming after interruption.
