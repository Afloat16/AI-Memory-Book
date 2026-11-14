# C4 fixed full-cohort development result

One preregistered native AB/BA run completed all 18,928 calls. All 9,464 full non-timing output pairs match published v0.3.2, and every recorded count/source/index/revision/cache invariant passes. All eight worker files and the exact aggregate are retained as gzip of their original bytes.

Aggregate pooled p95 across eight native cells improves 11.3339%, but public token512 and token1024 improve only 12.7253% and 8.8411%; public token2048 p95 increases 1.3269%. This development run provides insufficient margin for the fixed public/MCP formal gates. C4 was not formally rerun or represented as accepted. The separately prepared C4 formal evaluator and auditor remain unused preparation, not new measurement evidence.

[Summary](summary.json) retains every pooled and per-round cell, including public token2048 round1 p95 +11.4748%. [Original complete aggregate](manifest.json.gz) retains all samples. Source C4 is 0141adf1dde6cd69cf96d8eea23f4b6ebab36477, runtime 1c7c644c5187332e6fb5034fef0e232b5c1ae1e5f352b53fea90f7fd8acc4fb3. The source-bound helper is scripts/round5_c4_development_pair.py, SHA256 335bf2ab5eeb6e2701bbdc8e6205fbadf4f73106d31a6359932cd0cae53df8df. No query-result caching or competitor timing was used.
