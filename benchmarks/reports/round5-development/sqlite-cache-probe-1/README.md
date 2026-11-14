# SQLite page-cache development probe 1

This is a **development diagnostic on published v0.3.2**, not a release acceptance run. No product source was changed. The experiment completed once; all 24 isolated worker records and all 6,144 call observations are retained. The default and two alternatives returned identical complete non-timing payloads for every query/configuration across every round. The original database file hashes remained unchanged.

## Fixed measurement

- Baseline: published `v0.3.2`, commit `692fb959ddf8934c5f516ba3d74ceb4385a2fa82`, runtime SHA-256 `179ab871f4f6ca197efc83b13618cccad4688fd53d4a4af93305b02e78215e93`.
- Old regression inputs: unchanged synthetic61 and public1015 data; first 128 queries in each adapter's existing deterministic order. The manifest retains every selected ID and original query order.
- Compare SQLite's observed default `PRAGMA cache_size=-2000` against `-4096` and `-8192`. This is the database page cache, independent of the disabled application result cache.
- Four balanced orders: default/4 MiB/8 MiB; 8 MiB/4 MiB/default; 8 MiB/4 MiB/default; default/4 MiB/8 MiB. Each alternative has AB/BA/BA/AB ordering relative to default.
- Fresh process, connection and database copy for each worker. Original database files are not modified. The copy is opened normally and then `query_only=ON` is set before calls.
- Complete uncached native `recall` at 4,000 characters and at 1,024 `cl100k_base` tokens with an 8,000-character ceiling; five results maximum. Reference tokenizer is initialized before timing. Only response `latency_ms` is removed from complete payload equality.
- Query shuffles are fixed per round and configuration. No concurrent performance experiment ran. Copying warms the OS file cache; these are not cold-storage measurements. No MCP, ingestion, new retrieval-quality or cross-product comparison was measured.

## Saved observations

Negative changes mean lower latency. Each pooled configuration contains 512 samples per cache size. RSS differences compare mean process snapshots after that configuration's calls; they include the Python runtime and tokenizer as well as SQLite.

| Corpus | Budget | Page cache | Default p95, ms | Alternative p95, ms | p95 change | p50 change | Mean RSS difference, MiB |
|---|---|---|---:|---:|---:|---:|---:|
| synthetic61 | char4000 | 4MiB | 9.8734 | 9.3456 | -5.35% | -5.52% | +2.11 |
| synthetic61 | char4000 | 8MiB | 9.8734 | 9.6190 | -2.58% | -3.34% | +6.43 |
| synthetic61 | token1024 | 4MiB | 15.5565 | 15.5513 | -0.03% | -6.76% | +2.09 |
| synthetic61 | token1024 | 8MiB | 15.5565 | 15.0095 | -3.52% | -13.90% | +6.42 |
| public1015 | char4000 | 4MiB | 2.9744 | 2.7804 | -6.52% | -0.79% | +2.15 |
| public1015 | char4000 | 8MiB | 2.9744 | 3.1340 | +5.37% | -4.50% | +6.28 |
| public1015 | token1024 | 4MiB | 3.5229 | 3.3336 | -5.37% | -1.91% | +2.15 |
| public1015 | token1024 | 8MiB | 3.5229 | 3.3883 | -3.82% | -4.49% | +6.32 |

The 4 MiB setting alone does not establish the full formal performance gates. Its observed public p95 gains are about 5–7% with about 2.1 MiB more process RSS. It remains a possible development ingredient if a later combined candidate has an explicit rationale and separate frozen validation; these observations do not establish the combined result.

The 8 MiB setting has a retained adverse result: public character p95 increases by 5.37%, while process RSS increases by roughly 6.3 MiB. Its larger cache does not provide a consistent advantage in this diagnostic. This record does not hide the regression or select another run.

The short, old-data, single-host measurements have limited precision. The separate 56,784-call native/actual-MCP protocol and its source/resource gates remain mandatory for a release speed claim.

## Files and reproduction

`summary.json` is the original saved summary, and `manifest.json` retains the original plan's checksum, selected query IDs, schedule, source identities and every worker checksum. `r*-*.json.gz` files contain every timed row, payload hash, per-round latency and memory record. External corpus question strings are omitted from the public manifest; the original plan remains in the task workspace, unchanged.

`round5_sqlite_cache_probe.py` is an exact byte-for-byte copy of the measured script, verified against the plan's script SHA-256. It was originally executed from `.artifacts`, and intentionally retains that path convention. To reproduce a new, explicitly labeled diagnostic, copy it back to that location rather than editing the archived source:

```bash
mkdir -p .artifacts
cp benchmarks/reports/round5-development/sqlite-cache-probe-1/round5_sqlite_cache_probe.py .artifacts/round5_sqlite_cache_probe.py
TIKTOKEN_CACHE_DIR=.artifacts/tiktoken python .artifacts/round5_sqlite_cache_probe.py .artifacts/new-sqlite-cache-diagnostic
```

Prepare the published baseline as the repository's sibling `baseline-v0.3.2/src`, the SHA-verified LoCoMo file at `.artifacts/locomo10.json`, and baseline-ingested, closed/checkpointed databases at `.artifacts/round5-development-dbs/{synthetic61,public1015}.db`. The original exact database hashes and sizes are in the manifest. Install the locked tokenizer version `tiktoken==0.12.0` and prepopulate its cache. The script rejects an existing output directory, changed baseline runtime, nonempty source WAL, unexpected default SQLite cache size, any payload budget/cache invariant failure, or a changed input database. Reproduction is another diagnostic and must not replace this saved run.
