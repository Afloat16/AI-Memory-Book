# Round-three execution and recovery reconciliation

## One completed execution

The authoritative source is
[`a0d67b35d074077f43b5cea77954921802d51f44`](https://github.com/Afloat16/AI-Memory-Book/commit/a0d67b35d074077f43b5cea77954921802d51f44).
[Run 43267797247](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43267797247)
completed all ten stages and **9,216 native/component search calls**, with
`complete-verified` status and no validation failures. Its immutable final
result is
[`c99f20531053b1c164fc5a5d3fa8e0c831eeb4de`](https://github.com/Afloat16/AI-Memory-Book/commit/c99f20531053b1c164fc5a5d3fa8e0c831eeb4de).

During recovery, parallel preparations reproduced the same fixed 256-ID
selection. Repository inspection found the earlier hosted run already
executing; the later preparations were retained without starting another
comparison. The actual run, its source, host, model, binding and manifest were
not relabeled. The [machine-readable record](../benchmarks/reports/round3-run-reconciliation.json)
preserves the identities and disposition of all three registrations.

| Registration | Binding commit | Selection/audit commit | Scoring disposition |
|---|---|---|---|
| Authoritative hosted | `c05fd1c453db1e1365ba0c3e4ab359cd8f9017c0` | `a0d67b35d074077f43b5cea77954921802d51f44` | The single completed run |
| Later local | `254979496b24d9b5ad0a38f3884d479de0fb5db1` | `6f9050df09982c254bc6809830a85b5abb71f6ca` | Unused; zero retrieval/model inference calls |
| Later hosted freeze | `9c9c47006e62f935471a56a2ed669bd7dd78cd07` | `2e7769636c3c5423f82d5e3bd74f3c4cfd5d80c6`; independent preparation audit `383127451c3c3db65b516d44e60a3dbe4fb8f8ff` | Unused; zero retrieval/model inference calls |

The executed binding SHA256 is
`740361f1767a942887bdb7639b1be0223ae1c6dc2fc3b941f845d038884f842f`;
its manifest SHA256 is
`b29545eb90f89744d86e3f8822b838c44a1846be057161b1905f6c977b7b1ae5`.
The local unused binding SHA256 is
`1651d77fc1fbfbc2605fb714c7da5cee63efbcc6fc8c71ab2ce186fa8772719f`.
The hosted unused binding SHA256 is
`fcf73eaffb22b72ecd4629716982784e2831161595696ad7d5a423a0a633f11f`.
Their distinct timestamps/evaluator identities remain distinct.

All three select the same IDs in the same order, with selected-ID SHA256
`ccca7b09ad37e74652d84c26c0c2a823ffaf9a64f9fd911cf72d0e468dec1d0f`
and normalized dataset SHA256
`8470e4913f858788809b421acbc6a07bb0701daadc11062909b45d102dd9f79a`.
They share the registered baseline/candidate, model, dependencies, upstream
locks and retrieval policy. The later-hosted manifest differs from the actual
one only in its binding hash, evaluator commit and frozen timestamp.
Equivalent selected IDs do not make the unused preparation a pre-score audit
of the actual execution.

## Preserve the actual evaluator and unused preparation histories

The active selector, evaluator, binding and manifest preserve the executed
source bytes. The hosted evaluator also binds its asset-verification workflow,
plan, script and report. Its optional-dependency fixture skips only where
`tiktoken` is unavailable in a core-only installation; it runs in the MCP and
frozen comparison environments.

Later source-free failure diagnostics change error-reporting wrappers, not the
successful native/component/export/scoring functions. Those newer helpers stay
on their checkpoint history rather than replacing the active bound evaluator
or weakening its hash checks.

Unused files are archived as:

- [Local binding](../benchmarks/experiments/round3-unused-local-binding.json) and
  [local manifest](../benchmarks/experiments/round3-unused-local-manifest.json).
- [Hosted binding](../benchmarks/experiments/round3-unused-hosted-binding.json) and
  [hosted manifest](../benchmarks/experiments/round3-unused-hosted-manifest.json).

The hosted preparation audit at `3831274` applies to that unused preparation
only. It must not be described as a pre-score audit of the earlier actual run.
Both preparation histories are preserved in Git.

## Disclosure and recovery scope

The encoded-Parquet output disclosed in
[round3-preselection-disclosure.json](../benchmarks/experiments/round3-preselection-disclosure.json)
did not change runtime, ranking, selected IDs or outcome. Its metadata-only
selector wording belongs to the unused local registration. This public corpus
must not be described as wholly unexposed or a new domain.

The selected questions became regression data after their first score. There
was no retuning, replacement query, selection of a faster repeat, second
scoring run or mixing of different-host measurements during reconciliation.

Original performance and quality files are reused by Git object identity.
The recovery restored all **8,082 quality-screen calls** and preserved the
rejection, all **47,320 performance calls** and the startup resource exception.
Offline audits and evidence reconstruction are distinct from measurement.
The actual comparison's original strict assessment checks every registered
stage, attempt axis, payload, budget, source identity and retained ledger.
