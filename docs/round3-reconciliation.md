# Reconcile the existing round-three execution

The authoritative comparison uses the earlier hosted registration at
`a0d67b35d074077f43b5cea77954921802d51f44` and
[run 43267797247](https://github.com/Afloat16/AI-Memory-Book/actions/runs/43267797247).
Its registration appeared after this continuation's initial repository
inventory. Creating its dedicated trigger branch returned “Reference already
exists”; this continuation did not start another comparison.

Independent inspection found identical baseline and candidate sources, model,
packages, upstream locks, selected ID array/order and normalized dataset. The
comparison and controller implementations are unchanged.

| Identity | Authoritative hosted preparation | Later local verification |
|---|---|---|
| Binding commit | `c05fd1c453db1e1365ba0c3e4ab359cd8f9017c0` | `254979496b24d9b5ad0a38f3884d479de0fb5db1` |
| Selection commit | `a0d67b35d074077f43b5cea77954921802d51f44` | `6f9050df09982c254bc6809830a85b5abb71f6ca` |
| Binding SHA256 | `740361f1767a942887bdb7639b1be0223ae1c6dc2fc3b941f845d038884f842f` | `1651d77fc1fbfbc2605fb714c7da5cee63efbcc6fc8c71ab2ce186fa8772719f` |
| Selected ID SHA256 | `ccca7b09ad37e74652d84c26c0c2a823ffaf9a64f9fd911cf72d0e468dec1d0f` | Identical, including order |
| Dataset SHA256 | `8470e4913f858788809b421acbc6a07bb0701daadc11062909b45d102dd9f79a` | Identical |

The hosted evaluator also binds its asset-verification workflow, plan, script
and report. Its optional-dependency test correction skips the actual Book
fixture only in core-only installations without `tiktoken`; it runs in the MCP
and frozen comparison jobs. Preserve these original bytes, including its
selector, binding and manifest, for the active experiment's audit.

The later local binding and manifest are archived as
`benchmarks/experiments/round3-unused-local-binding.json` and
`round3-unused-local-manifest.json`. They were never used for retrieval or
scoring. Their disclosure and selection review are records of an independent
reproduction check, not another experiment. Both selections used the fixed
ID-only algorithm: 256 questions and zero historical overlap.

The encoded-Parquet output disclosed in `round3-preselection-disclosure.json`
did not change any runtime, ranking, selection or outcome. Its metadata-only
selector wording is not part of the hosted evaluator; the unused local
registration preserves it. Do not describe this public source as an unexposed
corpus or a new domain.

Original performance and quality files are reused by Git object identity.
Independent reconstruction and offline audits preserve original automatic
decisions and losses. No query measurements are replayed during reconciliation.
