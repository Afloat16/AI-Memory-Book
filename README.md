# Native core evidence

This evidence-only branch preserves hosted run 43883672930, attempt 1, from source
commit `0267f6cce5189e42ce9432e228366372e121cf38`. Preservation state: **complete-equivalent**.
It compares the already-native v0.8.1 baseline with the frozen native candidate.
Incomplete or differing runs remain evidence; they are not successful results.

`evidence-manifest.json` inventories every retained input with exact byte counts
and SHA-256 hashes. Both native binary/build records and available committed
runtime sources are retained. No data is downloaded or measured to audit this
branch. The original Python-to-native experiment remains separate and unchanged.

For a complete run, reproduce the full summary without executing either runtime:

```sh
PYTHONDONTWRITEBYTECODE=1 python frozen-evaluator/scripts/native_core_refinement_performance.py --audit benchmarks/reports/native-core-refinement/formal-run-1
```

Compare the JSON result with the original `benchmarks/reports/native-core-refinement/formal-run-1/summary.json`.
The frozen auditor requires only the Python standard library. `audit.json`
records whether the preserved summary was reproduced exactly. Raw ledgers,
including started attempts that failed, remain available when no summary exists.
