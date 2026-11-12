# Round-three recovery checkpoint — 2026-11-13

Continue from integration commit `93cea9544d024708d8fa9a423914bb255b9476d1`.
The registered plan, runtime candidates and frozen evaluators remain unchanged.

## Recovered evidence

- The formal performance run [43246417515](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43246417515) finished all **47,320 calls and 16 workers**. Complete non-timing payloads and invariants passed; its separate saved-row audit succeeded.
- All original files are preserved from result commit `35b8618a078fe377ecd6c5acc331c1281dbf61e7` under [round3-performance-43246417515-1](../benchmarks/reports/round3-performance-43246417515-1/).
- The registered numeric timing gate passed: pooled-cell p95 geometric mean improved **11.3587%**, and the best public native p95 improved **26.0501%**. No pooled p50/p95 cell regressed by more than 5%.
- The automatic acceptance field remains **false** because public1015 fresh native database opening increased from **34.4557 to 39.2941 ms mean (+14.0423%)**, requiring explicit cause analysis and independent review. Do not relabel this as an interrupted measurement or rerun it to obtain a faster sample.
- Old-data project-statistics evidence was partly uploaded before interruption. Recover the existing complete worker files and chunked transfer before considering any missing work. A failed quality candidate must remain unshipped under the original plan.
- The next Hotpot256 selection and its source/evaluator/model/component binding have not yet been created. Freeze all identities before selecting IDs or scoring.

## Remaining work

1. Finish a separate startup-resource review while retaining the unmodified raw report and all four rounds.
2. Recover and strictly assess all eight project-statistics workers, retaining any losses and transfer failures.
3. Freeze the accepted implementation, complete comparison evaluator, model and three upstream component identities.
4. Select the registered new 256 IDs, commit that manifest, and execute the same-host native/component comparison with per-stage durable publication.
5. Publish current results and limits, run the exact-commit release checks, and finish v0.3.1.

## Durable continuation

Use `optimization/v0.3.1-round3` for integration. Do not push incidental changes to the one-shot performance trigger branch. Use existing Git object IDs for published evidence and small atomic tree/commit updates for new text; the prior partial chunk upload is evidence to recover, not a reason to upload all historical blobs again.

No completed performance or model request is replayed by this checkpoint.
