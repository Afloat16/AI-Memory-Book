# Engineering memory development evidence — 2026-11-15

Read [the results and limitations](../../../docs/engineering-memory-results.md)
and [the experiment protocol](../../../docs/engineering-memory-evaluation.md)
before interpreting these records. These are synthetic development experiments,
with a fixed policy consumer and a pinned external search component. They do not
measure LLM-generated patches or real developers' longitudinal productivity.

## Contents

- `summary.json`: the derived comparison, including both character budgets,
  paired wins/losses, timing distributions, and integrity checks.
- `final/`: the complete baseline/candidate/candidate/baseline matrix. Each
  block contains a targeted replay, native engineering workflow, and external
  component comparison. `execution.json` records the commands and exit codes.
- `workflow-*`, `components-baseline`, and `targeted-*-smoke.json.gz`:
  earlier development observations. These are not pooled into final timings.
- `components-interrupted/`: the interrupted dependency preparation attempt;
  no searches or scored queries were produced.
- `candidate*-store.py.gz` and `candidate*-tests.py.gz`: the three development
  candidates. The pre-fix failure records are retained alongside them.
- `validation.json` and test logs: test results and any environment or historical
  fixture failures, recorded separately from benchmark measurements.
- `independent-recomputation.json`: an independent rescore of saved contexts
  and reconstruction of common component packs, without new timed runs.
- `document-compression.json`: original and compressed hashes for the 31
  checkpoint document bundles. `artifact-manifest.json` covers the saved files.

## Reading and reproducing

Large JSON, JSONL, source snapshots, and logs are stored as deterministic gzip
files. Decompression restores the exact original bytes. Paths embedded in the
original execution/checkpoint records remain unchanged; if a named file is not
present, look for the same path with `.gz` appended. Host-specific scratch paths
identify the original execution; they are not required local install paths.

Recompute the final summary from the committed evidence:

```bash
python scripts/summarize_engineering_memory.py \
  --input benchmarks/results/engineering-memory-20261115/final \
  --output .artifacts/engineering-summary.json
```

The summary reader accepts compressed records directly. To inspect a raw file,
use Python's `gzip.open(path, "rt", encoding="utf-8")` or `gzip -dc path`.
Quality cases are counted once per version and budget; repeated calls provide
timing samples, not additional independent tasks. Native excerpts and the
component comparison's common whole-block packing are different interfaces and
must not be combined into one score.
