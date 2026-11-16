# Frozen native-language experiment evidence

This branch preserves all 69 files, byte for byte, from the successful first
attempt of [run 43822446202](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43822446202).
No performance call was repeated and no timing sample or original summary was replaced.
The ZIP container itself is not duplicated in Git; its identity and every extracted
member's SHA-256 are recorded in `evidence-manifest.json`.

- Artifact: `native-language-formal-43822446202-1` (ID `14205446971`; 38,192,300 bytes).
- Artifact SHA-256: `9c8a2b32458d08d2009011d915e4b6f8c21c49a27d0ddf684bbb8334b54ef0a3`.
- Python baseline: `b1434ca8b218d096d5506aaea02631ca31306d21`.
- Native runtime: `22a29df0a920e526d3af594db92728d9b9c16d57`.
- Frozen evaluator: `b0d3e6157394bda44d5abb468d75dff6472a1692`.
- Verified: 113,568 timed calls, 56,784 paired calls, complete output/archive equivalence.

`benchmarks/reports/native-language/formal-run-1/` contains the original run, summary, workers, attempt ledgers,
start intents and logs. `.artifacts/native-language-formal/` contains the original build log,
build manifest and measured extension. The extension is retained as evidence;
it is not a supported distributable wheel and does not need to execute to audit results.

## Offline audit

With Python 3.12, from this branch's root, run:

```sh
PYTHONDONTWRITEBYTECODE=1 python frozen-evaluator/scripts/native_language_performance.py --audit benchmarks/reports/native-language/formal-run-1
```

The audit uses only the standard library and retained report bytes. It does not
download the dataset, load the measured extension, invoke MCP, or remeasure queries.
Compare its JSON result with the original `benchmarks/reports/native-language/formal-run-1/summary.json`.
`frozen-evaluator/` retains every evaluator-manifest file at its measured SHA-256.
`audit.json` records the successful exact-summary check performed before this branch
was created. Keep native and MCP timing boundaries distinct and retain negative
secondary results when interpreting the original summary.
