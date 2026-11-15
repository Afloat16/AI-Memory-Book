# Current developer engineering evidence

This directory retains a source-level validation of identifier normalization,
current-turn token packing, schema-4 migration and archive maintenance.
Read the [analysis and limitations](../../../docs/developer-engineering-validation.md)
and the [developer workflow](../../../docs/engineering-workflows.md).

| Files | Purpose |
|---|---|
| `summary.json` | Paired raw-output audit, source/data/evaluator identities, improvements and losses |
| `audit.py.gz` | Exact retained-output audit source used in the recorded workspace; its original paths and source-manifest inputs are retained as execution provenance |
| `dataset.json.gz` | Identical chronological synthetic workload used by all four runs |
| `baseline-workflow/`, `current-workflow/` | Native strategies at both 1200 and 2400 characters, with complete returned responses |
| `baseline-components/`, `current-components/` | Same-page, whole-block Book/billion-context comparison; native responses and common-packer outputs are retained separately |
| `default-profile/` | 80-case default/explicit equality; `reference.json` identifies this iteration's explicit run as the reference |
| `regressions/` | Token reproduction, independent migration/old-writer checks, installed-wheel and complete CLI examples |
| `tests.json`, `baseline-tests.log.gz`, `current-tests.log.gz` | Final local full-suite results and environment |
| `manifest.json` | SHA-256 and byte size of each retained evidence file |

The baseline is verified source from upstream `a0de3f48`; its local materialized
checkout has a different local Git history. The candidate's recorded local Git
commit is also not a published upstream commit. Runtime file hashes identify the
measured code. Earlier frozen experiment files were not rewritten.

Reports and raw records preserve their original runtime paths, timings and
metadata. JSONL files are gzip-compressed without changing their decompressed
bytes. The current package still reports the existing version string; the local
wheel check is not a release publication. These are synthetic development
diagnostics, not LLM coding-accuracy or production-performance measurements.
