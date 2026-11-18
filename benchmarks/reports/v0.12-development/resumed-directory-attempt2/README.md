# Resumed frozen directory-v2 contracts

Candidate source: `021a384567db5aa64fde155f090d2eb399f55c03`.
The unchanged `benchmarks/directory_navigation.py --protocol-v2` evaluator ran
once with the native backend and once with the Python reference. Both actual
imports and all tracked runtime bytes remained bound to that Git commit before
and after execution. The native extension binary identity is retained.

| Per backend | Native | Python |
| --- | ---: | ---: |
| Passed authored contracts | 119/119 | 119/119 |
| Failed authored contracts | 0 | 0 |
| Locator calls | 130 | 130 |
| Complete original-page reads | 161 | 161 |
| Distinct original pages read | 80 | 80 |
| Raw operation records | 597 | 597 |

These are the same 119 authored contracts on two implementations, not 238
independent cases, an answer-accuracy experiment, or a performance benchmark.
The frozen v2 protocol preserves its original disclosure about the v1 fixture
correction. No protocol, expectation, production source or old result changed.

`native/` and `python/` contain the original protocol copy, raw JSONL and full
report. `execution.json` additionally binds all tracked runtime files to Git,
the evaluator/protocol hashes, exact commands and exit codes. Each backend's
stdout/stderr is retained in its corresponding log.

The separately implemented offline audit rereads the raw operation matrix,
checks hashes and Git source inventories, reconstructs original message turns,
verifies project boundaries and every returned source coordinate, and checks
complete chapter pagination. It also audits the sibling crowding attempt.
`offline-audit.json` records a passing result. This audit makes no retrieval
calls and does not replace the original evaluator's results.

The saved native/Python directory records differ only in the `updated_at`
timestamp on 97 chapter responses, reflecting separate archive ingestion times.
All other saved fields agree. The original timestamps remain in raw JSONL;
this descriptive comparison is not a newly defined acceptance criterion.

Reproduce the offline audit to a new output file from the repository root:

```sh
.venv/bin/python benchmarks/reports/v0.12-development/resumed-directory-attempt2/audit_saved_evidence.py \
  --output /absolute/path/to/new-directory-crowding-audit.json
```

The bound baseline and candidate Git objects must remain available. The auditor
refuses an existing output file. No timing metric or speed claim is collected
by the directory protocol.

The offline auditor preserves the first attempt's verification logic. Only the
candidate commit and sibling crowding output path changed; the exact two
literal substitutions and both script hashes are recorded in
`auditor-binding.json`. Earlier attempt files remain unchanged.
