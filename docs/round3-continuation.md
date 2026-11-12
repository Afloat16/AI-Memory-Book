# v0.3.1 continuation checkpoint — 2026-11-13

The current continuation starts from `93cea9544d024708d8fa9a423914bb255b9476d1`
on `validation/v031-round3-integration`. The published baseline remains v0.3.0
at `dd2f88be742ed330269e7dd5915b6f75089d7fef`. The older
`continuation-status.md` describes the completed earlier experiment, not this
unfinished round.

## Current reconciled checkpoint

Both original experiments are now fully audited without replay. The formal
query-speed gate passed and its startup resource exception is independently
reviewed. The quality candidate failed 14 registered checks and remains
excluded; all 8,082 calls were recovered and independently matched against the
canonical hosted recovery byte for byte.

An earlier hosted registration appeared during recovery. Its existing
[comparison run 43267797247](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43267797247)
is authoritative. The later local selection reproduced its exact IDs/dataset
but was never scored. See [reconciliation](round3-reconciliation.md),
[performance review](round3-performance-review.md), and
[quality recovery review](round3-quality-review.md).

The lists below retain the initial recovery inventory and planned completion
order; they are not a second request to rerun completed measurements.

## Recovered work

- Runtime, plan, frozen performance evaluator, comparison evaluator and
  interruption-safe hosted controller are already committed.
- Performance run `43246417515`, result commit
  `35b8618a078fe377ecd6c5acc331c1281dbf61e7`, completed all 47,320 calls and
  16 workers. Its numeric query-speed gate and strict payload audit passed.
  Its automatic acceptance remains false because public native startup mean
  increased by 14.04%; an explicit resource review is outstanding. This
  continuation will preserve the original results and will not repeat timing.
- Four quality-screen workers are preserved at
  `36dbd82c4070968bfb7d7e2b93e1e4793907145e`. Additional evidence transfer
  stopped at commit `2bd5f27d1ae478c1735f36b5354fddd81114182b`, checkpoint
  48 of 78 chunks. Recover complete original files by content and hash before
  considering any further execution. Preserve incomplete files as such.
- No round-three new-cohort binding, selection or completed comparison was
  present at recovery. Do not treat old comparison numbers as v0.3.1 results.

## Completion order

1. Verify recovered quality files, apply the original one-candidate gate and
   retain all losses. A failed project-statistics candidate stays unshipped.
2. Record independent source review and the explicit startup resource review.
3. Commit source, evaluator, model and upstream identities before selecting the
   registered 256 new HotpotQA IDs. Preserve the original selection protocol.
4. Execute the existing hosted comparison sequentially. Publish every finished
   stage before starting the next; retain failed or interrupted stages.
5. Publish current measured comparisons, accepted runtime changes, release
   notes and validation status. Keep previous tags and experiment bytes intact.

Work is checkpointed on `optimization/v0.3.1-completion`. Commits and remote
pushes happen at each meaningful checkpoint. Large existing reports should
reuse Git objects or normal Git transfer rather than chat-sized blob payloads.
The authoritative acceptance rules remain
[`round3-plan.json`](../benchmarks/experiments/round3-plan.json).
