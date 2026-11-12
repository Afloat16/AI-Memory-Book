# Round-three independent selection record

The independent reviewer ran the existing deterministic selector **once**, on
2026-11-13 (Asia/Shanghai), after the binding was committed at
`254979496b24d9b5ad0a38f3884d479de0fb5db1`. No retrieval or scoring was run, and
no question, answer or source passage was displayed by this invocation.

```bash
PYTHONPATH=src .venv/bin/python scripts/round3_data.py \
  --parquet .artifacts/round3-source/hotpot-dev-distractor.parquet --freeze
```

The command exited 0. Its existing checks verified committed runtime/evaluator
identities, the frozen source bytes, registered salted-ID selection and prior
cohort exclusions. It wrote
`benchmarks/experiments/round3-hotpot256-manifest.json` without changing the
selector or candidate.

| Item | Verified value |
|---|---|
| Selected questions | 256 |
| Overlap with prior selections | 0 |
| Supplied context paragraphs | 2,559 |
| Required evidence annotations | 607 |
| Selected-ID SHA-256 | `ccca7b09ad37e74652d84c26c0c2a823ffaf9a64f9fd911cf72d0e468dec1d0f` |
| Dataset SHA-256 | `8470e4913f858788809b421acbc6a07bb0701daadc11062909b45d102dd9f79a` |
| Manifest file SHA-256 | `17ebacc267ea1ce5f9ac5e1830331a483955b9929b14163b414384356ead49a9` |
| Binding SHA-256 | `1651d77fc1fbfbc2605fb714c7da5cee63efbcc6fc8c71ab2ce186fa8772719f` |
| Baseline commit | `dd2f88be742ed330269e7dd5915b6f75089d7fef` |
| Candidate commit | `2d199b93f650eccd3dd239178822b31001b880e3` |
| Evaluator commit | `1b596f1744d5719bcd783ff27f919c6d9539a524` |
| Optional project statistics | Excluded (`false`) |

This is a new deterministic selection from the same public HotpotQA source,
not a new domain. The preparatory encoded-byte disclosure is included in the
evaluator binding at
`benchmarks/experiments/round3-preselection-disclosure.json`; this record does
not claim that the underlying corpus was never exposed. No second selection,
outcome filtering or implementation tuning occurred. The manifest must be
committed before the registered evaluator may load it for scoring.
