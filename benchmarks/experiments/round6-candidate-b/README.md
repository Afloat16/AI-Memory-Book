# Candidate B: rejected dense-project FTS ranking

Source commit: `e89737ce82baffd349e84d01184113142c0de602`.
Runtime SHA256: `01ce749679af461d03c3499d5423ffa82d73fe190fb318327301b58a643edf52`.

The implementation passed its nine-job source CI, 4,732 old-data complete payload comparisons and 2,304 historical Hotpot comparisons. Its sole balanced development run `43595785770` nevertheless regressed public native p95 by 19.49–29.00% and actual MCP token1024 p95 by 23.92%. Both AB and BA rounds show the public regressions. B was not advanced to formal acceptance and is excluded from the release candidate.

These two test files are preserved byte for byte from the B source checkpoint. They exercise the rejected private connection and dense-ranking implementation; they are archived outside the active test discovery tree because the active runtime has been restored exactly to A. To reproduce B's tests, check out its source commit in a separate worktree and run the original test paths from that checkout. Do not enable these tests against the different active A runtime.

The original source, plan, bindings, per-worker records, attempt ledgers, adverse values and CI remain in Git. See `benchmarks/experiments/round6-candidate-b-plan.json`, the round6 development reports for run `43595785770`, and `benchmarks/reports/round6-startup-source-selection.json`. The original recall gates remain unchanged and unpassed; the separately registered startup confirmation must stand on its own evidence.
