# v0.10.0 development records

These original local diagnostic observations are retained before the dedicated hosted comparison. They are not publication gates or end-to-end performance claims.

- `semantic-runtime-development.json`: original full v1 component run, including the 32,768-window candidate/baseline wall-time ratio of 1.692. Its evaluator hashes predate the current v2 script; its semantic candidate source hash matches the implementation checkpoint.
- `semantic-runtime-cpu-diagnostic.json`: separate wall/process-CPU diagnostic. It does not replace or explain away the adverse first result.
- `semantic-runtime-v2-smoke.json`: reduced-size v2 evaluator smoke, not a full default-fixture experiment.
- `semantic-runtime-source-manifest.json` and `semantic-targeted-tests.log`: semantic source identity and targeted verification.
- `installer-environment-audit.json`: synthetic owned-package reproduction of inherited Python environment and working-directory shadowing in the v0.9.0 installer. No private data was used.

Tracemalloc records tracked peak allocations, including NumPy-tracked buffers where applicable. It does not establish total process RSS or all SQLite/native allocations. Model verification uses deterministic synthetic artifacts and mock runtimes; it excludes real model inference and ONNX/tokenizer initialization costs.
