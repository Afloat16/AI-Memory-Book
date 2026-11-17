# v0.10.0 development records

These original local diagnostic observations are retained before the dedicated hosted comparison. They are not publication gates or end-to-end performance claims.

- `semantic-runtime-development.json`: original full v1 component run, including the 32,768-window candidate/baseline wall-time ratio of 1.692. Its evaluator hashes predate the current v2 script; its semantic candidate source hash matches the implementation checkpoint.
- `semantic-runtime-cpu-diagnostic.json`: separate wall/process-CPU diagnostic. It does not replace or explain away the adverse first result.
- `semantic-runtime-v2-smoke.json`: reduced-size v2 evaluator smoke, not a full default-fixture experiment.
- `semantic-runtime-source-manifest.json` and `semantic-targeted-tests.log`: semantic source identity and targeted verification.
- `installer-environment-audit.json`: synthetic owned-package reproduction of inherited Python environment and working-directory shadowing in the v0.9.0 installer. No private data was used.

Tracemalloc records tracked peak allocations, including NumPy-tracked buffers where applicable. It does not establish total process RSS or all SQLite/native allocations. Model verification uses deterministic synthetic artifacts and mock runtimes; it excludes real model inference and ONNX/tokenizer initialization costs.

## Additional retained development checks

The `.gz` files are deterministic gzip copies of the original local bytes.

- `directory-validation-v1.*.gz` retains the first **untimed** fixture rejection: session segmentation intentionally leaves a whole session page. The adaptive fixture correction in `directory-validation-v2.*.gz` validates all nine configurations before hosted timing; all three segmentation modes have explicit golden tests.
- `windows-ci-44003125307.log` records the genuine capture metadata issue corrected by comparing each stat API with itself. The next real Windows job passed all 41 capture/import/export tests.
- `python310-ci-44004377239.log` records a test-cleanup compatibility failure. Restoring a permissive SQLite authorizer fixes Python 3.10 cleanup while retaining the denial and transaction assertions.
- `windows-installer-ci-44005500056.log` records a test probe that printed a Unicode installation path without explicit UTF-8. The product launcher had already succeeded; the probe was corrected to use the same explicit UTF-8 setting.
- Installer diagnostics retain the initial local compiler-fallback smoke and an overly broad source-build test assertion, followed by the corrected checks. Actual final native smoke and the owned, offline PEP 517 source installation pass. Application, pip and proxy settings remain in the environment; only inherited Python import routing is removed from nested pip builds.
